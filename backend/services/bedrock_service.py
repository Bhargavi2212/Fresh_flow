"""Bedrock wrapper: Titan Embeddings V2 and Nova 2 Lite."""
import json
import logging
import time
from typing import Any

import boto3

from backend.config import get_settings
from backend.services.token_tracker import log_agent_call

logger = logging.getLogger(__name__)


def _get_client():
    settings = get_settings()
    return boto3.client(
        "bedrock-runtime",
        region_name=settings.aws_default_region,
        aws_access_key_id=settings.aws_access_key_id or None,
        aws_secret_access_key=settings.aws_secret_access_key or None,
    )


def embed_text(text: str, dimensions: int = 1024) -> list[float]:
    """
    Embed text using Amazon Titan Text Embeddings V2.
    Returns a list of floats (vector). Uses normalize: true per spec.
    """
    client = _get_client()
    body: dict[str, Any] = {
        "inputText": text,
        "dimensions": dimensions,
        "normalize": True,
    }
    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = client.invoke_model(
                modelId="amazon.titan-embed-text-v2:0",
                body=json.dumps(body),
            )
            body_bytes = response["body"].read()
            result = json.loads(body_bytes)
            emb = result["embedding"]
            # Token usage: Bedrock Titan embed may not return usage; estimate input tokens (~4 chars/token)
            input_tokens = max(1, len(text) // 4)
            log_agent_call("titan_embed", input_tokens, 0, "titan")
            return emb
        except Exception as e:
            if attempt == max_retries - 1:
                raise
            time.sleep(2 ** attempt)
    return []


def invoke_nova(prompt: str) -> str:
    """
    Call Nova 2 Lite with a prompt and return the response text.
    Used for health check and Phase 2 agents.
    If guardrail is configured and content is blocked, logs and returns empty string.
    """
    settings = get_settings()
    client = _get_client()
    body: dict[str, Any] = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 256,
        "messages": [{"role": "user", "content": prompt}],
    }
    kwargs: dict[str, Any] = {
        "modelId": "us.amazon.nova-2-lite-v1:0",
        "body": json.dumps(body),
    }
    if settings.bedrock_guardrail_id:
        kwargs["guardrailIdentifier"] = settings.bedrock_guardrail_id
        kwargs["guardrailVersion"] = settings.bedrock_guardrail_version or "DRAFT"
    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = client.invoke_model(**kwargs)
            result = json.loads(response["body"].read())
            content = result.get("content", [])
            if content and isinstance(content[0].get("text"), str):
                return content[0]["text"]
            if result.get("blockedReason") or result.get("amazonBedrockGuardrailBlock"):
                logger.warning(
                    "Bedrock guardrail blocked content: blockedReason=%s, guardrailBlock=%s",
                    result.get("blockedReason"),
                    result.get("amazonBedrockGuardrailBlock"),
                )
            return ""
        except Exception as e:
            err_name = type(e).__name__
            if "Guardrail" in err_name or "guardrail" in str(e).lower():
                logger.warning("Bedrock guardrail blocked request or response: %s", e)
                return ""
            if attempt == max_retries - 1:
                raise
            time.sleep(2 ** attempt)
    return ""

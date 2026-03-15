"""Strands + Bedrock config: Nova 2 Lite model and Titan embeddings for agents and tools."""
from typing import Literal

from strands.models import BedrockModel

from backend.config import get_settings
from backend.services.bedrock_service import embed_text as _embed_text

__all__ = ["get_bedrock_model", "embed_text"]


def embed_text(text: str, dimensions: int = 1024) -> list[float]:
    """
    Embed text using Titan Text Embeddings V2 (1024 dimensions, normalized).
    Re-exported so agents and tools use a single place for embeddings.
    """
    return _embed_text(text, dimensions=dimensions)


def get_bedrock_model(
    reasoning_effort: Literal["low", "medium", "high"] = "medium",
) -> BedrockModel:
    """
    Return a BedrockModel for Nova 2 Lite with the given extended-thinking effort.
    Order Intake uses "medium"; Inventory uses "low".
    """
    settings = get_settings()
    return BedrockModel(
        model_id="us.amazon.nova-2-lite-v1:0",
        region_name=settings.aws_default_region or "us-east-1",
        streaming=False,
        additional_request_fields={
            "reasoningConfig": {
                "type": "enabled",
                "maxReasoningEffort": reasoning_effort,
            }
        },
    )

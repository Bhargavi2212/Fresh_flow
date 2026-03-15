"""Thread-local token usage tracking for Bedrock (Nova/Titan) and cost estimate."""
import threading
from typing import Any

# Cost per 1M tokens (spec)
NOVA_INPUT_PER_M = 0.06
NOVA_OUTPUT_PER_M = 0.24
TITAN_PER_M = 0.02

_thread_local = threading.local()


def _get_storage() -> dict:
    if not getattr(_thread_local, "token_tracker", None):
        _thread_local.token_tracker = {"calls": [], "total_input": 0, "total_output": 0}
    return _thread_local.token_tracker


def start_tracking() -> None:
    """Start a new tracking session for the current thread (e.g. at start of run_orchestrator)."""
    _thread_local.token_tracker = {"calls": [], "total_input": 0, "total_output": 0}


def log_agent_call(agent_name: str, input_tokens: int, output_tokens: int, model: str = "nova") -> None:
    """
    Log one Bedrock call. model is 'nova' or 'titan'.
    Nova: $0.06/1M input, $0.24/1M output. Titan: $0.02/1M (input+output).
    """
    s = _get_storage()
    s["calls"].append({
        "agent": agent_name,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "model": model,
    })
    s["total_input"] += input_tokens
    s["total_output"] += output_tokens


def get_summary() -> dict[str, Any]:
    """
    Return summary for the current session: total_input_tokens, total_output_tokens,
    cost_estimate_usd, and calls list. Safe to call when no tracking started (returns zeros).
    """
    if not getattr(_thread_local, "token_tracker", None):
        return {
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "cost_estimate_usd": 0.0,
            "calls": [],
        }
    s = _get_storage()
    total_in = s["total_input"]
    total_out = s["total_output"]
    cost = 0.0
    for c in s["calls"]:
        if c.get("model") == "titan":
            cost += (c["input_tokens"] + c["output_tokens"]) / 1_000_000 * TITAN_PER_M
        else:
            cost += c["input_tokens"] / 1_000_000 * NOVA_INPUT_PER_M
            cost += c["output_tokens"] / 1_000_000 * NOVA_OUTPUT_PER_M
    return {
        "total_input_tokens": total_in,
        "total_output_tokens": total_out,
        "cost_estimate_usd": round(cost, 6),
        "calls": list(s["calls"]),
    }


def reset() -> None:
    """Reset the current thread's tracking (e.g. after storing summary)."""
    if getattr(_thread_local, "token_tracker", None):
        _thread_local.token_tracker = {"calls": [], "total_input": 0, "total_output": 0}

"""POST /api/ingest/web and POST /api/ingest/sms — raw order → Orchestrator pipeline."""
import asyncio
import time
from collections import deque
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, HTTPException, Request, Response

from backend.agents.orchestrator import run_orchestrator
from backend.api.schemas import IngestWebRequest, IngestWebResponse
from backend.config import get_settings
from backend.services.database import fetch_one
from backend.services.input_sanitizer import sanitize_order_input
from backend.services.websocket_manager import get_ws_manager

router = APIRouter(prefix="/api/ingest", tags=["ingest"])

# TwiML wording (spec-exact)
TWIML_UNKNOWN_NUMBER = "Hi! We don't recognize this number. Please contact your sales rep to get set up."
SMS_RATE_LIMIT_MESSAGE = "Too many orders from this number. Please try again later."

# SMS rate limit: per phone, count orders in last hour; max 10
_sms_order_times: dict[str, deque] = {}
_SMS_MAX_PER_HOUR = 10
_HOUR_SECS = 3600


def _sms_rate_limit_check(phone: str) -> bool:
    """Return True if under limit, False if over (should reject)."""
    now = time.time()
    if phone not in _sms_order_times:
        _sms_order_times[phone] = deque(maxlen=100)
    q = _sms_order_times[phone]
    while q and q[0] < now - _HOUR_SECS:
        q.popleft()
    if len(q) >= _SMS_MAX_PER_HOUR:
        return False
    q.append(now)
    return True


def _twiml_message(body: str) -> str:
    import xml.sax.saxutils
    escaped = xml.sax.saxutils.escape(body)
    return f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{escaped}</Message></Response>'


async def _process_sms_order(from_phone: str, body: str, customer_id: str, customer_name: str) -> None:
    """Background: run Orchestrator for SMS order; confirmation sent by send_order_confirmation."""
    try:
        await asyncio.to_thread(
            run_orchestrator,
            body,
            customer_id,
            "sms",
            customer_phone=from_phone,
        )
    except Exception:
        pass  # Log but do not crash; confirmation may still have been attempted


@router.post("/sms")
async def ingest_sms(request: Request):
    """
    Twilio webhook: form body From, Body. Look up customer by phone.
    If not found → 200 + TwiML unknown-number message.
    If found → 200 + TwiML ack, then background Orchestrator; confirmation via REST.
    If Twilio not configured → 503.
    """
    settings = get_settings()
    if not settings.twilio_account_sid or not settings.twilio_auth_token or not settings.twilio_phone_number:
        raise HTTPException(
            status_code=503,
            detail="Twilio not configured. Set TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER.",
        )

    form = await request.form()
    from_phone = (form.get("From") or "").strip()
    body_text = (form.get("Body") or "").strip()

    if not from_phone:
        return Response(content=_twiml_message(TWIML_UNKNOWN_NUMBER), media_type="application/xml")

    customer = await fetch_one(
        "SELECT customer_id, name FROM customers WHERE phone = $1",
        from_phone,
    )
    if not customer:
        return Response(content=_twiml_message(TWIML_UNKNOWN_NUMBER), media_type="application/xml")

    if not _sms_rate_limit_check(from_phone):
        return Response(content=_twiml_message(SMS_RATE_LIMIT_MESSAGE), media_type="application/xml")

    customer_id = customer["customer_id"]
    customer_name = (customer["name"] or "there").strip()
    body_text = sanitize_order_input(body_text)
    ack_message = f"Got it, {customer_name}! Processing your order now..."
    try:
        await get_ws_manager().broadcast({
            "type": "order_received",
            "order_id": "pending",
            "customer_name": customer_name,
            "channel": "sms",
            "raw_message": body_text[:500] if body_text else "",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
    except Exception:
        pass
    asyncio.create_task(_process_sms_order(from_phone, body_text, customer_id, customer_name))
    return Response(content=_twiml_message(ack_message), media_type="application/xml")


@router.post("/web", response_model=IngestWebResponse)
async def ingest_web(body: IngestWebRequest):
    """
    Ingest a raw order message via web: validate customer, run Orchestrator (parse → inventory → procure → save → confirm),
    map summary to IngestWebResponse. Full trace stored on the order.
    """
    customer = await fetch_one("SELECT customer_id, name FROM customers WHERE customer_id = $1", body.customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    customer_name = (customer.get("name") or "Customer").strip()

    raw_message = sanitize_order_input(body.message or "")

    try:
        await get_ws_manager().broadcast({
            "type": "order_received",
            "order_id": "pending",
            "customer_name": customer_name,
            "channel": body.channel or "web",
            "raw_message": raw_message[:500],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
    except Exception:
        pass

    try:
        result, summary = await asyncio.wait_for(
            asyncio.to_thread(
                run_orchestrator,
                raw_message,
                body.customer_id,
                body.channel,
                customer_phone="",
            ),
            timeout=60.0,
        )
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="Order processing timed out (60s). Please retry.")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Orchestrator failed: {e}") from e

    if not summary:
        raise HTTPException(
            status_code=502,
            detail="Orchestrator did not return a valid summary JSON.",
        )

    order_id = summary.get("order_id") or ""
    status = summary.get("status") or "needs_review"
    total_amount = summary.get("total_amount")
    if total_amount is not None:
        total_amount = Decimal(str(total_amount))
    confidence_score = summary.get("confidence_score")
    if confidence_score is None:
        confidence_score = 1.0

    parsed_items = summary.get("parsed_items")
    if parsed_items is None:
        parsed_items = []
    elif not isinstance(parsed_items, list):
        parsed_items = []

    procurement_signals = []
    if order_id:
        order_row = await fetch_one("SELECT agent_trace FROM orders WHERE order_id = $1", order_id)
        if order_row and order_row.get("agent_trace"):
            trace = order_row["agent_trace"] or {}
            inv = trace.get("inventory") or {}
            procurement_signals = inv.get("procurement_signals") or inv.get("procurementSignals") or []

    message = summary.get("message")

    return IngestWebResponse(
        order_id=order_id,
        status=status,
        parsed_items=parsed_items,
        procurement_signals=procurement_signals,
        customer_insights=[],
        total_amount=total_amount,
        confidence_score=float(confidence_score),
        message=message,
    )

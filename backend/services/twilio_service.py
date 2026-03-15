"""Twilio SMS sending. Catches failures and returns sent: false so order processing does not crash."""
import logging

from backend.config import get_settings

logger = logging.getLogger(__name__)


def send_sms(to_phone: str, body: str) -> dict:
    """
    Send an SMS via Twilio REST API.
    On missing credentials or API failure: log, return {sent: false, error: "..."}; do not raise.
    """
    settings = get_settings()
    if not settings.twilio_account_sid or not settings.twilio_auth_token or not settings.twilio_phone_number:
        logger.warning("Twilio not configured: missing account_sid, auth_token, or phone_number")
        return {"sent": False, "sid": None, "error": "Twilio not configured"}

    try:
        from twilio.rest import Client

        client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
        message = client.messages.create(
            body=body,
            from_=settings.twilio_phone_number,
            to=to_phone,
        )
        return {"sent": True, "sid": message.sid, "error": None}
    except Exception as e:  # noqa: BLE001
        logger.exception("Twilio send_sms failed: %s", e)
        return {"sent": False, "sid": None, "error": str(e)}

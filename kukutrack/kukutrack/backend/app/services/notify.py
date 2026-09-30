import logging

import httpx

from ..config import settings

log = logging.getLogger("kukutrack.sms")


def send_sms(phone: str, message: str) -> bool:
    """Send an SMS through Africa's Talking. Returns True on success."""
    if not settings.at_api_key:
        log.info("[SMS disabled] to=%s msg=%s", phone, message)
        return False
    base = "https://api.sandbox.africastalking.com" if settings.at_username == "sandbox" else "https://api.africastalking.com"
    data = {"username": settings.at_username, "to": f"+{phone}", "message": message}
    if settings.at_sender:
        data["from"] = settings.at_sender
    try:
        r = httpx.post(
            f"{base}/version1/messaging",
            data=data,
            headers={"apiKey": settings.at_api_key, "Accept": "application/json"},
            timeout=15,
        )
        r.raise_for_status()
        return True
    except httpx.HTTPError as e:
        log.warning("SMS failed: %s", e)
        return False

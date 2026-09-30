import base64
from datetime import datetime

import httpx

from ..config import settings


def _base() -> str:
    return "https://sandbox.safaricom.co.ke" if settings.mpesa_env == "sandbox" else "https://api.safaricom.co.ke"


def _token() -> str:
    r = httpx.get(
        f"{_base()}/oauth/v1/generate?grant_type=client_credentials",
        auth=(settings.mpesa_consumer_key, settings.mpesa_consumer_secret),
        timeout=15,
    )
    r.raise_for_status()
    return r.json()["access_token"]


def stk_push(phone: str, amount: int, reference: str, description: str) -> dict:
    ts = datetime.now().strftime("%Y%m%d%H%M%S")
    password = base64.b64encode(f"{settings.mpesa_shortcode}{settings.mpesa_passkey}{ts}".encode()).decode()
    payload = {
        "BusinessShortCode": settings.mpesa_shortcode,
        "Password": password,
        "Timestamp": ts,
        "TransactionType": "CustomerPayBillOnline",
        "Amount": int(amount),
        "PartyA": phone,
        "PartyB": settings.mpesa_shortcode,
        "PhoneNumber": phone,
        "CallBackURL": f"{settings.public_base_url}/api/billing/mpesa/{settings.callback_secret}",
        "AccountReference": reference[:12],
        "TransactionDesc": description[:13],
    }
    r = httpx.post(
        f"{_base()}/mpesa/stkpush/v1/processrequest",
        json=payload,
        headers={"Authorization": f"Bearer {_token()}"},
        timeout=20,
    )
    r.raise_for_status()
    return r.json()

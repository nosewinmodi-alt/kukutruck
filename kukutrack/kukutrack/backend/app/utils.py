import re
from datetime import date, datetime, timedelta, timezone


def now() -> datetime:
    """Naive UTC timestamp (portable across SQLite/Postgres)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def today() -> date:
    """Today's date in Kenya (UTC+3, no DST)."""
    return (now() + timedelta(hours=3)).date()


def normalize_phone(raw: str) -> str:
    """Return a Kenyan MSISDN as 2547XXXXXXXX / 2541XXXXXXXX (no plus sign)."""
    d = re.sub(r"\D", "", raw or "")
    if len(d) == 10 and d[0] == "0":
        d = "254" + d[1:]
    elif len(d) == 9 and d[0] in "71":
        d = "254" + d
    if not (len(d) == 12 and d.startswith("254") and d[3] in "71"):
        raise ValueError("Enter a valid Kenyan phone number, e.g. 0712345678")
    return d

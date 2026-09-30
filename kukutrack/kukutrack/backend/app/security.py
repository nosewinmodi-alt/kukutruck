import hashlib
import hmac
import os
import time
from datetime import timedelta

import jwt

from .config import settings
from .utils import now


def hash_password(pw: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.scrypt(pw.encode(), salt=salt, n=2**14, r=8, p=1)
    return f"{salt.hex()}${dk.hex()}"


def verify_password(pw: str, stored: str) -> bool:
    try:
        salt_hex, h = stored.split("$")
        dk = hashlib.scrypt(pw.encode(), salt=bytes.fromhex(salt_hex), n=2**14, r=8, p=1)
        return hmac.compare_digest(dk.hex(), h)
    except ValueError:
        return False


def create_token(user_id: int) -> str:
    exp = now() + timedelta(minutes=settings.access_token_minutes)
    return jwt.encode({"sub": str(user_id), "exp": exp}, settings.secret_key, algorithm="HS256")


def decode_token(token: str) -> int:
    return int(jwt.decode(token, settings.secret_key, algorithms=["HS256"])["sub"])


# Naive per-process login throttle (use Redis / a gateway limiter with multiple workers)
_fails: dict[str, list[float]] = {}


def login_blocked(phone: str, limit: int = 5, window: int = 300) -> bool:
    t = time.time()
    _fails[phone] = [x for x in _fails.get(phone, []) if t - x < window]
    return len(_fails[phone]) >= limit


def login_failed(phone: str) -> None:
    _fails.setdefault(phone, []).append(time.time())

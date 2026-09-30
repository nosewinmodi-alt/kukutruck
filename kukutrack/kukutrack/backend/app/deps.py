from typing import Annotated

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from . import models as m
from .db import get_db
from .security import decode_token
from .utils import today

DB = Annotated[Session, Depends(get_db)]
_bearer = HTTPBearer(auto_error=False)


def current_user(db: DB, creds: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> m.User:
    if not creds:
        raise HTTPException(401, "Not authenticated")
    try:
        user = db.get(m.User, decode_token(creds.credentials))
    except (jwt.PyJWTError, ValueError, KeyError):
        raise HTTPException(401, "Invalid or expired token")
    if not user:
        raise HTTPException(401, "User not found")
    return user


def require(*roles: str):
    def dep(user: m.User = Depends(current_user)) -> m.User:
        if user.role not in roles:
            raise HTTPException(403, "You do not have permission for this action")
        return user

    return dep


def paid_plan(db: DB, user: m.User = Depends(current_user)) -> m.User:
    farm = db.get(m.Farm, user.farm_id)
    if not farm.plan_expires_on or farm.plan_expires_on < today():
        raise HTTPException(402, "Subscription expired. Renew via M-Pesa to use this feature.")
    return user


def verified_vet(db: DB, user: m.User = Depends(current_user)) -> m.User:
    farm = db.get(m.Farm, user.farm_id)
    if farm.kind != "vet" or not farm.verified:
        raise HTTPException(403, "A verified veterinarian account is required")
    return user


Auth = Annotated[m.User, Depends(current_user)]
Manager = Annotated[m.User, Depends(require("owner", "manager"))]
Owner = Annotated[m.User, Depends(require("owner"))]
Paid = Annotated[m.User, Depends(paid_plan)]
Vet = Annotated[m.User, Depends(verified_vet)]

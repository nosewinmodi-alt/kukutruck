import hmac
import secrets
from datetime import timedelta

from fastapi import APIRouter, HTTPException
from pathlib import Path

from sqlalchemy import delete, func, or_, select, update

from .. import models as m, schemas as s
from ..config import settings
from ..deps import DB, Auth, Manager, Owner
from ..security import create_token, hash_password, login_blocked, login_failed, verify_password
from ..services.notify import send_sms
from ..utils import now, today

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=s.TokenOut, status_code=201)
def register(body: s.RegisterIn, db: DB):
    if db.scalar(select(m.User).where(m.User.phone == body.phone)):
        raise HTTPException(409, "This phone number is already registered")
    farm = m.Farm(name=body.farm_name, county=body.county, kind=body.account_type, licence_no=body.licence_no, plan_expires_on=today() + timedelta(days=settings.trial_days))
    db.add(farm)
    db.flush()
    user = m.User(farm_id=farm.id, name=body.name, phone=body.phone, password_hash=hash_password(body.password), role="owner", consented_at=now())
    db.add(user)
    db.commit()
    return s.TokenOut(access_token=create_token(user.id), user=s.UserOut.model_validate(user))


@router.post("/login", response_model=s.TokenOut)
def login(body: s.LoginIn, db: DB):
    if login_blocked(body.phone):
        raise HTTPException(429, "Too many attempts. Try again in a few minutes.")
    user = db.scalar(select(m.User).where(m.User.phone == body.phone))
    if not user or not verify_password(body.password, user.password_hash):
        login_failed(body.phone)
        raise HTTPException(401, "Wrong phone number or password")
    return s.TokenOut(access_token=create_token(user.id), user=s.UserOut.model_validate(user))


@router.get("/me", response_model=s.MeOut)
def me(user: Auth, db: DB):
    farm = db.get(m.Farm, user.farm_id)
    active = bool(farm.plan_expires_on and farm.plan_expires_on >= today())
    return s.MeOut(**s.UserOut.model_validate(user).model_dump(), farm_name=farm.name, plan_expires_on=farm.plan_expires_on, plan_active=active, account_type=farm.kind, verified=farm.verified)


@router.get("/staff", response_model=list[s.UserOut])
def list_staff(user: Manager, db: DB):
    return db.scalars(select(m.User).where(m.User.farm_id == user.farm_id).order_by(m.User.id)).all()


@router.post("/staff", response_model=s.UserOut, status_code=201)
def add_staff(body: s.StaffIn, user: Owner, db: DB):
    if db.scalar(select(m.User).where(m.User.phone == body.phone)):
        raise HTTPException(409, "This phone number is already registered")
    u = m.User(farm_id=user.farm_id, name=body.name, phone=body.phone, password_hash=hash_password(body.password), role=body.role)
    db.add(u)
    db.commit()
    return u


# ---------- password reset by SMS code ----------
def _code_hash(phone: str, code: str) -> str:
    return hmac.new(settings.secret_key.encode(), f"{phone}:{code}".encode(), "sha256").hexdigest()


@router.post("/forgot")
def forgot(body: s.ForgotIn, db: DB):
    """Always answers the same way so phone numbers cannot be probed. Max 3 codes per hour per number."""
    user = db.scalar(select(m.User).where(m.User.phone == body.phone))
    recent = db.scalar(select(func.count()).select_from(m.OtpCode).where(m.OtpCode.phone == body.phone, m.OtpCode.created_at > now() - timedelta(hours=1)))
    if user and recent < 3:
        code = f"{secrets.randbelow(10**6):06d}"
        db.add(m.OtpCode(phone=body.phone, code_hash=_code_hash(body.phone, code), expires_at=now() + timedelta(minutes=10)))
        db.commit()
        send_sms(body.phone, f"KukuTrack code: {code}. Valid for 10 minutes. Never share it.")
    return {"message": "If this number is registered, a code has been sent by SMS."}


@router.post("/reset")
def reset(body: s.ResetIn, db: DB):
    otp = db.scalar(select(m.OtpCode).where(m.OtpCode.phone == body.phone, m.OtpCode.used.is_(False), m.OtpCode.expires_at > now()).order_by(m.OtpCode.id.desc()))
    if not otp or otp.attempts >= 5:
        raise HTTPException(400, "Invalid or expired code")
    if not hmac.compare_digest(otp.code_hash, _code_hash(body.phone, body.code)):
        otp.attempts += 1
        db.commit()
        raise HTTPException(400, "Invalid or expired code")
    user = db.scalar(select(m.User).where(m.User.phone == body.phone))
    if not user:
        raise HTTPException(400, "Invalid or expired code")
    user.password_hash = hash_password(body.new_password)
    otp.used = True
    db.commit()
    return {"message": "Password changed. You can log in now."}


# ---------- Data Protection Act 2019: access + erasure ----------
def _dump(rows) -> list[dict]:
    out = []
    for r in rows:
        d = {c.name: getattr(r, c.name) for c in r.__table__.columns if c.name != "password_hash"}
        out.append({k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in d.items()})
    return out


@router.get("/account/export")
def export_account(user: Owner, db: DB):
    """Everything we hold about this account, as JSON (right of access / portability)."""
    fid = user.farm_id
    flock_ids = select(m.Flock.id).where(m.Flock.farm_id == fid)
    case_ids = select(m.VetCase.id).where(m.VetCase.farm_id == fid)

    def rows(model, cond):
        return _dump(db.scalars(select(model).where(cond)).all())

    return {
        "exported_at": now().isoformat(),
        "farm": _dump([db.get(m.Farm, fid)])[0],
        "users": rows(m.User, m.User.farm_id == fid),
        "houses": rows(m.House, m.House.farm_id == fid),
        "flocks": rows(m.Flock, m.Flock.farm_id == fid),
        "daily_logs": rows(m.DailyLog, m.DailyLog.flock_id.in_(flock_ids)),
        "vaccinations": rows(m.VaccinationTask, m.VaccinationTask.flock_id.in_(flock_ids)),
        "inventory": rows(m.InventoryItem, m.InventoryItem.farm_id == fid),
        "transactions": rows(m.Transaction, m.Transaction.farm_id == fid),
        "payments": rows(m.Payment, m.Payment.farm_id == fid),
        "listings": rows(m.Listing, m.Listing.farm_id == fid),
        "vet_cases": rows(m.VetCase, m.VetCase.farm_id == fid),
        "vet_messages": rows(m.VetMessage, m.VetMessage.case_id.in_(case_ids)),
    }


def _erase_farm(db, fid: int) -> None:
    users = select(m.User.id).where(m.User.farm_id == fid)
    flock_ids = select(m.Flock.id).where(m.Flock.farm_id == fid)
    case_ids = select(m.VetCase.id).where(m.VetCase.farm_id == fid)
    listing_ids = select(m.Listing.id).where(m.Listing.farm_id == fid)
    phones = [u.phone for u in db.scalars(select(m.User).where(m.User.farm_id == fid))]
    for p in db.scalars(select(m.VetPhoto).where(m.VetPhoto.case_id.in_(case_ids))):
        (Path(settings.upload_dir) / p.filename).unlink(missing_ok=True)
    # detach this account's footprint on other accounts' records
    db.execute(update(m.VetMessage).where(m.VetMessage.author_id.in_(users)).values(author_id=None))
    db.execute(update(m.VetCase).where(m.VetCase.assigned_vet_id.in_(users)).values(assigned_vet_id=None))
    db.execute(update(m.Inquiry).where(m.Inquiry.from_user_id.in_(users)).values(from_user_id=None))
    # then remove everything it owns
    db.execute(delete(m.VetPhoto).where(m.VetPhoto.case_id.in_(case_ids)))
    db.execute(delete(m.VetMessage).where(m.VetMessage.case_id.in_(case_ids)))
    db.execute(delete(m.VetCase).where(m.VetCase.farm_id == fid))
    db.execute(delete(m.Inquiry).where(or_(m.Inquiry.from_farm_id == fid, m.Inquiry.listing_id.in_(listing_ids))))
    db.execute(delete(m.Listing).where(m.Listing.farm_id == fid))
    db.execute(delete(m.ReportShare).where(m.ReportShare.farm_id == fid))
    db.execute(delete(m.DailyLog).where(m.DailyLog.flock_id.in_(flock_ids)))
    db.execute(delete(m.VaccinationTask).where(m.VaccinationTask.flock_id.in_(flock_ids)))
    for model in (m.Transaction, m.InventoryItem, m.Flock, m.House, m.Payment, m.User):
        db.execute(delete(model).where(model.farm_id == fid))
    db.execute(delete(m.OtpCode).where(m.OtpCode.phone.in_(phones)))
    db.execute(delete(m.Farm).where(m.Farm.id == fid))


@router.delete("/account")
def delete_account(body: s.DeleteAccountIn, user: Owner, db: DB):
    """Permanently erase the account and all its data (right of erasure). Irreversible."""
    if not verify_password(body.password, user.password_hash):
        raise HTTPException(403, "Wrong password")
    _erase_farm(db, user.farm_id)
    db.commit()
    return {"message": "Account and all data deleted"}

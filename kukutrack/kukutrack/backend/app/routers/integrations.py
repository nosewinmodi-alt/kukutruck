import hmac
import logging
from datetime import timedelta

import httpx
from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import PlainTextResponse
from pydantic import ValidationError
from sqlalchemy import select

from .. import models as m, schemas as s
from ..config import settings
from ..deps import DB, Auth, Owner
from ..services import logic, mpesa
from ..utils import normalize_phone, today

log = logging.getLogger("kukutrack.integrations")
router = APIRouter(tags=["integrations"])


# ---------- offline sync ----------
@router.post("/sync/push")
def sync_push(body: s.SyncPush, user: Auth, db: DB):
    """Apply a batch of offline-queued records. Idempotent: logs upsert by (flock, date), transactions dedupe by client_id."""
    applied, errors = {"logs": 0, "transactions": 0}, []
    if user.role == "vet":
        raise HTTPException(403, "Vets have read-only access")
    for i, raw in enumerate(body.logs):
        try:
            d = s.LogSync.model_validate(raw).model_dump()
            logic.upsert_log(db, logic.get_flock(db, user, d["flock_id"]), d, user.id)
            applied["logs"] += 1
        except (ValidationError, HTTPException) as e:
            errors.append({"type": "log", "index": i, "error": getattr(e, "detail", str(e))})
    if body.transactions and user.role not in ("owner", "manager"):
        errors.append({"type": "transaction", "error": "not permitted"})
    else:
        for i, raw in enumerate(body.transactions):
            try:
                d = s.TxIn.model_validate(raw).model_dump()
                logic.add_transaction(db, user, d)
                applied["transactions"] += 1
            except (ValidationError, HTTPException) as e:
                errors.append({"type": "transaction", "index": i, "error": getattr(e, "detail", str(e))})
    db.commit()
    return {"applied": applied, "errors": errors}


# ---------- M-Pesa subscription billing ----------
@router.post("/billing/checkout")
def checkout(body: s.CheckoutIn, user: Owner, db: DB):
    phone = normalize_phone(body.phone) if body.phone else user.phone
    try:
        res = mpesa.stk_push(phone, settings.plan_price_kes, f"KUKU{user.farm_id}", "KukuTrack")
    except (httpx.HTTPError, KeyError) as e:
        log.warning("STK push failed: %s", e)
        raise HTTPException(502, "Could not start M-Pesa payment. Try again shortly.")
    db.add(m.Payment(farm_id=user.farm_id, phone=phone, amount=settings.plan_price_kes, checkout_request_id=res["CheckoutRequestID"]))
    db.commit()
    return {"message": "Check your phone and enter your M-Pesa PIN", "checkout_request_id": res["CheckoutRequestID"]}


@router.post("/billing/mpesa/{secret}")
async def mpesa_callback(secret: str, request: Request, db: DB):
    if not hmac.compare_digest(secret, settings.callback_secret):
        raise HTTPException(404)
    cb = (await request.json()).get("Body", {}).get("stkCallback", {})
    pay = db.scalar(select(m.Payment).where(m.Payment.checkout_request_id == cb.get("CheckoutRequestID", "")))
    if pay and pay.status == "pending":
        items = {i["Name"]: i.get("Value") for i in cb.get("CallbackMetadata", {}).get("Item", [])}
        if cb.get("ResultCode") == 0 and int(items.get("Amount", 0)) >= pay.amount:
            pay.status, pay.receipt = "paid", str(items.get("MpesaReceiptNumber"))
            farm = db.get(m.Farm, pay.farm_id)
            start = max(today(), farm.plan_expires_on or today())
            farm.plan_expires_on = start + timedelta(days=30)
        else:
            pay.status = "failed"
        db.commit()
    return {"ResultCode": 0, "ResultDesc": "Accepted"}


# ---------- USSD (Africa's Talking) for feature phones ----------
@router.post("/ussd/{secret}", response_class=PlainTextResponse)
def ussd(secret: str, db: DB, phoneNumber: str = Form(...), text: str = Form("")):
    if not hmac.compare_digest(secret, settings.callback_secret):
        raise HTTPException(404)
    try:
        phone = normalize_phone(phoneNumber)
    except ValueError:
        return "END Invalid number"
    user = db.scalar(select(m.User).where(m.User.phone == phone))
    if not user:
        return "END Number not registered. Register on the KukuTrack app first."
    flocks = db.scalars(select(m.Flock).where(m.Flock.farm_id == user.farm_id, m.Flock.status == "active").order_by(m.Flock.id).limit(8)).all()
    p = text.split("*") if text else []
    if not p:
        return "CON KukuTrack\n1. Record today\n2. Vaccinations due\n3. Farm summary"
    if p[0] == "2":
        tasks = db.scalars(
            select(m.VaccinationTask).join(m.Flock).where(m.Flock.farm_id == user.farm_id, m.Flock.status == "active", m.VaccinationTask.done_on.is_(None), m.VaccinationTask.due_date <= today() + timedelta(days=7)).order_by(m.VaccinationTask.due_date).limit(5)
        ).all()
        names = {f.id: f.name for f in flocks}
        return "END " + ("\n".join(f"{t.due_date:%d/%m} {names.get(t.flock_id, '')}: {t.vaccine[:28]}" for t in tasks) or "Nothing due this week")
    if p[0] == "3":
        rows = [logic.flock_summary(db, f) for f in flocks]
        return "END " + ("\n".join(f"{r['name']}: {r['kpis']['live_birds']} birds, mort {r['kpis']['mortality_pct']}%" for r in rows) or "No active flocks")
    if p[0] != "1":
        return "END Invalid choice"
    if user.role == "vet":
        return "END Vets have read-only access"
    if not flocks:
        return "END No active flocks"
    if len(p) == 1:
        return "CON Choose flock:\n" + "\n".join(f"{i}. {f.name[:20]}" for i, f in enumerate(flocks, 1))
    try:
        flock = flocks[int(p[1]) - 1]
        if len(p) == 2:
            return "CON Eggs collected today? (0 if none)"
        if len(p) == 3:
            return "CON Birds that died today?"
        if len(p) == 4:
            return "CON Feed used today (kg)?"
        data = {"log_date": today(), "eggs": max(int(p[2]), 0), "deaths": max(int(p[3]), 0), "feed_kg": max(float(p[4]), 0)}
        logic.upsert_log(db, flock, data, user.id)
        db.commit()
        return f"END Saved for {flock.name}: {data['eggs']} eggs, {data['deaths']} dead, {data['feed_kg']}kg feed."
    except (ValueError, IndexError):
        return "END Invalid input. Dial again."
    except HTTPException as e:
        return f"END {e.detail}"

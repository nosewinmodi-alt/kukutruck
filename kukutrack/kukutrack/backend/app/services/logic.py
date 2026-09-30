from datetime import date, timedelta

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import models as m
from ..utils import now, today
from . import kpi


def get_flock(db: Session, user: m.User, flock_id: int) -> m.Flock:
    f = db.get(m.Flock, flock_id)
    if not f or f.farm_id != user.farm_id:  # tenant isolation
        raise HTTPException(404, "Flock not found")
    return f


def upsert_log(db: Session, flock: m.Flock, data: dict, user_id: int | None) -> m.DailyLog:
    day: date = data["log_date"]
    if flock.status != "active":
        raise HTTPException(409, "Flock is closed")
    if day > today() + timedelta(days=1):
        raise HTTPException(422, "Log date is in the future")
    if day < flock.placed_on:
        raise HTTPException(422, "Log date is before the flock was placed")
    log = db.scalar(select(m.DailyLog).where(m.DailyLog.flock_id == flock.id, m.DailyLog.log_date == day))
    if not log:
        log = m.DailyLog(flock_id=flock.id, log_date=day)
        db.add(log)
    for k, v in data.items():
        if k not in ("log_date", "flock_id"):
            setattr(log, k, v)
    log.recorded_by = user_id
    log.updated_at = now()
    return log


def add_transaction(db: Session, user: m.User, data: dict) -> tuple[m.Transaction, bool]:
    """Idempotent on (farm, client_id). Returns (tx, created)."""
    if data.get("flock_id"):
        get_flock(db, user, data["flock_id"])
    cid = data.get("client_id")
    if cid:
        existing = db.scalar(select(m.Transaction).where(m.Transaction.farm_id == user.farm_id, m.Transaction.client_id == cid))
        if existing:
            return existing, False
    tx = m.Transaction(farm_id=user.farm_id, created_by=user.id, **data)
    db.add(tx)
    return tx, True


def flock_summary(db: Session, f: m.Flock) -> dict:
    logs = db.scalars(select(m.DailyLog).where(m.DailyLog.flock_id == f.id).order_by(m.DailyLog.log_date)).all()
    totals = dict(
        db.execute(
            select(m.Transaction.kind, func.coalesce(func.sum(m.Transaction.amount), 0))
            .where(m.Transaction.flock_id == f.id)
            .group_by(m.Transaction.kind)
        ).all()
    )
    # Chick purchase is counted automatically as an expense - do not log it again.
    expenses = totals.get("expense", 0) + f.cost_per_chick * f.initial_count
    k_logs = [kpi.Log(l.log_date, l.eggs, l.cracked, l.deaths, l.feed_kg, l.water_l, l.avg_weight_g) for l in logs]
    kp = kpi.compute_kpis(f.kind, f.initial_count, k_logs, totals.get("income", 0), expenses)
    alerts = kpi.compute_alerts(f.kind, f.initial_count, k_logs)
    overdue = db.scalar(
        select(func.count()).select_from(m.VaccinationTask).where(
            m.VaccinationTask.flock_id == f.id, m.VaccinationTask.done_on.is_(None), m.VaccinationTask.due_date <= today() + timedelta(days=2)
        )
    )
    if overdue and f.status == "active":
        alerts.append({"code": "vaccination_due", "level": "warn", "value": overdue})
    return {
        "id": f.id, "name": f.name, "kind": f.kind, "breed": f.breed, "status": f.status,
        "initial_count": f.initial_count, "placed_on": f.placed_on,
        "age_days": (today() - f.placed_on).days, "kpis": kp, "alerts": alerts,
        "logged_today": bool(logs and logs[-1].log_date == today()),
    }

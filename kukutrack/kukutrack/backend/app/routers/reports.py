import csv
import io
from datetime import timedelta

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select

from .. import models as m
from ..deps import DB, Auth, Paid
from ..services import logic
from ..utils import today

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/dashboard")
def dashboard(user: Auth, db: DB):
    flocks = db.scalars(select(m.Flock).where(m.Flock.farm_id == user.farm_id, m.Flock.status == "active")).all()
    sums = [logic.flock_summary(db, f) for f in flocks]
    ids = [f.id for f in flocks]
    eggs_today = eggs_7d = 0
    if ids:
        base = select(func.coalesce(func.sum(m.DailyLog.eggs), 0)).where(m.DailyLog.flock_id.in_(ids))
        eggs_today = db.scalar(base.where(m.DailyLog.log_date == today()))
        eggs_7d = db.scalar(base.where(m.DailyLog.log_date > today() - timedelta(days=7)))
    month_start = today().replace(day=1)
    tot = dict(db.execute(
        select(m.Transaction.kind, func.coalesce(func.sum(m.Transaction.amount), 0))
        .where(m.Transaction.farm_id == user.farm_id, m.Transaction.tx_date >= month_start).group_by(m.Transaction.kind)
    ).all()) if user.role in ("owner", "manager") else {}
    low = db.scalars(select(m.InventoryItem).where(m.InventoryItem.farm_id == user.farm_id, m.InventoryItem.quantity <= m.InventoryItem.reorder_level, m.InventoryItem.reorder_level > 0)).all()
    alerts = [{**a, "flock": x["name"], "flock_id": x["id"]} for x in sums for a in x["alerts"]]
    alerts += [{"code": "low_stock", "level": "warn", "flock": i.name, "value": i.quantity, "unit": i.unit} for i in low]
    return {
        "active_flocks": len(flocks),
        "live_birds": sum(x["kpis"]["live_birds"] for x in sums),
        "eggs_today": eggs_today, "eggs_7d": eggs_7d,
        "not_logged_today": [{"id": x["id"], "name": x["name"]} for x in sums if not x["logged_today"]],
        "month_income": tot.get("income", 0), "month_expenses": tot.get("expense", 0),
        "alerts": alerts,
    }


@router.get("/export.csv")
def export_csv(user: Paid, db: DB, kind: str = Query("flocks", pattern="^(flocks|transactions)$")):
    buf = io.StringIO()
    w = csv.writer(buf)
    if kind == "flocks":
        w.writerow(["flock", "type", "placed_on", "status", "initial_birds", "live_birds", "mortality_pct", "eggs", "hen_day_pct", "fcr", "income_kes", "expenses_kes", "profit_kes"])
        for f in db.scalars(select(m.Flock).where(m.Flock.farm_id == user.farm_id).order_by(m.Flock.placed_on)):
            x = logic.flock_summary(db, f)
            k = x["kpis"]
            w.writerow([f.name, f.kind, f.placed_on, f.status, f.initial_count, k["live_birds"], k["mortality_pct"], k["total_eggs"], k["hen_day_pct"], k["fcr"], k["income"], k["expenses"], k["profit"]])
    else:
        w.writerow(["date", "type", "category", "amount_kes", "flock_id", "description"])
        for t in db.scalars(select(m.Transaction).where(m.Transaction.farm_id == user.farm_id).order_by(m.Transaction.tx_date)):
            w.writerow([t.tx_date, t.kind, t.category, t.amount, t.flock_id, t.description])
    buf.seek(0)
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv", headers={"Content-Disposition": f"attachment; filename=kukutrack-{kind}-{today()}.csv"})

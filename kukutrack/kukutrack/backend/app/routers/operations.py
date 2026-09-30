from datetime import timedelta

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select

from .. import models as m, schemas as s
from ..deps import DB, Auth, Manager
from ..services import logic, vaccination
from ..utils import now, today

router = APIRouter(tags=["operations"])


# ---------- houses ----------
@router.get("/houses", response_model=list[s.HouseOut])
def houses(user: Auth, db: DB):
    return db.scalars(select(m.House).where(m.House.farm_id == user.farm_id)).all()


@router.post("/houses", response_model=s.HouseOut, status_code=201)
def add_house(body: s.HouseIn, user: Manager, db: DB):
    h = m.House(farm_id=user.farm_id, **body.model_dump())
    db.add(h)
    db.commit()
    return h


# ---------- flocks ----------
@router.get("/flocks")
def flocks(user: Auth, db: DB, status: str = Query("active", pattern="^(active|closed|all)$")):
    q = select(m.Flock).where(m.Flock.farm_id == user.farm_id).order_by(m.Flock.placed_on.desc())
    if status != "all":
        q = q.where(m.Flock.status == status)
    return [logic.flock_summary(db, f) for f in db.scalars(q)]


@router.post("/flocks", response_model=s.FlockOut, status_code=201)
def add_flock(body: s.FlockIn, user: Manager, db: DB):
    if body.house_id and not db.scalar(select(m.House).where(m.House.id == body.house_id, m.House.farm_id == user.farm_id)):
        raise HTTPException(404, "House not found")
    f = m.Flock(farm_id=user.farm_id, **body.model_dump())
    db.add(f)
    db.flush()
    for due, name in vaccination.schedule(f.kind, f.placed_on):
        db.add(m.VaccinationTask(flock_id=f.id, vaccine=name, due_date=due))
    db.commit()
    return f


@router.get("/flocks/{flock_id}")
def flock_detail(flock_id: int, user: Auth, db: DB):
    return logic.flock_summary(db, logic.get_flock(db, user, flock_id))


@router.post("/flocks/{flock_id}/close", response_model=s.FlockOut)
def close_flock(flock_id: int, user: Manager, db: DB):
    f = logic.get_flock(db, user, flock_id)
    f.status, f.closed_on = "closed", today()
    db.commit()
    return f


# ---------- daily logs ----------
@router.put("/flocks/{flock_id}/logs", response_model=s.LogOut)
def put_log(flock_id: int, body: s.LogIn, user: Auth, db: DB):
    if user.role == "vet":
        raise HTTPException(403, "Vets have read-only access")
    log = logic.upsert_log(db, logic.get_flock(db, user, flock_id), body.model_dump(), user.id)
    db.commit()
    return log


@router.get("/flocks/{flock_id}/logs", response_model=list[s.LogOut])
def get_logs(flock_id: int, user: Auth, db: DB, limit: int = Query(14, ge=1, le=366)):
    logic.get_flock(db, user, flock_id)
    q = select(m.DailyLog).where(m.DailyLog.flock_id == flock_id).order_by(m.DailyLog.log_date.desc()).limit(limit)
    return db.scalars(q).all()


# ---------- vaccinations ----------
@router.get("/vaccinations", response_model=list[s.VaccOut])
def vaccinations(user: Auth, db: DB, flock_id: int | None = None, pending_only: bool = False):
    q = (
        select(m.VaccinationTask).join(m.Flock).where(m.Flock.farm_id == user.farm_id)
        .order_by(m.VaccinationTask.due_date)
    )
    if flock_id:
        q = q.where(m.VaccinationTask.flock_id == flock_id)
    if pending_only:
        q = q.where(m.VaccinationTask.done_on.is_(None), m.Flock.status == "active")
    return db.scalars(q).all()


@router.post("/vaccinations/{task_id}/done", response_model=s.VaccOut)
def vaccination_done(task_id: int, user: Auth, db: DB):
    if user.role == "vet":
        pass  # vets may sign off treatments
    t = db.get(m.VaccinationTask, task_id)
    if not t or logic.get_flock(db, user, t.flock_id) is None:
        raise HTTPException(404, "Task not found")
    t.done_on = today()
    db.commit()
    return t


# ---------- inventory ----------
@router.get("/inventory", response_model=list[s.InvOut])
def inventory(user: Auth, db: DB):
    return db.scalars(select(m.InventoryItem).where(m.InventoryItem.farm_id == user.farm_id).order_by(m.InventoryItem.name)).all()


@router.post("/inventory", response_model=s.InvOut, status_code=201)
def add_item(body: s.InvIn, user: Manager, db: DB):
    it = m.InventoryItem(farm_id=user.farm_id, **body.model_dump())
    db.add(it)
    db.commit()
    return it


@router.post("/inventory/{item_id}/adjust", response_model=s.InvOut)
def adjust_item(item_id: int, body: s.AdjustIn, user: Auth, db: DB):
    it = db.get(m.InventoryItem, item_id)
    if not it or it.farm_id != user.farm_id:
        raise HTTPException(404, "Item not found")
    if it.quantity + body.delta < 0:
        raise HTTPException(422, "Not enough stock")
    it.quantity += body.delta
    db.commit()
    return it


# ---------- finance ----------
@router.get("/transactions", response_model=list[s.TxOut])
def transactions(user: Manager, db: DB, flock_id: int | None = None, limit: int = Query(100, ge=1, le=1000)):
    q = select(m.Transaction).where(m.Transaction.farm_id == user.farm_id).order_by(m.Transaction.tx_date.desc(), m.Transaction.id.desc()).limit(limit)
    if flock_id:
        q = q.where(m.Transaction.flock_id == flock_id)
    return db.scalars(q).all()


@router.post("/transactions", response_model=s.TxOut, status_code=201)
def add_tx(body: s.TxIn, user: Manager, db: DB):
    tx, _ = logic.add_transaction(db, user, body.model_dump())
    db.commit()
    return tx

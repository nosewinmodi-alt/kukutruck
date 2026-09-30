"""Photo-based vet consultation. Verified vets (KVB licence checked by an admin) can see and answer every open case."""
import uuid
from datetime import timedelta
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import func, select

from .. import models as m, schemas as s
from ..config import settings
from ..deps import DB, Auth, Vet
from ..services import logic
from ..services.notify import send_sms
from ..utils import now

router = APIRouter(prefix="/vet", tags=["vet"])
MAX_BYTES, MAX_PHOTOS = 3 * 1024 * 1024, 5


def _sniff(head: bytes):
    if head.startswith(b"\xff\xd8\xff"):
        return "jpg", "image/jpeg"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png", "image/png"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "webp", "image/webp"
    return None


def _case(db, user: m.User, case_id: int) -> tuple[m.VetCase, bool]:
    """Return (case, viewer_is_verified_vet). Farms only see their own cases."""
    c = db.get(m.VetCase, case_id)
    if not c:
        raise HTTPException(404, "Case not found")
    if c.farm_id == user.farm_id:
        return c, False
    farm = db.get(m.Farm, user.farm_id)
    if farm.kind == "vet" and farm.verified:
        return c, True
    raise HTTPException(404, "Case not found")


def _brief(db, c: m.VetCase) -> dict:
    farm = db.get(m.Farm, c.farm_id)
    flock = db.get(m.Flock, c.flock_id) if c.flock_id else None
    return {"id": c.id, "title": c.title, "urgency": c.urgency, "status": c.status, "disease": c.disease,
            "farm_name": farm.name, "county": farm.county, "flock_kind": flock.kind if flock else None,
            "created_at": c.created_at, "updated_at": c.updated_at}


@router.post("/cases", status_code=201)
def create_case(body: s.VetCaseIn, user: Auth, db: DB):
    farm = db.get(m.Farm, user.farm_id)
    if farm.kind != "farm" or user.role == "vet":
        raise HTTPException(403, "Only farm accounts can open cases")
    if body.flock_id:
        logic.get_flock(db, user, body.flock_id)
    c = m.VetCase(farm_id=user.farm_id, created_by=user.id, **body.model_dump())
    db.add(c)
    db.commit()
    return _brief(db, c)


@router.get("/cases")
def cases(user: Auth, db: DB, status: str = Query("open", pattern="^(open|all)$")):
    farm = db.get(m.Farm, user.farm_id)
    q = select(m.VetCase)
    if farm.kind == "vet":
        if not farm.verified:
            raise HTTPException(403, "Your vet account is awaiting verification")
    else:
        q = q.where(m.VetCase.farm_id == user.farm_id)
    if status == "open":
        q = q.where(m.VetCase.status != "closed")
    rows = list(db.scalars(q.order_by(m.VetCase.updated_at.desc()).limit(200)))
    rows.sort(key=lambda c: c.urgency != "urgent")  # stable: urgent first
    return [_brief(db, c) for c in rows]


@router.get("/cases/{case_id}")
def case_detail(case_id: int, user: Auth, db: DB):
    c, is_vet = _case(db, user, case_id)
    d = _brief(db, c) | {"symptoms": c.symptoms, "affected_birds": c.affected_birds, "flock": None}
    if c.flock_id:
        snap = logic.flock_summary(db, db.get(m.Flock, c.flock_id))
        if is_vet:  # vets never see the farm's finances
            for k in ("income", "expenses", "profit", "cost_per_tray"):
                snap["kpis"].pop(k, None)
        d["flock"] = snap
    msgs = db.scalars(select(m.VetMessage).where(m.VetMessage.case_id == c.id).order_by(m.VetMessage.id)).all()
    names = {u.id: u.name for u in db.scalars(select(m.User).where(m.User.id.in_([x.author_id for x in msgs if x.author_id])))}
    d["messages"] = [{"id": x.id, "author": names.get(x.author_id, "Deleted user"), "from_vet": x.from_vet, "body": x.body, "created_at": x.created_at} for x in msgs]
    d["photos"] = [p.id for p in db.scalars(select(m.VetPhoto).where(m.VetPhoto.case_id == c.id).order_by(m.VetPhoto.id))]
    return d


@router.post("/cases/{case_id}/messages", status_code=201)
def post_message(case_id: int, body: s.MessageIn, user: Auth, db: DB):
    c, is_vet = _case(db, user, case_id)
    if user.role == "vet" and not is_vet:
        raise HTTPException(403, "Read-only access")
    if c.status == "closed":
        raise HTTPException(409, "This case is closed")
    db.add(m.VetMessage(case_id=c.id, author_id=user.id, from_vet=is_vet, body=body.body))
    if is_vet:
        c.assigned_vet_id = c.assigned_vet_id or user.id
        c.status = "answered"
    else:
        c.status = "open"
    c.updated_at = now()
    db.commit()
    if is_vet:
        creator = db.get(m.User, c.created_by)
        send_sms(creator.phone, f"KukuTrack: a vet replied to your case '{c.title[:40]}'. Open the app > Vet.")
    return {"ok": True}


@router.post("/cases/{case_id}/photos", status_code=201)
def upload_photo(case_id: int, file: UploadFile, user: Auth, db: DB):
    c, is_vet = _case(db, user, case_id)
    if is_vet or user.role == "vet":
        raise HTTPException(403, "Only the farm can add photos")
    if c.status == "closed":
        raise HTTPException(409, "This case is closed")
    if db.scalar(select(func.count()).select_from(m.VetPhoto).where(m.VetPhoto.case_id == c.id)) >= MAX_PHOTOS:
        raise HTTPException(409, f"Maximum {MAX_PHOTOS} photos per case")
    data = file.file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "Photo is larger than 3 MB")
    kind = _sniff(data[:12])
    if not kind:
        raise HTTPException(415, "Only JPEG, PNG or WebP photos are accepted")
    ext, ctype = kind
    name = f"{uuid.uuid4().hex}.{ext}"
    folder = Path(settings.upload_dir)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_bytes(data)
    p = m.VetPhoto(case_id=c.id, filename=name, content_type=ctype, size=len(data))
    db.add(p)
    db.commit()
    return {"id": p.id}


@router.get("/photos/{photo_id}")
def get_photo(photo_id: int, user: Auth, db: DB):
    p = db.get(m.VetPhoto, photo_id)
    if not p:
        raise HTTPException(404, "Photo not found")
    _case(db, user, p.case_id)  # same access rule as the case
    path = Path(settings.upload_dir) / p.filename
    if not path.exists():
        raise HTTPException(404, "Photo not found")
    return FileResponse(path, media_type=p.content_type, headers={"Cache-Control": "private, max-age=86400", "X-Content-Type-Options": "nosniff"})


@router.post("/cases/{case_id}/diagnosis")
def diagnose(case_id: int, body: s.DiagnosisIn, user: Vet, db: DB):
    c, _ = _case(db, user, case_id)
    c.disease = body.disease.strip()
    c.updated_at = now()
    db.add(m.VetMessage(case_id=c.id, author_id=user.id, from_vet=True, body=f"Suspected: {c.disease}"))
    db.commit()
    return {"disease": c.disease}


@router.post("/cases/{case_id}/close")
def close_case(case_id: int, user: Auth, db: DB):
    c, is_vet = _case(db, user, case_id)
    if user.role == "vet" and not is_vet:
        raise HTTPException(403, "Read-only access")
    c.status, c.updated_at = "closed", now()
    db.commit()
    return {"status": "closed"}


@router.get("/outbreaks")
def outbreaks(user: Auth, db: DB, days: int = Query(30, ge=1, le=180)):
    """County-level counts of vet-diagnosed diseases. Aggregates only, no farm identities."""
    rows = db.execute(
        select(m.Farm.county, m.VetCase.disease, func.count(m.VetCase.id))
        .select_from(m.VetCase).join(m.Farm, m.Farm.id == m.VetCase.farm_id)
        .where(m.VetCase.disease.is_not(None), m.VetCase.created_at >= now() - timedelta(days=days))
        .group_by(m.Farm.county, m.VetCase.disease)
    ).all()
    return sorted(({"county": c or "Unknown", "disease": d, "cases": n} for c, d, n in rows), key=lambda x: -x["cases"])

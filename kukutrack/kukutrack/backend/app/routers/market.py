"""Marketplace: farmers sell eggs/birds/manure/chicks, buyers post wanted ads, suppliers sell feed/drugs/equipment.
Contact phone numbers are only revealed to both sides once the seller accepts an inquiry."""
import statistics
from datetime import timedelta

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, select

from .. import models as m, schemas as s
from ..deps import DB, Auth, Manager
from ..services.notify import send_sms
from ..utils import now, today

router = APIRouter(prefix="/market", tags=["market"])


def _out(l: m.Listing, farm: m.Farm, mine: bool) -> dict:
    return {
        "id": l.id, "side": l.side, "category": l.category, "title": l.title, "description": l.description,
        "quantity": l.quantity, "unit": l.unit, "price_per_unit": l.price_per_unit, "county": l.county,
        "status": l.status, "expires_on": l.expires_on, "seller": farm.name, "seller_kind": farm.kind, "mine": mine,
    }


def _owners(db, farm_id: int):
    return db.scalars(select(m.User).where(m.User.farm_id == farm_id, m.User.role == "owner")).all()


@router.get("/listings")
def listings(user: Auth, db: DB, category: str | None = None, side: str | None = Query(None, pattern="^(sell|buy)$"),
             county: str | None = None, q: str | None = Query(None, max_length=60), mine: bool = False, limit: int = Query(50, ge=1, le=100)):
    qry = select(m.Listing, m.Farm).join(m.Farm, m.Farm.id == m.Listing.farm_id)
    if mine:
        qry = qry.where(m.Listing.farm_id == user.farm_id)
    else:
        qry = qry.where(m.Listing.status == "open", m.Listing.expires_on >= today())
    if category:
        qry = qry.where(m.Listing.category == category)
    if side:
        qry = qry.where(m.Listing.side == side)
    if county:
        qry = qry.where(m.Listing.county.ilike(county))
    if q:
        qry = qry.where(m.Listing.title.ilike(f"%{q}%"))
    qry = qry.order_by(m.Listing.created_at.desc()).limit(limit)
    return [_out(l, f, l.farm_id == user.farm_id) for l, f in db.execute(qry)]


@router.post("/listings", status_code=201)
def create_listing(body: s.ListingIn, user: Manager, db: DB):
    farm = db.get(m.Farm, user.farm_id)
    if farm.kind == "vet":
        raise HTTPException(403, "Veterinarian accounts cannot post listings")
    if farm.kind == "buyer" and body.side != "buy":
        raise HTTPException(403, "Buyer accounts can only post wanted ads")
    if farm.kind == "supplier" and body.side != "sell":
        raise HTTPException(403, "Supplier accounts can only post items for sale")
    open_n = db.scalar(select(func.count()).select_from(m.Listing).where(m.Listing.farm_id == farm.id, m.Listing.status == "open"))
    if open_n >= 20:
        raise HTTPException(409, "You already have 20 open listings. Close some first.")
    d = body.model_dump(exclude={"days_valid"})
    d["county"] = d["county"] or farm.county
    l = m.Listing(farm_id=farm.id, expires_on=today() + timedelta(days=body.days_valid), **d)
    db.add(l)
    db.commit()
    return _out(l, farm, True)


@router.post("/listings/{listing_id}/close")
def close_listing(listing_id: int, user: Manager, db: DB):
    l = db.get(m.Listing, listing_id)
    if not l or l.farm_id != user.farm_id:
        raise HTTPException(404, "Listing not found")
    l.status = "closed"
    db.commit()
    return {"status": "closed"}


@router.post("/listings/{listing_id}/inquiries", status_code=201)
def inquire(listing_id: int, body: s.InquiryIn, user: Manager, db: DB):
    l = db.get(m.Listing, listing_id)
    if not l or l.status != "open" or l.expires_on < today():
        raise HTTPException(404, "Listing not available")
    if l.farm_id == user.farm_id:
        raise HTTPException(400, "This is your own listing")
    me = db.get(m.Farm, user.farm_id)
    if me.kind == "vet":
        raise HTTPException(403, "Veterinarian accounts cannot trade")
    if db.scalar(select(m.Inquiry).where(m.Inquiry.listing_id == l.id, m.Inquiry.from_farm_id == user.farm_id, m.Inquiry.status == "pending")):
        raise HTTPException(409, "You already have a pending inquiry on this listing")
    inq = m.Inquiry(listing_id=l.id, from_farm_id=user.farm_id, from_user_id=user.id, quantity=body.quantity, message=body.message)
    db.add(inq)
    db.commit()
    for o in _owners(db, l.farm_id):
        send_sms(o.phone, f"KukuTrack: {me.name} is interested in '{l.title[:40]}'. Open the app > Market > Inquiries.")
    return {"id": inq.id, "status": inq.status}


@router.get("/inquiries")
def inquiries(user: Auth, db: DB, box: str = Query("in", pattern="^(in|out)$")):
    qry = select(m.Inquiry, m.Listing).join(m.Listing, m.Listing.id == m.Inquiry.listing_id)
    qry = qry.where(m.Listing.farm_id == user.farm_id) if box == "in" else qry.where(m.Inquiry.from_farm_id == user.farm_id)
    out = []
    for inq, l in db.execute(qry.order_by(m.Inquiry.created_at.desc()).limit(100)).all():
        other = db.get(m.Farm, inq.from_farm_id if box == "in" else l.farm_id)
        phone = None
        if inq.status in ("accepted", "completed"):  # reveal contact only after the seller accepts
            if box == "in":
                u = db.get(m.User, inq.from_user_id) if inq.from_user_id else None
            else:
                u = next(iter(_owners(db, l.farm_id)), None)
            phone = u.phone if u else None
        out.append({"id": inq.id, "listing_id": l.id, "listing_title": l.title, "unit": l.unit, "other": other.name,
                    "quantity": inq.quantity, "message": inq.message, "status": inq.status, "created_at": inq.created_at, "phone": phone})
    return out


@router.post("/inquiries/{inquiry_id}/respond")
def respond(inquiry_id: int, body: s.RespondIn, user: Manager, db: DB):
    inq = db.get(m.Inquiry, inquiry_id)
    l = db.get(m.Listing, inq.listing_id) if inq else None
    if not inq or l.farm_id != user.farm_id:
        raise HTTPException(404, "Inquiry not found")
    need, new = {"accept": ("pending", "accepted"), "decline": ("pending", "declined"), "complete": ("accepted", "completed")}[body.action]
    if inq.status != need:
        raise HTTPException(409, f"Cannot {body.action} an inquiry that is {inq.status}")
    inq.status, inq.updated_at = new, now()
    db.commit()
    if body.action == "accept" and inq.from_user_id:
        buyer = db.get(m.User, inq.from_user_id)
        farm = db.get(m.Farm, user.farm_id)
        send_sms(buyer.phone, f"KukuTrack: {farm.name} accepted your request for '{l.title[:40]}'. Call +{user.phone}.")
    return {"status": inq.status}


@router.get("/prices")
def prices(user: Auth, db: DB, category: str = Query(..., max_length=12)):
    """Median asking price per county/unit from open 'sell' listings."""
    rows = db.scalars(select(m.Listing).where(
        m.Listing.category == category, m.Listing.side == "sell", m.Listing.status == "open", m.Listing.expires_on >= today(),
        m.Listing.price_per_unit.is_not(None), m.Listing.price_per_unit > 0)).all()
    groups: dict[tuple[str, str], list[float]] = {}
    for l in rows:
        groups.setdefault((l.county or "Unknown", l.unit), []).append(l.price_per_unit)
    out = [{"county": c, "unit": u, "n": len(v), "median": round(statistics.median(v), 2), "min": min(v), "max": max(v)} for (c, u), v in groups.items()]
    return sorted(out, key=lambda x: -x["n"])[:10]

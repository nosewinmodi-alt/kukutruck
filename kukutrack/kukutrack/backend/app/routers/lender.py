"""Lender-ready farm performance report. The owner creates a revocable, expiring link to share with a SACCO/bank."""
import hashlib
import secrets
from datetime import date, timedelta
from html import escape as esc

from fastapi import APIRouter, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy import func, select

from .. import models as m, schemas as s
from ..config import settings
from ..deps import DB, Owner, Paid
from ..services import logic
from ..utils import now, today

router = APIRouter(prefix="/reports", tags=["lender"])
DISCLAIMER = ("Figures are recorded by the farmer in KukuTrack and have not been audited. The record-keeping score measures how "
              "complete and regular the records are; it is not a credit rating and says nothing about repayment ability.")


def _month_keys(n: int) -> list[str]:
    d, out = today().replace(day=1), []
    for _ in range(n):
        out.append(d.strftime("%Y-%m"))
        d = (d - timedelta(days=1)).replace(day=1)
    return out[::-1]


def build_report(db, farm_id: int, months: int = 12) -> dict:
    farm = db.get(m.Farm, farm_id)
    keys = _month_keys(months)
    start = date.fromisoformat(keys[0] + "-01")
    monthly = {k: {"income": 0.0, "expenses": 0.0} for k in keys}
    feed = 0.0
    for t in db.scalars(select(m.Transaction).where(m.Transaction.farm_id == farm_id, m.Transaction.tx_date >= start)):
        k = t.tx_date.strftime("%Y-%m")
        if k in monthly:
            monthly[k]["income" if t.kind == "income" else "expenses"] += t.amount
            if t.kind == "expense" and t.category == "feed":
                feed += t.amount
    rows, logged, active_days = [], 0, 0
    for f in db.scalars(select(m.Flock).where(m.Flock.farm_id == farm_id).order_by(m.Flock.placed_on)):
        if f.status == "closed" and f.closed_on and f.closed_on < start:
            continue
        k = logic.flock_summary(db, f)["kpis"]
        first, end = max(f.placed_on, start), f.closed_on or today()
        active_days += max((end - first).days + 1, 1)
        logged += db.scalar(select(func.count()).select_from(m.DailyLog).where(m.DailyLog.flock_id == f.id, m.DailyLog.log_date >= start))
        if f.placed_on >= start:  # chick purchase is an automatic expense
            monthly[f.placed_on.strftime("%Y-%m")]["expenses"] += f.cost_per_chick * f.initial_count
        rows.append({"name": f.name, "kind": f.kind, "status": f.status, "placed_on": f.placed_on, "initial": f.initial_count,
                     "live": k["live_birds"], "deaths": k["total_deaths"], "mortality_pct": k["mortality_pct"], "eggs": k["total_eggs"],
                     "hen_day_pct": k["hen_day_pct"], "fcr": k["fcr"], "income": k["income"], "expenses": k["expenses"], "profit": k["profit"]})
    income = sum(v["income"] for v in monthly.values())
    expenses = sum(v["expenses"] for v in monthly.values())
    with_data = [k for k, v in monthly.items() if v["income"] or v["expenses"]]
    first_idx = keys.index(with_data[0]) if with_data else len(keys) - 1
    active_months = len(keys) - first_idx
    tasks = db.scalars(select(m.VaccinationTask).join(m.Flock).where(
        m.Flock.farm_id == farm_id, m.VaccinationTask.due_date <= today(), m.VaccinationTask.due_date >= start)).all()
    on_time = sum(1 for t in tasks if t.done_on and t.done_on <= t.due_date + timedelta(days=3))
    completeness = min(logged / active_days, 1) if active_days else 0
    months_ratio = len(with_data) / active_months if active_months else 0
    if tasks:
        score = 50 * completeness + 30 * months_ratio + 20 * on_time / len(tasks)
    else:
        score = (50 * completeness + 30 * months_ratio) / 0.8
    hd = [r["hen_day_pct"] for r in rows if r["hen_day_pct"] is not None]
    total_init = sum(r["initial"] for r in rows)
    net = income - expenses
    return {
        "generated_on": today(), "farm": {"name": farm.name, "county": farm.county, "member_since": farm.created_at.date()},
        "period": {"start": start, "end": today(), "months": months},
        "financial": {"income": round(income, 2), "expenses": round(expenses, 2), "net": round(net, 2),
                      "margin_pct": round(net / income * 100, 1) if income else None,
                      "avg_monthly_net": round(net / active_months, 2) if active_months else None,
                      "feed_share_pct": round(feed / expenses * 100, 1) if expenses else None},
        "production": {"active_flocks": sum(1 for r in rows if r["status"] == "active"), "live_birds": sum(r["live"] for r in rows if r["status"] == "active"),
                       "avg_mortality_pct": round(sum(r["deaths"] for r in rows) / total_init * 100, 2) if total_init else None,
                       "avg_hen_day_pct": round(sum(hd) / len(hd), 1) if hd else None},
        "records": {"completeness_pct": round(completeness * 100), "months_with_records": len(with_data), "active_months": active_months,
                    "vaccination_on_time_pct": round(on_time / len(tasks) * 100) if tasks else None, "score": round(min(score, 100))},
        "monthly": [{"month": k, "income": round(v["income"], 2), "expenses": round(v["expenses"], 2), "net": round(v["income"] - v["expenses"], 2)} for k, v in monthly.items()],
        "flocks": rows, "disclaimer": DISCLAIMER,
    }


def _n(x, d=0, suffix=""):
    return "&ndash;" if x is None else f"{x:,.{d}f}{suffix}"


def render_html(r: dict) -> str:
    f, p, rec = r["financial"], r["production"], r["records"]
    box = lambda label, val: f'<div class="b"><span>{esc(label)}</span><b>{val}</b></div>'  # noqa: E731
    monthly = "".join(f"<tr><td>{x['month']}</td><td>{_n(x['income'])}</td><td>{_n(x['expenses'])}</td><td>{_n(x['net'])}</td></tr>" for x in r["monthly"])
    flocks = "".join(
        f"<tr><td>{esc(x['name'])}</td><td>{x['kind']}</td><td>{x['status']}</td><td>{x['placed_on']}</td><td>{x['initial']}</td><td>{x['live']}</td>"
        f"<td>{_n(x['mortality_pct'], 1, '%')}</td><td>{_n(x['hen_day_pct'], 1, '%')}</td><td>{_n(x['fcr'], 2)}</td><td>{_n(x['profit'])}</td></tr>" for x in r["flocks"])
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow"><title>Farm performance report - {esc(r['farm']['name'])}</title>
<style>body{{font:15px/1.5 system-ui,sans-serif;max-width:860px;margin:0 auto;padding:24px;color:#1F2A1B}}h1,h2{{font-family:Georgia,serif;margin:.6em 0 .3em}}
.g{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px}}.b{{border:1.5px solid #D9CDB0;border-radius:10px;padding:10px 12px}}.b span{{display:block;font-size:12px;color:#6B715E;text-transform:uppercase}}.b b{{font:700 22px Georgia,serif}}
table{{width:100%;border-collapse:collapse;font-size:13px;margin:6px 0 14px}}th,td{{padding:5px 6px;border-bottom:1px solid #D9CDB0;text-align:right}}th:first-child,td:first-child{{text-align:left}}
.note{{font-size:12px;color:#6B715E;border-top:1px solid #D9CDB0;margin-top:20px;padding-top:10px}}@media print{{body{{padding:0}}}}</style></head><body>
<h1>Farm performance report</h1><div><b>{esc(r['farm']['name'])}</b>{' &middot; ' + esc(r['farm']['county']) if r['farm']['county'] else ''}<br>
Period {r['period']['start']} to {r['period']['end']} ({r['period']['months']} months) &middot; Generated {r['generated_on']} &middot; On KukuTrack since {r['farm']['member_since']}</div>
<h2>Financial summary (KES)</h2><div class="g">{box('Income', _n(f['income']))}{box('Expenses', _n(f['expenses']))}{box('Net', _n(f['net']))}{box('Margin', _n(f['margin_pct'], 1, '%'))}{box('Avg monthly net', _n(f['avg_monthly_net']))}{box('Feed share of cost', _n(f['feed_share_pct'], 1, '%'))}</div>
<h2>Production</h2><div class="g">{box('Active flocks', p['active_flocks'])}{box('Live birds', _n(p['live_birds']))}{box('Mortality (all flocks)', _n(p['avg_mortality_pct'], 1, '%'))}{box('Avg hen-day (layers)', _n(p['avg_hen_day_pct'], 1, '%'))}</div>
<h2>Record-keeping quality</h2><div class="g">{box('Score /100', rec['score'])}{box('Days with records', str(rec['completeness_pct']) + '%')}{box('Months with money records', f"{rec['months_with_records']}/{rec['active_months']}")}{box('Vaccinations on time', _n(rec['vaccination_on_time_pct'], 0, '%'))}</div>
<h2>Monthly cash flow (KES)</h2><table><tr><th>Month</th><th>Income</th><th>Expenses</th><th>Net</th></tr>{monthly}</table>
<h2>Flocks</h2><div style="overflow-x:auto"><table><tr><th>Flock</th><th>Type</th><th>Status</th><th>Placed</th><th>Initial</th><th>Live</th><th>Mortality</th><th>Hen-day</th><th>FCR</th><th>Profit</th></tr>{flocks}</table></div>
<p class="note">{esc(r['disclaimer'])} Flock figures cover each flock's whole life; cash-flow figures cover the period above. Live snapshot at the time this page was opened.</p></body></html>"""


def _need_owner(user):
    if user.role != "owner":
        raise HTTPException(403, "Only the farm owner can share reports")
    return user


@router.get("/lender")
def lender_json(user: Paid, db: DB, months: int = Query(12, ge=3, le=24)):
    if user.role not in ("owner", "manager"):
        raise HTTPException(403, "Not permitted")
    return jsonable_encoder(build_report(db, user.farm_id, months))


@router.post("/lender/share", status_code=201)
def create_share(body: s.ShareIn, user: Paid, db: DB):
    _need_owner(user)
    raw = secrets.token_urlsafe(24)
    sh = m.ReportShare(farm_id=user.farm_id, token_hash=hashlib.sha256(raw.encode()).hexdigest(), expires_at=now() + timedelta(days=body.days))
    db.add(sh)
    db.commit()
    return {"id": sh.id, "url": f"{settings.public_base_url}/api/reports/shared/{raw}", "expires_at": sh.expires_at}


@router.get("/shares")
def list_shares(user: Owner, db: DB):
    rows = db.scalars(select(m.ReportShare).where(m.ReportShare.farm_id == user.farm_id).order_by(m.ReportShare.id.desc()).limit(20)).all()
    return [{"id": r.id, "created_at": r.created_at, "expires_at": r.expires_at, "active": (not r.revoked and r.expires_at > now())} for r in rows]


@router.delete("/shares/{share_id}")
def revoke_share(share_id: int, user: Owner, db: DB):
    sh = db.get(m.ReportShare, share_id)
    if not sh or sh.farm_id != user.farm_id:
        raise HTTPException(404, "Link not found")
    sh.revoked = True
    db.commit()
    return {"revoked": True}


@router.get("/shared/{token}", response_class=HTMLResponse)
def shared(token: str, db: DB, format: str = Query("html", pattern="^(html|json)$")):
    """Public (no login): whoever holds the link can read the report until it expires or is revoked."""
    sh = db.scalar(select(m.ReportShare).where(m.ReportShare.token_hash == hashlib.sha256(token.encode()).hexdigest()))
    if not sh or sh.revoked or sh.expires_at < now():
        raise HTTPException(404, "This link has expired or been revoked")
    headers = {"Cache-Control": "no-store", "X-Robots-Tag": "noindex", "Referrer-Policy": "no-referrer"}
    report = build_report(db, sh.farm_id)
    if format == "json":
        return JSONResponse(jsonable_encoder(report), headers=headers)
    return HTMLResponse(render_html(report), headers=headers)

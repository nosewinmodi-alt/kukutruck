"""Pure KPI + alert engine (no DB, no framework) so it is easy to test."""
from dataclasses import dataclass
from datetime import date


@dataclass
class Log:
    day: date
    eggs: int = 0
    cracked: int = 0
    deaths: int = 0
    feed_kg: float = 0.0
    water_l: float = 0.0
    avg_weight_g: float | None = None


def _r(x, n=2):
    return None if x is None else round(x, n)


def compute_kpis(kind: str, initial: int, logs: list[Log], income: float = 0.0, expenses: float = 0.0) -> dict:
    logs = sorted(logs, key=lambda l: l.day)
    live = initial
    bird_days = eggs = deaths = 0
    feed = 0.0
    weight_g = None
    for l in logs:
        bird_days += live  # birds present at the start of the day
        live = max(live - l.deaths, 0)
        eggs += l.eggs
        deaths += l.deaths
        feed += l.feed_kg
        if l.avg_weight_g:
            weight_g = l.avg_weight_g
    out = {
        "live_birds": live,
        "mortality_pct": _r(deaths / initial * 100 if initial else 0),
        "total_deaths": deaths,
        "total_feed_kg": _r(feed),
        "feed_g_per_bird_day": _r(feed * 1000 / bird_days) if bird_days else None,
        "total_eggs": eggs,
        "hen_day_pct": _r(eggs / bird_days * 100) if kind != "broiler" and bird_days else None,
        # Approximation: feed / (live birds x latest average weight). Ignores dead birds and chick weight.
        "fcr": _r(feed / (live * weight_g / 1000)) if kind == "broiler" and weight_g and live else None,
        "cost_per_tray": _r(expenses / (eggs / 30)) if eggs else None,
        "income": _r(income),
        "expenses": _r(expenses),
        "profit": _r(income - expenses),
        "days_logged": len(logs),
    }
    return out


def compute_alerts(kind: str, initial: int, logs: list[Log]) -> list[dict]:
    alerts = []
    logs = sorted(logs, key=lambda l: l.day)
    if not logs:
        return alerts
    live_before = initial - sum(l.deaths for l in logs[:-1])
    last = logs[-1]
    if live_before > 0:
        rate = last.deaths / live_before * 100
        if rate >= 1:
            alerts.append({"code": "mortality_critical", "level": "critical", "value": _r(rate)})
        elif rate >= 0.5:
            alerts.append({"code": "mortality_high", "level": "warn", "value": _r(rate)})
    if kind != "broiler":
        prev = [l.eggs for l in logs[-8:-1] if l.eggs > 0]
        if len(prev) >= 3 and last.eggs >= 0:
            avg = sum(prev) / len(prev)
            drop = (avg - last.eggs) / avg * 100
            if drop >= 15:
                alerts.append({"code": "egg_drop", "level": "warn", "value": _r(drop)})
    return alerts

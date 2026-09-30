"""Send SMS reminders for vaccinations due today/tomorrow. Run hourly via cron or the compose 'reminders' service."""
from datetime import timedelta

from sqlalchemy import select

from .. import models as m
from ..db import Base, SessionLocal, engine
from ..services.notify import send_sms
from ..utils import today


def run() -> int:
    sent = 0
    with SessionLocal() as db:
        rows = db.execute(
            select(m.VaccinationTask, m.Flock).join(m.Flock).where(
                m.VaccinationTask.done_on.is_(None), m.VaccinationTask.reminded.is_(False),
                m.VaccinationTask.due_date <= today() + timedelta(days=1), m.Flock.status == "active",
            )
        ).all()
        for task, flock in rows:
            users = db.scalars(select(m.User).where(m.User.farm_id == flock.farm_id, m.User.role.in_(["owner", "manager"]))).all()
            msg = f"KukuTrack: {task.vaccine} is due {task.due_date:%d %b} for {flock.name}. Reply via app once done."
            if any([send_sms(u.phone, msg) for u in users]):
                task.reminded = True
                sent += 1
        db.commit()
    return sent


if __name__ == "__main__":
    print("reminders sent:", run())

"""Admin tool: verify (or revoke) a veterinarian account after checking their KVB licence.

    python -m app.jobs.verify_vet 0712345678            # verify
    python -m app.jobs.verify_vet 0712345678 --revoke   # revoke
Check the licence number shown here against the Kenya Veterinary Board register BEFORE verifying.
"""
import sys

from sqlalchemy import select

from .. import models as m
from ..db import SessionLocal
from ..utils import normalize_phone


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    phone = normalize_phone(argv[0])
    with SessionLocal() as db:
        user = db.scalar(select(m.User).where(m.User.phone == phone))
        farm = db.get(m.Farm, user.farm_id) if user else None
        if not farm or farm.kind != "vet":
            print("No veterinarian account found for that number")
            return 1
        print(f"{user.name} | practice: {farm.name} | county: {farm.county} | licence: {farm.licence_no}")
        farm.verified = "--revoke" not in argv
        db.commit()
        print("VERIFIED" if farm.verified else "REVOKED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

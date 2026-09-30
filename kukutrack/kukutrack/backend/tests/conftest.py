import os

os.environ["DATABASE_URL"] = "sqlite:///./test.db"
os.environ["ENVIRONMENT"] = "test"

import pytest
from fastapi.testclient import TestClient

from app.db import Base, engine
from app.main import app


@pytest.fixture()
def client():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with TestClient(app) as c:
        yield c


def register(client, phone="0712345678", farm="Test Farm", kind="farm"):
    extra = {"licence_no": "KVB-123"} if kind == "vet" else {}
    r = client.post("/api/auth/register", json={"name": "Wanjiku", "phone": phone, "password": "secret1", "farm_name": farm, "consent": True, "account_type": kind, **extra})
    assert r.status_code == 201, r.text
    return {"Authorization": "Bearer " + r.json()["access_token"]}

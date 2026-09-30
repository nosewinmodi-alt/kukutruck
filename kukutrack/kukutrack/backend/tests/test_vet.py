from datetime import date

from conftest import register

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 32


def _verify(phone):
    from sqlalchemy import select

    from app import models as m
    from app.db import SessionLocal

    with SessionLocal() as db:
        u = db.scalar(select(m.User).where(m.User.phone == phone))
        db.get(m.Farm, u.farm_id).verified = True
        db.commit()


def test_vet_consultation(client):
    farm, vet = register(client, "0711111111", "Farm A"), register(client, "0733333333", "Dr Mwangi Vet", "vet")
    other = register(client, "0744444444", "Farm B")
    f = client.post("/api/flocks", json={"name": "H1", "kind": "layer", "initial_count": 100, "placed_on": date.today().isoformat(), "cost_per_chick": 50}, headers=farm).json()
    case = client.post("/api/vet/cases", json={"title": "Coughing birds", "symptoms": "Sneezing and gasping since Monday", "flock_id": f["id"], "urgency": "urgent"}, headers=farm).json()
    cid = case["id"]
    assert client.post(f"/api/vet/cases/{cid}/photos", files={"file": ("a.png", PNG, "image/png")}, headers=farm).status_code == 201
    assert client.post(f"/api/vet/cases/{cid}/photos", files={"file": ("a.txt", b"hello world!!", "text/plain")}, headers=farm).status_code == 415
    assert client.get(f"/api/vet/cases/{cid}", headers=other).status_code == 404       # other farms cannot see it
    assert client.get("/api/vet/cases", headers=vet).status_code == 403                 # unverified vet
    _verify("254733333333")
    assert len(client.get("/api/vet/cases", headers=vet).json()) == 1
    d = client.get(f"/api/vet/cases/{cid}", headers=vet).json()
    assert "profit" not in d["flock"]["kpis"] and len(d["photos"]) == 1               # vets never see finances
    assert client.get(f"/api/vet/photos/{d['photos'][0]}", headers=vet).status_code == 200
    assert client.get(f"/api/vet/photos/{d['photos'][0]}", headers=other).status_code == 404
    assert client.post(f"/api/vet/cases/{cid}/messages", json={"body": "Likely IB. Isolate and give electrolytes."}, headers=vet).status_code == 201
    assert client.get(f"/api/vet/cases/{cid}", headers=farm).json()["status"] == "answered"
    assert client.post(f"/api/vet/cases/{cid}/diagnosis", json={"disease": "Infectious Bronchitis"}, headers=farm).status_code == 403
    client.post(f"/api/vet/cases/{cid}/diagnosis", json={"disease": "Infectious Bronchitis"}, headers=vet)
    assert client.get("/api/vet/outbreaks", headers=other).json()[0]["cases"] == 1
    assert client.post(f"/api/vet/cases/{cid}/close", headers=farm).status_code == 200

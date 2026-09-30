from datetime import date

from conftest import register


def _flock(client, h, **kw):
    body = {"name": "House A", "kind": "layer", "initial_count": 200, "placed_on": date.today().isoformat(), "cost_per_chick": 100}
    r = client.post("/api/flocks", json={**body, **kw}, headers=h)
    assert r.status_code == 201, r.text
    return r.json()


def test_flow_and_kpis(client):
    h = register(client)
    f = _flock(client, h)
    assert len(client.get("/api/vaccinations", headers=h).json()) == 7  # template generated
    r = client.put(f"/api/flocks/{f['id']}/logs", json={"log_date": date.today().isoformat(), "eggs": 150, "deaths": 2, "feed_kg": 22}, headers=h)
    assert r.status_code == 200
    s = client.get(f"/api/flocks/{f['id']}", headers=h).json()
    assert s["kpis"]["live_birds"] == 198 and s["kpis"]["expenses"] == 20000
    client.post("/api/transactions", json={"kind": "income", "category": "eggs", "amount": 5000, "tx_date": date.today().isoformat(), "flock_id": f["id"]}, headers=h)
    assert client.get(f"/api/flocks/{f['id']}", headers=h).json()["kpis"]["profit"] == -15000
    assert client.get("/api/reports/dashboard", headers=h).json()["eggs_today"] == 150


def test_tenant_isolation(client):
    a, b = register(client, "0711111111", "A"), register(client, "0722222222", "B")
    f = _flock(client, a)
    assert client.get(f"/api/flocks/{f['id']}", headers=b).status_code == 404
    assert client.get("/api/flocks", headers=b).json() == []


def test_sync_idempotent(client):
    h = register(client)
    f = _flock(client, h)
    payload = {"logs": [{"flock_id": f["id"], "log_date": date.today().isoformat(), "eggs": 10}],
               "transactions": [{"kind": "expense", "category": "feed", "amount": 100, "tx_date": date.today().isoformat(), "client_id": "abc"}]}
    for _ in range(2):
        assert client.post("/api/sync/push", json=payload, headers=h).json()["errors"] == []
    assert len(client.get("/api/transactions", headers=h).json()) == 1
    assert len(client.get(f"/api/flocks/{f['id']}/logs", headers=h).json()) == 1


def test_roles(client):
    h = register(client)
    client.post("/api/auth/staff", json={"name": "Peter", "phone": "0733333333", "password": "secret1", "role": "worker"}, headers=h)
    tok = client.post("/api/auth/login", json={"phone": "0733333333", "password": "secret1"}).json()["access_token"]
    w = {"Authorization": "Bearer " + tok}
    assert client.post("/api/flocks", json={"name": "x", "kind": "layer", "initial_count": 5, "placed_on": date.today().isoformat()}, headers=w).status_code == 403
    assert client.get("/api/transactions", headers=w).status_code == 403


def test_consent_required(client):
    r = client.post("/api/auth/register", json={"name": "Wanjiku", "phone": "0712345678", "password": "secret1", "farm_name": "F", "consent": False})
    assert r.status_code == 422


def test_password_reset(client, monkeypatch):
    import re
    sent = {}
    monkeypatch.setattr("app.routers.auth.send_sms", lambda phone, msg: sent.update(msg=msg) or True)
    register(client)
    assert client.post("/api/auth/forgot", json={"phone": "0799999999"}).status_code == 200  # unknown number: same reply
    assert "msg" not in sent
    assert client.post("/api/auth/forgot", json={"phone": "0712345678"}).status_code == 200
    code = re.search(r"code: (\d{6})", sent["msg"]).group(1)
    wrong = "000000" if code != "000000" else "111111"
    body = {"phone": "0712345678", "new_password": "newpass1"}
    assert client.post("/api/auth/reset", json={**body, "code": wrong}).status_code == 400
    assert client.post("/api/auth/reset", json={**body, "code": code}).status_code == 200
    assert client.post("/api/auth/reset", json={**body, "code": code}).status_code == 400  # single use
    assert client.post("/api/auth/login", json={"phone": "0712345678", "password": "newpass1"}).status_code == 200


def test_export_and_delete(client):
    h = register(client)
    _flock(client, h)
    data = client.get("/api/auth/account/export", headers=h).json()
    assert len(data["flocks"]) == 1 and "password_hash" not in data["users"][0]
    assert client.request("DELETE", "/api/auth/account", json={"password": "wrong"}, headers=h).status_code == 403
    assert client.request("DELETE", "/api/auth/account", json={"password": "secret1"}, headers=h).status_code == 200
    assert client.post("/api/auth/login", json={"phone": "0712345678", "password": "secret1"}).status_code == 401
    assert client.get("/api/auth/me", headers=h).status_code == 401


def test_erasure_covers_market_and_vet(client):
    h = register(client)
    client.post("/api/market/listings", json={"side": "sell", "category": "eggs", "title": "Eggs today", "quantity": 5, "unit": "tray"}, headers=h)
    client.post("/api/vet/cases", json={"title": "Sick birds", "symptoms": "Not eating since Monday"}, headers=h)
    assert client.request("DELETE", "/api/auth/account", json={"password": "secret1"}, headers=h).status_code == 200
    assert client.get("/api/market/listings", headers=register(client, "0755555555", "New")).json() == []

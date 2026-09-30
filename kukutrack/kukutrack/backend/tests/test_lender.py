from datetime import date

from conftest import register


def test_lender_share_link(client):
    h = register(client, farm="Green Acres")
    f = client.post("/api/flocks", json={"name": "H1", "kind": "layer", "initial_count": 100, "placed_on": date.today().isoformat(), "cost_per_chick": 100}, headers=h).json()
    client.put(f"/api/flocks/{f['id']}/logs", json={"log_date": date.today().isoformat(), "eggs": 80, "deaths": 1, "feed_kg": 11}, headers=h)
    client.post("/api/transactions", json={"kind": "income", "category": "eggs", "amount": 8000, "tx_date": date.today().isoformat()}, headers=h)
    rep = client.get("/api/reports/lender", headers=h).json()
    assert rep["financial"]["income"] == 8000 and rep["financial"]["expenses"] == 10000 and 0 <= rep["records"]["score"] <= 100
    share = client.post("/api/reports/lender/share", json={"days": 7}, headers=h).json()
    token_path = share["url"].split("/api", 1)[1]
    page = client.get("/api" + token_path)                      # no auth header: lender opens the link
    assert page.status_code == 200 and "Green Acres" in page.text and "not a credit rating" in page.text
    assert client.get("/api" + token_path + "?format=json").json()["farm"]["name"] == "Green Acres"
    assert client.get("/api/reports/shared/not-a-real-token").status_code == 404
    client.delete(f"/api/reports/shares/{share['id']}", headers=h)
    assert client.get("/api" + token_path).status_code == 404   # revoked

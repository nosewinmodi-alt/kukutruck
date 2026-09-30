from conftest import register

LISTING = {"side": "sell", "category": "eggs", "title": "Fresh eggs, Kiambu", "quantity": 100, "unit": "tray", "price_per_unit": 420}


def test_market_flow_and_phone_privacy(client):
    farmer, buyer = register(client, "0711111111", "Farm A"), register(client, "0722222222", "Nairobi Hotels", "buyer")
    lid = client.post("/api/market/listings", json=LISTING, headers=farmer).json()["id"]
    assert client.post("/api/market/listings", json=LISTING, headers=buyer).status_code == 403  # buyers only post wanted ads
    assert [l["id"] for l in client.get("/api/market/listings?category=eggs", headers=buyer).json()] == [lid]
    iid = client.post(f"/api/market/listings/{lid}/inquiries", json={"quantity": 20, "message": "Weekly?"}, headers=buyer).json()["id"]
    assert client.post(f"/api/market/listings/{lid}/inquiries", json={"quantity": 5}, headers=buyer).status_code == 409
    inbox = client.get("/api/market/inquiries?box=in", headers=farmer).json()
    assert inbox[0]["status"] == "pending" and inbox[0]["phone"] is None  # hidden until accepted
    assert client.post(f"/api/market/inquiries/{iid}/respond", json={"action": "accept"}, headers=buyer).status_code == 404  # only seller
    assert client.post(f"/api/market/inquiries/{iid}/respond", json={"action": "accept"}, headers=farmer).status_code == 200
    assert client.get("/api/market/inquiries?box=in", headers=farmer).json()[0]["phone"] == "254722222222"
    assert client.get("/api/market/inquiries?box=out", headers=buyer).json()[0]["phone"] == "254711111111"
    assert client.get("/api/market/prices?category=eggs", headers=buyer).json()[0]["median"] == 420
    client.post(f"/api/market/listings/{lid}/close", headers=farmer)
    assert client.get("/api/market/listings", headers=buyer).json() == []

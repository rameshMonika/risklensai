"""Portfolio / holdings CRUD + per-user ownership isolation."""

from tests.conftest import register_and_login


def test_create_holding_uppercases_the_symbol(auth_client):
    resp = auth_client.post(
        "/portfolio/holdings", json={"symbol": "aapl", "quantity": 10, "avg_cost": 180.0}
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["symbol"] == "AAPL"
    assert body["quantity"] == 10 and body["avg_cost"] == 180.0
    assert "id" in body


def test_list_holdings_returns_what_was_added(auth_client):
    auth_client.post("/portfolio/holdings", json={"symbol": "NVDA", "quantity": 5, "avg_cost": 120.0})
    auth_client.post("/portfolio/holdings", json={"symbol": "MSFT", "quantity": 3, "avg_cost": 340.0})
    resp = auth_client.get("/portfolio/holdings")
    assert resp.status_code == 200
    symbols = {h["symbol"] for h in resp.json()}
    assert symbols == {"NVDA", "MSFT"}


def test_create_holding_rejects_non_positive_quantity(auth_client):
    assert (
        auth_client.post(
            "/portfolio/holdings", json={"symbol": "AAPL", "quantity": 0, "avg_cost": 180.0}
        ).status_code
        == 422
    )
    assert (
        auth_client.post(
            "/portfolio/holdings", json={"symbol": "AAPL", "quantity": -3, "avg_cost": 180.0}
        ).status_code
        == 422
    )


def test_update_holding_replaces_its_values(auth_client):
    hid = auth_client.post(
        "/portfolio/holdings", json={"symbol": "AAPL", "quantity": 10, "avg_cost": 180.0}
    ).json()["id"]
    resp = auth_client.put(
        f"/portfolio/holdings/{hid}", json={"symbol": "tsla", "quantity": 2, "avg_cost": 220.0}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["symbol"] == "TSLA" and body["quantity"] == 2 and body["avg_cost"] == 220.0


def test_delete_holding(auth_client):
    hid = auth_client.post(
        "/portfolio/holdings", json={"symbol": "AAPL", "quantity": 10, "avg_cost": 180.0}
    ).json()["id"]
    assert auth_client.delete(f"/portfolio/holdings/{hid}").status_code == 204
    assert auth_client.get("/portfolio/holdings").json() == []


def test_holdings_endpoints_require_auth(client):
    assert client.get("/portfolio/holdings").status_code == 401
    assert client.post(
        "/portfolio/holdings", json={"symbol": "AAPL", "quantity": 1, "avg_cost": 1.0}
    ).status_code == 401


def test_a_user_cannot_touch_another_users_holding(client):
    # user A creates a holding
    token_a = register_and_login(client, "owner@example.com", name="Owner")
    client.headers["Authorization"] = f"Bearer {token_a}"
    hid = client.post(
        "/portfolio/holdings", json={"symbol": "AAPL", "quantity": 10, "avg_cost": 180.0}
    ).json()["id"]

    # user B must not see it, edit it, or delete it
    token_b = register_and_login(client, "intruder@example.com", name="Intruder")
    client.headers["Authorization"] = f"Bearer {token_b}"

    assert client.get("/portfolio/holdings").json() == []          # B's own list is empty
    assert client.put(
        f"/portfolio/holdings/{hid}", json={"symbol": "X", "quantity": 1, "avg_cost": 1.0}
    ).status_code == 404
    assert client.delete(f"/portfolio/holdings/{hid}").status_code == 404

    # A's holding is untouched
    client.headers["Authorization"] = f"Bearer {token_a}"
    assert len(client.get("/portfolio/holdings").json()) == 1

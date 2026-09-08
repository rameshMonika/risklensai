"""Auth flow: register, login, /auth/me, refresh."""


def test_register_returns_the_user_without_the_password_hash(client):
    resp = client.post(
        "/auth/register",
        json={"name": "Ada", "email": "ada@example.com", "password": "password123"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["email"] == "ada@example.com"
    assert body["name"] == "Ada"
    assert "id" in body and "created_at" in body
    assert "password" not in body and "password_hash" not in body


def test_register_rejects_a_duplicate_email(client):
    payload = {"name": "Ada", "email": "dupe@example.com", "password": "password123"}
    assert client.post("/auth/register", json=payload).status_code == 201
    assert client.post("/auth/register", json=payload).status_code == 409


def test_register_rejects_a_short_password(client):
    resp = client.post(
        "/auth/register",
        json={"name": "Ada", "email": "short@example.com", "password": "1234567"},
    )
    assert resp.status_code == 422


def test_register_rejects_a_malformed_email(client):
    resp = client.post(
        "/auth/register",
        json={"name": "Ada", "email": "not-an-email", "password": "password123"},
    )
    assert resp.status_code == 422


def test_login_with_correct_credentials_returns_both_tokens(client):
    client.post(
        "/auth/register",
        json={"name": "Ada", "email": "login@example.com", "password": "password123"},
    )
    resp = client.post("/auth/login", json={"email": "login@example.com", "password": "password123"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["access_token"] and body["refresh_token"]
    assert body["token_type"] == "bearer"


def test_login_with_wrong_password_is_401(client):
    client.post(
        "/auth/register",
        json={"name": "Ada", "email": "wrongpw@example.com", "password": "password123"},
    )
    resp = client.post("/auth/login", json={"email": "wrongpw@example.com", "password": "WRONGpass1"})
    assert resp.status_code == 401


def test_login_with_unknown_email_is_401(client):
    resp = client.post("/auth/login", json={"email": "nobody@example.com", "password": "password123"})
    assert resp.status_code == 401


def test_me_returns_the_current_user(auth_client):
    resp = auth_client.get("/auth/me")
    assert resp.status_code == 200
    assert resp.json()["email"] == "primary@example.com"


def test_me_without_a_token_is_401(client):
    assert client.get("/auth/me").status_code == 401


def test_me_with_a_garbage_token_is_401(client):
    client.headers["Authorization"] = "Bearer not.a.jwt"
    assert client.get("/auth/me").status_code == 401


def test_refresh_issues_new_tokens(client):
    client.post(
        "/auth/register",
        json={"name": "Ada", "email": "refresh@example.com", "password": "password123"},
    )
    tokens = client.post(
        "/auth/login", json={"email": "refresh@example.com", "password": "password123"}
    ).json()
    resp = client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert resp.status_code == 200
    assert resp.json()["access_token"]


def test_refresh_rejects_an_access_token(client):
    client.post(
        "/auth/register",
        json={"name": "Ada", "email": "wrongtype@example.com", "password": "password123"},
    )
    tokens = client.post(
        "/auth/login", json={"email": "wrongtype@example.com", "password": "password123"}
    ).json()
    # passing the ACCESS token where a REFRESH token is expected
    resp = client.post("/auth/refresh", json={"refresh_token": tokens["access_token"]})
    assert resp.status_code == 401

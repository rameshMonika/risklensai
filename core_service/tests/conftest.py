"""Test setup for core_service.

Needs a real PostgreSQL (the models use postgres-only JSONB columns). CI runs
a `postgres:16` service and sets DATABASE_URL; locally, `docker compose up -d
postgres` first. The default below matches docker-compose.yml.

Isolation: the schema is created once per session; each test runs inside a
transaction on a single connection with `join_transaction_mode="create_savepoint"`,
so the endpoint code's own `db.commit()` calls land on savepoints and the whole
test is rolled back at teardown -- no truncate, no cross-test bleed.
"""

import os

os.environ.setdefault(
    "DATABASE_URL", "postgresql+psycopg2://postgres:postgres@localhost:5432/risklens"
)
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-not-a-real-one")
os.environ.setdefault("INTERNAL_SERVICE_API_KEY", "test-internal-key")
os.environ.setdefault("ALPHA_VANTAGE_API_KEY", "test-alpha-vantage-key")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from core_service.core.config import settings
from core_service.db import models  # noqa: F401  -- registers every table on Base
from core_service.db.base import Base
from core_service.db.session import get_db
from core_service.main import app


@pytest.fixture(scope="session")
def _engine():
    engine = create_engine(settings.database_url)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def db_session(_engine):
    connection = _engine.connect()
    outer = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        outer.rollback()
        connection.close()


@pytest.fixture
def client(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def register_and_login(client: TestClient, email: str, name: str = "User", password: str = "password123") -> str:
    """Register a user and return their access token."""
    client.post("/auth/register", json={"name": name, "email": email, "password": password})
    resp = client.post("/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


@pytest.fixture
def auth_client(client):
    """`client` with a registered, logged-in user's Bearer token set."""
    token = register_and_login(client, "primary@example.com", name="Primary")
    client.headers["Authorization"] = f"Bearer {token}"
    return client

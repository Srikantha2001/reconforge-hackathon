"""JWT auth + role-based access control (P4 acceptance).

Verifies login for all five demo users, wrong-password rejection, token
validation, and that require_role returns 403 for the wrong role / 401 when
unauthenticated.
"""
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.auth import DEMO_USERS


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:  # `with` triggers lifespan -> tables + user seed
        yield c


def _login(client, email, password):
    return client.post("/api/auth/login", json={"email": email, "password": password})


@pytest.mark.parametrize("user", DEMO_USERS, ids=[u["role"] for u in DEMO_USERS])
def test_login_all_demo_users(client, user):
    resp = _login(client, user["email"], user["password"])
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["role"] == user["role"]
    assert body["email"] == user["email"]


def test_login_wrong_password_401(client):
    resp = _login(client, "maker@db.com", "wrong-password")
    assert resp.status_code == 401


def test_login_unknown_email_401(client):
    resp = _login(client, "nobody@db.com", "whatever")
    assert resp.status_code == 401


def test_me_returns_identity(client):
    token = _login(client, "checker@db.com", "checker123").json()["access_token"]
    resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["role"] == "CHECKER"


def test_me_without_token_401(client):
    assert client.get("/api/auth/me").status_code == 401


def test_me_with_garbage_token_401(client):
    resp = client.get("/api/auth/me", headers={"Authorization": "Bearer not-a-jwt"})
    assert resp.status_code == 401


def test_require_role_allows_matching_role(client):
    token = _login(client, "maker@db.com", "maker123").json()["access_token"]
    resp = client.get("/api/auth/probe-maker", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


def test_require_role_rejects_wrong_role_403(client):
    token = _login(client, "checker@db.com", "checker123").json()["access_token"]
    resp = client.get("/api/auth/probe-maker", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403


def test_require_role_rejects_missing_token_401(client):
    assert client.get("/api/auth/probe-maker").status_code == 401


def test_actors_endpoint_removed(client):
    assert client.get("/api/actors").status_code == 404

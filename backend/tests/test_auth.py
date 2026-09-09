"""infra-002 认证授权测试。"""

import pytest

from app.core.security import create_access_token
from app.models.user import User


def _login(client, username, password):
    return client.post(
        "/api/auth/login",
        json={"username": username, "password": password},
    )


def _auth_header(token):
    return {"Authorization": f"Bearer {token}"}


def test_login_success(client, seed_users):
    r = _login(client, "admin", "admin123")
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert "access_token" in body["data"]
    assert body["data"]["user"]["username"] == "admin"


def test_login_wrong_password(client, seed_users):
    r = _login(client, "admin", "wrong")
    assert r.status_code == 401


def test_me_with_token(client, seed_users):
    token = _login(client, "admin", "admin123").json()["data"]["access_token"]
    r = client.get("/api/auth/me", headers=_auth_header(token))
    assert r.status_code == 200
    assert r.json()["data"]["username"] == "admin"
    assert r.json()["data"]["role"] == "ADMIN"


def test_me_without_token(client, seed_users):
    r = client.get("/api/auth/me")
    assert r.status_code == 401


def test_admin_only_with_collector_forbidden(client, seed_users):
    token = _login(client, "collector1", "admin123").json()["data"]["access_token"]
    r = client.get("/api/auth/admin-only", headers=_auth_header(token))
    assert r.status_code == 403


def test_admin_only_with_admin_ok(client, seed_users):
    token = _login(client, "admin", "admin123").json()["data"]["access_token"]
    r = client.get("/api/auth/admin-only", headers=_auth_header(token))
    assert r.status_code == 200


def test_supervisor_or_admin_with_supervisor_ok(client, seed_users):
    token = _login(client, "supervisor", "admin123").json()["data"]["access_token"]
    r = client.get("/api/auth/supervisor-or-admin", headers=_auth_header(token))
    assert r.status_code == 200


def test_supervisor_or_admin_with_collector_forbidden(client, seed_users):
    token = _login(client, "collector1", "admin123").json()["data"]["access_token"]
    r = client.get("/api/auth/supervisor-or-admin", headers=_auth_header(token))
    assert r.status_code == 403


def test_invalid_token_rejected(client, seed_users):
    r = client.get("/api/auth/me", headers=_auth_header("not.a.valid.token"))
    assert r.status_code == 401

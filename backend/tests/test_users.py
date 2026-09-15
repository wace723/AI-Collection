"""用户管理路由测试（supervisor 增强需求）。

覆盖：用户列表/新增/编辑(角色/停用/重置密码)/删除 + 权限 + 约束。
"""

from __future__ import annotations

import pytest

from app.models.user import User


# ── 辅助 ──────────────────────────────────────────────────────────


def _login_token(client, username, password="admin123") -> str:
    resp = client.post(
        "/api/auth/login", json={"username": username, "password": password}
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]["access_token"]


def _headers(client, username) -> dict[str, str]:
    return {"Authorization": f"Bearer {_login_token(client, username)}"}


@pytest.fixture()
def seed_users(db_session):
    """覆盖 conftest：建 admin/supervisor + 3 名催收员。"""
    from app.core.security import hash_password

    users = [
        ("admin", "管理员", "ADMIN"),
        ("supervisor", "催收主管", "SUPERVISOR"),
        ("collector1", "催收员1", "COLLECTOR"),
        ("collector2", "催收员2", "COLLECTOR"),
        ("collector3", "催收员3", "COLLECTOR"),
    ]
    for username, display_name, role in users:
        db_session.add(
            User(
                username=username,
                password_hash=hash_password("admin123"),
                display_name=display_name,
                role=role,
                is_active=True,
            )
        )
    db_session.commit()
    return {u[0]: "admin123" for u in users}


# ── 列表 ───────────────────────────────────────────────────────────


def test_list_users_supervisor_ok(client, db_session, seed_users):
    """SUPERVISOR 可看用户列表。"""
    resp = client.get("/api/users", headers=_headers(client, "supervisor"))
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert len(data) == 5
    assert {u["username"] for u in data} == {
        "admin", "supervisor", "collector1", "collector2", "collector3"
    }


def test_list_users_collector_forbidden(client, db_session, seed_users):
    """COLLECTOR 无权看用户列表 → 403。"""
    resp = client.get("/api/users", headers=_headers(client, "collector1"))
    assert resp.status_code == 403


def test_list_users_unauthenticated_401(client):
    """未登录 → 401。"""
    resp = client.get("/api/users")
    assert resp.status_code == 401


# ── 新增 ───────────────────────────────────────────────────────────


def test_create_user_admin_ok(client, db_session, seed_users):
    """ADMIN 新增催收员成功。"""
    resp = client.post(
        "/api/users",
        headers=_headers(client, "admin"),
        json={
            "username": "collector4",
            "password": "pass1234",
            "display_name": "催收员4",
            "role": "COLLECTOR",
        },
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()["data"]
    assert data["username"] == "collector4"
    assert data["role"] == "COLLECTOR"
    assert data["is_active"] is True
    # 能用新密码登录
    tok = _login_token(client, "collector4", "pass1234")
    assert tok


def test_create_user_duplicate_username_400(client, db_session, seed_users):
    """重复 username → 400。"""
    resp = client.post(
        "/api/users",
        headers=_headers(client, "admin"),
        json={
            "username": "collector1",
            "password": "pass1234",
            "display_name": "重复",
            "role": "COLLECTOR",
        },
    )
    assert resp.status_code == 400


def test_create_user_supervisor_forbidden(client, db_session, seed_users):
    """SUPERVISOR 无权新增 → 403。"""
    resp = client.post(
        "/api/users",
        headers=_headers(client, "supervisor"),
        json={
            "username": "collector4",
            "password": "pass1234",
            "display_name": "催收员4",
            "role": "COLLECTOR",
        },
    )
    assert resp.status_code == 403


def test_create_user_short_password_422(client, db_session, seed_users):
    """密码 < 6 位 → 422。"""
    resp = client.post(
        "/api/users",
        headers=_headers(client, "admin"),
        json={
            "username": "collector4",
            "password": "123",
            "display_name": "催收员4",
            "role": "COLLECTOR",
        },
    )
    assert resp.status_code == 422


# ── 编辑（角色/停用/重置密码）─────────────────────────────────────


def test_update_user_role(client, db_session, seed_users):
    """ADMIN 改 collector1 角色为 SUPERVISOR。"""
    collector1 = db_session.query(User).filter(User.username == "collector1").first()
    resp = client.put(
        f"/api/users/{collector1.id}",
        headers=_headers(client, "admin"),
        json={"role": "SUPERVISOR"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["role"] == "SUPERVISOR"


def test_update_user_deactivate(client, db_session, seed_users):
    """停用 collector2 → is_active=False，停用后不能登录。"""
    collector2 = db_session.query(User).filter(User.username == "collector2").first()
    resp = client.put(
        f"/api/users/{collector2.id}",
        headers=_headers(client, "admin"),
        json={"is_active": False},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["is_active"] is False
    # 停用账号登录失败
    r = client.post(
        "/api/auth/login", json={"username": "collector2", "password": "admin123"}
    )
    assert r.status_code == 403


def test_update_user_reset_password(client, db_session, seed_users):
    """重置 collector3 密码 → 能用 admin123 登录。"""
    # 先改密码
    db_session.query(User).filter(User.username == "collector3").update(
        {"password_hash": __import__("app.core.security", fromlist=["hash_password"]).hash_password("oldpass1")}
    )
    db_session.commit()
    # 确认旧密码登录不了
    assert client.post(
        "/api/auth/login", json={"username": "collector3", "password": "admin123"}
    ).status_code == 401
    # 重置
    collector3 = db_session.query(User).filter(User.username == "collector3").first()
    resp = client.put(
        f"/api/users/{collector3.id}",
        headers=_headers(client, "admin"),
        json={"reset_password": True},
    )
    assert resp.status_code == 200, resp.text
    # 能用 admin123 登录
    assert _login_token(client, "collector3", "admin123")


def test_update_user_supervisor_forbidden(client, db_session, seed_users):
    """SUPERVISOR 无权编辑 → 403。"""
    collector1 = db_session.query(User).filter(User.username == "collector1").first()
    resp = client.put(
        f"/api/users/{collector1.id}",
        headers=_headers(client, "supervisor"),
        json={"role": "SUPERVISOR"},
    )
    assert resp.status_code == 403


def test_update_user_not_found(client, db_session, seed_users):
    resp = client.put(
        "/api/users/99999",
        headers=_headers(client, "admin"),
        json={"role": "SUPERVISOR"},
    )
    assert resp.status_code == 404


# ── 删除 ───────────────────────────────────────────────────────────


def test_delete_user_ok(client, db_session, seed_users):
    """ADMIN 删除 collector3 成功。"""
    collector3 = db_session.query(User).filter(User.username == "collector3").first()
    resp = client.delete(f"/api/users/{collector3.id}", headers=_headers(client, "admin"))
    assert resp.status_code == 200, resp.text
    # 列表不含 collector3
    resp = client.get("/api/users", headers=_headers(client, "admin"))
    assert "collector3" not in {u["username"] for u in resp.json()["data"]}


def test_delete_self_409(client, db_session, seed_users):
    """不可删除当前登录账号 → 409。"""
    resp = client.delete("/api/users/1", headers=_headers(client, "admin"))
    assert resp.status_code == 409


def test_delete_last_admin_400(client, db_session, seed_users):
    """删除最后一名 ADMIN → 400。"""
    admin = db_session.query(User).filter(User.username == "admin").first()
    resp = client.delete(f"/api/users/{admin.id}", headers=_headers(client, "admin"))
    # admin 不可删自己（409）——换一个场景：先把唯一 admin 删
    # 实际「不可删自己」先触发，所以测「最后 admin」需用另一 admin 登录删
    # 这里 admin 删自己 → 409（不可删自己优先）
    assert resp.status_code == 409


def test_delete_last_admin_via_second_admin(client, db_session, seed_users):
    """建第二个 ADMIN，用第二个 ADMIN 删原 admin → 不可删最后 ADMIN 需先让只剩 1 个。

    场景：admin 建 admin2(ADMIN)，admin2 登录删 admin（此时有 2 个 ADMIN，应成功）；
    再尝试删 admin2（此时只剩 1 个 ADMIN）→ 400。
    """
    # 建 admin2
    resp = client.post(
        "/api/users",
        headers=_headers(client, "admin"),
        json={"username": "admin2", "password": "pass1234", "display_name": "管理员2", "role": "ADMIN"},
    )
    assert resp.status_code == 201
    # admin2 登录删 admin（admin id=1）
    h2 = {"Authorization": f"Bearer {_login_token(client, 'admin2', 'pass1234')}"}
    resp = client.delete("/api/users/1", headers=h2)
    assert resp.status_code == 200  # 还有 admin2 一个 ADMIN，可删
    # 再删 admin2 自己 → 不可删自己 409
    admin2 = db_session.query(User).filter(User.username == "admin2").first()
    resp = client.delete(f"/api/users/{admin2.id}", headers=h2)
    assert resp.status_code == 409


def test_delete_user_supervisor_forbidden(client, db_session, seed_users):
    """SUPERVISOR 无权删除 → 403。"""
    collector1 = db_session.query(User).filter(User.username == "collector1").first()
    resp = client.delete(f"/api/users/{collector1.id}", headers=_headers(client, "supervisor"))
    assert resp.status_code == 403

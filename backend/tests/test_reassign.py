"""手动改派任务测试（supervisor 增强需求，F-TASK-04）。

覆盖：改派 PENDING/IN_PROGRESS、终态不可改派、目标催收员校验、权限。
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.models.order import Order
from app.models.task import Task
from app.models.user import User
from app.services.risk_engine import seed_default_config
from app.services.task_engine import assign_pending_tasks


# ── 辅助 ──────────────────────────────────────────────────────────


def _login_token(client, username, password="admin123") -> str:
    resp = client.post(
        "/api/auth/login", json={"username": username, "password": password}
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]["access_token"]


def _headers(client, username) -> dict[str, str]:
    return {"Authorization": f"Bearer {_login_token(client, username)}"}


def _make_order(db, order_no, *, risk_tier="HIGH") -> Order:
    order = Order(
        supplier_no="S001",
        supplier_name=f"供应商{order_no}",
        biz_no="B001",
        service_fee_order_no=order_no,
        win_bid_date=date(2026, 8, 15),
        risk_tier=risk_tier,
        pay_status=None,
    )
    db.add(order)
    db.flush()
    return order


def _make_task(db, order, *, status="PENDING", assignee_id=None, risk_tier="HIGH") -> Task:
    task = Task(
        order_id=order.id,
        service_fee_order_no=order.service_fee_order_no,
        risk_tier=risk_tier,
        scene="FIRST",
        day_offset=7,
        due_date=order.win_bid_date + timedelta(days=7),
        status=status,
        batch_id="2026-09-15",
        assignee_id=assignee_id,
    )
    db.add(task)
    db.flush()
    return task


@pytest.fixture()
def seed_users(db_session):
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


@pytest.fixture()
def seed_risk_config(db_session):
    seed_default_config(db_session)


def _collectors(db) -> list[User]:
    return (
        db.query(User).filter(User.role == "COLLECTOR").order_by(User.id).all()
    )


# ── 改派 PENDING ──────────────────────────────────────────────────


def test_reassign_pending_task(client, db_session, seed_users, seed_risk_config):
    """SUPERVISOR 改派 PENDING 任务：assignee 变更，状态仍 PENDING。"""
    cols = _collectors(db_session)
    o = _make_order(db_session, "RA01")
    t = _make_task(db_session, o, status="PENDING", assignee_id=cols[0].id)
    db_session.commit()

    resp = client.post(
        f"/api/tasks/{t.id}/reassign?assignee_id={cols[1].id}",
        headers=_headers(client, "supervisor"),
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["assignee_id"] == cols[1].id
    assert data["status"] == "PENDING"  # 状态不变
    assert data["supplier_name"] == "供应商RA01"  # 附带 supplier_name


def test_reassign_in_progress_back_to_pending(client, db_session, seed_users, seed_risk_config):
    """改派 IN_PROGRESS 任务：退回 PENDING，assignee 变更。"""
    cols = _collectors(db_session)
    o = _make_order(db_session, "RA02")
    t = _make_task(db_session, o, status="IN_PROGRESS", assignee_id=cols[0].id)
    db_session.commit()

    resp = client.post(
        f"/api/tasks/{t.id}/reassign?assignee_id={cols[2].id}",
        headers=_headers(client, "supervisor"),
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["assignee_id"] == cols[2].id
    assert data["status"] == "PENDING"  # IN_PROGRESS 退回 PENDING


# ── 终态不可改派 ─────────────────────────────────────────────────


def test_reassign_done_task_400(client, db_session, seed_users, seed_risk_config):
    """终态 DONE 不可改派 → 400。"""
    cols = _collectors(db_session)
    o = _make_order(db_session, "RA03")
    t = _make_task(db_session, o, status="DONE", assignee_id=cols[0].id)
    t.result = "PAID"
    db_session.commit()

    resp = client.post(
        f"/api/tasks/{t.id}/reassign?assignee_id={cols[1].id}",
        headers=_headers(client, "supervisor"),
    )
    assert resp.status_code == 400


def test_reassign_cancelled_task_400(client, db_session, seed_users, seed_risk_config):
    """终态 CANCELLED 不可改派 → 400。"""
    cols = _collectors(db_session)
    o = _make_order(db_session, "RA04")
    t = _make_task(db_session, o, status="CANCELLED", assignee_id=cols[0].id)
    db_session.commit()

    resp = client.post(
        f"/api/tasks/{t.id}/reassign?assignee_id={cols[1].id}",
        headers=_headers(client, "supervisor"),
    )
    assert resp.status_code == 400


# ── 目标催收员校验 ───────────────────────────────────────────────


def test_reassign_to_nonexistent_user_400(client, db_session, seed_users, seed_risk_config):
    """改派给不存在的用户 → 400。"""
    cols = _collectors(db_session)
    o = _make_order(db_session, "RA05")
    t = _make_task(db_session, o, status="PENDING", assignee_id=cols[0].id)
    db_session.commit()

    resp = client.post(
        f"/api/tasks/{t.id}/reassign?assignee_id=99999",
        headers=_headers(client, "supervisor"),
    )
    assert resp.status_code == 400


def test_reassign_to_non_collector_400(client, db_session, seed_users, seed_risk_config):
    """改派给非催收员角色（supervisor）→ 400。"""
    cols = _collectors(db_session)
    o = _make_order(db_session, "RA06")
    t = _make_task(db_session, o, status="PENDING", assignee_id=cols[0].id)
    db_session.commit()
    supervisor = db_session.query(User).filter(User.username == "supervisor").first()

    resp = client.post(
        f"/api/tasks/{t.id}/reassign?assignee_id={supervisor.id}",
        headers=_headers(client, "supervisor"),
    )
    assert resp.status_code == 400


def test_reassign_to_inactive_collector_400(client, db_session, seed_users, seed_risk_config):
    """改派给已停用的催收员 → 400。"""
    cols = _collectors(db_session)
    o = _make_order(db_session, "RA07")
    t = _make_task(db_session, o, status="PENDING", assignee_id=cols[0].id)
    # 停用 collector3
    cols[2].is_active = False
    db_session.commit()

    resp = client.post(
        f"/api/tasks/{t.id}/reassign?assignee_id={cols[2].id}",
        headers=_headers(client, "supervisor"),
    )
    assert resp.status_code == 400


# ── 任务不存在 + 权限 ────────────────────────────────────────────


def test_reassign_task_not_found_404(client, db_session, seed_users, seed_risk_config):
    cols = _collectors(db_session)
    resp = client.post(
        f"/api/tasks/99999/reassign?assignee_id={cols[0].id}",
        headers=_headers(client, "supervisor"),
    )
    assert resp.status_code == 404


def test_reassign_collector_forbidden(client, db_session, seed_users, seed_risk_config):
    """COLLECTOR 无权改派 → 403。"""
    cols = _collectors(db_session)
    o = _make_order(db_session, "RA08")
    t = _make_task(db_session, o, status="PENDING", assignee_id=cols[0].id)
    db_session.commit()

    resp = client.post(
        f"/api/tasks/{t.id}/reassign?assignee_id={cols[1].id}",
        headers=_headers(client, "collector1"),
    )
    assert resp.status_code == 403


def test_reassign_admin_ok(client, db_session, seed_users, seed_risk_config):
    """ADMIN 也可改派。"""
    cols = _collectors(db_session)
    o = _make_order(db_session, "RA09")
    t = _make_task(db_session, o, status="PENDING", assignee_id=cols[0].id)
    db_session.commit()

    resp = client.post(
        f"/api/tasks/{t.id}/reassign?assignee_id={cols[1].id}",
        headers=_headers(client, "admin"),
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["assignee_id"] == cols[1].id


def test_reassign_unauthenticated_401(client, db_session, seed_users, seed_risk_config):
    cols = _collectors(db_session)
    o = _make_order(db_session, "RA10")
    t = _make_task(db_session, o, status="PENDING", assignee_id=cols[0].id)
    db_session.commit()

    resp = client.post(
        f"/api/tasks/{t.id}/reassign?assignee_id={cols[1].id}"
    )
    assert resp.status_code == 401

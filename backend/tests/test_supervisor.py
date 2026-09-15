"""员工绩效统计测试（supervisor 增强需求）。

覆盖：staff-performance 各催收员统计正确 + 权限。
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.models.order import Order
from app.models.task import Task, TaskResult
from app.models.user import User
from app.services.risk_engine import seed_default_config


def _login_token(client, username, password="admin123") -> str:
    resp = client.post(
        "/api/auth/login", json={"username": username, "password": password}
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]["access_token"]


def _headers(client, username) -> dict[str, str]:
    return {"Authorization": f"Bearer {_login_token(client, username)}"}


def _make_order(db, order_no) -> Order:
    order = Order(
        supplier_no="S001",
        supplier_name=f"供应商{order_no}",
        biz_no="B001",
        service_fee_order_no=order_no,
        win_bid_date=date(2026, 8, 15),
        risk_tier="HIGH",
        pay_status=None,
    )
    db.add(order)
    db.flush()
    return order


def _make_task(db, order, *, status="PENDING", assignee_id, result=None) -> Task:
    task = Task(
        order_id=order.id,
        service_fee_order_no=order.service_fee_order_no,
        risk_tier="HIGH",
        scene="FIRST",
        day_offset=7,
        due_date=order.win_bid_date + timedelta(days=7),
        status=status,
        batch_id="2026-09-15",
        assignee_id=assignee_id,
        result=result,
    )
    db.add(task)
    db.flush()
    return task


def _make_result(db, task, collector_id, *, result="PAID") -> TaskResult:
    tr = TaskResult(task_id=task.id, collector_id=collector_id, result=result)
    db.add(tr)
    db.flush()
    return tr


@pytest.fixture()
def seed_users(db_session):
    from app.core.security import hash_password

    users = [
        ("admin", "管理员", "ADMIN"),
        ("supervisor", "催收主管", "SUPERVISOR"),
        ("collector1", "催收员1", "COLLECTOR"),
        ("collector2", "催收员2", "COLLECTOR"),
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


def test_staff_performance_counts(client, db_session, seed_users, seed_risk_config):
    """各催收员统计正确：待处理/进行中/已完成/回款数/回款率。"""
    cols = _collectors(db_session)
    c1, c2 = cols[0].id, cols[1].id

    # collector1: 2 PENDING + 1 IN_PROGRESS + 2 DONE(其中1个 PAID，1个 DISPUTE)
    o1 = _make_order(db_session, "SP01")
    o2 = _make_order(db_session, "SP02")
    o3 = _make_order(db_session, "SP03")
    o4 = _make_order(db_session, "SP04")
    o5 = _make_order(db_session, "SP05")
    t1 = _make_task(db_session, o1, status="PENDING", assignee_id=c1)
    t2 = _make_task(db_session, o2, status="PENDING", assignee_id=c1)
    t3 = _make_task(db_session, o3, status="IN_PROGRESS", assignee_id=c1)
    t4 = _make_task(db_session, o4, status="DONE", assignee_id=c1, result="PAID")
    t5 = _make_task(db_session, o5, status="DONE", assignee_id=c1, result="DISPUTE")
    _make_result(db_session, t4, c1, result="PAID")
    # t5 是 DISPUTE，不产生 PAID 明细

    # collector2: 1 DONE(PAID)
    o6 = _make_order(db_session, "SP06")
    t6 = _make_task(db_session, o6, status="DONE", assignee_id=c2, result="PAID")
    _make_result(db_session, t6, c2, result="PAID")
    db_session.commit()

    resp = client.get(
        "/api/supervisor/staff-performance", headers=_headers(client, "supervisor")
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    perf_map = {p["id"]: p for p in data}

    # collector1: pending=2, in_progress=1, done=2, paid=1, rate=0.5
    p1 = perf_map[c1]
    assert p1["pending_count"] == 2
    assert p1["in_progress_count"] == 1
    assert p1["done_count"] == 2
    assert p1["paid_count"] == 1
    assert p1["paid_rate"] == 0.5

    # collector2: pending=0, in_progress=0, done=1, paid=1, rate=1.0
    p2 = perf_map[c2]
    assert p2["pending_count"] == 0
    assert p2["done_count"] == 1
    assert p2["paid_count"] == 1
    assert p2["paid_rate"] == 1.0


def test_staff_performance_empty(client, db_session, seed_users, seed_risk_config):
    """无任务时统计全 0，回款率 0.0。"""
    resp = client.get(
        "/api/supervisor/staff-performance", headers=_headers(client, "supervisor")
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert len(data) == 2  # collector1, collector2
    for p in data:
        assert p["pending_count"] == 0
        assert p["paid_count"] == 0
        assert p["paid_rate"] == 0.0


def test_staff_performance_collector_forbidden(client, db_session, seed_users, seed_risk_config):
    """COLLECTOR 无权看绩效 → 403。"""
    resp = client.get(
        "/api/supervisor/staff-performance", headers=_headers(client, "collector1")
    )
    assert resp.status_code == 403


def test_staff_performance_unauthenticated_401(client):
    resp = client.get("/api/supervisor/staff-performance")
    assert resp.status_code == 401


def test_staff_performance_admin_ok(client, db_session, seed_users, seed_risk_config):
    """ADMIN 可看绩效。"""
    resp = client.get(
        "/api/supervisor/staff-performance", headers=_headers(client, "admin")
    )
    assert resp.status_code == 200

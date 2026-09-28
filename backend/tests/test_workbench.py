"""wb-001 催收工作台后端测试（data-003 重写：两分类回填 + collection_state）。

覆盖：列表只看自己、风险+账龄排序、两分类回填（REACHED→DONE+COLLECTED，
UNREACHED→保持 IN_PROGRESS+PENDING_COLLECTION）、同日反复回填、权限控制、
详情/分页/状态过滤/collection_state 过滤边界。
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.models.order import Order, OrderFeature
from app.models.task import Task, TaskResult
from app.models.user import User
from app.services.risk_engine import seed_default_config
from app.services.risk_engine.config_service import get_current_config
from app.services.task_engine import assign_pending_tasks
from app.services.task_engine.states import (
    COLLECTED,
    IN_PROGRESS,
    PENDING_COLLECTION,
    REACHED,
    UNREACHED,
)


# ── 辅助 ──────────────────────────────────────────────────────────


def _login_token(client, username, password="admin123") -> str:
    resp = client.post(
        "/api/auth/login", json={"username": username, "password": password}
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]["access_token"]


def _headers(client, username) -> dict[str, str]:
    return {"Authorization": f"Bearer {_login_token(client, username)}"}


def _make_order(
    db, order_no, win_bid_date=date(2026, 8, 15), risk_tier="HIGH"
) -> Order:
    order = Order(
        supplier_no="S001",
        supplier_name=f"供应商{order_no}",
        biz_no="B001",
        service_fee_order_no=order_no,
        win_bid_date=win_bid_date,
        risk_tier=risk_tier,
        pay_status=None,
        collection_state=PENDING_COLLECTION,
    )
    db.add(order)
    db.flush()
    db.add(
        OrderFeature(
            order_id=order.id,
            history_fee_order_count=3,
            avg_pay_duration_days=20.5,
            win_rate=0.4,
            active_90d=8,
            is_member_at_win=True,
            register_fund=5_000_000,
            supplier_categories="工程类",
        )
    )
    db.flush()
    return order


def _make_task(
    db,
    order: Order,
    *,
    risk_tier="HIGH",
    day_offset=7,
    due_date=None,
    status=IN_PROGRESS,
    assignee_id=None,
    scene="ROUND_1",
    result=None,
) -> Task:
    task = Task(
        order_id=order.id,
        service_fee_order_no=order.service_fee_order_no,
        risk_tier=risk_tier,
        scene=scene,
        day_offset=day_offset,
        due_date=due_date or (order.win_bid_date + timedelta(days=day_offset)),
        status=status,
        batch_id="2026-09-09",
        assignee_id=assignee_id,
        result=result,
    )
    db.add(task)
    db.flush()
    return task


def _collectors(db) -> list[User]:
    return (
        db.query(User).filter(User.role == "COLLECTOR").order_by(User.id).all()
    )


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


@pytest.fixture()
def seed_risk_config(db_session):
    seed_default_config(db_session)
    return get_current_config(db_session)


def _assign(db_session) -> None:
    assign_pending_tasks(db_session)


# ── TC-WB-01：催收员只见自己任务 ──────────────────────────────────


def test_collector_sees_only_own_tasks(client, db_session, seed_users, seed_risk_config):
    cols = _collectors(db_session)
    o1 = _make_order(db_session, "WB01A")
    o2 = _make_order(db_session, "WB01B")
    _make_task(db_session, o1, assignee_id=cols[0].id, status=IN_PROGRESS)
    _make_task(db_session, o2, assignee_id=cols[1].id, status=IN_PROGRESS)
    db_session.commit()

    resp = client.get("/api/tasks", headers=_headers(client, "collector1"))
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["total"] == 1
    assert data["items"][0]["service_fee_order_no"] == "WB01A"
    assert data["items"][0]["supplier_name"] == "供应商WB01A"


def test_supervisor_sees_all_tasks(client, db_session, seed_users, seed_risk_config):
    cols = _collectors(db_session)
    o1 = _make_order(db_session, "SUP1")
    o2 = _make_order(db_session, "SUP2")
    _make_task(db_session, o1, assignee_id=cols[0].id, status=IN_PROGRESS)
    _make_task(db_session, o2, assignee_id=cols[1].id, status=IN_PROGRESS)
    db_session.commit()

    resp = client.get("/api/tasks", headers=_headers(client, "supervisor"))
    assert resp.json()["data"]["total"] == 2


# ── TC-WB-02：列表按风险+账龄排序 ─────────────────────────────────


def test_list_sorted_by_risk_then_age(client, db_session, seed_users, seed_risk_config):
    cols = _collectors(db_session)
    assignee = cols[0].id
    o_h1 = _make_order(db_session, "H1", risk_tier="HIGH")
    o_h2 = _make_order(db_session, "H2", risk_tier="HIGH")
    o_m = _make_order(db_session, "M1", risk_tier="MEDIUM")
    o_l = _make_order(db_session, "L1", risk_tier="LOW")
    _make_task(
        db_session, o_h1, risk_tier="HIGH", due_date=date(2026, 9, 5), assignee_id=assignee
    )
    _make_task(
        db_session, o_h2, risk_tier="HIGH", due_date=date(2026, 9, 1), assignee_id=assignee
    )
    _make_task(
        db_session, o_m, risk_tier="MEDIUM", due_date=date(2026, 9, 3), assignee_id=assignee
    )
    _make_task(
        db_session, o_l, risk_tier="LOW", due_date=date(2026, 8, 1), assignee_id=assignee
    )
    db_session.commit()

    resp = client.get("/api/tasks", headers=_headers(client, "collector1"))
    items = resp.json()["data"]["items"]
    order_nos = [it["service_fee_order_no"] for it in items]
    assert order_nos == ["H2", "H1", "M1", "L1"]


# ── TC-WB-04：两分类回填 ───────────────────────────────────────────


def test_reached_advances_to_collected(client, db_session, seed_users, seed_risk_config):
    """回填 REACHED→Task DONE；Order.collection_state→COLLECTED；TaskResult 写入。"""
    cols = _collectors(db_session)
    o = _make_order(db_session, "RES4")
    o.collection_state = PENDING_COLLECTION
    task = _make_task(db_session, o, assignee_id=cols[0].id, status=IN_PROGRESS)
    db_session.commit()

    resp = client.post(
        f"/api/tasks/{task.id}/result",
        json={"result": REACHED, "note": "客户确认下周付款"},
        headers=_headers(client, "collector1"),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["status"] == "DONE"
    assert resp.json()["data"]["result"] == REACHED

    # 详情含订单摘要与特征
    detail = client.get(
        f"/api/tasks/{task.id}", headers=_headers(client, "collector1")
    )
    d = detail.json()["data"]
    assert d["order"]["supplier_name"] == "供应商RES4"
    assert d["feature"]["history_fee_order_count"] == 3
    assert d["collection_state"] == COLLECTED

    # Order 状态推进为已催收
    db_session.refresh(o)
    assert o.collection_state == COLLECTED

    # TaskResult 明细
    rows = db_session.query(TaskResult).filter(TaskResult.task_id == task.id).all()
    assert len(rows) == 1
    assert rows[0].result == REACHED


def test_unreached_stays_in_progress(client, db_session, seed_users, seed_risk_config):
    """回填 UNREACHED→Task 保持 IN_PROGRESS；Order 保持 PENDING_COLLECTION。"""
    cols = _collectors(db_session)
    o = _make_order(db_session, "UNR5")
    o.collection_state = PENDING_COLLECTION
    task = _make_task(db_session, o, assignee_id=cols[0].id, status=IN_PROGRESS)
    db_session.commit()

    resp = client.post(
        f"/api/tasks/{task.id}/result",
        json={"result": UNREACHED, "note": "电话无人接听"},
        headers=_headers(client, "collector1"),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["status"] == IN_PROGRESS
    assert resp.json()["data"]["result"] == UNREACHED

    db_session.refresh(o)
    assert o.collection_state == PENDING_COLLECTION


def test_unreached_repeat_same_day(client, db_session, seed_users, seed_risk_config):
    """同日可反复回填 UNREACHED，每次写一条 TaskResult 明细，Task 保持 IN_PROGRESS。"""
    cols = _collectors(db_session)
    o = _make_order(db_session, "UNR6")
    o.collection_state = PENDING_COLLECTION
    task = _make_task(db_session, o, assignee_id=cols[0].id, status=IN_PROGRESS)
    db_session.commit()

    for i in range(3):
        resp = client.post(
            f"/api/tasks/{task.id}/result",
            json={"result": UNREACHED, "note": f"第{i+1}次未接通"},
            headers=_headers(client, "collector1"),
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["status"] == IN_PROGRESS

    rows = db_session.query(TaskResult).filter(TaskResult.task_id == task.id).all()
    assert len(rows) == 3
    assert all(r.result == UNREACHED for r in rows)


def test_terminal_task_cannot_submit(client, db_session, seed_users, seed_risk_config):
    """终态任务（DONE）不可回填 → 409。"""
    cols = _collectors(db_session)
    o = _make_order(db_session, "TERM7")
    task = _make_task(db_session, o, assignee_id=cols[0].id, status="DONE", result=REACHED)
    db_session.commit()

    resp = client.post(
        f"/api/tasks/{task.id}/result",
        json={"result": REACHED, "note": "再催一次"},
        headers=_headers(client, "collector1"),
    )
    assert resp.status_code == 409


def test_collector_cannot_submit_others_task(
    client, db_session, seed_users, seed_risk_config
):
    """COLLECTOR 回填他人任务 → 403。"""
    cols = _collectors(db_session)
    o = _make_order(db_session, "OTH8")
    task = _make_task(db_session, o, assignee_id=cols[1].id, status=IN_PROGRESS)
    db_session.commit()

    resp = client.post(
        f"/api/tasks/{task.id}/result",
        json={"result": REACHED, "note": "尝试操作"},
        headers=_headers(client, "collector1"),
    )
    assert resp.status_code == 403


# ── TC-WB-06：权限控制 ─────────────────────────────────────────────


def test_collector_cannot_access_config(client, seed_users, seed_risk_config):
    resp = client.put(
        "/api/config/risk",
        json={"high_threshold": 70, "medium_threshold": 30, "schedules": []},
        headers=_headers(client, "collector1"),
    )
    assert resp.status_code == 403


# ── collection_state 过滤 ──────────────────────────────────────────


def test_list_filter_by_collection_state(
    client, db_session, seed_users, seed_risk_config
):
    """按 collection_state 过滤任务列表。"""
    cols = _collectors(db_session)
    assignee = cols[0].id
    o1 = _make_order(db_session, "PC1")
    o1.collection_state = PENDING_COLLECTION
    _make_task(db_session, o1, assignee_id=assignee, status=IN_PROGRESS)
    o2 = _make_order(db_session, "COL2")
    o2.collection_state = COLLECTED
    _make_task(db_session, o2, assignee_id=assignee, status="DONE", result=REACHED)
    db_session.commit()

    resp = client.get(
        "/api/tasks?collection_state=PENDING_COLLECTION",
        headers=_headers(client, "supervisor"),
    )
    items = resp.json()["data"]["items"]
    assert len(items) == 1
    assert items[0]["service_fee_order_no"] == "PC1"


# ── 边界 ────────────────────────────────────────────────────────────


def test_detail_not_found_404(client, seed_users, seed_risk_config):
    resp = client.get("/api/tasks/999999", headers=_headers(client, "collector1"))
    assert resp.status_code == 404


def test_collector_cannot_view_other_task(
    client, db_session, seed_users, seed_risk_config
):
    cols = _collectors(db_session)
    o = _make_order(db_session, "OTHER")
    task = _make_task(db_session, o, assignee_id=cols[1].id, status=IN_PROGRESS)
    db_session.commit()
    resp = client.get(f"/api/tasks/{task.id}", headers=_headers(client, "collector1"))
    assert resp.status_code == 403


def test_list_status_filter_and_pagination(
    client, db_session, seed_users, seed_risk_config
):
    cols = _collectors(db_session)
    assignee = cols[0].id
    for i in range(5):
        o = _make_order(db_session, f"P{i}")
        _make_task(db_session, o, assignee_id=assignee, status=IN_PROGRESS)
    for i in range(3):
        o = _make_order(db_session, f"D{i}")
        _make_task(db_session, o, assignee_id=assignee, status="DONE", result=REACHED)
    db_session.commit()

    resp = client.get(
        "/api/tasks?status=IN_PROGRESS&size=2",
        headers=_headers(client, "collector1"),
    )
    data = resp.json()["data"]
    assert data["total"] == 5
    assert len(data["items"]) == 2
    assert all(it["status"] == IN_PROGRESS for it in data["items"])


def test_list_requires_auth(client, seed_users):
    resp = client.get("/api/tasks")
    assert resp.status_code == 401

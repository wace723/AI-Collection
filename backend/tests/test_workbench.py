"""wb-001 催收工作台后端测试。

覆盖 docs/03 TC-WB-01~06：列表只看自己、风险+账龄排序、并发领取防重、
结果回填、异议可被主管查看、权限控制，以及详情/分页/状态过滤边界。
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


# ── 辅助 ──────────────────────────────────────────────────────────


def _login_token(client, username, password="admin123") -> str:
    resp = client.post(
        "/api/auth/login", json={"username": username, "password": password}
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]["access_token"]


def _headers(client, username) -> dict[str, str]:
    return {"Authorization": f"Bearer {_login_token(client, username)}"}


def _make_order(db, order_no, win_bid_date=date(2026, 8, 15), risk_tier="HIGH") -> Order:
    order = Order(
        supplier_no="S001",
        supplier_name=f"供应商{order_no}",
        biz_no="B001",
        service_fee_order_no=order_no,
        win_bid_date=win_bid_date,
        risk_tier=risk_tier,
        pay_status=None,
    )
    db.add(order)
    db.flush()
    # 附带一条特征，验证详情返回
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
    status="PENDING_ASSIGN",
    assignee_id=None,
    scene="FIRST",
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
    """U1/U2 各分配任务，U1 登录列表只看到自己的。"""
    cols = _collectors(db_session)
    o1 = _make_order(db_session, "WB01A")
    o2 = _make_order(db_session, "WB01B")
    _make_task(db_session, o1, assignee_id=cols[0].id, status="PENDING")
    _make_task(db_session, o2, assignee_id=cols[1].id, status="PENDING")
    db_session.commit()

    resp = client.get("/api/tasks", headers=_headers(client, "collector1"))
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["total"] == 1
    assert data["items"][0]["service_fee_order_no"] == "WB01A"


def test_supervisor_sees_all_tasks(client, db_session, seed_users, seed_risk_config):
    """SUPVISOR 不带 assignee 看全部任务。"""
    cols = _collectors(db_session)
    o1 = _make_order(db_session, "SUP1")
    o2 = _make_order(db_session, "SUP2")
    _make_task(db_session, o1, assignee_id=cols[0].id, status="PENDING")
    _make_task(db_session, o2, assignee_id=cols[1].id, status="PENDING")
    db_session.commit()

    resp = client.get("/api/tasks", headers=_headers(client, "supervisor"))
    assert resp.json()["data"]["total"] == 2


# ── TC-WB-02：列表按风险+账龄排序 ─────────────────────────────────


def test_list_sorted_by_risk_then_age(client, db_session, seed_users, seed_risk_config):
    """HIGH 在前；同档按账龄倒序（due_date 升序：越早越前）。"""
    cols = _collectors(db_session)
    assignee = cols[0].id
    # 三个不同档 + 同档不同 due_date
    o_h1 = _make_order(db_session, "H1", risk_tier="HIGH")
    o_h2 = _make_order(db_session, "H2", risk_tier="HIGH")
    o_m = _make_order(db_session, "M1", risk_tier="MEDIUM")
    o_l = _make_order(db_session, "L1", risk_tier="LOW")
    _make_task(db_session, o_h1, risk_tier="HIGH", due_date=date(2026, 9, 5),
               assignee_id=assignee, status="PENDING")
    _make_task(db_session, o_h2, risk_tier="HIGH", due_date=date(2026, 9, 1),
               assignee_id=assignee, status="PENDING")  # 更早 → 排在 H1 前
    _make_task(db_session, o_m, risk_tier="MEDIUM", due_date=date(2026, 9, 3),
               assignee_id=assignee, status="PENDING")
    _make_task(db_session, o_l, risk_tier="LOW", due_date=date(2026, 8, 1),
               assignee_id=assignee, status="PENDING")
    db_session.commit()

    resp = client.get("/api/tasks", headers=_headers(client, "collector1"))
    items = resp.json()["data"]["items"]
    order_nos = [it["service_fee_order_no"] for it in items]
    # H2(09-01) → H1(09-05) → M → L
    assert order_nos == ["H2", "H1", "M1", "L1"]


# ── TC-WB-03：并发领取防重 ────────────────────────────────────────


def test_claim_only_once(client, db_session, seed_users, seed_risk_config):
    """同一 PENDING 任务第二次领取 → 409（已被领取/状态不符）。"""
    cols = _collectors(db_session)
    o = _make_order(db_session, "CLAIM")
    task = _make_task(db_session, o, assignee_id=cols[0].id, status="PENDING")
    db_session.commit()

    resp = client.post(f"/api/tasks/{task.id}/claim", headers=_headers(client, "collector1"))
    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == "IN_PROGRESS"

    # 再次领取 → 409
    resp2 = client.post(f"/api/tasks/{task.id}/claim", headers=_headers(client, "collector1"))
    assert resp2.status_code == 409


# ── TC-WB-04：处理结果回填 ─────────────────────────────────────────


def test_result_paid_flow_with_detail(client, db_session, seed_users, seed_risk_config):
    """领取→回填 PAID→DONE；详情可见订单+特征；TaskResult 写入。"""
    cols = _collectors(db_session)
    o = _make_order(db_session, "RES4")
    task = _make_task(db_session, o, assignee_id=cols[0].id, status="PENDING")
    db_session.commit()

    client.post(f"/api/tasks/{task.id}/claim", headers=_headers(client, "collector1"))
    resp = client.post(
        f"/api/tasks/{task.id}/result",
        json={"result": "PAID", "note": "已结清"},
        headers=_headers(client, "collector1"),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["status"] == "DONE"

    # 详情含订单摘要与特征
    detail = client.get(f"/api/tasks/{task.id}", headers=_headers(client, "collector1"))
    d = detail.json()["data"]
    assert d["order"]["supplier_name"] == "供应商RES4"
    assert d["feature"]["history_fee_order_count"] == 3
    assert d["feature"]["is_member_at_win"] is True

    # TaskResult 明细
    rows = db_session.query(TaskResult).filter(TaskResult.task_id == task.id).all()
    assert len(rows) == 1
    assert rows[0].result == "PAID"


# ── TC-WB-05：异议处理可被主管查看 ─────────────────────────────────


def test_dispute_visible_to_supervisor(client, db_session, seed_users, seed_risk_config):
    """回填 DISPUTE→DONE；supervisor 列表能看到该异议任务。"""
    cols = _collectors(db_session)
    o = _make_order(db_session, "DIS5")
    task = _make_task(db_session, o, assignee_id=cols[0].id, status="PENDING")
    db_session.commit()

    client.post(f"/api/tasks/{task.id}/claim", headers=_headers(client, "collector1"))
    client.post(
        f"/api/tasks/{task.id}/result",
        json={"result": "DISPUTE", "note": "客户对金额有异议"},
        headers=_headers(client, "collector1"),
    )

    # supervisor 看全部，能看到该异议任务且 result=DISPUTE
    resp = client.get(
        "/api/tasks?status=DONE", headers=_headers(client, "supervisor")
    )
    items = resp.json()["data"]["items"]
    assert any(it["id"] == task.id and it["result"] == "DISPUTE" for it in items)


# ── TC-WB-06：权限控制——催收员不能访问配置后台 ───────────────────


def test_collector_cannot_access_config(client, seed_users, seed_risk_config):
    """COLLECTOR 访问 PUT /api/config/risk → 403。"""
    resp = client.put(
        "/api/config/risk",
        json={"high_threshold": 70, "medium_threshold": 30, "schedules": []},
        headers=_headers(client, "collector1"),
    )
    assert resp.status_code == 403


# ── 边界 ────────────────────────────────────────────────────────────


def test_detail_not_found_404(client, seed_users, seed_risk_config):
    resp = client.get("/api/tasks/999999", headers=_headers(client, "collector1"))
    assert resp.status_code == 404


def test_collector_cannot_view_other_task(client, db_session, seed_users, seed_risk_config):
    """COLLECTOR 查看他人任务详情 → 403。"""
    cols = _collectors(db_session)
    o = _make_order(db_session, "OTHER")
    task = _make_task(db_session, o, assignee_id=cols[1].id, status="PENDING")
    db_session.commit()
    resp = client.get(f"/api/tasks/{task.id}", headers=_headers(client, "collector1"))
    assert resp.status_code == 403


def test_list_status_filter_and_pagination(client, db_session, seed_users, seed_risk_config):
    """status 过滤 + 分页 size 控制。"""
    cols = _collectors(db_session)
    assignee = cols[0].id
    for i in range(5):
        o = _make_order(db_session, f"P{i}")
        _make_task(db_session, o, assignee_id=assignee, status="PENDING")
    for i in range(3):
        o = _make_order(db_session, f"D{i}")
        _make_task(db_session, o, assignee_id=assignee, status="DONE")
    db_session.commit()

    # 只看 PENDING
    resp = client.get(
        "/api/tasks?status=PENDING&size=2", headers=_headers(client, "collector1")
    )
    data = resp.json()["data"]
    assert data["total"] == 5
    assert len(data["items"]) == 2
    assert data["page"] == 1
    assert data["limit"] == 2
    assert all(it["status"] == "PENDING" for it in data["items"])


def test_list_requires_auth(client, seed_users):
    resp = client.get("/api/tasks")
    assert resp.status_code == 401

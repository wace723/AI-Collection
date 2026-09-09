"""task-002 任务分配与状态机测试。

覆盖 docs/03 TC-TASK-09/10/11/12 + 幂等不重复分配 + 权限边界。
分配核心逻辑直接调 service 注入控制；状态机走 API 端到端。
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.models.order import Order
from app.models.task import Task, TaskResult
from app.models.user import User
from app.services.risk_engine import seed_default_config
from app.services.risk_engine.config_service import get_current_config
from app.services.task_engine import (
    AssignmentError,
    assign_pending_tasks,
    claim_task,
    generate_tasks,
    submit_result,
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


def _make_order(db, order_no, win_bid_date, risk_tier="HIGH") -> Order:
    order = Order(
        supplier_no="S001",
        supplier_name="测试供应商",
        biz_no="B001",
        service_fee_order_no=order_no,
        win_bid_date=win_bid_date,
        risk_tier=risk_tier,
        pay_status=None,
    )
    db.add(order)
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
        db.query(User)
        .filter(User.role == "COLLECTOR")
        .order_by(User.id)
        .all()
    )


@pytest.fixture()
def seed_users(db_session):
    """覆盖 conftest：建完整团队 admin/supervisor + 3 名催收员。

    本模块用例需要 3 名催收员验证负载均衡；conftest 的 seed_users 仅 1 名。
    pytest 中模块级同名 fixture 覆盖 conftest 同名 fixture。
    """
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


def _generate_some(db, today=date(2026, 9, 8)) -> None:
    """跑一次 generate_tasks 生成 PENDING_ASSIGN 任务。"""
    generate_tasks(db, today=today)


# ── TC-TASK-09：高风险优先 + 负载均衡 ─────────────────────────────


def test_assign_high_priority_and_load_balanced(db_session, seed_users, seed_risk_config):
    """3H/2M/1L 六任务，3 催收员初始 0 → 各分 2 个，HIGH 全部分完才分 MEDIUM。"""
    # 用不同 win_bid_date 构造不同风险档任务（绕过 generate，直接造 PENDING_ASSIGN）
    order_h1 = _make_order(db_session, "H1", date(2026, 8, 15), "HIGH")
    order_h2 = _make_order(db_session, "H2", date(2026, 8, 15), "HIGH")
    order_h3 = _make_order(db_session, "H3", date(2026, 8, 15), "HIGH")
    order_m1 = _make_order(db_session, "M1", date(2026, 8, 8), "MEDIUM")
    order_m2 = _make_order(db_session, "M2", date(2026, 8, 8), "MEDIUM")
    order_l1 = _make_order(db_session, "L1", date(2026, 6, 8), "LOW")
    for o, tier in [
        (order_h1, "HIGH"), (order_h2, "HIGH"), (order_h3, "HIGH"),
        (order_m1, "MEDIUM"), (order_m2, "MEDIUM"), (order_l1, "LOW"),
    ]:
        _make_task(db_session, o, risk_tier=tier, due_date=date(2026, 9, 7))
    db_session.commit()

    result = assign_pending_tasks(db_session)

    assert result.assigned == 6
    assert result.skipped == 0
    cols = _collectors(db_session)
    # 各催收员分到 2 个（负载均衡，差 ≤ 1）
    counts = {c.id: result.by_assignee.get(c.id, 0) for c in cols}
    assert list(counts.values()) == [2, 2, 2]

    # HIGH 三个分别分给 U1/U2/U3 各 1
    high_tasks = (
        db_session.query(Task).filter(Task.risk_tier == "HIGH").all()
    )
    assert {t.assignee_id for t in high_tasks} == {cols[0].id, cols[1].id, cols[2].id}
    assert all(t.status == "PENDING" for t in high_tasks)
    assert all(t.assigned_at is not None for t in high_tasks)


def test_assign_order_high_before_medium(db_session, seed_users, seed_risk_config):
    """高风险全部排在前：第一个 HIGH 给 U1，第二个给 U2 ... 再轮 MEDIUM。"""
    o1 = _make_order(db_session, "P1", date(2026, 8, 15), "HIGH")
    o2 = _make_order(db_session, "P2", date(2026, 8, 15), "MEDIUM")
    _make_task(db_session, o1, risk_tier="HIGH", due_date=date(2026, 9, 7))
    _make_task(db_session, o2, risk_tier="MEDIUM", due_date=date(2026, 9, 7))
    db_session.commit()

    result = assign_pending_tasks(db_session)
    cols = _collectors(db_session)
    high = db_session.query(Task).filter(Task.risk_tier == "HIGH").first()
    med = db_session.query(Task).filter(Task.risk_tier == "MEDIUM").first()
    # HIGH 先分给最小 id 的 U1；MEDIUM 再分给负载最低（U2）
    assert high.assignee_id == cols[0].id
    assert med.assignee_id == cols[1].id
    assert result.assigned == 2


# ── TC-TASK-10：负载不均时补齐 ─────────────────────────────────────


def test_assign_to_lowest_load(db_session, seed_users, seed_risk_config):
    """U1 已 5、U2 已 4、U3 已 0 待处理 → 新任务分给 U3。"""
    cols = _collectors(db_session)
    o_base = _make_order(db_session, "BASE", date(2026, 8, 15), "HIGH")
    # 给 U1 5 个 PENDING、U2 4 个、U3 0 个
    for i in range(5):
        _make_task(
            db_session, o_base, risk_tier="HIGH", due_date=date(2026, 9, 7),
            status="PENDING", assignee_id=cols[0].id, day_offset=7 + i,
        )
    for i in range(4):
        _make_task(
            db_session, o_base, risk_tier="HIGH", due_date=date(2026, 9, 7),
            status="PENDING", assignee_id=cols[1].id, day_offset=100 + i,
        )
    # 一个新 PENDING_ASSIGN 待分配
    o_new = _make_order(db_session, "NEW", date(2026, 8, 15), "HIGH")
    _make_task(db_session, o_new, risk_tier="HIGH", due_date=date(2026, 9, 7))
    db_session.commit()

    assign_pending_tasks(db_session)

    new_task = (
        db_session.query(Task).filter(Task.service_fee_order_no == "NEW").first()
    )
    assert new_task.assignee_id == cols[2].id  # U3 负载最低


# ── 幂等：已分配/处理中不重复分配 ──────────────────────────────────


def test_already_assigned_not_reassigned(db_session, seed_users, seed_risk_config):
    """已 PENDING/IN_PROGRESS/DONE 的任务不会被再次分配。"""
    cols = _collectors(db_session)
    o = _make_order(db_session, "X", date(2026, 8, 15), "HIGH")
    _make_task(db_session, o, risk_tier="HIGH", due_date=date(2026, 9, 7),
               status="PENDING", assignee_id=cols[0].id, day_offset=7)
    _make_task(db_session, o, risk_tier="HIGH", due_date=date(2026, 9, 7),
               status="IN_PROGRESS", assignee_id=cols[1].id, day_offset=15)
    _make_task(db_session, o, risk_tier="HIGH", due_date=date(2026, 9, 7),
               status="DONE", assignee_id=cols[2].id, day_offset=30, )
    db_session.commit()

    result = assign_pending_tasks(db_session)
    assert result.assigned == 0  # 无 PENDING_ASSIGN


def test_repeat_assign_is_idempotent(db_session, seed_users, seed_risk_config):
    """同一批 PENDING_ASSIGN 跑两次分配，第二次无新增。"""
    o = _make_order(db_session, "R", date(2026, 8, 15), "HIGH")
    _make_task(db_session, o, risk_tier="HIGH", due_date=date(2026, 9, 7))
    db_session.commit()

    r1 = assign_pending_tasks(db_session)
    assert r1.assigned == 1
    r2 = assign_pending_tasks(db_session)
    assert r2.assigned == 0


def test_no_collectors_returns_skipped(db_session, seed_users, seed_risk_config):
    """无活跃催收员：不分配，记录 skipped 数量。"""
    # 把所有 collector 置为 inactive
    db_session.query(User).filter(User.role == "COLLECTOR").update(
        {User.is_active: False}
    )
    db_session.commit()
    o = _make_order(db_session, "NC", date(2026, 8, 15), "HIGH")
    _make_task(db_session, o, risk_tier="HIGH", due_date=date(2026, 9, 7))
    db_session.commit()

    result = assign_pending_tasks(db_session)
    assert result.assigned == 0
    assert result.skipped == 1


# ── TC-TASK-11：状态机流转 PENDING_ASSIGN→PENDING→IN_PROGRESS→DONE ──


def test_state_machine_flow_via_api(client, db_session, seed_users, seed_risk_config):
    """分配 → 领取 → 回填 PAID → DONE；终态不可再操作。"""
    o = _make_order(db_session, "FLOW", date(2026, 8, 15), "HIGH")
    task = _make_task(db_session, o, risk_tier="HIGH", due_date=date(2026, 9, 7))
    db_session.commit()

    # 分配（ADMIN）
    resp = client.post("/api/tasks/assign/run", headers=_headers(client, "admin"))
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["assigned"] == 1

    db_session.expire_all()
    cols = _collectors(db_session)
    task = db_session.get(Task, task.id)
    assert task.status == "PENDING"
    assignee = task.assignee_id
    assignee_name = next(c.username for c in cols if c.id == assignee)

    # 领取（被分配的催收员）
    resp = client.post(
        f"/api/tasks/{task.id}/claim", headers=_headers(client, assignee_name)
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["status"] == "IN_PROGRESS"

    # 回填 PAID → DONE
    resp = client.post(
        f"/api/tasks/{task.id}/result",
        json={"result": "PAID", "note": "已结清"},
        headers=_headers(client, assignee_name),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()["data"]
    assert body["status"] == "DONE"
    assert body["result"] == "PAID"

    # 终态不可再领取 → 409
    resp = client.post(
        f"/api/tasks/{task.id}/claim", headers=_headers(client, assignee_name)
    )
    assert resp.status_code == 409

    # 写入 TaskResult 明细
    rows = db_session.query(TaskResult).filter(TaskResult.task_id == task.id).all()
    assert len(rows) == 1
    assert rows[0].result == "PAID"


# ── TC-TASK-12：承诺还款触发改期 ───────────────────────────────────


def test_promise_result_reschedules(client, db_session, seed_users, seed_risk_config):
    """result=PROMISE + next_followup_date → 任务回 PENDING；缺失改期日 → 409。"""
    o = _make_order(db_session, "PROM", date(2026, 8, 15), "HIGH")
    task = _make_task(db_session, o, risk_tier="HIGH", due_date=date(2026, 9, 7))
    db_session.commit()

    client.post("/api/tasks/assign/run", headers=_headers(client, "admin"))
    db_session.expire_all()
    task = db_session.get(Task, task.id)
    assignee_name = next(
        c.username for c in _collectors(db_session) if c.id == task.assignee_id
    )

    # 领取
    client.post(
        f"/api/tasks/{task.id}/claim", headers=_headers(client, assignee_name)
    )

    # PROMISE 缺改期日 → 409
    resp = client.post(
        f"/api/tasks/{task.id}/result",
        json={"result": "PROMISE"},
        headers=_headers(client, assignee_name),
    )
    assert resp.status_code == 409

    # PROMISE 带改期日 → PENDING + next_followup_date
    followup = (date.today() + timedelta(days=7)).isoformat()
    resp = client.post(
        f"/api/tasks/{task.id}/result",
        json={"result": "PROMISE", "next_followup_date": followup, "note": "承诺下周还"},
        headers=_headers(client, assignee_name),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()["data"]
    assert body["status"] == "PENDING"
    assert body["next_followup_date"] == followup

    # 改期后可再次领取（新一轮催收）
    resp = client.post(
        f"/api/tasks/{task.id}/claim", headers=_headers(client, assignee_name)
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == "IN_PROGRESS"


# ── 权限边界 ────────────────────────────────────────────────────────


def test_collector_cannot_claim_others_task(client, db_session, seed_users, seed_risk_config):
    """COLLECTOR 不能领取分配给别人的任务 → 409。"""
    o = _make_order(db_session, "OTHER", date(2026, 8, 15), "HIGH")
    task = _make_task(db_session, o, risk_tier="HIGH", due_date=date(2026, 9, 7))
    db_session.commit()
    client.post("/api/tasks/assign/run", headers=_headers(client, "admin"))
    db_session.expire_all()
    task = db_session.get(Task, task.id)
    # task 的 assignee 是某 collector，用另一个 collector 登录领取
    cols = _collectors(db_session)
    other = next(c for c in cols if c.id != task.assignee_id)
    resp = client.post(
        f"/api/tasks/{task.id}/claim", headers=_headers(client, other.username)
    )
    assert resp.status_code == 409


def test_assign_requires_admin(client, seed_users, seed_risk_config):
    """COLLECTOR 触发分配 → 403。"""
    resp = client.post(
        "/api/tasks/assign/run", headers=_headers(client, "collector1")
    )
    assert resp.status_code == 403


def test_assign_requires_auth(client, seed_users):
    """未登录触发分配 → 401。"""
    resp = client.post("/api/tasks/assign/run")
    assert resp.status_code == 401


def test_claim_nonexistent_task_404(client, seed_users, seed_risk_config):
    """领取不存在的任务 → 404。"""
    resp = client.post("/api/tasks/999999/claim", headers=_headers(client, "collector1"))
    assert resp.status_code == 404


def test_claim_wrong_state_409(client, db_session, seed_users, seed_risk_config):
    """对未分配(PENDING_ASSIGN)任务直接领取 → 409。"""
    o = _make_order(db_session, "WRONG", date(2026, 8, 15), "HIGH")
    task = _make_task(db_session, o, risk_tier="HIGH", due_date=date(2026, 9, 7))
    db_session.commit()
    # 直接给 collector1 领取（尚未分配，assignee_id 仍为 None）
    resp = client.post(
        f"/api/tasks/{task.id}/claim", headers=_headers(client, "collector1")
    )
    assert resp.status_code == 409

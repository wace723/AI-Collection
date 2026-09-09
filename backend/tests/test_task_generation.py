"""task-001 催收任务生成测试。

对应 docs/03-测试用例.md TC-TASK-01~08/13 + 跑批编排/权限/幂等边界。
生成逻辑（generate_tasks）为纯函数式服务调用，直接注入 today 断言；
手动触发 API 走 run_batch(recalc=false)（相对真实日期构造数据保证稳定）。
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from app.models.order import Order
from app.models.task import Task
from app.services.risk_engine import seed_default_config
from app.services.risk_engine.config_service import get_current_config
from app.services.task_engine import BatchNotReadyError, generate_tasks, run_batch


# ── 辅助 ──────────────────────────────────────────────────────────


def _login_token(client, username="admin", password="admin123") -> str:
    resp = client.post(
        "/api/auth/login", json={"username": username, "password": password}
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]["access_token"]


def _auth_headers(client, username="admin") -> dict[str, str]:
    return {"Authorization": f"Bearer {_login_token(client, username)}"}


def _make_order(
    db_session,
    order_no: str,
    *,
    win_bid_date: date | None = None,
    risk_tier: str | None = None,
    pay_status: str | None = None,
) -> Order:
    """构造订单。pay_status 默认 None = 未支付。"""
    order = Order(
        supplier_no="S001",
        supplier_name="测试供应商",
        biz_no="B001",
        service_fee_order_no=order_no,
        win_bid_date=win_bid_date,
        risk_tier=risk_tier,
        pay_status=pay_status,
    )
    db_session.add(order)
    db_session.flush()
    return order


def _tasks(db_session) -> list[Task]:
    return db_session.query(Task).order_by(Task.day_offset).all()


@pytest.fixture()
def seed_risk_config(db_session):
    """插入默认风险档配置 v1（HIGH 7/15/30, MEDIUM 30, LOW 90）。"""
    seed_default_config(db_session)
    return get_current_config(db_session)


def _add_unpaid_high_order(db_session, order_no: str, win: date) -> Order:
    return _make_order(
        db_session, order_no, win_bid_date=win, risk_tier="HIGH", pay_status=None
    )


# ── TC-TASK-01：高风险多轮任务按时点生成（核心） ───────────────────


def test_high_generates_due_points_in_order(db_session, seed_risk_config):
    """HIGH win=08-15，today=09-08：只生成 7 天(FIRST) 与 15 天(SECOND) 任务。"""
    _add_unpaid_high_order(db_session, "TC01_HIGH", date(2026, 8, 15))
    db_session.commit()

    result = generate_tasks(db_session, today=date(2026, 9, 8))

    assert result.batch_id == "2026-09-08"
    assert result.scanned == 1
    assert result.generated == 2
    assert result.idempotent_skipped == 0
    assert result.by_tier == {"HIGH": 2}

    tasks = _tasks(db_session)
    assert [(t.day_offset, t.due_date, t.scene, t.risk_tier) for t in tasks] == [
        (7, date(2026, 8, 22), "FIRST", "HIGH"),
        (15, date(2026, 8, 30), "SECOND", "HIGH"),
    ]
    assert all(t.status == "PENDING_ASSIGN" for t in tasks)
    assert all(t.batch_id == "2026-09-08" for t in tasks)
    assert all(t.service_fee_order_no == "TC01_HIGH" for t in tasks)


# ── TC-TASK-02：未到催收时点不生成 ─────────────────────────────────


def test_high_not_due_not_generated(db_session, seed_risk_config):
    """HIGH win=09-01，today=09-08：仅第 7 天(=09-08) 命中。"""
    _add_unpaid_high_order(db_session, "TC02_HIGH", date(2026, 9, 1))
    db_session.commit()

    result = generate_tasks(db_session, today=date(2026, 9, 8))

    assert result.generated == 1
    tasks = _tasks(db_session)
    assert len(tasks) == 1
    assert (tasks[0].day_offset, tasks[0].due_date, tasks[0].scene) == (
        7,
        date(2026, 9, 8),
        "FIRST",
    )


# ── TC-TASK-03：已支付订单不生成任务（核心） ───────────────────────


def test_paid_order_not_generated(db_session, seed_risk_config):
    """HIGH win=08-15 已 PAID：today=09-08 时点已到也不生成。"""
    _make_order(
        db_session,
        "TC03_PAID",
        win_bid_date=date(2026, 8, 15),
        risk_tier="HIGH",
        pay_status="PAID",
    )
    db_session.commit()

    result = generate_tasks(db_session, today=date(2026, 9, 8))

    assert result.scanned == 0
    assert result.generated == 0
    assert _tasks(db_session) == []


# ── TC-TASK-04：到达催收时点但已支付则跳过 ─────────────────────────


def test_paid_after_earlier_generation_skips_new(db_session, seed_risk_config):
    """首日未支付生成任务 → 标记 PAID → 同日再跑批不再新增。"""
    order = _add_unpaid_high_order(db_session, "TC04_PAID_LATE", date(2026, 8, 15))
    db_session.commit()

    first = generate_tasks(db_session, today=date(2026, 9, 8))
    assert first.generated == 2

    order.pay_status = "PAID"
    order.pay_time = datetime(2026, 9, 8, 10, 0, tzinfo=timezone.utc)
    db_session.commit()

    second = generate_tasks(db_session, today=date(2026, 9, 8))
    assert second.scanned == 0
    assert second.generated == 0
    assert len(_tasks(db_session)) == 2  # 不新增


# ── TC-TASK-05：重复跑批幂等 ──────────────────────────────────────


def test_repeat_batch_is_idempotent(db_session, seed_risk_config):
    """同日再次跑批：命中时点因任务已存在被跳过，不新增。"""
    _add_unpaid_high_order(db_session, "TC05_REPEAT", date(2026, 8, 15))
    db_session.commit()

    first = generate_tasks(db_session, today=date(2026, 9, 8))
    assert first.generated == 2

    second = generate_tasks(db_session, today=date(2026, 9, 8))
    assert second.batch_id == first.batch_id
    assert second.scanned == 1
    assert second.generated == 0
    assert second.idempotent_skipped == 2  # 7 天/15 天两时点均已存在

    assert len(_tasks(db_session)) == 2


def test_db_unique_constraint_blocks_duplicate(db_session, seed_risk_config):
    """DB 层兜底：同一 batch 插入重复 (order_id, day_offset) 被约束拒绝。"""
    _add_unpaid_high_order(db_session, "TC05_DUP", date(2026, 8, 15))
    db_session.commit()

    from sqlalchemy.exc import IntegrityError

    db_session.add(
        Task(
            order_id=db_session.query(Order).first().id,
            service_fee_order_no="TC05_DUP",
            risk_tier="HIGH",
            scene="FIRST",
            day_offset=7,
            due_date=date(2026, 8, 22),
            status="PENDING_ASSIGN",
            batch_id="2026-09-08",
        )
    )
    db_session.add(
        Task(
            order_id=db_session.query(Order).first().id,
            service_fee_order_no="TC05_DUP",
            risk_tier="HIGH",
            scene="FIRST",
            day_offset=7,
            due_date=date(2026, 8, 22),
            status="PENDING_ASSIGN",
            batch_id="2026-09-08",
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


# ── TC-TASK-06/07/08：中/低风险时点正确 ────────────────────────────


def test_medium_single_task_on_30th_day(db_session, seed_risk_config):
    """MEDIUM win=08-08，today=09-08（第 31 天）：30 天时点已到生成 1。"""
    _make_order(
        db_session,
        "TC06_MED",
        win_bid_date=date(2026, 8, 8),
        risk_tier="MEDIUM",
        pay_status=None,
    )
    db_session.commit()

    result = generate_tasks(db_session, today=date(2026, 9, 8))

    assert result.generated == 1
    tasks = _tasks(db_session)
    assert (tasks[0].day_offset, tasks[0].due_date, tasks[0].scene) == (
        30,
        date(2026, 9, 7),
        "FIRST",
    )


def test_low_generates_on_90th_day(db_session, seed_risk_config):
    """LOW win=06-08，today=09-08（第 92 天）：90 天时点已到生成 1。"""
    _make_order(
        db_session,
        "TC07_LOW",
        win_bid_date=date(2026, 6, 8),
        risk_tier="LOW",
        pay_status=None,
    )
    db_session.commit()

    result = generate_tasks(db_session, today=date(2026, 9, 8))

    assert result.generated == 1
    task = _tasks(db_session)[0]
    assert (task.day_offset, task.due_date) == (90, date(2026, 9, 6))


def test_low_not_generated_before_90th_day(db_session, seed_risk_config):
    """LOW win=06-11，today=09-08（第 89 天）：不生成。"""
    _make_order(
        db_session,
        "TC08_LOW",
        win_bid_date=date(2026, 6, 11),
        risk_tier="LOW",
        pay_status=None,
    )
    db_session.commit()

    result = generate_tasks(db_session, today=date(2026, 9, 8))

    assert result.generated == 0
    assert _tasks(db_session) == []


# ── TC-TASK-13：跑批批次号唯一（当日日期一致，异日不同） ───────────


def test_batch_id_is_today_and_differs_across_days(db_session, seed_risk_config):
    """同日批次一致；次日新到期订单使用新批次号，旧订单不重复生成。"""
    _add_unpaid_high_order(db_session, "TC13_D1", date(2026, 8, 15))
    # 次日才到 7 天时点的订单
    _add_unpaid_high_order(db_session, "TC13_D2", date(2026, 9, 2))
    db_session.commit()

    r1 = generate_tasks(db_session, today=date(2026, 9, 8))
    assert r1.batch_id == "2026-09-08"
    assert r1.generated == 2  # TC13_D1 的 7/15 天

    r2 = generate_tasks(db_session, today=date(2026, 9, 9))
    assert r2.batch_id == "2026-09-09"
    assert r2.generated == 1  # 仅 TC13_D2 的 7 天时点(=09-09)

    by_batch: dict[str, list[str]] = {}
    for t in _tasks(db_session):
        by_batch.setdefault(t.batch_id, []).append(t.service_fee_order_no)
    assert by_batch["2026-09-08"] == ["TC13_D1", "TC13_D1"]
    assert by_batch["2026-09-09"] == ["TC13_D2"]


# ── 边界与编排 ─────────────────────────────────────────────────────


def test_no_active_config_raises(db_session, seed_users):
    """无生效风险档配置时 generate_tasks 抛 BatchNotReadyError。"""
    _add_unpaid_high_order(db_session, "NO_CFG", date(2026, 8, 15))
    db_session.commit()
    with pytest.raises(BatchNotReadyError):
        generate_tasks(db_session, today=date(2026, 9, 8))


def test_pay_status_null_treated_as_unpaid(db_session, seed_risk_config):
    """pay_status=NULL（历史缺状态）视为未支付参与催收。"""
    _make_order(
        db_session,
        "NULL_PAY",
        win_bid_date=date(2026, 8, 15),
        risk_tier="HIGH",
        pay_status=None,  # NULL
    )
    db_session.commit()
    result = generate_tasks(db_session, today=date(2026, 9, 8))
    assert result.generated == 2


def test_missing_win_date_or_tier_ignored(db_session, seed_risk_config):
    """无中标日 / 无档位的未支付订单不参与生成（不算 scanned）。"""
    _make_order(db_session, "NO_WIN_DATE", win_bid_date=None, risk_tier="HIGH")
    _make_order(db_session, "NO_TIER", win_bid_date=date(2026, 8, 15), risk_tier=None)
    db_session.commit()
    result = generate_tasks(db_session, today=date(2026, 9, 8))
    assert result.scanned == 0
    assert result.generated == 0


def test_run_batch_recalc_then_generate(db_session, seed_risk_config):
    """run_batch(recalc_risk=True)：无档订单先按 mock(50→MEDIUM) 定档再生成。"""
    _make_order(
        db_session,
        "RECALC_MED",
        win_bid_date=date(2026, 8, 8),
        risk_tier=None,  # 尚未计算风险
        pay_status=None,
    )
    db_session.commit()

    result = run_batch(db_session, today=date(2026, 9, 8), recalc_risk=True)

    order = db_session.query(Order).filter_by(service_fee_order_no="RECALC_MED").first()
    assert order.risk_tier == "MEDIUM"  # mock 无特征=50 → MEDIUM
    assert result.generated == 1
    task = _tasks(db_session)[0]
    assert (task.risk_tier, task.day_offset) == ("MEDIUM", 30)


def test_run_batch_without_recalc_uses_existing_tier(db_session, seed_risk_config):
    """run_batch(recalc_risk=False)：保留已写档位直接生成。"""
    _make_order(
        db_session,
        "NO_RECALC_HIGH",
        win_bid_date=date(2026, 8, 15),
        risk_tier="HIGH",
    )
    db_session.commit()
    result = run_batch(db_session, today=date(2026, 9, 8), recalc_risk=False)
    assert result.generated == 2


# ── API：手动触发跑批 ──────────────────────────────────────────────


def test_manual_batch_run_and_status(client, db_session, seed_users, seed_risk_config):
    """ADMIN 手动跑批（recalc=false）→ 生成；再次跑批幂等；状态聚合可查。"""
    today = date.today()
    win = today - timedelta(days=40)  # HIGH 的 7/15/30 天全部到期
    _make_order(db_session, "API_BATCH", win_bid_date=win, risk_tier="HIGH")
    db_session.commit()

    resp = client.post(
        "/api/tasks/batch/run?recalc=false", headers=_auth_headers(client)
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["batch_id"] == today.isoformat()
    assert data["generated"] == 3
    assert data["by_tier"] == {"HIGH": 3}

    # 同日再次触发 → 幂等
    resp2 = client.post(
        "/api/tasks/batch/run?recalc=false", headers=_auth_headers(client)
    )
    data2 = resp2.json()["data"]
    assert data2["generated"] == 0
    assert data2["idempotent_skipped"] == 3

    # 批次状态聚合
    st = client.get(
        f"/api/tasks/batch/status/{today.isoformat()}",
        headers=_auth_headers(client),
    )
    assert st.status_code == 200, st.text
    sdata = st.json()["data"]
    assert sdata["total"] == 3
    assert sdata["by_status"] == {"PENDING_ASSIGN": 3}
    assert sdata["by_tier"] == {"HIGH": 3}


def test_manual_batch_requires_admin(client, seed_users, seed_risk_config):
    """COLLECTOR 触发跑批 → 403。"""
    resp = client.post(
        "/api/tasks/batch/run", headers=_auth_headers(client, username="collector1")
    )
    assert resp.status_code == 403


def test_manual_batch_requires_auth(client, seed_users):
    """未登录触发跑批 → 401。"""
    resp = client.post("/api/tasks/batch/run")
    assert resp.status_code == 401


def test_manual_batch_no_config_returns_400(client, db_session, seed_users):
    """无生效配置时手动跑批 → 400。"""
    _make_order(db_session, "API_NO_CFG", win_bid_date=date(2026, 8, 15), risk_tier="HIGH")
    db_session.commit()
    resp = client.post(
        "/api/tasks/batch/run?recalc=false", headers=_auth_headers(client)
    )
    assert resp.status_code == 400


def test_batch_status_requires_auth(client, seed_users):
    """未登录查批次状态 → 401。"""
    resp = client.get("/api/tasks/batch/status/2026-09-08")
    assert resp.status_code == 401

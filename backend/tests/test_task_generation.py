"""data-003 催收状态机推进测试。

重构后（data-003）generate_tasks 语义：状态机推进，每次跑批只推进到下一个未催轮次。
- NO_NEED + 首轮时点已到 + 待支付 → PENDING_COLLECTION + 生成首轮 Task（1 个）
- COLLECTED + 下一轮时点已到（该轮无 Task）+ 待支付 → PENDING_COLLECTION + 生成下一轮 Task
- 所有轮次都已催过 + 仍待支付 → FINALIZED（轮次耗尽终态）
- 已支付跳过；未到时点保持原态；同日重跑幂等
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from app.models.order import Order
from app.models.task import Task
from app.services.risk_engine import seed_default_config
from app.services.risk_engine.config_service import get_current_config
from app.services.task_engine import BatchNotReadyError, generate_tasks, run_batch
from app.services.task_engine.states import (
    COLLECTED,
    FINALIZED,
    NO_NEED,
    PENDING_COLLECTION,
)


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
    collection_state: str = NO_NEED,
) -> Order:
    """构造订单。pay_status 默认 None = 未支付。collection_state 默认 NO_NEED。"""
    order = Order(
        supplier_no="S001",
        supplier_name="测试供应商",
        biz_no="B001",
        service_fee_order_no=order_no,
        win_bid_date=win_bid_date,
        risk_tier=risk_tier,
        pay_status=pay_status,
        collection_state=collection_state,
    )
    db_session.add(order)
    db_session.flush()
    return order


def _tasks(db_session) -> list[Task]:
    return db_session.query(Task).order_by(Task.day_offset).all()


def _order(db_session, order_no: str) -> Order:
    return (
        db_session.query(Order).filter(Order.service_fee_order_no == order_no).first()
    )


@pytest.fixture()
def seed_risk_config(db_session):
    """插入默认风险档配置 v1（HIGH 7/15/30, MEDIUM 30, LOW 90）。"""
    seed_default_config(db_session)
    return get_current_config(db_session)


def _add_unpaid_high_order(db_session, order_no: str, win: date) -> Order:
    return _make_order(
        db_session,
        order_no,
        win_bid_date=win,
        risk_tier="HIGH",
        pay_status=None,
        collection_state=NO_NEED,
    )


# ── 首轮推进 ───────────────────────────────────────────────────────


def test_no_need_advances_to_first_round(db_session, seed_risk_config):
    """NO_NEED + 首轮 7 天时点已到 + 待支付 → PENDING_COLLECTION + 生成首轮 Task。

    HIGH win=08-15，today=09-08：7 天时点已到，推进到 PENDING_COLLECTION，生成 1 个首轮任务。
    （注意：状态机推进每次只推进到下一个未催轮次，不一次生成所有到期时点）
    """
    _add_unpaid_high_order(db_session, "TC01_HIGH", date(2026, 8, 15))
    db_session.commit()

    result = generate_tasks(db_session, today=date(2026, 9, 8))

    assert result.batch_id == "2026-09-08"
    assert result.scanned == 1
    assert result.generated == 1
    assert result.idempotent_skipped == 0
    assert result.by_tier == {"HIGH": 1}

    tasks = _tasks(db_session)
    assert len(tasks) == 1
    assert (tasks[0].day_offset, tasks[0].scene, tasks[0].risk_tier) == (
        7,
        "FIRST",
        "HIGH",
    )
    assert tasks[0].status == "PENDING_ASSIGN"
    assert tasks[0].batch_id == "2026-09-08"

    order = _order(db_session, "TC01_HIGH")
    assert order.collection_state == PENDING_COLLECTION


def test_not_due_stays_no_need(db_session, seed_risk_config):
    """NO_NEED + 首轮时点未到 → 保持 NO_NEED，不生成任务。"""
    _add_unpaid_high_order(db_session, "TC02_HIGH", date(2026, 9, 1))
    db_session.commit()

    result = generate_tasks(db_session, today=date(2026, 9, 8))

    assert result.generated == 1  # win=09-01，7 天时点=09-08 已到
    # 换一个未到的场景：win=09-05，7 天时点=09-12 未到
    _add_unpaid_high_order(db_session, "TC02b_HIGH", date(2026, 9, 5))
    db_session.commit()
    result2 = generate_tasks(db_session, today=date(2026, 9, 8))
    assert result2.generated == 0
    order = _order(db_session, "TC02b_HIGH")
    assert order.collection_state == NO_NEED


# ── 已支付跳过 ────────────────────────────────────────────────────


def test_paid_order_skipped(db_session, seed_risk_config):
    """已支付订单（pay_status=PAID）不参与状态机推进，不生成任务。"""
    _make_order(
        db_session,
        "TC03_PAID",
        win_bid_date=date(2026, 8, 15),
        risk_tier="HIGH",
        pay_status="PAID",
        collection_state=NO_NEED,
    )
    db_session.commit()

    result = generate_tasks(db_session, today=date(2026, 9, 8))

    assert result.scanned == 0
    assert result.generated == 0
    assert _tasks(db_session) == []
    order = _order(db_session, "TC03_PAID")
    assert order.collection_state == NO_NEED  # 不推进


def test_paid_after_first_generation_skips(db_session, seed_risk_config):
    """首日推进生成首轮任务 → 标记 PAID → 同日再跑批不再推进。"""
    order = _add_unpaid_high_order(db_session, "TC04_PAID_LATE", date(2026, 8, 15))
    db_session.commit()

    first = generate_tasks(db_session, today=date(2026, 9, 8))
    assert first.generated == 1
    assert order.collection_state == PENDING_COLLECTION

    order.pay_status = "PAID"
    order.pay_time = datetime(2026, 9, 8, 10, 0, tzinfo=timezone.utc)
    db_session.commit()

    second = generate_tasks(db_session, today=date(2026, 9, 8))
    assert second.scanned == 0
    assert second.generated == 0
    assert len(_tasks(db_session)) == 1  # 不新增


# ── 幂等 ──────────────────────────────────────────────────────────


def test_repeat_batch_advances_next_round(db_session, seed_risk_config):
    """同日再次跑批：PENDING_COLLECTION 订单推进到下一轮到期时点（生成 SECOND）。

    data-004：PENDING_COLLECTION 在 ADVANCEABLE_STATES，跑批为其生成当轮无 Task 的下一时点任务。
    win_bid=08-15，today=09-08：7 天(08-22) 和 15 天(08-30) 都到期。
    首次跑批生成 FIRST（day_offset=7）；第二次跑批 FIRST 已有 Task → 生成 SECOND（day_offset=15）。
    """
    _add_unpaid_high_order(db_session, "TC05_REPEAT", date(2026, 8, 15))
    db_session.commit()

    first = generate_tasks(db_session, today=date(2026, 9, 8))
    assert first.generated == 1  # 首轮 FIRST

    second = generate_tasks(db_session, today=date(2026, 9, 8))
    assert second.batch_id == first.batch_id
    assert second.scanned == 1  # PENDING_COLLECTION 在 ADVANCEABLE_STATES
    assert second.generated == 1  # 推进到 SECOND
    assert len(_tasks(db_session)) == 2  # FIRST + SECOND

    # 第三次跑批：FIRST+SECOND 都有 Task，30 天(THIRD) 时点=09-14 > today=09-08 未到 → 不生成
    third = generate_tasks(db_session, today=date(2026, 9, 8))
    assert third.generated == 0
    assert len(_tasks(db_session)) == 2


def test_db_unique_constraint_blocks_duplicate(db_session, seed_risk_config):
    """DB 层兜底：同一 batch 插入重复 (order_id, day_offset) 被约束拒绝。"""
    _add_unpaid_high_order(db_session, "TC05_DUP", date(2026, 8, 15))
    db_session.commit()

    from sqlalchemy.exc import IntegrityError

    order = _order(db_session, "TC05_DUP")
    db_session.add(
        Task(
            order_id=order.id,
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
            order_id=order.id,
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


# ── 中/低风险时点 ─────────────────────────────────────────────────


def test_medium_advances_on_30th_day(db_session, seed_risk_config):
    """MEDIUM win=08-08，today=09-08（第 31 天）：30 天时点已到，推进生成 1。"""
    _make_order(
        db_session,
        "TC06_MED",
        win_bid_date=date(2026, 8, 8),
        risk_tier="MEDIUM",
        pay_status=None,
        collection_state=NO_NEED,
    )
    db_session.commit()

    result = generate_tasks(db_session, today=date(2026, 9, 8))

    assert result.generated == 1
    tasks = _tasks(db_session)
    assert (tasks[0].day_offset, tasks[0].scene) == (30, "FIRST")
    order = _order(db_session, "TC06_MED")
    assert order.collection_state == PENDING_COLLECTION


def test_low_advances_on_90th_day(db_session, seed_risk_config):
    """LOW win=06-08，today=09-08（第 92 天）：90 天时点已到，推进生成 1。"""
    _make_order(
        db_session,
        "TC07_LOW",
        win_bid_date=date(2026, 6, 8),
        risk_tier="LOW",
        pay_status=None,
        collection_state=NO_NEED,
    )
    db_session.commit()

    result = generate_tasks(db_session, today=date(2026, 9, 8))

    assert result.generated == 1
    task = _tasks(db_session)[0]
    assert (task.day_offset, task.due_date) == (90, date(2026, 9, 6))


def test_low_not_due_stays_no_need(db_session, seed_risk_config):
    """LOW win=06-11，today=09-08（第 89 天）：未到 90 天，保持 NO_NEED。"""
    _make_order(
        db_session,
        "TC08_LOW",
        win_bid_date=date(2026, 6, 11),
        risk_tier="LOW",
        pay_status=None,
        collection_state=NO_NEED,
    )
    db_session.commit()

    result = generate_tasks(db_session, today=date(2026, 9, 8))

    assert result.generated == 0
    assert _tasks(db_session) == []
    order = _order(db_session, "TC08_LOW")
    assert order.collection_state == NO_NEED


# ── 下一轮推进（COLLECTED → PENDING_COLLECTION） ──────────────────


def test_collected_advances_to_next_round(db_session, seed_risk_config):
    """COLLECTED + 下一轮时点已到（该轮无 Task）+ 待支付 → 生成下一轮 Task。

    HIGH win=08-15，首轮已催（COLLECTED + day_offset=7 已有 Task），
    today=09-08：15 天时点已到且无 Task → 推进生成 SECOND 任务。
    """
    order = _add_unpaid_high_order(db_session, "NEXT_HIGH", date(2026, 8, 15))
    order.collection_state = COLLECTED
    # 首轮已催：插入 day_offset=7 的 DONE Task
    db_session.add(
        Task(
            order_id=order.id,
            service_fee_order_no="NEXT_HIGH",
            risk_tier="HIGH",
            scene="FIRST",
            day_offset=7,
            due_date=date(2026, 8, 22),
            status="DONE",
            result="REACHED",
            batch_id="2026-08-22",
        )
    )
    db_session.commit()

    result = generate_tasks(db_session, today=date(2026, 9, 8))

    assert result.scanned == 1
    assert result.generated == 1
    tasks = _tasks(db_session)
    # 首轮 DONE + 新生成 SECOND
    assert [(t.day_offset, t.status) for t in tasks] == [(7, "DONE"), (15, "PENDING_ASSIGN")]
    assert order.collection_state == PENDING_COLLECTION


def test_collected_next_round_not_due_stays(db_session, seed_risk_config):
    """COLLECTED + 下一轮时点未到 → 保持 COLLECTED，不生成。"""
    order = _add_unpaid_high_order(db_session, "NEXT_ND", date(2026, 8, 25))
    order.collection_state = COLLECTED
    db_session.add(
        Task(
            order_id=order.id,
            service_fee_order_no="NEXT_ND",
            risk_tier="HIGH",
            scene="FIRST",
            day_offset=7,
            due_date=date(2026, 9, 1),
            status="DONE",
            result="REACHED",
            batch_id="2026-09-01",
        )
    )
    db_session.commit()

    # today=09-05：15 天时点=09-09 未到
    result = generate_tasks(db_session, today=date(2026, 9, 5))

    assert result.generated == 0
    assert order.collection_state == COLLECTED


# ── 轮次耗尽终态 ──────────────────────────────────────────────────


def test_all_rounds_collected_finalized(db_session, seed_risk_config):
    """所有轮次都已催过且仍待支付 → FINALIZED（轮次耗尽终态）。"""
    order = _add_unpaid_high_order(db_session, "DONE_HIGH", date(2026, 8, 15))
    order.collection_state = COLLECTED
    # 三轮都已完成（DONE）
    for offset, scene in [(7, "FIRST"), (15, "SECOND"), (30, "THIRD")]:
        db_session.add(
            Task(
                order_id=order.id,
                service_fee_order_no="DONE_HIGH",
                risk_tier="HIGH",
                scene=scene,
                day_offset=offset,
                due_date=date(2026, 8, 15) + timedelta(days=offset),
                status="DONE",
                result="REACHED",
                batch_id="2026-08-15",
            )
        )
    db_session.commit()

    result = generate_tasks(db_session, today=date(2026, 9, 30))

    assert result.scanned == 1
    assert result.generated == 0
    assert result.finalized == 1
    assert order.collection_state == FINALIZED


# ── 批次号 ────────────────────────────────────────────────────────


def test_batch_id_is_today_and_differs_across_days(db_session, seed_risk_config):
    """同日批次一致；次日新到期订单用新批次号。"""
    _add_unpaid_high_order(db_session, "TC13_D1", date(2026, 8, 15))
    _add_unpaid_high_order(db_session, "TC13_D2", date(2026, 9, 2))
    db_session.commit()

    r1 = generate_tasks(db_session, today=date(2026, 9, 8))
    assert r1.batch_id == "2026-09-08"
    assert r1.generated == 1  # 仅 TC13_D1 首轮（day_offset=7）

    r2 = generate_tasks(db_session, today=date(2026, 9, 9))
    assert r2.batch_id == "2026-09-09"
    # TC13_D1 首轮已有 FIRST，today=09-09 时 15 天时点=08-30 已到 → 推进 SECOND
    # TC13_D2 首轮（09-09）→ 共 2 个
    assert r2.generated == 2

    by_batch: dict[str, list[str]] = {}
    for t in _tasks(db_session):
        by_batch.setdefault(t.batch_id, []).append(t.service_fee_order_no)
    assert by_batch["2026-09-08"] == ["TC13_D1"]
    assert sorted(by_batch["2026-09-09"]) == ["TC13_D1", "TC13_D2"]


# ── 边界与编排 ─────────────────────────────────────────────────────


def test_no_active_config_raises(db_session, seed_users):
    """无生效风险档配置时 generate_tasks 抛 BatchNotReadyError。"""
    _add_unpaid_high_order(db_session, "NO_CFG", date(2026, 8, 15))
    db_session.commit()
    with pytest.raises(BatchNotReadyError):
        generate_tasks(db_session, today=date(2026, 9, 8))


def test_pay_status_null_treated_as_unpaid(db_session, seed_risk_config):
    """pay_status=NULL（历史缺状态）视为未支付参与催收推进。"""
    _make_order(
        db_session,
        "NULL_PAY",
        win_bid_date=date(2026, 8, 15),
        risk_tier="HIGH",
        pay_status=None,
        collection_state=NO_NEED,
    )
    db_session.commit()
    result = generate_tasks(db_session, today=date(2026, 9, 8))
    assert result.generated == 1


def test_missing_win_date_or_tier_ignored(db_session, seed_risk_config):
    """无中标日 / 无档位的未支付订单不参与推进（不算 scanned）。"""
    _make_order(db_session, "NO_WIN_DATE", win_bid_date=None, risk_tier="HIGH")
    _make_order(
        db_session, "NO_TIER", win_bid_date=date(2026, 8, 15), risk_tier=None
    )
    db_session.commit()
    result = generate_tasks(db_session, today=date(2026, 9, 8))
    assert result.scanned == 0
    assert result.generated == 0


def test_run_batch_uses_imported_tier(db_session, seed_risk_config):
    """run_batch(recalc=False)：用导入写入的档位推进状态机。"""
    _make_order(
        db_session,
        "IMPORT_MED",
        win_bid_date=date(2026, 8, 8),
        risk_tier="MEDIUM",
        pay_status=None,
        collection_state=NO_NEED,
    )
    db_session.commit()

    result = run_batch(db_session, today=date(2026, 9, 8), recalc_risk=False)

    order = _order(db_session, "IMPORT_MED")
    assert order.risk_tier == "MEDIUM"
    assert result.generated == 1
    task = _tasks(db_session)[0]
    assert (task.risk_tier, task.day_offset) == ("MEDIUM", 30)
    assert order.collection_state == PENDING_COLLECTION


def test_run_batch_without_recalc_advances_first(db_session, seed_risk_config):
    """run_batch(recalc_risk=False)：推进首轮。"""
    _make_order(
        db_session,
        "NO_RECALC_HIGH",
        win_bid_date=date(2026, 8, 15),
        risk_tier="HIGH",
        collection_state=NO_NEED,
    )
    db_session.commit()
    result = run_batch(db_session, today=date(2026, 9, 8), recalc_risk=False)
    assert result.generated == 1


# ── API：手动触发跑批 ──────────────────────────────────────────────


def test_manual_batch_run_and_status(client, db_session, seed_users, seed_risk_config):
    """ADMIN 手动跑批（recalc=false）→ 推进首轮生成 1；再次跑批幂等。"""
    today = date.today()
    win = today - timedelta(days=40)  # HIGH 7 天时点已到
    _make_order(
        db_session,
        "API_BATCH",
        win_bid_date=win,
        risk_tier="HIGH",
        collection_state=NO_NEED,
    )
    db_session.commit()

    resp = client.post(
        "/api/tasks/batch/run?recalc=false", headers=_auth_headers(client)
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["batch_id"] == today.isoformat()
    assert data["generated"] == 1
    assert data["by_tier"] == {"HIGH": 1}

    # 同日再次触发 → 推进到下一轮（win=today-40，15 天时点已到 → 生成 SECOND）
    resp2 = client.post(
        "/api/tasks/batch/run?recalc=false", headers=_auth_headers(client)
    )
    data2 = resp2.json()["data"]
    assert data2["generated"] == 1  # 推进 SECOND

    # 批次状态聚合（FIRST+SECOND 同 batch_id，都 PENDING_ASSIGN）
    st = client.get(
        f"/api/tasks/batch/status/{today.isoformat()}",
        headers=_auth_headers(client),
    )
    assert st.status_code == 200, st.text
    sdata = st.json()["data"]
    assert sdata["total"] == 2  # FIRST + SECOND
    assert sdata["by_status"] == {"PENDING_ASSIGN": 2}
    assert sdata["by_tier"] == {"HIGH": 2}


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
    _make_order(
        db_session,
        "API_NO_CFG",
        win_bid_date=date(2026, 8, 15),
        risk_tier="HIGH",
        collection_state=NO_NEED,
    )
    db_session.commit()
    resp = client.post(
        "/api/tasks/batch/run?recalc=false", headers=_auth_headers(client)
    )
    assert resp.status_code == 400


def test_batch_status_requires_auth(client, seed_users):
    """未登录查批次状态 → 401。"""
    resp = client.get("/api/tasks/batch/status/2026-09-08")
    assert resp.status_code == 401

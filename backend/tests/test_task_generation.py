"""task-003 单活跃任务区间模型测试（BREAKING）。

重构后（task-003）generate_tasks 语义：单活跃任务区间模型。
- 一个订单同一时间**只有一个活跃任务**（当前区间对应的）
- 区间算法：current_offset = 最大的 day_offset 使 win_bid_date + day_offset <= today
  即 age >= day_offset 取最大的那个
- 若无 current_offset（未到首轮）→ NO_NEED，无任务
- 若有 current_offset 且活跃任务 day_offset == current_offset → 同区间幂等（skipped+1）
- 若有 current_offset 且活跃任务 day_offset != current_offset（或无活跃任务）→ 删除旧活跃任务（deleted+1），生成新区间任务（generated+1）
- 已接通（DONE）跨区间也删除（每轮独立催收）
- 已支付订单跳过（不推进不生成不删除）
- BatchResult 字段：generated / deleted / skipped / by_tier

区间计算示例（HIGH [7,15,30]，win=09-01）：
  today=09-07 (age=6)  → 无 current_offset (age<7) → NO_NEED
  today=09-08 (age=7)  → current_offset=7  (win+7=09-08<=today, win+15=09-16>today)
  today=09-15 (age=14) → current_offset=7  (win+15=09-16>today)
  today=09-16 (age=15) → current_offset=15 (win+15=09-16<=today, win+30=10-01>today)
  today=09-30 (age=29) → current_offset=15 (win+30=10-01>today)
  today=10-01 (age=30) → current_offset=30 (win+30=10-01<=today)
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
    """返回所有 Task（跨区间旧任务已被物理删除）。"""
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


# ── 首轮区间生成 ───────────────────────────────────────────────────


def test_no_need_advances_to_first_round(db_session, seed_risk_config):
    """NO_NEED + 首轮 7 天时点已到 + 待支付 → PENDING_COLLECTION + 生成首轮 Task。

    HIGH win=09-01，today=09-08（age=7）→ current_offset=7，生成 1 个首轮任务。
    """
    _add_unpaid_high_order(db_session, "TC01_HIGH", date(2026, 9, 1))
    db_session.commit()

    result = generate_tasks(db_session, today=date(2026, 9, 8))

    assert result.batch_id == "2026-09-08"
    assert result.scanned == 1
    assert result.generated == 1
    assert result.deleted == 0
    assert result.skipped == 0
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


# ── 未到首轮区间 ───────────────────────────────────────────────────


def test_not_due_stays_no_need(db_session, seed_risk_config):
    """NO_NEED + 首轮时点未到 → 保持 NO_NEED，不生成任务。

    HIGH win=09-05，today=09-08（age=3 <7）→ 未到首轮区间，无任务。
    """
    _add_unpaid_high_order(db_session, "TC02_HIGH", date(2026, 9, 5))
    db_session.commit()

    result = generate_tasks(db_session, today=date(2026, 9, 8))

    assert result.scanned == 1
    assert result.generated == 0
    assert result.deleted == 0
    assert result.skipped == 0
    assert _tasks(db_session) == []
    order = _order(db_session, "TC02_HIGH")
    assert order.collection_state == NO_NEED


# ── 已支付跳过 ────────────────────────────────────────────────────


def test_paid_order_skipped(db_session, seed_risk_config):
    """已支付订单（pay_status=PAID）不参与区间判定，不生成任务。"""
    _make_order(
        db_session,
        "TC03_PAID",
        win_bid_date=date(2026, 9, 1),
        risk_tier="HIGH",
        pay_status="PAID",
        collection_state=NO_NEED,
    )
    db_session.commit()

    result = generate_tasks(db_session, today=date(2026, 9, 8))

    assert result.scanned == 0
    assert result.generated == 0
    assert result.deleted == 0
    assert _tasks(db_session) == []
    order = _order(db_session, "TC03_PAID")
    assert order.collection_state == NO_NEED  # 不推进


def test_paid_after_first_generation_skips(db_session, seed_risk_config):
    """首日生成首轮任务 → 标记 PAID → 同日再跑批不再推进。"""
    order = _add_unpaid_high_order(db_session, "TC04_PAID_LATE", date(2026, 9, 1))
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
    assert second.deleted == 0
    assert len(_tasks(db_session)) == 1  # 不新增不删除


# ── 同区间幂等 ────────────────────────────────────────────────────


def test_same_interval_idempotent(db_session, seed_risk_config):
    """同区间再跑批，不重复生成（skipped+1），不删除。

    HIGH win=09-01，today=09-08（age=7，current_offset=7）：
    首次跑批生成 day_offset=7 任务；同日再跑批同区间 → skipped+1，不新增不删除。
    """
    _add_unpaid_high_order(db_session, "TC05_IDEM", date(2026, 9, 1))
    db_session.commit()

    first = generate_tasks(db_session, today=date(2026, 9, 8))
    assert first.generated == 1
    assert first.skipped == 0
    assert first.deleted == 0
    assert len(_tasks(db_session)) == 1

    # 同日再跑批：同区间幂等
    second = generate_tasks(db_session, today=date(2026, 9, 8))
    assert second.batch_id == first.batch_id
    assert second.scanned == 1
    assert second.generated == 0
    assert second.skipped == 1
    assert second.deleted == 0
    assert len(_tasks(db_session)) == 1  # 仍只有 1 个活跃任务


def test_db_unique_constraint_blocks_duplicate(db_session, seed_risk_config):
    """DB 层兜底：同一 batch 插入重复 (batch_id, order_id, day_offset) 被约束拒绝。"""
    _add_unpaid_high_order(db_session, "TC05_DUP", date(2026, 9, 1))
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
            due_date=date(2026, 9, 8),
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
            due_date=date(2026, 9, 8),
            status="PENDING_ASSIGN",
            batch_id="2026-09-08",
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


# ── 跨区间删旧生新 ────────────────────────────────────────────────


def test_cross_interval_delete_old_generate_new(db_session, seed_risk_config):
    """跨区间：age 从 [7,15) 进入 [15,30) → 删除 7 天任务，生成 15 天任务。

    HIGH win=09-01，首轮跑批 today=09-08（age=7，current_offset=7）→ 生成 day_offset=7。
    然后改 today=09-16（age=15，current_offset=15）→ 删除 7 天任务（deleted+1），生成 15 天任务（generated+1）。
    """
    _add_unpaid_high_order(db_session, "TC06_CROSS", date(2026, 9, 1))
    db_session.commit()

    # 首轮：生成 day_offset=7
    first = generate_tasks(db_session, today=date(2026, 9, 8))
    assert first.generated == 1
    tasks_after_first = _tasks(db_session)
    assert len(tasks_after_first) == 1
    assert tasks_after_first[0].day_offset == 7

    # 跨区间：age=15（today=09-16），current_offset=15
    second = generate_tasks(db_session, today=date(2026, 9, 16))
    assert second.batch_id == "2026-09-16"
    assert second.scanned == 1
    assert second.generated == 1  # 新生成 15 天任务
    assert second.deleted == 1  # 删除旧 7 天任务
    assert second.skipped == 0

    # 单活跃任务：只有 1 个任务，且是 15 天的
    tasks_after_second = _tasks(db_session)
    assert len(tasks_after_second) == 1
    assert tasks_after_second[0].day_offset == 15
    assert tasks_after_second[0].scene == "SECOND"
    assert tasks_after_second[0].status == "PENDING_ASSIGN"
    assert tasks_after_second[0].batch_id == "2026-09-16"

    order = _order(db_session, "TC06_CROSS")
    assert order.collection_state == PENDING_COLLECTION


def test_cross_interval_with_in_progress_task(db_session, seed_risk_config):
    """跨区间：IN_PROGRESS 任务也删除，生成新区间任务。

    HIGH win=09-01，首轮 today=09-08 → 生成 day_offset=7（设为 IN_PROGRESS）。
    跨区间 today=09-16 → 删除 IN_PROGRESS 的 7 天任务，生成 15 天任务。
    """
    order = _add_unpaid_high_order(db_session, "TC07_INPROG", date(2026, 9, 1))
    db_session.commit()

    # 首轮生成
    generate_tasks(db_session, today=date(2026, 9, 8))
    task = _tasks(db_session)[0]
    task.status = "IN_PROGRESS"
    order.collection_state = PENDING_COLLECTION
    db_session.commit()

    # 跨区间
    result = generate_tasks(db_session, today=date(2026, 9, 16))
    assert result.generated == 1
    assert result.deleted == 1
    assert result.skipped == 0

    tasks = _tasks(db_session)
    assert len(tasks) == 1
    assert tasks[0].day_offset == 15
    assert tasks[0].status == "PENDING_ASSIGN"


def test_done_task_cross_interval_still_replaced(db_session, seed_risk_config):
    """已接通（DONE）跨区间仍生成：DONE 任务跨区间也删除，生成新区间任务。

    HIGH win=09-01，首轮 today=09-08 → 生成 day_offset=7（回填 DONE/REACHED）。
    跨区间 today=09-16 → 删除 DONE 的 7 天任务，生成 15 天任务（每轮独立催收）。
    """
    order = _add_unpaid_high_order(db_session, "TC08_DONE", date(2026, 9, 1))
    db_session.commit()

    # 首轮生成
    generate_tasks(db_session, today=date(2026, 9, 8))
    task = _tasks(db_session)[0]
    task.status = "DONE"
    task.result = "REACHED"
    order.collection_state = COLLECTED
    db_session.commit()

    # 跨区间：DONE 任务也删除
    result = generate_tasks(db_session, today=date(2026, 9, 16))
    assert result.generated == 1
    assert result.deleted == 1
    assert result.skipped == 0

    tasks = _tasks(db_session)
    assert len(tasks) == 1
    assert tasks[0].day_offset == 15
    assert tasks[0].status == "PENDING_ASSIGN"
    assert order.collection_state == PENDING_COLLECTION


def test_single_active_task_invariant(db_session, seed_risk_config):
    """一个订单同时只有一个活跃任务（跨区间后旧任务被删除）。

    HIGH win=09-01，逐步跨区间 7→15→30，每步都只有 1 个活跃任务。
    """
    _add_unpaid_high_order(db_session, "TC09_SINGLE", date(2026, 9, 1))
    db_session.commit()

    # 区间 [7,15)：today=09-08（age=7）
    r1 = generate_tasks(db_session, today=date(2026, 9, 8))
    assert r1.generated == 1
    tasks = _tasks(db_session)
    assert len(tasks) == 1
    assert tasks[0].day_offset == 7

    # 区间 [15,30)：today=09-16（age=15）
    r2 = generate_tasks(db_session, today=date(2026, 9, 16))
    assert r2.generated == 1
    assert r2.deleted == 1
    tasks = _tasks(db_session)
    assert len(tasks) == 1
    assert tasks[0].day_offset == 15

    # 区间 [30,∞)：today=10-01（age=30）
    r3 = generate_tasks(db_session, today=date(2026, 10, 1))
    assert r3.generated == 1
    assert r3.deleted == 1
    tasks = _tasks(db_session)
    assert len(tasks) == 1
    assert tasks[0].day_offset == 30
    assert tasks[0].scene == "THIRD"


# ── 通用多轮适配（HIGH 3 轮 [7,15,30]）────────────────────────────


def test_high_multi_round_current_offset_15(db_session, seed_risk_config):
    """HIGH 3 轮 [7,15,30]，age=20 → 当前区间 15（不是 7 也不是 30）。

    HIGH win=08-15，today=09-04（age=20）：win+7=08-22<=09-04, win+15=08-30<=09-04,
    win+30=09-14>09-04 → current_offset=15。
    """
    _add_unpaid_high_order(db_session, "TC10_MULTI", date(2026, 8, 15))
    db_session.commit()

    result = generate_tasks(db_session, today=date(2026, 9, 4))

    assert result.generated == 1
    tasks = _tasks(db_session)
    assert len(tasks) == 1
    assert tasks[0].day_offset == 15
    assert tasks[0].scene == "SECOND"


def test_high_multi_round_current_offset_30(db_session, seed_risk_config):
    """HIGH 3 轮 [7,15,30]，age=35 → 当前区间 30（THIRD）。

    HIGH win=08-15，today=09-19（age=35）：win+30=09-14<=09-19 → current_offset=30。
    """
    _add_unpaid_high_order(db_session, "TC11_MULTI30", date(2026, 8, 15))
    db_session.commit()

    result = generate_tasks(db_session, today=date(2026, 9, 19))

    assert result.generated == 1
    tasks = _tasks(db_session)
    assert len(tasks) == 1
    assert tasks[0].day_offset == 30
    assert tasks[0].scene == "THIRD"


def test_high_age_exactly_7(db_session, seed_risk_config):
    """age 恰好 7 天 → current_offset=7（边界：win_bid_date + 7 == today）。"""
    _add_unpaid_high_order(db_session, "TC12_EDGE7", date(2026, 9, 1))
    db_session.commit()

    # today=09-08，win=09-01，age=7 → current_offset=7
    result = generate_tasks(db_session, today=date(2026, 9, 8))
    assert result.generated == 1
    assert _tasks(db_session)[0].day_offset == 7


def test_high_age_exactly_15(db_session, seed_risk_config):
    """age 恰好 15 天 → current_offset=15（边界）。"""
    _add_unpaid_high_order(db_session, "TC13_EDGE15", date(2026, 8, 24))
    db_session.commit()

    # today=09-08，win=08-24，age=15 → current_offset=15
    result = generate_tasks(db_session, today=date(2026, 9, 8))
    assert result.generated == 1
    assert _tasks(db_session)[0].day_offset == 15


def test_high_age_6_not_due(db_session, seed_risk_config):
    """age=6 天（<7）→ 未到首轮区间，NO_NEED。"""
    _add_unpaid_high_order(db_session, "TC14_EDGE6", date(2026, 9, 2))
    db_session.commit()

    # today=09-08，win=09-02，age=6 <7 → 无 current_offset
    result = generate_tasks(db_session, today=date(2026, 9, 8))
    assert result.generated == 0
    assert _tasks(db_session) == []
    assert _order(db_session, "TC14_EDGE6").collection_state == NO_NEED


# ── 中/低风险时点 ─────────────────────────────────────────────────


def test_medium_advances_on_30th_day(db_session, seed_risk_config):
    """MEDIUM win=08-08，today=09-08（age=31）：30 天时点已到，生成 1。"""
    _make_order(
        db_session,
        "TC15_MED",
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
    order = _order(db_session, "TC15_MED")
    assert order.collection_state == PENDING_COLLECTION


def test_low_advances_on_90th_day(db_session, seed_risk_config):
    """LOW win=06-08，today=09-08（age=92）：90 天时点已到，生成 1。"""
    _make_order(
        db_session,
        "TC16_LOW",
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
    """LOW win=06-11，today=09-08（age=89）：未到 90 天，保持 NO_NEED。"""
    _make_order(
        db_session,
        "TC17_LOW",
        win_bid_date=date(2026, 6, 11),
        risk_tier="LOW",
        pay_status=None,
        collection_state=NO_NEED,
    )
    db_session.commit()

    result = generate_tasks(db_session, today=date(2026, 9, 8))

    assert result.generated == 0
    assert _tasks(db_session) == []
    order = _order(db_session, "TC17_LOW")
    assert order.collection_state == NO_NEED


# ── COLLECTED 状态跨区间处理 ──────────────────────────────────────


def test_collected_cross_interval_generates_new(db_session, seed_risk_config):
    """COLLECTED（首轮已接通）+ 跨区间 → 删除旧 DONE 任务，生成新区间任务。

    HIGH win=09-01，首轮 7 天 DONE（COLLECTED），today=09-16（age=15，current_offset=15）→
    删除 7 天 DONE 任务，生成 15 天任务。
    """
    order = _add_unpaid_high_order(db_session, "TC18_COLL", date(2026, 9, 1))
    order.collection_state = COLLECTED
    db_session.add(
        Task(
            order_id=order.id,
            service_fee_order_no="TC18_COLL",
            risk_tier="HIGH",
            scene="FIRST",
            day_offset=7,
            due_date=date(2026, 9, 8),
            status="DONE",
            result="REACHED",
            batch_id="2026-09-08",
        )
    )
    db_session.commit()

    result = generate_tasks(db_session, today=date(2026, 9, 16))

    assert result.scanned == 1
    assert result.generated == 1
    assert result.deleted == 1
    assert result.skipped == 0
    tasks = _tasks(db_session)
    # 只有 1 个活跃任务（旧的 7 天 DONE 已删除，新的 15 天 PENDING_ASSIGN）
    assert len(tasks) == 1
    assert (tasks[0].day_offset, tasks[0].status) == (15, "PENDING_ASSIGN")
    assert order.collection_state == PENDING_COLLECTION


def test_collected_same_interval_idempotent(db_session, seed_risk_config):
    """COLLECTED + 同区间（DONE day_offset == current_offset）→ 幂等不删除不生成。

    HIGH win=09-01，7 天 DONE（COLLECTED），today=09-08（age=7，current_offset=7）→
    活跃任务 day_offset=7 == current_offset=7 → skipped，不删除不生成。
    """
    order = _add_unpaid_high_order(db_session, "TC19_COLL_IDEM", date(2026, 9, 1))
    order.collection_state = COLLECTED
    db_session.add(
        Task(
            order_id=order.id,
            service_fee_order_no="TC19_COLL_IDEM",
            risk_tier="HIGH",
            scene="FIRST",
            day_offset=7,
            due_date=date(2026, 9, 8),
            status="DONE",
            result="REACHED",
            batch_id="2026-09-08",
        )
    )
    db_session.commit()

    result = generate_tasks(db_session, today=date(2026, 9, 8))

    assert result.generated == 0
    assert result.deleted == 0
    assert result.skipped == 1
    # 状态保持 COLLECTED（同区间幂等不改变状态）
    assert order.collection_state == COLLECTED
    tasks = _tasks(db_session)
    assert len(tasks) == 1
    assert tasks[0].day_offset == 7


# ── 跑批幂等（同日重跑同区间）────────────────────────────────────


def test_repeat_batch_same_interval_idempotent(db_session, seed_risk_config):
    """同日重跑同区间：不重复生成/删除（skipped 累加）。

    HIGH win=09-01，today=09-08：首次生成 7 天任务，第二次同区间幂等。
    """
    _add_unpaid_high_order(db_session, "TC20_REPEAT", date(2026, 9, 1))
    db_session.commit()

    first = generate_tasks(db_session, today=date(2026, 9, 8))
    assert first.generated == 1
    assert first.skipped == 0

    second = generate_tasks(db_session, today=date(2026, 9, 8))
    assert second.generated == 0
    assert second.skipped == 1
    assert second.deleted == 0
    assert len(_tasks(db_session)) == 1

    third = generate_tasks(db_session, today=date(2026, 9, 8))
    assert third.generated == 0
    assert third.skipped == 1
    assert len(_tasks(db_session)) == 1


# ── 批次号 ────────────────────────────────────────────────────────


def test_batch_id_is_today_isoformat(db_session, seed_risk_config):
    """batch_id = today.isoformat()。"""
    _add_unpaid_high_order(db_session, "TC21_BID", date(2026, 9, 1))
    db_session.commit()

    result = generate_tasks(db_session, today=date(2026, 9, 8))
    assert result.batch_id == "2026-09-08"

    tasks = _tasks(db_session)
    assert tasks[0].batch_id == "2026-09-08"


def test_batch_id_differs_across_days(db_session, seed_risk_config):
    """不同日期跑批，batch_id 不同；跨区间旧 batch 的任务被删除。"""
    _add_unpaid_high_order(db_session, "TC22_BID2", date(2026, 9, 1))
    db_session.commit()

    r1 = generate_tasks(db_session, today=date(2026, 9, 8))
    assert r1.batch_id == "2026-09-08"
    assert r1.generated == 1

    # 跨区间跑批：today=09-16 → 新 batch_id
    r2 = generate_tasks(db_session, today=date(2026, 9, 16))
    assert r2.batch_id == "2026-09-16"
    assert r2.generated == 1
    assert r2.deleted == 1

    by_batch: dict[str, list[str]] = {}
    for t in _tasks(db_session):
        by_batch.setdefault(t.batch_id, []).append(t.service_fee_order_no)
    # 旧 batch 的任务已删除，只有新 batch 的任务
    assert "2026-09-08" not in by_batch
    assert by_batch["2026-09-16"] == ["TC22_BID2"]


# ── 边界与编排 ─────────────────────────────────────────────────────


def test_no_active_config_raises(db_session, seed_users):
    """无生效风险档配置时 generate_tasks 抛 BatchNotReadyError。"""
    _add_unpaid_high_order(db_session, "NO_CFG", date(2026, 9, 1))
    db_session.commit()
    with pytest.raises(BatchNotReadyError):
        generate_tasks(db_session, today=date(2026, 9, 8))


def test_pay_status_null_treated_as_unpaid(db_session, seed_risk_config):
    """pay_status=NULL（历史缺状态）视为未支付参与催收推进。"""
    _make_order(
        db_session,
        "NULL_PAY",
        win_bid_date=date(2026, 9, 1),
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
        db_session, "NO_TIER", win_bid_date=date(2026, 9, 1), risk_tier=None
    )
    db_session.commit()
    result = generate_tasks(db_session, today=date(2026, 9, 8))
    assert result.scanned == 0
    assert result.generated == 0


def test_run_batch_uses_imported_tier(db_session, seed_risk_config):
    """run_batch(recalc=False)：用导入写入的档位推进区间。"""
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
    """run_batch(recalc_risk=False)：生成首轮区间任务。"""
    _make_order(
        db_session,
        "NO_RECALC_HIGH",
        win_bid_date=date(2026, 9, 1),
        risk_tier="HIGH",
        collection_state=NO_NEED,
    )
    db_session.commit()
    result = run_batch(db_session, today=date(2026, 9, 8), recalc_risk=False)
    assert result.generated == 1


# ── 多订单混合场景 ────────────────────────────────────────────────


def test_multiple_orders_mixed_tiers(db_session, seed_risk_config):
    """多订单混合档位：HIGH + MEDIUM + LOW，各自按各自 day_offset 划区间。"""
    _add_unpaid_high_order(db_session, "MIX_HIGH", date(2026, 9, 1))  # age=7 → offset=7
    _make_order(
        db_session,
        "MIX_MED",
        win_bid_date=date(2026, 8, 8),
        risk_tier="MEDIUM",
        collection_state=NO_NEED,
    )  # age=31 → offset=30
    _make_order(
        db_session,
        "MIX_LOW",
        win_bid_date=date(2026, 6, 8),
        risk_tier="LOW",
        collection_state=NO_NEED,
    )  # age=92 → offset=90
    db_session.commit()

    result = generate_tasks(db_session, today=date(2026, 9, 8))

    assert result.scanned == 3
    assert result.generated == 3
    assert result.by_tier == {"HIGH": 1, "MEDIUM": 1, "LOW": 1}

    tasks_by_order = {}
    for t in _tasks(db_session):
        tasks_by_order[t.service_fee_order_no] = t.day_offset
    assert tasks_by_order == {"MIX_HIGH": 7, "MIX_MED": 30, "MIX_LOW": 90}


def test_paid_and_unpaid_mixed(db_session, seed_risk_config):
    """已支付 + 未支付混合：只处理未支付。"""
    _add_unpaid_high_order(db_session, "UNPAID_1", date(2026, 9, 1))
    _make_order(
        db_session,
        "PAID_1",
        win_bid_date=date(2026, 9, 1),
        risk_tier="HIGH",
        pay_status="PAID",
        collection_state=NO_NEED,
    )
    db_session.commit()

    result = generate_tasks(db_session, today=date(2026, 9, 8))

    assert result.scanned == 1  # 只有未支付
    assert result.generated == 1
    tasks = _tasks(db_session)
    assert len(tasks) == 1
    assert tasks[0].service_fee_order_no == "UNPAID_1"


# ── API：手动触发跑批 ──────────────────────────────────────────────


def test_manual_batch_run_and_status(client, db_session, seed_users, seed_risk_config):
    """ADMIN 手动跑批（recalc=false）→ 生成首轮任务；再次跑批同区间幂等。"""
    today = date.today()
    win = today - timedelta(days=10)  # HIGH age=10，区间 [7,15) → offset=7
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
    assert data["deleted"] == 0
    assert data["skipped"] == 0
    assert data["by_tier"] == {"HIGH": 1}

    # 同日再次触发 → 同区间幂等
    resp2 = client.post(
        "/api/tasks/batch/run?recalc=false", headers=_auth_headers(client)
    )
    data2 = resp2.json()["data"]
    assert data2["generated"] == 0
    assert data2["skipped"] == 1
    assert data2["deleted"] == 0

    # 批次状态聚合
    st = client.get(
        f"/api/tasks/batch/status/{today.isoformat()}",
        headers=_auth_headers(client),
    )
    assert st.status_code == 200, st.text
    sdata = st.json()["data"]
    assert sdata["total"] == 1  # 只有 1 个活跃任务
    assert sdata["by_status"] == {"PENDING_ASSIGN": 1}
    assert sdata["by_tier"] == {"HIGH": 1}


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
        win_bid_date=date(2026, 9, 1),
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

"""催收任务生成（data-003 状态机推进重构）。

跑批（状态机推进 + 生成阶段）：扫描 collection_state 为 NO_NEED 或 COLLECTED
且 pay_status 非 PAID 的订单，按各轮催收时点（win_bid_date + day_offset）判断
是否到达下一轮 → 推进 collection_state 为 PENDING_COLLECTION 并生成当轮 Task。

状态机推进规则（data-003 design.md D1/D3）：
- NO_NEED + 首轮时点已到 + 待支付 → PENDING_COLLECTION + 生成首轮 Task
- COLLECTED + 下一轮时点已到（该轮无 Task）+ 待支付 → PENDING_COLLECTION + 生成下一轮 Task
- 所有轮次都已催过 + 仍待支付 → FINALIZED（轮次耗尽终态）
- 已支付订单跳过（不推进不生成）
- 未到任何时点 → 保持原态

幂等（CLAUDE.md 设计约束 #3）：
- 业务去重：同一 (order_id, day_offset) 已存在**非 CANCELLED** 任务则不再生成。
- DB 兜底：batch_id + order_id + day_offset 唯一约束（uq_tasks_batch_order_day）。
- batch_id 用当日日期（TC-TASK-13），同日重跑同一 batch 自然幂等。

职责分离（设计约束 #1）：不调用风险算法；订单 risk_tier 由导入写入，本模块只按档位推进。
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.order import Order
from app.models.risk import CollectionSchedule
from app.models.task import Task
from app.services.risk_engine import recalculate_risks
from app.services.risk_engine.config_service import (
    ConfigSnapshot,
    get_current_config,
)
from app.services.task_engine.states import (
    ADVANCEABLE_STATES,
    COLLECTED,
    FINALIZED,
    NO_NEED,
    PENDING_ASSIGN,
    PENDING_COLLECTION,
)


class BatchNotReadyError(ValueError):
    """跑批前置条件不满足（如尚无生效风险档配置）。"""


@dataclass(frozen=True)
class BatchResult:
    """一次跑批（状态机推进 + 生成阶段）的结果统计。"""

    batch_id: str
    today: date
    scanned: int = 0  # 参与状态机判定的待推进订单数（NO_NEED/COLLECTED 且待支付）
    generated: int = 0  # 新建任务数
    idempotent_skipped: int = 0  # 因该时点已有任务而跳过的命中数
    finalized: int = 0  # 轮次耗尽进入终态的订单数
    by_tier: dict[str, int] = field(default_factory=dict)


def _schedules_by_tier(snap: ConfigSnapshot) -> dict[str, list[CollectionSchedule]]:
    """把当前配置的催收时点按风险档分组（仅 is_active）。"""
    grouped: dict[str, list[CollectionSchedule]] = defaultdict(list)
    for s in snap.schedules:
        if s.is_active:
            grouped[s.risk_tier].append(s)
    return dict(grouped)


def _load_existing_keys(db: Session, order_ids: list[int]) -> set[tuple[int, int]]:
    """加载这些订单已存在的可执行任务键 (order_id, day_offset)。

    排除 CANCELLED：被取消的时点允许再次生成（如已支付停催后不应再生成，
    但状态机已通过 pay_status 门控跳过，此处保留语义一致）。
    """
    if not order_ids:
        return set()
    rows = (
        db.query(Task.order_id, Task.day_offset)
        .filter(
            Task.order_id.in_(order_ids),
            Task.status != "CANCELLED",
        )
        .all()
    )
    return {(r[0], r[1]) for r in rows}


def generate_tasks(
    db: Session,
    *,
    today: date,
    batch_id: str | None = None,
) -> BatchResult:
    """状态机推进 + 生成催收任务（核心逻辑，纯推进，不重算风险）。

    Args:
        db: 数据库会话
        today: 判定基准日（业务本地日期，测试可注入）
        batch_id: 批次号，默认 today.isoformat()（当日日期，TC-TASK-13）

    Raises:
        BatchNotReadyError: 尚无生效风险档配置时
    """
    snap = get_current_config(db)
    if snap is None:
        raise BatchNotReadyError("尚无生效风险档配置，请先运行 seed 初始化")

    resolved_batch = batch_id or today.isoformat()
    sched_by_tier = _schedules_by_tier(snap)

    # 待推进订单：collection_state 为 NO_NEED/COLLECTED 且待支付（pay_status NULL 或非 PAID）
    orders = (
        db.query(Order)
        .filter(
            Order.collection_state.in_(ADVANCEABLE_STATES),
            or_(Order.pay_status.is_(None), Order.pay_status != "PAID"),
        )
        .all()
    )

    candidates: list[Order] = []
    for order in orders:
        if order.win_bid_date is None:
            continue  # 无中标日，无法计算应催日
        if not order.risk_tier or order.risk_tier not in sched_by_tier:
            continue  # 无档位或当前配置无该档时点
        candidates.append(order)

    existing = _load_existing_keys(db, [o.id for o in candidates])

    scanned = 0
    generated = 0
    idempotent_skipped = 0
    finalized = 0
    by_tier: dict[str, int] = defaultdict(int)

    for order in candidates:
        scanned += 1
        # 该档所有催收时点按 day_offset 升序
        tier_schedules = sorted(
            sched_by_tier[order.risk_tier], key=lambda s: s.day_offset
        )

        # 找「下一个应催轮次」：day_offset 使 win_bid_date+day_offset <= today
        # 且该 (order_id, day_offset) 无非 CANCELLED Task
        next_sched: CollectionSchedule | None = None
        all_due_reached = True
        for sch in tier_schedules:
            due_date = order.win_bid_date + timedelta(days=sch.day_offset)
            if due_date > today:
                all_due_reached = False
                break  # 后续 day_offset 更大，都未到时点
            key = (order.id, sch.day_offset)
            if key in existing:
                continue  # 该轮已有任务（已催过），看下一轮
            next_sched = sch
            break

        if next_sched is not None:
            # 到达下一轮时点 → 推进待催收 + 生成当轮 Task
            due_date = order.win_bid_date + timedelta(days=next_sched.day_offset)
            key = (order.id, next_sched.day_offset)
            # 幂等：理论上 existing 已过滤，DB 唯一约束兜底
            if key in existing:
                idempotent_skipped += 1
                continue
            order.collection_state = PENDING_COLLECTION
            db.add(
                Task(
                    order_id=order.id,
                    service_fee_order_no=order.service_fee_order_no,
                    risk_tier=order.risk_tier,
                    scene=next_sched.scene,
                    day_offset=next_sched.day_offset,
                    due_date=due_date,
                    status=PENDING_ASSIGN,
                    batch_id=resolved_batch,
                )
            )
            existing.add(key)
            generated += 1
            by_tier[order.risk_tier] += 1
        elif all_due_reached:
            # 所有轮次都已催过且仍待支付 → 轮次耗尽终态
            order.collection_state = FINALIZED
            finalized += 1
        # 否则：未到下一轮时点，保持原态（NO_NEED/COLLECTED）

    db.commit()
    return BatchResult(
        batch_id=resolved_batch,
        today=today,
        scanned=scanned,
        generated=generated,
        idempotent_skipped=idempotent_skipped,
        finalized=finalized,
        by_tier=dict(by_tier),
    )


def run_batch(
    db: Session,
    *,
    today: date,
    batch_id: str | None = None,
    recalc_risk: bool = False,
) -> BatchResult:
    """编排一次跑批：可选风险重算 → 状态机推进 + 任务生成。

    scheduler 每日任务与手动触发共用此入口。recalc_risk=True 时先对全库
    调用 recalculate_risks（复用 risk-001 编排器，Provider 可注入降级为 mock）。
    """
    if recalc_risk:
        recalculate_risks(db)
    return generate_tasks(db, today=today, batch_id=batch_id)


__all__ = [
    "BatchNotReadyError",
    "BatchResult",
    "generate_tasks",
    "run_batch",
]

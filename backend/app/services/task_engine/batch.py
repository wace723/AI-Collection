"""催收任务生成（单活跃任务区间模型，task-003 重构）。

跑批（单活跃任务区间模型）：扫描所有待支付订单，按各档配置的 day_offset 升序
划分催收区间，为每个订单维护**唯一一个活跃任务**（当前区间对应的任务）。

区间算法（design.md D1）：
- age_days = (today - win_bid_date).days
- current_offset = 最大的 day_offset 使 win_bid_date + day_offset <= today（即 age_days >= day_offset）
- 若无（age_days < 最小 day_offset）→ 未到首轮区间，NO_NEED，无任务
- 若有 → 当前区间对应 current_offset 的任务

单活跃任务维护（design.md D2）：
- 查该订单现有活跃任务（PENDING_ASSIGN/IN_PROGRESS/DONE）
- 若活跃任务 day_offset == current_offset → 同区间，幂等不重复生成
- 若活跃任务 day_offset != current_offset（或无活跃任务但应有）→ 删除旧活跃任务，
  生成新区间任务（PENDING_ASSIGN），collection_state → PENDING_COLLECTION
- 已接通（DONE）跨区间也删除（每轮独立催收）

幂等：同区间不重复生成/删除。多次跑批同区间幂等。
已支付订单跳过（不推进不生成不删除）。
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
    FINALIZED,
    NO_NEED,
    PENDING_ASSIGN,
    PENDING_COLLECTION,
)

# 活跃任务状态（非 CANCELLED）：跑批维护单活跃任务时查这些状态
_ACTIVE_STATUSES = ("PENDING_ASSIGN", "IN_PROGRESS", "DONE")


class BatchNotReadyError(ValueError):
    """跑批前置条件不满足（如尚无生效风险档配置）。"""


@dataclass(frozen=True)
class BatchResult:
    """一次跑批（单活跃任务区间模型）的结果统计。"""

    batch_id: str
    today: date
    scanned: int = 0  # 参与区间判定的待支付订单数
    generated: int = 0  # 新建任务数
    deleted: int = 0  # 跨区间删除的旧活跃任务数
    skipped: int = 0  # 同区间幂等跳过数
    by_tier: dict[str, int] = field(default_factory=dict)


def _schedules_by_tier(snap: ConfigSnapshot) -> dict[str, list[CollectionSchedule]]:
    """把当前配置的催收时点按风险档分组（仅 is_active），各档按 day_offset 升序。"""
    grouped: dict[str, list[CollectionSchedule]] = defaultdict(list)
    for s in snap.schedules:
        if s.is_active:
            grouped[s.risk_tier].append(s)
    for tier in grouped:
        grouped[tier].sort(key=lambda s: s.day_offset)
    return dict(grouped)


def _current_offset(day_offsets: list[int], win_bid_date: date, today: date) -> int | None:
    """算当前区间对应的 day_offset。

    返回最大的 day_offset 使 win_bid_date + day_offset <= today（age_days >= day_offset）。
    无则 None（未到首轮区间）。
    """
    current: int | None = None
    for off in day_offsets:  # 已升序
        if win_bid_date + timedelta(days=off) <= today:
            current = off
        else:
            break  # 后续更大，都未到
    return current


def _load_active_tasks(
    db: Session, order_ids: list[int]
) -> dict[int, list[Task]]:
    """加载这些订单的活跃任务（PENDING_ASSIGN/IN_PROGRESS/DONE），按 order_id 分组。"""
    if not order_ids:
        return {}
    rows = (
        db.query(Task)
        .filter(
            Task.order_id.in_(order_ids),
            Task.status.in_(_ACTIVE_STATUSES),
        )
        .all()
    )
    result: dict[int, list[Task]] = defaultdict(list)
    for t in rows:
        result[t.order_id].append(t)
    return dict(result)


def generate_tasks(
    db: Session,
    *,
    today: date,
    batch_id: str | None = None,
) -> BatchResult:
    """单活跃任务区间模型跑批（核心逻辑，纯推进，不重算风险）。

    Args:
        db: 数据库会话
        today: 判定基准日（业务本地日期，测试可注入）
        batch_id: 批次号，默认 today.isoformat()

    Raises:
        BatchNotReadyError: 尚无生效风险档配置时
    """
    snap = get_current_config(db)
    if snap is None:
        raise BatchNotReadyError("尚无生效风险档配置，请先运行 seed 初始化")

    resolved_batch = batch_id or today.isoformat()
    sched_by_tier = _schedules_by_tier(snap)

    # 扫描所有待支付订单（pay_status NULL 或非 PAID）；不限 collection_state，
    # 因跨区间需处理所有订单（COLLECTED 跨区间也要删旧生新）
    orders = (
        db.query(Order)
        .filter(or_(Order.pay_status.is_(None), Order.pay_status != "PAID"))
        .all()
    )

    candidates: list[Order] = []
    for order in orders:
        if order.win_bid_date is None:
            continue  # 无中标日，无法算区间
        if not order.risk_tier or order.risk_tier not in sched_by_tier:
            continue  # 无档位或当前配置无该档时点
        candidates.append(order)

    active_tasks = _load_active_tasks(db, [o.id for o in candidates])

    scanned = 0
    generated = 0
    deleted = 0
    skipped = 0
    by_tier: dict[str, int] = defaultdict(int)

    for order in candidates:
        scanned += 1
        day_offsets = [s.day_offset for s in sched_by_tier[order.risk_tier]]
        current_off = _current_offset(day_offsets, order.win_bid_date, today)

        if current_off is None:
            # 未到首轮区间
            order.collection_state = NO_NEED
            continue

        # 查该订单现有活跃任务
        order_active = active_tasks.get(order.id, [])

        # 判断是否已有当前区间的任务
        has_current = any(t.day_offset == current_off for t in order_active)

        if has_current:
            # 同区间幂等：不重复生成，不删除。collection_state 保持
            # （若回填过 REACHED 已是 COLLECTED，保持；否则 PENDING_COLLECTION）
            if order.collection_state == NO_NEED:
                order.collection_state = PENDING_COLLECTION
            skipped += 1
            continue

        # 跨区间或无活跃任务：删除旧活跃任务，生成新区间任务
        for t in order_active:
            db.delete(t)
            deleted += 1

        # 找当前区间对应的 schedule（取 scene）
        sched = next(
            s for s in sched_by_tier[order.risk_tier] if s.day_offset == current_off
        )
        due_date = order.win_bid_date + timedelta(days=current_off)
        db.add(
            Task(
                order_id=order.id,
                service_fee_order_no=order.service_fee_order_no,
                risk_tier=order.risk_tier,
                scene=sched.scene,
                day_offset=current_off,
                due_date=due_date,
                status=PENDING_ASSIGN,
                batch_id=resolved_batch,
            )
        )
        order.collection_state = PENDING_COLLECTION
        generated += 1
        by_tier[order.risk_tier] += 1

    db.commit()
    return BatchResult(
        batch_id=resolved_batch,
        today=today,
        scanned=scanned,
        generated=generated,
        deleted=deleted,
        skipped=skipped,
        by_tier=dict(by_tier),
    )


def run_batch(
    db: Session,
    *,
    today: date,
    batch_id: str | None = None,
    recalc_risk: bool = False,
) -> BatchResult:
    """编排一次跑批：可选风险重算 → 单活跃任务区间推进。

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

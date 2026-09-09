"""催收任务生成（task-001 跑批核心）。

跑批（生成阶段）：扫描未支付订单（pay_status 非 PAID，含 NULL），
命中「win_bid_date + 催收时点 <= today」且当前仍未支付 → 生成催收任务。

幂等（CLAUDE.md/CODEBUDDY.md 设计约束 #3）：
- 业务去重：同一 (order_id, day_offset) 已存在**非 CANCELLED** 任务则不再生成。
  该键跨批次成立，跨日重跑也不会重复生成同一时点任务。
- DB 兜底：batch_id + order_id + day_offset 唯一约束
  （模型 uq_tasks_batch_order_day，迁移增量加）。
- batch_id 用当日日期（TC-TASK-13），同日重跑同一 batch 自然幂等。

职责分离（设计约束 #1）：不调用风险算法；订单 risk_tier 由 risk-001 的
recalculate_risks 写入，本模块只按当前档位确定性生成。
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


class BatchNotReadyError(ValueError):
    """跑批前置条件不满足（如尚无生效风险档配置）。"""


@dataclass(frozen=True)
class BatchResult:
    """一次跑批（生成阶段）的结果统计。"""

    batch_id: str
    today: date
    scanned: int = 0  # 参与时点判定的未支付订单数（有中标日且有对应档位）
    generated: int = 0  # 新建任务数
    idempotent_skipped: int = 0  # 因该时点已有任务而跳过的命中数
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

    排除 CANCELLED：被取消的时点允许再次生成（如误生成后作废重发）。
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
    """生成催收任务（核心逻辑，纯生成，不重算风险）。

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

    # 未支付 = pay_status IS NULL（历史缺状态）或非 PAID。
    # SQL 的 `!= 'PAID'` 会排除 NULL，故用 or_ 显式含 NULL。
    orders = (
        db.query(Order)
        .filter(or_(Order.pay_status.is_(None), Order.pay_status != "PAID"))
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
    by_tier: dict[str, int] = defaultdict(int)

    for order in candidates:
        scanned += 1
        for sch in sched_by_tier[order.risk_tier]:
            due_date = order.win_bid_date + timedelta(days=sch.day_offset)
            if due_date > today:
                continue  # 未到催收时点（TC-TASK-02/08）
            key = (order.id, sch.day_offset)
            if key in existing:
                idempotent_skipped += 1
                continue  # 幂等：该时点任务已存在（TC-TASK-05）
            db.add(
                Task(
                    order_id=order.id,
                    service_fee_order_no=order.service_fee_order_no,
                    risk_tier=order.risk_tier,
                    scene=sch.scene,
                    day_offset=sch.day_offset,
                    due_date=due_date,
                    status="PENDING_ASSIGN",
                    batch_id=resolved_batch,
                )
            )
            existing.add(key)
            generated += 1
            by_tier[order.risk_tier] += 1

    db.commit()
    return BatchResult(
        batch_id=resolved_batch,
        today=today,
        scanned=scanned,
        generated=generated,
        idempotent_skipped=idempotent_skipped,
        by_tier=dict(by_tier),
    )


def run_batch(
    db: Session,
    *,
    today: date,
    batch_id: str | None = None,
    recalc_risk: bool = False,
) -> BatchResult:
    """编排一次跑批：可选风险重算 → 任务生成。

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

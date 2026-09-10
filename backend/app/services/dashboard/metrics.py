"""dash-001 数据大盘指标聚合。

职责（单一：只读聚合查询，不写库、不 commit）：
1. 日大盘（F-DASH-01）：当日新增任务数、各档分布、当日回款数、回款率
2. 风险档分布（F-DASH-04）：当前未支付订单按 risk_tier 计数
3. 账龄分布（F-DASH-05）：未支付订单按账龄段计数
4. 周大盘（F-DASH-02）：本周每日完成率/回款率趋势 + 催收员绩效排名
5. 月大盘（F-DASH-03）：月度欠费率、回款率、各档催收效果对比

关键语义（与 state.py 一致，确保 TC-DASH 可精确断言）：
- 未支付订单 = pay_status IS NULL OR pay_status != 'PAID'（与 batch.py 一致，含 NULL）
- 回款 = 催收员回填 TaskResult.result='PAID'（submit_result 不更新 Order.pay_status，
  故回款数来自 TaskResult 而非 Order.pay_status）
- 回款时间戳用 TaskResult.created_at（回填时刻），非 Task.created_at（创建时刻）
- 回款率分母 = 当日已处理任务数（TaskResult 终态结果 distinct task_id），分母 0 → 0.0
- 账龄段复用 talk_engine.matcher.map_age_bucket，Python 端遍历计算（规避 SQL case else_ 坑）
- 风险档 NULL 归入 'NONE'，账龄 win_bid_date NULL 归入 'UNKNOWN'，确保合计可断言
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.models.order import Order
from app.models.task import Task, TaskResult
from app.models.user import User
from app.services.talk_engine.matcher import AGE_BUCKETS, map_age_bucket

# 终态结果（PROMISE 是改期非终态，不计入「已处理」）
_TERMINAL_RESULTS = ("PAID", "DISPUTE", "LOST_CONTACT", "OTHER")
_PAID = "PAID"

# 风险档固定顺序（输出稳定）
_TIER_KEYS = ("HIGH", "MEDIUM", "LOW", "NONE")


@dataclass(frozen=True)
class DailyMetrics:
    """日大盘指标。"""

    date: date
    new_tasks: int
    new_tasks_by_tier: dict[str, int]   # {"HIGH","MEDIUM","LOW","NONE"}
    paid_count: int
    processed_count: int
    paid_rate: float
    unpaid_total: int
    risk_distribution: dict[str, int]
    age_distribution: dict[str, int]


@dataclass(frozen=True)
class DailyTrendPoint:
    """周/月趋势的单日点。"""

    date: date
    new_tasks: int
    completed: int
    completion_rate: float
    paid: int
    processed: int
    paid_rate: float


@dataclass(frozen=True)
class CollectorPerformance:
    """催收员绩效。"""

    collector_id: int
    username: str
    display_name: str
    paid_count: int


@dataclass(frozen=True)
class WeeklyMetrics:
    """周大盘。"""

    week_start: date
    week_end: date
    trend: list[DailyTrendPoint]
    collector_ranking: list[CollectorPerformance]


@dataclass(frozen=True)
class TierEffect:
    """单风险档的催收效果。"""

    risk_tier: str
    processed: int
    paid: int
    paid_rate: float


@dataclass(frozen=True)
class MonthlyMetrics:
    """月大盘。"""

    month_start: date
    month_end: date
    unpaid_rate: float
    paid_count: int
    processed_count: int
    paid_rate: float
    tier_effects: list[TierEffect]


def _rate(numerator: int, denominator: int) -> float:
    """安全比率：分母 0 返回 0.0，否则保留四位。"""
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 4)


def _new_tasks_by_tier(db: Session, today: date) -> dict[str, int]:
    """当日新增任务按风险档分组，NULL/未知档 → 'NONE'（与 _risk_distribution 一致）。"""
    rows = (
        db.query(Task.risk_tier, func.count(Task.id))
        .filter(func.date(Task.created_at) == today.isoformat())
        .group_by(Task.risk_tier)
        .all()
    )
    by_tier = {k: 0 for k in _TIER_KEYS}
    for tier, cnt in rows:
        key = tier if tier in ("HIGH", "MEDIUM", "LOW") else "NONE"
        by_tier[key] = cnt
    return by_tier


def _paid_count(db: Session, day: date) -> int:
    """指定日回款数（TaskResult PAID，distinct task 防同任务多次跟进重复计）。"""
    return (
        db.query(func.count(TaskResult.task_id.distinct()))
        .filter(
            TaskResult.result == _PAID,
            func.date(TaskResult.created_at) == day.isoformat(),
        )
        .scalar()
        or 0
    )


def _processed_count(db: Session, day: date) -> int:
    """指定日已处理任务数（终态结果 distinct task_id，防同任务多次跟进重复计）。"""
    return (
        db.query(func.count(TaskResult.task_id.distinct()))
        .filter(
            TaskResult.result.in_(_TERMINAL_RESULTS),
            func.date(TaskResult.created_at) == day.isoformat(),
        )
        .scalar()
        or 0
    )


def _completed_count(db: Session, day: date) -> int:
    """指定日完成数（终态结果 distinct task，等同 _processed_count 语义）。"""
    return _processed_count(db, day)


def _new_tasks_count(db: Session, day: date) -> int:
    """指定日新增任务数。"""
    return (
        db.query(func.count(Task.id))
        .filter(func.date(Task.created_at) == day.isoformat())
        .scalar()
        or 0
    )


def _unpaid_orders(db: Session) -> list[Order]:
    """当前未支付订单（pay_status NULL 或非 PAID）。"""
    return (
        db.query(Order)
        .filter(or_(Order.pay_status.is_(None), Order.pay_status != "PAID"))
        .all()
    )


def _risk_distribution(orders: list[Order]) -> dict[str, int]:
    """未支付订单按风险档分布，NULL/未知档 → 'NONE'。"""
    dist = {k: 0 for k in _TIER_KEYS}
    for o in orders:
        key = o.risk_tier if o.risk_tier in ("HIGH", "MEDIUM", "LOW") else "NONE"
        dist[key] += 1
    return dist


def _age_distribution(orders: list[Order], *, today: date) -> dict[str, int]:
    """未支付订单按账龄段分布，win_bid_date NULL → 'UNKNOWN'。"""
    buckets: dict[str, int] = {b: 0 for b in AGE_BUCKETS}
    buckets["UNKNOWN"] = 0
    for o in orders:
        if o.win_bid_date is None:
            buckets["UNKNOWN"] += 1
        else:
            age = (today - o.win_bid_date).days
            buckets[map_age_bucket(age)] += 1
    return buckets


def get_daily_metrics(db: Session, *, today: date) -> DailyMetrics:
    """日大盘（F-DASH-01/04/05，TC-DASH-01/02）。"""
    new_tasks = _new_tasks_count(db, today)
    new_tasks_by_tier = _new_tasks_by_tier(db, today)
    paid = _paid_count(db, today)
    processed = _processed_count(db, today)

    orders = _unpaid_orders(db)
    risk_dist = _risk_distribution(orders)
    age_dist = _age_distribution(orders, today=today)

    return DailyMetrics(
        date=today,
        new_tasks=new_tasks,
        new_tasks_by_tier=new_tasks_by_tier,
        paid_count=paid,
        processed_count=processed,
        paid_rate=_rate(paid, processed),
        unpaid_total=len(orders),
        risk_distribution=risk_dist,
        age_distribution=age_dist,
    )


def _trend_point(db: Session, day: date) -> DailyTrendPoint:
    """单日趋势点。"""
    new_tasks = _new_tasks_count(db, day)
    completed = _completed_count(db, day)
    paid = _paid_count(db, day)
    processed = _processed_count(db, day)
    return DailyTrendPoint(
        date=day,
        new_tasks=new_tasks,
        completed=completed,
        completion_rate=_rate(completed, new_tasks),
        paid=paid,
        processed=processed,
        paid_rate=_rate(paid, processed),
    )


def get_weekly_metrics(db: Session, *, today: date) -> WeeklyMetrics:
    """周大盘（F-DASH-02，TC-DASH-03）。

    周范围 = today-6 ~ today（含两端，共 7 天）。
    """
    week_start = today - timedelta(days=6)
    trend = [_trend_point(db, week_start + timedelta(days=i)) for i in range(7)]

    # 催收员绩效：本周 PAID 按 collector_id 分组
    rows = (
        db.query(
            TaskResult.collector_id,
            func.count(TaskResult.id),
        )
        .filter(
            TaskResult.result == _PAID,
            func.date(TaskResult.created_at).between(
                week_start.isoformat(), today.isoformat()
            ),
        )
        .group_by(TaskResult.collector_id)
        .all()
    )
    collector_ids = [cid for cid, _ in rows if cid is not None]
    users = (
        db.query(User)
        .filter(User.id.in_(collector_ids))
        .all()
        if collector_ids
        else []
    )
    user_map = {u.id: u for u in users}

    ranking = [
        CollectorPerformance(
            collector_id=cid,
            username=user_map[cid].username,
            display_name=user_map[cid].display_name,
            paid_count=cnt,
        )
        for cid, cnt in rows
        if cid is not None
    ]
    # 回款数降序，tie 取 collector_id 升序（稳定）
    ranking.sort(key=lambda x: (-x.paid_count, x.collector_id))

    return WeeklyMetrics(
        week_start=week_start,
        week_end=today,
        trend=trend,
        collector_ranking=ranking,
    )


def get_monthly_metrics(db: Session, *, today: date) -> MonthlyMetrics:
    """月大盘（F-DASH-03）。月范围 = 当月 1 日 ~ today。"""
    month_start = today.replace(day=1)

    total_orders = db.query(func.count(Order.id)).scalar() or 0
    unpaid_orders = _unpaid_orders(db)
    unpaid_rate = _rate(len(unpaid_orders), total_orders)

    paid = (
        db.query(func.count(TaskResult.id))
        .filter(
            TaskResult.result == _PAID,
            func.date(TaskResult.created_at).between(
                month_start.isoformat(), today.isoformat()
            ),
        )
        .scalar()
        or 0
    )
    processed = (
        db.query(func.count(TaskResult.task_id.distinct()))
        .filter(
            TaskResult.result.in_(_TERMINAL_RESULTS),
            func.date(TaskResult.created_at).between(
                month_start.isoformat(), today.isoformat()
            ),
        )
        .scalar()
        or 0
    )

    # 各档催收效果：按 Task.risk_tier 分组本月已处理/回款
    tier_rows = (
        db.query(
            Task.risk_tier,
            func.count(TaskResult.task_id.distinct()),
        )
        .join(TaskResult, TaskResult.task_id == Task.id)
        .filter(
            TaskResult.result.in_(_TERMINAL_RESULTS),
            func.date(TaskResult.created_at).between(
                month_start.isoformat(), today.isoformat()
            ),
        )
        .group_by(Task.risk_tier)
        .all()
    )
    paid_rows = (
        db.query(
            Task.risk_tier,
            func.count(TaskResult.task_id.distinct()),
        )
        .join(TaskResult, TaskResult.task_id == Task.id)
        .filter(
            TaskResult.result == _PAID,
            func.date(TaskResult.created_at).between(
                month_start.isoformat(), today.isoformat()
            ),
        )
        .group_by(Task.risk_tier)
        .all()
    )
    processed_map = {tier: cnt for tier, cnt in tier_rows}
    paid_map = {tier: cnt for tier, cnt in paid_rows}
    # 固定输出所有档位（含 NONE），无数据档位补 0，与日大盘稳定输出契约一致
    tier_effects = [
        TierEffect(
            risk_tier=tier,
            processed=processed_map.get(tier, 0),
            paid=paid_map.get(tier, 0),
            paid_rate=_rate(paid_map.get(tier, 0), processed_map.get(tier, 0)),
        )
        for tier in _TIER_KEYS
    ]

    return MonthlyMetrics(
        month_start=month_start,
        month_end=today,
        unpaid_rate=unpaid_rate,
        paid_count=paid,
        processed_count=processed,
        paid_rate=_rate(paid, processed),
        tier_effects=tier_effects,
    )


__all__ = [
    "DailyMetrics",
    "DailyTrendPoint",
    "CollectorPerformance",
    "WeeklyMetrics",
    "TierEffect",
    "MonthlyMetrics",
    "get_daily_metrics",
    "get_weekly_metrics",
    "get_monthly_metrics",
]

"""dash-001 数据大盘输出模型。

字段与 services.dashboard.metrics 的 frozen dataclass 一一对应。
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel


class DailyDashboardOut(BaseModel):
    """日大盘（F-DASH-01/04/05）。"""

    date: date
    new_tasks: int
    new_tasks_by_tier: dict[str, int]
    paid_count: int
    processed_count: int
    paid_rate: float
    unpaid_total: int
    risk_distribution: dict[str, int]
    age_distribution: dict[str, int]


class DailyTrendPointOut(BaseModel):
    """周/月趋势单日点。"""

    date: date
    new_tasks: int
    completed: int
    completion_rate: float
    paid: int
    processed: int
    paid_rate: float


class CollectorPerformanceOut(BaseModel):
    """催收员绩效。"""

    collector_id: int
    username: str
    display_name: str
    paid_count: int


class WeeklyDashboardOut(BaseModel):
    """周大盘（F-DASH-02）。"""

    week_start: date
    week_end: date
    trend: list[DailyTrendPointOut]
    collector_ranking: list[CollectorPerformanceOut]


class TierEffectOut(BaseModel):
    """单风险档催收效果。"""

    risk_tier: str
    processed: int
    paid: int
    paid_rate: float


class MonthlyDashboardOut(BaseModel):
    """月大盘（F-DASH-03）。"""

    month_start: date
    month_end: date
    unpaid_rate: float
    paid_count: int
    processed_count: int
    paid_rate: float
    tier_effects: list[TierEffectOut]


__all__ = [
    "DailyDashboardOut",
    "DailyTrendPointOut",
    "CollectorPerformanceOut",
    "WeeklyDashboardOut",
    "TierEffectOut",
    "MonthlyDashboardOut",
]

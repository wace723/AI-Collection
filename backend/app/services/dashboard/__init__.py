"""dash-001 数据大盘服务。

稳定对外入口：get_daily_metrics / get_weekly_metrics / get_monthly_metrics。
"""

from app.services.dashboard.metrics import (
    CollectorPerformance,
    DailyMetrics,
    DailyTrendPoint,
    MonthlyMetrics,
    TierEffect,
    WeeklyMetrics,
    get_daily_metrics,
    get_monthly_metrics,
    get_weekly_metrics,
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

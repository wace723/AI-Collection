"""dash-001 数据大盘路由。

GET /api/dashboard/daily   —— 日大盘（新增任务/各档/回款/回款率/风险分布/账龄分布）
GET /api/dashboard/weekly  —— 周大盘（7 日趋势 + 催收员绩效排名）
GET /api/dashboard/monthly —— 月大盘（月度欠费率/回款率/各档催收效果）

仅 SUPERVISOR/ADMIN 可见（大盘为管理层视角）。
"""

from __future__ import annotations

import dataclasses
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_db, require_role
from app.models.user import User
from app.schemas.common import APIResponse
from app.schemas.dashboard import (
    CollectorPerformanceOut,
    DailyDashboardOut,
    DailyTrendPointOut,
    MonthlyDashboardOut,
    TierEffectOut,
    WeeklyDashboardOut,
)
from app.services.dashboard import (
    get_daily_metrics,
    get_monthly_metrics,
    get_weekly_metrics,
)

router = APIRouter()


def _today_utc() -> datetime:
    """对齐 TaskResult.created_at 的 UTC 语义（CreatedAtMixin 用 utcnow）。"""
    return datetime.now(timezone.utc)


@router.get("/daily", response_model=APIResponse[DailyDashboardOut])
def daily_dashboard(
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_role("SUPERVISOR", "ADMIN")),
) -> APIResponse[DailyDashboardOut]:
    """日大盘。"""
    m = get_daily_metrics(db, today=_today_utc().date())
    return APIResponse(data=DailyDashboardOut(**dataclasses.asdict(m)))


@router.get("/weekly", response_model=APIResponse[WeeklyDashboardOut])
def weekly_dashboard(
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_role("SUPERVISOR", "ADMIN")),
) -> APIResponse[WeeklyDashboardOut]:
    """周大盘（7 日趋势 + 催收员绩效排名）。"""
    m = get_weekly_metrics(db, today=_today_utc().date())
    return APIResponse(
        data=WeeklyDashboardOut(
            week_start=m.week_start,
            week_end=m.week_end,
            trend=[
                DailyTrendPointOut(**dataclasses.asdict(p)) for p in m.trend
            ],
            collector_ranking=[
                CollectorPerformanceOut(**dataclasses.asdict(c))
                for c in m.collector_ranking
            ],
        )
    )


@router.get("/monthly", response_model=APIResponse[MonthlyDashboardOut])
def monthly_dashboard(
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_role("SUPERVISOR", "ADMIN")),
) -> APIResponse[MonthlyDashboardOut]:
    """月大盘（月度欠费率/回款率/各档催收效果对比）。"""
    m = get_monthly_metrics(db, today=_today_utc().date())
    return APIResponse(
        data=MonthlyDashboardOut(
            month_start=m.month_start,
            month_end=m.month_end,
            unpaid_rate=m.unpaid_rate,
            paid_count=m.paid_count,
            processed_count=m.processed_count,
            paid_rate=m.paid_rate,
            tier_effects=[
                TierEffectOut(**dataclasses.asdict(t)) for t in m.tier_effects
            ],
        )
    )

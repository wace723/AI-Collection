"""主管视图路由（supervisor 增强需求）。

GET /api/supervisor/staff-performance —— 员工绩效统计（SUPERVISOR/ADMIN）
"""

from __future__ import annotations

import dataclasses

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_db, require_role
from app.models.user import User
from app.schemas.common import APIResponse
from app.schemas.supervisor import StaffPerformanceOut
from app.services.supervisor_service import get_staff_performance

router = APIRouter()


@router.get("/staff-performance", response_model=APIResponse[list[StaffPerformanceOut]])
def staff_performance(
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_role("SUPERVISOR", "ADMIN")),
) -> APIResponse[list[StaffPerformanceOut]]:
    """各催收员任务完成情况（待处理/进行中/已完成/回款数/回款率）。"""
    rows = get_staff_performance(db)
    return APIResponse(
        data=[StaffPerformanceOut(**dataclasses.asdict(r)) for r in rows]
    )

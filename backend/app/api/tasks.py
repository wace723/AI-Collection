"""task-001 催收任务生成路由。

POST /api/tasks/batch/run              —— 手动触发跑批（ADMIN）
GET  /api/tasks/batch/status/{batch_id} —— 批次任务聚合状态（登录可见）
"""

from __future__ import annotations

from collections import Counter
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db, require_role
from app.models.task import Task
from app.models.user import User
from app.schemas.common import APIResponse
from app.schemas.task import BatchRunOut, BatchStatusOut
from app.services.task_engine import BatchNotReadyError, run_batch

router = APIRouter()


@router.post("/batch/run", response_model=APIResponse[BatchRunOut])
def run_manual_batch(
    recalc: bool = Query(
        default=True, description="是否先批量重算风险档再生成（模拟完整跑批）"
    ),
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_role("ADMIN")),
) -> APIResponse[BatchRunOut]:
    """手动触发跑批（仅 ADMIN）。

    与每日定时 job 同一入口（run_batch），默认 recalc=true。
    """
    try:
        result = run_batch(db, today=date.today(), recalc_risk=recalc)
    except BatchNotReadyError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    return APIResponse(
        data=BatchRunOut(
            batch_id=result.batch_id,
            today=result.today,
            scanned=result.scanned,
            generated=result.generated,
            idempotent_skipped=result.idempotent_skipped,
            by_tier=result.by_tier,
        )
    )


@router.get(
    "/batch/status/{batch_id}", response_model=APIResponse[BatchStatusOut]
)
def batch_status(
    batch_id: str,
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
) -> APIResponse[BatchStatusOut]:
    """按批次号查询任务聚合状态（登录可见）。"""
    rows = db.query(Task).filter(Task.batch_id == batch_id).all()
    return APIResponse(
        data=BatchStatusOut(
            batch_id=batch_id,
            total=len(rows),
            by_status=dict(Counter(r.status for r in rows)),
            by_tier=dict(Counter(r.risk_tier for r in rows)),
        )
    )

"""task-001/002 催收任务路由。

跑批与批次状态（task-001）：
    POST /api/tasks/batch/run              —— 手动触发跑批（ADMIN）
    GET  /api/tasks/batch/status/{batch_id} —— 批次任务聚合状态（登录可见）

分配与状态机（task-002）：
    POST /api/tasks/assign/run             —— 手动触发分配（ADMIN）
    POST /api/tasks/{id}/claim             —— 领取任务（COLLECTOR/SUPERVISOR/ADMIN）
    POST /api/tasks/{id}/result            —— 回填处理结果（同上）
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
from app.schemas.task import (
    AssignmentRunOut,
    BatchRunOut,
    BatchStatusOut,
    TaskOut,
    TaskResultIn,
)
from app.services.task_engine import (
    AssignmentError,
    BatchNotReadyError,
    TaskNotFoundError,
    TaskStateError,
    assign_pending_tasks,
    claim_task,
    run_batch,
    submit_result,
)

router = APIRouter()


# ── 跑批与批次状态（task-001） ──────────────────────────────────────


@router.post("/batch/run", response_model=APIResponse[BatchRunOut])
def run_manual_batch(
    recalc: bool = Query(
        default=True, description="是否先批量重算风险档再生成（模拟完整跑批）"
    ),
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_role("ADMIN")),
) -> APIResponse[BatchRunOut]:
    """手动触发跑批（仅 ADMIN）。与每日定时 job 同一入口（run_batch），默认 recalc=true。"""
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


# ── 分配与状态机（task-002） ────────────────────────────────────────


@router.post("/assign/run", response_model=APIResponse[AssignmentRunOut])
def run_manual_assign(
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_role("ADMIN")),
) -> APIResponse[AssignmentRunOut]:
    """手动触发任务分配（仅 ADMIN）：高风险优先 + 负载均衡。"""
    try:
        result = assign_pending_tasks(db)
    except AssignmentError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    return APIResponse(
        data=AssignmentRunOut(
            assigned=result.assigned,
            skipped=result.skipped,
            by_assignee=result.by_assignee,
            assignee_names=result.assignee_names,
        )
    )


@router.post("/{task_id}/claim", response_model=APIResponse[TaskOut])
def claim(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("COLLECTOR", "SUPERVISOR", "ADMIN")),
) -> APIResponse[TaskOut]:
    """领取任务：PENDING → IN_PROGRESS。COLLECTOR 只能领取分配给自己的任务。"""
    try:
        task = claim_task(db, task_id, current_user)
    except TaskNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except TaskStateError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return APIResponse(data=TaskOut.model_validate(task))


@router.post("/{task_id}/result", response_model=APIResponse[TaskOut])
def submit_task_result(
    task_id: int,
    payload: TaskResultIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("COLLECTOR", "SUPERVISOR", "ADMIN")),
) -> APIResponse[TaskOut]:
    """回填处理结果：IN_PROGRESS → DONE(终态) 或 PENDING(PROMISE 改期)。"""
    try:
        task = submit_result(
            db,
            task_id,
            current_user,
            result=payload.result,
            note=payload.note,
            next_followup_date=payload.next_followup_date,
            talk_used=payload.talk_used,
        )
    except TaskNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except TaskStateError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return APIResponse(data=TaskOut.model_validate(task))

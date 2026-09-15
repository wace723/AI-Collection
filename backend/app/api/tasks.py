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
from sqlalchemy import case
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db, require_role
from app.models.order import Order, OrderFeature
from app.models.task import Task
from app.models.user import User
from app.schemas.common import APIResponse, PagedResponse
from app.schemas.task import (
    AssignmentRunOut,
    BatchRunOut,
    BatchStatusOut,
    FeatureBriefOut,
    OrderBriefOut,
    TaskDetailOut,
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
    reassign_task,
    run_batch,
    submit_result,
)

router = APIRouter()

# 列表排序：风险档 HIGH<MEDIUM<LOW（数值越小越前）；同档按 due_date 升序（账龄倒序）；
# 再按 id 兜底稳定。用 sqlalchemy.case（非 func.case，避免 risk-002 记录的 else_ 坑）。
_RISK_ORDER = case(
    (Task.risk_tier == "HIGH", 0),
    (Task.risk_tier == "MEDIUM", 1),
    (Task.risk_tier == "LOW", 2),
    else_=3,
)


# ── 任务列表与详情（wb-001） ───────────────────────────────────────


def _task_to_out(task: Task, order: Order | None = None) -> TaskOut:
    """Task ORM → TaskOut，补充 supplier_name（来自关联 Order）。"""
    base = TaskOut.model_validate(task)
    if order is not None:
        base.supplier_name = order.supplier_name or ""
    return base


@router.get("", response_model=APIResponse[PagedResponse[TaskOut]])
def list_tasks(
    status_filter: str | None = Query(default=None, alias="status"),
    assignee: int | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> APIResponse[PagedResponse[TaskOut]]:
    """任务列表（按风险+账龄排序）。

    - COLLECTOR：强制只看分配给自己的任务（忽略 assignee 入参）
    - SUPERVISOR/ADMIN：可选 assignee 过滤，不传则看全部
    - 返回 supplier_name（join Order）
    """
    q = db.query(Task)
    if current_user.role == "COLLECTOR":
        q = q.filter(Task.assignee_id == current_user.id)
    elif assignee is not None:
        q = q.filter(Task.assignee_id == assignee)
    if status_filter:
        q = q.filter(Task.status == status_filter)

    total = q.count()
    rows = (
        q.order_by(_RISK_ORDER, Task.due_date, Task.id)
        .offset((page - 1) * size)
        .limit(size)
        .all()
    )
    # 批量取关联 Order 的 supplier_name（按需查询，避免 N+1）
    order_ids = [r.order_id for r in rows]
    orders_map: dict[int, Order] = {}
    if order_ids:
        for o in db.query(Order).filter(Order.id.in_(order_ids)).all():
            orders_map[o.id] = o
    return APIResponse(
        data=PagedResponse(
            items=[_task_to_out(r, orders_map.get(r.order_id)) for r in rows],
            total=total,
            page=page,
            limit=size,
        )
    )


@router.get("/{task_id}", response_model=APIResponse[TaskDetailOut])
def get_task(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> APIResponse[TaskDetailOut]:
    """任务详情（含订单摘要 + 特征摘要）。

    COLLECTOR 只能看分配给自己的任务，否则 403。
    """
    task = db.get(Task, task_id)
    if task is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"任务 {task_id} 不存在")
    if current_user.role == "COLLECTOR" and task.assignee_id != current_user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "无权查看他人任务")

    order = db.get(Order, task.order_id)
    feature = db.get(OrderFeature, task.order_id)
    base = _task_to_out(task, order)
    return APIResponse(
        data=TaskDetailOut(
            **base.model_dump(),
            order=OrderBriefOut.model_validate(order) if order else None,
            feature=FeatureBriefOut.model_validate(feature) if feature else None,
        )
    )


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
    return APIResponse(data=_task_to_out(task, db.get(Order, task.order_id)))


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
    return APIResponse(data=_task_to_out(task, db.get(Order, task.order_id)))


@router.post("/{task_id}/reassign", response_model=APIResponse[TaskOut])
def reassign(
    task_id: int,
    assignee_id: int = Query(..., description="目标催收员 ID"),
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_role("SUPERVISOR", "ADMIN")),
) -> APIResponse[TaskOut]:
    """主管手动改派任务（SUPERVISOR/ADMIN）。

    把任务从当前催收员改派给另一名活跃催收员；终态不可改派；
    IN_PROGRESS 改派退回 PENDING。
    """
    try:
        task = reassign_task(db, task_id, assignee_id)
    except TaskNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except TaskStateError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return APIResponse(data=_task_to_out(task, db.get(Order, task.order_id)))

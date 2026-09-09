"""talk-001 话术推荐路由。

GET /api/talk/recommend?task_id= —— 推荐基础话术（登录可见，COLLECTOR 仅自己任务）
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db
from app.models.task import Task
from app.models.user import User
from app.schemas.common import APIResponse
from app.schemas.talk import TalkRecommendOut, TalkTemplateOut
from app.services.talk_engine import recommend_talks
from app.services.talk_engine.matcher import derive_user_tag, map_age_bucket

router = APIRouter()


@router.get("/recommend", response_model=APIResponse[TalkRecommendOut])
def recommend(
    task_id: int = Query(..., description="任务 ID"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> APIResponse[TalkRecommendOut]:
    """推荐基础话术（按风险档×账龄段×场景×用户特征匹配，ANY 兜底）。

    COLLECTOR 只能查看分配给自己的任务；SUPERVISOR/ADMIN 任意。
    """
    task = db.get(Task, task_id)
    if task is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"任务 {task_id} 不存在")
    if current_user.role == "COLLECTOR" and task.assignee_id != current_user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "无权查看他人任务话术")

    today = date.today()
    recs = recommend_talks(db, task, today=today)

    # 复算展示用的 age_bucket / user_tag（与 matcher 一致）
    from app.models.order import Order, OrderFeature

    order = db.get(Order, task.order_id)
    feature = db.get(OrderFeature, task.order_id)
    age = (today - order.win_bid_date).days if order and order.win_bid_date else 0

    return APIResponse(
        data=TalkRecommendOut(
            task_id=task_id,
            age_bucket=map_age_bucket(age),
            user_tag=derive_user_tag(feature),
            templates=[
                TalkTemplateOut(
                    template_id=r.template_id,
                    name=r.name,
                    risk_tier=r.risk_tier,
                    age_bucket=r.age_bucket,
                    scene=r.scene,
                    user_feature_tag=r.user_feature_tag,
                    content=r.content,
                    score=r.score,
                )
                for r in recs
            ],
        )
    )

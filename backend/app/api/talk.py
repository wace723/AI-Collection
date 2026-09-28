"""talk-001/002/003 话术推荐、AI 生成与模板管理路由。

GET  /api/talk/recommend?task_id=      —— 推荐基础话术（登录，COLLECTOR 仅自己任务）
POST /api/talk/generate                —— AI 生成话术（同上）
POST /api/talk/feedback                —— 话术反馈
GET  /api/talk/templates               —— 模板列表（ADMIN，按档/轮/类型筛选）
POST /api/talk/templates               —— 创建模板（ADMIN，占位符校验）
PUT  /api/talk/templates/{id}          —— 更新模板（ADMIN）
DELETE /api/talk/templates/{id}        —— 软删除模板（ADMIN）
GET  /api/talk/templates/placeholders  —— 可用占位符列表（登录可见）
GET  /api/talk/coverage                —— 覆盖度矩阵（ADMIN）
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db, require_role
from app.models.task import Task
from app.models.talk import TalkTemplate
from app.models.user import User
from app.schemas.common import APIResponse
from app.schemas.talk import (
    CoverageCellOut,
    CoverageMatrixOut,
    FeedbackIn,
    FeedbackOut,
    GenerateTalkOut,
    PlaceholderOut,
    TalkRecommendOut,
    TalkTemplateIn,
    TalkTemplateItem,
    TalkTemplateManageOut,
)
from app.services.risk_engine.config_service import get_current_config
from app.services.talk_engine import recommend_talks
from app.services.talk_engine.coverage import compute_coverage
from app.services.talk_engine.generator import generate_talk, update_feedback
from app.services.talk_engine.placeholders import (
    available_placeholders,
    validate_placeholders,
)

router = APIRouter()


# ── 推荐话术（二维匹配，未配返回空 + has_talk=false） ─────────────────


@router.get("/recommend", response_model=APIResponse[TalkRecommendOut])
def recommend(
    task_id: int = Query(..., description="任务 ID"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> APIResponse[TalkRecommendOut]:
    """推荐基础话术（按 [风险档 × 轮次] 二维匹配，无兜底）。

    COLLECTOR 只能查看分配给自己的任务；SUPERVISOR/ADMIN 任意。
    未配话术返回空列表 + has_talk=false。
    """
    task = db.get(Task, task_id)
    if task is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"任务 {task_id} 不存在")
    if current_user.role == "COLLECTOR" and task.assignee_id != current_user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "无权查看他人任务话术")

    recs = recommend_talks(db, task, today=date.today())
    return APIResponse(
        data=TalkRecommendOut(
            task_id=task_id,
            has_talk=bool(recs),
            templates=[
                TalkTemplateItem(
                    template_id=r.template_id,
                    name=r.name,
                    risk_tier=r.risk_tier,
                    scene=r.scene,
                    template_type=r.template_type,
                    content=r.content,
                )
                for r in recs
            ],
        )
    )


def _check_task_access(db: Session, task_id: int, user: User) -> Task:
    """取任务并校验：COLLECTOR 只能操作自己的任务。"""
    task = db.get(Task, task_id)
    if task is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"任务 {task_id} 不存在")
    if user.role == "COLLECTOR" and task.assignee_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "无权操作他人任务")
    return task


@router.post("/generate", response_model=APIResponse[GenerateTalkOut])
def generate(
    task_id: int = Query(..., description="任务 ID"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> APIResponse[GenerateTalkOut]:
    """AI 生成话术（COLLECTOR 仅自己任务）。失败降级模板，不阻断。"""
    task = _check_task_access(db, task_id, current_user)
    result = generate_talk(db, task)
    return APIResponse(
        data=GenerateTalkOut(
            enabled=result.enabled,
            content=result.content,
            conversation_id=result.conversation_id,
            provider=result.provider,
            fallback=result.fallback,
            fallback_reason=result.fallback_reason,
        )
    )


@router.post("/feedback", response_model=APIResponse[FeedbackOut])
def feedback(
    payload: FeedbackIn,
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
) -> APIResponse[FeedbackOut]:
    """话术反馈 useful/useless（TC-TALK-09）。"""
    try:
        conv = update_feedback(db, payload.conversation_id, payload.feedback)
    except LookupError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    return APIResponse(
        data=FeedbackOut(
            conversation_id=conv.id, feedback=conv.feedback or ""
        )
    )


# ── 占位符列表（登录可见，供前端「插入变量」按钮） ────────────────────


@router.get(
    "/templates/placeholders",
    response_model=APIResponse[list[PlaceholderOut]],
)
def list_placeholders(
    _current_user: User = Depends(get_current_user),
) -> APIResponse[list[PlaceholderOut]]:
    """可用占位符列表（供前端模板编辑器插入变量按钮）。"""
    return APIResponse(
        data=[
            PlaceholderOut(key=p.key, description=p.description, group=p.group)
            for p in available_placeholders()
        ]
    )


# ── 话术模板管理 CRUD（ADMIN） ──────────────────────────────────────


def _validate_template_payload(payload: TalkTemplateIn) -> None:
    """校验模板载荷：scene 格式 + 类型必填字段 + 占位符合法性。"""
    # scene 必须 ROUND_N 格式
    if not (payload.scene.startswith("ROUND_") and payload.scene[6:].isdigit()):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"scene 必须为 ROUND_N 格式，得到 {payload.scene!r}",
        )
    # 类型必填字段
    if payload.template_type == "FIXED" and not payload.content:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "FIXED 模板必须填写 content",
        )
    if payload.template_type == "AI_PROMPT" and not (
        payload.system_prompt and payload.user_prompt
    ):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "AI_PROMPT 模板必须填写 system_prompt 和 user_prompt",
        )
    # 占位符校验（FIXED 校 content，AI_PROMPT 校 system+user prompt）
    texts = [payload.content or ""]
    if payload.template_type == "AI_PROMPT":
        texts += [payload.system_prompt or "", payload.user_prompt or ""]
    unknown: list[str] = []
    for t in texts:
        unknown += validate_placeholders(t)
    if unknown:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"模板含未知占位符：{unknown}，请使用「插入变量」按钮选择合法占位符",
        )


def _to_manage_out(t: TalkTemplate) -> TalkTemplateManageOut:
    return TalkTemplateManageOut(
        id=t.id,
        name=t.name,
        risk_tier=t.risk_tier,
        scene=t.scene,
        age_bucket=t.age_bucket,
        user_feature_tag=t.user_feature_tag,
        template_type=t.template_type,
        content=t.content,
        system_prompt=t.system_prompt,
        user_prompt=t.user_prompt,
        is_active=t.is_active,
    )


@router.get("/templates", response_model=APIResponse[list[TalkTemplateManageOut]])
def list_templates(
    risk_tier: str | None = Query(None, description="按风险档筛选"),
    scene: str | None = Query(None, description="按轮次筛选"),
    template_type: str | None = Query(None, description="按类型筛选"),
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_role("ADMIN")),
) -> APIResponse[list[TalkTemplateManageOut]]:
    """话术模板列表（ADMIN，按档/轮/类型筛选）。"""
    q = db.query(TalkTemplate)
    if risk_tier:
        q = q.filter(TalkTemplate.risk_tier == risk_tier)
    if scene:
        q = q.filter(TalkTemplate.scene == scene)
    if template_type:
        q = q.filter(TalkTemplate.template_type == template_type)
    rows = q.order_by(
        TalkTemplate.risk_tier, TalkTemplate.scene, TalkTemplate.template_type
    ).all()
    return APIResponse(data=[_to_manage_out(t) for t in rows])


@router.post(
    "/templates",
    response_model=APIResponse[TalkTemplateManageOut],
    status_code=status.HTTP_201_CREATED,
)
def create_template(
    payload: TalkTemplateIn,
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_role("ADMIN")),
) -> APIResponse[TalkTemplateManageOut]:
    """创建话术模板（ADMIN，占位符校验 400）。"""
    _validate_template_payload(payload)
    t = TalkTemplate(
        name=payload.name,
        risk_tier=payload.risk_tier,
        age_bucket="ANY",  # 存档，不再参与匹配
        scene=payload.scene,
        user_feature_tag=None,
        template_type=payload.template_type,
        content=payload.content or "",
        system_prompt=payload.system_prompt,
        user_prompt=payload.user_prompt,
        is_active=payload.is_active,
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    return APIResponse(data=_to_manage_out(t))


@router.put(
    "/templates/{template_id}",
    response_model=APIResponse[TalkTemplateManageOut],
)
def update_template(
    template_id: int,
    payload: TalkTemplateIn,
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_role("ADMIN")),
) -> APIResponse[TalkTemplateManageOut]:
    """更新话术模板（ADMIN，占位符校验 400）。"""
    t = db.get(TalkTemplate, template_id)
    if t is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"模板 {template_id} 不存在")
    _validate_template_payload(payload)
    t.name = payload.name
    t.risk_tier = payload.risk_tier
    t.scene = payload.scene
    t.template_type = payload.template_type
    t.content = payload.content or ""
    t.system_prompt = payload.system_prompt
    t.user_prompt = payload.user_prompt
    t.is_active = payload.is_active
    db.commit()
    db.refresh(t)
    return APIResponse(data=_to_manage_out(t))


@router.delete(
    "/templates/{template_id}",
    response_model=APIResponse[TalkTemplateManageOut],
)
def delete_template(
    template_id: int,
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_role("ADMIN")),
) -> APIResponse[TalkTemplateManageOut]:
    """软删除话术模板（ADMIN，is_active=False）。"""
    t = db.get(TalkTemplate, template_id)
    if t is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"模板 {template_id} 不存在")
    t.is_active = False
    db.commit()
    db.refresh(t)
    return APIResponse(data=_to_manage_out(t))


# ── 覆盖度矩阵（ADMIN） ────────────────────────────────────────────


@router.get("/coverage", response_model=APIResponse[CoverageMatrixOut])
def get_coverage(
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_role("ADMIN")),
) -> APIResponse[CoverageMatrixOut]:
    """话术覆盖度矩阵（按当前 active risk_config 展开 [档×轮]）。"""
    snap = get_current_config(db)
    if snap is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "尚无生效风险档配置"
        )
    matrix = compute_coverage(db, snap)
    return APIResponse(
        data=CoverageMatrixOut(
            cells=[
                CoverageCellOut(
                    risk_tier=c.risk_tier,
                    scene=c.scene,
                    day_offset=c.day_offset,
                    fixed_configured=c.fixed_configured,
                    ai_prompt_configured=c.ai_prompt_configured,
                )
                for c in matrix.cells
            ],
            missing_count=len(matrix.missing_cells),
        )
    )

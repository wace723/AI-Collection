"""种子数据脚本：插入默认用户 + 默认风险档配置 + 默认话术模板。

用法：python seed.py（在 backend/ 目录下运行）
幂等：已存在的用户/active 配置/同名模板均跳过，不重复插入。
默认密码统一为 admin123，仅用于开发环境。
"""

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models.ai_config import AIConfig
from app.models.talk import TalkTemplate
from app.models.user import User
from app.services.risk_engine.config_service import seed_default_config

# (username, display_name, role)
DEFAULT_USERS = [
    ("admin", "管理员", "ADMIN"),
    ("supervisor", "催收主管", "SUPERVISOR"),
    ("collector1", "催收员1", "COLLECTOR"),
    ("collector2", "催收员2", "COLLECTOR"),
    ("collector3", "催收员3", "COLLECTOR"),
]

DEFAULT_PASSWORD = "admin123"

# 默认话术模板（talk-003 二维匹配 [风险档 × 轮次]）。
# scene=ROUND_N（由 risk_config 的 schedules seq 自动生成）。
# template_type=FIXED（最终文本，content 含占位符）；AI_PROMPT 示例见末尾。
# 占位符经 validate_placeholders 校验，渲染见 renderer。
DEFAULT_TALK_TEMPLATES = [
    # ── HIGH 档 3 轮 FIXED ──
    {
        "name": "HIGH×ROUND_1×FIXED",
        "risk_tier": "HIGH",
        "age_bucket": "ANY",
        "scene": "ROUND_1",
        "user_feature_tag": None,
        "template_type": "FIXED",
        "content": "尊敬的{供应商名称}，您平台使用费订单{订单号}（标的：{标的名称}）已到应缴日{应催日}，请尽快登录平台完成缴费，避免影响后续投标资格。",
        "system_prompt": None,
        "user_prompt": None,
    },
    {
        "name": "HIGH×ROUND_2×FIXED",
        "risk_tier": "HIGH",
        "age_bucket": "ANY",
        "scene": "ROUND_2",
        "user_feature_tag": None,
        "template_type": "FIXED",
        "content": "{供应商名称}您好，订单{订单号}的平台使用费仍未缴纳（{账龄段}），请尽快处理，避免影响后续业务。",
        "system_prompt": None,
        "user_prompt": None,
    },
    {
        "name": "HIGH×ROUND_3×FIXED",
        "risk_tier": "HIGH",
        "age_bucket": "ANY",
        "scene": "ROUND_3",
        "user_feature_tag": None,
        "template_type": "FIXED",
        "content": "{供应商名称}，订单{订单号}平台使用费已逾期较久（高风险档，第3轮催收），请尽快缴纳，否则将影响信用记录。",
        "system_prompt": None,
        "user_prompt": None,
    },
    # ── MEDIUM 档 1 轮 FIXED ──
    {
        "name": "MEDIUM×ROUND_1×FIXED",
        "risk_tier": "MEDIUM",
        "age_bucket": "ANY",
        "scene": "ROUND_1",
        "user_feature_tag": None,
        "template_type": "FIXED",
        "content": "{供应商名称}，订单{订单号}（标的：{标的名称}）平台使用费已逾期，请尽快缴纳。",
        "system_prompt": None,
        "user_prompt": None,
    },
    # ── LOW 档 1 轮 FIXED ──
    {
        "name": "LOW×ROUND_1×FIXED",
        "risk_tier": "LOW",
        "age_bucket": "ANY",
        "scene": "ROUND_1",
        "user_feature_tag": None,
        "template_type": "FIXED",
        "content": "{供应商名称}，订单{订单号}平台使用费长期未缴，请尽快处理以免影响信用记录。",
        "system_prompt": None,
        "user_prompt": None,
    },
    # ── HIGH 档第 1 轮 AI_PROMPT 示例 ──
    {
        "name": "HIGH×ROUND_1×AI_PROMPT",
        "risk_tier": "HIGH",
        "age_bucket": "ANY",
        "scene": "ROUND_1",
        "user_feature_tag": None,
        "template_type": "AI_PROMPT",
        "content": "",
        "system_prompt": "语气正式但紧迫，强调逾期对投标资格的影响，给出具体缴费指引。",
        "user_prompt": "请为供应商{供应商名称}生成第1轮催收话术，订单号{订单号}，标的{标的名称}，风险档{风险档}，应催日{应催日}，账龄{账龄天数}天。",
    },
]


def seed_default_talk_templates(db) -> int:
    """插入默认话术模板（按 name 幂等）。返回新建数。"""
    created = 0
    for item in DEFAULT_TALK_TEMPLATES:
        existing = (
            db.query(TalkTemplate).filter(TalkTemplate.name == item["name"]).first()
        )
        if existing:
            continue
        db.add(TalkTemplate(is_active=True, **item))
        created += 1
    db.commit()
    return created


def seed_ai_config(db) -> bool:
    """首次用 .env 默认值初始化 AI 话术配置单行（id=1）。已存在则跳过。

    若 .env 提供了 LLM_API_KEY（用户放了真实 key），默认 provider=openai_compatible
    且 enabled=True（意图：放 key 即启用真实 LLM）；否则 mock/关闭。
    用户可在前端「配置后台」运行时修改。
    """
    if db.get(AIConfig, 1) is not None:
        return False
    has_key = bool(settings.LLM_API_KEY)
    db.add(
        AIConfig(
            id=1,
            provider="openai_compatible" if has_key else settings.LLM_PROVIDER,
            api_key=settings.LLM_API_KEY,
            base_url=settings.LLM_BASE_URL,
            model=settings.LLM_MODEL,
            enabled=has_key or settings.AI_TALK_ENABLED,
        )
    )
    db.commit()
    return True


def seed_users(db) -> tuple[list[str], list[str]]:
    """插入默认用户。返回 (created, skipped)。"""
    created: list[str] = []
    skipped: list[str] = []
    for username, display_name, role in DEFAULT_USERS:
        existing = db.query(User).filter(User.username == username).first()
        if existing:
            skipped.append(username)
            continue
        user = User(
            username=username,
            password_hash=hash_password(DEFAULT_PASSWORD),
            display_name=display_name,
            role=role,
            is_active=True,
        )
        db.add(user)
        created.append(username)
    db.commit()
    return created, skipped


def seed() -> None:
    db = SessionLocal()
    try:
        # 用户
        created, skipped = seed_users(db)
        print("=== 种子数据完成 ===")
        print(f"  用户新建: {created if created else '无'}")
        print(f"  用户跳过(已存在): {skipped if skipped else '无'}")

        # 风险档配置
        config_created = seed_default_config(db)
        if config_created:
            print("  风险档配置: 新建 v1（high=70, medium=30 + 5 催收时点）")
        else:
            print("  风险档配置: 跳过(已存在 active 配置)")

        # 话术模板
        talk_created = seed_default_talk_templates(db)
        if talk_created:
            print(f"  话术模板: 新建 {talk_created} 条（HIGH/MEDIUM/LOW + ANY 兜底）")
        else:
            print("  话术模板: 跳过(已存在)")

        # AI 话术配置（从 .env 默认值初始化单行）
        ai_created = seed_ai_config(db)
        if ai_created:
            print(
                f"  AI 配置: 新建（provider={settings.LLM_PROVIDER}, "
                f"model={settings.LLM_MODEL or '未设置'}, "
                f"enabled={settings.AI_TALK_ENABLED}）"
            )
        else:
            print("  AI 配置: 跳过(已存在)")

        print(f"  默认密码: {DEFAULT_PASSWORD}")
    finally:
        db.close()


if __name__ == "__main__":
    seed()

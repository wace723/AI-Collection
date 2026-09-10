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

# 默认话术模板（talk-001）。维度：[风险档 × 账龄段 × 场景 × 用户特征]
# user_feature_tag=None 表示该维度通配（ANY）。
DEFAULT_TALK_TEMPLATES = [
    {
        "name": "HIGH×8_15×SECOND×MEMBER",
        "risk_tier": "HIGH",
        "age_bucket": "8_15",
        "scene": "SECOND",
        "user_feature_tag": "MEMBER",
        "content": "尊敬的{供应商名称}（会员），您订单{service_fee_order_no}的平台使用费已逾期，请尽快登录平台完成缴费，避免影响后续投标资格与会员权益。",
    },
    {
        "name": "HIGH×ANY×SECOND×ANY",
        "risk_tier": "HIGH",
        "age_bucket": "ANY",
        "scene": "SECOND",
        "user_feature_tag": None,
        "content": "{供应商名称}您好，订单{service_fee_order_no}的平台使用费仍未缴纳，请尽快处理，避免影响后续业务。",
    },
    {
        "name": "HIGH×0_7×FIRST×ANY",
        "risk_tier": "HIGH",
        "age_bucket": "0_7",
        "scene": "FIRST",
        "user_feature_tag": None,
        "content": "{供应商名称}，您的平台使用费订单{service_fee_order_no}已到应缴日{应催日}，请及时缴费。",
    },
    {
        "name": "MEDIUM×31_90×FIRST×ANY",
        "risk_tier": "MEDIUM",
        "age_bucket": "31_90",
        "scene": "FIRST",
        "user_feature_tag": None,
        "content": "{供应商名称}，订单{service_fee_order_no}平台使用费已逾期较久（{风险档}档），请尽快缴纳。",
    },
    {
        "name": "LOW×90_PLUS×FIRST×ANY",
        "risk_tier": "LOW",
        "age_bucket": "90_PLUS",
        "scene": "FIRST",
        "user_feature_tag": None,
        "content": "{供应商名称}，订单{service_fee_order_no}平台使用费长期未缴，请尽快处理以免影响信用记录。",
    },
    {
        "name": "ANY×ANY×ANY×ANY",
        "risk_tier": "ANY",
        "age_bucket": "ANY",
        "scene": "ANY",
        "user_feature_tag": None,
        "content": "{供应商名称}您好，订单{service_fee_order_no}的平台使用费待缴纳，请尽快登录平台处理。",
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

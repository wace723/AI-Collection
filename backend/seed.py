"""种子数据脚本：插入默认用户 + 默认风险档配置。

用法：python seed.py（在 backend/ 目录下运行）
幂等：已存在的用户/active 配置均跳过，不重复插入。
默认密码统一为 admin123，仅用于开发环境。
"""

from app.core.database import SessionLocal
from app.core.security import hash_password
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

        print(f"  默认密码: {DEFAULT_PASSWORD}")
    finally:
        db.close()


if __name__ == "__main__":
    seed()

"""种子数据脚本：插入默认用户（3 催收员 + 1 主管 + 1 管理员）。

用法：python seed.py（在 backend/ 目录下运行）
幂等：已存在的用户跳过，不重复插入。
默认密码统一为 admin123，仅用于开发环境。
"""

from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models.user import User

# (username, display_name, role)
DEFAULT_USERS = [
    ("admin", "管理员", "ADMIN"),
    ("supervisor", "催收主管", "SUPERVISOR"),
    ("collector1", "催收员1", "COLLECTOR"),
    ("collector2", "催收员2", "COLLECTOR"),
    ("collector3", "催收员3", "COLLECTOR"),
]

DEFAULT_PASSWORD = "admin123"


def seed() -> None:
    db = SessionLocal()
    try:
        created = []
        skipped = []
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

        print("=== 种子数据完成 ===")
        print(f"  新建: {created if created else '无'}")
        print(f"  跳过(已存在): {skipped if skipped else '无'}")
        print(f"  默认密码: {DEFAULT_PASSWORD}")
    finally:
        db.close()


if __name__ == "__main__":
    seed()

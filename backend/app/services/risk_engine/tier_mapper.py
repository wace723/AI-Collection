"""风险档映射：风险概率 → HIGH/MEDIUM/LOW。

规则（docs/02 §3.2.3、docs/03 TC-RISK-02/03）：
    prob ≥ high_threshold   → HIGH
    prob ≥ medium_threshold → MEDIUM
    prob <  medium_threshold → LOW

默认阈值：high=70，medium=30（与 risk_configs 表默认一致）。
risk-001 阶段配置 CRUD 尚未实现（属 risk-002），此处优先读 active
配置；无 active 配置则回退默认阈值，保证 risk-001 可独立验证。
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models.risk import RiskConfig

HIGH = "HIGH"
MEDIUM = "MEDIUM"
LOW = "LOW"

# 默认阈值（与 RiskConfig 模型 default 一致）
DEFAULT_HIGH_THRESHOLD = 70.0
DEFAULT_MEDIUM_THRESHOLD = 30.0


@dataclass(frozen=True)
class Thresholds:
    """风险档阈值（已解析，含默认回退）。"""

    high: float = DEFAULT_HIGH_THRESHOLD
    medium: float = DEFAULT_MEDIUM_THRESHOLD


def get_active_thresholds(db: Session) -> Thresholds:
    """读取当前生效的风险档配置阈值。

    优先取 ``risk_configs`` 中 ``is_active=True`` 的记录；
    无 active 配置时回退默认阈值（70/30）。
    """
    config = (
        db.query(RiskConfig)
        .filter(RiskConfig.is_active.is_(True))
        .order_by(RiskConfig.version.desc())
        .first()
    )
    if config is None:
        return Thresholds()
    return Thresholds(
        high=float(config.high_threshold),
        medium=float(config.medium_threshold),
    )


def map_tier(prob: float, thresholds: Thresholds) -> str:
    """纯函数：概率 → 风险档。

    边界语义（docs/03 TC-RISK-02/03）：≥ 即归入该档。
        70.00 → HIGH，69.99 → MEDIUM
        30.00 → MEDIUM，29.99 → LOW
        0 → LOW，100 → HIGH
    """
    if prob >= thresholds.high:
        return HIGH
    if prob >= thresholds.medium:
        return MEDIUM
    return LOW


__all__ = [
    "HIGH",
    "MEDIUM",
    "LOW",
    "Thresholds",
    "get_active_thresholds",
    "map_tier",
]

"""风险重算编排器。

职责（单一：编排，不自己算概率、不自己定档位）：
1. 取当前生效阈值（tier_mapper）
2. 对每笔订单 + 特征调用注入的 RiskProvider 算概率
3. 用 tier_mapper 映射档位
4. 回写 Order.risk_prob / risk_tier / risk_import_time

Provider 通过 ``get_risk_provider`` 工厂按配置注入，切换 mock→algorithm
无需改调用方（CLAUDE.md 关键设计约束 #1）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.order import Order, OrderFeature
from app.services.risk_engine.provider import (
    AlgorithmRiskProvider,
    MockRiskProvider,
    RiskProvider,
)
from app.services.risk_engine.tier_mapper import Thresholds, get_active_thresholds, map_tier

# Provider 名称 → 实现类（扩展新 Provider 在此登记即可）
_PROVIDERS: dict[str, type[RiskProvider]] = {
    "mock": MockRiskProvider,
    "algorithm": AlgorithmRiskProvider,
}


def get_risk_provider(name: str | None = None) -> RiskProvider:
    """按配置名返回 RiskProvider 实例。

    默认从配置读取 RISK_PROVIDER（缺省 mock）。未知名回退 mock
    并保持调用方能正常工作（mock 是 MVP 安全默认）。
    """
    resolved = name or settings.RISK_PROVIDER
    cls = _PROVIDERS.get(resolved, MockRiskProvider)
    return cls()


@dataclass(frozen=True)
class RecalcResult:
    """重算结果统计。"""

    recalculated: int = 0
    skipped: int = 0
    tiers: dict[str, int] = field(default_factory=dict)


def recalculate_risks(
    db: Session,
    provider: RiskProvider | None = None,
    order_ids: list[int] | None = None,
    now: datetime | None = None,
) -> RecalcResult:
    """批量重算风险概率并回写。

    Args:
        db: 数据库会话
        provider: 风险计算 Provider，None 则按配置取默认
        order_ids: 仅重算指定订单；None 重算全部
        now: 计算时间戳（测试注入），None 用当前 UTC

    Returns:
        RecalcResult(recalculated, skipped, tiers)
    """
    prov = provider or get_risk_provider()
    thresholds = get_active_thresholds(db)
    calc_time = now or datetime.now(timezone.utc)

    query = db.query(Order)
    if order_ids:
        query = query.filter(Order.id.in_(order_ids))
    orders = query.all()

    recalculated = 0
    skipped = 0
    tiers: dict[str, int] = {}

    for order in orders:
        feature = (
            db.query(OrderFeature)
            .filter(OrderFeature.order_id == order.id)
            .first()
        )
        prob = prov.calculate(order, feature)
        tier = map_tier(prob, thresholds)

        order.risk_prob = prob
        order.risk_tier = tier
        order.risk_import_time = calc_time

        recalculated += 1
        tiers[tier] = tiers.get(tier, 0) + 1

    db.commit()
    del skipped  # 当前无跳过逻辑，保留字段供后续扩展
    return RecalcResult(recalculated=recalculated, skipped=0, tiers=tiers)


__all__ = [
    "RecalcResult",
    "get_risk_provider",
    "recalculate_risks",
]

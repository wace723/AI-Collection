"""risk-001 风险重算相关 schema。"""

from __future__ import annotations

from pydantic import BaseModel


class RecalcRiskSummary(BaseModel):
    """风险重算结果统计。"""

    recalculated: int
    skipped: int
    tiers: dict[str, int]


class RiskTierOut(BaseModel):
    """单笔订单风险档位（轻量，供列表/详情引用）。"""

    order_id: int
    risk_prob: float | None = None
    risk_tier: str | None = None


__all__ = ["RecalcRiskSummary", "RiskTierOut"]

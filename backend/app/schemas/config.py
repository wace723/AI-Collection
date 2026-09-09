"""risk-002 风险档配置相关 schema。

输入/输出 Pydantic 模型，遵循 schemas/auth.py、schemas/data.py 风格。
输入校验在边界 fail fast（high>medium、day_offset 正整数、枚举合法）。
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class RiskTierEnum(str, Enum):
    """风险档。"""

    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class SceneEnum(str, Enum):
    """催收场景。"""

    FIRST = "FIRST"
    SECOND = "SECOND"
    THIRD = "THIRD"
    DISPUTE = "DISPUTE"
    PROMISE = "PROMISE"


class ScheduleOut(BaseModel):
    """催收时点输出。"""

    risk_tier: RiskTierEnum
    day_offset: int
    scene: SceneEnum
    seq: int
    is_active: bool


class RiskConfigOut(BaseModel):
    """风险档配置输出（含关联催收时点）。"""

    id: int
    version: int
    high_threshold: float
    medium_threshold: float
    is_active: bool
    created_by: int | None = None
    created_at: datetime
    updated_at: datetime
    schedules: list[ScheduleOut] = []

    model_config = ConfigDict(from_attributes=True)


class ScheduleIn(BaseModel):
    """催收时点输入（创建/更新配置时提交）。"""

    risk_tier: RiskTierEnum
    day_offset: int = Field(gt=0, description="中标后第 N 天，必须为正整数")
    scene: SceneEnum
    seq: int = Field(ge=1, description="该档内轮次序号，从 1 开始")


class RiskConfigUpdateIn(BaseModel):
    """更新风险档配置输入（生成新版本）。

    阈值范围 (0,100)；high 必须严格大于 medium；至少 1 条催收时点。
    """

    high_threshold: float = Field(gt=0, lt=100)
    medium_threshold: float = Field(gt=0, lt=100)
    schedules: list[ScheduleIn] = Field(min_length=1)

    @model_validator(mode="after")
    def _high_gt_medium(self) -> RiskConfigUpdateIn:
        if self.high_threshold <= self.medium_threshold:
            raise ValueError("high_threshold 必须严格大于 medium_threshold")
        return self


__all__ = [
    "RiskTierEnum",
    "SceneEnum",
    "ScheduleOut",
    "RiskConfigOut",
    "ScheduleIn",
    "RiskConfigUpdateIn",
]

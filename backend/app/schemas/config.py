"""risk-002 风险档配置相关 schema。

输入/输出 Pydantic 模型，遵循 schemas/auth.py、schemas/data.py 风格。
输入校验在边界 fail fast（high>medium、day_offset 正整数、枚举合法）。
"""

from __future__ import annotations

import re
from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class RiskTierEnum(str, Enum):
    """风险档。"""

    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


# scene 格式：ROUND_N（N 为正整数，对应该档 schedules 的 seq）。
# talk-003 起由 config_service 按 seq 自动生成，支持任意轮次。
_ROUND_PATTERN = re.compile(r"^ROUND_\d+$")


class SceneEnum(str, Enum):
    """催收场景（轮次标识）。

    talk-003 起统一为 ROUND_N（N 为该档 schedules 的 seq，支持任意轮次）。
    旧 FIRST/SECOND/THIRD 已迁移为 ROUND_1/2/3。scene 由 config_service 按 seq
    自动生成，不再由前端显式传入固定枚举；此枚举仅用于格式校验与文档。
    """

    ROUND_1 = "ROUND_1"
    ROUND_2 = "ROUND_2"
    ROUND_3 = "ROUND_3"
    ROUND_4 = "ROUND_4"
    ROUND_5 = "ROUND_5"
    # ROUND_6 及以上：前端可传任意 ROUND_N 字符串，config_service 按 seq 生成


def _validate_round_scene(v: str | None) -> str | None:
    """校验 scene 为 ROUND_N 格式（None 表示由 seq 自动生成，放行）。"""
    if v is None:
        return None
    if not _ROUND_PATTERN.match(v):
        raise ValueError(f"scene 必须为 ROUND_N 格式（如 ROUND_1），得到 {v!r}")
    return v


class ScheduleOut(BaseModel):
    """催收时点输出。"""

    risk_tier: RiskTierEnum
    day_offset: int
    scene: str  # ROUND_N（由 seq 自动生成，输出为字符串）
    seq: int
    is_active: bool


class RiskConfigOut(BaseModel):
    """风险档配置输出（含关联催收时点）。

    talk-003：update 后附加 coverage_hint（话术覆盖度提示，可选）。
    """

    id: int
    version: int
    high_threshold: float
    medium_threshold: float
    is_active: bool
    created_by: int | None = None
    created_at: datetime
    updated_at: datetime
    schedules: list[ScheduleOut] = []
    coverage_hint: dict | None = None  # task 6.3 填充

    model_config = ConfigDict(from_attributes=True)


class ScheduleIn(BaseModel):
    """催收时点输入（创建/更新配置时提交）。

    scene 可选：传 None 时由 config_service 按 seq 自动生成 ROUND_{seq}；
    传值时必须为 ROUND_N 格式（会被 seq 生成覆盖，仅作格式校验）。
    """

    risk_tier: RiskTierEnum
    day_offset: int = Field(gt=0, description="中标后第 N 天，必须为正整数")
    scene: str | None = Field(
        default=None, description="轮次标识；None=由 seq 自动生成 ROUND_{seq}"
    )
    seq: int = Field(ge=1, description="该档内轮次序号，从 1 开始")

    @model_validator(mode="after")
    def _validate_scene_format(self) -> ScheduleIn:
        _validate_round_scene(self.scene)
        return self


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


class AIConfigOut(BaseModel):
    """AI 话术配置输出（api_key 脱敏）。"""

    provider: str
    api_key_masked: str | None = None
    base_url: str | None = None
    model: str | None = None
    enabled: bool
    from_db: bool = False  # True=来自 DB，False=回退 .env
    updated_at: datetime | None = None
    updated_by: int | None = None


class AIConfigUpdateIn(BaseModel):
    """更新 AI 配置输入（主管/管理员）。

    api_key 传空/None 时保留旧值（前端脱敏展示后不回填明文）。
    """

    provider: Literal["mock", "openai_compatible"] = "mock"
    api_key: str | None = None
    base_url: str | None = None
    model: str | None = None
    enabled: bool = False


__all__ = [
    "RiskTierEnum",
    "SceneEnum",
    "ScheduleOut",
    "RiskConfigOut",
    "ScheduleIn",
    "RiskConfigUpdateIn",
    "AIConfigOut",
    "AIConfigUpdateIn",
]

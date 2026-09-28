"""话术占位符统一注册表（talk-003 D4）。

固定模板与 AI 提示词模板共享同一套占位符。保存模板时校验占位符合法性，
渲染时由 renderer.build_values 取值。本模块只管"哪些占位符合法"与"前端展示"，
不负责取值（取值在 renderer，避免循环依赖）。

合法占位符（花括号内文本）：
    供应商名称 / service_fee_order_no / 订单号 / 风险档 / 场景 / 应催日 / 会员状态
    标的名称 / 概算金额 / 历史中标率 / 账龄段 / 账龄天数 / 工程局单位 / 下属单位
    / 注册省份 / 轮次
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# 占位符正则：匹配 {中文/英文/数字/下划线} 形式的 {xxx}
_PLACEHOLDER_PATTERN = re.compile(r"\{([^{}]+)\}")


@dataclass(frozen=True)
class PlaceholderInfo:
    """单个占位符的描述信息（供前端「插入变量」按钮展示）。"""

    key: str  # 花括号内的标识符，如 "供应商名称"
    description: str  # 中文说明，如 "供应商/公司名称"
    group: str = "基础"  # 分组：基础/标的/特征/催收


# 合法占位符注册表（顺序即前端展示顺序）
# ── 基础（订单标识）──
_SUPPLIER = PlaceholderInfo("供应商名称", "供应商/公司名称", "基础")
_ORDER_NO = PlaceholderInfo("service_fee_order_no", "平台使用费订单号（系统编码）", "基础")
_ORDER_NO_CN = PlaceholderInfo("订单号", "平台使用费订单号（中文别名，同 service_fee_order_no）", "基础")
# ── 标的 ──
_SUBJECT = PlaceholderInfo("标的名称", "中标标的名称", "标的")
_ESTIMATE = PlaceholderInfo("概算金额", "标的概算金额（元）", "标的")
# ── 特征 ──
_WIN_RATE = PlaceholderInfo("历史中标率", "供应商历史中标率", "特征")
_AGE_BUCKET = PlaceholderInfo("账龄段", "账龄所处阶段（0_7/8_15/16_30/31_90/90_PLUS）", "特征")
_AGE_DAYS = PlaceholderInfo("账龄天数", "自中标日起的账龄天数", "特征")
_BUREAU = PlaceholderInfo("工程局单位", "工程局/主管单位", "特征")
_SUBSIDIARY = PlaceholderInfo("下属单位", "下属单位", "特征")
_PROVINCE = PlaceholderInfo("注册省份", "供应商注册省份", "特征")
_MEMBER = PlaceholderInfo("会员状态", "会员/非会员", "特征")
# ── 催收 ──
_TIER = PlaceholderInfo("风险档", "风险档位（HIGH/MEDIUM/LOW）", "催收")
_SCENE = PlaceholderInfo("场景", "催收轮次标识（ROUND_N）", "催收")
_ROUND = PlaceholderInfo("轮次", "催收轮次序号（如 1/2/3）", "催收")
_DUE = PlaceholderInfo("应催日", "应催收日期", "催收")

_REGISTRY: tuple[PlaceholderInfo, ...] = (
    _SUPPLIER,
    _ORDER_NO,
    _ORDER_NO_CN,
    _SUBJECT,
    _ESTIMATE,
    _WIN_RATE,
    _AGE_BUCKET,
    _AGE_DAYS,
    _BUREAU,
    _SUBSIDIARY,
    _PROVINCE,
    _MEMBER,
    _TIER,
    _SCENE,
    _ROUND,
    _DUE,
)

# 合法占位符 key 集合（O(1) 查询）
_VALID_KEYS: frozenset[str] = frozenset(p.key for p in _REGISTRY)


def validate_placeholders(text: str | None) -> list[str]:
    """校验文本中所有 {xxx} 占位符是否合法。

    Returns:
        未知占位符 key 列表（空列表 = 全部合法）。文本为 None 或空返回 []。
    """
    if not text:
        return []
    found = _PLACEHOLDER_PATTERN.findall(text)
    return [k for k in found if k not in _VALID_KEYS]


def available_placeholders() -> list[PlaceholderInfo]:
    """返回所有合法占位符（按注册顺序，供前端展示可插入变量）。"""
    return list(_REGISTRY)


__all__ = [
    "PlaceholderInfo",
    "validate_placeholders",
    "available_placeholders",
]

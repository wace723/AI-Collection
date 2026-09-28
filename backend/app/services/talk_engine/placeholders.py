"""话术占位符统一注册表（talk-003 D4）。

固定模板与 AI 提示词模板共享同一套占位符。保存模板时校验占位符合法性，
渲染时由 renderer.build_values 取值。本模块只管"哪些占位符合法"与"前端展示"，
不负责取值（取值在 renderer，避免循环依赖）。

合法占位符覆盖 Order + OrderFeature 的全部业务字段（标识/标的/风险/催收/特征），
key 沿用 CSV 业务列名（中文为主），便于业务人员理解。
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
    group: str = "基础"  # 分组：基础/标的/催收/缴费历史/活跃度/资质标签


# ── 基础（订单标识）──
_SUPPLIER = PlaceholderInfo("供应商名称", "供应商/公司名称", "基础")
_SUPPLIER_NO = PlaceholderInfo("供应商编号", "供应商编号（supplier_no）", "基础")
_ORDER_NO = PlaceholderInfo("service_fee_order_no", "平台使用费订单号（系统编码）", "基础")
_ORDER_NO_CN = PlaceholderInfo("订单号", "平台使用费订单号（中文别名）", "基础")
_BIZ_NO = PlaceholderInfo("业务编号", "业务编号（biz_no）", "基础")
# ── 标的 ──
_SUBJECT = PlaceholderInfo("标的名称", "中标标的名称", "标的")
_ESTIMATE = PlaceholderInfo("概算金额", "标的概算金额（元）", "标的")
_TENDER_TYPE = PlaceholderInfo("招标方式", "招标方式描述", "标的")
_PURCHASE_TYPE = PlaceholderInfo("采购方式", "采购方式描述", "标的")
_BID_CATEGORY = PlaceholderInfo("中标品类", "中标品类", "标的")
_CONTRACT_TYPE = PlaceholderInfo("合同类型", "合同类型", "标的")
_ORDER_GEN_DATE = PlaceholderInfo("订单生成日期", "订单生成日期", "标的")
# ── 催收 ──
_TIER = PlaceholderInfo("风险档", "风险档位（HIGH/MEDIUM/LOW）", "催收")
_RISK_PROB = PlaceholderInfo("风险概率", "风险概率（0~100）", "催收")
_SCENE = PlaceholderInfo("场景", "催收轮次标识（ROUND_N）", "催收")
_ROUND = PlaceholderInfo("轮次", "催收轮次序号（如 1/2/3）", "催收")
_DUE = PlaceholderInfo("应催日", "应催收日期", "催收")
_AGE_BUCKET = PlaceholderInfo("账龄段", "账龄阶段（0_7/8_15/16_30/31_90/90_PLUS）", "催收")
_AGE_DAYS = PlaceholderInfo("账龄天数", "自中标日起的账龄天数", "催收")
# ── 供应商归属/注册 ──
_BUREAU = PlaceholderInfo("工程局单位", "工程局/主管单位", "供应商归属")
_SUBSIDIARY = PlaceholderInfo("下属单位", "下属单位", "供应商归属")
_PROVINCE = PlaceholderInfo("注册省份", "供应商注册省份", "供应商归属")
_AREA = PlaceholderInfo("注册地区", "供应商注册地区", "供应商归属")
_MEMBER = PlaceholderInfo("会员状态", "会员/非会员", "供应商归属")
# ── A 类 · 缴费历史 ──
_HIST_FEE_CNT = PlaceholderInfo("历史平台使用费订单数", "历史平台使用费订单数", "缴费历史")
_LAST_PAY_DUR = PlaceholderInfo("上次缴费历时_天", "上次缴费历时（天）", "缴费历史")
_AVG_PAY_DUR = PlaceholderInfo("历史缴费平均历时_天", "历史缴费平均历时（天）", "缴费历史")
# ── B 类 · 活跃度与支付 ──
_FWSC_PAY_AMT = PlaceholderInfo("服务市场历史支付金额", "服务市场历史支付金额（元）", "活跃度")
_SIGNUP_CNT = PlaceholderInfo("历史报名次数", "历史报名次数", "活跃度")
_BIDDING_CNT = PlaceholderInfo("历史投标次数", "历史投标次数", "活跃度")
_WIN_CNT = PlaceholderInfo("历史中标次数", "历史中标次数", "活跃度")
_WIN_RATE = PlaceholderInfo("历史中标率", "供应商历史中标率", "活跃度")
_ACTIVE_90D = PlaceholderInfo("近90天投标活跃度", "近90天投标活跃度", "活跃度")
_FIRST_WIN_INT = PlaceholderInfo("首次中标距本次间隔_天", "首次中标距本次间隔（天）", "活跃度")
_MEMBER_PURCH = PlaceholderInfo("中标前购买会员次数", "中标前购买会员次数", "活跃度")
# ── C 类 · 资质与标签 ──
_REGISTER_FUND = PlaceholderInfo("注册资金", "注册资金（元）", "资质标签")
_REGISTER_INT = PlaceholderInfo("注册时间距中标间隔_天", "注册时间距中标间隔（天）", "资质标签")
_IN_DATE_INT = PlaceholderInfo("平台入驻时间距中标间隔_天", "平台入驻时间距中标间隔（天）", "资质标签")
_ENTRY_INT = PlaceholderInfo("最早入库时间距中标间隔_天", "最早入库时间距中标间隔（天）", "资质标签")
_SUPPLIER_CAT = PlaceholderInfo("供应商品类", "供应商品类", "资质标签")
_ADS_WIN_RATE = PlaceholderInfo("标签表历史中标率", "标签表历史中标率", "资质标签")
_HIGH_QUALITY = PlaceholderInfo("股份优质评级次数", "股份优质评级次数", "资质标签")
_COOP_ORG = PlaceholderInfo("合作单位数量", "合作单位数量", "资质标签")
_TOTAL_PERF = PlaceholderInfo("累计履约项目数", "累计履约项目数", "资质标签")

_REGISTRY: tuple[PlaceholderInfo, ...] = (
    # 基础
    _SUPPLIER, _SUPPLIER_NO, _ORDER_NO, _ORDER_NO_CN, _BIZ_NO,
    # 标的
    _SUBJECT, _ESTIMATE, _TENDER_TYPE, _PURCHASE_TYPE, _BID_CATEGORY,
    _CONTRACT_TYPE, _ORDER_GEN_DATE,
    # 催收
    _TIER, _RISK_PROB, _SCENE, _ROUND, _DUE, _AGE_BUCKET, _AGE_DAYS,
    # 供应商归属
    _BUREAU, _SUBSIDIARY, _PROVINCE, _AREA, _MEMBER,
    # A 类 缴费历史
    _HIST_FEE_CNT, _LAST_PAY_DUR, _AVG_PAY_DUR,
    # B 类 活跃度
    _FWSC_PAY_AMT, _SIGNUP_CNT, _BIDDING_CNT, _WIN_CNT, _WIN_RATE,
    _ACTIVE_90D, _FIRST_WIN_INT, _MEMBER_PURCH,
    # C 类 资质标签
    _REGISTER_FUND, _REGISTER_INT, _IN_DATE_INT, _ENTRY_INT,
    _SUPPLIER_CAT, _ADS_WIN_RATE, _HIGH_QUALITY, _COOP_ORG, _TOTAL_PERF,
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

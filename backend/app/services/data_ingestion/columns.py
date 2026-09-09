"""CSV 列名 → 模型属性映射常量。

37 列表头与 Order/OrderFeature 模型属性的精确对应。
是 data_ingestion 解析的唯一事实来源，列映射集中管理便于维护。
"""

from __future__ import annotations

# 37 列表头（与示例文件 平台使用费特征查询_*.csv 一致）
EXPECTED_COLUMNS: tuple[str, ...] = (
    "供应商编号",
    "供应商名称",
    "招标编号",
    "服务费订单号",
    "招标类型",
    "采购类型",
    "中标日期",
    "实际支付时长_天",
    "标签_30天是否欠费",
    "标签_90天是否欠费",
    "标签_180天是否欠费",
    "标签_365天是否欠费",
    "历史平台使用费订单数",
    "上次缴费历时_天",
    "历史缴费平均历时_天",
    "服务市场历史支付金额",
    "历史报名次数",
    "历史投标次数",
    "历史中标次数",
    "历史中标率",
    "近90天投标活跃度",
    "首次中标距本次间隔_天",
    "中标时是否会员",
    "中标前购买会员次数",
    "注册资金",
    "注册地区",
    "注册时间距中标间隔_天",
    "平台入驻时间距中标间隔_天",
    "最早入库时间距中标间隔_天",
    "供应商品类",
    "标签表历史中标率",
    "股份优质评级次数",
    "合作单位数量",
    "累计履约项目数",
    "中标月份",
    "是否月末",
    "是否季末",
)

# 必填列（缺失即报 400，缺失到这些列无法建订单）
REQUIRED_COLUMNS: tuple[str, ...] = (
    "供应商编号",
    "供应商名称",
    "招标编号",
    "服务费订单号",
)

# CSV 列名 → Order 模型属性（标识 + 状态字段）
ORDER_FIELD_MAP: dict[str, str] = {
    "供应商编号": "supplier_no",
    "供应商名称": "supplier_name",
    "招标编号": "biz_no",
    "服务费订单号": "service_fee_order_no",
    "招标类型": "tender_type_desc",
    "采购类型": "purchase_type_desc",
    "中标日期": "win_bid_date",
    "注册地区": "register_area",
}

# CSV 列名 → OrderFeature 模型属性（37 列中的非标识特征字段）
FEATURE_FIELD_MAP: dict[str, str] = {
    "实际支付时长_天": "actual_pay_duration_days",
    "标签_30天是否欠费": "label_30",
    "标签_90天是否欠费": "label_90",
    "标签_180天是否欠费": "label_180",
    "标签_365天是否欠费": "label_365",
    "历史平台使用费订单数": "history_fee_order_count",
    "上次缴费历时_天": "last_pay_duration_days",
    "历史缴费平均历时_天": "avg_pay_duration_days",
    "服务市场历史支付金额": "fwsc_history_pay_amount",
    "历史报名次数": "signup_count",
    "历史投标次数": "bidding_count",
    "历史中标次数": "win_count",
    "历史中标率": "win_rate",
    "近90天投标活跃度": "active_90d",
    "首次中标距本次间隔_天": "first_win_interval_days",
    "中标时是否会员": "is_member_at_win",
    "中标前购买会员次数": "member_purchase_count_before_win",
    "注册资金": "register_fund",
    "注册时间距中标间隔_天": "register_interval_days",
    "平台入驻时间距中标间隔_天": "in_date_interval_days",
    "最早入库时间距中标间隔_天": "entry_interval_days",
    "供应商品类": "supplier_categories",
    "标签表历史中标率": "ads_win_rate",
    "股份优质评级次数": "high_quality_cnt",
    "合作单位数量": "cooperate_org_num",
    "累计履约项目数": "total_perform_project_num",
}

# 不入库的结构性列 → 存入 extra_features JSON（中标月份/是否月末/是否季末）
EXTRA_FEATURE_COLUMNS: tuple[str, ...] = (
    "中标月份",
    "是否月末",
    "是否季末",
)

# 各特征列的目标 Python 类型，用于空字符串→NULL 与类型转换
_INT_FIELDS: frozenset[str] = frozenset(
    {
        "actual_pay_duration_days",
        "label_30",
        "label_90",
        "label_180",
        "label_365",
        "history_fee_order_count",
        "last_pay_duration_days",
        "signup_count",
        "bidding_count",
        "win_count",
        "active_90d",
        "first_win_interval_days",
        "member_purchase_count_before_win",
        "register_interval_days",
        "in_date_interval_days",
        "entry_interval_days",
        "high_quality_cnt",
        "cooperate_org_num",
        "total_perform_project_num",
    }
)
_FLOAT_FIELDS: frozenset[str] = frozenset(
    {
        "avg_pay_duration_days",
        "fwsc_history_pay_amount",
        "win_rate",
        "ads_win_rate",
    }
)
_BIGINT_FIELDS: frozenset[str] = frozenset({"register_fund"})
_BOOL_FIELDS: frozenset[str] = frozenset({"is_member_at_win"})


def _is_int_field(attr: str) -> bool:
    return attr in _INT_FIELDS


def _is_float_field(attr: str) -> bool:
    return attr in _FLOAT_FIELDS


def _is_bigint_field(attr: str) -> bool:
    return attr in _BIGINT_FIELDS


def _is_bool_field(attr: str) -> bool:
    return attr in _BOOL_FIELDS

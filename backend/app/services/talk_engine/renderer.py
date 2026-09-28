"""话术变量占位符填充（talk-001 renderer，talk-003 扩展占位符集）。

占位符注册表见 placeholders.py（固定模板与 AI 模板共享）。本模块负责把注册的
占位符替换为实际值，并保证渲染后无残留花括号。

占位符覆盖 Order + OrderFeature 全部业务字段（标识/标的/风险/催收/特征），
key 沿用 CSV 业务列名（中文为主）。金额/比率做友好格式化，缺失值为空串。
"""

from __future__ import annotations

from datetime import date

from app.models.order import Order, OrderFeature
from app.models.task import Task
from app.services.talk_engine.matcher import map_age_bucket


def _fmt_money(amount) -> str:
    """金额格式化：None → 空；否则去掉末尾 .00。"""
    if amount is None:
        return ""
    try:
        f = float(amount)
        return str(int(f)) if f == int(f) else f"{f:.2f}"
    except (TypeError, ValueError):
        return str(amount)


def _fmt_rate(rate, *, as_percent: bool = False) -> str:
    """比率格式化：None → 空。as_percent=True 时乘 100 显示百分号。"""
    if rate is None:
        return ""
    try:
        f = float(rate)
        return f"{f:.2%}" if as_percent else f"{f:.4f}"
    except (TypeError, ValueError):
        return str(rate)


def _fmt_int(v) -> str:
    """整数格式化：None → 空。"""
    if v is None:
        return ""
    try:
        return str(int(v))
    except (TypeError, ValueError):
        return str(v)


def _fmt_date(d) -> str:
    """日期格式化：None → 空；date/datetime → isoformat 日期部分。"""
    if d is None:
        return ""
    iso = getattr(d, "isoformat", lambda: str(d))()
    return iso.split("T")[0] if "T" in iso else iso


def _round_num(scene: str) -> str:
    """从 ROUND_N 提取轮次序号 N（如 ROUND_2 → 2；非 ROUND_N 返回原值）。"""
    if scene and scene.startswith("ROUND_"):
        return scene.removeprefix("ROUND_")
    return scene or ""


def build_values(
    task: Task,
    order: Order | None,
    feature: OrderFeature | None,
    *,
    today: date | None = None,
) -> dict[str, str]:
    """构造占位符 → 实际值字典（注册表所有占位符，缺失值为空串）。

    Args:
        today: 账龄基准日，默认 date.today()
    """
    today = today or date.today()
    o = order
    f = feature
    is_member = bool(f and f.is_member_at_win)

    # 账龄（天）与账龄段
    age_days = 0
    if o and o.win_bid_date:
        age_days = max(0, (today - o.win_bid_date).days)

    return {
        # ── 基础 ──
        "供应商名称": o.supplier_name if o else "",
        "供应商编号": o.supplier_no if o else "",
        "service_fee_order_no": o.service_fee_order_no if o else "",
        "订单号": o.service_fee_order_no if o else "",
        "业务编号": o.biz_no if o else "",
        # ── 标的 ──
        "标的名称": o.subject_name if o else "",
        "概算金额": _fmt_money(o.subject_estimate_amount if o else None),
        "招标方式": o.tender_type_desc if o else "",
        "采购方式": o.purchase_type_desc if o else "",
        "中标品类": o.bid_category if o else "",
        "合同类型": o.contract_type if o else "",
        "订单生成日期": _fmt_date(o.order_generated_date if o else None),
        # ── 催收 ──
        "风险档": task.risk_tier,
        "风险概率": _fmt_int(o.risk_prob if o else None),
        "场景": task.scene,
        "轮次": _round_num(task.scene),
        "应催日": _fmt_date(task.due_date),
        "账龄段": map_age_bucket(age_days),
        "账龄天数": str(age_days),
        # ── 供应商归属/注册 ──
        "工程局单位": o.engineering_bureau if o else "",
        "下属单位": o.subsidiary if o else "",
        "注册省份": o.register_province if o else "",
        "注册地区": o.register_area if o else "",
        "会员状态": "会员" if is_member else "非会员",
        # ── A 类 缴费历史 ──
        "历史平台使用费订单数": _fmt_int(f.history_fee_order_count if f else None),
        "上次缴费历时_天": _fmt_int(f.last_pay_duration_days if f else None),
        "历史缴费平均历时_天": _fmt_int(f.avg_pay_duration_days if f else None),
        # ── B 类 活跃度与支付 ──
        "服务市场历史支付金额": _fmt_money(f.fwsc_history_pay_amount if f else None),
        "历史报名次数": _fmt_int(f.signup_count if f else None),
        "历史投标次数": _fmt_int(f.bidding_count if f else None),
        "历史中标次数": _fmt_int(f.win_count if f else None),
        "历史中标率": _fmt_rate(f.win_rate if f else None, as_percent=True),
        "近90天投标活跃度": _fmt_int(f.active_90d if f else None),
        "首次中标距本次间隔_天": _fmt_int(f.first_win_interval_days if f else None),
        "中标前购买会员次数": _fmt_int(f.member_purchase_count_before_win if f else None),
        # ── C 类 资质与标签 ──
        "注册资金": _fmt_money(f.register_fund if f else None),
        "注册时间距中标间隔_天": _fmt_int(f.register_interval_days if f else None),
        "平台入驻时间距中标间隔_天": _fmt_int(f.in_date_interval_days if f else None),
        "最早入库时间距中标间隔_天": _fmt_int(f.entry_interval_days if f else None),
        "供应商品类": f.supplier_categories if f else "",
        "标签表历史中标率": _fmt_rate(f.ads_win_rate if f else None, as_percent=True),
        "股份优质评级次数": _fmt_int(f.high_quality_cnt if f else None),
        "合作单位数量": _fmt_int(f.cooperate_org_num if f else None),
        "累计履约项目数": _fmt_int(f.total_perform_project_num if f else None),
    }


def render(
    content: str,
    *,
    task: Task,
    order: Order | None,
    feature: OrderFeature | None = None,
    today: date | None = None,
) -> str:
    """把模板内容里的 {占位符} 替换为实际值。

    渲染后若残留 { 或 }（未知占位符），保留原样不替换——但调用方应在保存模板时
    先 validate_placeholders 校验，保证不出现残留（D4 安全网）。
    """
    values = build_values(task, order, feature, today=today)
    out = content
    for key, val in values.items():
        out = out.replace("{" + key + "}", str(val))
    return out


__all__ = ["build_values", "render"]

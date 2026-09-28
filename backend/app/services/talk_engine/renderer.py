"""话术变量占位符填充（talk-001 renderer，talk-003 扩展占位符集）。

占位符注册表见 placeholders.py（固定模板与 AI 模板共享）。本模块负责把注册的
占位符替换为实际值，并保证渲染后无残留花括号。

支持占位符（注册表）：
    {供应商名称} {service_fee_order_no} {订单号} {风险档} {场景} {应催日} {会员状态}
    {标的名称} {概算金额} {历史中标率} {账龄段} {账龄天数}
    {工程局单位} {下属单位} {注册省份} {轮次}
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
    is_member = bool(feature and feature.is_member_at_win)

    # 账龄（天）与账龄段
    age_days = 0
    if order and order.win_bid_date:
        age_days = max(0, (today - order.win_bid_date).days)

    return {
        "供应商名称": order.supplier_name if order else "",
        "service_fee_order_no": order.service_fee_order_no if order else "",
        "订单号": order.service_fee_order_no if order else "",
        "标的名称": order.subject_name if order else "",
        "概算金额": _fmt_money(order.subject_estimate_amount if order else None),
        "历史中标率": (
            f"{float(feature.win_rate):.2%}"
            if feature and feature.win_rate is not None
            else ""
        ),
        "账龄段": map_age_bucket(age_days),
        "账龄天数": str(age_days),
        "工程局单位": order.engineering_bureau if order else "",
        "下属单位": order.subsidiary if order else "",
        "注册省份": order.register_province if order else "",
        "会员状态": "会员" if is_member else "非会员",
        "风险档": task.risk_tier,
        "场景": task.scene,
        "轮次": _round_num(task.scene),
        "应催日": task.due_date.isoformat() if task.due_date else "",
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

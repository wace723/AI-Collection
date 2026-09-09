"""话术变量占位符填充（talk-001 renderer）。

支持占位符（docs/03 TC-TALK-03）：
    {供应商名称} {service_fee_order_no} {订单号} {风险档} {场景} {应催日} {会员状态}
模板只用上述变量即可保证渲染后无残留。
"""

from __future__ import annotations

from app.models.order import Order, OrderFeature
from app.models.task import Task


def render(
    content: str,
    *,
    task: Task,
    order: Order | None,
    feature: OrderFeature | None = None,
) -> str:
    """把模板内容里的 {占位符} 替换为实际值。"""
    values: dict[str, str] = {
        "供应商名称": order.supplier_name if order else "",
        "service_fee_order_no": order.service_fee_order_no if order else "",
        "订单号": order.service_fee_order_no if order else "",
        "风险档": task.risk_tier,
        "场景": task.scene,
        "应催日": task.due_date.isoformat() if task.due_date else "",
        "会员状态": "会员" if (feature and feature.is_member_at_win) else "非会员",
    }
    out = content
    for key, val in values.items():
        out = out.replace("{" + key + "}", str(val))
    return out


__all__ = ["render"]

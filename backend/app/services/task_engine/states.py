"""催收状态与回填结果枚举常量（data-003 催收状态机）。

集中定义避免散落各处字面量。所有模块统一引用此处常量。
"""

from __future__ import annotations

# Order.collection_state 催收状态机四值
NO_NEED = "NO_NEED"  # 无需催收：未到首轮催收时点
PENDING_COLLECTION = "PENDING_COLLECTION"  # 待催收：已到当轮时点尚未接通
COLLECTED = "COLLECTED"  # 已催收：当轮已接通，等下一轮时点
FINALIZED = "FINALIZED"  # 终态：轮次耗尽或已支付停催

COLLECTION_STATES: tuple[str, ...] = (
    NO_NEED,
    PENDING_COLLECTION,
    COLLECTED,
    FINALIZED,
)

# 跑批需推进的活跃态（到达下一轮时点时推进）
ADVANCEABLE_STATES: tuple[str, ...] = (NO_NEED, COLLECTED)

# Task.result 回填结果两分类（BREAKING：替代旧 PAID/PROMISE/DISPUTE/LOST_CONTACT/OTHER）
UNREACHED = "UNREACHED"  # 未接通：该轮仍待催收，同日可反复重试
REACHED = "REACHED"  # 已接通：填自由文本反馈，该轮已催收

RESULT_VALUES: tuple[str, ...] = (UNREACHED, REACHED)

# Task.status 任务状态
PENDING_ASSIGN = "PENDING_ASSIGN"
IN_PROGRESS = "IN_PROGRESS"
DONE = "DONE"
CANCELLED = "CANCELLED"

TERMINAL_STATUSES: tuple[str, ...] = (DONE, CANCELLED)


__all__ = [
    "NO_NEED",
    "PENDING_COLLECTION",
    "COLLECTED",
    "FINALIZED",
    "COLLECTION_STATES",
    "ADVANCEABLE_STATES",
    "UNREACHED",
    "REACHED",
    "RESULT_VALUES",
    "PENDING_ASSIGN",
    "IN_PROGRESS",
    "DONE",
    "CANCELLED",
    "TERMINAL_STATUSES",
]

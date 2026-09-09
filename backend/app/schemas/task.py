"""task-001 催收任务生成相关 schema。"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel


class BatchRunOut(BaseModel):
    """一次跑批（生成阶段）的结果摘要。"""

    batch_id: str
    today: date
    scanned: int
    generated: int
    idempotent_skipped: int
    by_tier: dict[str, int]


class BatchStatusOut(BaseModel):
    """批次任务聚合状态（供跑批状态查询）。"""

    batch_id: str
    total: int
    by_status: dict[str, int]
    by_tier: dict[str, int]


__all__ = ["BatchRunOut", "BatchStatusOut"]

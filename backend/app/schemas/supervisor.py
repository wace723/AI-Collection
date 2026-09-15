"""主管视图 schema（supervisor 增强需求）。"""

from __future__ import annotations

from pydantic import BaseModel


class StaffPerformanceOut(BaseModel):
    """催收员绩效输出。"""

    id: int
    username: str
    display_name: str
    role: str
    is_active: bool
    pending_count: int
    in_progress_count: int
    done_count: int
    paid_count: int
    paid_rate: float


__all__ = ["StaffPerformanceOut"]

"""话术覆盖度矩阵与联动校验（talk-003 D6）。

纯函数模块：不依赖 risk_engine / talk_engine service 的可变状态，两边都可调用，
避免 risk_engine ↔ talk_engine 互相 import 成环。

- compute_coverage: 按当前 active risk_config snapshot 展开 [档×轮] 矩阵，
  每格标记 FIXED / AI_PROMPT 是否已配置（查 talk_templates）。
- diff_coverage: 对比新旧 snapshot 的轮次结构，输出新增/删除轮次格子 + 新 snap 缺口。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.models.talk import TalkTemplate
from app.services.risk_engine.config_service import ConfigSnapshot


@dataclass(frozen=True)
class CoverageCell:
    """覆盖度矩阵一格：(风险档, 轮次) 的 FIXED/AI_PROMPT 配置状态。"""

    risk_tier: str
    scene: str  # ROUND_N
    day_offset: int
    fixed_configured: bool
    ai_prompt_configured: bool


@dataclass(frozen=True)
class CoverageMatrix:
    """覆盖度矩阵：按档分组的格子列表。"""

    cells: list[CoverageCell] = field(default_factory=list)

    @property
    def missing_cells(self) -> list[CoverageCell]:
        """缺口格（FIXED 未配——AI_PROMPT 可选增强，缺失不算硬缺口）。"""
        return [c for c in self.cells if not c.fixed_configured]


@dataclass(frozen=True)
class CoverageHint:
    """风险档配置变更的话术覆盖提示（不阻断保存）。"""

    added_rounds: list[tuple[str, str]] = field(default_factory=list)  # (tier, scene) 新增轮次
    deleted_rounds: list[tuple[str, str]] = field(default_factory=list)  # (tier, scene) 删除轮次
    missing_cells: list[CoverageCell] = field(default_factory=list)  # 新 snap 缺口格

    @property
    def has_hint(self) -> bool:
        """是否有变更提示（仅轮次结构变更算，既有缺口不算本次变更提示）。"""
        return bool(self.added_rounds or self.deleted_rounds)


def _scheduled_rounds(snap: ConfigSnapshot) -> set[tuple[str, str]]:
    """提取 snapshot 中所有 (risk_tier, scene) 轮次（仅 is_active schedules）。"""
    return {
        (s.risk_tier, s.scene)
        for s in snap.schedules
        if s.is_active
    }


def _configured_keys(
    db: Session, risk_tier: str, scene: str
) -> tuple[bool, bool]:
    """查某 (档, 轮) 是否已配 FIXED / AI_PROMPT 模板。"""
    templates = (
        db.query(TalkTemplate)
        .filter(
            TalkTemplate.is_active.is_(True),
            TalkTemplate.risk_tier == risk_tier,
            TalkTemplate.scene == scene,
        )
        .all()
    )
    types = {t.template_type for t in templates}
    return ("FIXED" in types, "AI_PROMPT" in types)


def compute_coverage(db: Session, snap: ConfigSnapshot) -> CoverageMatrix:
    """按 active risk_config snapshot 展开覆盖度矩阵。

    仅含 is_active schedules，按 (档业务序, seq) 排序。
    """
    ordered = sorted(
        [s for s in snap.schedules if s.is_active],
        key=lambda s: (_tier_order(s.risk_tier), s.seq),
    )
    cells: list[CoverageCell] = []
    for s in ordered:
        fixed, ai = _configured_keys(db, s.risk_tier, s.scene)
        cells.append(
            CoverageCell(
                risk_tier=s.risk_tier,
                scene=s.scene,
                day_offset=s.day_offset,
                fixed_configured=fixed,
                ai_prompt_configured=ai,
            )
        )
    return CoverageMatrix(cells=cells)


def diff_coverage(
    db: Session,
    old_snap: ConfigSnapshot | None,
    new_snap: ConfigSnapshot,
) -> CoverageHint:
    """对比新旧 snapshot 轮次结构 + 新 snap 缺口。

    Args:
        old_snap: 变更前 snapshot（首次配置时为 None）
        new_snap: 变更后 snapshot
    Returns:
        CoverageHint（added/deleted 轮次 + 新 snap 缺口）
    """
    old_rounds = _scheduled_rounds(old_snap) if old_snap else set()
    new_rounds = _scheduled_rounds(new_snap)

    added = sorted(new_rounds - old_rounds, key=lambda r: (_tier_order(r[0]), r[1]))
    deleted = sorted(old_rounds - new_rounds, key=lambda r: (_tier_order(r[0]), r[1]))

    matrix = compute_coverage(db, new_snap)
    return CoverageHint(
        added_rounds=added,
        deleted_rounds=deleted,
        missing_cells=matrix.missing_cells,
    )


def _tier_order(tier: str) -> int:
    """风险档业务序（HIGH<MEDIUM<LOW）。"""
    return {"HIGH": 1, "MEDIUM": 2, "LOW": 3}.get(tier, 9)


def hint_to_dict(hint: CoverageHint) -> dict:
    """CoverageHint → 可序列化 dict（供 API 响应）。"""
    return {
        "added_rounds": [{"risk_tier": t, "scene": s} for t, s in hint.added_rounds],
        "deleted_rounds": [{"risk_tier": t, "scene": s} for t, s in hint.deleted_rounds],
        "missing_cells": [
            {
                "risk_tier": c.risk_tier,
                "scene": c.scene,
                "fixed_configured": c.fixed_configured,
                "ai_prompt_configured": c.ai_prompt_configured,
            }
            for c in hint.missing_cells
        ],
    }


__all__ = [
    "CoverageCell",
    "CoverageMatrix",
    "CoverageHint",
    "compute_coverage",
    "diff_coverage",
    "hint_to_dict",
]

"""风险档配置服务（版本化 + 回滚）。

设计（见 plan shimmering-percolating-charm.md）：
- 更新配置 = 创建新版本（不可变：不原地改旧记录）
- 回滚 = 方案 B：把目标历史版本的阈值+schedules 复制为新版本，
  旧记录永不被改。审计链完整，与 update 统一一条代码路径。
- is_active 唯一性：同事务内先 _deactivate_all 全表置 False，再 insert 新版本 True。
- version 由服务层自算（max+1），不接受外部传入，杜绝同 version 冲突。

risk-001 的 tier_mapper.get_active_thresholds 查 is_active=True order by version desc，
本服务插入 active 配置后其自动命中，无需改动 risk-001。
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.risk import CollectionSchedule, RiskConfig
from app.schemas.config import RiskConfigUpdateIn, ScheduleIn

# 默认催收时点（docs/02 §3.2.4）：
# HIGH → 7/15/30 天（FIRST/SECOND/THIRD），MEDIUM → 30 天（FIRST），LOW → 90 天（FIRST）
DEFAULT_SCHEDULES: list[ScheduleIn] = [
    ScheduleIn(risk_tier="HIGH", day_offset=7, scene="FIRST", seq=1),
    ScheduleIn(risk_tier="HIGH", day_offset=15, scene="SECOND", seq=2),
    ScheduleIn(risk_tier="HIGH", day_offset=30, scene="THIRD", seq=3),
    ScheduleIn(risk_tier="MEDIUM", day_offset=30, scene="FIRST", seq=1),
    ScheduleIn(risk_tier="LOW", day_offset=90, scene="FIRST", seq=1),
]


class ConfigNotFoundError(ValueError):
    """目标配置版本不存在。"""


class AlreadyActiveError(ValueError):
    """目标版本已是当前生效版本，无需回滚。"""


@dataclass(frozen=True)
class ConfigSnapshot:
    """配置快照（不可变）：RiskConfig + 关联 schedules。"""

    config: RiskConfig
    schedules: list[CollectionSchedule]


# 风险档业务序（字符串序 LOW<MEDIUM<HIGH 不符习惯，用此映射排序）
_TIER_ORDER = {"HIGH": 1, "MEDIUM": 2, "LOW": 3}


def _load_schedules(db: Session, config_id: int) -> list[CollectionSchedule]:
    """加载某配置关联的催收时点（按业务序 HIGH<MEDIUM<LOW + seq 排序）。"""
    rows = (
        db.query(CollectionSchedule)
        .filter(CollectionSchedule.risk_config_id == config_id)
        .all()
    )
    return sorted(rows, key=lambda r: (_TIER_ORDER.get(r.risk_tier, 9), r.seq))


def _snapshot(db: Session, config: RiskConfig) -> ConfigSnapshot:
    return ConfigSnapshot(config=config, schedules=_load_schedules(db, config.id))


def get_current_config(db: Session) -> ConfigSnapshot | None:
    """当前生效配置（is_active=True order by version desc）。无则 None。"""
    config = (
        db.query(RiskConfig)
        .filter(RiskConfig.is_active.is_(True))
        .order_by(RiskConfig.version.desc())
        .first()
    )
    if config is None:
        return None
    return _snapshot(db, config)


def get_config_history(db: Session) -> list[ConfigSnapshot]:
    """全部历史版本（version desc），含 schedules。"""
    configs = (
        db.query(RiskConfig).order_by(RiskConfig.version.desc()).all()
    )
    return [_snapshot(db, c) for c in configs]


def _next_version(db: Session) -> int:
    """max(version)+1，空表返回 1。"""
    max_v = db.query(func.max(RiskConfig.version)).scalar()
    return (max_v or 0) + 1


def _deactivate_all(db: Session) -> None:
    """同事务内把全部 RiskConfig.is_active 置 False（保证 active 唯一）。

    synchronize_session=False 不更新 session 缓存对象，需 expire_all
    让 identity map 失效，否则后续 query 返回缓存的旧 is_active 值。
    """
    db.query(RiskConfig).filter(RiskConfig.is_active.is_(True)).update(
        {RiskConfig.is_active: False}, synchronize_session=False
    )
    db.expire_all()


def _insert_version(
    db: Session,
    *,
    high: float,
    medium: float,
    schedules: list[ScheduleIn],
    created_by: int | None,
) -> ConfigSnapshot:
    """创建新版本 RiskConfig + 关联 schedules（内部统一路径）。

    步骤：_deactivate_all → insert RiskConfig(version=_next, is_active=True)
         → 批量 add CollectionSchedule → commit。
    """
    _deactivate_all(db)
    config = RiskConfig(
        version=_next_version(db),
        high_threshold=high,
        medium_threshold=medium,
        is_active=True,
        created_by=created_by,
    )
    db.add(config)
    db.flush()  # 拿到 config.id

    for s in schedules:
        db.add(
            CollectionSchedule(
                risk_config_id=config.id,
                risk_tier=s.risk_tier.value,
                day_offset=s.day_offset,
                scene=s.scene.value,
                seq=s.seq,
                is_active=True,
            )
        )
    db.commit()
    db.refresh(config)
    return _snapshot(db, config)


def update_config(
    db: Session, payload: RiskConfigUpdateIn, created_by: int | None
) -> ConfigSnapshot:
    """更新配置：创建新版本（阈值 + schedules 来自 payload）。不可变。"""
    return _insert_version(
        db,
        high=payload.high_threshold,
        medium=payload.medium_threshold,
        schedules=list(payload.schedules),
        created_by=created_by,
    )


def rollback_to_version(
    db: Session, version: int, created_by: int | None
) -> ConfigSnapshot:
    """回滚（方案 B）：复制目标历史版本阈值+schedules 为新版本。

    - 目标版本不存在 → ConfigNotFoundError（API 转 404）
    - 目标已是当前 active → AlreadyActiveError（API 转 400）
    """
    target = db.query(RiskConfig).filter(RiskConfig.version == version).first()
    if target is None:
        raise ConfigNotFoundError(f"版本 {version} 不存在")
    if target.is_active:
        raise AlreadyActiveError(f"版本 {version} 已是当前生效版本")

    # 复制目标版本的 schedules 为 ScheduleIn
    target_schedules = _load_schedules(db, target.id)
    schedule_ins = [
        ScheduleIn(
            risk_tier=s.risk_tier,
            day_offset=s.day_offset,
            scene=s.scene,
            seq=s.seq,
        )
        for s in target_schedules
    ]

    return _insert_version(
        db,
        high=float(target.high_threshold),
        medium=float(target.medium_threshold),
        schedules=schedule_ins,
        created_by=created_by,
    )


def seed_default_config(db: Session) -> bool:
    """幂等插入默认配置（v1, 70/30 + 5 schedules）。

    已存在 active 配置则跳过。返回是否新建。
    """
    existing = (
        db.query(RiskConfig).filter(RiskConfig.is_active.is_(True)).first()
    )
    if existing is not None:
        return False
    _insert_version(
        db,
        high=70.0,
        medium=30.0,
        schedules=list(DEFAULT_SCHEDULES),
        created_by=None,
    )
    return True


__all__ = [
    "DEFAULT_SCHEDULES",
    "ConfigSnapshot",
    "ConfigNotFoundError",
    "AlreadyActiveError",
    "get_current_config",
    "get_config_history",
    "update_config",
    "rollback_to_version",
    "seed_default_config",
]

"""跑批调度（APScheduler）。

每日凌晨按 settings.BATCH_RUN_CRON 触发完整跑批：
先重算风险（risk-001 编排器），再生成催收任务（task-001 核心）。
任务分配（task-002）后续在同一 job 追加。
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core.config import settings

logger = logging.getLogger(__name__)

_JOB_ID = "daily_collection_batch"


def run_daily_batch_job() -> dict[str, Any]:
    """每日跑批 job：重算风险 + 生成任务（独立 DB 会话，供线程使用）。

    返回结果 dict 供日志/调度器观察。job 内异常显式记录后继续抛出，
    由 APScheduler 捕获（避免后台线程静默失败）。
    """
    from app.core.database import SessionLocal
    from app.services.task_engine import assign_pending_tasks, run_batch

    db = SessionLocal()
    try:
        today = date.today()
        # 跑批：风险概率由 CSV 导入（data-002），不再 recalc
        result = run_batch(db, today=today, recalc_risk=False)
        assignment = assign_pending_tasks(db)
        payload = {
            "batch_id": result.batch_id,
            "today": result.today.isoformat(),
            "scanned": result.scanned,
            "generated": result.generated,
            "deleted": result.deleted,
            "skipped": result.skipped,
            "by_tier": result.by_tier,
            "assigned": assignment.assigned,
            "assignment_skipped": assignment.skipped,
            "by_assignee": assignment.by_assignee,
        }
        logger.info(
            "每日跑批完成 batch_id=%s generated=%s assigned=%s",
            result.batch_id,
            result.generated,
            assignment.assigned,
        )
        return payload
    except Exception:
        logger.exception("每日跑批失败")
        raise
    finally:
        db.close()


def build_scheduler() -> BackgroundScheduler:
    """构建并返回调度器（未 start；由应用 lifespan 启动/关闭）。"""
    scheduler = BackgroundScheduler(daemon=True)
    scheduler.add_job(
        run_daily_batch_job,
        trigger=CronTrigger.from_crontab(settings.BATCH_RUN_CRON),
        id=_JOB_ID,
        name="每日催收跑批",
        coalesce=True,  # 错过多次只补跑一次
        max_instances=1,  # 上次未跑完不并发叠加
        misfire_grace_time=3600,
    )
    return scheduler


__all__ = ["build_scheduler", "run_daily_batch_job"]

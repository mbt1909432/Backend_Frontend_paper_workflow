"""APScheduler 封装"""
from __future__ import annotations

from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config.settings import settings
from app.services.crawler_service import MonthlyArxivSyncService
from app.utils.logger import setup_logger


logger = setup_logger("scheduler")


def init_scheduler(sync_service: MonthlyArxivSyncService) -> Optional[AsyncIOScheduler]:
    if not settings.scheduler_enabled:
        logger.info("Scheduler disabled via settings")
        return None

    scheduler = AsyncIOScheduler(timezone=settings.scheduler_timezone)
    trigger = CronTrigger.from_crontab(settings.arxiv_cron, timezone=settings.scheduler_timezone)
    scheduler.add_job(
        sync_service.run_once,
        trigger=trigger,
        max_instances=1,
        misfire_grace_time=3600,
        coalesce=True,
    )
    scheduler.start()
    logger.info("Scheduler started with cron %s (%s)", settings.arxiv_cron, settings.scheduler_timezone)
    return scheduler



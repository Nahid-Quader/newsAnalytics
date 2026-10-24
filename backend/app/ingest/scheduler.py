"""Scheduled collection: one interval job per active source, using its `poll_minutes`."""

from __future__ import annotations

import logging

from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.schedulers.blocking import BlockingScheduler
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.connectors import Connector
from app.core.logging import log_event
from app.db import utcnow
from app.ingest.pipeline import run_source
from app.models import Source

logger = logging.getLogger(__name__)


def build_scheduler(session_factory: sessionmaker[Session], connectors: dict[str, Connector],
                    workers: int = 1) -> BlockingScheduler:
    # One worker by default: SQLite allows a single writer, and politeness matters more than speed.
    scheduler = BlockingScheduler(executors={"default": ThreadPoolExecutor(workers)}, timezone="UTC")
    with session_factory() as session:
        sources = list(session.scalars(select(Source).where(Source.active.is_(True))))
    for src in sources:
        connector = connectors.get(src.connector)
        if connector is None:
            log_event(logger, "no_connector", logging.ERROR, source_id=src.id, connector=src.connector)
            continue
        scheduler.add_job(
            _safe_run, "interval", minutes=src.poll_minutes, args=[session_factory, src.id, connector],
            id=src.id, next_run_time=utcnow(), max_instances=1, coalesce=True, misfire_grace_time=300,
        )
        log_event(logger, "job_scheduled", source_id=src.id, every_minutes=src.poll_minutes)
    return scheduler


def _safe_run(session_factory: sessionmaker[Session], source_id: str, connector: Connector) -> None:
    try:
        run_source(session_factory, source_id, connector)
    except Exception:
        logger.exception("scheduled_run_crashed", extra={"fields": {"source_id": source_id}})

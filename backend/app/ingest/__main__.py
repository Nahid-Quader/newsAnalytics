"""Command-line entry point.

    python -m app.ingest sync-sources          # load config/sources.yaml into the database
    python -m app.ingest run [--source ID ...]  # one collection run (all active sources by default)
    python -m app.ingest schedule               # keep collecting on each source's poll interval
    python -m app.ingest health                 # print per-source health
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict

from sqlalchemy.engine import make_url

from app.connectors import build_connectors
from app.core.config import get_settings
from app.core.http import PoliteHttpClient
from app.core.logging import configure_logging
from app.db import get_session_factory
from app.health import all_source_health
from app.ingest.pipeline import run_all
from app.ingest.scheduler import build_scheduler
from app.sources import load_sources, sync_sources


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.ingest")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("sync-sources")
    run_p = sub.add_parser("run")
    run_p.add_argument("--source", action="append", dest="sources", help="source id (repeatable)")
    sub.add_parser("schedule")
    sub.add_parser("health")
    args = parser.parse_args(argv)

    settings = get_settings()
    configure_logging(settings.log_level, settings.log_json)
    session_factory = get_session_factory()

    if args.command == "sync-sources":
        with session_factory() as session:
            result = sync_sources(session, load_sources(settings.sources_file))
        print(json.dumps(result))
        return 0

    if args.command == "health":
        with session_factory() as session:
            rows = [asdict(h) for h in all_source_health(session)]
        print(json.dumps(rows, ensure_ascii=False, indent=2, default=str))
        return 0

    http = PoliteHttpClient(settings)
    connectors = build_connectors(http)
    try:
        if args.command == "run":
            results = run_all(session_factory, connectors, args.sources)
            print(json.dumps([asdict(r) for r in results], ensure_ascii=False, indent=2, default=str))
            return 1 if any(r.status == "failed" for r in results) else 0
        if args.command == "schedule":
            is_sqlite = make_url(settings.database_url).get_backend_name() == "sqlite"
            scheduler = build_scheduler(session_factory, connectors, workers=1 if is_sqlite else 4)
            try:
                scheduler.start()
            except (KeyboardInterrupt, SystemExit):
                pass
            return 0
    finally:
        http.close()
    return 2


if __name__ == "__main__":
    sys.exit(main())

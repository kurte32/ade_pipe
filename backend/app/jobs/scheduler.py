"""Local scheduler: runs the background jobs on intervals.

In Azure each job is a Container Apps Job triggered by schedule.
"""

from __future__ import annotations

import importlib
import time

import structlog

from app.core.config import get_settings
from app.core.logging import configure_logging

log = structlog.get_logger()
JOBS: dict[str, int] = {
    "promote": 15,
    "outbox": 20,
    "purge": 3600,
    "expire_uploads": 600,
    "idempotency_cleanup": 3600,
}


def run_once(name: str) -> None:
    try:
        mod = importlib.import_module(f"app.jobs.{name}")
    except ModuleNotFoundError:
        log.warning("job_missing", job=name)
        return
    try:
        mod.run()
    except Exception:  # noqa: BLE001
        log.exception("job_failed", job=name)


def main() -> None:
    configure_logging(get_settings().log_level)
    last: dict[str, float] = {k: 0.0 for k in JOBS}
    log.info("scheduler_started", jobs=list(JOBS))
    while True:
        now = time.monotonic()
        for name, interval in JOBS.items():
            if now - last[name] >= interval:
                run_once(name)
                last[name] = time.monotonic()
        time.sleep(5)


if __name__ == "__main__":
    main()

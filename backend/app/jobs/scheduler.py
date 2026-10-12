"""Local scheduler: runs the background jobs on intervals.

In Azure each job is a Container Apps Job triggered by schedule.
"""

from __future__ import annotations

import importlib
import time
import uuid

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
    # Every line of a run carries the job name and a run id (backlog LOG-FIELDS).
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(job_name=name, job_run=uuid.uuid4().hex[:12])
    started = time.perf_counter()
    try:
        mod.run()
        log.info("job_done", duration_ms=round((time.perf_counter() - started) * 1000))
    except Exception:  # noqa: BLE001
        log.exception("job_failed", duration_ms=round((time.perf_counter() - started) * 1000))
    finally:
        structlog.contextvars.clear_contextvars()


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

"""Run one background job once.

python -m app.jobs.run <promote|outbox|purge|expire_uploads|idempotency_cleanup>
"""

from __future__ import annotations

import sys

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.jobs.scheduler import run_once

if __name__ == "__main__":
    configure_logging(get_settings().log_level)
    run_once(sys.argv[1])

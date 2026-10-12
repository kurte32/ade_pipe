"""Per-user request limits (audit IDN-8).

Front Door's WAF limits by client IP, which carrier NAT shares across many phones and which dev has
no Front Door for. These limits are per `oid`, per route family, in process: with several replicas
the effective limit is multiplied by the replica count, which is acceptable for an abuse brake
(not a quota). A limited request answers 429 Problem Details with Retry-After.
"""

from __future__ import annotations

import threading
import time
from collections import deque

from fastapi import Depends

from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.core.security import Claims, get_claims

WINDOW_SECONDS = 60.0


class SlidingWindowLimiter:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._events: dict[str, deque[float]] = {}

    def check(self, key: str, limit: int, now: float | None = None) -> float | None:
        """Record one event for `key`; return seconds to wait when over `limit`, else None."""
        if limit <= 0:
            return None
        t = time.monotonic() if now is None else now
        with self._lock:
            q = self._events.setdefault(key, deque())
            while q and t - q[0] >= WINDOW_SECONDS:
                q.popleft()
            if len(q) >= limit:
                return WINDOW_SECONDS - (t - q[0])
            q.append(t)
            return None

    def reset(self) -> None:
        with self._lock:
            self._events.clear()


limiter = SlidingWindowLimiter()


def rate_limited(bucket: str, setting: str):  # type: ignore[no-untyped-def]
    """Dependency: limit `bucket` for the caller to `settings.<setting>` requests per minute."""

    def checker(
        claims: Claims = Depends(get_claims), settings: Settings = Depends(get_settings)
    ) -> None:
        limit = int(getattr(settings, setting))
        wait = limiter.check(f"{bucket}:{claims.oid}", limit)
        if wait is not None:
            raise AppError(
                429,
                "too-many-requests",
                "Demasiadas peticiones",
                f"Límite de {limit} por minuto para esta operación; espera {int(wait) + 1} s.",
                headers={"Retry-After": str(int(wait) + 1)},
            )

    return checker

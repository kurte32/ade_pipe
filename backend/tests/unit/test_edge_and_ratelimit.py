"""Front Door origin validation (A3) and per-user rate limits (IDN-8)."""

from __future__ import annotations

import uuid

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.core.edge import FrontDoorMiddleware
from app.core.errors import register_error_handlers
from app.core.ratelimit import SlidingWindowLimiter, limiter, rate_limited
from app.core.security import Claims, get_claims


def test_front_door_header_is_required_on_api_paths_only() -> None:
    app = FastAPI()

    @app.get("/api/v1/x")
    def x() -> dict[str, int]:
        return {"ok": 1}

    @app.get("/healthz")
    def h() -> dict[str, int]:
        return {"ok": 1}

    app.add_middleware(FrontDoorMiddleware, front_door_id="fd-123")
    c = TestClient(app)
    assert c.get("/healthz").status_code == 200  # probes come from the platform, not Front Door
    r = c.get("/api/v1/x")
    assert r.status_code == 403 and r.headers["content-type"] == "application/problem+json"
    assert c.get("/api/v1/x", headers={"x-azure-fdid": "other"}).status_code == 403
    assert c.get("/api/v1/x", headers={"x-azure-fdid": "fd-123"}).status_code == 200


def test_sliding_window_limiter_counts_per_key() -> None:
    lim = SlidingWindowLimiter()
    assert lim.check("a", 2, now=0.0) is None
    assert lim.check("a", 2, now=1.0) is None
    wait = lim.check("a", 2, now=2.0)
    assert wait is not None and 57 < wait <= 58
    assert lim.check("b", 2, now=2.0) is None  # another user is unaffected
    assert lim.check("a", 2, now=61.0) is None  # the window slid
    assert lim.check("a", 0, now=61.0) is None  # 0 disables


def test_rate_limited_dependency_answers_429_problem() -> None:
    limiter.reset()
    app = FastAPI()
    register_error_handlers(app)
    claims = Claims(
        oid=uuid.uuid4(), name="x", username="x", roles=("Coordinador",), azp="a", tid="t", raw={}
    )
    app.dependency_overrides[get_claims] = lambda: claims
    app.dependency_overrides[get_settings] = lambda: Settings(  # type: ignore[call-arg]
        auth_tenant_id="t", auth_audience="a", auth_allowed_azp="a", rate_limit_loads_per_minute=2
    )

    @app.post("/load")
    def load(
        _: None = Depends(rate_limited("cargas", "rate_limit_loads_per_minute")),
    ) -> dict[str, int]:
        return {"ok": 1}

    c = TestClient(app)
    assert c.post("/load").status_code == 200
    assert c.post("/load").status_code == 200
    r = c.post("/load")
    assert r.status_code == 429
    assert r.json()["type"].endswith("too-many-requests")
    assert int(r.headers["retry-after"]) >= 1
    limiter.reset()

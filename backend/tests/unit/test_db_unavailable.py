"""A database outage answers 503 Problem Details with Retry-After, not a 500 (RB-11)."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.core.errors import register_error_handlers


def test_operational_error_is_503_problem() -> None:
    app = FastAPI()
    register_error_handlers(app)

    @app.get("/x")
    def x() -> None:
        raise OperationalError(
            "SELECT 1", None, ConnectionError("TCP Provider: connection refused")
        )

    r = TestClient(app, raise_server_exceptions=False).get("/x")
    assert r.status_code == 503
    assert r.headers["content-type"] == "application/problem+json"
    assert r.json()["type"].endswith("service-unavailable")
    assert r.headers["retry-after"] == "10"

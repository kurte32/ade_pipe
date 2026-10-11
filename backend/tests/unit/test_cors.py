"""CORS is off by default and an explicit allowlist when the SPAs live on another origin (INF-2)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import create_app


@pytest.fixture
def make_client(monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    def _make(origins: str) -> TestClient:
        monkeypatch.setenv("CORS_ALLOWED_ORIGINS", origins)
        get_settings.cache_clear()
        return TestClient(create_app())

    yield _make
    get_settings.cache_clear()


def test_no_cors_headers_by_default(make_client) -> None:  # type: ignore[no-untyped-def]
    r = make_client("").options(
        "/api/v1/me",
        headers={"origin": "https://evil.example", "access-control-request-method": "GET"},
    )
    assert "access-control-allow-origin" not in r.headers


def test_allowlisted_origin_gets_cors_headers_and_others_do_not(make_client) -> None:  # type: ignore[no-untyped-def]
    c = make_client("https://swa-pwa.example,https://swa-admin.example/")
    ok = c.options(
        "/api/v1/me",
        headers={"origin": "https://swa-admin.example", "access-control-request-method": "GET"},
    )
    assert ok.status_code == 200
    assert ok.headers["access-control-allow-origin"] == "https://swa-admin.example"
    assert "authorization" in ok.headers["access-control-allow-headers"].lower()
    bad = c.options(
        "/api/v1/me",
        headers={"origin": "https://evil.example", "access-control-request-method": "GET"},
    )
    assert "access-control-allow-origin" not in bad.headers

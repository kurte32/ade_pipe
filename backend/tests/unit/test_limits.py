"""Global request-body limit (audit B-05)."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.core.limits import BodyLimitMiddleware


def _app(limit: int) -> FastAPI:
    app = FastAPI()

    @app.post("/echo")
    async def echo(request: Request) -> dict[str, int]:
        return {"n": len(await request.body())}

    app.add_middleware(BodyLimitMiddleware, limit=limit)
    return app


def test_within_limit_passes() -> None:
    r = TestClient(_app(100)).post("/echo", content=b"x" * 100)
    assert r.status_code == 200 and r.json() == {"n": 100}


def test_chunked_body_over_limit_is_413_problem() -> None:
    """A streamed body with no Content-Length that overflows must still answer 413 Problem
    Details, even when the framework's body parser swallows the overflow (audit IDN-7)."""

    def chunks():  # type: ignore[no-untyped-def]
        for _ in range(5):
            yield b"x" * 40

    r = TestClient(_app(100)).post("/echo", content=chunks())
    assert r.status_code == 413
    assert r.headers["content-type"] == "application/problem+json"
    assert r.json()["type"].endswith("payload-too-large")


def test_declared_length_over_limit_is_413() -> None:
    r = TestClient(_app(100)).post("/echo", content=b"x" * 101)
    assert r.status_code == 413
    assert r.json()["type"].endswith("payload-too-large")


def test_streamed_body_over_limit_is_413() -> None:
    def gen():  # type: ignore[no-untyped-def]
        for _ in range(10):
            yield b"x" * 50

    r = TestClient(_app(100)).post("/echo", content=gen())
    assert r.status_code == 413

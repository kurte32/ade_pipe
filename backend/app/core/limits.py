"""Request-body size limit enforced before the application reads the body (audit B-05)."""

from __future__ import annotations

import json

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.errors import PROBLEM_BASE


class BodyTooLargeError(Exception):
    """Raised from receive() once the streamed body exceeds the limit."""


class BodyLimitMiddleware:
    """Reject bodies over ``limit`` bytes: by Content-Length up front, or while streaming."""

    def __init__(self, app: ASGIApp, limit: int) -> None:
        self.app = app
        self.limit = limit

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        for name, value in scope.get("headers", []):
            if name == b"content-length":
                try:
                    declared = int(value)
                except ValueError:
                    declared = -1
                if declared > self.limit:
                    await self._reject(scope, send)
                    return
                break

        seen = 0
        started = False
        overflow = False

        async def limited_receive() -> Message:
            nonlocal seen, overflow
            message = await receive()
            if message["type"] == "http.request":
                seen += len(message.get("body", b""))
                if seen > self.limit:
                    overflow = True
                    raise BodyTooLargeError
            return message

        async def tracking_send(message: Message) -> None:
            nonlocal started
            # A body parser may swallow BodyTooLargeError and answer 400 on its own (chunked
            # multipart did); the overflow still wins and is reported as 413 (audit IDN-7).
            if overflow:
                if not started:
                    started = True
                    await self._reject(scope, send)
                return
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, tracking_send)
        except BodyTooLargeError:
            if not started:
                started = True
                await self._reject(scope, send)

    async def _reject(self, scope: Scope, send: Send) -> None:
        body = json.dumps(
            {
                "type": PROBLEM_BASE + "payload-too-large",
                "title": "Contenido demasiado grande",
                "status": 413,
                "detail": f"El cuerpo de la petición supera {self.limit} bytes.",
                "instance": scope.get("path", ""),
            }
        ).encode()
        await send(
            {
                "type": "http.response.start",
                "status": 413,
                "headers": [
                    (b"content-type", b"application/problem+json"),
                    (b"content-length", str(len(body)).encode()),
                    (b"connection", b"close"),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})

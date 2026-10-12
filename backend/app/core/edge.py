"""Front Door origin validation (backlog A3).

Front Door adds `X-Azure-FDID: <profile id>` to every request it forwards. Behind a Private Link
origin the network already restricts who can reach the API, but a request that reaches the app
without the header (misconfiguration, a leaked direct hostname, a future public ingress) must be
refused here too, so the restriction does not depend on the network alone.
"""

from __future__ import annotations

import json

from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.errors import PROBLEM_BASE

HEADER = b"x-azure-fdid"


class FrontDoorMiddleware:
    def __init__(self, app: ASGIApp, front_door_id: str, prefix: str = "/api/") -> None:
        self.app = app
        self.expected = front_door_id.encode()
        self.prefix = prefix

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] != "http"
            or not self.expected
            or not scope["path"].startswith(self.prefix)
        ):
            await self.app(scope, receive, send)
            return
        got = next((v for k, v in scope.get("headers", []) if k == HEADER), b"")
        if got != self.expected:
            body = json.dumps(
                {
                    "type": PROBLEM_BASE + "forbidden",
                    "title": "Origen no permitido",
                    "status": 403,
                    "detail": "La petición no llegó a través de Front Door.",
                    "instance": scope.get("path", ""),
                }
            ).encode()
            await send(
                {
                    "type": "http.response.start",
                    "status": 403,
                    "headers": [
                        (b"content-type", b"application/problem+json"),
                        (b"content-length", str(len(body)).encode()),
                    ],
                }
            )
            await send({"type": "http.response.body", "body": body})
            return
        await self.app(scope, receive, send)

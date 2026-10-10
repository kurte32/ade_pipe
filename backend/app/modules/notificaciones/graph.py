"""Notification delivery. Teams activity feed through Microsoft Graph (ADR-007) or a log sink.

The Graph path needs the backend managed identity with the application permission
TeamsActivity.Send and a Teams app (TEAMS_APP_ID) installed for the users. It is not
verifiable without a tenant; the log sink keeps the outbox pipeline real locally.
"""

from __future__ import annotations

from typing import Any, Protocol

import httpx
import structlog

from app.core.config import Settings, get_settings

log = structlog.get_logger()


class Notifier(Protocol):
    def send(self, oid: str, body: dict[str, Any]) -> None: ...


class LogNotifier:
    """NOTIFY_MODE=log. Logs the event without personal data."""

    def send(self, oid: str, body: dict[str, Any]) -> None:
        log.info(
            "notificacion_enviada",
            modo="log",
            tipo=body.get("tipo"),
            sitio_id=body.get("sitio_id"),
            estatus_destino=body.get("estatus_destino"),
        )


class TeamsNotifier:
    """NOTIFY_MODE=graph. Sends a Teams activity feed notification."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        from azure.identity import DefaultAzureCredential

        self._cred = DefaultAzureCredential()

    def _token(self) -> str:
        return str(self._cred.get_token("https://graph.microsoft.com/.default").token)

    def send(self, oid: str, body: dict[str, Any]) -> None:
        if not self.settings.teams_app_id:
            raise RuntimeError("TEAMS_APP_ID no configurado")
        url = f"{self.settings.graph_base_url}/users/{oid}/teamwork/sendActivityNotification"
        payload = {
            "topic": {
                "source": "text",
                "value": str(body.get("sitio_nombre", "Sitio")),
                "webUrl": str(body.get("url", self.settings.app_public_url)),
            },
            "activityType": "devolucionSitio",
            "previewText": {
                "content": (
                    f"El sitio regresó a {body.get('estatus_destino_nombre', '')}: "
                    f"{body.get('motivo_nombre', '')}"
                )
            },
            "templateParameters": [
                {"name": "sitio", "value": str(body.get("sitio_nombre", ""))},
                {"name": "estatus", "value": str(body.get("estatus_destino_nombre", ""))},
                {"name": "motivo", "value": str(body.get("motivo_nombre", ""))},
            ],
        }
        r = httpx.post(
            url,
            json=payload,
            headers={"Authorization": f"Bearer {self._token()}"},
            timeout=15,
        )
        if r.status_code >= 300:
            raise RuntimeError(f"Graph {r.status_code}")
        log.info("notificacion_enviada", modo="graph", sitio_id=body.get("sitio_id"))


def get_notifier(settings: Settings | None = None) -> Notifier:
    s = settings or get_settings()
    if s.notify_mode == "graph":
        return TeamsNotifier(s)
    return LogNotifier()

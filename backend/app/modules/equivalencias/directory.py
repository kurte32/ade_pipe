"""Email to Entra object id resolution (Propuesta B5, ADR-006).

DIRECTORY_MODE=dev resolves against the local dev IdP user list; DIRECTORY_MODE=graph calls
Microsoft Graph with the backend managed identity (User.ReadBasic.All).
"""

from __future__ import annotations

import uuid
from typing import Protocol

import httpx
import structlog

from app.core.config import Settings, get_settings

log = structlog.get_logger()


class Directory(Protocol):
    def resolve(self, email: str) -> tuple[uuid.UUID, str] | None: ...


class DevDirectory:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    def users(self) -> list[dict[str, object]]:
        r = httpx.get(f"{self.base_url}/users", timeout=5)
        r.raise_for_status()
        data: list[dict[str, object]] = r.json()
        return data

    def resolve(self, email: str) -> tuple[uuid.UUID, str] | None:
        wanted = email.strip().lower()
        for u in self.users():
            if str(u.get("email", "")).lower() == wanted:
                return uuid.UUID(str(u["oid"])), str(u.get("name", ""))
        return None


class GraphDirectory:
    """Resolution through Microsoft Graph. Not verifiable without a tenant."""

    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    def _token(self) -> str:
        from azure.identity import DefaultAzureCredential

        return str(DefaultAzureCredential().get_token("https://graph.microsoft.com/.default").token)

    def resolve(self, email: str) -> tuple[uuid.UUID, str] | None:
        safe = httpx.URL(f"{self.base_url}/users/{email.strip()}").raw_path.decode()
        url = f"{self.base_url}{safe[len(httpx.URL(self.base_url).raw_path.decode()) :]}"
        r = httpx.get(
            url,
            params={"$select": "id,displayName,mail,userPrincipalName"},
            headers={"Authorization": f"Bearer {self._token()}"},
            timeout=10,
        )
        if r.status_code == 404:
            return None
        r.raise_for_status()
        body = r.json()
        return uuid.UUID(str(body["id"])), str(body.get("displayName", ""))


def get_directory(settings: Settings | None = None) -> Directory:
    s = settings or get_settings()
    if s.directory_mode == "graph":
        return GraphDirectory(s.graph_base_url)
    return DevDirectory(s.dev_idp_url)

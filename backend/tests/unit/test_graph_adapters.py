"""Graph notifier and directory adapters, exercised without a tenant (audit C8, C9)."""

from __future__ import annotations

import uuid
from typing import Any

import httpx
import pytest

from app.core.config import Settings
from app.jobs.outbox import describe_error
from app.modules.equivalencias import directory
from app.modules.notificaciones import graph


@pytest.fixture
def settings() -> Settings:
    return Settings(  # type: ignore[call-arg]
        teams_app_id="app-123",
        graph_base_url="https://graph.example/v1.0",
        app_public_url="https://pipeline.example",
    )


class _Resp:
    def __init__(self, status: int, body: Any = None) -> None:
        self.status_code = status
        self._body = body

    def json(self) -> Any:
        return self._body

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("boom", request=None, response=None)  # type: ignore[arg-type]


def _notifier(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> graph.TeamsNotifier:
    n = graph.TeamsNotifier.__new__(graph.TeamsNotifier)
    n.settings = settings
    monkeypatch.setattr(n, "_token", lambda: "tok")
    return n


def test_teams_payload_has_no_owner_contact_data(settings, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    sent: dict[str, Any] = {}

    def fake_post(url: str, json: Any, headers: dict[str, str], timeout: int) -> _Resp:
        sent.update(url=url, json=json, headers=headers)
        return _Resp(201)

    monkeypatch.setattr(graph.httpx, "post", fake_post)
    body = {
        "sitio_id": 7,
        "sitio_nombre": "Av. Xalapa 780",
        "estatus_destino_nombre": "Dueño Localizado",
        "motivo_nombre": "Falta documento",
        # fields that must never reach Teams even if present in the outbox body:
        "contacto_nombre": "María López",
        "telefono": "5512345678",
        "correo": "maria@example.com",
    }
    _notifier(settings, monkeypatch).send("oid-1", body)
    assert sent["url"].endswith("/users/oid-1/teamwork/sendActivityNotification")
    assert sent["headers"]["Authorization"] == "Bearer tok"
    flat = repr(sent["json"])
    for secret in ("María López", "5512345678", "maria@example.com"):
        assert secret not in flat


def test_teams_error_status_raises_safe_message(settings, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(graph.httpx, "post", lambda *a, **k: _Resp(403))
    with pytest.raises(RuntimeError) as e:
        _notifier(settings, monkeypatch).send("oid-1", {})
    assert str(e.value) == "Graph 403"
    assert describe_error(e.value) == "RuntimeError: Graph 403"


def test_teams_without_app_id_refuses(settings, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    settings.teams_app_id = ""
    with pytest.raises(RuntimeError, match="TEAMS_APP_ID"):
        _notifier(settings, monkeypatch).send("oid-1", {})


def test_describe_error_drops_unknown_text() -> None:
    assert describe_error(ValueError("https://x?access_token=abc")) == "ValueError"


def test_directory_resolves_and_handles_not_found(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    calls: list[str] = []
    oid = uuid.uuid4()

    def fake_get(url: str, params: Any, headers: Any, timeout: int) -> _Resp:
        calls.append(url)
        if "missing" in url:
            return _Resp(404)
        return _Resp(200, {"id": str(oid), "displayName": "Ana"})

    d = directory.GraphDirectory("https://graph.example/v1.0")
    monkeypatch.setattr(d, "_token", lambda: "tok")
    monkeypatch.setattr(directory.httpx, "get", fake_get)
    assert d.resolve("ana@x.com") == (oid, "Ana")
    assert d.resolve("missing@x.com") is None
    # a crafted address cannot escape the /users/{id} segment (audit A7)
    d.resolve("a/../../me@x.com")
    assert calls[-1] == "https://graph.example/v1.0/users/a%2F..%2F..%2Fme@x.com"


def test_equivalence_email_pattern_rejects_path_characters() -> None:
    import re

    from app.modules.equivalencias.schemas import CORREO_PATTERN

    assert re.fullmatch(CORREO_PATTERN, "ana.lopez@tiendas3b.mx")
    for bad in ("a/../../me@x.com", "../groups/x@x.com", "a%2F@x.com", "a?b@x.com", "a\\b@x.com"):
        assert not re.fullmatch(CORREO_PATTERN, bad), bad

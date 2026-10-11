"""Client address for the audit ledger honours only trusted proxy hops (audit A5)."""

from __future__ import annotations

import pytest
from starlette.requests import Request

from app import deps


def _req(xff: str | None, peer: str = "10.0.0.5") -> Request:
    headers = [(b"x-forwarded-for", xff.encode())] if xff is not None else []
    return Request({"type": "http", "headers": headers, "client": (peer, 1234)})


@pytest.fixture
def hops(monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    def set_hops(n: int) -> None:
        class S:
            trusted_proxy_hops = n

        monkeypatch.setattr(deps, "get_settings", lambda: S())

    return set_hops


def test_no_trusted_proxy_ignores_the_header(hops) -> None:  # type: ignore[no-untyped-def]
    hops(0)
    assert deps.client_ip(_req("203.0.113.9")) == "10.0.0.5"


def test_two_hops_takes_the_entry_front_door_appended(hops) -> None:  # type: ignore[no-untyped-def]
    hops(2)
    # client spoofed 1.1.1.1; Front Door appended the real client, ingress appended Front Door
    assert deps.client_ip(_req("1.1.1.1, 198.51.100.7, 10.1.2.3")) == "198.51.100.7"


def test_too_few_entries_or_garbage_falls_back_to_peer(hops) -> None:  # type: ignore[no-untyped-def]
    hops(2)
    assert deps.client_ip(_req("198.51.100.7")) == "10.0.0.5"
    assert deps.client_ip(_req("not-an-ip, 10.1.2.3")) == "10.0.0.5"

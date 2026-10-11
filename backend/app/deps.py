"""FastAPI dependencies shared by all modules."""

from __future__ import annotations

import ipaddress
from collections.abc import Generator
from typing import Annotated

from fastapi import Depends, Path, Request
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import session_for
from app.core.security import Claims, get_claims
from app.core.storage import BlobStore, get_blob_store

# sitio.id is an INT; anything larger overflowed pyodbc into a 500 (audit API-1).
SitioId = Annotated[int, Path(ge=1, le=2_147_483_647)]


def get_session(claims: Claims = Depends(get_claims)) -> Generator[Session, None, None]:
    """Transactional session with SESSION_CONTEXT (oid, rol) already set. Commits on success."""
    with session_for(claims) as session:
        yield session


def blob_store() -> BlobStore:
    return get_blob_store()


def client_ip(request: Request) -> str | None:
    """Client address for the audit ledger, never trusting what the client itself prepends (A5).

    Each trusted proxy appends the address it received the request from, so with N proxies in
    front of the API the real client is the N-th entry from the right of X-Forwarded-For. Anything
    further left was written by the client and is ignored. With no trusted proxies configured the
    header is ignored and the socket peer is used.
    """
    peer = request.client.host if request.client else None
    hops = get_settings().trusted_proxy_hops
    if hops > 0:
        entries = [e.strip() for e in request.headers.get("x-forwarded-for", "").split(",")]
        entries = [e for e in entries if e]
        if len(entries) >= hops:
            candidate = entries[-hops]
            try:
                ipaddress.ip_address(candidate)
            except ValueError:
                return peer[:45] if peer else None
            return candidate[:45]
    return peer[:45] if peer else None


def idempotency_key(request: Request) -> str | None:
    key = request.headers.get("Idempotency-Key")
    return key.strip() if key else None


def if_match(request: Request) -> str | None:
    v = request.headers.get("If-Match")
    return v.strip().strip('"') if v else None

"""FastAPI dependencies shared by all modules."""

from __future__ import annotations

from collections.abc import Generator

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.core.db import session_for
from app.core.security import Claims, get_claims
from app.core.storage import BlobStore, get_blob_store


def get_session(claims: Claims = Depends(get_claims)) -> Generator[Session, None, None]:
    """Transactional session with SESSION_CONTEXT (oid, rol) already set. Commits on success."""
    with session_for(claims) as session:
        yield session


def blob_store() -> BlobStore:
    return get_blob_store()


def client_ip(request: Request) -> str | None:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()[:45]
    return request.client.host[:45] if request.client else None


def idempotency_key(request: Request) -> str | None:
    key = request.headers.get("Idempotency-Key")
    return key.strip() if key else None


def if_match(request: Request) -> str | None:
    v = request.headers.get("If-Match")
    return v.strip().strip('"') if v else None

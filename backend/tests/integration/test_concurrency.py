"""Optimistic-concurrency regression tests (audit finding B-01).

Two independent sessions load the same site at the same rowversion; the first write wins, and the
second must be rejected by the database (``StaleDataError``) rather than silently overwriting it.
Before the ``version_id_col`` mapper fix, the second write committed too (lost update).
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.orm.exc import StaleDataError

from app.core.clock import to_utc_naive, utcnow
from app.core.db import SYSTEM_OID, session_factory, set_session_context
from app.models import Sitio


def _sistema_session():  # type: ignore[no-untyped-def]
    session = session_factory()()
    set_session_context(session, SYSTEM_OID, "Sistema")
    return session


@pytest.fixture
def one_site(dev_users):  # type: ignore[no-untyped-def]
    """A site owned by ard, created and torn down as Sistema."""
    from app.core.db import system_session
    from tests.conftest import make_sitio

    oid = uuid.UUID(str(dev_users["ard"]["oid"]))
    with system_session() as s:
        site = make_sitio(s, coordinador_oid=oid, usuario_codigo="ard")
        sid = site.id
    yield sid
    with system_session() as s:
        from sqlalchemy import text

        s.execute(text("DELETE FROM sitio WHERE id = :id"), {"id": sid})


def test_concurrent_update_same_rowversion_rejects_the_loser(one_site: int) -> None:
    """Two sessions read the same site; the second commit must raise StaleDataError."""
    s1 = _sistema_session()
    s2 = _sistema_session()
    try:
        a = s1.get(Sitio, one_site)
        b = s2.get(Sitio, one_site)
        assert a is not None and b is not None
        assert bytes(a.rowversion) == bytes(b.rowversion)  # same starting version

        a.actualizado_utc = to_utc_naive(utcnow())
        a.revision_detalle = "primera escritura"
        s1.commit()  # first writer wins; rowversion advances in the DB

        b.actualizado_utc = to_utc_naive(utcnow())
        b.revision_detalle = "segunda escritura (debe perder)"
        with pytest.raises(StaleDataError):
            s2.commit()  # stale rowversion -> zero rows updated -> rejected
    finally:
        s1.close()
        s2.close()


def test_concurrent_same_idempotency_key_returns_stored_response(  # type: ignore[no-untyped-def]
    client, coord_a_headers, two_sites
) -> None:
    """Concurrent replays of one Idempotency-Key all succeed with one identical body (audit B-02).

    Before the fix the losers raced past the lookup, hit the primary key of sitio_contacto, and
    surfaced as an unhandled 500 even though the write had succeeded.
    """
    import threading
    from collections import Counter

    key = f"b02-{uuid.uuid4()}"
    headers = {**coord_a_headers, "Idempotency-Key": key}
    body = {"nombre": "Concurrencia B02", "telefono": "55 1234 5678", "correo": None}
    n = 6
    barrier = threading.Barrier(n)
    results: list[tuple[int, dict]] = []  # type: ignore[type-arg]
    lock = threading.Lock()

    def fire() -> None:
        barrier.wait()
        r = client.put(f"/api/v1/sitios/{two_sites['a']}/contacto", json=body, headers=headers)
        with lock:
            results.append((r.status_code, r.json()))

    threads = [threading.Thread(target=fire) for _ in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    codes = Counter(code for code, _ in results)
    assert codes == {200: n}, codes
    bodies = {json_key(b) for _, b in results}
    assert len(bodies) == 1, "every replay must return the same stored response"


def json_key(body: dict) -> str:  # type: ignore[type-arg]
    import json

    return json.dumps(body, sort_keys=True)

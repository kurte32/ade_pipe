"""HU-01, HU-02 and the three-layer isolation (API, service, database with pooled connections)."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from app.core.db import (
    clear_session_context,
    get_engine,
    session_factory,
    session_for,
    set_session_context,
)
from app.core.security import Claims
from tests.conftest import PWA_CLIENT_ID, auth, mint

pytestmark = pytest.mark.integration


def test_me_without_token(client) -> None:  # type: ignore[no-untyped-def]
    r = client.get("/api/v1/me")
    assert r.status_code == 401
    assert r.headers["content-type"].startswith("application/problem+json")
    assert r.json()["type"].endswith("/unauthorized")
    assert r.headers.get("X-Correlation-Id")


def test_me_garbage_token(client) -> None:  # type: ignore[no-untyped-def]
    assert (
        client.get("/api/v1/me", headers={"Authorization": "Bearer abc.def.ghi"}).status_code == 401
    )


def test_me_coordinator(client, coord_a_headers) -> None:  # type: ignore[no-untyped-def]
    r = client.get("/api/v1/me", headers=coord_a_headers)
    assert r.status_code == 200
    assert r.json()["roles"] == ["Coordinador"]
    assert r.json()["name"]


def test_me_user_without_role_is_403(client) -> None:  # type: ignore[no-untyped-def]
    assert client.get("/api/v1/me", headers=auth("xna")).status_code == 403


def test_token_without_delegated_scope_is_401(client) -> None:  # type: ignore[no-untyped-def]
    t = mint("ard", PWA_CLIENT_ID, scope="other")
    assert client.get("/api/v1/me", headers={"Authorization": f"Bearer {t}"}).status_code == 401


def test_token_from_unknown_client_is_401(client) -> None:  # type: ignore[no-untyped-def]
    t = mint("ard", "99999999-9999-4999-8999-999999999999")
    assert client.get("/api/v1/me", headers={"Authorization": f"Bearer {t}"}).status_code == 401


def test_admin_route_requires_admin(client, coord_a_headers, admin_headers) -> None:  # type: ignore[no-untyped-def]
    # /api/v1/sitios/resumen is open to both; an admin-only route is exercised in the cargas tests.
    assert client.get("/api/v1/sitios/resumen", headers=coord_a_headers).status_code == 200
    assert client.get("/api/v1/sitios/resumen", headers=admin_headers).status_code == 200


# ---------------------------------------------------------------------------------------------
# Layer 1 and 2: API + service
# ---------------------------------------------------------------------------------------------


def _all_ids(client, headers) -> set[int]:  # type: ignore[no-untyped-def]
    """Collect every site id across pages so the assertion is robust to DB size (audit C6)."""
    ids: set[int] = set()
    cursor: str | None = None
    while True:
        url = "/api/v1/sitios?limit=200" + (f"&cursor={cursor}" if cursor else "")
        page = client.get(url, headers=headers).json()
        ids.update(s["id"] for s in page["items"])
        cursor = page.get("next_cursor")
        if not cursor:
            return ids


def test_list_only_mine(client, coord_a_headers, coord_b_headers, admin_headers, two_sites) -> None:  # type: ignore[no-untyped-def]
    ids_a = _all_ids(client, coord_a_headers)
    ids_b = _all_ids(client, coord_b_headers)
    ids_admin = _all_ids(client, admin_headers)
    assert two_sites["a"] in ids_a and two_sites["b"] not in ids_a
    assert two_sites["b"] in ids_b and two_sites["a"] not in ids_b
    assert {two_sites["a"], two_sites["b"]} <= ids_admin


def test_foreign_site_is_not_found(client, coord_a_headers, two_sites) -> None:  # type: ignore[no-untyped-def]
    r = client.get(f"/api/v1/sitios/{two_sites['b']}", headers=coord_a_headers)
    assert r.status_code == 404
    r = client.get(f"/api/v1/sitios/{two_sites['a']}", headers=coord_a_headers)
    assert r.status_code == 200
    assert r.headers["ETag"].startswith('"')
    assert r.json()["coordinador_oid"] is None  # not exposed to coordinators


def test_admin_sees_owner(client, admin_headers, two_sites) -> None:  # type: ignore[no-untyped-def]
    r = client.get(f"/api/v1/sitios/{two_sites['a']}", headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["coordinador_oid"] == str(two_sites["oid_a"])


def test_delta_reports_removed_ids(client, coord_a_headers, two_sites) -> None:  # type: ignore[no-untyped-def]
    r = client.get(
        f"/api/v1/sitios/delta?conocidos={two_sites['a']},{two_sites['b']}", headers=coord_a_headers
    )
    assert r.status_code == 200
    body = r.json()
    assert two_sites["b"] in body["removed_ids"]
    assert two_sites["a"] not in body["removed_ids"]
    assert len(body["max_rowversion"]) == 16


# ---------------------------------------------------------------------------------------------
# Layer 3: database, with a pooled connection reused across identities
# ---------------------------------------------------------------------------------------------


def _claims(oid: uuid.UUID, role: str) -> Claims:
    return Claims(oid=oid, name="t", username="t", roles=(role,), azp="x", tid="t")


def test_rls_on_pooled_connection(two_sites) -> None:  # type: ignore[no-untyped-def]
    q = text("SELECT id FROM sitio WHERE id IN (:a, :b)")
    params = {"a": two_sites["a"], "b": two_sites["b"]}
    spids: list[int] = []
    # Start from an empty pool so the three sequential sessions share one physical connection
    # (the pool is FIFO: with several idle connections the test would rotate through them).
    get_engine().dispose()
    # Same pool, sequential sessions: A, then B, then nobody.
    with session_for(_claims(two_sites["oid_a"], "Coordinador")) as s:
        spids.append(int(s.execute(text("SELECT @@SPID")).scalar()))
        assert {r[0] for r in s.execute(q, params)} == {two_sites["a"]}
    with session_for(_claims(two_sites["oid_b"], "Coordinador")) as s:
        spids.append(int(s.execute(text("SELECT @@SPID")).scalar()))
        assert {r[0] for r in s.execute(q, params)} == {two_sites["b"]}
    with session_factory()() as s:  # no context set: must see nothing
        spids.append(int(s.execute(text("SELECT @@SPID")).scalar()))
        assert {r[0] for r in s.execute(q, params)} == set()
    # The test only proves anything if the same physical connection served all three (TST-4).
    assert len(set(spids)) == 1, spids
    with session_for(_claims(uuid.uuid4(), "Admin")) as s:
        assert {r[0] for r in s.execute(q, params)} == {two_sites["a"], two_sites["b"]}


def test_rls_blocks_cross_write_and_raw_sql(two_sites) -> None:  # type: ignore[no-untyped-def]
    with session_for(_claims(two_sites["oid_a"], "Coordinador")) as s:
        # Update of a foreign row affects nothing (filter predicate)
        res = s.execute(
            text("UPDATE sitio SET nombre = N'hack' WHERE id = :b"), {"b": two_sites["b"]}
        )
        assert res.rowcount == 0
        # Insert claiming another coordinator's oid is blocked
        with pytest.raises(Exception, match="block predicate|Block predicate|BLOCK"):
            s.execute(
                text(
                    "INSERT INTO sitio_contacto (sitio_id, coordinador_oid, nombre, telefono, capturado_por, capturado_utc) "
                    "VALUES (:b, :oid_b, N'x', N'1', :oid_a, SYSUTCDATETIME())"
                ),
                {"b": two_sites["b"], "oid_b": two_sites["oid_b"], "oid_a": two_sites["oid_a"]},
            )
        s.rollback()


def test_app_user_cannot_touch_ledger_or_policy() -> None:
    with session_factory()() as s:
        set_session_context(s, "00000000-0000-0000-0000-000000000000", "Sistema")
        with pytest.raises(Exception, match="denied|DENY|permission|append only Ledger"):
            s.execute(text("DELETE FROM auditoria WHERE id = -1"))
        s.rollback()
        with pytest.raises(Exception, match="denied|permission|does not exist"):
            s.execute(text("ALTER SECURITY POLICY rls.coordinador_policy WITH (STATE = OFF)"))
        s.rollback()
        clear_session_context(s)


def test_delta_large_known_list_does_not_exceed_param_limit(client, coord_a_headers) -> None:  # type: ignore[no-untyped-def]
    """2500 known ids must not 500 on SQL Server's 2100-parameter cap (audit B-03)."""
    ids = ",".join(str(i) for i in range(900000, 902500))  # none of these exist
    r = client.get(f"/api/v1/sitios/delta?conocidos={ids}", headers=coord_a_headers)
    assert r.status_code == 200, r.text
    # every known-but-invisible id comes back as removed, chunked under the parameter limit
    assert len(r.json()["removed_ids"]) == 2500


def test_readyz_reports_the_applied_schema_revision(client) -> None:  # type: ignore[no-untyped-def]
    """D-03r: the app role may read alembic_version; /readyz says which revision is applied and
    whether it matches the code's head."""
    from app.main import CODE_SCHEMA_HEAD

    r = client.get("/readyz")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["schema"] == "ok"
    assert body["schema_revision"] == CODE_SCHEMA_HEAD == body["schema_head"]

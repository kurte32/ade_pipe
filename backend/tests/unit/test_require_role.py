"""Route role gate: which role the request runs with, and from which client (IDN-1, IDN-5)."""

from __future__ import annotations

import uuid

from fastapi import Depends, FastAPI, Request
from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.core.errors import register_error_handlers
from app.core.security import ROLE_ADMIN, ROLE_COORDINADOR, Claims, get_claims, require_role

PWA = "33333333-3333-4333-8333-333333333333"
ADMIN = "44444444-4444-4444-8444-444444444444"


def _app(roles: tuple[str, ...], azp: str, admin_azp: str = "") -> TestClient:
    app = FastAPI()
    register_error_handlers(app)
    claims = Claims(oid=uuid.uuid4(), name="x", username="x", roles=roles, azp=azp, tid="t", raw={})
    app.dependency_overrides[get_claims] = lambda: claims
    app.dependency_overrides[get_settings] = lambda: Settings(  # type: ignore[call-arg]
        auth_tenant_id="t",
        auth_audience="a",
        auth_allowed_azp=f"{PWA},{ADMIN}",
        auth_admin_azp=admin_azp,
    )

    @app.get("/coord")
    def coord(request: Request, _: Claims = Depends(require_role(ROLE_COORDINADOR))) -> dict:  # type: ignore[type-arg]
        return {"rol": request.state.context_role}

    @app.get("/admin")
    def admin(request: Request, _: Claims = Depends(require_role(ROLE_ADMIN))) -> dict:  # type: ignore[type-arg]
        return {"rol": request.state.context_role}

    @app.get("/any")
    def any_role(
        request: Request, _: Claims = Depends(require_role(ROLE_ADMIN, ROLE_COORDINADOR))
    ) -> dict:  # type: ignore[type-arg]
        return {"rol": request.state.context_role}

    return TestClient(app)


def test_dual_role_user_acts_as_coordinator_on_coordinator_routes() -> None:
    c = _app((ROLE_COORDINADOR, ROLE_ADMIN), PWA)
    assert c.get("/coord").json() == {"rol": ROLE_COORDINADOR}
    assert c.get("/admin").json() == {"rol": ROLE_ADMIN}
    assert c.get("/any").json() == {"rol": ROLE_ADMIN}


def test_role_without_permission_is_403() -> None:
    c = _app((ROLE_COORDINADOR,), PWA)
    assert c.get("/admin").status_code == 403
    assert _app((), PWA).get("/any").status_code == 403


def test_admin_is_honoured_only_from_the_admin_client_when_configured() -> None:
    # Without the binding (local default) either client works, as before.
    assert _app((ROLE_ADMIN,), PWA).get("/admin").status_code == 200
    # With it, an Admin token minted through the PWA client is just a token without that role.
    assert _app((ROLE_ADMIN,), PWA, admin_azp=ADMIN).get("/admin").status_code == 403
    assert _app((ROLE_ADMIN,), ADMIN, admin_azp=ADMIN).get("/admin").status_code == 200
    # And the admin client never acts as a coordinator.
    c = _app((ROLE_COORDINADOR, ROLE_ADMIN), ADMIN, admin_azp=ADMIN)
    assert c.get("/coord").status_code == 403
    assert c.get("/any").json() == {"rol": ROLE_ADMIN}

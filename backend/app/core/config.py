"""Application settings. All environment-specific values come from the environment.

Startup validation refuses development-only modes when ENVIRONMENT=production.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore", case_sensitive=False)

    environment: Literal["local", "test", "production"] = "local"
    log_level: str = "INFO"
    app_public_url: str = "http://localhost:5173"

    # Database
    db_host: str = "localhost"
    db_port: int = 1433
    db_name: str = "pipeline"
    db_auth: Literal["sql", "entra"] = "sql"
    db_user: str = "pipeline_app"
    db_password: str = ""
    db_admin_user: str = "sa"
    db_admin_password: str = ""
    db_pool_size: int = 5
    db_max_overflow: int = 10

    # Identity
    auth_mode: Literal["dev", "entra"] = "dev"
    auth_tenant_id: str
    auth_audience: str
    auth_allowed_azp: str = ""
    # Client id of the admin SPA registration; Admin is exercised only from it when set (IDN-5).
    auth_admin_azp: str = ""
    # SPA origins allowed by CORS. Empty behind Front Door (same origin); the SWA hosts without it.
    cors_allowed_origins: str = ""
    # Front Door profile id: when set, /api/* requests must carry X-Azure-FDID with this value, so
    # the origin restriction is not network-only (backlog A3). Empty = not behind Front Door.
    front_door_id: str = ""
    # Per-user request limits per minute (in-process, per replica). 0 disables a limit.
    rate_limit_captures_per_minute: int = 300
    rate_limit_transitions_per_minute: int = 300
    rate_limit_uploads_per_minute: int = 120
    rate_limit_upload_parts_per_minute: int = 1200
    rate_limit_loads_per_minute: int = 30
    auth_issuer: str
    auth_jwks_url: str
    auth_required_scope: str = "access_as_user"
    dev_idp_url: str = "http://localhost:8001"

    # Storage
    storage_mode: Literal["azurite", "azure"] = "azurite"
    storage_blob_endpoint: str = "http://localhost:10000/devstoreaccount1"
    storage_account_name: str = "devstoreaccount1"
    storage_account_key: str = ""
    storage_staging_account_url: str = ""
    storage_documents_account_url: str = ""
    storage_staging_container: str = "staging"
    storage_documents_container: str = "documents"

    # Integrations
    scan_mode: Literal["none", "defender"] = "none"
    scan_wait_seconds: int = 900
    notify_mode: Literal["log", "graph"] = "log"
    directory_mode: Literal["dev", "graph"] = "dev"
    graph_base_url: str = "https://graph.microsoft.com/v1.0"
    teams_app_id: str = ""

    # Telemetry
    applicationinsights_connection_string: str = ""

    # Limits
    pdf_max_bytes: int = 150 * 1024 * 1024
    pdf_max_pages: int = 50
    upload_chunk_bytes: int = 4 * 1024 * 1024
    photo_max_bytes: int = 1_572_864
    load_max_rows: int = 5000
    load_max_bytes: int = 10 * 1024 * 1024
    # Hard cap on any request body, enforced before the app reads it (audit B-05). Must exceed
    # load_max_bytes plus multipart overhead and upload_chunk_bytes.
    max_request_bytes: int = 12 * 1024 * 1024
    # Number of reverse proxies in front of the API that append to X-Forwarded-For (Container Apps
    # ingress = 1, plus Front Door = 2). 0 ignores the header and uses the socket peer (audit A5).
    trusted_proxy_hops: int = 0
    duplicate_distance_meters: float = 15.0
    suspicious_name_words: str = "prueba,viable,equivocado,ubicacion,ubicación,test"
    upload_session_ttl_hours: int = 72
    idempotency_ttl_days: int = 7
    retention_years: int = 5

    @property
    def allowed_azp(self) -> set[str]:
        return {x.strip() for x in self.auth_allowed_azp.split(",") if x.strip()}

    @property
    def suspicious_words(self) -> list[str]:
        return [w.strip().lower() for w in self.suspicious_name_words.split(",") if w.strip()]

    @field_validator("auth_issuer", "auth_jwks_url", "dev_idp_url", "storage_blob_endpoint")
    @classmethod
    def _strip_slash(cls, v: str) -> str:
        return v.rstrip("/")

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip().rstrip("/") for o in self.cors_allowed_origins.split(",") if o.strip()]

    @property
    def deployed(self) -> bool:
        """True outside the developer's compose stack (test/UAT and production in Azure).

        `local` is the only environment that may trust any SQL certificate, expose the API docs,
        accept the dev identity provider or run `e2e-cleanup` (audit IDN-2).
        """
        return self.environment != "local"

    @model_validator(mode="after")
    def _deployment_guard(self) -> Settings:
        if not self.deployed:
            return self
        problems: list[str] = []
        if self.auth_mode != "entra":
            problems.append("AUTH_MODE must be 'entra'")
        if not self.auth_issuer.startswith("https://login.microsoftonline.com/"):
            problems.append("AUTH_ISSUER must be the Entra v2 issuer")
        # The JWKS host is the actual trust root (signing keys are fetched from it), so pin it too;
        # a correct issuer string with a dev/attacker JWKS endpoint must not start (audit A1).
        if not self.auth_jwks_url.startswith("https://login.microsoftonline.com/"):
            problems.append("AUTH_JWKS_URL must be the Entra keys endpoint")
        if set(self.auth_tenant_id) <= set("0-"):
            problems.append("AUTH_TENANT_ID is a placeholder")
        if self.db_auth != "entra":
            problems.append("DB_AUTH must be 'entra' (managed identity)")
        if self.storage_mode != "azure":
            problems.append("STORAGE_MODE must be 'azure'")
        if not self.allowed_azp:
            problems.append("AUTH_ALLOWED_AZP must list the SPA client ids")
        if not self.auth_admin_azp:
            problems.append("AUTH_ADMIN_AZP must be the admin SPA client id")
        if self.notify_mode == "graph" and not self.teams_app_id:
            problems.append("TEAMS_APP_ID is required with NOTIFY_MODE='graph'")
        if self.environment == "production":
            if not self.front_door_id:
                problems.append("FRONT_DOOR_ID is required (origin validation, backlog A3)")
            if self.scan_mode != "defender":
                problems.append("SCAN_MODE must be 'defender'")
            if self.notify_mode != "graph":
                problems.append("NOTIFY_MODE must be 'graph'")
            if self.directory_mode != "graph":
                problems.append("DIRECTORY_MODE must be 'graph'")
        if problems:
            raise ValueError(f"Refusing to start in {self.environment}: " + "; ".join(problems))
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()

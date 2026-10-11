"""Application Insights via Azure Monitor OpenTelemetry.

Enabled only when a connection string is configured.
"""

from __future__ import annotations

import structlog
from fastapi import FastAPI

from app.core.config import Settings

log = structlog.get_logger()


def configure_telemetry(app: FastAPI, settings: Settings) -> None:
    if not settings.applicationinsights_connection_string:
        log.info("telemetry_disabled", reason="no APPLICATIONINSIGHTS_CONNECTION_STRING")
        return
    from azure.monitor.opentelemetry import configure_azure_monitor
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

    configure_azure_monitor(
        connection_string=settings.applicationinsights_connection_string,
        enable_live_metrics=False,
    )
    FastAPIInstrumentor.instrument_app(app, excluded_urls="healthz,readyz")
    log.info("telemetry_enabled")

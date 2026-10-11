# syntax=docker/dockerfile:1.7
FROM python:3.12-slim-bookworm AS base

ARG INSTALL_DEV=false
# An image started without ENVIRONMENT fails closed: the deployment guard applies.
ENV ENVIRONMENT=production
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_LINK_MODE=copy \
    PATH="/opt/venv/bin:$PATH"

# Microsoft ODBC Driver 18 for SQL Server (Debian 12 repository)
RUN apt-get update && apt-get install -y --no-install-recommends curl gnupg2 ca-certificates apt-transport-https \
    && curl -fsSL https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor -o /usr/share/keyrings/microsoft-prod.gpg \
    && echo "deb [arch=amd64 signed-by=/usr/share/keyrings/microsoft-prod.gpg] https://packages.microsoft.com/debian/12/prod bookworm main" > /etc/apt/sources.list.d/mssql-release.list \
    && apt-get update && ACCEPT_EULA=Y apt-get install -y --no-install-recommends msodbcsql18 unixodbc \
    && apt-get purge -y gnupg2 && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.4 /uv /bin/uv

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN if [ "$INSTALL_DEV" = "true" ]; then uv sync --frozen --no-install-project; else uv sync --frozen --no-install-project --no-dev; fi

COPY . .
RUN useradd -r -u 10001 -d /app appuser && chown -R appuser:appuser /app && chmod +x /app/scripts/*.sh
USER appuser
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/healthz')" || exit 1
# --no-proxy-headers: uvicorn must not rewrite the client address from X-Forwarded-For; the app
# applies TRUSTED_PROXY_HOPS itself (audit A5/D-12).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-proxy-headers"]

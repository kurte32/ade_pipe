.DEFAULT_GOAL := help
.PHONY: help up up-web down reset ps logs health db-migrate db-seed db-shell test test-unit lint dev e2e bicep-lint openapi
SHELL := /bin/bash
COMPOSE := docker compose
API_RUN := $(COMPOSE) run --rm --no-deps --user $$(id -u):$$(id -g) -e HOME=/tmp -e DB_HOST=sqlserver -e STORAGE_BLOB_ENDPOINT=http://azurite:10000/devstoreaccount1 -e DEV_IDP_URL=http://dev-idp:8001 api

help: ## List targets
	@grep -E '^[a-zA-Z0-9_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

.env:
	cp .env.example .env
	@echo "Created .env from .env.example (local development values)."

up: .env ## Start SQL Server, Azurite, dev identity provider, API (with migrations) and scheduler
	$(COMPOSE) up -d --build sqlserver azurite dev-idp api scheduler
	@$(MAKE) --no-print-directory health

up-web: .env ## Same as up, plus the two frontends in containers (profile web)
	$(COMPOSE) --profile web up -d --build

down: ## Stop everything, keep data
	$(COMPOSE) --profile web down

reset: ## Stop everything and delete all local data (database, blobs, dev keys)
	$(COMPOSE) --profile web down -v

ps: ## Show container status
	$(COMPOSE) --profile web ps

logs: ## Tail API and scheduler logs
	$(COMPOSE) logs -f --tail=200 api scheduler

health: ## Check health endpoints
	@for i in $$(seq 1 30); do curl -fsS http://localhost:$${API_PORT:-8000}/healthz >/dev/null 2>&1 && break; sleep 2; done; \
	curl -fsS http://localhost:$${API_PORT:-8000}/healthz && echo && curl -fsS http://localhost:$${API_PORT:-8000}/readyz && echo

db-migrate: ## Apply Alembic migrations
	$(API_RUN) alembic upgrade head

db-seed: ## Load the synthetic sample through the real bulk-load path and create dev data
	$(API_RUN) python -m app.cli seed

db-shell: ## Open sqlcmd against the local database
	$(COMPOSE) exec sqlserver /opt/mssql-tools18/bin/sqlcmd -S localhost -U sa -P "$$SQL_SA_PASSWORD" -C -d pipeline

test: ## Backend tests (unit + integration against the local stack)
	$(API_RUN) pytest -q

test-unit: ## Backend unit tests only (no database)
	$(API_RUN) pytest -q -m "not integration"

lint: ## Lint and type-check backend and frontends
	$(API_RUN) sh -c "ruff check . && ruff format --check . && mypy app"
	pnpm -r --if-present lint
	pnpm -r --if-present typecheck

dev: ## Run both frontends on the host with hot reload (needs node 22 + pnpm)
	pnpm install --frozen-lockfile
	pnpm dev

e2e: ## Playwright end-to-end tests against the running stack (frontends must be running)
	pnpm --filter e2e test

e2e-preview: ## Coordinator specs against the BUILT PWA (service worker active) served by vite preview
	cd apps/pwa-coordinador && VITE_ALLOW_DEV_AUTH=true pnpm exec vite build --mode development --outDir dist-preview --logLevel warn
	cd apps/pwa-coordinador && (pnpm exec vite preview --outDir dist-preview --port 4173 --strictPort > /tmp/vite-preview.log 2>&1 & echo $$! > /tmp/vite-preview.pid)
	for i in $$(seq 1 30); do curl -fsS http://localhost:4173/ >/dev/null 2>&1 && break; sleep 1; done
	PWA_URL=http://localhost:4173 pnpm --filter e2e exec playwright test tests/pwa.signin.spec.ts tests/pwa.a11y.spec.ts tests/pwa.flow.spec.ts --project=pwa-mobile; status=$$?; pkill -f 'dist-preview --port [4]173' 2>/dev/null; rm -f /tmp/vite-preview.pid; exit $$status

job-%: ## Run a background job once: make job-promote | job-outbox | job-purge
	$(API_RUN) python -m app.jobs.run $*

bicep-lint: ## Build and lint all Bicep templates (static validation, no subscription needed)
	bash infra/bicep/validate.sh

openapi: ## Export the OpenAPI document to docs/openapi.json
	$(API_RUN) python -m app.cli openapi > docs/openapi.json

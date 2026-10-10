# ADR-010: Infrastructure as Code and CI/CD

**Status:** Proposed  **Date:** 2026-10-10  **Deciders:** TI, Subdirección de IA

## Context and problem statement

TDD v0.1 (13) requires infrastructure as code for all resources, separate dev, test, and prod environments, a CI/CD pipeline with tests, static analysis, dependency and container scanning, and Alembic migrations, but leaves the CI/CD platform pending (pendiente 12). The repository today has no code and no git history. This ADR picks the IaC tool, the CI/CD platform, and the promotion model so Phase 1 can start.

## Requirements and constraints

- Fact (TDD 13): IaC for everything; three environments; CI with tests, static analysis, dependency and container scanning; Alembic migrations.
- Fact (TDD 13): CI/CD platform pending with TI.
- Fact (Step 1 audit): no repository, no code, no pipelines exist.
- Assumption (TO_BE 9.5): Bicep with Azure Verified Modules and GitHub Actions with OIDC, revisable when pendiente 12 is answered.
- Assumption (ADR-008): no long-lived deployment secrets; federated credentials per environment.
- Constraint: one container image must be promoted unchanged from `dev` to `test` to `prod`.

## Options considered

### Option A: Bicep with Azure Verified Modules, GitHub Actions with OIDC federation

| Dimension | Assessment |
|---|---|
| Complexity | Low |
| Cost | GitHub Actions minutes; no state storage |
| Security | OIDC federation, no stored credentials; environment protection rules |
| Reliability | ARM deployments are idempotent; `what-if` for drift |
| Team familiarity | Medium |

Pros: no state file to protect; first-class Azure resource coverage; `what-if` gives drift detection for free; GitHub environments provide approvals.
Cons: Azure-only (acceptable, the platform is Azure-only); AVM coverage of every resource must be checked (verify), with raw Bicep as fallback.

### Option B: Terraform with Azure DevOps Pipelines

| Dimension | Assessment |
|---|---|
| Complexity | Medium |
| Cost | State storage; Azure DevOps licensing (verify) |
| Security | State file contains sensitive data and must be protected; workload identity federation available |
| Reliability | Mature; plan output for review |
| Team familiarity | Depends on TI |

Pros: multi-cloud skills; strong plan review workflow.
Cons: state management is an extra security and operations concern; Azure DevOps is a second platform if code lives on GitHub.

### Option C: Bicep with Azure DevOps Pipelines

| Dimension | Assessment |
|---|---|
| Complexity | Low |
| Cost | Azure DevOps licensing (verify) |
| Security | Workload identity federation |
| Reliability | Good |
| Team familiarity | Depends on TI |

Pros: natural if TI standardizes on Azure DevOps.
Cons: only differs from Option A in the pipeline runtime; chosen if pendiente 12 points to Azure DevOps.

## Decision and rationale

Option A as the default, with Option C as the drop-in replacement if TI answers pendiente 12 with Azure DevOps; the Bicep templates and the pipeline stages are the same, only the workflow syntax changes. Terraform is not adopted because state protection is cost without benefit for an Azure-only platform.

Pipeline design:

- Repository: one git monorepo with `apps/`, `packages/`, `api/`, `infra/`, `architecture/`. First task of Phase 1 is `git init` with branch protection on `main`.
- CI on pull request: lint and type-check (ruff, mypy, eslint, tsc), unit tests, integration tests against a disposable Azure SQL (serverless) or SQL Edge container including RLS tests, `bicep build` and `what-if` against `dev`, dependency scanning (pip-audit, npm audit, or Dependabot), secret scanning, container build and vulnerability scan (Defender for Containers or Trivy), SBOM generation.
- Image promotion: one image built once per commit, tagged with the git SHA and signed; promotion to `test` and `prod` re-tags the same digest, never rebuilds.
- Deploy to `dev` on merge to `main`; to `test` on a release tag with environment approval; to `prod` on approval by a named role, with the same artifact.
- Migrations: Alembic runs as a Container Apps Job using a migration identity distinct from the runtime identity (ADR-009), before the new revision receives traffic; migrations are forward-only and backward-compatible with the previous revision so rollback is a traffic switch.
- Rollback: Container Apps revision traffic switch for the API; redeploy of the previous build artifact for the Static Web Apps; database rollback is a compensating migration, never a restore, except in disaster scenarios.
- Drift: nightly `what-if` on `test` and `prod` fails the workflow on differences and opens an issue.
- Environment provisioning: one parameter file per environment; `dev` can be destroyed and recreated; `test` and `prod` carry deletion locks.

## Advantages and disadvantages

Advantages: no credentials in the pipeline; one artifact across environments; migrations are an explicit, auditable step; drift is detected automatically.
Disadvantages: GitHub environments with approvals need the paid plan features (verify); AVM gaps may require raw Bicep; immutable storage and locks make `test` and `prod` teardown a manual procedure.

## Security, reliability, and cost implications

Security: OIDC federated credentials scoped per environment and branch or tag; least-privilege role assignments on each resource group; SBOM and image signature stored with the artifact; dependency and container scanning gate merges.
Reliability: idempotent deployments; blue-green through Container Apps revisions; migration job must succeed before traffic shift.
Cost: Actions minutes; disposable SQL for integration tests kept small and auto-paused.

## Consequences and risks

- Phase 1 critical path includes creating the federated credentials and the three resource groups before any application deploy.
- Risk: pendiente 12 answered late; mitigated because templates are platform-neutral and only workflow files change.
- Risk: integration tests need a real Azure SQL for RLS and ledger behaviour; SQL Edge may not support ledger (verify), so CI may need a serverless Azure SQL in `dev`.

## Conditions that would justify revisiting

- TI mandates Azure DevOps or Terraform as the corporate standard.
- The platform expands beyond Azure.
- A platform team provides golden pipelines and modules.

## Action items

- [ ] `git init`, branch protection, CODEOWNERS, Dependabot, secret scanning.
- [ ] Bicep modules for all resources in AZURE_DESIGN section 2 with per-environment parameter files.
- [ ] GitHub Actions workflows: `ci.yml`, `deploy-dev.yml`, `deploy-test.yml`, `deploy-prod.yml`, `drift.yml`.
- [ ] Federated credentials and role assignments per environment.
- [ ] Migration job definition with a separate migration identity.
- [ ] Confirm pendiente 12 with TI and swap workflow syntax if needed.

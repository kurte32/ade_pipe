# ADR-001: Compute platform for the API and background jobs

**Status:** Proposed  **Date:** 2026-10-10  **Deciders:** Subdirección de IA, TI

## Context and problem statement

The platform needs one Python 3.12 FastAPI service plus three background jobs (file promotion after malware scan, notification outbox delivery, retention purge). The TDD v0.1 (section 4.2) already names Azure Container Apps for the API but does not say where the jobs run, and the network posture (ADR-008) requires the compute to reach private endpoints inside a VNet. The question is which Azure compute hosts the service and the jobs with the least operational burden at the current scale.

## Requirements and constraints

- Fact (TDD 4.2): backend is Python, FastAPI, SQLAlchemy, Alembic, pandas, delivered as a container.
- Fact (TDD 5.1): the backend authenticates to SQL, storage, Key Vault, and Graph with a managed identity, no secrets.
- Fact (TDD 1, Anexo A): 10 users, 87 sites, 2 regions today.
- Fact (TDD 9.2): uploads are chunked, so any replica must be able to continue a session; state lives in Blob staging and SQL, not in process memory.
- Assumption (ADR-008): private endpoints for SQL, storage, Key Vault, ACR, so compute must be VNet-integrated.
- Assumption (TO_BE 2): modular monolith, one image, no broker.
- Constraint: one small team; operations must stay simple.

## Options considered

### Option A: Azure Container Apps (workload profile, VNet-integrated) with Container Apps Jobs for background work

| Dimension | Assessment |
|---|---|
| Complexity | Low to medium |
| Cost | Low at this scale; dedicated profile has a fixed floor when VNet-integrated |
| Security | Managed identity, internal ingress, Private Link origin for Front Door |
| Reliability | Managed revisions, health probes, zone redundancy available (verify) |
| Team familiarity | Medium; container-first teams adapt quickly |

Pros: one image serves API and jobs; scheduled and event-triggered jobs without a second runtime; revision-based rollback; scale to zero in dev.
Cons: fewer knobs than AKS; VNet integration requires a workload-profile environment, which has a fixed cost.

### Option B: Azure App Service (Linux, container) with WebJobs or a second App Service for jobs

| Dimension | Assessment |
|---|---|
| Complexity | Low |
| Cost | Comparable; always-on plan |
| Security | Managed identity, VNet integration, private endpoints supported |
| Reliability | Mature, deployment slots |
| Team familiarity | High |

Pros: deployment slots, very mature tooling.
Cons: background jobs are awkward for Linux containers (WebJobs are Windows-centric, so a second app or a Function would be needed); less natural fit for a container-first pipeline; two runtimes to patch.

### Option C: Azure Kubernetes Service

| Dimension | Assessment |
|---|---|
| Complexity | High |
| Cost | Highest floor (node pool) |
| Security | Strong but requires cluster hardening work |
| Reliability | Strong with effort |
| Team familiarity | Low to medium |

Pros: maximum flexibility.
Cons: a cluster for one container and ten users is unjustified; upgrades, node patching, and RBAC are ongoing work.

### Option D: Azure Functions (Python) for everything

| Dimension | Assessment |
|---|---|
| Complexity | Medium |
| Cost | Low |
| Security | Managed identity |
| Reliability | Good for short tasks |
| Team familiarity | Medium |

Pros: cheap for jobs.
Cons: chunked uploads and pandas parsing of files fit poorly in the Functions programming model; splitting the API into Functions fragments the modular monolith.

## Decision and rationale

Option A. Container Apps runs the API as one app with internal ingress and the three jobs as Container Apps Jobs from the same image. It satisfies managed identity, VNet integration, revision rollback, and keeps one deployment unit. App Service was the closest alternative and loses only on background jobs for Linux containers. AKS and Functions add complexity without a requirement behind it.

## Advantages and disadvantages

Advantages: single image and pipeline; jobs share code with the service layer; scale to zero in non-production; health probes and revisions built in.
Disadvantages: fixed cost of the workload-profile environment when VNet-integrated; fewer advanced networking controls than AKS; Container Apps ingress and Front Door timeouts for long downloads must be verified (verify).

## Security, reliability, and cost implications

Security: user-assigned managed identity shared by app and jobs; no inbound internet exposure (Front Door Private Link origin); image pulled from ACR over a private endpoint.
Reliability: minimum replica count of 1 in production (2 if zone redundancy is confirmed, verify); readiness and liveness probes on `/healthz`; jobs are idempotent and resumable so retries are safe.
Cost: dominated by the workload profile floor in prod and test; dev uses consumption and scales to zero.

## Consequences and risks

- The three jobs must be designed as idempotent batch runs reading state from SQL, which is already required by TO_BE section 5.
- Long-running downloads through ingress are an open verification item (AZURE_DESIGN section 7).
- If the Fabric VNet data gateway is dropped (ADR-008 alternative), Container Apps can move to the consumption profile and reduce cost.

## Conditions that would justify revisiting

- A second service with distinct scaling or language appears.
- Container Apps cannot meet the verified timeout needs for 150 MB downloads and a sidecar or different ingress is required.
- The organization standardizes on App Service or AKS with a platform team that absorbs the operational cost.

## Action items

- [ ] Confirm workload-profile environment sizing and zone redundancy availability in the target region (verify).
- [ ] Define `/healthz` (liveness) and `/readyz` (readiness, checks SQL and storage reachability).
- [ ] Define the three jobs with schedules and triggers in Bicep (ADR-010).
- [ ] Verify ingress timeout behaviour for `Range` downloads in Phase 0.

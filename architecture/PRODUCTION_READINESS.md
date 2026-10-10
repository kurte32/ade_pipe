# Production Readiness · Pipeline de Posibles Tiendas

Status: Proposed, 10 October 2026. Companion to `TO_BE.md`, `AZURE_DESIGN.md`, and `IMPLEMENTATION_PLAN.md`. ADR numbers refer to `ADR/`. Labels: Fact, Assumption, Recommendation, Open, as defined in `TO_BE.md`.

This document states how the platform is operated and the measurable gates it must pass before coordinators use it in production. Section 8 is the checklist executed in Phase 5 of the implementation plan.

## 1. Operational requirements

**Usage profile (Fact, TDD).** Ten coordinators in two regions, one or two administrators, 87 sites today. Coordinators work in the field with intermittent 4G and rely on the offline queue; administrators work from a desktop during office hours. Load is small; the operational risk is data integrity and field usability, not throughput.

**Availability target (Assumption, pending RPO and RTO from TDD pendiente 12).** Business hours availability with the PWA tolerating API outages through its offline queue. Proposed targets, to be ratified by TI and Negocio:

| Service level objective | Target | Measured by | Why this value |
|---|---|---|---|
| API availability (successful responses to health and user requests) | 99.5 % monthly, business hours Mexico City | Application Insights availability test through Front Door plus server request success rate | Coordinators can keep capturing offline during short outages; administrators cannot load during an outage |
| Sync success rate (queued operations accepted on first replay, excluding legitimate 412 and 422) | 99 % weekly | Custom metric from the PWA and API idempotency store | A lower rate means lost field work or repeated conflicts |
| Upload completion rate (upload sessions that reach promoted state within 24 hours of completion) | 98 % weekly | `subida_sesion` state transitions | Covers scan delay, promotion job failures, and abandoned sessions |
| List latency (RNF-08, Fact) | p95 under 3 s for `GET /api/v1/sitios` on 4G, measured on device | PWA telemetry with network type | Field usability requirement from the TDD |
| Notification delivery (return to Teams delivery) | 95 % within 15 minutes, 100 % within 24 hours or dead-lettered with alert | `notificacion_outbox` timestamps | Notification is not on the critical path (Fact, TDD section 11) |

**Error budget (Recommendation).** With the API availability SLO above, roughly 1 hour of business-hours downtime per month is tolerable. Spend it on planned maintenance first; if an incident consumes it, feature deployment pauses until the next month unless the change is a fix.

**Support model (Open).** The TDD names no operations owner. This document assumes the Subdirección de Inteligencia Artificial owns level 2 support and TI owns level 1 (device, Intune, Entra account issues). Ratify before go-live.

## 2. Observability design

### 2.1 Structured logs

All API and job logs are JSON lines sent to Application Insights through OpenTelemetry. Browser logs from both SPAs go to Application Insights through the JavaScript SDK with the same correlation id.

| Field | Required | Notes |
|---|---|---|
| `timestamp` (UTC), `level`, `logger`, `message` | Yes | Standard |
| `trace_id`, `span_id`, `correlation_id` | Yes | W3C trace context; `correlation_id` is returned to the client in every response header |
| `user_oid`, `user_role` | Yes on authenticated requests | Entra object id only; never name or email |
| `sitio_id`, `lote_id`, `subida_id`, `operacion_key` | When relevant | Business identifiers, not business content |
| `route`, `status_code`, `duration_ms` | Yes on requests | |
| `env`, `revision`, `job_name` | Yes | For correlating with deployments |

Forbidden in logs (Fact, TDD RNF-01 and section 5.3; enforced by a log filter and a unit test over the serializer): owner contact fields (`nombre`, `telefono`, `correo`, `notas` of `sitio_contacto`), file content or file names supplied by users, bearer tokens or any `Authorization` header, request bodies of `PUT /contacto`, Excel or CSV row contents beyond row number and result code, Graph responses beyond status code.

### 2.2 Traces

W3C `traceparent` is generated in the SPA, propagated through Front Door to the API, and from the API to SQL (as `SESSION_CONTEXT('trace_id')` for correlation in Query Store, Recommendation), to storage SDK calls, and to Graph calls. Jobs start a new trace and record the triggering event id. Sampling: 100 % of errors, 20 % of successful requests in `prod` (Assumption; tune on ingestion cost).

### 2.3 Metrics

Business metrics (custom metrics from the API and jobs, emitted on write and aggregated hourly):

| Metric | Source | Use |
|---|---|---|
| Sites per status and per region | `sitio` | Pipeline throughput; feeds the TDD's later Power BI work |
| Returns per week and per reason | `sitio_estatus_historial` | Quality signal |
| Sync queue depth per device | PWA telemetry | Coordinators stuck offline or in conflict |
| Blocked chains per device | PWA telemetry | Unresolved conflicts needing attention |
| Outbox backlog and age of oldest pending | `notificacion_outbox` | Notification delivery health |
| Uploads pending scan and age of oldest | `subida_sesion` | Defender or promotion job delay |
| Loads per week, rows by result | `carga_lote` | Admin activity and data quality |

Technical metrics (standard from Application Insights, Container Apps, Azure SQL, Storage, Front Door):

| Metric | Use |
|---|---|
| Request rate, error rate (4xx and 5xx separately), latency p50 p95 p99 per route | API health |
| 412 and 422 rate on transitions | Expected conflicts; a spike means a sync bug |
| 401 and 403 rate | Token or role problems after a policy change |
| Container Apps replica count, CPU, memory, restarts | Capacity and crashes |
| Azure SQL CPU, DTU or vCore utilisation, deadlocks, failed connections, storage | Database health; RLS predicate cost |
| Storage request errors and throttling on both accounts | Upload path |
| Front Door origin health, WAF blocked requests by rule | Ingress and false positives |
| Job duration, success and failure count per job | Promotion, outbox, purge |
| Application Insights daily ingestion GB | Cost control |

### 2.4 Dashboards (Recommendation, deployed by Bicep as Azure workbooks)

1. **Operations:** SLO panels, error rate, latency, replica count, SQL utilisation, job status, alert summary.
2. **Field:** sync queue depth and blocked chains per device, sync success rate, on-device list latency by network type, upload sessions by state.
3. **Business:** sites per status and region, returns per reason, loads per week.
4. **Security:** 401 and 403 trends, WAF blocks, Defender for Storage alerts, audit rows per action, failed RLS test runs.

### 2.5 Alerts

Alerts route to an on-call channel (Teams channel plus email; paging tool is Open). Every alert names a runbook from section 6.

| Condition | Severity | Action | Runbook |
|---|---|---|---|
| Availability test failing from two locations for 5 minutes | Sev 1 | Page on-call | RB-10 API outage |
| 5xx rate above 5 % over 10 minutes | Sev 2 | Page on-call | RB-10 |
| Azure SQL failed connections or CPU above 90 % for 15 minutes | Sev 2 | Page on-call | RB-11 database |
| Container Apps restarts above 3 in 15 minutes | Sev 2 | Page on-call | RB-10 |
| Sync success rate below 95 % over 1 hour, or blocked chains above 5 devices | Sev 2 | Notify L2 | RB-01 sync failures |
| Upload sessions pending scan older than 2 hours | Sev 3 | Notify L2 | RB-02 stuck upload sessions |
| Outbox pending older than 1 hour or any dead-lettered notification | Sev 3 | Notify L2 | RB-03 outbox backlog |
| Defender for Storage tags a blob Malicious | Sev 2 | Notify L2 and Seguridad | RB-04 flagged file |
| RLS cross-access test fails in CI | Blocker | Block merge, notify architect | RB-05 RLS failure |
| Purge job deleted more than the expected count or hit a legal hold | Sev 2 | Notify L2 and Legal | RB-07 retention purge |
| Application Insights daily ingestion above cap | Sev 3 | Notify L2 | RB-12 cost |
| WAF blocks above baseline by 10x in 1 hour | Sev 3 | Notify L2 and Seguridad | RB-13 WAF review |
| Nightly Bicep `what-if` reports drift | Sev 3 | Notify L2 | RB-14 drift |
| Front Door certificate expiring within 30 days | Sev 3 | Notify L2 | RB-15 certificate |

### 2.6 Log retention and cost controls

- Log Analytics interactive retention 90 days; audit-relevant tables (`auditoria` lives in SQL, not logs) do not depend on log retention (Fact, TDD RF-10 is satisfied by the ledger table).
- Daily ingestion cap set per environment with the Sev 3 alert above; sampling as in 2.2; request bodies never logged; PWA telemetry batched and sent only on sync.
- `dev` retention 30 days. Query Store on Azure SQL for performance history instead of logging query text.

## 3. Health checks

| Probe | Path | Checks | Container Apps configuration (Recommendation; verify defaults) |
|---|---|---|---|
| Liveness | `GET /healthz/live` | Process responds; no dependencies | Startup grace then periodic; failure restarts the replica |
| Readiness | `GET /healthz/ready` | SQL `SELECT 1` with the application user, `st-stg` and `st-doc` container metadata read, Key Vault secret list permission check, JWKS cache populated | Failure removes the replica from ingress without restart |
| Startup | `GET /healthz/ready` | Same as readiness | Longer threshold to cover Alembic check and JWKS fetch |
| Dependency detail | `GET /healthz/deps` (Admin role only) | Per-dependency status and latency including Graph token acquisition and Defender tag read | Not used by probes; for runbooks |

Jobs expose completion status through their exit code and a final structured log line; Container Apps job history is the health signal.

Front Door health probe targets `GET /healthz/ready` through the Private Link origin. Static Web Apps have no custom probe.

## 4. Resilience

**Timeouts (Recommendation; values are starting points for `dev`).** Every outbound call has an explicit timeout: SQL statement timeout per route class (short for reads, longer for bulk load confirm), storage SDK operation timeout per chunk, Graph request timeout short because it is off the critical path. Request-level timeout in the API below the Front Door and Container Apps ingress timeouts (values not verified in this exercise; measure in Phase 1).

**Retries.** Exponential backoff with full jitter and a bounded attempt count for SQL transient errors (using the driver's transient error list), storage 5xx and 429, and Graph 5xx and 429 honouring `Retry-After`. No retry on 4xx other than 429. The PWA queue retries with backoff and stops a site's chain on 412 or 422 (ADR-005).

**Idempotency.** Every mobile write carries `Idempotency-Key`; the API stores response code and body in `operacion_idempotente` for 7 days and returns the stored response on replay. Jobs are idempotent: promotion checks `subida_sesion` state and `sitio_archivo` existence before acting; outbox delivery marks rows atomically; purge records each deletion before deleting.

**Circuit breaker.** Only around Microsoft Graph (equivalence resolution and notifications). Open circuit: equivalence save returns a clear retryable error; outbox delivery pauses and resumes on half-open success. No breaker around SQL or storage, because the API cannot degrade usefully without them.

**Graceful degradation.**

| Dependency down | Behaviour | User impact |
|---|---|---|
| Entra ID | Cached JWKS keeps validating until key rotation; new sign-ins fail | PWA opens with cached data; sync waits; admin cannot sign in |
| Azure SQL | Readiness fails, Front Door marks origin unhealthy | PWA keeps capturing offline; admin web shows outage banner |
| `st-stg` | Uploads fail with retryable error; sessions resume later | Coordinator sees "reintentar más tarde"; nothing lost |
| `st-doc` | Promotion job retries; downloads fail | Files stay in staging; alert RB-02 |
| Defender for Storage | Promotion waits; alert after 2 hours | Documents show "en validación" |
| Microsoft Graph | Breaker opens; outbox accumulates; equivalence save rejected | Returns still happen; in-app notice works; Teams delayed |
| Fabric | None operationally | Analytics lag |
| Front Door | Total outage for new requests | PWA offline mode; incident RB-10 |

## 5. Backup and recovery

**Azure SQL.** Automated backups with zone-redundant backup storage; point-in-time restore within the automated retention window; long-term retention of weekly backups aligned with the five-year document retention (Assumption; align with Legal pendiente 7). Ledger tables keep their digest history; verify digest after any restore.

**Storage.** `st-doc`: version-level immutability with the five-year time-based policy and legal hold procedure (ADR-003); soft delete for blobs and containers; blob versioning; geo-redundant storage. `st-stg`: soft delete only, 7-day lifecycle deletion of abandoned sessions. Immutable blobs cannot be deleted by the application or an operator within the retention period, which is the primary protection against ransomware-style deletion.

**Configuration and code.** Bicep, Alembic migrations, and workflow definitions are in git; a full environment is reproducible from the repository plus the Entra registrations held by the identity team.

**RPO and RTO (Open, TDD pendiente 12).** Placeholders until ratified: RPO 1 hour for SQL (automated backup granularity), near zero for documents (immutable, geo-redundant); RTO 4 hours for a single-region service outage via restore to a side database and revision redeploy. Multi-region failover is not designed (Assumption 8 in `TO_BE.md`).

**Restore drill procedure (executed in Phase 5 and then twice a year).**

1. Point-in-time restore of the `test` database to a side database at a time 1 hour earlier.
2. Verify row counts for `sitio`, `sitio_estatus_historial`, and `auditoria`; verify ledger digest.
3. Verify the RLS security policy and the application user's permissions survived the restore; run the cross-access test against the side database.
4. Point the `test` API at the side database through a configuration change and run the integration suite.
5. Recover a soft-deleted blob version in `st-stg`; confirm that a promoted blob in `st-doc` cannot be deleted.
6. Record elapsed time against the RTO placeholder and file the report.

## 6. Runbooks

Written in Phase 5 under `docs/runbooks/`, each with symptoms, diagnosis queries, actions, and escalation.

| Id | Runbook | Trigger |
|---|---|---|
| RB-01 | Sync failures and blocked chains | Sync success alert; coordinator report of "pendiente" that never clears. Diagnosis by `operacion_idempotente` and PWA telemetry per device; actions include resolving the conflict with the coordinator and, as last resort, admin return to unblock |
| RB-02 | Stuck upload sessions | Pending-scan alert. Check Defender tag, Event Grid delivery, promotion job logs; rerun promotion job (idempotent) |
| RB-03 | Outbox backlog | Outbox alert. Check Graph permission, breaker state, Teams app status; replay dead-lettered rows after fix |
| RB-04 | Defender flagged file | Malicious tag. File stays in staging; notify Seguridad; inform coordinator through admin; delete staging blob after review; audit |
| RB-05 | RLS test failure in CI | Blocked merge. Treat as a security incident candidate: identify the change, confirm no deployment occurred, fix before any other merge |
| RB-06 | Graph application permission or Teams app changes | Permission revoked or app re-published. No client secrets exist (managed identity), so no key rotation; verify role assignments and re-consent |
| RB-07 | Retention purge | Scheduled purge and its alert. Dry-run report review, legal hold check, execution log, audit verification |
| RB-08 | Reassignment of a coordinator | Admin request or coordinator leaves. Update equivalence, reassign sites, confirm removal from the previous device on next sync, disable group membership |
| RB-09 | Restore from backup | Data loss or corruption. Section 5 procedure with production parameters and approvals |
| RB-10 | API outage | Availability or 5xx alert. Check revision, replica restarts, dependencies via `/healthz/deps`, roll back to previous revision |
| RB-11 | Database health | SQL alerts. Query Store top queries, RLS predicate plans, deadlocks, scale up temporarily |
| RB-12 | Monitoring cost | Ingestion cap alert. Review sampling and noisy loggers |
| RB-13 | WAF review | Block spike. Inspect rule matches; add exclusion only with Seguridad approval |
| RB-14 | Infrastructure drift | `what-if` alert. Identify manual change, revert or codify |
| RB-15 | Certificate and domain | Expiry alert. Renew through Front Door managed certificate or Key Vault certificate |

## 7. Incident response

| Severity | Definition | Response | Communication |
|---|---|---|---|
| Sev 1 | Platform unavailable for all users in business hours, or confirmed data exposure across coordinators | Page on-call immediately; architect joins; fix or roll back first | Status message to coordinators and administrators within 30 minutes; Seguridad informed for exposure |
| Sev 2 | Major function broken (sync, upload, bulk load, returns) or a security control failed (RLS, Defender, WAF) without confirmed exposure | Page on-call in business hours; next business morning otherwise | Message to affected role within 1 hour |
| Sev 3 | Degraded but workable (Teams delays, slow lists, drift, cost) | Ticket to L2 within one business day | Note in the operations channel |

Roles (Open; ratify with TI): L1 is TI service desk for device, Intune, and Entra account issues; L2 is the Subdirección de Inteligencia Artificial engineer on call; the architect is escalation for Sev 1 and security incidents; Seguridad is notified for any security-control failure.

Every Sev 1 and Sev 2 gets a blameless post-incident review within five business days with actions tracked in the risk register.

## 8. Production acceptance criteria

All gates must be checked with evidence attached before the production deployment approval in Phase 5. Owners are roles, not names.

### Security

- [ ] Penetration test completed on `test` with production-equivalent topology; no critical or high findings open; retest report attached. Owner: Seguridad.
- [ ] RLS cross-access test suite passes at API and database level, including child tables, Admin bypass, pooled-connection reuse, and reassignment; report attached to HU-18. Owner: backend lead.
- [ ] Role escalation tests pass: Coordinador token on every Admin route returns 403; token without roles returns 403; token with wrong audience, issuer, `tid`, or missing `scp` returns 401; token with `azp` outside the allowlist returns 401. Owner: backend lead.
- [ ] Assignment Required confirmed on `pipeline-api` and `pipeline-web-admin` in production; a coordinator cannot sign in to the admin web. Owner: identity team.
- [ ] Conditional Access policies A and B active and tested on a managed device. Owner: identity team.
- [ ] No secrets in the repository (secret scan clean) and none in Container Apps configuration beyond Key Vault references; shared key access disabled on both storage accounts; Entra-only authentication on SQL. Owner: infrastructure.
- [ ] Dependency scans (pip, npm) and container image scan show no critical findings; high findings have a dated exception. Owner: backend lead.
- [ ] Defender for Cloud recommendations reviewed for every production resource; high severity items closed or accepted in the risk register. Owner: infrastructure.
- [ ] Malware scanning verified end to end in production: a test file (EICAR) is tagged Malicious and never promoted. Owner: backend lead.
- [ ] Audit ledger verified: `UPDATE` and `DELETE` on `auditoria` and `sitio_estatus_historial` fail for the application user; ledger digest verification succeeds. Owner: backend lead.
- [ ] Logs reviewed for forbidden fields with the serializer test and a manual sample. Owner: backend lead.

### Reliability

- [ ] Restore drill from section 5 executed on `test` within the RTO placeholder; report attached. Owner: infrastructure.
- [ ] Azure SQL failover simulated; API recovers without manual action and the offline queue replays cleanly. Owner: backend lead.
- [ ] Graph outage simulated; returns succeed, outbox retries, breaker opens and closes. Owner: backend lead.
- [ ] Offline chain Playwright suite passes in CI and on a real device in low signal: three sites, full chain, zero duplicates, zero lost captures, conflict surfaced on admin return. Owner: frontend lead.
- [ ] Resumable upload of a 150 MB PDF with forced disconnect completes without re-sending received blocks. Owner: frontend lead.
- [ ] Immutability confirmed in production: deletion of a promoted blob is blocked. Owner: infrastructure.

### Operations

- [ ] Dashboards from 2.4 deployed and showing production data. Owner: infrastructure.
- [ ] All alerts from 2.5 deployed, routed, and each tested by forcing the condition at least once in `test`. Owner: infrastructure.
- [ ] Runbooks RB-01 to RB-15 written and walked through with the L2 owner. Owner: architect.
- [ ] On-call rota and severity model from section 7 ratified by TI and the Subdirección. Owner: architect.
- [ ] Health probes configured and the Front Door origin healthy through Private Link. Owner: infrastructure.
- [ ] Nightly `what-if` running on production with no drift. Owner: infrastructure.

### Compliance and privacy

- [ ] Privacy notice text from Legal shown before contact capture (TDD pendiente 13). Owner: Legal and frontend lead.
- [ ] Retention start event, legal hold procedure, and discarded-site treatment decided (TDD pendiente 7); retention policy configured accordingly on `st-doc`. Owner: Legal and infrastructure.
- [ ] Fabric Mirroring verified to exclude `sitio_contacto`, `auditoria`, `operacion_idempotente`, and `carga_fila_staging`. Owner: backend lead.
- [ ] Teams notification payload verified to contain no owner contact data. Owner: backend lead.
- [ ] Audit log covers every write and every document download with user, time, and origin (RF-10, RNF-07); sample verified. Owner: backend lead.

### Performance

- [ ] `GET /api/v1/sitios` p95 under 3 seconds on 4G measured on an Intune-managed device with the full production dataset (RNF-08). Owner: frontend lead.
- [ ] Download of a 150 MB document through Front Door completes on 4G with `Range` support; ingress timeouts verified sufficient (verify). Owner: backend lead.
- [ ] Bulk load of the 87-row sample completes preview within a time acceptable to the administrator (Assumption: under 30 seconds). Owner: backend lead.

### Deployment

- [ ] Production deployed from the same image digest and SPA bundles as `test`. Owner: infrastructure.
- [ ] Revision rollback rehearsed in `test`: traffic shifted to the previous revision within minutes, with the database migration confirmed backward compatible. Owner: infrastructure.
- [ ] Alembic migration job runs before traffic shift and is recorded in the deployment log. Owner: backend lead.
- [ ] Deletion locks on the production resource group; break-glass procedure documented and audited. Owner: infrastructure.
- [ ] Bicep `what-if` clean on production immediately after deployment. Owner: infrastructure.
- [ ] Go-live checklist signed by the architect, the operations owner, and Seguridad. Owner: architect.

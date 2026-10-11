# Improvement backlog · Pipeline de Posibles Tiendas

Date: 11 October 2026 · Branch `ux-redesign` · **Audience:** everyone who plans work · **When to read:** before starting anything, and to find who owns a decision · **Source of truth:** this file for the list; the source document named in each row for the detail.

 One consolidated, deduplicated list of everything still open across
`docs/audit/`, `docs/ux/`, `docs/DELIVERY_REPORT.md`, `architecture/` and the design review.
Each item keeps the id of its source so the detail can be found there. Items recorded as done in
those documents are not repeated here (the "Done" lists live in `docs/audit/REMEDIATION_PLAN.md`
and `docs/audit/PRODUCTION_READINESS_PLAN.md`).

How to use this file: pick from the top of the section that matches who you are; when an item is
closed, mark it in its source document and remove it here. `CHANGELOG.md` records what shipped.

Priority: **P0** blocks production · **P1** needed before the pilot ends · **P2** next quarter ·
**P3** nice to have. Effort: S (< 1 day), M (1 to 3 days), L (1 to 2 weeks), XL (longer or
depends on third parties).

## 1. Blocking the first deployment (needs Azure, IT or a business decision)

| Id | Item | Owner | Prio | Effort | Source |
|---|---|---|---|---|---|
| SUB | Azure test subscription with rights for resource groups, private networking and Front Door Premium, plus written authorization to create resources | TI | P0 | XL | PRODUCTION_READINESS_PLAN critical path 1 |
| ENTRA | Entra registrations per environment (`pipeline-api`, `pipeline-pwa-coordinador`, `pipeline-web-admin`), app roles, `requestedAccessTokenVersion=2`, Assignment Required on the API and the admin SPA, groups `PIPELINE-Coordinadores` / `PIPELINE-Admins`, Conditional Access policies | Identidad | P0 | L | AZURE_DEPLOYMENT §2.2 |
| PARAMS | Replace the all-zero placeholder GUIDs in `infra/bicep/params/*.bicepparam` | TI then engineering | P0 | S | AZURE_DEPLOYMENT §1 |
| SQL-ADM | `PIPELINE-SQL-Admins-{env}` group, migrate identity membership, one-time `CREATE USER … FROM EXTERNAL PROVIDER` | TI | P0 | S | AZURE_DEPLOYMENT §3 |
| GRAPH | Admin consent for `User.ReadBasic.All` and `TeamsActivity.Send` on `id-pipeline-api-{env}` | Identidad | P0 | S | DELIVERY_REPORT §8 |
| OIDC | GitHub OIDC federation per environment, role assignments, `AcrPull` on the dev registry, environment secrets and variables, required reviewers | TI + engineering | P0 | M | AZURE_DEPLOYMENT §2.3 |
| BRANCH | Branch protection on `main` requiring the `ci` checks | Repo admin | P0 | S | AZURE_DEPLOYMENT §2.3 |
| DEPLOY-RUN | Run `build-deploy` for real: 0 % revision, migrate job, health, traffic shift, auto-rollback, `az acr import` (all statically validated only). First run also verifies the audit remediation that could not be exercised locally: admin SPA on its own Front Door host (INF-1), dev SPA→API through CORS and `VITE_API_BASE_URL` plus the SQL firewall and NSG rules (INF-2), control-plane promotion into a private registry (INF-3), diagnostic settings (INF-4), drift zero-change (CI-2), smoke test tenant and admin checks (CI-4) | Engineering | P0 | M | AZURE_DEPLOYMENT §11; audit ENGINEERING_AUDIT_2026-10-11 §K |
| DEFENDER | Defender for Storage plan approved and enabled; EICAR check | Seguridad + TI | P0 | M | DELIVERY_REPORT §8 |
| IMMUT | Container-level immutability and legal hold on the documents account; confirm the ADR-003 addendum with Seguridad (locking is manual and irreversible) | Seguridad + Legal | P0 | M | AZURE_DEPLOYMENT §11 |
| MI-KV | Entra-only SQL with managed-identity token and Key Vault references resolved for the API and the migrate job | Engineering + TI | P0 | M | PRODUCTION_READINESS_PLAN 3.3 |
| Pend 4/5/8 | Business catalogs: required documents, minimum fields per status, return reasons, terminal statuses. Provisional values are seeded | Negocio | P0 | S (after decision) | TO_BE Q5 |
| Pend 7 | Retention start event, legal hold, treatment of discarded sites | Legal | P0 | S (after decision) | TO_BE Q1 |
| Pend 13 | Privacy notice shown before capturing owner contact data | Legal | P0 | S (after text) | PRODUCTION_READINESS §8 |

## 2. Required before go-live (test environment exists)

| Id | Item | Owner | Prio | Effort | Source |
|---|---|---|---|---|---|
| DEVICE | Offline chain on a real Intune Android phone: 24 h offline token renewal, `loginRedirect` from the installed PWA, selective-wipe behaviour | Engineering + Intune | P0 | M | DELIVERY_REPORT §10 item 1 |
| MSAL | MSAL sign-in and token negative cases against the real tenant | Engineering + Identidad | P0 | S | PRODUCTION_READINESS_PLAN 3.2 |
| TEAMS | Publish the Teams app or adopt the Power Automate fallback (ADR-007); verify activity-feed delivery; payload carries no contact data ; then set `notifyMode = 'graph'` and `teamsAppId` in the dev/test parameter files (they run with `log` until then) | TI + Seguridad | P0 | L | TO_BE Q4 |
| FABRIC | Workspace identity, trusted workspace access, OneLake shortcut, Mirroring through the VNet gateway excluding `sitio_contacto`, `auditoria`, `operacion_idempotente`, `carga_fila_staging` | Fabric admin + Datos | P1 | L | AZURE_DEPLOYMENT §2.5 |
| FD | Front Door, WAF and Private Link origin approval; rate-limit rule verified under a burst | TI | P0 | M | AZURE_DEPLOYMENT §8 |
| AZ-6 | Restrict the direct Static Web App hostnames to Front Door | Engineering | P1 | S | AZURE_DEPLOYMENT §6 |
| AZ-4 | Confirm `TRUSTED_PROXY_HOPS` by comparing the ledger IP with the caller IP | Engineering | P1 | S | AZURE_DEPLOYMENT §4 |
| OBS | App Insights wiring, dashboards; the four Bicep alert rules (`alertEmails`) forced once each and thresholds tuned | Engineering | P0 | M | OPERATIONS "Alerts to configure" |
| RESTORE | Restore drill in Azure: PITR to a side database and repoint (the local rehearsal of backup, restore, ledger verification and RLS on the copy passed on 11 October; RB-08 has the procedure)timed against the RTO | Engineering | P0 | M | OPERATIONS "Backup and recovery" |
| PEN | Penetration test (book now, 2 to 4 weeks lead time) plus the RLS test report; an OWASP ZAP baseline against the built PWA and the API and an authenticated active API scan over the OpenAPI contract (120 URLs) found 0 failures and 0 warnings on 11 October | Seguridad | P0 | XL | PRODUCTION_READINESS_PLAN Phase 4 |
| 150MB | 150 MB resumable upload with a forced disconnect and a 150 MB download through Front Door on 4G | Engineering | P1 | S | DELIVERY_REPORT §6 |
| RNF-08 | `GET /api/v1/sitios` p95 under 3 s on 4G with the full dataset (server side p95 200 ms for 200 items; sign-in plus first list 2.5 s cold and 1.7 s warm on emulated slow 4G, 11 October; `e2e/tools/net-timing.mjs`); bulk preview under 30 s | Engineering | P1 | S | IMPLEMENTATION_STATUS |
| SIM | Azure SQL failover and Graph outage simulations in the test environment (local SQL outage rehearsed on 11 October: 503 with Retry-After, self-recovery; Graph failure path covered by the outbox tests) | Engineering | P1 | S | PRODUCTION_READINESS §8 |
| SCANS | Defender for Cloud recommendations once deployed (CI already runs pip-audit, pnpm audit, gitleaks and Trivy on the image; a local Trivy run of the production image found 0 high/critical on 11 October) | Engineering | P1 | S | PRODUCTION_READINESS §8 |
| LOG-REVIEW | Manual sample of production logs for forbidden fields | Engineering | P1 | S | PRODUCTION_READINESS §8 |
| DRIFT | Nightly `drift.yml` green against test and prod | Engineering | P1 | S | AZURE_DEPLOYMENT §8 |
| GO-LIVE | Production from the same digest and bundles, rollback rehearsal, delete locks and break-glass, go-live checklist signed, two-week pilot in one region | Engineering + Seguridad | P0 | L | PRODUCTION_READINESS_PLAN Phase 5 |
| SUPPORT | Support model (L1 TI, L2 Subdirección de IA), on-call rota, severity model, paging tool, SLO targets | TI + Subdirección | P1 | M | PRODUCTION_READINESS §1, §7 |
| P1-LIC | Entra ID P1 for group-to-role assignment, or direct user assignment as fallback | Identidad | P1 | S | RISK_REGISTER R14 |

## 3. Engineering improvements (no external dependency)

| Id | Item | Prio | Effort | Source |
|---|---|---|---|---|
| LEDGER-DIGEST | Configure external ledger digest storage so `sp_verify_database_ledger` checks against an immutable copy | P2 | S | OPERATIONS RB-08 |
| XLS-REAL | Verify `.xls` parsing with a real legacy file from the business | P2 | S | DELIVERY_REPORT §9 |
| UX-SR | Screen-reader pass (TalkBack, NVDA); the axe WCAG 2 A/AA scan runs in the two a11y e2e specs since 11 October | P1 | M | ux/UX_VALIDATION §3 |
| UX-LOGO | Replace the re-created roundel with the official vector logo and a raster icon set for the manifest | P1 (Mercadotecnia) | S | ux/DESIGN_SYSTEM §1 |
| SCHED | Local scheduler uses fixed intervals, Azure uses cron; document only (accepted) | P3 | — | DELIVERY_REPORT §9 |

Observed in code during the documentation pass of 11 October 2026 (read, not reproduced), plus
what the engineering audit of the same day left open (`docs/audit/ENGINEERING_AUDIT_2026-10-11.md`
§L has the full remediation status):

| Id | Item | Prio | Effort | Where |
|---|---|---|---|---|
| ENTREGADO | Status `entregado` is seeded as terminal but no code path assigns it; either add the admin action or drop it from the catalog once Negocio decides (pendiente Q5). Audit DAT-15 | P2 | S | `backend/app/models.py`, `transiciones/service.py` |
| FE-10 | A contact or visit queued before a transition is sent unconditionally and its new ETag is recorded as "ours", so an admin change made in between is not surfaced as a 412 on the transition. Deliberate trade-off (offline devices rarely hold a fresh ETag; the backend now honours `If-Match` on captures when sent); decide whether captures should carry `etagBase` once the pilot shows how often admins change sites mid-capture | P3 | S | `apps/pwa-coordinador/src/sync/engine.ts` |
| DAT-13b | Still unaudited write: marking a notification read (user-facing read state; outbox outcomes and the `escaneando` transition are audited since 11 October) | P3 | S | `notificaciones/service.py`, `archivos/service.py`, `jobs/outbox.py` |
| E2E-ENTRA | No automated acceptance run against an Entra-protected environment (Playwright signs in through the dev picker only) | P1 | M | `e2e/helpers/auth.ts` |

## 4. Product ideas (not in the TDD; need a business owner before any work)

| Idea | Why | Source |
|---|---|---|
| Push or Teams notice to the coordinator when a load assigns new sites | Today the coordinator discovers new sites only by opening the app | UX audit, P11 |
| Admin bulk actions on the sites table (reassign several sites at once) | Reassignment after staff changes is one site at a time | UX audit, A4 |
| Photo limits per site (10 photos × 1.5 MB proposed) | Phone storage and sync time | Propuesta A3, pendiente 6 |
| Dashboard for regional managers (Power BI on Fabric) | Out of scope for v1 by TDD 2.2 | TO_BE §1 |
| AI inspection of uploaded documents | Explicitly deferred by the TDD | TO_BE §1 |

## 5. Documentation inconsistencies

Resolved on 11 October 2026: the design documents now state the implemented health paths
(`/healthz`, `/readyz`, `/healthz/deps`), the `user` hash log field, container-level storage
immutability, the 5 % / 10 min 5xx threshold, the runbook numbering RB-01 to RB-16, and that CI
runs on GitHub while the deploy workflows have not. When a design document and the code disagree
again, the code wins and the document gets the correction in the same PR.

## 6. Pending business decisions (summary; detail in `architecture/TO_BE.md` §9–10)

| # | Decision | Decides |
|---|---|---|
| 1 | Retention start event, legal hold, discarded sites (pendiente 7) | Legal |
| 2 | Are PDFs produced in the field without signal? | Negocio |
| 3 | Fabric trusted workspace access to a private storage account | TI + Fabric admin |
| 4 | Teams app publication or Power Automate fallback | TI + Seguridad |
| 5 | Terminal statuses and their reasons | Negocio |
| 6 | Shared phones between coordinators | Negocio + Seguridad |
| 7 | CI/CD platform, team composition, RPO/RTO (pendiente 12) | TI + Negocio |
| 8 | Tables replicated to Fabric | Seguridad + Datos |
| 9 | Required document catalog (pendiente 4) | Negocio |
| 10 | Minimum fields per status (pendiente 5) | Negocio |
| 11 | Return-reason catalog (pendiente 8) | Negocio |
| 12 | Privacy notice text (pendiente 13) | Legal |
| 13 | Photo limits (pendiente 6) | Negocio |
| 14 | Meaning of the GPS column (pendiente 2) | Negocio |
| 15 | Edge for Android mandate and selective wipe (pendiente 10) | Intune |
| 16 | MSAL cache in `localStorage` | Seguridad |
| 17 | Private networking mandate (ADR-008) | Seguridad |
| 18 | Support model, on-call, SLOs | TI + Subdirección de IA |
| 19 | Formal acceptance of risks R04 and R15 | Seguridad + Negocio |

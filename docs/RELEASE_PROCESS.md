# Release process · Pipeline de Posibles Tiendas

Date: 11 October 2026 · Branch `ux-redesign` · **Audience:** whoever cuts a release or deploys ·
**When to read:** before merging to `main`, tagging, or running `build-deploy` · **Source of
truth:** `.github/workflows/*.yml` and `docs/AZURE_DEPLOYMENT.md` for the Azure procedure.

**Status, stated plainly:** CI (`ci.yml`) runs on GitHub and is green. The deploy workflows
(`build-deploy.yml`, `deploy-environment.yml`, `drift.yml`) and every Bicep template are statically
validated only; they have never run against an Azure subscription. The first real execution is
Phase 3 of `docs/audit/PRODUCTION_READINESS_PLAN.md` and will need the prerequisites in
`docs/IMPROVEMENT_BACKLOG.md` §1.

## 1. Branches and versions

| Branch | Purpose |
|---|---|
| `main` | Integration branch; a push deploys **dev** (once Azure exists). Protected: `ci` checks required (to be configured, backlog BRANCH) |
| feature branches (`prod-readiness`, `ux-redesign`, …) | One topic each; merged by pull request with CI green |
| tags `release-x.y.z` | Trigger the build and the test and prod deployments. The workflow matches `release-*`; a `v1.0.0` tag does nothing |

Semantic versioning: patch for fixes, minor for new behaviour visible to users, major for a
contract change (API, data model migration that needs coordination). `CHANGELOG.md` gets a section
per release, written at tag time from the merged pull requests.

## 2. Definition of ready to release

- `make lint`, `make test`, `pnpm -r test`, `make e2e` green locally and `ci` green on the PR.
- `docs/openapi.json` regenerated if an endpoint changed (`make openapi && pnpm gen:api`).
- Migration reviewed for expand-and-contract (`docs/DATA_MODEL.md` §6): the previous image must
  run against the new schema, because rollback is a traffic shift, never a downgrade.
- No new visible string or `data-testid` changed without its Playwright assertion.
- `CHANGELOG.md` updated; backlog items closed in their source documents.
- For infrastructure changes: `make bicep-lint` clean and a `what-if` reviewed on the target.

## 3. What the pipeline does

```text
push main ──► build-deploy ──► ci ──► build (dev env: image → Trivy → ACR, SPA bundles) ──► deploy-dev
tag release-x.y.z ───────────► ci ──► build ───────────────┬─► deploy-test
                                                           └─► deploy-prod   (required reviewers)
```

- `build` runs under the `dev` GitHub environment, builds the API image once, scans it with
  Trivy (CRITICAL, fail), pushes it to the dev registry and resolves the **digest**. The SPA bundles
  are built once with `VITE_AUTH_MODE=msal` and uploaded as the `spa-bundles` artifact.
- `deploy-test` and `deploy-prod` both depend only on `build` and both fire on the same tag.
  Production is held only by the required reviewers of the `prod` environment; there is no
  automatic "test must be green first" gate. Reviewers must check test before approving prod.
- `workflow_dispatch` with `target` and an optional `image_digest` redeploys a known image. The SPA
  bundles are rebuilt from the current checkout, so an API-only hotfix still ships whatever
  frontend is on that ref.
- `deploy-environment.yml`, per environment: import the digest into the environment's registry
  and verify it → read the revision serving traffic → `what-if` → `main.bicep` with the new image
  at **0 % traffic** → run the migrate job and wait → wait for the new revision to be healthy →
  shift 100 % → write each SPA's `config.json` from GitHub variables → deploy both SPAs → smoke
  test (`/api/v1/me` returns 401 Problem Details) → keep the two newest revisions. Any failure after
  the shift moves traffic back automatically.
- `drift.yml` runs nightly `what-if` on dev, test and prod and fails on any change.

Configuration needed in GitHub per environment: secrets `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`,
`AZURE_SUBSCRIPTION_ID` (OIDC); variables `ACR_NAME`, `RESOURCE_GROUP`, `VITE_TENANT_ID`,
`VITE_SPA_CLIENT_ID_PWA`, `VITE_SPA_CLIENT_ID_ADMIN`, `VITE_API_CLIENT_ID`, `PUBLIC_HOST`, and
dev-only `DEV_ALLOWED_INGRESS_CIDRS`.

Pipeline rules added by the audit remediation (11 October 2026):

- A `release-x.y.z` tag reuses the image digest that `main` built for the same commit (it must
  exist in the dev registry); a tag on an unbuilt commit builds and scans first.
- `deploy-prod` runs only after `deploy-test` of the same tag succeeded; a manual
  `workflow_dispatch` with `target=prod` (rollback to a known digest) skips test and is held by the
  prod environment's reviewers. The dispatch input is validated (`sha256:<hex>`).
- The smoke test refuses a placeholder `VITE_TENANT_ID`, fetches the tenant's OIDC metadata, expects a
  401 Problem Details from `/api/v1/me`, and loads the admin page plus every script it references
  on the admin Front Door host.
- Every deploy step runs with `pipefail`; the drift job resolves the serving revision and the dev
  CIDR variable exactly like the deploy, so a clean deployment yields zero changes.
- Base images are pinned by digest in `backend/Dockerfile`; bump them deliberately.

## 4. Release checklist

1. Merge the release PR into `main`; wait for `ci` and (when Azure exists) `deploy-dev`.
2. Smoke dev by hand: sign in to both apps, advance a site, return it, load a small file.
3. Write the `CHANGELOG.md` section; bump nothing else (no version files exist).
4. `git tag release-x.y.z && git push origin release-x.y.z`.
5. Watch `deploy-test`; run the post-deployment checklist (`docs/AZURE_DEPLOYMENT.md` §8).
6. Run the acceptance set on test: Playwright against test URLs (`PWA_URL`, `ADMIN_URL`,
   `API_URL`, `DEV_IDP_URL` are not applicable with Entra; the suite needs the dev user picker, so
   on test use the manual script in `docs/ux/UX_VALIDATION.md` §2 plus the backend integration
   tests pointed at a disposable database). Automating this is backlog item E2E-ENTRA.
7. Approve `deploy-prod` in GitHub (required reviewers); watch the smoke test.
8. Announce to the coordinators if the PWA changed visibly; the service worker updates on the
   next load (`registerType: autoUpdate`).
9. Tag the backlog items that shipped as done in their source documents.

## 5. Migrations in a release

- The migrate job runs before traffic moves. If it fails, the deployment stops with the old
  revision still serving; fix forward or `alembic downgrade` through the job with a restore point
  (`docs/OPERATIONS.md` RB-09).
- Data-shape changes that the old image cannot tolerate must be split across two releases
  (add column → release → backfill and switch → release → drop column).
- Catalog changes (statuses, reasons, document types) are migrations too, with their own `INSERT`.

## 6. Rollback

| Layer | Action |
|---|---|
| API | Automatic if a post-shift step fails. Manual: `az containerapp ingress traffic set -g <rg> -n ca-pipeline-api-<env> --revision-weight <previous>=100`; or `workflow_dispatch` with the previous `image_digest` |
| SPAs | Re-run `build-deploy` on the previous tag, or redeploy the previous `spa-bundles` artifact |
| Infrastructure | Revert the Bicep or parameter change, review `what-if`, redeploy |
| Database | Never automatic. Expand-and-contract makes most releases rollback-safe without touching the schema; otherwise PITR decision first (`az sql db restore`), then `alembic downgrade` through the migrate job |

A rollback is a release: write it in `CHANGELOG.md` and open a backlog item for the cause.

## 7. Known gaps in the pipeline (tracked in `docs/IMPROVEMENT_BACKLOG.md`)

- E2E-ENTRA: no automated acceptance against an Entra-protected environment.
- AZURE-FIRST-RUN: every pipeline and template change made for the audit (admin host-based
  routing, dev CORS and API base, control-plane digest promotion, diagnostics, drift parameters,
  tenant check in the smoke test, prod after test) is statically validated only; the first real
  run of `build-deploy` is the gate (backlog DEPLOY-RUN).

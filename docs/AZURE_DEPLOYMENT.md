# Azure deployment

How the approved architecture (`architecture/AZURE_DESIGN.md`, ADR-001 to ADR-010) is provisioned and
how the application is deployed to it. Nothing in this document has been executed against an Azure
subscription yet. The verification status of every item is in section 11.

## 1. What gets deployed

| Resource | Bicep module | Notes |
|---|---|---|
| Resource group `rg-pipeline-{env}` with delete lock (test, prod) | `infra/bicep/rg.bicep`, `modules/rglock.bicep` | Subscription scope |
| VNet, subnets `snet-aca`, `snet-pe`, `snet-gw`, NSGs, private DNS zones | `modules/network.bicep` | `snet-gw` is delegated for the Fabric VNet data gateway |
| Log Analytics, Application Insights | `modules/monitoring.bicep` | Daily cap and retention are parameters |
| User-assigned identities `id-pipeline-api-{env}`, `id-pipeline-migrate-{env}` | `modules/identity.bicep` | API and jobs use the first; the Alembic job uses the second |
| Key Vault (RBAC, private endpoint) | `modules/keyvault.bicep` | Holds the App Insights connection string as a Key Vault reference |
| Storage `st{env}pipelinestg` (flat, Defender scanning, lifecycle) and `st{env}pipelinedoc` (ADLS Gen2, immutability) | `modules/storage.bicep` | Shared key disabled on both |
| Azure SQL server and database (Entra-only, private endpoint, LTR, auditing) | `modules/sql.bicep` | Admin is an Entra group |
| Container Registry | `modules/acr.bicep` | Premium with private endpoint in test and prod |
| Container Apps environment, API app, six jobs | `modules/containerapps.bicep`, `modules/acadns.bicep` | Jobs: migrate, promote, outbox, expire-uploads, purge, idempotency-cleanup |
| Two Static Web Apps | `modules/staticwebapps.bicep` | PWA and admin web |
| Front Door Premium, WAF, Private Link origin | `modules/frontdoor.bicep` | Disabled in dev |
| Fabric VNet data gateway placeholder | `modules/fabricgateway.bicep` | The gateway is created in the Fabric portal |

Parameter files: `infra/bicep/params/dev.bicepparam`, `test.bicepparam`, `prod.bicepparam`. Identity
values in the parameter files are placeholders (all-zero GUIDs) until the identity team provides the
registrations.

## 2. Prerequisites

1. **Subscription and permissions.** Owner or Contributor plus User Access Administrator on the
   subscription (role assignments are part of the templates). Resource providers: `Microsoft.App`,
   `Microsoft.Cdn`, `Microsoft.Sql`, `Microsoft.Security`, `Microsoft.Web`, `Microsoft.OperationalInsights`.
2. **Entra registrations** per environment, created by the identity team from the request message in
   the Entra guide (section 8) with the ADR-006 additions:
   - `pipeline-api-{env}`: Application ID URI `api://<client id>`, scope `access_as_user`, app roles
     `Coordinador` and `Admin`, `requestedAccessTokenVersion = 2`, Assignment Required = Yes.
   - `pipeline-pwa-coordinador-{env}` and `pipeline-web-admin-{env}`: SPA platform, redirect URIs from
     section 7, delegated permission `access_as_user` with admin consent. Assignment Required = Yes on
     the admin SPA with only `PIPELINE-Admins` assigned.
   - Groups `PIPELINE-Coordinadores` and `PIPELINE-Admins` assigned to the roles (needs Entra ID P1;
     fallback is direct user assignment).
   - Group `PIPELINE-SQL-Admins-{env}`: SQL server administrator. Add the managed identity
     `id-pipeline-migrate-{env}` to this group after the first deployment creates it.
   - Graph application permissions for `id-pipeline-api-{env}`: `User.ReadBasic.All` (equivalence
     resolution) and `TeamsActivity.Send` (notifications), granted by a Global or Privileged Role admin.
   - Conditional Access policies A and B from `architecture/AZURE_DESIGN.md` section 4.
3. **GitHub OIDC federation.** One Entra application (or user-assigned identity) per environment with a
   federated credential for the GitHub environment:

   ```bash
   APP=$(az ad app create --display-name "github-pipeline-$ENV" --query appId -o tsv)
   az ad sp create --id "$APP"
   az ad app federated-credential create --id "$APP" --parameters "{
     \"name\": \"github-$ENV\",
     \"issuer\": \"https://token.actions.githubusercontent.com\",
     \"subject\": \"repo:kurte32/ade_pipe:environment:$ENV\",
     \"audiences\": [\"api://AzureADTokenExchange\"]
   }"
   az role assignment create --assignee "$APP" --role Contributor --scope "/subscriptions/$SUB/resourceGroups/rg-pipeline-$ENV"
   az role assignment create --assignee "$APP" --role "User Access Administrator" --scope "/subscriptions/$SUB/resourceGroups/rg-pipeline-$ENV"
   az role assignment create --assignee "$APP" --role AcrPush --scope "<acr resource id>"   # after ACR exists
   ```

   For `test` and `prod`, the principal also needs `AcrPull` on the **dev** registry: deployments
   import the exact dev-built digest with `az acr import` instead of rebuilding.

   GitHub environment secrets: `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`. Variables:
   `ACR_NAME`, `RESOURCE_GROUP`, `VITE_TENANT_ID`, `VITE_API_CLIENT_ID`, `VITE_SPA_CLIENT_ID_PWA`,
   `VITE_SPA_CLIENT_ID_ADMIN`, `PUBLIC_HOST`, and for `dev` only `DEV_ALLOWED_INGRESS_CIDRS`
   (comma-separated office/VPN ranges; when unset the dev API admits nothing from outside). The four
   `VITE_*` values are written into each SPA's `config.json` at deploy time; they are not compiled
   into the bundles. Required reviewers on `test` and `prod`.

   Repository settings (manual, not in code): branch protection on `main` requiring the `ci`
   checks to pass before merge. `build-deploy` additionally runs CI as its first job and will not
   build or deploy when it fails.
4. **Defender for Storage** plan available in the subscription (per-storage-account enablement is in the
   template; the plan and its cost must be approved by Seguridad and TI).
5. **Fabric**: workspace with capacity, workspace identity, and tenant settings for trusted workspace
   access (TO_BE.md open question 3). Record the workspace identity object id in the parameter file
   (`fabricWorkspaceIdentityPrincipalId`).
6. **Tooling**: Azure CLI 2.60 or later, Bicep CLI 0.30 or later (`az bicep install`), `jq`.

## 3. First deployment of an environment

```bash
ENV=dev            # dev | test | prod
LOCATION=mexicocentral   # or the corporate default region
SUB=$(az account show --query id -o tsv)

# 1. Resource group (+ lock for test/prod)
az deployment sub create -l "$LOCATION" -f infra/bicep/rg.bicep -p env=$ENV location=$LOCATION

# 2. Fill the parameter file: tenant id, client ids, SQL admin group, Fabric identity, public URL.
#    Keep apiImage as the quickstart image for the very first run (the API container will fail
#    health checks until the real image is pushed; that is expected).

# 3. Infrastructure
az deployment group create -g rg-pipeline-$ENV -f infra/bicep/main.bicep -p infra/bicep/params/$ENV.bicepparam

# 4. One-time SQL bootstrap as a member of the SQL admin group (needs network access to the private
#    endpoint, e.g. from a jump host or a temporary firewall rule in dev):
#    CREATE USER [id-pipeline-api-$ENV] FROM EXTERNAL PROVIDER;
#    The migration job later adds this user to role pipeline_app_role.

# 5. Add id-pipeline-migrate-$ENV to the PIPELINE-SQL-Admins-$ENV group (identity team).

# 6. Push the first image and deploy through GitHub Actions (build-deploy.yml) or manually:
az acr login -n <acr name>
docker build -t <acr>.azurecr.io/pipeline-api:bootstrap backend && docker push <acr>.azurecr.io/pipeline-api:bootstrap
DIGEST=$(az acr repository show -n <acr name> --image pipeline-api:bootstrap --query digest -o tsv)
az deployment group create -g rg-pipeline-$ENV -f infra/bicep/main.bicep -p infra/bicep/params/$ENV.bicepparam -p apiImage=<acr>.azurecr.io/pipeline-api@$DIGEST

# 7. Migration
az containerapp job start -g rg-pipeline-$ENV -n caj-pipeline-migrate-$ENV

# 8. Static Web Apps: deploy the bundles (the workflow does this with the deployment token).
```

Afterwards every change goes through `build-deploy.yml`: push to `main` deploys `dev`; a
`release-x.y.z` tag deploys `test` and then `prod` after reviewer approval.

## 4. Configuration flow

```
infra/bicep/params/<env>.bicepparam
  -> main.bicep parameters
    -> modules/containerapps.bicep `commonEnv`
      -> container environment variables (API app and every job)
        -> backend/app/core/config.py Settings (pydantic-settings)
```

Production-only values are fixed in the template (`AUTH_MODE=entra`, `DB_AUTH=entra`,
`STORAGE_MODE=azure`, `SCAN_MODE=defender`, `NOTIFY_MODE=graph`, `DIRECTORY_MODE=graph`). The
application refuses to start otherwise when `ENVIRONMENT=production`. `AZURE_CLIENT_ID` selects the
user-assigned identity for `DefaultAzureCredential`. The App Insights connection string is a Key Vault
reference resolved by the Container Apps platform with each app's or job's own identity; both the
API identity and the migration identity hold Key Vault Secrets User.

`TRUSTED_PROXY_HOPS` is set from `deployFrontDoor` (2 with Front Door, 1 without) and decides which
`X-Forwarded-For` entry is recorded as the client address in the audit ledger. Confirm the real hop
count in the test environment by comparing a request's ledger IP with the caller's address.

The SPAs are built once, environment-neutral (`VITE_AUTH_MODE=msal` only). At startup they read
`<base>/config.json`, which the deployment writes per environment. Only the tenant and client ids can
come from that file; the auth mode stays compile-time, so a deployed file cannot enable the dev
sign-in. Without the file a production bundle refuses to start.

## 5. Deployment order and migration job

`deploy-environment.yml` runs, per environment:

1. Import the digest into the environment's registry when it differs from the build registry, and
   verify the digest after import.
2. Read the revision serving traffic now and pass it as `trafficRevision`, so the Bicep deployment
   creates the new revision with **0%** traffic (on the very first deployment there is no previous
   revision and the new one takes all traffic).
3. Run the migration job and wait for it.
4. Wait until the new revision reports `Healthy`, then shift 100% of traffic to it.
5. Write each SPA's `config.json`, deploy both SPAs, run the smoke test.
6. If any step after the shift fails, traffic is moved back to the previous revision automatically.


`caj-pipeline-migrate-{env}` runs `alembic upgrade head` from the same image as the API, with the
migration identity (`AZURE_CLIENT_ID` of `id-pipeline-migrate-{env}`) and `DB_USER` set to the API
identity name so the baseline migration adds it to `pipeline_app_role`. Migrations are
expand-and-contract: a new revision must work with the previous image, so rollback is a redeploy of
the previous digest, never an automatic downgrade.

## 6. Static Web Apps

Both apps are deployed as prebuilt bundles (`skip_app_build: true`). The admin app is routed at
`/admin/*` through Front Door, so it must be built with Vite `base: "/admin/"` (frontend concern).
Direct SWA hostnames remain reachable; in production restrict them to Front Door with SWA
`networking.allowedIpRanges` set to the Front Door backend ranges or use SWA private endpoints
(Standard SKU). This restriction is not in the template yet.

## 7. Front Door host and redirect URIs

| Environment | Public host | Redirect URIs to register |
|---|---|---|
| dev | `https://swa-pipeline-pwa-dev.azurestaticapps.net` (no Front Door) | that host, `https://swa-pipeline-admin-dev.azurestaticapps.net`, `http://localhost:5173`, `http://localhost:5174` |
| test | `https://pipeline-test-<hash>.z01.azurefd.net` (output `frontDoorHostname`) | `https://<host>/`, `https://<host>/admin/` |
| prod | custom domain on Front Door (to be defined by TI) | `https://<domain>/`, `https://<domain>/admin/` |

Update `appPublicUrl` in the parameter file once the host is known; it is used in Teams notification links.

## 8. Verification checklist after a deployment

- [ ] `az deployment group show` succeeded and `what-if` on the same parameters reports no changes.
- [ ] Container app revision healthy; `/healthz` and `/readyz` pass (readiness checks SQL and both containers).
- [ ] Migration job execution `Succeeded`; `SELECT * FROM alembic_version` shows the expected revision.
- [ ] `GET https://<host>/api/v1/me` without a token returns 401 Problem Details (smoke test in the workflow).
- [ ] Sign-in from the PWA with a `PIPELINE-Coordinadores` user returns `/api/v1/me` with role `Coordinador`.
- [ ] Defender for Storage: uploading the EICAR test file to `staging` produces the `Malicious` index tag and the file is never promoted.
- [ ] Documents container: `az storage container immutability-policy show` reports the configured period; deleting a promoted blob fails.
- [ ] Fabric: the OneLake shortcut to `st{env}pipelinedoc/documents` lists `pipeline/` and Mirroring shows only the selected tables.
- [ ] Front Door: WAF policy attached, Private Link origin approved (`az network private-endpoint-connection list` on the managed environment), routes healthy.
- [ ] Log Analytics receives `SQLSecurityAuditEvents` and container console logs; App Insights shows requests with correlation ids.
- [ ] Nightly `drift.yml` is green.

## 9. Rollback

- **API**: the container app runs in multiple-revision mode and each deployment keeps the previous
  revision active. A failure after the traffic shift restores the previous revision automatically
  (step 6 above); otherwise roll back with
  `az containerapp ingress traffic set -g <rg> -n ca-pipeline-api-<env> --revision-weight <previous>=100`
  (the previous revision name is printed by the "Revision serving traffic now" step). Migrations are
  expand-and-contract, so the previous revision runs against the new schema. If the previous
  revision was deactivated, re-run `build-deploy` with `workflow_dispatch`, `target=<env>` and
  `image_digest=<previous digest>`.
- **Infrastructure**: revert the Bicep or parameter change and redeploy; `what-if` shows the reverse delta first.
- **Database**: never downgrade in production automatically. If a migration must be reverted, run a
  manual `alembic downgrade <rev>` through the migration job with an overridden command, after a
  point-in-time restore decision (`az sql db restore`).
- **Static Web Apps**: redeploy the previous bundle artifact (artifacts are retained by GitHub for the
  configured period).

## 10. Teardown

`dev`: `az group delete -n rg-pipeline-dev`. `test` and `prod`: remove the delete lock (`az lock delete`),
break any legal hold, wait for the immutability period or accept that immutable blobs block the
storage account deletion, then delete the group. Key Vault has purge protection: the name stays
reserved for 90 days.

## 11. Verification status

| Item | Status |
|---|---|
| All Bicep modules and parameter files build and lint | statically validated (`bash infra/bicep/validate.sh`, Bicep 0.48.1) |
| GitHub workflows | statically validated (actionlint 1.7.12 clean locally and as a CI job; every action pinned to a commit SHA; Bicep CLI pinned with a checksum). Never executed on GitHub. |
| Deployment order (0% revision, migrate, health, shift, automatic rollback) | statically validated; not verified in Azure |
| Image digest promotion with `az acr import`; per-environment SPA `config.json` | runtime config verified locally in a production build; import not verified in Azure |
| Resource deployment to a subscription | not verified in Azure |
| Front Door Private Link origin approval to Container Apps | not verified in Azure |
| Defender for Storage on-upload scanning and index tags | not verified in Azure |
| Container-level immutability on an HNS account and legal hold | not verified in Azure (ADR-003 lists version-level immutability; version-level requires blob versioning, which is not available with hierarchical namespace, so the template uses container-level time-based retention; confirm with Seguridad) |
| Fabric trusted workspace access and OneLake shortcut | not verified in Azure |
| Mirroring through the VNet data gateway | not verified in Azure |
| Entra-only SQL with managed identity token from the API | not verified in Azure (local uses SQL authentication) |
| Key Vault reference resolution in Container Apps | not verified in Azure |
| OIDC federation and workflow permissions | not verified (no repository secrets configured) |

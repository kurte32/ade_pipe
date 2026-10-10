# Documentation corrections

Claims in the existing documentation that the audit found inaccurate, with the correction. The two
most material (clean-clone and the concurrency control) are corrected in the findings-commit alongside
this document; the rest are listed for the next docs pass.

| Doc / location | Current claim | Reality | Correction |
|---|---|---|---|
| README, LOCAL_DEVELOPMENT, DELIVERY_REPORT | "verified from a clean clone / clean state" | `.env.example` is untracked, so a real clone fails at step one (D-01) | Track `.env.example`; keep the claim only once a temp-clone smoke test passes |
| DELIVERY_REPORT / IMPLEMENTATION_STATUS | ETag/rowversion gives optimistic concurrency (412 on conflict) | The check is in Python, not the UPDATE; concurrent same-ETag writes all commit (B-01) | State the control as fixed only after the `version_id_col` fix is verified |
| OPERATIONS.md:92 | Documents store has "versioning" | `storage.bicep` never enables blob versioning (off on the HNS account); container immutability is used instead (D-10) | Remove "versioning"; say container-level immutability |
| OPERATIONS.md:75 (RB-08) | Swap the DB connection "Container App secret or Key Vault reference"; verify with `sp_verify_database_ledger` | `DB_HOST`/`DB_NAME` are plain env vars; the same doc says ledger digest storage is not configured | Fix the connection-swap wording; drop or caveat the ledger-verify step |
| DELIVERY_REPORT.md:74 | `pnpm audit --audit-level moderate` | `ci.yml:130` enforces `--audit-level high` (weaker) | Align the report with the workflow, or tighten the workflow |
| ENVIRONMENTS.md:57-58 | Dev uses `.env.local` per app | Tracked files are `apps/*/.env.development` | Correct the filename |
| IMPLEMENTATION_STATUS.md | Infra rows and "actionlint clean" | Infra rows use neither verification vocabulary; actionlint not reproducible here; the deploy workflows labelled "statically validated" contain D-02/D-04/D-05 defects | Normalise the vocabulary; note that "statically validated" means compile/lint only and does not imply the deploy path works |
| AZURE_DEPLOYMENT.md:127 | Key Vault refs resolve "with the API identity" | Each job is passed its own identity; the migrate identity has no vault access (D-02) | Correct to per-job identity and fix the grant |
| TO_BE.md §5 | `coordinador_oid` on child tables is "checked by a trigger" | No trigger exists in the baseline migration (B-07) | Add the trigger or remove the claim |
| README.md:10 vs LOCAL_DEVELOPMENT.md:23 | "10 dev coordinators" vs "10 equivalences" | Both seed facts are true but worded inconsistently | Make the seed description consistent |

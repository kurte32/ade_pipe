# Documentation hub · Pipeline de Posibles Tiendas

Start here. Every document in the repository, by the question it answers. Dates in each file say
when it was last verified; when two documents disagree, the one marked "Source of truth" in its
header wins, and `IMPROVEMENT_BACKLOG.md` §5 lists the known disagreements.

## If you need to…

| …then read | File |
|---|---|
| Run the stack on your machine | `LOCAL_DEVELOPMENT.md` |
| Understand the code, add an endpoint, a page, a job or a migration | `DEVELOPER_GUIDE.md`, `CONVENTIONS.md`, `DATA_MODEL.md` |
| Call the API or reproduce a problem with `curl` | `API_GUIDE.md`, `openapi.json` |
| Help a coordinator or the administrator with a problem | `SUPPORT_GUIDE.md`, then `OPERATIONS.md` |
| Operate the platform: health, logs, jobs, runbooks, backups, alerts | `OPERATIONS.md`, `architecture/PRODUCTION_READINESS.md` |
| Deploy to Azure for the first time or on a release | `RELEASE_PROCESS.md`, `AZURE_DEPLOYMENT.md`, `ENVIRONMENTS.md` |
| Know what is still open, who owns it and what to do next | `IMPROVEMENT_BACKLOG.md` |
| Decide whether the software is ready to deploy, and what the first deployment must verify | `RELEASE_READINESS.md` |
| Know what shipped and when | `../CHANGELOG.md` |
| Decode a Spanish domain term or a code identifier | `GLOSSARY.md` |
| See what was built and verified, requirement by requirement | `IMPLEMENTATION_STATUS.md`, `DELIVERY_REPORT.md` |
| Understand the design: why these services, flows, decisions | `../architecture/TO_BE.md`, `../architecture/AZURE_DESIGN.md`, `../architecture/SECURITY.md`, `../architecture/ADR/` |
| Read the independent audit and its remediation | `audit/README.md` (executive report, findings, security, risks, plans) |
| Understand the brand, the design system and the UX validation | `ux/DESIGN_SYSTEM.md`, `ux/UX_AUDIT.md`, `ux/UX_VALIDATION.md` |
| Read the original business documents | `../TDD_Pipeline_Tiendas_v0.1.pdf`, `../Propuesta_mejoras_TDD_v0.1.md`, `../Guia_Integracion_Entra_ID_React_FastAPI.pdf` |

## Reading paths

**New engineer, first day.** `../README.md` → `DEVELOPER_GUIDE.md` §1–4 → `CONVENTIONS.md` →
`GLOSSARY.md` → run the stack with `LOCAL_DEVELOPMENT.md` → `API_GUIDE.md` → skim
`../architecture/TO_BE.md` §1–6 → `ux/DESIGN_SYSTEM.md` before touching a screen.

**L1 / L2 support.** `SUPPORT_GUIDE.md` (symptom tables and the trace path) → `OPERATIONS.md`
runbooks → `DATA_MODEL.md` §5 queries → `GLOSSARY.md`.

**Release manager.** `RELEASE_PROCESS.md` → `AZURE_DEPLOYMENT.md` (first deployment, order,
rollback, verification checklist) → `ENVIRONMENTS.md` → `IMPROVEMENT_BACKLOG.md` §1 for what still
blocks the first deployment.

**Architect or business owner.** `../architecture/README.md` → `TO_BE.md` §9–10 (assumptions and
open questions) → `IMPROVEMENT_BACKLOG.md` §6 (decisions pending, with owners) →
`audit/EXECUTIVE_AUDIT_REPORT.md` → `audit/PRODUCTION_READINESS_PLAN.md`.

## Conventions for these documents

- English prose, Spanish domain nouns verbatim, UI strings quoted in Spanish.
- Each guide opens with date, branch, audience, when to read, and its source of truth.
- Facts are stated with their status: verified locally, statically validated, or not verified in
  Azure. Nothing is described as running in Azure until it has.
- Keep documents current in the same pull request as the change; `IMPROVEMENT_BACKLOG.md` is the
  only to-do list, `../CHANGELOG.md` the only history.

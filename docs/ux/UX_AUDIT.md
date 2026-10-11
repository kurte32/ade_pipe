# UX audit · Pipeline de Posibles Tiendas

Date: 11 October 2026. Branch `ux-redesign` (from `prod-readiness`). Scope: the coordinator PWA
(`apps/pwa-coordinador`) and the admin web (`apps/web-admin`), audited against the Tiendas 3B brand
(see `DESIGN_SYSTEM.md`), WCAG 2.2 AA and the operational workflows in `architecture/TO_BE.md`.

How the audit was done:

- Source review of every page and shared component (about 7,000 lines across `apps/` and `packages/`).
- Live exploration in Chrome (Claude in Chrome extension) of both apps against the local stack
  (`make up`, `make db-seed`, `pnpm dev`), signed in as coordinator `ard` and as `adm`.
- Systematic screenshots of every screen at 390 × 844 (phone) and 1366 × 900 (desktop) with
  `e2e/tools/screenshots.mjs` (Playwright Chromium). The Chrome extension could not resize the
  window below the screen bounds and its screenshot channel timed out on background tabs, so the
  phone-width evidence comes from Playwright.

Users and tasks (from the TDD and `architecture/TO_BE.md` section 1):

| Role | Device | Frequent tasks | High-impact actions |
|---|---|---|---|
| Coordinador regional (10 users) | Intune Android phone, often without signal | Open an assigned site, capture owner contact, capture measurements, take photos, upload the four PDFs, advance the status | Advance status (irreversible without the admin), propose discard |
| Administrador (1 user) | Desktop browser | Load a CSV/XLSX, decide warnings, confirm the load; review sites that need a decision; return a site with a reason; reassign; keep the equivalence table; consult the audit log | Confirm load (writes sites), return, discard, reassign |

## 1. Strengths worth keeping

- **Offline-first mechanics are solid and visible**: queue of pending operations, "pendiente de
  sincronizar" markers, conflict panel with "Reintentar con el estado actual" and "Descartar cambio
  local", session-expired banner. These are rare in internal tools and must survive the redesign.
- **Transition guard rails exist**: the PWA mirrors the backend rules (`precheck`) and tells the
  coordinator what is missing before letting them advance.
- **Forms are labelled** (`label for`), inputs use the right `type`/`inputMode`, touch targets are
  44 px, errors use `role="alert"`, loading uses `role="status"`.
- **Admin dialogs** already handle the stale-ETag (412) case with a clear message.
- **Consistent Spanish copy**, Mexico City time formatting, no absolute URLs, typed API client.
- **Density is reasonable on desktop**: tables for sites, loads, audit; `dl` for site facts.

## 2. Findings

Severity: **S1** blocks or seriously slows a frequent task · **S2** causes errors, confusion or
rework · **S3** polish and consistency. Priority order is by user impact, not aesthetics.

### Cross-cutting

| # | Finding | Where | Impact | Sev |
|---|---|---|---|---|
| X1 | No brand identity: generic blue (`#0a5fd6`), system font, a house icon, no product mark. The apps are not recognisable as Tiendas 3B. | Both shells, sign-in, manifest, favicon | Low trust in a tool coordinators are asked to use in the field; two apps that do not look like one product | S2 |
| X2 | Only 11 CSS custom properties; spacing, colours and sizes are repeated inline (`style={{ marginTop: 12 }}` and similar in 20+ places). Every later change is a scavenger hunt. | `base.css`, `admin.css`, inline styles | Inconsistent spacing; no single place to tune the design | S2 |
| X3 | Raw enum codes shown to users: load state `vista_previa`/`confirmado`, history `tipo` `devolucion`/`carga`, history `origen`, row result `ok`/`advertencia`, return reason codes (`calidad_datos`) on the admin detail. | Admin Cargas, CargaDetail, SitioDetail | Terminology a new user has to decode | S2 |
| X4 | No visible keyboard focus beyond the browser default; file inputs are 1 × 1 px with `opacity: 0`, so a keyboard user tabs into an invisible control. | Both apps, FotosSection, DocumentosSection | WCAG 2.4.7 / 2.4.11 failures for keyboard users | S2 |
| X5 | Modal has no focus trap and does not return focus; backdrop click closes a form mid-edit. | `web-admin/components/Modal` | Keyboard and screen-reader users lose their place; accidental data loss | S2 |
| X6 | Nav has no current-page indicator in the PWA (the `.active` rule lives only in `admin.css`); the PWA footer repeats an `inicio` link. | PWA shell | Users cannot tell where they are | S3 |
| X7 | `document.title` is static; browser history and tabs all read "Pipeline de Posibles Tiendas". | Both | Harder to find the right tab, worse screen-reader orientation | S3 |
| X8 | No `prefers-reduced-motion` handling (spinner only), no skip link. | Both | WCAG 2.3.3 (AAA, but cheap) and 2.4.1 | S3 |
| X9 | Status badge "falta" and "requiere atención" use the danger red for ordinary states, so a site with four missing documents reads as four alarms. | PWA detail, list | Real problems (devuelto, conflicts) no longer stand out | S2 |
| X10 | Sign-in screens are bare: no logo, no explanation of what the app is for, dev user list looks like production UI. | `packages/auth` SignIn | First impression; MSAL variant is a single unlabeled page | S3 |

### Coordinator PWA (phone, offline)

| # | Finding | Where | Impact | Sev |
|---|---|---|---|---|
| P1 | **The list does not say what needs doing.** Every site shows name, id, region and status; nothing says "returned by the admin, fix the phone" or "contact pending". Returned and blocked sites are mixed with the rest. | `MisSitios` | Coordinator opens sites one by one to find work; returned sites (the only thing the admin asks for) are easy to miss | S1 |
| P2 | Filter card (search field + full-width select) takes the first 40 % of a phone screen before the first site appears. | `MisSitios` | One extra scroll on every visit | S2 |
| P3 | **Detail page shows everything always**: contact form, measurements form, photos, four document rows and history on one long scroll (about 2,600 px on a phone) regardless of the current stage. The captured contact is rendered as a one-line summary *and* as an editable form. | `SitioDetalle` | Cognitive load; the next action is not obvious; scrolling past empty forms | S1 |
| P4 | The primary action ("Avanzar a …") is at the top, disabled, with a bullet list of missing items that is not linked to the sections where the items are captured. | `SitioDetalle` | A new user does not know what to do to enable the button | S1 |
| P5 | No stage indicator: the pipeline has four ordered stages but the UI shows only a status chip. | `SitioDetalle`, `MisSitios` | Users cannot see progress or what comes next | S2 |
| P6 | "Proponer descarte" (secondary outlined button) sits directly under the primary action with the same visual weight. | `SitioDetalle` | Risk of tapping the wrong one; descarte is rare | S2 |
| P7 | Meta line is an unbroken string: `#566 · Xalapa · potencial Sin estatus · campos 13/24 · origen 20 jul 2026, 11:54 a.m.`. "potencial Sin estatus" reads like a bug (it is a legitimate catalog value). Coordinates are plain text although the coordinator has to drive there. | `SitioDetalle` | Scanning; no way to open the location in a map | S2 |
| P8 | Sync state is split between a header button ("Sincronizar ahora"), three stacked banners and a tiny footer line. The banner for "server not responding" and "session expired" look identical to the offline banner. | `Shell` | Users cannot tell at a glance whether their captures are safe | S2 |
| P9 | Feedback after save is a small orange sentence ("Contacto enviado.") that stays until the next action; no success colour, no dismissal. | `SitioDetalle` flash | Weak confirmation of a consequential action | S3 |
| P10 | Document rows: a red "falta" chip for every missing PDF, a blue "Subir PDF" label styled as a primary button four times in a row, no explanation that uploads need signal until you are offline. | `DocumentosSection` | Visual noise; the one truly blocked state (offline) is not distinct | S2 |
| P11 | Empty states are a single muted sentence ("No tienes avisos.", "No tienes sitios asignados"). | `MisSitios`, `Notificaciones` | Missed chance to explain what the screen is for and what to do | S3 |
| P12 | Stale local cache has no recovery path except "Salir", which is not described as "borrar datos locales y volver a sincronizar". Observed during the audit: a Chrome profile whose IndexedDB predated a database reset showed site 1 as "Primera visita" with a contact while the server had it as "Sitio Prospectado". | `Shell`, sync engine | Rare in production, but when it happens the user has no idea | S3 |
| P13 | The sign-in filter hides nothing on a phone, but the `.signin` class has no styles; the title and the user list run edge to edge. | `SignIn` | Polish | S3 |

### Admin web (desktop)

| # | Finding | Where | Impact | Sev |
|---|---|---|---|---|
| A1 | **"Resumen" is a dashboard of six status counters (four of them zero) followed by two lists.** The things that need the admin's attention (sites waiting for a decision, loads left in preview, sites returned and not yet corrected) are either below the fold or absent. | `Resumen` | The admin's daily question "what do I have to do?" is not answered on the landing page | S1 |
| A2 | **Load preview has five same-weight buttons in a row** (Aprobar todas · Excluir todas · Guardar decisiones · Confirmar carga · Cancelar) with the destructive "Cancelar" in red right next to "Confirmar carga". Confirming requires two clicks (save decisions, then confirm) and the reason the confirm button is disabled is only a `title` tooltip. | `CargaDetail` | Risk of cancelling a reviewed load; extra step on every load | S1 |
| A3 | Load preview table: motivo codes in monospace (`nombre_sospechoso`) before the message; "Acción" column shows `insertar`/`actualizar`; the "Mostrar" filter is a full-width select with no counts. | `CargaDetail` | Slower review of warnings | S2 |
| A4 | Sites table: coordinator shown as a three-letter code only; "Campos 13/24" unexplained; no result count; filters apply only after pressing "Filtrar" even for the selects; on a phone the table collapses to one word per line. | `Sitios` | Slower lookup; no sense of the size of a filtered set | S2 |
| A5 | Site detail: three top actions with no context ("Devolver" disabled with a tooltip only), coordinator rendered as `ard a0000000-0000-4000-8000-000000000001`, "GPS (sin interpretar)", history columns `tipo` and `origen` in raw codes. | `SitioDetail` | Noise for the admin, raw identifiers on screen | S2 |
| A6 | Dialogs: "Descartar" uses the return-reason catalog (correct by backend contract) but says nothing about consequences beyond one sentence; "Devolver" does not show which coordinator will be notified. | `SitioDetail` dialogs | Consequential actions without enough context | S2 |
| A7 | Equivalences: the `oid` column prints 36-character GUIDs for every row; the only signal that matters (resolved or not) is buried in it. There is no "unsaved changes" state; "Guardar" is always enabled. | `Equivalencias` | Harder to spot the one unresolved row; accidental no-op saves | S2 |
| A8 | Audit log: the "Usuario" column is the first 8 characters of an oid; actions and entities are free-text filters with placeholder hints only. | `Auditoria` | The admin cannot tell who did what without a lookup | S2 |
| A9 | Loads list: state in raw codes, eight columns with "Resultado" as a long sentence; a load left in `vista_previa` (needs a decision) is not highlighted. | `Cargas` | Unfinished loads go unnoticed | S2 |
| A10 | Phone layout of the admin is not usable (tables wrap into single-word cells). Admin is desktop-first by design, but a tablet or a phone check of a load should not break. | All admin tables | Secondary device support | S3 |

### Accessibility and responsive summary

- Contrast: the current palette passes AA for text (primary `#0a5fd6` on white 5.9:1, muted
  `#5b6470` on `#f6f7f9` 5.3:1). The redesign must keep AA for every token pair; see the contrast
  table in `DESIGN_SYSTEM.md`.
- Keyboard: no visible focus style (X4), no focus trap in dialogs (X5), hidden file inputs (X4),
  disabled buttons that explain themselves only by `title` (A2, A5).
- Screen readers: landmarks exist (`header`, `nav aria-label`, `main`, `footer`); headings are
  hierarchical; tables lack `scope`; the status badge has no text alternative for its colour (it
  carries the label, so this is acceptable).
- Responsive: the PWA works at 390 px; admin tables need horizontal scrolling with minimum column
  widths rather than wrapping (A10).

## 3. Prioritised plan

| Priority | Items | Why first |
|---|---|---|
| 1 | X1, X2 (tokens and shared shell), P1, P3, P4, P5 | Brand and tokens shift every screen at once; the coordinator's list and detail are the most frequent screens in the product |
| 2 | A1, A2, A3, A9 | The admin's daily entry point and the business-critical load workflow |
| 3 | X3, X4, X5, X9, P6 to P10, A4 to A8 | Terminology, accessibility, dialogs, density |
| 4 | X6 to X8, X10, P11 to P13, A10 | Polish and secondary devices |

Recommended improvements per item are implemented in the redesign and recorded in
`UX_VALIDATION.md` (what changed, what was verified, what remains).

## 4. Assumptions recorded

- The four pipeline statuses, the terminal statuses, the document catalog and the return reasons
  are business catalogs served by the API; the UI translates codes to the catalog names and never
  invents new ones.
- "Potencial" values (`Muy alto`, `Alto`, `Medio`, `Bajo`, `Sin estatus`) come from the load file;
  `Sin estatus` is shown as "Potencial: sin definir" to avoid reading like an error. The stored
  value is untouched.
- Confirming a load with unsaved decisions saves them first and then confirms, using the two
  existing endpoints in sequence. No API change.
- The admin's attention queues on the landing page are computed from the first 200 sites returned
  by `GET /api/v1/sitios`, the same cap the previous "Resumen" used. A server-side filter would be
  needed above that volume; documented as a follow-up.

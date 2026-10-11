# UX validation · Pipeline de Posibles Tiendas

Date: 11 October 2026. Branch `ux-redesign`. Companion to `UX_AUDIT.md` (findings) and
`DESIGN_SYSTEM.md` (decisions). This file records what was changed, how it was verified, and what
is still open. Verified results and untested areas are kept apart.

## 1. What changed

### Shared (`packages/ui`, `packages/auth`)

- Design tokens and base styles (`base.css`): Tiendas 3B palette (brand red, green-black ink,
  storefront green for completion), self-hosted Montserrat for structure, system font for data,
  spacing and radius scales, focus ring, reduced-motion handling, skip link, table and form styles.
- New components: `AppBar` (brand roundel, product name, area, nav with `aria-current`, right
  slot), `PageHeader`, `Alert` (tones, banner mode, `role` by tone), `EmptyState`, `Field`
  (label/hint/error wired with `aria-describedby`), `Modal` (focus trap, focus restore, Escape,
  optional backdrop dismissal), `StageIndicator`, `Icon` (inline SVG set), `BrandMark`/`Brand`,
  `usePageTitle`, and label maps for every code the API returns (`labels.ts`).
- `EstatusBadge` keeps its API and classes (`badge`, `badge-devuelto`) and gains a tone per stage.
- `ProblemAlert` renders through `Alert`; `Spinner` respects reduced motion.
- Sign-in screen accepts a brand block and a one-sentence purpose; same picker, same test ids.
- App icons, manifest and `theme-color` now use the brand roundel and red.

### Coordinator PWA

| Audit item | Change |
|---|---|
| P1, P5 | Site list groups **"Requieren tu atención"** (returned by the admin, or with blocked local changes) above the rest, shows the return reason inline, and prints the next action for every site ("Localiza al dueño y captura su contacto"). |
| P2 | Filter card replaced by a compact search field and status chips with counts. |
| P3 | Captured contact and measurements are shown as summaries with "Editar"; the form opens in place. |
| P4 | New **"Siguiente paso"** card: a checklist of what the next stage needs, each item linking to its section, and the advance button directly below it. The card is highlighted when the advance is available. |
| P6 | "Proponer descarte" moved to a collapsed "Más acciones" block at the end, outlined red with an explanation. |
| P7 | Metadata as labelled pairs; "Sin estatus" potential shown as "Sin definir"; coordinates link to a map; the phone number is a `tel:` link. |
| P8 | Sync state is one chip in the app bar (Al día / Sin señal · n por enviar / n requieren atención / Sincronizando) that also triggers a sync; banners use the shared `Alert` with distinct tones and icons; the footer keeps the last sync time. |
| P9 | Feedback after save is a green success alert naming the action, dismissible. |
| P10 | Documents are a compact list with "n de 4", neutral "falta" tags, outlined upload buttons, and a single offline notice. |
| P11 | Empty states explain what the screen will show and how to get there. |
| X4 | File inputs are real, keyboard-focusable controls overlaying a styled button (`.file-button`), with a visible focus ring. |
| X7 | Document titles per page. |
| Forms | Per-field validation messages next to the field, first invalid field focused, hints for phone format and calculated area. |

### Admin web

| Audit item | Change |
|---|---|
| A1 | "Resumen" opens with three attention queues (sites in review, loads left in preview, returned sites not yet corrected) with direct links, then a compact pipeline funnel and the latest loads. The six-card KPI grid is gone. |
| A2 | Load preview: numbered steps, a sticky action bar with one primary action ("Confirmar carga"), "Cancelar carga" behind a confirmation dialog, and an explicit sentence saying why confirm is disabled. Confirming with unsaved decisions saves them first and then confirms (two existing endpoints, no API change). |
| A3, A9 | Row results and load states are labelled ("Correcta", "Advertencia", "Error"; "Vista previa", "Confirmada", "Cancelada"); reason messages come first with the code as a small tag; result filter is a chip row with counts; unconfirmed loads are highlighted with "Continuar revisión". |
| A4 | Sites: selects and the checkbox apply immediately, search applies with Enter or "Filtrar"; result count; coordinator code plus first name; "Campos" with a small completion bar and a tooltip; table scrolls horizontally on narrow screens instead of wrapping. |
| A5 | Site detail: actions in the page header with a clear hierarchy (Devolver primary, Reasignar secondary, Descartar outlined red), the reason a button is disabled written under the stage bar, coordinator by code and name, history with translated movements, reasons and origins, a two-column layout on wide screens. |
| A6 | Dialogs explain the consequence and who is notified; focus is trapped and restored; Escape closes; a dialog with typed text does not close on backdrop click. |
| A7 | Equivalences: "Cuenta resuelta" tag instead of raw GUIDs (the oid stays in the tooltip), warning when a code is unresolved, "Cambios sin guardar" note, remove button for new rows. "Guardar" stays enabled on purpose: saving re-resolves accounts, which is a legitimate action with no edits. |
| A8 | Audit log: user shown by name (coordinators from the equivalence table, "Administrador" for the admin role) with role and short oid underneath; user filter is a select; action and entity inputs offer the known values; correlation id moved into the detail toggle. |
| X3 | No raw enum codes remain on screen except audit actions, which are identifiers. |

## 2. How it was verified

### Automated

| Gate | Result |
|---|---|
| `pnpm -r typecheck` and `pnpm -r lint` (all packages and apps) | clean |
| Frontend unit tests (`pwa-coordinador` 10, `web-admin` 7, `api-client`, `auth`) | pass |
| Playwright e2e, full suite (`make e2e`), 14 existing tests | pass (two assertions updated on purpose: `lote-estado` now reads "Vista previa"/"Confirmada"; history shows "Devolución"/"Reasignación"; return reason shows the catalog name) |
| New e2e `admin.a11y.spec.ts`: dialog traps focus for 8 tabs, closes with Escape, restores focus; every admin page has one `h1`, a skip link and exactly one `aria-current="page"` nav item, and a page title | pass |
| New e2e `pwa.a11y.spec.ts` (Pixel 7 viewport): list, notifications and detail never scroll horizontally, have one `h1`, and the first tab stop shows a visible outline | pass |
| Screenshot tool `node e2e/tools/screenshots.mjs <dir> <label>`: every screen at 390 × 844 and 1366 × 900, console and page errors collected | 24 captures, no console errors |

Backend tests were not touched and were not rerun: no backend file changed (`git diff --stat`).

### In Chrome (Claude in Chrome extension, real session as `ard` and `adm`)

Exercised and observed:

- Coordinator list with real returned sites: the "Requieren tu atención" group, inline reasons,
  status chips with counts, next-action lines (`screenshots/pwa-lista-atencion-chrome.png`).
- Site detail of a returned site: returned alert with reason, "Siguiente paso" checklist with the
  pending item linked, disabled advance with its explanation.
- Measurements form: submitting empty shows two field-level errors and focuses the first field;
  entering 8.5 × 12 saves, the success alert reads "Medidas guardadas y enviadas.", the section
  switches to the summary with the computed 102 m² and an "Editar" control; the server state was
  refreshed by the sync that followed. No console errors.
- Admin site detail and the Reasignar dialog opened from the header actions.

Limitations of the Chrome session, stated plainly:

- The extension could not resize the window below the screen bounds and its screenshot channel
  timed out whenever a second tab was active or a batch mixed actions and captures. Phone-width
  evidence and systematic captures therefore come from Playwright Chromium, not from the
  extension. Interactive checks were done one tab at a time.
- The Chrome profile's IndexedDB predated a database reset, so the first screens showed stale
  sites; this is recorded as finding P12 and is not caused by the redesign.

### Before and after

`docs/ux/screenshots/` holds equivalent captures of the main screens before and after
(`*-before.png`, `*-after.png`): coordinator list and detail at phone width, admin summary, load
preview, site detail and equivalences at desktop width.

Step counts for the two most frequent tasks (counted on the running app):

| Task | Before | After |
|---|---|---|
| Coordinator finds a site the admin returned and sees why | Open list → scan 8 cards for a small "devuelto" chip → open site → read banner (3 steps, reason only inside the site) | Open list → reason is in the first group (1 step) |
| Admin confirms a load with warnings | Open preview → Aprobar todas → Guardar decisiones → Confirmar (3 clicks after review) | Open preview → Aprobar todas → Confirmar (2 clicks; decisions saved by the confirm) |
| Admin knows what needs a decision today | Scroll past six counters; preview loads not shown anywhere | Three queues at the top of the landing page |

## 3. Accessibility checks

| Requirement | Status |
|---|---|
| Colour contrast (WCAG 1.4.3) | Every token pair computed in `DESIGN_SYSTEM.md` passes AA; white on brand red 5.3:1, muted text 5.1:1 on the page background. Verified by formula, not by an automated scanner. |
| Visible focus (2.4.7) | Global `:focus-visible` ring; file inputs focusable; verified in the new e2e. |
| Keyboard (2.1.1) and no trap (2.1.2) | Dialog trap is intentional and escapable; verified in e2e. |
| Name, role, value (4.1.2) | Icons are `aria-hidden` unless labelled; chips use `aria-pressed`; sync chip has an `aria-label` with its state; tables use `th scope="col"`. |
| Status messages (4.1.3) | Success and sync banners use `role="status"`; errors use `role="alert"`; conflict panel sub-alerts use no role to avoid double announcements. |
| Target size (2.5.8) | 44 px controls on the PWA, 36 px in dense admin tables. |
| Reduced motion (2.3.3) | All animation disabled under `prefers-reduced-motion`. |
| Language, titles (3.1.1, 2.4.2) | `lang="es-MX"`, per-page titles. |
| Not verified | Screen-reader walkthrough with TalkBack or NVDA; automated axe scan. Listed as remaining work. |

## 4. Remaining issues and follow-ups

| Item | Severity | Note |
|---|---|---|
| Official vector logo | S2 | `BrandMark` is a re-creation of the roundel; Mercadotecnia must supply the official asset. |
| Attention queues cap | S3 | Landing-page queues come from the first 200 sites; a server-side filter (`devuelto`, `en_revision_admin`) would be needed above that volume. |
| Stale local cache (P12) | S3 | Sign-out clears local data; a "volver a descargar mis sitios" action in the sync chip menu would make recovery discoverable. |
| Screen-reader pass | S2 | Not performed. |
| Admin tables on phones | S3 | They scroll horizontally and remain readable; a card layout for the sites table on phones would be nicer but is secondary for a desktop-first admin. |
| Audit action labels | S3 | Actions stay as codes by design; a glossary tooltip could help new admins. |
| Chrome extension flakiness | tooling | Documented above; Playwright remains the CI path. |

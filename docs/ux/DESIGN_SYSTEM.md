# Design system · Pipeline de Posibles Tiendas

Date: 11 October 2026. Implemented in `packages/ui` (tokens in `src/base.css`, components in
`src/*.tsx`) and consumed by both apps. This document records the brand research, the decisions
derived from it, and the conventions every screen follows.

## 1. Brand research (observed on https://www.tiendas3b.com, 11 Oct 2026)

What was observed, with the method (computed styles read in Chrome plus screenshots):

| Element | Observation | Explicit brand identity or marketing-site choice? |
|---|---|---|
| Logo | Red roundel with a white "B" over "BB"; also lettered as "Tiendas 3B" on storefront renderings. Served as a 150 px JPG (`logos-marcas-…-tiendas3b-150x150.jpg`). | Brand identity |
| Primary red | `rgb(215, 18, 30)` = `#D7121E` on buttons and the roundel; `#E31B23` in a few places | Brand identity |
| Dark text | Headings in black; body in `#04211F` (a very dark green-black) and `rgba(4,33,31,.6)` for secondary text; nav links `#1C244B` (navy) | Site palette; the green-black ink reads as part of the brand because it matches the storefront green |
| Green | Storefront renderings (columns, bands) and the underlined highlight "3,624 tiendas" on the red band | Brand identity (storefront); exact value not published, sampled ≈ `#0E7A3A` for text use |
| Neutrals | Page `#F3F5F8` / `#FAFAFA`, borders `#E6E9EC`, inputs white with 3 px radius | Marketing-site choices |
| Typography | Montserrat everywhere (900 for headings, uppercase, tight letter-spacing −0.03 em; 400 body); Poppins in one widget | Montserrat is the brand voice; the weight-900 uppercase treatment is a marketing choice |
| Buttons | Filled red pill (`border-radius: 100px`, weight 900, 23 × 32 px padding) with white text; round red social icons | Marketing style; "filled red = primary" is on-brand |
| Forms | 42 px inputs, 1 px `#E6E9EC` border, 3 px radius, labels bold 16 px with "(Requerido)" | Marketing site (Gravity Forms) |
| Tone | Direct, plain Spanish, second person ("Réntanos tu local", "si el producto no te gusta, te devolvemos tu dinero"); value = cercanía, precio, sencillez | Brand voice |
| Layout | Centered 1,100 px container, generous white space, hero carousel, red full-width band | Marketing |

Not found and therefore **not claimed**: an official colour specification, a secondary palette, an
icon set, a vector logo. The vector mark used in the apps (`BrandMark` in `packages/ui/src/brand.tsx`)
is a re-creation of the roundel as observed and must be replaced by the official asset from
Mercadotecnia before go-live. It is flagged as such in the code.

## 2. Interpretation: from marketing site to operational product

The apps are tools for ten coordinators in the field and one administrator. They must be
recognisably Tiendas 3B without borrowing the marketing layout. Decisions:

- **Red is the brand accent and the primary action colour.** The site uses filled red for its
  only call to action, so a filled red button reads as "the thing to do". To keep red meaningful,
  no ordinary status uses it: missing documents are neutral, pending sync is amber, only errors,
  conflicts, returned sites and destructive actions are red. Destructive actions are *outlined*
  red with a confirmation step, so the filled red primary and the destructive action never look
  the same.
- **Green is the completion colour** (the storefront green): published documents, confirmed
  loads, the last coordinator stage, success messages.
- **Ink is the brand's green-black**, not pure black; secondary text is a grey derived from it.
- **Montserrat for structure, system font for data.** Montserrat (self-hosted, latin subset,
  weights 600/700/800) carries headings, the app bar, navigation, buttons and badges. Body text,
  forms and tables use the device's system font: it is denser, renders faster, and costs nothing
  offline. Two families with clearly distinct roles. The uppercase weight-900 headline treatment
  of the website is not used: operational screens need quiet headings.
- **Pills only where the site uses them**: badges, buttons and inputs keep a rounded (not fully
  round) 6 px radius so dense rows stay aligned; chips, the roundel and status dots are round.
- **No decorative gradients, carousels, hero images or oversized KPI cards.** Information first.

## 3. Tokens (`packages/ui/src/base.css`)

### Colour

| Token | Value | Use | Contrast (on white / on `--bg`) |
|---|---|---|---|
| `--color-brand` | `#D7121E` | Roundel, primary buttons, active nav indicator | white on it 5.3:1 |
| `--color-brand-strong` | `#B3121C` | Primary hover, destructive text and outlines | 7.0:1 / 6.6:1 |
| `--color-brand-soft` | `#FDECEC` | Error/returned tint backgrounds | — |
| `--color-ink` | `#04211F` | Headings, body text | 16.9:1 / 15.5:1 |
| `--color-text` | `#1D2B2A` | Default text (slightly lifted ink) | 14:1 |
| `--color-muted` | `#5C6B69` | Secondary text, hints | 5.6:1 / 5.1:1 |
| `--color-green` | `#0E7A3A` | Success text, completion | 5.5:1 |
| `--color-green-soft` | `#E3F3E8` | Success tint | — |
| `--color-amber` | `#8A5A00` | Pending / warning text | 5.9:1 |
| `--color-amber-soft` | `#FFF4E0` | Warning tint | — |
| `--color-navy` | `#1C244B` | Informational text, stage 2–3 chips | 15:1 |
| `--color-navy-soft` | `#E7EAF5` | Info tint | — |
| `--color-bg` | `#F3F5F8` | Page background | — |
| `--color-surface` | `#FFFFFF` | Cards, inputs, tables | — |
| `--color-surface-2` | `#F7F8FA` | Table header, subtle rows | — |
| `--color-border` | `#E1E5EA` | Borders, dividers | — |
| `--color-border-strong` | `#C5CCD4` | Input borders, hover | — |
| `--color-focus` | `#1C244B` | Focus ring (2 px + 2 px offset) | 15:1 |

Every text/background pair above was checked with the WCAG relative-luminance formula; all pass
AA for normal text. Disabled controls use 50 % opacity and are exempt (WCAG 1.4.3 exception).

### Typography

| Token | Value |
|---|---|
| `--font-display` | `"Montserrat", system-ui, sans-serif` (600, 700, 800; self-hosted via `@fontsource/montserrat`) |
| `--font-body` | `system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif` |
| `--font-mono` | `ui-monospace, "Cascadia Mono", "Segoe UI Mono", Menlo, monospace` (identifiers, codes) |
| `--text-xs` 12 px · `--text-sm` 13 px · `--text-base` 15 px · `--text-md` 16 px · `--text-lg` 18 px · `--text-xl` 22 px · `--text-2xl` 28 px | Line-height 1.5 body, 1.25 headings |

Headings: `h1` 22 px (phone) / 28 px (desktop) Montserrat 700, `h2` 16 px (phone) / 18 px
(desktop) Montserrat 700, section eyebrows are never uppercase. Numbers in tables use `font-variant-numeric: tabular-nums`.

### Spacing, radius, elevation, layout

- Spacing scale: `--space-1` 4 · `--space-2` 8 · `--space-3` 12 · `--space-4` 16 · `--space-5` 24 ·
  `--space-6` 32 · `--space-7` 48.
- Radius: `--radius-sm` 6 (inputs, buttons, tags) · `--radius` 10 (cards, dialogs) · `--radius-full`.
- Elevation: cards are flat with a 1 px border (`--shadow-none`); sticky bars and dialogs use
  `--shadow-md` (`0 8px 24px rgba(4,33,31,.16)`); nothing else casts a shadow.
- Containers: PWA `--container-narrow` 720 px, admin `--container` 1280 px, 16 px side gutters,
  no horizontal page scroll at 360 px.
- Touch targets: 44 px for primary and form controls on the PWA; 36 px for secondary chips,
  inline actions (`.small`, `.chip`, the sync chip) and dense admin tables (WCAG 2.5.8 requires
  24 px).

### Motion

Only state changes animate: dialog open (120 ms fade), alert enter (150 ms), spinner. All are
disabled under `prefers-reduced-motion: reduce`.

## 4. Components (`packages/ui`)

| Component | Purpose and rules |
|---|---|
| `AppBar` | Brand roundel + product name + area name, primary nav (`nav aria-label="Principal"`, `aria-current="page"` on the active link), right slot for status and account. Collapses to a single row with the nav below on phones. |
| `PageHeader` | `h1`, optional description, optional actions aligned right; back link above it when the page is a detail. |
| `Button` classes | `button` (primary, filled red), `.secondary` (outlined ink), `.ghost` (text only), `.danger` (outlined brand-strong red; always paired with a confirmation or a reversible action), `.small`. Icon + text, never icon-only without `aria-label`. Loading state keeps the width and shows "…". |
| `Badge` / `EstatusBadge` | Status chip; tone per stage (`stage-1` neutral … `stage-4` green, `terminal`, `devuelto` red). Text is the catalog label, never a colour alone. Keeps class `badge` and `badge-devuelto` for tests. |
| `StageIndicator` | The four coordinator stages as a stepper; done, current, upcoming. Terminal statuses show a single chip instead. |
| `Alert` | `tone` info/success/warning/error; `role="alert"` for errors, `role="status"` for the rest; optional action. Replaces the ad-hoc `.problem`, `.success`, `.offline-banner`, `.pending` paragraphs. |
| `EmptyState` | Icon, title, one sentence, optional action. |
| `Field` | Label, control, hint, error wired with `aria-describedby` and `aria-invalid`. |
| `Modal` | Focus trap, focus restore, `Escape`, labelled by its title, closes on backdrop click only when the form is untouched. |
| `DataTable` styles | Sticky header, `th scope="col"`, zebra off, 36 px rows, `.num` right-aligned tabular, `.nowrap`; horizontal scroll on narrow screens with the first column kept readable. |
| `Icon` set | Inline SVG, 20 px, 1.75 stroke, `aria-hidden` unless it is the only content. |
| `Spinner` | Unchanged API; respects reduced motion. |
| `ProblemAlert` | Unchanged API; renders through `Alert`. |

## 5. Interaction conventions

- **One primary action per screen**, filled red, placed where the eye lands after the content it
  acts on (bottom of a form, top of the "Siguiente paso" card).
- **Destructive = outlined red + confirmation** that names the object and the consequence
  ("Descartar sitio Av. 20 de Noviembre 668: pasa a Descartado y deja el pipeline. Los datos se
  conservan.").
- **Progressive disclosure**: captured data is shown as a summary with an "Editar" control; the
  form opens in place. Rare actions (proponer descarte) live under "Más acciones".
- **Status words are fixed**: Pendiente de sincronizar · Requiere atención · Devuelto · En revisión
  · Cargado · Falta. Same word, same tone, in both apps.
- **Feedback names the action**: "Guardar contacto" → "Contacto guardado"; offline → "Contacto
  guardado en el teléfono; se enviará al recuperar señal."
- **Errors say what to do**: validation errors sit next to the field and the first one gets focus;
  server errors keep the user's input.
- **Codes are translated** through the catalogs the API already serves; a code is shown in
  monospace only in the audit log, where it is the identifier.
- **Keyboard**: every control reachable in DOM order, visible focus ring, dialogs trap focus,
  `Escape` closes, skip link to `main`.
- **Document titles** follow "Page · Pipeline de Posibles Tiendas".

## 6. Writing

Spanish, informal second person (as the brand does), sentence case, no exclamation marks, no
"por favor". Verbs on buttons ("Guardar medidas", "Confirmar carga"). Labels say what the field
is, hints say the format ("10 a 15 dígitos"). Empty states say what the screen will show and how
to get there ("Cuando el administrador te devuelva un sitio, el aviso aparece aquí").

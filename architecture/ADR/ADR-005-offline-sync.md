# ADR-005: Offline capture and synchronization semantics

**Status:** Proposed  **Date:** 2026-10-10  **Deciders:** Subdirección de IA, Seguridad, Intune team, Negocio (PDF question)

## Context and problem statement

Coordinadores work with low or no coverage (TDD RNF-02, section 10). The TDD requires that no capture is lost, operations are idempotent, transitions use `If-Match` with `rowversion`, and the server rejects operations when the record changed. It does not define how a chain of offline operations on one site replays, how the MSAL session survives app restarts, which browser hosts the PWA, or whether 150 MB PDFs must be captured offline (its own top risk, section 16). This ADR fixes those semantics.

## Requirements and constraints

- Fact (TDD RNF-02): no capture lost; idempotent operations.
- Fact (TDD 7.2, 12): transitions require `If-Match`; concurrency by `rowversion`.
- Fact (TDD 10): client-generated operation id; retries with backoff; conflicts shown to the coordinador.
- Fact (TDD RF-08): PDFs upload chunked and resumable. The requirement does not say offline.
- Fact (Entra guide B3, D): MSAL cache defaults to `sessionStorage`; SPA refresh tokens have a limited lifetime, after which silent renewal fails and interactive sign-in is needed.
- Fact (verified in Learn): Microsoft Edge for Android is the browser Intune manages with app protection policies (PIN, cut/copy/paste restrictions, selective wipe) and Intune can force managed apps to open links in Edge.
- Assumption (TO_BE 9.2): PDFs upload online only; photos, contact, and measurements queue offline.
- Assumption (TO_BE 9.6, 9.7): Edge is the mandated host; MSAL cache in `localStorage` under Intune protection, to be ratified by Seguridad.
- Constraint: a service worker cannot call MSAL, so it cannot refresh tokens.

## Options considered

### Option A: Per-site FIFO queue in Dexie, chained ETags, `Idempotency-Key`, foreground sync

| Dimension | Assessment |
|---|---|
| Complexity | Medium |
| Cost | None |
| Security | Tokens only in app context; queue holds domain operations, not raw requests |
| Reliability | Deterministic replay; conflict isolated to one site |
| Team familiarity | Medium |

Pros: REST contract unchanged; conflicts are precise; parallelism across sites.
Cons: client must thread ETags; a small state machine per site in the app.

### Option B: Single `POST /sitios/{id}/sync` applying the whole chain in one transaction

| Dimension | Assessment |
|---|---|
| Complexity | Medium |
| Cost | None |
| Security | Same |
| Reliability | Atomic per site; fewer round trips on 4G |
| Team familiarity | Medium |

Pros: one request per site, atomic.
Cons: a second contract parallel to the REST endpoints; partial success is impossible, so a late validation error discards earlier valid captures until the coordinador fixes it.

### Option C: Workbox Background Sync replaying raw requests

| Dimension | Assessment |
|---|---|
| Complexity | Low |
| Cost | None |
| Security | Replays stale `Authorization` headers; cannot refresh tokens |
| Reliability | Order across requests not guaranteed per site; no ETag chaining |
| Team familiarity | High |

Pros: minimal code.
Cons: fails after token expiry; cannot express per-site ordering or conflict handling.

## Decision and rationale

Option A, with Option B kept as a documented fallback if 4G round trips prove too slow in UAT. Specifically:

- Access to the app does not need a valid token: the PWA opens and renders IndexedDB data for the last signed-in user. A token is needed only to synchronize and to fetch new data.
- MSAL cache in `localStorage`, justified by Edge under Intune app protection; Edge for Android is the mandated host; selective wipe must be verified to clear site data (Phase 0).
- Queue entries are domain operations (`contacto`, `visita`, `foto`, `transicion`) with a client-generated `Idempotency-Key`, the ETag known at creation, and the target site. Replay is FIFO per site, parallel across sites, and threads the ETag returned by the previous operation into the next.
- `PUT /contacto` and `PUT /visita` are last-write-wins without `If-Match` (only the owning coordinador writes them). `POST /transiciones` and `POST /admin/.../devolver` require `If-Match`.
- A 412 or 422 stops that site's chain; remaining operations for that site are marked blocked and shown with the server's current state. Other sites continue.
- Sync runs in the app foreground on open, on the `online` event, and on a timer. Background Sync may only wake the app.
- PDFs are uploaded only when online, chunked and resumable through `subida_sesion`. Photos are compressed on the client and queued with a per-site cap (pendiente 6).
- Transition rules live in code, one function per transition; parameters (minimum contact fields, required document types per status, duplicate distance) come from catalogs. `requisito_transicion` is reduced to parameters.

## Advantages and disadvantages

Advantages: removes the TDD's top risk (large files offline); false conflicts between a contact edit and the following transition disappear; the server contract stays REST with two well-known headers.
Disadvantages: client logic for chaining and blocking; `localStorage` tokens are a Seguridad decision; reliance on Edge limits browser choice.

## Security, reliability, and cost implications

Security: only the signed-in coordinador's sites are cached; cache cleared on sign-out, session expiry, or selective wipe; no PDFs at rest on the phone; `operacion_idempotente` stores response bodies without personal data beyond what the request already carried, purged after seven days.
Reliability: duplicates impossible by key; chain stops are visible; delta sync by `rowversion` includes removed sites so reassignment propagates.
Cost: none beyond the `operacion_idempotente` table.

## Consequences and risks

- New API elements: `Idempotency-Key` handling, `GET /sitios?desde=`, 412 and 422 bodies that include the current server state.
- Risk: `loginRedirect` inside an installed PWA may land in a browser tab instead of the app (verify in Phase 0). Mitigations: run from Edge without installing, `display: minimal-ui`, exclude Entra redirect responses from the service worker navigation fallback.
- Risk: after the refresh token lifetime, the coordinador must sign in interactively when back online; the queue persists through that.
- Open: shared phones between coordinadores would require sign-out clearing the queue (TO_BE open 6).

## Conditions that would justify revisiting

- Negocio confirms PDFs are produced in the field without signal (then allow one pending PDF per device with explicit warning).
- UAT shows per-operation round trips are too slow on 4G (switch to Option B per site).
- Intune policy forbids `localStorage` tokens; then the app must require sign-in before showing cached data, accepting reduced offline usability.

## Action items

- [ ] Phase 0 spike 1: Edge + Intune sign-in in installed PWA and browser tab, 24 h offline renewal, selective wipe behaviour.
- [ ] Specify queue entry schema and per-site state machine in the PWA.
- [ ] Implement `operacion_idempotente` and the `Idempotency-Key` middleware.
- [ ] Implement `GET /sitios?desde=` with removed-site reporting.
- [ ] Playwright offline tests: contact + transition chain, admin return mid-chain, duplicate replay.
- [ ] Ratify `localStorage` with Seguridad; record in TDD 5.4.

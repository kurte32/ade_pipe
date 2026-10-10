# ADR-007: Teams notification mechanism for devoluciones

**Status:** Proposed  **Date:** 2026-10-10  **Deciders:** Subdirección de IA, TI, Seguridad, Identidad

## Context and problem statement

When an administrator returns a site to an earlier status, the coordinador must receive a Teams notification with the site name, the status it returned to, and the general reason, without personal data, linking to the app (TDD RF-07, section 11). The TDD leaves the mechanism "por validar" and states that the notification is not on the critical path. The mechanism must address an individual user, not a channel.

## Requirements and constraints

- Fact (TDD 17.1): notifications are by Teams, a business decision.
- Fact (TDD 11, HU-14): a delivery failure must not revert the devolución; delivery retries.
- Fact (TDD 11): no owner contact data in the message.
- Fact (verified): Office 365 connectors and their incoming webhooks in Teams are retired; Microsoft points to Power Automate workflows, notification bots, or Graph activity feed notifications.
- Fact (TDD 16): an in-app notice in the PWA is the fallback.
- Assumption (TO_BE 9.9): Graph activity feed in Phase 4, Power Automate fallback, in-app notice baseline.
- Constraint: the backend already has a managed identity with Graph permissions planned (ADR-006).

## Options considered

### Option A: Teams activity feed notification via Microsoft Graph from the backend managed identity

| Dimension | Assessment |
|---|---|
| Complexity | Medium (Teams app manifest, admin consent, `TeamsActivity.Send`) |
| Cost | None recurring |
| Security | Application permission scoped to sending activity; no inbound surface |
| Reliability | Backend-controlled retry from the outbox |
| Team familiarity | Low to medium |

Pros: Microsoft-recommended for per-user notifications; lands in the user's activity feed with a deep link to the PWA; fully under backend control.
Cons: requires publishing a Teams app in the tenant and installing it for users (verify installation policy options); admin consent.

### Option B: Power Automate workflow triggered by the backend (HTTP request or queue)

| Dimension | Assessment |
|---|---|
| Complexity | Low |
| Cost | Licensing depends on the trigger and connector type (verify) |
| Security | Flow runs under its owner's identity; the trigger endpoint must be protected |
| Reliability | Depends on the flow owner's account and the service's limits |
| Team familiarity | High in most TI teams |

Pros: fastest to build; no Teams app to publish.
Cons: message appears from the Flow bot identity; the flow is tied to a person's account unless a service account is used; another runtime to monitor.

### Option C: Notification bot (Azure Bot Service, proactive messages)

| Dimension | Assessment |
|---|---|
| Complexity | High |
| Cost | Bot registration plus hosting |
| Security | Bot channel registration, additional endpoint |
| Reliability | Good |
| Team familiarity | Low |

Pros: richest messaging.
Cons: disproportionate for one notification type.

### Option D: In-app notice only

| Dimension | Assessment |
|---|---|
| Complexity | Lowest |
| Cost | None |
| Security | None added |
| Reliability | Visible at next sync only |
| Team familiarity | High |

Pros: already required as baseline.
Cons: does not satisfy RF-07 on its own.

## Decision and rationale

Baseline Option D in Phase 3, delivered from a `notificacion_outbox` table written in the same transaction as the devolución. Target Option A in Phase 4 if Identidad approves the Teams app and `TeamsActivity.Send`; otherwise Option B with a service account. Both are driven by the same outbox, so the choice does not touch the devolución flow. Option C is rejected as disproportionate.

## Advantages and disadvantages

Advantages: the devolución is never blocked; the mechanism can change without touching business logic; the in-app notice guarantees the coordinador sees the return at next sync regardless of Teams.
Disadvantages: Phase 4 depends on an approval outside the team; two possible implementations to keep documented.

## Security, reliability, and cost implications

Security: message content limited to site name, new status, reason code, and a deep link; no contact data. For Option A the managed identity gets only `TeamsActivity.Send` and `User.ReadBasic.All`. For Option B the trigger is a private endpoint or a queue, never an unauthenticated HTTP URL.
Reliability: outbox job with exponential backoff, dead-letter state after a configurable number of attempts, alert on backlog age.
Cost: none for Option A; Power Automate licensing to verify for Option B.

## Consequences and risks

- `notificacion_outbox` and the outbox job become Phase 3 deliverables regardless of mechanism.
- Risk: Teams app publication is refused or delayed; Option B is the documented fallback and does not change the data model.
- Risk: users dismiss activity feed notifications; the in-app indicator remains the authoritative signal.

## Conditions that would justify revisiting

- More notification types appear (assignment, reminders), which may justify a bot.
- The organization provides a central notification service.
- Graph activity feed requirements change (verify at implementation time).

## Action items

- [ ] Implement `notificacion_outbox` and the delivery job with retry and dead-letter (Phase 3).
- [ ] Submit the Teams app manifest and `TeamsActivity.Send` request to Identidad (start in Phase 0).
- [ ] Prototype Option A in `test` once consent is granted; otherwise build Option B with a service account.
- [ ] Add an alert on outbox backlog age.

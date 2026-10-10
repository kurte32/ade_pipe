# ADR-008: Network posture, secrets, and service-to-service identity

**Status:** Proposed  **Date:** 2026-10-10  **Deciders:** Seguridad, TI, Subdirección de IA

## Context and problem statement

TDD v0.1 (5.3) calls for private endpoints on SQL, Blob, and Key Vault, with OneLake access "por validar", managed identity everywhere, and no secrets in code. Private endpoints have consequences the TDD does not spell out: the Container Apps environment must be VNet-integrated, Front Door needs a Private Link origin, and Fabric Mirroring needs a VNet data gateway. This ADR decides the network posture and the secrets model, and records the cheaper alternative.

## Requirements and constraints

- Fact (TDD RNF-01, 5.3): encryption in transit and at rest; no secrets in code; private endpoints proposed.
- Fact (TDD 5.1): managed identity from the backend to SQL, storage, Key Vault, Graph.
- Fact (verified in Learn): Mirroring of Azure SQL Database that is not publicly accessible requires a VNet data gateway or an on-premises data gateway.
- Fact (ADR-003): Defender for Storage and the Fabric workspace need access to the storage accounts.
- Assumption (TO_BE 9.3, 9.4): private endpoints, VNet-integrated Container Apps, VNet data gateway, Front Door Premium with WAF.
- Open: whether private endpoints are a corporate mandate or a preference (Step 3 question 3, answered by default as mandate).
- Constraint: the SPAs are public clients and hold no secrets by design.

## Options considered

### Option A: Private endpoints, VNet-integrated Container Apps, Front Door Premium Private Link origin, VNet data gateway for Mirroring

| Dimension | Assessment |
|---|---|
| Complexity | Medium to high |
| Cost | Highest fixed floor (workload profile, Front Door Premium, gateway, private endpoints) |
| Security | Data services unreachable from the internet; API reachable only through Front Door |
| Reliability | More components; each is managed |
| Team familiarity | Medium |

Pros: strongest network isolation; aligns with the TDD; auditors rarely challenge it.
Cons: roughly doubles the fixed cost versus Option B; Fabric trusted workspace access and Defender resource rules must be confirmed (verify).

### Option B: Service firewalls with "trusted Azure services" and resource instance rules, Container Apps consumption profile with public ingress restricted to Front Door, Front Door Standard

| Dimension | Assessment |
|---|---|
| Complexity | Low |
| Cost | Low |
| Security | Data services accept only the backend identity and listed Azure services; API ingress restricted by header or IP to Front Door |
| Reliability | Fewer components |
| Team familiarity | High |

Pros: no VNet, no gateway, no Private Link; Mirroring connects directly.
Cons: data services have public endpoints protected by firewall rules; some organizations disallow this.

### Option C: Azure Firewall with forced tunnelling in addition to Option A

| Dimension | Assessment |
|---|---|
| Complexity | High |
| Cost | Highest |
| Security | Egress inspection |
| Reliability | Another managed component |
| Team familiarity | Low |

Pros: egress control.
Cons: no egress-inspection requirement has been established.

## Decision and rationale

Option A by default, because the TDD already commits to private endpoints and no counter-mandate exists. Option B is recorded as the simplification path and must be chosen explicitly by Seguridad if cost or complexity outweighs the isolation gain at ten users. Option C is rejected until a requirement appears.

Secrets model regardless of option: user-assigned managed identity for the API and jobs; Entra-only authentication on SQL; shared key access disabled on both storage accounts; Key Vault holds only what cannot be identity-based (certificates, any third-party credentials, Power Automate trigger secret if ADR-007 Option B); Container Apps reads Key Vault references with its identity; GitHub Actions authenticates with OIDC federation and holds no long-lived secrets; SPAs have no secrets.

## Advantages and disadvantages

Advantages: no credential to rotate for Azure resources; the API is not internet-reachable; a compromised SPA yields nothing beyond a user token.
Disadvantages: VNet, DNS zones, Private Link approval, and the gateway add to the IaC and to the Phase 1 critical path; local development needs a different connectivity story (dev environment without private endpoints).

## Security, reliability, and cost implications

Security: WAF managed rules on Front Door; NSG allow rules for outbound to Entra, Graph, Application Insights, Defender; Key Vault with purge protection and RBAC; Defender for Cloud on the subscription for posture.
Reliability: private DNS resolution is a single point of misconfiguration; health probes from Front Door to the private origin detect it; the VNet data gateway needs patching and monitoring.
Cost: Option A fixed floor is the largest cost driver in the design; `dev` uses Option B topology to keep cost near zero.

## Consequences and risks

- `dev` differs in topology from `test` and `prod` (AZURE_DESIGN section 5); network-dependent behaviour must be validated in `test`.
- Risk: Fabric trusted workspace access to a private storage account unavailable in the tenant; fallback is a public endpoint with firewall on the documents account only.
- Risk: Defender for Storage scanning on a private account requires resource rules (verify); otherwise staging stays public with firewall.
- Open: Seguridad confirms mandate versus preference; if preference, switch to Option B before Phase 1 IaC is written.

## Conditions that would justify revisiting

- Seguridad accepts Option B for this workload.
- A corporate hub-and-spoke network with Azure Firewall is provided centrally.
- Fabric or Defender cannot be made to work with private access in the tenant.

## Action items

- [ ] Obtain a written answer from Seguridad on private endpoints as mandate or preference.
- [ ] Phase 0: validate Fabric trusted workspace access and Defender resource rules against private accounts.
- [ ] Bicep modules for VNet, subnets, private endpoints, private DNS zones, Front Door Private Link origin, VNet data gateway.
- [ ] Disable shared key access and public network access on all data services in `test` and `prod`.
- [ ] Configure GitHub OIDC federated credentials per environment.

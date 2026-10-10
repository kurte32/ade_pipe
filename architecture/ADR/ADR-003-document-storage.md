# ADR-003: Document storage path and Fabric exposure

**Status:** Proposed  **Date:** 2026-10-10  **Deciders:** Subdirección de IA, Seguridad, TI, Fabric administrator, Legal (retention inputs)

## Context and problem statement

TDD v0.1 (sections 4.2, 4.3, 9) stores definitive documents and photos in OneLake (Lakehouse Files) written by the backend through the Data Lake SDK, with a Blob staging container for chunked upload and validation. The TDD itself lists as risks the write performance and permissions of an external backend writing to OneLake (section 16) and leaves malware scanning availability "por validar" (9.2). Retention of five years and a possible legal hold (RF-11, pendiente 7) are custom work in that design. This ADR decides where definitive files live and how Fabric sees them.

## Requirements and constraints

- Fact (TDD RF-08, RNF-05): PDFs up to 50 pages and 150 MB, chunked and resumable upload, validated before publishing.
- Fact (TDD RF-11, 9.3): five-year retention, controlled and audited purge, legal hold need to confirm with Legal.
- Fact (TDD 5.3): files never exposed by direct URL; type by signature; SHA-256; malware scan before publishing.
- Fact (TDD 2.1, HU-16): files must be visible in Fabric with metadata for a later AI agent.
- Fact (verified in Learn): OneLake shortcuts can point to an ADLS Gen2 container or folder and appear under the Lakehouse `Files` folder without copying data.
- Fact (verified in Learn): Defender for Storage on-upload scanning is triggered by blob creation and writes results as blob index tags and Event Grid events; index tags are not supported on accounts with hierarchical namespace.
- Assumption (TO_BE 9.1): accepted default is ADLS Gen2 plus shortcut.
- Open: retention start event and legal hold policy (pendiente 7); Fabric trusted workspace access to a private storage account (TO_BE open 3).

## Options considered

### Option A: Two storage accounts (flat Blob staging with Defender scanning, ADLS Gen2 definitive with immutability) and a OneLake shortcut

| Dimension | Assessment |
|---|---|
| Complexity | Medium (two accounts, one shortcut) |
| Cost | Low; storage in tens of GB; Defender per GB scanned |
| Security | Immutability and legal hold, managed scanning, private endpoints, no direct URLs |
| Reliability | Native redundancy, soft delete, no custom copy to Fabric |
| Team familiarity | High (standard Azure Storage) |

Pros: removes external writes to OneLake; retention enforced by the platform; scanning without code; Fabric sees files in place.
Cons: shortcut requires a delegated credential and trusted workspace access when the account is private (verify); two accounts to manage.

### Option B: TDD v0.1 design, Blob staging then backend writes to OneLake

| Dimension | Assessment |
|---|---|
| Complexity | Medium |
| Cost | Low |
| Security | Retention, legal hold, and scanning must be built or are unavailable in OneLake (verify) |
| Reliability | Depends on external write performance to OneLake, flagged as risk in TDD 16 |
| Team familiarity | Low (OneLake SDK from outside Fabric) |

Pros: files physically in OneLake; no shortcut.
Cons: TDD's own risk; purge job must implement retention; legal hold is custom; private access to OneLake was "por validar".

### Option C: Single ADLS Gen2 account for staging and definitive

| Dimension | Assessment |
|---|---|
| Complexity | Low |
| Cost | Lowest |
| Security | Defender scanning works but index tags are unavailable on hierarchical namespace, so results must be consumed from Event Grid only |
| Reliability | Good |
| Team familiarity | High |

Pros: one account.
Cons: scan result cannot be read back from the blob itself, which complicates the promotion job's idempotent "is it clean" check; staging lifecycle rules would coexist with immutable paths in the same account.

## Decision and rationale

Option A. It eliminates the TDD's storage risk, turns retention and legal hold into configuration, and gets malware scanning as a managed service. The staging account stays flat so the promotion job can read the Defender index tag as the source of truth and use the Event Grid event as the trigger. The definitive account uses the hierarchical namespace required by the OneLake shortcut.

## Advantages and disadvantages

Advantages: zero-copy exposure to Fabric; purge reduces to deleting expired blobs; soft delete and versioning protect against accidental deletion; promotion is a server-side copy within Azure Storage.
Disadvantages: one more storage account; the shortcut credential and trusted workspace access are tenant-level settings owned by the Fabric administrator; version-level immutability on hierarchical namespace accounts must be confirmed (verify).

## Security, reliability, and cost implications

Security: both accounts with shared key disabled, public network access disabled, private endpoints, managed identity with Blob Data Contributor. Immutability prevents deletion or modification within the retention period even by the backend identity. Downloads always go through the API with an audit row. Resource instance rules allow Defender and the Fabric workspace identity without opening public access (verify).
Reliability: geo-redundant storage; promotion is idempotent (copy, then metadata insert, keyed by `subida_sesion.id`); abandoned sessions are purged by a lifecycle rule after seven days.
Cost: negligible storage; Defender scanning charged per GB uploaded; Event Grid events at this volume are trivial.

## Consequences and risks

- The OneLake path in TDD 9.2 becomes `Files/pipeline/...` under the shortcut; the AI agent reads the same path.
- Retention start event remains open; the immutability policy is configured once Legal answers pendiente 7. Until then, use upload date as the provisional start (Assumption).
- Risk: if trusted workspace access cannot be granted, the fallback is a public-network-with-firewall configuration on the documents account only, decided with Seguridad.
- Risk: a legal hold placed on a blob also blocks the purge job; the job must log and skip, not fail.

## Conditions that would justify revisiting

- Fabric adds native immutability, legal hold, and malware scanning for OneLake-resident files.
- Trusted workspace access to private storage proves unavailable in the tenant and public access is unacceptable.
- Document volume grows to a scale where shortcut performance for the AI agent is insufficient (verify thresholds).

## Action items

- [ ] Phase 0 spike: upload 150 MB through staging, confirm Defender tag and event, promote to ADLS Gen2 with an immutability policy, view it through a Lakehouse shortcut.
- [ ] Confirm version-level immutability and legal hold on hierarchical namespace accounts (verify).
- [ ] Request Fabric trusted workspace access and workspace identity from the Fabric administrator.
- [ ] Define lifecycle rules for staging and the purge job behaviour with legal holds.
- [ ] Update TDD 4.2, 4.3, 9.2, 9.3, and 16 for v0.2.

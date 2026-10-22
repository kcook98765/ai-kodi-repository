# Review record contract

The repository retains **strict admission**. Rights authorization, owner risk
acknowledgment, technical release approval, observed runtime acceptance, final
release approval and operator publication authority are separate assertions.
There is no exception or waiver path. An acknowledgment cannot provide missing
rights, resolve an adverse finding or complete a test. Deferred testing remains
ineligible for production. This applies to every independently developed add-on.

The [JSON Schema](REVIEW-RECORD-SCHEMA.json) describes structural interchange;
`scripts/approval_contract.py` additionally validates decision consistency, dates,
intake scope and eligibility. The builder and independent auditor load the
hash-bound inputs separately, apply that shared contract and retain their own
production, archive, dependency, retention and inventory checks. Do not run the
auditor with Python optimization. No new Python package is required.

| Assertion | Unchanged legacy meaning | Version 2 clarification |
| --- | --- | --- |
| `rights_approved` | Affirmative reviewed redistribution/rights decision, mandatory for production | Must equal `rights_review.status == verified`; an attributable evidence-backed decision covering the package's relevant rights, licenses and attribution |
| Owner acknowledgment | No admission effect | `owner_acknowledgment` names the exact unresolved risk IDs, owner identity/role, time, rationale and evidence; never satisfies another gate |
| Technical release approval | Part of the old aggregate release judgment, no separate assertion | `technical_release.status == approved` is an explicit, attributable decision about frozen bytes and technical evidence; mandatory for v2 production |
| `runtime_accepted` | Affirmative per-lane acceptance with nonempty evidence | Must equal `runtime_test.status == passed`; observed platform, Kodi version and required feature scope, evidence and zero outstanding tests are required |
| Runtime deferral | False acceptance does not explain why | `runtime_test.status == deferred`, `runtime_accepted=false`, attributable deferral, exact scope and nonempty outstanding tests; always blocks production |
| `release_approved` | Final package release approval, mandatory for production | Must equal `release_decision.status == approved`, with explicit attribution and evidence; cannot be approved while any gate remains outstanding |
| Publication authority | Separate exact operator authorization | Unchanged; plans always retain `publication_authorized=false` and no executed remote actions |

`verified` is a reviewer's assertion of a supported rights basis, not automated
legal verification. Rights evidence must cover bundled code/art, licensing and
attribution and relevant external service/content/imagery/marks findings. A code
license alone cannot establish every relevant authorization. Provider permission
must have its own actual evidence if claimed; it is not inferred from a rights
status or an acknowledgment. This policy does not invent a universal provider
permission requirement or declare a particular legal basis sufficient.

## Version 2 records

Start from [the blocked template](REVIEW-RECORD-EXAMPLE.json). The zero hashes are
placeholders. Never turn a false approval into true during migration.

- `schema_version` is exactly integer `2`; `approval_policy` is `strict-v1`.
  Unknown versions/policies reject. `approval_lanes` must equal the selected
  intake lanes without duplicates, including an empty list for retained history.
- Existing package digest, source repository/commit, runtime-file allowlist,
  `fixture_only=false`, booleans and compatibility evidence remain mandatory.
  The intake hash of the complete review record binds all decisions, evidence,
  risks, source, exact package digest, policy and lane scope together. Each
  decision inherits that scope; do not reuse it for another package or lane.
- `rights_review` has `verified`, `pending`, `rejected` or `revoked` status.
  `technical_release` and `release_decision` have `approved`, `pending`,
  `rejected` or `revoked` status. `pending` is exactly `{"status":"pending"}`.
- Every recorded action has nonblank `actor`, `role`, UTC `recorded_at`
  (`YYYY-MM-DDTHH:MM:SSZ`), `rationale` and nonempty `evidence` references.
  Identities and references are operator-reviewed attestations, not authenticated
  signatures. Retain the cited evidence immutably and verify its scope/substance
  before approving. Tools do not dereference evidence or contact a provider.
- `owner_acknowledgment` is either `{"status":"not_recorded"}` or an
  attributed `acknowledged` action with `risk_ids` exactly matching the record's
  nonempty unresolved risks and `role=owner`. It records understanding, with no release effect.
- `unresolved_risks` is a list of unique `id`, `category` (`rights`, `runtime`,
  `technical`, `other`), nonblank `description` and nonempty `evidence` records.
  **Every unresolved risk blocks v2 production**, acknowledged or otherwise.
  Verified rights alongside an unresolved rights risk, or technical approval
  alongside an unresolved technical risk, is contradictory and rejects even a
  candidate record. No owner acceptance or alternate approval defeats this rule.
- Every v2 compatibility entry includes a `runtime_test` action: `passed`,
  `deferred`, `pending` or `failed`. A nonpending action also records `platform`,
  `kodi_version`, `scope` and `outstanding_tests`. Passed requires an empty list;
  deferred/failed require a nonempty list. A runtime-risk finding alongside all
  selected lanes passing is contradictory. Pending is an unrecorded test, not
  a completed or implicitly deferred test. Static evidence remains separate.

For example, a deferral is an action with this shape (synthetic illustration):

```json
{
  "status": "deferred",
  "actor": "repository-owner",
  "role": "owner",
  "recorded_at": "2026-10-22T23:00:00Z",
  "rationale": "Eligible-account playback remains unavailable for testing",
  "evidence": ["retained-deferral-decision-reference"],
  "platform": "Linux",
  "kodi_version": "21.3",
  "scope": "Authentication and entitled VOD",
  "outstanding_tests": ["Login and session reuse", "Video and audible audio"]
}
```

This requires `runtime_accepted=false` and a pending final release decision.
It can describe a private candidate; it cannot authorize production admission.

## Compatibility, reports and migration

Unversioned and explicit integer `schema_version=1` records retain the previous
boolean contract. Valid approved legacy releases still pass. Their reports say
`legacy_approved`, `legacy_accepted` and `legacy_unspecified` rather than claiming
new rights verification, separate technical approval, actor attribution or
deferral evidence. Legacy reports retain their original narrative limitations
and native-scope findings; the structured
unresolved-risk inventory is `null` (unspecified), never an assertion of no risk.
The new v2 fields and `runtime_test` are rejected in v1 to prevent silent interpretation loss.

Upgrade **all consumers first**: builder, auditor, qualifier and preflight. Older
tools ignore additive v2 keys and cannot enforce the new contract. Then create a
new hash-bound record, retaining the old record and a supersession reference in
its narrative/evidence. Supply actual rights, technical, runtime and final
release decisions; do not synthesize actors/times or retrospectively shrink
the scope of old acceptance. Update the intake's `review_record_sha256` after
review. Historic source and package bytes remain unchanged. Regenerate local
plans after upgrading; their approval-contract digest prevents stale preflight.

Each package's plan `approval` report includes its review-record digest, decision
statuses/attribution, exact runtime deferrals/outstanding tests, unresolved risks
and all admission blockers. The auditor rederives and compares that report from
the actual hashed inputs. Qualification and publication preflight include the
same audited reports. Candidate plans always add their private-profile blocker;
a successful structural audit never means approval or runtime execution.

The generated current repository installer retains its existing infrastructure
path; this clarification does not invent native acceptance for it or broaden
that path to ordinary add-ons. Catalog selection and loopback downloads cannot
prove a real Kodi GUI install/update or all-feature add-on behavior.

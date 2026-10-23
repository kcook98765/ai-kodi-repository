# Review record contract

The repository retains **strict admission for legacy/v1 and v2**. Rights authorization, owner risk
acknowledgment, technical release approval, observed runtime acceptance, final
release approval and operator publication authority are separate assertions.
Schema 3 adds only the bounded distribution route described below. An acknowledgment cannot provide missing
rights, resolve an adverse finding or complete a test. Deferred testing remains
ineligible for production. These runtime and authorization boundaries apply to every independently developed add-on.

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

## Version 3: independently developed unofficial integrations

Opt in with exactly `schema_version=3` and
`approval_policy="unofficial-integration-v1"`. Fully supported releases, including
unofficial clients with supported service-use findings, continue to use strict
v2. This route requires a nonempty list of **provider-service terms**
findings: residual uncertainty, or a known provider-authorization concern accepted
under the explicit owner-risk decision below. It supplies neither provider endorsement nor authorization to operate
an integration. Approval records and publications still require separate review
and operator authority; no existing record is automatically migrated or approved.

Retain `rights_approved=false` and `rights_review={"status":"pending"}`. Broad
rights are unverified. Do not reinterpret the old boolean as package-only rights.
Retain the existing source/package/runtime hashes, `fixture_only=false`, selected
lane scope, technical approval and completed per-lane static/runtime acceptance.
The final boolean still equals `release_decision.status == approved` and cannot
coexist with a hard blocker. Pending, deferred and failed required tests block.
No required scope can be retrospectively removed to turn unknowns into passes.
Empty lane lists require exact historical ledger membership, with acceptance
still checked over the recorded compatibility scope; they admit no new release.

Add one closed `unofficial_integration` object:

| Member | Required assertion |
| --- | --- |
| `package_distribution_review` | Attributed `verified` action with `scope=all_distributed_materials`; other statuses are `pending`, `rejected`, `revoked` and block |
| `service_use_review` | Attributed `terms_unresolved` action, or `authorization_unverified` with `upstream_provider` and the owner-risk exception below; both require `scope=runtime_service_content_and_marks`, exact provider-terms `risk_ids`, `provider_permission_obtained=false`, `provider_content_authorization=not_established`; `pending`, `blocked`, `revoked` block |
| `owner_distribution_decision` | Attributed `accepted` action with `role=owner`, exact provider-terms `risk_ids`, `authorization_claimed=false`; optionally includes the closed `provider_authorization_exception` below; `pending`, `declined`, `revoked` block |
| `disclosure` | Exactly `package_path`, `package_sha256`, `release_text`; canonical relative notice path in the hashed runtime inventory, actual nonempty UTF-8 ZIP member, and nonblank reviewed public text |

New actions use the existing `status`, `actor`, `role`, real UTC-second
`recorded_at`, `rationale`, `evidence` fields plus exactly their listed fields.
Pending is exactly `{"status":"pending"}`. New action and v3 risk evidence uses
`relative/path sha256:<64 lowercase hex>` references to immutable retained files.
The validator checks reference shape and record binding; **the operator verifies
retained file digests, provenance, scope and substance**. Tools do not fetch or
execute references. String attribution is not identity authentication.

Package and service reviewers must be independent of the accepting owner; both
reviewer actor names must differ from the accepting owner (ignoring surrounding
space and case). Owner acknowledgment remains a separate existing action with
`role=owner` naming **all** unresolved risks exactly. Acknowledgment alone has no
eligibility effect. Each service/owner action names the exact nonempty provider
terms set with no duplicates, omissions or additions. Decisions inherit the
record's exact package, source, runtime inventory, policy and lane scope.

### Explicit owner-risk provider-authorization decision

For schema 3 unofficial integrations only, the repository owner may elect to
publish independently developed software without verified provider authorization,
including when known provider terms restrict third-party integration. This is a
repository publication-policy decision; it grants no provider permission, content
rights or legal clearance. Seeking provider permission is not required for this
route. The concern remains unresolved and visible in plans and audits.

Record `service_use_review.status=authorization_unverified` and its nonblank
`upstream_provider`. Add `provider_authorization_exception` to the existing
attributed owner distribution action. It inherits that action's actor, owner
role, recording time, rationale, pinned evidence and exact risk IDs. A separate
acknowledgment by that same owner remains mandatory. Its exact required keys are:

```json
{
  "scope": "repository_provider_authorization_gate_only",
  "upstream_provider": "Synthetic provider",
  "addon_id": "plugin.video.example",
  "addon_version": "1.0.0",
  "package_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "provider_authorization_verified": false,
  "provider_terms_concern": "Known terms restrict third-party clients; owner accepts publication risk without verified permission or legal clearance.",
  "owner_accepts_risk": true,
  "expires_at": "2026-12-01T00:00:00Z"
}
```

This is a synthetic excerpt, not an approval or a complete review record. The
provider must equal the service review's provider. ID and version must equal
the independently inspected ZIP manifest; checksum must equal the frozen ZIP.
`expires_at` is a real UTC-second timestamp after the owner decision. The owner
decision must already be recorded, accepted and unexpired at every assessment,
including fresh publication preflight. Missing, malformed, future-dated, expired,
declined, revoked or mismatched decisions fail closed. Expiry does not trigger
automatic withdrawal of existing artifacts. A later promotion needs a renewed
reviewed decision. Actor identity and ownership of the repository remain facts
the operator must verify; these tools do not authenticate human signatures.

This replaces **only this repository's provider-authorization gate**. It does not
replace the independent all-materials package-rights audit, notices/attribution,
security, provenance, integrity, dependencies, runtime or final release approval.
It cannot clear a `rights`, `runtime`, `technical` or `other` finding. A package
rights defect must never be relabeled `provider_terms`. A service assessment must
record the known adverse terms and actual behavior; the owner accepts that risk
without treating the concern as resolved. A known unverified provider gate uses
`authorization_unverified`, not the prior residual-uncertainty disposition.

Absent this nested exception, the prior schema 3 route remains unchanged.
`authorization_unverified` without an active matching exception blocks release;
an exception attached to any other service status is contradictory. Broad rights
remain false/pending, provider permission remains false, and content authorization
remains `not_established`. The derived `provider_authorization_exception_active`
flag and full attributed decision appear in each plan and independent audit.

### Nonwaivable review requirements

Before recording `package_distribution_review=verified`, independently inspect
**every** source file, third-party code, artwork, media, font, binary, notice and
other ZIP member, plus exported repository artwork, metadata and promotional
assets. Establish independent development, the licensing/ownership chain,
redistribution conditions, attribution and an affirmative basis to distribute
all those materials. An MIT label, public source, generic art or absence of video
cannot replace that review. Missing attribution, unknown ownership, unauthorized
redistributed assets, copied provider applications, leaked credentials and
access-control circumvention block. Independently licensed third-party code
retains its own applicable license/notice requirements.

Assess actual accounts/entitlements, remote images/text, streaming, caching,
downloads, SDKs, application-bundle parsing, identifiers, reverse engineering and
sharing behavior. Review actual provider terms, including adverse clauses, and
retain their precise evidence. A package-distribution assessment must address
any restriction requiring authorization to **distribute the package or operate
the integration**. Missing rights to bundled or exported material always block.
The repository's separate provider-authorization gate may be replaced only by
the explicit owner-risk decision above; this changes no actual restriction or
legal obligation. Separately
licensed provider-material distribution uses the strict route with affirmative
rights evidence. No DRM, region, payment or authentication bypass exception is
created.

Only provider-service terms/applicability, runtime-use restrictions or the
explicit unverified provider-authorization concern may be `provider_terms`.
Unauthorized package content, licensing/ownership or attribution findings may
never receive that category. Every
unresolved `rights`, `runtime`, `technical` or `other` risk remains a hard blocker.
Machine validation cannot determine ownership, contractual applicability, legal
substance or authenticate reviewers. A dishonest terms label supplies no rights
and is an invalid review, even if its JSON shape passes. Retain adverse findings;
never delete, mark resolved or hide them because the owner accepts distribution.

### Disclosure, audit and compatibility

The bundled notice must explain independent/unofficial status, no provider
affiliation/endorsement and the actual project support route. Reviewed
`release_text` must also identify unresolved terms and their official URL, lack
of provider/content authorization, account/entitlement obligations and the
limited effect of the owner decision. Human review verifies meaning, including
non-affiliation and attribution; code verifies member/path/hash, nonempty text
and faithful rendering. No keyword heuristic claims to make legal judgments.
The builder escapes public notice text as text. The auditor independently
reconstructs each complete public notice from hashed records, even when a forged
plan updates site hashes. Private review evidence is never exported as a notice.

Reports separately derive `package_distribution_eligible` (all gates other than
the final release decision), `accepted_terms_risks` (full findings, still in
`unresolved_risks`) and `release_blockers`. They preserve broad rights pending,
provider/content authorization not established, the exact owner actions and
runtime scope. The auditor repeats the v3 production conjunction independently
and compares the complete report. Qualification/preflight propagate those same
reports; private candidate profiles always remain publication-ineligible.
Plans keep `publication_authorized=false`. Toolchain pins now include builder,
contract, auditor, qualifier, preflight and interchange schema. Regenerate plans
when any changes; old plans are deliberately stale.

V1/v2 semantics and installer bytes are unchanged. New fields/categories reject
in old record versions; removing/downgrading the version cannot silently admit a
v3 record. Old consumers reject v3 (and its false broad-rights boolean). Upgrade
all consumers together before considering any successor review record. Retain
historical records immutably and cite supersession evidence; never change an old
false field merely to pass. New terms, behavior/assets, complaints, revoked
evidence or adverse distribution findings require renewed review. Withdrawal
and publication remain separately authorized existing processes.

The regression fixtures in `tests/test_unofficial_integration.py` illustrate a
complete synthetic record and blocked alternatives. They are never live approval
records, provider permission or native-runtime proof. Tastemade receives no
special case and remains subject to its existing attribution, distribution,
runtime-scope and final-approval gates.

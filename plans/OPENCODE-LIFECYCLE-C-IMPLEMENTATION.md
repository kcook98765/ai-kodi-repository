# Phase C implementation and qualification

Status: **local implementation and verification PASS; Piers static qualification
UNVERIFIED; all native/runtime compatibility UNVERIFIED**. Base
`f2d8f3330d76a982d6f66601d8ec6ae2bc9c9c83`, 2026-10-23.

Work remains local in the existing isolated lifecycle worktree. No canonical
activation, push, publication, production credential/permission change, hosting,
live Kodi Lab operation or Phase D work occurred.

## 1. Multi-version qualification

| Requested target | Static tooling and observed controls | Native/runtime result |
| --- | --- | --- |
| Matrix 19.5 | PASS: Kodistubs 19.0.3; six positive Toolkit stages; invalid signature rejected; getSettings API rejected | UNVERIFIED |
| Nexus 20.5 | PASS: Kodistubs 20.0.1; six positive stages; invalid signature rejected; getSettings accepted | UNVERIFIED |
| Omega 21.3 | PASS: Kodistubs 21.0.0; six positive stages; invalid signature rejected; getSettings accepted | UNVERIFIED |
| Piers 22 preview | UNVERIFIED: no published or independently qualified matching 22 environment; explicit unverified task receipt | UNVERIFIED |

PASS concerns **matching-branch API checks under Toolkit's Python 3.10 syntax/type
target**, not complete embedded-Python/release/platform compatibility. Matrix can
use earlier interpreters; mypy 2.4.0 cannot target them. Native interpreter evidence
remains missing. Manifest Python floors/platform metadata do not supply acceptance.

The existing Nexus environment is unchanged. Matrix/Omega are local environment
copies with exact hash-pinned stub wheels installed without dependency resolution.
Trusted source/interpreter/distribution metadata/cache identities are bound per
lane. Each offline index has its own verified URL, filename, digest and acquisition
time, rechecked before cached returns and during review. Drift fails closed.

Piers is never substituted with another major's stubs. A pinned upstream
22.0.0a3 source exists but was not independently qualified/installed as preview
tooling here. Published matching tooling or a reviewed preview-source qualification
remains necessary. See [tester qualification](../reports/lifecycle-c/TESTER-QUALIFICATION.md).

## 2. Complete isolated candidate feed

The existing retention failure was correct: candidate URLs changed production
installer bytes under an existing ID/version/hash. The implementation adds an
explicit candidate-only context to the existing builder and independent auditor:

- Default production/fixture config retains the repository.ai.kodi identity gate.
  Original production config, ledger and installer source stay unchanged as
  private staging baseline evidence. Without a context, legacy candidate behavior
  and its retention guard remain unchanged.
- Only candidate profile selects config/candidate-repository.json. Its context
  binds the task/production hashes, a distinct
  repository.ai.kodi.candidate.<task-id> ID, a visibly LOCAL CANDIDATE installer,
  and distinct HTTPS origin. Production :443/trailing-dot aliases also reject.
- releases/candidate-manifest.json is a new identity-bound history namespace,
  never an emptied production ledger. Every candidate ZIP/hash and installer is
  retained. Changing destination cannot replace immutable installer bytes; use a
  new task/identity or a genuine version change.
- Inputs are exact frozen task ZIPs and derived **pending strict-v2 drafts**.
  Original records remain immutable/hash-bound. Candidate context rejects v3 and
  first-release exception records, preventing eligibility manufactured from empty
  test history. Rights/static/runtime/final acceptance stays false/pending.
- Optional owner-enrolled member tasks support dependencies and older candidates.
  Exact IDs/digests are resolved under locks, never arbitrary paths. Same-ID
  successors retain source repository identity; collisions reject. One highest
  numeric version is selected per ID/lane; earlier ZIPs remain identical downloads.
- Copied, hash-pinned trusted builder/qualifier/auditor scripts produce all four
  catalogs/sidecars, packages, artwork, candidate installer/root mirrors, index
  and inventory. Required dependency misses/cycles fail; optional misses warn.
  External dependency snapshots remain unavailable until separately reviewed.
- Independent audit rederives identities, packages, records and complete site
  inventory from reviewed inputs. A forged producer plan with updated hashes
  cannot admit substituted content. State freezes all staging inputs/outputs,
  receipts, parent/source/static evidence and feed digest. Review does not rebuild.

Operator enrollment may select candidate_base_url and prior feed_members. Default
`https://candidate.invalid/<task-id>/` is a non-routable placeholder. No hosting
service was created. Manager uses existing kodi_build action=feed; tester/reviewer
use existing qualification/review tools. Tool names and effective grants are
unchanged. Production preflight still rejects candidate plans; no publisher,
GitHub writer or approval creator exists.

## 3. Exact Phase C source changes

Relative to the preserved A/B implementation:

| File | Change |
| --- | --- |
| .gitignore | Exclude generated candidate identity config/ledger |
| AGENTS.md | Point to approved A-C local scope |
| config/LIFECYCLE-LANES.json | Stub acquisition pins and static-language scope |
| config/LIFECYCLE-TASK-SCHEMA.json | Optional candidate endpoint/member bindings |
| docs/AGENT-INTEGRATION.md | Optional local Phase C capabilities |
| docs/ARCHITECTURE.md | Candidate context/history and production boundaries |
| docs/LIFECYCLE-PREPARATION.md | Lane/feed workflow, native authority and activation |
| scripts/audit_candidate.py | Independent candidate context/ledger and pending-only checks |
| scripts/lifecycle.py | Registry/task/feed binding, per-lane receipts and integrity checks |
| scripts/lifecycle_feed.py | Complete private staging/build/freeze/verification |
| scripts/lifecycle_lanes.py | Closed registry, index verification, operator-only local setup |
| scripts/opencode/kodi.ts | Bounded Phase C arguments on existing tools |
| scripts/qualify.py | Explicit candidate config/ledger; fixture defaults preserved |
| scripts/repository.py | Candidate-only identity/history; production gate preserved |
| tests/test_lifecycle_feed.py | Sixteen feed/retention/source/cache/publication controls |
| tests/test_lifecycle_lanes.py | Twenty-two lane registry/index controls |
| plans/OPENCODE-LIFECYCLE-C-IMPLEMENTATION.md | This completion record |

Ignored local additions include Matrix/Omega environments/pinned wheels, the
installation registry, task data/staging/feed and evidence. Only this worktree's
local tool copy was updated. Shared Toolkit/Nexus and canonical profiles/adapters
remain preserved. Original approval_contract.py/check_publication.py are unchanged.

## 4. Tests and independent review

- **Final full suite: 192 run, 189 passed, 3 optional schema tests skipped** in the
  unchanged Toolkit environment. Those three then passed using the already
  installed system jsonschema, plus six task-schema checks. No shared dependency
  was installed or changed to hide skips.
- **22 lane tests passed**, plus actual per-lane trusted CLI positive/negative
  controls and the Matrix-versus-Nexus/Omega API boundary.
- **16 feed tests passed**: repeatability, distinct identity/origin, frozen drift,
  forged plan/site hashes, production refusal, dependency closure/failure,
  retained old candidates, source continuity, cached index drift and original
  production installer byte preservation.
- **Actual OpenCode task workflow passed**: public immutable-source acquisition,
  package preparation, three static passes/Piers unverified, full feed build,
  tester verification and independent reviewer-tool verification. It uses the
  existing MIT Toolkit sample and synthetic independent-source regressions;
  it is not new independent-add-on admission or native acceptance.
- **Actual permission-engine checks passed**: three roles' resolved rules and
  frontmatter match canonical after rebinding; all 21 harmless canaries match.
  Legacy zero-argument fixture validation/build/reproducibility/review passed,
  with 26 loopback paths and 17 selection cases. Fixture site/package bytes match
  A/B. No model inference or service was started.
- **Independent review PASS**: 24 reviewed files hash-pinned; ten independent
  focused reruns passed. Final evidence inspection rehashed all 55 live candidate
  staging files and checked production preservation, scope and tester/reviewer
  agreement. Origin/index findings were fixed before final source freeze.

Live candidate ID:
`repository.ai.kodi.candidate.e76d27008efd48bbbe81cf648c6d0de0`.
Site manifest SHA-256:
`355e5ce0471c250b7acac3f40aac4680d073a4b34038e095111c32f173c41bfe`.
The complete site has 24 files/two packages, with repeat-build proof and 24 derived
loopback URL checks. No hosted candidate HTTPS/native verification occurred. Source remains
`kcook98765/kodi-agent-toolkit@552b0b949220f2d545ab42a7f27d1826a535c686`.
Original warnings/coverage limits remain in the raw receipts.

## 5. Security, retention and recovery

No safety gate needed weakening. Original production installer SHA-256 remains
`f4ec0c67329e70516baa824606f9133ff95516bea0cfcee6370fa2ac7a0afdad`.
Candidate data stays in denied task storage with its own namespace and full
inventory. Production config/ledger/catalogs and retained package bytes remain
unchanged. No production output promotion or remote write occurred.
Read-only public HTTPS checks independently matched all four production catalogs,
both retained package ZIPs and the bootstrap page against the approved gh-pages
commit. Canonical private incoming ZIP/review-record files are not materialized;
their approved bytes/evidence still require restoration before a production build.
No approval record was invented to fill that gap.

A 22-file A/B source/local-profile snapshot was independently extracted and
hash-verified before editing. Archive SHA-256:
`0f9517b8242c54330c645a9d0211664644ec516cb15f2bf167a1f065e6faae0c`.
Rollback restores those reviewed local source/config bytes, retains C evidence
and re-enrolls work under current authority. It does not erase task data, rewrite
history, change shared Toolkit or roll back production.

All 24 canonical audited files remain preserved. Canonical main still has the
local unpushed f2d8f333 documentation commit. Final verification records remote
main/gh-pages preservation and original artifact/input hashes. No Lab credentials,
grants, instances, services or infrastructure were changed or used.

## 6. Remaining native-testing limits

Local static/dependency/source/package checks, complete feed audit, parser/selection
replay and ephemeral loopback HTTP are executable. Repository roles still have MCP
disabled; no exact target authorization is established here. Live Lab discovery,
status, install, navigation, launch, update and cleanup are not authorized/tested
in this phase. This does not imply a target is absent.

Native acceptance needs an exact disposable UUID/platform/build/version, supported
deployed schemas/grants, source/ZIP/feed digests and reachable trusted HTTPS feed.
Test bootstrap install, correct lane/category/dependencies, unchanged refresh,
normal higher-version update, retained downloads, scoped features and recovery.
Old-production-to-new testing additionally needs approved published baseline
restoration/installation under explicit authority; candidate history supplies no
production acceptance or downgrade authority. Default .invalid URLs cannot be
native-tested. Full target-Python and Piers tooling coverage remain unresolved.

## 7. Canonical activation prerequisites

1. Owner approval of reviewed source adoption and separately pending documentation;
   no push is implied by Phase C acceptance.
2. Recovery-tested backup and explicit migration of ignored profiles/adapters and
   installation state. Bind exact roots, qualified environments and caches while
   preserving model/provider/permissions.
3. Verify startup/schema/version integrity and actual engine/delegation behavior,
   then an owner-selected operational pilot with an independent add-on/successor.
   Debug-tool checks here do not establish natural-language autonomous operation.
4. Resolve tooling/Python/dependency/extension gaps for any claimed scope. Establish
   explicit target/hosting authority before native tests; never retarget a frozen
   candidate installer or point it at production.

## 8. Phase D owner approval/publication prerequisites

Real rights/licensing, technical, runtime and final owner decisions must replace
pending records under existing contracts, retaining immutable prior evidence.
Candidate mechanical PASS supplies none of them.

Prepare an independently audited **production** proposal with exact source/package/
record/site/asset digests, fresh main/gh-pages heads and protection, retained history
and recovery evidence. Obtain authenticated owner approval bound to that result.
A candidate site hash cannot authorize different production installer/catalog
bytes. Publication additionally requires a separately implemented trusted human
gate, short-lived scoped credentials kept away from add-on code, HTTPS/mirror
checks and separately authorized native evidence. No such integration is enabled;
Phase D has not begun and publication remains attended and approval-controlled.

## Local evidence

Ignored reports/lifecycle-c contains ab-baseline.json/tar, TESTER-QUALIFICATION.md,
lane-tooling-qualification.json and summary, live-task.json, live-cycle.json and
*-engine.json, final-permissions-and-fixtures.json and summary,
schema-supplement.json, REVIEWER.md, reviewer-focused.json,
reviewer-final-evidence.json and final-verification.json. They are not release
artifacts or approvals.
public-preservation.json records the separate read-only production HTTPS comparison.

Independent review SHA-256:
`8f450a58964c03bc180ff0915f4db92ffeb93b781b8d0e49a42a6d7e940d61a3`.
Final permission/fixture receipt SHA-256:
`bd32cd1e09221ccf3d7a57886a6c340c0c132e6fba7751858edd27d2ca7355db`.

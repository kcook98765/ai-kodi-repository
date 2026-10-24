# Phase D1/D2 local implementation

Status: **D1/D2 LOCAL IMPLEMENTATION COMPLETE; independent reviews PASS**.
Qualification is recorded against pinned local source bytes. Nothing in this
report authorizes canonical activation, GitHub writes or native Kodi operations.

Authority: owner-approved local, nonprivileged portions of
[the reviewed Phase D proposal](OPENCODE-LIFECYCLE-D-PUBLICATION-DESIGN.md), SHA-256
`9cad8c39e1001ae2c430d57ce50c04b90ed1a9d14605ee3412d168781e06dba8`.
The proposal is retained unchanged. A recover-tested pre-D1/D2 source/profile
snapshot and its hashes are in ignored `reports/lifecycle-d12/baseline.json` and
`baseline.tar`. Canonical main and prior historical worktrees remain untouched.

## Implemented components

- Canonical closed P/R/E documents bind immutable source/package identity,
  per-lane evidence, original review records/rights/provider dispositions,
  dependency/catalog/complete-site inventories, expected heads, typed Release
  assets, destination, prior/successor ledger and exact operation sequence.
- Preparation and frozen verification reuse existing builders, independent ZIP/
  site audits, qualification and approval-contract semantics. Submitted code is
  never imported or executed as an add-on or verifier.
- Explicit local simulated owner authorization binds E digest, destination,
  audience, nonce and expiry. Consumption, revocation and replay checks are
  separate from technical eligibility and independent frozen review.
- The concrete file-backed fake is the only backend. It models create-only
  tag/draft/assets, byte download verification, immutable Release publication,
  exact-parent complete Pages promotion, public observation and ledger completion.
- The one-shot local operator journals intent and receipts, consumes approval
  before effects, blocks subsequent releases on incomplete state and requires
  fresh exact-state recovery proposals/approvals. Status/reconcile never resumes
  writes. Forward recovery retains immutable historical package bytes.
- Manager prepares blocked candidate publication payloads through existing build
  tools; tester/reviewer independently evaluate frozen copies through existing
  qualify/review tools. No new effective role permission or model approval/
  execution action is added. Existing zero-argument fixture behavior is retained.
- A disabled approval workflow example is stored outside `.github/workflows`.
  It provides no authorization and cannot run as a workflow in this checkout.

Only explicitly synthetic inputs can complete a successful local simulation.
Real package candidates preserve release blockers and production authority false.
Local same-user records authenticate no human. There is no HTTP GitHub backend,
token support, privileged identity, service or real authorization verifier.

## Changed files

The final evidence inventory compares all source files to the preserved D1/D2
baseline. Files already modified by A–C are not attributed to this phase unless
their bytes changed again here.

| File | D1/D2 change |
| --- | --- |
| `scripts/publication_proposal.py` | New canonical frozen proposal preparation and verification |
| `scripts/publication_verify.py` | New read-only local Release/site byte observation |
| `scripts/publication_fake.py` | New file-only fake destination and immutable artifact effects |
| `scripts/publication_operator.py` | New simulated approval, journal, state machine and recovery |
| `scripts/lifecycle_publication.py` | New task-bound role preparation/evaluation bridge |
| `docs/PUBLICATION-PROPOSAL-SCHEMA.json` | New closed interchange schema |
| `scripts/lifecycle.py` | Local publication actions within existing tool permissions; new trusted toolchain pins |
| `scripts/opencode/kodi.ts` | Existing build/qualify/review schemas gain local publication action |
| `scripts/opencode/publication-approval.yml.example` | Disabled, inert future workflow example |
| `tests/test_publication_proposal.py` | Proposal/integrity/eligibility/schema tests |
| `tests/test_publication_operator.py` | Simulation/approval/fault/recovery tests |
| `tests/test_lifecycle_publication.py` | Actual task-bound role integration and denial tests |
| `tests/test_publication_security.py` | Independent adversarial security tests |
| `tests/test_publication_acceptance.py` | Independent black-box acceptance tests |
| `docs/PUBLICATION-OPERATOR.md` | Actual local usage, truthfulness and deferred deployment instructions |
| `docs/AGENT-INTEGRATION.md` | Standing workflow links to local-only preparation |
| `docs/RELEASE-WORKFLOW.md` | Local simulation boundary, unchanged actual release gates |
| `AGENTS.md` | Local role instructions, no authorization/permission broadening |
| This report | Implementation results and explicit remaining authority boundaries |

Only the isolated worktree's generated tool copy is refreshed for local engine
qualification. Its generated project config and role permission frontmatter stay
unchanged. No canonical profile or shared Toolkit/Lab file is edited.

## Qualification

The final evidence inventory is `reports/lifecycle-d12/final-verification.json`.
Its referenced raw reports distinguish these completed checks:

| Check | Result |
| --- | --- |
| Full regression through existing fixture validation | 256 run: 252 passed, four optional JSON-schema checks skipped |
| Supplemental schema checks with existing system validator | 4/4 passed; no dependency installation |
| Existing OpenCode permission engine | 21/21 canaries; three resolved roles match canonical and frontmatter/config are unchanged |
| Developer handoff role | Resolved permission rules also match canonical; publication canary denied without execution |
| Existing fixture tools | All five original manager/tester/reviewer tool calls PASS |
| Actual publication preparation tool serialization | Manager build, tester qualify and reviewer review return the same blocked frozen payload; extra bridge destination field rejected |
| New publication tests | 64 methods: proposal 16, operator 17, independent security 13, independent acceptance 12, role integration 6; fault loops also cover before/after all eight stages |
| Independent security review | PASS; no blocking findings; includes expired schema-3 policy observation, concurrent revocation and deleted-latch rejection |
| Independent acceptance review | 12/12 PASS on unchanged pinned files; actual CLI, isolated Python, SIGTERM after remote-fake effect, replay and fresh recovery |
| Retained successful simulation | Eight stages reach RECORDED, immutable artifacts retained, replay rejected without new effects; production authority remains false |

The final hash-bracketed standalone full-regression receipt is retained alongside
the engine/fixture gate. These are not native Kodi, HTTP/TLS, GitHub environment/
ruleset, App permission or production evidence. The file fake verifies state and
bytes; it cannot establish those live controls. The disposable bare-Git test
verifies ordinary local non-fast-forward rejection, not GitHub branch protection.

Fixture ZIP hashes, catalogs and complete site-manifest hash match Phase C.
The fixture plan digest changes because the fresh Toolkit validation receipts
have new evidence hashes; immutable package/site bytes remain unchanged.

Independent reviews are `reports/lifecycle-d12/SECURITY-REVIEW.md` and
`TESTER-REVIEW.md`, with source hashes in their adjacent JSON receipts. A successful
full simulation and its exact P/R/E/artifacts/fake state are retained under
`reports/lifecycle-d12/retained-simulation/` and `retained-simulation.json`.

The success path must reach `RECORDED` while reporting simulation-only and false
production authority. Negative cases must show zero effects for invalid
authorization/preflight, or only a recorded permitted prefix for partial failure.
Expired approval must stop writes while leaving read-only observation available.
Replayed approval cannot start another transaction. An altered destination or
package cannot retain an old digest/approval, and fresh self-consistent forged
inventories must still fail independent semantic verification.

## Production blockers and remaining limitations

- Exact retained private production ZIPs and original approved review/evidence
  records are missing from this worktree. The existing public hash/ledger cannot
  recreate an owner decision or establish its current validity.
- Piers 22 static remains UNVERIFIED. Phase C Matrix/Nexus/Omega API checks do not
  establish target-interpreter or native acceptance; those remain UNVERIFIED for
  all Phase C lanes. Real pending records remain pending and blocked.
- Expired/incomplete decisions and exceptions are not auto-renewed. Existing
  schema 3 routes keep their exact initial-artifact/provider/scenario/lane/history/
  expiry requirements and underlying false/unverified facts.
- Current implementation has one newly released add-on per proposal, alongside
  complete retained site/history. Multiple independent new releases need
  separate proposals or a later reviewed multi-Release extension.
- The concrete fake has no network/remote Git backend. Public HTTPS, actual
  Pages deployment, immutable Release enforcement and protected PR finalization
  remain future qualification work. Simulated results cannot clear those gates.
- Existing retained review records bind source URL/commit, but do not store
  historical numeric GitHub repository/owner IDs. Current enrolled numeric IDs
  and retained source-URL continuity are checked; future live admission needs
  retained prior task identity evidence before claiming historical numeric-ID
  continuity. Missing identity evidence cannot be supplied by a simulation.
- Same-user local stores and local simulated identities are not a hostile-code
  OS boundary or human authentication. Deployment requires a separate identity
  and restricted trusted code/store/credential custody.
- Whole-store restore cannot be detected solely by a hash chain inside that
  store. Recovery/reinstall must start disabled, change installation epoch and
  require owner-led reconciliation before a future live operator is enabled.

## Next stage and approval decisions

Review local implementation/evidence first. The next controlled stage is D3
deployment-boundary and transport qualification against an owner-selected
disposable destination, after separate approval of its exact resources and
credential custody. No live transport or remote authorization is enabled here.

Before that work, owner decisions are required for the isolated target, separate
OS publisher identity/install scope, App identity and permissions, owner numeric
identity, protected approval environment/revocation signal, branch/tag rulesets,
immutable Releases and durable backup/recovery policy. Production source adoption,
canonical activation, native target tests, ledger PR/merge capability and each
exact production release remain separately approved stages.

No decision is needed to retain truthful blockers. D1/D2 introduces no policy
exception and does not convert technical review or local test approval into
production authorization.

# Local publication implementation: D1/D2

This implementation is a local simulation. It cannot publish to GitHub, accept
GitHub owner authorization, use production credentials or operate Kodi Lab.
The [reviewed architecture](../plans/OPENCODE-LIFECYCLE-D-PUBLICATION-DESIGN.md)
remains the technical proposal for future authorized deployment.

The new proposal component freezes package/site/input/evidence bytes with their
source identity, per-lane outcomes, review and exact destination. Canonical P,
independent R and execution E have separate digests. Changing a package, record,
destination, operation, expected head or evidence invalidates the old approval.
Existing builders, independent audits and approval contracts still decide release
eligibility. Native/interpreter results remain unverified when absent; an owner
publication decision cannot supply them or enlarge an existing exception.

All executable proposals and approvals use `mode=local-simulation`. The sole
destination is `simulation/ai-kodi-repository`, numeric ID 1, with the reserved
origin `https://publication.invalid/`. Only synthetic test data can complete a
successful simulation. Real candidate preparations remain blocked and carry
false publication authority. A simulated PASS is a state-machine result, never
a production release, GitHub enforcement proof or native acceptance.

## Role workflow

After an owner-enrolled task has a complete frozen candidate feed:

1. Manager calls existing `kodi_build` with the task ID/digest and
   `action="publication"` to freeze a blocked local proposal.
2. Tester calls existing `kodi_qualify` with that task ID/digest and
   `action="publication"` to verify the frozen snapshot and blockers.
3. Reviewer calls existing `kodi_review` with that task ID/digest and
   `action="publication"`, then records substantive findings in its existing
   permitted review report. A successful machine verification is not an
   independent human decision or owner approval.

No role gains a new tool grant. There is no role action to issue simulated owner
approval, consume a nonce, execute publication or bypass a blocker. General shell,
GitHub writes, configuration edits and MCP remain denied. Empty-argument fixture
behavior is preserved. Changed trusted scripts/schema invalidate old task pins;
enroll a new task rather than silently migrate A–C evidence.

## Simulated operator and recovery

The local operator uses an isolated file-backed fake GitHub and a durable local
journal. It checks the exact proposal, simulated owner/destination/audience,
expiry, revocation and current expected remote state before effects. Approval is
consumed under the destination lock before the first mutation. Fake Releases
use create-only tags/assets and verified downloads, Pages uses a complete exact-
parent promotion, and ledger completion is distinct from public byte verification.

An interrupted or ambiguous transaction blocks a later release. Read-only status
and reconciliation do not resume writes. Recovery needs a fresh execution
proposal/nonce and simulated approval bound to the exact observed fake state and
completed prefix. Historical package bytes remain immutable during both release
and forward recovery. No force, clobber, delete/recreate, automatic rebase or
installed-Kodi downgrade is available.

The same-user local store is not the future OS security boundary. Local fake
approvals authenticate no human and are invalid for production. Restored state
must not automatically resume a publisher; future deployment needs disabled
restore, new installation epoch and owner-led reconciliation. The executable
interfaces and reproducible examples are exercised by the publication tests;
use each script's `--help` for its local CLI rather than supplying a remote URL.

## Deferred operator setup

Before a genuine publisher can be implemented or enabled, separately approve:

- A locked separate publisher identity and trusted installed code, sealed evidence
  store, credential custody, restricted invocation, backup and recovery policy.
- A scoped GitHub App, separately capped tokens, protected main and Pages/tag
  rulesets with no force/deletion bypass, and future immutable Release enforcement.
- A trusted approval-only workflow and owner-required environment with self-review
  and admin bypass disabled, exact owner/App/environment IDs and owner revocation
  control issue. The disabled `.yml.example` under `scripts/opencode/` is inert
  documentation, not an enrolled workflow or proof producer.
- A real read-only approval verifier and real transport implementation, qualified
  against a separately authorized isolated GitHub destination before production.
- Exact retained production ZIPs and private original review/evidence records,
  fresh release-gate assessment, and a protected ledger/config finalization path.
- Canonical adoption/activation and any exact native targets or production release.

None of those deployment or live-test actions is authorized by D1/D2. Missing
retained inputs, Piers static qualification, target-interpreter/native acceptance
and expired/incomplete decisions remain explicit production blockers.

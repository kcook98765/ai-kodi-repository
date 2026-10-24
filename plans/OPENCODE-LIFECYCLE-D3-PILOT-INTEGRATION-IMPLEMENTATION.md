# D3 disposable pilot integration implementation

Status: implemented locally; offline verification and independent reviews passed.
Live publication and canonical activation remain disabled.

## Implemented scope

The isolated lifecycle worktree extends the existing task adapter and OpenCode
manager/tester/reviewer roles with the separately versioned disposable-only
`d3-pr-pilot-v1` profile. The approved
[minimal pilot plan](OPENCODE-LIFECYCLE-D3-MINIMAL-PILOT-PLAN.md) remains authoritative.

The new typed HTTPS/App transport verifies the enrolled repository, source,
remote heads and complete protection state; creates only exact scoped tags,
Releases/assets and Git objects; verifies downloaded assets; promotes a complete
non-force Pages tree; verifies the actual Pages deployment/public bytes; and
normally merges the exact ledger PR. It provides GET-only observation/reconciliation.
There is no general request API, administrative write, delete/replace/force,
ambient token/CLI/SSH fallback or production enrollment. Actual App signing,
network effects and server enforcement remain unqualified.

App tokens are explicitly requested for one repository and narrowed by operation.
The maximum permission set is Contents write, Pull requests write, Actions read,
Pages read, Administration read and Metadata read. No Checks/Statuses, workflow
write, Pages write or administrative write permission was added. CI is verified
through the pinned Actions workflow/job and ordinary server-enforced merge gates.

Fresh structural candidate inputs are independently audited. A campaign-specific
candidate installer is rebuilt through existing deterministic builders with inert
first-party art/source. Updates preserve historical runtime ZIPs, original pending
review evidence, installer bytes, published ledger facts and complete Pages files.
The unchanged Phase C per-task installer workflow remains separate.

## Exact owner decision and recovery

P binds immutable source, task/installation/epoch, code, packages/digests, lanes,
full Pages/ledger changes, historical state, policy and destination. Trusted role
context and separate permitted reports bind manager/tester/reviewer sessions and
tools. Independent tester/reviewer evidence seals R; manager cannot impersonate
the child roles. Technical evidence supplies no publication authority.

A separate owner-installed exact-task metadata grant permits only reviewed
ledger/config Git objects and the proposal branch/PR before approval. The private
grant is checked independently before each staging effect. A public config hash
is not an issuer. The actual staged PR identity/head/base then seals E with P/R,
nonce, destination, audience and expiry, with a deterministic safe public summary.

The owner reviews local packages/private evidence and the public PR, then approves
once with the exact E/nonce/repository/expiry text. The verifier requires the
pinned numeric human User, typed review identity, exact commit/body/scope and valid
chronology; generic approval is rejected. Dismissal, changes requested, closure
or exact revocation comment revoke authority. Observed revocation is latched.
Nonce and review ID are consumed durably before effects. Final fresh owner proof
must match the consumed review identity; a different later review cannot silently
supply authority. All synthetic enrollment/proofs remain mock-only.

The installation journal records generation-linked state, intent before effect,
receipt, consumed nonces/reviews, revocation and finalization. Incomplete work
blocks later releases. Read-only reconcile observes ambiguous outcomes. Recovery
preserves exact P/R/artifacts, derives a fixed task-local recovery execution and
requires fresh bounded staging plus a new E/nonce/owner review. Lost final merge
receipts can be observed and finalized locally only after exact verification.
Historical Releases include their normalized asset/checksum inventory in retained
journal evidence. Subsequent updates compare it before new effects. Forward
corrections retain immutable history. Whole-store rollback/loss requires disabled
execution, independent reconciliation and a new enrollment epoch.

## OpenCode status

The source tool adds local `action=publication_pilot` preparation/review and an
optional manager-only `kodi_publication` helper. The closed helper accepts only
request/status/execute/reconcile and task/E identifiers. Paths, credentials,
backend selection and approval issuance are absent from model arguments.
The inactive overlay is not installed. Existing six active role/tool/config files
are byte-preserved; the canonical checkout and shared Toolkit are unchanged.
No canonical workflow was activated. Old task bindings are not silently migrated;
fresh pins are required after eventual adoption.

Public opt-in configuration and private staging/key custody are documented in
[PUBLICATION-D3-LOCAL.md](../docs/PUBLICATION-D3-LOCAL.md). Neither configuration nor
actual credentials are installed. Existing host administration is retained. No
separate OS isolation is claimed and no account/security migration is required.
The bootstrap helper is inventory-only with no apply/settings client.

## Exact files in this phase

Changed existing phase files:

- `docs/AGENT-INTEGRATION.md`
- `docs/PUBLICATION-D3-LOCAL.md`
- `scripts/lifecycle.py`
- `scripts/lifecycle_adapter.py`
- `scripts/opencode/kodi.ts`

Added:

- `scripts/lifecycle_pilot.py`
- `scripts/opencode/pilot-bootstrap.py`
- `scripts/opencode/pilot-profiles.json`
- `scripts/publication_cli.py`
- `scripts/publication_github_live.py`
- `scripts/publication_pilot.py`
- `scripts/publication_pilot_candidate.py`
- `scripts/publication_pilot_contract.py`
- `scripts/publication_pr_owner.py`
- `tests/pilot_github_model.py`
- `tests/test_lifecycle_pilot.py`
- `tests/test_publication_github_live.py`
- `tests/test_publication_pilot.py`
- `tests/test_publication_pilot_contract.py`
- `tests/test_publication_pr_owner.py`
- This implementation report.

Ignored local evidence is under `reports/lifecycle-d3-integration/`; it is not
published or presented as remote/native acceptance. Earlier uncommitted lifecycle
work was preserved. Existing mock-only publication modules were not modified.
Separate versioned sibling modules preserve their closed schemas, concrete mock
senders and journal behavior while reusing their pure builders/auditors/helpers.
This is an implementation organization choice within the approved profile scope.

## Verification

All **418 distinct discovered tests** are covered with no unresolved failure:

| Cohort | Final result |
| --- | --- |
| Existing fixture/A-B/C/D1-D2/strict-D3 regressions | 322 passed |
| New transport, contract, owner, role and protocol cases | 59 passed |
| New publication/journal/readiness/recovery cases | 37 covered: 34 passed initially; three failed cases passed focused retests after correction |
| Existing OpenCode effective permissions | 21 unchanged actual-engine canaries across manager/tester/reviewer |
| Existing fixed fixture tools | Build, qualify and review passed |
| Temporary opt-in tool registration | New source compiled/loaded; manager reached fail-closed bridge; tester/reviewer denied |
| Independent security review | PASS: 63 completed unaffected checks plus five final affected/boundary checks; 19 hashes stable |
| Independent tester review | PASS: 16 focused checks plus five additional fault cases; the two affected recovery faults retested after the helper fix |

The final correction uses the existing local operation-ID helper during partial
reconciliation; the negative deployment test accepts its clearer hard-failure
message. Earlier fixes addressed tag-variable shadowing in updates, actual Node
stdin ordering, private staging issuer validation, semantic policy checks,
consumed-review identity, historical checksum inventories and asynchronous Pages.
Unchanged evidence was reused; logs preserve unsuccessful attempts and focused
resolutions instead of presenting an interrupted aggregate as a clean rerun.

The [coverage summary](../reports/lifecycle-d3-integration/full-gate.json) records
all test identities, the three initial failures, their passing targeted receipts
and final runtime pins. [Security review](../reports/lifecycle-d3-integration/SECURITY-REVIEW.md)
and [tester review](../reports/lifecycle-d3-integration/TESTER-REVIEW.md) distinguish
mock evidence from live claims. Python compilation and whitespace checks passed.

Final engine SHA-256 is
`55ec6e61f8f6f5e2c4a812cc86b3fedacbbb68905c549e107019db7a8216b10b`;
transport is `c1d5fe323e89500ff085842d51bcc3a3e61148009561d61a3933164fa7aefe77`;
CLI is `048c181e91a53b970f1ac70fc0b662167448ac51aba5ef4a09265a5627bd0dc6`.
93 pre-phase files were byte-preserved; exactly five existing phase files changed.
All 51 canonical tracked files, clean canonical status, six active tool/role/config
files and shared Toolkit source were preserved. No publisher opt-in/configuration,
production credentials, GitHub changes or Kodi operations were introduced.

## Remaining live pilot prerequisites and owner decisions

No additional authority is requested to complete this offline implementation.
Live work requires separate owner approval for:

1. Creating the preferred qualification Organization/repository and selected-repo
   GitHub App, with reviewed bootstrap source/workflow/CODEOWNERS and empty
   published ledgers/Pages baseline.
2. Installing and reading back the exact rulesets, immutable Releases, trusted CI,
   normal-merge settings, branch Pages source and environment policy. App bypass
   must not bypass review, CI or historical integrity.
3. Enrolling actual numeric IDs, immutable source commits, workflow/environment
   identities and policy observations; accepting private key custody under the
   retained administration arrangement and issuing only short-lived App tokens.
4. Explicitly adopting the optional disposable tool/profile/configuration,
   enrolling fresh tasks and separately authorizing their metadata-only staging.
5. Reviewing and approving each exact frozen E before the live 1.0.0 pilot,
   interrupted recovery or 1.1.0 update. There is no general future-release grant.

Real credential/signing/token issuance, human GitHub review, server protections,
Actions/Pages deployment, public HTTPS and live recovery remain unqualified.
Production additionally requires retained private production inputs, current
rights/provider dispositions, qualified Piers tooling, target interpreters,
native acceptance and valid independent/owner evidence. No absent evidence is
upgraded to PASS. Claw hardening remains deferred; Kodi Lab and devices are untouched.

Two remaining limitations are explicit. Read-only inspection found `cryptography`
absent from the currently configured Toolkit helper interpreter, so actual App
signing fails closed until a separately reviewed publisher interpreter/dependency
setup; no shared environment was modified. An unclaimed fresh recovery E that
expires before execution needs trusted operator preparation of another immutable
recovery packet/new E/nonce/review. The current model helper does not renew that
pending packet automatically; no expired packet or approval may be overwritten
or reused. This fails closed and is not a production-authority exception.

The initial Pages seed is deliberately an empty-tree commit, consistent with the
existing empty-ledger retention guard. The first approved publication creates the
complete index/`.nojekyll`; an extra preseed landing page would be rejected. This
narrows bootstrap preparation without weakening retention. The live pilot must
also measure actual API quota/latency against the current 240-second helper
limit; simulated timing does not qualify those operational limits.

The final verification extension handles normal asynchronous Pages/public
readiness with bounded GET-only polling. A journaled first deadline is shared by
both public gates, capped at 120 seconds/E expiry, with five-second maximum waits.
Only typed pending deployment, public 404 and exact known-before mutable metadata
staleness are retried. Wrong ZIP/sidecar hashes, unknown content, unsafe identity,
failed deployment, expiry, revocation or changed consumed review remain blockers.
No late PASS, approval renewal or write retry is introduced.

One independent queued-readiness/finalization-recovery scenario observed 3,285
mock HTTP requests, seven simulated token issuances and 39 publication mutations.
The total includes public Pages and App calls and is not an authenticated REST
quota count. Before live execution, measure authenticated request usage, response
headers and serialized latency; schedule the two pilot versions within the
installation's rate budget and review the bounded helper timeout if needed.
GitHub documents a minimum 5,000 requests/hour for installation tokens, subject
to enterprise/scaling rules; tokens for the same installation share that budget.
[GitHub rate-limit documentation](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api).
No quota fallback, longer timeout, credential change or permission expansion was
introduced. No additional authority is needed for the completed offline work;
these are explicit prerequisites/decisions for the separately approved live pilot.

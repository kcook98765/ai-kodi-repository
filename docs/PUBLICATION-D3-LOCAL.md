# Local D3 qualification components

The reviewed [minimal pilot plan](../plans/OPENCODE-LIFECYCLE-D3-MINIMAL-PILOT-PLAN.md)
now has a separate, opt-in `d3-pr-pilot-v1` implementation. Real HTTPS/App transport
code exists; this phase exercises it only with mocked responses and simulated
signing/token providers. No real credentials, GitHub writes, hosting changes or
pilot activation were performed. Older mock-only D3 and D1/D2 schemas and guards
are preserved. The active OpenCode installation is unchanged.

## Transport and scope

Only the enrolled public repository
`kcook98765-kodi-qualification/ai-kodi-publisher-d3-qualification` and its separate
Pages origin are accepted. Actual repository, Organization, human, App,
installation, bot, workflow and environment identities require observed enrollment.
Old synthetic identities and the production identity are rejected. This profile
admits only the pinned inert first-party MIT fixture 1.0.0/1.1.0 and campaign
candidate installer. It cannot authorize independently supplied production add-ons.

`publication_github_live.py` provides fixed-host TLS, explicit App JWT signing,
short-lived repository-selected installation tokens and typed operations. The
ceiling is Contents/PR write and Actions/Pages/Administration/Metadata read;
tokens are narrowed per operation. There is no ambient token, GitHub CLI, SSH,
proxy, arbitrary endpoint/method, force push, delete, clobber or settings-write
fallback. Credentials never follow redirects. Ambiguous writes are not retried.
Audit records omit credentials and remote-error bodies. Real sockets are denied
in the transport tests.

Semantic readback requires eight rulesets, immutable Releases, merge settings,
CODEOWNERS, Pages environment/branch selection and read-only Actions defaults.
Pinning an unsafe policy hash is insufficient. App bypass applies only to separate
writer/creation rules; review, CI and immutable-history rules have no bypass.
Main uses normal merge with the exact approved head, after the trusted Actions
workflow/job and public-site checks. Missing settings/evidence block execution.

## Local preparation and independent roles

P binds immutable source, runtime ZIP/checksum inventory, Nexus selection,
complete Pages changes, expected heads/trees, before/after ledgers, retained
history, limitations and destination. A stable campaign candidate installer uses
the existing builders/auditors; 1.1.0 retains 1.0.0 ZIP and installer bytes.
Original pending records are preserved alongside explicit lane projections.
Untrusted source and submitted scripts never execute in this path.

Existing task-bound build/qualify/review source tools gain
`action=publication_pilot`. Manager status captures a fresh complete read-only
baseline; manager build freezes P. The tester and reviewer inspect P, write their
existing permitted report, then call their own tool to seal its receipt. Reports
must name the task and contain `D3-PILOT-QUALIFIED <P-sha256>` only after independent
assessment. Trusted tool context supplies role/session/tool provenance. Tester,
reviewer and manager sessions must differ; manager qualify/review cannot
impersonate a pilot child. A second manager build seals R. This supplies technical
evidence, never owner authorization.

P/R/E pin trusted adapter source. Changed code, artifacts, review, destination or
scope invalidate the proposal. Fresh tasks follow code adoption; old bindings
are not migrated silently. Native acceptance, target interpreters and Piers remain
UNVERIFIED, including in the public owner summary. Disposable transport success
never clears production compatibility, rights or retained-input blockers.

## Fixed bridge and owner decisions

The new manager-only `kodi_publication` source helper accepts status/request/
execute/reconcile, task/binding digest and an exact E digest where required. It
uses a fixed one-shot Python bridge with a scrubbed environment. No caller path,
key, backend, destination, authorization record or arbitrary operation is accepted.
`pilot-profiles.json` is an inactive opt-in overlay. Existing active roles/tools
and their effective permissions are unchanged; tester/reviewer remain denied.

No `.opencode/publication-pilot.json` opt-in or publisher credentials are installed.
A future operator-controlled public configuration binds schema/profile, project
root, installation UUID/epoch, enrollment, explicit remote activation and a pinned
private configuration locator/digest. The private file must be outside the project,
regular, current-user-owned and mode 0600, without links or traversal aliases.
Its closed fields are schema, profile, installation_uuid, epoch, key_file and
staging_authorizations. Key loading is lazy, explicit and has no fallback.

A private staging authorization selects an exact task/binding/source/destination/
installation/epoch/expiry and only these metadata effects: create_blob, create_tree,
create_commit, create_ledger_branch, create_ledger_pr and update_request_pr. Before
each fresh real staging effect the helper re-reads the selected private grant.
Knowing its public hash does not issue authority. Removing/replacing the grant or
pin revokes staging. Historical read-only observation retains the frozen evidence;
expired grants cannot authorize fresh staging.

Under that separately authorized grant, request stages only reviewed ledger/config
objects, the exact `publication-ledger/<P>` branch and proposal PR. No tags, assets,
main or Pages change is authorized. GitHub Contents tokens are coarse; the helper
and independently revalidated scope enforce the narrower path boundary.

Actual PR identity/head/base seals E with P/R, nonce, destination, expiry (at most
one hour), policy and full operation scope. The public PR contains a safe summary;
package/private evidence stays available for local owner inspection. The owner
uses **Review changes → Approve** with exactly:

```
APPROVE D3-PILOT sha256:<E> nonce:<N> repo-id:<ID> expires:<UTC>
```

Verification requires User 56806582, a typed review ID, APPROVED state, exact
commit/body/base/head/policy, timely review and no later revocation. Generic PR
approval, chat approval and synthetic records are insufficient. Nonce and review
ID are consumed durably before effects. Owner proof is re-read in the coordinator
and immediately before publication requests. A concurrent revocation cannot be
made atomic with GitHub writes; later effects stop once it is observed. Dismissal,
changes requested, PR closure or exact `REVOKE <E> <N>` comment revoke the decision;
observed revocation is durably latched. Mock proof/enrollment/grants cannot
activate the actual HTTPS sender.

## Publication, recovery and activation

The typed sequence verifies state, creates absent tags/drafts, uploads only exact
assets, downloads/verifies digests, publishes immutable Releases, constructs the
complete Pages tree/commit, performs a non-force Pages update, verifies deployment
and public bytes/catalogs/history, then normally merges the exact ledger PR and
verifies its two parents/tree. Public verification failure leaves main unfinalized.
Historical assets cannot be replaced or removed.

The installation/epoch journal records intents before effects, verified receipts,
nonce/review consumption, revocations and generation-linked history. An incomplete
transaction blocks the next release. GET-only reconcile observes interrupted
objects and never guesses success. Lost final merge responses can be observed and
finalized locally only after exact verification. Other partial states require
identical P/R/artifacts, a fresh metadata grant, new E/nonce and new owner review
for the exact remaining scope. Fixed task-local recovery storage preserves all
older executions. Rollback uses forward correction and retains immutable history.

Whole-store rollback does not prove freshness. Disable execution, reconcile
independently and enroll a new epoch after journal loss/restoration. Existing host
administrators remain a trust boundary; this implementation claims no separate
OS isolation and changes no accounts.

Live execution still requires separately approved destination/App creation,
reviewed source/workflow/CODEOWNERS/empty ledgers/Pages seeds, protection readback,
actual enrollment, credential custody, task staging and opt-in tool activation.
`opencode/pilot-bootstrap.py` emits an inventory only: no apply mode or admin
client. Actual App signing, owner review, GitHub protection enforcement, Actions,
Pages, HTTPS and recovery remain unqualified until an authorized live pilot.
Production remains separately blocked on private retained inputs, rights/provider
decisions, native/interpreter/Piers evidence and current exact owner approvals.

Two explicit live/operational limitations remain. The configured Toolkit helper
interpreter currently lacks `cryptography`; real App signing therefore fails
closed. A separately reviewed publisher interpreter/dependency arrangement is
needed before live execution; the shared Toolkit environment was not changed.
If a newly prepared recovery E expires before it is ever claimed, the current
model helper cannot automatically renew that pending packet. A trusted operator
must prepare another preserved P/R recovery packet with fresh E/nonce/review and
the same reconciled journal prefix. Never rewrite/delete the expired packet or
reuse its approval. Ordinary claimed-interruption recovery is integrated, while
this repeated unclaimed-expiry case remains an explicit operator boundary.

Initial qualification Pages must use an explicitly empty-tree commit. The existing
empty-ledger retention guard rejects importing an unrelated nonempty site; the
first approved publication supplies its complete index and `.nojekyll`. The
inventory helper follows that guard instead of seeding an extra landing page.
Real API latency/quota and the source helper's 240-second deadline still need
measurement during the separately authorized live pilot; no mock timing result
qualifies those operational limits.

Deployment/public readiness is now a bounded GET-only phase. Its first deadline
is journaled and shared by the public gate and pre-merge recheck, capped at 120
seconds and E expiry, with waits of at most five seconds. The operator refreshes
the exact consumed owner decision and frozen evidence around probes. Only a
scoped missing/pending deployment, public 404, or safe-MIME mutable catalog/index/
checksum matching its exact frozen before-hash can wait. Wrong ZIPs, versioned
sidecars, unknown bytes, unsafe identities and failed deployments remain hard
failures. No late observation supplies PASS after the deadline. A timeout keeps
partial state blocked for explicit recovery; waiting never renews approval or
retries a remote write. Mocked readiness timing still requires live qualification.

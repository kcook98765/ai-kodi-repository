# D3 minimal GitHub pilot — existing Claw installation

Status: **PREPARATION ONLY; implementation and remote writes NOT authorized.**
Owner direction: defer Linux/account/sudo/Docker/runner changes; retain current
OpenCode/Codex/Web. This plan supersedes the earlier host-setup prerequisites for
this disposable pilot only. It does not activate a publisher or change existing
[D3 implementation](OPENCODE-LIFECYCLE-D3-LOCAL-IMPLEMENTATION.md).

Recommendation: one public qualification repository, one repository-selected
GitHub App, a one-shot local helper, and **one exact approved PR review per
successful release**. No new server, service, Linux identity or agent framework.

## 1. Essential prerequisites and deferred work

| Essential for the disposable pilot | Deferred / outside this pilot |
| --- | --- |
| Real HTTPS/token/proof interfaces; enrolled numeric destination/actor IDs; actual source commits and protection baseline | Non-admin runner, separate publisher UID, sudo/Docker changes, Web migration and stronger OS credential isolation |
| Frozen P/R/E; independent tester/reviewer records; exact package/site/ledger hashes; genuine attributable owner decision | Production credential installation, production promotion and canonical publication activation |
| Single transaction lock, durable nonce/review consumption, revocation latch, per-effect journal and recover-tested evidence archive on existing private storage | New backup infrastructure or persistent monitoring/publisher service |
| Different HTTPS origin, create-only assets, retention, normal protected merge and public verification | Piers/static tooling, target interpreters, native Kodi acceptance and missing real production inputs: remain blockers for affected production claims, not this synthetic transport test |

The existing administrative account is trusted for this bounded pilot. Keep the
future test key outside Git and model-visible reports; give it only to the trusted
helper. Same-UID/admin processes can technically access it: this is operational
separation, **not OS credential isolation**. No further runner design is required.
Do not execute untrusted add-on code with the publisher credential present.

The 322-test implementation receipt is retained, not rerun for this plan. All 97
previous source files still match their reviewed hashes. Evidence is in ignored
`reports/lifecycle-d3-pilot-plan/`.

## 2. Destination and one-time GitHub setup

GET checks at **2026-10-24 01:18:53 UTC** returned 404 for the preferred account,
organization and repository. No matching public resource was found; this is **not
a reservation or guaranteed availability**. GitHub must confirm the name during
owner creation. Human owner `kcook98765` is User ID `56806582`; future organization,
repository, App, installation and bot IDs are unassigned and must be read back.

| Option | Setup / different-origin result |
| --- | --- |
| **Preferred:** organization `kcook98765-kodi-qualification`, public repository `ai-kodi-publisher-d3-qualification` | Existing human account owns the organization. No additional human login, DNS or custom certificate. Origin: `https://kcook98765-kodi-qualification.github.io`; project path `/ai-kodi-publisher-d3-qualification/` |
| Alternative: public `kcook98765/ai-kodi-publisher-d3-qualification` with a dedicated owner-controlled HTTPS subdomain | Repository currently returns 404. Fewer GitHub entities, but requires proven domain/DNS control, CNAME/TXT/TLS setup and an explicitly enrolled new origin. No such owned hostname is established. Default `kcook98765.github.io/<new-path>` is rejected by the existing guard |

The organization is simpler unless an appropriate DNS hostname is already under
owner control. Public organization repositories support Pages on GitHub Free;
GitHub documents both project origins and individual custom domains.
[Pages](https://docs.github.com/en/pages/getting-started-with-github-pages/what-is-github-pages),
[custom domains](https://docs.github.com/en/pages/configuring-a-custom-domain-for-your-github-pages-site/about-custom-domains-and-github-pages),
[organization creation](https://docs.github.com/en/organizations/collaborating-with-groups-in-organizations/creating-a-new-organization-from-scratch).

Owner setup is one organization form and one App registration/installation;
the remaining repository bootstrap can use a bounded, reviewed script under the
owner's existing administration session. Setup credentials never become routine
publisher credentials. One approved bootstrap seeds `main`, `gh-pages`, `d3-fixture-source`, trusted
validation code/workflow, `CODEOWNERS`, an **empty published ledger**, initial
qualification config and landing page. It does not publish a package. Then:

- Main: owner/code-owner PR approval, stale dismissal, last-push review, strict
  `qualification-validation` check from the actual enrolled CI App; no force/delete
  or review bypass. Seed a successful real check before requiring it.
- Make the publisher App the only normal main updater in a **separate writer
  ruleset**; retain independent review/check/integrity rules with no bypass. This
  prevents a preapproved ledger PR being merged manually before verification.
- Keep the reviewed Pages writer/integrity and tag-creation/immutable-tag rules;
  restrict App-created proposal branches to the enrolled namespace. The App's
  writer exception applies only to writer/creation rules, never review/integrity.
- Allow ordinary merge commits; disable squash, rebase, auto-merge, merge queues
  and automatic proposal-branch deletion. No competing main writer during a pilot.
- Pages: deploy from `gh-pages:/`, HTTPS, complete static tree and `.nojekyll`;
  `github-pages` permits only `gh-pages`. In the **new profile only**, no second
  human deployment review: the initial exact PR decision covers Pages too.
- Enable immutable **future** Releases before the first package release. Default
  Actions token remains read-only; no publisher key in CI, privileged runner or
  separate approval-dispatch workflow.

GitHub represents writer allowlists with ruleset bypass actors; their use is
limited to those separate rules. Protection/visibility failures stop setup.
[Rulesets](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/available-rules-for-rulesets),
[release immutability](https://docs.github.com/en/code-security/how-tos/secure-your-supply-chain/establish-provenance-and-integrity/prevent-release-changes),
[branch Pages](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site).

## 3. Exact remaining code changes

| File(s) | Minimum implementation |
| --- | --- |
| New `scripts/publication_github_live.py`; existing `scripts/publication_github.py` | Add fixed-host TLS transport/App JWT/token provider; reuse/extract pure request validators. Keep concrete mock sender/credentials unchanged. Add only scoped proposal-PR metadata and normal merge operations; no arbitrary URLs, shell, delete/clobber, force or settings writes |
| `scripts/publication_d3_contract.py` | Add separate versioned `d3-pr-pilot-v1` enrollment/P/R/E schema with actual IDs, observed policy, staged PR identity/head, source commits, independent task/session/tool evidence and exact full-site/ledger scope. Preserve existing mock-only schemas; do not flip their flags or reuse old approvals |
| `scripts/publication_owner.py` | Add genuine PR-review proof and matching real Pages deploy observation for the new profile. Verify integer owner/review IDs, exact review body/commit/time, fresh scope, revocation and expiry; synthetic proof types cannot authorize live writes |
| `scripts/publication_d3.py` | Reuse durable journal/recovery in an explicitly versioned live-pilot context: metadata request grant, approval consumption, existing publication stages, verified-public gate, narrow pinned merge, exact finalization observation. Do not relabel a mock journal as live |
| New `scripts/publication_cli.py` | Fixed one-shot `request/status/execute/reconcile` JSON interface bound to task/E/destination; helper resolves sealed paths. No caller-supplied command, key path, backend or arbitrary destination |
| New `scripts/opencode/pilot-bootstrap.py` | Default dry-run inventory of exact test-repository seed/settings; separately authorized owner-admin application only. Publisher has no settings-write fallback |
| `scripts/lifecycle.py`, `scripts/lifecycle_publication.py`, `scripts/opencode/kodi.ts`; new `scripts/opencode/pilot-profiles.json` | Wire existing manager/tester/reviewer preparation and evidence. Optional pilot-project manager-only publication tool calls the helper. Tester/reviewer stay nonpublishing; no approval-issuing tool, shell, general GitHub writes or credential reads. Fresh task/install pins are mandatory |
| Tests plus `docs/PUBLICATION-D3-LOCAL.md` / `docs/AGENT-INTEGRATION.md` | Add real-response/mock-server, PR proof, staging, merge, recovery and role canaries; document the opt-in pilot. Leave existing fixtures, strict D3 mode, canonical profile and running installation unchanged |

The current code explicitly rejects live senders/credentials and stamps mock
receipts. Connecting it requires these reviewed changes, not a configuration
toggle. No additional orchestration framework is needed. The pilot project can
use the existing OpenCode binary/Web; no global environment or service migration.

## 4. Minimum credential and operation scope

One private GitHub App owned by the qualification organization, installed on
**only the qualification repository**, with webhooks and user OAuth flows disabled:

For the personal-repository alternative, use a private App owned by `kcook98765`
instead and explicitly enroll User ownership/new origin; do not reuse the
organization enrollment. Private Apps install only on their owning account.
[App installation](https://docs.github.com/en/apps/using-github-apps/installing-your-own-github-app).

| Permission ceiling | Use |
| --- | --- |
| Contents write | Exact staging Git objects/branch, tag/Release/assets, Pages fast-forward, normal approved PR merge |
| Pull requests write | Create/update only the frozen request PR; read owner decisions/revocations |
| Actions read; Pages read | Actual deployment/job/build observations |
| Administration read; Metadata read | Verify destination and effective protections |
| No Actions/Workflows/Deployments/Issues/Administration write | No approval dispatch, settings changes, review fabrication or deployment bypass |

Mint explicit `repository_ids=[actual-pilot-id]` and per-operation permission
subsets. Tokens expire within one hour and new effects stop at earlier E/evidence
expiry. Observer tokens are read-only. Keep the App key in an owner-provided private
location outside the workspace; tokens stay in helper memory, out of arguments,
logs, model output and source/test environments. No ambient admin `gh`, PAT or SSH
fallback. The App is needed to author the PR as a bot so the human can approve it;
an owner-authored PAT PR cannot supply that independent required review.
[Installation tokens](https://docs.github.com/en/rest/apps/apps#create-an-installation-access-token-for-an-app),
[PR approval](https://docs.github.com/en/pull-requests/how-tos/review-pull-requests/approving-a-pull-request-with-required-reviews).

Allowed effects: scoped Git blob/tree/commit creation; one `publication-ledger/<P>`
branch; request PR creation/scope update; new tag/draft/assets; publish verified
immutable Release; exact non-force Pages update; ordinary `PUT /pulls/<id>/merge`
with `sha=<approved-ledger-head>` and `merge_method=merge`. All observations are
bounded GET/HEAD at enrolled GitHub/Pages hosts; asset-storage redirects never
receive authorization headers. No remote write is performed during this plan.

## 5. One owner approval

This is an **explicitly new disposable-only approval profile**, needing owner
authorization. It consolidates interaction, retaining exact-artifact authorization;
the existing workflow/Pages/ledger three-proof mode remains unchanged.

1. Manager freezes P; tester and reviewer independently assess exact bytes and
   freeze attributable R. The packet shows name/ID/version, immutable source,
   lanes/unknowns, rights, evidence/review hashes, every ZIP/checksum, tag/assets,
   full Pages delta, ledger/retention, destination and expected heads.
2. Under a **separate bounded preparation grant**, the App stages only the proposed
   ledger commit/branch/PR. No ZIP upload, tag, Release, main or Pages change is
   authorized by this grant. Contents permission is coarse; this restriction is
   enforced by the trusted helper, not GitHub token path scoping.
3. Seal E with actual PR identity, exact head/base, P/R, destination, nonce and
   expiry (at most one hour). Populate its deterministic public-safe summary in
   the PR. Bind a canonical scope projection rather than a circular E/body hash.
   Owner gets package bytes/private evidence through existing local access;
   public PR contains no private inputs or preapproval runtime ZIPs.
4. Owner uses **Review changes → Approve** once, with the supplied exact text:

   `APPROVE D3-PILOT sha256:<E> nonce:<N> repo-id:<ID> expires:<UTC>`

   The verifier checks User `56806582`, integer review ID, APPROVED state, exact
   `commit_id`, `submitted_at` within E lifetime, latest nondismissed decision,
   current PR scope/base/head and policy. A plain comment/chat message is not proof.
5. Manager requests one-shot execution; consume nonce **and review ID** durably
   before publication. Recheck proof/revocation/expiry before each effect. Owner
   can dismiss/request changes/close the unmerged PR or post `REVOKE <E> <N>` there;
   observed revocation is latched even after comment edit/deletion.

The same approval covers the exact Pages deployment and final ledger commit.
Owner does not manually merge; publisher merges only after public verification
and required checks. A stopped OpenCode session can be resumed with the proposal
ID; no webhook service or unattended publisher is needed. Drift/expiry/recovery
requires a fresh E/nonce and genuine new review, not editing an old approval.
[Review evidence API](https://docs.github.com/en/rest/pulls/reviews).

## 6. Pilot execution and qualification

After separate implementation/setup/credential approval:

1. Bootstrap/read back actual identities, protections, CI and Pages; enroll only
   this target. Create and independently recovery-test a private evidence archive
   using existing storage. Missing journal/unknown remote artifacts block startup.
2. Bind inert MIT `script.ai.kodi.d3.fixture` 1.0.0 to actual F10 source commit;
   build twice using existing deterministic builder/auditor. Use stable
   `repository.ai.kodi.candidate.<campaign-id>` and isolated complete candidate
   feed; published ledger starts empty. Nexus catalog transport only; native,
   target-interpreter and Piers remain UNVERIFIED.
3. Obtain independent tester/reviewer evidence, stage request, freeze E and obtain
   the one exact PR approval above.
4. Journal each intent; create tag at the frozen distribution commit, draft and
   exact individual ZIP/sidecar/SHA256SUMS assets. Download/hash actual bytes before
   publishing; require immutable Release readback and unchanged historical assets.
5. Promote the full reviewed Pages tree at its exact parent, without force.
   Verify the real deploy job/commit, HTTPS/MIME/actual bytes, catalogs, sidecars,
   bootstrap and contamination canaries. No PASS from branch push/build alone.
6. Recheck owner authority, checks and base/head; normally merge the already
   reviewed PR. Verify actual merge tree and both exact parents before RECORDED.
   Otherwise retain PUBLIC_BUT_UNRECONCILED and block the next release.
7. Replay E/review/nonce: zero new effects. Repeat with 1.1.0/F11 and a new
   proposal/review, proving 1.0.0 packages and installer bytes remain immutable.
8. Exercise approved interruption cases, freeze evidence, independently review
   results and revoke pilot App access after in-flight reconciliation.

The merge API pins the PR head, **not an expected base** (inference from its
documented parameters). Use the sole-writer rule/journal, immediate base preflight
and exact post-merge parents/tree. An unexpected accepted merge is an incomplete
incident requiring forward correction, not an atomic-CAS success claim.
[Merge API](https://docs.github.com/en/rest/pulls/pulls#merge-a-pull-request).

Qualification tests: preserve all existing 322 regressions; add genuine-versus-mock
proof rejection, editable/dismissed/stale reviews, review-ID/nonce replay, expired
or revoked authority, metadata-grant escape, early ledger merge denial, malformed
credentials, production/same-origin denial, changed heads/policy, partial uploads,
lost responses at every effect, failed/mixed Pages bytes, normal-merge races,
ledger failure/recovery and historical retention. Recheck actual role grants.
Run independent security/test review before enabling any sender.

Rollback/recovery: stop new effects, reconcile GET/HEAD only, retain every published
artifact, freeze fresh recovery E for the exact remaining suffix and obtain a new
review. Correct published mistakes through separately approved forward changes;
no force, deletion, mutable replacement, automatic rebase or installed-Kodi
downgrade claim. Retain test artifacts/private evidence at least 90 days after
final review, then until separate retirement approval; prefer archival. Restored
journals start disabled with a new epoch and remote reconciliation. Already
accepted asynchronous Pages jobs may finish after expiry/revocation; report that
truthfully and do not authorize subsequent writes from expired evidence.

## 7. Decisions requiring separate authorization

1. Implement/test the opt-in single-PR profile, including bounded metadata staging
   before publication approval, automatic pilot Pages deployment and the narrow
   post-verification merge. If declined, retain the existing three-review flow.
2. Create the preferred public organization/repository, or supply an already owned
   custom hostname for the personal-repository alternative; approve exact bootstrap
   branches, code, settings and sole-writer exception scope.
3. Create/install the test-only App, provide its private key to the helper under
   the existing admin trust arrangement, approve private evidence/archive location
   and retention policy. No production installation or credential.
4. After reviewed implementation/setup, activate **only the pilot project** manager
   interface on the existing installation and authorize the bounded live test
   cases. Each 1.0.0, 1.1.0 and recovery publication needs its own exact approval.

These are future decisions, not approvals granted by this preparation request.
No host security/account change, resource creation, credential installation,
GitHub write, canonical activation or Kodi Lab operation was performed.

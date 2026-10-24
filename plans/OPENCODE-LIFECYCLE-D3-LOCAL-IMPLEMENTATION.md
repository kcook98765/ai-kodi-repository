# D3 local implementation and infrastructure decisions

Scope: local implementation and mock qualification only. No live sender,
credential, OS account, permission, GitHub resource/settings, canonical agent,
running OpenCode installation or Kodi Lab change is authorized or made.
The reviewed [D3 plan](OPENCODE-LIFECYCLE-D3-QUALIFICATION-PLAN.md) and
[desired state](d3/PUBLISHER-QUALIFICATION-DESIRED-STATE.json) remain unchanged.
This report distinguishes implemented local checks from proposed infrastructure.

## Implemented local components

Four new modules extend the existing package/audit/publication architecture:

| Component | Implemented behavior |
| --- | --- |
| `publication_d3_contract.py` | Versioned qualification P/R/E, canonical digests, exact first-party immutable source/runtime bytes, stable campaign installer, sequential 1.0.0 then 1.1.0, full main/Pages trees, separate candidate commitments/published ledger and truthful production blockers |
| `publication_github.py` | Real REST shapes through a concrete finite mock only; closed destination/operation/credential caps, policy/head observations, create-only tag/draft/per-asset operations, verified downloads, individual Git objects/non-force Pages update, ledger branch/PR and read-only recovery lookup |
| `publication_owner.py` | Typed human/org/App/bot/run/environment/workflow/artifact checks, nonce/expiry/destination/digest scope, revocation, qualification/review hashes and separate successful owner-reviewed Pages deployment; no genuine human authentication or network authority from mocks |
| `publication_d3.py` | One-shot coordinator, durable nonce/owner-run consumption, append-only generation journal, independent revocation latch, before-effect intent/after-effect receipt, redacted audit, incomplete-publication blocking, exact read-only reconciliation and fresh-approval recovery |

Full semantic derivation runs at entry; every effect rehashes all frozen bundle
bytes and trusted modules, checks current owner authority, policy and branch heads,
then journals intent. Each asset/blob/tree/commit/ref/PR effect has its own receipt.
Missing Pages-owner review returns `AWAITING_PAGES_OWNER_REVIEW`; a submitted ledger
PR returns `PUBLIC_BUT_UNRECONCILED`. Only read-only verification of the exact
normal owner-reviewed merge, tree/parents and public bytes records finalization.

Nonce and owner workflow-run reuse are both rejected. A lost response is reconciled
by GET/HEAD, including Git objects and the exact ledger PR; explicit 404 alone
proves absence. Unknown/conflicting state blocks progress. Fresh E/nonce/run/owner
approval resumes only the observed missing suffix with unchanged P/R. Retained
timely Pages review is a fact about the same P/R, origin and deployed commit;
it never authorizes later writes after expiry. Those need current fresh approval.

No real HTTPS sender, App JWT/token loader, workflow dispatch service, root launcher
or remote authorization is enabled. Interfaces refuse live credentials and
non-mock senders. A general approval flag cannot enable production. Existing
D1/D2 modes, OpenCode role schemas/grants and canonical workflows are unchanged.

## Non-admin OpenCode runner decision

A dedicated non-admin account is necessary for the requested isolation from
automated repository work on this host. The existing administrative account has passwordless
sudo and Docker-socket access. A separate publisher UID does not stop a process
with those administrative powers from reading its key. Preserve the existing
administrative account and Codex installation as trusted maintenance tools;
do not describe them as isolated untrusted workers while they retain root access.
For a strict pilot boundary, administrative AI/source sessions must be stopped
or operated without pilot keys present. Human root administration remains trusted.

Read-only investigation found the existing OpenCode Web installation running
under the administrative account and using private configuration. Machine-specific
service, account and checkout details remain in private audit evidence. A new UID
cannot reuse private Toolkit/shared paths without changing existing permissions.
Export approved pinned code instead of widening existing checkout permissions.
The existing service was left running and unchanged.

This section records the earlier unactivated host-isolation proposal. The owner
subsequently deferred that migration; the minimal pilot plan governs current work.
`<agent-private-home>` represents the proposed private home inside agent state;
host-specific inventory remains private.

Proposed account and directories, **not created**:

| Item | Exact proposed boundary |
| --- | --- |
| `kodi-repo-agent-d3` | Private primary group; no sudo, Docker, adm or publisher membership; locked password; no administrative SSH identity; numeric UID/GID assigned and pinned only after approval |
| `<agent-private-home>/` | Agent-owned 0700 home; independent XDG config/cache/data/state; model credential provisioned separately with minimum provider authority |
| `/opt/ai-kodi-agent-d3/versions/<hash>/` | Root-owned reviewed OpenCode binary, Toolkit code, Python environments, plugin, skills and adapter templates; no writable imports or dependency auto-updates |
| `/var/lib/ai-kodi-agent-d3/workspaces/` | Agent-owned explicit per-task source/preparation/report storage; closed task bindings and fixture/candidate/production separation retained |
| Publisher paths | Root-installed trusted code/policy and publisher-only state/runtime/key custody exactly as in the reviewed D3 plan; agent cannot traverse them |
| Network | Outbound model provider plus bounded public GitHub discovery; no Docker socket, host administration or implicit native Kodi authority |

Ordinary source intake, deterministic packaging, offline validation, independent
role review, GitHub GETs and Web sessions require neither sudo nor Docker.
Read-only exported Toolkit code and separately installed pinned virtualenvs/cache
are sufficient for these paths. Python environments must be rebuilt at their
final paths, not copied with stale absolute shebangs. Root maintains versioned
code and dependencies; the agent writes only its task workspaces and reports.
Operator-controlled task enrollment must have a fixed request boundary before
an agent can create arbitrary approved-source tasks; do not restore shell access
to work around missing enrollment or adapter bindings.

Use bounded CLI/TUI first, with no new persistent service. Export reviewed
OpenCode/plugin 1.19.3 and the existing Toolkit pin
`552b0b949220f2d545ab42a7f27d1826a535c686`; separately qualify rebuilt environments
and caches at their new paths. Exact proposed per-user paths:

```text
HOME=<agent-private-home>
XDG_CONFIG_HOME=<agent-private-home>/.config
XDG_DATA_HOME=<agent-private-home>/.local/share
XDG_STATE_HOME=<agent-private-home>/.local/state
XDG_CACHE_HOME=/var/cache/ai-kodi-agent-d3
```

Launch OpenCode only in the trusted exported distribution project. Treat incoming
add-on instructions/plugins/configuration as data; do not launch OpenCode inside
an untrusted source checkout or import its environment/configuration. Retain the
four roles and their rules; only reviewed installation/task/report paths change
during a separately approved setup.

Proposed Web command, **not run**:

```text
/opt/ai-kodi-agent-d3/versions/<hash>/bin/opencode web --hostname 127.0.0.1 --port 4097
```

Run it as the new UID with its own home/config/runtime and separate Web password.
Keep mDNS disabled and CORS empty. A human can use an SSH tunnel to loopback or a
separately approved authenticated reverse proxy. Do not reuse the admin service's
environment file, auth database, sessions or browser credential. Port 4097 is a
proposal and must be checked for availability at installation. The existing
4096 service can coexist for trusted administration, but is outside the untrusted
runner isolation claim. OpenCode supports loopback binding and password-based
HTTP authentication for both Web and serve; this does not provide Linux identity
isolation by itself. [OpenCode server](https://docs.opencode.ai/docs/server/),
[Web documentation](https://docs.opencode.ai/docs/web/).

The initial runner needs no sudo rule. At separately approved publisher activation,
only the root-owned no-argument launcher may be added. Its exact sudoers rule is
in the reviewed plan. There is no general sudo/systemd-run/shell permission.
The reviewed publisher `NoNewPrivileges=yes` sandbox applies to the publisher
job; setting it on a runner process that must invoke sudo would prevent elevation.
Keep the initial runner unable to invoke a publisher. Later fixed-launcher
activation must explicitly review an invocation without inherited
`NoNewPrivileges`, granting only the exact no-argument root wrapper from the D3
plan. The publisher sandbox retains `NoNewPrivileges=yes`. No additional
privileged daemon or general sudo/systemd-run permission is proposed.

Required adjustments before a runner pilot: rebind the root-owned Python and
TypeScript adapter installation paths; update exported skills/plugin/cache/tool
paths; rebuild interpreter environments; provision independent model/Web auth;
verify parent path modes, role report locations and exact effective permissions;
rerun actual role/tool canaries. Existing canonical fixture adapters deliberately
pin the canonical checkout and cannot simply be pointed at the private original.
No profile or running installation is changed by this report.

The development-root OpenCode profile includes read-only Lab MCP at
`127.0.0.1:18100/mcp`; repository-specific profiles disable it. A new local UID can
reach a loopback listener but does not inherit a Lab identity or target grant.
Fresh effective Lab ACLs were **not verified**: no client secret was read and no
Lab operation was performed. Keep MCP disabled for the D3 runner. Any later native
test needs a separately approved client/target grant and existing approved source
execution isolation. Do not give Docker access or copy the administrative MCP
token. Detailed metadata is retained in the ignored runner investigation report.

## Qualification destination decision

GET-only discovery at `2026-10-24T00:30:03Z` returned 29 accessible repositories,
all owned by User `kcook98765` (56806582), and no organization memberships visible
to that CLI identity. Three repositories currently host Pages:

| Repository | Existing HTTPS origin |
| --- | --- |
| `kcook98765/ai-kodi-repository` | `https://kcook98765.github.io` |
| `kcook98765/kcook98765.github.io` | `https://kcook98765.github.io` |
| `kcook98765/repository.kcook98765` | `https://kcook98765.github.io` |

None is suitable for this qualification feed under the existing different-origin
guard. A different repository path is insufficient. Do not repurpose these sites
or alter their CNAME/hosting. This inventory does not prove the absence of another
account or privately controlled domain; it establishes that no suitable existing
destination was found through the current authorized identity. GitHub documents
the owner-derived default Pages origin. [GitHub Pages site types](https://docs.github.com/en/pages/getting-started-with-github-pages/what-is-github-pages).

Recommend the original smallest arrangement: one owner-controlled organization
`kcook98765-kodi-qualification` and one public repository
`ai-kodi-publisher-d3-qualification`, hosting only synthetic public test material
at `https://kcook98765-kodi-qualification.github.io/ai-kodi-publisher-d3-qualification/`.
The human `kcook98765` must create/control it as organization administrator.
The organization/repository numeric IDs are unassigned; no ownership or name
reservation is asserted. The human approver ID remains separate from the future
organization owner ID. An already controlled separate HTTPS hostname is an
alternative only with explicit ownership, DNS/TLS and hosting approval.

Retain branch-mode Pages from `gh-pages:/`, HTTPS, a distinct candidate installer
identity and an inert MIT fixture `script.ai.kodi.d3.fixture` 1.0.0 then 1.1.0.
The campaign feed identity is stable across these updates; source task/commit,
proposal and nonce identities remain separate. The published test ledger starts
empty and must never be relabeled from the populated candidate commitment ledger.
Keep every published version; revoke pilot credentials after reconciliation,
retain public artifacts and private evidence at least 90 days after final review
and thereafter until separate retirement approval. No automatic deletion.

## Credentials and GitHub policy needed later

No credential is installed or loaded. A future test-only GitHub App installation
must select only the new repository by numeric ID. Do not install it on production
or use the ambient administrative CLI/PAT. The proposed App's permission ceiling:

| Repository permission | Ceiling / operation use |
| --- | --- |
| Metadata | Read; exact repository and owner identity |
| Actions | Write ceiling; approval request dispatch only; observer tokens read |
| Contents | Write ceiling; create-only test tag/Release/assets/Git objects and exact Pages fast-forward; observer tokens read |
| Pull requests | Write ceiling; fixed ledger finalization PR only; observer tokens read for revocation issue comments/PR evidence |
| Administration | Read only; effective protection/environments/rules visibility |
| Pages | Read only; deployed configuration/build observations |
| Workflows, Deployments, Issues, Administration writes | Forbidden |

Mint explicit repository-ID and per-operation permission subsets, not the App's
whole default scope. Tokens expire after one hour; bind execution to the earlier
proposal/evidence/token expiry. The root-held pilot App key is delivered only to
the approved one-shot publisher sandbox. [Installation token scope](https://docs.github.com/en/rest/apps/apps#create-an-installation-access-token-for-an-app).
Read-only control-issue comments can use Pull requests read, already within the
reviewed App ceiling; no Issues write is necessary. [Issue comment permissions](https://docs.github.com/en/rest/issues/comments#list-issue-comments).

Before a live pilot, create/read back the seven reviewed split rulesets; protect
main through owner review/checks and immutable history; allow only the App's Pages
updates through the writer-only rule while never bypassing integrity rules;
forbid all tag updates/deletion; permit creation only in test namespaces; enable
immutability for new Releases. Seed checks/CODEOWNERS before enforcing them.
Install the protected approval-only workflow and owner-review environments, with
prevent-self-review and admin bypass disabled. The App cannot approve either
environment, change workflow policy or merge around main protections. Full
settings remain in the unchanged desired-state document. The production repository
and its historical mutable Release remain untouched.

The implemented finalization observer accepts the exact normal two-parent merge.
For the new pilot repository, propose `allow_merge_commit=true`,
`allow_squash_merge=false` and `allow_rebase_merge=false` during separately
approved bootstrap. Squash/rebase results are not silently adopted. These settings
have not been changed on any repository.

## Owner experience and live disposable pilot

Locally the verifier evaluates mocked observations only. A future live owner sees
one complete frozen summary: name/ID/version; source IDs/commit; lanes and truthful
test limitations; exact ZIP/sidecars and SHA-256; independent qualification/review;
rights disposition; Release tag/commit/assets/notes; full Pages before/after
inventory and heads; main/ledger changes and retention; destination numeric IDs;
E digest, nonce and expiry. The owner reviews the pinned workflow's scope artifact
and enters the exact digest/nonce/repository/run comment from the reviewed plan.
A general chat approval or a synthetic test identity is insufficient.

After separately approved setup and real transport/authentication qualification:

1. Enroll actual IDs, fixed policy/workflow/code hashes and clean remote baselines;
   recover-test private evidence storage. Prove runner/publisher credential denial.
2. Build fixture 1.0.0 twice, qualify/audit independently, freeze P/R/E and display
   unresolved conditions. Obtain the exact owner decision in the protected workflow.
3. Invoke the fixed one-shot operator. Journal consumption/intent before each
   object; create tag/draft/assets, download and verify actual bytes, then publish
   and verify immutable status. No blind retry after a lost response.
4. Prepare the complete Pages tree with the exact parent; normal non-force update,
   matching Pages owner review, deployment/HTTPS verification of every expected
   current/historical artifact, catalogs, sidecars and bootstrap.
5. Submit the exact ledger/config change through the protected PR path. Until
   owner-reviewed finalization is verified, block another release as
   `PUBLIC_BUT_UNRECONCILED`.
6. Test replay and the approved negative/interruption cases. Reconcile by GET only;
   resume only with fresh E/nonce/owner approval against the observed partial state.
   Then independently freeze/approve fixture 1.1.0, preserving all 1.0.0 artifacts.
7. Archive evidence, revoke the pilot App/keys after in-flight reconciliation and
   stop for review. Success does not enable production enrollment or unattended work.

GitHub ref updates expose a new SHA and force flag, not an old-SHA transaction
precondition. Exact sole-parent commit construction, immediate head observations,
non-force update and protected single-writer rules are needed together. No claim
of atomic cross-Release/Pages/ledger publication is made. [Reference API](https://docs.github.com/en/rest/git/refs#update-a-reference).
Approval expiration blocks new operator writes; an already accepted Pages job
can finish later. Strict server-side deployment expiry is a separate workflow/
hosting decision, not a guarantee supplied by legacy branch-mode Pages.

## Remaining blockers and separate approvals

| Requirement | Disposable transport pilot | Real production |
| --- | --- | --- |
| Non-admin runner and publisher OS isolation, safe backup/recovery, real transport and owner-proof integration | Blocking until approved, deployed and tested | Blocking |
| Distinct origin, assigned organization/repository/App/environment IDs and settings | Blocking until created/enrolled/verified under separate authority | Production-specific enrollment/settings also required |
| Genuine current owner approval for each exact E | Blocking for live writes; mock observations are insufficient | Blocking |
| Missing retained private production ZIP/review/evidence inputs | Does not block an independent synthetic fixture | Blocking; original bytes/facts cannot be reconstructed by assertion |
| Piers static tooling | Outside Nexus transport-only pilot; remains UNVERIFIED | Blocks any unsupported Piers claim |
| Target interpreter/native acceptance | Outside transport-only pilot; remain UNVERIFIED | Required by release contract unless an existing exact, valid scoped exception applies |
| Expired/incomplete evidence or exception | Blocks any affected pilot proposal | Blocks affected production proposal; no automatic extension |

Decisions requiring separate approval: the new runner boundary and host installation;
organization/repository ownership and public synthetic hosting; pilot-only App and
key custody; exact rules/workflow/environments; private recover-tested evidence
backup location; live authenticated sender/observer qualification; the retention
policy; and each initial/update/recovery publication proposal. Production setup,
canonical activation, Kodi Lab/native work and production publication remain
separate later decisions.

## Local verification and exact files

The settled full suite passed **322 tests, zero failures/errors/skips**, in
433.119 seconds, with source hashes unchanged during execution. This includes
all 256 earlier tests plus 66 new methods: coordinator/journal 19, transport 29,
contract 7 and owner verification 11. The four earlier optional schema checks ran
successfully with the existing system Python validator. No dependency was installed.

Independent security review passed 60 focused tests and fixed two reproduced
defects before the final gate: a skipped Pages deployment being mistaken for a
successful deployment, and a JSON float actor ID comparing equal to the required
integer owner ID during ledger review. Both have serialized-response regressions.
No unresolved local-scope security blocker remains.

Independent tester verification includes six permission tests, 21 actual engine
canaries and developer parity/publication denial. No checked operation, inference,
service activation or publication ran. Three additional serialized-wire recovery
flows passed for lost tag/draft/publish responses: each reconciled read-only,
rejected old authority, used fresh approval and reached recorded finalization
without repeating the lost effect. The final independent suite passed **66/66**
with zero skips/failures in 254.964 seconds and all 13 captured runtime/test pins
unchanged. Its initial 240-second harness timeout is retained as incomplete,
not an implementation failure or qualified result. The completed bounded rerun
and review are in `reports/lifecycle-d3-local/TESTER-REVIEW.md`.

The 23 planned groups are mapped in the private qualification coverage receipt.
Only applicable local/mock portions are qualified. Actual OS/key denial,
GitHub rule/environment enforcement, external backup restore, live authentication,
Pages hosting and all native/interpreter/Piers claims remain unperformed or
unverified. Mock responses do not prove those controls exist remotely.

Exactly **11 new source/document files** were added in this phase. No existing
source file changed; all 86 prior source files, 51 canonical tracked files and
six enrolled configuration/role/tool files match the saved baseline. Canonical
main remains clean at `f2d8f3330d76a982d6f66601d8ec6ae2bc9c9c83`; its pending
documentation commit was not pushed. Seven re-read GitHub control/metadata
projections match the preceding audit. Proposed users/install paths are absent.

| Exact new file | Purpose |
| --- | --- |
| `scripts/publication_d3_contract.py` | Frozen qualification contract and owner summary |
| `scripts/publication_github.py` | Narrow REST interfaces and concrete mock sender |
| `scripts/publication_owner.py` | Owner/Pages proof verification interfaces |
| `scripts/publication_d3.py` | Durable one-shot coordinator and recovery |
| `tests/d3_github_model.py` | Test-only stateful API model; no sockets |
| `tests/test_publication_d3.py` | Serialized coordinator/journal/fault/update tests |
| `tests/test_publication_d3_contract.py` | Source/identity/retention/freeze/expiry tests |
| `tests/test_publication_github.py` | Transport scope, request/response and failure tests |
| `tests/test_publication_owner.py` | Owner/run/artifact/environment/revocation tests |
| `docs/PUBLICATION-D3-LOCAL.md` | Interface boundaries and activation prerequisites |
| `plans/OPENCODE-LIFECYCLE-D3-LOCAL-IMPLEMENTATION.md` | This report and infrastructure decision review |

Ignored private evidence is under `reports/lifecycle-d3-local/`: full and independent
test receipts, security review, role canaries, infrastructure metadata, preservation
checks and final file hashes. `owner-example/OWNER-PREVIEW.json` is a retained local
mock summary with its frozen bundle beneath it. It is explicitly not a dispatched
request or live approval; every authority flag is false. Before live authorization,
genuine reviewer task/session/tool provenance and real authenticated workflow/run
correlation must be retained and qualified, in addition to the hash bindings
modeled here.

# D3 publisher isolation and qualification preparation

Status: **PREPARATION COMPLETE FOR REVIEW; execution NOT authorized**.
Audit date: 2026-10-24 UTC (2026-10-23 on Claw). No account, credential, repository, protection,
workflow, hosting or canonical-agent change is made by this plan.

Authoritative inputs are [the Phase D design](OPENCODE-LIFECYCLE-D-PUBLICATION-DESIGN.md)
and [the D1/D2 implementation report](OPENCODE-LIFECYCLE-D12-IMPLEMENTATION.md).
The former remains SHA-256
`9cad8c39e1001ae2c430d57ce50c04b90ed1a9d14605ee3412d168781e06dba8`.
This plan specifies the next controlled implementation/pilot, not permission to
execute it. Desired settings are recorded separately in the inert
[desired-state manifest](d3/PUBLISHER-QUALIFICATION-DESIRED-STATE.json).

## 1. Findings and execution gates

All **84 D1/D2 source hashes** still match the final implementation receipt.
Retained results are 256 tests: 252 passed, four optional schema checks subsequently
passed with the existing system validator; 64 publication test methods; 21 core
role permission canaries, developer parity, five fixture calls and three actual
publication-preparation calls. These tests were **not rerun** during this audit.

Two concrete prerequisites prevent claiming a ready credentialed pilot:

1. The current development UID 1000 has unrestricted passwordless sudo and
   read/write access to the root-owned Docker socket. A second UID does not
   protect publisher keys from a compromised administrative process. Docker's
   [own documentation](https://docs.docker.com/engine/install/linux-postinstall/)
   identifies its group as a root-level grant. Run automated agents/source work
   under a separate non-admin identity before claiming that boundary. Trusted
   human host administrators remain outside it. If Codex/OpenCode continue under
   the administrative UID, strict credential isolation from those processes is
   **BLOCKED**, not established by directory modes or systemd flags.
2. The existing candidate guard compares normalized HTTPS hostname/effective
   port. Another project under `kcook98765.github.io` shares production's origin
   and is rejected. Preserve that control. The proposed pilot therefore needs
   separately approved ownership of a genuinely different origin.

No existing sudo/Docker membership is removed here. No alternative hostname,
organization ownership, credential, target ID or human review is assumed.

### Current remote state, refreshed by GET only

| Item | Observation |
| --- | --- |
| Production repository | Public `kcook98765/ai-kodi-repository`, ID `1428864210`; owner User `kcook98765`, ID `56806582` |
| Main | `d6e1359a6668e688891359869ef2c7d34bc2ddff`, unprotected; protection GET explicitly 404 |
| Pages branch | `e66f5f6ac88450b92a5d1c5a2d43be70b86c513f`, unprotected; protection GET explicitly 404 |
| Rulesets | Empty, including parent rulesets |
| Pages | Legacy branch deployment from `gh-pages`, root `/`, built, HTTPS enforced |
| Pages environment | ID `24961524844`; only branch `gh-pages`; no human reviewer; administrators may bypass |
| Actions | Default read permissions; cannot approve PR reviews; only dynamic Pages workflow |
| Existing Release | `tastemade-0.1.0`, ID `421485828`, `immutable=false`; ZIP and two checksum assets unchanged in metadata |
| Current CLI identity | Reports admin/push authority; never reuse it as an agent/publisher credential |
| Future immutability default | Not exposed in the inspected repository response; cannot infer it from one mutable historical Release |

Evidence: ignored `reports/lifecycle-d3-preparation/{baseline,github-audit,host-audit,proposed-destination}.json`.
Canonical local main is still the separately pending documentation commit; no
push/adoption is implied. Existing incoming private production artifacts remain
unavailable; `incoming/` contains only its README.

## 2. D1/D2 conformance and required extensions

| Reviewed requirement | D1/D2 evidence | Required D3 extension |
| --- | --- | --- |
| Frozen P/R/E | Canonical closed documents, complete hashes, source/package/lane/assets/ledger rederivation; any changed bytes stale the binding | Versioned qualification-only audience/destination; real remote IDs, heads, assets and policy baseline; no migration of old approvals |
| Independent review | Frozen report hash separate from package eligibility; role assessment remains procedural | Retain real reviewer task/session/tool provenance and owner inspection; local actor strings never authenticate a human |
| Exact owner decision | Explicit simulated identity, destination, nonce, expiry and digest | Read-only GitHub owner-proof verifier and trusted workflow scope artifact; reject all `approve-test` records for real writes |
| Replay and revocation | Locked persistent consumption/journal, independent revocation latch/index, fail closed on missing latch | Authenticated control-issue revocation, remote request/run correlation, installation/epoch binding; fresh owner-approved recovery |
| Publication | Concrete file fake only; create-only tag/assets, verification, Pages and ledger model | Real allowlisted HTTP/Git transport, real IDs/receipts, per-asset partial upload and exact-parent branch writes |
| Retention | Complete frozen site/ledger and immutable historical bytes, next-release blocking after partial failure | Discover all published remote assets plus ledger/journals; unknown orphan artifacts or missing journal block initialization/release |
| Recovery | Read-only reconciliation, exact recorded prefix and fresh E/nonce; observations work after policy expiry | Reconcile real objects and non-atomic partial uploads/deployments/PRs without blind retries |
| OS boundary | Same-user simulation; no keys, HTTP backend or privileged identity | Root-installed trusted code/policy, non-admin agent UID, separate publisher UID and verified sandbox/key custody |
| Role grants | Existing build/qualify/review preparation; no model authorization/execution | A separately approved disposable profile may gain only fixed request/status/execute interfaces; canonical grants remain unchanged |

Preserve the passing simulation mode and its tests. Do not change its constants
to real values, accept simulation approvals at a real backend or make a candidate
eligible by changing flags. Add an explicitly versioned
`isolated-transport-qualification` contract with an enrolled test-only destination,
installer/add-on namespace, trusted code and genuine owner authorization.

Transport qualification is a distinct gate. Package identity, licensing of the
test material, archive safety, audit, hashes, retention, destinations and owner
authorization remain mandatory. Native/interpreter outcomes remain UNVERIFIED;
real-package production eligibility stays false. This is not a production-policy
exception. Keep existing v1/v2/v3 release and exception consumers unchanged.

Candidate-feed retention commitments and the sandbox's **published** ledger are
different records. The sandbox published ledger starts empty and appends only
after verified publication; do not copy the populated candidate ledger and label
it published history. Bind both inventories independently in the new proposal.

## 3. Proposed Claw identity, ownership and invocation

Recommended new pilot identities, subject to separate host approval:

| Identity | Intended properties |
| --- | --- |
| `kodi-repo-agent-d3` | Dedicated existing-role runner; no sudo except the exact launcher below; no Docker, adm or publisher groups; no administrative SSH/credential access |
| `kodi-publisher-d3` | Locked system account/private primary group; nologin; no sudo, Docker, interactive SSH or supplementary groups; runs trusted publisher code only |
| Human host administrator | Installs reviewed code/policy and authorizes setup; remains a trusted root principal outside worker isolation |

Numeric UIDs/GIDs are assigned only at approved creation, recorded and pinned.
Do not widen access to existing private checkouts. Export a reviewed code/Toolkit
installation and create a separate disposable agent workspace outside them.
Do not run the D3 agent as a child of an untrusted source process with inherited
admin sockets, environment, credentials or arbitrary file descriptors.
Stop or relaunch administrative AI sessions under the non-admin boundary before
injecting pilot credentials if strict isolation from those sessions is required.
Provision only the agent's needed model authentication; do not copy administrative
GitHub/SSH credentials or general user configuration into its workspace.

| Proposed path | Ownership/mode and use |
| --- | --- |
| `/opt/ai-kodi-publisher-d3/versions/<code-sha256>/` | root:root; directories 0755, code/data 0644, fixed executable wrappers 0755; reviewed immutable-by-policy installation, no writable imports |
| `/usr/local/libexec/ai-kodi-publisher-d3-entry` | root:root 0755; minimal no-argument launcher, not a general command runner |
| `/etc/ai-kodi-publisher-d3/` | root:publisher-group 0750; root-owned policy/enrollment 0640; only explicit pilot destination enabled |
| `/etc/ai-kodi-publisher-d3/app-key.pem` | root:root 0600; **pilot App only**, loaded into approved transient jobs, never installed during preparation |
| `/var/lib/ai-kodi-publisher-d3/` | publisher:publisher 0700; sealed proposals, requests, append-only journal, receipts, independent revocation index and scratch subdirectories; files 0600 |
| `/run/ai-kodi-publisher-d3/` | publisher:publisher 0700; per-operation runtime files; bounded cleanup after durable receipts |
| `/var/lib/ai-kodi-agent-d3/` | agent:agent 0700; isolated role profile/workspaces; contains no publisher key, issuer token or writable publisher code |
| Durable backup destination | Owner-approved separate trust/storage boundary; not agent-writable; exact location not yet enrolled |

Only this proposed sudoers command is authorized for the agent identity:

```sudoers
kodi-repo-agent-d3 ALL=(root) NOPASSWD: /usr/local/libexec/ai-kodi-publisher-d3-entry ""
```

The empty quoted argument list is intentional. Do not grant `sudo python`,
`sudo bash`, `sudo systemd-run`, arbitrary arguments, environment preservation or
SETENV. The root launcher validates a small bounded JSON control header and
internally chooses fixed transient-unit properties. It does not execute uploaded
code, parse add-on archives as root or accept caller paths/unit names.

Control verbs: `submit`, `request`, `status`, `execute-one`, `reconcile`.
Inputs are enrolled task/proposal IDs and exact digests; no caller repository,
URL, executable, interpreter, policy file, working directory or environment map.
Bounded proposal bytes enter over a dedicated stream/file descriptor into the
unprivileged ingest job. No publisher access to a development checkout is needed.
Seal with descriptor-relative no-follow copying before independent review;
verify inventories, safe types, size limits, permissions and trusted tool pins.
Root policy chooses the destination and installation UUID/epoch; the caller cannot.

The root launcher starts a **transient one-shot** using the existing systemd
manager. No daemon, enabled unit, timer, socket service or agent framework is
introduced. Each invocation performs one bounded step and exits; manager polling
handles owner/deployment waits without a background process. Proposed properties:

```ini
[Service]
Type=oneshot
User=kodi-publisher-d3
Group=kodi-publisher-d3
UMask=0077
NoNewPrivileges=yes
CapabilityBoundingSet=
AmbientCapabilities=
ProtectSystem=strict
ProtectHome=yes
PrivateTmp=yes
PrivateDevices=yes
ProtectKernelTunables=yes
ProtectKernelModules=yes
ProtectControlGroups=yes
ProtectProc=invisible
ProcSubset=pid
RestrictSUIDSGID=yes
RestrictRealtime=yes
LockPersonality=yes
RestrictNamespaces=yes
RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6
InaccessiblePaths=-/run/docker.sock -/run/containerd -/run/dbus -/run/user -/var/lib/docker
ReadWritePaths=/var/lib/ai-kodi-publisher-d3 /run/ai-kodi-publisher-d3
WorkingDirectory=/var/lib/ai-kodi-publisher-d3
TimeoutStartSec=180
Restart=no
LimitCORE=0
MemoryMax=1G
TasksMax=64
```

Use `PrivateNetwork=yes` and **no credential mount** for ingest/local checks;
networked read/write steps use only fixed HTTPS transports. Root policy supplies
the pinned interpreter, isolated `-I -B` bootstrap and fixed installed code path.
The networked credential-bearing variant may add
`LoadCredential=github-app-key:/etc/ai-kodi-publisher-d3/app-key.pem`.
Scrub inherited environment and descriptors; disable Git hooks, caller Git config,
credential helpers and shell interpolation. No Docker or source execution.
These are proposed properties for the observed systemd 255, not a tested sandbox.
[The versioned manual](https://www.freedesktop.org/software/systemd/man/255/systemd.exec.html)
documents credentials and filesystem isolation. A read-only filesystem does not
block privileged Unix-socket IPC; test that denial explicitly. Empty configured
supplementary groups do not remove groups from the system account database.

GitHub review authenticates owner evidence; root-owned code enforces access to
the local issuer key. GitHub does not release that local key. Administrators can
defeat local controls, so current administrative model processes must not be
described as isolated by these settings. This remains an execution approval gate.

## 4. Disposable destination and credential boundaries

Recommended proposed target:

| Property | Desired value |
| --- | --- |
| Organization | `kcook98765-kodi-qualification`, proposed and not owned/created yet |
| Organization administrator | Human `kcook98765` (User ID `56806582`), ownership must be established and verified |
| Repository | `kcook98765-kodi-qualification/ai-kodi-publisher-d3-qualification` |
| Visibility | Public, synthetic code/artifacts only; supports documented public environment-review features without assuming paid private features |
| Pages origin/base | `https://kcook98765-kodi-qualification.github.io/ai-kodi-publisher-d3-qualification/` |
| Hosting | Branch `gh-pages`, root `/`, HTTPS enforced, `.nojekyll`; preserve existing static feed structure |
| Installer | Existing isolated candidate form `repository.ai.kodi.candidate.<pilot-task-id>`, display name clearly D3 qualification |
| Test add-on | First-party inert MIT `script.ai.kodi.d3.fixture`, versions `1.0.0` then `1.1.0`; no provider, streams, secrets or third-party art |
| Lane scope | Nexus transport catalog first; other catalogs remain complete but do not assert add-on native/interpreter compatibility; Piers qualification stays unverified |
| Published ledger | Separate sandbox `releases/manifest.json`, empty initial published history, exact append after verification; no production artifacts/records |
| Forbidden destination | Production repo ID `1428864210`, production name/origin and production installer/add-on package identities |

Bootstrap fixture source on branch `d3-fixture-source`: commit F10 contains
`fixtures/addon/` version 1.0.0, followed by F11 with version 1.1.0. Retain both;
pin their actual full commits, trees and runtime member hashes. This branch is
independent of main, so selecting F10/F11 does not move the publication baseline.
Source and destination remain distinct typed roles in the same disposable repo.
A second upstream test repository is optional and separately approved.

Enroll one stable 32-hex **campaign feed ID** as `pilot-task-id` for both versions.
Keep each source task/digest, publication E and nonce separate. The new
qualification assembler must use that explicit stable campaign context, preserving
installer identity/origin and unchanged installer ZIP bytes across the add-on
update. Existing C per-task feed creation creates a new installer for a new task;
it cannot simply be reused as a stable-update pilot. Do not mutate old bindings
or relax their checks. Reuse the existing deterministic builder/auditor under a
separate reviewed qualification adapter. If installer bytes change, increment its
version and separately review its maintenance proposal, retaining the old ZIP.

Read-only name checks returned 404 for the proposed organization/repository and
the same-owner alternative. A 404 is not a name reservation or ownership proof.
All new numeric repository/organization/App/environment IDs remain **unassigned**.
After separately approved creation, capture and reapprove actual IDs, origin and
bootstrap heads before enrolling any write authority. A custom hostname owned by
the user is an alternative, requiring separate DNS/HTTPS approval and proof.
The proposed repository's `owner.id` is the new **organization ID**, distinct from
the approving human User ID `56806582`. Keep repository-owner, human-owner, App,
bot-user and installation identities separately typed; never substitute one ID
for another in source/destination validation or authorization.
Do not use case, trailing-dot, encoded-path or alternate-port aliases to evade
the origin guard. Do not relax the guard to use a same-owner project path.

An organization pilot exercises public branch/tag rulesets but does not prove
every personal-account production behavior. Personal production controls still
need separate D4 adoption/verification. This topology difference is explicit.

Create a dedicated App proposal named `ai-kodi-publisher-d3-claw`, owned by the
human/qualification organization as approved, installed on **only** this repository.
No production installation, classic PAT, ambient `gh` login or all-repositories
grant. Suggested token caps, always narrowed by exact repository ID:

| Operation | Required repository permissions |
| --- | --- |
| Request fixed approval workflow | Actions write; metadata read; no Contents write or Deployments write |
| Observe approval, Pages, policy and artifacts | Actions read, Contents read, Pages read, Administration read where required; public issue comments can be read without a write grant |
| Tag/draft/assets/Pages branch | Contents write only for mutation; required observation permissions remain read-only |
| Exact finalization branch/PR | Contents write and Pull requests write, distinct capped invocation; no main direct-push or review approval |
| Human setup | Owner/admin settings changes only, not runtime App authority |

Do not grant Administration write, Workflows write, Deployments write or Issues
write to the runtime App. Contents and Actions permissions are coarse; installed
code, policy and rules enforce narrower operations. The protected workflow has
read-only default token permissions and no local publisher key.
[Installation tokens](https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/generating-an-installation-access-token-for-a-github-app)
can be narrowed to repository IDs/permissions and expire after one hour. Mint
only the current action's cap after its gate, discard/revoke it on completion,
and never return tokens in arguments, logs, reports or model output. Do not assume
a fixed token string format.

Verify minimum-scope visibility of required policy fields in the pilot. GitHub
documents in the [ruleset read API](https://docs.github.com/en/rest/repos/rules#get-a-repository-ruleset)
that bypass actors may be omitted for callers without the
necessary access; absent data is not an empty allowlist. If required inspection
is unavailable, stop for a separately approved read-only inspection arrangement;
do not add Administration write to make a preflight pass.

## 5. Exact GitHub settings and non-disruptive rollout

[Branch/tag rulesets](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/available-rules-for-rulesets)
are supported on public user/organization repositories. Classic actor-restriction
and organization-only controls must not be assumed to work on the personal
production repository. Use active branch/tag rulesets, not a public push ruleset.

| Ruleset/settings | Exact desired behavior | Impact / qualification |
| --- | --- | --- |
| `main-integrity`, branch `refs/heads/main` | PR required, one approving owner CODEOWNER review, stale reviews dismissed, last push independently approved, threads resolved, no force/delete; bypass actors empty | Bootstrap root CODEOWNERS with `* @kcook98765` after owner membership is confirmed; use App-authored ledger PR so owner can review |
| `main-validation` | Strict required check `qualification-validation`; expected CI App ID captured after bootstrap | Enable only after check exists and passes; do not invent a passing/missing check or bypass a blocked merge |
| `pages-writer`, branch `refs/heads/gh-pages` | Restrict updates; only enrolled publisher App is the authorized writer | GitHub represents this writer allowlist using an Integration bypass actor **only in this set** |
| `pages-integrity`, same branch | Block force pushes and deletion, linear history; no bypass actors | Publisher performs a normal exact-parent fast-forward and cannot bypass integrity rules |
| `tags-creator`, tag `refs/tags/script.ai.kodi.d3.fixture-*` and chosen installer tag pattern | Restrict creation to publisher App only | Newly approved tags only, no mutable aliases |
| `tags-other-creations`, all tags excluding those two pilot patterns | Restrict creation; bypass actors empty | Even the App cannot create an unrelated tag; bootstrap source uses commits, not extra tags |
| `tags-immutable`, all tags | Restrict updates/deletion; bypass actors empty | App cannot move/delete a prior tag; include every legacy tag when later designing production protections |
| Approval environment `kodi-d3-publication` | Required User `56806582`, prevent self-review, administrators cannot bypass; selected branch **main** only | Dispatcher is an App, owner reviews exact E before any release/tag/site write |
| Pages environment `github-pages` | Same required owner/no-self/no-admin-bypass; selected branch **gh-pages** only | Additional human review for actual Pages deployment; does not authorize earlier Release writes |
| Pages settings | Deploy from branch gh-pages `/`, HTTPS enforced, no production CNAME | Keep static hosting structure; no production hosting migration |
| Releases | Settings → General → Releases → Enable release immutability | Draft first, upload/download-verify all assets, publish, require immutable readback |
| Actions defaults | Read-only default token; PR-review approval false; reviewed actions SHA-pinned | No secrets/issuer key in untrusted PR jobs; do not add a self-hosted privileged runner |

The writer allowlist uses GitHub's `bypass_actors` API terminology; it is not a
blanket bypass of review, integrity or immutability. This mechanism requires owner
acceptance. If the requirement means literally **no bypass actors anywhere**, a
normal PR-only Pages flow is the alternative; it needs separate review of commit
binding/merge semantics and is not silently substituted for the reviewed exact-
parent push design. Settings sketches, not executable API payloads, are in the
desired-state manifest.

Required PR approvals must be achievable. Bootstrap trusted workflow/code first
under explicit setup authority, establish the validation check, then enable the
rules. Routine ledger PRs come from the integration App; owner review is distinct.
Verify the human owner's write/organization-owner access before enabling the
CODEOWNER gate. Another independent maintainer is optional, not invented. Do not configure an impossible self-review
gate or fake a required status. No need to change current merge methods merely
to test the pilot.

GitHub documents that [immutability affects future releases only](https://docs.github.com/en/code-security/how-tos/secure-your-supply-chain/establish-provenance-and-integrity/prevent-release-changes).
It does not retroactively lock Tastemade. Preserve/monitor its exact current tag
and assets; no replacement/deletion/re-upload. Immutable assets/tag do not freeze
all title/notes/latest labels or prevent every administrator operation; publisher
exposes no delete or mutable replacement action.

D4 must apply no-update/no-delete tag integrity to **all production tag refs**,
including `tastemade-0.1.0`, with no publisher bypass. Pilot creation patterns are
not production namespace coverage. Protecting an old tag does not retroactively
make its already mutable Release assets immutable; continue explicit hash checks.

[Pages branch publication](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site)
is implemented by GitHub Actions. An App push must be qualified; a GITHUB_TOKEN
push does not trigger a branch Pages build. Protect `github-pages` for actual
deployment review, and keep the separate pre-all-writes approval environment.
The second Pages review is an additional owner interaction, followed by normal
protected ledger PR review; routine execution needs no Codex but is not unattended.

No settings are enabled now. The production repository needs no D3 setting change.
After the disposable pilot, a separately approved production change window can
adopt protections in dependency order: trusted checks/PR path, main rules,
publisher writer/tag restrictions, approval/Pages environments, future release
immutability. Existing HTTPS bytes remain unchanged by configuration alone, but
new pushes/deployments may become blocked/waiting; rehearse before adoption.

## 6. Exact owner-facing authorization

The manager prepares a sealed proposal and asks for substantive independent
review. The owner receives this manifest view, derived from the same frozen bytes:

```text
Scope: D3 DISPOSABLE TRANSPORT QUALIFICATION — production authority false
Add-on: D3 transport fixture / script.ai.kodi.d3.fixture / 1.0.0
Source: <owner-approved repository ID/name and immutable commit>
Lanes: Nexus catalog transport; interpreter/native UNVERIFIED
Package: <filename, byte size, SHA-256>
Review: <independent report digest, task/session provenance, findings>
Evidence: <static/offline/transport scopes, digests and unverified limitations>
Rights/provider: first-party test-material review; no provider integration
Release: <exact tag/commit/title/notes and asset names/sizes/hashes>
Pages: <origin, branch, old/new heads/trees, complete additions/changes>
History: <original ledger, append-only successor, retained artifacts/backups>
Destination: <actual test repository numeric ID, name and owner ID>
Proposal: sha256:<E>; nonce:<N>; expires:<UTC>
```

Full private P/R/evidence stays in the sealed local store; safe reviewed summary,
digest and request scope are emitted by a trusted approval-only workflow on main.
The workflow-generated request artifact binds E/N/destination, workflow revision,
environment and run/attempt. Owner can inspect exact local bytes through a
read-only owner viewer; no public artifact contains private intake or local paths.

The App dispatches the enrolled workflow; the human owner reviews its environment
job with this exact qualification-only comment:

```text
APPROVE D3-QUALIFICATION sha256:<E> nonce:<N> repo-id:<test-repo-id> run:<run-id>
```

The live verifier requires real GitHub User `56806582`, exact environment/run/
workflow/input-artifact bindings, first attempt only, no contradictory rejection
or bypass, current policy and expiry, unused nonce and correct installation epoch.
Capture the dispatcher's bot User ID/login separately from App ID and installation
ID. A run's `actor.id` is not an App ID; never infer one from the other. Correlate
the exact dispatch response/run and scope artifact, rejecting ambiguous matches.
Workflow success, a local approval JSON, `release_approved=true` or an App comment
is insufficient. Local `approve-test`/simulated identities remain rejected by the
networked qualification path. This genuinely tests human approval for a synthetic
release; no synthetic event may impersonate that human.

Recommend a one-hour pilot request lifetime, capped by any earlier evidence
expiry. GitHub's [review-history response](https://docs.github.com/en/rest/actions/workflow-runs#get-the-review-history-for-a-workflow-run)
does not supply approval timestamp/run attempt: get attempt from run data, record
actual first observation time and never invent an event time. Reruns require
fresh E/nonce/run/owner review. Any changed bytes or destination invalidates E.

Owner revocation: `REVOKE <E> <N>` on one enrolled control issue, accepted only
from the pinned numeric owner. Check all pages before each write, latch observed
revocation durably even after edit/delete, and fail closed if unreadable. No App
Issues/Deployments-write approval path. An administrative local stop is not a
model tool. Cancellation/recovery cannot erase immutable published artifacts.

Before Pages deployment, owner separately reviews the actual matching Pages
run/commit under `github-pages`; the operator correlates its review to E and the
expected branch head. Reject wrong/stale run selection. An environment's native
review UI is not an artifact-digest verifier; the local operator provides binding.

Expiry blocks starting/resuming operator writes. Already accepted GitHub jobs or
requests may finish later; no claim of atomic cancellation is made. If a Pages
job waits past E expiry, report pending/expired, do not start another write,
and require owner-controlled cancellation/reconciliation or fresh recovery
approval before continuing. Never automatically approve a pending job. If strict
server-side expiry of the eventual deployment is required, a custom Pages workflow
with a post-review expiry verifier is a separate hosting/design decision; legacy
branch deployment must not be advertised as providing that guarantee.

## 7. Reproducible pilot procedure (all NOT EXECUTED)

1. **Approve setup scope.** Confirm non-admin execution boundary, ownership of
   the distinct origin, public synthetic-only repository and pilot-only App.
   Approve exact host/code installation and bootstrap write inventory separately.
2. **Bootstrap destination.** Owner creates the approved organization/repository,
   seeds reviewed trusted source/workflow/check and empty published ledger plus
   gh-pages, configures Pages/environments/rules/immutability. Capture actual IDs,
   heads, ruleset payloads and actor/field visibility. Bootstrap is not a release
   proposal or a general future publication grant.
3. **Prove isolation before keys.** Test agent denial of keys, state, runtime
   credentials, Docker/D-Bus/admin paths, alternate interpreters and launcher
   argument injection. Confirm no groups/host-admin escape. Only then install
   the specifically approved pilot App credential, never a production credential.
4. **Prepare fixture 1.0.0.** Enroll exact source/commit, build twice with existing
   deterministic machinery, independent audit and a distinct candidate installer/
   origin. Check complete catalogs/sidecars/bootstrap and sandbox published ledger
   separately. Keep native/interpreter/Piers facts unverified. Freeze P.
5. **Independent review.** Reviewer checks sealed source-to-ZIP mapping, all test
   material/rights, lane metadata, dependency closure, exact delta/retention,
   trusted code and destination. Freeze R, then E against actual remote heads.
6. **Owner approval.** Request the protected workflow, display the manifest above,
   capture the owner's exact qualification review. Negative missing/forged/test
   approvals must produce **zero mutation requests**.
7. **One-shot publication.** Reserve nonce/journal before effects; revalidate
   owner/source/destination/policy/heads at each step. Create exact new tag and
   draft; upload exact ZIP/sidecar/sums individually with IDs and receipts; download
   each asset and compare actual bytes; publish only the complete draft, then
   verify immutable status and tag commit. No auto-tagging from moving main.
8. **Pages promotion/review.** Push the precomputed exact child normally, never
   force; await the matching deployment and owner Pages review. Return/poll bounded
   status rather than leave a writer running for human approval. Record pending,
   failed or unknown states accurately.
9. **Public verification.** Bounded HTTPS HEAD/GET of complete site, ZIPs, SHA
   sidecars/catalogs, root/index and negative contamination paths. Require exact
   bytes/MIME/redirect policy and deployment commit. Release redirects use explicit
   storage-host rules without cross-origin credential forwarding. No native test.
10. **Ledger finalization.** Propose only the approved append/config changes on a
    fixed branch/PR; owner approves through normal protected checks. Verify actual
    merged tree/parents and ledger chronology. Until verified, report
    PUBLIC_BUT_UNRECONCILED and block another release. No main direct push/bypass.
11. **Replay/update.** Reuse E/nonce: zero new effects. Independently prepare/review/
    approve fixture 1.1.0; ensure 1.0.0 assets remain unchanged and catalog selects
    the intended higher version. This is metadata transport, not Kodi update proof.
12. **Interruption/recovery.** Intentionally stop at preapproved checkpoints,
    including response loss after Release exposure and after Pages push, partial
    upload and finalization failure. Reconcile GETs only; unknown foreign objects
    remain blockers. Fresh exact-state E/nonce/owner approval resumes only missing
    operations. Never blindly retry POST/upload/merge or adopt unreviewed bytes.
13. **Freeze evidence and retire.** Rehash all source/proposals/reviews/API/HTTP/
    journal receipts and independently review pilot outcomes. Revoke pilot tokens/
    App access, disable invocation after in-flight reconciliation, archive under
    the retention policy below. No automatic production enrollment follows.

The existing fake's atomic `upload_assets` and whole snapshot CAS are not GitHub
transactions. Real transport needs per-object state, before/effect/receipt journaling
and exact operation identity. GitHub has no atomic Release/branch/PR transaction.
An exact-parent non-force branch push handles competing branch changes; tags/
asset creation detect name collisions; other drift stops subsequent writes and
preserves the permitted prefix. Runtime API errors must never trigger force,
clobber, overwrite, automatic rebase or privileged fallback.

## 8. Qualification cases, evidence and forward recovery

The independent tester's private report contains 23 proposed cases, all
NOT_EXECUTED. Required acceptance groups:

| Group | Required negative/success cases and oracle |
| --- | --- |
| Isolation | Source/model UID cannot read keys, credential runtime, journals or alter code/policy; no Docker/admin/sudo escape or arbitrary launcher command |
| Destination | Reject production ID/name/origin, same-origin alternate path, aliases and unenrolled repo before minting a write token or sending a mutation; no live production-target probe |
| Freeze | Changed ZIP/member/source/review/catalog/Pages/destination/head/ledger changes invalidate old E/approval; self-consistent forged inventory independently rejected |
| Owner proof | Genuine owner passes; missing/test/bot/wrong owner/env/workflow/run/attempt/comment/digest/expiry/revocation fails with zero mutations |
| Policy | Read back active split rules, exact publisher writer role, immutable-release behavior; insufficient visibility fails closed; forbidden write tests use disposable destination only |
| Concurrency | Advance main/gh-pages/tag/assets during approval wait and between effects; normal push rejects stale parent, no auto-merge/rebase or overwritten content |
| Release | Missing/conflicting/extra/corrupt asset, duplicate upload and lost response; never replace an immutable asset or promote an incomplete Release |
| Pages/public | Required owner review actually waits, wrong deployment SHA, partial/mixed bytes, HTML ZIP, missing sidecar, redirect/HTTPS failure; no complete PASS from branch push alone |
| Ledger/history | Owner-reviewed exact finalization, failure after public exposure, orphan published package, missing/stale journal, chronology/source continuity; next release stays blocked |
| Recovery | Controlled interruption at every write; exact observations, retained old/new assets, new owner approval for missing suffix; rejected stale/replayed/revoked approval |
| Claims | Production/native/interpreter/Piers statuses remain false/unverified; no Kodi Lab call, installation or unattended publication |

Each result records code/policy/schema hashes, numeric destination/actor, source,
P/R/E digests, nonce/epoch, step, time, expected/observed heads, API/asset/run/PR
IDs, actual content hashes, ordered remote calls and retained recovery state.
No secrets, auth headers or private raw evidence enter public logs. A fault test
passes only if its observed effects equal the approved prefix; a fake response or
green workflow cannot establish actual remote enforcement.

Keep approvals, journals, revocation observations, original private review and
recovery receipts durably with restrictive ownership. Back up and independently
recover-test before the first pilot write. Restore/reinstall starts disabled with
a new epoch and owner-led remote reconciliation; an internal hash chain alone
cannot detect whole-store rollback. Reconcile all existing public assets when
enrolling a destination, not only current catalogs; do not start with an empty
journal over an unresolved earlier publication and call it a fresh release.

Forward rollback requires a new exact approved corrective proposal. Retain every
published immutable ZIP/sidecar/tag and append history; restore only coherent
selected metadata while retaining new artifacts. A lower selected catalog version
does not downgrade an installed Kodi add-on. D3 performs no installs/downgrades.

### Cleanup and retention

The destination is isolated, not automatically disposable after success. Proposed
policy: freeze/retain its published artifacts and complete private evidence for
at least 90 days after the final review, then retain until the owner separately
approves archival/deletion. Revoke test App access and disable invocation promptly
after reconciliation; remove only credential runtime and non-evidence scratch.
No automated release/tag/asset/repository deletion or cleanup task. Prefer archive
after recover-tested export. Any destructive retirement needs separate approval
and must never touch production. Do not reuse immutable Release tags or the old
destination identity for another campaign.

## 9. Blockers and separate approvals

| Item | Blocks disposable D3? | Blocks real production? |
| --- | --- | --- |
| Administrative development UID / unproven key isolation | Yes, before credentialed isolation qualification | Yes for strict worker-compromise isolation |
| Different-origin destination ownership, numeric IDs and public Pages | Yes | Does not itself block existing production hosting; required for this pilot |
| Real transport/owner-proof/sandbox implementation absent | Yes, implement/review before pilot | Yes |
| Pilot-only App/host/protection/bootstrap authority absent | Yes | Production setup remains separately unapproved |
| Missing original private production ZIP/review/evidence | No for independent synthetic test repo/ledger | Yes; restore exact retained originals, do not infer approvals from hashes |
| Piers matching static tooling unavailable | No for Nexus transport scope with Piers UNVERIFIED | Yes for a proposed Piers admission |
| Target-interpreter/native acceptance unverified | No for explicitly transport-only inert test material | Yes where the real release contract requires them; existing exact exceptions retain their scope |
| Expired/incomplete policy evidence | Yes if the pilot's own required artifact/right/owner evidence is absent/expired | Yes for affected real releases, including retained records under current semantics |
| Historical numeric source identity absent from old records | No for newly enrolled test fixture | Must resolve for real continuity claims; URL/commit evidence alone cannot prove historic numeric IDs |
| External dependency snapshots/nonnumeric versions unsupported | Avoid in fixture | Blocks real packages needing unsupported cases |

Specifically absent are the configured `plugin.video.tastemade-0.1.0.zip`
(SHA-256 `d21af0f89c118c2a4c789b656b27d6211a086cce961dc3501fa4ad00564fce87`)
and `tastemade-review-v3-approved-r10.json`
(SHA-256 `442db92cb401bf981de89eeebac9be54492a81d97fa57abcf2bb69f4a33df05f`).
The ledger still pins installer 0.1.0 and Tastemade 0.1.0. Current validity/expiry
of that missing private decision is **not established**, rather than asserted
active or expired. Pilot evidence is not yet created; its own missing/expired
approvals also block execution.

Requested future approvals, individually bounded:

1. Review/accept this plan and authorize a **local real-transport/owner-proof and
   isolation launcher implementation**, preserving D1/D2 fake behavior. This is
   separate from actually installing accounts/keys or making remote writes.
2. Select the non-admin agent boundary; approve exact new pilot account/layout/
   launcher/sandbox and backup installation. If admin-run models must remain,
   explicitly decide the threat-model limitation; do not call it key isolation.
3. Approve the proposed organization/repository ownership/public visibility and
   distinct origin, or supply an owned alternative satisfying the existing guard.
4. Approve bootstrap writes, pilot App/key custody and selected-repository grants,
   protected branches/tags/environments, immutability and required-check setup.
   Reapprove assigned IDs/heads before enabling the operator.
5. Accept scoped writer-allowlist API semantics, extra owner Pages review and normal
   ledger PR review; alternatively review a PR-only Pages/hosting redesign.
6. Approve one exact initial pilot proposal, the bounded negative/fault campaign
   against that disposable target, and each fresh recovery/update proposal.
7. Approve the proposed retention policy; defer destructive cleanup. Production
   enrollment/credentials/settings, canonical adoption, native tests and every
   production release remain independent D4/D5 decisions.

Nothing above grants a future arbitrary release approval. D3 preparation changes
no D1/D2 implementation, approval record, role grant or production resource.

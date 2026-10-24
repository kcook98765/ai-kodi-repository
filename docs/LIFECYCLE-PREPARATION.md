# Task-bound OpenCode lifecycle preparation, Phases A-C

This optional **local worktree** adapter extends the existing manager, tester and
reviewer tools. Canonical installed profiles are unchanged. This implementation
has no GitHub writer, publisher, native controller or production-feed build path.
It uses the existing Toolkit, deterministic package builder, review-record
contract and independent archive auditor. Source is data, never imported/executed.

## Installation and authority

The operator explicitly runs `python3 -B scripts/lifecycle.py install` with
`--toolkit`, `--plugin-module` and `--shared` pointing to existing trusted
installations. The script derives its distribution root from its own location;
there are no workstation checkout names in the new path. It refuses to overwrite
an existing profile. For future migration, preserve/recover-test the old ignored
profiles first and separately authorize activation. No shared dependency install,
production profile replacement, service or credential change is performed.

The tracked templates under scripts/opencode generate ignored local opencode.json,
role files, tool file and installation manifest. Permission dictionaries retain
insertion order because matching order affects the permission engine. The same
tool names, exact role/delegation grants, report-only edits, shell denial and MCP
denial remain. Root rebinding changes the permitted project identity, not grant
semantics. Model/provider and Toolkit skill paths are inherited/preserved.

The installation manifest pins the trusted Toolkit source-file hashes,
interpreter identity, distribution versions/RECORD digests and cache manifest.
Distribution RECORD digests fingerprint installed metadata; they are not a
re-hash of every third-party installed file or a whole-environment integrity proof.
Task enrollment checks these pins. Validation checks them again; no silent
environment upgrade is accepted. Requalifying/changing this manifest is an
operator action, not a role-tool capability.

Only the operator can enroll/revoke a task. A nonempty owner_authorization is an
operator-retained reference to the owner's actual instruction, not authenticated
proof by itself. The agent cannot create a new binding through any exposed tool.
The boundary is the existing OpenCode permissions plus trusted local operator
control; it is not a cryptographic signature or adversarial same-user OS sandbox.
Task bindings expire after 24 hours and can be revoked sooner. Re-enrollment
requires current owner authority and produces a distinct task ID/digest.

## Owner-selected repository and immutable source

Use `python3 -B scripts/lifecycle.py resolve OWNER/REPO branch BRANCH` (or tag or
commit) for anonymous read-only discovery. Repository transfers/renames, private
access or a different numeric repository ID fail closed. Commit inputs require
full 40-character lowercase SHAs. Tags can be lightweight or bounded annotated
tag chains. Discovery accepts only public GitHub HTTPS and fixed endpoints;
there is no generic endpoint/URL, shell, gh HOME, token or credential fallback.
Access/rate-limit errors are BLOCKED, never empty results.

Create a local request conforming to config/LIFECYCLE-TASK-SCHEMA.json:

```json
{
  "schema": 1,
  "owner_authorization": "retained reference to the owner's exact source/preparation instruction",
  "repository": "OWNER/REPO",
  "repository_id": 123456,
  "ref_kind": "tag",
  "ref": "v1.2.3",
  "expected_commit": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "lanes": ["nexus", "omega"]
}
```

These are placeholders, not an authorization or approved source. `expected_commit`
is optional when the owner's instruction intentionally selects a moving branch;
the enrollment resolution becomes immutable for that task. If supplied, ref
movement from the expected commit rejects. Run
`python3 -B scripts/lifecycle.py enroll REQUEST.json`, retain the returned task_id
and expected_digest and supply both to every role operation. No supplied path can
redirect task storage or production destinations.

The binding records repository numeric/name identity, requested ref, resolved
commit/tree, requested Kodi lanes/target versions, production config/ledger
digests, installation/toolchain/schema hashes, permitted stages and false native/
publication authority. Matrix 19.5, Nexus 20.5, Omega 21.3 and Piers 22 are target
labels, not accepted compatibility. Changed installation, source identity,
baseline, task digest, schema/toolchain, expiry or revocation stops that task.

## Existing role tools with task arguments

All examples below additionally require task_id and expected_digest. An absent
binding keeps the original fixture operation, never a default production action.

| Tool and role | Task arguments | Effect |
| --- | --- | --- |
| kodi_github, manager | action=acquire | Fetch pinned Git tree/archive, verify every Git blob and archive path, store source data and return manifest locations |
| kodi_github, manager | action=list, resource=issues/pulls/releases, page=1..5 | Recheck repository ID, fixed GET, at most 20 records/page, disclose nonexhaustive coverage/next-page |
| kodi_inspect, all existing roles | no further arguments | Read own binding/state and bounded acquired inventory |
| kodi_inspect, all existing roles | file=relative source member | Return at most 64,000 bytes of UTF-8 source as explicitly untrusted data |
| kodi_build, manager | addon_subdir=relative directory or `.`, runtime_files=explicit array | Freeze selection, deterministically build/audit candidate package and metadata |
| kodi_validate, tester | lane=matrix/nexus/omega/piers | Run the independently registered matching-stub Toolkit static CLI on selected runtime bytes; persist stages/warnings, scope and cache identity |
| kodi_validate, tester | enrolled lane without qualified tooling | UNVERIFIED, with an immutable scoped receipt; no other-lane substitution |
| kodi_build, manager | action=feed | Build and freeze the complete candidate repository using existing builder/auditor/qualifier in isolated task staging |
| kodi_qualify, manager/tester | no further arguments | Verify frozen candidate package/source/evidence and any complete feed; no rebuild or native execution |
| kodi_review, manager/reviewer | no further arguments | Independent archive/source mapping, metadata and recorded static-evidence audit; reviewer remains the independent role |

Use original Toolkit validation/compatibility skills, while respecting these
actual schemas. Task qualification verifies frozen package/feed evidence. Feed
construction invokes the existing full qualifier before freezing; reviewer checks
do not rebuild it. The zero-argument fixture workflow remains separate.
Model roles cannot enroll, change decisions, edit source or install dependencies.
Direct CLI `--role` alone is not authorization for a hostile local OS user; role
identity must come from OpenCode's trusted context and permission engine.

Run state is under a per-task lock, with generation compare-and-write and immutable
transition records. Closed per-stage schemas/journal/predecessor digests reject
malformed or stale state. A failed acquisition with ambiguous partial local files
requires inspection/new enrollment, not retargeting an existing task.

## Package and metadata outputs

Data lives in `.opencode/lifecycle-data/<task_id>/`, beneath existing denied raw
read/edit rules. Tools independently enforce exact task containment; a role can
inspect only its supplied binding through those tools. No host-path arguments,
linked ancestors, traversal or cross-task file reads are accepted. This is local
tool/role isolation, not a claim of an adversarial OS sandbox. Public source
configuration, AGENTS, plugins and build/test hooks remain inert data.

Acquisition checks API repository/commit/tree identity, rejects truncated trees,
and verifies downloaded member contents using Git blob hashes. Archive/member
counts, byte limits, single root, portable paths, duplicates, special/linked files,
CRC and redirects are checked before materialization. LFS, submodules, export-
ignored/missing tree content and unsupported source layouts fail closed. GitHub
archive root-name formatting is not trusted as identity.

This uses the documented [Git tree API](https://docs.github.com/en/rest/git/trees)
and [commit-addressed archives](https://docs.github.com/en/repositories/working-with-files/using-files/downloading-source-code-archives),
while enforcing smaller local response limits and rejecting truncated inventories.

Runtime selection freezes one actual manifest/root and explicit file allowlist.
Existing ID/version/metadata, extension entry point, dependency declaration,
artwork/license, hidden/development-file, checksum and credential-pattern checks
apply unchanged. No source tests, setup.py, package install, Git hooks/filters or
add-on entry points run. Repository-installer identity is reserved for separately
scoped maintenance. Existing identical versions report no new release; changed
bytes at a published version and version regression reject.

Outputs include:

- source archive/file hashes and frozen source-to-runtime mapping;
- canonical deterministic runtime ZIP, SHA-256 sidecar and pending strict-v2
  review record with rights/static/runtime/final acceptance remaining false;
- config/candidate.json in existing intake schema;
- untouched copies of production config/repository config/retention ledger;
- candidate change-proposal.json containing exact proposed config/ledger data,
  retained records needing scope review, blockers and application_authorized=false;
- per-lane **catalog fragments**, with exact XML/sidecars for the candidate only,
  clearly separate from a complete installable repository feed;
- frozen preparation and tester receipts. Reviewer verifies all referenced
  receipt hashes, lane/package/source/toolchain identity and original stage
  warnings. It never treats a tester summary as rerunning validation.

Every production/catalog promotion remains unavailable. The original builder
retention guard still rejects changed production installer bytes. Complete local
candidate feeds instead use the explicit isolated context described below. Applying
production lane changes still requires real successor decisions and retained
artifacts; local preparation supplies neither.

Existing scripts/audit_candidate.py supplies independent ZIP and complete-site
inspection. It reconstructs metadata separately from builder output. A package or
feed-mechanics PASS can coexist with failed/unverified static lanes and release
blockers: read each scope/result. Static checks never flip static_accepted or
runtime_accepted; no native compatibility is claimed.

## Verification and remaining phases

Run focused unit checks using the trusted Toolkit interpreter, then the complete
repository unittest suite on settled bytes. tests/check_lifecycle_permissions.py
compares the actual OpenCode resolved manager/tester/reviewer rules with canonical
after root rebinding, evaluates harmless canaries without executing their checked
operations, and optionally exercises the full zero-argument fixture cycle. These
checks use supported debug tools without inference, production changes or services.

The following are now available in the isolated Phase C installation. No canonical
activation or native test is performed by this document.

## Independent static lane environments

Operator command `python3 -B scripts/lifecycle.py configure-lanes` registers local
Matrix 19.0.3, existing Nexus 20.0.1 and local Omega 21.0.0 Kodistubs environments.
It refuses to overwrite an existing registry. New environments copy the trusted
Nexus environment and install only exact hash-pinned stub wheels with no dependency
resolution; pip runs through the copied environment's Python module, not scripts
with old shebangs. No shared Toolkit or environment is modified. Acquisition is
operator-only, never an agent permission to install software.

The closed registry binds paths, Toolkit/interpreter/distribution metadata/cache
identity, exact stub major/version and explicit coverage limits separately for
all four requested lanes. Each lane checks its own official offline index filename,
source URL, byte hash, schema and timestamp, including before cached returns and
during review. Missing/mismatched tooling, index drift, unknown lanes and unsupported
versions fail closed. All selected receipts are immutable and referenced by state.

| Requested target | Matching stubs and available static evidence | Runtime/native scope |
| --- | --- | --- |
| Matrix 19.5 | 19.0.3; independent positive/negative API controls | UNVERIFIED |
| Nexus 20.5 | 20.0.1; existing environment plus independent controls | UNVERIFIED |
| Omega 21.3 | 21.0.0; independent positive/negative API controls | UNVERIFIED |
| Piers 22 preview | No published or independently qualified 22 environment; UNVERIFIED | UNVERIFIED |

The pinned Toolkit uses Python 3.10 for syntax and mypy, and mypy 2.4.0 does not
support older targets. A PASS therefore means those explicit static checks with
matching Kodi API stubs passed. It is not complete target-interpreter compatibility:
Matrix, in particular, can run on earlier Python builds. No runtime version is
inferred from a manifest Python floor or platform=all. Retain this limitation in
reports rather than advertising full Matrix/Piers support. A separately reviewed
Python-target/stub-tooling extension is required to remove the gap.

Piers is never tested against Omega/Nexus stubs. A pinned upstream 22.0.0a3 source
exists, but was not installed/independently qualified as preview tooling in this
phase. A later reviewed preview/published environment and representative API controls
are prerequisites. A registry status change alone supplies no qualification.

## Complete isolated candidate feed

After package preparation and all desired static checks, manager invokes
`kodi_build` with `action=feed` and the same task ID/digest. The task freezes a
complete feed, not only the earlier catalog fragments. Subsequent tester/reviewer
calls verify its original bytes and receipts; they do not rebuild. Further static
validation is refused once the feed is frozen; use a new task for changed evidence.

Optional operator enrollment fields are `candidate_base_url` and `feed_members`.
The URL must be an HTTPS origin distinct from production, with canonical path and
no credentials/query/fragment. Explicit :443 and trailing-dot production aliases
also reject. Default is `https://candidate.invalid/<task-id>/`, a safe placeholder,
not a reachable native-test service. A different destination requires a new
candidate identity/task or a genuinely new installer version; existing ID/version
bytes cannot be replaced. No server or hosting deployment is created here.

`feed_members` lists at most 25 prior prepared task IDs and exact binding digests.
They are owner-bound dependency/older-candidate inputs, never arbitrary paths.
Each is locked and reverified. Same-ID successors must retain source repository
identity, ID/version collisions reject, one highest numeric candidate is selected
per ID/lane, and previous ZIPs remain byte-identical downloads with empty current
lane scope. This is candidate history, not a substitute for production history.

The isolated staging tree keeps original production config/ledger/installer source
unchanged. Only candidate profile loads config/candidate-repository.json, whose
context binds those production hashes and the task ID. Default production/fixture
loading keeps the original identity gate. The generated installer uses
repository.ai.kodi.candidate.<task-id>, visibly says LOCAL CANDIDATE, and references
only the isolated destination. The candidate ledger is a new history namespace
bound to that identity, not a cleared production ledger.

Candidate intake contains exact original runtime ZIPs plus derived **pending
strict-v2 drafts**. Original task review records remain immutable and hash-bound.
No v3/first-release exception can be enabled using empty candidate history. All
rights/static/runtime/final decisions remain false/pending. Dependencies resolve
only through admitted same-lane packages and reviewed baseline built-ins; optional
misses remain warnings, required misses/cycles fail. External snapshots remain
unavailable pending separate reviewed support.

The existing builder, qualifier and independent auditor run from copied trusted,
hash-pinned scripts. They generate all four catalogs/sidecars, nested packages,
artwork, candidate installer/root mirrors, index and complete inventory. Repeat
builds prove whole-site reproducibility; a candidate-only ledger pins all retained
candidate packages including its installer. The independent auditor reconstructs
identity/inventory from reviewed inputs, rather than trusting producer plan hashes.
The task freezes all staging inputs, outputs, source/evidence references and
verification receipts under its state digest. Extra/changed files, altered copied
verifiers, changed parents/validation evidence or retention data reject.

Production preflight continues to reject this candidate profile. There is no
production build, approval writer, publisher or remote operation in role tools.

## Native readiness and authority

| Operation | Current phase authority |
| --- | --- |
| Local static/manifest/dependency checks and source/package audit | Executable within exact task scope |
| Complete feed audit, selection/parser replay and ephemeral loopback GET/HEAD | Executable locally; not native evidence |
| Start a persistent feed server, upload/host candidate site | Not authorized |
| Live Lab target discovery/status/install/navigation/launch/update/cleanup | No separately established target authority in this session; not executed |
| Production repository/Kodi mutation or publication | Unavailable and unauthorized |

Repository roles still have MCP disabled and unchanged grants. Current deployed
schemas and exact target grants must be discovered through a separately authorized
supported integration; checkout code/old receipts do not supply target authority.
No Lab credentials, grants, managed instances, services or infrastructure were read
or changed to manufacture readiness.

Native acceptance needs an exact disposable UUID/build/version/platform, approved
source/ZIP/feed digests, reachable trusted HTTPS destination and scoped server
permissions. Test repository installation/bootstrap discovery, correct lane/category,
required dependencies, unchanged-catalog refresh, normal higher-version update,
retained downloads, scoped launch/features and recoverable cleanup. Record native
observations independently for every claimed version; static/loopback successes
cannot replace them. For old-production-to-new updates, separately restore/install
approved published baseline bytes and records under explicit authority; this new
candidate ledger cannot invent old production acceptance or downgrade authority.

Canonical activation needs reviewed versioned templates/source, exact local bindings,
a recovery-tested configuration backup, actual-engine permission parity and approved
migration. Phase D owner decisions/publication additionally require authenticated
exact-artifact approval, retained rights/runtime/release decisions, frozen site and
asset digests, fresh remote heads/protection, short-lived scoped credentials, a
human publication gate, rollback evidence and separate publication authority. None
is installed or activated here; no unattended publication exists.

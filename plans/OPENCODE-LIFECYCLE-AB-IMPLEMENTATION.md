# OpenCode lifecycle Phases A/B implementation

Status: **PASS for isolated public-source intake and local candidate preparation**.
Base: `f2d8f3330d76a982d6f66601d8ec6ae2bc9c9c83`, 2026-10-23.
Implementation remains uncommitted in the isolated lifecycle worktree. No push,
publication, production activation, credential change, Lab operation or Phase C
tooling installation was performed.

## Implemented capabilities

The existing OpenCode tool names and manager/tester/reviewer roles now support an
operator-enrolled task referencing an owner-selected **public GitHub** repository.
Each task pins repository numeric/name identity, branch/tag/full commit resolution,
immutable commit/tree, archive/member hashes, selected runtime files, lanes and
target Kodi labels, production baseline, installation/toolchain/schema identities
and a 24-hour expiry. Roles cannot enroll or change authority themselves.

Acquisition uses anonymous fixed-origin GETs, checks every source file against the
pinned Git blob inventory and rejects traversal, linked/special files, truncation,
unapproved redirects, LFS/submodules and malformed tasks. Source/config/hooks are
inert data. Per-task source/artifact storage sits under existing denied raw-read/
edit rules; inspection is through bounded task tools. Closed state/journal checks,
locking, generation comparison, revocation and exact binding digests fail closed.

Preparation reuses the existing deterministic ZIP builder, runtime policy,
strict-v2 review-record contract and independent archive auditor. It produces a
candidate ZIP/sidecar, pending review record, candidate intake metadata, exact
local config/ledger proposal and candidate-only catalog fragments. Historical
inputs are copied unchanged and no proposal is applied. Same-version changed bytes,
already-published identical releases and non-increasing numeric versions reject.
Metadata selection matches actual retained identity/hash, not similar name prefixes.

The tester can reuse the existing Nexus Toolkit environment for static validation
of selected runtime bytes. Reviewer tools check original ZIP/source mapping,
metadata, recorded static-evidence hashes, stage outcomes and warnings. Real-source
Matrix/Omega/Piers validation is explicitly BLOCKED pending matching tooling;
rights/static/runtime/final review acceptances remain false. No native test runs.

Local installation derives checkout paths and renders existing permission rules
without adding tools or grants. Zero-argument operations retain the legacy fixture
path. Canonical ignored adapters/profiles are untouched. There is no production
profile argument, remote writer, publisher or new orchestration framework.

## Exact implementation files

Paths are relative to this isolated worktree. This table lists every implementation
source/documentation/test file, including this report; the prior design proposal
is retained unchanged as an input.

| File | Change |
| --- | --- |
| AGENTS.md | Point to authorized local A/B preparation instructions |
| docs/AGENT-INTEGRATION.md | Distinguish optional local A/B installation from canonical fixture-only profile |
| docs/LIFECYCLE-PREPARATION.md | Enrollment, schemas, tool use, security, activation and limitations |
| config/LIFECYCLE-TASK-SCHEMA.json | Closed public-source task request interchange schema |
| scripts/lifecycle.py | Operator setup/enrollment/revocation, bounded GET/source identity, isolated store, candidate preparation, static validation and frozen verification |
| scripts/lifecycle_adapter.py | Closed stdin JSON bridge with role/operation checks; no enrollment/publication surface |
| scripts/opencode/kodi.ts | Existing tool names with optional task-bound arguments and bounded credential-free subprocesses |
| scripts/opencode/fixture_adapter.py | Portable legacy fixture adapter; fixed GitHub list reads use anonymous GETs |
| scripts/opencode/profiles.json | Versioned templates preserving existing ordered permissions and delegation |
| tests/test_lifecycle.py | Forty-three focused intake, identity, isolation, packaging, metadata, state and authorization regressions |
| tests/test_lifecycle_permissions.py | Six template/permission-order preservation checks |
| tests/check_lifecycle_permissions.py | Actual OpenCode engine parity/canaries and complete legacy fixture workflow harness |
| plans/OPENCODE-LIFECYCLE-AB-IMPLEMENTATION.md | This implementation and verification record |

Ignored local outputs include generated opencode.json, .opencode role/tool/control
files, installation manifest and task data, plus reports/lifecycle-ab evidence.
No existing tracked production config, ledger, package or builder/auditor/approval
implementation was modified.

## Verification results

- **49 focused A/B tests passed**, covering public repository/ref/tag/commit
  resolution, two unrelated source namespaces and task workspaces, exact source/
  artifact identity, Git/archive mismatch, malformed tasks, expiry/revocation,
  symlink/traversal containment, frozen inventory/metadata/receipts, version
  progression, lane handling, no-credential GETs, permission templates and denied
  production/wrong-role operations. Real Python subprocess boundary included.
- **Final complete suite through actual OpenCode fixture validation: 154 run,
  151 passed, 3 skipped** in the unchanged Toolkit environment. The three optional
  jsonschema interchange tests were then run with the already-installed system
  jsonschema 4.10.3: **all 3 passed**, plus six task-schema checks. No dependency was
  installed or Toolkit environment changed.
- **Actual OpenCode permission verification passed:** manager/tester/reviewer
  resolved rules and frontmatter match canonical after root rebinding; all **21
  canaries** match baseline without executing the checked operations. Only the
  engine's nondeterministic ordering of commuting generated skill allows is
  normalized; configured/deny ordering is preserved. No model inference or service
  was needed. Malformed, missing-digest, unknown-task and disabled-role calls were
  also exercised through the actual tool boundary.
- **Legacy fixture workflow passed:** both fixtures' six Nexus static stages,
  fixture build, whole-site repeatability, frozen review, **26 loopback paths**,
  **17 lane-selection cases** and retained fixture versions. Warnings retained:
  unverified example.org URL, advised Nexus Python dependency floor, and expected
  duplicate-ZIP warning from a hostile-archive regression.
- **Live public GET/intake/tool cycle passed:** existing Toolkit source repository
  ID `1418207072`, commit `552b0b949220f2d545ab42a7f27d1826a535c686`, tree
  `6f59572e6fcd6e123e9f7011ce6b388fea41fdaa`. Manager acquired and prepared the
  existing MIT sample using task arguments through OpenCode; tester completed
  Nexus static checks, Omega returned BLOCKED, reviewer checked frozen bytes and
  original tester receipts. ZIP SHA-256:
  `d5bb647070259a2033e28024c728741d7a1b41f6dc23a83d9c47736c03a0a695`.
  This exercises live intake using an existing sample, **not** release admission
  or native compatibility of a newly selected independent add-on.
- Distribution repository main resolution also passed anonymously, at the
  existing remote commit `d6e1359a6668e688891359869ef2c7d34bc2ddff`.
- Independent source review **PASS**, with eight focused reviewer reruns and
  twelve source/docs/test file hashes frozen. All material findings were fixed
  before the final full gate. No reviewed source delta followed that freeze.
- Source/credential-pattern scan passed and document/code whitespace checks
  passed. All **24 canonical audited file hashes** remain unchanged; canonical
  main is clean and still one local documentation commit ahead. Shared Toolkit
  remains clean at its original pin. Remote main and gh-pages remain unchanged.

## Evidence

These ignored files are local evidence, not public artifacts or approvals:

| Evidence | Contents |
| --- | --- |
| reports/lifecycle-ab/final-permissions-and-fixtures.json | Actual resolved engine permissions, canaries and fixture tool results |
| reports/lifecycle-ab/final-fixture-summary.json | Full-suite counts/skips, stages/warnings, fixture hashes and preservation |
| reports/lifecycle-ab/schema-supplement.json | Three previously skipped schema tests passed in existing system environment |
| reports/lifecycle-ab/live-intake-task.json | Frozen sample task/source/installation binding |
| reports/lifecycle-ab/live-intake-acquisition.json | Live source archive/member identity and manifest discovery |
| reports/lifecycle-ab/live-tool-cycle.json | Actual task-bound manager/tester/reviewer outputs |
| reports/lifecycle-ab/*-engine.json | Raw actual OpenCode tool receipts for that cycle |
| reports/lifecycle-ab/schema-negatives.json | Actual tool-boundary malformed/unauthorized calls |
| reports/lifecycle-ab/REVIEWER.md | Independent review and frozen file hashes |
| reports/lifecycle-ab/final-verification.json | Final reviewed-byte, evidence, source-scan and preservation checks |

Independent review SHA-256:
`334bfde6f92b309bc34db98346b2045013f4d3308a693bf4c1cc5750fb7ca78c`.
Final permission/fixture receipt SHA-256:
`0720129f4e3e7ae12830bcbc9e22a4fb3f27406f3099712387ab4d6039553323`.

## Remaining limits and Phase C prerequisites

Full installable candidate-feed construction remains unavailable: the existing
historical-package restoration and preview-installer retention checks are
preserved. Catalog fragments and config/ledger proposals are local review data;
they must not be deployed or represented as full feed qualification. Applying
lane changes requires real successor review records and retained artifacts.

This phase uses anonymous public access only. Private credentials, arbitrary source
build/test execution, LFS/submodules/export-ignore support, broader version
comparison, module/native/skin dependencies and external dependency snapshots are
not silently enabled. Toolkit pins include actual Toolkit source/interpreter plus
distribution version/RECORD metadata, not a whole-environment integrity proof.
Role/task containment does not claim an adversarial same-user OS sandbox.

Phase C requires separate review/approval for matching Matrix/Omega/Piers tooling,
embedded-Python/API/stub evidence, additional dependency/extension/version handling,
and each native scenario/target. No such environment was installed and no native
compatibility is claimed for Matrix 19.5, Nexus 20.5, Omega 21.3 or Piers 22.

The integration verification uses supported debug tools without model inference.
Natural-language unattended orchestration and a new independent add-on plus its
successor still need the later operational pilot. Task enrollment remains an
explicit owner-authorized operator action, not model self-enrollment.

Separate approval remains necessary for canonical installation/migration, pushing
the existing documentation commit or this implementation, a concrete new add-on
pilot, full-feed staging, private credentials/execution expansion, Phase C/native
work, and every GitHub write or publication. No such operation is pending for
automatic execution after this report.

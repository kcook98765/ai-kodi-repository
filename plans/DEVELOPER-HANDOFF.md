# Developer Handoff

**Role:** Developer handoff (local fixture foundation only).
**Repository:** `kcook98765/ai-kodi-repository` — addon_id `repository.ai.kodi`, version `0.1.0`.
**Base URL:** `https://kcook98765.github.io/ai-kodi-repository/`.
**Distribution state:** Production add-on intake is empty; only the repository
installer is eligible for the initial infrastructure publication.

This document defines the source-package and evidence contracts, the proposed
Tastemade/Aura task gates, and the task-card fields for future user review. It is a
handoff, not a release plan and not a publication authorization.

## 1. Authority and roles

The **`kodi-repo-manager` is primary for repository management and distribution.**
This handoff is a developer-role document: it defines contracts and gates only. It
does not grant publication authority, does not modify source/config/adapters, and
does not run or delegate tests.

- **Manager (primary):** builds local candidates, verifies catalogs/sidecars/dependencies,
  compares whole-site repeat builds, checks historical retention, and prepares the release
  plan containing exact package/feed hashes and intended actions. Writes only
  `plans/MANAGER-READINESS.md`.
- **Tester:** supplies version/platform-specific static and native acceptance, warnings and
  limitations. Writes only its `reports/` agent document.
- **Release reviewer:** independently inspects frozen bytes, dependency closure, rights and
  evidence. Writes only its `reports/` agent document.
- **Operator:** verifies and copies only approved ZIP/evidence into `incoming/`; controls
  configuration, adapters and machine evidence.
- **User:** the only authority that can approve publication; approval must bind the concrete
  result.

Test success supplies no publication authority. Model conclusions and `release_approved`
fields are not authority to publish.

## 2. Source-package contract

What an independently developed add-on repository must supply for approved release intake
(`docs/RELEASE-WORKFLOW.md`, step 1):

1. **Source identity** — `source_repository` (owner/name), `ref`, and `source_commit` (pinned SHA).
2. **Clean-state disposition** — how the tree was frozen (clean checkout, no local
   modifications, no uncommitted files).
3. **License notices** — license text and attribution; redistribution/rights disposition.
4. **Runtime-file allowlist** — explicit relative-path allowlist of files that belong in the
   installer; rejects extra development files, linked paths, traversal, duplicate/encrypted/
   oversized ZIPs, and XML entity declarations.
5. **Deterministic ZIP** — sorted entries, one manifest-ID root, normalized regular-file
   modes, 1980 timestamps, fixed deflate settings.
6. **Hashes** — source SHA-256, per-file SHA-256, and ZIP SHA-256.

## 3. Evidence contract

What must accompany the package (`docs/RELEASE-WORKFLOW.md`, steps 2–3):

- **Static acceptance** — version/platform-specific static validation per lane.
- **Native/runtime acceptance** — native Kodi installation/update behavior on separately
  authorized disposable targets.
- **Warnings and limitations** — retained, not suppressed.
- **Frozen-bytes inspection** — independent review of the exact bytes.
- **Dependency closure** — required dependencies resolve within the lane plus explicit
  built-in API floors; optional misses remain warnings; cycles fail. External
  official/third-party dependency snapshot admission is deliberately unavailable until a
  reviewed snapshot adapter exists.
- **Rights** — redistribution rights approval.
- **Human-reviewed evidence** — booleans do not authenticate its claims.

## 4. Review-record schema

Each admitted package's review record must contain:

- `package_sha256`
- `runtime_files` (relative path → SHA-256)
- `source_repository`
- `source_commit`
- `release_approved`
- `rights_approved`
- `fixture_only=false`
- compatibility entries, each with `static_accepted`, `runtime_accepted`, and evidence references

`config/production.json` lists, per package: `zip`, `sha256`, `review_record`,
`review_record_sha256`, and selected lanes.

## 5. Lanes

| Lane | Major | `xbmc.addon` range (inclusive) | Built-ins |
| --- | --- | --- | --- |
| Matrix | 19 | 19.0.0 .. 19.9.999 | `xbmc.addon` 19.0.0, `xbmc.python` 3.0.0 |
| Nexus | 20 | 20.0.0 .. 20.9.999 | `xbmc.addon` 20.0.0, `xbmc.python` 3.0.1 |
| Omega | 21 | 21.0.0 .. 21.9.999 | `xbmc.addon` 21.0.0, `xbmc.python` 3.0.1 |
| Piers | 22 | 21.90.0 .. 22.9.999 | `xbmc.addon` 21.90.0, `xbmc.python` 3.1.0 |

Directory selection is not a dependency solver or evidence of runtime compatibility. The
current numeric version comparator accepts only `x.y.z` and fails closed on Kodi
suffixes/epochs.

## 6. Tastemade / Aura outstanding gates

Both add-ons are currently **unreleased with no approved distribution inputs**
(`production_intake.packages=[]`; note: "Tastemade and Aura have no approved distribution
inputs"). Unreleased Tastemade and Aura inspection packages remain inadmissible. Each gate
below must be independently evidenced before admission; none may be inferred from the other
add-on or from fixture results.

### Tastemade — `kcook98765/plugin.video.tastemade`

1. Source freeze: pinned `source_commit` in the independent repository.
2. Clean-state disposition.
3. License/rights notices and `rights_approved`.
4. Runtime-file allowlist.
5. Deterministic ZIP + source/file/ZIP SHA-256.
6. Per-lane static acceptance (Matrix/Nexus/Omega/Piers as applicable to the manifest).
7. Per-lane native/runtime acceptance on authorized disposable targets.
8. Dependency closure within lane + built-in API floors.
9. Complete review record with `fixture_only=false`.
10. `release_approved` by the independent reviewer against the plan and input hashes.

### Aura — `kcook98765/skin.aura`

1. Source freeze: pinned `source_commit`.
2. Clean-state disposition.
3. License/rights notices and `rights_approved`.
4. Runtime-file allowlist.
5. Deterministic ZIP + source/file/ZIP SHA-256.
6. Per-lane static acceptance.
7. Per-lane native/runtime acceptance.
8. Dependency closure within lane + built-in API floors.
9. Complete review record with `fixture_only=false`.
10. `release_approved` by the independent reviewer.

Note: a skin's runtime behavior and dependency profile differ from a video add-on; per-lane
acceptance must be evidenced for the skin's actual manifest and entry points, not inferred
from Tastemade.

## 7. Task-card fields for future user review

Per `docs/MONITORING.md`, each proposed developer task card contains:

- **Source repository and pinned revision**
- **Issue/PR URL and number**
- **Observed/expected behavior with evidence**
- **Affected Kodi versions/platforms**
- **Proposed scope and owner**
- **Constraints**
- **Test/acceptance criteria**
- **Runtime authority needed**
- **User decision**

The manager prepares a local card. The user approves before the developer primary receives
source-change authority. The developer may delegate bounded testing/review but never infers
publication scope.

## 8. Boundaries of this handoff

- No sibling source projects read or modified.
- No tests run or delegated.
- No source/config/adapter edits.
- No Kodi/remote/publication calls.
- No packages created.
- This document is a handoff, not a release plan or publication authorization.

## 9. Reference paths (from `kodi_inspect`)

- `docs/ARCHITECTURE.md`
- `docs/RELEASE-WORKFLOW.md`
- `docs/MONITORING.md`
- `docs/SOURCES.md`
- `scripts/repository.py`
- `scripts/qualify.py`
- `tests/test_repository.py`
- `README.md`, `AGENTS.md`

# Identity and layout

This document is the authoritative distribution architecture. Existing OpenCode
roles enter through [the standing workflow contract](AGENT-INTEGRATION.md),
which references this architecture and the release/approval procedures rather
than defining a separate repository policy.

The public GitHub identity is `kcook98765/ai-kodi-repository`, explicitly
selected by the owner. `repository.ai.kodi` follows Kodi's `repository.*` type prefix,
lowercase dotted ID and manifest/folder equality conventions. This is a local
identity choice, not a globally reserved ID or official Kodi endorsement.

Each add-on keeps its independent development repository. This distribution
repository owns reviewed release ZIPs, catalogs, artwork, retention records and
update metadata. Ordinary add-ons require valid manifest IDs, declared extension
points, dependencies and versions; Kodi derives their normal categories from
those declarations (for example, a video plugin declares provides=video).
Repository installation, dependency resolution and updates remain native Kodi
operations. No custom installer or bootstrap add-on catalog replaces them.

```
config/             repository identity, explicit lane ranges, reviewed production intake
packages/           repository installer runtime assets only
fixtures/           two MIT Toolkit-derived disposable versions
scripts/            offline deterministic build, inspection, URL qualification
tests/              hostile-package and release-boundary failure controls
incoming/           ignored reviewed ZIP/evidence intake, never auto-discovered
releases/           retained-version hash ledger
plans/              manager readiness and developer handoff
docs/               architecture, approval, monitoring and source references
.opencode/          ignored local role profiles and scoped adapters
dist/fixture/       ignored local qualification feed, artifacts, checksums and plan
dist/production/    ignored reviewed production site and release plan
reports/            ignored machine evidence and independent agent reports
```

# Kodi catalogs

A single installer has four `xbmc.addon.repository/dir` blocks. Each block has
`info`, `checksum verify="sha256"`, `datadir`, `artdir`, `hashes=sha256`.
Catalogs contain ordinary manifests in an `<addons>` root, including the
repository installer for future updates. No invented per-add-on download URL
or checksum element is used. `addons.xml.sha256` contains the plain hexadecimal
SHA-256 of exact uncompressed XML bytes and is both the refresh marker and the
verified index digest. Each ZIP has a `.zip.sha256` sidecar; Kodi's hash resolver
can fall back to that when static hosting omits a Content-SHA256 header.

| Lane | Directory selector (`xbmc.addon` API, inclusive) | Disposable version |
| --- | --- | --- |
| Matrix 19 | 19.0.0 .. 19.9.999 | script.toolkit.sample 1.0.0 |
| Nexus 20 | 20.0.0 .. 20.9.999 | script.toolkit.sample 1.0.0 |
| Omega 21 | 21.0.0 .. 21.9.999 | script.toolkit.sample 1.1.0 |
| Piers 22 | 21.90.0 .. 22.9.999 | script.toolkit.sample 1.1.0 |

Piers RC1 currently uses API 21.90.901. Nexus/Omega development APIs 19.90.x and
20.90.x are intentionally excluded. Future Kodi 23 is excluded. Directory
selection is not a dependency solver or evidence of add-on runtime compatibility.
The two fixture versions are both statically checked in the existing qualified
Nexus lane; no Matrix/Omega/Piers Python stub qualification is claimed.

Production manifests require reviewed per-lane static/runtime acceptance records,
source commit and repository, redistribution rights and exact ZIP/runtime hashes.
The versioned [approval contract](APPROVAL-CONTRACT.md) preserves that strict
policy for legacy/v1 and v2. Version 2 adds attributable rights, owner acknowledgment, technical and
final release decisions, explicit runtime deferrals and unresolved risk reports.
Acknowledgment never supplies rights; deferred testing never supplies acceptance.
Every unresolved v2 risk blocks production. Explicit schema 3 adds only a
reviewed independently developed unofficial-integration distribution route, with
broad rights pending, retained accepted terms findings, separate service review
and owner distribution decision, bound public disclosures and unchanged runtime
and nonwaivable package-rights gates. An explicit, attributable, expiring owner-risk
decision may replace only the repository's provider-authorization gate, binding
provider, inspected add-on ID/version and frozen ZIP hash while reporting
authorization unverified. It supplies no legal clearance. No current approvals are migrated. Legacy records retain their original
boolean meaning and report their attribution/evidence limitations explicitly.
The separate schema 3 `unofficial-integration-initial-release-v1` route admits
only named, expiring, owner-accepted initial-release coverage limitations after
independent verification. Runtime acceptance stays false/deferred. Both consumers
check artifact/source/lane scope, first-release history, individual observations,
independent verification, provider safeguards and separate final owner approval.
Plans/audits and independently reconstructed public notices preserve limitations
and scoped supplemental outcomes. Failed tests, security defects and substantive
rights defects remain ineligible. The original schema 3 route remains unchanged.
The current numeric version comparator accepts only x.y.z and fails closed on
Kodi suffixes/epochs. Extending it requires Kodi-equivalent comparison tests.
Required dependencies resolve within that lane plus explicit built-in API floors.
Optional misses remain warnings; cycles fail. External official/third-party
dependency snapshot admission is deliberately unavailable until a reviewed
snapshot adapter exists. Thus future real releases may be blocked even when Kodi
could resolve their dependencies. Do not weaken the gate to admit them.
The current built-in table is deliberately minimal (repository/Python APIs).
Aura's GUI API and external provider/helper dependencies need separately reviewed
lane data before admission. File-based `library` declarations are checked now;
directory-based module libraries need extension-specific validation before use.

The independent auditor derives packages and lane membership from hashed review
records and the retention ledger, then compares the complete generated ZIP,
catalog, artwork and release-mirror inventory. It does not import builder code or
use the plan itself as proof of approval. Both consumers apply the shared
versioned approval contract to separately loaded hashed records, and the auditor
independently enforces production gates
and compares the plan's approval report with those records. Ordinary add-ons use
this same path; there is no fixture/installer-only type allowlist. Skin archives
can be inspected structurally, but production skin admission still needs reviewed GUI
API/provider dependency data and lane/runtime evidence. This change adds no such
data and does not qualify Aura.

Private candidate qualification uses ignored `config/candidate.json`, the same
ZIP/hash/source/runtime allowlist schema and `--profile candidate`. It permits
explicit false rights/release/static/runtime decisions, retains those blockers
in the plan and independent audit, and writes only `dist/candidate/` with
`candidate/` URL prefixes. Production preflight rejects candidate plans. Candidate
catalog membership is a proposed test lane, not compatibility acceptance. Use a
separate disposable copy of this repository for real candidate inputs; never
promote candidate output or change production inputs to simulate approval.

# Hosting arrangement

Phase C adds an explicit **local candidate-only context** to the task-bound adapter;
see [lifecycle preparation](LIFECYCLE-PREPARATION.md). A dedicated candidate config
selects a distinct repository.ai.kodi.candidate.<task-id> installer and HTTPS origin,
with a separate identity-bound candidate ledger. Original production config,
installer source and production ledger remain immutable baseline evidence. Existing
production/default fixture identity checks and the old candidate-retention failure
remain unchanged without that explicit context. The independent auditor validates
the context separately and reconstructs the complete site from frozen reviewed
inputs. This context accepts pending strict-v2 records only, cannot activate
first-release exceptions using an empty test history, and cannot pass publication
preflight. No hosting, native operation or production approval is granted.

Use GitHub Pages at `https://kcook98765.github.io/ai-kodi-repository/` for
`catalogs/<lane>/addons.xml[.sha256]`, `packages/<id>/<id>-<version>.zip[.sha256]`
and `artwork/<lane>/<id>/<asset>`. Deploy a generated static artifact with
`.nojekyll`. Stable paths make Kodi's datadir concatenation and artwork resolution
work; nested directories need no listing. The root index is a Kodi HTTPDirectory-
compatible bootstrap containing one filename-matching link to the current
installer. Root copies of every retained installer ZIP and sidecar are immutable,
byte-identical mirrors of the canonical nested packages. The configured installer
version selects the link automatically. Ordinary add-ons remain catalog-only
installation choices; required public disclosures stay on the root page.
Generation, independent inventory/page reconstruction, publication preflight and
source-matched parser qualification all cover this bootstrap contract.

Retain identical reviewed ZIPs and SHA256SUMS as GitHub Release assets. A pinned
asset URL is `https://github.com/kcook98765/ai-kodi-repository/releases/download/<tag>/<id>-<version>.zip`;
the release page and GitHub blob/source browsing return HTML. GitHub source
archives include development files and are not Kodi installers. `latest/download`
is a mutable alias; tag-pinned downloads are preferable, with immutable releases
or policy preventing replacement. Release asset paths are flat below a tag, while
Kodi constructs `<datadir>/<id>/<id>-<version>.zip`. Therefore Releases alone
do not satisfy this layout. Do not rely on HTML or JavaScript redirects; a future
server-side redirect/CDN mapping requires separate HTTP/HTTPS qualification.
GitHub documents direct streaming or HTTP 302 for binary asset API downloads;
store the stable published browser-download URL, not a resolved redirect target.
Every metadata/artwork/package URL in the installer is absolute HTTPS, avoiding
dependence on browser-relative navigation or the Release page URL.

Pages mirrors ZIP bytes for straightforward initial operation. This duplicates
storage. Monitor Pages site size, build/deploy limits and bandwidth; larger
catalogs may need a stable HTTPS object store/CDN preserving the same path layout.
The initial infrastructure promotion uses a generated `gh-pages` branch and
repository-only catalogs. See HOSTING.md for layout and verification commands.
Native Kodi behavior still needs a separately authorized acceptance phase.

Retain every published package in production intake and the version/hash ledger,
even if its lane list becomes empty. Catalogs expose one selected current version
per ID/lane, while old downloads remain available. The builder never deletes old
outputs and rejects changed bytes at an existing package path. Ledger entries
prevent removal or replacement of retained historical inputs. Clean restoration
must reacquire all ledger packages from approved pinned Releases and verify them
before building. Installer updates follow the same version/byte policy. The
current generated installer is included before its ledger hash is checked;
historical installer versions enter as reviewed packages with no current lanes.
The ledger remains operator-maintained; these tools do not add entries for you.

# Reproducibility and security

ZIPs have sorted entries, one manifest-ID root, normalized regular-file modes,
1980 timestamps and fixed deflate settings. Record Python/zlib/Toolkit versions;
repeatability is qualified in this environment, not promised across arbitrary
compressor versions. Input hashes and review records are independent of generated
feed markers. Explicit runtime allowlists reject extra development files, linked
paths, traversal, duplicate/encrypted/oversized ZIPs and XML entity declarations.
No add-on Python code is imported or executed. Reviewed input metadata is trusted
operator evidence; local role tools do not provide an adversarial OS sandbox or
cryptographic proof of a human signature. HTTPS and checksums do not establish
publisher identity independently of the hosting account.

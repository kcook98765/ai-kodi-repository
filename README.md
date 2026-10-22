# AI Kodi Repository

Version-aware distribution infrastructure for independently developed Kodi
add-ons. Repository installer: **`repository.ai.kodi` 0.1.0**.

The initial catalogs contain only the repository installer. Tastemade, Aura and
the disposable test add-ons are not distributed. Native Kodi installation and
update acceptance remains a separate validation phase.

[Download the repository installer](https://kcook98765.github.io/ai-kodi-repository/packages/repository.ai.kodi/repository.ai.kodi-0.1.0.zip)
and its [SHA-256 checksum](https://kcook98765.github.io/ai-kodi-repository/packages/repository.ai.kodi/repository.ai.kodi-0.1.0.zip.sha256).
Use Kodi's **Install from zip file** with that ZIP. GitHub's source archives are
development source, not installable repository packages.

The installer selects Matrix 19, Nexus 20, Omega 21 or Piers 22 catalogs by the
`xbmc.addon` API version. Pages serves stable metadata, artwork and nested package
paths over HTTPS. Reviewed ZIPs can also be retained as tag-pinned GitHub Release
assets. Source browsing and Release HTML pages are not repository feeds.

Build and verify the production infrastructure with Python 3.12 (standard library
only; qualified with Python 3.12.3 and zlib 1.3):

```sh
python3 -B -m unittest discover -s tests -v
python3 -B scripts/repository.py build --profile production
python3 -B scripts/repository.py verify --profile production
python3 -B scripts/audit_candidate.py --profile production
python3 -B scripts/check_publication.py
```

Output: `dist/production/site/`, `dist/production/release-assets/`,
`SHA256SUMS` and a hash-bound dry-run `release-plan.json`. These commands cannot
publish. Only an explicitly approved operator promotes the verified production
site to `gh-pages`. Fixture qualification additionally requires the original
Kodi Agent Toolkit and matching static-validation evidence; see
[agent integration](docs/AGENT-INTEGRATION.md). Never deploy `dist/fixture/`.

See [architecture](docs/ARCHITECTURE.md), [release workflow](docs/RELEASE-WORKFLOW.md),
[approval contract and migration](docs/APPROVAL-CONTRACT.md),
[monitoring design](docs/MONITORING.md), [source references](docs/SOURCES.md), and
[contributing](CONTRIBUTING.md), [hosting](docs/HOSTING.md), and
[native agent readiness](plans/MANAGER-READINESS.md).

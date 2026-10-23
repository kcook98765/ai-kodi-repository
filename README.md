# AI Kodi Repository

Version-aware distribution infrastructure for independently developed Kodi
add-ons. Repository installer: **`repository.ai.kodi` 0.1.0**.

Install entirely inside Kodi, using this HTTPS File manager source:

```text
https://kcook98765.github.io/ai-kodi-repository/
```

1. Open **Settings → File manager → Add source**, enter the URL, and name it **AI Kodi**.
2. Open **Settings → Add-ons → Install from zip file**. If prompted, enable
   **Unknown sources** under System → Add-ons and acknowledge Kodi's warning.
3. Select **AI Kodi**, then **repository.ai.kodi-0.1.0.zip** (or the current
   approved installer shown there).
4. After the installed notification, open **Install from repository → AI Kodi Repository**.
5. Browse the normal Kodi categories and install the desired compatible add-on.
   On Omega, **Video add-ons → Tastemade 0.1.0** is published. Other current lanes
   contain the repository installer only; Aura and disposable fixtures are not published.

The root ZIP is a byte-identical copy of the canonical installer, with a
SHA-256 sidecar. Ordinary add-ons are installed through **Install from repository**;
the bootstrap page does not offer their ZIPs. Kodi resolves required dependencies
and checks for updates according to its normal settings. Tastemade requires Kodi's
Python API; InputStream Adaptive is optional and not an installation prerequisite.
No browser, SMB share or ZIP transfer is required. Unknown sources is a standard
Kodi requirement; a bootstrap sidecar is not automatically verified by manual ZIP
installation. Repository-driven downloads retain the configured SHA-256 checks.

The bootstrap is published. Core repository installation and Tastemade discovery
and installation are accepted on **Kodi 21.2 Omega**, based on the owner's manual
native PASS report. Native updates and native acceptance on other Kodi versions
remain pending. The owner reports a Tastemade launch error, deferred to separate
add-on debugging; its cause is unresolved and is not attributed to Kodi 21.2. See the
[acceptance record and remaining tests](docs/NATIVE-ACCEPTANCE.md).

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
[approval contract and migration](docs/APPROVAL-CONTRACT.md) (strict v1/v2 and
explicit v3 unofficial-integration review with an expiring, exact-artifact owner-risk
provider-authorization exception; no automatic approvals or legal clearance),
and the separate initial-release runtime-coverage route (unobserved/unavailable
limitations, expiring owner acceptance, independent verification and final owner approval),
[monitoring design](docs/MONITORING.md), [source references](docs/SOURCES.md), and
[contributing](CONTRIBUTING.md), [hosting](docs/HOSTING.md), and
[native agent readiness](plans/MANAGER-READINESS.md).

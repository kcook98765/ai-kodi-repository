# Public hosting

Source: `https://github.com/kcook98765/ai-kodi-repository`, default branch `main`.
Static site: `https://kcook98765.github.io/ai-kodi-repository/`, generated
`gh-pages` branch, root directory, `.nojekyll`, HTTPS enforced. Branch publication
uses GitHub's Pages build. There is no repository-owned automatic publisher.
Only reviewed production output belongs on that branch.

```
index.html                         # current installer link only
repository.ai.kodi-0.1.0.zip[.sha256] # byte-identical bootstrap copy
.nojekyll
catalogs/{matrix,nexus,omega,piers}/addons.xml[.sha256]
packages/repository.ai.kodi/repository.ai.kodi-0.1.0.zip[.sha256]
packages/plugin.video.tastemade/plugin.video.tastemade-0.1.0.zip[.sha256]
artwork/{matrix,nexus,omega,piers}/repository.ai.kodi/resources/icon.png
artwork/omega/plugin.video.tastemade/resources/{icon.png,fanart.jpg}
```

The root index is the permanent Kodi File manager bootstrap source. Its single
installer anchor uses a relative filename with exactly matching text:

```html
<a href="repository.ai.kodi-0.1.0.zip">repository.ai.kodi-0.1.0.zip</a><br>
```

Keep anchors attribute-free for Matrix, with double quotes and trailing markup.
Kodi parses the response as a directory listing; browser visibility alone proves
nothing. The full root HTML retains required package disclosures but offers no
ordinary add-on ZIP downloads. No JavaScript, authentication or server autoindex
is needed. See README for the native installation steps and NATIVE-ACCEPTANCE.md
for the source-derived parser checks and remaining native tests.

The builder derives the current installer link from repository configuration.
For every retained installer version it copies the canonical ZIP and SHA-256
sidecar to the site root; it never repackages the bootstrap copy. Existing root
copies are immutable and retained. After a future installer version is reviewed,
update the normal installer source/config and retain its predecessors under the
existing release contract; the index selects the configured version automatically.
No hand-maintained ZIP list or mutable unversioned ZIP alias is used.

Kodi constructs package paths below `datadir` and reads `.zip.sha256` when the
host has no Content-SHA256 header. Nested package directories need no listing:
repository installation and updates use catalogs, not HTML discovery. The four
catalogs remain version-separated; Tastemade 0.1.0 is Omega-only. Root discovery
always offers the repository installer, never a cross-version list of add-ons.
Publishing an installer does not imply native Kodi acceptance.

Release assets are flat under a pinned tag and can redirect to GitHub's asset
storage. They are useful for direct downloads and recovery, but do not replace
the nested Pages feed. Never use a Release HTML page, GitHub blob URL or mutable
`latest/download` alias as a repository catalog. Only the infrastructure installer
is eligible for an initial `repository-0.1.0` release; real add-ons need separate
approval and evidence.

Before promotion, build twice, verify, independently audit and scan the frozen
source and site. Review the exact commit, site manifest and asset hashes. Copy
only `release-plan.json`'s `site_files` into a separate `gh-pages` checkout;
verify every digest and reject extra files. Never copy the whole `dist/` tree.
Push `main` and the approved static branch without force. Configure Pages only
for that branch and root. Record source and hosting commit IDs outside the feed.
Download-check immutable Release assets before catalog promotion when distributing
real packages. Recheck all public HTTPS GET/HEAD responses, XML/ZIP bytes, hash
sidecars and version selection after deployment. `check_publication.py --https`
checks the complete reviewed site, bootstrap copies, index MIME/discovery, catalogs
and packages; it never publishes.

Pages build/deployment is coherent but caches can briefly expose earlier bytes.
Retain and verify ZIPs first, promote matching metadata as one site, and stop on
mixed hashes. Do not replace or delete old package versions. Retain a verified
site snapshot, Release assets and ledger for restoration. A catalog rollback
does not downgrade installed add-ons. Larger catalogs may require object storage
or a CDN preserving these stable paths and the same verification contract.

The source branch, Pages configuration and Release uploads require existing
GitHub permissions. A denied operation stops at that gate; do not broaden
credentials or substitute a different host without approval.

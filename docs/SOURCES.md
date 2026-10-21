# Reviewed primary documentation

Reviewed 2026-10-21. Live branch versions are dated observations; source snapshots
and SHA-256 are retained privately beside this phase's preservation evidence.

- [Official Kodi repository format](https://kodi.wiki/view/Add-on_repositories):
  directory/catalog/installer contract and version bounds (retrieved through search
  cache after direct wiki access returned 503).
- [Official manifest requirements](https://kodi.wiki/view/Addon.xml) and
  [type/ID structure](https://kodi.wiki/view/Add-on_structure).
- [Kodi Matrix repository implementation](https://github.com/xbmc/xbmc/blob/Matrix/xbmc/addons/Repository.cpp)
  and [Omega implementation](https://github.com/xbmc/xbmc/blob/Omega/xbmc/addons/Repository.cpp):
  xbmc.addon version selection, checksum verify and ZIP hash-sidecar fallback.
- [Kodi Piers version API](https://github.com/xbmc/xbmc/blob/Piers/version.txt):
  current RC1 ADDON_API 21.90.901. Stable Matrix branch ADDON_API is 19.1.0,
  Nexus 20.5.0, Omega 21.3.0. All are covered by the respective bounds.
- [GitHub Pages](https://docs.github.com/en/pages/getting-started-with-github-pages/what-is-github-pages)
  and [Pages limits](https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits).
- [Direct Release links](https://docs.github.com/en/repositories/releasing-projects-on-github/linking-to-releases).
- [Release asset binary and redirect behavior](https://docs.github.com/en/rest/releases/assets#get-a-release-asset).
- [OpenCode agents](https://opencode.ai/docs/agents/),
  [permissions](https://opencode.ai/docs/permissions/),
  [custom tools](https://opencode.ai/docs/custom-tools/).
- Local original Kodi Agent Toolkit README, docs/validation.md,
  docs/github-publication.md, docs/limitations.md and original compatibility and
  validation skills at Toolkit commit 552b0b949220f2d545ab42a7f27d1826a535c686.
- Historical FOUR-AGENT-SETUP.md, TASTEMADE-ONBOARDING.md and AURA-ONBOARDING.md
  were reviewed and are preserved unchanged.

Reusable functionality: original Toolkit discovery/source snapshots, six-stage
Nexus validation, official checker offline replay, report building; the existing
role profiles, native task delegation, permission canaries, GitHub GET integration,
and sorted/normalized allowlist ZIP packaging. Repository-specific catalog and
URL tooling is new glue; it does not replace Toolkit add-on validation.

The fixture LICENSE.txt remains the Toolkit's original MIT notice. The repository
installer's temporary tiny icon is the Toolkit MIT fixture icon with attribution
here; the initial infrastructure installer retains that MIT icon unchanged.
- [Creating a Pages site](https://docs.github.com/en/pages/getting-started-with-github-pages/creating-a-github-pages-site)
  and [Pages configuration API](https://docs.github.com/en/rest/pages/pages):
  generated branch/root source and HTTPS enforcement.

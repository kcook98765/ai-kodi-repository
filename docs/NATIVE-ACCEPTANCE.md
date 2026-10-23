# Bootstrap verification and native acceptance

The permanent source is `https://kcook98765.github.io/ai-kodi-repository/`.
Users add it in File manager as AI Kodi, install the repository ZIP from that
source, then install compatible add-ons through Install from repository.
Read README.md for the complete instructions and Kodi's Unknown sources step.
No new server, custom installer or external browser is needed.

## What local checks establish

`qualify.py` replays the HTTPDirectory anchor regex and label/link equality for
the generated ASCII filenames. It uses case-insensitive DOTALL matching,
double-quoted links and trailing content. Matrix's attribute-free anchor syntax
is the common supported subset. The configured current installer must be the
only discovered entry in every replay. Qualification verifies copy bytes,
sidecars, GET/HEAD for the bare source URL as well as index/artifact paths, and
HTML MIME on ephemeral loopback HTTP. It does not
run Kodi, prove public HTTPS delivery, or replace native acceptance.

Primary implementation references:

- [Matrix 19.5 HTTPDirectory](https://github.com/xbmc/xbmc/blob/f8fdeb6b1b1a7b753e1559d34a98cea62b4920d9/xbmc/filesystem/HTTPDirectory.cpp)
- [Nexus 20.5 HTTPDirectory](https://github.com/xbmc/xbmc/blob/4b95737efaddf7c869736e539318f18433413ff1/xbmc/filesystem/HTTPDirectory.cpp)
- [Omega 21.3 HTTPDirectory](https://github.com/xbmc/xbmc/blob/a3a448d26b8d560a65655dab2cd122994dc4e146/xbmc/filesystem/HTTPDirectory.cpp)
- [Omega regex options](https://github.com/xbmc/xbmc/blob/a3a448d26b8d560a65655dab2cd122994dc4e146/xbmc/utils/RegExp.cpp)
- [Inspected Piers branch snapshot](https://github.com/xbmc/xbmc/blob/f2a4ce5e517ff5b45fa11ffe1322bdb0e62df457/xbmc/filesystem/HTTPDirectory.cpp)
- [Kodi repository behavior](https://kodi.wiki/view/Add-on_repositories)

This replay covers our generated subset, not arbitrary HTML/Unicode, Kodi's
complete URL normalization, platform networking, or its GUI. The Piers runtime
build must be pinned independently; a branch snapshot is not device acceptance.

## Separately authorized Kodi Lab session

Do not start or modify managed instances under local implementation authority.
Bind each future session to an exact disposable target, runtime build and clean
profile, with supported snapshot/recovery and the necessary existing grants.
Use a distinct fixture repository identity for staged update tests; never replace
the production repository with a fixture under its real ID.

1. On fresh Omega 21.3, enter the documented HTTPS URL using native File manager.
   Save as AI Kodi, reopen, and browse it. Record the warning/Unknown sources
   flow and the visible installer filename. No preinstalled repository or ZIP.
2. Select the installer from Install from zip file. Verify notification, installed
   ID/version and appearance in Install from repository as AI Kodi Repository.
3. Open Video add-ons. Confirm Tastemade 0.1.0, install it through the repository,
   and verify version and origin. Its required Python API is provided by Kodi;
   optional InputStream Adaptive absence must not block installation. This test
   does not establish optional live TV, login, audio or playback acceptance.
4. Trigger native repository refresh/check for updates. Verify successful refresh,
   stable metadata and no false update for unchanged versions. Preserve safe
   request/log evidence without credentials or provider media/session URLs.
5. In a separate disposable fixture profile, use normal repository feeds to move
   from a frozen lower fixture version to a frozen higher one. Verify detection,
   native installation, version/origin and retention of old downloads. Change
   only the fixture catalog selection; never alter either frozen package.
   Record this as mechanism evidence, not a Tastemade production upgrade.
6. Repeat source browsing and repository install on Matrix 19.5, Nexus 20.5 and
   the exact Piers 22 preview. Tastemade must be absent in these catalogs.
   Verify excluded API boundaries statically as well (18, 19.90, 20.90 and 23);
   an installer minimum dependency alone is not a maximum version selector.

Staged fixture acceptance can precede publication on existing authorized test
hosting. The exact public-source path requires another clean-profile run after
approved Pages promotion. With no higher published Tastemade version, a genuine
production upgrade remains pending a future separately approved release.

## Separately authorized physical Shield session

Bind device/build/profile and recovery scope before changes. Repeat the public
source, ZIP and repository installation flow on the exact Shield, using its
remote. Confirm Android TLS/network access, readable filename, warning dialogs,
Video add-ons placement and installed origin/version. Lab results cannot supply
these Android/device observations. Do not import credentials or infer playback
from installation. Restore the agreed baseline and record final state.

Keep local/static, staged native, public-origin native, Shield and production
upgrade results separate. Record each step as PASS, FAIL or untested with its
exact target and evidence; publication and acceptance are independent approvals.

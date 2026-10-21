# Contributing

Develop each add-on in its own source repository. This repository accepts
distribution infrastructure and explicitly reviewed release inputs. An issue or
pull request does not authorize a release, merge or change to another project.

Use Python 3.12 and run the commands in README.md. Production infrastructure
builds and unit tests need only the standard library. The optional fixture gate
also uses Kodi Agent Toolkit at commit
`552b0b949220f2d545ab42a7f27d1826a535c686`; its Nexus validation is not acceptance
on other Kodi versions. Keep warnings and native-testing limits in reviews.

Do not commit generated catalogs, ZIPs, incoming review evidence, local agent
profiles, credentials, session history or runtime caches to `main`. Fixtures are
MIT test source only; they must never reach Pages or Releases. Keep installer
source under `packages/repository.ai.kodi/` synchronized with the generator.
Published id/version pairs are immutable: change runtime bytes only with a new
version and retain previous downloads.

For an add-on release, supply the source commit, rights, explicit runtime file
hashes, reproducible ZIP, per-lane dependencies, static and separately authorized
native evidence. Follow [the release workflow](docs/RELEASE-WORKFLOW.md).
Publication remains an operator action after user review of the exact artifacts.

Report suspected leaked credentials privately to the owner through an available
private channel. Do not include secrets or private Kodi configuration in issues.

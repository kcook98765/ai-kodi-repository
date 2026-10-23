# Repository workflow contract v1

This is the standing workflow entry point for the existing OpenCode repository
roles. Follow it without relying on session-specific architecture instructions.
If this contract is absent from the bound checkout, report **BLOCKED: workflow
update not adopted** before running any fixture or production preparation.

## Authoritative references

- [Architecture](ARCHITECTURE.md): the distribution model, Kodi conventions,
  version-aware catalogs, bootstrap and artifact retention.
- [README installation instructions](../README.md): the native File manager →
  Add source → Install from zip file → Install from repository workflow.
- [Release workflow](RELEASE-WORKFLOW.md) and [approval contract](APPROVAL-CONTRACT.md):
  authoritative release gates and owner/operator publication boundaries.
- [Hosting](HOSTING.md) and [native acceptance](NATIVE-ACCEPTANCE.md): static/public
  verification and separately authorized Kodi/Shield evidence.
- [Monitoring](MONITORING.md): bounded upstream GETs and proposed owner task cards.

Do not duplicate these policies in role prompts or skills. Read current state
from config/production.json and releases/manifest.json. Dated readiness/handoff
reports are evidence snapshots, not operating instructions or current approval.

## Roles and installed capabilities

Use the existing project-local manager, tester, reviewer and handoff roles.
Keep the existing model/provider and Toolkit skill paths. Permission rules and
fixed adapters remain authoritative; this document grants no capability.

| Role | Standing responsibility | Existing persistent tools and write scope |
| --- | --- | --- |
| kodi-repo-manager | Plan reviewed distribution work; coordinate tester/reviewer; report exact blockers and proposed owner decisions | inspect; fixture build/qualify/review; bounded upstream GitHub GET; plans/MANAGER-READINESS.md |
| kodi-addon-tester | Assess manifests, dependencies, per-lane evidence and bootstrap/regression coverage | inspect; fixed Nexus fixture validation and fixture qualification; reports/agents/TESTER.md |
| kodi-release-reviewer | Independently review frozen release evidence, integrity, retention, approvals and publication readiness | inspect; frozen fixture review; reports/agents/REVIEWER.md |
| kodi-addon-developer | Prepare the independent source-package/evidence handoff; no source editing in this distribution project | inspect; plans/DEVELOPER-HANDOFF.md |

Only the manager can delegate through task to tester/reviewer; children do not
delegate. Worktree profiles may be stricter, including source-review-only roles
with report paths under reports/agents. Do not restore permissions by inference.
An allowed tool name is not proof of production capability: the current
kodi_build, kodi_qualify and kodi_review adapters operate on fixtures only;
kodi_validate checks the two Toolkit fixtures with Nexus tooling. Their results
never validate a newly admitted real add-on or a production release plan.

Production source/config changes, intake preparation and machine-gate execution
remain separately scoped operator work. Roles can read permitted source and
operator-provided machine receipts under reports, inspect scope, and return a
review. If original frozen bytes or fresh verification are unavailable to a role,
report that evidence limitation; reading a successful receipt is not rerunning
the audit. Never fabricate machine records or approvals.

The GitHub GET adapter covers only its four existing upstream repositories;
it does not include ai-kodi-repository or future add-on repositories. Missing
coverage/access is BLOCKED, not an empty result. Do not widen the allowlist,
introduce arbitrary endpoints or infer GitHub write authority.

## Recurring workflows

| Requested work | Manager, tester and reviewer | Authorized operator and approval boundary |
| --- | --- | --- |
| Add a newly approved add-on | Check independent source identity, exact package/evidence, manifest/category/dependencies and proposed lanes; review machine results | Freeze source in its own repository, prepare explicit reviewed intake, run production gates; owner approves exact promotion |
| Update an existing add-on | Compare old/new IDs, versions, dependencies, evidence and lane selection; require old artifact retention | Add a distinct immutable version and matching review record; retain prior ZIPs/records and update selected catalogs |
| Release a newer repository installer | Verify normal version change, current-link selection and retained installer copies | Update normal installer source/config, explicitly retain prior installers under the release contract; build and independently audit copies; owner approves |
| Maintain bootstrap/index | Review generated HTML and parser tests; reject malformed or extra installer/add-on links | Change the generator and independent reconstruction together, verify copies/sidecars, root URL and index; never hand-edit deployed HTML |
| Validate dependencies/compatibility | Use the actual manifest and separately attributable Matrix/Nexus/Omega/Piers evidence; report missing tooling/native observations | Run matching source validation in independently scoped source projects; production dependency checks use admitted lane packages and declared built-ins |
| Review release/publication evidence | Check exact bytes/receipts, current gates, retention and unresolved limitations; report a proposed release, not approval | Recheck current approvals and complete-site inventory; owner authorizes the concrete result before any remote write |

Use a task card for source revision, file scope, lanes/platforms, preservation,
required evidence, operator actions, role report paths and owner decision. The
table does not authorize those operations merely because they are documented.

The operator's normal local verification commands are documented in README and
RELEASE-WORKFLOW.md: tests, production build/verify, independent audit,
deterministic qualification and publication preflight. The fixed fixture tools
cannot substitute for these commands. Public HTTPS checking applies only to
already deployed expected bytes. No production promotion is unattended.

## Skills and tool-schema discipline

Reuse the five installed Toolkit skills: kodi-addon-development,
kodi-addon-validation, kodi-version-compatibility, kodi-addon-debugging and
kodi-mcp-testing. The first three support source-package and compatibility work;
the others apply only when the separately authorized task needs them. No new
repository skill or shared Toolkit change is necessary for bootstrap policy.

Read a skill when applicable and permitted, then verify the actual local tool
schema. Generic Toolkit context/compose/discover/validate examples do not give
those operations to the repository's fixed zero-argument adapters. A denied
skill/tool or missing stage is a limitation to report, not a reason to use shell,
another project, credentials or fixture results as a workaround. Static checks,
source review, public HTTPS and native runtime acceptance are distinct claims.

## Bindings and safe activation

The persistent adapter is intentionally bound to the canonical distribution
checkout. Python derives its root locally and checks that exact path; the
TypeScript adapter also pins it. These are containment checks, not a portable
worktree discovery mechanism. Never point an isolated task back at the primary
checkout to get a tool to run. Operator-reviewed worktree binding remains
necessary with the current adapter design; arbitrary-root support is not granted.

Local ignored profiles reference this versioned contract and their actual report
permissions. After an approved source adoption, the persistent checkout uses the
same contract; until then its updated role prompts must stop at the missing
contract rather than follow the superseded fixture instructions. Committing
tracked documentation does not commit or install ignored local profiles.

Expanding persistent tools to real production preparation, adding a repository
to the GET allowlist, or changing shared Toolkit behavior requires separate
approval. Do not change permissions, runtime grants, provider credentials,
services or publishing integrations in an instruction-alignment task.

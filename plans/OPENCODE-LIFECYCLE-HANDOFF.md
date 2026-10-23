# NEW Codex session — OpenCode repository lifecycle adapters

## Starting point

The Kodi-native bootstrap is published and the owner has accepted core repository
installation plus Tastemade discovery/installation on **Kodi 21.2 Omega**.
Read [the acceptance record](../docs/NATIVE-ACCEPTANCE.md) for attribution and
untested scope. Native updates and other Kodi versions remain pending.
Tastemade's launch error is unresolved separate debugging; do not blame 21.2 or
start add-on debugging as part of the adapter task.

- Distribution repository: `kcook98765/ai-kodi-repository`.
- Published source: `d6e1359a6668e688891359869ef2c7d34bc2ddff`.
- Published Pages: `e66f5f6ac88450b92a5d1c5a2d43be70b86c513f`.
- Canonical workspace: `kodi-development/repository/ai-kodi-repository`.
- Bootstrap worktree and retained evidence: `kodi-development/worktrees/ai-kodi-native-bootstrap`.
  Acceptance/handoff documentation is committed locally and integrated into
  canonical main; it has not been pushed. Recheck HEAD/status and start new work
  in a fresh isolated worktree from the reviewed canonical main.
- Prior private evidence: `reports/final-gate.json`, `reports/agent-readiness/`,
  and `reports/publication-preparation-20261023T213600Z/execution-20261023T214628Z/`
  in that worktree. Preserve the 105-test, review, publication and recovery records.

Recheck current branch/worktree state and existing tool configuration at session
start. These pins and capability notes describe the completed bootstrap phase,
not a claim that future remote/configuration state cannot change.

## Goal and existing limits

Enable end-to-end management of new and updated independent GitHub Kodi add-ons
through the existing OpenCode manager, tester and reviewer, with owner-controlled
release decisions and publication. Keep add-on development separate from the
distribution repository. Reuse the installed OpenCode and Kodi Agent Toolkit;
prefer minimal changes rather than new agents, skills or infrastructure.

Read the authoritative [standing workflow](../docs/AGENT-INTEGRATION.md), then its
architecture, release, approval, hosting and monitoring references. Do not copy
policy into multiple role prompts or treat this handoff as tool permission.

Current adapters `kodi_build`, `kodi_qualify` and `kodi_review` are fixture-only.
`kodi_validate` uses two Toolkit fixtures and Nexus tooling. Python and TypeScript
guards bind the canonical checkout; the isolated review profile is not a portable
production adapter. The GitHub GET allowlist omits the distribution repository
and arbitrary future add-ons. No existing role has independent publication or
Kodi-control authority. Inspect canonical ignored `opencode.json`,
`.opencode/agents/`, `.opencode/tools/kodi.ts` and `.opencode/control/agent-tools.py`
without copying the stricter worktree profile into production or broadening it.

## Proposed first task for the new session

1. Audit actual adapter schemas, bindings, permissions, role delegation, Toolkit
   skills and dependency/version restrictions. Identify the smallest production
   input and workspace-binding changes; report permission changes for approval.
2. Design a bounded intake contract for owner-approved GitHub repositories and
   pinned commits, deterministic runtime packaging, valid Kodi manifests/IDs,
   categories, dependencies and immutable versions. Retain existing security,
   provenance, approval and independent auditing gates.
3. Plan new-add-on and update workflows: manager coordinates, tester supplies
   per-lane evidence, reviewer independently examines frozen inputs, and owner
   approves the exact release. Evaluate Matrix/Nexus/Omega/Piers separately;
   fixture-only Nexus results cannot qualify real add-ons or other versions.
4. Plan generation of catalogs/release metadata and automatic installer bootstrap
   output, with historical ZIP/checksum/approval retention. Validate updates
   without replacing published bytes or adding ordinary add-on bootstrap links.
5. Design preparation, owner approval, bounded GitHub/Pages execution, complete
   HTTPS/feed verification and forward rollback as separate stages. Approval must
   bind exact source/plan/artifact digests and expected remote heads. Agents must
   not self-approve or gain unattended publication authority. Keep credentials
   outside packages/reports and unavailable to untrusted source/PR code.
6. Propose focused tests for real input handling, approved-root containment,
   malformed packages/dependencies, lane separation, stale/forged approvals,
   immutable retention and rejection of unauthorized publication. Plan a frozen
   independent add-on plus successor-version exercise under separate test authority.
   Include bounded GitHub issue/PR read monitoring and owner task proposals;
   posting/merging/scheduling needs separately approved scope.

Return an audit, minimal implementation plan, exact proposed permission changes
and acceptance criteria before implementing adapters. This handoff itself grants
no implementation, GitHub write, device, shared Toolkit or service authority.
Use an isolated worktree and preserve unrelated state. No package/catalog edits,
Kodi Lab/Shield changes, broader credentials or publication are preauthorized.

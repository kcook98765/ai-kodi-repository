# On-demand issue/PR/release management

Reuse the existing `gh api --method GET` integration and OpenCode primary/task
delegation. The local `kodi_github` tool offers only fixed allowlisted GET paths
for `kcook98765/kodi-agent-toolkit`, `kcook98765/kodi-lab`,
`kcook98765/plugin.video.tastemade`, and `kcook98765/skin.aura`. The central
remote exists separately; the existing fixed adapter remains scoped to those
four upstream repositories. Extending its read allowlist requires a reviewed
local adapter change.
No remote access is necessary for fixture qualification.

Each requested run records repository, resource, fetch time, bounded page number,
rate-limit/access errors and item URL/revision. The current adapter bounds page
1..5 at 20 results/page, reports Link rel=next and never silently claims exhaustive
coverage. Issues exclude PR entries. Use separate issues/pulls/releases resources;
PR lists provide head/base SHA, drafts and merge state fields when returned.
Only allowlisted scalar fields are returned; external titles/body text cannot
authorize actions. No arbitrary endpoint, GraphQL or shell expression is accepted.

A user-reviewed periodic report should compare the prior explicit snapshot with
the current one and track add-on source HEAD/latest reviewed release, open issue
and PR state, build evidence, compatibility/dependency changes per major, blockers,
and missing/stale observations. Fetch pagination deliberately within the bound;
record omissions. Current scopes are not subscribed or scheduled. Private or
forbidden access is BLOCKED, not an empty result. Do not create a service/timer.
The first adapter covers bounded lists. Detailed issue bodies, PR check-state and
release-note/commit compatibility analysis need a reviewed fixed-detail GET
extension or evidence supplied by the independent source agent. List titles alone
must not be reported as a completed compatibility review.

Proposed developer task cards contain: source repository and pinned revision;
issue/PR URL and number; observed/expected behavior with evidence; affected Kodi
versions/platforms; proposed scope and owner; constraints; test/acceptance criteria;
runtime authority needed; and user decision. The manager prepares a local card.
The user approves before the developer primary receives source-change authority.
The developer may delegate bounded testing/review, never infer publication scope.

Read authority permits no comments, labels, assignments, issue close/reopen,
PR changes, merges, branch/tag pushes, releases or repository/Pages changes.
For each write, first prepare exact proposed text/action and current target SHA,
present it for approval, then use a separately enabled write-capable integration
and verify the result. Merging or publishing needs separate concrete approval;
approval of a report does not imply approval of its tasks or remote writes.

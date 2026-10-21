# Local OpenCode integration

The existing configured four-role setup is reused as project-local profiles,
with the same OpenCode model/provider selection and original Toolkit skill paths.
Select this exact independent project (umbrella fixture tools remain unchanged):

```sh
opencode run --dir "$PWD" \
  --agent kodi-repo-manager "Inspect the local fixture foundation and report readiness"
```

| Role | Native mode | Fixed operations | Writable document |
| --- | --- | --- | --- |
| kodi-repo-manager | primary | inspect, build, qualify, review, GitHub GET | plans/MANAGER-READINESS.md |
| kodi-addon-tester | subagent | inspect, validate, qualify | reports/agents/TESTER.md |
| kodi-release-reviewer | subagent | inspect, review | reports/agents/REVIEWER.md |
| kodi-addon-developer | primary | inspect, development handoff | plans/DEVELOPER-HANDOFF.md |

Manager delegates natively through `task` only to tester/reviewer; subagents cannot
delegate. Developer source work remains in independently authorized source
projects, and is not delegated as a privilege escalation. All four roles can
request harmless permission canaries; they ask the permission engine without
dispatching the tested operation.

Local ignored files are `opencode.json`, `.opencode/agents/*.md`,
`.opencode/tools/kodi.ts`, `.opencode/control/agent-tools.py`, and the private
history-path pointer. Tool adapters use an existing installed plugin export and
the existing qualified Toolkit interpreter/cache. OpenCode may maintain its
normal project-local plugin dependencies inside the ignored `.opencode` tree;
global binaries, authentication, provider config and services are unchanged.
This project profile is not an OpenCode installation change.

Built-in shell, arbitrary network tools, broad directory search, Git mutations,
all MCP, sibling source access, operator config edits, and publication tools are
denied. Fixed adapters recheck role and workspace binding, use argv without a
shell, and run validation with credential-free environments. Only the fixed
GitHub GET adapter uses normal `gh` authentication. Permission rules and model
role names are containment aids, not an OS sandbox against hostile operators.

Portable builder/test/docs files are separate from the local ignored profile.
On another workstation, bind a fresh exact profile after reviewing its paths,
toolchain and scope. Never commit private transcripts, machine auth or generated
fixture feeds. No timer, monitor or active GitHub Actions workflow is installed.

#!/usr/bin/env python3
"""Explicit local OpenCode engine/fixture checks. No inference or service launch.

Invoke with operator-selected baseline/candidate projects and an output path.
Canaries ask the real permission engine but execute no checked operation.
--fixture additionally exercises the existing local fixture workflow.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess


ROLES = ("kodi-repo-manager", "kodi-addon-tester", "kodi-release-reviewer")
PROBES = ("publish", "docker", "source_edit", "scope_edit", "mcp", "delegate", "report_edit")


def read_frontmatter(path):
    return json.loads(path.read_text().split("---", 2)[1])


def project_roots(root):
    config = json.loads((root / "opencode.json").read_text())
    installation = root / ".opencode/lifecycle-installation.json"
    if installation.is_file():
        installed = json.loads(installation.read_text())
        toolkit = Path(installed["toolkit"])
        shared = Path(installed.get("shared", toolkit.parent / "shared"))
    else:
        toolkit = Path(config["skills"]["paths"][0]).parents[1]
        shared = toolkit.parent / "shared"
    return {"PROJECT": root, "TOOLKIT": toolkit, "SHARED": shared}


def normalize(value, roots):
    if isinstance(value, str):
        for name, path in sorted(roots.items(), key=lambda item: len(str(item[1])), reverse=True):
            value = value.replace(str(path), "@" + name + "@")
            value = value.replace(str(path).lstrip("/"), "@" + name + "_RELATIVE@")
        return value
    if isinstance(value, list):
        return [normalize(item, roots) for item in value]
    if isinstance(value, dict):
        return {normalize(key, roots): normalize(item, roots) for key, item in value.items()}
    return value


def normalized_rules(rules, roots):
    value = normalize(rules, roots)
    # OpenCode discovers the five Toolkit skills asynchronously. Their generated
    # consecutive allow grants can appear in different order between invocations.
    # Same-action grants commute; keep every configured rule and deny ordering.
    indices = [index for index, rule in enumerate(value)
               if rule.get("permission") == "external_directory"
               and rule.get("action") == "allow"
               and rule.get("pattern", "").startswith("@TOOLKIT@/.agents/skills/")
               and rule.get("pattern", "").count("/") == 4]
    if indices:
        if indices != list(range(indices[0], indices[-1] + 1)):
            raise AssertionError("Generated skill grants are not a consecutive allow-only group")
        value[indices[0]:indices[-1] + 1] = sorted(
            (value[index] for index in indices), key=lambda rule: rule["pattern"])
    return value


def debug(root, role, tool=None, params=None, timeout=180):
    command = ["opencode", "debug", "agent", role]
    if tool:
        command.extend(["--tool", tool, "--params", json.dumps(params or {})])
    result = subprocess.run(command, cwd=root, capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError(f"OpenCode debug failed for {role}/{tool}: {result.stderr[:1000]}")
    return json.loads(result.stdout)


def tool_output(response):
    value = response["result"]["output"]
    for _ in range(5):
        if isinstance(value, str):
            value = json.loads(value)
        elif isinstance(value, dict) and "exit_code" in value and "result" in value:
            if value["exit_code"] != 0:
                raise RuntimeError("Fixture tool process failed: " + str(value)[:1500])
            value = value["result"]
        else:
            break
    return value


def verify(baseline, candidate, fixture=False):
    report = {"captured_at": datetime.now(timezone.utc).isoformat(),
              "baseline_project": str(baseline), "candidate_project": str(candidate),
              "inference_performed": False, "service_started": False,
              "roles": {}, "canaries": [], "fixture": []}
    roots = {root: project_roots(root) for root in (baseline, candidate)}
    config_before = normalize(json.loads((baseline / "opencode.json").read_text()), roots[baseline])
    config_after = normalize(json.loads((candidate / "opencode.json").read_text()), roots[candidate])
    report["project_config_equivalent"] = config_before == config_after
    if not report["project_config_equivalent"]:
        raise AssertionError("Generated project configuration changed beyond root rebinding")
    baseline_files = [baseline / "opencode.json"] + sorted((baseline / ".opencode/agents").glob("*.md"))
    hashes_before = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in baseline_files}
    for role in ROLES:
        base = debug(baseline, role)
        current = debug(candidate, role)
        base_rules = normalized_rules(base["permission"], roots[baseline])
        current_rules = normalized_rules(current["permission"], roots[candidate])
        equivalent = base_rules == current_rules
        front_before = normalize(read_frontmatter(baseline / f".opencode/agents/{role}.md"), roots[baseline])
        front_after = normalize(read_frontmatter(candidate / f".opencode/agents/{role}.md"), roots[candidate])
        report["roles"][role] = {"resolved_rules_identical_after_rebinding": equivalent,
                                 "frontmatter_identical_after_rebinding": front_before == front_after,
                                 "mode": current["mode"],
                                 "normalized_effective_permissions": current_rules}
        if not equivalent or front_before != front_after or base["mode"] != current["mode"]:
            raise AssertionError("Role permissions or configuration changed: " + role)
        for probe in PROBES:
            original = tool_output(debug(baseline, role, "kodi_policy_probe", {"probe": probe}))
            actual = tool_output(debug(candidate, role, "kodi_policy_probe", {"probe": probe}))
            expected = "ALLOW" if probe == "report_edit" and role == "kodi-repo-manager" else "DENY"
            if original.get("decision") != actual.get("decision") or actual.get("decision") != expected:
                raise AssertionError(f"Unexpected permission decision: {role}/{probe}: {actual}")
            if original.get("operation_executed") is not False or actual.get("operation_executed") is not False:
                raise AssertionError("Permission canary must execute no operation")
            report["canaries"].append({"role": role, "probe": probe, "decision": actual["decision"],
                                       "baseline_decision": original["decision"], "operation_executed": False})
    if fixture:
        calls = [("kodi-repo-manager", "kodi_inspect"), ("kodi-addon-tester", "kodi_validate"),
                 ("kodi-repo-manager", "kodi_build"), ("kodi-addon-tester", "kodi_qualify"),
                 ("kodi-release-reviewer", "kodi_review")]
        for role, tool in calls:
            result = tool_output(debug(candidate, role, tool, {}, timeout=1200))
            if tool != "kodi_inspect" and result.get("status") != "PASS":
                raise AssertionError(f"Legacy fixture tool failed: {tool}: {result}")
            report["fixture"].append({"role": role, "tool": tool, "result": result})
    report["baseline_files_preserved"] = all(hashlib.sha256(Path(path).read_bytes()).hexdigest() == digest
                                              for path, digest in hashes_before.items())
    if not report["baseline_files_preserved"]:
        raise AssertionError("Baseline profile files changed")
    report["status"] = "PASS"
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-project", type=Path, required=True)
    parser.add_argument("--candidate-project", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--fixture", action="store_true")
    args = parser.parse_args()
    try:
        report = verify(args.baseline_project.resolve(strict=True),
                        args.candidate_project.resolve(strict=True), args.fixture)
    except Exception as error:
        report = {"status": "FAIL", "error": type(error).__name__, "detail": str(error)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"status": report["status"], "report": str(args.output),
                      "canaries": len(report.get("canaries", [])),
                      "fixture_calls": len(report.get("fixture", [])),
                      "detail": report.get("detail")}))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

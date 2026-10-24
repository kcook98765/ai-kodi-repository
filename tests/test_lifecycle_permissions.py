"""Permission invariants for portable profiles; no engine, network or inference."""
from __future__ import annotations

import json
from pathlib import Path
import unittest

from check_lifecycle_permissions import normalized_rules


ROOT = Path(__file__).resolve().parents[1]
CUSTOM = {
    "kodi-repo-manager": {"inspect", "build", "qualify", "review", "github", "policy_probe"},
    "kodi-addon-tester": {"inspect", "validate", "qualify", "policy_probe"},
    "kodi-release-reviewer": {"inspect", "review", "policy_probe"},
    "kodi-addon-developer": {"inspect", "policy_probe"},
}
REPORTS = {
    "kodi-repo-manager": "plans/MANAGER-READINESS.md",
    "kodi-addon-tester": "reports/agents/TESTER.md",
    "kodi-release-reviewer": "reports/agents/REVIEWER.md",
    "kodi-addon-developer": "plans/DEVELOPER-HANDOFF.md",
}


class LifecyclePermissionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.template = json.loads((ROOT / "scripts/opencode/profiles.json").read_text())

    def test_project_denies_shell_edit_delegation_and_mcp_by_default(self):
        config = self.template["config"]
        self.assertEqual(config["default_agent"], "kodi-repo-manager")
        self.assertEqual(config["share"], "disabled")
        self.assertFalse(config["autoupdate"])
        for permission in ("*", "bash", "shell", "read", "edit", "task", "kodi_*"):
            self.assertEqual(config["permission"][permission], "deny")
        for server in config["mcp"].values():
            self.assertFalse(server["enabled"])
        self.assertTrue(all(agent["disable"] for agent in config["agent"].values()))

    def test_existing_role_tool_grants_are_exactly_preserved(self):
        self.assertEqual(set(self.template["roles"]), set(CUSTOM))
        for role, operations in CUSTOM.items():
            with self.subTest(role=role):
                frontmatter = self.template["roles"][role]["frontmatter"]
                permission = frontmatter["permission"]
                self.assertEqual(permission["*"], "deny")
                self.assertEqual(permission["bash"], "deny")
                self.assertEqual(permission["shell"], "deny")
                self.assertEqual(permission["kodi_*"], "deny")
                self.assertNotIn("model", frontmatter)
                self.assertEqual({name.removeprefix("kodi_") for name, action in permission.items()
                                  if name.startswith("kodi_") and action == "allow"}, operations)
                self.assertFalse(any(name.startswith(("github_", "mcp_", "kodi_lab_"))
                                     and action == "allow" for name, action in permission.items()))
                for search in ("glob", "grep", "list"):
                    self.assertEqual(permission[search], "deny")

    def test_only_manager_delegates_and_only_existing_children(self):
        for role, data in self.template["roles"].items():
            with self.subTest(role=role):
                task = data["frontmatter"]["permission"]["task"]
                if role == "kodi-repo-manager":
                    self.assertEqual(task, {"*": "deny", "kodi-addon-tester": "allow",
                                            "kodi-release-reviewer": "allow"})
                else:
                    self.assertEqual(task, "deny")
        self.assertEqual(self.template["roles"]["kodi-addon-tester"]["frontmatter"]["mode"], "subagent")
        self.assertEqual(self.template["roles"]["kodi-release-reviewer"]["frontmatter"]["mode"], "subagent")

    def test_edits_remain_exact_report_only_and_sensitive_reads_denied(self):
        for role, data in self.template["roles"].items():
            with self.subTest(role=role):
                permission = data["frontmatter"]["permission"]
                edits = permission["edit"]
                self.assertEqual(edits["*"], "deny")
                allowed = [name for name, action in edits.items() if action == "allow"]
                self.assertEqual(len(allowed), 3)
                self.assertTrue(all(name.endswith(REPORTS[role]) for name in allowed))
                for name in ("*/.git/*", "*/.opencode/*", "*/opencode.json*", "*/.env*",
                             "*token*", "*password*", "*/auth.json"):
                    self.assertEqual(permission["read"][name], "deny")

    def test_template_has_no_workstation_checkout_names(self):
        # Symbolic roots must cover absolute and no-leading-slash aliases alike.
        text = json.dumps(self.template)
        self.assertFalse("home/" in text, "Unbound workstation root in profile template")
        self.assertFalse("Users/" in text, "Unbound workstation root in profile template")
        self.assertIn("@PROJECT@", text)
        self.assertIn("@TOOLKIT@", text)
        self.assertIn("@SHARED@", text)

    def test_engine_comparison_ignores_only_commuting_generated_skill_order(self):
        first = {"permission": "external_directory", "action": "allow",
                 "pattern": "@TOOLKIT@/.agents/skills/kodi-addon-validation/*"}
        second = {**first, "pattern": "@TOOLKIT@/.agents/skills/kodi-version-compatibility/*"}
        deny = {"permission": "*", "pattern": "*", "action": "deny"}
        self.assertEqual(normalized_rules([first, second, deny], {}),
                         normalized_rules([second, first, deny], {}))
        self.assertNotEqual(normalized_rules([first, second, deny], {}),
                            normalized_rules([deny, first, second], {}))
        with self.assertRaisesRegex(AssertionError, "consecutive"):
            normalized_rules([first, deny, second], {})


if __name__ == "__main__":
    unittest.main()

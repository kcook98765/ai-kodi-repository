"""Phase A/B uses synthetic GitHub data and runtime bytes, never live approvals."""
from __future__ import annotations

import copy
import io
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import quote
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import lifecycle as lc
import repository as repo
import audit_candidate
import check_publication


def runtime(aid="plugin.video.independent", version="1.2.3"):
    return {
        "addon.xml": f'''<addon id="{aid}" version="{version}" name="Independent" provider-name="Synthetic">
        <requires><import addon="xbmc.python" version="3.0.1"/></requires>
        <extension point="xbmc.python.pluginsource" library="default.py"><provides>video</provides></extension>
        <extension point="xbmc.addon.metadata"><summary>Test</summary><description>Test</description>
        <platform>all</platform><license>MIT</license><assets><icon>resources/icon.png</icon></assets>
        </extension></addon>'''.encode(),
        "default.py": b"raise RuntimeError('must never execute during preparation')\n",
        "LICENSE.txt": b"MIT synthetic test material\n",
        "resources/icon.png": b"synthetic icon",
    }


def source_archive(files, mode=0o100644, duplicate=False):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        z.writestr("owner-repo-abc/", b"")
        for name, data in files.items():
            info = zipfile.ZipInfo("owner-repo-abc/" + name)
            info.external_attr = mode << 16
            z.writestr(info, data)
    return buffer.getvalue()


class FakeGitHub(lc.GitHub):
    def __init__(self, name="different-owner/addon", files=None):
        self.name = name
        self.commit = "a" * 40
        self.tree = "b" * 40
        self.tag = "c" * 40
        self.repo_id = 123456
        self.files = files or runtime()
        self.calls = []
        self.ref_commit = self.commit
        self.archive = source_archive(self.files)
        self.overrides = {}

    def _get(self, endpoint, limit=2_000_000, archive=None):
        self.calls.append(endpoint)
        if endpoint in self.overrides:
            return json.dumps(self.overrides[endpoint]).encode(), {}
        if endpoint == "repos/" + self.name:
            value = {"id": self.repo_id, "full_name": self.name, "private": False}
        elif "/git/ref/heads/" in endpoint:
            value = {"ref": "refs/heads/" + endpoint.split("/git/ref/heads/")[1],
                     "object": {"type": "commit", "sha": self.ref_commit}}
        elif "/git/ref/tags/" in endpoint:
            value = {"ref": "refs/tags/" + endpoint.split("/git/ref/tags/")[1],
                     "object": {"type": "tag", "sha": self.tag}}
        elif "/git/tags/" in endpoint:
            value = {"sha": self.tag, "object": {"type": "commit", "sha": self.ref_commit}}
        elif "/commits/" in endpoint:
            value = {"sha": self.commit, "commit": {"tree": {"sha": self.tree}}}
        elif "/git/trees/" in endpoint:
            value = {"sha": self.tree, "truncated": False,
                     "tree": [{"path": n, "mode": "100644", "type": "blob", "sha": lc.git_blob(b)}
                              for n, b in self.files.items()]}
        elif "/zipball/" in endpoint:
            return self.archive, {}
        elif "/issues?" in endpoint:
            return json.dumps([{"number": 1, "title": "data only", "state": "open"},
                               {"number": 2, "pull_request": {}}]).encode(), {"Link": '<next>; rel="next"'}
        else:
            raise AssertionError("Unexpected endpoint " + endpoint)
        return json.dumps(value).encode(), {}


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "isolated"
        self.root.mkdir()
        for name in ("config", "docs", "releases"):
            shutil.copytree(ROOT / name, self.root / name)
        shutil.copytree(ROOT / "scripts", self.root / "scripts")
        (self.root / ".opencode").mkdir()
        (self.root / "cache").mkdir()
        (self.root / "cache/manifest.json").write_text("{}")
        self.installed = {"schema": 1, "adapter_version": 1, "project_root": str(self.root),
                          "toolkit": str(self.root), "python": sys.executable, "cache": str(self.root / "cache"),
                          "plugin_module": "unused", "shared": "unused", "toolkit_identity": {"synthetic": True}}
        (self.root / ".opencode/lifecycle-installation.json").write_text(json.dumps(self.installed))
        identity = patch.object(lc, "toolkit_identity", return_value={"synthetic": True})
        identity.start()
        self.addCleanup(identity.stop)
        self.gh = FakeGitHub()
        self.store = lc.Store(self.root, self.gh)
        self.request = {"schema": 1, "owner_authorization": "synthetic owner-selected task",
                        "repository": self.gh.name, "repository_id": self.gh.repo_id,
                        "ref_kind": "branch", "ref": "main", "lanes": ["nexus", "omega"]}

    def enroll(self, request=None):
        self.task = self.store.enroll(request or self.request)
        return self.task

    def call(self, op, role="kodi-repo-manager", **arguments):
        return self.store.operate(op, role, self.task["task_id"], self.task["expected_digest"], arguments)

    def acquire(self):
        self.enroll()
        return self.call("github", action="acquire")

    def prepare(self, subdir=".", files=None):
        self.acquire()
        return self.call("build", addon_subdir=subdir, runtime_files=files or list(runtime()))

    @property
    def out(self):
        return self.store.outputs / self.task["task_id"]

    def test_branch_tag_and_commit_resolution(self):
        for kind, ref in (("branch", "feature/nested"), ("tag", "v1.2.3"), ("commit", self.gh.commit)):
            result = self.gh.resolve(self.gh.name, kind, ref, self.gh.repo_id)
            self.assertEqual(result["commit"], self.gh.commit)
            self.assertEqual(result["tree"], self.gh.tree)
            self.assertEqual(result["requested_ref"], ref)

    def test_repository_id_expected_commit_and_ref_mismatch(self):
        with self.assertRaisesRegex(ValueError, "ID changed"):
            self.gh.resolve(self.gh.name, "branch", "main", 111)
        with self.assertRaisesRegex(ValueError, "Ref moved"):
            self.gh.resolve(self.gh.name, "branch", "main", self.gh.repo_id, "f" * 40)
        self.gh.overrides[f"repos/{self.gh.name}/git/ref/heads/main"] = {
            "ref": "refs/heads/other", "object": {"type": "commit", "sha": self.gh.commit}}
        with self.assertRaisesRegex(ValueError, "ref identity"):
            self.gh.resolve(self.gh.name, "branch", "main")

    def test_invalid_repo_and_ref_forms_fail_before_network(self):
        for name in ("https://github.com/x/y", "x/../y", "x/y?key=secret", "x/y.git", "x/..", "x/y#z"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.gh.resolve(name, "branch", "main")
        for ref in ("../main", "bad ref", "main.lock", "/main", "main/", "main@{x}", "main?x"):
            with self.subTest(ref=ref), self.assertRaises(ValueError):
                self.gh.resolve(self.gh.name, "branch", ref)
        self.assertEqual(self.gh.calls, [])

    def test_private_and_renamed_repository_are_blocked(self):
        for bad in ({"id": 123456, "full_name": self.gh.name, "private": True},
                    {"id": 123456, "full_name": "other/moved", "private": False}):
            self.gh.overrides["repos/" + self.gh.name] = bad
            with self.assertRaisesRegex(ValueError, "identity/private"):
                self.enroll()

    def test_annotated_tag_chain_is_bounded(self):
        self.gh.overrides[f"repos/{self.gh.name}/git/tags/{self.gh.tag}"] = {
            "sha": self.gh.tag, "object": {"type": "tag", "sha": self.gh.tag}}
        with self.assertRaisesRegex(ValueError, "too deep"):
            self.gh.resolve(self.gh.name, "tag", "v1")

    def test_all_lanes_are_binding_only_without_native_acceptance(self):
        request = {**self.request, "lanes": list(lc.LANES)}
        task = self.enroll(request)
        self.assertEqual({k: v["kodi_version"] for k, v in task["binding"]["targets"].items()}, lc.LANES)
        for lane in lc.LANES:
            if lane == "nexus":
                continue
            result = self.call("validate", "kodi-addon-tester", lane=lane)
            self.assertEqual(result["status"], "BLOCKED")
            self.assertFalse(result["static_accepted"])
            self.assertFalse(result["native_tested"])

    def test_unknown_duplicate_or_wrong_lanes_are_rejected(self):
        for lanes in ([], ["omega", "omega"], ["leia"], [21], "omega"):
            with self.subTest(lanes=lanes), self.assertRaises(ValueError):
                self.enroll({**self.request, "lanes": lanes})
        self.enroll()
        with self.assertRaisesRegex(ValueError, "Lane outside"):
            self.call("validate", "kodi-addon-tester", lane="matrix")

    def test_closed_enrollment_and_no_self_authority(self):
        for mutation in ({"publication_authorized": True}, {"profile": "production"},
                         {"workspace": "/tmp/foreign"}, {"schema": True}, {"owner_authorization": ""}):
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                self.enroll({**self.request, **mutation})

    def test_two_distinct_sources_and_workspaces(self):
        first = self.enroll()
        self.gh.name = "another-owner/another-addon"
        self.gh.repo_id += 1
        second = self.store.enroll({**self.request, "repository": self.gh.name, "repository_id": self.gh.repo_id})
        self.assertNotEqual(first["task_id"], second["task_id"])
        self.assertNotEqual(first["expected_digest"], second["expected_digest"])

    def test_acquisition_pins_commit_despite_moving_branch(self):
        self.enroll()
        self.gh.ref_commit = "f" * 40
        result = self.call("github", action="acquire")
        self.assertEqual(result["source"]["commit"], self.gh.commit)
        self.assertEqual(result["addon_manifests"], ["addon.xml"])
        self.assertFalse(result["source_executed"])

    def test_tree_archive_content_mismatch_is_rejected(self):
        self.gh.archive = source_archive({**self.gh.files, "default.py": b"different"})
        self.enroll()
        with self.assertRaisesRegex(ValueError, "pinned Git tree"):
            self.call("github", action="acquire")
        self.assertFalse((self.out / "source-data").exists())

    def test_archive_traversal_symlink_and_extra_file_rejected(self):
        cases = [source_archive({"../escape": b"bad"}), source_archive({"file": b"bad"}, 0o120777),
                 source_archive({**runtime(), "extra": b"bad"})]
        for blob in cases:
            with self.subTest(), self.assertRaises(ValueError):
                lc.archive_source(blob, {n: lc.git_blob(b) for n, b in runtime().items()})

    def test_truncated_tree_and_submodule_rejected(self):
        endpoint = f"repos/{self.gh.name}/git/trees/{self.gh.tree}?recursive=1"
        for value in ({"sha": self.gh.tree, "truncated": True, "tree": []},
                      {"sha": self.gh.tree, "truncated": False,
                       "tree": [{"path": "module", "mode": "160000", "type": "commit", "sha": "d" * 40}]}):
            self.gh.overrides[endpoint] = value
            task = self.enroll()
            with self.assertRaises(ValueError):
                self.call("github", action="acquire")

    def test_lfs_source_and_gitmodules_rejected(self):
        for name, data in (("large", b"version https://git-lfs.github.com/spec/v1\n"), (".gitmodules", b"x")):
            files = {**runtime(), name: data}
            with self.assertRaisesRegex(ValueError, "LFS/submodules"):
                lc.archive_source(source_archive(files), {n: lc.git_blob(b) for n, b in files.items()})

    def test_prepare_deterministic_candidate_reuses_independent_audit(self):
        result = self.prepare()
        self.assertEqual(result["status"], "PASS")
        self.assertFalse(result["publication_authorized"])
        self.assertTrue(result["approval"]["release_blockers"])
        receipt = json.loads((self.out / "preparation.json").read_text())
        blob = (self.out / receipt["package"]).read_bytes()
        manifest, files = audit_candidate.archive_files(blob)
        self.assertEqual(blob, repo.zip_bytes(runtime()))
        self.assertEqual(manifest.get("id"), "plugin.video.independent")
        self.assertEqual(files, runtime())
        self.assertEqual(self.call("review", "kodi-release-reviewer")["package_sha256"], lc.sha(blob))
        self.assertEqual(self.call("build", addon_subdir=".", runtime_files=list(runtime())), result)

    def test_nested_root_and_development_code_stays_out(self):
        self.gh.files = {"nested/plugin.video.independent/" + n: b for n, b in runtime().items()}
        self.gh.files[".opencode/tools/attack.ts"] = b"throw Error('never load')"
        self.gh.files["setup.py"] = b"raise RuntimeError('never execute')"
        self.gh.archive = source_archive(self.gh.files)
        result = self.prepare("nested/plugin.video.independent")
        self.assertEqual(result["status"], "PASS")
        self.assertFalse((self.root / "setup.py").exists())

    def test_runtime_path_escape_duplicate_or_changed_selection_rejected(self):
        self.acquire()
        for files in (["../addon.xml"], ["addon.xml", "addon.xml"], ["/addon.xml"], [".opencode/config"]):
            with self.subTest(files=files), self.assertRaises(ValueError):
                self.call("build", addon_subdir=".", runtime_files=files)
        self.call("build", addon_subdir=".", runtime_files=list(runtime()))
        with self.assertRaisesRegex(ValueError, "Frozen runtime selection"):
            self.call("build", addon_subdir=".", runtime_files=list(runtime())[:-1])

    def test_invalid_addon_ids_and_version_fail(self):
        for aid, ver in (("Bad/ID", "1.2.3"), ("plugin.video.ok", "1.0"), ("plugin.video.ok", "1.0.0~beta")):
            with self.subTest(aid=aid, ver=ver):
                self.gh.files = runtime(aid, ver)
                self.gh.archive = source_archive(self.gh.files)
                with self.assertRaises(ValueError):
                    self.prepare()

    def test_baseline_production_and_fixture_are_untouched(self):
        before = self.store.baseline()
        self.prepare()
        self.assertEqual(before, self.store.baseline())
        for name, digest in before.items():
            self.assertEqual(lc.sha((self.out / "candidate" / name).read_bytes()), digest)
        self.assertFalse((self.root / "dist").exists())
        record = next((self.out / "candidate/incoming").glob("*-pending-review.json"))
        value = json.loads(record.read_text())
        self.assertFalse(value["fixture_only"])
        self.assertFalse(value["rights_approved"])
        self.assertFalse(value["release_approved"])
        for acceptance in value["compatibility"].values():
            self.assertFalse(acceptance["static_accepted"])
            self.assertFalse(acceptance["runtime_accepted"])

    def test_all_remote_writes_and_production_promotion_are_unavailable(self):
        self.enroll()
        for op in ("publish", "enroll", "push", "tag", "production", "release"):
            with self.subTest(op=op), self.assertRaisesRegex(ValueError, "Role denied"):
                self.call(op)
        for action in ("publish", "POST", "release", "../../../other"):
            with self.subTest(action=action), self.assertRaises(ValueError):
                self.call("github", action=action)
        self.assertFalse(any("zipball" in p for p in self.gh.calls))

    def test_wrong_roles_digest_revocation_and_unenrolled_task_fail(self):
        self.enroll()
        for operation, role in (("build", "kodi-addon-tester"), ("github", "kodi-release-reviewer"),
                                ("validate", "kodi-repo-manager"), ("review", "kodi-addon-tester")):
            with self.subTest(operation=operation), self.assertRaises(ValueError):
                self.call(operation, role)
        for task, digest in (("../escape", self.task["expected_digest"]), (self.task["task_id"], "0" * 64),
                             ("0" * 32, self.task["expected_digest"])):
            with self.assertRaises(ValueError):
                self.store.operate("inspect", "kodi-repo-manager", task, digest, {})
        (self.store.control / self.task["task_id"] / "revoked").write_text("revoked")
        with self.assertRaisesRegex(ValueError, "revoked"):
            self.call("inspect")

    def test_forged_binding_and_baseline_drift_rejected(self):
        self.enroll()
        (self.root / "config/production.json").write_text("{}")
        with self.assertRaisesRegex(ValueError, "baseline drift"):
            self.call("inspect")

    def test_source_package_record_and_config_mutation_rejected(self):
        for relative in ("source-data/default.py", "source-files.json", "source-archive.zip", "preparation.json",
                         "candidate/config/candidate.json", "candidate/incoming/plugin.video.independent-1.2.3.zip",
                         "candidate/incoming/plugin.video.independent-1.2.3-pending-review.json"):
            with self.subTest(relative=relative):
                self.prepare()
                path = self.out / relative
                path.write_bytes(path.read_bytes() + b" ")
                with self.assertRaises((ValueError, AssertionError)):
                    self.call("review", "kodi-release-reviewer")

    def test_linked_output_or_source_is_rejected(self):
        self.acquire()
        (self.out / "source-data/default.py").unlink()
        (self.out / "source-data/default.py").symlink_to(self.root / "docs/ARCHITECTURE.md")
        with self.assertRaisesRegex(ValueError, "Linked"):
            self.call("build", addon_subdir=".", runtime_files=list(runtime()))

    def test_ledger_existing_version_bytes_and_regression_block(self):
        ledger = self.root / "releases/manifest.json"
        original = json.loads(ledger.read_text())
        for old_version in ("1.2.3", "2.0.0"):
            ledger.write_text(json.dumps({**original, "packages": original["packages"] +
                [{"id": "plugin.video.independent", "version": old_version, "sha256": "0" * 64}]}))
            with self.assertRaises(ValueError):
                self.prepare()

    def test_generation_compare_and_write_rejects_stale_state(self):
        self.enroll()
        old = {"generation": 0, "stage": "enrolled", "validations": {}}
        self.call("github", action="acquire")
        with self.assertRaisesRegex(ValueError, "Stale task generation"):
            self.store.transition(self.task["binding"], old, "acquired")

    def test_list_is_bounded_get_for_enrolled_repository(self):
        self.enroll()
        result = self.call("github", action="list", resource="issues", page=2)
        self.assertEqual(len(result["items"]), 1)
        self.assertTrue(result["has_next_page"])
        self.assertFalse(result["exhaustive"])
        self.assertEqual(result["method"], "GET")
        with self.assertRaises(ValueError):
            self.call("github", action="list", resource="issues", page=6)

    def test_listing_rechecks_repository_id_before_get(self):
        self.enroll()
        self.gh.repo_id += 1
        with self.assertRaisesRegex(ValueError, "ID changed"):
            self.call("github", action="list", resource="issues")
        self.assertFalse(any("/issues?" in endpoint for endpoint in self.gh.calls))

    def test_malformed_state_and_journal_drift_fail_closed(self):
        self.enroll()
        state_path = self.store.control / self.task["task_id"] / "state.json"
        original = state_path.read_bytes()
        for state in ({"generation": 0, "stage": "production", "publication_authorized": True},
                      {"generation": 0, "stage": "enrolled", "validations": {}, "extra": True},
                      {"generation": 1, "stage": "enrolled", "validations": {}, "previous_state_sha256": "0" * 64}):
            with self.subTest(state=state):
                state_path.write_text(json.dumps(state))
                with self.assertRaises(ValueError):
                    self.call("inspect")
        state_path.write_bytes(original)
        self.assertEqual(self.call("inspect")["state"]["stage"], "enrolled")

    def test_toolchain_drift_and_task_expiry_reject(self):
        self.enroll()
        (self.root / "scripts/repository.py").write_text("# changed toolchain")
        with self.assertRaisesRegex(ValueError, "toolchain/version drift"):
            self.call("inspect")
        shutil.copyfile(ROOT / "scripts/repository.py", self.root / "scripts/repository.py")
        binding_path = self.store.control / self.task["task_id"] / "binding.json"
        binding = json.loads(binding_path.read_text())
        binding["expires_at"] = "2000-01-01T00:00:00Z"
        raw = repo.json_bytes(binding)
        binding_path.write_bytes(raw)
        self.task["expected_digest"] = lc.sha(raw)
        with self.assertRaisesRegex(ValueError, "Task expired"):
            self.call("inspect")

    def test_linked_task_output_root_rejected_before_temp_creation(self):
        self.enroll()
        outside = self.root / "outside"
        outside.mkdir()
        self.out.rmdir()
        self.out.symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "Linked|escapes scope"):
            self.call("github", action="acquire")
        self.assertEqual(list(outside.iterdir()), [])

    def test_bounded_source_reader_and_cross_task_path_rejection(self):
        self.acquire()
        result = self.call("inspect", file="default.py")
        self.assertTrue(result["untrusted_source_data"])
        self.assertIn("must never execute", result["text"])
        for name in ("../other/source.py", "/etc/passwd", "missing.py"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.call("inspect", file=name)

    def test_catalog_and_config_ledger_proposals_keep_approvals_pending(self):
        self.prepare()
        proposal = json.loads((self.out / "candidate/change-proposal.json").read_text())
        self.assertFalse(proposal["application_authorized"])
        self.assertEqual(proposal["proposed_retention_ledger"]["packages"][-1]["version"], "1.2.3")
        for lane in self.request["lanes"]:
            catalog = self.out / f"candidate/catalog-fragments/{lane}/addons.xml"
            parsed = audit_candidate.xml(catalog.read_bytes())
            self.assertEqual(parsed[0].get("id"), "plugin.video.independent")
        (self.out / "candidate/change-proposal.json").write_text("{}")
        with self.assertRaisesRegex(ValueError, "proposal changed"):
            self.call("review", "kodi-release-reviewer")

    def test_similarly_prefixed_addon_lanes_are_preserved(self):
        path = self.root / "config/production.json"
        config = json.loads(path.read_text())
        other = {"zip": "plugin.video.independent-helper-1.0.0.zip", "sha256": "f" * 64,
                 "lanes": ["nexus", "omega"], "review_record": "other.json", "review_record_sha256": "e" * 64}
        config["packages"].append(other)
        path.write_text(json.dumps(config))
        self.prepare()
        proposal = json.loads((self.out / "candidate/change-proposal.json").read_text())
        self.assertEqual(proposal["proposed_production_input"]["packages"][-2], other)

    def test_identical_published_artifact_is_not_appended_again(self):
        path = self.root / "releases/manifest.json"
        ledger = json.loads(path.read_text())
        ledger["packages"].append({"id": "plugin.video.independent", "version": "1.2.3", "sha256": lc.sha(repo.zip_bytes(runtime()))})
        path.write_text(json.dumps(ledger))
        with self.assertRaisesRegex(ValueError, "Already published identical"):
            self.prepare()

    def test_existing_nexus_static_cli_keeps_review_acceptance_false(self):
        self.prepare()
        cache = self.root / "cache"
        (cache / "manifest.json").write_text("{}")
        validation = {"branch": "nexus", "passed": True, "source_snapshot": {n: lc.sha(b) for n, b in runtime().items()},
                      "checks": {"official_checker": {"warnings": ["unverified URL"]}}}
        process = subprocess.CompletedProcess([], 0, stdout=json.dumps(validation), stderr="")
        with patch.object(lc.subprocess, "run", return_value=process) as run:
            result = self.call("validate", "kodi-addon-tester", lane="nexus")
            self.assertEqual(result["status"], "PASS")
            self.assertFalse(result["static_accepted"])
            self.assertFalse(result["native_tested"])
            self.assertEqual(result["validation"]["checks"]["official_checker"]["warnings"], ["unverified URL"])
            command = run.call_args.args[0]
            self.assertIn("kodi_agent_toolkit.cli", command)
            self.assertNotIn("HOME", run.call_args.kwargs["env"])
            self.assertNotIn("GH_TOKEN", run.call_args.kwargs["env"])
        self.assertEqual(self.call("validate", "kodi-addon-tester", lane="nexus"), result)
        reviewed = self.call("review", "kodi-release-reviewer")
        self.assertEqual(reviewed["static_evidence"]["nexus"]["status"], "PASS")
        (self.out / "validation/nexus.json").write_text("{}")
        with self.assertRaisesRegex(ValueError, "Validation receipt changed"):
            self.call("review", "kodi-release-reviewer")
        review = next((self.out / "candidate/incoming").glob("*-pending-review.json"))
        self.assertFalse(json.loads(review.read_text())["compatibility"]["nexus"]["static_accepted"])

    def test_redirects_only_allow_exact_pinned_codeload_origin(self):
        from urllib.request import Request
        handler = lc.Redirects(self.gh.name, self.gh.commit)
        request = Request("https://api.github.com/repos/x/y/zipball/" + self.gh.commit)
        for url in ("https://example.org/evil", "http://codeload.github.com/x/y", "https://codeload.github.com/other/repo/legacy.zip/" + self.gh.commit,
                    "https://codeload.github.com/" + self.gh.name + "/legacy.zip/" + self.gh.commit + "?token=x"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                handler.redirect_request(request, None, 302, "found", {}, url)

    def test_json_bridge_crosses_real_subprocess_and_rejects_role(self):
        self.prepare()
        request = {"task_id": self.task["task_id"], "expected_digest": self.task["expected_digest"], "arguments": {}}
        command = [sys.executable, "-I", "-B", str(self.root / "scripts/lifecycle_adapter.py"), "--operation", "review", "--role"]
        good = subprocess.run(command + ["kodi-release-reviewer"], input=json.dumps(request), text=True, capture_output=True)
        self.assertEqual(good.returncode, 0, good.stdout + good.stderr)
        self.assertEqual(json.loads(good.stdout)["package_sha256"], lc.sha(repo.zip_bytes(runtime())))
        bad = subprocess.run(command + ["kodi-addon-tester"], input=json.dumps(request), text=True, capture_output=True)
        self.assertEqual(bad.returncode, 1)
        self.assertEqual(json.loads(bad.stdout)["status"], "BLOCKED")

    def test_transport_uses_get_without_tokens_and_size_limit(self):
        class Response:
            status = 200
            headers = {}
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self, limit): return b"x" * limit
        class Opener:
            def open(self, request, timeout):
                self.request = request
                return Response()
        opener = Opener()
        with patch.object(lc, "build_opener", return_value=opener), patch.dict(os.environ, {"GH_TOKEN": "must-not-leak"}):
            with self.assertRaisesRegex(ValueError, "exceeds limit"):
                lc.GitHub()._get("repos/owner/repo", limit=100)
        self.assertEqual(opener.request.get_method(), "GET")
        self.assertIsNone(opener.request.get_header("Authorization"))

    def test_access_error_has_no_credential_fallback(self):
        from urllib.error import HTTPError
        with patch.object(lc, "build_opener") as make:
            make.return_value.open.side_effect = HTTPError("https://api.github.com/repos/x/y", 403, "Denied", {}, None)
            with self.assertRaisesRegex(ValueError, "BLOCKED.*403.*no credential fallback"):
                lc.GitHub()._get("repos/x/y")
            self.assertEqual(make.return_value.open.call_count, 1)

    def test_installer_binds_arbitrary_fresh_root_and_refuses_overwrite(self):
        fresh = self.root.parent / "fresh project"
        fresh.mkdir()
        shutil.copytree(ROOT / "scripts", fresh / "scripts")
        toolkit = self.root.parent / "trusted-toolkit"
        (toolkit / ".venv/bin").mkdir(parents=True)
        (toolkit / ".venv/bin/python").write_text("synthetic interpreter marker")
        plugin = self.root.parent / "plugin.js"
        plugin.write_text("trusted plugin marker")
        shared = self.root.parent / "shared"
        shared.mkdir()
        with patch.object(lc, "ROOT", fresh):
            result = lc.install(fresh, toolkit, plugin, shared)
            self.assertEqual(result["project_root"], str(fresh))
            local = json.loads((fresh / ".opencode/lifecycle-installation.json").read_text())
            self.assertEqual(local["toolkit"], str(toolkit))
            profile = (fresh / ".opencode/agents/kodi-repo-manager.md").read_text()
            self.assertNotIn("@PROJECT@", profile)
            self.assertNotIn("@TOOLKIT_PROJECT_RELATIVE@", profile)
            self.assertIn(os.path.relpath(toolkit, fresh), profile)
            before = (fresh / "opencode.json").read_bytes()
            with self.assertRaisesRegex(ValueError, "Existing profile"):
                lc.install(fresh, toolkit, plugin, shared)
            self.assertEqual(before, (fresh / "opencode.json").read_bytes())

    def test_toolkit_pin_drift_blocks_enrollment_and_validation(self):
        with patch.object(lc, "toolkit_identity", return_value={"synthetic": "changed"}):
            with self.assertRaisesRegex(ValueError, "Toolkit installation drift"):
                self.enroll()
        self.prepare()
        with patch.object(lc, "toolkit_identity", return_value={"synthetic": "changed"}):
            with self.assertRaisesRegex(ValueError, "Toolkit environment drift"):
                self.call("validate", "kodi-addon-tester", lane="nexus")

    def test_numeric_equivalent_version_cannot_be_an_update(self):
        path = self.root / "releases/manifest.json"
        ledger = json.loads(path.read_text())
        ledger["packages"].append({"id": "plugin.video.independent", "version": "1.2.3", "sha256": "0" * 64})
        path.write_text(json.dumps(ledger))
        self.gh.files = runtime(version="01.2.3")
        self.gh.archive = source_archive(self.gh.files)
        with self.assertRaisesRegex(ValueError, "does not increase"):
            self.prepare()


if __name__ == "__main__":
    unittest.main()

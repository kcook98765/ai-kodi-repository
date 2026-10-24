"""Real REST request shapes against finite in-memory mocked responses only."""
from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import publication_github as github
import publication_proposal as core

NOW = datetime(2026, 10, 24, 1, 0, tzinfo=timezone.utc)
MAIN = "1" * 40
PAGES = "2" * 40
TREE = "3" * 40
HEADS = {"main_sha": MAIN, "pages_sha": PAGES}
TAG = "script.ai.kodi.d3.fixture-1.0.0"
NAME = TAG + ".zip"
ENROLLED = {"mode": github.MODE, "repository": github.QUAL_REPOSITORY, "repository_id": 900001,
            "owner_id": 900002, "human_owner_id": 56806582, "origin": github.QUAL_ORIGIN,
            "app_id": 900003, "app_installation_id": 900004, "branch": "gh-pages", "path": "/"}
PREFIX = "/repos/" + github.QUAL_REPOSITORY


def credential(**permissions):
    return github.SimulatedCredential(900003, 900004, core.utc(NOW + timedelta(minutes=30)), permissions)


def exchange(method, path, value=None, *, status=200, body=None, binary=False, headers=None, upload=False, absolute=False):
    url = path if absolute else (github.UPLOADS if upload else github.API) + PREFIX + path
    response = github.MockResponse(status, value if binary else core.canonical(value), headers or {})
    return github.MockExchange(method, url, response, body)


def repo_response(**changes):
    value = {"id": 900001, "full_name": github.QUAL_REPOSITORY, "private": False,
             "owner": {"id": 900002, "login": "kcook98765-kodi-qualification", "type": "Organization"}}
    value.update(changes)
    return value


def ref_response(ref, sha):
    return {"ref": "refs/" + ref, "url": "ignored-safe-api-metadata", "object": {"type": "commit", "sha": sha, "url": "metadata"}}


def preflight():
    return [exchange("GET", "", repo_response()), exchange("GET", "/git/ref/heads/main", ref_response("heads/main", MAIN)),
            exchange("GET", "/git/ref/heads/gh-pages", ref_response("heads/gh-pages", PAGES))]


def asset(identity=7, name=NAME, data=b"frozen zip bytes"):
    return {"id": identity, "name": name, "state": "uploaded", "size": len(data), "digest": "sha256:" + core.sha(data)}


def draft(**changes):
    value = {"id": 5, "tag_name": TAG, "draft": True, "immutable": False, "name": "Reviewed fixture", "body": "Reviewed notes"}
    value.update(changes)
    return value


class GitHubTransportTests(unittest.TestCase):
    def client(self, exchanges, **changes):
        sender = github.ScriptedMockSender(exchanges)
        client = github.GitHubQualification(dict(ENROLLED, **changes), sender, clock=lambda: NOW)
        return client, sender

    def assert_no_mutations(self, sender):
        self.assertFalse(any(r["method"] not in ("GET", "HEAD") for r in sender.requests))

    def test_fixed_qualification_destination_rejects_production_and_aliases(self):
        cases = [{"repository": "kcook98765/ai-kodi-repository"}, {"repository_id": 1428864210},
                 {"repository_id": True}, {"owner_id": True}, {"human_owner_id": True},
                 {"origin": "https://kcook98765.github.io/other-project/"},
                 {"origin": github.QUAL_ORIGIN.replace("https://", "http://")},
                 {"origin": github.QUAL_ORIGIN + "../"}, {"origin": "https://user:secret@example.invalid/"},
                 {"branch": "main"}, {"path": "/docs"}, {"mode": "production"}]
        for changes in cases:
            with self.subTest(changes=changes), self.assertRaises(ValueError): self.client([], **changes)

    def test_concrete_mock_only_no_callable_or_network_fallback(self):
        with self.assertRaises(ValueError): github.GitHubQualification(ENROLLED, lambda *a: None)
        client, sender = self.client([])
        with patch("socket.socket", side_effect=AssertionError("No network")), \
             patch("subprocess.Popen", side_effect=AssertionError("No process")), self.assertRaisesRegex(ValueError, "Mock transport"):
            client.create_tag(credential(contents="write"), HEADS, TAG, MAIN)
        self.assert_no_mutations(sender)

    def test_arbitrary_origin_and_canonical_aliases_fail_before_any_request(self):
        aliases = ["https://attacker.example/", github.QUAL_ORIGIN.replace(".github.io/", ".github.io:443/"),
                   github.QUAL_ORIGIN.replace("kcook98765-kodi-qualification.github.io", "KCOOK98765-KODI-QUALIFICATION.GITHUB.IO"),
                   github.QUAL_ORIGIN.replace(".github.io/", ".github.io./"),
                   github.QUAL_ORIGIN.replace("/ai-kodi", "/%61i-kodi")]
        for origin in aliases:
            sender = github.ScriptedMockSender([])
            with self.subTest(origin=origin), self.assertRaisesRegex(ValueError, "Unenrolled qualification origin"):
                github.GitHubQualification(dict(ENROLLED, origin=origin), sender, clock=lambda: NOW)
            self.assertEqual(sender.requests, [])

    def test_per_operation_caps_expiry_and_installation_identity(self):
        client, sender = self.client([])
        credentials = [credential(contents="read"), credential(contents="write", actions="write"),
                       github.SimulatedCredential(900003, 900004, core.utc(NOW), {"contents": "write"}),
                       github.SimulatedCredential(900003, 900004, core.utc(NOW + timedelta(hours=2)), {"contents": "write"}),
                       github.SimulatedCredential(900003, 999, core.utc(NOW + timedelta(minutes=1)), {"contents": "write"})]
        for value in credentials:
            with self.subTest(value=value), self.assertRaises(ValueError): client.create_tag(value, HEADS, TAG, MAIN)
        self.assertEqual(sender.requests, [])
        self.assertNotIn("token", repr(credential(contents="write")).lower())

    def test_repository_numeric_identity_checked_before_write(self):
        for bad_id in (1428864210, True, 900009):
            client, sender = self.client([exchange("GET", "", repo_response(id=bad_id))])
            with self.assertRaises(ValueError): client.create_tag(credential(contents="write"), HEADS, TAG, MAIN)
            self.assert_no_mutations(sender)

    def test_stale_head_rejected_before_tag_creation(self):
        queue = preflight(); queue[1] = exchange("GET", "/git/ref/heads/main", ref_response("heads/main", "f" * 40))
        client, sender = self.client(queue)
        with self.assertRaisesRegex(ValueError, "concurrent"):
            client.create_tag(credential(contents="write"), HEADS, TAG, MAIN)
        self.assert_no_mutations(sender)

    def test_create_tag_shapes_and_real_response_extra_url(self):
        client, sender = self.client(preflight() + [exchange("GET", "/git/ref/tags/" + TAG, {}, status=404),
            exchange("POST", "/git/refs", ref_response("tags/" + TAG, MAIN), status=201,
                     body={"ref": "refs/tags/" + TAG, "sha": MAIN})])
        receipt = client.create_tag(credential(contents="write"), HEADS, TAG, MAIN)
        self.assertEqual(receipt["commit"], MAIN); self.assertFalse(receipt["production_authorized"])
        self.assertEqual([r["method"] for r in sender.requests].count("POST"), 1)
        self.assertEqual(sender.remaining, 0)

    def test_existing_tag_is_never_moved(self):
        client, sender = self.client(preflight() + [exchange("GET", "/git/ref/tags/" + TAG, ref_response("tags/" + TAG, MAIN))])
        with self.assertRaisesRegex(ValueError, "cannot be replaced"):
            client.create_tag(credential(contents="write"), HEADS, TAG, MAIN)
        self.assert_no_mutations(sender)

    def test_draft_release_explicit_commit_and_no_latest_override(self):
        body = {"tag_name": TAG, "target_commitish": MAIN, "name": "Reviewed fixture", "body": "Reviewed notes",
                "draft": True, "prerelease": False, "make_latest": "false"}
        queue = preflight() + [exchange("GET", "/git/ref/tags/" + TAG, ref_response("tags/" + TAG, MAIN)),
            exchange("GET", "/releases/tags/" + TAG, {}, status=404), exchange("POST", "/releases", draft(), status=201, body=body)]
        client, sender = self.client(queue)
        receipt = client.create_draft(credential(contents="write"), HEADS, TAG, MAIN, "Reviewed fixture", "Reviewed notes")
        self.assertEqual(receipt["id"], 5); self.assertEqual(sender.remaining, 0)

    def test_per_asset_upload_uses_fixed_upload_host(self):
        data = b"frozen zip bytes"
        queue = preflight() + [exchange("GET", "/releases/5", draft()),
            exchange("GET", "/releases/5/assets?per_page=100&page=1", []),
            exchange("POST", "/releases/5/assets?name=" + NAME, asset(data=data), status=201, body=data, upload=True)]
        client, sender = self.client(queue)
        value = client.upload_asset(credential(contents="write"), HEADS, 5, TAG, NAME, data, core.sha(data))
        self.assertEqual(value["sha256"], core.sha(data))
        self.assertTrue(sender.requests[-1]["url"].startswith(github.UPLOADS))
        self.assertEqual(sum(r["method"] == "POST" for r in sender.requests), 1)

    def test_asset_collision_refuses_clobber(self):
        queue = preflight() + [exchange("GET", "/releases/5", draft()),
                              exchange("GET", "/releases/5/assets?per_page=100&page=1", [asset()])]
        client, sender = self.client(queue)
        with self.assertRaisesRegex(ValueError, "collision"):
            client.upload_asset(credential(contents="write"), HEADS, 5, TAG, NAME, b"frozen zip bytes", core.sha(b"frozen zip bytes"))
        self.assert_no_mutations(sender)

    def test_asset_download_hash_and_safe_redirect_without_auth_forwarding(self):
        data = b"frozen zip bytes"; location = "https://release-assets.githubusercontent.com/safe/object?private=signed-value"
        client, sender = self.client([exchange("GET", "/releases/assets/7", asset()),
            exchange("GET", "/releases/assets/7", b"", status=302, binary=True, headers={"Location": location}),
            exchange("GET", location, data, binary=True, absolute=True)])
        receipt = client.download_asset(credential(contents="read"), 5, 7, NAME, core.sha(data), len(data))
        self.assertEqual(receipt["sha256"], core.sha(data))
        self.assertFalse(sender.requests[-1]["authenticated"])
        self.assertNotIn("signed-value", repr(sender.requests))

    def test_foreign_redirect_and_wrong_download_bytes_rejected(self):
        for scenario in ("redirect", "bytes"):
            queue = [exchange("GET", "/releases/assets/7", asset())]
            queue.append(exchange("GET", "/releases/assets/7", b"tampered", binary=True) if scenario == "bytes" else
                         exchange("GET", "/releases/assets/7", b"", status=302, binary=True, headers={"Location": "https://attacker.invalid/secret"}))
            client, sender = self.client(queue)
            with self.assertRaises(ValueError):
                client.download_asset(credential(contents="read"), 5, 7, NAME, core.sha(b"frozen zip bytes"), len(b"frozen zip bytes"))
            self.assert_no_mutations(sender)

    def test_changed_release_notes_reject_publication_before_patch(self):
        queue = preflight() + [exchange("GET", "/git/ref/tags/" + TAG, ref_response("tags/" + TAG, MAIN)),
                              exchange("GET", "/releases/5", draft(body="Altered unreviewed notes"))]
        client, sender = self.client(queue)
        with self.assertRaisesRegex(ValueError, "notes changed"):
            client.publish_release(credential(contents="write"), HEADS, 5, TAG, MAIN,
                                   {NAME: {"id": 7, "sha256": core.sha(b"frozen zip bytes"), "size": len(b"frozen zip bytes")}},
                                   name="Reviewed fixture", notes="Reviewed notes")
        self.assert_no_mutations(sender)

    def test_malformed_redirect_and_json_errors_do_not_echo_input(self):
        secret = "private-location-sentinel"
        client, sender = self.client([exchange("GET", "/releases/assets/7", asset()),
            exchange("GET", "/releases/assets/7", b"", status=302, binary=True,
                     headers={"Location": "https://release-assets.githubusercontent.com:" + secret + "/file"})])
        with self.assertRaises(ValueError) as caught:
            client.download_asset(credential(contents="read"), 5, 7, NAME, core.sha(b"frozen zip bytes"), len(b"frozen zip bytes"))
        self.assertNotIn(secret, str(caught.exception))
        for raw in (b'{"id":1,"id":2}', b'{"secret":"' + secret.encode() + b'"', b'not-json-' + secret.encode()):
            with self.assertRaises(ValueError) as caught: github.parse_json(raw)
            self.assertNotIn(secret, str(caught.exception))

    def test_publish_requires_complete_matching_assets_and_download_verification(self):
        data = b"frozen zip bytes"; planned = {NAME: {"id": 7, "sha256": core.sha(data), "size": len(data)}}
        queue = preflight() + [exchange("GET", "/git/ref/tags/" + TAG, ref_response("tags/" + TAG, MAIN)),
            exchange("GET", "/releases/5", draft()), exchange("GET", "/releases/5/assets?per_page=100&page=1", [asset()]),
            exchange("GET", "/releases/assets/7", asset()), exchange("GET", "/releases/assets/7", data, binary=True),
            exchange("PATCH", "/releases/5", draft(draft=False, immutable=True), body={"draft": False})]
        client, sender = self.client(queue)
        result = client.publish_release(credential(contents="write"), HEADS, 5, TAG, MAIN, planned,
                                        name="Reviewed fixture", notes="Reviewed notes")
        self.assertTrue(result["immutable"]); self.assertEqual(sender.requests[-1]["method"], "PATCH")

    def test_blob_tree_commit_one_effect_per_call(self):
        data = b"whole file"; blob = core.git_object("blob", data)
        client, sender = self.client(preflight() + [exchange("POST", "/git/blobs", {"sha": blob}, status=201,
            body={"encoding": "base64", "content": base64.b64encode(data).decode()})])
        self.assertEqual(client.create_blob(credential(contents="write"), HEADS, data, blob)["sha"], blob)
        self.assertEqual(sum(r["method"] == "POST" for r in sender.requests), 1)
        tree = core.git_tree({"index.html": data})
        client, sender = self.client(preflight() + [exchange("POST", "/git/trees", {"sha": tree, "truncated": False}, status=201,
            body={"tree": [{"path": "index.html", "mode": "100644", "type": "blob", "sha": blob}]})])
        self.assertEqual(client.create_tree(credential(contents="write"), HEADS, {"index.html": blob}, tree)["sha"], tree)
        target = core.git_commit(tree, PAGES, "Approved Pages")
        client, sender = self.client(preflight() + [exchange("POST", "/git/commits", {"sha": target, "tree": {"sha": tree}, "parents": [{"sha": PAGES}]}, status=201)])
        self.assertEqual(client.create_commit(credential(contents="write"), HEADS, tree, PAGES, "Approved Pages", target)["sha"], target)

    def test_pages_update_requires_exact_single_parent_and_force_false(self):
        target = "9" * 40
        queue = preflight() + [exchange("GET", "/git/commits/" + target, {"sha": target, "tree": {"sha": TREE}, "parents": [{"sha": PAGES}]}),
            exchange("PATCH", "/git/refs/heads/gh-pages", ref_response("heads/gh-pages", target), body={"sha": target, "force": False})]
        client, sender = self.client(queue)
        result = client.fast_forward_pages(credential(contents="write"), HEADS, target, PAGES, TREE)
        self.assertFalse(result["force"])
        client, sender = self.client(preflight() + [exchange("GET", "/git/commits/" + target,
            {"sha": target, "tree": {"sha": TREE}, "parents": [{"sha": PAGES}, {"sha": MAIN}]})])
        with self.assertRaisesRegex(ValueError, "unexpected parent"):
            client.fast_forward_pages(credential(contents="write"), HEADS, target, PAGES, TREE)
        self.assert_no_mutations(sender)

    def test_pages_preparation_preserves_old_packages_and_never_writes(self):
        old = b"immutable historical ZIP"; package_path = "packages/" + TAG + "/" + NAME
        queue = preflight() + [exchange("GET", "/git/commits/" + PAGES, {"sha": PAGES, "tree": {"sha": TREE}}),
            exchange("GET", "/git/trees/" + TREE + "?recursive=1", {"sha": TREE, "truncated": False, "tree": [
                {"path": package_path, "type": "blob", "mode": "100644", "sha": core.git_object("blob", old)}]})]
        client, sender = self.client(queue)
        result = client.prepare_pages(credential(contents="read"), HEADS, {package_path: old, "index.html": b"new reviewed index"})
        self.assertEqual(result["parent"], PAGES); self.assert_no_mutations(sender)
        client, sender = self.client(queue)
        with self.assertRaisesRegex(ValueError, "Historical package"):
            client.prepare_pages(credential(contents="read"), HEADS, {package_path: b"replace history"})
        self.assert_no_mutations(sender)

    def test_ledger_tree_uses_base_tree_and_only_reviewed_patch_paths(self):
        blob = "4" * 40; expected = "5" * 40
        body = {"base_tree": TREE, "tree": [{"path": "releases/manifest.json", "mode": "100644", "type": "blob", "sha": blob}]}
        client, sender = self.client(preflight() + [exchange("POST", "/git/trees", {"sha": expected, "truncated": False}, status=201, body=body)])
        result = client.create_tree(credential(contents="write"), HEADS, {"releases/manifest.json": blob}, expected, base_tree=TREE)
        self.assertEqual(result["sha"], expected)
        client, sender = self.client([])
        with self.assertRaises(ValueError):
            client.create_tree(credential(contents="write"), HEADS, {"README.md": blob}, expected, base_tree=TREE)
        self.assert_no_mutations(sender)

    def test_public_https_mock_checks_mime_hash_and_omits_auth(self):
        data = b"<addons />"; path = "catalogs/nexus/addons.xml"; url = github.QUAL_ORIGIN + path
        queue = [exchange("HEAD", url, b"", binary=True, absolute=True, headers={"Content-Type": "application/xml"}),
                 exchange("GET", url, data, binary=True, absolute=True, headers={"Content-Type": "application/xml"})]
        client, sender = self.client(queue)
        result = client.read_public(path, core.sha(data), mime="application/xml")
        self.assertEqual(result["size"], len(data)); self.assertTrue(all(not r["authenticated"] for r in sender.requests))

    def test_ledger_branch_and_pr_are_separate_effects_without_main_push(self):
        branch = "publication-ledger/" + "a" * 64; target = "b" * 40
        client, sender = self.client(preflight() + [exchange("GET", "/git/commits/" + target,
            {"sha": target, "parents": [{"sha": MAIN}], "tree": {"sha": TREE}}),
            exchange("GET", "/git/ref/heads/" + branch, {}, status=404),
            exchange("POST", "/git/refs", ref_response("heads/" + branch, target), status=201,
                     body={"ref": "refs/heads/" + branch, "sha": target})])
        self.assertEqual(client.create_ledger_branch(credential(contents="write"), HEADS, branch, target)["sha"], target)
        self.assertEqual(sum(r["method"] == "POST" for r in sender.requests), 1)
        result = {"number": 9, "state": "open", "head": {"ref": branch, "sha": target, "repo": {"id": 900001}},
                  "base": {"ref": "main", "sha": MAIN, "repo": {"id": 900001}}}
        client, sender = self.client(preflight() + [exchange("GET", "/git/ref/heads/" + branch, ref_response("heads/" + branch, target)),
            exchange("POST", "/pulls", result, status=201,
                     body={"title": "Retain exact release", "body": "Owner-reviewed ledger delta", "head": branch, "base": "main", "draft": False})])
        receipt = client.create_ledger_pr(credential(contents="read", pull_requests="write"), HEADS,
                                          branch, target, "Retain exact release", "Owner-reviewed ledger delta")
        self.assertEqual(receipt["state"], "PUBLIC_BUT_UNRECONCILED")
        self.assertEqual(sum(r["method"] == "POST" for r in sender.requests), 1)
        self.assertFalse(any(r["method"] == "PATCH" for r in sender.requests))

    def test_policy_details_require_bypass_visibility(self):
        queue = [exchange("GET", "", repo_response()), exchange("GET", "/rulesets?includes_parents=true&per_page=100&page=1", [{"id": 1}]),
                 exchange("GET", "/rulesets/1", {"id": 1, "name": "hidden-bypass", "target": "branch", "enforcement": "active",
                                                   "conditions": {}, "rules": []})]
        client, sender = self.client(queue)
        with self.assertRaisesRegex(ValueError, "visibility incomplete"):
            client.inspect_policy(credential(administration="read", actions="read", contents="read"))
        self.assert_no_mutations(sender)

    def test_optional_git_absence_requires_explicit_404(self):
        for method, suffix in (("read_blob", "/git/blobs/" + TREE),
                               ("read_tree", "/git/trees/" + TREE + "?recursive=1"),
                               ("read_commit", "/git/commits/" + TREE)):
            with self.subTest(method=method):
                client, sender = self.client([exchange("GET", suffix, {"message": "Not Found"}, status=404)])
                self.assertIsNone(getattr(client, method)(credential(contents="read"), TREE, absent=True))
                self.assert_no_mutations(sender)
                client, sender = self.client([exchange("GET", suffix, {}, status=404)])
                with self.assertRaises(ValueError): getattr(client, method)(credential(contents="read"), TREE)
                for status in (403, 500):
                    client, sender = self.client([exchange("GET", suffix, {}, status=status)])
                    with self.assertRaises(ValueError): getattr(client, method)(credential(contents="read"), TREE, absent=True)
                    self.assert_no_mutations(sender)

    def test_optional_git_reads_still_validate_normal_responses(self):
        blob = b"immutable blob"; identity = core.git_object("blob", blob)
        client, sender = self.client([exchange("GET", "/git/blobs/" + identity,
            {"sha": identity, "encoding": "base64", "content": base64.b64encode(blob).decode(), "size": len(blob)})])
        self.assertEqual(client.read_blob(credential(contents="read"), identity, expected_sha256=core.sha(blob), absent=True), blob)
        client, sender = self.client([exchange("GET", "/git/trees/" + TREE + "?recursive=1",
            {"sha": TREE, "truncated": False, "tree": []})])
        self.assertEqual(client.read_tree(credential(contents="read"), TREE, absent=True)["sha"], TREE)
        client, sender = self.client([exchange("GET", "/git/commits/" + MAIN,
            {"sha": MAIN, "tree": {"sha": TREE}, "parents": []})])
        self.assertEqual(client.read_commit(credential(contents="read"), MAIN, absent=True)["sha"], MAIN)
        client, sender = self.client([exchange("GET", "/git/trees/" + TREE + "?recursive=1",
            {"sha": TREE, "truncated": True, "tree": []})])
        with self.assertRaises(ValueError): client.read_tree(credential(contents="read"), TREE, absent=True)

    def test_lost_pr_response_lookup_is_scoped_unique_and_read_only(self):
        branch = "publication-ledger/" + "a" * 64; target = "b" * 40
        path = "/pulls?state=all&head=kcook98765-kodi-qualification%3Apublication-ledger%2F" + "a" * 64 + "&base=main&per_page=100&page=1"
        item = {"number": 9, "state": "open", "head": {"ref": branch, "sha": target, "repo": {"id": 900001}},
                "base": {"ref": "main", "sha": MAIN, "repo": {"id": 900001}}}
        client, sender = self.client([exchange("GET", path, [])])
        self.assertIsNone(client.find_ledger_pr(credential(pull_requests="read"), branch, target))
        self.assert_no_mutations(sender)
        client, sender = self.client([exchange("GET", path, [item])])
        self.assertEqual(client.find_ledger_pr(credential(pull_requests="read"), branch, target)["number"], 9)
        self.assert_no_mutations(sender)
        for records in ([item, item], [dict(item, head={"ref": branch, "sha": "f" * 40, "repo": {"id": 900001}})],
                        [dict(item, head={"ref": branch, "sha": target, "repo": {"id": 1428864210}})]):
            client, sender = self.client([exchange("GET", path, records)])
            with self.assertRaises(ValueError): client.find_ledger_pr(credential(pull_requests="read"), branch, target)
            self.assert_no_mutations(sender)

    def test_http_failure_redacts_untrusted_body_and_no_blind_retry(self):
        for status in (401, 403, 409, 422, 429, 500):
            client, sender = self.client([exchange("GET", "", {"message": "secret-body-token-value"}, status=status)])
            with self.subTest(status=status), self.assertRaises(ValueError) as caught:
                client.create_tag(credential(contents="write"), HEADS, TAG, MAIN)
            self.assertNotIn("secret-body-token-value", str(caught.exception)); self.assertEqual(len(sender.requests), 1)

    def test_pagination_outside_repo_and_incomplete_collection_rejected(self):
        client, sender = self.client([exchange("GET", "/releases/5/assets?per_page=100&page=1", [],
            headers={"Link": '<https://attacker.invalid/api>; rel="next"'})])
        with self.assertRaisesRegex(ValueError, "pagination"):
            client.read_assets(credential(contents="read"), 5)
        self.assert_no_mutations(sender)

    def test_no_arbitrary_method_endpoint_escape(self):
        client, sender = self.client([])
        for method, path in (("DELETE", "/releases/5"), ("POST", "/pages"), ("PATCH", "/git/refs/heads/main"),
                             ("GET", "/../../production"), ("POST", "/issues/1")):
            with self.subTest(method=method, path=path), self.assertRaises(ValueError):
                client._request(method, path, credential(contents="write"))
        self.assertEqual(sender.requests, [])


if __name__ == "__main__": unittest.main()

"""Consistent mock responses never authenticate a real human."""
import base64
import copy
from datetime import timedelta
from pathlib import Path
import tempfile
import unittest
from test_publication_d3_contract import build_d3_bundle, NOW, WORKFLOW
import publication_proposal as core
import publication_d3_contract as contract
import publication_github as github
import publication_owner as owner


def build_owner_observation(data, run_id=7001, now=NOW, *, pages=False):
    e = data["enrollment"]; x = data["execution"]
    head = data["payload"]["pages"]["commit"] if pages else x["expected"]["main_sha"]
    workflow_id = e["pages_workflow_id"] if pages else e["workflow_id"]; environment = contract.mock_environment(e, pages)
    repository = {"id": e["repository_id"], "full_name": e["repository"], "private": False,
                  "owner": {"id": e["owner_id"], "type": "Organization", "login": e["repository"].split("/")[0]}}
    raw = {"run": {"id": run_id, "workflow_id": workflow_id, "run_attempt": 1, "event": "push" if pages else "workflow_dispatch",
             "head_sha": head, "head_branch": "gh-pages" if pages else "main", "status": "completed", "conclusion": "success",
             "created_at": x["created_at"], "repository": repository,
             "actor": {"id": e["bot_user_id"], "login": e["bot_login"], "type": "Bot"}},
        "workflow": {"id": workflow_id, "path": "dynamic/pages/pages-build-deployment" if pages else e["workflow_path"], "state": "active"},
        "environment": environment, "environment_branches": [{"id": 1, "type": "branch", "name": "gh-pages" if pages else "main"}],
        "review_history": [{"state": "approved", "comment": owner.pages_comment(data, run_id) if pages else owner.approval_comment(data, run_id),
            "user": {"id": e["human_owner_id"], "type": "User", "login": "kcook98765"},
            "environments": [{"id": environment["id"], "name": environment["name"]}]}],
        "jobs": [{"id": 888, "name": "deploy" if pages else "owner-approval", "run_id": run_id, "run_attempt": 1,
                  "head_sha": head, "status": "completed", "conclusion": "success"}],
        "control_issue": {"number": e["control_issue_number"], "repository_url": github.API + "/repos/" + e["repository"]},
        "revocation_comments": [], "mock_only": True, "source": "scripted-mock-transport", "production_authorized": False}
    if not pages:
        archive = owner.scope_archive(owner.scope_document(data, run_id))
        raw.update(artifact_metadata={"id": 999, "name": owner.ARTIFACT_NAME, "expired": False,
            "size_in_bytes": len(archive), "digest": "sha256:" + core.sha(archive),
            "workflow_run": {"id": run_id, "repository_id": e["repository_id"], "head_repository_id": e["repository_id"],
                             "head_sha": head, "head_branch": "main"}}, artifact_archive=archive,
            workflow_file={"type": "file", "encoding": "base64", "content": base64.b64encode(WORKFLOW).decode(), "sha": core.git_object("blob", WORKFLOW)})
    return raw


def owner_exchanges(data, run_id=7001, *, observation=None, pages=False):
    raw = build_owner_observation(data, run_id, pages=pages) if observation is None else observation
    e = data["enrollment"]; prefix = github.API + "/repos/" + e["repository"]; result = []
    def add(path, value): result.append(github.MockExchange("GET", prefix + path, github.MockResponse.json(200, value)))
    add("", raw["run"]["repository"]); add(f"/actions/runs/{run_id}", raw["run"])
    add("/actions/workflows/" + str(e["pages_workflow_id"] if pages else e["workflow_id"]), raw["workflow"])
    env = "/environments/" + ("github-pages" if pages else e["environment_name"]); add(env, raw["environment"])
    add(env + "/deployment-branch-policies?per_page=100&page=1", {"total_count": len(raw["environment_branches"]), "branch_policies": raw["environment_branches"]})
    add(f"/actions/runs/{run_id}/approvals", raw["review_history"])
    add(f"/actions/runs/{run_id}/jobs?per_page=100&page=1", {"total_count": len(raw["jobs"]), "jobs": raw["jobs"]})
    if not pages:
        add(f"/actions/runs/{run_id}/artifacts?per_page=100&page=1", {"total_count": 1, "artifacts": [raw["artifact_metadata"]]})
        result.append(github.MockExchange("GET", prefix + "/actions/artifacts/" + str(raw["artifact_metadata"]["id"]) + "/zip", github.MockResponse(200, raw["artifact_archive"])))
        add("/contents/" + e["workflow_path"] + "?ref=" + e["workflow_commit"], raw["workflow_file"])
    add("/issues/" + str(e["control_issue_number"]), raw["control_issue"])
    add("/issues/" + str(e["control_issue_number"]) + "/comments?per_page=100&page=1", raw["revocation_comments"])
    return result


def make_verifier(data, observations=None, *, pages=False, run_id=7001):
    sender = github.ScriptedMockSender(owner_exchanges(data, run_id, observation=observations, pages=pages))
    transport = github.GitHubQualification(contract.transport_enrollment(data["enrollment"]), sender, clock=lambda: NOW)
    credential = github.SimulatedCredential(data["enrollment"]["app_id"], data["enrollment"]["app_installation_id"],
        core.utc(NOW + timedelta(hours=1)), {"actions": "read", "contents": "read", "administration": "read", "pull_requests": "read"})
    return owner.OwnerVerifier(data["enrollment"], transport, credential), sender


class OwnerProofTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.bundle = build_d3_bundle(Path(self.temp.name) / "case"); self.data = contract.load_bundle(self.bundle, now=NOW)

    def verify(self, raw=None, pages=False):
        verifier, sender = make_verifier(self.data, raw, pages=pages)
        value = verifier.verify_pages(self.data, 7001, now=NOW) if pages else verifier.verify(self.data, 7001, now=NOW)
        self.assertEqual(sender.remaining, 0); return value

    def test_actual_mock_http_boundary_has_no_live_owner_authority(self):
        value = self.verify(); self.assertEqual(value["status"], "MOCK_OWNER_PROOF_VERIFIED")
        for key in ("production_authorized", "network_authorized", "real_owner_authenticated"): self.assertFalse(value[key])

    def test_pages_requires_separate_owner_review(self):
        self.assertEqual(self.verify(pages=True)["status"], "MOCK_PAGES_OWNER_PROOF_VERIFIED")
        raw = build_owner_observation(self.data, pages=True); raw["review_history"] = []
        with self.assertRaises(ValueError): self.verify(raw, True)

    def test_successful_build_cannot_replace_a_skipped_deployment(self):
        raw = build_owner_observation(self.data, pages=True)
        raw["jobs"][0]["conclusion"] = "skipped"
        raw["jobs"].append({**raw["jobs"][0], "id": 889, "name": "build", "conclusion": "success"})
        with self.assertRaisesRegex(ValueError, "deployment job"): self.verify(raw, True)

    def test_typed_human_bot_organization_and_attempt_mismatch(self):
        changes = [lambda p: p["run"].update(run_attempt=2),
                   lambda p: p["run"]["actor"].update(id=self.data["enrollment"]["app_id"]),
                   lambda p: p["review_history"][0]["user"].update(type="Bot"),
                   lambda p: p["review_history"][0]["user"].update(id=self.data["enrollment"]["owner_id"]),
                   lambda p: p["run"]["repository"]["owner"].update(type="User")]
        for change in changes:
            raw = build_owner_observation(self.data); change(raw)
            with self.subTest(change=change), self.assertRaises(ValueError): self.verify(raw)

    def test_archive_hash_must_not_be_inner_scope_hash(self):
        raw = build_owner_observation(self.data)
        raw["artifact_metadata"]["digest"] = "sha256:" + core.sha(core.canonical(owner.scope_document(self.data, 7001)))
        with self.assertRaisesRegex(ValueError, "Archive"): self.verify(raw)

    def test_exact_comment_and_foreign_artifact_head_rejected(self):
        raw = build_owner_observation(self.data); raw["review_history"][0]["comment"] += "\n"
        with self.assertRaises(ValueError): self.verify(raw)
        raw = build_owner_observation(self.data); raw["artifact_metadata"]["workflow_run"]["head_repository_id"] += 1
        with self.assertRaises(ValueError): self.verify(raw)

    def test_gated_job_belongs_to_exact_run_head_attempt(self):
        for key, value in (("run_id", 42), ("head_sha", "f" * 40), ("run_attempt", True)):
            raw = build_owner_observation(self.data); raw["jobs"][0][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError): self.verify(raw)

    def test_revocation_is_typed_and_nonowner_spoof_ignored(self):
        raw = build_owner_observation(self.data)
        comment = {"id": 77, "user": {"id": self.data["enrollment"]["human_owner_id"], "type": "User"},
                   "body": f'REVOKE {self.data["digest"]} {self.data["execution"]["nonce"]}'}
        raw["revocation_comments"] = [comment]
        with self.assertRaises(owner.RevokedApproval) as raised: self.verify(raw)
        self.assertEqual(raised.exception.nonce, self.data["execution"]["nonce"])
        raw = build_owner_observation(self.data); comment = copy.deepcopy(comment); comment["user"]["id"] += 1
        raw["revocation_comments"] = [comment]; self.verify(raw)

    def test_environment_bypass_and_missing_control_issue_reject(self):
        raw = build_owner_observation(self.data); raw["environment"]["can_admins_bypass"] = True
        with self.assertRaises(ValueError): self.verify(raw)
        raw = build_owner_observation(self.data); raw["control_issue"]["number"] += 1
        with self.assertRaises(ValueError): self.verify(raw)

    def test_local_simulation_record_or_arbitrary_reader_cannot_authorize(self):
        with self.assertRaises(ValueError): owner.OwnerVerifier(self.data["enrollment"], object(), object())
        verifier, _ = make_verifier(self.data); altered = copy.deepcopy(self.data)
        altered["execution"]["mode"] = "local-simulation"
        with self.assertRaises(ValueError): verifier.verify(altered, 7001, now=NOW)

    def test_standalone_owner_interface_rejects_bad_digest_scope_nonce_lifetime(self):
        changes = [lambda d: d.update(digest="0" * 64),
                   lambda d: d["execution"].update(nonce="invalid"),
                   lambda d: d["execution"]["destination"].update(repository_id=contract.PRODUCTION_ID),
                   lambda d: d["execution"]["audience"].update(epoch=2),
                   lambda d: d["execution"].update(expires_at=core.utc(NOW + timedelta(hours=3))),
                   lambda d: d["payload"].update(campaign_id="f" * 32)]
        for index, change in enumerate(changes):
            data = copy.deepcopy(self.data); change(data)
            if index in (1, 2, 3, 4): data["digest"] = core.sha(core.canonical(data["execution"]))
            verifier, sender = make_verifier(data)
            with self.subTest(index=index), self.assertRaises(ValueError): verifier.verify(data, 7001, now=NOW)
            self.assertEqual(sender.requests, [])


if __name__ == "__main__": unittest.main()

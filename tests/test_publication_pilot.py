"""Disposable single-PR coordinator contracts; all remote responses are simulated."""
from __future__ import annotations

import copy
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import publication_pilot as pilot
import publication_proposal as frozen
from publication_fake import durable


class PilotJournalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "journal"
        self.identity = {"installation_uuid": "d" * 32, "epoch": 1, "enrollment_sha256": "e" * 64}
        self.journal = pilot.PilotJournal(self.root, self.identity)

    def bundle(self, letter="a", nonce="b", recovery=None):
        return {"digest": letter * 64, "execution": {"nonce": nonce * 32,
            "payload_sha256": "c" * 64, "review_sha256": "d" * 64, "pr": {"number": 1}, "recovery": recovery}}

    def test_nonce_and_review_are_consumed_durably_before_effect(self):
        data = self.bundle()
        with self.journal.lock():
            self.journal.claim(data, "0" * 64, owner_review_id=17)
            self.journal.update(data["digest"], pending="create_tag")
        restored = pilot.PilotJournal(self.root, self.identity)
        state = restored.load()
        self.assertEqual(state["used"]["b" * 32], "a" * 64)
        self.assertEqual(state["owner_reviews"]["17"], "a" * 64)
        self.assertEqual(state["transactions"]["a" * 64]["owner_review_id"], 17)
        with restored.lock(), self.assertRaisesRegex(ValueError, "nonce replay"):
            restored.claim(data, "0" * 64, owner_review_id=18)
        with restored.lock(), self.assertRaisesRegex(ValueError, "review replay"):
            restored.claim(self.bundle("f", "1"), "0" * 64, owner_review_id=17)

    def test_review_must_be_real_integer_not_bool_float_or_missing(self):
        for value in (None, True, 1.0, "1", 0):
            with self.subTest(value=value), self.journal.lock(), self.assertRaises(ValueError):
                self.journal.claim(self.bundle(), "0" * 64, owner_review_id=value)
        self.assertIsNone(self.journal.load()["active"])

    def test_old_mock_journal_cannot_be_relabelled_as_pilot(self):
        import publication_d3
        oldroot = Path(self.temp.name) / "old"
        publication_d3.QualificationJournal(oldroot, self.identity)
        with self.assertRaises(ValueError): pilot.PilotJournal(oldroot, self.identity)

    def test_missing_journal_and_torn_save_fail_closed(self):
        durable(self.root / "journal/0000000001.json", frozen.canonical({
            "generation": 1, "previous": "0" * 64, "state_sha256": "0" * 64}), exclusive=True)
        with self.assertRaisesRegex(ValueError, "generation mismatch"): self.journal.status()
        (self.root / "state.json").unlink()
        with self.assertRaisesRegex(ValueError, "missing journal"): pilot.PilotJournal(self.root, self.identity)

    def test_revocation_latch_survives_restart_and_deletion_is_detected(self):
        self.journal.latch_revocation("b" * 32, "f" * 64)
        restored = pilot.PilotJournal(self.root, self.identity)
        with self.assertRaisesRegex(ValueError, "revoked"): restored.check_revoked("b" * 32)
        (self.root / "revocations" / ("b" * 32 + ".json")).unlink()
        with self.assertRaisesRegex(ValueError, "inventory changed"): restored.status()

    def test_partial_blocks_next_release_and_requires_fresh_recovery(self):
        data = self.bundle()
        with self.journal.lock():
            self.journal.claim(data, "0" * 64, owner_review_id=17)
            self.journal.update(data["digest"], pending="create_tag")
            self.journal.fail(data["digest"])
            with self.assertRaisesRegex(ValueError, "Incomplete"):
                self.journal.claim(self.bundle("f", "1"), "0" * 64, owner_review_id=18)
        self.assertEqual(self.journal.load()["transactions"][data["digest"]]["status"], "UNKNOWN_REMOTE_STATE")
        recovery = {"transaction": data["digest"], "remote_state_sha256": "1" * 64, "completed": []}
        with self.journal.lock(), self.assertRaisesRegex(ValueError, "reconciliation"):
            self.journal.claim(self.bundle("f", "1", recovery), "1" * 64, owner_review_id=18)

    def test_recovery_preserves_receipts_and_owner_decisions(self):
        data = self.bundle()
        with self.journal.lock():
            self.journal.claim(data, "0" * 64, owner_review_id=17)
            self.journal.update(data["digest"], pending="create_tag")
            self.journal.update(data["digest"], receipt={"tag": "v1"}, completed="create_tag")
            state = self.journal.load(); state["transactions"][data["digest"]]["reconciled"] = True
            self.journal._save(state)
            recovery = {"transaction": data["digest"], "remote_state_sha256": "1" * 64, "completed": ["create_tag"]}
            self.journal.claim(self.bundle("f", "1", recovery), "1" * 64, owner_review_id=18)
        state = self.journal.load()
        self.assertEqual(len(state["used"]), 2); self.assertEqual(len(state["owner_reviews"]), 2)
        self.assertEqual(state["transactions"]["f" * 64]["receipts"]["create_tag"], {"tag": "v1"})

    def test_recorded_requires_exact_terminal_merge_and_no_pending(self):
        data = self.bundle()
        with self.journal.lock():
            self.journal.claim(data, "0" * 64, owner_review_id=17)
            with self.assertRaisesRegex(ValueError, "Unverified"): self.journal.finish(data["digest"])
            self.journal.update(data["digest"], completed="merge_ledger")
            self.journal.finish(data["digest"])
        self.assertIsNone(self.journal.status()["active"])

    def test_installation_epoch_symlink_and_stale_writer_are_rejected(self):
        with self.assertRaises(ValueError): pilot.PilotJournal(self.root, dict(self.identity, epoch=2))
        linked = Path(self.temp.name) / "linked"; linked.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(ValueError): pilot.PilotJournal(linked, self.identity)
        with self.journal.lock():
            state = self.journal.load(); self.journal.claim(self.bundle(), "0" * 64, owner_review_id=17)
            with self.assertRaisesRegex(ValueError, "Stale"): self.journal._save(state)



class PilotFlowTests(unittest.TestCase):
    def setUp(self):
        from test_publication_pilot_contract import build_pilot_material, test_enrollment, NOW
        import publication_pilot_contract as contract
        import publication_github_live as live
        import publication_pr_owner as owner
        from pilot_github_model import PilotGitHubModel, TestSigner, pilot_policy
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.now = NOW
        e = test_enrollment(NOW); e["policy_sha256"] = frozen.sha(frozen.canonical(pilot_policy(e)))
        e["identity_evidence"]["policy_sha256"] = e["policy_sha256"]
        self.path = build_pilot_material(self.root / "fixture", seal=False, enrollment=e)
        self.data = contract.load_material(self.path, now=NOW)
        self.model = PilotGitHubModel(self.data, now=NOW)
        self.backend = live.ScriptedHTTPS([])
        self.backend.send = self.model.send
        provider = live.AppTokenProvider(e, TestSigner(), self.backend, clock=lambda:self.now)
        self.transport = live.PilotGitHub(e, provider, self.backend, clock=lambda:self.now)
        verifier = owner.OwnerPRVerifier(e, self.transport)
        self.operator = pilot.PilotOperator(self.root / "journal", e, self.transport, verifier, clock=lambda:self.now, wait=self.advance_readiness)

    def advance_readiness(self, seconds):
        from datetime import timedelta
        self.now += timedelta(seconds=seconds)
        self.model.now = self.now

    def request(self):
        import publication_pilot_contract as contract
        result = self.operator.request(self.path, self.data["digest"])
        self.data = contract.load_material(self.path, result["proposal_sha256"], now=self.now)
        self.model.bind(self.data)
        return result

    def approve(self, review_id=7600):
        self.model.approve(self.data, review_id=review_id)

    def test_staging_is_metadata_only_and_does_not_consume_owner_authority(self):
        result = self.request()
        self.assertEqual(result["status"], "AWAITING_OWNER_APPROVAL")
        self.assertEqual(self.model.refs["heads/main"], self.data["payload"]["expected"]["main_sha"])
        self.assertEqual(self.model.refs["heads/gh-pages"], self.data["payload"]["expected"]["pages_sha"])
        self.assertEqual(self.model.releases, {})
        self.assertFalse(any(ref.startswith("tags/") for ref in self.model.refs))
        state = self.operator.journal.load()
        self.assertEqual(state["used"], {}); self.assertEqual(state["owner_reviews"], {})
        self.assertTrue(all(c["path"] in {"/git/blobs", "/git/trees", "/git/commits", "/git/refs", "/pulls", "/pulls/1"}
                            for c in self.model.mutations))

    def test_full_single_review_pilot_records_and_replay_has_zero_effects(self):
        self.request(); self.approve()
        result = self.operator.execute(self.path, self.data["digest"])
        self.assertEqual(result["status"], "RECORDED"); self.assertTrue(result["mock_only"])
        self.assertFalse(result["production_authorized"])
        self.assertIsNone(self.operator.status()["active"])
        before = len(self.model.mutations)
        with self.assertRaisesRegex(ValueError, "nonce replay"):
            self.operator.execute(self.path, self.data["digest"])
        self.assertEqual(len(self.model.mutations), before)
        self.assertEqual(sum(c["method"] == "PUT" for c in self.model.mutations), 1)

    def test_unapproved_request_cannot_create_release(self):
        self.request(); before = len(self.model.mutations)
        with self.assertRaisesRegex(ValueError, "approval absent"):
            self.operator.execute(self.path, self.data["digest"])
        self.assertEqual(len(self.model.mutations), before)

    def test_missing_separate_metadata_grant_has_zero_remote_effects(self):
        (self.path / "preparation.json").unlink()
        with self.assertRaisesRegex(ValueError, "preparation grant is missing"):
            self.operator.request(self.path)
        self.assertEqual(self.model.calls, [])
        self.assertFalse((self.path / "preparation.json").exists())

    def test_dismissal_during_publication_latches_and_stops_next_effect(self):
        self.request(); self.approve()
        def dismiss(model, method, path):
            if path == "/git/refs": model.reviews[1][-1]["state"] = "DISMISSED"
        self.model.after_effect = dismiss
        with self.assertRaisesRegex(ValueError, "revoked or dismissed"):
            self.operator.execute(self.path, self.data["digest"])
        self.assertEqual(self.model.releases, {})
        with self.assertRaisesRegex(ValueError, "revoked"):
            self.operator.journal.check_revoked(self.data["execution"]["nonce"])

    def test_expiry_after_tag_cannot_authorize_another_effect(self):
        from datetime import timedelta
        self.request(); self.approve()
        def expire(model, method, path):
            if path == "/git/refs": self.now += timedelta(hours=2)
        self.model.after_effect = expire
        with self.assertRaisesRegex(ValueError, "expired"):
            self.operator.execute(self.path, self.data["digest"])
        self.assertEqual(self.model.releases, {})

    def test_policy_or_heads_changed_after_tag_stops_publication(self):
        self.request(); self.approve()
        def change(model, method, path):
            if path == "/git/refs": model.policy["rulesets"][0]["enforcement"] = "disabled"
        self.model.after_effect = change
        with self.assertRaisesRegex(ValueError, "policy changed|Unsafe ruleset"):
            self.operator.execute(self.path, self.data["digest"])
        self.assertEqual(self.model.releases, {})

    def test_failed_actual_deployment_keeps_main_unchanged(self):
        self.request(); self.approve(); self.model.deploy_failed = True
        main = self.model.refs["heads/main"]
        with self.assertRaisesRegex(ValueError, "workflow identity/result mismatch|jobs unverified|Pages deployment run failed"):
            self.operator.execute(self.path, self.data["digest"])
        self.assertEqual(self.model.refs["heads/main"], main)
        self.assertIsNotNone(self.operator.status()["active"])
        self.assertTrue(any(not r["draft"] for r in self.model.releases.values()))

    def test_lost_tag_response_reconcile_is_read_only_and_needs_fresh_authority(self):
        self.request(); self.approve(); self.model.loss_after = ("POST", "/git/refs")
        with self.assertRaises(ValueError): self.operator.execute(self.path, self.data["digest"])
        effects = len(self.model.mutations)
        result = self.operator.reconcile(self.path, self.data["digest"])
        self.assertEqual(len(self.model.mutations), effects)
        self.assertEqual(result["status"], "RECONCILED_NEEDS_FRESH_OWNER_APPROVAL")
        self.assertEqual(result["recovery"]["completed"], ["create_tag"])
        with self.assertRaisesRegex(ValueError, "nonce replay"):
            self.operator.execute(self.path, self.data["digest"])

    def test_lost_merge_response_can_only_be_observed_and_recorded(self):
        self.request(); self.approve(); self.model.loss_after = ("PUT", "/pulls/1/merge")
        with self.assertRaises(ValueError): self.operator.execute(self.path, self.data["digest"])
        effects = len(self.model.mutations)
        self.assertEqual(self.operator.reconcile(self.path, self.data["digest"])["status"], "RECORDED")
        self.assertEqual(len(self.model.mutations), effects)
        self.assertIsNone(self.operator.status()["active"])

    def test_lost_metadata_response_requires_read_only_reconciliation(self):
        self.model.loss_after = ("POST", "/git/blobs")
        with self.assertRaises(ValueError): self.request()
        count = len(self.model.mutations)
        with self.assertRaisesRegex(ValueError, "GET-only reconciliation"):
            self.operator.request(self.path)
        self.assertEqual(len(self.model.mutations), count)
        self.operator.reconcile_request(self.path)
        self.assertEqual(len(self.model.mutations), count)
        self.request()
        self.assertEqual(self.model.releases, {})

    def test_metadata_scope_cannot_create_a_tag(self):
        from publication_github_live import BoundScope
        p = self.data["payload"]
        with self.assertRaisesRegex(ValueError, "outside exact frozen authority"):
            self.transport.create_tag(BoundScope(self.path, "preparation"), self.operator._heads(self.data),
                                      p["release"]["tag"], p["release"]["commit"])
        self.assertEqual(self.model.mutations, [])

    def test_update_1_1_retains_1_0_assets_and_installer_bytes(self):
        import publication_pilot_contract as contract
        from test_publication_pilot_contract import build_pilot_material
        self.request(); self.approve(); first = self.operator.execute(self.path, self.data["digest"])
        old_assets = copy.deepcopy(self.model.asset_bytes)
        old_public = {n: b for n, b in self.model.published_files.items() if n.endswith((".zip", ".zip.sha256"))}
        oldpath = self.path
        self.path = build_pilot_material(self.root / "update", version="1.1.0", previous=oldpath,
            now=self.now, seal=False, main_head=first["merge_sha"], enrollment=self.data["enrollment"])
        self.data = contract.load_material(self.path, now=self.now); self.model.bind(self.data)
        self.request(); self.approve(review_id=7601)
        historical = self.model.releases[1]
        saved_assets = copy.deepcopy(historical["assets"]); saved_name = historical["name"]
        before = len(self.model.mutations)
        sidecar = next(a for a in historical["assets"] if a["name"].endswith(".sha256"))
        historical["assets"].remove(sidecar)
        with self.assertRaisesRegex(ValueError, "Historical Release"):
            self.operator.execute(self.path, self.data["digest"])
        self.assertEqual(len(self.model.mutations), before)
        historical["assets"] = copy.deepcopy(saved_assets)
        next(a for a in historical["assets"] if a["name"].endswith(".sha256"))["digest"] = "sha256:" + "a" * 64
        with self.assertRaisesRegex(ValueError, "Historical Release"):
            self.operator.execute(self.path, self.data["digest"])
        self.assertEqual(len(self.model.mutations), before)
        historical["assets"] = copy.deepcopy(saved_assets); historical["name"] = "Altered historical disclosure"
        with self.assertRaisesRegex(ValueError, "Historical Release"):
            self.operator.execute(self.path, self.data["digest"])
        self.assertEqual(len(self.model.mutations), before)
        historical["name"] = saved_name
        self.assertEqual(self.operator.execute(self.path, self.data["digest"])["status"], "RECORDED")
        for identity, raw in old_assets.items(): self.assertEqual(self.model.asset_bytes[identity], raw)
        for name, raw in old_public.items(): self.assertEqual(self.model.published_files[name], raw)
        self.assertEqual(len(self.model.releases), 2)

    def recover_material(self, recovery):
        import shutil
        from unittest.mock import patch
        import publication_cli as cli
        import publication_pilot_contract as contract
        from test_publication_pilot_contract import metadata_authorization
        out = self.root / "recovery-task"; fixed = out / "publication-pilot/material"
        shutil.copytree(self.path, fixed); old_digest = self.data["digest"]
        self.operator._pilot_context = {"root": self.root, "config": {}, "private": {}, "private_sha": "a" * 64, "binding": {}}
        def issue(root, config, private, private_sha, binding, output, *, material=None):
            expected = out / "publication-pilot/recoveries" / old_digest / "material"
            self.assertEqual(material, expected)
            data = contract.load_material(material, now=self.now)
            contract.preparation_grant(material, authorization=metadata_authorization(data, self.now), now=self.now)
            return material
        request = {"operation": "request", "task_id": self.data["payload"]["task"]["id"],
                   "expected_digest": self.data["payload"]["task"]["sha256"]}
        with patch.object(cli, "issue_staging_grant", side_effect=issue):
            result = cli.dispatch_operator(self.operator, request, out)
        self.path = out / "publication-pilot/recoveries" / old_digest / "material"
        self.data = contract.load_material(self.path, result["proposal_sha256"], now=self.now); self.model.bind(self.data)
        self.assertEqual(self.data["execution"]["recovery"], recovery)

    def test_lost_pages_ref_recovers_only_with_fresh_execution_and_new_review(self):
        self.request(); self.approve(); old_digest = self.data["digest"]
        self.model.loss_after = ("PATCH", "/git/refs/heads/gh-pages")
        with self.assertRaises(ValueError): self.operator.execute(self.path, old_digest)
        effects = len(self.model.mutations)
        recovery = self.operator.reconcile(self.path, old_digest)["recovery"]
        self.assertEqual(len(self.model.mutations), effects); self.assertIn("promote_pages", recovery["completed"])
        self.recover_material(recovery); self.assertNotEqual(self.data["digest"], old_digest)
        with self.assertRaisesRegex(ValueError, "stale|exact execution digest"):
            self.operator.execute(self.path, self.data["digest"])
        self.approve(review_id=7601)
        self.assertEqual(self.operator.execute(self.path, self.data["digest"])["status"], "RECORDED")
        state = self.operator.journal.load()
        self.assertEqual(len(state["used"]), 2); self.assertEqual(len(state["owner_reviews"]), 2)
        self.assertEqual(sum(c["path"] == "/git/refs/heads/gh-pages" and c["method"] == "PATCH" for c in self.model.mutations), 1)

    def test_cli_fixed_task_material_request_and_status(self):
        import shutil
        import publication_cli as cli
        import publication_pilot_contract as contract
        out = self.root / "task-output"; fixed = out / "publication-pilot/material"
        shutil.copytree(self.path, fixed); self.path = fixed
        self.data = contract.load_material(fixed, now=self.now); self.model.bind(self.data)
        request = {"operation": "request", "task_id": self.data["payload"]["task"]["id"],
                   "expected_digest": self.data["payload"]["task"]["sha256"]}
        result = cli.dispatch_operator(self.operator, request, out)
        self.assertEqual(result["status"], "AWAITING_OWNER_APPROVAL")
        request["operation"] = "status"
        self.assertEqual(cli.dispatch_operator(self.operator, request, out)["material"]["proposal_sha256"], result["proposal_sha256"])
        request["expected_digest"] = "a" * 64
        with self.assertRaisesRegex(ValueError, "task binding changed"): cli.dispatch_operator(self.operator, request, out)

    def test_cli_configured_factory_has_zero_network_and_lazy_key(self):
        import publication_cli as cli
        from unittest.mock import patch
        import publication_github_live as live
        e = copy.deepcopy(self.data["enrollment"]); e["identity_evidence"]["kind"] = "github-readback"
        config = {"remote_enabled": True, "enrollment": e, "installation_uuid": e["installation_uuid"], "epoch": e["epoch"]}
        private = {"key_file": str(self.root / "missing-private-key")}
        with patch.object(live.HTTPSBackend, "send", side_effect=AssertionError("network forbidden")):
            operator = cli.configured_operator(self.root / "project", config, private, "a" * 64, {}, self.root / "out")
        self.assertEqual(operator.status()["mode"], pilot.MODE)
        self.assertFalse((self.root / "missing-private-key").exists())

    def test_late_revoke_during_write_token_mint_is_latched_before_tag(self):
        from urllib.parse import urlsplit
        self.request(); self.approve(); before = len(self.model.mutations)
        self.transport.provider._tokens.clear()
        def wire(method, url, headers, raw, **kwargs):
            response = self.model.send(method, url, headers, raw, **kwargs)
            if method == "POST" and urlsplit(url).path.endswith("/access_tokens"):
                if frozen.strict_load(raw)["permissions"].get("contents") == "write": self.model.revoke(self.data)
            return response
        self.backend.send = wire
        with self.assertRaisesRegex(ValueError, "revoked or dismissed"):
            self.operator.execute(self.path, self.data["digest"])
        self.assertEqual(len(self.model.mutations), before)
        with self.assertRaisesRegex(ValueError, "revoked"):
            self.operator.journal.check_revoked(self.data["execution"]["nonce"])

    def test_cli_reconcile_before_execution_seal_is_metadata_get_only(self):
        import shutil
        import publication_cli as cli
        import publication_pilot_contract as contract
        out = self.root / "metadata-task"; fixed = out / "publication-pilot/material"
        shutil.copytree(self.path, fixed); self.path = fixed
        self.data = contract.load_material(fixed, now=self.now); self.model.bind(self.data)
        request = {"operation": "request", "task_id": self.data["payload"]["task"]["id"],
                   "expected_digest": self.data["payload"]["task"]["sha256"]}
        self.model.loss_after = ("POST", "/git/blobs")
        with self.assertRaises(ValueError): cli.dispatch_operator(self.operator, request, out)
        request.update(operation="reconcile", proposal_sha256=self.data["payload_sha256"])
        before = len(self.model.mutations)
        self.assertEqual(cli.dispatch_operator(self.operator, request, out)["status"], "RECONCILED_METADATA_REQUEST")
        self.assertEqual(len(self.model.mutations), before)
        request["operation"] = "request"; request.pop("proposal_sha256")
        self.assertEqual(cli.dispatch_operator(self.operator, request, out)["status"], "AWAITING_OWNER_APPROVAL")

    def test_cli_status_freezes_complete_read_only_source_and_site_inputs_once(self):
        import publication_cli as cli
        out = self.root / "status-task"
        self.operator._pilot_context = {"root": self.root, "config": {}, "private": {}, "private_sha": "a" * 64,
            "binding": {"source": {"commit": self.data["payload"]["source"]["commit"]}}}
        request = {"operation": "status", "task_id": self.data["payload"]["task"]["id"],
                   "expected_digest": self.data["payload"]["task"]["sha256"]}
        result = cli.dispatch_operator(self.operator, request, out)
        path = out / "publication-pilot/inputs.json"; raw = frozen.safe_read(path); inputs = frozen.strict_load(raw)
        self.assertEqual(result["inputs_sha256"], frozen.sha(raw)); self.assertEqual(self.model.mutations, [])
        self.assertIn(".github/CODEOWNERS", inputs["main_files"])
        self.assertIn(self.data["enrollment"]["validation_workflow_path"], inputs["main_files"])
        self.assertEqual(inputs["source_commit"], self.data["payload"]["source"]["commit"])
        calls = len(self.model.calls)
        self.assertEqual(cli.dispatch_operator(self.operator, request, out)["inputs_sha256"], result["inputs_sha256"])
        self.assertEqual(len(self.model.calls), calls); self.assertEqual(frozen.safe_read(path), raw)


    def test_queued_pages_and_public_404_reach_recorded_with_one_approval(self):
        from urllib.parse import urlsplit
        import publication_github_live as live
        self.request(); self.approve(); waits = []
        def advance(seconds):
            waits.append(seconds); self.advance_readiness(seconds)
        self.operator.wait = advance
        workflow = "/actions/workflows/" + str(self.data["enrollment"]["pages_workflow_id"]) + "/runs"
        def wire(method, url, headers, raw, **kwargs):
            response = self.model.send(method, url, headers, raw, **kwargs)
            parsed = urlsplit(url)
            if method == "GET" and parsed.path.endswith(workflow) and not waits:
                value = frozen.strict_load(response.body)
                value["workflow_runs"][0].update(status="queued", conclusion=None)
                return live.HTTPResponse.json(200, value)
            if parsed.hostname == "kcook98765-kodi-qualification.github.io" and len(waits) == 1:
                return live.HTTPResponse(404, b"", {})
            return response
        self.backend.send = wire
        result = self.operator.execute(self.path, self.data["digest"])
        self.assertEqual(result["status"], "RECORDED"); self.assertEqual(waits, [5, 5])
        state = self.operator.journal.load()
        self.assertEqual(len(state["used"]), 1); self.assertEqual(len(state["owner_reviews"]), 1)
        history = state["transactions"][self.data["digest"]]["readiness_history"]
        self.assertEqual([v["reason"] for v in history if v["status"] == "PENDING"], ["pages", "public_bytes"])
        self.assertEqual(sum(c["method"] == "PUT" for c in self.model.mutations), 1)
        self.assertEqual(sum(c["path"] == "/git/refs/heads/gh-pages" for c in self.model.mutations), 1)


class PilotReadinessTests(unittest.TestCase):
    """Scheduling tests complement serialized HTTP qualification."""
    def setUp(self):
        from datetime import timedelta
        from unittest.mock import Mock, patch
        from test_publication_pilot_contract import NOW
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.now = NOW; self.waits = []; self.revoked = False
        timer = patch.object(pilot.time, "monotonic", lambda:(self.now - NOW).total_seconds())
        timer.start(); self.addCleanup(timer.stop)
        self.op = object.__new__(pilot.PilotOperator); self.op.clock = lambda:self.now; self.op.wait = self.wait
        self.op.journal = pilot.PilotJournal(Path(self.temp.name) / "journal", {
            "installation_uuid": "d" * 32, "epoch": 1, "enrollment_sha256": "e" * 64})
        self.data = {"digest": "a" * 64, "execution": {"nonce": "b" * 32, "payload_sha256": "c" * 64,
            "review_sha256": "d" * 64, "recovery": None, "pr": {"number": 1},
            "created_at": frozen.utc(NOW), "expires_at": frozen.utc(NOW + timedelta(hours=1))}}
        with self.op.journal.lock(): self.op.journal.claim(self.data, "0" * 64, owner_review_id=17)
        def fresh(path, data): frozen.require(self.now < frozen.timestamp(data["execution"]["expires_at"]), "execution expired")
        def owner(data):
            frozen.require(not self.revoked, "owner revoked")
            return {"review_id": 17}
        self.op._fresh = fresh; self.op._owner = owner; self.op._public = Mock()
        self.op._effect = Mock(side_effect=AssertionError("Readiness must never retry a write"))

    def wait(self, seconds):
        from datetime import timedelta
        self.waits.append(seconds); self.now += timedelta(seconds=seconds)

    def test_pending_pages_and_public_bytes_eventually_verify(self):
        from publication_github_live import PendingPagesReadiness, PendingPublicBytes
        self.op._public.side_effect = [PendingPagesReadiness("queued"), PendingPublicBytes("old site"), None]
        with self.op.journal.lock(): self.op._await_public(Path(self.temp.name), self.data, {})
        self.assertEqual(self.waits, [5, 5]); self.assertEqual(self.op._public.call_count, 3)
        tx = self.op.journal.load()["transactions"][self.data["digest"]]
        self.assertEqual([v["status"] for v in tx["readiness_history"] if v["status"] != "OBSERVING"],
                         ["PENDING", "PENDING", "VERIFIED"])
        self.op._effect.assert_not_called()

    def test_pending_timeout_is_bounded_and_never_verifies(self):
        from publication_github_live import PendingPagesReadiness
        self.op._public.side_effect = PendingPagesReadiness("queued")
        with self.op.journal.lock(), self.assertRaisesRegex(ValueError, "readiness deadline"):
            self.op._await_public(Path(self.temp.name), self.data, {})
        self.assertEqual(sum(self.waits), 120); self.assertEqual(self.op._public.call_count, 24)
        self.assertEqual(self.op.journal.load()["transactions"][self.data["digest"]]["readiness"]["status"], "TIMED_OUT")
        self.op._effect.assert_not_called()

    def test_execution_expiry_shortens_readiness_budget(self):
        from datetime import timedelta
        from publication_github_live import PendingPagesReadiness
        self.data["execution"]["expires_at"] = frozen.utc(self.now + timedelta(seconds=7))
        self.op._public.side_effect = PendingPagesReadiness("building")
        with self.op.journal.lock(), self.assertRaisesRegex(ValueError, "readiness deadline"):
            self.op._await_public(Path(self.temp.name), self.data, {})
        self.assertEqual(self.waits, [5, 2]); self.assertEqual(self.op._public.call_count, 2)
        self.op._effect.assert_not_called()

    def test_revocation_during_wait_stops_before_another_public_read(self):
        from publication_github_live import PendingPagesReadiness
        self.op._public.side_effect = PendingPagesReadiness("queued")
        def revoke(seconds): self.wait(seconds); self.revoked = True
        self.op.wait = revoke
        with self.op.journal.lock(), self.assertRaisesRegex(ValueError, "revoked"):
            self.op._await_public(Path(self.temp.name), self.data, {})
        self.assertEqual(self.op._public.call_count, 1); self.assertEqual(self.waits, [5])
        self.op._effect.assert_not_called()

    def test_failed_or_unsafe_observation_is_not_a_pending_retry(self):
        self.op._public.side_effect = ValueError("failed deployment or unsafe response")
        with self.op.journal.lock(), self.assertRaisesRegex(ValueError, "failed deployment"):
            self.op._await_public(Path(self.temp.name), self.data, {})
        self.assertEqual(self.waits, []); self.assertEqual(self.op._public.call_count, 1)
        self.op._effect.assert_not_called()

    def test_different_review_after_wait_is_not_consumed_authority(self):
        from publication_github_live import PendingPagesReadiness
        self.op._public.side_effect = PendingPagesReadiness("queued")
        self.op._owner = lambda data:{"review_id": 18 if self.waits else 17}
        with self.op.journal.lock(), self.assertRaisesRegex(ValueError, "Consumed owner decision changed"):
            self.op._await_public(Path(self.temp.name), self.data, {})
        self.assertEqual(self.op._public.call_count, 1); self.op._effect.assert_not_called()

    def test_late_success_never_becomes_pass_after_deadline(self):
        from datetime import timedelta
        def late(data, heads): self.now += timedelta(seconds=121)
        self.op._public.side_effect = late
        with self.op.journal.lock(), self.assertRaisesRegex(ValueError, "after its readiness deadline"):
            self.op._await_public(Path(self.temp.name), self.data, {})
        self.assertEqual(self.waits, []); self.op._effect.assert_not_called()

    def test_recheck_and_restart_retain_the_first_readiness_deadline(self):
        from datetime import timedelta
        from publication_github_live import PendingPagesReadiness
        with self.op.journal.lock(): self.op._await_public(Path(self.temp.name), self.data, {})
        original = self.op.journal.load()["transactions"][self.data["digest"]]["readiness"]
        self.now += timedelta(seconds=115)
        del self.op._readiness_wall_deadlines
        self.op._public.side_effect = PendingPagesReadiness("queued again")
        with self.op.journal.lock(), self.assertRaisesRegex(ValueError, "readiness deadline"):
            self.op._await_public(Path(self.temp.name), self.data, {})
        final = self.op.journal.load()["transactions"][self.data["digest"]]["readiness"]
        self.assertEqual(self.waits, [5]); self.assertEqual(final["deadline"], original["deadline"])
        self.assertEqual(final["attempts"], 2); self.op._effect.assert_not_called()


if __name__ == "__main__":
    unittest.main()

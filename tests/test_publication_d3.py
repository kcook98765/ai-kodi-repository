"""D3 durable state is local, single-use and independent of ambient credentials."""
from __future__ import annotations

import copy
from pathlib import Path
import sys
import tempfile
import unittest
from datetime import timedelta
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import publication_d3 as d3
import publication_proposal as frozen
from publication_fake import durable
import publication_d3_contract as contract
import publication_github as github
import publication_owner as owner
from test_publication_d3_contract import build_d3_bundle, NOW
from test_publication_owner import build_owner_observation
from d3_github_model import GitHubModel


class JournalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "journal"
        self.identity = {"installation_uuid": "d" * 32, "epoch": 1,
                         "enrollment_sha256": "e" * 64}
        self.journal = d3.QualificationJournal(self.root, self.identity)

    def bundle(self, letter="a", nonce="b", recovery=None):
        return {"digest": letter * 64,
                "execution": {"nonce": nonce * 32, "payload_sha256": "c" * 64,
                              "review_sha256": "d" * 64, "recovery": recovery}}

    def test_consume_before_effect_and_restart_replay_rejection(self):
        value = self.bundle()
        with self.journal.lock():
            self.journal.claim(value, "0" * 64)
            self.journal.update(value["digest"], pending="upload_asset:fixture.zip")
        restarted = d3.QualificationJournal(self.root, self.identity)
        self.assertEqual(restarted.status()["transactions"][value["digest"]]["pending"],
                         "upload_asset:fixture.zip")
        with restarted.lock(), self.assertRaisesRegex(ValueError, "replay"):
            restarted.claim(value, "0" * 64)

    def test_incomplete_blocks_later_release_after_lost_response(self):
        value = self.bundle()
        with self.journal.lock():
            self.journal.claim(value, "0" * 64)
            self.journal.update(value["digest"], pending="publish_release")
            self.journal.fail(value["digest"])
        self.assertEqual(self.journal.status()["transactions"][value["digest"]]["status"],
                         "UNKNOWN_REMOTE_STATE")
        with self.journal.lock(), self.assertRaisesRegex(ValueError, "Incomplete"):
            self.journal.claim(self.bundle("f", "1"), "0" * 64)

    def test_recovery_requires_same_payload_fresh_nonce_and_reconciliation(self):
        value = self.bundle()
        with self.journal.lock():
            self.journal.claim(value, "0" * 64)
        recovery = {"transaction": value["digest"], "remote_state_sha256": "1" * 64, "completed": []}
        with self.journal.lock(), self.assertRaisesRegex(ValueError, "reconciliation"):
            self.journal.claim(self.bundle("f", "1", recovery), "1" * 64)
        with self.journal.lock():
            state = self.journal.load()
            state["transactions"][value["digest"]]["reconciled"] = True
            self.journal._save(state)
            altered = self.bundle("f", "1", recovery)
            altered["execution"]["payload_sha256"] = "e" * 64
            with self.assertRaisesRegex(ValueError, "changes reviewed"):
                self.journal.claim(altered, "1" * 64)
            self.journal.claim(self.bundle("f", "1", recovery), "1" * 64)
        self.assertEqual(len(self.journal.load()["used"]), 2)

    def test_revocation_can_be_latched_during_writer_and_survives_restart(self):
        value = self.bundle()
        with self.journal.lock():
            self.journal.claim(value, "0" * 64)
            self.journal.latch_revocation(value["execution"]["nonce"], "e" * 64)
            with self.assertRaisesRegex(ValueError, "revoked"):
                self.journal.check_revoked(value["execution"]["nonce"])
        restored = d3.QualificationJournal(self.root, self.identity)
        with self.assertRaisesRegex(ValueError, "revoked"):
            restored.check_revoked(value["execution"]["nonce"])
        (self.root / "revocations" / ("b" * 32 + ".json")).unlink()
        with self.assertRaisesRegex(ValueError, "inventory changed"):
            restored.status()

    def test_missing_index_or_journal_and_torn_commit_fail_closed(self):
        index = self.root / "revocations/index.json"
        original = index.read_bytes()
        index.unlink()
        with self.assertRaises((ValueError, OSError)):
            self.journal.status()
        index.write_bytes(original)
        durable(self.root / "journal/0000000001.json", frozen.canonical({
            "generation": 1, "previous": "0" * 64, "state_sha256": "0" * 64}), exclusive=True)
        with self.assertRaisesRegex(ValueError, "generation mismatch"):
            self.journal.status()

    def test_changed_installation_epoch_and_sourcepath_links_rejected(self):
        changed = dict(self.identity, epoch=2)
        with self.assertRaisesRegex(ValueError, "epoch changed"):
            d3.QualificationJournal(self.root, changed)
        linked = Path(self.temp.name) / "linked"
        linked.symlink_to(self.root, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "Linked"):
            d3.QualificationJournal(linked, self.identity)

    def test_stale_state_writer_and_missing_intent_rejected(self):
        with self.journal.lock():
            before = self.journal.load()
            self.journal.claim(self.bundle(), "0" * 64)
            with self.assertRaisesRegex(ValueError, "Stale"):
                self.journal._save(before)
            with self.assertRaisesRegex(ValueError, "no durable intent"):
                self.journal.update("a" * 64, receipt={"asset_id": 1})

    def test_symlinked_and_hardlinked_state_rejected(self):
        state = self.root / "state.json"
        other = self.root / "hardlink"
        import os
        os.link(state, other)
        with self.assertRaisesRegex(ValueError, "hardlinked"):
            self.journal.status()


class QualificationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = build_d3_bundle(self.root / "fixture")
        self.data = contract.load_bundle(self.path, now=NOW)
        self.enrolled = self.data["enrollment"]
        raw = build_owner_observation(self.data, 7001)
        pages = build_owner_observation(self.data, 7002, pages=True)
        self.model = GitHubModel(self.data, raw, pages)
        self.sender = github.ScriptedMockSender([])
        self.transport = github.GitHubQualification(contract.transport_enrollment(self.enrolled), self.sender, clock=lambda: NOW)
        self.owner = owner.OwnerVerifier(self.enrolled, self.transport, self.credential({
            "actions": "read", "contents": "read", "administration": "read", "pull_requests": "read"}))
        caps = {"inspect": {"contents": "read", "pages": "read"}, "read": {"contents": "read"},
                "write": {"contents": "write"}, "ledger_pr": {"contents": "read", "pull_requests": "write"},
                "policy": {"administration": "read", "actions": "read", "contents": "read"},
                "ledger_read": {"pull_requests": "read"}, "pages_read": {"pages": "read"}}
        self.creds = {name: self.credential(cap) for name, cap in caps.items()}
        self.operator = d3.LocalQualificationOperator(self.root / "operator", self.enrolled, self.transport,
                                                       self.owner, self.creds, clock=lambda: NOW)
        self.addCleanup(patch.stopall)
        patch.object(self.sender, "send", side_effect=self.model.send).start()

    def credential(self, permissions):
        return github.SimulatedCredential(self.enrolled["app_id"], self.enrolled["app_installation_id"],
                                           frozen.utc(NOW + timedelta(minutes=30)), permissions)

    def execute(self, pages_run_id=7002):
        return self.operator.execute(self.path, self.data["digest"], run_id=7001, pages_run_id=pages_run_id)

    def test_complete_serialized_mock_publication_owner_merge_and_replay(self):
        result = self.execute()
        self.assertEqual(result["status"], "PUBLIC_BUT_UNRECONCILED")
        self.assertFalse(result["production_authorized"])
        with self.assertRaisesRegex(ValueError, "replay"): self.execute()
        with self.assertRaisesRegex(ValueError, "not exactly merged"):
            self.operator.observe_finalization(self.path, self.data["digest"])
        before = len(self.model.mutations)
        merge = self.model.owner_merge()
        original_get = self.model.get
        def malformed_actor(path, query, headers):
            if path.endswith("/reviews"):
                value = copy.deepcopy(self.model.reviews[1])
                value[0]["user"]["id"] = float(self.enrolled["human_owner_id"])
                return github.MockResponse.json(200, value)
            return original_get(path, query, headers)
        with patch.object(self.model, "get", side_effect=malformed_actor):
            with self.assertRaisesRegex(ValueError, "owner review"):
                self.operator.observe_finalization(self.path, self.data["digest"])
        result = self.operator.observe_finalization(self.path, self.data["digest"])
        self.assertEqual(result["status"], "RECORDED")
        self.assertEqual(result["merge_sha"], merge)
        self.assertEqual(before, len(self.model.mutations), "Finalization observation must never write")
        self.assertIsNone(self.operator.journal.status()["active"])
        self.assertTrue(all(c["method"] in {"GET", "POST", "PATCH", "HEAD"} for c in self.model.calls))
        self.assertFalse(any(c["authenticated"] for c in self.model.calls if c["host"].endswith("github.io")))
        self.assertFalse(any(c["method"] in {"DELETE", "PUT"} for c in self.model.calls))

    def test_missing_credentials_fail_before_any_request(self):
        for bad in ({}, dict(self.creds, write=None)):
            with self.assertRaises(ValueError):
                d3.LocalQualificationOperator(self.root / "denied", self.enrolled, self.transport, self.owner, bad, clock=lambda: NOW)
        self.assertEqual(self.model.calls, [])

    def test_wrong_owner_or_tampered_package_has_zero_effects(self):
        self.model.owner_raw["review_history"][0]["user"]["id"] = 123
        with self.assertRaises(ValueError): self.execute()
        self.assertEqual(self.model.mutations, [])
        self.model.owner_raw = build_owner_observation(self.data, 7001)
        package = next((self.path / "snapshot/incoming").glob("*.zip"))
        package.write_bytes(package.read_bytes() + b"altered")
        with self.assertRaises(ValueError): self.execute()
        self.assertEqual(self.model.mutations, [])

    def test_changed_head_and_policy_reject_before_first_write(self):
        self.model.refs["heads/main"] = "f" * 40
        with self.assertRaisesRegex(ValueError, "Stale"): self.execute()
        self.assertEqual(self.model.mutations, [])
        self.model.refs["heads/main"] = self.data["payload"]["expected"]["main_sha"]
        self.model.policy["rulesets"][0]["enforcement"] = "disabled"
        with self.assertRaisesRegex(ValueError, "policy baseline"): self.execute()
        self.assertEqual(self.model.mutations, [])

    def test_missing_pages_review_cannot_advance_ledger(self):
        result = self.execute(pages_run_id=None)
        self.assertEqual(result["status"], "AWAITING_PAGES_OWNER_REVIEW")
        self.assertEqual(self.model.pulls, {})
        self.assertEqual(self.operator.journal.status()["active"], self.data["digest"])

    def test_revocation_between_asset_effects_latches_after_comment_deletion(self):
        def revoke(model, method, path):
            if method == "POST" and path.endswith("/assets"):
                model.owner_raw["revocation_comments"] = [{"id": 11,
                    "user": {"id": self.enrolled["human_owner_id"], "type": "User"},
                    "body": f'REVOKE {self.data["digest"]} {self.data["execution"]["nonce"]}'}]
        self.model.after_effect = revoke
        with self.assertRaises(owner.RevokedApproval): self.execute()
        count = len(self.model.mutations)
        self.model.owner_raw["revocation_comments"] = []
        with self.assertRaisesRegex(ValueError, "revoked"):
            self.operator.journal.check_revoked(self.data["execution"]["nonce"])
        self.assertEqual(count, len(self.model.mutations))

    def test_interrupted_asset_is_observed_without_retry_and_fresh_approval_recovers(self):
        self.model.loss_after = ("POST", "/releases/1/assets")
        with self.assertRaises(ValueError): self.execute()
        count = len(self.model.mutations)
        recovery = self.operator.reconcile(self.path, self.data["digest"])
        self.assertEqual(count, len(self.model.mutations))
        self.assertIn("RECONCILED", recovery["status"])
        import shutil
        recovered = self.root / "recovery"; shutil.copytree(self.path, recovered)
        (recovered / "execution.json").unlink()
        contract.seal_execution(recovered, recovery=recovery["recovery"], now=NOW)
        fresh = contract.load_bundle(recovered, now=NOW)
        self.model.bind(fresh, build_owner_observation(fresh, 7011), build_owner_observation(fresh, 7012, pages=True))
        with self.assertRaisesRegex(ValueError, "run replay"):
            self.operator.execute(recovered, fresh["digest"], run_id=7001, pages_run_id=7012)
        result = self.operator.execute(recovered, fresh["digest"], run_id=7011, pages_run_id=7012)
        self.assertEqual(result["status"], "PUBLIC_BUT_UNRECONCILED")
        self.model.owner_merge()
        self.assertEqual(self.operator.observe_finalization(recovered, fresh["digest"])["status"], "RECORDED")

    def test_failed_pages_blocks_ledger_and_later_release(self):
        self.model.pages_failed = True
        with self.assertRaisesRegex(ValueError, "Pages deployment"): self.execute()
        self.assertEqual(self.model.pulls, {})
        self.assertEqual(self.operator.journal.status()["active"], self.data["digest"])
        with self.assertRaisesRegex(ValueError, "replay"): self.execute()

    def test_update_keeps_all_old_assets_and_stable_campaign_installer(self):
        self.execute(); merge = self.model.owner_merge()
        self.operator.observe_finalization(self.path, self.data["digest"])
        old_assets = copy.deepcopy(self.model.asset_bytes)
        old_public = {n: b for n, b in self.model.published_files.items() if n.endswith((".zip", ".zip.sha256"))}
        updated = build_d3_bundle(self.root / "update", version="1.1.0", previous=self.path, main_head=merge)
        fresh = contract.load_bundle(updated, now=NOW)
        self.assertEqual(fresh["enrollment"], self.data["enrollment"])
        self.model.bind(fresh, build_owner_observation(fresh, 7021), build_owner_observation(fresh, 7022, pages=True))
        result = self.operator.execute(updated, fresh["digest"], run_id=7021, pages_run_id=7022)
        self.assertEqual(result["status"], "PUBLIC_BUT_UNRECONCILED")
        self.model.owner_merge()
        self.assertEqual(self.operator.observe_finalization(updated, fresh["digest"])["status"], "RECORDED")
        self.assertTrue(all(self.model.asset_bytes[n] == raw for n, raw in old_assets.items()))
        self.assertTrue(all(self.model.published_files[n] == raw for n, raw in old_public.items()))
        self.assertEqual(len(self.model.releases), 2)
        self.assertFalse(fresh["payload"]["qualification"]["production_authorized"])

    def test_lost_git_object_pages_and_ledger_pr_responses_require_exact_recovery(self):
        # Each subcase has a new isolated published ledger and immutable objects.
        for index, fault in enumerate([("POST", "/git/blobs"), ("POST", "/git/trees"),
                                      ("POST", "/git/commits"), ("PATCH", "/git/refs/heads/gh-pages"),
                                      ("POST", "/pulls")]):
            with self.subTest(fault=fault):
                if index:
                    self.setUp()
                self.model.loss_after = fault
                with self.assertRaises(ValueError): self.execute()
                before = len(self.model.mutations)
                observation = self.operator.reconcile(self.path, self.data["digest"])
                self.assertEqual(before, len(self.model.mutations))
                self.assertEqual(observation["status"], "RECONCILED_NEEDS_FRESH_OWNER_APPROVAL")
                import shutil
                recovered = self.root / "fresh-recovery"; shutil.copytree(self.path, recovered)
                (recovered / "execution.json").unlink()
                contract.seal_execution(recovered, now=NOW, recovery=observation["recovery"])
                data = contract.load_bundle(recovered, now=NOW)
                self.model.bind(data, build_owner_observation(data, 7031), build_owner_observation(data, 7032, pages=True))
                result = self.operator.execute(recovered, data["digest"], run_id=7031, pages_run_id=7032)
                self.assertEqual(result["status"], "PUBLIC_BUT_UNRECONCILED")
                self.model.owner_merge()
                self.assertEqual(self.operator.observe_finalization(recovered, data["digest"])["status"], "RECORDED")

    def test_audit_records_cannot_include_raw_error_or_credential_fields(self):
        self.model.fail_before = ("POST", "/git/refs")
        with self.assertRaises(ValueError) as caught: self.execute()
        self.assertNotIn("PRIVATE-TOKEN", str(caught.exception))
        raw = (self.root / "operator/state.json").read_bytes()
        self.assertNotIn(b"PRIVATE-TOKEN", raw)
        self.assertNotIn(b"Authorization", raw)
        with self.operator.journal.lock(), self.assertRaises(ValueError):
            self.operator.journal.audit(self.data["digest"], operation="bad token secret", status="failed", at=frozen.utc(NOW))


if __name__ == "__main__":
    unittest.main()

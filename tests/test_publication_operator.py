"""Real frozen bundles through the disk-only publication simulator."""
from __future__ import annotations

import copy
from datetime import timedelta
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from test_publication_proposal import build_simulated_bundle, NOW
import publication_proposal as proposal
from publication_fake import FakeGitHub, durable, digest
from publication_operator import Operator, KINDS, MUTATIONS


class OperatorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def case(self, name="case", fault=None):
        base = self.root / name
        bundle = build_simulated_bundle(base)
        data = proposal.load_bundle(bundle, now=NOW)
        fake = FakeGitHub.create(base / "fake", data["execution"]["expected"], {},
                                 (bundle / "snapshot/releases/manifest.json").read_bytes())
        fake.fault = fault
        operator = Operator(base / "operator", fake, clock=lambda: NOW)
        return bundle, data, fake, operator

    def approve(self, bundle, data, operator):
        request = operator.request(bundle, data["digest"])
        operator.simulate_approve(request["request_id"])
        return request

    def recovery(self, bundle, data, operator):
        observed = operator.reconcile(bundle, data["digest"])
        copy_path = bundle.parent / ("recovery-" + data["digest"][:12])
        shutil.copytree(bundle, copy_path)
        (copy_path / "execution.json").unlink()
        result = proposal.seal_execution(copy_path, audience=proposal.SIM_AUDIENCE,
                                         now=NOW, recovery=observed["recovery"])
        return copy_path, proposal.load_bundle(copy_path, result["digest"], now=NOW)

    def test_complete_success_and_consumed_approval(self):
        bundle, data, fake, operator = self.case()
        self.approve(bundle, data, operator)
        result = operator.execute(bundle, data["digest"])
        self.assertEqual(result["status"], "RECORDED")
        self.assertFalse(result["publication_authorized"])
        self.assertIsNone(operator.status()["active"])
        snapshot = fake.snapshot()
        self.assertEqual(snapshot["ledger_sha256"], data["payload"]["retention"]["after_sha256"])
        self.assertEqual(snapshot["pages_sha"], data["payload"]["pages"]["commit"])
        self.assertTrue(snapshot["releases"][data["payload"]["release"]["tag"]]["immutable"])
        before = fake.snapshot()
        with self.assertRaisesRegex(ValueError, "replay"):
            operator.execute(bundle, data["digest"])
        self.assertEqual(before, fake.snapshot())

    def test_missing_or_wrong_owner_approval_zero_fake_writes(self):
        bundle, data, fake, operator = self.case()
        request = operator.request(bundle, data["digest"])
        with self.assertRaisesRegex(ValueError, "owner identity"):
            operator.simulate_approve(request["request_id"], owner_id=2)
        with self.assertRaisesRegex(ValueError, "authorization"):
            operator.execute(bundle, data["digest"])
        self.assertEqual(fake.snapshot()["calls"], [])

    def test_revoked_and_expired_approvals_zero_fake_writes(self):
        for scenario in ("revoked", "expired"):
            with self.subTest(scenario=scenario):
                bundle, data, fake, operator = self.case(scenario)
                request = self.approve(bundle, data, operator)
                if scenario == "revoked": operator.revoke(request["request_id"])
                else: operator.clock = lambda: NOW + timedelta(hours=2)
                with self.assertRaises(ValueError): operator.execute(bundle, data["digest"])
                self.assertEqual(fake.snapshot()["calls"], [])

    def test_observed_revocation_cannot_be_cleared_by_latch_deletion(self):
        bundle, data, fake, operator = self.case()
        request = self.approve(bundle, data, operator)
        operator.revoke(request["request_id"])
        (operator.root / "revocations" / (request["request_id"] + ".json")).unlink()
        with self.assertRaisesRegex(ValueError, "Revocation inventory"):
            operator.execute(bundle, data["digest"])
        self.assertEqual(fake.snapshot()["calls"], [])

    def test_proposal_digest_and_frozen_blob_mismatch_zero_writes(self):
        for scenario in ("digest", "blob"):
            bundle, data, fake, operator = self.case(scenario)
            self.approve(bundle, data, operator)
            if scenario == "blob":
                record = next(iter(data["payload"]["release"]["assets"].values()))
                path = data["root"] / record["path"]; path.write_bytes(path.read_bytes() + b"tamper")
            with self.assertRaises(ValueError):
                operator.execute(bundle, "0" * 64 if scenario == "digest" else data["digest"])
            self.assertEqual(fake.snapshot()["calls"], [])

    def test_full_remote_snapshot_bound_before_owner_approval(self):
        for name, mutate in {
            "main": lambda s: s.update(main_sha="9" * 40),
            "pages": lambda s: s.update(pages_sha="9" * 40),
            "tag": lambda s: s["tags"].update({"unexpected": "9" * 40}),
            "policy": lambda s: s["policy"].update(immutable_releases=False),
        }.items():
            bundle, data, fake, operator = self.case(name)
            self.approve(bundle, data, operator)
            state = fake.snapshot(); mutate(state)
            durable(fake.root / "state.json", proposal.canonical(state))
            with self.assertRaisesRegex(ValueError, "Remote state changed"):
                operator.execute(bundle, data["digest"])
            self.assertEqual(fake.snapshot()["calls"], [])

    def test_conflicting_existing_release_tag_rejected(self):
        bundle, data, fake, operator = self.case()
        state = fake.snapshot(); state["tags"][data["payload"]["release"]["tag"]] = "f" * 40
        durable(fake.root / "state.json", proposal.canonical(state))
        with self.assertRaisesRegex(ValueError, "Conflicting"):
            operator.request(bundle, data["digest"])
        self.assertEqual(fake.snapshot()["calls"], [])

    def test_foreign_asset_mutation_between_stages_stops_next_write(self):
        bundle, data, fake, operator = self.case()
        self.approve(bundle, data, operator)
        original = fake.apply
        def interfere(kind, *args):
            result = original(kind, *args)
            if kind == "create_draft":
                state = fake.snapshot(); state["tags"]["foreign"] = "f" * 40
                durable(fake.root / "state.json", proposal.canonical(state))
            return result
        # Mutation before apply returns is part of its newly observed state;
        # apply result's state digest must bind the exact resulting snapshot.
        with patch.object(fake, "apply", interfere):
            with self.assertRaises(ValueError): operator.execute(bundle, data["digest"])
        self.assertEqual([x["kind"] for x in fake.snapshot()["calls"]], ["create_tag", "create_draft"])

    def test_revocation_can_latch_between_writes_while_writer_locked(self):
        bundle, data, fake, operator = self.case()
        request = self.approve(bundle, data, operator); original = fake.apply
        def revoke_after_tag(kind, *args):
            result = original(kind, *args)
            if kind == "create_tag": operator.revoke(request["request_id"])
            return result
        with patch.object(fake, "apply", revoke_after_tag):
            with self.assertRaisesRegex(ValueError, "revoked"):
                operator.execute(bundle, data["digest"])
        self.assertEqual([x["kind"] for x in fake.snapshot()["calls"]], ["create_tag"])

    def test_failures_before_every_stage_require_explicit_recovery(self):
        for kind in KINDS:
            with self.subTest(kind=kind):
                bundle, data, fake, operator = self.case(kind, ("before", kind))
                self.approve(bundle, data, operator)
                with self.assertRaises(TimeoutError): operator.execute(bundle, data["digest"])
                self.assertEqual(operator.status()["active"], data["digest"])
                with self.assertRaisesRegex(ValueError, "replay"):
                    operator.execute(bundle, data["digest"])
                other = bundle.parent / "new-proposal"; shutil.copytree(bundle, other)
                (other / "execution.json").unlink()
                proposal.seal_execution(other, audience=proposal.SIM_AUDIENCE, now=NOW)
                other_data = proposal.load_bundle(other, now=NOW)
                with self.assertRaisesRegex(ValueError, "Incomplete"):
                    operator.request(other, other_data["digest"])
                fake.fault = None
                recovery, recovered = self.recovery(bundle, data, operator)
                self.approve(recovery, recovered, operator)
                self.assertEqual(operator.execute(recovery, recovered["digest"])["status"], "RECORDED")

    def test_response_lost_after_every_stage_never_repeats_immutable_writes(self):
        for kind in KINDS:
            with self.subTest(kind=kind):
                bundle, data, fake, operator = self.case(kind, ("after", kind))
                self.approve(bundle, data, operator)
                with self.assertRaises(TimeoutError): operator.execute(bundle, data["digest"])
                before = fake.snapshot()
                observation = operator.reconcile(bundle, data["digest"])
                self.assertEqual(fake.snapshot(), before)
                fake.fault = None
                recovery, recovered = self.recovery(bundle, data, operator)
                self.approve(recovery, recovered, operator)
                self.assertEqual(operator.execute(recovery, recovered["digest"])["status"], "RECORDED")
                calls = [c["kind"] for c in fake.snapshot()["calls"]]
                self.assertEqual(calls, [k for k in KINDS if k in MUTATIONS])

    def test_public_release_retained_after_pages_failure(self):
        bundle, data, fake, operator = self.case(fault=("before", "promote_pages"))
        self.approve(bundle, data, operator)
        with self.assertRaises(TimeoutError): operator.execute(bundle, data["digest"])
        snapshot = fake.snapshot(); release = snapshot["releases"][data["payload"]["release"]["tag"]]
        self.assertTrue(release["immutable"]); self.assertFalse(release["draft"])
        self.assertEqual(snapshot["ledger_sha256"], data["execution"]["expected"]["ledger_sha256"])
        self.assertEqual(len(release["assets"]), 3)
        for asset in release["assets"].values(): self.assertEqual(proposal.sha(fake.blob(asset["sha256"])), asset["sha256"])
        self.assertIsNotNone(operator.status()["active"])

    def test_incomplete_public_verification_and_ledger_failure_block_closure(self):
        for kind in ("verify_public", "finalize_ledger"):
            bundle, data, fake, operator = self.case(kind, ("before", kind))
            self.approve(bundle, data, operator)
            with self.assertRaises(TimeoutError): operator.execute(bundle, data["digest"])
            self.assertEqual(fake.snapshot()["ledger_sha256"], data["execution"]["expected"]["ledger_sha256"])
            self.assertEqual(fake.snapshot()["pages_sha"], data["payload"]["pages"]["commit"])
            self.assertIsNotNone(operator.status()["active"])

    def test_historical_blob_change_fails_read_only_snapshot(self):
        bundle, data, fake, operator = self.case()
        self.approve(bundle, data, operator); operator.execute(bundle, data["digest"])
        checksum = next(iter(fake.snapshot()["historical"].values()))
        (fake.root / "blobs" / checksum).write_bytes(b"modified history")
        with self.assertRaisesRegex(ValueError, "Historical"):
            fake.snapshot()

    def test_stale_journal_or_removed_state_fails_closed(self):
        bundle, data, fake, operator = self.case()
        old = (operator.root / "state.json").read_bytes()
        operator.request(bundle, data["digest"])
        durable(operator.root / "state.json", old)
        with self.assertRaisesRegex(ValueError, "generation"):
            operator.status()
        (operator.root / "state.json").unlink()
        with self.assertRaisesRegex(ValueError, "Missing state"):
            Operator(operator.root, fake)

    def test_no_network_transport_or_nonconcrete_backend(self):
        bundle, data, fake, operator = self.case()
        with patch("socket.socket", side_effect=AssertionError("Network forbidden")), \
                patch("subprocess.Popen", side_effect=AssertionError("Subprocess forbidden")):
            self.approve(bundle, data, operator)
            self.assertEqual(operator.execute(bundle, data["digest"])["status"], "RECORDED")
        with self.assertRaisesRegex(ValueError, "concrete"):
            Operator(self.root / "bad-store", object())

    def test_actual_bare_git_competing_parent_rejects_nonforce_push(self):
        remote = self.root / "bare.git"; work = self.root / "work"
        env = {"PATH": "/usr/bin:/bin", "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull,
               "GIT_TERMINAL_PROMPT": "0", "GIT_AUTHOR_NAME": "Synthetic", "GIT_AUTHOR_EMAIL": "test@example.invalid",
               "GIT_COMMITTER_NAME": "Synthetic", "GIT_COMMITTER_EMAIL": "test@example.invalid"}
        def git(*args, data=None, check=True):
            return subprocess.run(["git", *map(str, args)], input=data, env=env,
                                  capture_output=True, check=check).stdout.decode().strip()
        git("init", "--bare", remote); git("init", work)
        tree = git("-C", work, "mktree", data=b"")
        base = git("-C", work, "commit-tree", tree, data=b"base\n")
        intended = git("-C", work, "commit-tree", tree, "-p", base, data=b"intended\n")
        concurrent = git("-C", work, "commit-tree", tree, "-p", base, data=b"concurrent\n")
        git("-C", work, "push", remote, base + ":refs/heads/gh-pages")
        git("-C", work, "push", remote, concurrent + ":refs/heads/gh-pages")
        result = subprocess.run(["git", "-C", str(work), "push", str(remote), intended + ":refs/heads/gh-pages"],
                                env=env, capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(git("--git-dir", remote, "rev-parse", "refs/heads/gh-pages"), concurrent)


if __name__ == "__main__": unittest.main()

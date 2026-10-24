"""Independent D1/D2 adversarial controls; local synthetic data only."""
from pathlib import Path
import ast
from datetime import datetime, timezone
import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import publication_proposal as proposal
from publication_fake import FakeGitHub


class PublicationSecurityTests(unittest.TestCase):
    def test_strict_parser_rejects_ambiguous_json(self):
        for raw in (b'{"x":1,"x":2}', b'{"x":{"y":1,"y":2}}',
                    b'{"x":1.0}', b'{"x":NaN}', b'{"x":Infinity}',
                    b'{"x":1}\n', b'{ "x":1}', b'{"z":1,"a":2}',
                    b'{"x":9007199254740992}', b'{"x":"\\ud800"}',
                    b'\xef\xbb\xbf{}', b'{"x":"\xff"}'):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                proposal.strict_load(raw)

    def test_canonical_rejects_unsupported_values(self):
        for value in ({"x": 1.0}, {"x": float("inf")}, {1: "x"},
                      {"x": b"x"}, {"x": 2**53}, {"x": "\ud800"}):
            with self.subTest(type=type(value)), self.assertRaises(ValueError):
                proposal.canonical(value)

    def test_destination_rejects_aliases_extra_fields_and_boolean_ids(self):
        changes = [dict(repository="kcook98765/ai-kodi-repository"),
                   dict(repository_id=1428864210),
                   dict(base_url="https://kcook98765.github.io/ai-kodi-repository/"),
                   dict(base_url="https://publication.invalid.:443/ai-kodi-repository/"),
                   dict(repository_id=True), dict(owner_id=True), dict(force=False)]
        for mutation in changes:
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                proposal.destination(dict(proposal.SIM_DESTINATION, **mutation))

    def test_safe_read_rejects_links_and_special_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"; source.write_bytes(b"synthetic")
            linked = root / "linked"; linked.symlink_to(source)
            hard = root / "hard"; os.link(source, hard)
            for path in (linked, hard):
                with self.subTest(path=path.name), self.assertRaises(ValueError):
                    proposal.safe_read(path)
            hard.unlink()
            fifo = root / "fifo"; os.mkfifo(fifo)
            with self.assertRaises(ValueError):
                proposal.safe_read(fifo)

    def test_ancestor_swap_cannot_read_outside_snapshot(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            folder = root / "snapshot"; folder.mkdir()
            victim = folder / "item"; victim.write_bytes(b"reviewed data")
            outside = root / "outside"; outside.mkdir()
            (outside / "item").write_bytes(b"private outside snapshot")
            opened = os.open

            def swap(path, *args, **kwargs):
                if Path(path) == victim and not folder.is_symlink():
                    folder.rename(root / "retained")
                    folder.symlink_to(outside, target_is_directory=True)
                return opened(path, *args, **kwargs)

            try:
                with patch.object(os, "open", side_effect=swap):
                    observed = proposal.safe_read(victim)
            except (ValueError, OSError):
                return
            self.assertEqual(observed, b"reviewed data", "Ancestor race escaped the frozen snapshot")

    def test_fake_storage_rejects_historical_blob_changes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            ledger = b'{"packages":[],"schema":1}'
            files = {"packages/synthetic/synthetic-1.0.0.zip": b"frozen test bytes"}
            expected = {"main_sha": "a" * 40, "pages_sha": "b" * 40,
                        "pages_tree": "c" * 40, "ledger_sha256": proposal.sha(ledger),
                        "site_files": {n: proposal.sha(b) for n, b in files.items()}}
            fake = FakeGitHub.create(root / "fake", expected, files, ledger)
            checksum = expected["site_files"][next(iter(files))]
            (fake.root / "blobs" / checksum).write_bytes(b"changed test bytes")
            with self.assertRaisesRegex(ValueError, "modified"):
                fake.snapshot()

    def test_fake_and_operator_have_no_network_or_shell_implementation(self):
        forbidden = {"socket", "http", "urllib", "requests", "httpx", "subprocess"}
        for name in ("publication_fake.py", "publication_operator.py"):
            tree = ast.parse((ROOT / "scripts" / name).read_text())
            for node in ast.walk(tree):
                modules = ([alias.name for alias in node.names] if isinstance(node, ast.Import)
                           else [node.module or ""] if isinstance(node, ast.ImportFrom) else [])
                self.assertTrue(all(module.split(".")[0] not in forbidden for module in modules),
                                f"Unexpected production transport import in {name}: {modules}")
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                    if isinstance(node.func.value, ast.Name) and node.func.value.id == "os":
                        self.assertNotIn(node.func.attr, {"system", "popen", "execv", "execve", "spawnv"})

    def test_expired_v3_policy_allows_only_byte_observation(self):
        import test_runtime_exception as runtime
        import approval_contract
        import publication_verify
        fixture = runtime.RuntimeExceptionTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        record = fixture.initial()
        record["source_repository"] = "https://github.com/simulation/v3-expiry-control"
        fixture.save(record)
        config = json.loads((fixture.root / "config/repository.json").read_bytes())
        config.update(base_url=proposal.SIM_DESTINATION["base_url"],
                      github_repository=proposal.SIM_DESTINATION["repository"])
        (fixture.root / "config/repository.json").write_bytes(proposal.repo.json_bytes(config))
        for name, raw in proposal.repo.installer(config, "production").items():
            (fixture.root / "packages/repository.ai.kodi" / name).write_bytes(raw)
        proposal.repo.build("production")
        now = datetime.now(timezone.utc).replace(microsecond=0)
        with tempfile.TemporaryDirectory() as temporary:
            bundle = Path(temporary) / "bundle"
            expected = {"main_sha": "1" * 40, "pages_sha": "2" * 40,
                        "pages_tree": proposal.git_tree({}), "site_files": {},
                        "ledger_sha256": proposal.sha((fixture.root / "releases/manifest.json").read_bytes())}
            proposal.prepare(fixture.root, bundle,
                             source={"repository": "simulation/v3-expiry-control", "repository_id": 990,
                                     "owner_id": 991, "commit": record["source_commit"]},
                             lanes=["nexus", "omega"], expected=expected,
                             release_tag="plugin.video.example-1.0.0", synthetic=True, now=now)
            proposal.seal_review(bundle, b"Synthetic v3-expiry independent review.", now=now)
            from publication_operator import SIM_AUDIENCE
            frozen = proposal.seal_execution(bundle, audience=SIM_AUDIENCE, now=now)
            # Existing genuine policy predicates reject expired synthetic v3
            # exceptions. Historical byte observation must not renew them.
            future = datetime(2100, 1, 1, tzinfo=timezone.utc)
            with patch.object(approval_contract, "utc_now", return_value=future):
                with self.assertRaises((ValueError, AssertionError)):
                    proposal.load_bundle(bundle, frozen["digest"], now=now)
                observed = proposal.load_bundle(bundle, frozen["digest"], now=now, observation=True)
                self.assertFalse(observed["simulation_eligible"])
                self.assertTrue(any("not assessed" in b for b in observed["eligibility_blockers"]))
                result = publication_verify.observe_directory(bundle, bundle / "snapshot/dist/production/site")
                self.assertEqual(result["status"], "PASS")
                self.assertFalse(result["production_verified"])


class PublicationSecurityFlowTests(unittest.TestCase):
    def setUp(self):
        import test_publication_acceptance as acceptance
        self.fixture = acceptance.PublicationAcceptanceTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def frozen(self):
        from publication_operator import SIM_AUDIENCE
        proposal.seal_review(self.fixture.bundle, b"Independent synthetic adversarial review.", now=self.fixture.now)
        return proposal.seal_execution(self.fixture.bundle, audience=SIM_AUDIENCE, now=self.fixture.now)

    def test_private_snapshot_evidence_cannot_be_release_asset(self):
        value = self.fixture.payload()
        relative = "evidence/synthetic-only.txt"
        raw = proposal.safe_read(self.fixture.bundle / "snapshot" / relative)
        value["release"]["assets"]["private-evidence.txt"] = {
            "path": relative, "sha256": proposal.sha(raw), "size": len(raw)}
        self.fixture.rewrite_payload(value)
        with self.assertRaises(ValueError):
            proposal.verify_payload(self.fixture.bundle)

    def test_frozen_tag_grammar_is_rechecked(self):
        value = self.fixture.payload()
        value["release"]["tag"] = "../../unreviewed tag"
        self.fixture.rewrite_payload(value)
        with self.assertRaises(ValueError):
            proposal.verify_payload(self.fixture.bundle)

    def test_midtransaction_revocation_stops_later_effects(self):
        frozen = self.frozen()
        operator, fake = self.fixture.operator()
        operator.request(self.fixture.bundle, frozen["digest"])
        nonce = frozen["execution"]["nonce"]
        operator.simulate_approve(nonce)
        apply = fake.apply

        def revoke_after_first(kind, *args, **kwargs):
            result = apply(kind, *args, **kwargs)
            if kind == "create_tag":
                operator.revoke(nonce)
            return result

        with patch.object(fake, "apply", side_effect=revoke_after_first):
            with self.assertRaisesRegex(ValueError, "revoked"):
                operator.execute(self.fixture.bundle, frozen["digest"])
        self.assertEqual([call["kind"] for call in fake.snapshot()["calls"]], ["create_tag"])
        self.assertIsNotNone(operator.status()["active"])

    def test_complete_simulation_has_no_network_or_subprocess_calls(self):
        import socket
        import subprocess
        import urllib.request
        frozen = self.frozen()
        operator, fake = self.fixture.operator()
        with patch.object(socket, "socket", side_effect=AssertionError("network forbidden")), \
                patch.object(subprocess, "run", side_effect=AssertionError("subprocess forbidden")), \
                patch.object(urllib.request, "urlopen", side_effect=AssertionError("HTTP forbidden")):
            operator.request(self.fixture.bundle, frozen["digest"])
            operator.simulate_approve(frozen["execution"]["nonce"])
            result = operator.execute(self.fixture.bundle, frozen["digest"])
        self.assertEqual(result["status"], "RECORDED")
        self.assertFalse(result["publication_authorized"])
        self.assertEqual(len(fake.snapshot()["calls"]), 6)

    def test_ambiguous_effect_with_foreign_remote_change_is_not_adopted(self):
        frozen = self.frozen()
        operator, fake = self.fixture.operator(("after", "create_draft"))
        operator.request(self.fixture.bundle, frozen["digest"])
        operator.simulate_approve(frozen["execution"]["nonce"])
        with self.assertRaises(TimeoutError):
            operator.execute(self.fixture.bundle, frozen["digest"])
        from publication_fake import durable
        state = fake.snapshot()
        state["tags"]["foreign-change"] = "f" * 40
        durable(fake.root / "state.json", proposal.canonical(state))
        before = fake.snapshot()
        with self.assertRaises(ValueError):
            operator.reconcile(self.fixture.bundle, frozen["digest"])
        self.assertEqual(fake.snapshot(), before)


if __name__ == "__main__":
    unittest.main()

"""Synthetic publication proposals never supply actual production approval."""
from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import publication_proposal as proposal
import publication_verify
import repository as repo

NOW = datetime(2026, 10, 23, 23, 0, 0, tzinfo=timezone.utc)


def build_simulated_bundle(base, *, lanes=None, qualification=True, seal=True, now=NOW):
    """Public test helper: complete independently audited synthetic production site."""
    base = Path(base); base.mkdir(parents=True, exist_ok=True)
    stage = base / "stage"; stage.mkdir()
    for name in ("config", "packages", "releases"):
        shutil.copytree(proposal.ROOT / name, stage / name)
    shutil.copyfile(proposal.ROOT / "LICENSE", stage / "LICENSE")
    (stage / "incoming").mkdir(); (stage / "evidence").mkdir()
    config = json.loads((stage / "config/repository.json").read_text())
    config["github_repository"] = proposal.SIM_DESTINATION["repository"]
    config["base_url"] = proposal.SIM_DESTINATION["base_url"]
    (stage / "config/repository.json").write_bytes(repo.json_bytes(config))
    ledger = {"schema": 1, "packages": []}
    (stage / "releases/manifest.json").write_bytes(repo.json_bytes(ledger))
    lanes = ["nexus"] if lanes is None else lanes
    source = {"repository": "simulation/source-addon", "repository_id": 101, "owner_id": 100, "commit": "a" * 40}
    manifest = repo.parse_xml(b'''<addon id="plugin.video.publication.fixture" version="1.0.0" name="Synthetic publication fixture" provider-name="Local tests"><requires><import addon="xbmc.python" version="3.0.0"/></requires><extension point="xbmc.python.pluginsource" library="default.py"><provides>video</provides></extension><extension point="xbmc.addon.metadata"><summary>Fixture</summary><description>Synthetic local publication only</description><platform>all</platform><license>MIT</license></extension></addon>''')
    files = {"addon.xml": repo.xml_bytes(manifest), "default.py": b"# Inert synthetic fixture\n", "LICENSE.txt": b"MIT synthetic tests\n"}
    blob = repo.zip_bytes(files)
    record = {"package_sha256": proposal.sha(blob), "runtime_files": {n: proposal.sha(b) for n, b in files.items()},
              "source_repository": "https://github.com/" + source["repository"], "source_commit": source["commit"],
              "fixture_only": False, "release_approved": True, "rights_approved": True,
              "compatibility": {lane: {"static_accepted": True, "runtime_accepted": True,
                                        "evidence": ["Synthetic simulation only; no actual native result"]} for lane in lanes}}
    (stage / "incoming/package.zip").write_bytes(blob)
    raw_record = repo.json_bytes(record); (stage / "incoming/review.json").write_bytes(raw_record)
    intake = {"external_dependencies": {}, "packages": [{"zip": "package.zip", "sha256": proposal.sha(blob),
               "review_record": "review.json", "review_record_sha256": proposal.sha(raw_record), "lanes": lanes}]}
    (stage / "config/production.json").write_bytes(repo.json_bytes(intake))
    evidence = proposal.canonical({"synthetic": True, "scope": "Local test identities and results only"})
    (stage / "evidence/qualification.json").write_bytes(evidence)
    receipts = {lane: {kind: {"status": "passed", "target": proposal.LANES[lane], "scope": "Synthetic local test only",
                  "evidence": [{"path": "evidence/qualification.json", "sha256": proposal.sha(evidence)}]}
                       for kind in ("static", "interpreter", "native")} for lane in lanes} if qualification else None
    with proposal.stage_context(stage):
        for name, raw in repo.installer(config, "production").items():
            (stage / "packages/repository.ai.kodi" / name).write_bytes(raw)
        repo.build("production")
        first = (stage / "dist/production/release-plan.json").read_bytes()
        repo.build("production")
        if first != (stage / "dist/production/release-plan.json").read_bytes():
            raise AssertionError("Nondeterministic fixture package build")
    expected = {"main_sha": "1" * 40, "pages_sha": "2" * 40, "pages_tree": proposal.git_tree({}),
                "ledger_sha256": proposal.sha(repo.json_bytes(ledger)), "site_files": {}}
    bundle = base / "bundle"
    proposal.prepare(stage, bundle, source=source, lanes=lanes, expected=expected,
                     release_tag="plugin.video.publication.fixture-1.0.0", qualification=receipts,
                     synthetic=True, now=now)
    if seal:
        proposal.seal_review(bundle, b"Independent synthetic review; no production authority.\n", now=now)
        proposal.seal_execution(bundle, audience=proposal.SIM_AUDIENCE, now=now)
    return bundle


class ProposalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)

    def bundle(self, **kwargs):
        return build_simulated_bundle(self.base, **kwargs)

    def test_synthetic_bundle_binds_complete_audited_site(self):
        path = self.bundle(); result = proposal.load_bundle(path, now=NOW)
        self.assertTrue(result["simulation_eligible"])
        self.assertEqual(result["eligibility_blockers"], [])
        self.assertTrue(result["production_blockers"])
        self.assertFalse(result["execution"]["publication_authorized"])
        self.assertEqual(len(result["payload"]["release"]["assets"]), 3)
        self.assertEqual(set(result["payload"]["catalogs"]), set(proposal.LANES))

    def test_canonical_parser_rejects_duplicates_floats_and_normalization(self):
        for raw in (b'{"a":1,"a":1}', b'{"a":1.0}', b'{ "a":1}', b'{"a":NaN}', b'{}\n', b'"\\ud800"'):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                proposal.strict_load(raw)
        for value in ({"a": 1.2}, {1: "key"}, 2**54):
            with self.assertRaises(ValueError):
                proposal.canonical(value)
        self.assertEqual(proposal.strict_load(b'{"a":1}'), {"a": 1})

    def test_digest_and_frozen_package_mutation_rejected(self):
        path = self.bundle(); verified = proposal.load_bundle(path, now=NOW)
        with self.assertRaisesRegex(ValueError, "digest"):
            proposal.load_bundle(path, "0" * 64, now=NOW)
        file = next((path / "snapshot/incoming").glob("*.zip")); file.write_bytes(file.read_bytes() + b"modified")
        with self.assertRaisesRegex(ValueError, "inventory"):
            proposal.load_bundle(path, verified["digest"], now=NOW)

    def test_changed_destination_rejected_even_after_rehash(self):
        path = self.bundle(); file = path / "execution.json"; value = proposal.strict_load(file.read_bytes())
        value["destination"]["repository"] = "kcook98765/ai-kodi-repository"; file.write_bytes(proposal.canonical(value))
        with self.assertRaisesRegex(ValueError, "destination"):
            proposal.load_bundle(path, now=NOW)

    def test_expiry_and_read_only_observation(self):
        path = self.bundle()
        with self.assertRaisesRegex(ValueError, "Expired"):
            proposal.load_bundle(path, now=NOW + timedelta(hours=2))
        observed = proposal.load_bundle(path, now=NOW + timedelta(hours=2), observation=True)
        self.assertFalse(observed["simulation_eligible"])
        self.assertIn("Fresh release eligibility not assessed in byte-observation mode", observed["eligibility_blockers"])

    def test_missing_evidence_and_piers_remain_blocked(self):
        path = self.bundle(qualification=False)
        result = proposal.load_bundle(path, now=NOW)
        self.assertFalse(result["simulation_eligible"])
        self.assertTrue(any("native UNVERIFIED" in b for b in result["eligibility_blockers"]))
        with tempfile.TemporaryDirectory() as temp:
            path = build_simulated_bundle(Path(temp), lanes=["piers"])
            self.assertFalse(proposal.load_bundle(path, now=NOW)["simulation_eligible"])

    def test_unknown_lane_and_real_source_synthetic_label_rejected(self):
        path = self.bundle(seal=False); file = path / "payload.json"; value = proposal.strict_load(file.read_bytes())
        for mutate in (lambda p: p.update(lanes=["kodi23"]),
                       lambda p: p["source"].update(repository="real/source")):
            changed = copy.deepcopy(value); mutate(changed); file.write_bytes(proposal.canonical(changed))
            with self.assertRaises(ValueError):
                proposal.verify_payload(path)

    def test_safe_paths_and_linked_files_fail_closed(self):
        for name in ("../escape", "/absolute", "C:/escape", "file%2fescape", ".git/config", "a/./b", "a\\b", "é.txt"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                proposal.safe_name(name)
        linked = self.base / "link"; target = self.base / "target"; target.write_bytes(b"payload")
        linked.symlink_to(target)
        with self.assertRaises(ValueError):
            proposal.safe_read(linked)
        linked.unlink(); os.link(target, linked)
        with self.assertRaises(ValueError):
            proposal.safe_read(target)

    def test_forged_rehashed_source_and_assets_are_not_reviewable(self):
        path = self.bundle(seal=False); file = path / "payload.json"; original = proposal.strict_load(file.read_bytes())
        mutations = [lambda p: p["source"].update(commit="f" * 40),
                     lambda p: p.update(lanes=["omega"]), lambda p: p["release"].update(assets={}),
                     lambda p: p["retention"].update(main_commit="f" * 40)]
        for mutate in mutations:
            changed = copy.deepcopy(original); mutate(changed); file.write_bytes(proposal.canonical(changed))
            with self.assertRaises(ValueError):
                proposal.verify_payload(path)

    def test_observation_checks_all_public_bytes(self):
        path = self.bundle(); payload = proposal.verify_payload(path)["payload"]
        site = path / "snapshot" / payload["pages"]["site_prefix"]
        self.assertEqual(publication_verify.observe_directory(path, site)["status"], "PASS")
        assets = {n: proposal.safe_read(path / "snapshot" / item["path"]) for n, item in payload["release"]["assets"].items()}
        self.assertEqual(publication_verify.verify_assets(payload, assets)["status"], "PASS")
        assets.pop("SHA256SUMS")
        with self.assertRaises(ValueError):
            publication_verify.verify_assets(payload, assets)

    def test_schema_matches_the_three_canonical_documents(self):
        try:
            import jsonschema
        except ImportError:
            self.skipTest("Optional interchange-schema validation dependency unavailable")
        path = self.bundle()
        schema = json.loads((proposal.ROOT / "docs/PUBLICATION-PROPOSAL-SCHEMA.json").read_text())
        jsonschema.Draft202012Validator.check_schema(schema)
        for name in ("payload.json", "review.json", "execution.json"):
            jsonschema.validate(proposal.strict_load((path / name).read_bytes()), schema)

    def test_frozen_lane_evidence_hash_mismatch_rejected(self):
        path = self.bundle(seal=False); file = path / "payload.json"; value = proposal.strict_load(file.read_bytes())
        value["qualification"]["nexus"]["native"]["evidence"][0]["sha256"] = "0" * 64
        file.write_bytes(proposal.canonical(value))
        with self.assertRaisesRegex(ValueError, "evidence hash"):
            proposal.verify_payload(path)

    def test_toolchain_drift_invalidates_the_payload(self):
        from unittest.mock import patch
        path = self.bundle(); changed = dict(proposal.toolchain())
        changed["scripts/publication_operator.py"] = "0" * 64
        with patch.object(proposal, "toolchain", return_value=changed), self.assertRaisesRegex(ValueError, "toolchain"):
            proposal.verify_payload(path)

    def update_case(self, version="1.1.0", foreign_source=False):
        first = self.bundle(seal=False)
        old = proposal.verify_payload(first)["payload"]; stage = self.base / "stage"
        (stage / "releases/manifest.json").write_bytes(repo.json_bytes(old["retention"]["after"]))
        prior = json.loads((stage / "incoming/review.json").read_text())
        if foreign_source:
            prior["source_repository"] = "https://github.com/simulation/foreign-source"
            (stage / "incoming/review.json").write_bytes(repo.json_bytes(prior))
        source = dict(old["source"], commit="b" * 40)
        _, runtime = repo.inspect_zip((stage / "incoming/package.zip").read_bytes())
        manifest = repo.parse_xml(runtime["addon.xml"]); manifest.set("version", version)
        runtime["addon.xml"] = repo.xml_bytes(manifest); runtime["default.py"] += b"# updated\n"
        blob = repo.zip_bytes(runtime); (stage / "incoming/update.zip").write_bytes(blob)
        record = dict(prior, source_repository="https://github.com/" + source["repository"], source_commit=source["commit"],
                      package_sha256=proposal.sha(blob), runtime_files={n: proposal.sha(b) for n, b in runtime.items()})
        (stage / "incoming/update.json").write_bytes(repo.json_bytes(record))
        intake = json.loads((stage / "config/production.json").read_text())
        intake["packages"][0]["lanes"] = []
        intake["packages"][0]["review_record_sha256"] = proposal.sha((stage / "incoming/review.json").read_bytes())
        intake["packages"].append({"zip": "update.zip", "sha256": proposal.sha(blob),
            "review_record": "update.json", "review_record_sha256": proposal.sha(repo.json_bytes(record)), "lanes": ["nexus"]})
        (stage / "config/production.json").write_bytes(repo.json_bytes(intake))
        with proposal.stage_context(stage):
            repo.build("production")
        expected = {"main_sha": old["retention"]["main_commit"], "pages_sha": old["pages"]["commit"],
                    "pages_tree": old["pages"]["tree"], "ledger_sha256": proposal.sha((stage / "releases/manifest.json").read_bytes()),
                    "site_files": old["pages"]["site_files"]}
        return proposal.prepare(stage, self.base / "update-bundle", source=source, lanes=["nexus"], expected=expected,
                                release_tag="plugin.video.publication.fixture-" + version,
                                qualification=old["qualification"], synthetic=True, now=NOW)

    def test_update_preserves_history_and_advances_numeric_version(self):
        update = self.update_case()
        before = update["retention"]["before"]["packages"]
        self.assertEqual(update["retention"]["after"]["packages"][:len(before)], before)
        self.assertEqual(update["catalogs"]["nexus"]["ids"]["plugin.video.publication.fixture"], "1.1.0")
        self.assertIn("packages/plugin.video.publication.fixture/plugin.video.publication.fixture-1.0.0.zip",
                      update["pages"]["site_files"])

    def test_update_rejects_lower_version(self):
        with self.assertRaisesRegex(ValueError, "progression"):
            self.update_case(version="0.9.0")

    def test_update_rejects_source_identity_change(self):
        with self.assertRaisesRegex(ValueError, "source identity"):
            self.update_case(foreign_source=True)


if __name__ == "__main__":
    unittest.main()

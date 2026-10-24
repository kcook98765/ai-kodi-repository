"""D3 contract fixtures are first-party synthetic data, never live releases."""
from datetime import datetime, timedelta, timezone
import copy
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import publication_proposal as base
import publication_d3_contract as contract
import repository as repo

NOW = datetime(2026, 10, 24, 1, 0, 0, tzinfo=timezone.utc)
WORKFLOW = b"# inert local approval workflow projection\n"


def build_d3_bundle(directory, version="1.0.0", previous=None, now=NOW, *, seal=True, main_head=None, extra_future=False):
    directory = Path(directory); directory.mkdir(parents=True)
    enrollment = contract.mock_enrollment(now=now, workflow_bytes=WORKFLOW)
    stage = directory / "stage"; stage.mkdir()
    for name in ("config", "packages", "releases"): shutil.copytree(contract.ROOT / name, stage / name)
    shutil.copyfile(contract.ROOT / "LICENSE", stage / "LICENSE"); (stage / "incoming").mkdir()
    (stage / "config/production.json").write_bytes(repo.json_bytes({"schema": 1, "external_dependencies": {}, "packages": []}))
    (stage / "releases/manifest.json").write_bytes(repo.json_bytes({"schema": 1, "packages": []}))
    production = json.loads((stage / "config/repository.json").read_text())
    candidate = {**production, "addon_id": "repository.ai.kodi.candidate." + enrollment["campaign_id"],
                 "base_url": enrollment["base_url"], "github_repository": enrollment["repository"], "provider": "AI Kodi D3 LOCAL QUALIFICATION",
                 "candidate_context": {"task_id": enrollment["campaign_id"],
                  "production_config_sha256": base.sha((stage / "config/repository.json").read_bytes()),
                  "production_ledger_sha256": base.sha((stage / "releases/manifest.json").read_bytes())}}
    (stage / "config/candidate-repository.json").write_bytes(repo.json_bytes(candidate))
    for name, raw in contract.installer_assets().items(): (stage / "packages/repository.ai.kodi" / name).write_bytes(raw)
    with base.stage_context(stage):
        for name, raw in repo.installer(candidate, "candidate").items():
            path = stage / "packages" / candidate["addon_id"] / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(raw)
    ledger = {"schema": 1, "repository_id": candidate["addon_id"], "packages": []}
    (stage / "releases/candidate-manifest.json").write_bytes(repo.json_bytes(ledger))
    intake = {"schema": 1, "external_dependencies": {}, "packages": []}
    for selected in (["1.0.0"] if version == "1.0.0" and not extra_future else ["1.0.0", "1.1.0"]):
        files = contract.fixture_files(selected); blob = repo.zip_bytes(files)
        record = json.loads((contract.ROOT / "docs/REVIEW-RECORD-EXAMPLE.json").read_text())
        lanes = ["nexus"] if selected == version else []
        record.update(package_sha256=base.sha(blob), runtime_files={n: base.sha(raw) for n, raw in files.items()},
                      source_repository="https://github.com/" + enrollment["repository"],
                      source_commit=enrollment["fixture_source"]["commits"][selected], approval_lanes=lanes)
        zip_name = contract.ADDON_ID + "-" + selected + ".zip"; review_name = selected + "-pending.json"
        (stage / "incoming" / zip_name).write_bytes(blob); raw = repo.json_bytes(record); (stage / "incoming" / review_name).write_bytes(raw)
        intake["packages"].append({"zip": zip_name, "sha256": base.sha(blob), "review_record": review_name,
                                   "review_record_sha256": base.sha(raw), "lanes": lanes})
    (stage / "config/candidate.json").write_bytes(repo.json_bytes(intake))
    with base.stage_context(stage):
        repo.build("candidate"); plan = json.loads((stage / "dist/candidate/release-plan.json").read_text())
        ledger["packages"] = [{k: p[k] for k in ("id", "version", "sha256")} for p in plan["packages"]]
        (stage / "releases/candidate-manifest.json").write_bytes(repo.json_bytes(ledger)); repo.build("candidate")
    source = {"repository": enrollment["repository"], "repository_id": enrollment["repository_id"], "owner_id": enrollment["owner_id"],
              "commit": enrollment["fixture_source"]["commits"][version]}
    published = {"schema": 1, "packages": []}
    main_files = {enrollment["workflow_path"]: WORKFLOW, "README.md": b"D3 qualification only\n",
                  "releases/manifest.json": repo.json_bytes(published), "config/qualification.json": b"{}"}
    expected = {"main_sha": "c" * 40, "main_tree": contract.tree(main_files), "pages_sha": "2" * 40,
                "pages_tree": base.git_tree({}), "ledger_sha256": base.sha(repo.json_bytes(published)), "site_files": {}}
    if previous is not None:
        prior = contract.load_bundle(previous, now=now, observation=True); p = prior["payload"]; enrollment = prior["enrollment"]
        published = p["retention"]["after"]
        main_files = {n: base.safe_read(prior["root"] / item["path"]) for n, item in p["main_base"]["files"].items()}
        main_files.update({"releases/manifest.json": base.safe_read(prior["root"] / p["retention"]["successor_path"]),
                           "config/qualification.json": base.safe_read(prior["root"] / p["retention"]["config_path"])})
        expected = {"main_sha": p["retention"]["main_commit"], "main_tree": p["retention"]["main_tree"], "pages_sha": p["pages"]["commit"],
                    "pages_tree": p["pages"]["tree"], "ledger_sha256": p["retention"]["after_sha256"], "site_files": p["pages"]["site_files"]}
    if main_head is not None: expected["main_sha"] = main_head
    frozen = directory / "candidate"; before = {k: expected[k] for k in expected if k != "main_tree"}
    before.update(ledger_sha256=base.sha((stage / "releases/candidate-manifest.json").read_bytes()), site_files={})
    base.prepare(stage, frozen, source=source, lanes=["nexus"], expected=before, release_tag=contract.ADDON_ID + "-" + version,
                 profile="candidate", synthetic=False, now=now)
    output = directory / "bundle"
    contract.assemble(frozen, output, enrollment=enrollment, published_ledger=published, expected=expected, main_files=main_files,
                      qualification_report=b"Independent first-party inert MIT fixture inspection; mock only.\n",
                      reviewer_report=b"Independent frozen D3 qualification review; production not approved.\n", now=now)
    if seal: contract.seal_execution(output, now=now)
    return output


class D3ContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup); self.root = Path(self.temp.name)

    def test_frozen_fixture_keeps_production_and_native_claims_false(self):
        data = contract.load_bundle(build_d3_bundle(self.root / "first"), now=NOW)
        self.assertTrue(data["transport_eligible"]); self.assertFalse(data["production_authorized"]); self.assertFalse(data["network_authorized"])
        for key in ("native_acceptance", "target_interpreter_compatibility", "piers_static"):
            self.assertEqual(data["payload"]["qualification"][key], "UNVERIFIED")
        self.assertEqual(data["payload"]["retention"]["before"]["packages"], [])
        self.assertEqual(len(data["payload"]["candidate_ledger"]["packages"]), 2)

    def test_update_preserves_campaign_installer_history_and_workflow(self):
        first = build_d3_bundle(self.root / "first")
        second = build_d3_bundle(self.root / "second", "1.1.0", first, NOW + timedelta(minutes=1))
        a = contract.load_bundle(first, now=NOW); b = contract.load_bundle(second, now=NOW + timedelta(minutes=1))
        self.assertEqual(a["enrollment"], b["enrollment"])
        installer = "repository.ai.kodi.candidate." + a["enrollment"]["campaign_id"]
        self.assertEqual(next(p["sha256"] for p in a["payload"]["packages"] if p["id"] == installer),
                         next(p["sha256"] for p in b["payload"]["packages"] if p["id"] == installer))
        self.assertEqual(b["payload"]["retention"]["before"], a["payload"]["retention"]["after"])
        self.assertEqual(len(b["payload"]["release"]["assets"]), 3)
        self.assertIn(a["enrollment"]["workflow_path"], b["payload"]["main_base"]["files"])

    def test_enrollment_rejects_unassigned_aliases_and_mistyped_identities(self):
        original = contract.mock_enrollment(now=NOW)
        for key, value in (("repository_id", contract.PRODUCTION_ID), ("owner_id", 56806582), ("app_id", True),
                           ("repository", "kcook98765/ai-kodi-repository"), ("base_url", "https://kcook98765.github.io/other/"),
                           ("owner_type", "User"), ("repository_id", None), ("policy_sha256", "0" * 64)):
            changed = copy.deepcopy(original); changed[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError): contract.validate_enrollment(changed)

    def test_digest_or_finalization_tree_change_fails(self):
        path = build_d3_bundle(self.root / "first"); data = contract.load_bundle(path, now=NOW)
        with self.assertRaisesRegex(ValueError, "digest"): contract.load_bundle(path, "0" * 64, now=NOW)
        data["payload"]["retention"]["main_tree"] = "f" * 40
        (path / "payload.json").write_bytes(base.canonical(data["payload"]))
        with self.assertRaises(ValueError): contract.load_bundle(path, now=NOW)

    def test_one_hour_expiry_and_safe_observation(self):
        path = build_d3_bundle(self.root / "first", seal=False)
        with self.assertRaisesRegex(ValueError, "one hour"): contract.seal_execution(path, lifetime=3601, now=NOW)
        contract.seal_execution(path, now=NOW)
        with self.assertRaisesRegex(ValueError, "expired"): contract.load_bundle(path, now=NOW + timedelta(hours=2))
        self.assertFalse(contract.load_bundle(path, now=NOW + timedelta(hours=2), observation=True)["production_authorized"])

    def test_summary_omits_private_paths_and_reports(self):
        data = contract.load_bundle(build_d3_bundle(self.root / "first"), now=NOW)
        summary = base.canonical(contract.owner_summary(data))
        self.assertNotIn(str(self.root).encode(), summary); self.assertNotIn(b"Independent frozen", summary)
        self.assertIn(b"UNVERIFIED", summary)

    def test_initial_release_cannot_publish_an_unselected_future_version(self):
        with self.assertRaisesRegex(ValueError, "version inventory"):
            build_d3_bundle(self.root / "first", extra_future=True)


if __name__ == "__main__": unittest.main()

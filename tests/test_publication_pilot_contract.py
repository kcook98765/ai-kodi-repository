"""Local fixture materials for the explicitly versioned single-PR pilot."""
from datetime import timedelta
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import publication_proposal as base
import publication_pilot_contract as contract
import publication_d3_contract as old
import repository as repo
from test_publication_d3_contract import build_d3_bundle, NOW

VALIDATION = b"# first-party inert qualification validation fixture\n"


def test_enrollment(now=NOW):
    source = old.mock_enrollment(now=now)["fixture_source"]
    value = {"schema": 1, "profile": contract.PROFILE, "repository": old.QUAL_REPOSITORY,
             "repository_id": 1100001, "owner_id": 1100002, "owner_type": "Organization", "human_owner_id": old.OWNER_ID,
             "base_url": old.QUAL_BASE, "branch": "gh-pages", "path": "/", "app_id": 1100003,
             "app_installation_id": 1100004, "bot_user_id": 1100005, "bot_login": "ai-kodi-pilot-test[bot]",
             "ci_app_id": 1100006, "pages_workflow_id": 1100007, "validation_workflow_id": 1100008, "pages_environment_id": 1100009,
             "validation_workflow_path": ".github/workflows/qualification-validation.yml",
             "validation_workflow_commit": "c" * 40, "validation_workflow_sha256": base.sha(VALIDATION),
             "validation_job_name": "qualification-validation", "campaign_id": "d" * 32,
             "installation_uuid": "e" * 32, "epoch": 1, "fixture_source": source,
             "evidence_expires_at": base.utc(now + timedelta(hours=4)), "policy_sha256": "0" * 64}
    from publication_github_live import expected_policy
    value["policy_sha256"] = base.sha(base.canonical(expected_policy(value)))
    value["identity_evidence"] = {"kind": "local-test-fixture", "observed_at": base.utc(now),
        "repository_sha256": base.sha(b"local repository API fixture"), "installation_sha256": base.sha(b"local App API fixture"),
        "source_sha256": base.sha(base.canonical(source)), "policy_sha256": value["policy_sha256"]}
    return contract.validate_enrollment(value)


def role_record(data, role, session, now=NOW):
    return {"schema": 1, "kind": "opencode-role-receipt-v1", "role": role, "tool": "kodi_qualify" if role == "kodi-addon-tester" else "kodi_review", "task": data["payload"]["task"],
            "session": session, "payload_sha256": data["payload_sha256"], "toolchain_sha256": base.sha(base.canonical(data["payload"]["toolchain"])),
            "result": "QUALIFIED_FOR_TRANSPORT", "report": "Independent local inert-fixture inspection; native/interpreter/Piers UNVERIFIED.",
            "recorded_at": base.utc(now)}


def metadata_authorization(data, now=NOW):
    return {"kind": "local-test-staging", "actor_id": old.OWNER_ID, "payload_sha256": data["payload_sha256"],
            "review_sha256": data["review_sha256"], "task": data["payload"]["task"],
            "destination_sha256": base.sha(base.canonical(contract.transport_enrollment(data["enrollment"]))),
            "branch": contract.ledger_branch(data), "expires_at": base.utc(now + timedelta(hours=1)),
            "metadata_only": True, "authorization_sha256": "0" * 64}


def staged_pr(data, number=12):
    return {"number": number, "id": 1200001 + number, "node_id": "PR_local_test_" + str(number),
            "head_sha": data["payload"]["retention"]["main_commit"], "base_sha": data["payload"]["expected"]["main_sha"],
            "head_ref": contract.ledger_branch(data), "base_ref": "main",
            "url": "https://github.com/" + data["enrollment"]["repository"] + "/pull/" + str(number)}


def build_pilot_material(directory, version="1.0.0", previous=None, now=NOW, *, seal=True, main_head=None, enrollment=None):
    directory = Path(directory); directory.mkdir(parents=True)
    old_previous = None if previous is None else Path(previous).parent / "old-audit/bundle"
    old_bundle = build_d3_bundle(directory / "old-audit", version=version, previous=old_previous, now=now, seal=True)
    # New candidate freeze, not a relabelled mock payload/review/authorization.
    stage = old_bundle.parent / "stage"; e = test_enrollment(now) if enrollment is None else enrollment
    original = old.verify_payload(old_bundle); oldp = original["payload"]
    main_files = {n: base.safe_read(original["root"] / info["path"]) for n, info in oldp["main_base"]["files"].items()}
    main_files[e["validation_workflow_path"]] = VALIDATION
    main_files[".github/CODEOWNERS"] = b"* @kcook98765\n"
    published = {"schema": 1, "packages": []}
    expected = dict(oldp["expected"], main_tree=old.tree(main_files))
    if previous is not None:
        prior = contract.load_material(previous, now=now, observation=True); p = prior["payload"]
        published = p["retention"]["after"]
        main_files = {n: base.safe_read(prior["root"] / i["path"]) for n, i in p["main_base"]["files"].items()}
        main_files.update({"releases/manifest.json": base.safe_read(prior["root"] / p["retention"]["successor_path"]),
                           "config/qualification.json": base.safe_read(prior["root"] / p["retention"]["config_path"])})
        expected = {"main_sha": p["retention"]["main_commit"], "main_tree": p["retention"]["main_tree"], "pages_sha": p["pages"]["commit"],
                    "pages_tree": p["pages"]["tree"], "ledger_sha256": p["retention"]["after_sha256"], "site_files": p["pages"]["site_files"]}
    if main_head is not None: expected["main_sha"] = main_head
    source = {"repository": e["repository"], "repository_id": e["repository_id"], "owner_id": e["owner_id"], "commit": e["fixture_source"]["commits"][version]}
    candidate = directory / "candidate"
    before = {k: v for k, v in expected.items() if k != "main_tree"}
    before.update(ledger_sha256=base.sha(base.safe_read(stage / "releases/candidate-manifest.json")), site_files={})
    base.prepare(stage, candidate, source=source, lanes=["nexus"], expected=before, release_tag=old.ADDON_ID + "-" + version,
                 profile="candidate", synthetic=False, now=now)
    output = directory / "material"
    task = {"id": "1" * 32, "sha256": base.sha(b"local test owner task"), "installation_uuid": e["installation_uuid"], "epoch": e["epoch"]}
    data = contract.prepare_material(candidate, output, enrollment=e, task=task, session="2" * 32,
        published_ledger=published, expected=expected, main_files=main_files, now=now)
    contract.seal_review(output, tester_record=role_record(data, "kodi-addon-tester", "3" * 32, now),
                         reviewer_record=role_record(data, "kodi-release-reviewer", "4" * 32, now), now=now)
    data = contract.load_material(output, now=now)
    contract.preparation_grant(output, authorization=metadata_authorization(data, now), now=now)
    if seal: contract.seal_execution(output, staged_pr(data), now=now)
    return output


class PilotContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup); self.root = Path(self.temp.name)

    def test_material_preserves_truthful_unknowns_and_ledgers(self):
        data = contract.load_material(build_pilot_material(self.root / "one"), now=NOW)
        self.assertEqual(data["payload"]["profile"], contract.PROFILE)
        self.assertFalse(data["production_authorized"]); self.assertFalse(data["network_authorized"])
        self.assertEqual(data["payload"]["retention"]["before"]["packages"], [])
        self.assertEqual(len(data["payload"]["candidate_ledger"]["packages"]), 2)
        for name in ("native_acceptance", "target_interpreter_compatibility", "piers_static"):
            self.assertEqual(data["payload"]["qualification"][name], "UNVERIFIED")

    def test_enrollment_rejects_production_old_mocks_bool_and_origin_aliases(self):
        original = test_enrollment()
        for key, value in (("repository_id", old.PRODUCTION_ID), ("owner_id", True), ("app_id", 900003),
                           ("base_url", "https://kcook98765.github.io/pilot/"), ("human_owner_id", 1)):
            with self.subTest(key=key), self.assertRaises(ValueError): contract.validate_enrollment(dict(original, **{key: value}))

    def test_preparation_has_no_publication_effects(self):
        path = build_pilot_material(self.root / "one", seal=False)
        scope = contract.transport_authority(path, "preparation", now=NOW)
        self.assertTrue(scope["mock_only"])
        self.assertEqual(set(scope["effects"]), {"create_blob", "create_tree", "create_commit", "create_ledger_branch", "create_ledger_pr"})
        with self.assertRaises(ValueError): contract.transport_authority(path, "publication", now=NOW)

    def test_pr_digest_body_cycle_is_absent_and_mutation_rejected(self):
        path = build_pilot_material(self.root / "one"); data = contract.load_material(path, now=NOW)
        self.assertIn(data["digest"], contract.request_body(data))
        self.assertNotIn(data["digest"], base.canonical(contract.scope_projection(data)).decode())
        x = data["execution"]; x["pr"]["head_sha"] = "f" * 40
        (path / "execution.json").write_bytes(base.canonical(x))
        with self.assertRaises(ValueError): contract.load_material(path, now=NOW)

    def test_new_grants_require_separate_authorization_and_exact_role_sessions(self):
        path = build_pilot_material(self.root / "one", seal=False)
        (path / "preparation.json").unlink()
        with self.assertRaisesRegex(ValueError, "Separate"): contract.preparation_grant(path, now=NOW)
        data = contract.load_material(path, now=NOW); r = data["review"]
        r["reviewer"]["session"] = r["tester"]["session"]
        (path / "review.json").write_bytes(base.canonical(r))
        with self.assertRaises(ValueError): contract.load_material(path, now=NOW)

    def test_expiry_one_hour_and_digest_guard(self):
        path = build_pilot_material(self.root / "one", seal=False); data = contract.load_material(path, now=NOW)
        with self.assertRaises(ValueError): contract.seal_execution(path, staged_pr(data), lifetime=3601, now=NOW)
        contract.seal_execution(path, staged_pr(data), now=NOW)
        with self.assertRaises(ValueError): contract.load_material(path, "0" * 64, now=NOW)
        with self.assertRaises(ValueError): contract.load_material(path, now=NOW + timedelta(hours=2))
        self.assertFalse(contract.load_material(path, now=NOW + timedelta(hours=2), observation=True)["production_authorized"])

    def test_update_retains_prior_package_and_stable_installer_campaign(self):
        first = build_pilot_material(self.root / "one")
        second = build_pilot_material(self.root / "two", version="1.1.0", previous=first, now=NOW + timedelta(minutes=1))
        a = contract.load_material(first, now=NOW); b = contract.load_material(second, now=NOW + timedelta(minutes=1))
        self.assertEqual(a["enrollment"]["campaign_id"], b["enrollment"]["campaign_id"])
        self.assertEqual(a["payload"]["retention"]["after"], b["payload"]["retention"]["before"])
        self.assertEqual(len(b["payload"]["release"]["assets"]), 3)
        for path, sha in a["payload"]["pages"]["site_files"].items():
            if path.endswith((".zip", ".zip.sha256")): self.assertEqual(b["payload"]["pages"]["site_files"][path], sha)

    def test_campaign_rebuild_uses_existing_builder_and_reproduces_feed(self):
        import publication_pilot_candidate as builder
        material = build_pilot_material(self.root / "source")
        data = contract.load_material(material, now=NOW)
        first = builder.prepare_candidate(material / "candidate", self.root / "rebuilt-one", enrollment=data["enrollment"], now=NOW)
        second = builder.prepare_candidate(material / "candidate", self.root / "rebuilt-two", enrollment=data["enrollment"], now=NOW)
        a = base.verify_payload(first); b = base.verify_payload(second)
        self.assertEqual(a["payload"]["pages"]["site_files"], b["payload"]["pages"]["site_files"])
        self.assertEqual(a["payload"]["packages"], b["payload"]["packages"])
        cfg = json.loads(base.safe_read(a["root"] / "config/candidate-repository.json"))
        self.assertEqual(cfg["addon_id"], "repository.ai.kodi.candidate." + data["enrollment"]["campaign_id"])
        self.assertFalse((a["root"] / "dist/production").exists())

    def test_historical_staging_issuer_is_observable_but_not_fresh_metadata_authority(self):
        path = build_pilot_material(self.root / "one"); data = contract.load_material(path, now=NOW)
        grant = data["preparation"]; grant["authorization"]["kind"] = "owner-staging-authorization"
        grant["authorization"]["authorization_sha256"] = "f" * 64
        (path / "preparation.json").write_bytes(base.canonical(grant))
        execution = data["execution"]; execution["preparation_sha256"] = base.sha(base.canonical(grant))
        (path / "execution.json").write_bytes(base.canonical(execution))
        with patch("publication_cli.validate_staging_authority", side_effect=ValueError("Current issuer changed")) as validate:
            observed = contract.load_material(path, now=NOW, observation=True)
            self.assertEqual(validate.call_count, 0)
            self.assertEqual(observed["execution"]["preparation_sha256"], execution["preparation_sha256"])
            self.assertTrue(contract.transport_authority(path, "publication", now=NOW)["mock_only"])
            with self.assertRaisesRegex(ValueError, "issuer changed"):
                contract.transport_authority(path, "preparation", now=NOW)
            self.assertEqual(validate.call_count, 1)

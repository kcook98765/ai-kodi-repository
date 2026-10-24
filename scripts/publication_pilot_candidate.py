"""Rebuild a first-party pilot feed with a stable campaign installer identity.

Inputs are independently frozen candidate data. Installed trusted builders run;
copied add-on source, package entry points and submitted scripts never execute.
"""
from __future__ import annotations
import copy
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
import publication_proposal as base
import publication_pilot_contract as contract
import publication_d3_contract as d3
import audit_candidate
import repository as repo


def _fixture_intake(root, enrollment):
    intake = json.loads(base.safe_read(root / "config/candidate.json", base.MAX_JSON))
    base.require(type(intake) is dict and type(intake.get("packages")) is list, "Missing frozen candidate intake")
    result = {}
    for item in intake["packages"]:
        base.safe_name(item["zip"]); base.safe_name(item["review_record"])
        raw = base.safe_read(root / "incoming" / item["zip"])
        manifest, files = audit_candidate.archive_files(raw)
        version = manifest.get("version")
        base.require(manifest.get("id") == d3.ADDON_ID and version in ("1.0.0", "1.1.0") and version not in result
                     and files == d3.fixture_files(version) and base.sha(raw) == item["sha256"], "Only exact first-party fixture runtime intake is permitted")
        review_raw = base.safe_read(root / "incoming" / item["review_record"], base.MAX_JSON)
        base.require(base.sha(review_raw) == item["review_record_sha256"], "Frozen pending record digest changed")
        review = json.loads(review_raw)
        base.require(review.get("source_repository") == "https://github.com/" + enrollment["repository"]
                     and review.get("source_commit") == enrollment["fixture_source"]["commits"][version], "Pending fixture provenance differs from actual enrolled source")
        result[version] = (raw, review_raw, review)
    return result


def prepare_candidate(candidate_bundle, output, *, enrollment, previous=None, now=None):
    enrollment = contract.validate_enrollment(enrollment)
    current = base.verify_payload(candidate_bundle); p = current["payload"]
    base.require({f.name for f in Path(candidate_bundle).iterdir()} == {"payload.json", "snapshot"}
                 and p["profile"] == "candidate" and p["synthetic"] is False, "Exact fresh candidate P-only input required")
    selected = [i for i in p["packages"] if i["id"] == d3.ADDON_ID and i["lanes"]]
    base.require(len(selected) == 1 and selected[0]["lanes"] == ["nexus"], "Pilot selects one Nexus fixture release")
    version = selected[0]["version"]
    base.require(p["source"] == {"repository": enrollment["repository"], "repository_id": enrollment["repository_id"],
                                "owner_id": enrollment["owner_id"], "commit": enrollment["fixture_source"]["commits"].get(version)}, "Fresh candidate source identity differs from enrollment")
    available = _fixture_intake(current["root"], enrollment)
    base.require(version in available, "Selected source runtime missing")
    retained_raw = {}; prior = None
    if previous is not None:
        prior = contract.load_material(previous, now=now, observation=True)
        base.require(contract.same(prior["enrollment"], enrollment), "Campaign enrollment changed during update")
        old = _fixture_intake(prior["root"], enrollment)
        for old_version, item in old.items():
            if old_version in available: base.require(available[old_version][0] == item[0], "Historical runtime ZIP mutation")
            available.setdefault(old_version, item); retained_raw[old_version] = item[1]
    versions = ["1.0.0"] if version == "1.0.0" else ["1.0.0", "1.1.0"]
    base.require(version in ("1.0.0", "1.1.0") and all(v in available for v in versions)
                 and ((version == "1.0.0" and prior is None) or (version == "1.1.0" and prior is not None
                       and prior["payload"]["qualification"]["version"] == "1.0.0")), "Pilot update requires the exact retained 1.0.0 baseline")
    output = Path(output).absolute()
    base.require(not output.exists() and not output.is_relative_to(Path(candidate_bundle).absolute())
                 and (previous is None or not output.is_relative_to(Path(previous).absolute()))
                 and not any(p.is_symlink() for p in [output, *output.parents]), "Output exists, is linked or overlaps frozen input")
    output.mkdir(parents=True); stage = output / "stage"
    for name in base.inventory(current["root"]):
        if name == "LICENSE" or name.startswith(("config/", "packages/repository.ai.kodi/", "releases/")):
            base.write_new(stage / name, base.safe_read(current["root"] / name))
    production = json.loads(base.safe_read(stage / "config/repository.json", base.MAX_JSON))
    installer_id = "repository.ai.kodi.candidate." + enrollment["campaign_id"]
    candidate_config = {**production, "addon_id": installer_id, "base_url": enrollment["base_url"],
        "github_repository": enrollment["repository"], "provider": "AI Kodi qualification",
        "candidate_context": {"task_id": enrollment["campaign_id"],
            "production_config_sha256": base.sha(base.safe_read(stage / "config/repository.json")),
            "production_ledger_sha256": base.sha(base.safe_read(stage / "releases/manifest.json"))}}
    # All replacements are inside this newly created disposable stage.
    (stage / "config/candidate-repository.json").write_bytes(repo.json_bytes(candidate_config))
    for name, raw in d3.installer_assets().items():
        target = stage / "packages/repository.ai.kodi" / name; target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(raw)
    with base.stage_context(stage):
        for name, raw in repo.installer(candidate_config, "candidate").items(): base.write_new(stage / "packages" / installer_id / name, raw)
    intake = {"schema": 1, "external_dependencies": {}, "packages": []}
    for selected_version in versions:
        blob, record_raw, record = available[selected_version]
        lanes = ["nexus"] if selected_version == version else []
        # Preserve the original pending record as evidence; create an explicit
        # candidate lane projection rather than mutating that historical record.
        old_record = record_raw; record = copy.deepcopy(record)
        if "approval_lanes" in record: record["approval_lanes"] = lanes
        record_raw = repo.json_bytes(record)
        zip_name = d3.ADDON_ID + "-" + selected_version + ".zip"
        record_name = "pilot-" + selected_version + "-pending.json"
        base.write_new(stage / "incoming" / zip_name, blob); base.write_new(stage / "incoming" / record_name, record_raw)
        base.write_new(stage / "incoming/preserved-reviews" / (base.sha(old_record) + ".json"), old_record)
        intake["packages"].append({"zip": zip_name, "sha256": base.sha(blob), "review_record": record_name,
                                  "review_record_sha256": base.sha(record_raw), "lanes": lanes})
    (stage / "config/candidate.json").write_bytes(repo.json_bytes(intake))
    ledger = {"schema": 1, "repository_id": installer_id, "packages": []}
    (stage / "releases/candidate-manifest.json").write_bytes(repo.json_bytes(ledger))
    with base.stage_context(stage):
        repo.build("candidate"); plan = json.loads(base.safe_read(stage / "dist/candidate/release-plan.json", base.MAX_JSON))
        ledger["packages"] = [{k: item[k] for k in ("id", "version", "sha256")} for item in plan["packages"]]
        (stage / "releases/candidate-manifest.json").write_bytes(repo.json_bytes(ledger)); repo.build("candidate")
    expected = copy.deepcopy(p["expected"])
    expected.update(ledger_sha256=base.sha(base.safe_read(stage / "releases/candidate-manifest.json")), site_files={})
    frozen = output / "candidate"
    base.prepare(stage, frozen, source=p["source"], lanes=["nexus"], expected=expected,
                 release_tag=d3.ADDON_ID + "-" + version, profile="candidate", synthetic=False, now=now)
    return frozen

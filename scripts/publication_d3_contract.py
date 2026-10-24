"""Versioned, mock-only D3 transport qualification. Never production authority."""
from __future__ import annotations

from datetime import timedelta
import copy
import json
from pathlib import Path
import re
import struct
import sys
import uuid
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parent))
import publication_proposal as base
import audit_candidate
import repository as repo

ROOT = Path(__file__).resolve().parents[1]
MODE = "isolated-transport-qualification"
OWNER_ID = 56806582
QUAL_REPOSITORY = "kcook98765-kodi-qualification/ai-kodi-publisher-d3-qualification"
QUAL_BASE = "https://kcook98765-kodi-qualification.github.io/ai-kodi-publisher-d3-qualification/"
ADDON_ID = "script.ai.kodi.d3.fixture"
PRODUCTION_ID = 1428864210
ENROLL_FIELDS = {"schema", "mode", "mock_only", "repository", "repository_id", "owner_id", "owner_type",
                "human_owner_id", "base_url", "branch", "path", "app_id", "app_installation_id", "bot_user_id",
                "bot_login", "environment_id", "environment_name", "workflow_id", "workflow_path", "workflow_commit",
                "workflow_sha256", "control_issue_number", "campaign_id", "installation_uuid", "epoch",
                "fixture_source", "evidence_expires_at", "policy_sha256", "pages_environment_id", "pages_workflow_id"}


def same(left, right):
    return base.canonical(left) == base.canonical(right)


def git_path(name):
    base.require(type(name) is str and name.isascii() and "%" not in name, "Unsafe Git metadata path")
    repo.safe_path(ROOT, name, exists=False)
    base.require(not any(p == ".git" for p in Path(name).parts), "Git control data forbidden")
    return name


def tree(files):
    """Git tree over trusted-data paths, including the reviewed workflow baseline."""
    repo.inventory_paths(files)
    nested = {}
    for name, raw in files.items():
        parts = git_path(name).split("/"); node = nested
        for component in parts[:-1]:
            base.require(component not in node or type(node[component]) is dict, "Git path collision")
            node = node.setdefault(component, {})
        base.require(parts[-1] not in node and type(raw) is bytes, "Duplicate or nonbytes Git entry")
        node[parts[-1]] = raw
    def encode(node):
        raw = b""
        for name in sorted(node, key=lambda k: (k + "/" if type(node[k]) is dict else k).encode()):
            item = node[name]; directory = type(item) is dict
            checksum = encode(item) if directory else base.git_object("blob", item)
            raw += (b"40000" if directory else b"100644") + b" " + name.encode() + b"\0" + bytes.fromhex(checksum)
        return base.git_object("tree", raw)
    return encode(nested)


def fixture_files(version):
    base.require(version in ("1.0.0", "1.1.0"), "Unsupported D3 fixture version")
    xml = (f'<addon id="{ADDON_ID}" version="{version}" name="D3 transport fixture" provider-name="AI Kodi qualification">'
           '<requires><import addon="xbmc.python" version="3.0.1"/></requires>'
           '<extension point="xbmc.python.script" library="default.py"/>'
           '<extension point="xbmc.addon.metadata"><summary>D3 inert transport qualification</summary>'
           '<description>First-party synthetic fixture; no native compatibility claim.</description>'
           '<platform>all</platform><license>MIT</license></extension></addon>').encode()
    return {"addon.xml": repo.xml_bytes(repo.parse_xml(xml)),
            "default.py": b"# First-party D3 inert transport qualification fixture.\n",
            "LICENSE.txt": base.safe_read(ROOT / "LICENSE")}


def source_materials():
    result = {}; parent = None
    for version in ("1.0.0", "1.1.0"):
        files = {"fixtures/addon/" + n: raw for n, raw in fixture_files(version).items()}
        root = tree(files)
        body = (f"tree {root}\n" + (f"parent {parent}\n" if parent else "") +
                "author D3 Fixture <fixture@example.invalid> 0 +0000\n"
                "committer D3 Fixture <fixture@example.invalid> 0 +0000\n\n" +
                "Immutable local D3 fixture " + version + "\n").encode()
        checksum = base.git_object("commit", body)
        result[version] = {"commit": checksum, "tree": root, "commit_body": body.decode(),
                           "files": {n: base.sha(raw) for n, raw in fixture_files(version).items()}}
        parent = checksum
    return result


def installer_assets():
    """A first-party fixed pixel; no downloaded or third-party artwork."""
    def chunk(kind, raw):
        return struct.pack("!I", len(raw)) + kind + raw + struct.pack("!I", zlib.crc32(kind + raw) & 0xffffffff)
    image = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack("!IIBBBBB", 1, 1, 8, 6, 0, 0, 0))
             + chunk(b"IDAT", zlib.compress(b"\0\x30\x70\xb0\xff")) + chunk(b"IEND", b""))
    notice = b"First-party D3 qualification icon generated from a fixed RGBA pixel.\n\n" + base.safe_read(ROOT / "LICENSE")
    return {"resources/icon.png": image, "resources/ICON-LICENSE.txt": notice, "LICENSE.txt": base.safe_read(ROOT / "LICENSE")}


def mock_environment(enrolled, pages=False):
    return {"id": enrolled["pages_environment_id"] if pages else enrolled["environment_id"],
            "name": "github-pages" if pages else enrolled["environment_name"], "can_admins_bypass": False,
            "deployment_branch_policy": {"protected_branches": False, "custom_branch_policies": True},
            "protection_rules": [{"type": "required_reviewers", "prevent_self_review": True,
                "reviewers": [{"type": "User", "reviewer": {"id": enrolled["human_owner_id"], "type": "User", "login": "kcook98765"}}]},
                {"type": "branch_policy"}]}


def mock_policy(enrolled):
    """Concrete synthetic API policy fixture derived from the reviewed plan."""
    desired = json.loads(base.safe_read(ROOT / "plans/d3/PUBLISHER-QUALIFICATION-DESIRED-STATE.json"))
    rules = []
    for index, item in enumerate(desired["ruleset_designs"], 1):
        bypass = copy.deepcopy(item["bypass_actors"])
        for actor in bypass:
            actor["actor_id"] = enrolled["app_id"]
        entries = []
        for name in item["rules"]:
            rule = {"type": name}
            if name == "pull_request":
                rule["parameters"] = {k: item[k] for k in ("required_approving_review_count", "dismiss_stale_reviews_on_push",
                    "require_code_owner_review", "require_last_push_approval", "required_review_thread_resolution")}
            elif name == "required_status_checks":
                rule["parameters"] = {"strict_required_status_checks_policy": True,
                    "required_status_checks": [{"context": item["required_check_context"], "integration_id": 900010}]}
            elif name == "update":
                rule["parameters"] = {"update_allows_fetch_and_merge": False}
            entries.append(rule)
        rules.append({"id": 910000 + index, "name": item["name"], "target": item["target"], "enforcement": "active",
                      "bypass_actors": bypass, "conditions": {"ref_name": {"include": item["refs"], "exclude": item.get("exclude_refs", [])}}, "rules": entries})
    return {"rulesets": rules, "environments": {"kodi-d3-publication": mock_environment(enrolled), "github-pages": mock_environment(enrolled, True)},
            "mock_only": True, "production_authorized": False}


def validate_enrollment(value):
    base.closed(value, ENROLL_FIELDS)
    base.require(type(value["schema"]) is int and value["schema"] == 1 and value["mode"] == MODE
                 and value["mock_only"] is True, "Only versioned local D3 mocks are supported")
    base.require(value["repository"] == QUAL_REPOSITORY and value["base_url"] == QUAL_BASE
                 and value["owner_type"] == "Organization" and value["branch"] == "gh-pages"
                 and value["path"] == "/", "Unenrolled, aliased or production destination")
    ids = ["repository_id", "owner_id", "human_owner_id", "app_id", "app_installation_id", "bot_user_id",
           "environment_id", "workflow_id", "control_issue_number", "epoch", "pages_environment_id", "pages_workflow_id"]
    base.require(all(type(value[k]) is int and 0 < value[k] <= 2**53 - 1 for k in ids), "Missing or mistyped numeric enrollment identity")
    typed_ids = [value[k] for k in ("repository_id", "owner_id", "human_owner_id", "app_id", "app_installation_id", "bot_user_id")]
    base.require(len(set(typed_ids)) == len(typed_ids) and value["human_owner_id"] == OWNER_ID
                 and PRODUCTION_ID not in typed_ids, "Human, organization, App, installation and bot identities must be distinct")
    base.require(value["pages_environment_id"] != value["environment_id"] and value["pages_workflow_id"] != value["workflow_id"], "Pages approval must be separately enrolled")
    base.require(type(value["bot_login"]) is str and re.fullmatch(r"[a-z0-9-]+\[bot\]", value["bot_login"]), "Invalid enrolled App bot login")
    base.require(value["environment_name"] == "kodi-d3-publication"
                 and value["workflow_path"] == ".github/workflows/publication-approval.yml", "Unenrolled approval surface")
    for name, expression in (("campaign_id", base.HEX32), ("installation_uuid", base.HEX32),
                             ("workflow_commit", base.HEX40), ("workflow_sha256", base.HEX64), ("policy_sha256", base.HEX64)):
        base.require(type(value[name]) is str and expression.fullmatch(value[name]), "Invalid enrolled hash/identity")
    source = value["fixture_source"]; base.closed(source, {"branch", "commits", "files"})
    material = source_materials()
    base.require(source["branch"] == "d3-fixture-source"
                 and same(source["commits"], {v: m["commit"] for v, m in material.items()})
                 and same(source["files"], {v: m["files"] for v, m in material.items()}),
                 "Fixture source must bind both immutable first-party source versions")
    base.timestamp(value["evidence_expires_at"])
    base.require(value["policy_sha256"] == base.sha(base.canonical(mock_policy(value))), "Enrolled mock policy differs from reviewed split rules")
    return copy.deepcopy(value)


def transport_enrollment(value):
    value = validate_enrollment(value)
    keys = ("mode", "repository", "repository_id", "owner_id", "human_owner_id", "app_id", "app_installation_id", "branch", "path")
    return {**{k: value[k] for k in keys}, "origin": value["base_url"]}


def mock_enrollment(*, now=None, campaign_id="d" * 32, workflow_bytes=b"# inert local approval workflow projection\n"):
    moment = base.timestamp(now)
    material = source_materials()
    value = {"schema": 1, "mode": MODE, "mock_only": True, "repository": QUAL_REPOSITORY,
        "repository_id": 900001, "owner_id": 900002, "owner_type": "Organization", "human_owner_id": OWNER_ID,
        "base_url": QUAL_BASE, "branch": "gh-pages", "path": "/", "app_id": 900003,
        "app_installation_id": 900004, "bot_user_id": 900005, "bot_login": "ai-kodi-publisher-d3-claw[bot]",
        "environment_id": 900006, "environment_name": "kodi-d3-publication", "workflow_id": 900007,
        "pages_environment_id": 900008, "pages_workflow_id": 900009,
        "workflow_path": ".github/workflows/publication-approval.yml", "workflow_commit": "c" * 40,
        "workflow_sha256": base.sha(workflow_bytes), "control_issue_number": 1, "campaign_id": campaign_id,
        "installation_uuid": "e" * 32, "epoch": 1,
        "fixture_source": {"branch": "d3-fixture-source", "commits": {v: m["commit"] for v, m in material.items()},
                           "files": {v: m["files"] for v, m in material.items()}},
        "evidence_expires_at": base.utc(moment + timedelta(hours=4)), "policy_sha256": "0" * 64}
    value["policy_sha256"] = base.sha(base.canonical(mock_policy(value)))
    return validate_enrollment(value)


def toolchain():
    names = ["scripts/publication_d3_contract.py", "scripts/publication_owner.py", "scripts/publication_github.py", "scripts/publication_d3.py"]
    return {n: base.sha(base.safe_read(ROOT / n)) for n in names}


def _ledger(value):
    base.closed(value, {"schema", "packages"})
    base.require(type(value["schema"]) is int and value["schema"] == 1 and type(value["packages"]) is list, "Malformed published ledger")
    keys = set()
    for item in value["packages"]:
        base.closed(item, {"id", "version", "sha256"})
        base.require(item["id"] == ADDON_ID or re.fullmatch(r"repository\.ai\.kodi\.candidate\.[0-9a-f]{32}", item["id"]), "Production package identity in qualification ledger")
        repo.version(item["version"])
        base.require(type(item["sha256"]) is str and base.HEX64.fullmatch(item["sha256"])
                     and (item["id"], item["version"]) not in keys, "Malformed or duplicate retained qualification artifact")
        keys.add((item["id"], item["version"]))
    return value


def operation_id(operation):
    return operation["kind"] + (":" + operation["name"] if operation["kind"] == "upload_asset" else "")


def operations(payload):
    return ([{"kind": "create_tag"}, {"kind": "create_draft"}] +
            [{"kind": "upload_asset", "name": n} for n in sorted(payload["release"]["assets"])] +
            [{"kind": n} for n in ("verify_assets", "publish_release", "promote_pages", "verify_public", "finalize_ledger")])


def _derived(snapshot, original, enrollment, published, expected, main_files):
    plan = json.loads(base.safe_read(snapshot / "dist/candidate/release-plan.json", base.MAX_JSON))
    packages = plan["packages"]; installer_id = "repository.ai.kodi.candidate." + enrollment["campaign_id"]
    fixture = [p for p in packages if p["id"] == ADDON_ID and p["lanes"]]
    base.require(len(fixture) == 1 and fixture[0]["lanes"] == ["nexus"], "One Nexus fixture release is required")
    fixture = fixture[0]; version = fixture["version"]
    base.require(version in ("1.0.0", "1.1.0"), "Unenrolled fixture version")
    wanted_versions = ["1.0.0"] if version == "1.0.0" else ["1.0.0", "1.1.0"]
    base.require(sorted(p["version"] for p in packages if p["id"] == ADDON_ID) == wanted_versions,
                 "Fixture version inventory exceeds the selected qualification step")
    source = original["source"]
    base.require(source["repository"] == enrollment["repository"] and source["repository_id"] == enrollment["repository_id"]
                 and source["owner_id"] == enrollment["owner_id"] and source["commit"] == enrollment["fixture_source"]["commits"][version], "Fixture source identity or immutable commit changed")
    base.require(set(p["id"] for p in packages) == {ADDON_ID, installer_id}, "Unreviewed or production package in qualification feed")
    for item in packages:
        manifest, files = audit_candidate.archive_files(base.safe_read(snapshot / "dist/candidate/site" / item["path"]))
        if item["id"] == ADDON_ID:
            base.require(same({n: base.sha(raw) for n, raw in files.items()}, enrollment["fixture_source"]["files"][item["version"]])
                         and files == fixture_files(item["version"]), "Fixture runtime bytes are not the independently pinned inert MIT source")
            base.require(item["provenance"].get("source_repository") == "https://github.com/" + enrollment["repository"]
                         and item["provenance"].get("source_commit") == enrollment["fixture_source"]["commits"][item["version"]],
                         "Retained fixture provenance no longer identifies its enrolled immutable source")
        else:
            base.require(item["version"] == "0.1.0", "Installer maintenance needs separate qualification")
            base.require(all(files.get(n) == raw for n, raw in installer_assets().items()), "Installer contains unreviewed material or artwork")
            for node in manifest.findall("extension[@point='xbmc.addon.repository']/dir/*"):
                if node.tag in ("info", "checksum", "datadir", "artdir"):
                    base.require(node.text.startswith(enrollment["base_url"] + "candidate/"), "Installer destination escaped isolated feed")
    published = _ledger(published)
    old = {(p["id"], p["version"]): p["sha256"] for p in published["packages"]}
    actual = {(p["id"], p["version"]): p for p in packages}
    base.require(all(k in actual and actual[k]["sha256"] == checksum for k, checksum in old.items()), "Published qualification artifact removed or changed")
    old_versions = [p["version"] for p in published["packages"] if p["id"] == ADDON_ID]
    base.require((version == "1.0.0" and not old_versions) or (version == "1.1.0" and old_versions == ["1.0.0"]), "Qualification sequence must publish 1.0.0 before 1.1.0")
    if not published["packages"]:
        base.require(not expected["site_files"], "Initial empty published ledger cannot hide existing public files")
    current = list(published["packages"])
    assets = {}
    for item in packages:
        if (item["id"], item["version"]) in old:
            continue
        current.append({k: item[k] for k in ("id", "version", "sha256")})
        for name in (Path(item["path"]).name, Path(item["path"]).name + ".sha256"):
            path = "dist/candidate/release-assets/" + name; raw = base.safe_read(snapshot / path)
            assets[name] = {"path": path, "sha256": base.sha(raw), "size": len(raw)}
    sums = "".join(f'{assets[n]["sha256"]}  {n}\n' for n in sorted(assets)).encode()
    assets["SHA256SUMS"] = {"path": "d3-data/SHA256SUMS", "sha256": base.sha(sums), "size": len(sums)}
    after = {"schema": 1, "packages": current}; after_raw = repo.json_bytes(after)
    config = {"schema": 1, "campaign_id": enrollment["campaign_id"], "published_packages": current,
              "production_authorized": False, "mode": MODE}
    config_raw = base.canonical(config)
    changes = dict(main_files, **{"releases/manifest.json": after_raw, "config/qualification.json": config_raw})
    main_tree = tree(changes)
    release = {"tag": ADDON_ID + "-" + version, "commit": expected["main_sha"], "name": "D3 transport fixture " + version,
               "notes": "Synthetic isolated transport qualification only; native/interpreter/Piers UNVERIFIED; production authority false.", "assets": assets}
    pages = copy.deepcopy(original["pages"])
    pages["parent"] = expected["pages_sha"]
    pages["commit"] = base.git_commit(pages["tree"], pages["parent"], "Simulated reviewed Pages publication")
    pages["changes"] = [{"path": n, "before": expected["site_files"].get(n), "after": checksum}
                        for n, checksum in sorted(pages["site_files"].items()) if expected["site_files"].get(n) != checksum]
    base.require(set(expected["site_files"]) <= set(pages["site_files"]), "Qualification Pages deletion forbidden")
    for name, checksum in expected["site_files"].items():
        if name.endswith((".zip", ".zip.sha256")):
            base.require(pages["site_files"][name] == checksum, "Historical public qualification bytes changed")
    retention = {"before": published, "after": after, "before_sha256": base.sha(repo.json_bytes(published)),
                 "after_sha256": base.sha(after_raw), "successor_path": "d3-data/manifest.json",
                 "config_path": "d3-data/qualification.json", "config_sha256": base.sha(config_raw),
                 "main_parent": expected["main_sha"], "main_tree": main_tree,
                 "main_commit": base.git_commit(main_tree, expected["main_sha"], "Simulated retention finalization")}
    candidate_path = "releases/candidate-manifest.json"
    candidate_raw = base.safe_read(snapshot / candidate_path)
    candidate_ledger = json.loads(candidate_raw)
    base.closed(candidate_ledger, {"schema", "repository_id", "packages"})
    base.require(type(candidate_ledger["schema"]) is int and candidate_ledger["schema"] == 1
                 and candidate_ledger["repository_id"] == installer_id
                 and same(candidate_ledger["packages"], [{k: p[k] for k in ("id", "version", "sha256")} for p in packages]),
                 "Candidate commitment ledger differs from complete reviewed campaign inventory")
    baseline = {"files": {n: {"sha256": base.sha(raw), "path": "d3-main/" + base.sha(raw)} for n, raw in sorted(main_files.items())},
                "tree": tree(main_files), "commit": expected["main_sha"]}
    qualification = {"addon_id": ADDON_ID, "version": version, "package_sha256": fixture["sha256"],
                     "source_commit": source["commit"], "runtime_files": enrollment["fixture_source"]["files"][version],
                     "material_review": "first-party-inert-MIT-fixture", "provider_integration": False,
                     "offline_audit": "verified-frozen-candidate", "native_acceptance": "UNVERIFIED",
                     "target_interpreter_compatibility": "UNVERIFIED", "piers_static": "UNVERIFIED",
                     "production_authorized": False}
    return {"release": release, "pages": pages, "retention": retention, "main_base": baseline,
            "qualification": qualification, "candidate_ledger": candidate_ledger,
            "candidate_ledger_sha256": base.sha(candidate_raw)}, sums, after_raw, config_raw


def assemble(base_bundle, output, *, enrollment, published_ledger, expected, main_files,
             qualification_report, reviewer_report, now=None):
    enrollment = validate_enrollment(enrollment); current = base.verify_payload(base_bundle)
    base.require({p.name for p in Path(base_bundle).iterdir()} == {"snapshot", "payload.json"}, "D3 intake requires a complete P-only candidate without extra controls")
    original = current["payload"]
    base.require(original["profile"] == "candidate" and original["synthetic"] is False, "D3 must reuse a truthful frozen candidate, never simulation approval")
    base.closed(expected, {"main_sha", "main_tree", "pages_sha", "pages_tree", "ledger_sha256", "site_files"})
    base.validate_expected({k: expected[k] for k in expected if k != "main_tree"})
    base.require(type(expected["main_tree"]) is str and base.HEX40.fullmatch(expected["main_tree"])
                 and tree(main_files) == expected["main_tree"], "Complete baseline main tree must match expected remote state")
    base.require(enrollment["workflow_path"] in main_files and base.sha(main_files[enrollment["workflow_path"]]) == enrollment["workflow_sha256"], "Pinned approval workflow bytes missing from complete main baseline")
    base.require(main_files.get("releases/manifest.json") == repo.json_bytes(_ledger(published_ledger))
                 and expected["ledger_sha256"] == base.sha(repo.json_bytes(published_ledger)), "Published ledger baseline differs from main")
    base.require(type(qualification_report) is bytes and qualification_report and type(reviewer_report) is bytes and reviewer_report,
                 "Independent qualification and review reports required")
    output = Path(output).absolute()
    base.require(not output.exists() and not output.is_relative_to(Path(base_bundle).absolute()), "D3 output already exists or overlaps input")
    output.mkdir(parents=True); snapshot = output / "snapshot"; snapshot.mkdir()
    for name in base.inventory(Path(base_bundle)):
        base.write_new(output / "base" / name, base.safe_read(Path(base_bundle) / name))
    for name in base.inventory(current["root"]):
        base.write_new(snapshot / name, base.safe_read(current["root"] / name))
    derived, sums, ledger_raw, config_raw = _derived(snapshot, original, enrollment, published_ledger, expected, main_files)
    for name, raw in (("d3-data/SHA256SUMS", sums), ("d3-data/manifest.json", ledger_raw),
                      ("d3-data/qualification.json", config_raw), ("d3-data/qualification-report.txt", qualification_report)):
        base.write_new(snapshot / name, raw)
    for raw in main_files.values():
        path = snapshot / "d3-main" / base.sha(raw)
        if not path.exists(): base.write_new(path, raw)
    payload = {"schema": 1, "kind": "d3-qualification-payload-v1", "mode": MODE, "mock_only": True,
               "production_authorized": False, "created_at": base.utc(now), "enrollment": enrollment,
               "base_payload_sha256": current["payload_sha256"], "toolchain": toolchain(),
               "source": original["source"], "campaign_id": enrollment["campaign_id"],
               "expected": expected, "files": base.inventory(snapshot), "packages": original["packages"],
               "catalogs": original["catalogs"], "qualification_report_sha256": base.sha(qualification_report), **derived}
    base.write_new(output / "payload.json", base.canonical(payload))
    report_path = output / "review-report.txt"; base.write_new(report_path, reviewer_report)
    review = {"schema": 1, "kind": "d3-independent-review-v1", "mode": MODE, "mock_only": True,
              "payload_sha256": base.sha(base.canonical(payload)), "report_sha256": base.sha(reviewer_report),
              "role": "kodi-release-reviewer", "created_at": base.utc(now), "production_authorized": False}
    base.write_new(output / "review.json", base.canonical(review))
    verify_payload(output)
    return payload


def verify_payload(path):
    path = Path(path).absolute(); payload = base.strict_load(base.safe_read(path / "payload.json", base.MAX_JSON))
    base.closed(payload, {"schema", "kind", "mode", "mock_only", "production_authorized", "created_at", "enrollment",
                          "base_payload_sha256", "toolchain", "source", "campaign_id", "expected", "files", "packages",
                          "catalogs", "qualification_report_sha256", "release", "pages", "retention", "main_base",
                          "qualification", "candidate_ledger", "candidate_ledger_sha256"})
    base.require(type(payload["schema"]) is int and payload["schema"] == 1 and payload["kind"] == "d3-qualification-payload-v1"
                 and payload["mode"] == MODE and payload["mock_only"] is True and payload["production_authorized"] is False,
                 "Only local D3 qualification payloads are supported")
    enrollment = validate_enrollment(payload["enrollment"]); snapshot = path / "snapshot"
    base.require(same(payload["toolchain"], toolchain()) and same(payload["files"], base.inventory(snapshot)), "Frozen D3 toolchain or snapshot changed")
    original = base.verify_payload(path / "base")
    base.require({p.name for p in (path / "base").iterdir()} == {"snapshot", "payload.json"}, "Unreviewed base candidate controls")
    base.require(original["payload_sha256"] == payload["base_payload_sha256"]
                 and same(original["payload"]["source"], payload["source"])
                 and same(original["payload"]["packages"], payload["packages"])
                 and same(original["payload"]["catalogs"], payload["catalogs"]), "Base candidate metadata changed")
    for name, item in original["payload"]["files"].items():
        base.require(name in payload["files"] and same(item, payload["files"][name]), "D3 changed the independently frozen candidate")
    base.require(payload["campaign_id"] == enrollment["campaign_id"], "Campaign feed identity changed")
    base.timestamp(payload["created_at"])
    expected = payload["expected"]; base.closed(expected, {"main_sha", "main_tree", "pages_sha", "pages_tree", "ledger_sha256", "site_files"})
    base.validate_expected({k: expected[k] for k in expected if k != "main_tree"})
    main = payload["main_base"]; base.closed(main, {"files", "tree", "commit"}); main_files = {}
    base.require(type(main["files"]) is dict, "Main baseline inventory missing")
    for name, item in main["files"].items():
        git_path(name); base.closed(item, {"sha256", "path"}); base.safe_name(item["path"])
        raw = base.safe_read(snapshot / item["path"])
        base.require(item["path"] == "d3-main/" + base.sha(raw) and item["sha256"] == base.sha(raw), "Main baseline bytes changed")
        main_files[name] = raw
    base.require(tree(main_files) == expected["main_tree"] == main["tree"] and main["commit"] == expected["main_sha"]
                 and enrollment["workflow_path"] in main_files and base.sha(main_files[enrollment["workflow_path"]]) == enrollment["workflow_sha256"], "Complete main baseline or trusted workflow changed")
    published = _ledger(payload["retention"]["before"])
    base.require(main_files.get("releases/manifest.json") == repo.json_bytes(published)
                 and expected["ledger_sha256"] == base.sha(repo.json_bytes(published)), "Published baseline ledger does not match main")
    derived, sums, ledger_raw, config_raw = _derived(snapshot, original["payload"], enrollment, published, expected, main_files)
    base.require(all(same(payload[k], v) for k, v in derived.items()), "D3 proposal exceeds independently derived qualification scope")
    for name, raw in (("d3-data/SHA256SUMS", sums), ("d3-data/manifest.json", ledger_raw), ("d3-data/qualification.json", config_raw)):
        base.require(base.safe_read(snapshot / name) == raw, "Frozen D3 successor bytes changed")
    base.require(base.sha(base.safe_read(snapshot / "d3-data/qualification-report.txt")) == payload["qualification_report_sha256"], "Qualification report changed")
    return {"payload": payload, "payload_sha256": base.sha(base.canonical(payload)), "root": snapshot, "enrollment": enrollment,
            "transport_eligible": True, "production_authorized": False, "network_authorized": False,
            "production_blockers": ["Local D3 mocks grant no remote authority", "Production retained private inputs not verified",
                                    "Native acceptance UNVERIFIED", "Target interpreter compatibility UNVERIFIED", "Piers static UNVERIFIED"]}


def seal_execution(path, *, nonce=None, lifetime=3600, now=None, recovery=None):
    data = verify_payload(path); path = Path(path); moment = base.timestamp(now)
    review = base.strict_load(base.safe_read(path / "review.json", base.MAX_JSON))
    base.require(type(lifetime) is int and 0 < lifetime <= 3600, "D3 owner request lifetime is at most one hour")
    expires = min(moment + timedelta(seconds=lifetime), base.timestamp(data["enrollment"]["evidence_expires_at"]))
    base.require(expires > moment, "D3 qualification evidence expired")
    approved = operations(data["payload"]); completed = []
    if recovery is not None:
        base.closed(recovery, {"transaction", "remote_state_sha256", "completed"})
        base.require(all(type(recovery[k]) is str and base.HEX64.fullmatch(recovery[k]) for k in ("transaction", "remote_state_sha256")), "Malformed recovery binding")
        completed = recovery["completed"]
        base.require(type(completed) is list and completed == [operation_id(o) for o in approved[:len(completed)]], "Recovery must bind the exact completed prefix")
    execution = {"schema": 1, "kind": "d3-execution-proposal-v1", "mode": MODE, "mock_only": True, "production_authorized": False,
                 "payload_sha256": data["payload_sha256"], "review_sha256": base.sha(base.canonical(review)),
                 "enrollment_sha256": base.sha(base.canonical(data["enrollment"])), "expected": data["payload"]["expected"],
                 "destination": transport_enrollment(data["enrollment"]), "nonce": uuid.uuid4().hex if nonce is None else nonce,
                 "created_at": base.utc(moment), "expires_at": base.utc(expires),
                 "audience": {k: data["enrollment"][k] for k in ("installation_uuid", "epoch", "app_id", "app_installation_id")},
                 "operations": approved[len(completed):], "recovery": recovery}
    base.require(type(execution["nonce"]) is str and base.HEX32.fullmatch(execution["nonce"]), "Malformed D3 nonce")
    base.write_new(path / "execution.json", base.canonical(execution))
    return {"execution": execution, "digest": base.sha(base.canonical(execution))}


def load_bundle(path, expected_digest=None, now=None, observation=False):
    data = verify_payload(path); path = Path(path)
    base.require({p.name for p in path.iterdir()} == {"snapshot", "base", "payload.json", "review.json", "review-report.txt", "execution.json"}, "Unexpected D3 bundle controls")
    review = base.strict_load(base.safe_read(path / "review.json", base.MAX_JSON))
    base.closed(review, {"schema", "kind", "mode", "mock_only", "payload_sha256", "report_sha256", "role", "created_at", "production_authorized"})
    base.require(type(review["schema"]) is int and review["schema"] == 1 and review["kind"] == "d3-independent-review-v1"
                 and review["mode"] == MODE and review["mock_only"] is True and review["production_authorized"] is False
                 and review["role"] == "kodi-release-reviewer" and review["payload_sha256"] == data["payload_sha256"]
                 and review["report_sha256"] == base.sha(base.safe_read(path / "review-report.txt")), "D3 independent review binding failed")
    execution = base.strict_load(base.safe_read(path / "execution.json", base.MAX_JSON))
    base.closed(execution, {"schema", "kind", "mode", "mock_only", "production_authorized", "payload_sha256", "review_sha256", "enrollment_sha256", "expected", "destination", "nonce", "created_at", "expires_at", "audience", "operations", "recovery"})
    enrollment = data["enrollment"]
    base.require(type(execution["schema"]) is int and execution["schema"] == 1 and execution["kind"] == "d3-execution-proposal-v1"
                 and execution["mode"] == MODE and execution["mock_only"] is True and execution["production_authorized"] is False,
                 "D3 execution cannot become production authority")
    base.require(execution["payload_sha256"] == data["payload_sha256"] and execution["review_sha256"] == base.sha(base.canonical(review))
                 and execution["enrollment_sha256"] == base.sha(base.canonical(enrollment))
                 and same(execution["expected"], data["payload"]["expected"])
                 and same(execution["destination"], transport_enrollment(enrollment))
                 and same(execution["audience"], {k: enrollment[k] for k in ("installation_uuid", "epoch", "app_id", "app_installation_id")}), "D3 execution scope changed")
    created = base.timestamp(execution["created_at"]); expires = base.timestamp(execution["expires_at"]); current = base.timestamp(now)
    base.require(base.timestamp(data["payload"]["created_at"]) <= base.timestamp(review["created_at"]) <= created < expires
                 and expires - created <= timedelta(hours=1) and expires <= base.timestamp(enrollment["evidence_expires_at"]), "D3 approval/evidence chronology invalid")
    base.require(type(observation) is bool and (observation or created <= current < expires), "D3 proposal expired or future")
    base.require(type(execution["nonce"]) is str and base.HEX32.fullmatch(execution["nonce"]), "Malformed D3 nonce")
    approved = operations(data["payload"]); completed = []
    if execution["recovery"] is not None:
        recovery = execution["recovery"]; base.closed(recovery, {"transaction", "remote_state_sha256", "completed"})
        base.require(all(type(recovery[k]) is str and base.HEX64.fullmatch(recovery[k]) for k in ("transaction", "remote_state_sha256")), "Malformed D3 recovery")
        completed = recovery["completed"]
        base.require(type(completed) is list and len(completed) <= len(approved) and completed == [operation_id(o) for o in approved[:len(completed)]], "D3 recovery prefix changed")
    base.require(same(execution["operations"], approved[len(completed):]), "Unreviewed D3 operations")
    checksum = base.sha(base.canonical(execution))
    base.require(expected_digest is None or checksum == expected_digest, "D3 proposal digest mismatch")
    return dict(data, review=review, execution=execution, digest=checksum)


def owner_summary(data):
    payload = data["payload"]; execution = data["execution"]; enrollment = data["enrollment"]
    return {"scope": "LOCAL MOCK D3 DISPOSABLE TRANSPORT QUALIFICATION", "production_authorized": False,
            "network_authorized": False, "addon": payload["qualification"]["addon_id"],
            "version": payload["qualification"]["version"], "source": payload["source"],
            "lanes": ["nexus"], "native": "UNVERIFIED", "interpreter": "UNVERIFIED", "piers": "UNVERIFIED",
            "destination": transport_enrollment(enrollment), "release_tag": payload["release"]["tag"],
            "assets": {n: {k: a[k] for k in ("sha256", "size")} for n, a in payload["release"]["assets"].items()},
            "pages": {k: payload["pages"][k] for k in ("parent", "tree", "commit", "changes")},
            "retention": {k: payload["retention"][k] for k in ("before_sha256", "after_sha256")},
            "review_sha256": execution["review_sha256"], "proposal_sha256": data["digest"],
            "nonce": execution["nonce"], "expires_at": execution["expires_at"]}

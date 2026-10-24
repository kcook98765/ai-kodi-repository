#!/usr/bin/env python3
"""Local-only frozen publication payloads. No network, credentials or source execution."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import threading
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parent))
import repository as repo
import audit_candidate
import qualify
import check_publication

ROOT = Path(__file__).resolve().parents[1]
SIM_DESTINATION = {"repository": "simulation/ai-kodi-repository", "repository_id": 1,
                   "owner_id": 1, "base_url": "https://publication.invalid/ai-kodi-repository/",
                   "branch": "gh-pages", "path": "/"}
SIM_AUDIENCE = {"installation_uuid": "0" * 32, "epoch": 1, "app_id": 2,
                "app_installation_id": 3,
                "key_policy_sha256": hashlib.sha256(b"local-test-policy-v1").hexdigest()}
KINDS = ["create_tag", "create_draft", "upload_assets", "verify_assets", "publish_release",
         "promote_pages", "verify_public", "finalize_ledger"]
LANES = {"matrix": "19.5", "nexus": "20.5", "omega": "21.3", "piers": "22 preview"}
HEX40 = re.compile(r"[0-9a-f]{40}\Z")
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
HEX32 = re.compile(r"[0-9a-f]{32}\Z")
MAX_FILES = 10000
MAX_BYTES = 512_000_000
MAX_JSON = 16_000_000
_ROOT_LOCK = threading.RLock()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def closed(value, names):
    require(type(value) is dict and set(value) == set(names), "Unknown or missing publication fields")


def canonical(value):
    def check(item):
        require(type(item) in (dict, list, str, int, bool, type(None)), "Unsupported canonical JSON type")
        if type(item) is int:
            require(abs(item) <= 2**53 - 1, "Integer outside interoperable range")
        elif type(item) is str:
            require(not any(0xD800 <= ord(c) <= 0xDFFF for c in item), "Invalid Unicode surrogate")
        elif type(item) is dict:
            require(all(type(k) is str for k in item), "Non-string JSON key")
            for key, part in item.items():
                check(key); check(part)
        elif type(item) is list:
            for part in item:
                check(part)
    check(value)
    result = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")
    require(len(result) <= MAX_JSON, "Canonical document too large")
    return result


def strict_load(raw):
    require(type(raw) is bytes and len(raw) <= MAX_JSON, "Oversized JSON")
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "Duplicate JSON key")
            result[key] = value
        return result
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs,
                           parse_float=lambda _: (_ for _ in ()).throw(ValueError("Float forbidden")),
                           parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Constant forbidden")))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("Invalid JSON") from error
    require(raw == canonical(value), "Noncanonical JSON bytes")
    return value


def timestamp(now=None):
    value = datetime.now(timezone.utc) if now is None else now
    if isinstance(value, str):
        require(re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", value), "Invalid UTC timestamp")
        value = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    require(isinstance(value, datetime) and value.tzinfo is not None, "Expected timezone-aware timestamp")
    return value.astimezone(timezone.utc).replace(microsecond=0)


def utc(value):
    return timestamp(value).strftime("%Y-%m-%dT%H:%M:%SZ")


def safe_name(name):
    require(type(name) is str and name.isascii() and "%" not in name,
            "Only portable unencoded ASCII paths are supported")
    repo.safe_path(ROOT, name, exists=False)
    require(not any(part.startswith(".") and part != ".nojekyll" for part in Path(name).parts),
            "Hidden control path forbidden")
    return name


def safe_read(path, limit=repo.MAX_RUNTIME_BYTES):
    path = Path(path).absolute()
    require(not any(p.is_symlink() for p in [path, *path.parents]), "Linked snapshot input")
    require(".." not in path.parts, "Parent path component forbidden")
    parent = os.open(path.anchor, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for component in path.parts[1:-1]:
            child = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
            os.close(parent); parent = child
        fd = os.open(path.parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
    finally:
        os.close(parent)
    try:
        before = os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and before.st_size <= limit,
                "Nonregular, hard-linked or oversized snapshot input")
        pieces = []; remaining = limit + 1
        while remaining:
            part = os.read(fd, min(1_000_000, remaining))
            if not part:
                break
            pieces.append(part); remaining -= len(part)
        raw = b"".join(pieces); after = os.fstat(fd)
        require(len(raw) <= limit and (before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) ==
                (after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns), "Snapshot input changed while reading")
        return raw
    finally:
        os.close(fd)


def write_new(path, raw):
    path = Path(path).absolute()
    require(not any(p.is_symlink() for p in [path, *path.parents]), "Linked publication output")
    require(".." not in path.parts, "Parent output component forbidden")
    parent = os.open(path.anchor, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for component in path.parts[1:-1]:
            try:
                os.mkdir(component, 0o700, dir_fd=parent)
            except FileExistsError:
                pass
            child = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
            os.close(parent); parent = child
        fd = os.open(path.parts[-1], os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=parent)
    finally:
        os.close(parent)
    with os.fdopen(fd, "wb") as stream:
        stream.write(raw); stream.flush(); os.fsync(stream.fileno())


def inventory(root):
    root = Path(root).absolute()
    require(root.is_dir() and not any(p.is_symlink() for p in [root, *root.parents]), "Unsafe snapshot directory")
    result = {}; total = 0
    for directory, dirs, files in os.walk(root, followlinks=False):
        require(not any((Path(directory) / n).is_symlink() for n in dirs), "Linked snapshot directory")
        for name in sorted(files):
            path = Path(directory) / name; relative = safe_name(path.relative_to(root).as_posix())
            raw = safe_read(path); total += len(raw)
            require(total <= MAX_BYTES and len(result) < MAX_FILES, "Snapshot resource limit")
            result[relative] = {"sha256": sha(raw), "size": len(raw)}
    require(len({n.casefold() for n in result}) == len(result), "Case-colliding snapshot paths")
    repo.inventory_paths(result)
    return dict(sorted(result.items()))


def toolchain():
    names = ["scripts/repository.py", "scripts/audit_candidate.py", "scripts/approval_contract.py",
             "scripts/qualify.py", "scripts/check_publication.py", "scripts/publication_proposal.py",
             "scripts/publication_verify.py", "scripts/publication_operator.py", "scripts/publication_fake.py",
             "scripts/lifecycle_publication.py", "scripts/opencode/kodi.ts", "scripts/opencode/profiles.json",
             "docs/REVIEW-RECORD-SCHEMA.json",
             "docs/PUBLICATION-PROPOSAL-SCHEMA.json"]
    return {n: sha(safe_read(ROOT / n)) for n in names}


@contextmanager
def stage_context(root):
    """Use installed trusted modules, never import or execute copied source."""
    require(__debug__, "Independent audits require nonoptimized Python")
    modules = (repo, audit_candidate, qualify, check_publication)
    with _ROOT_LOCK:
        old = [m.ROOT for m in modules]
        try:
            for module in modules:
                module.ROOT = Path(root)
            yield
        finally:
            for module, prior in zip(modules, old):
                module.ROOT = prior


def destination(value):
    require(type(value) is dict and canonical(value) == canonical(SIM_DESTINATION),
            "Only the enrolled local simulation destination is allowed")


def validate_source(value):
    closed(value, {"repository", "repository_id", "owner_id", "commit"})
    require(type(value["repository"]) is str and re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", value["repository"])
            and not any(p in (".", "..") for p in value["repository"].split("/")), "Invalid source repository")
    require(all(type(value[k]) is int and value[k] > 0 for k in ("repository_id", "owner_id")), "Invalid numeric source identity")
    require(type(value["commit"]) is str and HEX40.fullmatch(value["commit"]), "Immutable source commit required")


def validate_expected(value):
    closed(value, {"main_sha", "pages_sha", "pages_tree", "ledger_sha256", "site_files"})
    for name in ("main_sha", "pages_sha", "pages_tree"):
        require(type(value[name]) is str and HEX40.fullmatch(value[name]), "Invalid expected branch/tree")
    require(type(value["ledger_sha256"]) is str and HEX64.fullmatch(value["ledger_sha256"]), "Invalid ledger digest")
    require(type(value["site_files"]) is dict, "Invalid retained site inventory")
    for name, digest in value["site_files"].items():
        safe_name(name); require(type(digest) is str and HEX64.fullmatch(digest), "Invalid retained file hash")


def git_object(kind, raw):
    return hashlib.sha1(kind.encode() + b" " + str(len(raw)).encode() + b"\0" + raw).hexdigest()


def git_tree(files):
    tree = {}
    for name, raw in files.items():
        target = tree; parts = safe_name(name).split("/")
        for part in parts[:-1]:
            require(part not in target or type(target[part]) is dict, "Git path collision")
            target = target.setdefault(part, {})
        require(parts[-1] not in target, "Duplicate Git path")
        target[parts[-1]] = raw
    def encode(node):
        result = b""
        for name in sorted(node, key=lambda n: (n + "/" if type(node[n]) is dict else n).encode()):
            value = node[name]; directory = type(value) is dict
            digest = encode(value) if directory else git_object("blob", value)
            result += (b"40000" if directory else b"100644") + b" " + name.encode() + b"\0" + bytes.fromhex(digest)
        return git_object("tree", result)
    return encode(tree)


def git_commit(tree, parent, label):
    raw = (f"tree {tree}\nparent {parent}\nauthor Simulation Publisher <simulation@example.invalid> 0 +0000\n"
           f"committer Simulation Publisher <simulation@example.invalid> 0 +0000\n\n{label}\n").encode()
    return git_object("commit", raw)


def selected_plan(root, profile):
    path = root / f"dist/{profile}/release-plan.json"
    require(path.is_file(), "Missing prepared release plan; retained private inputs or qualification unavailable")
    plan = json.loads(safe_read(path, MAX_JSON))
    with stage_context(root):
        repo.verify(profile)
        audited = audit_candidate.audit(profile)
    require(audited["status"] == "PASS", "Independent package audit failed")
    return plan, audited


def evidence_blockers(root, payload):
    blockers = []
    qualification = payload["qualification"]
    require(type(qualification) is dict and set(qualification) <= set(payload["lanes"]), "Qualification lane mismatch")
    for lane in payload["lanes"]:
        receipt = qualification.get(lane)
        if receipt is not None:
            closed(receipt, {"static", "interpreter", "native"})
        for kind in ("static", "interpreter", "native"):
            item = None if receipt is None else receipt[kind]
            if item is not None:
                closed(item, {"status", "target", "scope", "evidence"})
                require(item["status"] in ("passed", "failed", "deferred", "unverified"), "Invalid qualification outcome")
                require(type(item["target"]) is str and item["target"] == LANES[lane]
                        and type(item["scope"]) is str and bool(item["scope"].strip()), "Wrong qualification target/scope")
                require(type(item["evidence"]) is list and bool(item["evidence"]), "Evidence references required")
                for ref in item["evidence"]:
                    closed(ref, {"path", "sha256"}); safe_name(ref["path"])
                    require(ref["path"] in payload["files"] and sha(safe_read(root / ref["path"])) == ref["sha256"],
                            "Qualification evidence hash mismatch")
            # No D1/D2 code authenticates real native/interpreter evidence. Synthetic
            # receipts exercise mechanics only and never authorize production.
            passed = item is not None and item["status"] == "passed" and payload["synthetic"]
            if lane == "piers" and kind == "static":
                passed = False
            if not passed:
                blockers.append(f"{lane}: {kind} UNVERIFIED or not accepted")
    return blockers


def derive(root, payload, observation=False):
    profile = payload["profile"]
    if observation:
        plan = json.loads(safe_read(root / f"dist/{profile}/release-plan.json", MAX_JSON))
        with stage_context(root):
            repo.verify(profile)
        audited = {"release_blockers": ["Fresh release eligibility not assessed in byte-observation mode"]}
    else:
        plan, audited = selected_plan(root, profile)
    require(canonical(payload["packages"]) == canonical(plan["packages"])
            and canonical(payload["catalogs"]) == canonical(plan["catalogs"]), "Frozen package/catalog metadata changed")
    require(payload["plan_sha256"] == sha(safe_read(root / f"dist/{profile}/release-plan.json")), "Release plan changed")
    require(payload["pages"]["site_files"] == plan["site_files"], "Site inventory differs from audited plan")
    blockers = list(audited.get("release_blockers", []))
    production = json.loads(safe_read(root / "config/production.json", MAX_JSON))
    for item in production["packages"]:
        for key in ("zip", "review_record"):
            safe_name(item[key])
            if not (root / "incoming" / item[key]).is_file():
                blockers.append("Missing retained private production input: incoming/" + item[key])
    if profile != "production":
        blockers.append("Candidate feed cannot authorize production promotion")
    if not observation:
        blockers.extend(evidence_blockers(root, payload))
    if not payload["synthetic"]:
        blockers.append("Real publication authorization and evidence authentication are unavailable in D1/D2")
    require(payload["source"]["repository"].startswith("simulation/") or not payload["synthetic"],
            "Synthetic simulation requires an explicit simulation source namespace")
    return sorted(set(blockers))


def semantic_bindings(root, payload):
    """Independently derive scope rather than trust a rehashed proposal's claims."""
    profile = payload["profile"]
    plan = json.loads(safe_read(root / f"dist/{profile}/release-plan.json", MAX_JSON))
    matches = [p for p in plan["packages"]
               if p.get("provenance", {}).get("source_commit") == payload["source"]["commit"]
               and p.get("provenance", {}).get("source_repository") == "https://github.com/" + payload["source"]["repository"]]
    require(len(matches) == 1 and sorted(matches[0]["lanes"]) == sorted(payload["lanes"]),
            "Frozen source or lane identity differs from the audited package")
    package = matches[0]; release = payload["release"]
    for old in plan["packages"]:
        if old["id"] == package["id"]:
            require(old["provenance"].get("source_repository") == "https://github.com/" + payload["source"]["repository"],
                    "Add-on source identity changed from retained records")
    require(type(release["tag"]) is str and re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,150}", release["tag"])
            and ".." not in release["tag"], "Unsafe frozen release tag")
    require(release["name"] == package["id"] + " " + package["version"]
            and release["notes"] == "Local simulated publication; no production authorization.",
            "Release title or notes exceed reviewed local scope")
    expected_assets = {}
    for name in (Path(package["path"]).name, Path(package["path"]).name + ".sha256"):
        path = f"dist/{profile}/release-assets/{name}"; raw = safe_read(root / path)
        expected_assets[name] = {"path": path, "sha256": sha(raw), "size": len(raw)}
    sums = "".join(f'{expected_assets[n]["sha256"]}  {n}\n' for n in sorted(expected_assets)).encode()
    require(safe_read(root / "publication-data/SHA256SUMS") == sums, "Unreviewed Release checksum list")
    expected_assets["SHA256SUMS"] = {"path": "publication-data/SHA256SUMS", "sha256": sha(sums), "size": len(sums)}
    require(release["assets"] == expected_assets, "Release assets differ from exact selected public package")
    ledger_path = "releases/candidate-manifest.json" if profile == "candidate" and (root / "config/candidate-repository.json").exists() else "releases/manifest.json"
    ledger_raw = safe_read(root / ledger_path); ledger = json.loads(ledger_raw)
    retained = list(ledger["packages"])
    for item in plan["packages"]:
        old = next((p for p in retained if (p["id"], p["version"]) == (item["id"], item["version"])), None)
        if old:
            require(old["sha256"] == item["sha256"], "Immutable retained artifact mismatch")
        else:
            prior = [repo.version(p["version"]) for p in retained if p["id"] == item["id"]]
            require(not prior or repo.version(item["version"]) > max(prior), "Version progression required")
            retained.append({k: item[k] for k in ("id", "version", "sha256")})
    successor = dict(ledger, packages=retained); config_path = f"config/{profile}.json"
    tree = git_tree({"releases/manifest.json": repo.json_bytes(successor),
                     "config/production.json": safe_read(root / config_path)})
    expected_retention = {"before": ledger, "after": successor, "before_sha256": sha(ledger_raw),
                          "after_sha256": sha(repo.json_bytes(successor)), "successor_path": "publication-data/manifest.json",
                          "config_path": config_path, "config_sha256": sha(safe_read(root / config_path)),
                          "main_parent": payload["expected"]["main_sha"],
                          "main_commit": git_commit(tree, payload["expected"]["main_sha"], "Simulated retention finalization")}
    require(canonical(payload["retention"]) == canonical(expected_retention), "Ledger/config finalization exceeds audited retention scope")


def prepare(stage, output, *, source, lanes, expected, release_tag, qualification=None,
            profile="production", synthetic=False, now=None):
    """Seal a reviewed-input snapshot; no build, network or approval is performed."""
    stage = Path(stage).absolute(); output = Path(output).absolute()
    require(profile in ("production", "candidate") and type(synthetic) is bool, "Invalid preparation profile")
    validate_source(source); validate_expected(expected)
    require(type(lanes) is list and bool(lanes) and len(set(lanes)) == len(lanes)
            and all(l in LANES for l in lanes), "Invalid or unsupported Kodi lane")
    require(type(release_tag) is str and re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,150}", release_tag)
            and ".." not in release_tag, "Unsafe release tag")
    require(not output.exists() and not output.is_relative_to(stage) and not stage.is_relative_to(output), "Snapshot output overlaps or already exists")
    plan, _ = selected_plan(stage, profile)
    package_matches = [p for p in plan["packages"] if p.get("provenance", {}).get("source_commit") == source["commit"]
                       and p.get("provenance", {}).get("source_repository") == "https://github.com/" + source["repository"]]
    require(len(package_matches) == 1, "Exactly one source-bound add-on release is supported per proposal")
    package = package_matches[0]
    require(sorted(package["lanes"]) == sorted(lanes), "Package lane scope mismatch")
    require(not synthetic or source["repository"].startswith("simulation/"), "Real source cannot be labelled a synthetic fixture")
    output.mkdir(parents=True); snapshot = output / "snapshot"; snapshot.mkdir()
    selected = []
    for name in ("config", "incoming", "releases", "packages", f"dist/{profile}", "evidence", "LICENSE"):
        path = stage / name
        if not path.exists():
            continue
        require(not path.is_symlink(), "Linked source root")
        if path.is_dir():
            selected.extend(name + "/" + n for n in inventory(path))
        else:
            selected.append(name)
    total = 0
    for name in sorted(selected):
        safe_name(name); raw = safe_read(stage / name); total += len(raw)
        require(total <= MAX_BYTES and len(selected) <= MAX_FILES, "Snapshot resource limit")
        write_new(snapshot / name, raw)
    site_prefix = f"dist/{profile}/site"
    site = {n: safe_read(snapshot / site_prefix / n) for n in plan["site_files"]}
    require(all(name in site and sha(site[name]) == digest for name, digest in expected["site_files"].items()
                if name.endswith((".zip", ".zip.sha256"))), "Historical immutable public artifact changed or removed")
    ledger_path = "releases/candidate-manifest.json" if profile == "candidate" and (snapshot / "config/candidate-repository.json").exists() else "releases/manifest.json"
    ledger_raw = safe_read(snapshot / ledger_path); ledger = json.loads(ledger_raw)
    require(sha(ledger_raw) == expected["ledger_sha256"], "Expected retention ledger mismatch")
    retained = list(ledger["packages"])
    for item in plan["packages"]:
        old = next((p for p in retained if (p["id"], p["version"]) == (item["id"], item["version"])), None)
        if old:
            require(old["sha256"] == item["sha256"], "Immutable retained package changed")
        else:
            previous = [repo.version(p["version"]) for p in retained if p["id"] == item["id"]]
            require(not previous or repo.version(item["version"]) > max(previous), "Version progression required")
            retained.append({k: item[k] for k in ("id", "version", "sha256")})
    successor = dict(ledger, packages=retained)
    successor_path = "publication-data/manifest.json"
    write_new(snapshot / successor_path, repo.json_bytes(successor))
    asset_names = [Path(package["path"]).name, Path(package["path"]).name + ".sha256"]
    assets = {}
    for name in asset_names:
        path = f"dist/{profile}/release-assets/{name}"; raw = safe_read(snapshot / path)
        assets[name] = {"path": path, "sha256": sha(raw), "size": len(raw)}
    sums = "".join(f'{assets[n]["sha256"]}  {n}\n' for n in sorted(assets)).encode()
    write_new(snapshot / "publication-data/SHA256SUMS", sums)
    assets["SHA256SUMS"] = {"path": "publication-data/SHA256SUMS", "sha256": sha(sums), "size": len(sums)}
    tree = git_tree(site)
    config_path = f"config/{profile}.json"
    main_tree = git_tree({"releases/manifest.json": repo.json_bytes(successor),
                          "config/production.json": safe_read(snapshot / config_path)})
    payload = {"schema": 1, "mode": "local-simulation", "profile": profile, "synthetic": synthetic,
               "publication_authorized": False, "source": source, "lanes": lanes,
               "destination": dict(SIM_DESTINATION), "expected": expected,
               "created_at": utc(now), "toolchain": toolchain(), "files": inventory(snapshot),
               "packages": plan["packages"], "catalogs": plan["catalogs"],
               "plan_sha256": sha(safe_read(snapshot / f"dist/{profile}/release-plan.json")),
               "qualification": {} if qualification is None else qualification,
               "release": {"tag": release_tag, "commit": expected["main_sha"],
                           "name": package["id"] + " " + package["version"],
                           "notes": "Local simulated publication; no production authorization.", "assets": assets},
               "pages": {"parent": expected["pages_sha"], "tree": tree,
                         "commit": git_commit(tree, expected["pages_sha"], "Simulated reviewed Pages publication"),
                         "site_prefix": site_prefix, "site_files": plan["site_files"],
                         "changes": [{"path": n, "before": expected["site_files"].get(n), "after": sha(raw)}
                                     for n, raw in sorted(site.items()) if expected["site_files"].get(n) != sha(raw)]},
               "retention": {"before": ledger, "after": successor, "before_sha256": sha(ledger_raw),
                             "after_sha256": sha(repo.json_bytes(successor)), "successor_path": successor_path,
                             "config_path": config_path, "config_sha256": sha(safe_read(snapshot / config_path)),
                             "main_parent": expected["main_sha"],
                             "main_commit": git_commit(main_tree, expected["main_sha"], "Simulated retention finalization")}}
    write_new(output / "payload.json", canonical(payload))
    verify_payload(output)
    return payload


def verify_payload(path, observation=False):
    path = Path(path).absolute(); root = path / "snapshot"
    require(type(observation) is bool, "Invalid observation mode")
    payload = strict_load(safe_read(path / "payload.json", MAX_JSON))
    closed(payload, {"schema", "mode", "profile", "synthetic", "publication_authorized", "source", "lanes", "destination", "expected",
                     "created_at", "toolchain", "files", "packages", "catalogs", "plan_sha256", "qualification", "release", "pages", "retention"})
    require(payload["schema"] == 1 and type(payload["schema"]) is int and payload["mode"] == "local-simulation"
            and payload["publication_authorized"] is False and type(payload["synthetic"]) is bool, "Production capability is unavailable")
    require(payload["profile"] in ("candidate", "production"), "Invalid frozen profile")
    timestamp(payload["created_at"])
    destination(payload["destination"]); validate_source(payload["source"]); validate_expected(payload["expected"])
    require(payload["toolchain"] == toolchain(), "Trusted publication toolchain changed")
    require(canonical(payload["files"]) == canonical(inventory(root)), "Frozen snapshot inventory changed")
    require(type(payload["lanes"]) is list and payload["lanes"] and len(set(payload["lanes"])) == len(payload["lanes"])
            and all(l in LANES for l in payload["lanes"]), "Invalid frozen lanes")
    closed(payload["release"], {"tag", "commit", "name", "notes", "assets"})
    closed(payload["pages"], {"parent", "tree", "commit", "site_prefix", "site_files", "changes"})
    closed(payload["retention"], {"before", "after", "before_sha256", "after_sha256", "successor_path", "config_path", "config_sha256", "main_parent", "main_commit"})
    require(payload["release"]["commit"] == payload["expected"]["main_sha"]
            and payload["pages"]["parent"] == payload["expected"]["pages_sha"]
            and payload["retention"]["main_parent"] == payload["expected"]["main_sha"], "Proposal head scope mismatch")
    for name, asset in payload["release"]["assets"].items():
        safe_name(name); require("/" not in name, "Unsafe asset name")
        closed(asset, {"path", "sha256", "size"}); safe_name(asset["path"])
        raw = safe_read(root / asset["path"])
        require(asset["sha256"] == sha(raw) and type(asset["size"]) is int and asset["size"] == len(raw), "Release asset changed")
    pages = payload["pages"]; require(pages["site_prefix"] == f'dist/{payload["profile"]}/site', "Site root mismatch")
    files = {n: safe_read(root / pages["site_prefix"] / safe_name(n)) for n in pages["site_files"]}
    require({n: sha(b) for n, b in files.items()} == pages["site_files"] and git_tree(files) == pages["tree"]
            and git_commit(pages["tree"], pages["parent"], "Simulated reviewed Pages publication") == pages["commit"], "Pages commit identity mismatch")
    expected_changes = [{"path": n, "before": payload["expected"]["site_files"].get(n), "after": sha(raw)}
                        for n, raw in sorted(files.items()) if payload["expected"]["site_files"].get(n) != sha(raw)]
    require(pages["changes"] == expected_changes and set(payload["expected"]["site_files"]) <= set(files), "Deletion or altered Pages delta")
    require(all(sha(files[name]) == digest for name, digest in payload["expected"]["site_files"].items()
                if name.endswith((".zip", ".zip.sha256"))), "Historical immutable public file changed")
    retention = payload["retention"]
    require(retention["after"]["packages"][:len(retention["before"]["packages"])] == retention["before"]["packages"], "Historical ledger reordered or removed")
    require(retention["before_sha256"] == payload["expected"]["ledger_sha256"]
            and sha(safe_read(root / retention["successor_path"])) == retention["after_sha256"]
            and safe_read(root / retention["successor_path"]) == repo.json_bytes(retention["after"])
            and sha(safe_read(root / retention["config_path"])) == retention["config_sha256"], "Retention successor changed")
    semantic_bindings(root, payload)
    blockers = derive(root, payload, observation=observation)
    return {"payload": payload, "root": root, "payload_sha256": sha(canonical(payload)),
            "eligibility_blockers": blockers,
            "production_blockers": ["D1/D2 local simulation has no production authority", *blockers],
            "simulation_eligible": not observation and payload["synthetic"] and not blockers}


def seal_review(path, report, reviewer="simulated-reviewer", now=None):
    verified = verify_payload(path)
    require(type(report) is bytes and 0 < len(report) <= 2_000_000 and type(reviewer) is str and reviewer.strip(), "Independent review report required")
    require(reviewer not in ("manager", "kodi-repo-manager"), "Manager cannot independently review its own payload")
    value = {"schema": 1, "mode": "local-simulation", "payload_sha256": verified["payload_sha256"],
             "reviewer": reviewer, "role": "kodi-release-reviewer", "created_at": utc(now),
             "report_path": "review-report.txt", "report_sha256": sha(report),
             "scope": "Local simulated independent review only; not authenticated human approval",
             "publication_authorized": False}
    write_new(Path(path) / "review-report.txt", report)
    write_new(Path(path) / "review.json", canonical(value))
    return value


def audience_check(value):
    closed(value, {"installation_uuid", "epoch", "app_id", "app_installation_id", "key_policy_sha256"})
    require(type(value["installation_uuid"]) is str and HEX32.fullmatch(value["installation_uuid"])
            and type(value["epoch"]) is int and value["epoch"] > 0 and value["app_id"] == 2
            and value["app_installation_id"] == 3 and type(value["app_id"]) is int
            and type(value["app_installation_id"]) is int and type(value["key_policy_sha256"]) is str
            and HEX64.fullmatch(value["key_policy_sha256"]), "Invalid simulated installation audience")


def seal_execution(path, *, audience, nonce=None, lifetime=3600, now=None, recovery=None):
    verified = verify_payload(path); audience_check(audience)
    review = strict_load(safe_read(Path(path) / "review.json", MAX_JSON))
    moment = timestamp(now)
    require(type(lifetime) is int and 0 < lifetime <= 86400, "Invalid proposal lifetime")
    completed = []
    if recovery is not None:
        closed(recovery, {"transaction", "remote_state_sha256", "completed"})
        require(all(type(recovery[k]) is str and HEX64.fullmatch(recovery[k]) for k in ("transaction", "remote_state_sha256")), "Invalid recovery identity")
        completed = recovery["completed"]
        require(type(completed) is list and completed == KINDS[:len(completed)] and len(completed) <= len(KINDS), "Invalid recovery prefix")
    value = {"schema": 1, "mode": "local-simulation", "payload_sha256": verified["payload_sha256"],
             "review_sha256": sha(canonical(review)), "destination": dict(SIM_DESTINATION),
             "expected": verified["payload"]["expected"], "nonce": uuid.uuid4().hex if nonce is None else nonce,
             "created_at": utc(moment), "expires_at": utc(moment + timedelta(seconds=lifetime)),
             "audience": audience, "operations": [{"kind": k} for k in KINDS[len(completed):]],
             "recovery": recovery, "publication_authorized": False}
    require(type(value["nonce"]) is str and HEX32.fullmatch(value["nonce"]), "Malformed nonce")
    write_new(Path(path) / "execution.json", canonical(value))
    return {"execution": value, "digest": sha(canonical(value))}


def load_bundle(path, expected_digest=None, now=None, observation=False):
    result = verify_payload(path, observation=observation); path = Path(path)
    allowed = {"snapshot", "payload.json", "review.json", "review-report.txt", "execution.json"}
    require({p.name for p in path.iterdir()} <= allowed, "Unexpected bundle control file")
    review = strict_load(safe_read(path / "review.json", MAX_JSON))
    closed(review, {"schema", "mode", "payload_sha256", "reviewer", "role", "created_at", "report_path", "report_sha256", "scope", "publication_authorized"})
    require(review["schema"] == 1 and type(review["schema"]) is int and review["mode"] == "local-simulation"
            and review["publication_authorized"] is False and review["role"] == "kodi-release-reviewer"
            and type(review["reviewer"]) is str and review["reviewer"].strip()
            and review["reviewer"] not in ("manager", "kodi-repo-manager")
            and review["payload_sha256"] == result["payload_sha256"] and review["report_path"] == "review-report.txt"
            and review["scope"] == "Local simulated independent review only; not authenticated human approval"
            and sha(safe_read(path / "review-report.txt")) == review["report_sha256"], "Independent frozen review mismatch")
    execution = strict_load(safe_read(path / "execution.json", MAX_JSON))
    closed(execution, {"schema", "mode", "payload_sha256", "review_sha256", "destination", "expected", "nonce", "created_at", "expires_at", "audience", "operations", "recovery", "publication_authorized"})
    require(execution["schema"] == 1 and type(execution["schema"]) is int and execution["mode"] == "local-simulation"
            and execution["publication_authorized"] is False, "Production authorization is unavailable")
    destination(execution["destination"]); audience_check(execution["audience"])
    require(execution["payload_sha256"] == result["payload_sha256"] and execution["review_sha256"] == sha(canonical(review))
            and execution["expected"] == result["payload"]["expected"] and execution["destination"] == result["payload"]["destination"], "Execution proposal exceeds independently reviewed scope")
    require(type(execution["nonce"]) is str and HEX32.fullmatch(execution["nonce"]), "Malformed nonce")
    current = timestamp(now); created = timestamp(execution["created_at"]); expires = timestamp(execution["expires_at"])
    require(type(observation) is bool, "Invalid observation mode")
    require(timestamp(result["payload"]["created_at"]) <= timestamp(review["created_at"]) <= created < expires
            and expires - created <= timedelta(hours=24), "Invalid publication chronology")
    require(observation or created <= current < expires, "Expired, future or stale publication proposal")
    completed = []
    if execution["recovery"] is not None:
        recovery = execution["recovery"]; closed(recovery, {"transaction", "remote_state_sha256", "completed"})
        require(all(type(recovery[k]) is str and HEX64.fullmatch(recovery[k]) for k in ("transaction", "remote_state_sha256")), "Invalid recovery identity")
        completed = recovery["completed"]
        require(type(completed) is list and completed == KINDS[:len(completed)] and len(completed) <= len(KINDS), "Recovery changes approved operation order")
    require(execution["operations"] == [{"kind": k} for k in KINDS[len(completed):]], "Unauthorized publication operations")
    digest = sha(canonical(execution))
    require(expected_digest is None or expected_digest == digest, "Proposal digest mismatch")
    return dict(result, review=review, execution=execution, digest=digest)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("inspect", "verify"))
    parser.add_argument("bundle", type=Path)
    parser.add_argument("--digest")
    args = parser.parse_args()
    result = verify_payload(args.bundle) if args.action == "inspect" else load_bundle(args.bundle, args.digest)
    print(json.dumps({k: v for k, v in result.items() if k not in ("root", "payload", "review", "execution")}, sort_keys=True))


if __name__ == "__main__":
    require(__debug__, "Run without -O")
    main()

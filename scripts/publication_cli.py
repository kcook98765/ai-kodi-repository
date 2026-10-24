#!/usr/bin/env python3
"""Task-bound publisher bridge. No caller paths, credentials or approval issuer.

An absent opt-in configuration blocks before credential or network access. The
current OpenCode installation is not activated by adding this source file.
"""
from __future__ import annotations

from datetime import datetime, timezone
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import publication_proposal as frozen
import lifecycle as lc

ROOT = Path(__file__).resolve().parents[1]
PROFILE = "d3-pr-pilot-v1"
OPERATIONS = {"request", "status", "execute", "reconcile"}


def public_config(root=ROOT):
    """Read only the fixed operator-controlled project opt-in, never ambient env."""
    path = Path(root) / ".opencode/publication-pilot.json"
    frozen.require(path.exists(), "Disposable publisher configuration is not installed")
    data = frozen.strict_load(frozen.safe_read(path, frozen.MAX_JSON))
    lc.closed(data, {"schema", "profile", "project_root", "installation_uuid", "epoch", "enrollment", "remote_enabled"},
              {"private_config_file", "private_config_sha256"})
    frozen.require(type(data["schema"]) is int and data["schema"] == 1 and data["profile"] == PROFILE and
                   data["project_root"] == str(Path(root).resolve()) and type(data["remote_enabled"]) is bool,
                   "Pilot configuration identity mismatch")
    frozen.require(type(data["installation_uuid"]) is str and frozen.HEX32.fullmatch(data["installation_uuid"]) and
                   type(data["epoch"]) is int and data["epoch"] > 0, "Pilot installation/epoch missing")
    import publication_pilot_contract as contract
    contract.validate_enrollment(data["enrollment"])
    return data


def _private_config(root, config):
    """Explicit owner-installed file only; no CLI, token env, gh or SSH fallback."""
    frozen.require(type(config.get("private_config_file")) is str and type(config.get("private_config_sha256")) is str and
                   frozen.HEX64.fullmatch(config["private_config_sha256"]), "Private publisher locator is not installed")
    private = Path(config["private_config_file"])
    frozen.require(".." not in private.parts, "Private locator traversal rejected")
    frozen.require(private == private.resolve(strict=True), "Private locator aliases rejected")
    frozen.require(private.is_absolute() and not private.is_relative_to(Path(root).resolve()),
                   "Private publisher configuration must be outside the project")
    raw = frozen.safe_read(private, frozen.MAX_JSON)
    metadata = private.lstat()
    frozen.require(stat.S_ISREG(metadata.st_mode) and metadata.st_nlink == 1 and metadata.st_uid == os.getuid() and
                   stat.S_IMODE(metadata.st_mode) == 0o600 and frozen.sha(raw) == config["private_config_sha256"],
                   "Private publisher configuration mode/owner/digest mismatch")
    value = frozen.strict_load(raw)
    frozen.closed(value, {"schema", "profile", "installation_uuid", "epoch", "key_file", "staging_authorizations"})
    frozen.require(type(value["schema"]) is int and value["schema"] == 1 and value["profile"] == PROFILE and
                   value["installation_uuid"] == config["installation_uuid"] and value["epoch"] == config["epoch"] and
                   type(value["staging_authorizations"]) is dict, "Private pilot identity/authority mismatch")
    key = Path(value["key_file"]) if type(value["key_file"]) is str else Path(root)
    frozen.require(".." not in key.parts, "Credential locator traversal rejected")
    frozen.require(key == key.resolve(), "Credential locator aliases rejected")
    frozen.require(key.is_absolute() and not key.is_relative_to(Path(root).resolve()), "Credential path is not private")
    return value, config["private_config_sha256"]



def validate_staging_authority(data, authorization, *, root=ROOT, now=None, observation=False):
    """Re-read the private owner exact-task metadata grant before every effect."""
    import publication_pilot_contract as contract
    config = public_config(root)
    private, private_sha = _private_config(root, config)
    p = data["payload"]; e = data["enrollment"]; task = p["task"]
    frozen.require(config["remote_enabled"] is True and
                   config["installation_uuid"] == task["installation_uuid"] and config["epoch"] == task["epoch"] and
                   frozen.canonical(config["enrollment"]) == frozen.canonical(e), "Stale staging enrollment")
    record = private["staging_authorizations"].get(task["id"])
    frozen.closed(record, {"task_sha256", "source_commit", "destination_sha256", "installation_uuid", "epoch",
                           "expires_at", "metadata_only", "operations"})
    effects = {"create_blob", "create_tree", "create_commit", "create_ledger_branch", "create_ledger_pr", "update_request_pr"}
    frozen.require(record["task_sha256"] == task["sha256"] and record["source_commit"] == p["source"]["commit"] and
                   record["destination_sha256"] == frozen.sha(frozen.canonical(contract.transport_enrollment(e))) and
                   record["installation_uuid"] == task["installation_uuid"] and type(record["epoch"]) is int and
                   record["epoch"] == task["epoch"] and record["metadata_only"] is True and
                   type(record["operations"]) is list and set(record["operations"]) == effects and len(record["operations"]) == len(effects),
                   "Exact-task metadata authority missing or changed")
    current = now or datetime.now(timezone.utc)
    frozen.require((observation or frozen.timestamp(record["expires_at"]) > current) and
                   frozen.timestamp(authorization["expires_at"]) <= frozen.timestamp(record["expires_at"]) and
                   authorization["authorization_sha256"] == private_sha,
                   "Staging authority expired, revoked or replaced")
    return record


def issue_staging_grant(root, config, private, private_sha, binding, out, *, material=None):
    """Narrow a preexisting owner grant; tests cannot issue owner authority."""
    import publication_pilot_contract as contract
    path = Path(out) / "publication-pilot/material" if material is None else Path(material)
    frozen.require(path.is_relative_to(Path(out) / "publication-pilot"), "Staging material outside task")
    data = contract.load_material(path)
    record = private["staging_authorizations"].get(binding["task_id"])
    frozen.require(type(record) is dict, "Owner metadata staging authorization is missing")
    authorization = {"kind": "owner-staging-authorization", "actor_id": 56806582,
        "payload_sha256": data["payload_sha256"], "review_sha256": data["review_sha256"],
        "task": data["payload"]["task"], "destination_sha256": frozen.sha(frozen.canonical(contract.transport_enrollment(data["enrollment"]))),
        "branch": contract.ledger_branch(data), "expires_at": record["expires_at"],
        "metadata_only": True, "authorization_sha256": private_sha}
    validate_staging_authority(data, authorization, root=root)
    if not (path / "preparation.json").exists():
        contract.preparation_grant(path, authorization=authorization)
    return path

def _request(value, role):
    frozen.require(role == "kodi-repo-manager", "Only the repository manager may use the pilot helper")
    lc.closed(value, {"operation", "task_id", "expected_digest"}, {"proposal_sha256"})
    frozen.require(value["operation"] in OPERATIONS and type(value["task_id"]) is str and
                   frozen.HEX32.fullmatch(value["task_id"]) and type(value["expected_digest"]) is str and
                   frozen.HEX64.fullmatch(value["expected_digest"]), "Malformed task-bound publication request")
    proposal = value.get("proposal_sha256")
    frozen.require(proposal is None or type(proposal) is str and frozen.HEX64.fullmatch(proposal), "Malformed execution digest")
    frozen.require(value["operation"] not in {"execute", "reconcile"} or proposal is not None,
                   "Exact execution digest required")
    frozen.require(value["operation"] != "request" or proposal is None, "Request cannot select an execution")
    return dict(value)


def dispatch(request, *, role, root=ROOT, factory=None):
    """Closed role protocol; factory injection exists only inside Python tests."""
    request = _request(request, role)
    config = public_config(root)
    frozen.require(config["remote_enabled"] is True, "Disposable network activation is disabled")
    store = lc.Store(Path(root))
    with store.bound(request["task_id"], request["expected_digest"]) as (binding, state, out):
        frozen.require(binding["source"]["repository"] == config["enrollment"]["repository"] and
                       binding["source"]["repository_id"] == config["enrollment"]["repository_id"],
                       "Task source is outside the disposable enrollment")
        # The implementation factory is fixed; no endpoint/backend selector is
        # accepted by the JSON protocol. Only an explicit private config can
        # construct real token/HTTP objects.
        operator = (factory or operator_factory)(Path(root), config, binding, out)
        return dispatch_operator(operator, request, out)


def operator_factory(root, config, binding, out):
    # Filled by the reviewed typed transport/coordinator integration below.
    private, private_sha = _private_config(root, config)
    return configured_operator(root, config, private, private_sha, binding, out)


def dispatch_operator(operator, request, out):
    """Resolve only fixed task materials; JSON inputs never choose a path."""
    import publication_pilot_contract as contract
    base = Path(out) / "publication-pilot"
    material = base / "material"
    operation = request["operation"]
    context = getattr(operator, "_pilot_context", None)
    if operation == "status":
        result = operator.status()
        if material.exists():
            data = contract.load_material(material, now=operator.now(), observation=True)
            frozen.require(data["payload"]["task"]["id"] == request["task_id"] and
                           data["payload"]["task"]["sha256"] == request["expected_digest"], "Material task binding changed")
            result["material"] = {"payload_sha256": data["payload_sha256"],
                                  "proposal_sha256": data["digest"] if data["execution"] is not None else None}
        elif context is not None:
            # Initial inspection is read-only remotely. It freezes complete bytes
            # locally; later preparation must reject stale or changed baselines.
            import base64
            inputs = base / "inputs.json"
            if not inputs.exists():
                transport = operator.transport
                observed = transport.inspect()
                policy = transport.inspect_policy()
                frozen.require(policy["policy_sha256"] == operator.enrollment["policy_sha256"], "Observed pilot policy changed")
                def files_at(commit):
                    meta = transport.read_commit(commit)
                    tree = transport.read_tree(meta["tree"]["sha"])
                    files = {}
                    for item in tree["tree"]:
                        if item["type"] == "tree": continue
                        frozen.require(item["type"] == "blob" and item["mode"] == "100644", "Unsupported baseline file mode")
                        __import__("publication_d3_contract").git_path(item["path"])
                        files[item["path"]] = transport.read_blob(item["sha"])
                    return meta["tree"]["sha"], files
                main_tree, main_files = files_at(observed["main_sha"])
                pages_tree, site_files = files_at(observed["pages_sha"])
                frozen.require("releases/manifest.json" in main_files, "Published ledger baseline missing")
                import repository as repo
                import publication_d3_contract as ledger_contract
                ledger = ledger_contract._ledger(json.loads(main_files["releases/manifest.json"]))
                frozen.require(repo.json_bytes(ledger) == main_files["releases/manifest.json"], "Noncanonical or malformed published ledger")
                source_commit = context["binding"]["source"]["commit"]
                frozen.require(source_commit in operator.enrollment["fixture_source"]["commits"].values(), "Unenrolled immutable source commit")
                _, source_files = files_at(source_commit)
                version = next(v for v, commit in operator.enrollment["fixture_source"]["commits"].items() if commit == source_commit)
                frozen.require({n.removeprefix("fixtures/addon/"): frozen.sha(raw) for n, raw in source_files.items()} ==
                               operator.enrollment["fixture_source"]["files"][version], "Remote inert source bytes changed")
                transport.inspect(expected_heads={"main_sha": observed["main_sha"], "pages_sha": observed["pages_sha"]})
                frozen.require(transport.inspect_policy()["policy_sha256"] == operator.enrollment["policy_sha256"], "Policy changed during baseline capture")
                task = {"id": request["task_id"], "sha256": request["expected_digest"],
                        "installation_uuid": operator.enrollment["installation_uuid"], "epoch": operator.enrollment["epoch"]}
                value = {"schema": 1, "profile": PROFILE, "task": task,
                         "enrollment_sha256": frozen.sha(frozen.canonical(operator.enrollment)),
                         "observed_at": frozen.utc(operator.now()), "source_commit": source_commit,
                         "expected": {"main_sha": observed["main_sha"], "main_tree": main_tree,
                             "pages_sha": observed["pages_sha"], "pages_tree": pages_tree,
                             "ledger_sha256": frozen.sha(main_files["releases/manifest.json"]),
                             "site_files": {n: frozen.sha(raw) for n, raw in site_files.items()}},
                         "published_ledger": ledger,
                         "main_files": {n: base64.b64encode(raw).decode("ascii") for n, raw in main_files.items()}}
                frozen.write_new(inputs, frozen.canonical(value))
            value = frozen.strict_load(frozen.safe_read(inputs, frozen.MAX_JSON))
            frozen.require(value["task"]["id"] == request["task_id"] and value["task"]["sha256"] == request["expected_digest"], "Observed input task changed")
            result["inputs_sha256"] = frozen.sha(frozen.canonical(value))
        return result
    proposal = request.get("proposal_sha256")
    if operation in {"execute", "reconcile"}:
        candidates = [material]
        folder = base / "recoveries"
        if folder.exists():
            frozen.require(not folder.is_symlink(), "Linked recovery storage")
            for path in sorted(folder.iterdir()):
                frozen.require(path.is_dir() and not path.is_symlink() and frozen.HEX64.fullmatch(path.name),
                               "Malformed recovery storage")
                candidates.append(path / "material")
        matched = []
        for candidate in candidates:
            if not candidate.exists(): continue
            data = contract.load_material(candidate, now=operator.now(), observation=True)
            frozen.require(data["payload"]["task"]["id"] == request["task_id"] and
                           data["payload"]["task"]["sha256"] == request["expected_digest"], "Material task binding changed")
            if data["digest"] == proposal: matched.append((candidate, data.get("execution") is not None))
        frozen.require(len(matched) == 1, "Missing or ambiguous exact execution material")
        candidate, sealed = matched[0]
        if operation == "execute":
            frozen.require(sealed, "Exact sealed execution required")
            return operator.execute(candidate, proposal)
        if sealed and proposal in operator.status()["transactions"]:
            return operator.reconcile(candidate, proposal)
        return operator.reconcile_request(candidate, proposal)
    frozen.require(operation == "request" and material.is_dir(), "Reviewed pilot material is missing")
    state = operator.status()
    if state["active"] is not None:
        # This explicit request observes first and creates fresh authorization
        # material only for the exact remaining suffix of this task's release.
        active = state["active"]
        frozen.require(type(active) is str and frozen.HEX64.fullmatch(active), "Malformed active execution")
        candidates = [material]
        folder = base / "recoveries"
        if folder.exists():
            frozen.require(not folder.is_symlink(), "Linked recovery storage")
            for entry in sorted(folder.iterdir()):
                frozen.require(entry.is_dir() and not entry.is_symlink() and frozen.HEX64.fullmatch(entry.name),
                               "Malformed recovery storage")
                candidates.append(entry / "material")
        matched = []
        for candidate in candidates:
            if not candidate.exists(): continue
            data = contract.load_material(candidate, now=operator.now(), observation=True)
            frozen.require(data["payload"]["task"]["id"] == request["task_id"] and
                           data["payload"]["task"]["sha256"] == request["expected_digest"], "Recovery task binding changed")
            if data.get("execution") is not None and data["digest"] == active: matched.append((candidate, data))
        frozen.require(len(matched) == 1, "Missing or ambiguous interrupted execution")
        source, old = matched[0]
        observation = operator.reconcile(source, active)
        if observation["status"] == "RECORDED": return observation
        frozen.require(observation["status"] == "RECONCILED_NEEDS_FRESH_OWNER_APPROVAL" and context is not None,
                       "Read-only reconciliation and fresh private metadata authority are required")
        recovery = observation["recovery"]
        target = base / "recoveries" / active / "material"
        if not target.exists():
            for name in frozen.inventory(source):
                if name in {"execution.json", "preparation.json"}: continue
                frozen.write_new(target / name, frozen.safe_read(source / name))
        fresh = contract.load_material(target, now=operator.now(), observation=True)
        frozen.require(fresh["payload_sha256"] == old["payload_sha256"] and fresh["review_sha256"] == old["review_sha256"],
                       "Recovery changes independently reviewed bytes")
        issue_staging_grant(context["root"], context["config"], context["private"], context["private_sha"],
                            context["binding"], Path(out), material=target)
        return operator.request(target, fresh["digest"], recovery=recovery)
    data = contract.load_material(material, now=operator.now())
    frozen.require(data["payload"]["task"]["id"] == request["task_id"] and
                   data["payload"]["task"]["sha256"] == request["expected_digest"], "Material task binding changed")
    if context is not None:
        issue_staging_grant(context["root"], context["config"], context["private"], context["private_sha"],
                            context["binding"], Path(out))
    frozen.require((material / "preparation.json").exists(), "Separate owner metadata authorization is missing")
    state = operator.status()
    frozen.require(state["active"] is None, "Recovery requires separately prepared fresh material and exact owner review")
    return operator.request(material, data["digest"])


def configured_operator(root, config, private, private_sha, binding, out):
    """Construct the explicit enrolled App backend without making a request."""
    import publication_github_live as github
    import publication_pilot as pilot
    import publication_pr_owner as owner
    frozen.require(config["remote_enabled"] is True and config["enrollment"]["identity_evidence"]["kind"] == "github-readback",
                   "Actual pilot readback and explicit activation are required")
    frozen.require(config["enrollment"]["installation_uuid"] == config["installation_uuid"] and
                   config["enrollment"]["epoch"] == config["epoch"], "Publisher installation identity mismatch")
    class PinnedPrivateKey:
        def sign_rs256(self, raw):
            current, checksum = _private_config(root, config)
            frozen.require(checksum == private_sha and current == private, "Private publisher configuration changed")
            key = Path(current["key_file"])
            keybytes = frozen.safe_read(key, 32768)
            metadata = key.lstat()
            frozen.require(stat.S_ISREG(metadata.st_mode) and metadata.st_nlink == 1 and metadata.st_uid == os.getuid() and
                           stat.S_IMODE(metadata.st_mode) == 0o600, "Private App key metadata rejected")
            return github.ExplicitRS256Key(keybytes).sign_rs256(raw)
    backend = github.HTTPSBackend()
    provider = github.AppTokenProvider(config["enrollment"], PinnedPrivateKey(), backend)
    transport = github.PilotGitHub(config["enrollment"], provider, backend)
    verifier = owner.OwnerPRVerifier(config["enrollment"], transport)
    journal = Path(root) / ".opencode/pilot-journal" / config["installation_uuid"] / str(config["epoch"])
    result = pilot.PilotOperator(journal, config["enrollment"], transport, verifier)
    result._pilot_context = {"root": Path(root), "config": config, "private": private,
                             "private_sha": private_sha, "binding": binding}
    return result



def protocol_load(raw):
    """Tool stdin is ordinary JSON; only frozen files require canonical bytes."""
    def unique(items):
        result = {}
        for key, value in items:
            frozen.require(key not in result, "Duplicate protocol key")
            result[key] = value
        return result
    def invalid(_):
        raise ValueError("Numeric protocol constants are forbidden")
    frozen.require(type(raw) is bytes and len(raw) <= 100000, "Oversized protocol request")
    return json.loads(raw.decode("utf-8"), object_pairs_hook=unique, parse_float=invalid, parse_constant=invalid)

def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--role", required=True)
    args = parser.parse_args()
    raw = sys.stdin.buffer.read(100_001)
    frozen.require(len(raw) <= 100_000, "Oversized publisher request")
    value = protocol_load(raw)
    result = dispatch(value, role=args.role)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # No private path, source response, credential value or exception chain.
        print(json.dumps({"status": "BLOCKED", "detail": "Disposable publisher request denied; inspect private operator evidence", "production_authorized": False}))
        sys.exit(1)

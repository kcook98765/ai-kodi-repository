"""Opt-in local pilot role receipts; no credential access or remote mutations."""
from datetime import datetime, timedelta, timezone
import base64
from pathlib import Path

import lifecycle as lc
import publication_proposal as frozen
import publication_pilot_contract as contract

REPORTS = {"kodi-addon-tester": "reports/agents/TESTER.md", "kodi-release-reviewer": "reports/agents/REVIEWER.md"}
TOOLS = {"build": "kodi_build", "qualify": "kodi_qualify", "review": "kodi_review"}


def provenance(context, role, operation):
    lc.closed(context, {"agent", "session_id", "tool"})
    lc.require(context["agent"] == role and context["tool"] == TOOLS[operation] and
               type(context["session_id"]) is str and 0 < len(context["session_id"]) <= 200,
               "Trusted role tool context required")
    return frozen.sha(context["session_id"].encode())[:32]


def task_identity(binding, config):
    return {"id": binding["task_id"], "sha256": frozen.sha(lc.repo.json_bytes(binding)),
            "installation_uuid": config["installation_uuid"], "epoch": config["epoch"]}


def operate(store, binding, state, out, operation, role, context):
    import publication_cli
    import lifecycle_publication
    import publication_pilot_candidate
    lc.require(operation in TOOLS, "Pilot role operation denied")
    expected_role = {"build": "kodi-repo-manager", "qualify": "kodi-addon-tester", "review": "kodi-release-reviewer"}[operation]
    lc.require(role == expected_role, "Pilot independent role denied")
    session = provenance(context, role, operation)
    config = publication_cli.public_config(store.root)
    e = config["enrollment"]; task = task_identity(binding, config)
    lc.require(binding["source"]["repository"] == e["repository"] and binding["source"]["repository_id"] == e["repository_id"],
               "Task is outside enrolled disposable destination")
    target = out / "publication-pilot/material"
    if operation == "build" and not target.exists():
        raw = frozen.safe_read(out / "publication-pilot/inputs.json", frozen.MAX_JSON)
        inputs = frozen.strict_load(raw)
        lc.closed(inputs, {"schema", "profile", "task", "enrollment_sha256", "observed_at", "expected", "published_ledger", "main_files", "source_commit"})
        lc.require(type(inputs["schema"]) is int and inputs["schema"] == 1 and inputs["profile"] == contract.PROFILE and
                   inputs["task"] == task and inputs["enrollment_sha256"] == frozen.sha(frozen.canonical(e)) and
                   inputs["source_commit"] == binding["source"]["commit"], "Observed pilot baseline binding mismatch")
        age = datetime.now(timezone.utc) - frozen.timestamp(inputs["observed_at"])
        lc.require(timedelta(0) <= age < timedelta(hours=1), "Pilot baseline is stale")
        main = {}
        for name, value in inputs["main_files"].items():
            contract.d3.git_path(name); lc.require(type(value) is str, "Invalid main baseline bytes")
            main[name] = base64.b64decode(value, validate=True)
        # Reuse the frozen source/package/feed path; its old mock heads do not
        # become remote evidence. The new P uses the observed baseline above.
        lifecycle_publication.operate(store, binding, state, out, "build", role)
        previous = retained_material(store.root, config, inputs["published_ledger"])
        candidate = publication_pilot_candidate.prepare_candidate(out / "publication", out / "publication-pilot/candidate",
            enrollment=e, previous=previous)
        contract.prepare_material(candidate, target, enrollment=e, task=task, session=session,
            published_ledger=inputs["published_ledger"], expected=inputs["expected"], main_files=main)
    data = contract.load_material(target)
    lc.require(data["payload"]["task"] == task and data["enrollment"] == e and
               data["payload"]["source"]["commit"] == binding["source"]["commit"], "Pilot material/task mismatch")
    if operation != "build":
        lc.require((store.root / REPORTS[role]).is_file(), "Independent report must bind task and exact P with qualification disposition")
        report = frozen.safe_read(store.root / REPORTS[role], 100000).decode("utf-8")
        marker = "D3-PILOT-QUALIFIED " + data["payload_sha256"]
        lc.require(marker in report and task["id"] in report, "Independent report must bind task and exact P with qualification disposition")
        record = {"schema": 1, "kind": "opencode-role-receipt-v1", "role": role, "tool": TOOLS[operation],
                  "task": task, "session": session, "payload_sha256": data["payload_sha256"],
                  "toolchain_sha256": frozen.sha(frozen.canonical(data["payload"]["toolchain"])),
                  "result": "QUALIFIED_FOR_TRANSPORT", "report": report, "recorded_at": frozen.utc(None)}
        contract._record(record, data, role)
        receipt = out / "publication-pilot/receipts" / (role + ".json")
        frozen.write_new(receipt, frozen.canonical(record))
    elif data.get("review") is None:
        receipts = out / "publication-pilot/receipts"
        files = [receipts / (r + ".json") for r in REPORTS]
        if all(p.exists() for p in files):
            contract.seal_review(target, tester_record=frozen.strict_load(frozen.safe_read(files[0])),
                                 reviewer_record=frozen.strict_load(frozen.safe_read(files[1])))
            data = contract.load_material(target)
    return {"status": "REVIEWED" if data.get("review") else "AWAITING_INDEPENDENT_REVIEW", "profile": contract.PROFILE,
            "task_id": task["id"], "payload_sha256": data["payload_sha256"], "role": role,
            "scope": contract.scope_projection(data), "publication_authorized": False, "remote_actions_executed": [],
            "independent_review_recorded": data.get("review") is not None}


def retained_material(root, config, published):
    """Only the fixed installation journal can select historical local evidence."""
    if not published["packages"]: return None
    import publication_pilot
    journal_root = Path(root) / ".opencode/pilot-journal" / config["installation_uuid"] / str(config["epoch"])
    lc.require((journal_root / "state.json").is_file(), "Missing historical publication journal")
    journal = publication_pilot.PilotJournal(journal_root, {"installation_uuid": config["installation_uuid"], "epoch": config["epoch"],
        "enrollment_sha256": frozen.sha(frozen.canonical(config["enrollment"]))})
    state = journal.load()
    matches = []
    for execution_sha, tx in state["transactions"].items():
        if tx["status"] != "RECORDED": continue
        task_id = tx.get("task_id")
        lc.require(type(task_id) is str and frozen.HEX32.fullmatch(task_id), "Historical task identity missing")
        base = Path(root) / ".opencode/lifecycle-data" / task_id / "publication-pilot"
        path = Path(tx.get("material_path", ""))
        initial = base / "material"
        recovery = path.parent
        allowed_recovery = (recovery.parent == base / "recoveries" and
                            frozen.HEX64.fullmatch(recovery.name) is not None and path.name == "material")
        lc.require(path == initial or allowed_recovery, "Historical material locator outside fixed task storage")
        prior = contract.load_material(path, expected_digest=execution_sha, observation=True)
        lc.require(prior["payload"]["task"]["id"] == task_id, "Historical material task identity changed")
        if prior["enrollment"] == config["enrollment"] and prior["payload"]["retention"]["after"] == published:
            matches.append(path)
    lc.require(len(matches) == 1, "Missing or ambiguous finalized historical pilot evidence")
    return matches[0]

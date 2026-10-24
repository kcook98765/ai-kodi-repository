"""Frozen, opt-in d3-pr-pilot-v1 materials. This module performs no remote IO.

The older mock-only D3 profile is not converted into a live authorization. Fresh
candidate provenance, independent records, enrollment and a staged PR are required.
"""
from __future__ import annotations

import copy
from datetime import timedelta
from pathlib import Path
import re
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parent))
import publication_proposal as base
import publication_d3_contract as d3
import repository as repo

PROFILE = "d3-pr-pilot-v1"
ROOT = Path(__file__).resolve().parents[1]
ENROLL_FIELDS = {"schema", "profile", "repository", "repository_id", "owner_id", "owner_type", "human_owner_id",
                 "base_url", "branch", "path", "app_id", "app_installation_id", "bot_user_id", "bot_login",
                 "campaign_id", "installation_uuid", "epoch", "fixture_source", "evidence_expires_at",
                 "policy_sha256", "ci_app_id", "identity_evidence", "pages_workflow_id", "validation_workflow_id",
                 "validation_workflow_path", "validation_workflow_commit", "validation_workflow_sha256", "validation_job_name", "pages_environment_id"}


def same(a, b):
    return base.canonical(a) == base.canonical(b)


def validate_enrollment(value):
    base.closed(value, ENROLL_FIELDS)
    base.require(type(value["schema"]) is int and value["schema"] == 1 and value["profile"] == PROFILE,
                 "Wrong pilot enrollment version")
    base.require(value["repository"] == d3.QUAL_REPOSITORY and value["base_url"] == d3.QUAL_BASE
                 and value["owner_type"] == "Organization" and value["branch"] == "gh-pages" and value["path"] == "/",
                 "Production, same-origin or unenrolled pilot destination")
    identities = ["repository_id", "owner_id", "human_owner_id", "app_id", "app_installation_id", "bot_user_id", "ci_app_id", "epoch", "pages_workflow_id", "validation_workflow_id", "pages_environment_id"]
    base.require(all(type(value[n]) is int and 0 < value[n] <= 2**53 - 1 for n in identities),
                 "Actual typed numeric pilot identities are required")
    distinct = [value[n] for n in ("repository_id", "owner_id", "human_owner_id", "app_id", "app_installation_id", "bot_user_id")]
    base.require(value["human_owner_id"] == d3.OWNER_ID and len(distinct) == len(set(distinct))
                 and d3.PRODUCTION_ID not in distinct and not any(900001 <= n <= 900009 for n in distinct),
                 "Production, old synthetic or conflated pilot identities")
    base.require(type(value["bot_login"]) is str and re.fullmatch(r"[a-z0-9-]+\[bot\]", value["bot_login"]), "Invalid App bot login")
    base.require(value["validation_workflow_path"] == ".github/workflows/qualification-validation.yml"
                 and value["validation_job_name"] == "qualification-validation", "Unenrolled validation workflow/job")
    for n, rx in (("campaign_id", base.HEX32), ("installation_uuid", base.HEX32), ("policy_sha256", base.HEX64),
                  ("validation_workflow_commit", base.HEX40), ("validation_workflow_sha256", base.HEX64)):
        base.require(type(value[n]) is str and rx.fullmatch(value[n]), "Invalid pilot pin")
    source = value["fixture_source"]; base.closed(source, {"branch", "commits", "files"})
    base.require(source["branch"] == "d3-fixture-source", "Wrong immutable source branch")
    base.closed(source["commits"], {"1.0.0", "1.1.0"}); base.closed(source["files"], {"1.0.0", "1.1.0"})
    for version in ("1.0.0", "1.1.0"):
        base.require(type(source["commits"][version]) is str and base.HEX40.fullmatch(source["commits"][version]), "Missing actual source commit")
        base.require(same(source["files"][version], {n: base.sha(raw) for n, raw in d3.fixture_files(version).items()}),
                     "Pilot source must be the independently pinned inert first-party MIT fixture")
    base.require(source["commits"]["1.0.0"] != source["commits"]["1.1.0"], "Source versions must have distinct immutable commits")
    evidence = value["identity_evidence"]
    base.closed(evidence, {"kind", "observed_at", "repository_sha256", "installation_sha256", "source_sha256", "policy_sha256"})
    base.require(evidence["kind"] in ("github-readback", "local-test-fixture"), "Enrollment requires readback provenance")
    for name in ("repository_sha256", "installation_sha256", "source_sha256", "policy_sha256"):
        base.require(type(evidence[name]) is str and base.HEX64.fullmatch(evidence[name]), "Enrollment observation hash missing")
    base.require(evidence["source_sha256"] == base.sha(base.canonical(source))
                 and evidence["policy_sha256"] == value["policy_sha256"], "Source/policy observation not bound")
    base.require(base.timestamp(evidence["observed_at"]) < base.timestamp(value["evidence_expires_at"]), "Expired enrollment evidence")
    return copy.deepcopy(value)


def transport_enrollment(value):
    value = validate_enrollment(value)
    return {"mode": PROFILE, **{n: value[n] for n in ("repository", "repository_id", "owner_id", "human_owner_id", "app_id", "app_installation_id", "branch", "path")}, "origin": value["base_url"]}


def toolchain():
    names = ("scripts/publication_pilot_contract.py", "scripts/publication_pr_owner.py", "scripts/publication_github_live.py",
             "scripts/publication_pilot.py", "scripts/publication_d3_contract.py", "scripts/publication_cli.py",
             "scripts/lifecycle_pilot.py", "scripts/lifecycle.py", "scripts/lifecycle_adapter.py", "scripts/opencode/kodi.ts",
             "scripts/opencode/pilot-profiles.json", "scripts/publication_pilot_candidate.py")
    return {n: base.sha(base.safe_read(ROOT / n)) for n in names}


def _task(value):
    base.closed(value, {"id", "sha256", "installation_uuid", "epoch"})
    base.require(type(value["id"]) is str and base.HEX32.fullmatch(value["id"])
                 and type(value["sha256"]) is str and base.HEX64.fullmatch(value["sha256"])
                 and type(value["installation_uuid"]) is str and base.HEX32.fullmatch(value["installation_uuid"])
                 and type(value["epoch"]) is int and value["epoch"] > 0, "Invalid task/install provenance")
    return value


def _derived(snapshot, original, enrollment, published, expected, main_files):
    # Reuse the independent candidate/archive/catalog/retention checks. This pure
    # function does not validate or reinterpret any old D3 mock approval record.
    result, sums, ledger_raw, _ = d3._derived(snapshot, original, enrollment, published, expected, main_files)
    config = {"schema": 1, "profile": PROFILE, "campaign_id": enrollment["campaign_id"],
              "published_packages": result["retention"]["after"]["packages"], "production_authorized": False}
    config_raw = base.canonical(config)
    files = dict(main_files, **{"releases/manifest.json": ledger_raw, "config/qualification.json": config_raw})
    tree = d3.tree(files)
    result["retention"].update(config_sha256=base.sha(config_raw), main_tree=tree,
        main_commit=base.git_commit(tree, expected["main_sha"], "Reviewed pilot ledger proposal"))
    result["release"]["notes"] = "First-party inert MIT pilot fixture; native/interpreter/Piers UNVERIFIED; production authority false."
    result["pages"]["commit"] = base.git_commit(result["pages"]["tree"], expected["pages_sha"], "Reviewed pilot Pages publication")
    return result, sums, ledger_raw, config_raw


def prepare_material(candidate_bundle, output, *, enrollment, task, session, published_ledger=None, expected=None, main_files=None, now=None):
    enrollment = validate_enrollment(enrollment); _task(task)
    base.require(task["installation_uuid"] == enrollment["installation_uuid"] and task["epoch"] == enrollment["epoch"], "Stale task enrollment")
    base.require(type(session) is str and base.HEX32.fullmatch(session), "Manager session pin required")
    candidate = base.verify_payload(candidate_bundle); original = candidate["payload"]
    base.require({p.name for p in Path(candidate_bundle).iterdir()} == {"payload.json", "snapshot"}
                 and original["profile"] == "candidate" and original["synthetic"] is False, "Fresh exact candidate P required; old mock controls forbidden")
    base.require(published_ledger is not None and expected is not None and main_files is not None, "Observed complete main/Pages and published ledger baselines required")
    base.closed(expected, {"main_sha", "main_tree", "pages_sha", "pages_tree", "ledger_sha256", "site_files"})
    base.validate_expected({k: v for k, v in expected.items() if k != "main_tree"})
    base.require(d3.tree(main_files) == expected["main_tree"] and main_files.get("releases/manifest.json") == repo.json_bytes(d3._ledger(published_ledger))
                 and expected["ledger_sha256"] == base.sha(repo.json_bytes(published_ledger)), "Complete observed main baseline mismatch")
    base.require(enrollment["validation_workflow_path"] in main_files
                 and base.sha(main_files[enrollment["validation_workflow_path"]]) == enrollment["validation_workflow_sha256"]
                 and main_files.get(".github/CODEOWNERS") == b"* @kcook98765\n", "Validation workflow/owner review not retained in complete baseline")
    output = Path(output).absolute(); base.require(not output.exists() and not output.is_relative_to(Path(candidate_bundle).absolute()), "Output exists or overlaps candidate")
    output.mkdir(parents=True)
    for name in base.inventory(Path(candidate_bundle)):
        base.write_new(output / "candidate" / name, base.safe_read(Path(candidate_bundle) / name))
    snapshot = output / "snapshot"
    for name in base.inventory(candidate["root"]): base.write_new(snapshot / name, base.safe_read(candidate["root"] / name))
    derived, sums, ledger_raw, config_raw = _derived(snapshot, original, enrollment, published_ledger, expected, main_files)
    for name, raw in (("d3-data/SHA256SUMS", sums), ("d3-data/manifest.json", ledger_raw), ("d3-data/qualification.json", config_raw)):
        base.write_new(snapshot / name, raw)
    for raw in main_files.values():
        file = snapshot / "d3-main" / base.sha(raw)
        if not file.exists(): base.write_new(file, raw)
    payload = {"schema": 1, "profile": PROFILE, "kind": "pilot-payload-v1", "production_authorized": False,
               "created_at": base.utc(now), "enrollment": enrollment, "task": task, "manager_session": session, "manager_tool": "kodi_build",
               "candidate_payload_sha256": candidate["payload_sha256"], "toolchain": toolchain(),
               "source": original["source"], "expected": expected, "files": base.inventory(snapshot),
               "packages": original["packages"], "catalogs": original["catalogs"], **derived}
    base.write_new(output / "payload.json", base.canonical(payload))
    return verify_payload(output)


def verify_payload(path):
    path = Path(path).absolute(); p = base.strict_load(base.safe_read(path / "payload.json", base.MAX_JSON))
    base.closed(p, {"schema", "profile", "kind", "production_authorized", "created_at", "enrollment", "task", "manager_session", "manager_tool", "candidate_payload_sha256", "toolchain", "source", "expected", "files", "packages", "catalogs", "release", "pages", "retention", "main_base", "qualification", "candidate_ledger", "candidate_ledger_sha256"})
    base.require(type(p["schema"]) is int and p["schema"] == 1 and p["profile"] == PROFILE and p["kind"] == "pilot-payload-v1" and p["production_authorized"] is False, "Wrong pilot P profile")
    e = validate_enrollment(p["enrollment"]); _task(p["task"])
    base.require(p["task"]["installation_uuid"] == e["installation_uuid"] and p["task"]["epoch"] == e["epoch"]
                 and type(p["manager_session"]) is str and base.HEX32.fullmatch(p["manager_session"])
                 and p["manager_tool"] == "kodi_build", "Stale task/session/tool binding")
    base.require(same(p["toolchain"], toolchain()) and same(p["files"], base.inventory(path / "snapshot")), "Pilot frozen files/toolchain changed")
    candidate = base.verify_payload(path / "candidate")
    base.require({f.name for f in (path / "candidate").iterdir()} == {"snapshot", "payload.json"}
                 and candidate["payload"]["profile"] == "candidate" and candidate["payload"]["synthetic"] is False
                 and candidate["payload_sha256"] == p["candidate_payload_sha256"], "Mock/altered candidate provenance")
    for name in ("source", "packages", "catalogs"): base.require(same(p[name], candidate["payload"][name]), "Pilot candidate identity mismatch")
    for name, info in candidate["payload"]["files"].items(): base.require(same(p["files"].get(name), info), "Changed independently frozen candidate")
    main = p["main_base"]; base.closed(main, {"files", "tree", "commit"}); main_files = {}
    for name, item in main["files"].items():
        d3.git_path(name); base.closed(item, {"path", "sha256"}); base.safe_name(item["path"])
        raw = base.safe_read(path / "snapshot" / item["path"])
        base.require(item["sha256"] == base.sha(raw) and item["path"] == "d3-main/" + base.sha(raw), "Main baseline bytes changed")
        main_files[name] = raw
    base.closed(p["expected"], {"main_sha", "main_tree", "pages_sha", "pages_tree", "ledger_sha256", "site_files"})
    base.validate_expected({k: v for k, v in p["expected"].items() if k != "main_tree"})
    base.require(d3.tree(main_files) == main["tree"] == p["expected"]["main_tree"] and main["commit"] == p["expected"]["main_sha"]
                 and main_files.get("releases/manifest.json") == repo.json_bytes(p["retention"]["before"])
                 and p["expected"]["ledger_sha256"] == base.sha(repo.json_bytes(p["retention"]["before"])), "Observed baseline changed")
    base.require(e["validation_workflow_path"] in main_files and base.sha(main_files[e["validation_workflow_path"]]) == e["validation_workflow_sha256"]
                 and main_files.get(".github/CODEOWNERS") == b"* @kcook98765\n", "Pinned validation workflow/CODEOWNERS changed")
    derived, sums, ledger, config = _derived(path / "snapshot", candidate["payload"], e, p["retention"]["before"], p["expected"], main_files)
    base.require(all(same(p[n], v) for n, v in derived.items()), "Pilot scope exceeds independently derived frozen artifacts")
    for name, raw in (("d3-data/SHA256SUMS", sums), ("d3-data/manifest.json", ledger), ("d3-data/qualification.json", config)):
        base.require(base.safe_read(path / "snapshot" / name) == raw, "Pilot successor bytes changed")
    base.timestamp(p["created_at"])
    return {"payload": p, "payload_sha256": base.sha(base.canonical(p)), "root": path / "snapshot", "material_path": path,
            "enrollment": e, "production_authorized": False, "network_authorized": False}


def _record(value, data, role):
    base.closed(value, {"schema", "kind", "role", "tool", "task", "session", "payload_sha256", "toolchain_sha256", "result", "report", "recorded_at"})
    base.require(type(value["schema"]) is int and value["schema"] == 1 and value["kind"] == "opencode-role-receipt-v1" and value["role"] == role
                 and same(value["task"], data["payload"]["task"]) and value["payload_sha256"] == data["payload_sha256"]
                 and value["toolchain_sha256"] == base.sha(base.canonical(data["payload"]["toolchain"]))
                 and value["tool"] == ("kodi_qualify" if role == "kodi-addon-tester" else "kodi_review")
                 and value["result"] == "QUALIFIED_FOR_TRANSPORT" and type(value["report"]) is str and 0 < len(value["report"]) <= 100000,
                 "Missing exact independent task/P/tool receipt")
    base.require(type(value["session"]) is str and base.HEX32.fullmatch(value["session"])
                 and value["session"] != data["payload"]["manager_session"]
                 and base.timestamp(value["recorded_at"]) >= base.timestamp(data["payload"]["created_at"]), "Independent role/session/time required")
    return value


def seal_review(path, *, tester_record, reviewer_record, now=None):
    data = verify_payload(path); _record(tester_record, data, "kodi-addon-tester"); _record(reviewer_record, data, "kodi-release-reviewer")
    base.require(tester_record["session"] != reviewer_record["session"], "Independent tester and reviewer sessions required")
    review = {"schema": 1, "profile": PROFILE, "kind": "pilot-review-v1", "payload_sha256": data["payload_sha256"],
              "tester": tester_record, "reviewer": reviewer_record, "created_at": base.utc(now), "production_authorized": False}
    base.write_new(Path(path) / "review.json", base.canonical(review)); return review


def _review(path, data):
    r = base.strict_load(base.safe_read(Path(path) / "review.json", base.MAX_JSON))
    base.closed(r, {"schema", "profile", "kind", "payload_sha256", "tester", "reviewer", "created_at", "production_authorized"})
    base.require(type(r["schema"]) is int and r["schema"] == 1 and r["profile"] == PROFILE and r["kind"] == "pilot-review-v1"
                 and r["production_authorized"] is False and r["payload_sha256"] == data["payload_sha256"], "Wrong frozen pilot review")
    _record(r["tester"], data, "kodi-addon-tester"); _record(r["reviewer"], data, "kodi-release-reviewer")
    base.require(r["tester"]["session"] != r["reviewer"]["session"] and max(base.timestamp(r[n]["recorded_at"]) for n in ("tester", "reviewer")) <= base.timestamp(r["created_at"]), "Independent review chronology/session invalid")
    return r


def ledger_branch(data): return "publication-ledger/" + data["payload_sha256"]
def request_title(data): return "D3 pilot publication " + data["payload"]["release"]["tag"]
def ledger_message(data=None): return "Reviewed pilot ledger proposal"
def pages_message(data=None): return "Reviewed pilot Pages publication"


def scope_projection(data):
    p = data["payload"]
    return {"profile": PROFILE, "payload_sha256": data["payload_sha256"], "review_sha256": data.get("review_sha256"),
            "destination": transport_enrollment(data["enrollment"]), "task": p["task"], "head": p["retention"]["main_commit"],
            "base": p["expected"]["main_sha"], "branch": ledger_branch(data), "assets": {n: {k: v[k] for k in ("size", "sha256")} for n, v in p["release"]["assets"].items()},
            "tag": p["release"]["tag"], "pages": {k: p["pages"][k] for k in ("parent", "tree", "commit", "changes")},
            "retention": {k: p["retention"][k] for k in ("before_sha256", "after_sha256")},
            "native": "UNVERIFIED", "interpreter": "UNVERIFIED", "piers": "UNVERIFIED", "production_authorized": False}


def preparation_body(data):
    return "D3 pilot metadata staging only; publication requires an exact owner PR review.\n\n" + base.canonical(scope_projection(data)).decode()


def request_body(data):
    if data.get("execution") is None: return preparation_body(data)
    x = data["execution"]
    public = {"scope": scope_projection(data), "execution_sha256": data["digest"], "nonce": x["nonce"],
              "expires_at": x["expires_at"], "approval": approval_text(data)}
    return "D3 pilot exact publication request. Review changes → Approve using the exact supplied text.\n\n" + base.canonical(public).decode()


def approval_text(data):
    return f'APPROVE D3-PILOT sha256:{data["digest"]} nonce:{data["execution"]["nonce"]} repo-id:{data["enrollment"]["repository_id"]} expires:{data["execution"]["expires_at"]}'


def preparation_grant(path, *, authorization=None, nonce=None, lifetime=3600, now=None):
    data = load_material(path, now=now); moment = base.timestamp(now)
    base.require(data.get("review") is not None and type(lifetime) is int and 0 < lifetime <= 3600, "Reviewed metadata preparation grant max one hour")
    expires = min(moment + timedelta(seconds=lifetime), base.timestamp(data["enrollment"]["evidence_expires_at"]))
    base.require(expires > moment, "Preparation evidence expired")
    base.require(authorization is not None, "Separate bounded owner metadata authorization required")
    _metadata_authorization(authorization, data, moment)
    expires = min(expires, base.timestamp(authorization["expires_at"]))
    grant = {"schema": 1, "profile": PROFILE, "kind": "pilot-metadata-grant-v1", "payload_sha256": data["payload_sha256"],
             "review_sha256": data["review_sha256"], "enrollment_sha256": base.sha(base.canonical(data["enrollment"])),
             "task": data["payload"]["task"], "destination": transport_enrollment(data["enrollment"]), "expected": data["payload"]["expected"],
             "branch": ledger_branch(data), "scope_sha256": base.sha(base.canonical(scope_projection(data))),
             "nonce": uuid.uuid4().hex if nonce is None else nonce, "created_at": base.utc(moment), "expires_at": base.utc(expires),
             "effects": ["create_blob", "create_tree", "create_commit", "create_ledger_branch", "create_ledger_pr", "update_request_pr"],
             "authorization": authorization, "publication_authorized": False}
    base.require(type(grant["nonce"]) is str and base.HEX32.fullmatch(grant["nonce"]), "Invalid preparation nonce")
    base.write_new(Path(path) / "preparation.json", base.canonical(grant)); return grant


def _metadata_authorization(value, data, moment, observation=False):
    base.closed(value, {"kind", "actor_id", "payload_sha256", "review_sha256", "task", "destination_sha256", "branch", "expires_at", "metadata_only", "authorization_sha256"})
    # A caller-authored record is not an authenticated live owner decision. The
    # trusted helper must separately enroll a real issuer before live staging.
    base.require(value["kind"] in ("local-test-staging", "owner-staging-authorization") and type(value["actor_id"]) is int and value["actor_id"] == d3.OWNER_ID
                 and value["payload_sha256"] == data["payload_sha256"] and value["review_sha256"] == data.get("review_sha256")
                 and same(value["task"], data["payload"]["task"]) and value["destination_sha256"] == base.sha(base.canonical(transport_enrollment(data["enrollment"])))
                 and value["branch"] == ledger_branch(data) and value["metadata_only"] is True,
                 "Unauthenticated or out-of-scope metadata authorization")
    base.require(type(value["authorization_sha256"]) is str and base.HEX64.fullmatch(value["authorization_sha256"]), "Missing staging issuer digest")
    if value["kind"] == "owner-staging-authorization" and not observation:
        import publication_cli
        publication_cli.validate_staging_authority(data, value, now=moment, observation=observation)
    if not observation: base.require(base.timestamp(value["expires_at"]) > moment, "Metadata authorization expired")


def _pr(pr, data):
    base.closed(pr, {"number", "id", "node_id", "head_sha", "base_sha", "head_ref", "base_ref", "url"})
    base.require(all(type(pr[n]) is int and 0 < pr[n] <= 2**53 - 1 for n in ("number", "id"))
                 and type(pr["node_id"]) is str and re.fullmatch(r"[A-Za-z0-9_=-]{3,200}", pr["node_id"])
                 and pr["head_sha"] == data["payload"]["retention"]["main_commit"] and pr["base_sha"] == data["payload"]["expected"]["main_sha"]
                 and pr["head_ref"] == ledger_branch(data) and pr["base_ref"] == "main"
                 and pr["url"] == "https://github.com/" + data["enrollment"]["repository"] + "/pull/" + str(pr["number"]), "Staged PR identity/head/base changed")
    return pr


def operations(payload):
    ops = d3.operations(payload); ops[-1] = {"kind": "merge_ledger"}; return ops


def seal_execution(path, staged_pr, *, nonce=None, lifetime=3600, now=None, recovery=None):
    data = load_material(path, now=now); moment = base.timestamp(now)
    base.require(data.get("review") is not None and data.get("preparation") is not None, "Review and separate metadata grant required")
    _pr(staged_pr, data); base.require(type(lifetime) is int and 0 < lifetime <= 3600, "Pilot approval lifetime max one hour")
    expires = min(moment + timedelta(seconds=lifetime), base.timestamp(data["enrollment"]["evidence_expires_at"]))
    base.require(expires > moment, "Pilot evidence expired")
    approved = operations(data["payload"]); completed = []
    if recovery is not None:
        base.closed(recovery, {"transaction", "remote_state_sha256", "completed"})
        base.require(all(type(recovery[k]) is str and base.HEX64.fullmatch(recovery[k]) for k in ("transaction", "remote_state_sha256")), "Malformed recovery")
        completed = recovery["completed"]
        base.require(type(completed) is list and completed == [d3.operation_id(o) for o in approved[:len(completed)]], "Recovery requires exact completed prefix")
    x = {"schema": 1, "profile": PROFILE, "kind": "pilot-execution-v1", "production_authorized": False,
         "payload_sha256": data["payload_sha256"], "review_sha256": data["review_sha256"],
         "enrollment_sha256": base.sha(base.canonical(data["enrollment"])), "preparation_sha256": base.sha(base.canonical(data["preparation"])),
         "destination": transport_enrollment(data["enrollment"]), "expected": data["payload"]["expected"],
         "task": data["payload"]["task"], "pr": staged_pr, "scope_sha256": base.sha(base.canonical(scope_projection(data))),
         "audience": {n: data["enrollment"][n] for n in ("installation_uuid", "epoch", "app_id", "app_installation_id")},
         "nonce": uuid.uuid4().hex if nonce is None else nonce, "created_at": base.utc(moment), "expires_at": base.utc(expires),
         "operations": approved[len(completed):], "recovery": recovery}
    base.require(type(x["nonce"]) is str and base.HEX32.fullmatch(x["nonce"]), "Malformed publication nonce")
    base.write_new(Path(path) / "execution.json", base.canonical(x)); return x


def load_material(path, expected_digest=None, now=None, observation=False):
    path = Path(path).absolute(); data = verify_payload(path); names = {f.name for f in path.iterdir()}
    base.require(names <= {"payload.json", "candidate", "snapshot", "review.json", "preparation.json", "execution.json"}, "Unreviewed outer control files")
    data.update(review=None, execution=None, preparation=None, digest=data["payload_sha256"])
    moment = base.timestamp(now)
    if "review.json" in names:
        data["review"] = _review(path, data); data["review_sha256"] = base.sha(base.canonical(data["review"]))
    if "preparation.json" in names:
        g = base.strict_load(base.safe_read(path / "preparation.json", base.MAX_JSON))
        base.closed(g, {"schema", "profile", "kind", "payload_sha256", "review_sha256", "enrollment_sha256", "task", "destination", "expected", "branch", "scope_sha256", "nonce", "created_at", "expires_at", "effects", "authorization", "publication_authorized"})
        base.require(type(g["schema"]) is int and g["schema"] == 1 and g["profile"] == PROFILE and g["kind"] == "pilot-metadata-grant-v1"
                     and g["publication_authorized"] is False and g["payload_sha256"] == data["payload_sha256"] and g["review_sha256"] == data.get("review_sha256")
                     and g["enrollment_sha256"] == base.sha(base.canonical(data["enrollment"])) and same(g["task"], data["payload"]["task"])
                     and same(g["destination"], transport_enrollment(data["enrollment"])) and same(g["expected"], data["payload"]["expected"])
                     and g["branch"] == ledger_branch(data) and g["scope_sha256"] == base.sha(base.canonical(scope_projection(data)))
                     and g["effects"] == ["create_blob", "create_tree", "create_commit", "create_ledger_branch", "create_ledger_pr", "update_request_pr"], "Altered or overbroad metadata grant")
        _metadata_authorization(g["authorization"], data, moment, observation or "execution.json" in names)
        base.require(base.timestamp(g["expires_at"]) <= base.timestamp(g["authorization"]["expires_at"]), "Grant exceeds owner metadata scope")
        _lifetime(g, data, moment, observation or "execution.json" in names); data["preparation"] = g
    if "execution.json" in names:
        x = base.strict_load(base.safe_read(path / "execution.json", base.MAX_JSON))
        base.closed(x, {"schema", "profile", "kind", "production_authorized", "payload_sha256", "review_sha256", "enrollment_sha256", "preparation_sha256", "destination", "expected", "task", "pr", "scope_sha256", "audience", "nonce", "created_at", "expires_at", "operations", "recovery"})
        base.require(type(x["schema"]) is int and x["schema"] == 1 and x["profile"] == PROFILE and x["kind"] == "pilot-execution-v1"
                     and x["production_authorized"] is False and x["payload_sha256"] == data["payload_sha256"] and x["review_sha256"] == data.get("review_sha256")
                     and data["preparation"] is not None and x["preparation_sha256"] == base.sha(base.canonical(data["preparation"]))
                     and x["enrollment_sha256"] == base.sha(base.canonical(data["enrollment"])) and same(x["destination"], transport_enrollment(data["enrollment"]))
                     and same(x["expected"], data["payload"]["expected"]) and same(x["task"], data["payload"]["task"])
                     and x["scope_sha256"] == base.sha(base.canonical(scope_projection(data)))
                     and same(x["audience"], {n: data["enrollment"][n] for n in ("installation_uuid", "epoch", "app_id", "app_installation_id")}), "Altered execution destination or reviewed scope")
        _pr(x["pr"], data); _lifetime(x, data, moment, observation)
        approved = operations(data["payload"]); completed = []
        if x["recovery"] is not None:
            rec = x["recovery"]; base.closed(rec, {"transaction", "remote_state_sha256", "completed"}); completed = rec["completed"]
            base.require(all(type(rec[k]) is str and base.HEX64.fullmatch(rec[k]) for k in ("transaction", "remote_state_sha256"))
                         and type(completed) is list and completed == [d3.operation_id(o) for o in approved[:len(completed)]], "Invalid recovery prefix")
        base.require(same(x["operations"], approved[len(completed):]), "Unauthorized execution operations")
        data.update(execution=x, digest=base.sha(base.canonical(x)))
    if expected_digest is not None: base.require(type(expected_digest) is str and data["digest"] == expected_digest, "Material digest mismatch")
    return data


def _lifetime(value, data, moment, observation):
    created = base.timestamp(value["created_at"]); expires = base.timestamp(value["expires_at"])
    base.require(type(value["nonce"]) is str and base.HEX32.fullmatch(value["nonce"])
                 and base.timestamp(data["review"]["created_at"]) <= created < expires <= base.timestamp(data["enrollment"]["evidence_expires_at"])
                 and expires - created <= timedelta(hours=1), "Invalid nonce, chronology or lifetime")
    if not observation: base.require(created <= moment < expires, "Approval or metadata grant expired/not yet valid")


def owner_summary(data):
    return {**scope_projection(data), "execution_sha256": data["digest"], "nonce": data["execution"]["nonce"], "expires_at": data["execution"]["expires_at"]}


def transport_authority(path, kind, now=None):
    """Re-load sealed data for every effect; no caller-authored grant dictionary."""
    base.require(kind in ("preparation", "publication"), "Unknown transport authority")
    data = load_material(path, now=now); grant = data[kind if kind == "preparation" else "execution"]
    base.require(grant is not None, "Required sealed authority absent")
    if kind == "preparation":
        _lifetime(grant, data, base.timestamp(now), False)
        _metadata_authorization(grant["authorization"], data, base.timestamp(now), False)
    return {"schema": 1, "profile": PROFILE, "kind": kind, "proposal_sha256": data["payload_sha256"],
            "execution_sha256": data["digest"] if data["execution"] is not None else None,
            "repository_id": data["enrollment"]["repository_id"], "expires_at": grant["expires_at"],
            "heads": {n: data["payload"]["expected"][n] for n in ("main_sha", "pages_sha")},
            "policy_sha256": data["enrollment"]["policy_sha256"],
            "mock_only": (data["preparation"]["authorization"]["kind"] == "local-test-staging"
                          or data["enrollment"]["identity_evidence"]["kind"] == "local-test-fixture"),
            "effects": effect_scopes(data, kind)}


def effect_scopes(data, kind):
    # Filled with exact argument hashes by the reviewed pure effect projection.
    return _effect_scopes(data, kind)


def _effect_scopes(data, kind):
    p = data["payload"]; snapshot = data["root"]; effects = {}
    initial = {n: p["expected"][n] for n in ("main_sha", "pages_sha")}
    after_pages = dict(initial, pages_sha=p["pages"]["commit"])
    def add(name, args, heads):
        args = dict(args, heads=heads)
        checksum = base.sha(base.canonical(args)); effects.setdefault(name, [])
        if checksum not in effects[name]: effects[name].append(checksum)
    def add_git(files, tree, parent, message, base_tree, heads):
        blobs = {}
        for name, raw in files.items():
            blob = base.git_object("blob", raw); blobs[name] = blob
            add("create_blob", {"data": {"size": len(raw), "sha256": base.sha(raw)}, "expected_sha": blob}, heads)
        add("create_tree", {"files": blobs, "expected_tree": tree, "base_tree": base_tree}, heads)
        add("create_commit", {"tree": tree, "parent": parent, "message": message,
                              "expected_sha": base.git_commit(tree, parent, message)}, heads)
    retained = p["retention"]
    if kind == "preparation":
        # Complete base tree preservation: only the two exact reviewed ledger
        # entries are added against its pinned baseline tree.
        main = {"releases/manifest.json": base.safe_read(snapshot / retained["successor_path"]),
                "config/qualification.json": base.safe_read(snapshot / retained["config_path"])}
        add_git(main, retained["main_tree"], retained["main_parent"], ledger_message(data), p["expected"]["main_tree"], initial)
        add("create_ledger_branch", {"branch": ledger_branch(data), "target": retained["main_commit"]}, initial)
        add("create_ledger_pr", {"branch": ledger_branch(data), "target": retained["main_commit"], "title": request_title(data), "body": preparation_body(data)}, initial)
        if data["execution"] is not None:
            add("update_request_pr", {"number": data["execution"]["pr"]["number"], "target": retained["main_commit"], "title": request_title(data), "body": request_body(data)}, initial)
            recovery = data["execution"]["recovery"]
            if recovery is not None and "promote_pages" in recovery["completed"]:
                add("update_request_pr", {"number": data["execution"]["pr"]["number"], "target": retained["main_commit"], "title": request_title(data), "body": request_body(data)}, after_pages)
    else:
        release = p["release"]
        add("create_tag", {"tag": release["tag"], "target": release["commit"]}, initial)
        add("create_draft", {"tag": release["tag"], "target": release["commit"], "name": release["name"], "notes": release["notes"]}, initial)
        for name, asset in release["assets"].items():
            add("upload_asset", {"tag": release["tag"], "name": name, "data": {"size": asset["size"], "sha256": asset["sha256"]}, "expected_sha256": asset["sha256"]}, initial)
        add("publish_release", {"tag": release["tag"], "target": release["commit"], "assets": {n: {"size": a["size"], "sha256": a["sha256"]} for n, a in release["assets"].items()}, "name": release["name"], "notes": release["notes"]}, initial)
        site = {n: base.safe_read(snapshot / p["pages"]["site_prefix"] / n) for n in p["pages"]["site_files"]}
        add_git(site, p["pages"]["tree"], p["pages"]["parent"], pages_message(data), None, initial)
        add("fast_forward_pages", {"target": p["pages"]["commit"], "parent": p["pages"]["parent"], "tree": p["pages"]["tree"]}, initial)
        add("merge_ledger_pr", {"number": data["execution"]["pr"]["number"], "target": retained["main_commit"], "expected_tree": retained["main_tree"]}, after_pages)
    return {name: sorted(values) for name, values in effects.items()}

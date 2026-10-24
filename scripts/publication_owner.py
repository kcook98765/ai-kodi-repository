"""Strict owner-proof checks through a concrete local scripted mock only.

A successful observation authenticates no real human and grants no network or
production authority. D1/D2 approve-test objects are never owner proof here.
"""
from __future__ import annotations
import base64
import io
from pathlib import Path
import stat
import sys
import zipfile
from datetime import timedelta
sys.path.insert(0, str(Path(__file__).resolve().parent))
import publication_proposal as core
import publication_d3_contract as contract
import publication_github as github

ARTIFACT_NAME = "d3-approval-request"
SCOPE_MEMBER = "approval-scope.json"


class RevokedApproval(ValueError):
    def __init__(self, nonce, proposal_sha256, revocation_sha256):
        super().__init__("Authenticated mock owner revocation observed")
        self.nonce = nonce
        self.proposal_sha256 = proposal_sha256
        self.revocation_sha256 = revocation_sha256


def approval_comment(data, run_id):
    return (f'APPROVE D3-QUALIFICATION sha256:{data["digest"]} nonce:{data["execution"]["nonce"]} '
            f'repo-id:{data["enrollment"]["repository_id"]} run:{run_id}')


def scope_document(data, run_id):
    e = data["enrollment"]; x = data["execution"]
    return {"schema": 1, "mode": contract.MODE, "proposal_sha256": data["digest"], "nonce": x["nonce"],
            "repository_id": e["repository_id"], "owner_id": e["owner_id"], "run_id": run_id, "run_attempt": 1,
            "workflow_id": e["workflow_id"], "workflow_commit": x["expected"]["main_sha"], "environment_id": e["environment_id"],
            "installation_uuid": e["installation_uuid"], "epoch": e["epoch"], "expires_at": x["expires_at"],
            "summary_sha256": core.sha(core.canonical(contract.owner_summary(data)))}


def scope_archive(document):
    """Synthetic artifact producer for local test responses only."""
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as zipped:
        info = zipfile.ZipInfo(SCOPE_MEMBER, (1980, 1, 1, 0, 0, 0))
        info.create_system = 3; info.external_attr = 0o100644 << 16
        zipped.writestr(info, core.canonical(document))
    return out.getvalue()


def number(value, expected, label):
    core.require(type(value) is int and value == expected, label + " numeric identity mismatch")


def identity(value, expected, kind, label):
    core.require(type(value) is dict and value.get("type") == kind, label + " actor type mismatch")
    number(value.get("id"), expected, label)


def pages_comment(data, run_id):
    return (f'APPROVE D3-PAGES sha256:{data["digest"]} nonce:{data["execution"]["nonce"]} '
            f'repo-id:{data["enrollment"]["repository_id"]} run:{run_id}')


def revocation(raw, data):
    e = data["enrollment"]; issue = raw["control_issue"]
    number(issue.get("number"), e["control_issue_number"], "Revocation issue")
    core.require(issue.get("repository_url") == "https://api.github.com/repos/" + e["repository"], "Wrong revocation issue repository")
    comments = raw["revocation_comments"]; core.require(type(comments) is list, "Complete revocation history required")
    body = f'REVOKE {data["digest"]} {data["execution"]["nonce"]}'
    for comment in comments:
        core.require(type(comment) is dict and type(comment.get("user")) is dict and type(comment.get("body")) is str, "Malformed revocation comment")
        actor = comment["user"]
        if type(actor.get("id")) is int and actor["id"] == e["human_owner_id"] and actor.get("type") == "User" and comment["body"] == body:
            raise RevokedApproval(data["execution"]["nonce"], data["digest"], core.sha(core.canonical(comment)))


def bound_proposal(data, enrolled, now=None):
    """Verify the approval audience/digests independently of caller bookkeeping.

    Package/file eligibility remains the frozen contract's separate root-entry
    gate; an owner's decision cannot supply technical evidence.
    """
    x = data["execution"]; current = core.timestamp(now)
    core.closed(x, {"schema", "kind", "mode", "mock_only", "production_authorized", "payload_sha256", "review_sha256",
                    "enrollment_sha256", "expected", "destination", "nonce", "created_at", "expires_at", "audience", "operations", "recovery"})
    core.require(type(x["schema"]) is int and x["schema"] == 1 and x["kind"] == "d3-execution-proposal-v1"
                 and x["mode"] == contract.MODE and x["mock_only"] is True and x["production_authorized"] is False
                 and contract.same(data["enrollment"], enrolled), "Owner proof has wrong qualification audience")
    core.require(type(data["digest"]) is str and core.HEX64.fullmatch(data["digest"])
                 and core.sha(core.canonical(x)) == data["digest"]
                 and x["payload_sha256"] == core.sha(core.canonical(data["payload"]))
                 and x["review_sha256"] == core.sha(core.canonical(data["review"]))
                 and x["enrollment_sha256"] == core.sha(core.canonical(enrolled)), "Owner proof proposal digest binding failed")
    core.require(data["review"]["payload_sha256"] == x["payload_sha256"]
                 and contract.same(x["expected"], data["payload"]["expected"])
                 and contract.same(x["destination"], contract.transport_enrollment(enrolled))
                 and contract.same(x["audience"], {k: enrolled[k] for k in ("installation_uuid", "epoch", "app_id", "app_installation_id")}),
                 "Owner approval destination, installation or reviewed scope changed")
    core.require(type(x["nonce"]) is str and core.HEX32.fullmatch(x["nonce"]), "Malformed owner proposal nonce")
    created = core.timestamp(x["created_at"]); expires = core.timestamp(x["expires_at"])
    core.require(core.timestamp(data["payload"]["created_at"]) <= core.timestamp(data["review"]["created_at"]) <= created <= current < expires
                 and expires - created <= timedelta(hours=1) and expires <= core.timestamp(enrolled["evidence_expires_at"]),
                 "Owner proposal or evidence expired, future or overlong")
    return current


class OwnerVerifier:
    def __init__(self, enrollment, transport, credential):
        self.enrollment = contract.validate_enrollment(enrollment)
        core.require(type(transport) is github.GitHubQualification and type(transport.sender) is github.ScriptedMockSender
                     and type(credential) is github.SimulatedCredential, "Concrete trusted mock transport required")
        core.require(contract.same(transport.enrolled, contract.transport_enrollment(enrollment)), "Owner-proof destination mismatch")
        self.transport = transport; self.credential = credential

    def verify(self, data, run_id, now=None):
        e = self.enrollment; x = data["execution"]; current = bound_proposal(data, e, now)
        core.require(contract.same(data["enrollment"], e) and x["mode"] == contract.MODE
                     and x["mock_only"] is True and x["production_authorized"] is False, "Unrelated, simulation or live owner authority rejected")
        core.require(type(run_id) is int and run_id > 0, "Correlated dispatch run ID required")
        core.require(core.timestamp(x["created_at"]) <= current < core.timestamp(x["expires_at"])
                     <= core.timestamp(e["evidence_expires_at"]), "Owner proposal/evidence expired")
        raw = self.transport.observe_owner_proof(self.credential, e, run_id)
        core.closed(raw, {"run", "workflow", "environment", "environment_branches", "review_history", "jobs",
                          "artifact_metadata", "artifact_archive", "workflow_file", "revocation_comments", "control_issue",
                          "mock_only", "source", "production_authorized"})
        core.require(raw["mock_only"] is True and raw["source"] == "scripted-mock-transport"
                     and raw["production_authorized"] is False, "Untrusted or live owner observation source")
        revocation(raw, data)
        run = raw["run"]; number(run.get("id"), run_id, "Run"); number(run.get("run_attempt"), 1, "Run attempt")
        number(run.get("workflow_id"), e["workflow_id"], "Workflow")
        core.require(run.get("event") == "workflow_dispatch" and run.get("head_sha") == x["expected"]["main_sha"]
                     and run.get("head_branch") == "main" and run.get("status") == "completed" and run.get("conclusion") == "success",
                     "Wrong or incomplete approval run")
        repository = run.get("repository"); core.require(type(repository) is dict, "Run repository missing")
        number(repository.get("id"), e["repository_id"], "Run repository")
        core.require(repository.get("full_name") == e["repository"], "Run repository name mismatch")
        identity(repository.get("owner"), e["owner_id"], "Organization", "Repository organization")
        identity(run.get("actor"), e["bot_user_id"], "Bot", "Dispatcher bot")
        core.require(run["actor"].get("login") == e["bot_login"], "Dispatcher login mismatch")
        core.require(core.timestamp(x["created_at"]) <= core.timestamp(run.get("created_at")) <= current, "Stale or future run")
        workflow = raw["workflow"]; number(workflow.get("id"), e["workflow_id"], "Workflow")
        core.require(workflow.get("path") == e["workflow_path"] and workflow.get("state") == "active", "Wrong workflow path/state")
        content = raw["workflow_file"]
        core.require(content.get("type") == "file" and content.get("encoding") == "base64" and type(content.get("content")) is str, "Workflow content missing")
        try: workflow_bytes = base64.b64decode(content["content"].replace("\n", ""), validate=True)
        except (ValueError, TypeError) as error: raise ValueError("Invalid workflow content") from error
        core.require(len(workflow_bytes) <= 100000 and core.sha(workflow_bytes) == e["workflow_sha256"]
                     and content.get("sha") == core.git_object("blob", workflow_bytes), "Workflow bytes changed")
        environment = raw["environment"]; number(environment.get("id"), e["environment_id"], "Environment")
        core.require(environment.get("name") == e["environment_name"] and environment.get("can_admins_bypass") is False
                     and contract.same(environment.get("deployment_branch_policy"), {"protected_branches": False, "custom_branch_policies": True}), "Unsafe environment policy")
        rules = environment.get("protection_rules"); core.require(type(rules) is list, "Missing reviewer policy")
        reviewer_rules = [r for r in rules if r.get("type") == "required_reviewers"]
        core.require(len(reviewer_rules) == 1 and reviewer_rules[0].get("prevent_self_review") is True, "Owner/self-review policy missing")
        reviewers = reviewer_rules[0].get("reviewers")
        core.require(type(reviewers) is list and len(reviewers) == 1 and reviewers[0].get("type") == "User", "Exact human owner required")
        identity(reviewers[0].get("reviewer"), e["human_owner_id"], "User", "Required reviewer")
        policies = raw["environment_branches"]
        core.require(type(policies) is list and len(policies) == 1
                     and policies[0].get("name") == "main" and policies[0].get("type") == "branch", "Unenrolled deployment refs")
        jobs = raw["jobs"]; core.require(type(jobs) is list, "Missing gated job evidence")
        gated = [j for j in jobs if j.get("name") == "owner-approval"]
        core.require(len(gated) == 1 and gated[0].get("status") == "completed" and gated[0].get("conclusion") == "success", "Owner job incomplete")
        number(gated[0].get("run_id"), run_id, "Gated job run"); number(gated[0].get("run_attempt"), 1, "Gated job attempt")
        core.require(gated[0].get("head_sha") == x["expected"]["main_sha"], "Gated job head mismatch")
        history = raw["review_history"]; core.require(type(history) is list and len(history) == 1, "Missing or contradictory approval history")
        decision = history[0]; identity(decision.get("user"), e["human_owner_id"], "User", "Approving owner")
        core.require(decision.get("state") == "approved" and decision.get("comment") == approval_comment(data, run_id), "Exact owner comment required")
        environments = decision.get("environments"); core.require(type(environments) is list and len(environments) == 1, "Ambiguous approval environment")
        number(environments[0].get("id"), e["environment_id"], "Approved environment")
        core.require(environments[0].get("name") == e["environment_name"], "Approved environment name changed")
        metadata = raw["artifact_metadata"]
        core.require(metadata.get("name") == ARTIFACT_NAME and type(metadata.get("id")) is int and metadata["id"] > 0
                     and metadata.get("expired") is False, "Trusted scope artifact missing")
        association = metadata.get("workflow_run"); core.require(type(association) is dict, "Artifact run binding missing")
        number(association.get("id"), run_id, "Artifact run"); number(association.get("repository_id"), e["repository_id"], "Artifact repository")
        number(association.get("head_repository_id"), e["repository_id"], "Artifact head repository")
        core.require(association.get("head_sha") == x["expected"]["main_sha"] and association.get("head_branch") == "main", "Artifact workflow head changed")
        archive = raw["artifact_archive"]
        core.require(type(archive) is bytes and len(archive) <= 1000000 and type(metadata.get("size_in_bytes")) is int
                     and metadata["size_in_bytes"] == len(archive) and metadata.get("digest") == "sha256:" + core.sha(archive), "Archive hash/size mismatch")
        try:
            with zipfile.ZipFile(io.BytesIO(archive)) as zipped:
                members = zipped.infolist()
                core.require(len(members) == 1 and members[0].filename == SCOPE_MEMBER and not members[0].is_dir()
                             and not members[0].flag_bits & 1 and members[0].file_size <= 100000
                             and stat.S_IFMT(members[0].external_attr >> 16) in (0, stat.S_IFREG), "Unsafe scope archive")
                scope_raw = zipped.read(SCOPE_MEMBER)
        except (zipfile.BadZipFile, RuntimeError) as error: raise ValueError("Malformed scope archive") from error
        core.require(contract.same(core.strict_load(scope_raw), scope_document(data, run_id)), "Scope document differs from frozen E")
        comments = raw["revocation_comments"]
        proof = {"run_id": run_id, "scope_archive_sha256": core.sha(archive), "scope_document_sha256": core.sha(scope_raw),
                 "review_sha256": core.sha(core.canonical(history)), "environment_sha256": core.sha(core.canonical(environment)),
                 "revocation_sha256": core.sha(core.canonical(comments))}
        return {"status": "MOCK_OWNER_PROOF_VERIFIED", "actor_id": e["human_owner_id"], "run_id": run_id,
                "proposal_sha256": data["digest"], "nonce": x["nonce"], "proof_sha256": core.sha(core.canonical(proof)),
                "expires_at": x["expires_at"], "observed_at": core.utc(current), "mock_only": True,
                "production_authorized": False, "network_authorized": False, "real_owner_authenticated": False}

    def verify_pages(self, data, run_id, now=None):
        e = self.enrollment; x = data["execution"]; current = bound_proposal(data, e, now)
        core.require(contract.same(data["enrollment"], e) and x["mode"] == contract.MODE and x["mock_only"] is True
                     and x["production_authorized"] is False, "Wrong Pages qualification scope")
        core.require(type(run_id) is int and run_id > 0 and core.timestamp(x["created_at"]) <= current < core.timestamp(x["expires_at"]), "Expired or malformed Pages owner request")
        raw = self.transport.observe_pages_proof(self.credential, e, run_id)
        core.closed(raw, {"run", "workflow", "environment", "environment_branches", "review_history", "jobs",
                          "revocation_comments", "control_issue", "mock_only", "source", "production_authorized"})
        core.require(raw["mock_only"] is True and raw["source"] == "scripted-mock-transport" and raw["production_authorized"] is False, "Untrusted Pages observation source")
        revocation(raw, data)
        run = raw["run"]; number(run.get("id"), run_id, "Pages run"); number(run.get("run_attempt"), 1, "Pages run attempt")
        number(run.get("workflow_id"), e["pages_workflow_id"], "Pages workflow")
        core.require(run.get("event") == "push" and run.get("head_sha") == data["payload"]["pages"]["commit"]
                     and run.get("head_branch") == "gh-pages" and run.get("status") == "completed" and run.get("conclusion") == "success", "Pages deployment does not match approved commit")
        repository = run.get("repository"); core.require(type(repository) is dict and repository.get("full_name") == e["repository"], "Wrong Pages repository")
        number(repository.get("id"), e["repository_id"], "Pages repository"); identity(repository.get("owner"), e["owner_id"], "Organization", "Pages organization")
        identity(run.get("actor"), e["bot_user_id"], "Bot", "Pages dispatch bot")
        core.require(run["actor"].get("login") == e["bot_login"]
                     and core.timestamp(x["created_at"]) <= core.timestamp(run.get("created_at")) <= current,
                     "Pages run is stale, future or dispatched by an unenrolled bot")
        workflow = raw["workflow"]; number(workflow.get("id"), e["pages_workflow_id"], "Pages workflow")
        core.require(workflow.get("path") == "dynamic/pages/pages-build-deployment" and workflow.get("state") == "active", "Wrong managed Pages workflow")
        environment = raw["environment"]; number(environment.get("id"), e["pages_environment_id"], "Pages environment")
        core.require(environment.get("name") == "github-pages" and environment.get("can_admins_bypass") is False
                     and contract.same(environment.get("deployment_branch_policy"), {"protected_branches": False, "custom_branch_policies": True}), "Pages environment bypass/ref policy mismatch")
        rules = environment.get("protection_rules"); core.require(type(rules) is list, "Pages reviewer policy missing")
        reviewers = [r for r in rules if r.get("type") == "required_reviewers"]
        core.require(len(reviewers) == 1 and reviewers[0].get("prevent_self_review") is True
                     and type(reviewers[0].get("reviewers")) is list and len(reviewers[0]["reviewers"]) == 1
                     and reviewers[0]["reviewers"][0].get("type") == "User", "Pages human/self-review gate missing")
        identity(reviewers[0]["reviewers"][0].get("reviewer"), e["human_owner_id"], "User", "Required Pages owner")
        policies = raw["environment_branches"]
        core.require(type(policies) is list and len(policies) == 1 and policies[0].get("name") == "gh-pages" and policies[0].get("type") == "branch", "Pages permits unenrolled refs")
        history = raw["review_history"]; core.require(type(history) is list and len(history) == 1, "Pages owner history missing or ambiguous")
        decision = history[0]; identity(decision.get("user"), e["human_owner_id"], "User", "Approving Pages owner")
        core.require(decision.get("state") == "approved" and decision.get("comment") == pages_comment(data, run_id), "Exact Pages owner comment required")
        environments = decision.get("environments"); core.require(type(environments) is list and len(environments) == 1, "Pages decision environment missing")
        number(environments[0].get("id"), e["pages_environment_id"], "Approved Pages environment")
        core.require(environments[0].get("name") == "github-pages", "Wrong Pages approval environment name")
        jobs = raw["jobs"]; core.require(type(jobs) is list and jobs, "Pages jobs missing")
        for job in jobs:
            number(job.get("run_id"), run_id, "Pages job run"); number(job.get("run_attempt"), 1, "Pages job attempt")
            core.require(job.get("head_sha") == data["payload"]["pages"]["commit"] and job.get("status") == "completed"
                         and job.get("conclusion") in ("success", "skipped"), "Pages jobs not complete for approved commit")
        deployed = [j for j in jobs if j.get("name") == "deploy"]
        core.require(len(deployed) == 1 and deployed[0].get("status") == "completed"
                     and deployed[0].get("conclusion") == "success", "Actual Pages deployment job did not succeed")
        proof = {k: raw[k] for k in ("run", "workflow", "environment", "environment_branches", "review_history", "jobs", "revocation_comments")}
        return {"status": "MOCK_PAGES_OWNER_PROOF_VERIFIED", "actor_id": e["human_owner_id"], "run_id": run_id,
                "proposal_sha256": data["digest"], "nonce": x["nonce"], "proof_sha256": core.sha(core.canonical(proof)),
                "expires_at": x["expires_at"], "observed_at": core.utc(current), "mock_only": True,
                "production_authorized": False, "network_authorized": False, "real_owner_authenticated": False}

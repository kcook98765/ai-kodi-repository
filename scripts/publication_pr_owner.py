"""Exact owner PR decisions for d3-pr-pilot-v1, with mock authority separated."""
from __future__ import annotations
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
import publication_proposal as base
import publication_pilot_contract as contract


class RevokedApproval(ValueError):
    def __init__(self, nonce, proposal_sha256, revocation_sha256, review_id=None):
        super().__init__("Bound PR publication approval revoked or dismissed")
        self.nonce = nonce; self.proposal_sha256 = proposal_sha256
        self.revocation_sha256 = revocation_sha256; self.review_id = review_id


def approval_comment(data): return contract.approval_text(data)


def _number(value, expected, label):
    base.require(type(value) is int and value == expected, label + " numeric identity mismatch")


def _actor(value, expected, kind, label):
    base.require(type(value) is dict and value.get("type") == kind, label + " actor type mismatch")
    _number(value.get("id"), expected, label)


def _id(value):
    base.require(type(value) is int and 0 < value <= 2**53 - 1, "Malformed GitHub object ID")
    return value


class OwnerPRVerifier:
    def __init__(self, enrollment, transport):
        import publication_github_live as github
        self.enrollment = contract.validate_enrollment(enrollment)
        base.require(type(transport) is github.PilotGitHub, "Concrete enrolled pilot transport required")
        actual = getattr(transport, "enrollment", getattr(transport, "enrolled", None))
        base.require(contract.same(actual, self.enrollment) or contract.same(actual, contract.transport_enrollment(self.enrollment)), "PR verifier transport destination mismatch")
        self.transport = transport

    def verify(self, data, now=None):
        current = base.timestamp(now)
        base.require(type(data) is dict and "material_path" in data and data.get("execution") is not None, "Frozen exact PR execution material required")
        fresh = contract.load_material(data["material_path"], data.get("digest"), now=current)
        base.require(contract.same(fresh["enrollment"], self.enrollment)
                     and all(contract.same(fresh[name], data[name]) for name in ("payload", "review", "execution")), "Caller altered frozen PR proposal")
        data = fresh; x = data["execution"]; e = self.enrollment
        raw = self.transport.observe_pr_owner(x["pr"]["number"])
        base.closed(raw, {"pr", "reviews", "comments", "policy", "transport", "authenticated"})
        base.require(raw["transport"] in ("scripted-mock-https", "github-https") and type(raw["authenticated"]) is bool
                     and raw["authenticated"] is (raw["transport"] == "github-https"), "Untrusted PR observation marker")
        pr = raw["pr"]; expected = x["pr"]; base.require(type(pr) is dict, "Malformed PR observation")
        _number(pr.get("number"), expected["number"], "PR number"); _number(pr.get("id"), expected["id"], "PR")
        base.require(pr.get("node_id") == expected["node_id"] and pr.get("html_url") == expected["url"], "PR object identity changed")
        comments = raw["comments"]; reviews = raw["reviews"]
        base.require(type(comments) is list and type(reviews) is list, "Complete PR decision/revocation history required")
        for comment in comments:
            base.require(type(comment) is dict and type(comment.get("user")) is dict and type(comment.get("body")) is str, "Malformed PR revocation comment")
            _id(comment.get("id")); actor = comment["user"]
            if type(actor.get("id")) is int and actor["id"] == e["human_owner_id"] and actor.get("type") == "User" and comment["body"] == f'REVOKE {data["digest"]} {x["nonce"]}':
                raise RevokedApproval(x["nonce"], data["digest"], base.sha(base.canonical(comment)))
        if pr.get("state") == "closed":
            raise RevokedApproval(x["nonce"], data["digest"], base.sha(base.canonical({"pr_id": pr["id"], "state": "closed", "merged": pr.get("merged")})))
        base.require(pr.get("state") == "open" and pr.get("merged") is False and pr.get("draft") is False, "Owner decision requires an open unmerged request PR")
        _actor(pr.get("user"), e["bot_user_id"], "Bot", "PR author")
        base.require(pr["user"].get("login") == e["bot_login"] and pr.get("title") == contract.request_title(data)
                     and pr.get("body") == contract.request_body(data), "Current PR public scope changed")
        for field, ref, commit in (("head", expected["head_ref"], expected["head_sha"]), ("base", "main", expected["base_sha"])):
            item = pr.get(field); base.require(type(item) is dict and item.get("ref") == ref and item.get("sha") == commit, "PR head/base changed")
            repository = item.get("repo"); base.require(type(repository) is dict and repository.get("full_name") == e["repository"], "PR repository name changed")
            _number(repository.get("id"), e["repository_id"], "PR repository")
            _actor(repository.get("owner"), e["owner_id"], "Organization", "PR organization")
        policy = raw["policy"]
        base.require(type(policy) is dict and policy.get("policy_sha256") == e["policy_sha256"], "Observed protection policy changed")
        decisions = []; seen = set()
        for review in reviews:
            base.require(type(review) is dict and type(review.get("user")) is dict and type(review.get("body")) is str, "Malformed review history")
            ident = _id(review.get("id")); base.require(ident not in seen, "Duplicate review identity"); seen.add(ident)
            actor = review["user"]
            base.require(type(actor.get("id")) is int and actor.get("type") in ("User", "Bot"), "Mistyped review actor")
            if actor["id"] != e["human_owner_id"]: continue
            _actor(actor, e["human_owner_id"], "User", "Owner review")
            state = review.get("state")
            base.require(state in ("APPROVED", "CHANGES_REQUESTED", "DISMISSED", "COMMENTED", "PENDING"), "Unknown owner review state")
            if state == "DISMISSED" and review["body"] == approval_comment(data):
                raise RevokedApproval(x["nonce"], data["digest"], base.sha(base.canonical(review)), ident)
            if state in ("APPROVED", "CHANGES_REQUESTED", "DISMISSED"):
                decisions.append((base.timestamp(review.get("submitted_at")), ident, review))
        base.require(decisions, "Genuine attributable owner PR approval absent")
        decisions.sort(key=lambda item: (item[0], item[1])); selected = decisions[-1][2]
        if selected["state"] != "APPROVED":
            raise RevokedApproval(x["nonce"], data["digest"], base.sha(base.canonical(selected)), selected["id"])
        base.require(selected.get("commit_id") == expected["head_sha"] and selected["body"] == approval_comment(data), "Approval stale or not bound to exact execution digest")
        submitted = base.timestamp(selected["submitted_at"])
        base.require(base.timestamp(x["created_at"]) <= submitted <= current < base.timestamp(x["expires_at"]), "Approval submission outside proposal lifetime")
        authenticated = raw["authenticated"] and e["identity_evidence"]["kind"] == "github-readback"
        return {"status": "OWNER_PR_PROOF_VERIFIED" if authenticated else "MOCK_OWNER_PR_PROOF_VERIFIED",
                "actor_id": e["human_owner_id"], "review_id": selected["id"], "pr_id": expected["id"], "pr_number": expected["number"],
                "proposal_sha256": data["digest"], "nonce": x["nonce"], "proof_sha256": base.sha(base.canonical(raw)),
                "expires_at": x["expires_at"], "observed_at": base.utc(current), "mock_only": not authenticated,
                "network_authorized": authenticated, "production_authorized": False, "real_owner_authenticated": authenticated}

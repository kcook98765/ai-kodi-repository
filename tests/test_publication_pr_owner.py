"""Owner proof exercises finite HTTP responses; no network or valid credentials."""
import copy
from datetime import timedelta
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import publication_proposal as base
import publication_pilot_contract as contract
import publication_pr_owner as owner
import publication_github_live as live
from test_publication_pilot_contract import build_pilot_material, NOW
from pilot_github_model import pilot_policy, CEILING, TestSigner


def build_pr_observation(data, now=NOW):
    e = data["enrollment"]; x = data["execution"]; staged = x["pr"]
    repository = {"id": e["repository_id"], "full_name": e["repository"], "private": False,
        "owner": {"id": e["owner_id"], "type": "Organization", "login": e["repository"].split("/")[0]}}
    pr = {"id": staged["id"], "number": staged["number"], "node_id": staged["node_id"], "html_url": staged["url"],
          "head": {"sha": staged["head_sha"], "ref": staged["head_ref"], "repo": copy.deepcopy(repository)},
          "base": {"sha": staged["base_sha"], "ref": "main", "repo": copy.deepcopy(repository)},
          "state": "open", "merged": False, "draft": False, "title": contract.request_title(data), "body": contract.request_body(data),
          "user": {"id": e["bot_user_id"], "type": "Bot", "login": e["bot_login"]}}
    review = {"id": 1300001, "user": {"id": e["human_owner_id"], "type": "User", "login": "kcook98765"},
              "state": "APPROVED", "commit_id": staged["head_sha"], "submitted_at": base.utc(now), "body": owner.approval_comment(data)}
    policy = {**live.expected_policy(e), "policy_sha256": e["policy_sha256"]}
    return {"pr": pr, "reviews": [review], "comments": [], "policy": policy,
            "transport": "scripted-mock-https", "authenticated": False, "mock_only": True, "production_authorized": False}


def owner_exchanges(data, observation=None, now=NOW, *, minted=None):
    raw = build_pr_observation(data, now) if observation is None else observation
    e = data["enrollment"]; number = data["execution"]["pr"]["number"]; out = []; minted = set() if minted is None else minted
    prefix = "https://api.github.com/repos/" + e["repository"]
    def token(cap):
        requested = dict(cap, metadata="read"); key = tuple(sorted(requested.items()))
        if key in minted: return
        minted.add(key); org = {"id": e["owner_id"], "type": "Organization"}
        out.extend([live.HTTPExchange("GET", "https://api.github.com/app", live.HTTPResponse.json(200, {"id": e["app_id"], "owner": org, "permissions": CEILING})),
            live.HTTPExchange("GET", "https://api.github.com/app/installations/" + str(e["app_installation_id"]), live.HTTPResponse.json(200,
                {"id": e["app_installation_id"], "app_id": e["app_id"], "repository_selection": "selected", "suspended_at": None, "account": org, "permissions": CEILING})),
            live.HTTPExchange("POST", "https://api.github.com/app/installations/" + str(e["app_installation_id"]) + "/access_tokens", live.HTTPResponse.json(201,
                {"token": "local_test_token_never_valid", "permissions": requested, "expires_at": base.utc(now + timedelta(hours=1)), "repository_selection": "selected",
                 "repositories": [{"id": e["repository_id"], "full_name": e["repository"]}]}), {"repository_ids": [e["repository_id"]], "permissions": requested})])
    def get(path, value, cap):
        token(cap); out.append(live.HTTPExchange("GET", prefix + path, live.HTTPResponse.json(200, value)))
    get(f"/pulls/{number}", raw["pr"], {"pull_requests": "read"})
    get(f"/pulls/{number}/reviews?per_page=100&page=1", raw["reviews"], {"pull_requests": "read"})
    get(f"/issues/{number}/comments?per_page=100&page=1", raw["comments"], {"pull_requests": "read"})
    get("", dict(raw["pr"]["head"]["repo"], **raw["policy"]["repository"]), {"contents": "read"})
    rules = raw["policy"]["rulesets"]
    get("/rulesets?includes_parents=true&per_page=100&page=1", [{"id": r["id"]} for r in rules], {"administration": "read"})
    for rule in rules: get("/rulesets/" + str(rule["id"]), rule, {"administration": "read"})
    get("/environments/github-pages", raw["policy"]["environments"]["github-pages"], {"actions": "read"})
    get("/environments/github-pages/deployment-branch-policies?per_page=100&page=1",
        {"total_count": len(raw["policy"]["pages_branch_policies"]), "branch_policies": raw["policy"]["pages_branch_policies"]}, {"actions": "read"})
    get("/actions/permissions/workflow", raw["policy"]["default_actions"], {"administration": "read"})
    get("/immutable-releases", raw["policy"]["immutable_releases"], {"administration": "read"})
    return out


def make_verifier(data, observation=None, now=NOW):
    backend = live.ScriptedHTTPS(owner_exchanges(data, observation, now))
    provider = live.AppTokenProvider(data["enrollment"], TestSigner(), backend, clock=lambda: now)
    transport = live.PilotGitHub(data["enrollment"], provider, backend, clock=lambda: now)
    return owner.OwnerPRVerifier(data["enrollment"], transport), backend


class PROwnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.path = build_pilot_material(Path(self.temp.name) / "one")
        self.data = contract.load_material(self.path, now=NOW)

    def test_serialized_owner_proof_never_turns_mock_into_live(self):
        verifier, backend = make_verifier(self.data)
        receipt = verifier.verify(self.data, now=NOW)
        self.assertEqual(receipt["review_id"], 1300001); self.assertTrue(receipt["mock_only"])
        self.assertFalse(receipt["network_authorized"]); self.assertFalse(receipt["real_owner_authenticated"])
        self.assertEqual(backend.remaining, 0)

    def test_review_actor_and_id_are_typed_not_app_bot_org_or_bool(self):
        for field, value in (("id", True), ("user", {"id": 56806582, "type": "Bot"}),
                             ("user", {"id": self.data["enrollment"]["app_id"], "type": "User"})):
            raw = build_pr_observation(self.data); raw["reviews"][0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError): make_verifier(self.data, raw)[0].verify(self.data, now=NOW)

    def test_exact_body_commit_submitted_time_and_current_scope_required(self):
        for field, value in (("body", "APPROVE"), ("commit_id", "f" * 40), ("submitted_at", base.utc(NOW - timedelta(seconds=1)))):
            raw = build_pr_observation(self.data); raw["reviews"][0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError): make_verifier(self.data, raw)[0].verify(self.data, now=NOW)
        raw = build_pr_observation(self.data); raw["pr"]["body"] += " changed"
        with self.assertRaises(ValueError): make_verifier(self.data, raw)[0].verify(self.data, now=NOW)

    def test_latest_decision_and_dismissal_are_revocation(self):
        raw = build_pr_observation(self.data); later = copy.deepcopy(raw["reviews"][0]); later.update(id=1300002, state="CHANGES_REQUESTED", body="Stop")
        raw["reviews"].append(later)
        with self.assertRaises(owner.RevokedApproval): make_verifier(self.data, raw)[0].verify(self.data, now=NOW)
        raw = build_pr_observation(self.data); raw["reviews"][0]["state"] = "DISMISSED"
        with self.assertRaises(owner.RevokedApproval): make_verifier(self.data, raw)[0].verify(self.data, now=NOW)

    def test_close_and_owner_revoke_fail_but_spoof_does_not(self):
        raw = build_pr_observation(self.data); raw["pr"]["state"] = "closed"
        with self.assertRaises(owner.RevokedApproval): make_verifier(self.data, raw)[0].verify(self.data, now=NOW)
        raw = build_pr_observation(self.data)
        revoke = {"id": 1400001, "body": "REVOKE " + self.data["digest"] + " " + self.data["execution"]["nonce"], "user": {"id": 56806582, "type": "User"}}
        raw["comments"].append(revoke)
        with self.assertRaises(owner.RevokedApproval): make_verifier(self.data, raw)[0].verify(self.data, now=NOW)
        revoke["user"] = {"id": self.data["enrollment"]["bot_user_id"], "type": "Bot"}
        self.assertTrue(make_verifier(self.data, raw)[0].verify(self.data, now=NOW)["mock_only"])

    def test_no_arbitrary_reader_or_mutated_caller_receipt(self):
        with self.assertRaises(ValueError): owner.OwnerPRVerifier(self.data["enrollment"], object())
        verifier, backend = make_verifier(self.data); forged = copy.deepcopy(self.data)
        forged["execution"]["destination"]["repository_id"] = 1
        with self.assertRaises(ValueError): verifier.verify(forged, now=NOW)
        self.assertEqual(len(backend.requests), 0)

    def test_each_effect_observes_fresh_history_instead_of_cached_approval(self):
        minted = set(); raw = build_pr_observation(self.data)
        first = owner_exchanges(self.data, raw, minted=minted)
        raw["reviews"][0]["state"] = "DISMISSED"
        second = owner_exchanges(self.data, raw, minted=minted)
        backend = live.ScriptedHTTPS(first + second)
        provider = live.AppTokenProvider(self.data["enrollment"], TestSigner(), backend, clock=lambda: NOW)
        transport = live.PilotGitHub(self.data["enrollment"], provider, backend, clock=lambda: NOW)
        verifier = owner.OwnerPRVerifier(self.data["enrollment"], transport)
        self.assertTrue(verifier.verify(self.data, now=NOW)["mock_only"])
        with self.assertRaises(owner.RevokedApproval): verifier.verify(self.data, now=NOW)
        self.assertEqual(backend.remaining, 0)

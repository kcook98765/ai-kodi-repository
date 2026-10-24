"""In-memory GitHub REST wire model. No listener, sockets, keys or real tokens."""
from __future__ import annotations

import copy
from datetime import timedelta
from urllib.parse import urlsplit, parse_qs

import publication_proposal as frozen
import publication_github_live as live
import publication_pilot_contract as contract
from d3_github_model import GitHubModel


CEILING = {"contents": "write", "pull_requests": "write", "actions": "read", "pages": "read",
           "administration": "read", "metadata": "read"}


class TestSigner:
    def sign_rs256(self, raw):
        return b"local-test-signature-never-valid-on-github"


def pilot_policy(enrollment):
    return live.expected_policy(enrollment)


class PilotGitHubModel(GitHubModel):
    """Exercises serialized GitHub-shaped HTTP, without network authority."""
    def __init__(self, data, *, now):
        self.now = now; self.comments = {}; self.run_id = 8200; self.deploy_failed = False; self.runs = {}
        super().__init__(data, {}, {})
        import publication_d3_contract as source_fixture
        previous = None
        for version, identity in self.e["fixture_source"]["commits"].items():
            self.seed_commit(identity, {"fixtures/addon/" + n: raw for n, raw in source_fixture.fixture_files(version).items()})
            self.commits[identity]["parents"] = [] if previous is None else [{"sha": previous}]
            previous = identity
        self.refs["heads/d3-fixture-source"] = previous
        self.token_requests = []

    def bind(self, data, owner_raw=None, pages_raw=None):
        self.data = data; self.e = data["enrollment"]
        self.owner_raw = {}; self.pages_raw = {}
        self.policy = pilot_policy(self.e)

    def response(self, status, value=None, raw=None, headers=None):
        return live.HTTPResponse(status, frozen.canonical(value) if raw is None else raw, headers or {})

    def send(self, method, url, headers, raw, *, max_size):
        parsed = urlsplit(url)
        if parsed.path == "/app" or parsed.path.startswith("/app/installations/"):
            self.calls.append({"method": method, "path": parsed.path, "authenticated": "Authorization" in headers})
            owner = {"id": self.e["owner_id"], "type": "Organization"}
            if parsed.path == "/app":
                return self.response(200, {"id": self.e["app_id"], "owner": owner, "permissions": CEILING})
            if method == "GET":
                return self.response(200, {"id": self.e["app_installation_id"], "app_id": self.e["app_id"],
                    "repository_selection": "selected", "suspended_at": None, "account": owner, "permissions": CEILING})
            body = frozen.strict_load(raw); self.token_requests.append(copy.deepcopy(body))
            assert body["repository_ids"] == [self.e["repository_id"]]
            return self.response(201, {"token": "test_token_never_valid_on_github", "permissions": body["permissions"],
                "expires_at": frozen.utc(self.now + timedelta(hours=1)), "repository_selection": "selected",
                "repositories": [{"id": self.e["repository_id"], "full_name": self.e["repository"]}]})
        # Base model handles create-only immutable Release/Git objects and public paths.
        if method != "PUT":
            return super().send(method, url, headers, raw)
        prefix = "/repos/" + self.e["repository"]; assert parsed.path.startswith(prefix)
        path = parsed.path.removeprefix(prefix)
        self.calls.append({"method": method, "host": parsed.hostname, "path": path,
                           "authenticated": "Authorization" in headers, "body_sha256": frozen.sha(raw)})
        if self.fail_before == (method, path): return self.response(500, {})
        result = self.write(method, path, parse_qs(parsed.query), frozen.strict_load(raw))
        self.mutations.append({"method": method, "path": path, "sha256": frozen.sha(raw)})
        if self.after_effect: self.after_effect(self, method, path)
        if self.loss_after == (method, path):
            self.loss_after = None; raise TimeoutError("local simulated lost response")
        return result

    def get(self, path, query, headers):
        if path == "":
            return self.response(200, {"id": self.e["repository_id"], "full_name": self.e["repository"], "private": False,
                "owner": {"id": self.e["owner_id"], "type": "Organization", "login": self.e["repository"].split("/")[0]},
                **self.policy["repository"]})
        if path == "/actions/permissions/workflow": return self.response(200, self.policy["default_actions"])
        if path == "/immutable-releases": return self.response(200, self.policy["immutable_releases"])
        if path.startswith("/contents/"):
            import base64
            name = self.e["validation_workflow_path"]
            raw = frozen.safe_read(self.data["root"] / self.data["payload"]["main_base"]["files"][name]["path"])
            return self.response(200, {"type": "file", "path": name, "encoding": "base64", "content": base64.b64encode(raw).decode(),
                                       "sha": frozen.git_object("blob", raw)})
        if path.startswith("/issues/") and path.endswith("/comments"):
            return self.response(200, self.comments.get(int(path.split("/")[2]), []))
        if path.startswith("/actions/workflows/") and not path.endswith("/runs"):
            identity = int(path.rsplit("/", 1)[1])
            return self.response(200, {"id": identity, "state": "active", "path":
                "dynamic/pages/pages-build-deployment" if identity == self.e["pages_workflow_id"] else self.e["validation_workflow_path"]})
        if path.startswith("/actions/workflows/") and path.endswith("/runs"):
            commit = query.get("head_sha", [self.refs["heads/gh-pages"]])[0]
            identity = int(path.split("/")[3]); validation = identity == self.e["validation_workflow_id"]
            run = self.deploy_run(commit, validation=validation)
            self.runs[run["id"]] = run
            return self.response(200, {"total_count": 1, "workflow_runs": [run]})
        if path.startswith("/actions/runs/"):
            identity = int(path.split("/")[3]); run = self.runs[identity]
            if path.endswith("/jobs"):
                validation = run["workflow_id"] == self.e["validation_workflow_id"]
                return self.response(200, {"total_count": 1, "jobs": [{"id": 8300 + int(validation), "run_id": identity,
                    "head_sha": run["head_sha"], "name": self.e["validation_job_name"] if validation else "deploy",
                    "status": "completed", "conclusion": run["conclusion"], "environment": {"name": "github-pages"}}]})
            return self.response(200, run)
        if path.startswith("/environments/") and path.endswith("deployment-branch-policies"):
            return self.response(200, {"total_count": len(self.policy["pages_branch_policies"]), "branch_policies": self.policy["pages_branch_policies"]})
        return super().get(path, query, headers)

    def deploy_run(self, commit, *, validation=False):
        return {"id": self.run_id + int(validation), "workflow_id": self.e["validation_workflow_id"] if validation else self.e["pages_workflow_id"],
            "head_sha": commit, "head_branch": "gh-pages", "event": "push", "status": "completed",
            "conclusion": "failure" if self.deploy_failed and not validation else "success", "run_attempt": 1,
            "path": self.e["validation_workflow_path"] if validation else "dynamic/pages/pages-build-deployment", "repository": {"id": self.e["repository_id"], "full_name": self.e["repository"]}}

    def write(self, method, path, query, body):
        if path == "/pulls":
            response = super().write(method, path, query, body)
            number = len(self.pulls); pr = self.pulls[number]
            repo = {"id": self.e["repository_id"], "full_name": self.e["repository"],
                    "owner": {"id": self.e["owner_id"], "type": "Organization"}}
            pr["head"]["repo"] = copy.deepcopy(repo); pr["base"]["repo"] = copy.deepcopy(repo)
            pr.update(id=7400 + number, node_id="PR_local_test_" + str(number),
                html_url="https://github.com/" + self.e["repository"] + "/pull/" + str(number),
                title=body["title"], body=body["body"], draft=False, mergeable=True, mergeable_state="clean",
                user={"id": self.e["bot_user_id"], "login": self.e["bot_login"], "type": "Bot"})
            return self.response(201, pr)
        if method == "PATCH" and path.startswith("/pulls/"):
            number = int(path.split("/")[2]); pr = self.pulls[number]
            assert pr["state"] == "open"; pr.update(body)
            return self.response(200, pr)
        if method == "PUT" and path.endswith("/merge"):
            number = int(path.split("/")[2]); pr = self.pulls[number]
            assert body == {"sha": pr["head"]["sha"], "merge_method": "merge"}
            assert pr["state"] == "open" and pr["base"]["sha"] == self.refs["heads/main"]
            # GitHub protection supplies the final independent checks enforcement.
            reviews = self.reviews.get(number, [])
            assert reviews and reviews[-1]["state"] == "APPROVED" and reviews[-1]["commit_id"] == pr["head"]["sha"]
            head = pr["head"]["sha"]; parent = self.refs["heads/main"]
            tree = self.commits[head]["tree"]["sha"]
            bodyraw = (f"tree {tree}\nparent {parent}\nparent {head}\nauthor Pilot <pilot@example.invalid> 0 +0000\n"
                       "committer Pilot <pilot@example.invalid> 0 +0000\n\nReviewed pilot normal merge\n").encode()
            merge = frozen.git_object("commit", bodyraw)
            self.commits[merge] = {"sha": merge, "tree": {"sha": tree}, "parents": [{"sha": parent}, {"sha": head}]}
            self.refs["heads/main"] = merge; pr.update(state="closed", merged=True, merge_commit_sha=merge)
            return self.response(200, {"merged": True, "sha": merge, "message": "Pull Request successfully merged"})
        return super().write(method, path, query, body)

    def approve(self, data, *, review_id=7600):
        number = data["execution"]["pr"]["number"]
        self.reviews.setdefault(number, []).append({"id": review_id, "state": "APPROVED", "commit_id": data["execution"]["pr"]["head_sha"],
            "body": contract.approval_text(data), "submitted_at": frozen.utc(self.now),
            "user": {"id": self.e["human_owner_id"], "login": "kcook98765", "type": "User"}, "author_association": "OWNER"})

    def revoke(self, data):
        number = data["execution"]["pr"]["number"]
        self.comments.setdefault(number, []).append({"id": 7700, "body": "REVOKE " + data["digest"] + " " + data["execution"]["nonce"],
            "created_at": frozen.utc(self.now), "updated_at": frozen.utc(self.now),
            "user": {"id": self.e["human_owner_id"], "type": "User"}})

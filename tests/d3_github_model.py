"""Stateful API fixture used only by local tests; no sockets or credentials.

The production module has no pluggable sender. Tests patch the concrete mock's
send method to this local protocol model to cross request/response serialization.
"""
import base64
import copy
from urllib.parse import urlsplit, parse_qs

import publication_proposal as frozen
import publication_d3_contract as contract
import publication_github as github


class GitHubModel:
    def __init__(self, data, owner_raw, pages_raw):
        self.calls = []; self.mutations = []; self.loss_after = None; self.fail_before = None
        self.pages_failed = False; self.after_effect = None
        self.blobs = {}; self.trees = {}; self.commits = {}; self.refs = {}
        self.releases = {}; self.asset_bytes = {}; self.pulls = {}; self.reviews = {}
        self.published_files = {}; self.pages_build = {}
        self.bind(data, owner_raw, pages_raw)
        p = data["payload"]
        main_files = {n: frozen.safe_read(data["root"] / item["path"]) for n, item in p["main_base"]["files"].items()}
        self.seed_commit(p["expected"]["main_sha"], main_files)
        self.seed_commit(p["expected"]["pages_sha"], {})
        self.refs = {"heads/main": p["expected"]["main_sha"], "heads/gh-pages": p["expected"]["pages_sha"]}

    def bind(self, data, owner_raw, pages_raw):
        self.data = data; self.e = data["enrollment"]
        self.owner_raw = owner_raw; self.pages_raw = pages_raw
        self.policy = contract.mock_policy(self.e)

    def seed_commit(self, sha, files):
        blob_map = {}
        for name, raw in files.items():
            digest = frozen.git_object("blob", raw); self.blobs[digest] = raw; blob_map[name] = digest
        tree = contract.tree(files); self.trees[tree] = blob_map
        self.commits[sha] = {"sha": sha, "tree": {"sha": tree}, "parents": []}

    def response(self, status, value=None, raw=None, headers=None):
        return github.MockResponse(status, frozen.canonical(value) if raw is None else raw, headers or {})

    def owner_merge(self):
        number, pr = next(reversed(self.pulls.items()))
        head = pr["head"]["sha"]; parent = self.refs["heads/main"]
        tree = self.commits[head]["tree"]["sha"]
        body = (f"tree {tree}\nparent {parent}\nparent {head}\nauthor Owner <owner@example.invalid> 0 +0000\n"
                "committer Owner <owner@example.invalid> 0 +0000\n\nReviewed D3 ledger merge\n").encode()
        merge = frozen.git_object("commit", body)
        self.commits[merge] = {"sha": merge, "tree": {"sha": tree}, "parents": [{"sha": parent}, {"sha": head}]}
        pr.update(merged=True, state="closed", merge_commit_sha=merge)
        self.refs["heads/main"] = merge
        self.reviews[number] = [{"id": 1, "state": "APPROVED", "commit_id": head,
                                 "user": {"id": self.e["human_owner_id"], "type": "User"}}]
        return merge

    def send(self, method, url, headers, raw):
        parsed = urlsplit(url); prefix = "/repos/" + self.e["repository"]
        path = parsed.path.removeprefix(prefix); query = parse_qs(parsed.query)
        self.calls.append({"method": method, "host": parsed.hostname, "path": path,
                           "authenticated": "Authorization" in headers, "body_sha256": frozen.sha(raw)})
        if self.fail_before == (method, path): return self.response(500, {"message": "PRIVATE-TOKEN-DO-NOT-LOG"})
        if parsed.hostname == "kcook98765-kodi-qualification.github.io":
            public_path = parsed.path.removeprefix(urlsplit(self.e["base_url"]).path)
            public_path = public_path or "index.html"
            data = self.published_files.get(public_path or "index.html")
            if data is None: return self.response(404, {})
            mime = "application/zip" if public_path.endswith(".zip") else "text/html" if public_path.endswith(".html") else "application/octet-stream"
            return self.response(200, raw=data if method == "GET" else b"", headers={"Content-Type": mime, "Content-Length": str(len(data))})
        assert parsed.hostname in {"api.github.com", "uploads.github.com"}, url
        assert parsed.path.startswith(prefix), url
        if method == "GET": return self.get(path, query, headers)
        assert method in {"POST", "PATCH"}, method
        body = raw if parsed.hostname == "uploads.github.com" else frozen.strict_load(raw)
        result = self.write(method, path, query, body)
        self.mutations.append({"method": method, "path": path, "sha256": frozen.sha(raw)})
        if self.after_effect: self.after_effect(self, method, path)
        if self.loss_after == (method, path):
            self.loss_after = None
            raise TimeoutError("PRIVATE-TOKEN-LOST-RESPONSE")
        return result

    def get(self, path, query, headers):
        e = self.e
        if path == "": return self.response(200, {"id": e["repository_id"], "full_name": e["repository"], "private": False,
            "owner": {"id": e["owner_id"], "type": "Organization", "login": e["repository"].split("/")[0]}})
        if path == "/pages": return self.response(200, {"html_url": e["base_url"], "https_enforced": True,
            "build_type": "legacy", "source": {"branch": "gh-pages", "path": "/"}, "status": "built"})
        if path == "/pages/builds/latest":
            return self.response(200, dict(self.pages_build, status="errored" if self.pages_failed else "built"))
        if path.startswith("/git/ref/"):
            ref = path.removeprefix("/git/ref/"); sha = self.refs.get(ref)
            return self.response(404, {}) if sha is None else self.response(200, {"ref": "refs/" + ref,
                "object": {"type": "commit", "sha": sha, "url": "api-metadata"}})
        if path.startswith("/git/commits/"):
            value = self.commits.get(path.rsplit("/", 1)[1])
            return self.response(200, value) if value else self.response(404, {})
        if path.startswith("/git/trees/"):
            sha = path.rsplit("/", 1)[1]
            if sha not in self.trees: return self.response(404, {})
            return self.response(200, {"sha": sha, "truncated": False, "tree": [
                {"path": n, "mode": "100644", "type": "blob", "sha": checksum} for n, checksum in sorted(self.trees[sha].items())]})
        if path.startswith("/git/blobs/"):
            sha = path.rsplit("/", 1)[1]
            if sha not in self.blobs: return self.response(404, {})
            raw = self.blobs[sha]
            return self.response(200, {"sha": sha, "size": len(raw), "encoding": "base64", "content": base64.b64encode(raw).decode()})
        if path == "/releases": return self.response(200, list(self.releases.values()))
        if path.startswith("/releases/tags/"):
            value = next((r for r in self.releases.values() if r["tag_name"] == path.rsplit("/", 1)[1]), None)
            return self.response(200, value) if value else self.response(404, {})
        if path.startswith("/releases/assets/"):
            identity = int(path.rsplit("/", 1)[1]); raw = self.asset_bytes[identity]
            if headers["Accept"] == "application/octet-stream": return self.response(200, raw=raw)
            asset = next(a for r in self.releases.values() for a in r["assets"] if a["id"] == identity)
            return self.response(200, asset)
        if path.startswith("/releases/"):
            parts = path.strip("/").split("/"); release = self.releases[int(parts[1])]
            return self.response(200, release["assets"] if len(parts) == 3 else release)
        if path == "/rulesets": return self.response(200, [{"id": r["id"]} for r in self.policy["rulesets"]])
        if path.startswith("/rulesets/"): return self.response(200, next(r for r in self.policy["rulesets"] if r["id"] == int(path.rsplit("/", 1)[1])))
        if path.startswith("/environments/"):
            name = path.split("/")[2]
            if path.endswith("deployment-branch-policies"):
                values = self.owner_raw["environment_branches"] if name == "kodi-d3-publication" else self.pages_raw["environment_branches"]
                return self.response(200, {"total_count": len(values), "branch_policies": values})
            return self.response(200, self.policy["environments"][name])
        if path.startswith("/actions/") or path.startswith("/contents/") or path.startswith("/issues/"):
            return self.proof_get(path, query)
        if path == "/pulls":
            wanted = query["head"][0].split(":", 1)[1]
            return self.response(200, [p for p in self.pulls.values() if p["head"]["ref"] == wanted])
        if path.startswith("/pulls/"):
            number = int(path.split("/")[2])
            return self.response(200, self.reviews.get(number, []) if path.endswith("/reviews") else self.pulls[number])
        raise AssertionError(("Unsupported GET fixture", path, query))

    def proof_get(self, path, query):
        if path.startswith("/contents/"): return self.response(200, self.owner_raw["workflow_file"])
        if path.startswith("/issues/"):
            return self.response(200, self.owner_raw["revocation_comments"] if path.endswith("/comments") else self.owner_raw["control_issue"])
        if path.startswith("/actions/workflows/"):
            number = int(path.rsplit("/", 1)[1])
            raw = self.owner_raw if number == self.e["workflow_id"] else self.pages_raw
            return self.response(200, raw["workflow"])
        if path.startswith("/actions/artifacts/"): return self.response(200, raw=self.owner_raw["artifact_archive"])
        if path.startswith("/actions/runs/"):
            number = int(path.split("/")[3]); raw = self.owner_raw if number == self.owner_raw["run"]["id"] else self.pages_raw
            if path.endswith("/approvals"): return self.response(200, raw["review_history"])
            if path.endswith("/jobs"): return self.response(200, {"total_count": len(raw["jobs"]), "jobs": raw["jobs"]})
            if path.endswith("/artifacts"): return self.response(200, {"total_count": 1, "artifacts": [raw["artifact_metadata"]]})
            return self.response(200, raw["run"])
        raise AssertionError(("Unsupported proof fixture", path, query))

    def write(self, method, path, query, body):
        if path == "/git/refs":
            ref = body["ref"].removeprefix("refs/")
            assert ref not in self.refs, "create-only ref"
            self.refs[ref] = body["sha"]
            return self.response(201, {"ref": body["ref"], "object": {"type": "commit", "sha": body["sha"], "url": "metadata"}})
        if path == "/releases":
            assert not any(r["tag_name"] == body["tag_name"] for r in self.releases.values())
            identity = len(self.releases) + 1
            value = {"id": identity, "tag_name": body["tag_name"], "draft": True, "immutable": False,
                     "name": body["name"], "body": body["body"], "assets": []}
            self.releases[identity] = value
            return self.response(201, value)
        if path.startswith("/releases/") and path.endswith("/assets"):
            release = self.releases[int(path.split("/")[2])]; name = query["name"][0]
            assert release["draft"] and not any(a["name"] == name for a in release["assets"])
            identity = len(self.asset_bytes) + 100
            value = {"id": identity, "name": name, "state": "uploaded", "size": len(body), "digest": "sha256:" + frozen.sha(body)}
            self.asset_bytes[identity] = body; release["assets"].append(value)
            return self.response(201, value)
        if path.startswith("/releases/") and method == "PATCH":
            release = self.releases[int(path.rsplit("/", 1)[1])]
            assert release["draft"] and body == {"draft": False}
            release.update(draft=False, immutable=True)
            return self.response(200, release)
        if path == "/git/blobs":
            data = base64.b64decode(body["content"], validate=True); sha = frozen.git_object("blob", data)
            self.blobs[sha] = data
            return self.response(201, {"sha": sha})
        if path == "/git/trees":
            files = dict(self.trees[body["base_tree"]]) if "base_tree" in body else {}
            files.update({item["path"]: item["sha"] for item in body["tree"]})
            sha = contract.tree({name: self.blobs[digest] for name, digest in files.items()})
            self.trees[sha] = files
            return self.response(201, {"sha": sha, "truncated": False})
        if path == "/git/commits":
            assert len(body["parents"]) == 1
            sha = frozen.git_commit(body["tree"], body["parents"][0], body["message"].removesuffix("\n"))
            value = {"sha": sha, "tree": {"sha": body["tree"]}, "parents": [{"sha": p} for p in body["parents"]]}
            self.commits[sha] = value
            return self.response(201, value)
        if path == "/git/refs/heads/gh-pages":
            value = self.commits[body["sha"]]
            assert body["force"] is False and value["parents"] == [{"sha": self.refs["heads/gh-pages"]}], "non-fastforward refused"
            self.refs["heads/gh-pages"] = value["sha"]
            self.published_files = {n: self.blobs[h] for n, h in self.trees[value["tree"]["sha"]].items()}
            self.pages_build = {"commit": value["sha"], "status": "built"}
            return self.response(200, {"ref": "refs/heads/gh-pages", "object": {"sha": value["sha"], "type": "commit"}})
        if path == "/pulls":
            identity = len(self.pulls) + 1; repo = {"id": self.e["repository_id"]}
            value = {"number": identity, "state": "open", "merged": False,
                     "head": {"ref": body["head"], "sha": self.refs["heads/" + body["head"]], "repo": repo},
                     "base": {"ref": "main", "sha": self.refs["heads/main"], "repo": repo}}
            self.pulls[identity] = value
            return self.response(201, value)
        raise AssertionError(("Unsupported write fixture", method, path))

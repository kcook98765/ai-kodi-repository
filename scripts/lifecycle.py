#!/usr/bin/env python3
"""Task-bound public GitHub intake and local preparation. Never executes source.

Enrollment/installation are operator operations, deliberately absent from role tools.
No credentials, Git subprocess, remote writes, production build or native controls.
"""
from __future__ import annotations

import argparse
import copy
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import fcntl
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener
import uuid
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
import approval_contract
import audit_candidate
import check_publication
import repository as repo
import lifecycle_lanes

ROOT = Path(__file__).resolve().parents[1]
LANES = {"matrix": "19.5", "nexus": "20.5", "omega": "21.3", "piers": "22 preview"}
ROLES = {
    "inspect": {"kodi-repo-manager", "kodi-addon-tester", "kodi-release-reviewer", "kodi-addon-developer"},
    "github": {"kodi-repo-manager"},
    "build": {"kodi-repo-manager"},
    "validate": {"kodi-addon-tester"},
    "qualify": {"kodi-repo-manager", "kodi-addon-tester"},
    "review": {"kodi-repo-manager", "kodi-release-reviewer"},
}
SHA = re.compile(r"[0-9a-f]{40}\Z")
DIGEST = re.compile(r"[0-9a-f]{64}\Z")
TASK = re.compile(r"[0-9a-f]{32}\Z")
REPOSITORY = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9_.-]{1,100}\Z")


def require(condition, message):
    repo.require(condition, message)


def closed(value, required, optional=()):
    require(isinstance(value, dict) and set(required) <= set(value)
            and set(value) <= set(required) | set(optional), "Malformed/unknown task fields")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def git_blob(data):
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def repository_name(name):
    require(isinstance(name, str) and REPOSITORY.fullmatch(name)
            and name.split("/")[1] not in (".", "..")
            and not name.endswith(".git"), "Expected GitHub owner/repository")
    return name


def plain_ref(kind, value):
    require(kind in ("branch", "tag", "commit"), "Unknown ref kind")
    require(isinstance(value, str) and 0 < len(value) <= 200, "Invalid ref")
    if kind == "commit":
        require(SHA.fullmatch(value), "Commit must be a full lowercase SHA")
    else:
        require(not any(ord(c) < 33 or c in "~^:?*[\\" for c in value)
                and ".." not in value and "@{" not in value
                and all(p and not p.startswith(".") and not p.endswith((".lock", "."))
                        for p in value.split("/")), "Unsafe Git ref")


def path_at(base, relative, exists=True):
    """Reject linked ancestors, traversal, special files and noncanonical names."""
    for p in [base, *base.parents]:
        require(not p.is_symlink(), "Linked workspace ancestor")
    p = repo.safe_path(base, relative, exists=exists)
    if exists:
        require(stat.S_ISREG(p.lstat().st_mode), "Nonregular input")
    return p


def read_json(path, limit=2_000_000):
    require(path.is_file() and not path.is_symlink() and path.stat().st_size <= limit,
            "Missing/oversized/linked JSON input")
    return json.loads(path.read_bytes())


def toolchain(root):
    return {name: sha(path_at(root, name).read_bytes()) for name in (
        "scripts/lifecycle.py", "scripts/lifecycle_adapter.py", "scripts/repository.py",
        "scripts/audit_candidate.py", "scripts/approval_contract.py", "scripts/check_publication.py", "scripts/qualify.py",
        "scripts/opencode/kodi.ts", "scripts/opencode/fixture_adapter.py", "scripts/opencode/profiles.json",
        "scripts/lifecycle_lanes.py", "scripts/lifecycle_feed.py", "config/LIFECYCLE-LANES.json",
        "config/LIFECYCLE-TASK-SCHEMA.json", "docs/REVIEW-RECORD-EXAMPLE.json",
        "scripts/lifecycle_publication.py", "scripts/publication_proposal.py",
        "scripts/publication_verify.py", "scripts/publication_operator.py", "scripts/publication_fake.py",
        "docs/PUBLICATION-PROPOSAL-SCHEMA.json", "scripts/lifecycle_pilot.py", "scripts/publication_cli.py",
        "scripts/publication_github_live.py", "scripts/publication_pilot.py", "scripts/publication_pilot_contract.py",
        "scripts/publication_pr_owner.py", "scripts/publication_pilot_candidate.py", "scripts/opencode/pilot-profiles.json")}


def toolkit_identity(installed):
    """Fingerprint trusted installed tooling; never runs from acquired source cwd."""
    toolkit = Path(installed["toolkit"])
    source = toolkit / "src/kodi_agent_toolkit"
    hashes = {f.name: sha(path_at(source, f.name).read_bytes()) for f in sorted(source.glob("*.py"))}
    require(hashes and "validate.py" in hashes, "Trusted Toolkit source unavailable")
    code = ("import importlib.metadata as m,json,sys,zlib; "
            "print(json.dumps({'python':sys.version,'zlib':zlib.ZLIB_RUNTIME_VERSION,'packages':"
            "{n:{'version':m.version(n),'record':m.distribution(n).read_text('RECORD')} "
            "for n in ['kodi-agent-toolkit','Kodistubs','mypy','kodi-addon-checker']}}))")
    result = subprocess.run([installed["python"], "-I", "-B", "-c", code], cwd=toolkit,
                            env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"},
                            capture_output=True, text=True, timeout=20)
    require(result.returncode == 0 and len(result.stdout) < 2_000_000, "Cannot fingerprint trusted validation environment")
    environment = json.loads(result.stdout)
    for package in environment["packages"].values():
        package["record_sha256"] = sha((package.pop("record") or "").encode())
    return {"source_files": hashes, "environment": environment,
            "interpreter_sha256": sha(Path(installed["python"]).resolve(strict=True).read_bytes()),
            "cache_manifest_sha256": sha(path_at(Path(installed["cache"]), "manifest.json").read_bytes())}


def check_state(directory, state):
    common = {"generation", "stage", "validations"}
    if 'feed_sha256' in state:
        require(state.get('stage') == 'prepared', 'Feed receipt requires prepared state')
        common.add('feed_sha256')
    stages = {"enrolled": set(), "acquired": {"archive_sha256", "source_manifest_sha256"},
              "prepared": {"archive_sha256", "source_manifest_sha256", "selection", "preparation_sha256"}}
    require(state.get("stage") in stages and type(state.get("generation")) is int
            and state["generation"] >= 0, "Malformed task stage/generation")
    fields = common | stages[state["stage"]]
    if state["generation"]:
        fields.add("previous_state_sha256")
    closed(state, fields)
    for key in fields & {"archive_sha256", "source_manifest_sha256", "preparation_sha256", "previous_state_sha256", "feed_sha256"}:
        require(isinstance(state[key], str) and DIGEST.fullmatch(state[key]), "Malformed state digest")
    require(isinstance(state["validations"], dict)
            and all(k in LANES and isinstance(v, str) and DIGEST.fullmatch(v)
                    for k, v in state["validations"].items()), "Malformed validation receipts")
    require(read_json(path_at(directory, f"transition-{state['generation']}.json")) == state,
            "State does not match committed transition")
    if state["generation"]:
        previous = path_at(directory, f"transition-{state['generation'] - 1}.json").read_bytes()
        require(sha(previous) == state["previous_state_sha256"], "Transition predecessor changed")


def write_new(path, data):
    """Outputs are immutable; an identical retry is safe."""
    path_at(path.parent, path.name, exists=False)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as stream:
            stream.write(data)
    except FileExistsError:
        require(path.read_bytes() == data, "Immutable output differs")


def replace_json(path, value):
    path_at(path.parent, path.name, exists=False)
    tmp = path.with_name(path.name + "." + uuid.uuid4().hex)
    try:
        with tmp.open("xb") as stream:
            stream.write(repo.json_bytes(value))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


class Redirects(HTTPRedirectHandler):
    def __init__(self, repository=None, commit=None):
        self.repository = repository
        self.commit = commit

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        target = urlsplit(newurl)
        allowed = (self.repository is not None and self.commit is not None
                   and target.scheme == "https" and target.netloc == "codeload.github.com"
                   and target.path.casefold() == f"/{self.repository}/legacy.zip/{self.commit}".casefold()
                   and not target.query and not target.fragment)
        require(allowed, "Unapproved GitHub redirect")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class GitHub:
    """Anonymous fixed-origin GET transport: never inherits gh, HOME or tokens."""
    def _get(self, endpoint, limit=2_000_000, archive=None):
        require(endpoint.startswith("repos/") and not any(c in endpoint for c in "\r\n#"),
                "Invalid fixed endpoint")
        url = "https://api.github.com/" + endpoint
        opener = build_opener(ProxyHandler({}), Redirects(*(archive or (None, None))))
        try:
            with opener.open(Request(url, method="GET", headers={
                    "User-Agent": "ai-kodi-repository-local-intake",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28"}), timeout=25) as response:
                require(response.status == 200, "GitHub GET did not succeed")
                data = response.read(limit + 1)
                require(len(data) <= limit, "GitHub response exceeds limit")
                return data, dict(response.headers)
        except (HTTPError, URLError, TimeoutError) as error:
            code = getattr(error, "code", None)
            raise ValueError(f"BLOCKED: GitHub GET unavailable ({code or type(error).__name__}); no credential fallback") from None

    def json(self, endpoint):
        return json.loads(self._get(endpoint)[0])

    def resolve(self, name, kind, ref, expected_id=None, expected_commit=None):
        repository_name(name)
        plain_ref(kind, ref)
        metadata = self.json("repos/" + name)
        require(metadata.get("full_name", "").casefold() == name.casefold()
                and type(metadata.get("id")) is int and metadata["id"] > 0
                and metadata.get("private") is False, "Repository identity/private access mismatch")
        require(expected_id is None or metadata["id"] == expected_id, "Repository ID changed")
        name = metadata["full_name"]
        repository_name(name)
        commit = ref
        if kind != "commit":
            result = self.json(f"repos/{name}/git/ref/" + ("heads/" if kind == "branch" else "tags/") + quote(ref, safe="/"))
            require(result.get("ref") == ("refs/heads/" if kind == "branch" else "refs/tags/") + ref,
                    "Resolved ref identity mismatch")
            obj = result["object"]
            for _ in range(8):
                require(SHA.fullmatch(obj.get("sha", "")), "Malformed ref object")
                if obj.get("type") == "commit":
                    break
                require(kind == "tag" and obj.get("type") == "tag", "Ref is not a commit/tag")
                obj = self.json(f"repos/{name}/git/tags/{obj['sha']}")["object"]
            require(obj.get("type") == "commit", "Annotated tag chain too deep")
            commit = obj["sha"]
        require(SHA.fullmatch(commit), "Malformed commit")
        resolved = self.json(f"repos/{name}/commits/{commit}")
        require(resolved.get("sha") == commit, "Commit identity mismatch")
        require(expected_commit is None or commit == expected_commit, "Ref moved from expected commit")
        tree = resolved["commit"]["tree"]["sha"]
        require(SHA.fullmatch(tree), "Malformed source tree")
        return {"repository": name, "repository_id": metadata["id"], "ref_kind": kind,
                "requested_ref": ref, "commit": commit, "tree": tree}

    def source(self, source):
        name, commit = source["repository"], source["commit"]
        current = self.resolve(name, "commit", commit, source["repository_id"], commit)
        require(current["tree"] == source["tree"], "Source tree changed")
        tree = self.json(f"repos/{name}/git/trees/{source['tree']}?recursive=1")
        require(tree.get("sha") == source["tree"] and tree.get("truncated") is False,
                "Truncated or mismatched Git tree")
        entries = tree.get("tree")
        require(isinstance(entries, list) and len(entries) <= repo.MAX_ENTRIES, "Source tree exceeds bounds")
        blobs = {}
        for item in entries:
            path_at(ROOT, item["path"], exists=False)
            if item.get("type") == "tree":
                require(item.get("mode") == "040000", "Malformed Git directory")
                continue
            require(item.get("type") == "blob" and item.get("mode") in ("100644", "100755")
                    and SHA.fullmatch(item.get("sha", "")), "Symlink/submodule/special Git object unsupported")
            require(item["path"] not in blobs, "Duplicate Git tree path")
            blobs[item["path"]] = item["sha"]
        repo.inventory_paths(blobs)
        data, _ = self._get(f"repos/{name}/zipball/{commit}", repo.MAX_ZIP_BYTES, (name, commit))
        return data, blobs

    def listing(self, name, resource, page=1):
        repository_name(name)
        require(resource in ("issues", "pulls", "releases") and type(page) is int and 1 <= page <= 5,
                "Unknown resource/page")
        data, headers = self._get(f"repos/{name}/{resource}?per_page=20&page={page}")
        values = json.loads(data)
        require(isinstance(values, list) and len(values) <= 20, "Malformed listing")
        keys = ("number", "title", "state", "tag_name", "name", "html_url", "draft",
                "prerelease", "published_at", "updated_at")
        rows = []
        for value in values:
            if resource == "issues" and "pull_request" in value:
                continue
            row = {k: value[k] for k in keys if k in value}
            if resource == "pulls":
                row.update(head_sha=value["head"]["sha"], base_sha=value["base"]["sha"])
            rows.append(row)
        return {"status": "PASS", "method": "GET", "repository": name, "resource": resource,
                "page": page, "per_page": 20, "items": rows, "exhaustive": False,
                "has_next_page": 'rel="next"' in headers.get("Link", ""),
                "fetched_at": datetime.now(timezone.utc).isoformat()}


def archive_source(data, expected):
    """Verify Git blob identities before materializing any archive member."""
    require(len(data) <= repo.MAX_ZIP_BYTES, "Source archive too large")
    files = {}
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        entries = archive.infolist()
        require(0 < len(entries) <= repo.MAX_ENTRIES
                and sum(i.file_size for i in entries) <= repo.MAX_RUNTIME_BYTES,
                "Source archive resource limits")
        names = [i.filename.rstrip("/") for i in entries]
        require(len(names) == len({n.casefold() for n in names}), "Duplicate/case-colliding source entries")
        for name in names:
            path_at(ROOT, name, exists=False)
        repo.inventory_paths([i.filename for i in entries if not i.is_dir()])
        roots = set()
        for item in entries:
            require(not item.flag_bits & 1 and not stat.S_ISLNK(item.external_attr >> 16), "Linked/encrypted source")
            parts = item.filename.rstrip("/").split("/")
            roots.add(parts[0])
            mode = stat.S_IFMT(item.external_attr >> 16)
            require(mode in (0, stat.S_IFREG, stat.S_IFDIR), "Special source member")
            if item.is_dir():
                continue
            require(mode in (0, stat.S_IFREG) and len(parts) >= 2, "Malformed source member")
            name = "/".join(parts[1:])
            blob = archive.read(item)
            require(name in expected and git_blob(blob) == expected[name], "Source differs from pinned Git tree")
            require(not blob.startswith(b"version https://git-lfs.github.com/spec/v1")
                    and name.split("/")[-1] != ".gitmodules", "LFS/submodules require separate reviewed support")
            files[name] = blob
        require(len(roots) == 1 and set(files) == set(expected) and archive.testzip() is None,
                "Missing/extra source files or archive root")
    return files


def installation(root=ROOT):
    path = path_at(root, ".opencode/lifecycle-installation.json")
    value = read_json(path)
    closed(value, {"schema", "project_root", "toolkit", "python", "cache", "plugin_module", "shared", "adapter_version", "toolkit_identity"}, {'lane_environments'})
    require(value["schema"] == 1 and value["project_root"] == str(root), "Installation root mismatch")
    require(value["adapter_version"] == 1, "Adapter installation version mismatch")
    lifecycle_lanes.registry(value)
    return value


class Store:
    def __init__(self, root=ROOT, github=None):
        self.root = root
        self.github = github or GitHub()
        self.control = root / ".opencode/lifecycle"
        self.outputs = root / ".opencode/lifecycle-data"

    def baseline(self):
        return {p: sha(path_at(self.root, p).read_bytes()) for p in
                ("config/repository.json", "config/production.json", "releases/manifest.json")}

    def enroll(self, request):
        closed(request, {"schema", "owner_authorization", "repository", "repository_id", "ref_kind", "ref", "lanes"},
               {"expected_commit", "candidate_base_url", "feed_members"})
        require(type(request["schema"]) is int and request["schema"] == 1, "Unknown task schema")
        require(isinstance(request["owner_authorization"], str)
                and 0 < len(request["owner_authorization"].strip()) <= 2000, "Missing owner task authorization")
        require(type(request["repository_id"]) is int and request["repository_id"] > 0, "Invalid repository ID")
        lanes = request["lanes"]
        require(isinstance(lanes, list) and lanes and all(isinstance(x, str) and x in LANES for x in lanes)
                and len(set(lanes)) == len(lanes), "Invalid/duplicate compatibility lanes")
        if "expected_commit" in request:
            require(isinstance(request["expected_commit"], str) and SHA.fullmatch(request["expected_commit"]), "Invalid expected commit")
        source = self.github.resolve(request["repository"], request["ref_kind"], request["ref"],
                                     request["repository_id"], request.get("expected_commit"))
        installed = installation(self.root)
        require(toolkit_identity(installed) == installed["toolkit_identity"], "Trusted Toolkit installation drift")
        lane_environments = lifecycle_lanes.registry(installed)
        for lane in lane_environments:
            lifecycle_lanes.verify(installed, lane, toolkit_identity)
        baseline = self.baseline()
        task = uuid.uuid4().hex
        feed_base = request.get('candidate_base_url', 'https://candidate.invalid/'+task+'/')
        url = urlsplit(feed_base)
        production_url = urlsplit(read_json(self.root/'config/repository.json')['base_url'])
        require(url.scheme == 'https' and url.hostname and not url.username and not url.password
                and not url.query and not url.fragment and url.path.endswith('/') and '%' not in feed_base
                and '..' not in url.path.split('/') and
                (url.hostname.lower().rstrip('.'),url.port or 443) !=
                (production_url.hostname.lower().rstrip('.'),production_url.port or 443), 'Invalid/production candidate endpoint')
        members = request.get('feed_members', [])
        require(isinstance(members, list) and len(members) <= 25, 'Too many candidate feed members')
        seen = set()
        for member in members:
            closed(member, {'task_id','expected_digest'})
            require(member['task_id'] not in seen, 'Duplicate feed member')
            seen.add(member['task_id'])
            self.operate('review','kodi-release-reviewer',member['task_id'],member['expected_digest'],{})
        binding = {"schema": 1, "adapter_version": 1, "task_id": task, "project_root": str(self.root),
                   "owner_authorization": request["owner_authorization"], "source": source,
                   "expires_at": (datetime.now(timezone.utc) + timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                   "toolchain": toolchain(self.root), "stages": ["inspect", "github", "build", "validate", "qualify", "review"],
                   "installation_sha256": sha(path_at(self.root, ".opencode/lifecycle-installation.json").read_bytes()),
                   "toolkit_identity": installed["toolkit_identity"],
                   "lane_environments": lane_environments, "candidate_feed": {'base_url':feed_base, 'members':members},
                   "targets": {k: {"kodi_version": LANES[k], "native_tested": False} for k in lanes},
                   "baseline": baseline, "profile": "candidate", "runtime_authorized": False,
                   "publication_authorized": False, "github_method": "GET"}
        for parent in (self.control, self.outputs):
            path_at(parent.parent, parent.name, exists=False)
            parent.mkdir(parents=True, exist_ok=True)
        directory = self.control / task
        directory.mkdir(mode=0o700)
        (self.outputs / task).mkdir(mode=0o700)
        write_new(directory / "binding.json", repo.json_bytes(binding))
        initial = {"generation": 0, "stage": "enrolled", "validations": {}}
        write_new(directory / "transition-0.json", repo.json_bytes(initial))
        write_new(directory / "state.json", repo.json_bytes(initial))
        return {"task_id": task, "expected_digest": sha(repo.json_bytes(binding)), "binding": binding}

    @contextmanager
    def bound(self, task, digest):
        require(isinstance(task, str) and TASK.fullmatch(task)
                and isinstance(digest, str) and DIGEST.fullmatch(digest), "Malformed task/digest")
        directory = self.control / task
        binding_path = path_at(directory, "binding.json")
        require(sha(binding_path.read_bytes()) == digest, "Task binding digest mismatch")
        binding = read_json(binding_path)
        closed(binding, {"schema", "adapter_version", "task_id", "project_root", "owner_authorization", "source", "expires_at",
                        "toolchain", "installation_sha256", "toolkit_identity", "lane_environments", "candidate_feed", "stages", "targets", "baseline", "profile", "runtime_authorized",
                        "publication_authorized", "github_method"})
        require(binding.get("schema") == 1 and binding.get("task_id") == task
                and binding.get("project_root") == str(self.root)
                and binding.get("profile") == "candidate"
                and binding.get("runtime_authorized") is False
                and binding.get("publication_authorized") is False
                and binding.get("github_method") == "GET", "Task authority mismatch")
        require(binding["baseline"] == self.baseline(), "Distribution baseline drift")
        require(binding["adapter_version"] == 1 and binding["toolchain"] == toolchain(self.root), "Task toolchain/version drift")
        require(sha(path_at(self.root, ".opencode/lifecycle-installation.json").read_bytes()) == binding["installation_sha256"],
                "Task installation binding drift")
        require(binding["stages"] == ["inspect", "github", "build", "validate", "qualify", "review"], "Task stage authority mismatch")
        require(datetime.strptime(binding["expires_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
                > datetime.now(timezone.utc), "Task expired; owner must enroll a new task")
        out = self.outputs / task
        path_at(out.parent, out.name, exists=False)
        require(out.is_dir(), "Missing task workspace")
        lock = path_at(directory, "lock", exists=False)
        with lock.open("a+b") as stream:
            fcntl.flock(stream, fcntl.LOCK_EX)
            # Check again under the same lock as every state read/write.
            require(sha(binding_path.read_bytes()) == digest, "Task changed under lock")
            state = read_json(path_at(directory, "state.json"))
            check_state(directory, state)
            if (directory / "revoked").exists():
                raise ValueError("Task revoked")
            yield binding, state, out

    def transition(self, binding, state, stage, **fields):
        directory = self.control / binding["task_id"]
        require(read_json(directory / "state.json") == state, "Stale task generation")
        updated = {**state, **fields, "stage": stage, "generation": state["generation"] + 1,
                   "previous_state_sha256": sha(repo.json_bytes(state))}
        write_new(directory / f"transition-{updated['generation']}.json", repo.json_bytes(updated))
        replace_json(directory / "state.json", updated)

    def acquire(self, binding, state, out):
        require(state["stage"] == "enrolled", "Source already acquired; inspect existing task")
        data, tree = self.github.source(binding["source"])
        files = archive_source(data, tree)
        source_dir = out / "source-data"
        require(not source_dir.exists(), "Ambiguous prior source acquisition; enroll a new task")
        with tempfile.TemporaryDirectory(prefix="acquire-", dir=out) as temporary:
            staging = Path(temporary) / "source-data"
            staging.mkdir()
            for name, blob in files.items():
                write_new(path_at(staging, name, exists=False), blob)
            staging.rename(source_dir)
        manifest = {n: sha(b) for n, b in files.items()}
        write_new(out / "source-archive.zip", data)
        write_new(out / "source-files.json", repo.json_bytes(manifest))
        self.transition(binding, state, "acquired", archive_sha256=sha(data),
                        source_manifest_sha256=sha(repo.json_bytes(manifest)))
        return {"status": "PASS", "source": binding["source"], "archive_sha256": sha(data),
                "source_manifest_sha256": sha(repo.json_bytes(manifest)),
                "addon_manifests": sorted(n for n in files if n.split("/")[-1] == "addon.xml"),
                "source_executed": False}

    def source_files(self, state, out):
        raw = path_at(out, "source-files.json").read_bytes()
        require(sha(raw) == state["source_manifest_sha256"], "Source inventory changed")
        manifest = json.loads(raw)
        require(sha(path_at(out, "source-archive.zip").read_bytes()) == state["archive_sha256"], "Source archive changed")
        actual = {}
        base = out / "source-data"
        for p in base.rglob("*"):
            require(not p.is_symlink(), "Linked acquired source")
            if p.is_file():
                name = p.relative_to(base).as_posix()
                blob = path_at(base, name).read_bytes()
                require(sha(blob) == manifest.get(name), "Acquired source changed")
                actual[name] = blob
            else:
                require(p.is_dir(), "Special acquired source")
        require(set(actual) == set(manifest), "Source inventory mismatch")
        return actual

    def prepare(self, binding, state, out, subdir, runtime_files):
        require(state["stage"] in ("acquired", "prepared"), "Acquire source first")
        require(isinstance(subdir, str), "Select an add-on root")
        if subdir != ".":
            path_at(out / "source-data", subdir, exists=False)
        require(isinstance(runtime_files, list) and runtime_files and len(runtime_files) <= repo.MAX_ENTRIES
                and all(isinstance(x, str) for x in runtime_files), "Explicit runtime allowlist required")
        repo.inventory_paths(runtime_files)
        source = self.source_files(state, out)
        files = {}
        prefix = "" if subdir == "." else subdir + "/"
        for name in runtime_files:
            repo.runtime_name(name)
            require(prefix + name in source, "Runtime member unavailable in selected source")
            files[name] = source[prefix + name]
        selection = {"addon_subdir": subdir, "runtime_files": sorted(runtime_files)}
        if state["stage"] == "prepared":
            require(state["selection"] == selection, "Frozen runtime selection differs; enroll a new task")
            return self.review(binding, state, out)
        blob = repo.zip_bytes(files)
        require(blob == repo.zip_bytes(files), "Package generation is nondeterministic")
        manifest, _ = repo.inspect_zip(blob)
        aid, ver = manifest.get("id"), manifest.get("version")
        require(aid != read_json(self.root / "config/repository.json")["addon_id"],
                "Repository installer identity requires separately scoped maintenance")
        historical = read_json(self.root / "releases/manifest.json")["packages"]
        for old in historical:
            if old["id"] == aid:
                require(old["version"] != ver or old["sha256"] == sha(blob), "Published version bytes would change")
                require(old["version"] != ver, "Already published identical artifact; no new release")
                require(repo.version(ver) > repo.version(old["version"]), "Candidate version does not increase release history")
        for name, data in files.items():
            check_publication.scan_bytes(name, data)
        filename = f"{aid}-{ver}.zip"
        template = read_json(self.root / "docs/REVIEW-RECORD-EXAMPLE.json")
        template.pop("note", None)
        lanes = list(binding["targets"])
        record = {**template, "package_sha256": sha(blob), "source_repository": "https://github.com/" + binding["source"]["repository"],
                  "source_commit": binding["source"]["commit"], "runtime_files": {n: sha(b) for n, b in files.items()},
                  "approval_lanes": lanes, "compatibility": {lane: {"static_accepted": False,
                  "runtime_accepted": False, "evidence": [], "runtime_test": {"status": "pending"}} for lane in lanes}}
        approval = approval_contract.assess(record, lanes, package_identity=(aid, ver), release_history=historical)
        review_name = f"{aid}-{ver}-pending-review.json"
        intake = {"schema": 1, "external_dependencies": {}, "packages": [{"zip": filename, "sha256": sha(blob),
                  "review_record": review_name, "review_record_sha256": sha(repo.json_bytes(record)), "lanes": lanes}]}
        candidate = out / "candidate"
        for name in ("config/repository.json", "config/production.json", "releases/manifest.json"):
            write_new(candidate / name, path_at(self.root, name).read_bytes())
        write_new(candidate / "incoming" / filename, blob)
        write_new(candidate / "incoming" / (filename + ".sha256"), (sha(blob) + "\n").encode())
        write_new(candidate / "incoming" / review_name, repo.json_bytes(record))
        write_new(candidate / "config/candidate.json", repo.json_bytes(intake))
        # A frozen metadata proposal, never applied to production inputs.
        proposed_config = read_json(self.root / "config/production.json")
        prior_hashes = {old["sha256"] for old in historical if old["id"] == aid}
        for old in proposed_config["packages"]:
            if old["sha256"] in prior_hashes:
                old["lanes"] = [lane for lane in old["lanes"] if lane not in lanes]
        proposed_config["packages"].append(intake["packages"][0])
        ledger = read_json(self.root / "releases/manifest.json")
        if not any(old["id"] == aid and old["version"] == ver for old in ledger["packages"]):
            ledger["packages"].append({"id": aid, "version": ver, "sha256": sha(blob)})
        proposal = {"profile": "candidate", "application_authorized": False,
                    "baseline": binding["baseline"], "proposed_production_input": proposed_config,
                    "proposed_retention_ledger": ledger,
                    "blockers": approval["release_blockers"] + [
                        "Retained review records must be reviewed and superseded if their active lane scope changes",
                        "Restore every retained artifact before attempting a full feed build"]}
        write_new(candidate / "change-proposal.json", repo.json_bytes(proposal))
        catalog_hashes = {}
        for lane in lanes:
            catalog = repo.ET.Element("addons")
            catalog.append(copy.deepcopy(manifest))
            catalog_bytes = repo.xml_bytes(catalog)
            relative = f"candidate/catalog-fragments/{lane}/addons.xml"
            write_new(out / relative, catalog_bytes)
            write_new(out / (relative + ".sha256"), (sha(catalog_bytes) + "\n").encode())
            catalog_hashes[relative] = sha(catalog_bytes)
        receipt = {"profile": "candidate", "task_id": binding["task_id"], "source": binding["source"],
                   "source_archive_sha256": state["archive_sha256"], "source_manifest_sha256": state["source_manifest_sha256"],
                   "selection": selection, "addon_id": aid, "version": ver, "package": "candidate/incoming/" + filename,
                   "package_sha256": sha(blob), "review_record": "candidate/incoming/" + review_name,
                   "review_record_sha256": sha(repo.json_bytes(record)), "input_config_sha256": sha(repo.json_bytes(intake)),
                   "change_proposal_sha256": sha(repo.json_bytes(proposal)), "catalog_fragments": catalog_hashes,
                   "baseline": binding["baseline"], "approval": approval,
                   "native_tested": False, "source_executed": False, "publication_authorized": False,
                   "feed_status": "BLOCKED: retained production packages and preview-installer identity require separately reviewed staging; package audit only"}
        write_new(out / "preparation.json", repo.json_bytes(receipt))
        self.transition(binding, state, "prepared", selection=selection, preparation_sha256=sha(repo.json_bytes(receipt)))
        return self.review(binding, read_json(self.control / binding["task_id"] / "state.json"), out)

    def review(self, binding, state, out):
        require(state["stage"] == "prepared", "No frozen candidate package")
        raw = path_at(out, "preparation.json").read_bytes()
        require(sha(raw) == state["preparation_sha256"], "Preparation receipt changed")
        receipt = json.loads(raw)
        blob = path_at(out, receipt["package"]).read_bytes()
        require(sha(blob) == receipt["package_sha256"], "Candidate package changed")
        # Independent ZIP auditor does not import builder implementation.
        manifest, files = audit_candidate.archive_files(blob)
        require((manifest.get("id"), manifest.get("version")) == (receipt["addon_id"], receipt["version"]),
                "Independent archive identity mismatch")
        source = self.source_files(state, out)
        selection = state["selection"]
        prefix = "" if selection["addon_subdir"] == "." else selection["addon_subdir"] + "/"
        require(set(files) == set(selection["runtime_files"])
                and all(data == source[prefix + name] for name, data in files.items()), "Independent source mapping mismatch")
        record_bytes = path_at(out, receipt["review_record"]).read_bytes()
        require(sha(record_bytes) == receipt["review_record_sha256"], "Review record changed")
        record = json.loads(record_bytes)
        candidate = out / "candidate"
        for name, expected in binding["baseline"].items():
            require(sha(path_at(candidate, name).read_bytes()) == expected, "Retained baseline changed")
        config_raw = path_at(candidate, "config/candidate.json").read_bytes()
        require(sha(config_raw) == receipt["input_config_sha256"], "Candidate intake changed")
        require(sha(path_at(candidate, "change-proposal.json").read_bytes()) == receipt["change_proposal_sha256"],
                "Config/ledger proposal changed")
        for name, digest in receipt["catalog_fragments"].items():
            raw_catalog = path_at(out, name).read_bytes()
            require(sha(raw_catalog) == digest
                    and path_at(out, name + ".sha256").read_text() == digest + "\n", "Catalog fragment changed")
            parsed = audit_candidate.xml(raw_catalog)
            require(parsed.tag == "addons" and len(parsed) == 1
                    and audit_candidate.structure(parsed[0]) == audit_candidate.structure(manifest),
                    "Independent candidate catalog metadata mismatch")
        require(path_at(candidate / "incoming", Path(receipt["package"]).name + ".sha256").read_text() == sha(blob) + "\n",
                "Candidate sidecar changed")
        require(record["runtime_files"] == {n: sha(b) for n, b in files.items()}
                and record["package_sha256"] == sha(blob)
                and record["source_commit"] == binding["source"]["commit"]
                and record["source_repository"] == "https://github.com/" + binding["source"]["repository"],
                "Review provenance mismatch")
        approval = approval_contract.assess(record, list(binding["targets"]),
                  package_identity=(manifest.get("id"), manifest.get("version")),
                  release_history=read_json(self.root / "releases/manifest.json")["packages"])
        require(approval == receipt["approval"] and approval["release_blockers"], "Candidate approvals changed")
        static_evidence = {}
        for lane, digest in state["validations"].items():
            raw_validation = path_at(out, f"validation/{lane}.json").read_bytes()
            require(sha(raw_validation) == digest, "Validation receipt changed")
            validation = json.loads(raw_validation)
            registered = binding['lane_environments'].get(lane)
            expected_identity = registered.get('identity') if registered and registered['status']=='available' else binding['toolkit_identity']
            if registered:
                cache = registered.get('cache',installation(self.root)['cache'])
                require(validation.get('lane_index') == lifecycle_lanes.index_identity(cache,lane),
                        'Lane validation index identity changed')
            require(validation["lane"] == lane and validation["package_sha256"] == sha(blob)
                    and validation["toolkit_identity"] == expected_identity
                    and validation["validation"]["branch"] == lane
                    and validation["validation"]["source_snapshot"] == record["runtime_files"],
                    "Validation identity mismatch")
            static_evidence[lane] = {"sha256": digest, "status": validation["status"],
                                     "checks": validation["validation"]["checks"],
                                     "toolkit_identity": validation["toolkit_identity"],
                                     'coverage_limits':validation.get('coverage_limits', []),
                                     "static_accepted": False, "native_tested": False}
        result = {"status": "PASS", "scope": "independent frozen candidate package/source audit only",
                "task_id": binding["task_id"], "package_sha256": sha(blob),
                "addon_id": receipt["addon_id"], "version": receipt["version"],
                "approval": approval, "targets": binding["targets"], "feed_status": receipt["feed_status"],
                "static_evidence": static_evidence,
                "native_tested": False, "publication_authorized": False}
        if 'feed_sha256' in state:
            import lifecycle_feed
            result['feed'] = lifecycle_feed.verify(self, binding, state, out)
        return result

    def validate(self, binding, state, out, lane):
        require(lane in binding["targets"], "Lane outside owner task")
        registered = binding['lane_environments'].get(lane)
        if lane != "nexus" and registered is None:
            return {"status": "BLOCKED", "lane": lane, "target": binding["targets"][lane],
                    "reason": "Matching lane tooling is not qualified; Phase C required",
                    "native_tested": False, "static_accepted": False, "publication_authorized": False}
        audit = self.review(binding, state, out)
        require('feed_sha256' not in state, 'Feed evidence frozen; validate before feed construction or enroll a new task')
        installed = installation(self.root)
        if registered and registered['status'] == 'available':
            lifecycle_lanes.verify(installed, lane, toolkit_identity)
            require(lifecycle_lanes.select(installed,lane) == registered, 'Bound lane registry drift')
            installed = {**installed, **{k:registered[k] for k in ('python','toolkit','cache')}}
        expected_identity = registered['identity'] if registered and registered['status']=='available' else binding['toolkit_identity']
        require(toolkit_identity(installed) == expected_identity, "Trusted Toolkit environment drift")
        cache = Path(installed["cache"])
        require(cache.is_dir() and not cache.is_symlink(), "Explicit Toolkit cache unavailable")
        cache_digest = sha(path_at(cache, "manifest.json").read_bytes())
        lane_index = lifecycle_lanes.index_identity(cache,lane) if registered else None
        if lane in state["validations"]:
            raw = path_at(out, f"validation/{lane}.json").read_bytes()
            require(sha(raw) == state["validations"][lane], "Validation receipt changed")
            result = json.loads(raw)
            require(result["cache_manifest_sha256"] == cache_digest, "Validation cache drift")
            require(result.get('lane_index') == lane_index, 'Cached lane index drift')
            return result
        receipt = read_json(out / "preparation.json")
        _, files = audit_candidate.archive_files(path_at(out, receipt["package"]).read_bytes())
        addon = out / "static-source" / audit["addon_id"]
        for name, blob in files.items():
            write_new(addon / name, blob)
        if registered and registered['status'] == 'unverified':
            result = {'status':'UNVERIFIED','scope':'No matching qualified static environment','lane':lane,
                      'reason':registered['reason'],'package_sha256':receipt['package_sha256'],
                      'cache_manifest_sha256':cache_digest,'toolkit_identity':expected_identity,
                      'lane_index':lane_index,
                      'validation':{'branch':lane,'passed':False,'source_snapshot':{n:sha(b) for n,b in files.items()},
                                    'checks':{'types':{'status':'unverified','passed':False}}},
                      'coverage_limits':lifecycle_lanes.LIMITS,'static_accepted':False,'native_tested':False,'publication_authorized':False}
            write_new(out/f'validation/{lane}.json', repo.json_bytes(result))
            self.transition(binding,state,'prepared',validations={**state['validations'],lane:sha(repo.json_bytes(result))})
            return result
        command = [installed["python"], "-I", "-B", "-m", "kodi_agent_toolkit.cli", "validate",
                   str(addon), "--branch", lane, "--cache", str(cache)]
        process = subprocess.run(command, cwd=installed["toolkit"], env={"PATH": "/usr/bin:/bin",
                   "LANG": "C.UTF-8", "PYTHONDONTWRITEBYTECODE": "1", "PYTHONNOUSERSITE": "1"},
                   capture_output=True, text=True, timeout=180)
        require(len(process.stdout) + len(process.stderr) <= 2_000_000, "Toolkit output exceeds bound")
        data = json.loads(process.stdout)
        require(data.get("branch") == lane and data.get("source_snapshot") == {n: sha(b) for n, b in files.items()},
                "Toolkit source/lane identity mismatch")
        require(all(path_at(addon, n).read_bytes() == b for n, b in files.items()), "Static source changed")
        result = {"status": "PASS" if process.returncode == 0 and data.get("passed") is True else "FAIL",
                  "scope": "matching-branch Toolkit API checks with Python 3.10 static language target", "lane": lane,
                  "package_sha256": receipt["package_sha256"], "cache_manifest_sha256": cache_digest,
                  "toolkit_identity": expected_identity,
                  'coverage_limits': registered['coverage_limits'] if registered else list(lifecycle_lanes.LIMITS),
                  'lane_index':lane_index,
                  'runtime_python_compatibility':'UNVERIFIED',
                  "validation": data, "exit_code": process.returncode, "stderr": process.stderr,
                  "static_accepted": False, "native_tested": False, "publication_authorized": False}
        write_new(out / f"validation/{lane}.json", repo.json_bytes(result))
        self.transition(binding, state, "prepared", validations={**state["validations"], lane: sha(repo.json_bytes(result))})
        return result

    def operate(self, operation, role, task, digest, arguments, context=None):
        require(__debug__, "Independent audits require nonoptimized Python")
        require(operation in ROLES and role in ROLES[operation], "Role denied")
        with self.bound(task, digest) as (binding, state, out):
            if arguments.get("action") == "publication_pilot":
                closed(arguments, {"action"})
                import lifecycle_pilot
                return lifecycle_pilot.operate(self, binding, state, out, operation, role, context)
            require(context is None, "Unexpected role context")
            if operation == "inspect":
                closed(arguments, set(), {"file"})
                result = {"binding": binding, "state": state, "status": "PASS"}
                if state["stage"] in ("acquired", "prepared"):
                    files = self.source_files(state, out)
                    result["addon_manifests"] = sorted(n for n in files if n.endswith("addon.xml"))
                    result["source_files"] = sorted(files)
                    if "file" in arguments:
                        name = arguments["file"]
                        require(isinstance(name, str) and name in files and len(files[name]) <= 64_000,
                                "Unavailable/oversized source text")
                        result = {"path": name, "sha256": sha(files[name]), "text": files[name].decode("utf-8"),
                                  "untrusted_source_data": True}
                else:
                    require(not arguments, "Acquire source before reading a file")
                return result
            if operation == "github":
                closed(arguments, {"action"}, {"resource", "page"})
                require(arguments["action"] in ("acquire", "list"), "Unknown GitHub action")
                if arguments["action"] == "acquire":
                    require(set(arguments) == {"action"}, "Unexpected acquisition fields")
                    return self.acquire(binding, state, out)
                require("resource" in arguments, "Select fixed listing resource")
                self.github.resolve(binding["source"]["repository"], "commit", binding["source"]["commit"],
                                    binding["source"]["repository_id"], binding["source"]["commit"])
                return self.github.listing(binding["source"]["repository"], arguments["resource"], arguments.get("page", 1))
            if operation == "build":
                if arguments.get('action') == 'publication':
                    closed(arguments, {'action'})
                    import lifecycle_publication
                    return lifecycle_publication.operate(self, binding, state, out, operation, role)
                if arguments.get('action') == 'feed':
                    closed(arguments, {'action'})
                    import lifecycle_feed
                    return lifecycle_feed.build(self,binding,state,out)
                closed(arguments, {"addon_subdir", "runtime_files"})
                return self.prepare(binding, state, out, arguments["addon_subdir"], arguments["runtime_files"])
            if operation in ("qualify", "review"):
                if arguments.get('action') == 'publication':
                    closed(arguments, {'action'})
                    import lifecycle_publication
                    return lifecycle_publication.operate(self, binding, state, out, operation, role)
                closed(arguments, set())
                return self.review(binding, state, out)
            closed(arguments, {"lane"})
            return self.validate(binding, state, out, arguments["lane"])


def install(root, toolkit, plugin_module, shared):
    """Explicit local installation, no overwrite and no production activation."""
    require(root == ROOT, "Installer binds only its own reviewed checkout")
    require(not (root / "opencode.json").exists() and not (root / ".opencode").exists(),
            "Existing profile requires separately reviewed migration")
    for p in (root, toolkit, plugin_module, shared):
        require(p.is_absolute() and p.resolve(strict=True) == p and not p.is_symlink(), "Expected exact existing installation path")
    require((toolkit / ".venv/bin/python").exists() and plugin_module.is_file(), "Missing trusted dependencies")
    templates = read_json(root / "scripts/opencode/profiles.json")
    replacements = {"@PROJECT@": str(root), "@TOOLKIT@": str(toolkit), "@SHARED@": str(shared),
                    "@PROJECT_RELATIVE@": str(root).lstrip("/"),
                    "@TOOLKIT_RELATIVE@": str(toolkit).lstrip("/"),
                    "@SHARED_RELATIVE@": str(shared).lstrip("/"),
                    "@TOOLKIT_PROJECT_RELATIVE@": os.path.relpath(toolkit, root),
                    "@SHARED_PROJECT_RELATIVE@": os.path.relpath(shared, root)}
    def render(value):
        text = json.dumps(value)
        for old, new in replacements.items():
            text = text.replace(old, new)
        return json.loads(text)
    templates = render(templates)
    profile = root / ".opencode"
    (profile / "agents").mkdir(parents=True)
    (profile / "tools").mkdir()
    (profile / "control").mkdir()
    install_record = {"schema": 1, "adapter_version": 1, "project_root": str(root), "toolkit": str(toolkit),
                      "python": str(toolkit / ".venv/bin/python"), "cache": str(toolkit / ".local/index-cache"),
                      "plugin_module": str(plugin_module), "shared": str(shared)}
    install_record["toolkit_identity"] = toolkit_identity(install_record)
    write_new(profile / "lifecycle-installation.json", repo.json_bytes(install_record))
    for role, value in templates["roles"].items():
        prompt = value["prompt"] + "\nFor an enrolled Phase A/B task, read docs/LIFECYCLE-PREPARATION.md and use only task-bound local preparation. Permissions remain unchanged.\n"
        write_new(profile / "agents" / (role + ".md"), ("---\n" + json.dumps(value["frontmatter"], indent=2) + "\n---\n" + prompt).encode())
    shutil.copyfile(root / "scripts/opencode/kodi.ts", profile / "tools/kodi.ts")
    shutil.copyfile(root / "scripts/opencode/fixture_adapter.py", profile / "control/agent-tools.py")
    # Preserve insertion order: the engine's last matching permission wins.
    write_new(root / "opencode.json", (json.dumps(templates["config"], indent=2) + "\n").encode())
    return {"status": "PASS", "scope": "local isolated profile installation", "project_root": str(root),
            "publication_authorized": False}


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser('configure-lanes')
    setup = commands.add_parser("install")
    for name in ("toolkit", "plugin-module", "shared"):
        setup.add_argument("--" + name, type=Path, required=True)
    resolve = commands.add_parser("resolve")
    resolve.add_argument("repository")
    resolve.add_argument("ref_kind", choices=("branch", "tag", "commit"))
    resolve.add_argument("ref")
    enroll = commands.add_parser("enroll")
    enroll.add_argument("request", type=Path)
    revoke = commands.add_parser("revoke")
    revoke.add_argument("task_id")
    args = parser.parse_args()
    if args.command == "install":
        result = install(ROOT, args.toolkit, args.plugin_module, args.shared)
    elif args.command == "resolve":
        result = GitHub().resolve(args.repository, args.ref_kind, args.ref)
    elif args.command == 'configure-lanes':
        result = lifecycle_lanes.configure(ROOT)
    else:
        installation()
        store = Store()
        if args.command == "enroll":
            result = store.enroll(read_json(args.request))
        else:
            require(TASK.fullmatch(args.task_id), "Malformed task ID")
            directory = store.control / args.task_id
            write_new(path_at(directory, "revoked", exists=False), b"operator revoked\n")
            result = {"status": "PASS", "task_id": args.task_id, "revoked": True}
    print(json.dumps(result))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(json.dumps({"status": "BLOCKED", "error": type(error).__name__, "detail": str(error)[:1000]}))
        sys.exit(1)

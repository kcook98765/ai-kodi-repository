"""Qualification-only GitHub REST shapes through a concrete scripted mock.

There is deliberately no socket/HTTP implementation, environment credential
lookup, Git invocation or production enrollment. Public methods model bounded
individual requests so an external coordinator can journal each separate effect.
Local simulated credentials and responses authorize no real GitHub operation.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
import json
from pathlib import Path
import re
import sys
from urllib.parse import quote, urlsplit, urlunsplit

sys.path.insert(0, str(Path(__file__).resolve().parent))
import publication_proposal as core


MODE = "isolated-transport-qualification"
API = "https://api.github.com"
UPLOADS = "https://uploads.github.com"
API_VERSION = "2026-03-10"
QUAL_REPOSITORY = "kcook98765-kodi-qualification/ai-kodi-publisher-d3-qualification"
QUAL_ORIGIN = "https://kcook98765-kodi-qualification.github.io/ai-kodi-publisher-d3-qualification/"
PRODUCTION_ID = 1428864210
MAX_JSON = 4_000_000
MAX_ASSET = 64_000_000
MAX_PAGES = 20
COMMIT = re.compile(r"[0-9a-f]{40}\Z")
DIGEST = re.compile(r"[0-9a-f]{64}\Z")
TAG = re.compile(r"(?:script\.ai\.kodi\.d3\.fixture-(?:1\.0\.0|1\.1\.0)|repository\.ai\.kodi\.candidate\.[0-9a-f]{32}-[0-9]+\.[0-9]+\.[0-9]+)\Z")
LEDGER_BRANCH = re.compile(r"publication-ledger/[0-9a-f]{64}\Z")


def need(value, message):
    core.require(value, message)


def number(value):
    need(type(value) is int and 0 < value < 2**53, "Invalid numeric GitHub identity")
    return value


def commit(value):
    need(type(value) is str and COMMIT.fullmatch(value), "Invalid immutable Git identity")
    return value


def checksum(value):
    need(type(value) is str and DIGEST.fullmatch(value), "Invalid SHA-256")
    return value


def tag_name(value):
    need(type(value) is str and TAG.fullmatch(value), "Tag outside qualification namespace")
    return value


def asset_name(value):
    need(type(value) is str and re.fullmatch(r"[A-Za-z0-9_.-]{1,200}", value), "Invalid asset name")
    if value != "SHA256SUMS":
        package = value.removesuffix(".sha256").removesuffix(".zip")
        tag_name(package)
        need(value in (package + ".zip", package + ".zip.sha256"), "Unsupported qualification asset")
    return value


def text(value, limit=10000):
    need(type(value) is str and len(value.encode("utf-8")) <= limit and "\0" not in value,
         "Invalid bounded text")
    return value


def parse_json(raw):
    need(type(raw) is bytes and len(raw) <= MAX_JSON, "Oversized GitHub JSON response")
    def pairs(items):
        result = {}
        for name, value in items:
            need(name not in result, "Duplicate GitHub JSON field")
            result[name] = value
        return result
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Invalid JSON constant")))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("Malformed GitHub JSON response") from error


def enrollment(value):
    fields = {"mode", "repository", "repository_id", "owner_id", "human_owner_id", "origin",
              "app_id", "app_installation_id", "branch", "path"}
    need(type(value) is dict and set(value) == fields, "Closed qualification transport enrollment required")
    need(value["mode"] == MODE and value["repository"] == QUAL_REPOSITORY,
         "Only the explicitly selected qualification repository is supported")
    for name in ("repository_id", "owner_id", "human_owner_id", "app_id", "app_installation_id"):
        number(value[name])
    need(value["repository_id"] != PRODUCTION_ID and value["owner_id"] != value["human_owner_id"]
         and value["human_owner_id"] == 56806582, "Production/owner identity is outside qualification scope")
    need(value["origin"] == QUAL_ORIGIN, "Unenrolled qualification origin")
    origin = urlsplit(value["origin"])
    need(origin.scheme == "https" and origin.username is None and origin.password is None and
         origin.hostname is not None and origin.hostname == origin.hostname.lower() and
         not origin.hostname.endswith(".") and origin.port in (None, 443) and
         origin.hostname not in ("kcook98765.github.io", "github.com", "api.github.com", "uploads.github.com") and
         origin.path.startswith("/") and origin.path.endswith("/") and not origin.query and not origin.fragment,
         "Qualification origin must be canonical HTTPS and distinct from production")
    need(value["branch"] == "gh-pages" and value["path"] == "/", "Unenrolled Pages branch/path")
    return dict(value)


@dataclass(frozen=True)
class SimulatedCredential:
    """No token material exists in this descriptor or in any request."""
    app_id: int
    installation_id: int
    expires_at: str
    permissions: dict = field(repr=False)


@dataclass(frozen=True)
class MockResponse:
    status: int
    body: bytes = field(default=b"", repr=False)
    headers: dict = field(default_factory=dict, repr=False)

    @classmethod
    def json(cls, status, value, headers=None):
        return cls(status, json.dumps(value, separators=(",", ":")).encode(), headers or {})


@dataclass(frozen=True)
class MockExchange:
    method: str
    url: str = field(repr=False)
    response: MockResponse = field(repr=False)
    body: object = field(default=None, repr=False)


class ScriptedMockSender:
    """Finite in-memory expectations. No callback or network fallback accepted."""
    def __init__(self, exchanges):
        need(type(exchanges) is list and all(type(x) is MockExchange for x in exchanges), "Concrete scripted mock required")
        self._queue = list(exchanges)
        self.requests = []

    def send(self, method, url, headers, body):
        safe_url = urlunsplit((*urlsplit(url)[:3], "", ""))
        self.requests.append({"method": method, "url": safe_url, "body_sha256": core.sha(body),
                              "body_size": len(body), "authenticated": "Authorization" in headers})
        need(bool(self._queue), "No scripted mock response; network is unavailable")
        expected = self._queue.pop(0)
        need(method == expected.method and url == expected.url, "Unexpected mocked request shape")
        if expected.body is not None:
            wanted = expected.body if type(expected.body) is bytes else core.canonical(expected.body)
            need(body == wanted, "Unexpected mocked request body")
        need(type(expected.response) is MockResponse, "Mock response type rejected")
        return expected.response

    @property
    def remaining(self):
        return len(self._queue)


class GitHubQualification:
    """Typed API shapes only; this class cannot transmit a network request."""
    def __init__(self, enrolled, sender, *, clock=None):
        self.enrolled = enrollment(enrolled)
        need(type(sender) is ScriptedMockSender, "Only the concrete in-memory mock sender is supported")
        self.sender = sender
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.prefix = "/repos/" + self.enrolled["repository"]

    def _credentials(self, credential, caps):
        enrollment(self.enrolled)
        need(self.prefix == "/repos/" + QUAL_REPOSITORY, "Transport destination binding changed")
        need(type(credential) is SimulatedCredential, "Only simulated qualification credentials are accepted")
        need(type(credential.app_id) is int and credential.app_id == self.enrolled["app_id"] and
             type(credential.installation_id) is int and credential.installation_id == self.enrolled["app_installation_id"],
             "Credential installation identity mismatch")
        now = core.timestamp(self.clock()); expiry = core.timestamp(credential.expires_at)
        need(now < expiry and expiry - now <= timedelta(hours=1), "Expired/overlong mock credential")
        need(type(credential.permissions) is dict and set(credential.permissions) <= set(caps) | {"metadata"},
             "Credential exceeds per-operation permission cap")
        levels = {"read": 1, "write": 2}
        for name, value in credential.permissions.items():
            need(value in levels and (name != "metadata" or value == "read"), "Invalid permission capability")
            need(name == "metadata" or levels[value] <= levels[caps[name]], "Credential exceeds operation scope")
        for name, value in caps.items():
            need(credential.permissions.get(name) == value, "Missing exact operation capability")

    def _request(self, method, suffix, credential, *, body=None, statuses=(200,), upload=False, binary=False, absolute=None):
        enrollment(self.enrolled)
        need(self.prefix == "/repos/" + QUAL_REPOSITORY, "Transport destination binding changed")
        need(method in ("GET", "POST", "PATCH"), "Mutation method forbidden")
        routes = (
            r"", r"/pages", r"/git/ref/heads/(?:main|gh-pages)",
            r"/git/ref/tags/[A-Za-z0-9_.-]+", r"/git/tags/[0-9a-f]{40}",
            r"/git/commits/[0-9a-f]{40}", r"/git/trees/[0-9a-f]{40}\?recursive=1",
            r"/releases(?:\?per_page=100&page=[0-9]+)?", r"/releases/tags/[A-Za-z0-9_.-]+",
            r"/releases/[0-9]+", r"/releases/[0-9]+/assets(?:\?per_page=100&page=[0-9]+|\?name=[A-Za-z0-9_.-]+)?",
            r"/releases/assets/[0-9]+", r"/git/(?:refs|blobs|trees|commits)",
            r"/git/blobs/[0-9a-f]{40}", r"/pages/builds/latest", r"/pulls/[0-9]+(?:/reviews\?per_page=100&page=[0-9]+)?",
            r"/actions/runs/[0-9]+(?:/approvals|/jobs\?per_page=100&page=[0-9]+|/artifacts\?per_page=100&page=[0-9]+)?",
            r"/actions/workflows/[0-9]+", r"/actions/artifacts/[0-9]+/zip",
            r"/environments/(?:kodi-d3-publication|github-pages)(?:/deployment-branch-policies\?per_page=100&page=[0-9]+)?",
            r"/issues/[0-9]+(?:/comments\?per_page=100&page=[0-9]+)?",
            r"/rulesets\?includes_parents=true&per_page=100&page=[0-9]+", r"/rulesets/[0-9]+",
            r"/contents/\.github/workflows/publication-approval\.yml\?ref=[0-9a-f]{40}",
            r"/git/refs/heads/gh-pages", r"/pulls", r"/git/ref/heads/publication-ledger/[0-9a-f]{64}",
            r"/pulls\?state=all&head=kcook98765-kodi-qualification%3Apublication-ledger%2F[0-9a-f]{64}&base=main&per_page=100&page=[0-9]+")
        need(type(suffix) is str and any(re.fullmatch(route, suffix) for route in routes), "Endpoint outside allowlist")
        if method == "POST":
            need(suffix in ("/git/refs", "/git/blobs", "/git/trees", "/git/commits", "/releases", "/pulls") or
                 re.fullmatch(r"/releases/[0-9]+/assets\?name=[A-Za-z0-9_.-]+", suffix), "POST endpoint denied")
        if method == "PATCH":
            need(suffix == "/git/refs/heads/gh-pages" or re.fullmatch(r"/releases/[0-9]+", suffix), "PATCH endpoint denied")
        if upload:
            need(method == "POST" and "/assets?name=" in suffix, "Upload scope denied")
        url = (UPLOADS if upload else API) + self.prefix + suffix
        headers = {"Accept": "application/octet-stream" if binary else "application/vnd.github+json",
                   "X-GitHub-Api-Version": API_VERSION, "Authorization": "Bearer MOCK-ONLY-NOT-A-CREDENTIAL"}
        if absolute is not None:
            try:
                parsed = urlsplit(absolute)
                port = parsed.port
            except (TypeError, ValueError):
                raise ValueError("Malformed asset redirect origin") from None
            allowed = parsed.hostname == "release-assets.githubusercontent.com" or (
                suffix.startswith("/actions/artifacts/") and parsed.hostname is not None and
                parsed.hostname.endswith(".blob.core.windows.net"))
            need(binary and method == "GET" and parsed.scheme == "https" and allowed and port in (None, 443) and
                 parsed.username is None and parsed.password is None and not parsed.fragment,
                 "Unexpected asset redirect destination")
            url = absolute
            headers.pop("Authorization")
        raw = b"" if body is None else body if type(body) is bytes else core.canonical(body)
        if body is not None: headers["Content-Type"] = "application/octet-stream" if upload else "application/json"
        need(len(raw) <= MAX_ASSET * 2, "Oversized mocked request")
        try:
            response = self.sender.send(method, url, headers, raw)
        except Exception:
            raise ValueError("Mock transport failed; remote effect may be unknown") from None
        need(type(response.status) is int and type(response.headers) is dict and type(response.body) is bytes,
             "Malformed mocked HTTP response")
        need(response.status in statuses, "GitHub operation rejected (HTTP " + str(response.status) + ")")
        need(len(response.body) <= (MAX_ASSET if binary else MAX_JSON), "Oversized GitHub response")
        return response

    def _json(self, method, suffix, credential, **kwargs):
        response = self._request(method, suffix, credential, **kwargs)
        value = parse_json(response.body)
        need(type(value) is dict, "Expected GitHub JSON object")
        return value

    def _read_object(self, suffix, credential, *, absent=False):
        need(type(absent) is bool, "Absence handling must be explicit")
        response = self._request("GET", suffix, credential, statuses=(200, 404) if absent else (200,))
        if response.status == 404: return None
        value = parse_json(response.body)
        need(type(value) is dict, "Expected GitHub JSON object")
        return value

    def _repo(self, credential):
        value = self._json("GET", "", credential)
        need(type(value) is dict and number(value.get("id")) == self.enrolled["repository_id"] and
             value.get("full_name") == self.enrolled["repository"] and value.get("private") is False,
             "Unexpected repository identity or visibility")
        owner = value.get("owner", {})
        need(type(owner) is dict and number(owner.get("id")) == self.enrolled["owner_id"] and
             owner.get("type") == "Organization" and owner.get("login") == self.enrolled["repository"].split("/")[0],
             "Unexpected repository owner")
        return value

    def _ref(self, credential, ref, *, absent=False):
        response = self._request("GET", "/git/ref/" + ref, credential, statuses=(200, 404) if absent else (200,))
        if response.status == 404: return None
        value = parse_json(response.body)
        need(type(value) is dict and value.get("ref") == "refs/" + ref and type(value.get("object")) is dict,
             "Unexpected Git reference identity")
        obj = value["object"]; commit(obj.get("sha"))
        need(obj.get("type") in ("commit", "tag"), "Unsupported Git reference object")
        return value

    def _tag_commit(self, credential, tag):
        value = self._ref(credential, "tags/" + tag_name(tag))["object"]
        for _ in range(5):
            if value["type"] == "commit": return value["sha"]
            item = self._json("GET", "/git/tags/" + commit(value["sha"]), credential)
            need(type(item) is dict and item.get("sha") == value["sha"] and type(item.get("object")) is dict,
                 "Annotated tag identity mismatch")
            value = item["object"]; commit(value.get("sha"))
            need(value.get("type") in ("commit", "tag"), "Unsupported tag target")
        raise ValueError("Annotated tag chain exceeds bound")

    def _preflight(self, credential, heads):
        need(type(heads) is dict and set(heads) == {"main_sha", "pages_sha"}, "Exact branch heads required")
        self._repo(credential)
        for branch, key in (("main", "main_sha"), ("gh-pages", "pages_sha")):
            ref = self._ref(credential, "heads/" + branch)
            need(ref["object"]["type"] == "commit" and ref["object"]["sha"] == commit(heads[key]),
                 "Unexpected concurrent branch head")

    def _list(self, credential, path):
        result = []
        for page in range(1, MAX_PAGES + 1):
            suffix = path + ("&" if "?" in path else "?") + f"per_page=100&page={page}"
            response = self._request("GET", suffix, credential)
            items = parse_json(response.body)
            need(type(items) is list and len(items) <= 100, "Malformed paginated GitHub inventory")
            result.extend(items)
            link = response.headers.get("Link", response.headers.get("link", ""))
            need(type(link) is str, "Malformed pagination link")
            if 'rel="next"' not in link: return result
            next_url = API + self.prefix + path + ("&" if "?" in path else "?") + f"per_page=100&page={page + 1}"
            need(f'<{next_url}>; rel="next"' in link, "Out-of-scope pagination continuation")
        raise ValueError("Incomplete GitHub history exceeds pagination bound")

    def _asset(self, value, *, expected=None):
        need(type(value) is dict, "Malformed release asset")
        need(type(value.get("digest")) is str and value["digest"].startswith("sha256:"), "Missing asset SHA-256 identity")
        normalized = {"id": number(value.get("id")), "name": asset_name(value.get("name")),
                      "size": value.get("size"), "sha256": value.get("digest", "").removeprefix("sha256:")}
        need(type(normalized["size"]) is int and 0 <= normalized["size"] <= MAX_ASSET and value.get("state") == "uploaded",
             "Incomplete or oversized release asset")
        checksum(normalized["sha256"])
        if expected is not None:
            need(core.canonical(normalized) == core.canonical(expected), "Conflicting release asset identity")
        return normalized

    def _release(self, credential, release_id, tag):
        value = self._json("GET", "/releases/" + str(number(release_id)), credential)
        need(type(value) is dict and number(value.get("id")) == release_id and value.get("tag_name") == tag_name(tag) and
             type(value.get("draft")) is bool and type(value.get("immutable")) is bool,
             "Unexpected Release object identity")
        return value

    def inspect(self, credential, expected_heads=None):
        self._credentials(credential, {"contents": "read", "pages": "read"})
        repository = self._repo(credential)
        main = self._ref(credential, "heads/main")["object"]["sha"]
        pages_sha = self._ref(credential, "heads/gh-pages")["object"]["sha"]
        if expected_heads is not None:
            need(expected_heads == {"main_sha": main, "pages_sha": pages_sha}, "Stale branch baseline")
        page = self._json("GET", "/pages", credential)
        need(type(page) is dict and page.get("html_url") == self.enrolled["origin"] and page.get("https_enforced") is True and
             page.get("build_type") == "legacy" and page.get("source") == {"branch": "gh-pages", "path": "/"},
             "Unexpected Pages destination/source")
        releases = []; seen = set()
        for item in self._list(credential, "/releases"):
            need(type(item) is dict and number(item.get("id")) not in seen, "Duplicate Release identity")
            seen.add(item["id"]); tag_name(item.get("tag_name"))
            assets = [self._asset(a) for a in self._list(credential, f'/releases/{item["id"]}/assets')]
            need(len({a["name"] for a in assets}) == len(assets) and len({a["id"] for a in assets}) == len(assets),
                 "Duplicate historical asset inventory")
            need(type(item.get("draft")) is bool and type(item.get("immutable")) is bool,
                 "Malformed Release state")
            releases.append({"id": item["id"], "tag": item["tag_name"], "draft": item["draft"],
                             "immutable": item["immutable"], "name": text(item.get("name"), 1000),
                             "notes": text(item.get("body")), "assets": assets})
        result = {"mode": MODE, "mock_only": True, "production_authorized": False,
                  "repository_id": repository["id"], "owner_id": repository["owner"]["id"],
                  "main_sha": main, "pages_sha": pages_sha, "heads": {"main": main, "gh-pages": pages_sha},
                  "pages": page, "releases": releases}
        result["snapshot_sha256"] = core.sha(core.canonical(result))
        return result

    def create_tag(self, credential, heads, tag, target):
        self._credentials(credential, {"contents": "write"}); tag_name(tag); commit(target)
        need(target == heads["main_sha"], "Release tag must bind reviewed distribution commit")
        self._preflight(credential, heads)
        need(self._ref(credential, "tags/" + tag, absent=True) is None, "Existing tag cannot be replaced")
        value = self._json("POST", "/git/refs", credential, body={"ref": "refs/tags/" + tag, "sha": target}, statuses=(201,))
        need(value.get("ref") == "refs/tags/" + tag and value.get("object", {}).get("type") == "commit" and
             value["object"].get("sha") == target,
             "Created tag differs from reviewed commit")
        return {"tag": tag, "commit": target, "mock_only": True, "production_authorized": False}

    def create_draft(self, credential, heads, tag, target, name, notes):
        self._credentials(credential, {"contents": "write"}); self._preflight(credential, heads)
        need(self._tag_commit(credential, tag) == commit(target) == heads["main_sha"], "Release tag target changed")
        absent = self._request("GET", "/releases/tags/" + tag, credential, statuses=(200, 404))
        need(absent.status == 404, "Existing Release cannot be replaced")
        body = {"tag_name": tag, "target_commitish": target, "name": text(name, 1000), "body": text(notes),
                "draft": True, "prerelease": False, "make_latest": "false"}
        value = self._json("POST", "/releases", credential, body=body, statuses=(201,))
        need(number(value.get("id")) and value.get("tag_name") == tag and value.get("draft") is True and
             value.get("immutable") is False and value.get("name") == name and value.get("body") == notes,
             "Created draft metadata mismatch")
        return {"id": value["id"], "tag": tag, "mock_only": True, "production_authorized": False}

    def upload_asset(self, credential, heads, release_id, tag, name, data, expected_sha256):
        self._credentials(credential, {"contents": "write"}); asset_name(name); checksum(expected_sha256)
        need(type(data) is bytes and len(data) <= MAX_ASSET and core.sha(data) == expected_sha256, "Frozen upload bytes mismatch")
        self._preflight(credential, heads)
        release = self._release(credential, release_id, tag)
        need(release["draft"] and not release["immutable"], "Assets require an unpublished draft")
        prior = [self._asset(a) for a in self._list(credential, f"/releases/{release_id}/assets")]
        need(name not in [a["name"] for a in prior], "Asset collision; clobber/delete forbidden")
        response = self._request("POST", f"/releases/{release_id}/assets?name=" + name, credential,
                                 body=data, statuses=(201,), upload=True)
        actual = self._asset(parse_json(response.body))
        need(actual["name"] == name and actual["sha256"] == expected_sha256 and actual["size"] == len(data),
             "Uploaded asset receipt mismatch")
        return dict(actual, mock_only=True, production_authorized=False)

    def _download(self, credential, asset_id, name, expected_sha256, size):
        expected = {"id": number(asset_id), "name": asset_name(name), "sha256": checksum(expected_sha256), "size": size}
        need(type(size) is int and 0 <= size <= MAX_ASSET, "Invalid expected asset size")
        suffix = f"/releases/assets/{asset_id}"
        self._asset(self._json("GET", suffix, credential), expected=expected)
        response = self._request("GET", suffix, credential, binary=True, statuses=(200, 302))
        if response.status == 302:
            location = response.headers.get("Location", response.headers.get("location"))
            need(type(location) is str, "Asset redirect missing")
            response = self._request("GET", suffix, credential, binary=True, absolute=location)
        need(len(response.body) == size and core.sha(response.body) == expected_sha256, "Downloaded asset bytes mismatch")
        return {"id": asset_id, "name": name, "sha256": expected_sha256, "size": size,
                "mock_only": True, "production_authorized": False}

    def download_asset(self, credential, release_id, asset_id, name, expected_sha256, size):
        self._credentials(credential, {"contents": "read"}); number(release_id)
        return self._download(credential, asset_id, name, expected_sha256, size)

    def publish_release(self, credential, heads, release_id, tag, target, assets, *, name, notes):
        self._credentials(credential, {"contents": "write"}); self._preflight(credential, heads)
        need(self._tag_commit(credential, tag) == commit(target), "Release tag changed")
        release = self._release(credential, release_id, tag)
        need(release["draft"] and not release["immutable"], "Release is not a new draft")
        need(release.get("name") == text(name, 1000) and release.get("body") == text(notes), "Reviewed Release title/notes changed")
        need(type(assets) is dict and assets, "Exact reviewed asset inventory required")
        actual = [self._asset(a) for a in self._list(credential, f"/releases/{release_id}/assets")]
        expected = [{"name": n, **a} for n, a in sorted(assets.items())]
        need(core.canonical(sorted(actual, key=lambda a: a["name"])) == core.canonical(expected), "Incomplete/conflicting Release asset set")
        for asset in actual:
            self._download(credential, asset["id"], asset["name"], asset["sha256"], asset["size"])
        value = self._json("PATCH", f"/releases/{release_id}", credential, body={"draft": False}, statuses=(200,))
        need(value.get("id") == release_id and type(value.get("id")) is int and value.get("tag_name") == tag and
             value.get("draft") is False and value.get("immutable") is True and value.get("name") == name and
             value.get("body") == notes, "Published Release is not immutable/exact")
        return {"id": release_id, "tag": tag, "immutable": True, "mock_only": True, "production_authorized": False}

    def create_blob(self, credential, heads, data, expected_sha=None):
        self._credentials(credential, {"contents": "write"})
        need(type(data) is bytes and len(data) <= MAX_ASSET, "Invalid bounded Git blob")
        expected = core.git_object("blob", data)
        need(expected_sha is None or commit(expected_sha) == expected, "Frozen blob identity mismatch")
        self._preflight(credential, heads)
        body = {"encoding": "base64", "content": base64.b64encode(data).decode("ascii")}
        value = self._json("POST", "/git/blobs", credential, body=body, statuses=(201,))
        need(value.get("sha") == expected, "Created Git blob mismatch")
        return {"sha": expected, "mock_only": True, "production_authorized": False}

    def create_tree(self, credential, heads, files, expected_tree, base_tree=None):
        self._credentials(credential, {"contents": "write"}); commit(expected_tree)
        need(type(files) is dict and files and len(files) <= 10000, "Exact bounded Git tree required")
        entries = [{"path": core.safe_name(n), "mode": "100644", "type": "blob", "sha": commit(s)} for n, s in sorted(files.items())]
        need(not any(n.startswith((".github/", ".git/")) for n in files), "Control source path injection")
        self._preflight(credential, heads)
        body = {"tree": entries}
        if base_tree is not None:
            need(set(files) <= {"releases/manifest.json", "config/qualification.json"}, "Ledger tree patch exceeds reviewed paths")
            body["base_tree"] = commit(base_tree)
        value = self._json("POST", "/git/trees", credential, body=body, statuses=(201,))
        need(value.get("sha") == expected_tree and value.get("truncated") is False, "Created Git tree mismatch/incomplete")
        return {"sha": expected_tree, "mock_only": True, "production_authorized": False}

    def create_commit(self, credential, heads, tree, parent, message, expected_sha):
        self._credentials(credential, {"contents": "write"}); commit(tree); commit(parent); commit(expected_sha); text(message)
        need(parent in (heads["main_sha"], heads["pages_sha"]) and
             core.git_commit(tree, parent, message) == expected_sha, "Frozen Git commit identity/parent mismatch")
        self._preflight(credential, heads)
        person = {"name": "Simulation Publisher", "email": "simulation@example.invalid", "date": "1970-01-01T00:00:00Z"}
        body = {"tree": tree, "parents": [parent], "message": message + "\n", "author": person, "committer": person}
        value = self._json("POST", "/git/commits", credential, body=body, statuses=(201,))
        need(value.get("sha") == expected_sha and value.get("tree", {}).get("sha") == tree and
             [p.get("sha") for p in value.get("parents", [])] == [parent], "Created Git commit differs")
        return {"sha": expected_sha, "tree": tree, "parent": parent, "mock_only": True, "production_authorized": False}

    def fast_forward_pages(self, credential, heads, target, parent, tree):
        self._credentials(credential, {"contents": "write"}); commit(target); commit(tree)
        need(parent == heads["pages_sha"], "Pages parent differs from approved head")
        self._preflight(credential, heads)
        value = self._json("GET", "/git/commits/" + target, credential)
        need(value.get("sha") == target and value.get("tree", {}).get("sha") == tree and
             [p.get("sha") for p in value.get("parents", [])] == [parent], "Pages commit has unexpected parent/tree")
        value = self._json("PATCH", "/git/refs/heads/gh-pages", credential,
                           body={"sha": target, "force": False})
        need(value.get("ref") == "refs/heads/gh-pages" and value.get("object", {}).get("type") == "commit" and
             value["object"].get("sha") == target, "Pages ref update response differs")
        return {"sha": target, "parent": parent, "tree": tree, "force": False, "mock_only": True, "production_authorized": False}

    def create_ledger_branch(self, credential, heads, branch, target):
        self._credentials(credential, {"contents": "write"})
        need(type(branch) is str and LEDGER_BRANCH.fullmatch(branch), "Unapproved ledger branch")
        commit(target); self._preflight(credential, heads)
        value = self._json("GET", "/git/commits/" + target, credential)
        need(value.get("sha") == target and [p.get("sha") for p in value.get("parents", [])] == [heads["main_sha"]],
             "Ledger branch commit parent mismatch")
        need(self._ref(credential, "heads/" + branch, absent=True) is None, "Ledger branch already exists")
        value = self._json("POST", "/git/refs", credential, body={"ref": "refs/heads/" + branch, "sha": target}, statuses=(201,))
        need(value.get("ref") == "refs/heads/" + branch and value.get("object", {}).get("type") == "commit" and
             value.get("object", {}).get("sha") == target,
             "Ledger branch creation mismatch")
        return {"branch": branch, "sha": target, "mock_only": True, "production_authorized": False}

    def create_ledger_pr(self, credential, heads, branch, target, title, body):
        self._credentials(credential, {"contents": "read", "pull_requests": "write"})
        need(type(branch) is str and LEDGER_BRANCH.fullmatch(branch), "Unapproved ledger PR branch")
        self._preflight(credential, heads)
        need(self._ref(credential, "heads/" + branch)["object"]["sha"] == commit(target), "Ledger PR head changed")
        value = self._json("POST", "/pulls", credential, body={"title": text(title, 1000), "body": text(body),
                            "head": branch, "base": "main", "draft": False}, statuses=(201,))
        need(type(value) is dict and number(value.get("number")) and value.get("state") == "open", "Malformed ledger PR result")
        for part, ref, sha in (("head", branch, target), ("base", "main", heads["main_sha"])):
            item = value.get(part, {})
            need(item.get("ref") == ref and item.get("sha") == sha and
                 number(item.get("repo", {}).get("id")) == self.enrolled["repository_id"], "Ledger PR destination/head mismatch")
        return {"number": value["number"], "branch": branch, "sha": target,
                "state": "PUBLIC_BUT_UNRECONCILED", "mock_only": True, "production_authorized": False}

    def prepare_pages(self, credential, heads, files, *, message="Simulated reviewed Pages publication"):
        """Read-only complete-site planning; not a hidden multi-write operation."""
        self._credentials(credential, {"contents": "read"}); self._preflight(credential, heads)
        need(type(files) is dict and files and len(files) <= 10000, "Complete Pages files required")
        for path, data in files.items():
            core.safe_name(path)
            need(type(data) is bytes and len(data) <= MAX_ASSET and not path.startswith((".github/", ".git/")), "Invalid Pages file")
            need("repository.ai.kodi-" not in path, "Production installer forbidden in qualification")
        old = self._json("GET", "/git/commits/" + heads["pages_sha"], credential)
        need(old.get("sha") == heads["pages_sha"], "Old Pages commit identity changed")
        tree = self._json("GET", "/git/trees/" + commit(old.get("tree", {}).get("sha")) + "?recursive=1", credential)
        need(tree.get("truncated") is False and type(tree.get("tree")) is list, "Incomplete old Pages tree")
        seen = set()
        for item in tree["tree"]:
            need(type(item) is dict and item.get("type") in ("blob", "tree"), "Unknown old Pages entry")
            path = core.safe_name(item.get("path")); commit(item.get("sha"))
            need(path not in seen, "Duplicate old Pages path"); seen.add(path)
            if item["type"] == "tree": continue
            need(item.get("mode") == "100644" and path in files, "Historical file deletion/link forbidden")
            if path.endswith((".zip", ".zip.sha256")):
                need(core.git_object("blob", files[path]) == item["sha"], "Historical package modification forbidden")
        tree_sha = core.git_tree(files)
        return {"tree": tree_sha, "commit": core.git_commit(tree_sha, heads["pages_sha"], message),
                "parent": heads["pages_sha"], "message": message,
                "blobs": {n: core.git_object("blob", b) for n, b in sorted(files.items())},
                "mock_only": True, "production_authorized": False}

    def read_commit(self, credential, identity, *, absent=False):
        self._credentials(credential, {"contents": "read"})
        value = self._read_object("/git/commits/" + commit(identity), credential, absent=absent)
        if value is None: return None
        need(value.get("sha") == identity and type(value.get("tree")) is dict and
             type(value.get("parents")) is list and len(value["parents"]) <= 2, "Unexpected Git commit response")
        commit(value["tree"].get("sha"))
        for parent in value["parents"]:
            need(type(parent) is dict, "Malformed Git parent"); commit(parent.get("sha"))
        return value

    def read_tree(self, credential, identity, *, absent=False):
        self._credentials(credential, {"contents": "read"})
        value = self._read_object("/git/trees/" + commit(identity) + "?recursive=1", credential, absent=absent)
        if value is None: return None
        need(value.get("sha") == identity and value.get("truncated") is False and type(value.get("tree")) is list
             and len(value["tree"]) <= 10000, "Incomplete or unexpected Git tree")
        seen = set()
        for item in value["tree"]:
            need(type(item) is dict and type(item.get("path")) is str and item["path"].isascii(), "Malformed Git tree entry")
            name = item["path"]
            core.repo.safe_path(core.ROOT, name, exists=False)
            need(".git" not in Path(name).parts and name.casefold() not in seen, "Unsafe/colliding Git tree path")
            seen.add(name.casefold()); commit(item.get("sha"))
            need((item.get("type"), item.get("mode")) in (("blob", "100644"), ("tree", "040000")),
                 "Executable/link/special Git tree entry is unsupported")
        return value

    def read_blob(self, credential, identity, expected_sha256=None, *, absent=False):
        self._credentials(credential, {"contents": "read"})
        value = self._read_object("/git/blobs/" + commit(identity), credential, absent=absent)
        if value is None: return None
        need(value.get("sha") == identity and value.get("encoding") == "base64" and type(value.get("content")) is str,
             "Malformed Git blob response")
        try: raw = base64.b64decode("".join(value["content"].split()), validate=True)
        except Exception: raise ValueError("Invalid Git blob encoding") from None
        need(type(value.get("size")) is int and value["size"] == len(raw) <= MAX_ASSET and
             core.git_object("blob", raw) == identity, "Git blob bytes mismatch")
        if expected_sha256 is not None: need(core.sha(raw) == checksum(expected_sha256), "Git blob SHA-256 mismatch")
        return raw

    def read_tag(self, credential, tag, *, absent=False):
        self._credentials(credential, {"contents": "read"}); tag_name(tag)
        value = self._ref(credential, "tags/" + tag, absent=absent)
        if value is None: return None
        return {"tag": tag, "commit": self._tag_commit(credential, tag), "ref": value,
                "mock_only": True, "production_authorized": False}

    def read_release(self, credential, release_id, tag):
        self._credentials(credential, {"contents": "read"})
        return self._release(credential, release_id, tag)

    def read_assets(self, credential, release_id):
        self._credentials(credential, {"contents": "read"})
        values = [self._asset(v) for v in self._list(credential, f"/releases/{number(release_id)}/assets")]
        need(len({v["id"] for v in values}) == len(values) and len({v["name"] for v in values}) == len(values),
             "Duplicate asset identity")
        return values

    def read_ledger_pr(self, credential, identity):
        self._credentials(credential, {"pull_requests": "read"})
        value = self._json("GET", "/pulls/" + str(number(identity)), credential)
        need(number(value.get("number")) == identity, "Unexpected ledger PR number")
        for key in ("head", "base"):
            part = value.get(key, {})
            need(type(part) is dict and number(part.get("repo", {}).get("id")) == self.enrolled["repository_id"],
                 "Foreign ledger PR repository")
        need(value["base"].get("ref") == "main" and LEDGER_BRANCH.fullmatch(value["head"].get("ref", "")),
             "Ledger PR branch scope differs")
        commit(value["head"].get("sha")); commit(value["base"].get("sha"))
        return value

    def read_pages_build(self, credential):
        self._credentials(credential, {"pages": "read"})
        value = self._json("GET", "/pages/builds/latest", credential)
        commit(value.get("commit"))
        need(value.get("status") in ("queued", "building", "built", "errored"), "Unknown Pages build status")
        return value

    def read_ledger_reviews(self, credential, identity):
        self._credentials(credential, {"pull_requests": "read"})
        return self._list(credential, f"/pulls/{number(identity)}/reviews")

    def find_ledger_pr(self, credential, branch, target):
        """Read-only recovery lookup; absence never causes an automatic POST."""
        self._credentials(credential, {"pull_requests": "read"})
        need(type(branch) is str and LEDGER_BRANCH.fullmatch(branch), "Unapproved ledger lookup branch")
        commit(target)
        head = quote(self.enrolled["repository"].split("/")[0] + ":" + branch, safe="")
        values = self._list(credential, "/pulls?state=all&head=" + head + "&base=main")
        need(len(values) <= 1, "Ambiguous ledger PR lookup")
        if not values: return None
        value = values[0]
        need(type(value) is dict and number(value.get("number")) and value.get("state") in ("open", "closed"),
             "Malformed ledger PR lookup result")
        for key, expected in (("head", branch), ("base", "main")):
            part = value.get(key)
            need(type(part) is dict and part.get("ref") == expected and type(part.get("repo")) is dict and
                 number(part["repo"].get("id")) == self.enrolled["repository_id"], "Foreign ledger PR lookup result")
            commit(part.get("sha"))
        need(value["head"]["sha"] == target, "Ledger PR lookup head differs")
        return value

    def read_public(self, path, expected_sha256, *, mime=None):
        """Bounded public HEAD/GET at enrolled Pages origin, without credentials."""
        enrollment(self.enrolled)
        checksum(expected_sha256)
        need(type(path) is str and (path == "" or core.safe_name(path)), "Unsafe public path")
        url = self.enrolled["origin"] + path
        receipts = []; raw = None
        for method in ("HEAD", "GET"):
            try: response = self.sender.send(method, url, {}, b"")
            except Exception: raise ValueError("Mock public observation failed") from None
            need(type(response) is MockResponse and response.status == 200 and type(response.body) is bytes,
                 "Public redirect/error response rejected")
            content_type = response.headers.get("Content-Type", response.headers.get("content-type", ""))
            need(type(content_type) is str and len(response.body) <= MAX_ASSET, "Oversized/malformed public response")
            if mime is not None: need(content_type.split(";", 1)[0].strip().lower() == mime, "Public MIME mismatch")
            elif path.endswith((".zip", ".xml", ".sha256")):
                need("html" not in content_type.lower(), "HTML substitute for public artifact")
            if method == "GET": raw = response.body
            receipts.append({"method": method, "status": 200})
        need(core.sha(raw) == expected_sha256, "Public artifact bytes mismatch")
        return {"path": path, "sha256": expected_sha256, "size": len(raw), "responses": receipts,
                "mock_only": True, "production_authorized": False}

    def inspect_policy(self, credential):
        self._credentials(credential, {"administration": "read", "actions": "read", "contents": "read"})
        self._repo(credential)
        rules = []; seen = set()
        for item in self._list(credential, "/rulesets?includes_parents=true"):
            identity = number(item.get("id")); need(identity not in seen, "Duplicate ruleset identity"); seen.add(identity)
            detail = self._json("GET", "/rulesets/" + str(identity), credential)
            need(number(detail.get("id")) == identity and
                 {"name", "target", "enforcement", "bypass_actors", "conditions", "rules"} <= set(detail) and
                 type(detail["bypass_actors"]) is list and type(detail["rules"]) is list,
                 "Ruleset detail/bypass visibility incomplete")
            rules.append(detail)
        environments = {name: self._json("GET", "/environments/" + name, credential)
                        for name in ("kodi-d3-publication", "github-pages")}
        result = {"rulesets": rules, "environments": environments, "mock_only": True, "production_authorized": False}
        result["policy_sha256"] = core.sha(core.canonical(result))
        result["sha256"] = result["policy_sha256"]
        return result

    def read_absent(self, path):
        """Verify reviewed contamination canaries remain absent at the pilot origin."""
        enrollment(self.enrolled); core.safe_name(path)
        for method in ("HEAD", "GET"):
            try: response = self.sender.send(method, self.enrolled["origin"] + path, {}, b"")
            except Exception: raise ValueError("Mock excluded-path observation failed") from None
            need(type(response) is MockResponse and type(response.status) is int and response.status == 404,
                 "Excluded path is unexpectedly public")
        return {"path": path, "status": "ABSENT", "mock_only": True, "production_authorized": False}

    def _collection(self, credential, path, key):
        result = []; total = None
        for page in range(1, MAX_PAGES + 1):
            response = self._request("GET", path + f"?per_page=100&page={page}", credential)
            value = parse_json(response.body)
            need(type(value) is dict and type(value.get("total_count")) is int and value["total_count"] >= 0 and
                 type(value.get(key)) is list and len(value[key]) <= 100, "Malformed paginated collection")
            if total is None: total = value["total_count"]
            need(value["total_count"] == total, "Collection changed during pagination")
            result.extend(value[key]); link = response.headers.get("Link", "")
            need(type(link) is str, "Invalid collection pagination")
            if 'rel="next"' not in link:
                need(len(result) == total, "Incomplete paginated collection")
                return result
            expected = API + self.prefix + path + f"?per_page=100&page={page + 1}"
            need(f'<{expected}>; rel="next"' in link, "Foreign collection pagination")
        raise ValueError("Collection exceeds page bound")

    def observe_owner_proof(self, credential, enrolled, run_id):
        """Raw, bounded mock observations for the independent owner verifier."""
        import publication_d3_contract as contract
        contract.validate_enrollment(enrolled)
        need(core.canonical(contract.transport_enrollment(enrolled)) == core.canonical(self.enrolled),
             "Owner-proof transport enrollment differs")
        self._credentials(credential, {"actions": "read", "contents": "read", "administration": "read", "pull_requests": "read"})
        self._repo(credential); number(run_id)
        run = self._json("GET", f"/actions/runs/{run_id}", credential)
        workflow = self._json("GET", f'/actions/workflows/{enrolled["workflow_id"]}', credential)
        envpath = "/environments/" + enrolled["environment_name"]
        environment = self._json("GET", envpath, credential)
        environment_branches = self._collection(credential, envpath + "/deployment-branch-policies", "branch_policies")
        reviews = parse_json(self._request("GET", f"/actions/runs/{run_id}/approvals", credential).body)
        need(type(reviews) is list and len(reviews) <= 100, "Malformed approval history")
        jobs = self._collection(credential, f"/actions/runs/{run_id}/jobs", "jobs")
        artifacts = self._collection(credential, f"/actions/runs/{run_id}/artifacts", "artifacts")
        matching = [a for a in artifacts if type(a) is dict and a.get("name") == "d3-approval-request"]
        need(len(matching) == 1 and matching[0].get("expired") is False, "Scope artifact missing/ambiguous/expired")
        metadata = matching[0]; identity = number(metadata.get("id"))
        suffix = f"/actions/artifacts/{identity}/zip"
        archive = self._request("GET", suffix, credential, binary=True, statuses=(200, 302))
        if archive.status == 302:
            location = archive.headers.get("Location")
            need(type(location) is str, "Missing artifact redirect")
            archive = self._request("GET", suffix, credential, binary=True, absolute=location)
        need(len(archive.body) <= MAX_JSON, "Oversized approval archive")
        workflow_file = self._json("GET", "/contents/" + enrolled["workflow_path"] + "?ref=" + enrolled["workflow_commit"], credential)
        control = self._json("GET", f'/issues/{enrolled["control_issue_number"]}', credential)
        comments = self._list(credential, f'/issues/{enrolled["control_issue_number"]}/comments')
        return {"run": run, "workflow": workflow, "environment": environment,
                "environment_branches": environment_branches, "review_history": reviews, "jobs": jobs,
                "artifact_metadata": metadata, "artifact_archive": archive.body, "workflow_file": workflow_file,
                "revocation_comments": comments, "control_issue": control,
                "mock_only": True, "source": "scripted-mock-transport", "production_authorized": False}

    def observe_pages_proof(self, credential, enrolled, run_id):
        """Separate Pages environment review observations, never an approval action."""
        import publication_d3_contract as contract
        contract.validate_enrollment(enrolled)
        need(core.canonical(contract.transport_enrollment(enrolled)) == core.canonical(self.enrolled),
             "Pages-proof transport enrollment differs")
        self._credentials(credential, {"actions": "read", "contents": "read", "administration": "read", "pull_requests": "read"})
        self._repo(credential); number(run_id)
        run = self._json("GET", f"/actions/runs/{run_id}", credential)
        workflow = self._json("GET", f'/actions/workflows/{enrolled["pages_workflow_id"]}', credential)
        envpath = "/environments/github-pages"
        environment = self._json("GET", envpath, credential)
        branches = self._collection(credential, envpath + "/deployment-branch-policies", "branch_policies")
        reviews = parse_json(self._request("GET", f"/actions/runs/{run_id}/approvals", credential).body)
        need(type(reviews) is list and len(reviews) <= 100, "Malformed Pages approval history")
        jobs = self._collection(credential, f"/actions/runs/{run_id}/jobs", "jobs")
        control = self._json("GET", f'/issues/{enrolled["control_issue_number"]}', credential)
        comments = self._list(credential, f'/issues/{enrolled["control_issue_number"]}/comments')
        return {"run": run, "workflow": workflow, "environment": environment,
                "environment_branches": branches, "review_history": reviews, "jobs": jobs,
                "revocation_comments": comments, "control_issue": control,
                "mock_only": True, "source": "scripted-mock-transport", "production_authorized": False}

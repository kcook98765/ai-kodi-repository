"""Opt-in D3 pilot HTTPS/App transport; importing performs no I/O.

The old mock-only client is unchanged. This sender has no ambient credential,
proxy, arbitrary destination, redirect forwarding, or automatic retry fallback.
Tests use finite serialized HTTP exchanges and never invoke network or real keys.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import http.client
import inspect as signatures
from pathlib import Path
import re
import ssl
import sys
import socket
import threading
import time
from urllib.parse import quote, urlsplit, urlunsplit

sys.path.insert(0, str(Path(__file__).resolve().parent))
import publication_proposal as core
from publication_github import (need, number, commit, checksum, tag_name, asset_name,
                                text, parse_json, API, UPLOADS, API_VERSION,
                                QUAL_REPOSITORY, QUAL_ORIGIN, PRODUCTION_ID,
                                MAX_JSON, MAX_ASSET, MAX_PAGES, LEDGER_BRANCH)

PROFILE = "d3-pr-pilot-v1"
PERMISSIONS = {"contents": "write", "pull_requests": "write", "actions": "read",
               "pages": "read", "administration": "read", "metadata": "read"}


class PendingPagesReadiness(ValueError):
    """A scoped read observed normal asynchronous Pages propagation."""


class PendingPublicBytes(ValueError):
    """The enrolled public path is absent or still serves safe stale bytes."""


def validate_enrollment(value):
    import publication_pilot_contract as contract
    contract.validate_enrollment(value)
    need(value["profile"] == PROFILE and value["repository"] == QUAL_REPOSITORY and
         value["base_url"] == QUAL_ORIGIN and value["branch"] == "gh-pages" and value["path"] == "/",
         "Destination outside enrolled disposable pilot")
    for key in ("repository_id", "owner_id", "app_id", "app_installation_id", "human_owner_id"):
        number(value[key])
    need(value["repository_id"] != PRODUCTION_ID and value["human_owner_id"] == 56806582 and
         value["owner_id"] != value["human_owner_id"], "Production or invalid pilot owner")
    return dict(value)


def permissions(value):
    need(type(value) is dict and value and set(value) <= set(PERMISSIONS), "Permission ceiling exceeded")
    for key, level in value.items():
        need(level in ("read", "write") and (level == "read" or PERMISSIONS[key] == "write"),
             "Permission ceiling exceeded")
    return dict(value)


def expected_policy(e):
    """Pure reviewed semantics. Placeholder ruleset/branch IDs require readback."""
    actor={'actor_id':e['app_id'],'actor_type':'Integration','bypass_mode':'always'}
    tags=['refs/tags/script.ai.kodi.d3.fixture-*','refs/tags/repository.ai.kodi.candidate.*-*']
    pr={'required_approving_review_count':1,'dismiss_stale_reviews_on_push':True,'require_code_owner_review':True,
        'require_last_push_approval':True,'required_review_thread_resolution':True}
    defs=[('main-writer','branch',['refs/heads/main'],[],[actor],[{'type':'update','parameters':{'update_allows_fetch_and_merge':False}}]),
      ('main-integrity','branch',['refs/heads/main'],[],[],[{'type':'pull_request','parameters':pr},{'type':'deletion'},{'type':'non_fast_forward'}]),
      ('main-validation','branch',['refs/heads/main'],[],[],[{'type':'required_status_checks','parameters':{'strict_required_status_checks_policy':True,
        'required_status_checks':[{'context':'qualification-validation','integration_id':e['ci_app_id']}]}}]),
      ('pages-writer','branch',['refs/heads/gh-pages'],[],[actor],[{'type':'update','parameters':{'update_allows_fetch_and_merge':False}}]),
      ('pages-integrity','branch',['refs/heads/gh-pages'],[],[],[{'type':'deletion'},{'type':'non_fast_forward'},{'type':'required_linear_history'}]),
      ('tags-creator','tag',tags,[],[actor],[{'type':'creation'}]),('tags-other-creations','tag',['~ALL'],tags,[],[{'type':'creation'}]),
      ('tags-immutable','tag',['~ALL'],[],[],[{'type':'update'},{'type':'deletion'}])]
    rules=[{'id':i+1,'name':n,'target':t,'enforcement':'active','conditions':{'ref_name':{'include':inc,'exclude':ex}},
            'bypass_actors':a,'rules':r} for i,(n,t,inc,ex,a,r) in enumerate(defs)]
    return {'rulesets':rules,'environments':{'github-pages':{'id':e['pages_environment_id'],'name':'github-pages','can_admins_bypass':False,
      'deployment_branch_policy':{'protected_branches':False,'custom_branch_policies':True},'protection_rules':[]}},
      'pages_branch_policies':[{'id':1,'name':'gh-pages','type':'branch'}],
      'repository':{'allow_merge_commit':True,'allow_squash_merge':False,'allow_rebase_merge':False,'allow_auto_merge':False,
                    'delete_branch_on_merge':False,'allow_update_branch':False},
      'default_actions':{'default_workflow_permissions':'read','can_approve_pull_request_reviews':False},
      'immutable_releases':{'enabled':True,'enforced_by_owner':False}}


def validate_policy(e, observed):
    need(type(observed)is dict,'Complete observed policy required');expected=expected_policy(e)
    need(type(observed.get('rulesets'))is list and len(observed['rulesets'])==8,'Eight reviewed rulesets required')
    known={v['name']:v for v in expected['rulesets']};seen=set();ids=set()
    fields=('name','target','enforcement','conditions','bypass_actors','rules')
    for v in observed['rulesets']:
        need(type(v)is dict and number(v.get('id'))not in ids,'Invalid ruleset identity');ids.add(v['id'])
        n=v.get('name');need(n in known and n not in seen,'Unknown/duplicate ruleset');seen.add(n)
        need(all(k in v for k in fields),'Invisible ruleset integrity/bypass fields')
        need(core.canonical({k:v[k] for k in fields})==core.canonical({k:known[n][k] for k in fields}),
             'Unsafe ruleset writers, bypasses, reviews, checks or immutable history')
    for key in ('repository','default_actions'):
        need(core.canonical(observed.get(key))==core.canonical(expected[key]),'Unsafe '+key+' settings')
    immutable=observed.get('immutable_releases')
    need(type(immutable)is dict and immutable.get('enabled')is True and type(immutable.get('enforced_by_owner'))is bool,
         'Future immutable Releases are not enabled')
    envs=observed.get('environments');need(type(envs)is dict and set(envs)=={'github-pages'},'Wrong Pages environment scope')
    env=envs['github-pages'];target=expected['environments']['github-pages']
    need(type(env)is dict and type(env.get('id'))is int and env['id']==e['pages_environment_id'] and
         all(core.canonical(env.get(k))==core.canonical(v) for k,v in target.items() if k!='protection_rules'),
         'Unsafe Pages environment')
    protections=env.get('protection_rules')
    need(type(protections)is list and len(protections)<=1,'Unexpected Pages review/protection gate')
    for rule in protections:
        need(type(rule)is dict and rule.get('type')=='branch_policy' and
             ('id' not in rule or number(rule['id'])),'Unexpected Pages review/protection gate')
    b=observed.get('pages_branch_policies')
    need(type(b)is list and len(b)==1 and type(b[0])is dict and number(b[0].get('id')) and
         b[0].get('name')=='gh-pages' and b[0].get('type')=='branch','Pages must select only gh-pages')
    return observed


@dataclass(frozen=True)
class HTTPResponse:
    status: int
    body: bytes = field(default=b"", repr=False)
    headers: dict = field(default_factory=dict, repr=False)

    @classmethod
    def json(cls, status, value, headers=None):
        return cls(status, core.canonical(value), headers or {})


@dataclass(frozen=True)
class HTTPExchange:
    method: str
    url: str = field(repr=False)
    response: HTTPResponse = field(repr=False)
    body: object = field(default=None, repr=False)


class ScriptedHTTPS:
    """Finite mock HTTP at the serialization boundary; no network fallback."""
    transport_origin = "scripted-mock-https"

    def __init__(self, exchanges):
        need(type(exchanges) is list and all(type(e) is HTTPExchange for e in exchanges), "Scripted HTTP exchanges required")
        self._exchanges = list(exchanges)
        self.requests = []

    def send(self, method, url, headers, body, *, max_size):
        self.requests.append({"method": method, "url": urlunsplit((*urlsplit(url)[:3], "", "")),
                              "body_sha256": core.sha(body), "size": len(body),
                              "authenticated": "Authorization" in headers})
        need(self._exchanges, "Unscripted HTTP request; no network fallback")
        item = self._exchanges.pop(0)
        need((method, url) == (item.method, item.url), "Unexpected HTTP request shape")
        if item.body is not None:
            wanted = item.body if type(item.body) is bytes else core.canonical(item.body)
            need(body == wanted, "Unexpected HTTP request body")
        need(type(item.response) is HTTPResponse and type(item.response.status) is int and
             type(item.response.body) is bytes and len(item.response.body) <= max_size,
             "Malformed or oversized HTTP response")
        return item.response

    @property
    def remaining(self): return len(self._exchanges)


def _url(url, *, allow_storage=False):
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except Exception:
        raise ValueError("Invalid HTTPS destination") from None
    hosts = {"api.github.com", "uploads.github.com", "kcook98765-kodi-qualification.github.io"}
    storage = parsed.hostname == "release-assets.githubusercontent.com" or (
        parsed.hostname is not None and parsed.hostname.endswith(".blob.core.windows.net"))
    need(parsed.scheme == "https" and (parsed.hostname in hosts or allow_storage and storage),
         "HTTPS host outside pilot allowlist")
    need(parsed.username is None and parsed.password is None and port is None and not parsed.fragment and
         parsed.netloc == parsed.hostname and parsed.path.startswith("/") and
         not any(c in url for c in ("\r", "\n", "\0")), "Noncanonical HTTPS destination")
    return parsed


class HTTPSBackend:
    """One TLS-verified request; no automatic redirects, proxies, or retries."""
    transport_origin = "github-https"

    def __init__(self, *, timeout=15):
        need(type(timeout) in (int, float) and 1 <= timeout <= 30, "Invalid bounded HTTPS timeout")
        self.timeout = timeout

    def send(self, method, url, headers, body, *, max_size):
        parsed = _url(url, allow_storage=True)
        need(method in ("GET", "HEAD", "POST", "PATCH", "PUT") and type(body) is bytes and
             len(body) <= MAX_ASSET and type(max_size) is int and 0 < max_size <= MAX_ASSET,
             "Invalid bounded HTTPS request")
        need(type(headers) is dict and set(headers) <= {"Accept", "Authorization", "X-GitHub-Api-Version",
                                                       "Content-Type", "Content-Length", "User-Agent"},
             "Unsupported HTTPS request headers")
        need(all(type(v) is str and not any(c in v for c in ("\r", "\n", "\0")) for v in headers.values()),
             "Unsafe HTTPS header")
        need("Authorization" not in headers or parsed.hostname in ("api.github.com", "uploads.github.com"),
             "Credential forwarding to non-API host forbidden")
        connection = None
        timer = None
        active_response = [None]
        deadline = time.monotonic() + self.timeout
        try:
            context = ssl.create_default_context()
            context.minimum_version = ssl.TLSVersion.TLSv1_2
            connection = http.client.HTTPSConnection(parsed.hostname, timeout=self.timeout, context=context)
            # A request deadline supplements socket timeouts, which otherwise
            # restart under a slow trickle. No persistent worker is retained.
            def interrupt():
                active = connection.sock
                if active is None and active_response[0] is not None:
                    active = getattr(getattr(active_response[0].fp, "raw", None), "_sock", None)
                if active is not None:
                    try: active.shutdown(socket.SHUT_RDWR)
                    except OSError: pass
                connection.close()
            timer = threading.Timer(self.timeout, interrupt)
            timer.daemon = True
            timer.start()
            path = parsed.path + ("?" + parsed.query if parsed.query else "")
            connection.request(method, path, body=body, headers=headers)
            response = connection.getresponse()
            active_response[0] = response
            lengths = response.headers.get_all("Content-Length", [])
            need(len(lengths) <= 1 and (not lengths or lengths[0].isdigit() and int(lengths[0]) <= max_size),
                 "Oversized or ambiguous HTTP length")
            raw = response.read(max_size + 1)
            need(time.monotonic() <= deadline and len(raw) <= max_size and
                 (method == "HEAD" or not lengths or len(raw) == int(lengths[0])),
                 "Incomplete or oversized HTTP response")
            return HTTPResponse(response.status, raw, dict(response.getheaders()))
        except Exception:
            raise ValueError("HTTPS operation failed; remote outcome may require read-only reconciliation") from None
        finally:
            if timer is not None: timer.cancel()
            if connection is not None: connection.close()


class ExplicitRS256Key:
    """Caller supplies PEM bytes; no key path or environment lookup exists."""
    def __init__(self, pem_bytes):
        need(type(pem_bytes) is bytes and 0 < len(pem_bytes) < 32768, "Explicit private-key bytes required")
        self._pem = pem_bytes

    def sign_rs256(self, raw):
        try:
            from cryptography.hazmat.primitives import hashes, serialization
            from cryptography.hazmat.primitives.asymmetric import padding, rsa
            key = serialization.load_pem_private_key(self._pem, password=None)
            need(isinstance(key, rsa.RSAPrivateKey) and key.key_size >= 2048, "Unsupported App signing key")
            return key.sign(raw, padding.PKCS1v15(), hashes.SHA256())
        except Exception:
            raise ValueError("App signing failed") from None


def _b64(raw): return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


@dataclass(frozen=True)
class _Token:
    value: str = field(repr=False)
    expires_at: str
    permissions: dict


class AppTokenProvider:
    """Explicit App-only installation credentials; no GH/ambient auth fallback."""
    def __init__(self, enrolled, key_provider, backend, *, clock=None):
        self.enrolled = validate_enrollment(enrolled)
        need(callable(getattr(key_provider, "sign_rs256", None)), "Explicit RS256 key provider required")
        need(type(backend) in (HTTPSBackend, ScriptedHTTPS), "Concrete bounded HTTPS backend required")
        self.key_provider, self.backend = key_provider, backend
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self._tokens = {}

    def _app_json(self, method, path, jwt, body=None, status=200):
        headers = {"Accept": "application/vnd.github+json", "Authorization": "Bearer " + jwt,
                   "X-GitHub-Api-Version": API_VERSION, "User-Agent": "ai-kodi-d3-pilot"}
        raw = b"" if body is None else core.canonical(body)
        if body is not None: headers["Content-Type"] = "application/json"
        try: result = self.backend.send(method, API + path, headers, raw, max_size=MAX_JSON)
        except Exception: raise ValueError("App credential request failed") from None
        need(type(result) is HTTPResponse and result.status == status, "App credential request rejected")
        result = parse_json(result.body); need(type(result) is dict, "Malformed App response")
        return result

    def token(self, caps):
        validate_enrollment(self.enrolled); caps = dict(permissions(caps), metadata="read")
        now = core.timestamp(self.clock()); cache = tuple(sorted(caps.items()))
        retained = self._tokens.get(cache)
        if retained and now + timedelta(seconds=30) < core.timestamp(retained.expires_at): return retained
        claims = {"iat": int(now.timestamp()) - 60, "exp": int(now.timestamp()) + 540,
                  "iss": str(self.enrolled["app_id"])}
        raw = (_b64(core.canonical({"alg": "RS256", "typ": "JWT"})) + "." + _b64(core.canonical(claims))).encode()
        try: signature = self.key_provider.sign_rs256(raw)
        except Exception: raise ValueError("App signing failed") from None
        need(type(signature) is bytes and 0 < len(signature) <= 1024, "Invalid App signature")
        jwt = raw.decode() + "." + _b64(signature)
        app = self._app_json("GET", "/app", jwt)
        need(number(app.get("id")) == self.enrolled["app_id"] and
             number(app.get("owner", {}).get("id")) == self.enrolled["owner_id"] and
             app.get("owner", {}).get("type") == "Organization", "App identity mismatch")
        permissions(app.get("permissions"))
        installation = self._app_json("GET", "/app/installations/" + str(self.enrolled["app_installation_id"]), jwt)
        need(number(installation.get("id")) == self.enrolled["app_installation_id"] and
             number(installation.get("app_id")) == self.enrolled["app_id"] and
             installation.get("repository_selection") == "selected" and installation.get("suspended_at") is None and
             number(installation.get("account", {}).get("id")) == self.enrolled["owner_id"] and
             installation.get("account", {}).get("type") == "Organization", "App installation identity mismatch")
        permissions(installation.get("permissions"))
        value = self._app_json("POST", "/app/installations/" + str(self.enrolled["app_installation_id"]) + "/access_tokens",
                               jwt, {"repository_ids": [self.enrolled["repository_id"]], "permissions": caps}, status=201)
        granted = value.get("permissions"); permissions(granted)
        need(core.canonical(granted) == core.canonical(caps) and value.get("repository_selection") == "selected",
             "Installation token permission/repository scope mismatch")
        repos = value.get("repositories")
        need(type(repos) is list and len(repos) == 1 and number(repos[0].get("id")) == self.enrolled["repository_id"] and
             repos[0].get("full_name") == QUAL_REPOSITORY, "Installation token destination mismatch")
        expiry = core.timestamp(value.get("expires_at"))
        observed = core.timestamp(self.clock())
        need(observed < expiry <= observed + timedelta(hours=1), "Invalid installation token lifetime")
        token = value.get("token")
        need(type(token) is str and 1 <= len(token) <= 1024 and re.fullmatch(r"[A-Za-z0-9_.-]+", token),
             "Malformed installation token")
        result = _Token(token, core.utc(expiry), granted); self._tokens[cache] = result
        return result


@dataclass
class BoundScope:
    """Sealed contract source; caller-created booleans do not supply authority."""
    path: Path
    kind: str
    binding_sha256: str | None = None
    # Runtime transaction context, populated only after the coordinator durably
    # consumes this owner review. It is not read from proposal/approval JSON.
    claimed_review_id: int | None = None

    @classmethod
    def load(cls, path, kind, *, now=None):
        import publication_pilot_contract as contract
        value = contract.transport_authority(path, kind=kind, now=now)
        return cls(Path(path).resolve(), kind, core.sha(core.canonical(value)))

    def verify(self, method, arguments, enrolled, now):
        import publication_pilot_contract as contract
        if self.kind == "publication":
            need(type(self.claimed_review_id) is int and 0 < self.claimed_review_id < 2**53,
                 "A durably claimed owner review is required")
        value = contract.transport_authority(self.path, kind=self.kind, now=now)
        observed = core.sha(core.canonical(value))
        if self.binding_sha256 is None: self.binding_sha256 = observed
        need(observed == self.binding_sha256, "Frozen authority changed")
        need(value.get("schema") == 1 and value.get("profile") == PROFILE and
             value.get("kind") == self.kind and self.kind in ("preparation", "publication") and
             type(value.get("repository_id")) is int and value["repository_id"] == enrolled["repository_id"],
             "Publication authority destination/type mismatch")
        need(core.timestamp(now) < core.timestamp(value["expires_at"]), "Publication authority expired")
        digest = core.sha(core.canonical(effect_arguments(method, arguments)))
        need(digest in value["effects"].get(method, []), "Effect outside exact frozen authority")
        return value


def effect_arguments(method, arguments):
    result = dict(arguments)
    for key in ("scope", "credential"): result.pop(key, None)
    # These IDs cannot exist until a draft is created. The frozen tag and strict
    # release readback bind the returned numeric object before its individual use.
    if method in ("upload_asset", "publish_release"): result.pop("release_id", None)
    if method == "publish_release":
        result["assets"] = {name: {k: item[k] for k in ("size", "sha256")}
                            for name, item in result["assets"].items()}
    if method == "create_blob" and result.get("expected_sha") is None:
        result["expected_sha"] = core.git_object("blob", result["data"])
    if "data" in result:
        raw = result["data"]; need(type(raw) is bytes, "Frozen binary effect input required")
        result["data"] = {"size": len(raw), "sha256": core.sha(raw)}
    return result


@dataclass
class _Access:
    caps: dict
    scope: BoundScope | None = None
    effect: str | None = None
    arguments: dict | None = None


class _ValidatedObjects:
    """Response validators/builders reused as source, with distinct live receipts."""
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
        need(type(page) is dict and page.get("html_url") == self.enrolled["base_url"] and page.get("https_enforced") is True and
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
        result = {"profile": PROFILE, "mock_only": self.mock_only, "transport_origin": self.transport_origin, "production_authorized": False,
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
        return {"tag": tag, "commit": target, "mock_only": self.mock_only, "transport_origin": self.transport_origin, "production_authorized": False}

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
        return {"id": value["id"], "tag": tag, "mock_only": self.mock_only, "transport_origin": self.transport_origin, "production_authorized": False}

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
        return dict(actual, mock_only=self.mock_only, transport_origin=self.transport_origin, production_authorized=False)

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
                "mock_only": self.mock_only, "transport_origin": self.transport_origin, "production_authorized": False}

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
        return {"id": release_id, "tag": tag, "immutable": True, "mock_only": self.mock_only, "transport_origin": self.transport_origin, "production_authorized": False}

    def create_blob(self, credential, heads, data, expected_sha=None):
        self._credentials(credential, {"contents": "write"})
        need(type(data) is bytes and len(data) <= MAX_ASSET, "Invalid bounded Git blob")
        expected = core.git_object("blob", data)
        need(expected_sha is None or commit(expected_sha) == expected, "Frozen blob identity mismatch")
        self._preflight(credential, heads)
        body = {"encoding": "base64", "content": base64.b64encode(data).decode("ascii")}
        value = self._json("POST", "/git/blobs", credential, body=body, statuses=(201,))
        need(value.get("sha") == expected, "Created Git blob mismatch")
        return {"sha": expected, "mock_only": self.mock_only, "transport_origin": self.transport_origin, "production_authorized": False}

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
        return {"sha": expected_tree, "mock_only": self.mock_only, "transport_origin": self.transport_origin, "production_authorized": False}

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
        return {"sha": expected_sha, "tree": tree, "parent": parent, "mock_only": self.mock_only, "transport_origin": self.transport_origin, "production_authorized": False}

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
        return {"sha": target, "parent": parent, "tree": tree, "force": False, "mock_only": self.mock_only, "transport_origin": self.transport_origin, "production_authorized": False}

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
        return {"branch": branch, "sha": target, "mock_only": self.mock_only, "transport_origin": self.transport_origin, "production_authorized": False}

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
                "state": "PUBLIC_BUT_UNRECONCILED", "mock_only": self.mock_only, "transport_origin": self.transport_origin, "production_authorized": False}

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
                "mock_only": self.mock_only, "transport_origin": self.transport_origin, "production_authorized": False}

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
                "mock_only": self.mock_only, "transport_origin": self.transport_origin, "production_authorized": False}

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

    def read_public(self, path, expected_sha256, *, mime=None, previous_sha256=None):
        """Bounded public HEAD/GET at enrolled Pages origin, without credentials."""
        validate_enrollment(self.enrolled)
        checksum(expected_sha256)
        if previous_sha256 is not None: checksum(previous_sha256)
        need(type(path) is str and (path == "" or core.safe_name(path)), "Unsafe public path")
        url = self.enrolled["base_url"] + path
        receipts = []; raw = None
        mutable = path in ("", "index.html") or re.fullmatch(
            r"(?:(?:matrix|nexus|omega|piers)/)?(?:index\.html|addons\.xml(?:\.(?:md5|sha256))?)|"
            r"candidate/catalogs/(?:matrix|nexus|omega|piers)/addons\.xml(?:\.(?:md5|sha256))?", path)
        pending_mimes = {"text/html"} if path == "" or path.endswith(".html") else (
            {"application/xml", "text/xml"} if path.endswith(".xml") else (
                {"text/plain", "application/octet-stream"} if path.endswith((".md5", ".sha256")) else set()))
        safe_for_pending = mime is not None or bool(pending_mimes)
        for method in ("HEAD", "GET"):
            try: response = self.backend.send(method, url, {}, b"", max_size=MAX_ASSET)
            except Exception: raise ValueError("Public HTTPS observation failed") from None
            need(type(response) is HTTPResponse and type(response.status) is int and type(response.body) is bytes and
                 len(response.body) <= MAX_ASSET, "Malformed public response")
            if response.status == 404:
                raise PendingPublicBytes("Approved public path is not available yet")
            need(response.status == 200,
                 "Public redirect/error response rejected")
            content_type = response.headers.get("Content-Type", response.headers.get("content-type", ""))
            need(type(content_type) is str and len(response.body) <= MAX_ASSET, "Oversized/malformed public response")
            if mime is not None: need(content_type.split(";", 1)[0].strip().lower() == mime, "Public MIME mismatch")
            elif path.endswith((".zip", ".xml", ".sha256")):
                need("html" not in content_type.lower(), "HTML substitute for public artifact")
            if mime is None:
                safe_for_pending = safe_for_pending and content_type.split(";", 1)[0].strip().lower() in pending_mimes
            if method == "GET": raw = response.body
            receipts.append({"method": method, "status": 200})
        if core.sha(raw) != expected_sha256 and mutable and safe_for_pending and previous_sha256 == core.sha(raw):
            raise PendingPublicBytes("Mutable approved path still serves its exact known previous bytes")
        need(core.sha(raw) == expected_sha256, "Public artifact bytes mismatch")
        return {"path": path, "sha256": expected_sha256, "size": len(raw), "responses": receipts,
                "mock_only": self.mock_only, "transport_origin": self.transport_origin, "production_authorized": False}

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
                        for name in ("github-pages",)}
        result = {"rulesets": rules, "environments": environments, "mock_only": self.mock_only, "transport_origin": self.transport_origin, "production_authorized": False}
        result["policy_sha256"] = core.sha(core.canonical({"rulesets": rules, "environments": environments}))
        result["sha256"] = result["policy_sha256"]
        return result

    def read_absent(self, path):
        """Verify reviewed contamination canaries remain absent at the pilot origin."""
        validate_enrollment(self.enrolled); core.safe_name(path)
        for method in ("HEAD", "GET"):
            try: response = self.backend.send(method, self.enrolled["base_url"] + path, {}, b"", max_size=MAX_ASSET)
            except Exception: raise ValueError("Excluded-path HTTPS observation failed") from None
            need(type(response) is HTTPResponse and type(response.status) is int and response.status == 404,
                 "Excluded path is unexpectedly public")
        return {"path": path, "status": "ABSENT", "mock_only": self.mock_only, "transport_origin": self.transport_origin, "production_authorized": False}



class PilotGitHub(_ValidatedObjects):
    """Explicit pilot backend with exact sealed authority for every write."""
    def __init__(self, enrolled, token_provider, backend, *, clock=None):
        self.enrolled = validate_enrollment(enrolled)
        need(type(backend) in (HTTPSBackend, ScriptedHTTPS), "Concrete bounded HTTPS backend required")
        need(type(token_provider) is AppTokenProvider and token_provider.backend is backend and
             core.canonical(token_provider.enrolled) == core.canonical(self.enrolled),
             "Explicit destination-bound App token provider required")
        self.provider, self.backend = token_provider, backend
        self.enrollment = self.enrolled
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.prefix = "/repos/" + QUAL_REPOSITORY
        self.transport_origin = backend.transport_origin
        self.mock_only = type(backend) is ScriptedHTTPS

    def _credentials(self, access, caps):
        validate_enrollment(self.enrolled)
        need(type(access) is _Access and core.canonical(access.caps) == core.canonical(caps),
             "Internal exact operation access required")
        permissions(caps)

    def _caps(self, method, suffix):
        if method not in ("GET", "HEAD"):
            if suffix.startswith("/pulls") and not suffix.endswith("/merge"): return {"pull_requests": "write"}
            return {"contents": "write"}
        if suffix.startswith(("/pulls", "/issues")): return {"pull_requests": "read"}
        if suffix == "/actions/permissions/workflow": return {"administration": "read"}
        if suffix.startswith("/actions/"): return {"actions": "read"}
        if suffix.startswith("/pages"): return {"pages": "read"}
        if suffix.startswith("/environments/"): return {"actions": "read"}
        if suffix.startswith(("/rulesets", "/immutable-releases")): return {"administration": "read"}
        return {"contents": "read"}

    def _request(self, method, suffix, access, *, body=None, statuses=(200,), upload=False, binary=False, absolute=None):
        validate_enrollment(self.enrolled)
        need(self.prefix == "/repos/" + QUAL_REPOSITORY and type(access) is _Access, "Transport binding changed")
        need(method in ("GET", "POST", "PATCH", "PUT"), "Mutation method forbidden")
        routes = (
            r"", r"/pages", r"/git/ref/heads/(?:main|gh-pages|d3-fixture-source)",
            r"/git/ref/tags/[A-Za-z0-9_.-]+", r"/git/tags/[0-9a-f]{40}",
            r"/git/commits/[0-9a-f]{40}", r"/git/trees/[0-9a-f]{40}\?recursive=1",
            r"/releases(?:\?per_page=100&page=[0-9]+)?", r"/releases/tags/[A-Za-z0-9_.-]+",
            r"/releases/[0-9]+", r"/releases/[0-9]+/assets(?:\?per_page=100&page=[0-9]+|\?name=[A-Za-z0-9_.-]+)?",
            r"/releases/assets/[0-9]+", r"/git/(?:refs|blobs|trees|commits)",
            r"/git/blobs/[0-9a-f]{40}", r"/pages/builds/latest", r"/pulls/[0-9]+(?:/reviews\?per_page=100&page=[0-9]+)?",
            r"/actions/runs/[0-9]+(?:/approvals|/jobs\?per_page=100&page=[0-9]+|/artifacts\?per_page=100&page=[0-9]+)?",
            r"/actions/workflows/[0-9]+", r"/actions/artifacts/[0-9]+/zip", r"/actions/permissions/workflow",r"/immutable-releases",
            r"/actions/workflows/[0-9]+/runs\?head_sha=[0-9a-f]{40}(?:&status=completed)?&per_page=100&page=[0-9]+",
            r"/environments/(?:kodi-d3-publication|github-pages)(?:/deployment-branch-policies\?per_page=100&page=[0-9]+)?",
            r"/issues/[0-9]+(?:/comments\?per_page=100&page=[0-9]+)?",
            r"/rulesets\?includes_parents=true&per_page=100&page=[0-9]+", r"/rulesets/[0-9]+",
            r"/contents/\.github/workflows/qualification-validation\.yml\?ref=[0-9a-f]{40}",
            r"/git/refs/heads/gh-pages", r"/pulls", r"/pulls/[0-9]+/merge", r"/git/ref/heads/publication-ledger/[0-9a-f]{64}",
            r"/pulls\?state=all&head=kcook98765-kodi-qualification%3Apublication-ledger%2F[0-9a-f]{64}&base=main&per_page=100&page=[0-9]+")
        need(type(suffix) is str and any(re.fullmatch(route, suffix) for route in routes), "Endpoint outside allowlist")
        if method == "POST":
            need(suffix in ("/git/refs", "/git/blobs", "/git/trees", "/git/commits", "/releases", "/pulls") or
                 re.fullmatch(r"/releases/[0-9]+/assets\?name=[A-Za-z0-9_.-]+", suffix), "POST endpoint denied")
        if method == "PATCH":
            need(suffix == "/git/refs/heads/gh-pages" or re.fullmatch(r"/(?:releases|pulls)/[0-9]+", suffix), "PATCH endpoint denied")

        if method == "PUT":
            need(re.fullmatch(r"/pulls/[0-9]+/merge", suffix), "PUT endpoint denied")
        if upload: need(method == "POST" and "/assets?name=" in suffix, "Upload scope denied")
        url = (UPLOADS if upload else API) + self.prefix + suffix
        headers = {"Accept": "application/octet-stream" if binary else "application/vnd.github+json",
                   "X-GitHub-Api-Version": API_VERSION, "User-Agent": "ai-kodi-d3-pilot"}
        if absolute is not None:
            parsed = _url(absolute, allow_storage=True)
            allowed = parsed.hostname == "release-assets.githubusercontent.com" or (
                suffix.startswith("/actions/artifacts/") and parsed.hostname.endswith(".blob.core.windows.net"))
            need(binary and method == "GET" and allowed, "Unexpected download redirect destination")
            url = absolute
        else:
            if method not in ("GET", "HEAD"):
                need(type(access.scope) is BoundScope, "Sealed write scope required")
                access.scope.verify(access.effect, access.arguments, self.enrolled, self.clock())
            token = self.provider.token(self._caps(method, suffix))
            need(core.timestamp(self.clock()) < core.timestamp(token.expires_at), "Installation credential expired")
            if method not in ("GET", "HEAD"): self._before_write(access)
            headers["Authorization"] = "Bearer " + token.value
        raw = b"" if body is None else body if type(body) is bytes else core.canonical(body)
        if body is not None: headers["Content-Type"] = "application/octet-stream" if type(body) is bytes else "application/json"
        try: response = self.backend.send(method, url, headers, raw, max_size=MAX_ASSET if binary else MAX_JSON)
        except Exception: raise ValueError("GitHub HTTPS operation failed; reconcile before retry") from None
        need(type(response) is HTTPResponse and type(response.status) is int and response.status in statuses and
             type(response.body) is bytes and len(response.body) <= (MAX_ASSET if binary else MAX_JSON),
             "GitHub HTTPS response rejected; reconcile before retry")
        return response

    def _before_write(self, access):
        need(type(access.scope) is BoundScope and access.effect is not None, "A sealed write scope is required")
        authority = access.scope.verify(access.effect, access.arguments, self.enrolled, self.clock())
        need(self.mock_only or authority.get("mock_only") is False,
             "Local test authority cannot authorize HTTPS effects")
        policy = self.inspect_policy()
        need(policy["sha256"] == authority["policy_sha256"], "Remote policy baseline changed")
        self._preflight(access, access.arguments["heads"])
        if access.scope.kind == "publication":
            # No generic callback or truthy field can replace a fresh attributable
            # PR proof. Token minting and the slower state reads finish first.
            import publication_pilot_contract as contract
            from publication_pr_owner import OwnerPRVerifier
            material = contract.load_material(access.scope.path, now=self.clock())
            proof = OwnerPRVerifier(self.enrolled, self).verify(material, now=self.clock())
            need(type(proof.get("review_id")) is int and proof["review_id"] == access.scope.claimed_review_id,
                 "Owner review changed after durable consumption")
            need(self.mock_only or proof.get("real_owner_authenticated") is True,
                 "Synthetic owner proof cannot authorize HTTPS effects")
        # A slow policy/head/token read must not carry the operation past expiry.
        access.scope.verify(access.effect, access.arguments, self.enrolled, self.clock())

    def _invoke(self, method, caps, scope, *args, **kwargs):
        fn = getattr(_ValidatedObjects, method)
        bound = signatures.signature(fn).bind(self, None, *args, **kwargs); bound.apply_defaults()
        arguments = {k: v for k, v in bound.arguments.items() if k not in ("self", "credential")}
        access = _Access(caps, scope, method if scope is not None else None, arguments)
        if any(v == "write" for v in caps.values()):
            need(type(scope) is BoundScope, "Sealed publication/preparation authority required")
            authority = scope.verify(method, arguments, self.enrolled, self.clock())
            need(self.mock_only or authority.get("mock_only") is False,
                 "Local test authority cannot authorize HTTPS effects")
        result = fn(self, access, *args, **kwargs)
        return result

    def inspect(self, expected_heads=None):
        return self._invoke("inspect",{"contents":"read","pages":"read"},None,expected_heads)

    def inspect_policy(self):
        access=_Access({"administration":"read"}); raw_repo=self._repo(access)
        rules=[];seen=set()
        for item in self._list(access,"/rulesets?includes_parents=true"):
            identity=number(item.get("id"));need(identity not in seen,"Duplicate ruleset");seen.add(identity)
            detail=self._json("GET","/rulesets/"+str(identity),access)
            need(number(detail.get("id"))==identity,"Ruleset readback changed")
            rules.append(detail)
        env=self._json("GET","/environments/github-pages",access)
        branches=self._collection("/environments/github-pages/deployment-branch-policies","branch_policies")
        target=expected_policy(self.enrolled)
        result={"rulesets":rules,"environments":{"github-pages":env},"pages_branch_policies":branches,
                "repository":{k:raw_repo.get(k) for k in target["repository"]},
                "default_actions":self._json("GET","/actions/permissions/workflow",access),
                "immutable_releases":self._json("GET","/immutable-releases",access)}
        validate_policy(self.enrolled,result)
        digest=core.sha(core.canonical(result))
        return self._receipt(**result,policy_sha256=digest,sha256=digest)

    def prepare_pages(self, heads, files, *, message="Simulated reviewed Pages publication"):
        return self._invoke("prepare_pages",{"contents":"read"},None,heads,files,message=message)

    def read_commit(self, identity, *, absent=False):
        return self._invoke("read_commit",{"contents":"read"},None,identity,absent=absent)

    def read_tree(self, identity, *, absent=False):
        return self._invoke("read_tree",{"contents":"read"},None,identity,absent=absent)

    def read_blob(self, identity, expected_sha256=None, *, absent=False):
        return self._invoke("read_blob",{"contents":"read"},None,identity,expected_sha256,absent=absent)

    def read_tag(self, tag, *, absent=False):
        return self._invoke("read_tag",{"contents":"read"},None,tag,absent=absent)

    def read_release(self, release_id, tag):
        return self._invoke("read_release",{"contents":"read"},None,release_id,tag)

    def read_assets(self, release_id):
        return self._invoke("read_assets",{"contents":"read"},None,release_id)

    def download_asset(self, release_id, asset_id, name, expected_sha256, size):
        return self._invoke("download_asset",{"contents":"read"},None,release_id,asset_id,name,expected_sha256,size)

    def read_ledger_pr(self, identity):
        return self._invoke("read_ledger_pr",{"pull_requests":"read"},None,identity)

    def read_ledger_reviews(self, identity):
        return self._invoke("read_ledger_reviews",{"pull_requests":"read"},None,identity)

    def find_ledger_pr(self, branch,target):
        return self._invoke("find_ledger_pr",{"pull_requests":"read"},None,branch,target)

    def read_pages_build(self, expected_commit=None):
        if expected_commit is not None: commit(expected_commit)
        value = self._invoke("read_pages_build",{"pages":"read"},None)
        if expected_commit is not None and value["commit"] != expected_commit:
            raise PendingPagesReadiness("Pages build still identifies the previous commit")
        if value["status"] in ("queued", "building"):
            raise PendingPagesReadiness("Pages build is pending")
        need(value["status"] == "built", "Pages build failed")
        return value

    def create_tag(self,scope,heads,tag,target):
        return self._invoke("create_tag",{"contents":"write"},scope,heads,tag,target)

    def create_draft(self,scope,heads,tag,target,name,notes):
        return self._invoke("create_draft",{"contents":"write"},scope,heads,tag,target,name,notes)

    def upload_asset(self,scope,heads,release_id,tag,name,data,expected_sha256):
        return self._invoke("upload_asset",{"contents":"write"},scope,heads,release_id,tag,name,data,expected_sha256)

    def publish_release(self,scope,heads,release_id,tag,target,assets,*,name,notes):
        return self._invoke("publish_release",{"contents":"write"},scope,heads,release_id,tag,target,assets,name=name,notes=notes)

    def create_blob(self,scope,heads,data,expected_sha=None):
        return self._invoke("create_blob",{"contents":"write"},scope,heads,data,expected_sha)

    def create_tree(self,scope,heads,files,expected_tree,base_tree=None):
        return self._invoke("create_tree",{"contents":"write"},scope,heads,files,expected_tree,base_tree)

    def create_commit(self,scope,heads,tree,parent,message,expected_sha):
        return self._invoke("create_commit",{"contents":"write"},scope,heads,tree,parent,message,expected_sha)

    def fast_forward_pages(self,scope,heads,target,parent,tree):
        return self._invoke("fast_forward_pages",{"contents":"write"},scope,heads,target,parent,tree)

    def create_ledger_branch(self,scope,heads,branch,target):
        return self._invoke("create_ledger_branch",{"contents":"write"},scope,heads,branch,target)

    def create_ledger_pr(self,scope,heads,branch,target,title,body):
        return self._invoke("create_ledger_pr",{"pull_requests":"write","contents":"read"},scope,heads,branch,target,title,body)

    def read_ref(self, branch, *, absent=False):
        need(branch in ("main", "gh-pages", "d3-fixture-source") or
             type(branch) is str and LEDGER_BRANCH.fullmatch(branch), "Unenrolled branch observation")
        need(type(absent) is bool, "Explicit absence policy required")
        return self._ref(_Access({"contents": "read"}), "heads/" + branch, absent=absent)

    def update_request_pr(self, scope, heads, number, target, title, body):
        arguments = {"heads": heads, "number": number, "target": target, "title": title, "body": body}
        access = _Access({"pull_requests": "write"}, scope, "update_request_pr", arguments)
        need(type(scope) is BoundScope, "Sealed metadata request grant required")
        authority = scope.verify(access.effect, arguments, self.enrolled, self.clock())
        need(self.mock_only or authority.get("mock_only") is False,
             "Local test authority cannot authorize HTTPS effects")
        self._preflight(access, heads)
        pr = self.read_ledger_pr(number)
        need(pr.get("state") == "open" and pr.get("draft") is False and pr["head"]["sha"] == commit(target)
             and pr["base"]["sha"] == heads["main_sha"], "Request PR identity/state changed")
        value = self._json("PATCH", f"/pulls/{number}", access,
                           body={"title": text(title, 1000), "body": text(body, 60000)})
        need(type(value.get("number")) is int and value["number"] == number and
             value.get("title") == title and value.get("body") == body and
             value.get("head", {}).get("sha") == target and value.get("state") == "open",
             "Request PR metadata response mismatch")
        return self._receipt(number=number, sha=target, body_sha256=core.sha(body.encode()))

    def merge_ledger_pr(self, scope, heads, number, target, expected_tree):
        arguments = {"heads": heads, "number": number, "target": target, "expected_tree": expected_tree}
        access = _Access({"contents": "write"}, scope, "merge_ledger_pr", arguments)
        need(type(scope) is BoundScope, "Sealed publication scope required")
        authority = scope.verify(access.effect, arguments, self.enrolled, self.clock())
        need(self.mock_only or authority.get("mock_only") is False,
             "Local test authority cannot authorize HTTPS effects")
        self._preflight(access, heads)
        pr = self.read_ledger_pr(number)
        need(pr.get("state") == "open" and pr.get("draft") is False and pr.get("merged") is False and
             pr["head"]["sha"] == commit(target) and pr["base"]["sha"] == heads["main_sha"] and
             pr.get("mergeable") is True and pr.get("mergeable_state") == "clean",
             "Ledger PR not exactly mergeable")
        head = self.read_commit(target)
        need([p["sha"] for p in head["parents"]] == [heads["main_sha"]] and
             head["tree"]["sha"] == commit(expected_tree), "Approved ledger parent/tree changed")
        value = self._json("PUT", f"/pulls/{number}/merge", access,
                           body={"sha": target, "merge_method": "merge"})
        need(value.get("merged") is True, "Normal merge failed; reconcile before retry")
        merged = commit(value.get("sha"))
        actual = self.read_commit(merged)
        need([p["sha"] for p in actual["parents"]] == [heads["main_sha"], target] and
             actual["tree"]["sha"] == expected_tree and
             self.read_ref("main")["object"]["sha"] == merged,
             "Accepted merge differs; retain incomplete incident for forward recovery")
        return self._receipt(number=number, sha=merged, tree=expected_tree,
                             parents=[heads["main_sha"], target], merged=True)

    def _receipt(self, **values):
        return {**values, "profile": PROFILE, "transport_origin": self.transport_origin,
                "mock_only": self.mock_only, "production_authorized": False}

    def observe_pr_owner(self, number):
        """Raw complete observations; independent verifier decides PR authority."""
        pr = self.read_ledger_pr(number)
        reviews = self.read_ledger_reviews(number)
        comments = self._list(_Access({"pull_requests": "read"}), f"/issues/{number}/comments")
        policy = self.inspect_policy()
        return {"pr": pr, "reviews": reviews, "comments": comments, "policy": policy,
                "transport": self.transport_origin, "authenticated": not self.mock_only}

    def _collection(self, path, key):
        values = []; total = None
        access = _Access({"actions": "read"})
        for page in range(1, MAX_PAGES + 1):
            suffix = path + ("&" if "?" in path else "?") + f"per_page=100&page={page}"
            response = self._request("GET", suffix, access)
            result = parse_json(response.body)
            need(type(result) is dict and type(result.get("total_count")) is int and result["total_count"] >= 0 and
                 type(result.get(key)) is list and len(result[key]) <= 100, "Malformed Actions collection")
            if total is None: total = result["total_count"]
            need(total == result["total_count"], "Actions collection changed")
            values.extend(result[key]); link = response.headers.get("Link", response.headers.get("link", ""))
            need(type(link) is str, "Malformed Actions pagination")
            if 'rel="next"' not in link:
                need(len(values) == total, "Incomplete Actions collection")
                return values
            next_suffix = path + ("&" if "?" in path else "?") + f"per_page=100&page={page + 1}"
            need(f'<{API + self.prefix + next_suffix}>; rel="next"' in link, "Foreign Actions continuation")
        raise ValueError("Actions collection exceeds bound")

    def observe_pages_deployment(self, expected_commit):
        """Actual branch Pages build + trusted Actions run, never public-byte proof."""
        validate_enrollment(self.enrolled); commit(expected_commit)
        identity = number(self.enrolled["pages_workflow_id"])
        access = _Access({"actions": "read"})
        workflow = self._json("GET", f"/actions/workflows/{identity}", access)
        need(number(workflow.get("id")) == identity and workflow.get("path") == "dynamic/pages/pages-build-deployment" and
             workflow.get("state") == "active", "Untrusted Pages workflow")
        runs = self._collection(f"/actions/workflows/{identity}/runs?head_sha={expected_commit}", "workflow_runs")
        for item in runs:
            need(type(item) is dict and number(item.get("id")) and item.get("head_sha") == expected_commit and
                 type(item.get("workflow_id")) is int and item["workflow_id"] == identity and
                 item.get("head_branch") == "gh-pages" and
                 number(item.get("repository", {}).get("id")) == self.enrolled["repository_id"] and
                 item.get("repository", {}).get("full_name") == QUAL_REPOSITORY,
                 "Pages workflow identity mismatch")
        if not runs:
            raise PendingPagesReadiness("Pages deployment run missing; waiting for scoped readiness")
        need(len(runs) == 1, "Ambiguous Pages deployment runs")
        run = runs[0]; run_id = run["id"]
        if run.get("status") in ("queued", "in_progress"):
            need(run.get("conclusion") is None, "Inconsistent pending Pages result")
            raise PendingPagesReadiness("Pages deployment run is pending")
        need(run.get("status") == "completed" and run.get("conclusion") == "success",
             "Pages deployment run failed")
        jobs = self._collection(f"/actions/runs/{run_id}/jobs", "jobs")
        need(jobs and len({j.get('id') for j in jobs if type(j)is dict})==len(jobs) and
             all(type(j) is dict and number(j.get("id")) and j.get("run_id") == run_id and
                          type(j.get("run_id")) is int and j.get("head_sha") == expected_commit and
                          j.get("status") == "completed" and j.get("conclusion") in ("success", "skipped") for j in jobs),
             "Pages jobs unverified")
        deploys = [j for j in jobs if j.get("name") == "deploy"]
        need(len(deploys) == 1 and deploys[0].get("conclusion") == "success",
             "Exactly one successful completed Pages deploy job is required")
        page = self._json("GET", "/pages", _Access({"pages": "read"}))
        need(page.get("html_url") == QUAL_ORIGIN and page.get("https_enforced") is True and
             page.get("build_type") == "legacy" and page.get("source") == {"branch": "gh-pages", "path": "/"},
             "Pages destination/source changed")
        build = self.read_pages_build(expected_commit)
        environment = self._json("GET", "/environments/github-pages", _Access({"administration": "read"}))
        need(environment.get("name") == "github-pages" and number(environment.get("id")) == self.enrolled["pages_environment_id"],
             "Pages environment identity changed")
        return self._receipt(commit=expected_commit, status="completed", conclusion="success", run=run,
                             workflow=workflow, jobs=jobs, pages=page, build=build, environment=environment)

    def observe_validation(self, expected_commit):
        """Trusted pinned CI run/jobs under Actions read; no Checks/Statuses API."""
        validate_enrollment(self.enrolled); commit(expected_commit)
        e=self.enrolled; identity=number(e['validation_workflow_id'])
        access=_Access({'actions':'read'})
        workflow=self._json('GET',f'/actions/workflows/{identity}',access)
        need(number(workflow.get('id'))==identity and workflow.get('path')==e['validation_workflow_path'] and
             workflow.get('state')=='active','Validation workflow identity changed')
        # Independently read and hash the workflow at the pinned distribution
        # commit. The reviewed main tree preserves this exact control source.
        suffix='/contents/'+e['validation_workflow_path']+'?ref='+commit(e['validation_workflow_commit'])
        source=self._json('GET',suffix,_Access({'contents':'read'}))
        need(source.get('type')=='file' and source.get('path')==e['validation_workflow_path'] and
             source.get('encoding')=='base64' and type(source.get('content')) is str,'Malformed validation workflow source')
        try: raw=base64.b64decode(''.join(source['content'].split()),validate=True)
        except Exception: raise ValueError('Malformed validation workflow encoding') from None
        need(core.sha(raw)==e['validation_workflow_sha256'] and core.git_object('blob',raw)==source.get('sha'),
             'Pinned validation workflow bytes changed')
        runs=self._collection(f'/actions/workflows/{identity}/runs?head_sha={expected_commit}&status=completed','workflow_runs')
        matching=[r for r in runs if type(r)is dict and r.get('head_sha')==expected_commit]
        need(len(matching)==1,'Validation run absent or ambiguous')
        run=matching[0];run_id=number(run.get('id'))
        need(type(run.get('workflow_id'))is int and run['workflow_id']==identity and
             run.get('status')=='completed' and run.get('conclusion')=='success' and
             run.get('path')==e['validation_workflow_path'] and
             number(run.get('repository',{}).get('id'))==e['repository_id'] and
             run.get('repository',{}).get('full_name')==QUAL_REPOSITORY,'Validation run failed or identity changed')
        jobs=self._collection(f'/actions/runs/{run_id}/jobs','jobs')
        matching=[j for j in jobs if type(j)is dict and j.get('name')==e['validation_job_name']]
        need(len(matching)==1,'Required validation job absent or ambiguous')
        job=matching[0];number(job.get('id'))
        need(type(job.get('run_id'))is int and job['run_id']==run_id and job.get('head_sha')==expected_commit and
             job.get('status')=='completed' and job.get('conclusion')=='success','Validation job failed or wrong head')
        return self._receipt(commit=expected_commit,status='completed',conclusion='success',workflow=workflow,run=run,jobs=jobs,
                             workflow_sha256=core.sha(raw),required_check_app_id=e['ci_app_id'])

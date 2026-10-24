"""Single-PR disposable publication pilot. Never a production publisher.

The versioned journal is separate from historical mock D3 records. Every write is
bound to a sealed metadata grant or exact owner-reviewed execution. There is no
ambient credential, shell, settings mutation or automatic retry.
"""
from __future__ import annotations

import copy
from contextlib import contextmanager
from datetime import timedelta
import fcntl
import os
from pathlib import Path
import re
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))

import publication_proposal as frozen
from publication_fake import durable, regular, digest
from publication_operator import utc


MODE = "d3-pr-pilot-v1"


def operation_id(operation):
    return operation["kind"] + (":" + operation["name"] if "name" in operation else "")


def release_inventory(values):
    """Canonical complete Release metadata; API pagination order is immaterial."""
    result = copy.deepcopy(values)
    for item in result:
        item["assets"] = sorted(item["assets"], key=lambda asset: (asset["name"], asset["id"]))
    return sorted(result, key=lambda release: (release["tag"], release["id"]))


class PilotJournal:
    """Durable single-use state, with an independently writable revocation latch.

    Journal-first writes deliberately fail closed after a torn commit. Whole-store
    rollback still needs external recovery evidence and a new installation epoch.
    """

    def __init__(self, root, identity):
        frozen.closed(identity, {"installation_uuid", "epoch", "enrollment_sha256"})
        frozen.require(type(identity["installation_uuid"]) is str and frozen.HEX32.fullmatch(identity["installation_uuid"])
                       and type(identity["epoch"]) is int and identity["epoch"] > 0 and
                       type(identity["enrollment_sha256"]) is str and frozen.HEX64.fullmatch(identity["enrollment_sha256"]),
                       "Missing qualification installation configuration")
        self.root = Path(root).absolute()
        for parent in (self.root, *self.root.parents):
            frozen.require(not parent.is_symlink(), "Linked qualification storage")
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.identity = copy.deepcopy(identity)
        with self.lock():
            state = self.root / "state.json"
            if not state.exists():
                frozen.require(set(p.name for p in self.root.iterdir()) <= {"lock"},
                               "Uninitialized or missing journal; reconciliation required")
                (self.root / "journal").mkdir(mode=0o700)
                (self.root / "revocations").mkdir(mode=0o700)
                durable(self.root / "revocations/index.json", frozen.canonical({}), exclusive=True)
                self._save({"schema": 1, "mode": MODE, "production_authorized": False, "identity": self.identity,
                            "generation": 0, "used": {}, "owner_reviews": {}, "active": None,
                            "transactions": {}, "preparations": {}, "preparation_active": None, "metadata_grants": {}}, initial=True)
            self.load()

    @contextmanager
    def lock(self):
        fd = os.open(regular(self.root / "lock"), os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise ValueError("Qualification writer already active") from exc
            yield
        finally:
            os.close(fd)

    def load(self):
        state = frozen.strict_load(frozen.safe_read(regular(self.root / "state.json"), frozen.MAX_JSON))
        frozen.closed(state, {"schema", "mode", "production_authorized", "identity", "generation",
                              "used", "owner_reviews", "active", "transactions", "preparations", "preparation_active", "metadata_grants"})
        frozen.require(type(state.get("schema")) is int and state.get("schema") == 1 and state.get("mode") == MODE and
                       state.get("production_authorized") is False and
                       state.get("identity") == self.identity, "Journal mode/installation/epoch changed")
        folder = self.root / "journal"
        frozen.require(folder.is_dir() and not folder.is_symlink(), "Missing qualification journal")
        paths = sorted(folder.iterdir())
        frozen.require(len(paths) == state["generation"] + 1, "Journal generation mismatch; recovery disabled")
        previous = "0" * 64
        for index, path in enumerate(paths):
            frozen.require(path.name == f"{index:010d}.json", "Journal sequence changed")
            raw = frozen.safe_read(regular(path), frozen.MAX_JSON)
            event = frozen.strict_load(raw)
            frozen.closed(event, {"generation", "previous", "state_sha256"})
            frozen.require(event["generation"] == index and event["previous"] == previous,
                           "Journal chain changed")
            previous = frozen.sha(raw)
        frozen.require(event["state_sha256"] == digest(state), "Journal/state interrupted or altered")
        self.revocations()
        return state

    def _save(self, state, *, initial=False):
        previous = "0" * 64
        if not initial:
            current = self.load()
            frozen.require(current["generation"] == state["generation"], "Stale qualification writer")
            previous = frozen.sha(frozen.safe_read(self.root / "journal" / f'{state["generation"]:010d}.json'))
            state["generation"] += 1
        raw = frozen.canonical(state)
        event = {"generation": state["generation"], "previous": previous, "state_sha256": frozen.sha(raw)}
        durable(self.root / "journal" / f'{state["generation"]:010d}.json', frozen.canonical(event), exclusive=True)
        durable(self.root / "state.json", raw, exclusive=initial)

    def revocations(self):
        directory = self.root / "revocations"
        frozen.require(directory.is_dir() and not directory.is_symlink(), "Missing revocation inventory")
        index = frozen.strict_load(frozen.safe_read(regular(directory / "index.json"), frozen.MAX_JSON))
        frozen.require(type(index) is dict and {p.name for p in directory.iterdir()} == set(index) | {"index.json"},
                       "Revocation inventory changed")
        for name, checksum in index.items():
            frozen.require(re.fullmatch(r"[0-9a-f]{32}\.json", name) is not None,
                           "Malformed revocation identity")
            frozen.require(frozen.sha(frozen.safe_read(regular(directory / name))) == checksum,
                           "Revocation latch changed")
        return index

    def latch_revocation(self, nonce, proof_digest):
        frozen.require(type(nonce) is str and re.fullmatch(r"[0-9a-f]{32}", nonce) and
                       type(proof_digest) is str and re.fullmatch(r"[0-9a-f]{64}", proof_digest),
                       "Invalid revocation binding")
        fd = os.open(regular(self.root / "revocation-lock"), os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            index = self.revocations()
            name = nonce + ".json"
            if name not in index:
                raw = frozen.canonical({"nonce": nonce, "proof_sha256": proof_digest, "mode": MODE})
                durable(self.root / "revocations" / name, raw, exclusive=True)
                index[name] = frozen.sha(raw)
                durable(self.root / "revocations/index.json", frozen.canonical(index))
        finally:
            os.close(fd)

    def check_revoked(self, nonce):
        frozen.require(nonce + ".json" not in self.revocations(), "Owner authorization revoked")

    def claim(self, bundle, remote_digest, remote_snapshot=None, owner_review_id=None):
        state = self.load()
        execution = bundle["execution"]
        nonce = execution["nonce"]
        self.check_revoked(nonce)
        frozen.require(nonce not in state["used"], "Owner authorization nonce replay")
        frozen.require(type(owner_review_id) is int and owner_review_id > 0 and str(owner_review_id) not in state["owner_reviews"],
                       "Owner authorization review replay or missing decision")
        recovery = execution["recovery"]
        completed = []
        receipts = {}
        baseline = [] if remote_snapshot is None else copy.deepcopy(remote_snapshot["releases"])
        if recovery is None:
            frozen.require(state["active"] is None, "Incomplete publication blocks the next release")
            origin = bundle["digest"]
        else:
            frozen.require(state["active"] == recovery["transaction"], "Recovery does not bind active transaction")
            old = state["transactions"][state["active"]]
            frozen.require(old["payload_sha256"] == execution["payload_sha256"] and
                           old["review_sha256"] == execution["review_sha256"] and
                           recovery["remote_state_sha256"] == remote_digest,
                           "Recovery changes reviewed artifacts or observed remote state")
            frozen.require(old.get("pending") is None and old.get("reconciled") is True and
                           recovery["completed"] == old["completed"],
                           "GET-only reconciliation required before recovery")
            completed = list(old["completed"])
            receipts = copy.deepcopy(old["receipts"])
            baseline = copy.deepcopy(old["baseline_releases"])
            origin = old["origin"]
        state["used"][nonce] = bundle["digest"]
        if owner_review_id is not None:
            state["owner_reviews"][str(owner_review_id)] = bundle["digest"]
        state["active"] = bundle["digest"]
        state["transactions"][bundle["digest"]] = {
            "origin": origin, "nonce": nonce, "owner_review_id": owner_review_id,
            "pr": copy.deepcopy(execution.get("pr")), "payload_sha256": execution["payload_sha256"],
            "review_sha256": execution["review_sha256"], "completed": completed,
            "receipts": receipts, "pending": None, "status": "CLAIMED", "reconciled": False,
            "remote_sha256": remote_digest, "baseline_releases": baseline, "audit": []}
        self._save(state)

    def update(self, execution_digest, *, pending=None, receipt=None, completed=None, status=None):
        state = self.load()
        frozen.require(state["active"] == execution_digest, "Inactive qualification transaction")
        tx = state["transactions"][execution_digest]
        if pending is not None:
            frozen.require(tx["pending"] is None, "Unreconciled remote intent")
            tx["pending"] = pending
        if receipt is not None:
            frozen.require(tx["pending"] is not None, "Receipt has no durable intent")
            tx["receipts"][tx["pending"]] = copy.deepcopy(receipt)
            tx["pending"] = None
        if completed is not None:
            tx["completed"].append(completed)
        if status is not None:
            tx["status"] = status
        self._save(state)

    def fail(self, execution_digest):
        state = self.load()
        tx = state["transactions"][execution_digest]
        tx["status"] = ("UNKNOWN_REMOTE_STATE" if tx["pending"] else
                        "PUBLIC_BUT_UNRECONCILED" if "publish_release" in tx["receipts"] else "INCOMPLETE")
        self._save(state)

    def audit(self, execution_digest, *, operation, status, at, object_id=None, sha256=None):
        """Closed metadata only; raw bodies, errors, headers and tokens are refused."""
        frozen.require(type(operation) is str and re.fullmatch(r"[a-z_]+(?::[A-Za-z0-9._/-]+)?", operation)
                       and status in {"intent", "verified", "pending", "failed", "observed"}, "Invalid audit event")
        frozen.timestamp(at)
        frozen.require(object_id is None or type(object_id) is int and object_id > 0, "Invalid audit object ID")
        frozen.require(sha256 is None or type(sha256) is str and frozen.HEX64.fullmatch(sha256), "Invalid audit checksum")
        state = self.load()
        tx = state["transactions"][execution_digest]
        tx["audit"].append({"operation": operation, "status": status, "at": at,
                            "object_id": object_id, "sha256": sha256})
        self._save(state)

    def finish(self, execution_digest):
        state = self.load()
        tx = state["transactions"][execution_digest]
        frozen.require(state["active"] == execution_digest and tx["pending"] is None and
                       tx["completed"] and tx["completed"][-1] == "merge_ledger",
                       "Unverified finalization cannot clear active release")
        tx["status"] = "RECORDED"
        state["active"] = None
        if tx["payload_sha256"] in state["preparations"]:
            state["preparations"][tx["payload_sha256"]]["status"] = "RECORDED"
        self._save(state)

    def status(self):
        with self.lock():
            value = self.load()
            return {"mode": MODE, "production_authorized": False,
                    "active": value["active"], "transactions": copy.deepcopy(value["transactions"]),
                    "preparation_active": value["preparation_active"],
                    "preparations": copy.deepcopy(value["preparations"]), "generation": value["generation"]}


class PilotOperator:
    """One-shot disposable pilot; callers supply reviewed material, never commands.

    The transport owns credential minting and fixed-host policy. A scripted test
    backend can exercise this engine but cannot generate live owner authority.
    """

    def __init__(self, root, enrollment, transport, owner, *, clock=None, wait=None):
        import publication_pilot_contract as contract
        import publication_github_live as github
        import publication_pr_owner as approval
        self.enrollment = contract.validate_enrollment(enrollment)
        frozen.require(type(transport) is github.PilotGitHub and transport.enrollment == self.enrollment,
                       "Pilot transport does not match enrollment")
        frozen.require(type(owner) is approval.OwnerPRVerifier and owner.enrollment == self.enrollment,
                       "Pilot owner verifier does not match enrollment")
        self.transport = transport
        self.owner = owner
        self.clock = clock
        self.wait = time.sleep if wait is None else wait
        frozen.require(callable(self.wait), "Trusted readiness wait callback required")
        self.journal = PilotJournal(root, {
            "installation_uuid": self.enrollment["installation_uuid"], "epoch": self.enrollment["epoch"],
            "enrollment_sha256": digest(self.enrollment)})

    def now(self):
        return utc(self.clock() if self.clock else None)

    def _load(self, path, expected_digest=None, *, observation=False):
        import publication_pilot_contract as contract
        data = contract.load_material(path, expected_digest=expected_digest, now=self.now(), observation=observation)
        frozen.require(data["enrollment"] == self.enrollment, "Pilot enrollment changed")
        data["_guard"] = frozen.inventory(path)
        return data

    def _scope(self, path, kind, *, data=None):
        from publication_github_live import BoundScope
        scope = BoundScope(path, kind)
        if kind == "publication":
            frozen.require(data is not None, "Publication scope requires a consumed decision")
            frozen.require(self.journal.load()["active"] == data["digest"], "Publication decision is not active")
            tx = self._tx(data)
            scope.claimed_review_id = tx["owner_review_id"]
        return scope

    def _heads(self, data, *, recovered=False):
        heads = {k: data["payload"]["expected"][k] for k in ("main_sha", "pages_sha")}
        if recovered and "pages_ref" in self._tx(data)["receipts"]:
            heads["pages_sha"] = data["payload"]["pages"]["commit"]
        return heads

    def _policy(self):
        observed = self.transport.inspect_policy()
        frozen.require(observed["policy_sha256"] == self.enrollment["policy_sha256"],
                       "Pilot protections or sole-writer policy changed")
        return observed

    def _tx(self, data):
        return self.journal.load()["transactions"][data["digest"]]

    def _owner(self, data):
        from publication_pr_owner import RevokedApproval
        nonce = data["execution"]["nonce"]
        self.journal.check_revoked(nonce)
        try:
            receipt = self.owner.verify(data, now=self.now())
        except RevokedApproval as error:
            frozen.require(error.nonce == nonce and error.proposal_sha256 == data["digest"],
                           "Revocation scope changed")
            self.journal.latch_revocation(nonce, error.revocation_sha256)
            raise
        frozen.require(type(receipt.get("review_id")) is int and receipt["review_id"] > 0 and
                       type(receipt.get("actor_id")) is int and
                       receipt["actor_id"] == self.enrollment["human_owner_id"] and
                       receipt.get("proposal_sha256") == data["digest"] and receipt.get("nonce") == nonce,
                       "Owner proof has wrong identity or exact scope")
        # A mock transport cannot smuggle a purported genuine proof into a receipt.
        frozen.require(receipt.get("mock_only") is (self.transport.transport_origin != "github-https"),
                       "Owner proof and transport origin differ")
        return receipt

    def _fresh(self, path, data):
        import publication_pilot_contract as contract
        frozen.require(frozen.inventory(path) == data["_guard"], "Frozen pilot bytes changed")
        frozen.require(contract.toolchain() == data["payload"]["toolchain"], "Pilot toolchain changed")
        e = data["execution"]
        frozen.require(frozen.timestamp(e["created_at"]) <= self.now() < frozen.timestamp(e["expires_at"]),
                       "Pilot execution expired")

    def _effect(self, path, data, heads, name, function):
        tx = self._tx(data)
        if name in tx["receipts"]:
            return tx["receipts"][name]
        frozen.require(tx["pending"] is None, "Unreconciled intent blocks execution")
        self._fresh(path, data)
        proof = self._owner(data)
        frozen.require(proof["review_id"] == tx["owner_review_id"], "Owner decision changed during execution")
        observed = self.transport.inspect(expected_heads=heads)
        self._phase_state(data, observed)
        self._policy()
        self.journal.update(data["digest"], pending=name)
        self.journal.audit(data["digest"], operation=name, status="intent", at=frozen.utc(self.now()))
        from publication_pr_owner import RevokedApproval
        try:
            result = function()
        except RevokedApproval as error:
            frozen.require(error.nonce == data["execution"]["nonce"] and error.proposal_sha256 == data["digest"],
                           "Transport revocation scope changed")
            self.journal.latch_revocation(error.nonce, error.revocation_sha256)
            raise
        frozen.require(type(result) is dict, "Missing publication effect receipt")
        self.journal.update(data["digest"], receipt=result)
        self.journal.audit(data["digest"], operation=name, status="verified", at=frozen.utc(self.now()))
        return result

    def _prep_effect(self, path, data, heads, name, function):
        import publication_pilot_contract as contract
        state = self.journal.load(); prep = state["preparations"][data["payload_sha256"]]
        if name in prep["receipts"]:
            return prep["receipts"][name]
        frozen.require(prep["pending"] is None, "Metadata preparation requires GET-only reconciliation")
        contract.transport_authority(path, "preparation", now=self.now())
        frozen.require(frozen.inventory(path) == data["_guard"], "Reviewed metadata material changed")
        self.transport.inspect(expected_heads=heads); self._policy()
        prep["pending"] = name; self.journal._save(state)
        receipt = function()
        frozen.require(type(receipt) is dict, "Missing metadata effect receipt")
        state = self.journal.load(); prep = state["preparations"][data["payload_sha256"]]
        frozen.require(prep["pending"] == name, "Metadata intent changed")
        prep["receipts"][name] = receipt; prep["pending"] = None
        self.journal._save(state)
        return receipt

    def request(self, path, expected_digest=None, *, nonce=None, lifetime=3600, recovery=None):
        """Stage only reviewed ledger metadata and one request PR, then seal E.

        This does not issue owner authorization. Contents-write GitHub tokens are
        coarse; the independently validated preparation scope is the path boundary.
        """
        import publication_pilot_contract as contract
        data = self._load(path)
        frozen.require(expected_digest is None or expected_digest in {data["payload_sha256"], data["digest"]},
                       "Request material digest mismatch")
        frozen.require(data.get("review") is not None, "Independent review is missing")
        frozen.require((Path(path) / "preparation.json").exists(),
                       "Separate owner-authorized metadata preparation grant is missing")
        contract.transport_authority(path, "preparation", now=self.now())
        p = data["payload"]; retention = p["retention"]; heads = self._heads(data)
        scope = self._scope(path, "preparation")
        with self.journal.lock():
            state = self.journal.load(); key = data["payload_sha256"]
            grant = data["preparation"]; grant_identity = {"payload_sha256": key, "grant_sha256": digest(grant)}
            old_grant = state["metadata_grants"].get(grant["nonce"])
            frozen.require(old_grant is None or old_grant == grant_identity, "Metadata grant nonce replay or altered grant")
            frozen.require(state["active"] is None or recovery is not None and
                           recovery["transaction"] == state["active"], "Incomplete publication blocks new request")
            frozen.require(state["preparation_active"] in {None, key}, "Incomplete metadata request blocks next release")
            if key not in state["preparations"]:
                state["preparations"][key] = {"review_sha256": data["review_sha256"], "receipts": {},
                    "pending": None, "status": "PREPARING", "execution_sha256": None, "grant_nonces": []}
                state["preparation_active"] = key
            else:
                frozen.require(state["preparations"][key]["review_sha256"] == data["review_sha256"],
                               "Metadata request review changed")
            if recovery is not None:
                old = state["transactions"].get(recovery["transaction"])
                frozen.require(old is not None and old["payload_sha256"] == key and old["reconciled"] is True,
                               "Fresh recovery requires reconciled identical publication")
                if "pages_ref" in old["receipts"]:
                    heads["pages_sha"] = p["pages"]["commit"]
            self.transport.inspect(expected_heads=heads); self._policy()
            self._verify_main(data)
            state["metadata_grants"][grant["nonce"]] = grant_identity
            if grant["nonce"] not in state["preparations"][key]["grant_nonces"]:
                state["preparations"][key]["grant_nonces"].append(grant["nonce"])
            self.journal._save(state)
            changed = {"releases/manifest.json": frozen.safe_read(data["root"] / retention["successor_path"]),
                       "config/qualification.json": frozen.safe_read(data["root"] / retention["config_path"])}
            blobs = {}
            for name, raw in sorted(changed.items()):
                receipt = self._prep_effect(path, data, heads, "ledger_blob:" + name,
                    lambda raw=raw: self.transport.create_blob(scope, heads, raw, expected_sha=frozen.git_object("blob", raw)))
                blobs[name] = receipt["sha"]
            self._prep_effect(path, data, heads, "ledger_tree", lambda: self.transport.create_tree(
                scope, heads, blobs, retention["main_tree"], base_tree=p["main_base"]["tree"]))
            self._prep_effect(path, data, heads, "ledger_commit", lambda: self.transport.create_commit(
                scope, heads, retention["main_tree"], retention["main_parent"],
                contract.ledger_message(data), retention["main_commit"]))
            branch = contract.ledger_branch(data)
            self._prep_effect(path, data, heads, "ledger_branch", lambda: self.transport.create_ledger_branch(
                scope, heads, branch, retention["main_commit"]))
            receipt = self._prep_effect(path, data, heads, "ledger_pr", lambda: self.transport.create_ledger_pr(
                scope, heads, branch, retention["main_commit"], contract.request_title(data), contract.preparation_body(data)))
            pr = self.transport.read_ledger_pr(receipt["number"])
            staged = {"number": pr["number"], "id": pr["id"], "node_id": pr["node_id"],
                      "head_sha": pr["head"]["sha"], "base_sha": pr["base"]["sha"],
                      "head_ref": pr["head"]["ref"], "base_ref": pr["base"]["ref"], "url": pr["html_url"]}
            if data.get("execution") is None:
                contract.seal_execution(path, staged, nonce=nonce, lifetime=lifetime, now=self.now(), recovery=recovery)
                data = self._load(path)
            else:
                frozen.require(data["execution"]["pr"] == staged and data["execution"]["recovery"] == recovery,
                               "Staged request identity or recovery changed")
            # Sealing adds the exact E summary effect; pin its fresh bounded scope.
            scope = self._scope(path, "preparation")
            # The final body is public-safe and binds E through a noncircular scope.
            self._prep_effect(path, data, heads, "request_scope:" + data["digest"], lambda:
                self.transport.update_request_pr(scope, heads, staged["number"], staged["head_sha"],
                                                 contract.request_title(data), contract.request_body(data)))
            state = self.journal.load(); prep = state["preparations"][key]
            prep["status"] = "AWAITING_OWNER_APPROVAL"; prep["execution_sha256"] = data["digest"]
            prep["pr"] = staged; self.journal._save(state)
            return self._result(data, "AWAITING_OWNER_APPROVAL", pr=staged)

    def _result(self, data, status, **extra):
        return {"profile": MODE, "status": status, "proposal_sha256": data["digest"],
                "transport_origin": self.transport.transport_origin,
                "mock_only": self.transport.transport_origin != "github-https",
                "production_authorized": False, **extra}

    def status(self):
        result = self.journal.status()
        result["transport_origin"] = self.transport.transport_origin
        return result
    def _assets(self, data):
        assets = {}
        for name, expected in data["payload"]["release"]["assets"].items():
            receipt = self._receipt(data["digest"], "upload_asset:" + name)
            frozen.require(receipt is not None and receipt["name"] == name and
                           receipt["sha256"] == expected["sha256"] and receipt["size"] == expected["size"],
                           "Incomplete or altered asset receipts")
            assets[name] = {k: receipt[k] for k in ("id", "sha256", "size")}
        return assets

    def _verify_assets(self, data):
        for name, asset in self._assets(data).items():
            self.transport.download_asset(self._receipt(data["digest"], "create_draft")["id"],
                                          asset["id"], name, asset["sha256"], asset["size"])

    def _retention(self, data, observed, recovering):
        payload = data["payload"]
        old = {item["sha256"] for item in payload["retention"]["before"]["packages"]}
        history = [r for r in observed["releases"]
                   if not (recovering and r["tag"] == payload["release"]["tag"])]
        recorded = [tx for tx in self.journal.load()["transactions"].values()
                    if tx["status"] == "RECORDED" and
                    tx.get("finalization", {}).get("merge_sha") == payload["expected"]["main_sha"]]
        if old:
            frozen.require(len(recorded) == 1 and "public_gate" in recorded[0],
                           "Historical release inventory is not retained by this installation")
            prior = recorded[0]["public_gate"]
            frozen.require(release_inventory(history) == prior["releases"],
                           "Historical Release asset, checksum or disclosure metadata changed")
            for tag, target in prior["tag_commits"].items():
                frozen.require(self.transport.read_tag(tag)["commit"] == target,
                               "Historical immutable tag changed")
        else:
            frozen.require(not history, "Unknown historical Release inventory")
        seen = set()
        for release in observed["releases"]:
            if recovering and release["tag"] == payload["release"]["tag"]:
                continue
            frozen.require(not release["draft"] and release["immutable"] is True,
                           "Unknown draft or mutable historical Release blocks publication")
            for asset in release["assets"]:
                if asset["name"].endswith(".zip"):
                    frozen.require(asset["sha256"] in old, "Unreconciled historical package")
                    seen.add(asset["sha256"])
                self.transport.download_asset(release["id"], asset["id"],
                                              asset["name"], asset["sha256"], asset["size"])
        frozen.require(seen == old, "Published ledger and historical Release inventory disagree")
        if not recovering:
            frozen.require(not any(r["tag"] == payload["release"]["tag"] for r in observed["releases"]),
                           "Release tag collision")
        self._verify_main(data)

    def _phase_state(self, data, observed):
        tx = self.journal.load()["transactions"][data["digest"]]
        tag = data["payload"]["release"]["tag"]
        old = [r for r in tx["baseline_releases"] if r["tag"] != tag]
        actual = [r for r in observed["releases"] if r["tag"] != tag]
        frozen.require(release_inventory(actual) == release_inventory(old), "Historical Release state changed")
        for historical_tag, target in tx.get("baseline_tags", {}).items():
            frozen.require(self.transport.read_tag(historical_tag)["commit"] == target, "Historical immutable tag changed")
        current = [r for r in observed["releases"] if r["tag"] == tag]
        receipts = tx["receipts"]
        if "create_tag" in receipts:
            frozen.require(self.transport.read_tag(tag)["commit"] == data["payload"]["release"]["commit"],
                           "Reviewed tag target changed")
        if "create_draft" not in receipts:
            frozen.require(not current, "Unexpected Release before approved draft creation")
            return
        frozen.require(len(current) == 1 and current[0]["id"] == receipts["create_draft"]["id"], "Release identity changed")
        release = current[0]
        desired = data["payload"]["release"]
        frozen.require(release["name"] == desired["name"] and release["notes"] == desired["notes"],
                       "Reviewed Release disclosure changed")
        assets = []
        for name in sorted(desired["assets"]):
            receipt = receipts.get("upload_asset:" + name)
            if receipt:
                assets.append({k: receipt[k] for k in ("id", "name", "size", "sha256")})
        frozen.require(sorted(release["assets"], key=lambda a: a["name"]) == assets, "Unexpected staged asset change")
        published = "publish_release" in receipts
        frozen.require(release["draft"] is not published and release["immutable"] is published,
                       "Unexpected Release publication state")

    def _verify_main(self, data):
        payload = data["payload"]
        expected = payload["main_base"]
        commit = self.transport.read_commit(expected["commit"])
        frozen.require(commit["tree"]["sha"] == expected["tree"], "Main tree differs from reviewed baseline")
        tree = self.transport.read_tree(expected["tree"])
        actual = {item["path"]: item for item in tree["tree"] if item["type"] == "blob"}
        frozen.require(set(actual) == set(expected["files"]), "Complete main inventory changed")
        for name, item in actual.items():
            frozen.require(item["mode"] == "100644", "Main baseline contains unsupported mode")
            self.transport.read_blob(item["sha"], expected_sha256=expected["files"][name]["sha256"])

    def _pages(self, path, data, heads):
        scope = self._scope(path, "publication", data=data)
        p = data["payload"]; pages = p["pages"]
        if self._receipt(data["digest"], "pages_ref") is not None:
            frozen.require(heads["pages_sha"] == pages["commit"], "Recovered Pages head changed")
            return
        files = {n: frozen.safe_read(data["root"] / pages["site_prefix"] / frozen.safe_name(n))
                 for n in pages["site_files"]}
        import publication_pilot_contract as contract
        plan = self.transport.prepare_pages(heads, files, message=contract.pages_message(data))
        frozen.require(plan["tree"] == pages["tree"] and plan["commit"] == pages["commit"],
                       "Complete Pages preparation differs from frozen proposal")
        for name, raw in sorted(files.items()):
            self._effect(path, data, heads, "pages_blob:" + name,
                         lambda raw=raw: self.transport.create_blob(scope, heads, raw, expected_sha=frozen.git_object("blob", raw)))
        self._effect(path, data, heads, "pages_tree", lambda: self.transport.create_tree(
            scope, heads, plan["blobs"], pages["tree"]))
        self._effect(path, data, heads, "pages_commit", lambda: self.transport.create_commit(
            scope, heads, pages["tree"], pages["parent"], plan["message"], pages["commit"]))
        self._effect(path, data, heads, "pages_ref", lambda: self.transport.fast_forward_pages(
            scope, heads, pages["commit"], pages["parent"], pages["tree"]))

    def execute(self, path, expected_digest):
        """Consume the exact owner decision before the first publication effect."""
        import publication_pilot_contract as contract
        data = self._load(path, expected_digest)
        frozen.require(data.get("execution") is not None, "Sealed execution is missing")
        p = data["payload"]; e = data["execution"]
        with self.journal.lock():
            state = self.journal.load(); prep = state["preparations"].get(data["payload_sha256"])
            frozen.require(e["nonce"] not in state["used"], "Owner authorization nonce replay")
            frozen.require(prep is not None and prep.get("execution_sha256") == data["digest"] and
                           prep.get("status") == "AWAITING_OWNER_APPROVAL" and prep.get("pending") is None and
                           prep.get("pr") == e["pr"], "Request PR was not completely staged by this installation")
            frozen.require(e["nonce"] not in state["used"], "Owner authorization nonce replay")
            frozen.require(e["recovery"] is not None or state["active"] is None,
                           "Incomplete publication blocks the next release")
            proof = self._owner(data)
            frozen.require(str(proof["review_id"]) not in state["owner_reviews"], "Owner authorization review replay")
            heads = self._heads(data)
            if e["recovery"] is not None:
                old = state["transactions"].get(e["recovery"]["transaction"])
                frozen.require(old is not None, "Unknown recovery transaction")
                if "pages_ref" in old["receipts"]:
                    heads["pages_sha"] = p["pages"]["commit"]
            observed = self.transport.inspect(expected_heads=heads); self._policy()
            self._retention(data, observed, e["recovery"] is not None)
            self.journal.claim(data, observed["snapshot_sha256"], observed, owner_review_id=proof["review_id"])
            state = self.journal.load(); state["transactions"][data["digest"]]["owner_review_id"] = proof["review_id"]
            state["transactions"][data["digest"]]["pr"] = e["pr"]
            state["transactions"][data["digest"]]["owner_proof"] = proof
            state["transactions"][data["digest"]]["task_id"] = p["task"]["id"]
            state["transactions"][data["digest"]]["material_path"] = str(Path(path).absolute())
            state["transactions"][data["digest"]]["baseline_tags"] = {
                r["tag"]: self.transport.read_tag(r["tag"])["commit"] for r in observed["releases"]
                if r["tag"] != p["release"]["tag"]}
            state["preparation_active"] = None; self.journal._save(state)
            scope = self._scope(path, "publication", data=data)
            try:
                for op in e["operations"]:
                    kind = op["kind"]; key = operation_id(op)
                    if key in self._tx(data)["completed"]:
                        continue
                    if kind == "create_tag":
                        self._effect(path, data, heads, kind, lambda: self.transport.create_tag(
                            scope, heads, p["release"]["tag"], p["release"]["commit"]))
                    elif kind == "create_draft":
                        self._effect(path, data, heads, kind, lambda: self.transport.create_draft(
                            scope, heads, p["release"]["tag"], p["release"]["commit"],
                            p["release"]["name"], p["release"]["notes"]))
                    elif kind == "upload_asset":
                        name = op["name"]; asset = p["release"]["assets"][name]
                        raw = frozen.safe_read(data["root"] / asset["path"])
                        release_id = self._tx(data)["receipts"]["create_draft"]["id"]
                        self._effect(path, data, heads, key, lambda: self.transport.upload_asset(
                            scope, heads, release_id, p["release"]["tag"], name, raw, asset["sha256"]))
                    elif kind == "verify_assets":
                        self._verify_assets(data)
                    elif kind == "publish_release":
                        self._verify_assets(data)
                        self._effect(path, data, heads, kind, lambda: self.transport.publish_release(
                            scope, heads, self._tx(data)["receipts"]["create_draft"]["id"], p["release"]["tag"],
                            p["release"]["commit"], self._assets(data), name=p["release"]["name"], notes=p["release"]["notes"]))
                    elif kind == "promote_pages":
                        self._pages(path, data, heads); heads["pages_sha"] = p["pages"]["commit"]
                    elif kind == "verify_public":
                        self._await_public(path, data, heads)
                    elif kind == "merge_ledger":
                        # Public verification is repeated immediately before the only main write.
                        self._await_public(path, data, heads)
                        validation = self.transport.observe_validation(e["pr"]["head_sha"])
                        frozen.require(validation.get("commit") == e["pr"]["head_sha"] and
                                       validation.get("status") == "completed" and validation.get("conclusion") == "success",
                                       "Pinned validation workflow/job is unverified")
                        frozen.require("verify_public" in self._tx(data)["completed"], "Public gate is incomplete")
                        self._effect(path, data, heads, kind, lambda: self.transport.merge_ledger_pr(
                            scope, heads, e["pr"]["number"], e["pr"]["head_sha"], p["retention"]["main_tree"]))
                        merge = self._verify_merge(data)
                        self.journal.update(data["digest"], completed=key)
                        self.journal.finish(data["digest"])
                        return self._result(data, "RECORDED", merge_sha=merge)
                    else:
                        raise ValueError("Unapproved pilot operation")
                    self.journal.update(data["digest"], completed=key)
                raise ValueError("Publication omitted exact ledger merge")
            except BaseException:
                self.journal.fail(data["digest"])
                raise

    def _await_public(self, path, data, heads):
        """Poll only narrowly classified pending reads; never retry a write.

        The fixed budget and interval cannot be supplied through the CLI. An
        in-flight read may finish after the deadline; it never supplies a PASS
        after that deadline and no further authorized effect follows it.
        """
        from publication_github_live import PendingPagesReadiness, PendingPublicBytes
        self._fresh(path, data)
        state = self.journal.load(); tx = state["transactions"][data["digest"]]
        saved = tx.get("readiness")
        if saved is None:
            started = self.now()
            deadline = min(started + timedelta(seconds=120), frozen.timestamp(data["execution"]["expires_at"]))
            attempts = 0
            tx["readiness"] = {"status": "STARTED", "attempts": 0, "started_at": frozen.utc(started),
                "deadline": frozen.utc(deadline), "reason": None, "observed_at": frozen.utc(started)}
            self.journal._save(state)
        else:
            started = frozen.timestamp(saved["started_at"]); deadline = frozen.timestamp(saved["deadline"])
            attempts = saved["attempts"]
            frozen.require(type(attempts) is int and attempts >= 0 and
                           started < deadline <= started + timedelta(seconds=120) and
                           deadline <= frozen.timestamp(data["execution"]["expires_at"]),
                           "Persisted readiness budget changed")
        wall_budgets = getattr(self, "_readiness_wall_deadlines", {})
        self._readiness_wall_deadlines = wall_budgets
        wall_deadline = wall_budgets.setdefault(data["digest"], time.monotonic() +
            min(120, max(0, (deadline - self.now()).total_seconds())))
        def remaining():
            return min((deadline - self.now()).total_seconds(), wall_deadline - time.monotonic())
        def record(status, reason=None):
            state = self.journal.load()
            tx = state["transactions"][data["digest"]]
            value = {"status": status, "attempts": attempts, "deadline": frozen.utc(deadline),
                     "started_at": frozen.utc(started), "reason": reason, "observed_at": frozen.utc(self.now())}
            tx["readiness"] = value
            tx.setdefault("readiness_history", []).append(copy.deepcopy(value))
            self.journal._save(state)
        while True:
            if remaining() <= 0:
                record("TIMED_OUT")
                raise ValueError("Pages/public readiness deadline reached; fresh authorization may be required")
            self._fresh(path, data)
            proof = self._owner(data)
            frozen.require(proof["review_id"] == self._tx(data)["owner_review_id"],
                           "Consumed owner decision changed while awaiting Pages")
            if remaining() <= 0:
                record("TIMED_OUT")
                raise ValueError("Pages/public readiness deadline reached during approval observation")
            attempts += 1
            record("OBSERVING")
            try:
                self._public(data, heads)
            except (PendingPagesReadiness, PendingPublicBytes) as pending:
                reason = "pages" if isinstance(pending, PendingPagesReadiness) else "public_bytes"
                record("PENDING", reason)
                pause = min(5, remaining())
                if pause <= 0:
                    record("TIMED_OUT", reason)
                    raise ValueError("Pages/public readiness deadline reached; fresh authorization may be required") from None
                self.wait(pause)
                continue
            if remaining() <= 0:
                record("TIMED_OUT")
                raise ValueError("Public verification completed after its readiness deadline")
            self._fresh(path, data)
            proof = self._owner(data)
            frozen.require(proof["review_id"] == self._tx(data)["owner_review_id"],
                           "Consumed owner decision changed during public verification")
            if remaining() <= 0:
                record("TIMED_OUT")
                raise ValueError("Public verification completed after its readiness deadline")
            record("VERIFIED")
            return

    def _public(self, data, heads):
        self._verify_assets(data)
        p = data["payload"]
        observed = self.transport.inspect(expected_heads=heads)
        self._phase_state(data, observed)
        release = next((r for r in observed["releases"] if r["tag"] == p["release"]["tag"]), None)
        frozen.require(release is not None and release["immutable"] is True and release["draft"] is False,
                       "Public Release is not immutable")
        deployment = self.transport.observe_pages_deployment(p["pages"]["commit"])
        frozen.require(deployment.get("commit") == p["pages"]["commit"] and
                       deployment.get("conclusion") == "success" and deployment.get("status") == "completed",
                       "Actual Pages deploy job is incomplete or belongs to another commit")
        build = self.transport.read_pages_build(p["pages"]["commit"])
        frozen.require(build.get("status") == "built" and build.get("commit") == p["pages"]["commit"],
                       "Pages deployment is pending, failed or mismatched")
        for name, checksum in p["pages"]["site_files"].items():
            mime = "application/zip" if name.endswith(".zip") else "text/html" if name.endswith(".html") else None
            self.transport.read_public(name, checksum, mime=mime, previous_sha256=p["expected"]["site_files"].get(name))
        self.transport.read_public("", p["pages"]["site_files"]["index.html"], mime="text/html",
                                   previous_sha256=p["expected"]["site_files"].get("index.html"))
        for name in ("repository.ai.kodi-0.1.0.zip", "incoming/README.md", "releases/manifest.json"):
            self.transport.read_absent(name)
        state = self.journal.load()
        state["transactions"][data["digest"]]["public_gate"] = {
            "pages_commit": p["pages"]["commit"], "release_id": release["id"],
            "site_sha256": digest(p["pages"]["site_files"]), "deployment_sha256": digest(deployment),
            "releases": release_inventory(observed["releases"]),
            "tag_commits": {r["tag"]: self.transport.read_tag(r["tag"])["commit"] for r in observed["releases"]},
            "verified_at": frozen.utc(self.now()), "transport_origin": self.transport.transport_origin,
            "production_authorized": False}
        self.journal._save(state)

    def _verify_merge(self, data):
        p = data["payload"]; expected = data["execution"]["pr"]
        pr = self.transport.read_ledger_pr(expected["number"])
        frozen.require(pr.get("merged") is True and pr.get("state") == "closed" and
                       pr.get("head", {}).get("sha") == expected["head_sha"] and
                       pr.get("head", {}).get("ref") == expected["head_ref"] and
                       pr.get("base", {}).get("ref") == "main", "Exact ledger PR is not merged")
        observed = self.transport.inspect(); merge = pr.get("merge_commit_sha")
        frozen.require(observed["main_sha"] == merge and observed["pages_sha"] == p["pages"]["commit"],
                       "Post-merge branch identities changed")
        commit = self.transport.read_commit(merge)
        frozen.require(commit["tree"]["sha"] == p["retention"]["main_tree"] and
                       [a["sha"] for a in commit["parents"]] == [p["expected"]["main_sha"], expected["head_sha"]],
                       "Merged ledger tree or exact two parents differ; forward reconciliation required")
        # Verify the complete tree, including every unchanged protected baseline file.
        tree = self.transport.read_tree(p["retention"]["main_tree"])
        files = {n: frozen.safe_read(data["root"] / item["path"]) for n, item in p["main_base"]["files"].items()}
        files.update({"releases/manifest.json": frozen.safe_read(data["root"] / p["retention"]["successor_path"]),
                      "config/qualification.json": frozen.safe_read(data["root"] / p["retention"]["config_path"])})
        actual = {item["path"]: item["sha"] for item in tree["tree"]
                  if item["type"] == "blob" and item["mode"] == "100644"}
        frozen.require(actual == {n: frozen.git_object("blob", raw) for n, raw in files.items()},
                       "Complete merged main tree changed")
        for name, raw in files.items():
            self.transport.read_blob(actual[name], expected_sha256=frozen.sha(raw))
        self._public(data, {"main_sha": merge, "pages_sha": p["pages"]["commit"]})
        state = self.journal.load()
        state["transactions"][data["digest"]]["finalization"] = {
            "merge_sha": merge, "tree": p["retention"]["main_tree"],
            "parents": [p["expected"]["main_sha"], expected["head_sha"]],
            "public_gate_sha256": digest(state["transactions"][data["digest"]]["public_gate"])}
        self.journal._save(state)
        return merge

    def _receipt(self, txid, key):
        return self.journal.load()["transactions"][txid]["receipts"].get(key)

    def reconcile(self, path, expected_digest):
        """GET/HEAD only; lost responses never cause an automatic retry."""
        import publication_pilot_contract as contract
        data = self._load(path, expected_digest, observation=True)
        p = data["payload"]
        with self.journal.lock():
            state = self.journal.load()
            frozen.require(state["active"] == data["digest"], "No matching interrupted transaction")
            tx = state["transactions"][data["digest"]]
            observed = self.transport.inspect()
            if tx["pending"] == "merge_ledger" or "merge_ledger" in tx["receipts"]:
                pr = self.transport.read_ledger_pr(data["execution"]["pr"]["number"])
                if pr.get("merged") is True:
                    merge = self._verify_merge(data)
                    state = self.journal.load(); tx = state["transactions"][data["digest"]]
                    if tx["pending"] == "merge_ledger":
                        tx["receipts"]["merge_ledger"] = {"sha": merge, "merged": True}
                        tx["pending"] = None
                    if "merge_ledger" not in tx["completed"]: tx["completed"].append("merge_ledger")
                    self.journal._save(state); self.journal.finish(data["digest"])
                    return self._result(data, "RECORDED", merge_sha=merge, automatic_retry=False)
                frozen.require(pr.get("state") == "open" and pr.get("merged") is False,
                               "Ledger merge outcome is ambiguous")
                tx["pending"] = None
                self.journal._save(state)
                state = self.journal.load(); tx = state["transactions"][data["digest"]]
            frozen.require(observed["main_sha"] == p["expected"]["main_sha"] and
                           observed["pages_sha"] in {p["expected"]["pages_sha"], p["pages"]["commit"]},
                           "Unexpected remote heads require owner reconciliation")
            current = next((r for r in observed["releases"] if r["tag"] == p["release"]["tag"]), None)
            pending = tx["pending"]; receipt = None; absent = False
            if pending == "create_tag":
                actual = self.transport.read_tag(p["release"]["tag"], absent=True)
                absent = actual is None
                if not absent:
                    frozen.require(actual["commit"] == p["release"]["commit"], "Conflicting recovery tag")
                    receipt = {"tag": p["release"]["tag"], "commit": actual["commit"]}
            elif pending == "create_draft":
                absent = current is None
                if not absent:
                    frozen.require(current["draft"] and current["name"] == p["release"]["name"] and
                                   current["notes"] == p["release"]["notes"], "Conflicting recovery draft")
                    receipt = {"id": current["id"], "tag": current["tag"]}
            elif pending and pending.startswith("upload_asset:"):
                frozen.require(current is not None and current["draft"] is True, "Recovery draft missing")
                name = pending.split(":", 1)[1]
                actual = next((a for a in current["assets"] if a["name"] == name), None)
                absent = actual is None
                if not absent:
                    expected = p["release"]["assets"][name]
                    frozen.require(actual["sha256"] == expected["sha256"] and actual["size"] == expected["size"], "Conflicting recovery asset")
                    receipt = self.transport.download_asset(current["id"], actual["id"],
                                                           name, expected["sha256"], expected["size"])
            elif pending == "publish_release":
                frozen.require(current is not None, "Recovery Release missing")
                absent = current["draft"] is True and current["immutable"] is False
                if not absent:
                    frozen.require(current["draft"] is False and current["immutable"] is True, "Release state ambiguous")
                    self._verify_assets(data)
                    receipt = {"id": current["id"], "tag": current["tag"], "immutable": True}
            elif pending == "pages_ref":
                absent = observed["pages_sha"] == p["expected"]["pages_sha"]
                if not absent:
                    commit = self.transport.read_commit(p["pages"]["commit"])
                    frozen.require(commit["tree"]["sha"] == p["pages"]["tree"] and
                                   [a["sha"] for a in commit["parents"]] == [p["pages"]["parent"]], "Recovery Pages identity mismatch")
                    receipt = {"sha": p["pages"]["commit"], "parent": p["pages"]["parent"], "tree": p["pages"]["tree"], "force": False}
            elif pending and (pending.startswith("pages_blob:") or pending.startswith("ledger_blob:")):
                name = pending.split(":", 1)[1]
                if pending.startswith("pages_blob:"):
                    frozen.require(name in p["pages"]["site_files"], "Unreviewed Pages recovery path")
                    raw = frozen.safe_read(data["root"] / p["pages"]["site_prefix"] / name)
                else:
                    mapping = {"releases/manifest.json": p["retention"]["successor_path"],
                               "config/qualification.json": p["retention"]["config_path"]}
                    frozen.require(name in mapping, "Unreviewed ledger recovery path")
                    raw = frozen.safe_read(data["root"] / mapping[name])
                sha = frozen.git_object("blob", raw)
                actual = self.transport.read_blob(sha, expected_sha256=frozen.sha(raw), absent=True)
                absent = actual is None
                if not absent: receipt = {"sha": sha}
            elif pending in {"pages_tree", "ledger_tree"}:
                if pending == "pages_tree":
                    sha = p["pages"]["tree"]
                    files = {n: frozen.safe_read(data["root"] / p["pages"]["site_prefix"] / n) for n in p["pages"]["site_files"]}
                else:
                    sha = p["retention"]["main_tree"]
                    files = {n: frozen.safe_read(data["root"] / item["path"]) for n, item in p["main_base"]["files"].items()}
                    files.update({"releases/manifest.json": frozen.safe_read(data["root"] / p["retention"]["successor_path"]),
                                  "config/qualification.json": frozen.safe_read(data["root"] / p["retention"]["config_path"])})
                actual = self.transport.read_tree(sha, absent=True)
                absent = actual is None
                if not absent:
                    wanted = {n: frozen.git_object("blob", raw) for n, raw in files.items()}
                    seen = {a["path"]: a["sha"] for a in actual["tree"] if a["type"] == "blob" and a["mode"] == "100644"}
                    frozen.require(seen == wanted, "Recovery tree content differs")
                    receipt = {"sha": sha}
            elif pending in {"pages_commit", "ledger_commit"}:
                meta = p["pages"] if pending == "pages_commit" else {
                    "commit": p["retention"]["main_commit"], "tree": p["retention"]["main_tree"], "parent": p["retention"]["main_parent"]}
                actual = self.transport.read_commit(meta["commit"], absent=True)
                absent = actual is None
                if not absent:
                    frozen.require(actual["tree"]["sha"] == meta["tree"] and
                                   [a["sha"] for a in actual["parents"]] == [meta["parent"]], "Recovery commit content differs")
                    receipt = {"sha": meta["commit"], "tree": meta["tree"], "parent": meta["parent"]}
            elif pending == "ledger_branch":
                branch = "publication-ledger/" + data["execution"]["payload_sha256"]
                actual = self.transport.read_ref(branch, absent=True)
                absent = actual is None
                if not absent:
                    frozen.require(actual["object"]["sha"] == p["retention"]["main_commit"], "Recovery ledger branch changed")
                    receipt = {"branch": branch, "sha": p["retention"]["main_commit"]}
            elif pending == "ledger_pr":
                branch = "publication-ledger/" + data["execution"]["payload_sha256"]
                actual = self.transport.find_ledger_pr(branch, p["retention"]["main_commit"])
                absent = actual is None
                if not absent:
                    receipt = {"number": actual["number"], "branch": branch, "sha": p["retention"]["main_commit"],
                               "state": "PUBLIC_BUT_UNRECONCILED"}
            elif pending is not None:
                return {"status": "UNKNOWN_REMOTE_STATE", "pending": pending, "mock_only": self.transport.transport_origin != "github-https",
                        "production_authorized": False, "automatic_retry": False}
            if pending is not None:
                frozen.require(absent or receipt is not None, "Incomplete reconciliation")
                if receipt is not None:
                    tx["receipts"][pending] = dict(receipt, transport_origin=self.transport.transport_origin, production_authorized=False)
                tx["pending"] = None
            self.journal._save(state)
            self._phase_state(data, observed)
            state = self.journal.load(); tx = state["transactions"][data["digest"]]; prefix = []
            for operation in contract.operations(p):
                kind = operation["kind"]; key = operation_id(operation)
                if kind in {"create_tag", "create_draft", "upload_asset", "publish_release"}:
                    if key not in tx["receipts"]: break
                elif kind == "verify_assets":
                    if not all("upload_asset:" + n in tx["receipts"] for n in p["release"]["assets"]): break
                    self._verify_assets(data)
                elif kind == "promote_pages":
                    if "pages_ref" not in tx["receipts"]: break
                elif kind == "verify_public":
                    if "verify_public" not in tx["completed"]: break
                    self._public(data, {"main_sha": observed["main_sha"], "pages_sha": observed["pages_sha"]})
                else:
                    break
                prefix.append(key)
            state = self.journal.load(); tx = state["transactions"][data["digest"]]
            tx["completed"] = prefix; tx["reconciled"] = True; tx["status"] = "RECONCILED_NEEDS_FRESH_OWNER_APPROVAL"
            tx["remote_sha256"] = observed["snapshot_sha256"]
            self.journal._save(state)
            return {"status": tx["status"], "mock_only": self.transport.transport_origin != "github-https", "production_authorized": False,
                    "recovery": {"transaction": data["digest"], "remote_state_sha256": observed["snapshot_sha256"], "completed": prefix}}
    def reconcile_request(self, path, expected_digest=None):
        """GET-only observation of interrupted metadata; never an automatic retry."""
        import publication_pilot_contract as contract
        data = self._load(path, observation=True)
        frozen.require(expected_digest is None or expected_digest in {data["payload_sha256"], data["digest"]},
                       "Request material digest mismatch")
        p = data["payload"]; r = p["retention"]; key = data["payload_sha256"]
        with self.journal.lock():
            state = self.journal.load(); prep = state["preparations"].get(key)
            frozen.require(prep is not None and state["preparation_active"] == key,
                           "No matching interrupted metadata request")
            heads = self.transport.inspect(expected_heads=self._heads(data)); self._policy()
            pending = prep["pending"]; receipt = None; absent = False
            if pending and pending.startswith("ledger_blob:"):
                name = pending.split(":", 1)[1]
                paths = {"releases/manifest.json": r["successor_path"], "config/qualification.json": r["config_path"]}
                frozen.require(name in paths, "Unknown metadata blob")
                raw = frozen.safe_read(data["root"] / paths[name]); sha = frozen.git_object("blob", raw)
                actual = self.transport.read_blob(sha, expected_sha256=frozen.sha(raw), absent=True)
                absent = actual is None
                if not absent: receipt = {"sha": sha}
            elif pending == "ledger_tree":
                actual = self.transport.read_tree(r["main_tree"], absent=True); absent = actual is None
                if not absent:
                    files = {n: frozen.safe_read(data["root"] / item["path"]) for n, item in p["main_base"]["files"].items()}
                    files.update({"releases/manifest.json": frozen.safe_read(data["root"] / r["successor_path"]),
                                  "config/qualification.json": frozen.safe_read(data["root"] / r["config_path"])})
                    wanted = {n: frozen.git_object("blob", raw) for n, raw in files.items()}
                    seen = {a["path"]: a["sha"] for a in actual["tree"] if a["type"] == "blob" and a["mode"] == "100644"}
                    frozen.require(seen == wanted, "Metadata tree differs")
                    receipt = {"sha": r["main_tree"]}
            elif pending == "ledger_commit":
                actual = self.transport.read_commit(r["main_commit"], absent=True); absent = actual is None
                if not absent:
                    frozen.require(actual["tree"]["sha"] == r["main_tree"] and
                                   [a["sha"] for a in actual["parents"]] == [r["main_parent"]], "Metadata commit differs")
                    receipt = {"sha": r["main_commit"]}
            elif pending == "ledger_branch":
                branch = contract.ledger_branch(data); actual = self.transport.read_ref(branch, absent=True)
                absent = actual is None
                if not absent:
                    frozen.require(actual["object"]["sha"] == r["main_commit"], "Metadata branch changed")
                    receipt = {"branch": branch, "sha": r["main_commit"]}
            elif pending == "ledger_pr":
                actual = self.transport.find_ledger_pr(contract.ledger_branch(data), r["main_commit"])
                absent = actual is None
                if not absent:
                    frozen.require(actual["body"] == contract.preparation_body(data) and
                                   actual["title"] == contract.request_title(data), "Request PR scope differs")
                    receipt = {"number": actual["number"], "branch": contract.ledger_branch(data), "sha": r["main_commit"]}
            elif pending and pending.startswith("request_scope:"):
                frozen.require(data.get("execution") is not None and pending == "request_scope:" + data["digest"],
                               "Sealed request scope differs")
                pr = self.transport.read_ledger_pr(data["execution"]["pr"]["number"])
                frozen.require(pr["head"]["sha"] == r["main_commit"] and pr["base"]["sha"] == p["expected"]["main_sha"],
                               "Request PR heads changed")
                absent = pr["body"] == contract.preparation_body(data)
                frozen.require(absent or pr["body"] == contract.request_body(data), "Unexpected request PR body")
                if not absent: receipt = {"number": pr["number"], "sha": r["main_commit"]}
            elif pending is not None:
                raise ValueError("Unknown metadata intent")
            if pending is not None:
                frozen.require(absent or receipt is not None, "Metadata intent remains ambiguous")
                if receipt is not None: prep["receipts"][pending] = receipt
                prep["pending"] = None
            prep["status"] = "RECONCILED_METADATA_REQUEST"; prep["remote_sha256"] = heads["snapshot_sha256"]
            self.journal._save(state)
            return self._result(data, prep["status"], automatic_retry=False)

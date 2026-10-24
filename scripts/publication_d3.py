"""Local D3 journal and one-shot qualification coordinator.

Only the concrete scripted mock GitHub transport is accepted. This extends the
existing frozen-package machinery; it has no network sender, credential loader,
service or model-facing publication tool. Every result has production authority
false. An interrupted intent needs observation and a fresh approved execution.
"""
from __future__ import annotations

import copy
from contextlib import contextmanager
import fcntl
import os
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

import publication_proposal as frozen
from publication_fake import durable, regular, digest
from publication_operator import utc


MODE = "isolated-transport-qualification"


def operation_id(operation):
    return operation["kind"] + (":" + operation["name"] if "name" in operation else "")


class QualificationJournal:
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
                self._save({"schema": 1, "mode": MODE, "mock_only": True,
                            "production_authorized": False, "identity": self.identity,
                            "generation": 0, "used": {}, "owner_runs": {}, "active": None,
                            "transactions": {}}, initial=True)
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
        frozen.closed(state, {"schema", "mode", "mock_only", "production_authorized", "identity", "generation",
                              "used", "owner_runs", "active", "transactions"})
        frozen.require(state.get("schema") == 1 and state.get("mode") == MODE and
                       state.get("mock_only") is True and state.get("production_authorized") is False and
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
                raw = frozen.canonical({"nonce": nonce, "proof_sha256": proof_digest, "mock_only": True})
                durable(self.root / "revocations" / name, raw, exclusive=True)
                index[name] = frozen.sha(raw)
                durable(self.root / "revocations/index.json", frozen.canonical(index))
        finally:
            os.close(fd)

    def check_revoked(self, nonce):
        frozen.require(nonce + ".json" not in self.revocations(), "Owner authorization revoked")

    def claim(self, bundle, remote_digest, remote_snapshot=None, owner_run_id=None):
        state = self.load()
        execution = bundle["execution"]
        nonce = execution["nonce"]
        self.check_revoked(nonce)
        frozen.require(nonce not in state["used"], "Owner authorization nonce replay")
        if owner_run_id is not None:
            frozen.require(type(owner_run_id) is int and owner_run_id > 0 and str(owner_run_id) not in state["owner_runs"],
                           "Owner authorization run replay")
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
        if owner_run_id is not None:
            state["owner_runs"][str(owner_run_id)] = bundle["digest"]
        state["active"] = bundle["digest"]
        state["transactions"][bundle["digest"]] = {
            "origin": origin, "nonce": nonce, "payload_sha256": execution["payload_sha256"],
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
        tx["status"] = "UNKNOWN_REMOTE_STATE" if tx["pending"] else "INCOMPLETE"
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
                       tx["completed"] and tx["completed"][-1] == "finalize_ledger",
                       "Unverified finalization cannot clear active release")
        tx["status"] = "RECORDED"
        state["active"] = None
        self._save(state)

    def status(self):
        with self.lock():
            value = self.load()
            return {"mode": MODE, "mock_only": True, "production_authorized": False,
                    "active": value["active"], "transactions": copy.deepcopy(value["transactions"]),
                    "generation": value["generation"]}


class LocalQualificationOperator:
    """One-shot extension of the frozen-package workflow, using mocks only."""

    def __init__(self, root, enrollment, transport, owner, credentials, *, clock=None):
        import publication_d3_contract as contract
        import publication_github as github
        import publication_owner as approval
        self.enrollment = contract.validate_enrollment(enrollment)
        frozen.require(type(transport) is github.GitHubQualification and
                       type(transport.sender) is github.ScriptedMockSender and
                       transport.enrolled == contract.transport_enrollment(self.enrollment),
                       "Only the enrolled concrete mock transport is supported")
        frozen.require(type(owner) is approval.OwnerVerifier and owner.enrollment == self.enrollment,
                       "Missing matching owner-verification configuration")
        frozen.require(type(credentials) is dict and set(credentials) ==
                       {"inspect", "read", "write", "ledger_pr", "policy", "ledger_read", "pages_read"}, "Missing operation credentials")
        caps = {"inspect": {"contents": "read", "pages": "read"}, "read": {"contents": "read"},
                "write": {"contents": "write"}, "ledger_pr": {"contents": "read", "pull_requests": "write"},
                "policy": {"administration": "read", "actions": "read", "contents": "read"},
                "ledger_read": {"pull_requests": "read"}, "pages_read": {"pages": "read"}}
        for name, cap in caps.items():
            transport._credentials(credentials[name], cap)
        self.transport = transport
        self.owner = owner
        self.credentials = dict(credentials)
        self.clock = clock
        self.journal = QualificationJournal(root, {
            "installation_uuid": self.enrollment["installation_uuid"], "epoch": self.enrollment["epoch"],
            "enrollment_sha256": digest(self.enrollment)})

    def now(self):
        return utc(self.clock() if self.clock else None)

    def _load(self, path, expected_digest, *, observation=False):
        import publication_d3_contract as contract
        data = contract.load_bundle(path, expected_digest=expected_digest, now=self.now(), observation=observation)
        frozen.require(data["enrollment"] == self.enrollment and
                       (observation or data["transport_eligible"] is True), "D3 enrollment or eligibility changed")
        data["_guard"] = frozen.inventory(path)
        return data

    def _owner(self, data, run_id):
        from publication_owner import RevokedApproval
        self.journal.check_revoked(data["execution"]["nonce"])
        try:
            receipt = self.owner.verify(data, run_id=run_id, now=self.now())
        except RevokedApproval as error:
            frozen.require(error.nonce == data["execution"]["nonce"] and error.proposal_sha256 == data["digest"],
                           "Revocation proof scope changed")
            self.journal.latch_revocation(error.nonce, error.revocation_sha256)
            raise
        frozen.require(receipt.get("mock_only") is True and receipt.get("network_authorized") is False and
                       receipt.get("production_authorized") is False and receipt.get("proposal_sha256") == data["digest"] and
                       receipt.get("nonce") == data["execution"]["nonce"], "Owner proof exceeds local scope")
        return receipt

    def _receipt(self, txid, key):
        return self.journal.load()["transactions"][txid]["receipts"].get(key)

    def _effect(self, path, data, run_id, heads, name, function):
        # Callables here are fixed trusted adapter calls, never caller inputs.
        prior = self._receipt(data["digest"], name)
        if prior is not None:
            return prior
        import publication_d3_contract as contract
        # Full semantic validation ran at entry. Rehash every sealed byte and
        # trusted module before each effect; equal bytes retain that derivation.
        frozen.require(frozen.inventory(path) == data["_guard"] and
                       contract.toolchain() == data["payload"]["toolchain"], "Frozen D3 proposal or toolchain changed")
        frozen.require(frozen.timestamp(data["execution"]["created_at"]) <= self.now() <
                       frozen.timestamp(data["execution"]["expires_at"]), "D3 execution expired")
        self._owner(data, run_id)
        observed = self.transport.inspect(self.credentials["inspect"], expected_heads=heads)
        self._phase_state(data, observed)
        policy = self.transport.inspect_policy(self.credentials["policy"])
        frozen.require(policy["policy_sha256"] == self.enrollment["policy_sha256"], "Remote publication policy changed")
        self.journal.update(data["digest"], pending=name)
        self.journal.audit(data["digest"], operation=name, status="intent", at=frozen.utc(self.now()))
        result = function()
        frozen.require(type(result) is dict and result.get("mock_only") is True and
                       result.get("production_authorized") is False, "Unexpected adapter receipt")
        self.journal.update(data["digest"], receipt=result)
        self.journal.audit(data["digest"], operation=name, status="verified", at=frozen.utc(self.now()))
        return result

    def execute(self, path, expected_digest, *, run_id, pages_run_id=None):
        """A pending protected ledger PR never means RECORDED."""
        import publication_d3_contract as contract
        data = self._load(path, expected_digest)
        p = data["payload"]
        heads = {k: p["expected"][k] for k in ("main_sha", "pages_sha")}
        with self.journal.lock():
            initial = self.journal.load()
            frozen.require(data["execution"]["nonce"] not in initial["used"], "Owner authorization nonce replay")
            frozen.require(type(run_id) is int and run_id > 0 and str(run_id) not in initial["owner_runs"],
                           "Owner authorization run replay")
            frozen.require(data["execution"]["recovery"] is not None or initial["active"] is None,
                           "Incomplete publication blocks the next release")
            self._owner(data, run_id)
            recovery = data["execution"]["recovery"]
            if recovery is not None:
                old = self.journal.load()["transactions"].get(recovery["transaction"])
                frozen.require(old is not None, "Unknown recovery transaction")
                if "pages_ref" in old["receipts"]:
                    heads["pages_sha"] = p["pages"]["commit"]
            observed = self.transport.inspect(self.credentials["inspect"], expected_heads=heads)
            policy = self.transport.inspect_policy(self.credentials["policy"])
            frozen.require(policy["policy_sha256"] == self.enrollment["policy_sha256"], "Remote policy baseline changed")
            self._retention(data, observed, recovery is not None)
            self.journal.claim(data, observed["snapshot_sha256"], observed, owner_run_id=run_id)
            txid = data["digest"]
            frozen.require(pages_run_id is None or type(pages_run_id) is int and pages_run_id > 0,
                           "Invalid correlated Pages run ID")
            state = self.journal.load()
            state["transactions"][txid]["pages_run_id"] = pages_run_id
            self.journal._save(state)
            try:
                for operation in data["execution"]["operations"]:
                    kind = operation["kind"]
                    if kind == "create_tag":
                        self._effect(path, data, run_id, heads, kind, lambda: self.transport.create_tag(
                            self.credentials["write"], heads, p["release"]["tag"], p["release"]["commit"]))
                    elif kind == "create_draft":
                        self._effect(path, data, run_id, heads, kind, lambda: self.transport.create_draft(
                            self.credentials["write"], heads, p["release"]["tag"], p["release"]["commit"],
                            p["release"]["name"], p["release"]["notes"]))
                    elif kind == "upload_asset":
                        name = operation["name"]; asset = p["release"]["assets"][name]
                        raw = frozen.safe_read(data["root"] / asset["path"])
                        release_id = self._receipt(txid, "create_draft")["id"]
                        self._effect(path, data, run_id, heads, "upload_asset:" + name, lambda: self.transport.upload_asset(
                            self.credentials["write"], heads, release_id, p["release"]["tag"], name, raw, asset["sha256"]))
                    elif kind == "verify_assets":
                        self._verify_assets(data)
                    elif kind == "publish_release":
                        assets = self._assets(data)
                        self._effect(path, data, run_id, heads, kind, lambda: self.transport.publish_release(
                            self.credentials["write"], heads, self._receipt(txid, "create_draft")["id"],
                            p["release"]["tag"], p["release"]["commit"], assets,
                            name=p["release"]["name"], notes=p["release"]["notes"]))
                    elif kind == "promote_pages":
                        self._pages(path, data, run_id, heads)
                        heads["pages_sha"] = p["pages"]["commit"]
                    elif kind == "verify_public":
                        if pages_run_id is None:
                            self.journal.update(txid, status="AWAITING_PAGES_OWNER_REVIEW")
                            return {"status": "AWAITING_PAGES_OWNER_REVIEW", "mock_only": True,
                                    "production_authorized": False, "proposal_sha256": txid}
                        self._public(data, heads)
                    elif kind == "finalize_ledger":
                        self._ledger(path, data, run_id, heads)
                        self.journal.update(txid, status="PUBLIC_BUT_UNRECONCILED")
                        return {"status": "PUBLIC_BUT_UNRECONCILED", "mock_only": True,
                                "production_authorized": False, "proposal_sha256": txid}
                    else:
                        raise ValueError("Unapproved qualification operation")
                    self.journal.update(txid, completed=contract.operation_id(operation))
            except BaseException:
                self.journal.fail(txid)
                raise

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
            self.transport.download_asset(self.credentials["read"], self._receipt(data["digest"], "create_draft")["id"],
                                          asset["id"], name, asset["sha256"], asset["size"])

    def _retention(self, data, observed, recovering):
        payload = data["payload"]
        old = {item["sha256"] for item in payload["retention"]["before"]["packages"]}
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
                self.transport.download_asset(self.credentials["read"], release["id"], asset["id"],
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
        frozen.require(frozen.canonical(actual) == frozen.canonical(old), "Historical Release state changed")
        current = [r for r in observed["releases"] if r["tag"] == tag]
        receipts = tx["receipts"]
        if "create_tag" in receipts:
            frozen.require(self.transport.read_tag(self.credentials["read"], tag)["commit"] == data["payload"]["release"]["commit"],
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
        commit = self.transport.read_commit(self.credentials["read"], expected["commit"])
        frozen.require(commit["tree"]["sha"] == expected["tree"], "Main tree differs from reviewed baseline")
        tree = self.transport.read_tree(self.credentials["read"], expected["tree"])
        actual = {item["path"]: item for item in tree["tree"] if item["type"] == "blob"}
        frozen.require(set(actual) == set(expected["files"]), "Complete main inventory changed")
        for name, item in actual.items():
            frozen.require(item["mode"] == "100644", "Main baseline contains unsupported mode")
            self.transport.read_blob(self.credentials["read"], item["sha"], expected_sha256=expected["files"][name]["sha256"])

    def _pages(self, path, data, run_id, heads):
        p = data["payload"]; pages = p["pages"]
        if self._receipt(data["digest"], "pages_ref") is not None:
            frozen.require(heads["pages_sha"] == pages["commit"], "Recovered Pages head changed")
            return
        files = {n: frozen.safe_read(data["root"] / pages["site_prefix"] / frozen.safe_name(n))
                 for n in pages["site_files"]}
        plan = self.transport.prepare_pages(self.credentials["read"], heads, files)
        frozen.require(plan["tree"] == pages["tree"] and plan["commit"] == pages["commit"],
                       "Complete Pages preparation differs from frozen proposal")
        for name, raw in sorted(files.items()):
            self._effect(path, data, run_id, heads, "pages_blob:" + name,
                         lambda raw=raw: self.transport.create_blob(self.credentials["write"], heads, raw))
        self._effect(path, data, run_id, heads, "pages_tree", lambda: self.transport.create_tree(
            self.credentials["write"], heads, plan["blobs"], pages["tree"]))
        self._effect(path, data, run_id, heads, "pages_commit", lambda: self.transport.create_commit(
            self.credentials["write"], heads, pages["tree"], pages["parent"], plan["message"], pages["commit"]))
        self._effect(path, data, run_id, heads, "pages_ref", lambda: self.transport.fast_forward_pages(
            self.credentials["write"], heads, pages["commit"], pages["parent"], pages["tree"]))

    def _public(self, data, heads, *, retained_review=False):
        self._verify_assets(data)
        p = data["payload"]
        tx = self.journal.load()["transactions"][data["digest"]]
        retained_review = retained_review or "pages_owner_proof" in tx["receipts"]
        if retained_review:
            proof = tx["receipts"].get("pages_owner_proof")
            proof_tx = self.journal.load()["transactions"].get(proof["proposal_sha256"]) if proof else None
            frozen.require(proof is not None and proof_tx is not None and proof_tx["origin"] == tx["origin"] and
                           proof_tx["payload_sha256"] == tx["payload_sha256"] and proof_tx["review_sha256"] == tx["review_sha256"] and
                           proof_tx["receipts"].get("pages_owner_proof") == proof and
                           proof["pages_commit"] == p["pages"]["commit"] and
                           frozen.timestamp(proof["observed_at"]) < frozen.timestamp(proof["execution_expires_at"]),
                           "No retained timely Pages owner proof")
        else:
            frozen.require(type(tx.get("pages_run_id")) is int, "Matching Pages owner review is missing")
            from publication_owner import RevokedApproval
            try:
                proof = self.owner.verify_pages(data, tx["pages_run_id"], now=self.now())
            except RevokedApproval as error:
                frozen.require(error.nonce == data["execution"]["nonce"] and error.proposal_sha256 == data["digest"],
                               "Pages revocation proof scope changed")
                self.journal.latch_revocation(error.nonce, error.revocation_sha256)
                raise
            frozen.require(proof.get("mock_only") is True and proof.get("production_authorized") is False,
                           "Pages proof exceeds local qualification scope")
            proof = dict(proof, pages_commit=p["pages"]["commit"], execution_expires_at=data["execution"]["expires_at"])
            state = self.journal.load()
            state["transactions"][data["digest"]]["receipts"]["pages_owner_proof"] = proof
            self.journal._save(state)
        observed = self.transport.inspect(self.credentials["inspect"], expected_heads=heads)
        release = next((r for r in observed["releases"] if r["tag"] == p["release"]["tag"]), None)
        frozen.require(release is not None and release["immutable"] is True and not release["draft"],
                       "Public Release is not verified immutable")
        build = self.transport.read_pages_build(self.credentials["pages_read"])
        frozen.require(build.get("status") == "built" and build.get("commit") == p["pages"]["commit"],
                       "Pages deployment pending/failed or commit mismatch")
        for name, checksum in p["pages"]["site_files"].items():
            mime = "application/zip" if name.endswith(".zip") else "text/html" if name.endswith(".html") else None
            self.transport.read_public(name, checksum, mime=mime)
        self.transport.read_public("", p["pages"]["site_files"]["index.html"], mime="text/html")
        for name in ("repository.ai.kodi-0.1.0.zip", "incoming/README.md", "releases/manifest.json"):
            self.transport.read_absent(name)

    def _ledger(self, path, data, run_id, heads):
        retention = data["payload"]["retention"]
        changed = {"releases/manifest.json": frozen.safe_read(data["root"] / retention["successor_path"]),
                   "config/qualification.json": frozen.safe_read(data["root"] / retention["config_path"])}
        blobs = {}
        for name, raw in sorted(changed.items()):
            receipt = self._effect(path, data, run_id, heads, "ledger_blob:" + name,
                                   lambda raw=raw: self.transport.create_blob(self.credentials["write"], heads, raw))
            blobs[name] = receipt["sha"]
        self._effect(path, data, run_id, heads, "ledger_tree", lambda: self.transport.create_tree(
            self.credentials["write"], heads, blobs, retention["main_tree"], base_tree=data["payload"]["main_base"]["tree"]))
        self._effect(path, data, run_id, heads, "ledger_commit", lambda: self.transport.create_commit(
            self.credentials["write"], heads, retention["main_tree"], retention["main_parent"],
            "Simulated retention finalization", retention["main_commit"]))
        branch = "publication-ledger/" + data["execution"]["payload_sha256"]
        self._effect(path, data, run_id, heads, "ledger_branch", lambda: self.transport.create_ledger_branch(
            self.credentials["write"], heads, branch, retention["main_commit"]))
        self._effect(path, data, run_id, heads, "ledger_pr", lambda: self.transport.create_ledger_pr(
            self.credentials["ledger_pr"], heads, branch, retention["main_commit"],
            "Record D3 qualification " + data["payload"]["qualification"]["version"],
            "Frozen qualification proposal sha256:" + data["digest"] + "; production_authorized=false"))

    def observe_finalization(self, path, expected_digest):
        """Observe the owner's normal protected merge; never approve or merge it."""
        data = self._load(path, expected_digest, observation=True)
        with self.journal.lock():
            state = self.journal.load()
            frozen.require(state["active"] == data["digest"], "No active finalization")
            tx = state["transactions"][data["digest"]]
            frozen.require(tx["pending"] is None and "verify_public" in tx["completed"] and
                           "ledger_pr" in tx["receipts"], "Public verification/ledger PR incomplete")
            receipt = tx["receipts"]["ledger_pr"]
            pr = self.transport.read_ledger_pr(self.credentials["ledger_read"], receipt["number"])
            p = data["payload"]; retention = p["retention"]
            frozen.require(pr.get("merged") is True and pr.get("state") == "closed" and
                           pr.get("head", {}).get("sha") == retention["main_commit"] and
                           pr.get("head", {}).get("ref") == receipt["branch"] and
                           pr.get("base", {}).get("ref") == "main", "Ledger protected PR is not exactly merged")
            reviews = self.transport.read_ledger_reviews(self.credentials["ledger_read"], receipt["number"])
            owner_reviews = [r for r in reviews if type(r.get("user", {}).get("id")) is int and
                             r["user"]["id"] == self.enrollment["human_owner_id"]
                             and r.get("user", {}).get("type") == "User" and
                             r.get("state") in {"APPROVED", "CHANGES_REQUESTED", "DISMISSED"}]
            frozen.require(bool(owner_reviews) and owner_reviews[-1].get("state") == "APPROVED" and
                           owner_reviews[-1].get("commit_id") == retention["main_commit"],
                           "Missing current owner review of exact ledger commit")
            observed = self.transport.inspect(self.credentials["inspect"])
            merge_sha = pr.get("merge_commit_sha")
            frozen.require(observed["main_sha"] == merge_sha and observed["pages_sha"] == p["pages"]["commit"],
                           "Finalization branch identity changed")
            commit = self.transport.read_commit(self.credentials["read"], merge_sha)
            frozen.require(commit["tree"]["sha"] == retention["main_tree"] and
                           [item["sha"] for item in commit["parents"]] == [retention["main_parent"], retention["main_commit"]],
                           "Merged ledger tree or exact parents differ")
            self._public(data, {"main_sha": merge_sha, "pages_sha": p["pages"]["commit"]}, retained_review=True)
            self.journal.update(data["digest"], completed="finalize_ledger")
            self.journal.finish(data["digest"])
            return {"status": "RECORDED", "mock_only": True, "production_authorized": False,
                    "proposal_sha256": data["digest"], "merge_sha": merge_sha}

    def reconcile(self, path, expected_digest):
        """GET/HEAD only; lost responses never cause an automatic retry."""
        import publication_d3_contract as contract
        data = self._load(path, expected_digest, observation=True)
        p = data["payload"]
        with self.journal.lock():
            state = self.journal.load()
            frozen.require(state["active"] == data["digest"], "No matching interrupted transaction")
            tx = state["transactions"][data["digest"]]
            observed = self.transport.inspect(self.credentials["inspect"])
            frozen.require(observed["main_sha"] == p["expected"]["main_sha"] and
                           observed["pages_sha"] in {p["expected"]["pages_sha"], p["pages"]["commit"]},
                           "Unexpected remote heads require owner reconciliation")
            current = next((r for r in observed["releases"] if r["tag"] == p["release"]["tag"]), None)
            pending = tx["pending"]; receipt = None; absent = False
            if pending == "create_tag":
                actual = self.transport.read_tag(self.credentials["read"], p["release"]["tag"], absent=True)
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
                    receipt = self.transport.download_asset(self.credentials["read"], current["id"], actual["id"],
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
                    commit = self.transport.read_commit(self.credentials["read"], p["pages"]["commit"])
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
                actual = self.transport.read_blob(self.credentials["read"], sha, expected_sha256=frozen.sha(raw), absent=True)
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
                actual = self.transport.read_tree(self.credentials["read"], sha, absent=True)
                absent = actual is None
                if not absent:
                    wanted = {n: frozen.git_object("blob", raw) for n, raw in files.items()}
                    seen = {a["path"]: a["sha"] for a in actual["tree"] if a["type"] == "blob" and a["mode"] == "100644"}
                    frozen.require(seen == wanted, "Recovery tree content differs")
                    receipt = {"sha": sha}
            elif pending in {"pages_commit", "ledger_commit"}:
                meta = p["pages"] if pending == "pages_commit" else {
                    "commit": p["retention"]["main_commit"], "tree": p["retention"]["main_tree"], "parent": p["retention"]["main_parent"]}
                actual = self.transport.read_commit(self.credentials["read"], meta["commit"], absent=True)
                absent = actual is None
                if not absent:
                    frozen.require(actual["tree"]["sha"] == meta["tree"] and
                                   [a["sha"] for a in actual["parents"]] == [meta["parent"]], "Recovery commit content differs")
                    receipt = {"sha": meta["commit"], "tree": meta["tree"], "parent": meta["parent"]}
            elif pending == "ledger_branch":
                branch = "publication-ledger/" + data["execution"]["payload_sha256"]
                self.transport._credentials(self.credentials["read"], {"contents": "read"})
                actual = self.transport._ref(self.credentials["read"], "heads/" + branch, absent=True)
                absent = actual is None
                if not absent:
                    frozen.require(actual["object"]["sha"] == p["retention"]["main_commit"], "Recovery ledger branch changed")
                    receipt = {"branch": branch, "sha": p["retention"]["main_commit"]}
            elif pending == "ledger_pr":
                branch = "publication-ledger/" + data["execution"]["payload_sha256"]
                actual = self.transport.find_ledger_pr(self.credentials["ledger_read"], branch, p["retention"]["main_commit"])
                absent = actual is None
                if not absent:
                    receipt = {"number": actual["number"], "branch": branch, "sha": p["retention"]["main_commit"],
                               "state": "PUBLIC_BUT_UNRECONCILED"}
            elif pending is not None:
                return {"status": "UNKNOWN_REMOTE_STATE", "pending": pending, "mock_only": True,
                        "production_authorized": False, "automatic_retry": False}
            if pending is not None:
                frozen.require(absent or receipt is not None, "Incomplete reconciliation")
                if receipt is not None:
                    tx["receipts"][pending] = dict(receipt, mock_only=True, production_authorized=False)
                tx["pending"] = None
            self.journal._save(state)
            self._phase_state(data, observed)
            state = self.journal.load(); tx = state["transactions"][data["digest"]]; prefix = []
            for operation in contract.operations(p):
                kind = operation["kind"]; key = contract.operation_id(operation)
                if kind in {"create_tag", "create_draft", "upload_asset", "publish_release"}:
                    if key not in tx["receipts"]: break
                elif kind == "verify_assets":
                    if not all("upload_asset:" + n in tx["receipts"] for n in p["release"]["assets"]): break
                    self._verify_assets(data)
                elif kind == "promote_pages":
                    if "pages_ref" not in tx["receipts"]: break
                elif kind == "verify_public":
                    if "verify_public" not in tx["completed"]: break
                    self._public(data, {"main_sha": observed["main_sha"], "pages_sha": observed["pages_sha"]}, retained_review=True)
                else:
                    break
                prefix.append(key)
            tx["completed"] = prefix; tx["reconciled"] = True; tx["status"] = "RECONCILED_NEEDS_FRESH_OWNER_APPROVAL"
            tx["remote_sha256"] = observed["snapshot_sha256"]
            self.journal._save(state)
            return {"status": tx["status"], "mock_only": True, "production_authorized": False,
                    "recovery": {"transaction": data["digest"], "remote_state_sha256": observed["snapshot_sha256"], "completed": prefix}}

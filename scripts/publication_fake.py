"""Disk-only fake GitHub/Pages destination. No HTTP, credentials or remote Git.

This module cannot operate a real repository. The sole destination uses the
reserved .invalid namespace, and every effect is an isolated local file write.
"""
from __future__ import annotations

import copy
import fcntl
import json
import os
from pathlib import Path
import stat

import publication_proposal as proposal


def digest(value):
    return proposal.sha(proposal.canonical(value))


def regular(path):
    path = Path(path)
    for ancestor in (path, *path.parents):
        proposal.require(not ancestor.is_symlink(), "Linked fake storage path")
    if path.exists():
        mode = path.lstat()
        proposal.require(stat.S_ISREG(mode.st_mode) and mode.st_nlink == 1,
                         "Nonregular or hardlinked fake storage")
    return path


def durable(path, data, *, exclusive=False):
    path = regular(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if exclusive:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(data); stream.flush(); os.fsync(stream.fileno())
    else:
        temporary = path.with_name(path.name + ".new")
        fd = os.open(regular(temporary), os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(data); stream.flush(); os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            if temporary.exists(): temporary.unlink()
    directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try: os.fsync(directory)
    finally: os.close(directory)


class FakeGitHub:
    """Concrete fake-only backend. It has no URL or transport configuration."""

    def __init__(self, root, *, fault=None):
        self.root = Path(root).resolve(strict=True)
        proposal.require(self.root.is_dir(), "Fake destination directory missing")
        for parent in (Path(root), *Path(root).parents):
            proposal.require(not parent.is_symlink(), "Linked fake destination")
        self.fault = fault
        self.snapshot()

    @classmethod
    def create(cls, root, expected, initial_files, ledger, config=b"{}"):
        root = Path(root)
        proposal.require(not root.exists(), "Fake destination already exists")
        for parent in root.parents:
            proposal.require(not parent.is_symlink(), "Linked fake destination ancestor")
        root.mkdir(parents=True)
        (root / "blobs").mkdir()
        proposal.validate_expected(expected)
        proposal.require(type(ledger) is bytes and type(config) is bytes and
                         all(type(b) is bytes for b in initial_files.values()), "Fake seeds must be bytes")
        proposal.require(type(initial_files) is dict and
                         {n: proposal.sha(b) for n, b in initial_files.items()} == expected["site_files"],
                         "Fake initial site identity mismatch")
        proposal.require(proposal.sha(ledger) == expected["ledger_sha256"], "Fake initial ledger mismatch")
        state = {"schema": 1, "mode": "local-simulation", "destination": proposal.SIM_DESTINATION,
                 "main_sha": expected["main_sha"], "pages_sha": expected["pages_sha"],
                 "pages_tree": expected["pages_tree"], "site_files": {}, "public_files": {},
                 "historical": {}, "tags": {}, "releases": {}, "calls": [],
                 "ledger_sha256": proposal.sha(ledger), "config_sha256": proposal.sha(config),
                 "deployment": {"commit": expected["pages_sha"], "status": "success"},
                 "policy": {"protected": True, "immutable_releases": True, "owner_id": 1}}
        for data in list(initial_files.values()) + [ledger, config]:
            path = root / "blobs" / proposal.sha(data)
            if not path.exists(): durable(path, data, exclusive=True)
        for name, data in initial_files.items():
            state["site_files"][name] = proposal.sha(data)
            if name.endswith((".zip", ".zip.sha256")): state["historical"][name] = proposal.sha(data)
        state["public_files"] = dict(state["site_files"])
        durable(root / "state.json", proposal.canonical(state), exclusive=True)
        return cls(root)

    def blob(self, checksum):
        proposal.require(type(checksum) is str and len(checksum) == 64 and
                         all(c in "0123456789abcdef" for c in checksum), "Malformed fake blob digest")
        data = proposal.safe_read(regular(self.root / "blobs" / checksum))
        proposal.require(proposal.sha(data) == checksum, "Historical fake artifact modified")
        return data

    def _store_blob(self, data):
        checksum = proposal.sha(data)
        path = self.root / "blobs" / checksum
        if path.exists(): proposal.require(self.blob(checksum) == data, "Immutable fake blob conflict")
        else: durable(path, data, exclusive=True)
        return checksum

    def snapshot(self):
        raw = proposal.safe_read(regular(self.root / "state.json"), proposal.MAX_JSON)
        state = proposal.strict_load(raw)
        proposal.require(type(state.get("schema")) is int and state.get("schema") == 1 and state.get("mode") == "local-simulation" and
                         state.get("destination") == proposal.SIM_DESTINATION,
                         "Unauthorized/out-of-scope fake destination")
        proposal.destination(state["destination"])
        proposal.require(type(state["destination"]["repository_id"]) is int and
                         type(state["destination"]["owner_id"]) is int and
                         type(state["policy"].get("owner_id")) is int and
                         type(state["policy"].get("protected")) is bool and
                         type(state["policy"].get("immutable_releases")) is bool,
                         "Boolean or malformed fake numeric identity")
        for checksum in set(state["site_files"].values()) | set(state["public_files"].values()) | set(state["historical"].values()) | {state["ledger_sha256"], state["config_sha256"]}:
            self.blob(checksum)
        for path, checksum in state["historical"].items():
            proposal.require(state["site_files"].get(path) == checksum,
                             "Immutable historical package removed or changed")
        for release in state["releases"].values():
            for asset in release["assets"].values():
                proposal.require(len(self.blob(asset["sha256"])) == asset["size"], "Fake asset size mismatch")
        return copy.deepcopy(state)

    def _fault(self, when, kind):
        if self.fault == (when, kind): raise TimeoutError("Injected fake failure " + when + " " + kind)

    @staticmethod
    def site_bytes(payload, bundle_root):
        prefix = payload["pages"]["site_prefix"].rstrip("/")
        result = {}
        for path, checksum in payload["pages"]["site_files"].items():
            data = regular(Path(bundle_root) / prefix / path).read_bytes()
            proposal.require(proposal.sha(data) == checksum, "Frozen Pages bytes changed")
            result[path] = data
        return result

    def apply(self, kind, payload, bundle_root, expected_snapshot, transaction):
        """One bounded simulated operation, checked under a local destination lock."""
        lockpath = regular(self.root / "lock")
        fd = os.open(lockpath, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            state = self.snapshot()
            proposal.require(state == expected_snapshot, "Unexpected concurrent fake remote change")
            proposal.require(state["policy"] == {"protected": True, "immutable_releases": True, "owner_id": 1},
                             "Fake protection or authorization policy changed")
            self._fault("before", kind)
            release = payload["release"]; pages = payload["pages"]; retention = payload["retention"]
            tag = release["tag"]
            if kind == "create_tag":
                proposal.require(tag not in state["tags"], "Conflicting existing Release tag")
                state["tags"][tag] = release["commit"]
            elif kind == "create_draft":
                proposal.require(state["tags"].get(tag) == release["commit"] and tag not in state["releases"],
                                 "Conflicting Release or tag identity")
                state["releases"][tag] = {"id": len(state["releases"]) + 1, "transaction": transaction,
                    "commit": release["commit"], "name": release["name"], "notes": release["notes"],
                    "assets": {}, "draft": True, "immutable": False}
            elif kind == "upload_assets":
                item = state["releases"][tag]
                proposal.require(item["draft"] and not item["immutable"] and item["transaction"] == transaction,
                                 "Cannot upload to mutable foreign/published Release")
                proposal.require(not item["assets"], "Conflicting existing Release assets")
                for name, record in release["assets"].items():
                    data = regular(Path(bundle_root) / record["path"]).read_bytes()
                    proposal.require(proposal.sha(data) == record["sha256"] and len(data) == record["size"],
                                     "Frozen Release asset mismatch")
                    self._store_blob(data)
                    item["assets"][name] = {"sha256": record["sha256"], "size": record["size"]}
            elif kind == "verify_assets":
                self._verify_assets(state, payload)
                self._fault("after", kind)
                return {"kind": kind, "status": "PASS", "mutation": False}
            elif kind == "publish_release":
                self._verify_assets(state, payload)
                item = state["releases"][tag]
                proposal.require(item["draft"] and item["transaction"] == transaction, "Release already published/foreign")
                item["draft"] = False; item["immutable"] = True
            elif kind == "promote_pages":
                proposal.require(state["pages_sha"] == pages["parent"], "Pages head changed; force/rebase forbidden")
                proposal.require(not state["releases"][tag]["draft"] and state["releases"][tag]["immutable"],
                                 "Release must be verified and immutable before Pages")
                files = self.site_bytes(payload, bundle_root)
                proposal.require(set(state["site_files"]) <= set(files), "Historical site deletion prohibited")
                for path, checksum in state["historical"].items():
                    proposal.require(proposal.sha(files[path]) == checksum, "Historical immutable package replacement")
                state["site_files"] = {n: self._store_blob(b) for n, b in files.items()}
                state["public_files"] = dict(state["site_files"])
                for name, checksum in state["site_files"].items():
                    if name.endswith((".zip", ".zip.sha256")): state["historical"][name] = checksum
                state["pages_sha"] = pages["commit"]; state["pages_tree"] = pages["tree"]
                state["deployment"] = {"commit": pages["commit"], "status": "success"}
            elif kind == "verify_public":
                self.verify_public(state, payload)
                self._fault("after", kind)
                return {"kind": kind, "status": "PASS", "mutation": False}
            elif kind == "finalize_ledger":
                self.verify_public(state, payload)
                proposal.require(state["main_sha"] == retention["main_parent"], "Main head changed before ledger finalization")
                before = json.loads(self.blob(state["ledger_sha256"]))
                after = retention["after"]
                proposal.require(after["packages"][:len(before["packages"])] == before["packages"],
                                 "Ledger history removal/reorder/modification")
                raw = regular(Path(bundle_root) / retention["successor_path"]).read_bytes()
                proposal.require(proposal.sha(raw) == retention["after_sha256"] and json.loads(raw) == after,
                                 "Successor ledger identity mismatch")
                config = regular(Path(bundle_root) / retention["config_path"]).read_bytes()
                proposal.require(proposal.sha(config) == retention["config_sha256"], "Successor config identity mismatch")
                state["ledger_sha256"] = self._store_blob(raw); state["config_sha256"] = self._store_blob(config)
                state["main_sha"] = retention["main_commit"]
            else:
                raise ValueError("Unsupported fake publication operation")
            state["calls"].append({"kind": kind, "transaction": transaction})
            durable(self.root / "state.json", proposal.canonical(state))
            self._fault("after", kind)
            return {"kind": kind, "status": "PASS", "mutation": True, "state_sha256": digest(state)}
        finally:
            os.close(fd)

    def _verify_assets(self, state, payload):
        planned = payload["release"]
        item = state["releases"][planned["tag"]]
        proposal.require(item["commit"] == planned["commit"] and item["name"] == planned["name"] and
                         item["notes"] == planned["notes"] and set(item["assets"]) == set(planned["assets"]),
                         "Incomplete/conflicting Release metadata or assets")
        for name, record in planned["assets"].items():
            asset = item["assets"][name]; data = self.blob(asset["sha256"])
            proposal.require(asset == {"sha256": record["sha256"], "size": record["size"]} and
                             proposal.sha(data) == record["sha256"] and len(data) == record["size"],
                             "Downloaded Release asset mismatch")

    def verify_public(self, state, payload):
        self._verify_assets(state, payload)
        item = state["releases"][payload["release"]["tag"]]
        proposal.require(not item["draft"] and item["immutable"], "Public Release not immutable")
        pages = payload["pages"]
        proposal.require(state["pages_sha"] == pages["commit"] and state["pages_tree"] == pages["tree"] and
                         state["deployment"] == {"commit": pages["commit"], "status": "success"},
                         "Pages deployment not verified for exact commit")
        proposal.require(state["site_files"] == pages["site_files"] and state["public_files"] == pages["site_files"],
                         "Incomplete public Pages verification")
        for name, checksum in state["public_files"].items():
            proposal.require(proposal.sha(self.blob(checksum)) == checksum, "Public artifact hash mismatch")

    def completed_prefix(self, payload, transaction):
        """Read-only reconciliation; never infers a completed byte verification."""
        state = self.snapshot(); result = []
        for call in state["calls"]:
            if call["transaction"] == transaction: result.append(call["kind"])
        return result

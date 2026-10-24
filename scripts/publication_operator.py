"""Nonprivileged, fake-only publication state machine.

Local simulated identities and approvals have no production authority. There is
no GitHub HTTP backend, token handling, shell command, OS identity deployment or
remote authorization implementation in this module.
"""
from __future__ import annotations

import copy
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import os
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import publication_proposal as proposal
from publication_fake import FakeGitHub, digest, durable, regular


KINDS = ("create_tag", "create_draft", "upload_assets", "verify_assets",
         "publish_release", "promote_pages", "verify_public", "finalize_ledger")
MUTATIONS = frozenset(KINDS) - {"verify_assets", "verify_public"}
SIM_AUDIENCE = {"installation_uuid": "0" * 32, "epoch": 1, "app_id": 2,
                "app_installation_id": 3,
                "key_policy_sha256": proposal.sha(b"local-test-policy-v1")}


def utc(now=None):
    if now is None: return datetime.now(timezone.utc)
    if isinstance(now, str):
        proposal.require(re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", now) is not None,
                         "Malformed publication clock")
        return datetime.strptime(now, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    proposal.require(isinstance(now, datetime) and now.tzinfo is not None, "Timezone-aware clock required")
    return now.astimezone(timezone.utc)


class Operator:
    """A one-shot local simulator, never a privileged or remote publisher."""

    def __init__(self, root, backend, *, audience=None, clock=None):
        proposal.require(type(backend) is FakeGitHub, "Only the concrete disk fake backend is supported")
        self.root = Path(root)
        for p in (self.root, *self.root.parents):
            proposal.require(not p.is_symlink(), "Linked operator storage")
        self.root.mkdir(parents=True, exist_ok=True)
        self.root = self.root.resolve(strict=True)
        proposal.require(not self.root.is_relative_to(backend.root) and not backend.root.is_relative_to(self.root),
                         "Operator and fake destination stores must be disjoint")
        self.backend = backend
        self.audience = copy.deepcopy(audience or SIM_AUDIENCE)
        self.clock = clock
        fresh = not (self.root / "state.json").exists() and not (self.root / "journal").exists()
        (self.root / "revocations").mkdir(exist_ok=True)
        proposal.require(not (self.root / "revocations").is_symlink(), "Linked revocation store")
        if fresh:
            proposal.require(not list((self.root / "revocations").iterdir()), "Unexpected initial revocation state")
            durable(self.root / "revocations/index.json", proposal.canonical({}), exclusive=True)
        self._revocations()
        with self._lock():
            if not (self.root / "state.json").exists():
                proposal.require(not (self.root / "journal").exists(), "Missing state with existing journal; recovery required")
                (self.root / "journal").mkdir()
                initial = {"schema": 1, "mode": "local-simulation", "audience": self.audience,
                           "generation": 0, "active": None, "requests": {}, "used": {}, "transactions": {}}
                self._persist(initial, initialize=True)
            self._load()

    def now(self):
        return utc(self.clock() if self.clock else None)

    @contextmanager
    def _lock(self):
        fd = os.open(regular(self.root / "lock"), os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            try: fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc: raise ValueError("Another publication transaction holds the lock") from exc
            yield
        finally: os.close(fd)

    def _load(self):
        state = proposal.strict_load(regular(self.root / "state.json").read_bytes())
        proposal.require(state.get("schema") == 1 and state.get("mode") == "local-simulation" and
                         state.get("audience") == self.audience, "Operator identity/epoch or mode mismatch")
        journal = self.root / "journal"
        proposal.require(journal.is_dir() and not journal.is_symlink(), "Operator journal missing/linked")
        records = sorted(journal.iterdir())
        proposal.require(len(records) == state["generation"] + 1, "Journal generation mismatch; restore stays disabled")
        previous = "0" * 64
        for generation, path in enumerate(records):
            proposal.require(path.name == f"{generation:010d}.json", "Malformed append-only journal sequence")
            raw = regular(path).read_bytes(); record = proposal.strict_load(raw)
            proposal.require(set(record) == {"generation", "previous", "state_sha256"} and
                             record["generation"] == generation and record["previous"] == previous,
                             "Publication journal chain changed")
            previous = proposal.sha(raw)
        proposal.require(record["state_sha256"] == digest(state), "Operator state changed or interrupted journal commit")
        return state

    def _persist(self, state, *, initialize=False):
        if initialize:
            previous = "0" * 64
        else:
            current = self._load()
            proposal.require(current["generation"] == state["generation"], "Stale publication state writer")
            previous = proposal.sha(regular(self.root / "journal" / f'{state["generation"]:010d}.json').read_bytes())
            state["generation"] += 1
        raw = proposal.canonical(state)
        event = {"generation": state["generation"], "previous": previous, "state_sha256": proposal.sha(raw)}
        # Intent/journal reaches durable storage before corresponding state. A
        # crash between these writes blocks future writes rather than guessing.
        durable(self.root / "journal" / f'{state["generation"]:010d}.json', proposal.canonical(event), exclusive=True)
        durable(self.root / "state.json", raw, exclusive=initialize)

    def _bundle(self, bundle, expected_digest):
        result = proposal.load_bundle(bundle, expected_digest=expected_digest, now=self.now())
        execution = result["execution"]
        proposal.require(execution["mode"] == "local-simulation" and execution["destination"] == proposal.SIM_DESTINATION,
                         "Production or out-of-scope destination is forbidden")
        proposal.require(execution["audience"] == self.audience, "Publication operator audience mismatch")
        proposal.require(result.get("simulation_eligible") is True and not result.get("eligibility_blockers"),
                         "Release eligibility blocked: " + "; ".join(result.get("eligibility_blockers", [])))
        proposal.require(utc(execution["created_at"]) <= self.now() < utc(execution["expires_at"]),
                         "Expired or future publication proposal")
        return result

    def _baseline(self, data, snapshot):
        expected = data["execution"]["expected"]
        for name in ("main_sha", "pages_sha", "pages_tree", "ledger_sha256", "site_files"):
            proposal.require(snapshot[name] == expected[name], "Stale proposal / changed fake remote " + name)
        tag = data["payload"]["release"]["tag"]
        proposal.require(tag not in snapshot["tags"] and tag not in snapshot["releases"],
                         "Conflicting existing Release tag/assets")
        ledger = data["payload"]["retention"]["before"]
        retained = {item["sha256"] for item in ledger["packages"]}
        published = {checksum for name, checksum in snapshot["site_files"].items() if name.endswith(".zip")}
        proposal.require(retained == published, "Published ZIP inventory and historical ledger disagree")
        for item in snapshot["releases"].values():
            if item["draft"]: continue
            for name, asset in item["assets"].items():
                if name.endswith(".zip"):
                    proposal.require(asset["sha256"] in retained, "Unreconciled public Release blocks later publication")
                    sidecar = item["assets"].get(name + ".sha256")
                    proposal.require(sidecar is not None and self.backend.blob(sidecar["sha256"]) ==
                                     (asset["sha256"] + "\n").encode(), "Historical Release sidecar mismatch")

    def request(self, bundle, expected_digest):
        """Create a local test-approval request, never a remote dispatch."""
        data = self._bundle(bundle, expected_digest)
        execution = data["execution"]; nonce = execution["nonce"]
        with self._lock():
            state = self._load(); snapshot = self.backend.snapshot()
            proposal.require(nonce not in state["requests"] and nonce not in state["used"], "Publication nonce replay")
            recovery = execution["recovery"]
            if recovery is None:
                proposal.require(state["active"] is None, "Incomplete publication blocks a later release")
                self._baseline(data, snapshot)
                origin = data["digest"]
            else:
                proposal.require(state["active"] == recovery["transaction"], "Recovery does not name active transaction")
                old = state["transactions"][state["active"]]
                proposal.require(old["payload_sha256"] == execution["payload_sha256"] and
                                 old["review_sha256"] == execution["review_sha256"], "Recovery changes reviewed release payload")
                proposal.require(digest(snapshot) == recovery["remote_state_sha256"], "Recovery remote state changed")
                completed = self._reconciled_prefix(old, data["payload"], snapshot)
                proposal.require(completed == recovery["completed"] and
                                 completed + [o["kind"] for o in execution["operations"]] == list(KINDS),
                                 "Recovery must name exact completed prefix and missing suffix")
                origin = old["origin"]
            request = {"mode": "local-simulation", "request_id": nonce, "proposal_sha256": data["digest"],
                       "destination": copy.deepcopy(execution["destination"]), "audience": copy.deepcopy(self.audience),
                       "created_at": execution["created_at"], "expires_at": execution["expires_at"],
                       "remote_state_sha256": digest(snapshot), "origin": origin,
                       "approval": None, "revoked": False}
            state["requests"][nonce] = request
            self._persist(state)
            return {"status": "AWAITING_SIMULATED_OWNER", "request_id": nonce,
                    "proposal_sha256": data["digest"], "simulation_only": True,
                    "publication_authorized": False}

    def simulate_approve(self, request_id, *, owner_id=1):
        """Test harness only. A local record never authenticates a real owner."""
        proposal.require(type(owner_id) is int and owner_id == 1, "Simulated owner identity denied")
        with self._lock():
            state = self._load(); request = state["requests"].get(request_id)
            proposal.require(request is not None and not self._is_revoked(request_id) and not request["revoked"] and request_id not in state["used"],
                             "Missing/revoked/consumed test request")
            proposal.require(request["approval"] is None and self.now() < utc(request["expires_at"]),
                             "Duplicate or expired simulated approval")
            request["approval"] = {"mode": "local-simulation", "actor_id": owner_id,
                "actor_type": "simulated-user", "proposal_sha256": request["proposal_sha256"],
                "nonce": request_id, "destination": copy.deepcopy(request["destination"]),
                "expires_at": request["expires_at"], "status": "approved"}
            self._persist(state)
            return {"status": "SIMULATED_APPROVAL_RECORDED", "simulation_only": True, "publication_authorized": False}

    def revoke(self, request_id, *, owner_id=1):
        proposal.require(type(owner_id) is int and owner_id == 1, "Simulated revocation identity denied")
        proposal.require(type(request_id) is str and re.fullmatch("[0-9a-f]{32}", request_id), "Invalid revocation nonce")
        # Independent durable latch: revocation stays writable/observable while
        # execute owns its transaction lock. State is atomically replaced.
        fd = os.open(regular(self.root / "revocation-lock"), os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            state = proposal.strict_load(regular(self.root / "state.json").read_bytes())
            proposal.require(request_id in state["requests"], "Unknown publication request")
            index = self._revocations()
            path = self.root / "revocations" / (request_id + ".json")
            if not path.exists():
                raw = proposal.canonical({"mode": "local-simulation", "owner_id": 1, "nonce": request_id})
                durable(path, raw, exclusive=True)
                index[path.name] = proposal.sha(raw)
                durable(self.root / "revocations/index.json", proposal.canonical(index))
            return {"status": "REVOKED", "simulation_only": True, "publication_authorized": False}
        finally: os.close(fd)

    def _is_revoked(self, nonce):
        return nonce + ".json" in self._revocations()

    def _revocations(self):
        directory = self.root / "revocations"
        index = proposal.strict_load(proposal.safe_read(regular(directory / "index.json"), proposal.MAX_JSON))
        proposal.require(type(index) is dict and
                         {p.name for p in directory.iterdir()} == set(index) | {"index.json"},
                         "Revocation inventory changed; no publication allowed")
        for name, checksum in index.items():
            proposal.require(re.fullmatch("[0-9a-f]{32}\\.json", name) is not None,
                             "Malformed revocation index")
            raw = proposal.safe_read(regular(directory / name), proposal.MAX_JSON)
            expected = {"mode": "local-simulation", "owner_id": 1, "nonce": name[:-5]}
            proposal.require(proposal.sha(raw) == checksum and raw == proposal.canonical(expected),
                             "Observed revocation latch changed")
        return index

    def _authorization(self, state, execution, expected_digest):
        nonce = execution["nonce"]; request = state["requests"].get(nonce)
        proposal.require(request is not None and not request["revoked"] and not self._is_revoked(nonce),
                         "Publication request missing or revoked")
        approval = request["approval"]
        required = {"mode": "local-simulation", "actor_id": 1, "actor_type": "simulated-user",
            "proposal_sha256": expected_digest, "nonce": nonce, "destination": execution["destination"],
            "expires_at": execution["expires_at"], "status": "approved"}
        proposal.require(proposal.canonical(approval) == proposal.canonical(required) and request["proposal_sha256"] == expected_digest and
                         request["audience"] == self.audience and self.now() < utc(request["expires_at"]),
                         "Missing/expired/mismatched simulated owner authorization")
        return request

    def execute(self, bundle, expected_digest):
        data = self._bundle(bundle, expected_digest)
        execution = data["execution"]; nonce = execution["nonce"]; checksum = data["digest"]
        with self._lock():
            state = self._load(); request = self._authorization(state, execution, checksum)
            proposal.require(nonce not in state["used"] and checksum not in state["transactions"], "Consumed approval replay")
            snapshot = self.backend.snapshot()
            proposal.require(digest(snapshot) == request["remote_state_sha256"], "Remote state changed after approval request")
            recovery = execution["recovery"]
            if recovery is None:
                proposal.require(state["active"] is None, "Incomplete publication blocks later release")
                self._baseline(data, snapshot); completed = []
            else:
                proposal.require(state["active"] == recovery["transaction"] and
                                 digest(snapshot) == recovery["remote_state_sha256"], "Recovery baseline changed")
                completed = list(recovery["completed"])
            transaction = {"digest": checksum, "origin": request["origin"], "nonce": nonce,
                "payload_sha256": execution["payload_sha256"], "review_sha256": execution["review_sha256"],
                "stage": "RESERVED", "completed": completed, "intent": None,
                "expected_snapshot": snapshot, "receipts": [], "error": None}
            state["used"][nonce] = checksum; state["active"] = checksum
            state["transactions"][checksum] = transaction
            # Consumption and intent are durable before the first fake effect.
            self._persist(state)
            try:
                for operation in execution["operations"]:
                    kind = operation["kind"]
                    proposal.require(kind == KINDS[len(transaction["completed"])] and set(operation) == {"kind"},
                                     "Out-of-order or unauthorized publication operation")
                    self._bundle(bundle, checksum)
                    self._authorization(state, execution, checksum)
                    proposal.require(self.backend.snapshot() == transaction["expected_snapshot"],
                                     "Unexpected remote branch/asset/policy change")
                    transaction["intent"] = kind
                    self._persist(state)
                    receipt = self.backend.apply(kind, data["payload"], data["root"],
                                                 transaction["expected_snapshot"], transaction["origin"])
                    observed = self.backend.snapshot()
                    proposal.require((kind in MUTATIONS and receipt.get("state_sha256") == digest(observed)) or
                                     (kind not in MUTATIONS and observed == transaction["expected_snapshot"]),
                                     "Unexpected remote change after operation receipt")
                    transaction["completed"].append(kind); transaction["intent"] = None
                    transaction["expected_snapshot"] = observed
                    transaction["receipts"].append(receipt)
                    transaction["stage"] = {"create_tag": "TAG_CREATED", "create_draft": "DRAFT_STAGED",
                        "upload_assets": "ASSETS_STAGED", "verify_assets": "ASSETS_VERIFIED",
                        "publish_release": "RELEASE_PUBLIC", "promote_pages": "PAGES_SUBMITTED",
                        "verify_public": "PUBLIC_BUT_UNRECONCILED", "finalize_ledger": "RECORDED"}[kind]
                    self._persist(state)
                proposal.require(transaction["completed"] == list(KINDS), "Incomplete publication operation list")
                transaction["stage"] = "RECORDED"
                state["active"] = None
                self._persist(state)
            except BaseException as exc:
                transaction["stage"] = "UNKNOWN_REMOTE_STATE"
                transaction["error"] = type(exc).__name__
                self._persist(state)
                raise
            return {"status": "RECORDED", "simulation_only": True, "publication_authorized": False,
                    "transaction": checksum, "completed": transaction["completed"], "receipts": transaction["receipts"]}

    def _reconciled_prefix(self, transaction, payload, snapshot):
        """Adopt only one ambiguous effect named in this journal's durable intent."""
        completed = list(transaction["completed"])
        intent = transaction["intent"]
        if intent is None: return completed
        old = transaction["expected_snapshot"]
        if snapshot == old: return completed
        observed = [call["kind"] for call in snapshot["calls"] if call["transaction"] == transaction["origin"]]
        previous = [call["kind"] for call in old["calls"] if call["transaction"] == transaction["origin"]]
        proposal.require(intent in MUTATIONS and observed == previous + [intent],
                         "Unknown foreign effect; cannot reconcile publication")
        # Reproduce the intended operation into a temporary in-memory comparison
        # through effect-specific predicates, never by replaying a write.
        release = payload["release"]; tag = release["tag"]
        unchanged = copy.deepcopy(snapshot)
        unchanged["calls"] = old["calls"]
        if intent == "create_tag":
            proposal.require(snapshot["tags"].get(tag) == release["commit"], "Ambiguous tag differs")
            unchanged["tags"].pop(tag)
        elif intent == "create_draft":
            item = snapshot["releases"].get(tag)
            proposal.require(item is not None and item["draft"] and not item["assets"] and
                             item["transaction"] == transaction["origin"] and item["commit"] == release["commit"] and
                             item["name"] == release["name"] and item["notes"] == release["notes"], "Ambiguous draft differs")
            unchanged["releases"].pop(tag)
        elif intent == "upload_assets":
            self.backend._verify_assets(snapshot, payload)
            unchanged["releases"][tag]["assets"] = old["releases"][tag]["assets"]
        elif intent == "publish_release":
            self.backend._verify_assets(snapshot, payload)
            proposal.require(not snapshot["releases"][tag]["draft"] and snapshot["releases"][tag]["immutable"],
                             "Ambiguous public Release differs")
            for key in ("draft", "immutable"):
                unchanged["releases"][tag][key] = old["releases"][tag][key]
        elif intent == "promote_pages":
            self.backend.verify_public(snapshot, payload)
            expected_history = dict(old["historical"])
            expected_history.update({n: s for n, s in payload["pages"]["site_files"].items()
                                     if n.endswith((".zip", ".zip.sha256"))})
            proposal.require(snapshot["historical"] == expected_history, "Unexpected retained history during reconciliation")
            for key in ("site_files", "public_files", "historical", "pages_sha", "pages_tree", "deployment"):
                unchanged[key] = old[key]
        elif intent == "finalize_ledger":
            retention = payload["retention"]
            proposal.require(snapshot["ledger_sha256"] == retention["after_sha256"] and
                             snapshot["config_sha256"] == retention["config_sha256"] and
                             snapshot["main_sha"] == retention["main_commit"], "Ambiguous ledger finalization differs")
            for key in ("ledger_sha256", "config_sha256", "main_sha"): unchanged[key] = old[key]
        proposal.require(unchanged == old, "Unexpected concurrent state during reconciliation")
        return completed + [intent]

    def reconcile(self, bundle, expected_digest):
        """Read-only status and exact recovery description; never resumes writes."""
        # Observation remains useful after expiry; use the existing recorded
        # transaction's proposal bytes without issuing a new authorization.
        data = proposal.load_bundle(bundle, expected_digest=expected_digest, now=None, observation=True)
        with self._lock():
            state = self._load()
            proposal.require(expected_digest in state["transactions"], "No recorded publication transaction")
            transaction = state["transactions"][expected_digest]; snapshot = self.backend.snapshot()
            completed = self._reconciled_prefix(transaction, data["payload"], snapshot)
            return {"status": transaction["stage"], "simulation_only": True,
                    "publication_authorized": False, "transaction": expected_digest,
                    "recovery": {"transaction": expected_digest, "remote_state_sha256": digest(snapshot), "completed": completed},
                    "remaining": [{"kind": k} for k in KINDS[len(completed):]],
                    "remote_snapshot": snapshot}

    def status(self):
        with self._lock():
            state = self._load()
            return {"mode": "local-simulation", "publication_authorized": False,
                    "generation": state["generation"], "active": state["active"],
                    "transactions": {k: {"stage": v["stage"], "completed": v["completed"], "error": v["error"]}
                                     for k, v in state["transactions"].items()}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("init", "request", "approve-test", "execute", "revoke-test", "status", "reconcile"))
    parser.add_argument("--store", type=Path, required=True)
    parser.add_argument("--fake", type=Path, required=True)
    parser.add_argument("--bundle", type=Path)
    parser.add_argument("--digest")
    parser.add_argument("--request-id")
    parser.add_argument("--owner-id", type=int, default=1)
    parser.add_argument("--now")
    parser.add_argument("--baseline-site", type=Path)
    parser.add_argument("--fault", choices=[f"{when}:{kind}" for when in ("before", "after") for kind in KINDS])
    args = parser.parse_args()
    try:
        if args.command == "init":
            proposal.require(args.bundle is not None, "Frozen bundle required for fake initialization")
            data = proposal.load_bundle(args.bundle, args.digest, now=args.now)
            expected = data["execution"]["expected"]; root = data["root"]
            matching = [name for name, record in data["payload"]["files"].items()
                        if record["sha256"] == expected["ledger_sha256"]]
            proposal.require(matching, "Original ledger bytes unavailable")
            ledger = proposal.safe_read(root / matching[0])
            baseline = args.baseline_site or root / data["payload"]["pages"]["site_prefix"]
            initial_files = {name: proposal.safe_read(baseline / proposal.safe_name(name))
                             for name in expected["site_files"]}
            backend = FakeGitHub.create(args.fake, expected, initial_files, ledger)
            operator = Operator(args.store, backend, clock=(lambda: args.now) if args.now else None)
            result = dict(operator.status(), status="FAKE_INITIALIZED")
        else:
            proposal.require(args.store.is_dir() and args.fake.is_dir(), "Existing local stores required")
            fault = tuple(args.fault.split(":")) if args.fault else None
            operator = Operator(args.store, FakeGitHub(args.fake, fault=fault), clock=(lambda: args.now) if args.now else None)
            if args.command == "status": result = operator.status()
            elif args.command in ("approve-test", "revoke-test"):
                proposal.require(args.request_id is not None, "Local request identity required")
                method = operator.simulate_approve if args.command == "approve-test" else operator.revoke
                result = method(args.request_id, owner_id=args.owner_id)
            else:
                proposal.require(args.bundle is not None and args.digest is not None, "Exact frozen bundle and digest required")
                result = getattr(operator, args.command)(args.bundle, args.digest)
        print(proposal.canonical(result).decode())
    except (ValueError, OSError, KeyError, AssertionError) as exc:
        print(proposal.canonical({"status": "BLOCKED", "simulation_only": True,
                                 "publication_authorized": False, "error": str(exc)[:1000]}).decode())
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

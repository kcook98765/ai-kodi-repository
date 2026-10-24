#!/usr/bin/env python3
"""Read-only local observations for simulated publication; no network transport."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import audit_candidate


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def verify_assets(payload, assets):
    require(__debug__, "Independent ZIP checks require nonoptimized Python")
    expected = payload["release"]["assets"]
    require(type(assets) is dict and set(assets) == set(expected), "Simulated Release asset inventory mismatch")
    for name, raw in assets.items():
        require(type(raw) is bytes and len(raw) == expected[name]["size"]
                and sha(raw) == expected[name]["sha256"], "Simulated Release asset digest mismatch")
        if name.endswith(".zip"):
            audit_candidate.archive_files(raw)
            require(assets.get(name + ".sha256") == (sha(raw) + "\n").encode(), "Release sidecar mismatch")
    sums = "".join(f'{sha(assets[n])}  {n}\n' for n in sorted(assets) if n != "SHA256SUMS").encode()
    require(assets.get("SHA256SUMS") == sums, "Release checksum list mismatch")
    return {"status": "PASS", "scope": "local simulated Release byte observation", "assets": len(assets),
            "production_verified": False, "native_verified": False}


def verify_site(payload, files):
    require(__debug__, "Independent ZIP checks require nonoptimized Python")
    expected = payload["pages"]["site_files"]
    require(type(files) is dict and set(files) == set(expected), "Simulated public site inventory mismatch")
    for name, raw in files.items():
        require(type(raw) is bytes and sha(raw) == expected[name], "Simulated public site digest mismatch")
        if name.endswith(".zip"):
            audit_candidate.archive_files(raw)
            require(files.get(name + ".sha256") == (sha(raw) + "\n").encode(), "Public package sidecar mismatch")
    for lane, entry in payload["catalogs"].items():
        raw = files[entry["path"]]
        require(sha(raw) == entry["sha256"] and files.get(entry["path"] + ".sha256") == (sha(raw) + "\n").encode(),
                "Public catalog sidecar mismatch")
        catalog = audit_candidate.xml(raw)
        require(catalog.tag == "addons" and {n.get("id"): n.get("version") for n in catalog} == entry["ids"],
                "Public catalog identity mismatch")
    return {"status": "PASS", "scope": "local simulated complete-site byte observation", "files": len(files),
            "production_verified": False, "native_verified": False}


def observe_directory(bundle, directory):
    """Observation deliberately remains usable after approval expiry; no writes."""
    import publication_proposal as proposal
    payload = proposal.verify_payload(bundle, observation=True)["payload"]
    directory = Path(directory)
    metadata = proposal.inventory(directory)
    files = {n: proposal.safe_read(directory / n) for n in metadata}
    return verify_site(payload, files)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path)
    parser.add_argument("site", type=Path)
    args = parser.parse_args()
    print(json.dumps(observe_directory(args.bundle, args.site), sort_keys=True))

#!/usr/bin/env python3
"""Emit a disposable pilot setup inventory only. No apply mode or remote client."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import publication_proposal as frozen
import publication_pilot_contract as contract
import publication_github_live as github
import publication_d3_contract as d3


def inventory(enrollment):
    e = contract.validate_enrollment(enrollment)
    return {"schema": 1, "profile": contract.PROFILE, "mode": "dry-run-only", "remote_actions": [],
        "destination": contract.transport_enrollment(e), "required_permissions": github.PERMISSIONS,
        "settings": github.expected_policy(e),
        "seeds": {"main": {"releases/manifest.json": {"schema": 1, "packages": []},
                            "config/qualification.json": {}, ".github/CODEOWNERS": "* @kcook98765\n",
                            e["validation_workflow_path"]: {"sha256": e["validation_workflow_sha256"], "source_commit": e["validation_workflow_commit"]}},
                  "gh-pages": {"files": {}, "published_packages": [], "initial_commit": "empty-tree-only"},
                  "d3-fixture-source": {v: {"commit": e["fixture_source"]["commits"][v],
                     "files": {n: frozen.sha(raw) for n, raw in d3.fixture_files(v).items()}} for v in ("1.0.0", "1.1.0")}},
        "manual_requirements": ["Owner creates the separate public organization/repository and App after approval",
            "Owner reviews trusted validation workflow bytes; install no third-party actions or add-on execution",
            "Seed all branches then enable and read back the eight rulesets, immutable Releases and Pages policy",
            "Enroll actual numeric identities and observed policy/source/workflow hashes",
            "Separately approve credential custody, exact-task metadata staging and opt-in tool activation"],
        "production_authorized": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--enrollment", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(inventory(frozen.strict_load(frozen.safe_read(args.enrollment, frozen.MAX_JSON))), sort_keys=True, indent=2))


if __name__ == "__main__": main()

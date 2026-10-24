#!/usr/bin/env python3
"""JSON bridge for the existing role tools; no enrollment/publication operation."""
import argparse
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lifecycle


def main():
    os.umask(0o077)
    lifecycle.require(__debug__, "Independent audits require nonoptimized Python")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--role", required=True)
    parser.add_argument("--operation", choices=lifecycle.ROLES, required=True)
    args = parser.parse_args()
    lifecycle.installation()
    raw = sys.stdin.buffer.read(100_001)
    lifecycle.require(len(raw) <= 100_000, "Oversized role request")
    request = json.loads(raw)
    lifecycle.closed(request, {"task_id", "expected_digest", "arguments"}, {"context"})
    result = lifecycle.Store().operate(args.operation, args.role, request["task_id"],
                                       request["expected_digest"], request["arguments"], context=request.get("context"))
    print(json.dumps(result))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(json.dumps({"status": "BLOCKED", "error": type(error).__name__, "detail": str(error)[:1000]}))
        sys.exit(1)

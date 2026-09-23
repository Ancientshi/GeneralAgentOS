from __future__ import annotations

import argparse
import json
import os
import sys

from .common import BenchError
from .engine import Engine


def main():
    parser = argparse.ArgumentParser(description="Independent GeneralAgentOS benchmark runner")
    parser.add_argument("--config", default=os.getenv("GAOS_BENCH_CONFIG", "benchmarks.yaml"))
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("catalog")
    sub.add_parser("serve", help="Start the MCP stdio server")
    listing = sub.add_parser("tasks")
    listing.add_argument("benchmark")
    listing.add_argument("--query", default="")
    listing.add_argument("--variant")
    listing.add_argument("--offset", type=int, default=0)
    listing.add_argument("--limit", type=int, default=20)
    for name in ("show", "start"):
        p = sub.add_parser(name)
        p.add_argument("benchmark")
        p.add_argument("task_id")
        p.add_argument("--variant")
    for name in ("status", "submit", "evaluate"):
        sub.add_parser(name).add_argument("run_id")
    reference = sub.add_parser("prepare-reference")
    reference.add_argument("task_id")
    args = parser.parse_args()
    if args.command == "serve":
        from .server import serve

        serve(args.config)
        return
    try:
        engine = Engine(args.config)
        if args.command == "catalog":
            result = engine.catalog()
        elif args.command == "tasks":
            result = engine.list_tasks(args.benchmark, args.query, args.variant, args.offset, args.limit)
        elif args.command == "show":
            result = engine.get_task(args.benchmark, args.task_id, args.variant)
        elif args.command == "start":
            result = engine.start(args.benchmark, args.task_id, args.variant)
        elif args.command == "prepare-reference":
            result = engine.prepare_reference(args.task_id)
        else:
            result = {"status": engine.status, "submit": engine.submit, "evaluate": engine.grade}[
                args.command
            ](args.run_id)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        if isinstance(result, dict) and result.get("status") in {
            "blocked",
            "evaluator_error",
            "invalid_submission",
        }:
            raise SystemExit(2)
    except (BenchError, OSError, KeyError) as exc:
        print(json.dumps({"status": "error", "message": str(exc)}), file=sys.stderr)
        raise SystemExit(2) from None


if __name__ == "__main__":
    main()

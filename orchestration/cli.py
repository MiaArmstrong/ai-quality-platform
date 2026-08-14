from __future__ import annotations

import argparse
import json
from pathlib import Path

from tools.validate_contracts import validate_repository

from .compiler import compile_system
from .runtime import MockRoleExecutor, OrchestrationEngine, SQLiteEventStore


def _engine(root: Path, database: Path) -> tuple[OrchestrationEngine, SQLiteEventStore]:
    compiled = compile_system(root)
    store = SQLiteEventStore(database)
    return OrchestrationEngine(compiled, store, MockRoleExecutor()), store


def main() -> int:
    parser = argparse.ArgumentParser(description="AI Quality Platform mock orchestrator")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--db", type=Path, default=Path("orchestration.db"))
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("validate")
    compile_command = commands.add_parser("compile")
    compile_command.add_argument("--output", type=Path)
    start = commands.add_parser("start")
    start.add_argument("--work-item", required=True)
    for name in ("inspect", "resume"):
        command = commands.add_parser(name); command.add_argument("run_id")
    for name in ("approve", "reject"):
        command = commands.add_parser(name); command.add_argument("run_id"); command.add_argument("--by", required=True); command.add_argument("--reason", required=True)
    args = parser.parse_args(); root=args.root.resolve()
    if args.command=="validate":
        errors=validate_repository(root)
        if errors: print(json.dumps({"valid":False,"errors":errors},indent=2)); return 1
        print(json.dumps({"valid":True},indent=2)); return 0
    if args.command=="compile":
        compiled=compile_system(root); payload=compiled.as_dict()
        if args.output: args.output.write_text(json.dumps(payload,indent=2,sort_keys=True),encoding="utf-8")
        print(json.dumps({"snapshot_hash":compiled.snapshot_hash,"sources":len(compiled.source_hashes)},indent=2)); return 0
    engine,store=_engine(root,args.db)
    try:
        if args.command=="start": result={"run_id":engine.start({"text":args.work_item})}
        elif args.command=="inspect": result=engine.inspect(args.run_id)
        elif args.command=="resume": result=engine.resume(args.run_id)
        else:
            engine.decide_gate(args.run_id,"approved" if args.command=="approve" else "rejected",args.by,args.reason)
            result=engine.inspect(args.run_id)["run"]
        print(json.dumps(result,indent=2,sort_keys=True)); return 0
    finally: store.close()


if __name__ == "__main__": raise SystemExit(main())

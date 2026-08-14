"""Run the deterministic automate workflow through both rejection/rework paths."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from orchestration.compiler import compile_system
from orchestration.runtime import MockRoleExecutor, OrchestrationEngine, SQLiteEventStore


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    store = SQLiteEventStore(args.db)
    engine = OrchestrationEngine(compile_system(args.root), store, MockRoleExecutor())
    try:
        run_id = engine.start({"id": "DEMO-1", "objective": "Demonstrate gated mock automation"})
        engine.decide_gate(run_id, "rejected", "demo-human", "Design requires one revision")
        engine.resume(run_id)
        engine.decide_gate(run_id, "approved", "demo-human", "Revised design approved")
        engine.resume(run_id)
        engine.decide_gate(run_id, "rejected", "demo-human", "Implementation requires rework")
        engine.resume(run_id)
        engine.decide_gate(run_id, "approved", "demo-human", "Reworked implementation approved")
        engine.resume(run_id)
        result = engine.inspect(run_id)
        print(json.dumps({
            "run": result["run"],
            "event_history": [
                {"event_id": event["event_id"], "type": event["event_type"], "node": event["node_id"], "payload": event["payload"]}
                for event in result["events"]
            ],
        }, indent=2, sort_keys=True))
        return 0 if result["run"]["state"] == "COMPLETED" else 1
    finally:
        store.close()


if __name__ == "__main__":
    raise SystemExit(main())

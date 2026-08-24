"""Optional harmless OpenAI smoke test; disabled unless explicitly enabled."""
from __future__ import annotations
import json, os, sys, tempfile
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from orchestration import MockRoleExecutor, OrchestrationEngine, ProviderRoleExecutor, RoleDispatchExecutor, SQLiteEventStore, compile_system
from orchestration.context import ContextCompiler
from orchestration.providers.openai import OpenAIProvider, OpenAIProviderConfig


ROLE_ID = "architect"
LOGICAL_TIER = "high_reasoning"
EXPECTED_ARTIFACTS = ("automation_design", "sources_of_record")
MAX_PROVIDER_ATTEMPTS = 2


def validate_smoke_result(compiled: Any, store: SQLiteEventStore, run_id: str) -> dict[str, Any]:
    attempts = store.connection.execute(
        "SELECT * FROM provider_attempts WHERE run_id=? AND node_id='design' ORDER BY attempt", (run_id,)
    ).fetchall()
    if not attempts or len(attempts) > MAX_PROVIDER_ATTEMPTS:
        raise RuntimeError(f"Architect smoke expected 1-{MAX_PROVIDER_ATTEMPTS} provider attempts; observed {len(attempts)}")
    routing = store.connection.execute(
        "SELECT * FROM routing_events WHERE run_id=? AND task_id='design' ORDER BY attempt", (run_id,)
    ).fetchall()
    if any(row["selected_tier"] != LOGICAL_TIER or row["transition"] == "escalate" for row in routing):
        raise RuntimeError("Architect smoke must remain at high_reasoning without escalation")

    validations: dict[str, dict[str, Any]] = {}
    for artifact_type in EXPECTED_ARTIFACTS:
        row = store.connection.execute(
            "SELECT * FROM artifacts WHERE run_id=? AND artifact_type=? AND producer_node='design' AND active=1 ORDER BY created_at DESC LIMIT 1",
            (run_id, artifact_type),
        ).fetchone()
        if row is None:
            raise RuntimeError(f"Architect smoke did not persist required artifact: {artifact_type}")
        content = json.loads(row["content_json"])
        errors = [error.message for error in Draft202012Validator(compiled.artifact_contracts[artifact_type]).iter_errors(content)]
        validations[artifact_type] = {"valid": not errors, "errors": errors, "content_hash": row["content_hash"]}
        if errors:
            raise RuntimeError(f"Architect artifact failed contract validation: {artifact_type}: {errors}")

    return {
        "role_id": ROLE_ID,
        "logical_tier": LOGICAL_TIER,
        "resolved_model": attempts[-1]["model"],
        "attempts": len(attempts),
        "repair_used": len(attempts) == 2,
        "escalated": False,
        "artifact_validation": validations,
    }


def main() -> int:
    if os.environ.get("AQP_RUN_OPENAI_SMOKE") != "1":
        print("Skipped: set AQP_RUN_OPENAI_SMOKE=1 to enable the real-provider smoke test.")
        return 0
    compiled = compile_system(ROOT)
    config = OpenAIProviderConfig.from_environment(compiled.registry["providers"]["openai"])
    resolved_model = config.resolve_model(LOGICAL_TIER)
    print(json.dumps({
        "preflight": {
            "role_id": ROLE_ID,
            "logical_tier": LOGICAL_TIER,
            "resolved_model": resolved_model,
            "expected_artifacts": list(EXPECTED_ARTIFACTS),
            "provider_tools": [],
            "outward_actions": [],
            "max_provider_attempts": MAX_PROVIDER_ATTEMPTS,
            "escalation_allowed": False,
        }
    }, indent=2, sort_keys=True))
    selected = ProviderRoleExecutor(ContextCompiler(ROOT, compiled), OpenAIProvider(config))
    executor = RoleDispatchExecutor(selected, MockRoleExecutor(), {ROLE_ID})
    with tempfile.TemporaryDirectory() as directory:
        store = SQLiteEventStore(Path(directory) / "smoke.db")
        try:
            engine = OrchestrationEngine(compiled, store, executor)
            run_id = engine.start({"task": "Produce a read-only test-design outline for a synthetic calculator requirement. Do not call tools or perform actions."})
            result = engine.inspect(run_id)
            validation = validate_smoke_result(compiled, store, run_id)
            print(json.dumps({"validation": validation, **{key: result[key] for key in ("run", "artifacts", "provider_attempts", "routing", "events")}}, indent=2, sort_keys=True))
        finally:
            store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Optional harmless OpenAI smoke test; disabled unless explicitly enabled."""
from __future__ import annotations
import json, os, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from orchestration import MockRoleExecutor, OrchestrationEngine, ProviderRoleExecutor, RoleDispatchExecutor, SQLiteEventStore, compile_system
from orchestration.context import ContextCompiler
from orchestration.providers.openai import OpenAIProvider, OpenAIProviderConfig


def main() -> int:
    if os.environ.get("AQP_RUN_OPENAI_SMOKE") != "1":
        print("Skipped: set AQP_RUN_OPENAI_SMOKE=1 to enable the real-provider smoke test.")
        return 0
    compiled = compile_system(ROOT)
    config = OpenAIProviderConfig.from_environment(compiled.registry["providers"]["openai"])
    selected = ProviderRoleExecutor(ContextCompiler(ROOT, compiled), OpenAIProvider(config))
    executor = RoleDispatchExecutor(selected, MockRoleExecutor(), {"architect"})
    with tempfile.TemporaryDirectory() as directory:
        store = SQLiteEventStore(Path(directory) / "smoke.db")
        try:
            engine = OrchestrationEngine(compiled, store, executor)
            run_id = engine.start({"task": "Produce a read-only test-design outline for a synthetic calculator requirement. Do not call tools or perform actions."})
            result = engine.inspect(run_id)
            print(json.dumps({key: result[key] for key in ("run", "artifacts", "provider_attempts")}, indent=2, sort_keys=True))
        finally:
            store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

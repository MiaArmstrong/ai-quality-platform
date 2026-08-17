from __future__ import annotations

import json
import tempfile
import unittest
import uuid
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from orchestration.compiler import compile_system
from orchestration.authorization import AuthorizationService
from orchestration.context import ContextCompiler
from orchestration.provider_executor import ProviderRoleExecutor, RoleDispatchExecutor
from orchestration.providers.base import ExecutionRequest
from orchestration.providers.openai import OpenAIProvider, OpenAIProviderConfig, ProviderConfigurationError
from orchestration.runtime import MockRoleExecutor, OrchestrationEngine, SQLiteEventStore


ROOT = Path(__file__).resolve().parents[1]


class FakeResponses:
    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        raw = self.outputs.pop(0)
        return SimpleNamespace(
            id=f"resp-{len(self.calls)}", model=kwargs["model"], output_text=raw,
            usage=SimpleNamespace(input_tokens=11, output_tokens=7, input_tokens_details=SimpleNamespace(cached_tokens=3)),
        )


def artifact_payload(escalate=False):
    artifacts = {
        "automation_design": {"summary": "Read-only design", "confidence": 0.2 if escalate else 0.9, "escalation_requested": escalate, "evidence": ["work_item"]},
        "sources_of_record": {"sources": ["work_item"]},
    }
    return {
        "outcome": "escalate" if escalate else "success",
        "reason_code": "confidence_low" if escalate else "complete",
        "artifacts": artifacts,
    }


class ProviderConfigTests(unittest.TestCase):
    def setUp(self):
        self.contract = compile_system(ROOT).registry["providers"]["openai"]

    def test_missing_api_key_is_explicit(self):
        with self.assertRaisesRegex(ProviderConfigurationError, "OPENAI_API_KEY"):
            OpenAIProviderConfig.from_environment(self.contract, {})

    def test_tier_model_resolution_uses_environment(self):
        env = {"OPENAI_API_KEY": "synthetic", "AQP_OPENAI_MODEL_ECONOMY": "e", "AQP_OPENAI_MODEL_STANDARD": "s", "AQP_OPENAI_MODEL_HIGH_REASONING": "h"}
        config = OpenAIProviderConfig.from_environment(self.contract, env)
        self.assertEqual(("e", "s", "h"), tuple(config.resolve_model(tier) for tier in ("economy", "standard", "high_reasoning")))


class ContextCompilerTests(unittest.TestCase):
    def test_compiles_only_role_dependencies_and_hashes_sources(self):
        compiled = compile_system(ROOT)
        request = ContextCompiler(ROOT, compiled).compile(role_id="architect", task="design", workflow_context={"workflow_id": "automate"}, inputs={"work_item": {"id": "X"}}, tier="high_reasoning", produces=["automation_design", "sources_of_record"], authorization_context={}, attempt=1)
        self.assertEqual({".agents/roles/architect.md"}, set(request.source_hashes))
        self.assertNotIn("implementer", request.role_instructions.lower())
        self.assertEqual(64, len(next(iter(request.source_hashes.values()))))


class OpenAIProviderTests(unittest.TestCase):
    def request(self):
        compiled = compile_system(ROOT)
        return ContextCompiler(ROOT, compiled).compile(role_id="architect", task="design", workflow_context={}, inputs={"work_item": {}}, tier="high_reasoning", produces=["automation_design", "sources_of_record"], authorization_context={}, attempt=1)

    def provider(self, outputs):
        responses = FakeResponses(outputs)
        return OpenAIProvider(OpenAIProviderConfig("synthetic", {"high_reasoning": "configured-model"}), SimpleNamespace(responses=responses)), responses

    def test_structured_output_and_telemetry(self):
        provider, responses = self.provider([json.dumps(artifact_payload())])
        result = provider.execute(self.request())
        self.assertEqual("success", result.outcome)
        self.assertEqual((11, 7, 3), (result.telemetry.input_tokens, result.telemetry.output_tokens, result.telemetry.cached_tokens))
        self.assertIsNone(result.telemetry.estimated_cost)
        self.assertEqual("json_schema", responses.calls[0]["text"]["format"]["type"])

    def test_malformed_and_schema_invalid_output_are_not_coerced(self):
        malformed, _ = self.provider(["not-json"])
        invalid, _ = self.provider([json.dumps({"outcome": "success", "reason_code": "x", "artifacts": {}})])
        self.assertEqual("malformed_json", malformed.execute(self.request()).reason_code)
        result = invalid.execute(self.request())
        self.assertEqual("schema_validation_failed", result.reason_code)
        self.assertTrue(result.validation_errors)


class ProviderRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = SQLiteEventStore(Path(self.temp.name) / "runtime.db")
        self.compiled = compile_system(ROOT)

    def tearDown(self):
        self.store.close(); self.temp.cleanup()

    def engine(self, outputs):
        provider = OpenAIProvider(OpenAIProviderConfig("synthetic", {"high_reasoning": "high", "standard": "standard"}), SimpleNamespace(responses=FakeResponses([json.dumps(item) if isinstance(item, dict) else item for item in outputs])))
        selected = ProviderRoleExecutor(ContextCompiler(ROOT, self.compiled), provider)
        return OrchestrationEngine(self.compiled, self.store, RoleDispatchExecutor(selected, MockRoleExecutor(), {"architect"}))

    def test_provider_cannot_cross_authorization_boundary(self):
        responses = FakeResponses([json.dumps(artifact_payload())])
        provider = OpenAIProvider(OpenAIProviderConfig("synthetic", {"high_reasoning": "high"}), SimpleNamespace(responses=responses))
        executor = ProviderRoleExecutor(ContextCompiler(ROOT, self.compiled), provider, AuthorizationService(self.compiled.registry, self.compiled.capabilities))
        with self.assertRaisesRegex(PermissionError, "authorization DENY"):
            executor.execute(role_id="architect", task_id="design", tier="high_reasoning", inputs={"work_item": {}}, produces=["automation_design", "sources_of_record"], attempt=1, actions=[{"capability": "repo.write", "resource": "orchestration/runtime.py"}], task_context={}, gate_approvals=[])
        self.assertEqual([], responses.calls)

    def test_provider_artifacts_events_and_mock_regression(self):
        engine = self.engine([artifact_payload()])
        run_id = engine.start({"id": "REAL-1"})
        self.assertEqual("AWAITING_HUMAN", self.store.run(run_id)["state"])
        provider_rows = self.store.connection.execute("SELECT model,input_tokens FROM provider_attempts WHERE run_id=?", (run_id,)).fetchall()
        self.assertEqual([("high", 11)], [tuple(row) for row in provider_rows])
        self.assertIn(("design_critique", 1), engine.executor.fallback.calls)

    def test_invalid_output_repairs_once_and_preserves_both_attempts(self):
        engine = self.engine(["bad-json", artifact_payload()])
        run_id = engine.start({"id": "REPAIR-1"})
        rows = self.store.connection.execute("SELECT raw_output,validation_errors_json FROM provider_attempts WHERE run_id=? ORDER BY id", (run_id,)).fetchall()
        self.assertEqual(2, len(rows)); self.assertEqual("bad-json", rows[0]["raw_output"])

    def test_low_confidence_escalation_creates_new_attempt(self):
        provider = OpenAIProvider(OpenAIProviderConfig("synthetic", {"high_reasoning": "high", "standard": "standard"}), SimpleNamespace(responses=FakeResponses([json.dumps(artifact_payload(escalate=True)), json.dumps(artifact_payload())])))
        selected = ProviderRoleExecutor(ContextCompiler(ROOT, self.compiled), provider)
        engine = OrchestrationEngine(self.compiled, self.store, RoleDispatchExecutor(selected, MockRoleExecutor(), {"requirements_analyst"}))
        run_id = str(uuid.uuid4()); now = datetime.now(timezone.utc).isoformat()
        self.store.connection.execute("INSERT INTO runs VALUES(?,?,?,?,?,?,?)", (run_id, "automate", self.compiled.snapshot_hash, "design", "CREATED", now, now))
        engine._artifact(run_id, "work_item", "input", {"id": "ESC-1"})
        engine._set_state(run_id, "CONTEXT_READY")
        engine._set_state(run_id, "ROUTED")
        engine._execute_task(run_id, {"id": "design", "type": "task", "role_id": "requirements_analyst", "requires": ["work_item"], "produces": ["automation_design", "sources_of_record"], "actions": []})
        attempts = self.store.connection.execute("SELECT attempt,tier,status FROM task_attempts WHERE run_id=? ORDER BY attempt", (run_id,)).fetchall()
        self.assertEqual([(1, "standard", "ESCALATED"), (2, "high_reasoning", "COMPLETED")], [tuple(row) for row in attempts])
        artifact_count = self.store.connection.execute("SELECT COUNT(*) FROM artifacts WHERE run_id=? AND artifact_type='automation_design'", (run_id,)).fetchone()[0]
        self.assertEqual(2, artifact_count)


if __name__ == "__main__":
    unittest.main()

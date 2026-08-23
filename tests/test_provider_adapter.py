from __future__ import annotations

import json
import tempfile
import unittest
import uuid
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from jsonschema import Draft202012Validator

from orchestration.compiler import compile_system
from orchestration.authorization import AuthorizationService
from orchestration.context import ContextCompiler
from orchestration.provider_executor import ProviderRoleExecutor, RoleDispatchExecutor
from orchestration.providers.base import ExecutionRequest
from orchestration.providers.openai import OpenAIProvider, OpenAIProviderConfig, OpenAIProviderRequestError, ProviderConfigurationError
from orchestration.providers.openai_schema import OpenAISchemaCompatibilityError, make_openai_structured_output_schema, validate_openai_structured_output_schema
from orchestration.runtime import MockRoleExecutor, OrchestrationEngine, SQLiteEventStore
from orchestration.semantic_validation import SemanticOutputValidator
from tools.smoke_openai_provider import EXPECTED_ARTIFACTS, MAX_PROVIDER_ATTEMPTS, validate_smoke_result


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


class BadRequestError(Exception):
    def __init__(self, api_key):
        self.status_code = 400
        self.body = {"error": {"type": "invalid_request_error", "code": "invalid_json_schema", "param": "text.format.schema", "message": f"Invalid schema; bearer {api_key}"}}
        self.request_id = "req_safe_123"


class DirectBadRequestError(Exception):
    def __init__(self):
        self.status_code = 400
        self.body = {"type": "invalid_request_error", "code": "invalid_model", "param": "model", "message": "Model is unavailable"}
        self.request_id = "req_safe_456"


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


def inconsistent_architect_payload():
    payload = artifact_payload()
    payload["artifacts"]["automation_design"]["escalation_requested"] = True
    payload["artifacts"]["automation_design"]["confidence"] = 0.82
    return payload


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

    def test_openai_compatibility_validator_reproduces_legacy_envelope_failure(self):
        compiled = compile_system(ROOT)
        request = ContextCompiler(ROOT, compiled).compile(role_id="architect", task="design", workflow_context={}, inputs={"work_item": {}}, tier="high_reasoning", produces=["automation_design", "sources_of_record"], authorization_context={}, attempt=1)
        legacy = json.loads(json.dumps(request.output_contract))
        legacy["properties"]["outcome"].pop("type")
        with self.assertRaises(OpenAISchemaCompatibilityError) as raised:
            validate_openai_structured_output_schema(legacy)
        joined = " ".join(raised.exception.errors)
        self.assertIn("must declare type", joined)
        self.assertIn("minLength", joined)

    def test_provider_projection_preserves_canonical_schema_and_is_compatible(self):
        request = ContextCompiler(ROOT, compile_system(ROOT)).compile(role_id="architect", task="design", workflow_context={}, inputs={"work_item": {}}, tier="high_reasoning", produces=["automation_design", "sources_of_record"], authorization_context={}, attempt=1)
        projected = make_openai_structured_output_schema(request.output_contract)
        validate_openai_structured_output_schema(projected)
        self.assertIn("minLength", request.output_contract["properties"]["reason_code"])
        self.assertNotIn("minLength", projected["properties"]["reason_code"])
        self.assertEqual("string", projected["properties"]["outcome"]["type"])

    def test_unsafe_composition_is_not_silently_removed(self):
        with self.assertRaisesRegex(OpenAISchemaCompatibilityError, "allOf"):
            make_openai_structured_output_schema({"type": "object", "properties": {}, "required": [], "additionalProperties": False, "allOf": []})


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
        self.assertTrue(responses.calls[0]["text"]["format"]["strict"])
        self.assertNotIn("tools", responses.calls[0])
        self.assertNotIn("synthetic", json.dumps(responses.calls[0]))
        sent_schema = responses.calls[0]["text"]["format"]["schema"]
        validate_openai_structured_output_schema(sent_schema)
        self.assertEqual({"type", "name", "strict", "schema"}, set(responses.calls[0]["text"]["format"]))

    def test_malformed_and_schema_invalid_output_are_not_coerced(self):
        malformed, _ = self.provider(["not-json"])
        invalid, _ = self.provider([json.dumps({"outcome": "success", "reason_code": "x", "artifacts": {}})])
        self.assertEqual("malformed_json", malformed.execute(self.request()).reason_code)
        result = invalid.execute(self.request())
        self.assertEqual("schema_validation_failed", result.reason_code)
        self.assertTrue(result.validation_errors)

    def test_provider_projection_does_not_weaken_canonical_result_validation(self):
        payload = artifact_payload()
        payload["artifacts"]["automation_design"]["summary"] = ""
        provider, _ = self.provider([json.dumps(payload)])
        result = provider.execute(self.request())
        self.assertEqual("schema_validation_failed", result.reason_code)
        self.assertTrue(any("should be non-empty" in error for error in result.validation_errors))

    def test_bad_request_exposes_only_safe_diagnostics(self):
        api_key = "sk-secret-value-12345678"
        provider = OpenAIProvider(OpenAIProviderConfig(api_key, {"high_reasoning": "configured-model"}), SimpleNamespace(responses=SimpleNamespace(create=lambda **kwargs: (_ for _ in ()).throw(BadRequestError(api_key)))))
        with self.assertRaises(OpenAIProviderRequestError) as raised:
            provider.execute(self.request())
        error = raised.exception
        self.assertEqual((400, "invalid_request_error", "invalid_json_schema", "text.format.schema"), (error.status, error.error_type, error.code, error.param))
        self.assertEqual("req_safe_123", error.request_id)
        self.assertNotIn(api_key, str(error))
        self.assertIn("[REDACTED]", str(error))

    def test_bad_request_accepts_sdk_direct_error_body(self):
        provider = OpenAIProvider(OpenAIProviderConfig("synthetic", {"high_reasoning": "configured-model"}), SimpleNamespace(responses=SimpleNamespace(create=lambda **kwargs: (_ for _ in ()).throw(DirectBadRequestError()))))
        with self.assertRaises(OpenAIProviderRequestError) as raised:
            provider.execute(self.request())
        error = raised.exception
        self.assertEqual(("invalid_request_error", "invalid_model", "model", "req_safe_456"), (error.error_type, error.code, error.param, error.request_id))
        self.assertIn("Model is unavailable", error.safe_message)

    def test_provider_rejects_incompatible_schema_before_api_call(self):
        provider, responses = self.provider([json.dumps(artifact_payload())])
        request = self.request()
        incompatible = dict(request.output_contract)
        incompatible["allOf"] = []
        with self.assertRaisesRegex(OpenAISchemaCompatibilityError, "allOf"):
            provider.execute(replace(request, output_contract=incompatible))
        self.assertEqual([], responses.calls)


class SemanticOutputValidationTests(unittest.TestCase):
    def test_exact_smoke_inconsistency_is_schema_valid_but_semantically_invalid(self):
        payload = inconsistent_architect_payload()
        request = ContextCompiler(ROOT, compile_system(ROOT)).compile(role_id="architect", task="design", workflow_context={}, inputs={"work_item": {}}, tier="high_reasoning", produces=["automation_design", "sources_of_record"], authorization_context={}, attempt=1)
        self.assertEqual([], list(Draft202012Validator(request.output_contract).iter_errors(payload)))

        result = SemanticOutputValidator().validate(
            role_id="architect", outcome=payload["outcome"], artifacts=payload["artifacts"], escalation_available=False,
        )
        self.assertEqual("INVALID", result.status)
        self.assertTrue(result.repairable)
        self.assertEqual(
            {"architect_escalation_success_conflict/v1", "architect_escalation_unavailable_tier/v1"},
            set(result.rule_ids),
        )
        self.assertTrue(all(item.artifact_type == "automation_design" for item in result.findings))
        self.assertTrue(all(item.field_paths and item.severity == "ERROR" for item in result.findings))
        schema = json.loads((ROOT / ".agents/schemas/semantic-validation-result.v1.schema.json").read_text(encoding="utf-8"))
        self.assertEqual([], list(Draft202012Validator(schema).iter_errors(result.as_dict())))

    def test_valid_architect_result_has_structured_valid_status(self):
        payload = artifact_payload()
        result = SemanticOutputValidator().validate(
            role_id="architect", outcome=payload["outcome"], artifacts=payload["artifacts"], escalation_available=False,
        )
        self.assertEqual({"status": "VALID", "rule_ids": [], "repairable": False, "findings": []}, result.as_dict())


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

    def test_smoke_requires_and_validates_both_architect_artifacts(self):
        engine = self.engine([artifact_payload()])
        run_id = engine.start({"id": "SMOKE-CONTRACT-1"})
        result = validate_smoke_result(self.compiled, self.store, run_id)
        self.assertEqual(set(EXPECTED_ARTIFACTS), set(result["artifact_validation"]))
        self.assertTrue(all(item["valid"] for item in result["artifact_validation"].values()))
        self.assertEqual(1, result["attempts"])
        self.assertLessEqual(result["attempts"], MAX_PROVIDER_ATTEMPTS)
        self.assertFalse(result["repair_used"])
        self.assertFalse(result["escalated"])

    def test_smoke_rejects_a_missing_architect_artifact(self):
        engine = self.engine([artifact_payload()])
        run_id = engine.start({"id": "SMOKE-CONTRACT-2"})
        self.store.connection.execute("UPDATE artifacts SET active=0 WHERE run_id=? AND artifact_type='sources_of_record'", (run_id,))
        with self.assertRaisesRegex(RuntimeError, "sources_of_record"):
            validate_smoke_result(self.compiled, self.store, run_id)

    def test_invalid_output_repairs_once_and_preserves_both_attempts(self):
        engine = self.engine(["bad-json", artifact_payload()])
        run_id = engine.start({"id": "REPAIR-1"})
        rows = self.store.connection.execute("SELECT raw_output,validation_errors_json FROM provider_attempts WHERE run_id=? ORDER BY id", (run_id,)).fetchall()
        self.assertEqual(2, len(rows)); self.assertEqual("bad-json", rows[0]["raw_output"])

    def test_semantic_inconsistency_repairs_once_before_artifact_acceptance(self):
        engine = self.engine([inconsistent_architect_payload(), artifact_payload()])
        run_id = engine.start({"id": "SEMANTIC-REPAIR-1"})
        rows = self.store.connection.execute(
            "SELECT semantic_validation_status,semantic_rule_ids_json,semantic_validation_json,repair_attempted,repair_succeeded,raw_output FROM provider_attempts WHERE run_id=? ORDER BY attempt", (run_id,)
        ).fetchall()
        self.assertEqual(2, len(rows))
        self.assertEqual(("INVALID", 1, 0), (rows[0]["semantic_validation_status"], rows[0]["repair_attempted"], rows[0]["repair_succeeded"]))
        self.assertEqual(("VALID", 0, 1), (rows[1]["semantic_validation_status"], rows[1]["repair_attempted"], rows[1]["repair_succeeded"]))
        self.assertIn("architect_escalation_success_conflict/v1", json.loads(rows[0]["semantic_rule_ids_json"]))
        self.assertEqual("INVALID", json.loads(rows[0]["semantic_validation_json"])["status"])
        self.assertIn('"escalation_requested": true', rows[0]["raw_output"])
        artifacts = self.store.connection.execute(
            "SELECT artifact_type,COUNT(*) FROM artifacts WHERE run_id=? AND producer_node='design' GROUP BY artifact_type", (run_id,)
        ).fetchall()
        self.assertEqual([("automation_design", 1), ("sources_of_record", 1)], [tuple(row) for row in artifacts])
        events = self.store.events(run_id)
        self.assertTrue(any(item["event_type"] == "provider_repair_requested" and item["payload"]["semantic_rule_ids"] for item in events))
        self.assertTrue(any(item["event_type"] == "provider_repair_completed" and item["payload"]["succeeded"] is True for item in events))

    def test_failed_semantic_repair_preserves_evidence_and_accepts_no_artifacts(self):
        engine = self.engine([inconsistent_architect_payload(), inconsistent_architect_payload()])
        run_id = engine.start({"id": "SEMANTIC-REPAIR-2"})
        self.assertEqual("FAILED", self.store.run(run_id)["state"])
        count = self.store.connection.execute(
            "SELECT COUNT(*) FROM artifacts WHERE run_id=? AND producer_node='design'", (run_id,)
        ).fetchone()[0]
        self.assertEqual(0, count)
        attempts = self.store.connection.execute(
            "SELECT semantic_validation_status,raw_output,repair_succeeded FROM provider_attempts WHERE run_id=? ORDER BY attempt", (run_id,)
        ).fetchall()
        self.assertEqual(2, len(attempts))
        self.assertTrue(all(row["semantic_validation_status"] == "INVALID" and row["raw_output"] for row in attempts))
        self.assertTrue(all(row["repair_succeeded"] == 0 for row in attempts))
        self.assertTrue(any(item["event_type"] == "provider_repair_completed" and item["payload"]["succeeded"] is False for item in self.store.events(run_id)))

    def test_highest_tier_escalation_request_is_repaired_not_silently_ignored(self):
        engine = self.engine([artifact_payload(escalate=True), artifact_payload()])
        run_id = engine.start({"id": "SEMANTIC-HIGHEST-TIER"})
        rows = self.store.connection.execute(
            "SELECT semantic_validation_status,semantic_rule_ids_json FROM provider_attempts WHERE run_id=? ORDER BY attempt", (run_id,)
        ).fetchall()
        self.assertEqual(2, len(rows))
        self.assertIn("architect_escalation_unavailable_tier/v1", json.loads(rows[0]["semantic_rule_ids_json"]))
        self.assertEqual("VALID", rows[1]["semantic_validation_status"])

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

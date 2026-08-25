from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from orchestration.compiler import compile_system
from orchestration.context import ContextCompiler
from orchestration.provider_executor import ProviderRoleExecutor, RoleDispatchExecutor
from orchestration.providers.base import ExecutionResult, ExecutionTelemetry
from orchestration.providers.openai import OpenAIProvider, OpenAIProviderConfig, ProviderConfigurationError
from orchestration.providers.base import ProviderInputBudgetError
from orchestration.runtime import MockRoleExecutor, OrchestrationEngine, SQLiteEventStore
from orchestration.semantic_validation import SemanticOutputValidator
from tools.demo_multi_role_provider import AMBIGUOUS_FIXTURE, EXPLICIT_DIVIDE_BY_ZERO_FIXTURE, MAX_SANITIZED_ITEMS, MAX_SANITIZED_REPORT_BYTES, BudgetedRoleDispatchExecutor, DemoProviderCallBudgetExceeded, DeterministicQAIntakeExecutor, MAX_PROVIDER_CALLS, conservative_cost_ceiling, preflight, require_demo_safety, sanitized_demo_report


ROOT = Path(__file__).resolve().parents[1]


def readiness(verdict="READY"):
    return {"verdict": verdict, "summary": "Synthetic requirement reviewed.", "readiness_checks": [], "definition_of_done": ["Arithmetic is deterministic."], "missing_information": [], "conflicts": [], "blocking_conditions": [], "candidate_tests": [], "risks_notes": []}


def verifier(verdict="SUPPORTED"):
    return {"verdict": verdict, "summary": "Evidence challenged.", "challenged_claims": [{"claim": "The plan covers arithmetic.", "assessment": "SUPPORTED", "evidence_refs": ["qa_intake"]}], "evidence": [{"source": "qa_intake", "observation": "A deterministic plan exists."}], "concerns": [], "unsupported_assumptions": [], "evidence_gaps": [], "recommended_next_action": "Request QA signoff."}


class QueueProvider:
    provider_id = "synthetic"

    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.config = SimpleNamespace(resolve_model=lambda tier: f"synthetic-{tier}")

    def execute(self, request):
        item = self.outputs.pop(0)
        return ExecutionResult(item["outcome"], item["reason_code"], item.get("artifacts", {}), ExecutionTelemetry("synthetic", f"synthetic-{request.model_tier}", 1, request.attempt, 10, 5, 2, None), json.dumps(item), f"response-{request.attempt}")


class InvalidIntakeExecutor(DeterministicQAIntakeExecutor):
    def execute(self, **kwargs):
        if kwargs["role_id"] == "intake_analyst":
            return {"outcome": "success", "reason_code": "bad_fixture", "artifacts": {"qa_intake": {"summary": "invalid"}}}
        return super().execute(**kwargs)


class MultiRoleWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = SQLiteEventStore(Path(self.temp.name) / "runtime.db")
        self.compiled = compile_system(ROOT)

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def engine(self, outputs, fallback=None):
        provider = ProviderRoleExecutor(ContextCompiler(ROOT, self.compiled), QueueProvider(outputs))
        dispatch = RoleDispatchExecutor(provider, fallback or DeterministicQAIntakeExecutor(), {"requirements_analyst", "adversarial_verifier"})
        return OrchestrationEngine(self.compiled, self.store, dispatch, workflow_id="qa-provider-demo")

    @staticmethod
    def success_outputs():
        return [
            {"outcome": "success", "reason_code": "ready", "artifacts": {"requirements_readiness": readiness(), "sources_of_record": {"sources": ["work_item"]}}},
            {"outcome": "success", "reason_code": "supported", "artifacts": {"verifier_result": verifier()}},
        ]

    def test_default_workflow_selection_preserves_automate_path(self):
        implicit = OrchestrationEngine(self.compiled, self.store, MockRoleExecutor())
        self.assertEqual(("automate", "design"), (implicit.workflow_id, implicit.workflow["initial_node"]))
        other_store = SQLiteEventStore(Path(self.temp.name) / "explicit.db")
        try:
            explicit = OrchestrationEngine(self.compiled, other_store, MockRoleExecutor(), workflow_id="automate")
            implicit_run = implicit.start({"id": "implicit"})
            explicit_run = explicit.start({"id": "explicit"})
            self.assertEqual(("design_gate", "AWAITING_HUMAN"), (self.store.run(implicit_run)["current_node"], self.store.run(implicit_run)["state"]))
            self.assertEqual(("design_gate", "AWAITING_HUMAN"), (other_store.run(explicit_run)["current_node"], other_store.run(explicit_run)["state"]))
        finally:
            other_store.close()

    def test_multi_role_workflow_stops_at_signoff_with_canonical_artifacts(self):
        engine = self.engine(self.success_outputs())
        run_id = engine.start({"id": "synthetic"})
        run = self.store.run(run_id)
        self.assertEqual(("qa_signoff", "AWAITING_HUMAN"), (run["current_node"], run["state"]))
        self.assertEqual({"requirements_readiness", "sources_of_record", "qa_intake", "verifier_result", "work_item"}, {row[0] for row in self.store.connection.execute("SELECT artifact_type FROM artifacts WHERE run_id=? AND active=1", (run_id,))})
        summary = engine.summarize(run_id)
        self.assertEqual({"requirements_analyst": 1, "adversarial_verifier": 1}, summary["calls_by_role"])
        self.assertIsNone(summary["estimated_cost"])

    def test_invalid_local_qa_intake_is_rejected_before_persistence(self):
        engine = self.engine(self.success_outputs(), InvalidIntakeExecutor())
        run_id = engine.start({"id": "synthetic"})
        self.assertEqual("FAILED", self.store.run(run_id)["state"])
        self.assertEqual(0, self.store.connection.execute("SELECT COUNT(*) FROM artifacts WHERE artifact_type='qa_intake'").fetchone()[0])

    def test_ambiguous_divide_by_zero_input_surfaces_ambiguity_risk(self):
        engine = self.engine(self.success_outputs())
        run_id = engine.start(dict(AMBIGUOUS_FIXTURE))
        content = json.loads(self.store.connection.execute("SELECT content_json FROM artifacts WHERE run_id=? AND artifact_type='qa_intake'", (run_id,)).fetchone()[0])
        self.assertIn("Divide-by-zero behavior may remain ambiguous.", content["risks"])

    def test_explicit_divide_by_zero_input_omits_stale_ambiguity_risk(self):
        engine = self.engine(self.success_outputs())
        run_id = engine.start(dict(EXPLICIT_DIVIDE_BY_ZERO_FIXTURE))
        content = json.loads(self.store.connection.execute("SELECT content_json FROM artifacts WHERE run_id=? AND artifact_type='qa_intake'", (run_id,)).fetchone()[0])
        self.assertNotIn("Divide-by-zero behavior may remain ambiguous.", content["risks"])

    def test_sanitized_demo_report_is_bounded_and_preserves_gate_results(self):
        outputs = self.success_outputs()
        outputs[0]["artifacts"]["requirements_readiness"]["summary"] = "Bearer sensitive-demo-token"
        outputs[0]["artifacts"]["requirements_readiness"]["risks_notes"] = ["x" * 1000] * (MAX_SANITIZED_ITEMS + 2)
        outputs[0]["artifacts"]["requirements_readiness"]["missing_information"] = [{"gap_id": "g" * 1000, "description": "d" * 1000, "blocks_readiness": False}] * (MAX_SANITIZED_ITEMS + 2)
        outputs[0]["artifacts"]["requirements_readiness"]["conflicts"] = [{"conflict_id": "c" * 1000, "description": "d" * 1000, "sources": [], "blocks_readiness": False}] * (MAX_SANITIZED_ITEMS + 2)
        outputs[0]["artifacts"]["requirements_readiness"]["candidate_tests"] = [{"test_id": "t" * 1000, "description": "d" * 1000, "expected_result": "e" * 1000}] * (MAX_SANITIZED_ITEMS + 2)
        outputs[1]["artifacts"]["verifier_result"]["challenged_claims"][0]["evidence_refs"] = ["e" * 1000] * (MAX_SANITIZED_ITEMS + 2)
        outputs[1]["artifacts"]["verifier_result"]["concerns"] = [{"description": "c" * 1000, "critical": False}] * (MAX_SANITIZED_ITEMS + 2)
        outputs[1]["artifacts"]["verifier_result"]["unsupported_assumptions"] = ["u" * 1000] * (MAX_SANITIZED_ITEMS + 2)
        outputs[1]["artifacts"]["verifier_result"]["evidence_gaps"] = ["g" * 1000] * (MAX_SANITIZED_ITEMS + 2)
        outputs[1]["artifacts"]["verifier_result"]["recommended_next_action"] = "Do not expose " + "sk-" + "sensitive-demo-token"
        engine = self.engine(outputs)
        run_id = engine.start(dict(EXPLICIT_DIVIDE_BY_ZERO_FIXTURE))
        self.store.connection.execute("UPDATE provider_attempts SET routing_reason=?, model=? WHERE run_id=?", ("r" * 1000, "m" * 1000, run_id))
        report = sanitized_demo_report(engine, run_id)
        self.assertEqual(("READY", "SUPPORTED"), (report["requirements_analyst"]["verdict"], report["adversarial_verifier"]["verdict"]))
        self.assertEqual(("AWAITING_HUMAN", "qa_signoff", "pending"), (report["workflow"]["state"], report["workflow"]["current_node"], report["gate"]["status"]))
        self.assertEqual({"requirements_readiness", "qa_intake", "verifier_result"}, set(report["gate"]["evidence"]))
        self.assertTrue(all(set(value) == {"artifact_id", "content_hash"} for value in report["gate"]["evidence"].values()))
        self.assertEqual(MAX_SANITIZED_ITEMS, len(report["requirements_analyst"]["risks_notes"]))
        self.assertEqual(MAX_SANITIZED_ITEMS, len(report["adversarial_verifier"]["challenged_claims"][0]["evidence_refs"]))
        self.assertEqual(report["report_bytes"], len(json.dumps(report, separators=(",", ":")).encode("utf-8")))
        self.assertLessEqual(report["report_bytes"], MAX_SANITIZED_REPORT_BYTES)
        self.assertNotIn("raw_output", json.dumps(report))
        self.assertNotIn("sensitive-demo-token", json.dumps(report))
        self.assertIn("[REDACTED]", json.dumps(report))
        self.assertFalse(report["detail_truncated"])

    def test_requirements_attempt_sequence_is_finite_and_auditable(self):
        invalid = {"outcome": "success", "reason_code": "bad", "artifacts": {"requirements_readiness": {"verdict": "READY"}, "sources_of_record": {"sources": []}}}
        escalate = {"outcome": "escalate", "reason_code": "confidence_low", "artifacts": {"requirements_readiness": readiness("NEEDS_INFO") | {"missing_information": [{"gap_id": "g", "description": "unknown", "blocks_readiness": False}]}, "sources_of_record": {"sources": ["work_item"]}}}
        outputs = [invalid, escalate, self.success_outputs()[0], self.success_outputs()[1]]
        engine = self.engine(outputs)
        run_id = engine.start({"id": "synthetic"})
        rows = self.store.connection.execute("SELECT attempt,tier,routing_transition,final_task_outcome,repair_attempted FROM provider_attempts WHERE run_id=? AND role_id='requirements_analyst' ORDER BY attempt", (run_id,)).fetchall()
        self.assertEqual(3, len(rows))
        self.assertEqual([(1, "standard", "none"), (2, "standard", "none"), (3, "high_reasoning", "escalate")], [(row["attempt"], row["tier"], row["routing_transition"]) for row in rows])
        self.assertEqual("schema_validation_failed", rows[0]["final_task_outcome"])
        self.assertEqual("escalate", rows[1]["final_task_outcome"])
        self.assertEqual(1, rows[0]["repair_attempted"])

    def test_verifier_repairs_once_and_cannot_escalate_at_highest_tier(self):
        invalid_review = verifier("REFUTED")
        engine = self.engine([self.success_outputs()[0], {"outcome": "success", "reason_code": "invalid_semantics", "artifacts": {"verifier_result": invalid_review}}, self.success_outputs()[1]])
        run_id = engine.start({"id": "synthetic"})
        rows = self.store.connection.execute("SELECT attempt,tier,routing_transition,final_task_outcome FROM provider_attempts WHERE run_id=? AND role_id='adversarial_verifier' ORDER BY attempt", (run_id,)).fetchall()
        self.assertEqual(2, len(rows))
        self.assertTrue(all(row["tier"] == "high_reasoning" and row["routing_transition"] == "none" for row in rows))
        self.assertEqual("semantic_validation_failed", rows[0]["final_task_outcome"])

    def test_preflight_is_offline_and_declares_five_call_ceiling(self):
        pricing = {"gpt-5.6-terra": {"input_per_million": 2, "cached_input_per_million": .2, "cache_write_per_million": 2.5, "output_per_million": 12}, "gpt-5.6-sol": {"input_per_million": 4, "cached_input_per_million": .4, "cache_write_per_million": 5, "output_per_million": 20}}
        env = {"AQP_OPENAI_MODEL_ECONOMY": "e", "AQP_OPENAI_MODEL_STANDARD": "gpt-5.6-terra", "AQP_OPENAI_MODEL_HIGH_REASONING": "gpt-5.6-sol", "AQP_OPENAI_MAX_INPUT_TOKENS": "32000", "AQP_OPENAI_MAX_OUTPUT_TOKENS": "4096", "AQP_OPENAI_PRICING_JSON": json.dumps(pricing)}
        result = preflight(env, estimator_available=True)
        self.assertEqual(MAX_PROVIDER_CALLS, result["maximum_provider_calls"])
        self.assertEqual([], result["provider_tools"])
        self.assertEqual([], result["outward_actions"])
        self.assertEqual((32000, 4096), (result["maximum_compiled_input_tokens_per_request"], result["maximum_output_tokens_per_request"]))
        self.assertTrue(result["safety_budgets_enforced"])
        self.assertTrue(result["call_budgets_enforced"])

    def test_demo_call_budget_blocks_third_sol_request_before_delegate(self):
        class Delegate:
            authorization = None

            def __init__(self):
                self.prepared = []

            def attempt_descriptor(self, role_id, tier):
                return {"provider": "synthetic", "model": tier}

            def prepare_request(self, **kwargs):
                self.prepared.append(kwargs["tier"])
                return {}

        delegate = Delegate()
        budgeted = BudgetedRoleDispatchExecutor(delegate)
        first = {"role_id": "requirements_analyst", "task_id": "requirements_analysis", "attempt": 1, "tier": "high_reasoning"}
        second = {"role_id": "adversarial_verifier", "task_id": "adversarial_verify", "attempt": 1, "tier": "high_reasoning"}
        budgeted.prepare_request(**first)
        budgeted.prepare_request(**second)
        with self.assertRaises(DemoProviderCallBudgetExceeded):
            budgeted.prepare_request(role_id="adversarial_verifier", task_id="adversarial_verify", attempt=2, tier="high_reasoning")
        self.assertEqual(["high_reasoning", "high_reasoning"], delegate.prepared)
        with self.assertRaises(DemoProviderCallBudgetExceeded):
            budgeted.execute(role_id="adversarial_verifier", task_id="adversarial_verify", attempt=2, tier="high_reasoning")

        terra_delegate = Delegate()
        terra_budgeted = BudgetedRoleDispatchExecutor(terra_delegate)
        for attempt in range(1, 4):
            terra_budgeted.prepare_request(role_id="requirements_analyst", task_id="requirements_analysis", attempt=attempt, tier="standard")
        with self.assertRaises(DemoProviderCallBudgetExceeded):
            terra_budgeted.prepare_request(role_id="requirements_analyst", task_id="requirements_analysis", attempt=4, tier="standard")

        total_delegate = Delegate()
        total_budgeted = BudgetedRoleDispatchExecutor(total_delegate)
        for attempt in range(1, 4):
            total_budgeted.prepare_request(role_id="requirements_analyst", task_id="requirements_analysis", attempt=attempt, tier="standard")
        for attempt in range(1, 3):
            total_budgeted.prepare_request(role_id="adversarial_verifier", task_id="adversarial_verify", attempt=attempt, tier="high_reasoning")
        with self.assertRaises(DemoProviderCallBudgetExceeded):
            total_budgeted.prepare_request(role_id="requirements_analyst", task_id="requirements_analysis", attempt=4, tier="standard")

    def test_demo_safety_refuses_missing_pricing_even_with_token_budgets(self):
        env = {"AQP_OPENAI_MODEL_ECONOMY": "e", "AQP_OPENAI_MODEL_STANDARD": "s", "AQP_OPENAI_MODEL_HIGH_REASONING": "h", "AQP_OPENAI_MAX_INPUT_TOKENS": "32000", "AQP_OPENAI_MAX_OUTPUT_TOKENS": "4096"}
        result = preflight(env, estimator_available=True)
        self.assertFalse(result["safety_budgets_enforced"])
        with self.assertRaisesRegex(ValueError, "safety requirements are not met"):
            require_demo_safety(result)

    def test_demo_refuses_execution_without_required_budgets(self):
        with self.assertRaisesRegex(ValueError, "AQP_OPENAI_MAX_INPUT_TOKENS=32000"):
            require_demo_safety({"safety_budgets_enforced": False, "safety_errors": ["AQP_OPENAI_MAX_INPUT_TOKENS=32000"]})


class AdditionalSemanticRulesTests(unittest.TestCase):
    def setUp(self):
        self.validator = SemanticOutputValidator()

    def test_requirements_cross_field_rules(self):
        value = readiness()
        value["blocking_conditions"] = [{"condition_id": "b", "description": "blocked", "dependency": "owner"}]
        result = self.validator.validate(role_id="requirements_analyst", outcome="success", artifacts={"requirements_readiness": value}, escalation_available=True)
        self.assertEqual("INVALID", result.status)
        self.assertIn("requirements_ready_with_blockers/v1", result.rule_ids)

        for verdict, expected in (("BLOCKED", "requirements_blocked_without_condition/v1"), ("NEEDS_INFO", "requirements_needs_info_without_gap/v1")):
            with self.subTest(verdict=verdict):
                result = self.validator.validate(role_id="requirements_analyst", outcome="success", artifacts={"requirements_readiness": readiness(verdict)}, escalation_available=True)
                self.assertIn(expected, result.rule_ids)

    def test_verifier_cross_field_rules(self):
        result = self.validator.validate(role_id="adversarial_verifier", outcome="success", artifacts={"verifier_result": verifier("REFUTED")}, escalation_available=False)
        self.assertEqual("INVALID", result.status)
        self.assertIn("verifier_refuted_without_claim/v1", result.rule_ids)

        cases = [
            (verifier("SUPPORTED") | {"concerns": [{"description": "critical contradiction", "critical": True}]}, "verifier_supported_with_critical_concern/v1"),
            (verifier("INSUFFICIENT_EVIDENCE"), "verifier_insufficient_without_gap/v1"),
            (verifier("SUPPORTED_WITH_CONCERNS"), "verifier_concerns_without_concern/v1"),
        ]
        for artifact, expected in cases:
            with self.subTest(rule=expected):
                result = self.validator.validate(role_id="adversarial_verifier", outcome="success", artifacts={"verifier_result": artifact}, escalation_available=False)
                self.assertIn(expected, result.rule_ids)


class PricingTests(unittest.TestCase):
    def test_pricing_is_optional_and_distinguishes_token_classes(self):
        usage = SimpleNamespace(input_tokens=100, output_tokens=20, input_tokens_details=SimpleNamespace(cached_tokens=40, cache_write_tokens=10))
        provider = OpenAIProvider(OpenAIProviderConfig("synthetic", {"standard": "m"}, {"m": {"input_per_million": 10, "cached_input_per_million": 2, "cache_write_per_million": 12.5, "output_per_million": 30}}), client=SimpleNamespace())
        self.assertAlmostEqual((50 * 10 + 40 * 2 + 10 * 12.5 + 20 * 30) / 1_000_000, provider._estimate_cost("m", usage))
        missing = OpenAIProvider(OpenAIProviderConfig("synthetic", {"standard": "m"}, {"m": {"input_per_million": 10}}), client=SimpleNamespace())
        self.assertIsNone(missing._estimate_cost("m", usage))

    def test_missing_observed_cache_write_usage_is_not_fabricated(self):
        usage = SimpleNamespace(input_tokens=100, output_tokens=20, input_tokens_details=SimpleNamespace(cached_tokens=0))
        pricing = {"m": {"input_per_million": 10, "cached_input_per_million": 2, "cache_write_per_million": 12.5, "output_per_million": 30}}
        provider = OpenAIProvider(OpenAIProviderConfig("synthetic", {"standard": "m"}, pricing), client=SimpleNamespace())
        self.assertIsNone(provider._estimate_cost("m", usage))

    def test_conservative_ceiling_uses_configured_cache_write_rate(self):
        pricing = {"terra": {"input_per_million": 2, "cached_input_per_million": .2, "cache_write_per_million": 2.5, "output_per_million": 12}, "sol": {"input_per_million": 4, "cached_input_per_million": .4, "cache_write_per_million": 5, "output_per_million": 20}}
        self.assertAlmostEqual(0.871296, conservative_cost_ceiling(pricing, terra_model="terra", sol_model="sol", max_input_tokens=32000, max_output_tokens=4096))

    def test_pricing_environment_rejects_invalid_json(self):
        contract = compile_system(ROOT).registry["providers"]["openai"]
        env = {"OPENAI_API_KEY": "synthetic", "AQP_OPENAI_MODEL_ECONOMY": "e", "AQP_OPENAI_MODEL_STANDARD": "s", "AQP_OPENAI_MODEL_HIGH_REASONING": "h", "AQP_OPENAI_PRICING_JSON": "not-json"}
        with self.assertRaises(ProviderConfigurationError):
            OpenAIProviderConfig.from_environment(contract, env)


if __name__ == "__main__":
    unittest.main()

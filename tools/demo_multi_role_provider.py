"""Opt-in, read-only multi-role provider demo. No provider call occurs by default."""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from orchestration.compiler import compile_system
from orchestration.context import ContextCompiler
from orchestration.provider_executor import ProviderRoleExecutor, RoleDispatchExecutor
from orchestration.providers.openai import OpenAIProvider, OpenAIProviderConfig
from orchestration.providers.openai_schema import make_openai_structured_output_schema
from orchestration.runtime import MockRoleExecutor, OrchestrationEngine, SQLiteEventStore


WORKFLOW_ID = "qa-provider-demo"
ENABLE_ENV = "AQP_RUN_OPENAI_MULTI_ROLE_DEMO"
PROVIDER_ROLES = {"requirements_analyst", "adversarial_verifier"}
MAX_PROVIDER_CALLS = 5
MAX_TERRA_CALLS = 3
MAX_SOL_CALLS = 2
REQUIRED_MAX_OUTPUT_TOKENS = 4096
REQUIRED_MAX_INPUT_TOKENS = 32000
MAX_SANITIZED_ITEMS = 3
MAX_SANITIZED_TEXT_CHARS = 200
MAX_SANITIZED_REPORT_BYTES = 16_000
REQUIRED_CONSERVATIVE_COST_CEILING = 0.871296
REQUIRED_TERRA_MODEL = "gpt-5.6-terra"
REQUIRED_SOL_MODEL = "gpt-5.6-sol"
AMBIGUOUS_FIXTURE = {
    "id": "SYNTHETIC-CALCULATOR",
    "objective": "Define QA readiness and testing for a calculator, including ambiguous divide-by-zero behavior.",
}
EXPLICIT_DIVIDE_BY_ZERO_FIXTURE = {
    "id": "SYNTHETIC-CALCULATOR-EXPLICIT-DIVIDE-BY-ZERO",
    "objective": "Define QA readiness and testing for a synthetic calculator, including divide-by-zero behavior. When the divisor is zero, the calculator must reject the operation and return the structured error `DIVIDE_BY_ZERO`; it must not return Infinity, NaN, or a numeric result. Assess the remaining requirement for testability, missing information, risks, and candidate tests without inventing unspecified product behavior.",
}
FIXTURES = {"ambiguous": AMBIGUOUS_FIXTURE, "explicit-divide-by-zero": EXPLICIT_DIVIDE_BY_ZERO_FIXTURE}


def conservative_cost_ceiling(pricing: dict[str, Any], *, terra_model: str, sol_model: str, max_input_tokens: int, max_output_tokens: int) -> float | None:
    required = {"input_per_million", "cached_input_per_million", "cache_write_per_million", "output_per_million"}
    total = 0.0
    for model, calls in ((terra_model, MAX_TERRA_CALLS), (sol_model, MAX_SOL_CALLS)):
        rates = pricing.get(model)
        if not isinstance(rates, dict) or not required.issubset(rates):
            return None
        # Conservative demo ceiling: no cached-read discount and every input
        # token charged at the configured cache-write rate.
        total += calls * (
            max_input_tokens * rates["cache_write_per_million"]
            + max_output_tokens * rates["output_per_million"]
        ) / 1_000_000
    return total


def require_demo_safety(check: dict[str, Any]) -> None:
    required = (
        check.get("safety_budgets_enforced") is True,
        check.get("call_budgets_enforced") is True,
        check.get("maximum_compiled_input_tokens_per_request") == REQUIRED_MAX_INPUT_TOKENS,
        check.get("maximum_output_tokens_per_request") == REQUIRED_MAX_OUTPUT_TOKENS,
        check.get("maximum_provider_calls") == MAX_PROVIDER_CALLS,
        check.get("maximum_terra_calls") == MAX_TERRA_CALLS,
        check.get("maximum_sol_calls") == MAX_SOL_CALLS,
        math.isclose(check.get("conservative_maximum_estimated_workflow_cost") or -1, REQUIRED_CONSERVATIVE_COST_CEILING, rel_tol=0, abs_tol=1e-12),
        check.get("pricing") == {"configured": True, "error": None},
        check.get("provider_tools") == [],
        check.get("outward_actions") == [],
        check.get("structured_output_compatible") is True,
        check.get("stops_at_gate") == "qa_signoff",
    )
    if not all(required):
        raise ValueError(f"real provider demo safety requirements are not met: {', '.join(check.get('safety_errors', [])) or provider_budget_message()}")


class DemoProviderCallBudgetExceeded(RuntimeError):
    """Raised locally before a demo attempt can exceed its approved call cap."""


class BudgetedRoleDispatchExecutor:
    """Demo-only wrapper enforcing workflow and tier call budgets before dispatch."""

    def __init__(self, delegate: RoleDispatchExecutor):
        self.delegate = delegate
        self.calls = 0
        self.calls_by_tier = {"standard": 0, "high_reasoning": 0}
        self.reserved: set[tuple[str, str, int]] = set()

    @property
    def authorization(self) -> Any:
        return self.delegate.authorization

    @authorization.setter
    def authorization(self, value: Any) -> None:
        self.delegate.authorization = value

    def prepare_request(self, **kwargs: Any) -> dict[str, Any] | None:
        if self.delegate.attempt_descriptor(kwargs["role_id"], kwargs["tier"]) is None:
            return self.delegate.prepare_request(**kwargs)
        limit = {"standard": MAX_TERRA_CALLS, "high_reasoning": MAX_SOL_CALLS}.get(kwargs["tier"], 0)
        if self.calls >= MAX_PROVIDER_CALLS or self.calls_by_tier.get(kwargs["tier"], 0) >= limit:
            raise DemoProviderCallBudgetExceeded("demo provider call budget exceeded before dispatch")
        key = (kwargs["role_id"], kwargs["task_id"], kwargs["attempt"])
        self.calls += 1
        self.calls_by_tier[kwargs["tier"]] = self.calls_by_tier.get(kwargs["tier"], 0) + 1
        self.reserved.add(key)
        try:
            return self.delegate.prepare_request(**kwargs)
        except Exception:
            self.reserved.discard(key)
            self.calls -= 1
            self.calls_by_tier[kwargs["tier"]] -= 1
            raise

    def execute(self, **kwargs: Any) -> dict[str, Any]:
        if self.delegate.attempt_descriptor(kwargs["role_id"], kwargs["tier"]) is not None:
            key = (kwargs["role_id"], kwargs["task_id"], kwargs["attempt"])
            if key not in self.reserved:
                raise DemoProviderCallBudgetExceeded("demo provider execution lacks a reserved call budget")
            self.reserved.remove(key)
        return self.delegate.execute(**kwargs)

    def attempt_descriptor(self, role_id: str, tier: str) -> dict[str, str] | None:
        return self.delegate.attempt_descriptor(role_id, tier)


class DeterministicQAIntakeExecutor(MockRoleExecutor):
    """Produces the demo's local artifact; runtime performs canonical validation."""

    def execute(self, **kwargs: Any) -> dict[str, Any]:
        if kwargs["role_id"] != "intake_analyst":
            return super().execute(**kwargs)
        self.calls.append((kwargs["task_id"], kwargs["attempt"]))
        work_item = kwargs["inputs"]["work_item"]
        readiness = kwargs["inputs"]["requirements_readiness"]
        ambiguity_risk = "Divide-by-zero behavior may remain ambiguous."
        explicit_zero_behavior = divide_by_zero_behavior_is_explicit(work_item)
        risks = [
            str(item) for item in readiness.get("risks_notes", ())
            if str(item).strip() and not (explicit_zero_behavior and str(item).casefold() == ambiguity_risk.casefold())
        ]
        if not explicit_zero_behavior and ambiguity_risk not in risks:
            risks.append(ambiguity_risk)
        return {
            "outcome": "success",
            "reason_code": "deterministic_intake_complete",
            "artifacts": {
                "qa_intake": {
                    "summary": "Synthetic calculator QA intake derived from validated requirements evidence.",
                    "classification": "READY_FOR_QA",
                    "test_plan": [{"test_id": "calculator-core", "description": "Exercise arithmetic operations and divide-by-zero behavior.", "expected_result": "Defined arithmetic results and explicit divide-by-zero handling."}],
                    "risks": risks,
                    "sources_used": ["work_item", "requirements_readiness", "sources_of_record"],
                }
            },
        }


def divide_by_zero_behavior_is_explicit(work_item: dict[str, Any]) -> bool:
    """Recognize the demo's explicit zero-divisor product decision from input."""
    text = " ".join(str(value) for value in work_item.values()).casefold()
    return all(marker in text for marker in ("divisor is zero", "divide_by_zero", "must reject"))


def _bounded_text(value: Any) -> str:
    text = re.sub(r"(?i)bearer\s+\S+", "Bearer [REDACTED]", str(value))
    text = re.sub(r"sk-[A-Za-z0-9_-]{8,}", "[REDACTED]", text)
    return text if len(text) <= MAX_SANITIZED_TEXT_CHARS else text[: MAX_SANITIZED_TEXT_CHARS - 3] + "..."


def _bounded_items(values: Any, fields: tuple[str, ...] | None = None) -> list[Any]:
    result = []
    for value in list(values or ())[:MAX_SANITIZED_ITEMS]:
        if fields is None:
            result.append(_bounded_text(value))
        elif isinstance(value, dict):
            item = {}
            for field in fields:
                field_value = value.get(field)
                if isinstance(field_value, str):
                    field_value = _bounded_text(field_value)
                elif isinstance(field_value, (list, tuple)):
                    field_value = _bounded_items(field_value)
                item[field] = field_value
            result.append(item)
    return result


def sanitized_demo_report(engine: OrchestrationEngine, run_id: str) -> dict[str, Any]:
    """Return bounded accepted artifacts and gate evidence without raw output."""
    store = engine.store
    artifacts = {
        row["artifact_type"]: json.loads(row["content_json"])
        for row in store.connection.execute(
            "SELECT artifact_type,content_json FROM artifacts WHERE run_id=? AND active=1",
            (run_id,),
        )
    }
    readiness = artifacts.get("requirements_readiness")
    intake = artifacts.get("qa_intake")
    verifier = artifacts.get("verifier_result")
    gate_row = store.connection.execute(
        "SELECT gate_id,gate_type,status,evidence_json FROM gates WHERE run_id=? ORDER BY requested_at DESC LIMIT 1",
        (run_id,),
    ).fetchone()
    run = dict(store.run(run_id))
    telemetry = engine.summarize(run_id)
    telemetry["calls_by_role"] = {_bounded_text(key): value for key, value in telemetry["calls_by_role"].items()}
    telemetry["attempts"] = [
        {
            key: (_bounded_text(value) if isinstance(value, str) else _bounded_items(value) if isinstance(value, (list, tuple)) else value)
            for key, value in attempt.items()
        }
        for attempt in telemetry["attempts"][:MAX_PROVIDER_CALLS]
    ]
    report = {
        "workflow": {"run_id": run["run_id"], "state": run["state"], "current_node": run["current_node"]},
        "requirements_analyst": None if readiness is None else {
            "verdict": readiness["verdict"],
            "summary": _bounded_text(readiness["summary"]),
            "missing_information": _bounded_items(readiness["missing_information"], ("gap_id", "description", "blocks_readiness")),
            "conflicts": _bounded_items(readiness["conflicts"], ("conflict_id", "description", "blocks_readiness")),
            "candidate_tests": _bounded_items(readiness["candidate_tests"], ("test_id", "description", "expected_result")),
            "risks_notes": _bounded_items(readiness["risks_notes"]),
        },
        "qa_intake": None if intake is None else {
            "classification": intake["classification"],
            "risks": _bounded_items(intake["risks"]),
            "test_plan": _bounded_items(intake["test_plan"], ("test_id", "description", "expected_result")),
        },
        "adversarial_verifier": None if verifier is None else {
            "verdict": verifier["verdict"],
            "summary": _bounded_text(verifier["summary"]),
            "challenged_claims": _bounded_items(verifier["challenged_claims"], ("claim", "assessment", "evidence_refs")),
            "concerns": _bounded_items(verifier["concerns"], ("description", "critical")),
            "unsupported_assumptions": _bounded_items(verifier["unsupported_assumptions"]),
            "evidence_gaps": _bounded_items(verifier["evidence_gaps"]),
            "recommended_next_action": _bounded_text(verifier["recommended_next_action"]),
        },
        "gate": None if gate_row is None else {
            "gate_id": gate_row["gate_id"],
            "gate_type": gate_row["gate_type"],
            "status": gate_row["status"],
            "evidence": json.loads(gate_row["evidence_json"]),
        },
        "telemetry": telemetry,
    }
    report["detail_truncated"] = False
    report["report_bytes"] = 0
    report["report_limit_bytes"] = MAX_SANITIZED_REPORT_BYTES
    size = len(json.dumps(report, separators=(",", ":")).encode("utf-8"))
    report["report_bytes"] = size
    size = len(json.dumps(report, separators=(",", ":")).encode("utf-8"))
    report["report_bytes"] = size
    if size > MAX_SANITIZED_REPORT_BYTES:
        report["detail_truncated"] = True
        for section in ("requirements_analyst", "qa_intake", "adversarial_verifier"):
            if report[section] is not None:
                report[section] = {key: value for key, value in report[section].items() if key in {"verdict", "classification", "recommended_next_action"}}
        report["telemetry"]["attempts"] = []
        report["report_bytes"] = len(json.dumps(report, separators=(",", ":")).encode("utf-8"))
        if report["report_bytes"] > MAX_SANITIZED_REPORT_BYTES:
            raise ValueError(f"minimal sanitized demo report exceeds {MAX_SANITIZED_REPORT_BYTES} bytes")
    return report


def preflight(environ: dict[str, str] | None = None, *, estimator_available: bool | None = None) -> dict[str, Any]:
    env = os.environ if environ is None else environ
    compiled = compile_system(ROOT)
    registry = compiled.registry
    provider = registry["providers"]["openai"]
    models = {tier: env.get(name) for tier, name in provider["model_env"].items()}
    def configured_integer(field: str) -> int | None:
        raw = env.get(provider[field], "")
        try:
            value = int(raw)
        except ValueError:
            return None
        return value if value > 0 else None
    max_output_tokens = configured_integer("max_output_tokens_env")
    max_input_tokens = configured_integer("max_input_tokens_env")
    if estimator_available is None:
        estimator_available = importlib.util.find_spec("tiktoken") is not None
    safety_errors = []
    if max_input_tokens != REQUIRED_MAX_INPUT_TOKENS:
        safety_errors.append(f"AQP_OPENAI_MAX_INPUT_TOKENS must equal {REQUIRED_MAX_INPUT_TOKENS}")
    if max_output_tokens != REQUIRED_MAX_OUTPUT_TOKENS:
        safety_errors.append(f"AQP_OPENAI_MAX_OUTPUT_TOKENS must equal {REQUIRED_MAX_OUTPUT_TOKENS}")
    if not estimator_available:
        safety_errors.append("optional tiktoken provider dependency is not installed")
    pricing = None
    pricing_error = None
    pricing_raw = env.get(provider["pricing_env"])
    if pricing_raw:
        try:
            pricing = json.loads(pricing_raw)
            if not isinstance(pricing, dict):
                raise ValueError("pricing must be an object")
        except (json.JSONDecodeError, ValueError) as exc:
            pricing_error = str(exc)
    compiler = ContextCompiler(ROOT, compiled)
    for role_id, tier, produces in (
        ("requirements_analyst", "standard", ["requirements_readiness", "sources_of_record"]),
        ("adversarial_verifier", "high_reasoning", ["verifier_result"]),
    ):
        request = compiler.compile(role_id=role_id, task="preflight", workflow_context={"workflow_id": WORKFLOW_ID}, inputs={}, tier=tier, produces=produces, authorization_context={"actions_permitted": False}, attempt=1)
        make_openai_structured_output_schema(request.output_contract)
    cost_ceiling = conservative_cost_ceiling(pricing or {}, terra_model=models["standard"] or "", sol_model=models["high_reasoning"] or "", max_input_tokens=max_input_tokens or 0, max_output_tokens=max_output_tokens or 0) if max_input_tokens and max_output_tokens else None
    if not models["standard"] or not models["high_reasoning"]:
        safety_errors.append("standard and high-reasoning models must resolve")
    if models["standard"] != REQUIRED_TERRA_MODEL or models["high_reasoning"] != REQUIRED_SOL_MODEL:
        safety_errors.append(f"demo models must resolve to {REQUIRED_TERRA_MODEL} and {REQUIRED_SOL_MODEL}")
    if pricing is None or pricing_error is not None:
        safety_errors.append("pricing must be configured without errors")
    if not math.isclose(cost_ceiling or -1, REQUIRED_CONSERVATIVE_COST_CEILING, rel_tol=0, abs_tol=1e-12):
        safety_errors.append(f"conservative cost ceiling must equal {REQUIRED_CONSERVATIVE_COST_CEILING}")
    return {
        "workflow_id": WORKFLOW_ID,
        "roles": [
            {"role_id": "requirements_analyst", "logical_tier": "standard", "resolved_model": models["standard"], "expected_artifacts": ["requirements_readiness", "sources_of_record"], "max_provider_calls": 3},
            {"role_id": "intake_analyst", "execution": "deterministic_local", "expected_artifacts": ["qa_intake"], "max_provider_calls": 0},
            {"role_id": "adversarial_verifier", "logical_tier": "high_reasoning", "resolved_model": models["high_reasoning"], "expected_artifacts": ["verifier_result"], "max_provider_calls": 2},
        ],
        "maximum_provider_calls": MAX_PROVIDER_CALLS,
        "maximum_terra_calls": MAX_TERRA_CALLS,
        "maximum_sol_calls": MAX_SOL_CALLS,
        "maximum_output_tokens_per_request": max_output_tokens,
        "maximum_compiled_input_tokens_per_request": max_input_tokens,
        "input_budget_counting": {"available": estimator_available, "method": "tiktoken with 256-token protocol allowance", "exact_server_count": False},
        "provider_tools": [],
        "outward_actions": [],
        "stops_at_gate": "qa_signoff",
        "pricing": {"configured": pricing is not None, "error": pricing_error},
        "conservative_maximum_estimated_workflow_cost": cost_ceiling,
        "conservative_cost_assumption": "all input charged at configured cache-write rate; no cached-read discount",
        "safety_budgets_enforced": not safety_errors,
        "call_budgets_enforced": True,
        "safety_errors": safety_errors,
        "structured_output_compatible": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--fixture", choices=sorted(FIXTURES), default="ambiguous")
    args = parser.parse_args()
    print(json.dumps({"preflight": preflight()}, indent=2, sort_keys=True))
    if args.preflight_only:
        return 0
    if os.getenv(ENABLE_ENV) != "1":
        raise SystemExit(f"real provider demo disabled; set {ENABLE_ENV}=1 explicitly")
    check = preflight()
    try:
        require_demo_safety(check)
    except ValueError as exc:
        raise SystemExit(str(exc)) from None
    compiled = compile_system(ROOT)
    config = OpenAIProviderConfig.from_environment(compiled.registry["providers"]["openai"])
    provider_executor = ProviderRoleExecutor(ContextCompiler(ROOT, compiled), OpenAIProvider(config))
    fallback = DeterministicQAIntakeExecutor()
    dispatch = BudgetedRoleDispatchExecutor(RoleDispatchExecutor(provider_executor, fallback, PROVIDER_ROLES))
    with tempfile.TemporaryDirectory() as directory:
        store = SQLiteEventStore(Path(directory) / "multi-role-demo.db")
        try:
            engine = OrchestrationEngine(compiled, store, dispatch, workflow_id=WORKFLOW_ID)
            run_id = engine.start(dict(FIXTURES[args.fixture]))
            print(json.dumps({"result": sanitized_demo_report(engine, run_id)}, indent=2, sort_keys=True))
        finally:
            store.close()
    return 0


def provider_budget_message() -> str:
    return f"AQP_OPENAI_MAX_INPUT_TOKENS={REQUIRED_MAX_INPUT_TOKENS} and AQP_OPENAI_MAX_OUTPUT_TOKENS={REQUIRED_MAX_OUTPUT_TOKENS}"


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

from typing import Any

from jsonschema import Draft202012Validator

from .authorization import AuthorizationService, GateApproval
from .compiler import CompiledSystem
from .context import ContextCompiler
from .providers.base import ModelProvider
from .semantic_validation import SemanticOutputValidator


class ProviderRoleExecutor:
    """Adapts a model provider to the runtime without granting action authority."""

    def __init__(self, compiler: ContextCompiler, provider: ModelProvider, authorization: AuthorizationService | None = None, semantic_validator: SemanticOutputValidator | None = None):
        self.compiler = compiler
        self.provider = provider
        self.authorization = authorization
        self.semantic_validator = semantic_validator or SemanticOutputValidator()

    def execute(self, *, role_id: str, task_id: str, tier: str, inputs: dict[str, Any], produces: list[str], attempt: int, actions: list[dict[str, Any]], task_context: dict[str, Any], gate_approvals: list[GateApproval]) -> dict[str, Any]:
        if self.authorization is None:
            raise RuntimeError("provider executor requires an authorization service")
        decisions = []
        for action in actions:
            context = dict(task_context)
            for key in ("command_category", "external_system_category"):
                if key in action:
                    context[key] = action[key]
            decision = self.authorization.decide(role_id=role_id, capability=action["capability"], resource=action["resource"], task_context=context, gate_approvals=gate_approvals)
            decisions.append(decision.as_dict())
            if decision.decision != "ALLOW":
                raise PermissionError(f"authorization {decision.decision}: {decision.reason_code}")
        request = self.compiler.compile(
            role_id=role_id, task=task_id,
            workflow_context=task_context.get("workflow_context", {}), inputs=inputs,
            tier=tier, produces=produces,
            authorization_context={"decisions": decisions, "actions_permitted": False},
            attempt=attempt, repair_context=task_context.get("repair_context"),
        )
        result = self.provider.execute(request)
        envelope = {
            "outcome": result.outcome,
            "reason_code": result.reason_code,
            "artifacts": dict(result.artifacts),
        }
        canonical_errors = self._canonical_validation_errors(request.output_contract, envelope)
        if canonical_errors:
            return {
                "outcome": "failure",
                "reason_code": "schema_validation_failed",
                "artifacts": {},
                "raw_output": result.raw_output,
                "provider_response_id": result.provider_response_id,
                "validation_errors": list(canonical_errors),
                "semantic_validation": None,
                "source_hashes": dict(request.source_hashes),
                "telemetry": result.telemetry.__dict__,
            }
        semantic_validation = None
        if not canonical_errors:
            role = self.compiler.compiled.registry["agents"][role_id]
            semantic_validation = self.semantic_validator.validate(
                role_id=role_id,
                outcome=result.outcome,
                artifacts=result.artifacts,
                escalation_available=role.get("escalation_tier") is not None,
            )
            if semantic_validation.status == "INVALID":
                return {
                    "outcome": "failure",
                    "reason_code": "semantic_validation_failed",
                    "artifacts": {},
                    "raw_output": result.raw_output,
                    "provider_response_id": result.provider_response_id,
                    "validation_errors": [],
                    "semantic_validation": semantic_validation.as_dict(),
                    "source_hashes": dict(request.source_hashes),
                    "telemetry": result.telemetry.__dict__,
                }
        return {
            "outcome": result.outcome, "reason_code": result.reason_code,
            "artifacts": dict(result.artifacts), "raw_output": result.raw_output,
            "provider_response_id": result.provider_response_id,
            "validation_errors": list(canonical_errors),
            "semantic_validation": semantic_validation.as_dict() if semantic_validation else None,
            "source_hashes": dict(request.source_hashes),
            "telemetry": result.telemetry.__dict__,
        }

    def attempt_descriptor(self, role_id: str, tier: str) -> dict[str, str]:
        provider = getattr(self.provider, "provider_id", self.provider.__class__.__name__.lower())
        config = getattr(self.provider, "config", None)
        model = config.resolve_model(tier) if config is not None and hasattr(config, "resolve_model") else tier
        return {"provider": provider, "model": model}

    @staticmethod
    def _canonical_validation_errors(contract: Any, envelope: dict[str, Any]) -> tuple[str, ...]:
        envelope_schema = {
            "type": "object",
            "required": ["outcome", "reason_code", "artifacts"],
            "properties": {
                "outcome": contract["properties"]["outcome"],
                "reason_code": contract["properties"]["reason_code"],
                "artifacts": {"type": "object"},
            },
            "additionalProperties": False,
        }
        envelope_errors = tuple(f"envelope: {error.message}" for error in Draft202012Validator(envelope_schema).iter_errors(envelope))
        if envelope_errors:
            return envelope_errors
        artifact_schema = contract["properties"]["artifacts"]
        artifacts = envelope["artifacts"]
        expected = set(artifact_schema["required"])
        actual = set(artifacts)
        errors = [f"artifacts: missing required artifact {name}" for name in sorted(expected - actual)]
        errors.extend(f"artifacts: undeclared artifact {name}" for name in sorted(actual - set(artifact_schema["properties"])))
        for artifact_type in sorted(actual & set(artifact_schema["properties"])):
            errors.extend(f"{artifact_type}: {error.message}" for error in Draft202012Validator(artifact_schema["properties"][artifact_type]).iter_errors(artifacts[artifact_type]))
        return tuple(errors)


class RoleDispatchExecutor:
    """Routes selected read-only roles to a provider and leaves all others mocked."""

    def __init__(self, provider_executor: ProviderRoleExecutor, fallback: Any, provider_roles: set[str]):
        self.provider_executor = provider_executor
        self.fallback = fallback
        self.provider_roles = set(provider_roles)

    @property
    def authorization(self) -> AuthorizationService | None:
        return self.provider_executor.authorization

    @authorization.setter
    def authorization(self, value: AuthorizationService) -> None:
        self.provider_executor.authorization = value
        if hasattr(self.fallback, "authorization"):
            self.fallback.authorization = value

    def execute(self, **kwargs: Any) -> dict[str, Any]:
        target = self.provider_executor if kwargs["role_id"] in self.provider_roles else self.fallback
        return target.execute(**kwargs)

    def attempt_descriptor(self, role_id: str, tier: str) -> dict[str, str] | None:
        if role_id not in self.provider_roles:
            return None
        return self.provider_executor.attempt_descriptor(role_id, tier)

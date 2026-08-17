from __future__ import annotations

from typing import Any

from .authorization import AuthorizationService, GateApproval
from .compiler import CompiledSystem
from .context import ContextCompiler
from .providers.base import ModelProvider


class ProviderRoleExecutor:
    """Adapts a model provider to the runtime without granting action authority."""

    def __init__(self, compiler: ContextCompiler, provider: ModelProvider, authorization: AuthorizationService | None = None):
        self.compiler = compiler
        self.provider = provider
        self.authorization = authorization

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
        return {
            "outcome": result.outcome, "reason_code": result.reason_code,
            "artifacts": dict(result.artifacts), "raw_output": result.raw_output,
            "provider_response_id": result.provider_response_id,
            "validation_errors": list(result.validation_errors),
            "source_hashes": dict(request.source_hashes),
            "telemetry": result.telemetry.__dict__,
        }


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

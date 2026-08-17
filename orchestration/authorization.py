from __future__ import annotations

import hashlib
import json
import posixpath
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Iterable, Mapping


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _resource_hash(resource: str) -> str:
    return hashlib.sha256(resource.encode()).hexdigest()


@dataclass(frozen=True)
class GateApproval:
    gate_type: str
    capability: str
    resource_hash: str
    policy_version: str
    status: str = "approved"
    stale: bool = False

    @classmethod
    def for_resource(cls, gate_type: str, capability: str, resource: str, policy_version: str = "role-capability-policy/v1") -> "GateApproval":
        return cls(gate_type, capability, _resource_hash(resource), policy_version)


@dataclass(frozen=True)
class AuthorizationDecision:
    schema_version: str
    decision_id: str
    decision: str
    role_id: str
    capability: str
    resource: str
    reason_code: str
    applicable_gate: str | None
    policy_version: str
    timestamp: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class AuthorizationService:
    """Evaluates policy only; it never performs the requested action."""

    def __init__(self, registry: Mapping[str, Any], capabilities: Mapping[str, Any], audit_sink: Callable[[AuthorizationDecision], None] | None = None):
        self.registry = registry
        self.capabilities = capabilities
        self.audit_sink = audit_sink
        self.audit_log: list[AuthorizationDecision] = []
        self.policy_version = registry["authorization_policy_version"]

    def _emit(self, role_id: str, capability: str, resource: str, decision: str, reason: str, gate: str | None = None) -> AuthorizationDecision:
        result = AuthorizationDecision("authorization-event/v1", str(uuid.uuid4()), decision, role_id, capability, resource, reason, gate, self.policy_version, _now())
        self.audit_log.append(result)
        if self.audit_sink:
            self.audit_sink(result)
        return result

    @staticmethod
    def _safe_path(resource: str) -> str | None:
        normalized = resource.replace("\\", "/")
        if normalized.startswith("/") or ":" in normalized.split("/")[0] or ".." in normalized.split("/"):
            return None
        path = posixpath.normpath(normalized)
        return path[2:] if path.startswith("./") else path

    @staticmethod
    def _matches(path: str, prefix: str) -> bool:
        clean = prefix.replace("\\", "/").rstrip("/")
        return clean == "." or path == clean or path.startswith(clean + "/")

    def _scope_reason(self, capability: str, resource: str, scope: Mapping[str, Any], task_context: Mapping[str, Any]) -> str | None:
        if capability.startswith("repo."):
            path = self._safe_path(resource)
            if path is None:
                return "RESOURCE_PATH_INVALID"
            prefixes = scope.get("path_prefixes", [])
            if prefixes and not any(self._matches(path, prefix) for prefix in prefixes):
                return "PATH_PREFIX_NOT_ALLOWED"
            if capability == "repo.write":
                writable: list[str] = []
                for prefix in scope.get("writable_directories", []):
                    if prefix == "@task.authorized_paths":
                        writable.extend(task_context.get("authorized_paths", []))
                    else:
                        writable.append(prefix)
                if not writable or not any(self._matches(path, prefix) for prefix in writable):
                    return "WRITE_SCOPE_NOT_AUTHORIZED"
                if any(self._matches(path, prefix) for prefix in scope.get("read_only_directories", [])):
                    return "READ_ONLY_SCOPE"
        if capability in {"repo.execute", "tests.run"}:
            category = task_context.get("command_category")
            if category not in scope.get("command_categories", []):
                return "COMMAND_CATEGORY_NOT_ALLOWED"
        if capability.startswith(("wiki.", "external.")):
            category = task_context.get("external_system_category")
            categories = scope.get("external_system_categories", [])
            if categories and category not in categories:
                return "EXTERNAL_SYSTEM_NOT_ALLOWED"
        return None

    def decide(self, *, role_id: str, capability: str, resource: str, task_context: Mapping[str, Any] | None = None, gate_approvals: Iterable[GateApproval] = ()) -> AuthorizationDecision:
        context = task_context or {}
        if role_id not in self.registry["agents"]:
            return self._emit(role_id, capability, resource, "DENY", "UNKNOWN_ROLE")
        if capability not in self.capabilities:
            return self._emit(role_id, capability, resource, "DENY", "UNKNOWN_CAPABILITY")
        policy = self.registry["agents"][role_id]["capability_policy"]
        if capability in policy["denied"]:
            return self._emit(role_id, capability, resource, "DENY", "EXPLICITLY_DENIED")
        gated = {item["capability"]: item["gate_type"] for item in policy["gated"]}
        if capability not in policy["allowed"] and capability not in gated:
            return self._emit(role_id, capability, resource, "DENY", "NOT_GRANTED")
        scope_reason = self._scope_reason(capability, resource, policy["scope"], context)
        if scope_reason:
            return self._emit(role_id, capability, resource, "DENY", scope_reason)
        if capability in policy["scope"].get("task_granted_capabilities", []) and capability not in context.get("granted_capabilities", []):
            return self._emit(role_id, capability, resource, "DENY", "TASK_GRANT_REQUIRED")
        if capability in gated:
            gate_type = gated[capability]
            matching = [approval for approval in gate_approvals if approval.gate_type == gate_type and approval.capability == capability and approval.resource_hash == _resource_hash(resource)]
            valid = [approval for approval in matching if approval.status == "approved" and not approval.stale and approval.policy_version == self.policy_version]
            if valid:
                return self._emit(role_id, capability, resource, "ALLOW", "VALID_GATE_APPROVAL", gate_type)
            reason = "GATE_APPROVAL_STALE_OR_INVALID" if matching else "HUMAN_GATE_REQUIRED"
            return self._emit(role_id, capability, resource, "REQUIRE_GATE", reason, gate_type)
        return self._emit(role_id, capability, resource, "ALLOW", "EXPLICITLY_ALLOWED")

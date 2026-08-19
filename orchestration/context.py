from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .compiler import CompiledSystem
from .providers.base import ExecutionRequest


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _plain(value: Any) -> Any:
    if isinstance(value, dict) or hasattr(value, "items"):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, tuple) or isinstance(value, list):
        return [_plain(item) for item in value]
    return value


class ContextCompiler:
    """Compiles only role-scoped instructions and supplied artifact context."""

    def __init__(self, root: Path, compiled: CompiledSystem):
        self.root = root.resolve()
        self.compiled = compiled

    def _read(self, relative: str) -> tuple[str, str]:
        path = (self.root / relative).resolve()
        path.relative_to(self.root)
        text = path.read_text(encoding="utf-8")
        return text, _digest(text)

    def compile(self, *, role_id: str, task: str, workflow_context: dict[str, Any], inputs: dict[str, Any], tier: str, produces: list[str], authorization_context: dict[str, Any], attempt: int, repair_context: dict[str, Any] | None = None) -> ExecutionRequest:
        role = self.compiled.registry["agents"][role_id]
        produces = list(produces)
        role_text, role_hash = self._read(role["role_file"])
        hashes = {role["role_file"]: role_hash}
        skills: dict[str, str] = {}
        standards: dict[str, str] = {}
        pending = list(role.get("skills", ()))
        skill_ids: list[str] = []
        while pending:
            skill_id = pending.pop(0)
            if skill_id in skill_ids:
                continue
            skill_ids.append(skill_id)
            pending.extend(self.compiled.registry["skills"][skill_id]["dependencies"]["skills"])
        standard_ids = list(role.get("standards", ()))
        for skill_id in skill_ids:
            relative = self.compiled.registry["skills"][skill_id]["skill_file"]
            skills[skill_id], hashes[relative] = self._read(relative)
            standard_ids.extend(self.compiled.registry["skills"][skill_id]["dependencies"]["standards"])
        for standard_id in dict.fromkeys(standard_ids):
            relative = self.compiled.registry["standards"][standard_id]["standard_file"]
            standards[standard_id], hashes[relative] = self._read(relative)
        contracts = {}
        for artifact_type in produces:
            if artifact_type not in self.compiled.artifact_contracts:
                raise ValueError(f"no declared artifact contract for {artifact_type}")
            contracts[artifact_type] = _plain(self.compiled.artifact_contracts[artifact_type])
        output_contract = {
            "type": "object",
            "required": ["outcome", "reason_code", "artifacts"],
            "properties": {
                "outcome": {"type": "string", "enum": ["success", "escalate", "failure"]},
                "reason_code": {"type": "string", "minLength": 1},
                "artifacts": {"type": "object", "required": produces, "properties": contracts, "additionalProperties": False},
            },
            "additionalProperties": False,
        }
        return ExecutionRequest(role_id, role_text, skills, standards, task, workflow_context, inputs, tier, output_contract, authorization_context, hashes, attempt, repair_context)

    @staticmethod
    def render(request: ExecutionRequest) -> tuple[str, str]:
        instructions = "\n\n".join([request.role_instructions, *request.skills.values(), *request.standards.values()])
        payload = {
            "task": request.task,
            "workflow_context": request.workflow_context,
            "input_artifacts": request.input_artifacts,
            "authorization_context": request.authorization_context,
            "sources": request.source_hashes,
            "repair_context": request.repair_context,
        }
        return instructions, json.dumps(payload, sort_keys=True)

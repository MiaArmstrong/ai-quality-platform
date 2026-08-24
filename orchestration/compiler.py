from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

from tools.validate_contracts import load_json, load_yaml, validate_registry_data


class CompilationError(ValueError):
    pass


def _hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value


@dataclass(frozen=True)
class CompiledSystem:
    schema_version: str
    snapshot_hash: str
    source_hashes: Mapping[str, str]
    registry: Mapping[str, Any]
    workflows: Mapping[str, Any]
    artifact_types: tuple[str, ...]
    artifact_contracts: Mapping[str, Any]
    capabilities: Mapping[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "snapshot_hash": self.snapshot_hash,
            "source_hashes": dict(self.source_hashes),
            "registry": _thaw(self.registry),
            "workflows": _thaw(self.workflows),
            "artifact_types": list(self.artifact_types),
            "artifact_contracts": _thaw(self.artifact_contracts),
            "capabilities": _thaw(self.capabilities),
        }


def compile_system(root: Path) -> CompiledSystem:
    root = root.resolve()
    registry = load_yaml(root / ".agents/agent-registry.yaml")
    workflows = {
        workflow_id: load_json(root / definition["definition_file"])
        for workflow_id, definition in registry["workflows"].items()
    }
    errors = validate_registry_data(root, registry, workflows)
    if errors:
        raise CompilationError("\n".join(errors))
    artifact_doc = load_json(root / registry["artifact_types_file"])
    artifact_types = tuple(artifact_doc["artifact_types"])
    artifact_contracts = load_json(root / registry["artifact_contracts_file"])["contracts"]
    capability_doc = load_json(root / registry["capability_registry_file"])
    capabilities = {item["id"]: item for item in capability_doc["capabilities"]}
    referenced = {".agents/agent-registry.yaml", registry["artifact_types_file"], registry["artifact_contracts_file"], registry["capability_registry_file"]}
    referenced.update(item["role_file"] for item in registry["agents"].values())
    referenced.update(item["skill_file"] for item in registry["skills"].values())
    referenced.update(item["standard_file"] for item in registry["standards"].values())
    referenced.update(item["definition_file"] for item in registry["workflows"].values())
    referenced.update(registry["schemas"].values())
    source_hashes = {relative: _hash((root / relative).read_bytes()) for relative in sorted(referenced)}
    payload = {
        "schema_version": "compiled-system/v1",
        "source_hashes": source_hashes,
        "registry": registry,
        "workflows": workflows,
        "artifact_types": artifact_types,
        "artifact_contracts": artifact_contracts,
        "capabilities": capabilities,
    }
    snapshot_hash = _hash(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode())
    return CompiledSystem(
        "compiled-system/v1",
        snapshot_hash,
        _freeze(source_hashes),
        _freeze(registry),
        _freeze(workflows),
        artifact_types,
        _freeze(artifact_contracts),
        _freeze(capabilities),
    )

"""Validate the declarative agent-system contracts without executing workflows."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator, FormatChecker


EXPECTED_VERDICTS = [
    "SUPPORTED",
    "SUPPORTED_WITH_CONCERNS",
    "REFUTED",
    "INSUFFICIENT_EVIDENCE",
]


class ContractError(ValueError):
    """Raised when a contract cannot be loaded without losing information."""


class UniqueKeyLoader(yaml.SafeLoader):
    pass


def _construct_unique_mapping(loader: UniqueKeyLoader, node: yaml.MappingNode, deep: bool = False) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in result:
            raise ContractError(f"duplicate YAML key: {key}")
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_unique_mapping
)


def _unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ContractError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as stream:
        value = yaml.load(stream, Loader=UniqueKeyLoader)
    if not isinstance(value, dict):
        raise ContractError(f"{path}: root must be an object")
    return value


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as stream:
        value = json.load(stream, object_pairs_hook=_unique_json_object)
    if not isinstance(value, dict):
        raise ContractError(f"{path}: root must be an object")
    return value


def _schema_errors(instance: Any, schema: dict[str, Any], label: str) -> list[str]:
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = []
    for error in sorted(validator.iter_errors(instance), key=lambda item: list(item.path)):
        location = ".".join(str(part) for part in error.path) or "<root>"
        errors.append(f"{label}:{location}: {error.message}")
    return errors


def _check_file(root: Path, relative: str, label: str, errors: list[str]) -> None:
    path = (root / relative).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError:
        errors.append(f"{label}: path escapes repository root: {relative}")
        return
    if not path.is_file():
        errors.append(f"{label}: referenced file does not exist: {relative}")


def _front_matter(path: Path) -> dict[str, Any]:
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0] != "---":
        raise ContractError(f"{path}: missing opening YAML front-matter delimiter")
    try:
        closing = lines.index("---", 1)
    except ValueError as exc:
        raise ContractError(f"{path}: missing exact closing YAML front-matter delimiter") from exc
    value = yaml.load("\n".join(lines[1:closing]), Loader=UniqueKeyLoader)
    if not isinstance(value, dict):
        raise ContractError(f"{path}: front matter must be an object")
    return value


def _markdown_enum(path: Path) -> set[str]:
    return set(re.findall(r"`(SUPPORTED|SUPPORTED_WITH_CONCERNS|REFUTED|INSUFFICIENT_EVIDENCE)`", path.read_text(encoding="utf-8")))


def validate_registry_data(root: Path, registry: dict[str, Any], workflow_documents: dict[str, dict[str, Any]] | None = None) -> list[str]:
    errors: list[str] = []
    schema_path = root / ".agents/schemas/agent-registry.v1.schema.json"
    if schema_path.is_file():
        errors.extend(_schema_errors(registry, load_json(schema_path), "registry"))

    tiers = set(registry.get("enums", {}).get("tiers", []))
    verdicts = registry.get("enums", {}).get("verifier_verdicts", [])
    gate_types = set(registry.get("enums", {}).get("gate_types", []))
    roles = registry.get("agents", {})
    skills = registry.get("skills", {})
    standards = registry.get("standards", {})
    artifact_types: set[str] = set()
    artifact_types_file = registry.get("artifact_types_file", "")
    _check_file(root, artifact_types_file, "artifact types", errors)
    if (root / artifact_types_file).is_file():
        artifact_document = load_json(root / artifact_types_file)
        artifact_schema_path = root / ".agents/schemas/artifact-types.v1.schema.json"
        if artifact_schema_path.is_file():
            errors.extend(_schema_errors(artifact_document, load_json(artifact_schema_path), "artifact types"))
        values = artifact_document.get("artifact_types", [])
        if len(values) != len(set(values)):
            errors.append("artifact types: duplicate IDs")
        artifact_types = set(values)
    capabilities_file = registry.get("capability_registry_file", "")
    _check_file(root, capabilities_file, "capability registry", errors)
    capabilities: dict[str, dict[str, Any]] = {}
    if (root / capabilities_file).is_file():
        capability_document = load_json(root / capabilities_file)
        capability_schema_path = root / ".agents/schemas/capability-registry.v1.schema.json"
        if capability_schema_path.is_file():
            errors.extend(_schema_errors(capability_document, load_json(capability_schema_path), "capability registry"))
        capability_ids = [item.get("id") for item in capability_document.get("capabilities", [])]
        if len(capability_ids) != len(set(capability_ids)):
            errors.append("capability registry: duplicate IDs")
        capabilities = {item["id"]: item for item in capability_document.get("capabilities", []) if "id" in item}
    policy_schema_path = root / ".agents/schemas/role-capability-policy.v1.schema.json"
    policy_schema = load_json(policy_schema_path) if policy_schema_path.is_file() else None

    if verdicts != EXPECTED_VERDICTS:
        errors.append(f"registry: verifier verdict enum must equal {EXPECTED_VERDICTS}")

    for standard_id, definition in standards.items():
        _check_file(root, definition.get("standard_file", ""), f"standard {standard_id}", errors)

    for skill_id, definition in skills.items():
        skill_file = definition.get("skill_file", "")
        _check_file(root, skill_file, f"skill {skill_id}", errors)
        path = root / skill_file
        if path.is_file():
            try:
                metadata = _front_matter(path)
                if metadata.get("name") != skill_id:
                    errors.append(f"skill {skill_id}: front-matter name is {metadata.get('name')!r}")
            except ContractError as exc:
                errors.append(str(exc))
        dependencies = definition.get("dependencies", {})
        for dependency in dependencies.get("skills", []):
            if dependency not in skills:
                errors.append(f"skill {skill_id}: unknown skill dependency: {dependency}")
        for dependency in dependencies.get("standards", []):
            if dependency not in standards:
                errors.append(f"skill {skill_id}: unknown standard dependency: {dependency}")

    for role_id, definition in roles.items():
        _check_file(root, definition.get("role_file", ""), f"role {role_id}", errors)
        tier = definition.get("default_tier")
        escalation = definition.get("escalation_tier")
        if tier not in tiers:
            errors.append(f"role {role_id}: unknown default tier: {tier}")
        if escalation is not None:
            if escalation not in tiers:
                errors.append(f"role {role_id}: unknown escalation tier: {escalation}")
            allowed = registry.get("routing_policy", {}).get("allowed_transitions", {}).get(tier, [])
            if escalation not in allowed:
                errors.append(f"role {role_id}: tier transition {tier} -> {escalation} is not allowed")
        for skill_id in definition.get("skills", []):
            if skill_id not in skills:
                errors.append(f"role {role_id}: unknown skill: {skill_id}")
        for standard_id in definition.get("standards", []):
            if standard_id not in standards:
                errors.append(f"role {role_id}: unknown standard: {standard_id}")
        policy = definition.get("capability_policy", {})
        if policy_schema:
            errors.extend(_schema_errors(policy, policy_schema, f"role {role_id} capability policy"))
        allowed, denied = set(policy.get("allowed", [])), set(policy.get("denied", []))
        gated = {item.get("capability"): item.get("gate_type") for item in policy.get("gated", [])}
        gated_ids = [item.get("capability") for item in policy.get("gated", [])]
        if len(gated_ids) != len(set(gated_ids)):
            errors.append(f"role {role_id}: duplicate gated capability IDs")
        for capability in allowed | denied | set(gated):
            if capability not in capabilities:
                errors.append(f"role {role_id}: unknown capability: {capability}")
        conflicts = (allowed & denied) | (allowed & set(gated)) | (denied & set(gated))
        if conflicts:
            errors.append(f"role {role_id}: conflicting capability policies: {sorted(conflicts)}")
        for capability, gate_type in gated.items():
            if gate_type not in gate_types:
                errors.append(f"role {role_id}: gated capability {capability} references unknown gate type {gate_type}")
            if capability in capabilities and not capabilities[capability].get("gate_capable", False):
                errors.append(f"role {role_id}: capability is not gate-capable: {capability}")
        scope = policy.get("scope", {})
        for field in ("path_prefixes", "read_only_directories", "writable_directories"):
            for value in scope.get(field, []):
                if value.startswith(("/", "\\")) or ".." in value.replace("\\", "/").split("/"):
                    errors.append(f"role {role_id}: malformed {field} scope: {value}")
                if value.startswith("@") and not (field == "writable_directories" and value == "@task.authorized_paths"):
                    errors.append(f"role {role_id}: unknown dynamic scope token: {value}")
        for capability in scope.get("task_granted_capabilities", []):
            if capability not in allowed:
                errors.append(f"role {role_id}: task-granted capability must also be allowed: {capability}")

    required_gate_capable = {"wiki.write", "external.write", "vcs.push", "vcs.pr_create", "vcs.merge", "deploy.execute", "destructive.execute"}
    for capability in sorted(required_gate_capable):
        if capability not in capabilities or not capabilities[capability].get("gate_capable", False):
            errors.append(f"capability registry: sensitive capability must be gate-capable: {capability}")

    transitions = registry.get("routing_policy", {}).get("allowed_transitions", {})
    for source, destinations in transitions.items():
        if source not in tiers:
            errors.append(f"routing: unknown transition source tier: {source}")
        for destination in destinations:
            if destination not in tiers:
                errors.append(f"routing: unknown transition destination tier: {destination}")
            if destination == source:
                errors.append(f"routing: self-transition is not allowed: {source}")

    workflow_schema_path = root / ".agents/schemas/workflow-definition.v1.schema.json"
    workflow_schema = load_json(workflow_schema_path) if workflow_schema_path.is_file() else None
    for workflow_id, definition in registry.get("workflows", {}).items():
        relative = definition.get("definition_file", "")
        _check_file(root, relative, f"workflow {workflow_id}", errors)
        try:
            workflow = (workflow_documents or {}).get(workflow_id) or load_json(root / relative)
        except (ContractError, json.JSONDecodeError) as exc:
            errors.append(f"workflow {workflow_id}: {exc}")
            continue
        if workflow_schema:
            errors.extend(_schema_errors(workflow, workflow_schema, f"workflow {workflow_id}"))
        if workflow.get("workflow_id") != workflow_id:
            errors.append(f"workflow {workflow_id}: document ID does not match registry key")
        nodes = workflow.get("nodes", [])
        node_ids = [node.get("id") for node in nodes]
        duplicates = sorted({node_id for node_id in node_ids if node_ids.count(node_id) > 1})
        if duplicates:
            errors.append(f"workflow {workflow_id}: duplicate node IDs: {duplicates}")
        node_id_set = set(node_ids)
        if workflow.get("initial_node") not in node_id_set:
            errors.append(f"workflow {workflow_id}: initial node does not exist")
        present_gates = set()
        for node in nodes:
            if node.get("type") == "task" and node.get("role_id") not in roles:
                errors.append(f"workflow {workflow_id}: node {node.get('id')} references unknown role {node.get('role_id')}")
            if node.get("type") == "gate":
                gate_type = node.get("gate_type")
                present_gates.add(gate_type)
                if gate_type not in gate_types:
                    errors.append(f"workflow {workflow_id}: node {node.get('id')} references unknown gate type {gate_type}")
            for artifact_type in node.get("requires", []) + node.get("produces", []):
                if artifact_type not in artifact_types:
                    errors.append(f"workflow {workflow_id}: node {node.get('id')} references unknown artifact type {artifact_type}")
            for action in node.get("actions", []):
                capability = action.get("capability")
                if capability not in capabilities:
                    errors.append(f"workflow {workflow_id}: node {node.get('id')} references unknown capability {capability}")
                if node.get("type") == "task" and node.get("role_id") in roles:
                    policy = roles[node["role_id"]].get("capability_policy", {})
                    granted = set(policy.get("allowed", [])) | {item.get("capability") for item in policy.get("gated", [])}
                    if capability not in granted:
                        errors.append(f"workflow {workflow_id}: node {node.get('id')} declares capability not granted to role: {capability}")
        for required_gate in workflow.get("required_gates", []):
            if required_gate not in present_gates:
                errors.append(f"workflow {workflow_id}: required gate is missing: {required_gate}")
        for transition in workflow.get("transitions", []):
            if transition.get("from") not in node_id_set or transition.get("to") not in node_id_set:
                errors.append(f"workflow {workflow_id}: transition references unknown node: {transition}")
            if transition.get("on") == "bypass" and transition.get("bypass_reason_required") is not True:
                errors.append(f"workflow {workflow_id}: gate bypass must require an audit reason")

    expected = set(EXPECTED_VERDICTS)
    for relative in [
        ".agents/roles/adversarial-verifier.md",
        ".agents/standards/adversarial-verification.md",
    ]:
        path = root / relative
        if path.is_file() and _markdown_enum(path) != expected:
            errors.append(f"{relative}: verdict enum does not match registry")

    for schema_name, relative in registry.get("schemas", {}).items():
        _check_file(root, relative, f"schema {schema_name}", errors)
        path = root / relative
        if path.is_file():
            try:
                Draft202012Validator.check_schema(load_json(path))
            except Exception as exc:  # jsonschema reports several schema-specific types
                errors.append(f"schema {schema_name}: invalid JSON Schema: {exc}")
    return errors


def validate_repository(root: Path) -> list[str]:
    registry_path = root / ".agents/agent-registry.yaml"
    try:
        registry = load_yaml(registry_path)
    except (ContractError, yaml.YAMLError) as exc:
        return [f"registry: {exc}"]
    return validate_registry_data(root, registry)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    errors = validate_repository(args.root.resolve())
    if errors:
        print("Contract validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print("Contract validation passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping


UNSUPPORTED_KEYWORDS = {
    "allOf", "not", "dependentRequired", "dependentSchemas", "if", "then", "else",
    "minLength", "maxLength", "patternProperties", "uniqueItems", "contains",
    "minContains", "maxContains", "propertyNames", "unevaluatedProperties",
}
DEFER_TO_CANONICAL_VALIDATION = {"minLength", "maxLength"}
SUPPORTED_KEYWORDS = {
    "type", "properties", "required", "additionalProperties", "items", "enum",
    "anyOf", "$defs", "$ref", "description", "title", "pattern", "format",
    "multipleOf", "maximum", "exclusiveMaximum", "minimum", "exclusiveMinimum",
    "minItems", "maxItems", "const",
}


class OpenAISchemaCompatibilityError(ValueError):
    def __init__(self, errors: list[str]):
        self.errors = tuple(errors)
        super().__init__("OpenAI Structured Outputs schema is incompatible: " + "; ".join(errors))


def _path(parts: tuple[str, ...]) -> str:
    return "$" + "".join(f".{part}" for part in parts)


def validate_openai_structured_output_schema(schema: Mapping[str, Any]) -> None:
    errors: list[str] = []

    def visit(node: Any, path: tuple[str, ...], *, root: bool = False) -> None:
        if not isinstance(node, Mapping):
            return
        location = _path(path)
        for keyword in node:
            if keyword in UNSUPPORTED_KEYWORDS:
                errors.append(f"{location}: unsupported keyword {keyword!r}")
            elif keyword not in SUPPORTED_KEYWORDS:
                errors.append(f"{location}: unsupported or unknown keyword {keyword!r}")
        if root and node.get("type") != "object":
            errors.append("$: root schema must have type 'object'")
        if not any(key in node for key in ("type", "$ref", "anyOf")):
            errors.append(f"{location}: schema node must declare type, $ref, or anyOf")
        if node.get("type") == "object":
            properties = node.get("properties")
            if not isinstance(properties, Mapping):
                errors.append(f"{location}: object must declare properties")
                properties = {}
            if node.get("additionalProperties") is not False:
                errors.append(f"{location}: object must set additionalProperties to false")
            required = node.get("required")
            if not isinstance(required, list):
                errors.append(f"{location}: object must declare required as an array")
            elif set(required) != set(properties):
                missing = sorted(set(properties) - set(required))
                extra = sorted(set(required) - set(properties))
                errors.append(f"{location}: required must exactly match properties (missing={missing}, extra={extra})")
            for name, child in properties.items():
                visit(child, path + ("properties", str(name)))
        if node.get("type") == "array":
            if "items" not in node:
                errors.append(f"{location}: array must declare items")
            else:
                visit(node["items"], path + ("items",))
        for index, child in enumerate(node.get("anyOf", [])):
            visit(child, path + ("anyOf", str(index)))
        for name, child in node.get("$defs", {}).items():
            visit(child, path + ("$defs", str(name)))

    visit(schema, (), root=True)
    if errors:
        raise OpenAISchemaCompatibilityError(errors)


def make_openai_structured_output_schema(canonical_schema: Mapping[str, Any]) -> dict[str, Any]:
    """Project a canonical schema onto the documented OpenAI strict subset."""
    result = deepcopy(dict(canonical_schema))

    def project(node: Any) -> None:
        if not isinstance(node, dict):
            return
        for keyword in DEFER_TO_CANONICAL_VALIDATION:
            node.pop(keyword, None)
        for child in node.get("properties", {}).values():
            project(child)
        if "items" in node:
            project(node["items"])
        for child in node.get("anyOf", []):
            project(child)
        for child in node.get("$defs", {}).values():
            project(child)

    project(result)
    validate_openai_structured_output_schema(result)
    return result

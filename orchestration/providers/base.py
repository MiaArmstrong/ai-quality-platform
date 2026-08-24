from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol


@dataclass(frozen=True)
class ExecutionRequest:
    role_id: str
    role_instructions: str
    skills: Mapping[str, str]
    standards: Mapping[str, str]
    task: str
    workflow_context: Mapping[str, Any]
    input_artifacts: Mapping[str, Any]
    model_tier: str
    output_contract: Mapping[str, Any]
    authorization_context: Mapping[str, Any]
    source_hashes: Mapping[str, str]
    attempt: int
    repair_context: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class ExecutionTelemetry:
    provider: str
    model: str
    latency_ms: int
    attempt: int
    input_tokens: int | None = None
    output_tokens: int | None = None
    cached_tokens: int | None = None
    estimated_cost: float | None = None


@dataclass(frozen=True)
class ExecutionResult:
    outcome: str
    reason_code: str
    artifacts: Mapping[str, Any]
    telemetry: ExecutionTelemetry
    raw_output: str | None = None
    provider_response_id: str | None = None
    validation_errors: tuple[str, ...] = field(default_factory=tuple)


class ModelProvider(Protocol):
    def execute(self, request: ExecutionRequest) -> ExecutionResult: ...

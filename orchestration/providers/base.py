from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol


class ProviderInputBudgetError(ValueError):
    def __init__(self, *, estimated_input_tokens: int, max_input_tokens: int, counting_method: str):
        self.estimated_input_tokens = estimated_input_tokens
        self.max_input_tokens = max_input_tokens
        self.counting_method = counting_method
        self.safe_message = "compiled provider request exceeds the configured input-token budget"
        super().__init__(self.safe_message)


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
    cache_write_tokens: int | None = None
    max_output_tokens: int | None = None
    max_input_tokens: int | None = None
    estimated_input_tokens: int | None = None


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

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any, Mapping

from jsonschema import Draft202012Validator

from .base import ExecutionRequest, ExecutionResult, ExecutionTelemetry
from .openai_schema import make_openai_structured_output_schema


class ProviderConfigurationError(ValueError):
    pass


class OpenAIProviderRequestError(RuntimeError):
    def __init__(self, *, status: int | None, error_type: str | None, code: str | None, param: str | None, request_id: str | None, message: str):
        self.status, self.error_type, self.code, self.param = status, error_type, code, param
        self.request_id = request_id
        self.safe_message = message
        super().__init__(f"OpenAI request rejected (status={status}, type={error_type}, code={code}, param={param}, request_id={request_id}): {message}")


@dataclass(frozen=True)
class OpenAIProviderConfig:
    api_key: str
    models: Mapping[str, str]
    pricing: Mapping[str, Mapping[str, float]] | None = None

    @classmethod
    def from_environment(cls, provider_contract: Mapping[str, Any], environ: Mapping[str, str] | None = None) -> "OpenAIProviderConfig":
        env = os.environ if environ is None else environ
        key_name = provider_contract["api_key_env"]
        api_key = env.get(key_name)
        if not api_key:
            raise ProviderConfigurationError(f"missing required environment variable: {key_name}")
        models = {tier: env.get(name, "") for tier, name in provider_contract["model_env"].items()}
        missing = [tier for tier, model in models.items() if not model]
        if missing:
            raise ProviderConfigurationError(f"missing model configuration for tiers: {', '.join(missing)}")
        return cls(api_key, models)

    def resolve_model(self, tier: str) -> str:
        try:
            return self.models[tier]
        except KeyError as exc:
            raise ProviderConfigurationError(f"no OpenAI model configured for tier: {tier}") from exc


class OpenAIProvider:
    provider_id = "openai"

    def __init__(self, config: OpenAIProviderConfig, client: Any | None = None):
        self.config = config
        if client is None:
            try:
                from openai import OpenAI
            except ImportError as exc:
                raise ProviderConfigurationError("OpenAI provider requires the optional 'openai' package") from exc
            client = OpenAI(api_key=config.api_key)
        self.client = client

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        from orchestration.context import ContextCompiler

        model = self.config.resolve_model(request.model_tier)
        provider_schema = make_openai_structured_output_schema(request.output_contract)
        instructions, input_text = ContextCompiler.render(request)
        started = time.perf_counter()
        try:
            response = self.client.responses.create(
                model=model,
                instructions=instructions,
                input=input_text,
                text={"format": {"type": "json_schema", "name": "role_execution", "strict": True, "schema": provider_schema}},
            )
        except Exception as exc:
            if exc.__class__.__name__ != "BadRequestError" and getattr(exc, "status_code", None) != 400:
                raise
            raise self._safe_bad_request(exc) from None
        latency_ms = round((time.perf_counter() - started) * 1000)
        raw = getattr(response, "output_text", None)
        usage = getattr(response, "usage", None)
        input_details = getattr(usage, "input_tokens_details", None) if usage else None
        telemetry = ExecutionTelemetry(
            self.provider_id, getattr(response, "model", model), latency_ms, request.attempt,
            getattr(usage, "input_tokens", None) if usage else None,
            getattr(usage, "output_tokens", None) if usage else None,
            getattr(input_details, "cached_tokens", None) if input_details else None,
            self._estimate_cost(model, usage),
        )
        if not raw:
            return ExecutionResult("failure", "provider_no_output", {}, telemetry, raw, getattr(response, "id", None), ("response contained no output text",))
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            return ExecutionResult("failure", "malformed_json", {}, telemetry, raw, getattr(response, "id", None), (str(exc),))
        errors = tuple(error.message for error in Draft202012Validator(request.output_contract).iter_errors(parsed))
        if errors:
            return ExecutionResult("failure", "schema_validation_failed", {}, telemetry, raw, getattr(response, "id", None), errors)
        return ExecutionResult(parsed["outcome"], parsed["reason_code"], parsed["artifacts"], telemetry, raw, getattr(response, "id", None))

    def _safe_bad_request(self, exc: Exception) -> OpenAIProviderRequestError:
        body = getattr(exc, "body", None)
        error = body.get("error", body) if isinstance(body, dict) else {}
        response = getattr(exc, "response", None)
        if not error and response is not None:
            try:
                response_body = response.json()
                error = response_body.get("error", response_body) if isinstance(response_body, dict) else {}
            except Exception:
                pass
        message = str(error.get("message") or (body if isinstance(body, str) else None) or getattr(exc, "message", None) or "OpenAI rejected the request")
        if self.config.api_key:
            message = message.replace(self.config.api_key, "[REDACTED]")
        import re
        message = re.sub(r"(?i)bearer\s+\S+", "Bearer [REDACTED]", message)
        message = re.sub(r"sk-[A-Za-z0-9_-]{8,}", "[REDACTED]", message)[:1000]
        return OpenAIProviderRequestError(
            status=getattr(exc, "status_code", 400),
            error_type=error.get("type") or getattr(exc, "type", None),
            code=error.get("code") or getattr(exc, "code", None),
            param=error.get("param") or getattr(exc, "param", None),
            request_id=getattr(exc, "request_id", None),
            message=message,
        )

    def _estimate_cost(self, model: str, usage: Any) -> float | None:
        if not self.config.pricing or model not in self.config.pricing or usage is None:
            return None
        rates = self.config.pricing[model]
        return (getattr(usage, "input_tokens", 0) * rates.get("input_per_token", 0.0) + getattr(usage, "output_tokens", 0) * rates.get("output_per_token", 0.0))

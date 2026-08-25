from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any, Mapping

from jsonschema import Draft202012Validator

from .base import ExecutionRequest, ExecutionResult, ExecutionTelemetry, ProviderInputBudgetError
from .openai_schema import make_openai_structured_output_schema


class ProviderConfigurationError(ValueError):
    pass


class TiktokenInputEstimator:
    """Deterministic local estimate; server protocol accounting can differ."""

    counting_method = "tiktoken_with_256_token_protocol_allowance"

    def estimate(self, *, model: str, instructions: str, input_text: str, output_schema: Mapping[str, Any]) -> int:
        try:
            import tiktoken
        except ImportError as exc:
            raise ProviderConfigurationError("input budgeting requires the optional 'tiktoken' package") from exc
        try:
            encoding = tiktoken.encoding_for_model(model)
        except KeyError:
            encoding = tiktoken.get_encoding("o200k_base")
        schema_text = json.dumps(output_schema, sort_keys=True, separators=(",", ":"))
        return sum(len(encoding.encode(value)) for value in (instructions, input_text, schema_text)) + 256


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
    max_output_tokens: int | None = None
    max_input_tokens: int | None = None

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
        pricing = None
        pricing_name = provider_contract.get("pricing_env")
        if pricing_name and env.get(pricing_name):
            try:
                pricing = json.loads(env[pricing_name])
            except json.JSONDecodeError as exc:
                raise ProviderConfigurationError(f"invalid JSON in pricing environment variable: {pricing_name}") from exc
            if not isinstance(pricing, dict):
                raise ProviderConfigurationError(f"pricing environment variable must contain a JSON object: {pricing_name}")
        def positive_integer(field: str) -> int | None:
            name = provider_contract.get(field)
            if not name or not env.get(name):
                return None
            try:
                value = int(env[name])
            except ValueError as exc:
                raise ProviderConfigurationError(f"{name} must be a positive integer") from exc
            if value <= 0:
                raise ProviderConfigurationError(f"{name} must be a positive integer")
            return value
        return cls(api_key, models, pricing, positive_integer("max_output_tokens_env"), positive_integer("max_input_tokens_env"))

    def resolve_model(self, tier: str) -> str:
        try:
            return self.models[tier]
        except KeyError as exc:
            raise ProviderConfigurationError(f"no OpenAI model configured for tier: {tier}") from exc


class OpenAIProvider:
    provider_id = "openai"

    def __init__(self, config: OpenAIProviderConfig, client: Any | None = None, input_estimator: Any | None = None):
        self.config = config
        self.input_estimator = input_estimator or TiktokenInputEstimator()
        if client is None:
            try:
                from openai import OpenAI
            except ImportError as exc:
                raise ProviderConfigurationError("OpenAI provider requires the optional 'openai' package") from exc
            client = OpenAI(api_key=config.api_key)
        self.client = client

    def validate_request_budget(self, request: ExecutionRequest) -> int | None:
        if self.config.max_input_tokens is None:
            return None
        from orchestration.context import ContextCompiler
        model = self.config.resolve_model(request.model_tier)
        provider_schema = make_openai_structured_output_schema(request.output_contract)
        instructions, input_text = ContextCompiler.render(request)
        estimate = self.input_estimator.estimate(model=model, instructions=instructions, input_text=input_text, output_schema=provider_schema)
        if estimate > self.config.max_input_tokens:
            raise ProviderInputBudgetError(
                estimated_input_tokens=estimate,
                max_input_tokens=self.config.max_input_tokens,
                counting_method=getattr(self.input_estimator, "counting_method", self.input_estimator.__class__.__name__),
            )
        return estimate

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        from orchestration.context import ContextCompiler

        model = self.config.resolve_model(request.model_tier)
        provider_schema = make_openai_structured_output_schema(request.output_contract)
        instructions, input_text = ContextCompiler.render(request)
        estimated_input_tokens = self.validate_request_budget(request)
        started = time.perf_counter()
        request_args = {
            "model": model,
            "instructions": instructions,
            "input": input_text,
            "text": {"format": {"type": "json_schema", "name": "role_execution", "strict": True, "schema": provider_schema}},
            "store": False,
        }
        if self.config.max_output_tokens is not None:
            request_args["max_output_tokens"] = self.config.max_output_tokens
        try:
            response = self.client.responses.create(
                **request_args,
            )
        except Exception as exc:
            raise self._safe_request_error(exc) from None
        latency_ms = round((time.perf_counter() - started) * 1000)
        raw = getattr(response, "output_text", None)
        usage = getattr(response, "usage", None)
        input_details = getattr(usage, "input_tokens_details", None) if usage else None
        telemetry = ExecutionTelemetry(
            provider=self.provider_id, model=getattr(response, "model", model), latency_ms=latency_ms, attempt=request.attempt,
            input_tokens=getattr(usage, "input_tokens", None) if usage else None,
            output_tokens=getattr(usage, "output_tokens", None) if usage else None,
            cached_tokens=getattr(input_details, "cached_tokens", None) if input_details else None,
            cache_write_tokens=getattr(input_details, "cache_write_tokens", None) if input_details else None,
            estimated_cost=self._estimate_cost(model, usage),
            max_output_tokens=self.config.max_output_tokens,
            max_input_tokens=self.config.max_input_tokens,
            estimated_input_tokens=estimated_input_tokens,
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
        return self._safe_request_error(exc)

    def _safe_request_error(self, exc: Exception) -> OpenAIProviderRequestError:
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
            status=getattr(exc, "status_code", None),
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
        required = {"input_per_million", "cached_input_per_million", "cache_write_per_million", "output_per_million"}
        if not required.issubset(rates):
            return None
        input_tokens = getattr(usage, "input_tokens", None)
        output_tokens = getattr(usage, "output_tokens", None)
        details = getattr(usage, "input_tokens_details", None)
        cached_tokens = getattr(details, "cached_tokens", None) if details is not None else None
        cache_write_tokens = getattr(details, "cache_write_tokens", None) if details is not None else None
        if input_tokens is None or output_tokens is None or cached_tokens is None or cache_write_tokens is None:
            return None
        normal_tokens = input_tokens - cached_tokens - cache_write_tokens
        if normal_tokens < 0:
            return None
        return (
            normal_tokens * rates["input_per_million"]
            + cached_tokens * rates["cached_input_per_million"]
            + cache_write_tokens * rates["cache_write_per_million"]
            + output_tokens * rates["output_per_million"]
        ) / 1_000_000

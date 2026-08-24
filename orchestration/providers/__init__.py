"""Provider adapters for model-only role execution."""

from .base import ExecutionRequest, ExecutionResult, ExecutionTelemetry, ModelProvider
from .openai import OpenAIProvider, OpenAIProviderConfig, OpenAIProviderRequestError
from .openai_schema import OpenAISchemaCompatibilityError, make_openai_structured_output_schema, validate_openai_structured_output_schema

__all__ = ["ExecutionRequest", "ExecutionResult", "ExecutionTelemetry", "ModelProvider", "OpenAIProvider", "OpenAIProviderConfig", "OpenAIProviderRequestError", "OpenAISchemaCompatibilityError", "make_openai_structured_output_schema", "validate_openai_structured_output_schema"]

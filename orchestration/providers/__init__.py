"""Provider adapters for model-only role execution."""

from .base import ExecutionRequest, ExecutionResult, ExecutionTelemetry, ModelProvider
from .openai import OpenAIProvider, OpenAIProviderConfig

__all__ = ["ExecutionRequest", "ExecutionResult", "ExecutionTelemetry", "ModelProvider", "OpenAIProvider", "OpenAIProviderConfig"]

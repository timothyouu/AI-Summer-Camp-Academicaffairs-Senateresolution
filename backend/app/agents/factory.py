from __future__ import annotations

import importlib
import importlib.util
from threading import Lock
from typing import Any

from ..config import get_settings
from .pipeline import AgentPipeline, LLM


_STRANDS_GENERATION_ERROR_NAMES = (
    "ContextWindowOverflowException",
    "MaxTokensReachedException",
    "ModelThrottledException",
    "ProviderTokenCountError",
    "StructuredOutputException",
)

_GUARDRAIL_REFUSAL_MARKER = (
    "i can help you find and understand existing policy, but i can't help with that"
)

_BEDROCK_CONNECT_TIMEOUT_SECONDS = 3
_BEDROCK_TRANSPORT_ERROR_NAMES = (
    "ConnectTimeoutError",
    "ConnectionClosedError",
    "EndpointConnectionError",
    "ReadTimeoutError",
)


def strands_available() -> bool:
    return importlib.util.find_spec("strands") is not None


class StrandsLLM:
    """Lazy Strands adapter; no SDK or AWS import occurs in local mode.

    A new SDK agent is created for every generation. Strands agents retain
    conversation state and reject concurrent calls by default, while the
    pipeline deliberately runs blind per-source extractors in parallel. Fresh
    instances keep those extractor contexts isolated and avoid sharing mutable
    agent history between pipeline roles.
    """

    def __init__(self, *, generation_timeout_seconds: float | None = None) -> None:
        module = importlib.import_module("strands")
        self._agent_type: Any = getattr(module, "Agent")
        settings = get_settings()
        self._generation_timeout_seconds = (
            settings.bedrock_generation_timeout_seconds
            if generation_timeout_seconds is None
            else generation_timeout_seconds
        )
        if self._generation_timeout_seconds <= 0:
            raise ValueError("Strands generation timeout must be positive")
        models = importlib.import_module("strands.models")
        model_type: Any = getattr(models, "BedrockModel")
        botocore_config = importlib.import_module("botocore.config")
        config_type: Any = getattr(botocore_config, "Config")
        client_config = config_type(
            connect_timeout=_BEDROCK_CONNECT_TIMEOUT_SECONDS,
            read_timeout=self._generation_timeout_seconds,
            retries={"total_max_attempts": 1, "mode": "standard"},
        )
        model_kwargs: dict[str, Any] = {
            "model_id": settings.bedrock_model_id,
            "streaming": settings.bedrock_streaming,
            "max_tokens": settings.bedrock_max_tokens,
            "temperature": settings.bedrock_temperature,
        }
        if settings.guardrails_aws:
            model_kwargs.update(
                guardrail_id=settings.bedrock_guardrail_id,
                guardrail_version=settings.bedrock_guardrail_version,
            )
        self._bedrock_model: Any = model_type(
            boto_client_config=client_config,
            **model_kwargs,
        )
        self._generation_error_types = _strands_generation_error_types()
        self._transport_error_types = _bedrock_transport_error_types()
        self._circuit_lock = Lock()
        self._disabled_reason: str | None = None

    def generate(self, system: str, user: str, json_mode: bool = False) -> str:
        del json_mode
        with self._circuit_lock:
            disabled_reason = self._disabled_reason
        if disabled_reason is not None:
            raise RuntimeError(f"Strands generation disabled after {disabled_reason}")
        agent: Any = self._agent_type(
            model=self._bedrock_model,
            system_prompt=system,
            callback_handler=None,
            retry_strategy=None,
        )
        try:
            result = agent(user, limits={"max_turns": 1})
        except Exception as exc:
            if not isinstance(exc, self._generation_error_types + self._transport_error_types):
                raise
            reason = f"Strands generation failed: {exc}"
            self._disable(reason)
            raise RuntimeError(reason) from exc
        text = _message_text(getattr(result, "message", result))
        if _is_repeated_guardrail_refusal(text):
            reason = "Strands generation repeated the guardrail refusal response"
            self._disable(reason)
            raise RuntimeError(reason)
        return text

    def _disable(self, reason: str) -> None:
        with self._circuit_lock:
            if self._disabled_reason is None:
                self._disabled_reason = reason


def _strands_generation_error_types() -> tuple[type[Exception], ...]:
    """Return recoverable SDK generation errors without importing Strands locally."""
    try:
        exceptions = importlib.import_module("strands.types.exceptions")
    except ImportError:
        return ()
    return tuple(
        error_type
        for name in _STRANDS_GENERATION_ERROR_NAMES
        if isinstance((error_type := getattr(exceptions, name, None)), type)
        and issubclass(error_type, Exception)
    )


def _bedrock_transport_error_types() -> tuple[type[Exception], ...]:
    """Return retryable Botocore transport errors without importing AWS locally."""
    try:
        exceptions = importlib.import_module("botocore.exceptions")
    except ImportError:
        return ()
    return tuple(
        error_type
        for name in _BEDROCK_TRANSPORT_ERROR_NAMES
        if isinstance((error_type := getattr(exceptions, name, None)), type)
        and issubclass(error_type, Exception)
    )


def _message_text(message: Any) -> str:
    """Extract assistant text from a Strands result message.

    Strands returns a structured message ({"role": ..., "content": [{"text":
    ...}, ...]}) — str() on it would yield a Python repr that never parses as
    the JSON the pipeline asked for.
    """
    if isinstance(message, str):
        return message
    content = message.get("content", []) if isinstance(message, dict) else getattr(message, "content", [])
    parts = [block.get("text", "") if isinstance(block, dict) else str(getattr(block, "text", ""))
             for block in content or []]
    text = "".join(parts).strip()
    return text if text else str(message)


def _is_repeated_guardrail_refusal(text: str) -> bool:
    normalized = " ".join(text.lower().split())
    return normalized.count(_GUARDRAIL_REFUSAL_MARKER) >= 2


class _DeterministicLLM:
    """Select the pipeline's grounded fallbacks without calling a text model."""

    def generate(self, system: str, user: str, json_mode: bool = False) -> str:
        del system, user, json_mode
        raise RuntimeError("Bedrock text generation is disabled; using deterministic analysis")


def create_pipeline(*, llm: LLM | None = None) -> AgentPipeline:
    """Use KB-grounded deterministic analysis unless generation is opted in."""
    if llm is not None:
        return AgentPipeline(llm=llm)
    settings = get_settings()
    if settings.retrieval_aws:
        if settings.bedrock_generation_enabled and strands_available():
            return AgentPipeline(llm=StrandsLLM(), authoritative=True)
        return AgentPipeline(llm=_DeterministicLLM(), authoritative=True)
    return AgentPipeline()

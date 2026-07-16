from __future__ import annotations

import importlib
import importlib.util
from queue import Empty, Queue
from threading import Lock, Thread
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


class _RecoverableStrandsError(RuntimeError):
    """A provider outcome that should open the per-request fallback circuit."""


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
        models = importlib.import_module("strands.models")
        model_type: Any = getattr(models, "BedrockModel")
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
        self._bedrock_model: Any = model_type(**model_kwargs)
        self._generation_error_types = _strands_generation_error_types()
        self._generation_timeout_seconds = (
            settings.bedrock_generation_timeout_seconds
            if generation_timeout_seconds is None
            else generation_timeout_seconds
        )
        if self._generation_timeout_seconds <= 0:
            raise ValueError("Strands generation timeout must be positive")
        self._circuit_lock = Lock()
        self._disabled_reason: str | None = None

    def generate(self, system: str, user: str, json_mode: bool = False) -> str:
        del json_mode
        with self._circuit_lock:
            disabled_reason = self._disabled_reason
        if disabled_reason is not None:
            raise RuntimeError(f"Strands generation disabled after {disabled_reason}")
        agent: Any = self._agent_type(model=self._bedrock_model, system_prompt=system)
        try:
            result = self._invoke_with_timeout(agent, user)
        except _RecoverableStrandsError as exc:
            self._disable(str(exc))
            raise RuntimeError(str(exc)) from exc
        except Exception as exc:
            if not isinstance(exc, self._generation_error_types):
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

    def _invoke_with_timeout(self, agent: Any, user: str) -> Any:
        """Bound one provider call without hiding exceptions from completed calls.

        The Strands call is synchronous and can keep consuming a guardrail refusal
        stream until the outer Lambda timeout. A daemon worker lets the request
        fall back deterministically while the provider call is still stalled;
        completed SDK and programmer exceptions are returned to ``generate`` and
        retain their existing selective handling.
        """
        outcome: Queue[tuple[bool, Any]] = Queue(maxsize=1)

        def invoke() -> None:
            try:
                outcome.put((True, agent(user)))
            except Exception as exc:
                outcome.put((False, exc))

        Thread(target=invoke, name="strands-generation", daemon=True).start()
        try:
            succeeded, value = outcome.get(timeout=self._generation_timeout_seconds)
        except Empty as exc:
            raise _RecoverableStrandsError(
                f"Strands generation exceeded {self._generation_timeout_seconds:g} seconds"
            ) from exc
        if not succeeded:
            raise value
        return value


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


def create_pipeline(*, llm: LLM | None = None) -> AgentPipeline:
    """Select Strands only when both its SDK and a configured Bedrock KB are present."""
    if llm is not None:
        return AgentPipeline(llm=llm)
    if get_settings().retrieval_aws and strands_available():
        return AgentPipeline(llm=StrandsLLM(), authoritative=True)
    return AgentPipeline()

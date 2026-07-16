from __future__ import annotations

import importlib
import importlib.util
from typing import Any

from ..config import get_settings
from .pipeline import AgentPipeline, LLM


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

    def __init__(self) -> None:
        module = importlib.import_module("strands")
        self._agent_type: Any = getattr(module, "Agent")
        self._bedrock_model: Any | None = None
        settings = get_settings()
        if settings.guardrails_aws:
            try:
                models = importlib.import_module("strands.models")
                model_type: Any = getattr(models, "BedrockModel")
                self._bedrock_model = model_type(
                    guardrail_id=settings.bedrock_guardrail_id,
                    guardrail_version=settings.bedrock_guardrail_version,
                )
            except (ImportError, AttributeError, TypeError):
                # Older Strands releases may not expose BedrockModel here.
                self._bedrock_model = None

    def generate(self, system: str, user: str, json_mode: bool = False) -> str:
        del json_mode
        if self._bedrock_model is None:
            agent: Any = self._agent_type(system_prompt=system)
        else:
            agent = self._agent_type(model=self._bedrock_model, system_prompt=system)
        result = agent(user)
        return _message_text(getattr(result, "message", result))


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


def create_pipeline(*, llm: LLM | None = None) -> AgentPipeline:
    """Select Strands only when both its SDK and a configured Bedrock KB are present."""
    if llm is not None:
        return AgentPipeline(llm=llm)
    if get_settings().retrieval_aws and strands_available():
        return AgentPipeline(llm=StrandsLLM(), authoritative=True)
    return AgentPipeline()

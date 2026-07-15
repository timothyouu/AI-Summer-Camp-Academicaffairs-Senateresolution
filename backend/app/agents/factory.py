from __future__ import annotations

import importlib
import importlib.util
from typing import Any

from ..config import get_settings
from .pipeline import AgentPipeline, LLM


def strands_available() -> bool:
    return importlib.util.find_spec("strands") is not None


class StrandsLLM:
    """Lazy Strands adapter; no SDK or AWS import occurs in local mode."""

    def __init__(self) -> None:
        module = importlib.import_module("strands")
        agent_type = getattr(module, "Agent")
        self._agent: Any = agent_type(system_prompt="Return only the requested structured JSON. Ground every policy claim in supplied text.")

    def generate(self, system: str, user: str, json_mode: bool = False) -> str:
        del json_mode
        result = self._agent(f"{system}\n\nINPUT:\n{user}")
        return str(getattr(result, "message", result))


def create_pipeline(*, llm: LLM | None = None) -> AgentPipeline:
    """Select Strands only when both its SDK and a configured Bedrock KB are present."""
    if llm is not None:
        return AgentPipeline(llm=llm)
    if get_settings().retrieval_aws and strands_available():
        return AgentPipeline(llm=StrandsLLM())
    return AgentPipeline()

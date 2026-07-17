from __future__ import annotations

import importlib
import importlib.util
from typing import Any

from ..config import bedrock_client_config, get_settings
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

    def __init__(self, model_id: str | None = None) -> None:
        module = importlib.import_module("strands")
        self._agent_type: Any = getattr(module, "Agent")
        self._bedrock_model: Any | None = None
        settings = get_settings()
        # Build an explicit BedrockModel when a guardrail is set OR a specific
        # model id is requested (the fast-model split). Otherwise the Agent uses
        # the SDK default model, unchanged from before.
        if settings.guardrails_aws or model_id:
            kwargs: dict[str, Any] = {}
            if settings.guardrails_aws:
                kwargs["guardrail_id"] = settings.bedrock_guardrail_id
                kwargs["guardrail_version"] = settings.bedrock_guardrail_version
            if model_id:
                kwargs["model_id"] = model_id
            try:
                models = importlib.import_module("strands.models")
                model_type: Any = getattr(models, "BedrockModel")
                self._bedrock_model = model_type(**kwargs)
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


class BedrockConverseLLM:
    """Direct Bedrock generation via boto3 ``converse``.

    Used on the authoritative path when a Knowledge Base is configured but the
    Strands SDK is not installed — so naming ``BEDROCK_KB_ID`` alone is enough to
    get real generated answers, closing the "KB set but generation still local"
    tripwire. Mirrors the boto3 seam already used for KB retrieval; the
    Guardrail attaches when configured, matching ``StrandsLLM``.
    """

    def __init__(self, model_id: str | None = None) -> None:
        import boto3  # type: ignore[import-not-found]  # Lazy: absent in local mode.

        settings = get_settings()
        self._client: Any = boto3.client(
            "bedrock-runtime", region_name=settings.aws_region,
            config=bedrock_client_config(settings),
        )
        self._model_id = model_id or settings.bedrock_model_id
        self._guardrail: dict[str, Any] | None = None
        if settings.guardrails_aws:
            self._guardrail = {
                "guardrailIdentifier": settings.bedrock_guardrail_id,
                "guardrailVersion": settings.bedrock_guardrail_version or "DRAFT",
            }

    def generate(self, system: str, user: str, json_mode: bool = False) -> str:
        del json_mode
        kwargs: dict[str, Any] = {
            "modelId": self._model_id,
            "system": [{"text": system}],
            "messages": [{"role": "user", "content": [{"text": user}]}],
            "inferenceConfig": {"maxTokens": 1024, "temperature": 0.0},
        }
        if self._guardrail is not None:
            kwargs["guardrailConfig"] = self._guardrail
        response = self._client.converse(**kwargs)
        return _message_text(response.get("output", {}).get("message", {}))


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
    """Pick the generation seam for a configured Knowledge Base.

    Naming ``BEDROCK_KB_ID`` is sufficient to get real generated answers: the
    Strands SDK is used when installed, otherwise generation falls back to a
    direct boto3 Bedrock ``converse`` call. Only when no KB is configured does
    the pipeline stay fully local (``ModuleLLM``, whose ``generate`` raises).

    When ``BEDROCK_FAST_MODEL_ID`` is set, the pipeline's mechanical stages
    (extract/detect/verify) run on the fast model while user-facing prose
    (synthesis, draft revision) stays on ``bedrock_model_id`` via a separate
    ``synthesis_llm``. Unset -> both are the same instance, byte-for-byte
    identical to before.
    """
    if llm is not None:
        return AgentPipeline(llm=llm)
    if not get_settings().retrieval_aws:
        return AgentPipeline()
    fast_model = get_settings().bedrock_fast_model_id
    use_strands = strands_available()
    if not fast_model:
        # Unchanged path: one model everywhere. Constructors are called with no
        # args so the generation-gate tests' zero-arg monkeypatches still apply.
        selected: LLM = StrandsLLM() if use_strands else BedrockConverseLLM()
        return AgentPipeline(llm=selected, authoritative=True)
    # Split: fast model for mechanical JSON stages, default model for prose.
    if use_strands:
        mechanical: LLM = StrandsLLM(fast_model)
        prose: LLM = StrandsLLM()
    else:
        mechanical = BedrockConverseLLM(fast_model)
        prose = BedrockConverseLLM()
    return AgentPipeline(llm=mechanical, synthesis_llm=prose, authoritative=True)

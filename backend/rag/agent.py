from typing import Any, Union

from strands import Agent
from strands.models import BedrockModel

from config import (
    BEDROCK_GUARDRAIL_ID,
    BEDROCK_GUARDRAIL_VERSION,
    MODEL_ID,
    REGION,
)

from retrieval.search import (
    search_academic_policy,
    search_senate_policy
)

# Guardrails attach only when BEDROCK_GUARDRAIL_ID is set, matching the
# env-gated pattern used across the repo (nothing flips until the env var is).
model: Union[str, BedrockModel] = MODEL_ID
if BEDROCK_GUARDRAIL_ID:
    model = BedrockModel(
        model_id=MODEL_ID,
        region_name=REGION,
        guardrail_id=BEDROCK_GUARDRAIL_ID,
        guardrail_version=BEDROCK_GUARDRAIL_VERSION,
    )
    print("Guardrail enabled:", BEDROCK_GUARDRAIL_ID, BEDROCK_GUARDRAIL_VERSION)

# Create the Strands Agent
agent = Agent(
    model=model,
    tools=[
        search_academic_policy,
        search_senate_policy
    ],
    system_prompt="""
You are the CSUB Policy Intelligence Assistant.

Your job is to answer policy questions using the provided
Academic Affairs and Senate Resolution knowledge bases.

Always:
- Use the retrieval tools before answering.
- Do not make up policies.
- Explain which policy information supports your answer.
"""
)


def ask_policy_assistant(question: str) -> Any:
    response = agent(question)

    return response


# Test locally
if __name__ == "__main__":
    question = "What is the academic probation policy?"

    answer = ask_policy_assistant(question)

    print(answer)

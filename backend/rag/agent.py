from typing import Any

from strands import Agent
from config import MODEL_ID
from retrieval.search import (
    search_academic_policy,
    search_senate_policy
)


# Create the Strands Agent
agent = Agent(
    model=MODEL_ID,
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

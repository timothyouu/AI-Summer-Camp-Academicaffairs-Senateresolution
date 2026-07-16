import boto3
from config import ACADEMIC_KB_ID, REGION, SENATE_KB_ID
from strands import tool


# Bedrock Knowledge Base client
bedrock_agent = boto3.client(
    "bedrock-agent-runtime",
    region_name=REGION,
)


def search_policy(question: str, knowledge_base_id: str) -> str:
    """
    Search a Bedrock Knowledge Base and return relevant documents.
    """

    response = bedrock_agent.retrieve(
        knowledgeBaseId=knowledge_base_id,
        retrievalQuery={"text": question},
        retrievalConfiguration={
            "vectorSearchConfiguration": {
                "numberOfResults": 5,
            }
        },
    )

    documents: list[str] = []

    for result in response["retrievalResults"]:
        text = result["content"]["text"]
        documents.append(text)

    return "\n\n".join(documents)

@tool
def search_academic_policy(question: str) -> str:
    """
    Search the Academic Affairs policy knowledge base.
    Use this for questions about academic policies.
    """
    return search_policy(
        question,
        ACADEMIC_KB_ID
    )

@tool
def search_senate_policy(question: str) -> str:
    """
    Search the Senate Resolution knowledge base.
    Use this for questions about senate resolutions.
    """
    return search_policy(
        question,
        SENATE_KB_ID
    )

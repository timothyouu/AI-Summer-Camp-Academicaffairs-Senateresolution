import boto3
from config import ACADEMIC_KB_ID, SENATE_KB_ID
from strands import tool


# Bedrock Knowledge Base client
bedrock_agent = boto3.client(
    "bedrock-agent-runtime",
    region_name="us-west-2"
)


def search_policy(question, knowledge_base_id):
    """
    Search a Bedrock Knowledge Base and return relevant documents.
    """

    response = bedrock_agent.retrieve(
    knowledgeBaseId=knowledge_base_id,
    retrievalQuery={
        "text": question
    },
    retrievalConfiguration={
        "managedSearchConfiguration": {
            "numberOfResults": 5
        }
    }
)

    documents = []

    for result in response["retrievalResults"]:
        text = result["content"]["text"]
        documents.append(text)

    return "\n\n".join(documents)

@tool
def search_academic_policy(question: str):
    """
    Search the Academic Affairs policy knowledge base.
    Use this for questions about academic policies.
    """
    return search_policy(
        question,
        ACADEMIC_KB_ID
    )

@tool
def search_senate_policy(question: str):
    """
    Search the Senate Resolution knowledge base.
    Use this for questions about senate resolutions.
    """
    return search_policy(
        question,
        SENATE_KB_ID
    )
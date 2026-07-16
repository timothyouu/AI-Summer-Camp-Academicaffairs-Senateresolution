import boto3
from config import MODEL_ID, REGION

client = boto3.client(
    "bedrock-runtime",
    region_name=REGION,
)


def ask_claude(question: str, context: str) -> str:

    response = client.converse(
        modelId=MODEL_ID,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "text": f"""
You are a Policy Intelligence Assistant for a university.

Your job is to help employees and policy reviewers understand existing policies.

Policy Information:
{context}

Question:
{question}

Follow these rules:

1. Only provide information supported by official policy documents.
2. Never invent policy names, sections, or requirements.
3. If sources conflict, clearly identify the conflict.
4. Explain which office or person should be consulted.
5. Provide a concise answer.
6. Mention what source document should be checked.
"""
                    }
                ]
            }
        ]
    )

    answer = response["output"]["message"]["content"][0]["text"]

    return answer

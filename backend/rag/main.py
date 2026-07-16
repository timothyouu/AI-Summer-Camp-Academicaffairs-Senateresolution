import boto3
from config import MODEL_ID, REGION

client = boto3.client(
    "bedrock-runtime",
    region_name=REGION,
)

response = client.converse(
    modelId=MODEL_ID,
    messages=[
        {
            "role": "user",
            "content": [
                {
                    "text": "You are a university policy assistant. Explain what your role is and how you help faculty and staff find policies."
                }
            ]
        }
    ]
)

answer = response["output"]["message"]["content"][0]["text"]

print(answer)

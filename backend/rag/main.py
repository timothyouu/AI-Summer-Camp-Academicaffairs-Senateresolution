import boto3

client = boto3.client(
    "bedrock-runtime",
    region_name="us-west-2"
)

response = client.converse(
    modelId="us.anthropic.claude-sonnet-4-5-20250929-v1:0",
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
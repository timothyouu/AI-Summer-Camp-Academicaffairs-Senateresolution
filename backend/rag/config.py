import os


REGION = os.getenv("AWS_REGION", "us-west-2")
MODEL_ID = os.getenv(
    "BEDROCK_MODEL_ID",
    "us.anthropic.claude-sonnet-4-5-20250929-v1:0",
)
ACADEMIC_KB_ID = os.getenv("ACADEMIC_KB_ID", "HHFJ4IDG9M")
SENATE_KB_ID = os.getenv("SENATE_KB_ID", "87GR7ILJEF")
BEDROCK_GUARDRAIL_ID = os.getenv("BEDROCK_GUARDRAIL_ID") or None
BEDROCK_GUARDRAIL_VERSION = os.getenv("BEDROCK_GUARDRAIL_VERSION", "1")

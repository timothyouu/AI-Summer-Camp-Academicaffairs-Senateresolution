# config.py
# AWS Bedrock configuration for CSUB Policy Intelligence Assistant


# Claude model running on Amazon Bedrock
MODEL_ID = "us.anthropic.claude-sonnet-4-5-20250929-v1:0"


# Knowledge Base IDs
# Replace these with your actual Bedrock Knowledge Base IDs

ACADEMIC_KB_ID = "HHFJ4IDG9M"

SENATE_KB_ID = "87GR7ILJEF"


# Bedrock Guardrail (optional for now)
# Replace after you connect your guardrail

GUARDRAIL_ID = "YOUR_GUARDRAIL_ID"

GUARDRAIL_VERSION = "1"
#!/usr/bin/env python3
"""CDK app entrypoint for the Policy Intelligence Assistant AWS stack.

Deploy order and post-deploy steps live in infra/README.md. This file only
wires up the App and the single stack; all resources are defined in
infra/stacks/policy_intelligence_stack.py.
"""
from __future__ import annotations

import os

import aws_cdk as cdk

from stacks.policy_intelligence_stack import PolicyIntelligenceStack

app = cdk.App()

# Region defaults to us-west-2 per LOOP.md / implementation2.md §5 (Bedrock +
# OpenSearch Serverless availability). Override with CDK_DEFAULT_REGION or
# AWS_REGION in the shell before `cdk deploy` if a different region is needed.
region = os.getenv("CDK_DEFAULT_REGION") or os.getenv("AWS_REGION") or "us-west-2"
account = os.getenv("CDK_DEFAULT_ACCOUNT")

PolicyIntelligenceStack(
    app,
    "PolicyIntelligenceStack",
    env=cdk.Environment(account=account, region=region),
    description="Policy Intelligence Assistant — S3 corpus, Bedrock KB + OpenSearch "
    "Serverless, DynamoDB, Cognito, API Gateway + Lambda (implementation2.md §2).",
)

app.synth()

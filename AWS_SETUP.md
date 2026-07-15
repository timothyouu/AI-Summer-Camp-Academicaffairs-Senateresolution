# AWS_SETUP.md — connecting the real AWS services

Everything on branch `prod` runs locally today with zero AWS. This file is the
complete, ordered list of manual steps that turn on the real architecture from
`implementation2.md`. Nothing else is required — no code changes.

## 0. One-time installs (hook-blocked for Claude; run these yourself)

```bash
# Backend deps (into the project venv)
backend/.venv/bin/pip install boto3 mangum strands-agents

# IaC toolchain
backend/.venv/bin/pip install -r infra/requirements.txt   # aws-cdk-lib + constructs
npm install -g aws-cdk                                     # cdk CLI
```

`aws-amplify` / `@aws-amplify/ui-react` are NOT needed — the frontend uses the
Cognito Hosted UI redirect (PKCE) flow with zero new npm packages.

## 1. Credentials

```bash
aws configure          # access key, secret, region us-west-2
aws sts get-caller-identity   # sanity check
```

Verify Bedrock model access in the console (us-west-2): Titan Text Embeddings V2
and the Claude model used by `backend/app/llm.py`.

## 2. Deploy the stack

```bash
cd infra
cdk bootstrap
cdk deploy
```

Full detail (including Lambda dependency bundling before a real deploy, and the
OpenSearch Serverless custom-resource notes) is in `infra/README.md`.

## 3. Post-deploy (from `infra/README.md`, summarized)

1. Upload the corpus to the S3 bucket under `handbook/`, `cba/`, `resolutions/`,
   `synthetic/` prefixes.
2. Run the initial Knowledge Base sync once:
   `aws bedrock-agent start-ingestion-job --knowledge-base-id <BedrockKbId> --data-source-id <BedrockDataSourceId>`
   (later uploads auto-sync via the S3-event ingestion Lambda).
3. Create the two demo Cognito users and add them to the `makers` / `employees`
   groups (exact `aws cognito-idp` commands in `infra/README.md`).
4. Console-test retrieval: KB `retrieve` for "service credit tenure clock".

## 4. Backend env vars (the "drop the key" moment)

Each variable independently flips one integration from local to AWS; unset ones
keep the local path. Values come from the `cdk deploy` stack outputs
(mapping table in `infra/README.md`). Locally, put them in `backend/.env`
(template: `backend/.env.example`); on Lambda they are already set by the stack.

| Env var | Turns on |
|---|---|
| `AWS_REGION` | region for all AWS clients |
| `BEDROCK_KB_ID` | Bedrock KB retrieval (replaces NumPy index) + Strands mode (if `strands` installed) |
| `DDB_CONFLICTS_TABLE` | DynamoDB conflict log (replaces SQLite) |
| `DDB_UPLOADS_TABLE` | DynamoDB upload registry (replaces SQLite) |
| `CORPUS_BUCKET` | presigned S3 PUT uploads + event-driven ingestion |
| `COGNITO_USER_POOL_ID` + `COGNITO_CLIENT_ID` | Cognito JWT auth, roles from `cognito:groups` (replaces demo accounts) |

## 5. Frontend env vars

Template: `frontend/.env.example`. Set `VITE_API_BASE_URL` to the `ApiUrl`
output; set `VITE_AGENT_BASE_URL` to the `AgentFunctionUrl` output (see the
note below); for real sign-in set `VITE_USE_COGNITO=true` plus
`VITE_COGNITO_DOMAIN`, `VITE_COGNITO_CLIENT_ID`, `VITE_REDIRECT_URI`
(hosted UI values from the stack outputs). Unset ⇒ demo login unchanged.

`VITE_AGENT_BASE_URL` (Lambda Function URL from the `AgentFunctionUrl` output)
is where the two long-running agent endpoints — `POST /api/chat` and
`POST /api/check-resolution` — are sent. API Gateway HTTP API has a hard ~29s
integration cap, and the retrieval + multi-agent Bedrock pipeline can exceed
it; the Function URL allows up to the 15-min Lambda max (the function timeout is
120s). Those two endpoints validate the Cognito JWT in-app (the Function URL
uses `auth_type=NONE`, so it bypasses the gateway authorizer), so they stay
authenticated. If `VITE_AGENT_BASE_URL` is unset, both calls fall back to
`VITE_API_BASE_URL` — fine locally, but under a real HTTP API a slow pipeline
would 5xx at ~29s, so set it for the AWS demo.

Hosting: connect the repo (`prod` branch, `frontend/` app root) to Amplify
Hosting and set the same env vars in the Amplify console.

## 6. Verify end-to-end

1. `backend`: run the API locally with the env vars set — ask the service-credit
   question; expect KB-backed citations.
2. Upload a small PDF via the UI — status should go pending → ingesting → ready,
   then answer a question from it.
3. Sign in via the hosted UI as each demo user — employee vs reviewer routing
   should follow the Cognito group.

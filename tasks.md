# Shipping Tasks — Policy Intelligence Assistant

Deployment punch-list from the 2026-07-16 repo audit. The code is ship-ready:
152 backend tests pass, tsc + vite build clean, `main`/`prod` in sync, and all
backend/AWS service wiring is complete in the CDK stack (S3 → ingestion Lambda →
Bedrock KB sync; all env vars injected into the Lambdas from stack resources).
Everything below is deployment/environment work, not code work. Ordered by
dependency; details in `AWS_SETUP.md`.

## 1. Install missing backend + infra Python deps (Tim runs — hook-blocked)

boto3, mangum, strands-agents are in `backend/requirements.txt` but missing from
`backend/.venv`; aws-cdk-lib is missing for infra.

```bash
backend/.venv/bin/pip install -r backend/requirements.txt
backend/.venv/bin/pip install -r infra/requirements.txt
```

## 2. Install Docker + configure AWS credentials (Tim runs)

Docker is required for `cdk synth`/`cdk deploy` (not installed on this WSL).
Then:

```bash
aws configure                  # access key, secret, region us-west-2
aws sts get-caller-identity    # sanity check
```

Verify Bedrock model access in the console (us-west-2): Titan Text Embeddings V2
and the Claude generation model.

## 3. cdk bootstrap + cdk deploy PolicyIntelligenceStack

From `infra/` with the venv active. Creates all 7 DynamoDB tables, S3 corpus
bucket, Bedrock KB + Guardrail, OpenSearch Serverless, 3 Lambdas, API Gateway,
Function URL, Cognito. Blocked by tasks 1 and 2. Lambda dependency bundling
notes in `infra/README.md`.

## 4. Upload corpus to S3 + run initial KB ingestion job

Run `infra/scripts/prepare_corpus.py` (validate first, then with
`--bucket $CORPUS_BUCKET` from the stack output). Do NOT raw
`aws s3 cp --recursive` — files must land under the `handbook/`, `cba/`,
`resolutions/`, `synthetic/` prefixes with `.metadata.json` sidecars. Then:

```bash
aws bedrock-agent start-ingestion-job \
  --knowledge-base-id <BedrockKbId> --data-source-id <BedrockDataSourceId>
```

The real PDFs (`CSUB University_Handbook_2025.pdf`, `Unit 3 CBA 2022-2026.pdf`)
are already in `data/corpus/` and declared in `CORPUS_SOURCES` — no prep needed.

## 5. Seed the DynamoDB conflict log via the env-driven store

```bash
export AWS_REGION=us-west-2
export DDB_CONFLICTS_TABLE=<DdbConflictsTable stack output>
backend/.venv/bin/python -m backend.scripts.seed_conflicts
```

(AWS_SETUP.md §3.3, from the repo root.)

## 6. Invoke the catalog scraper Lambda (current + one archived edition) + re-ingest

Find the `CatalogScraperFn` name via `aws lambda list-functions`, invoke for
`catalog.csub.edu` 2026 `is_current=true` and `archivedcatalogs/2024-2025`
`is_current=false`, then run one more `start-ingestion-job` (AWS_SETUP.md §7).
The local zero-AWS smoke test already passed 2026-07-15.

## 7. Wire the frontend: Amplify Hosting + VITE_* env vars + SPA rewrite

Connect the `prod` branch to Amplify Hosting (`amplify.yml` exists,
`appRoot: frontend`). Set `AMPLIFY_MONOREPO_APP_ROOT=frontend`,
`VITE_API_BASE_URL` = `ApiUrl` output, `VITE_AGENT_BASE_URL` =
`AgentFunctionUrl` output (required — chat/check-resolution 5xx at ~29s via API
Gateway without it). Add the `/<*>` → `/index.html` `200 (Rewrite)` rule.
Cognito `VITE_*` vars stay unset — demo login stays on (locked decision).

## 8. Redeploy with frontendOrigin for CORS, then verify end-to-end

Once the Amplify URL is known:

```bash
cd infra && cdk deploy -c frontendOrigin=https://main.dXXXX.amplifyapp.com
```

(exact scheme + host, no trailing slash) so Cognito and both API CORS policies
register it. Then AWS_SETUP.md §6: the service-credit question returns
KB-backed citations; a PDF upload goes pending → ingesting → ready and is
answerable; role routing works via demo login.

## 9. Update the stale CLAUDE.md constraint about the missing handbook PDF

CLAUDE.md Active Constraints says "Handbook PDF not yet in `data/corpus/`" —
both real PDFs were added 2026-07-16 and are declared in `prepare_corpus.py`.
Mark the entry as updated per the maintenance rule (don't delete). Also becomes
stale once task 2 lands: "No AWS credentials on this WSL machine."

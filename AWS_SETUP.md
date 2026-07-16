# AWS_SETUP.md — connecting the real AWS services

Everything on branch `prod` runs locally today with zero AWS. This file is the
complete, ordered list of manual steps that turn on the real architecture from
`implementation2.md`. Nothing else is required — no code changes.

## 0. One-time installs (hook-blocked for Claude; run these yourself)

```bash
# Backend runtime (the virtualenv is intentionally not committed)
python3 -m venv backend/.venv
backend/.venv/bin/pip install -r backend/requirements.txt

# IaC toolchain
backend/.venv/bin/pip install -r infra/requirements.txt   # aws-cdk-lib + constructs
npm install -g aws-cdk                                     # cdk CLI

# Frontend dependencies for local verification (Amplify installs these during its build)
cd frontend && npm ci && cd ..
```

`aws-amplify` / `@aws-amplify/ui-react` are NOT needed — the frontend uses the
Cognito Hosted UI redirect (PKCE) flow with zero new npm packages.

## 1. Credentials

```bash
aws configure          # access key, secret, region us-west-2
aws sts get-caller-identity   # sanity check
```

Verify Bedrock model access in the console (us-west-2): Titan Text Embeddings V2
and whichever Bedrock model the Strands Agent is configured to use (or selects
by default). The production model ID remains an explicit deployment choice.

## 2. Deploy the stack

`cdk deploy` below creates every DynamoDB table itself, so the scripts are not a
prerequisite for it. Use them when you want to provision or health-check
DynamoDB **on its own** — standing up the full stack also creates an OpenSearch
Serverless collection and a Bedrock Knowledge Base, which is slow and costly to
spin up just to exercise persistence:

```bash
./scripts/setup_dynamodb_tables.sh    # idempotent; never deletes a table
./scripts/verify_dynamodb_tables.sh   # ACTIVE + write/delete healthcheck + GSIs
```

If setup reports a key-schema mismatch, that table is left over from the
app-memory round and the backend cannot read it — the script prints the scan and
delete commands rather than changing anything itself. See the integration note in
`Yaza_DynamoDB_Work_Summary.md`.

```bash
source backend/.venv/bin/activate
cd infra
cdk bootstrap
cdk deploy
```

Full detail (including Lambda dependency bundling before a real deploy, and the
OpenSearch Serverless custom-resource notes) is in `infra/README.md`.

## 3. Post-deploy (from `infra/README.md`, summarized)

1. From the repository root, validate the explicit source mapping, then upload
   the corpus and generated Bedrock metadata sidecars under the KB's included
   prefixes. Do not use a raw `aws s3 cp data/corpus ... --recursive`: most
   supplied files are flat, so that command puts them outside the configured
   `handbook/`, `cba/`, `resolutions/`, and `synthetic/` prefixes.

   ```bash
   backend/.venv/bin/python infra/scripts/prepare_corpus.py
   export CORPUS_BUCKET="$(aws cloudformation describe-stacks \
     --stack-name PolicyIntelligenceStack \
     --query "Stacks[0].Outputs[?OutputKey=='CorpusBucketName'].OutputValue | [0]" \
     --output text)"
   backend/.venv/bin/python infra/scripts/prepare_corpus.py --bucket "$CORPUS_BUCKET"
   ```

   The helper refuses undeclared or missing corpus files, preserves each
   source's document type in metadata, and generates the `.metadata.json`
   sidecar fields consumed by retrieval: `source`, `section`, `doc_type`, and
   `topic`.
2. Run the initial Knowledge Base sync once:
   `aws bedrock-agent start-ingestion-job --knowledge-base-id <BedrockKbId> --data-source-id <BedrockDataSourceId>`
   (later uploads auto-sync via the S3-event ingestion Lambda).
3. Seed the DynamoDB conflict log through the same env-driven store used by the
   API. Run this from the repository root after `cdk deploy`:

   ```bash
   export AWS_REGION=us-west-2
   export DDB_CONFLICTS_TABLE="$(aws cloudformation describe-stacks \
     --stack-name PolicyIntelligenceStack \
     --query "Stacks[0].Outputs[?OutputKey=='DdbConflictsTable'].OutputValue | [0]" \
     --output text)"
   backend/.venv/bin/python -m backend.scripts.seed_conflicts
   ```

4. Create the two demo Cognito users and add them to the `makers` / `employees`
   groups (exact `aws cognito-idp` commands in `infra/README.md`).
5. Console-test retrieval: KB `retrieve` for "service credit tenure clock".

## 4. Backend env vars (the "drop the key" moment)

Each variable independently flips one integration from local to AWS; unset ones
keep the local path. Values come from the `cdk deploy` stack outputs
(mapping table in `infra/README.md`). On Lambda they are already set by the
stack. For local AWS-mode testing, copy `backend/.env.example` to
`backend/.env`, fill it in, then explicitly load it before starting the API:

```bash
set -a
source backend/.env
set +a
backend/.venv/bin/uvicorn backend.app.main:app --reload
```

The backend intentionally does not auto-load `.env`, so merely creating that
file without exporting it does not change modes.

| Env var | Turns on |
|---|---|
| `AWS_REGION` | region for all AWS clients |
| `BEDROCK_KB_ID` | Bedrock KB retrieval (replaces NumPy index) + Strands mode (if `strands` installed) |
| `BEDROCK_GUARDRAIL_ID` | Bedrock Guardrails for Strands generation |
| `BEDROCK_GUARDRAIL_VERSION` | pinned Bedrock Guardrail version used by Strands generation |
| `DDB_CONFLICTS_TABLE` | DynamoDB conflict log (replaces SQLite) |
| `DDB_UPLOADS_TABLE` | DynamoDB upload registry (replaces SQLite) |
| `DDB_REGISTRY_TABLE` | DynamoDB source registry (replaces SQLite) |
| `DDB_PERMISSIONS_TABLE` | DynamoDB per-user, per-source-type permissions (replaces SQLite) |
| `DDB_DRAFTS_TABLE` | DynamoDB versioned drafting history (replaces SQLite) |
| `CORPUS_BUCKET` | presigned S3 PUT uploads + event-driven ingestion |
| `COGNITO_USER_POOL_ID` + `COGNITO_CLIENT_ID` | Cognito JWT auth, roles from `cognito:groups` (replaces demo accounts) |
| `FRONTEND_ORIGINS` | comma-separated CORS origins for the FastAPI app itself. Local-only: deployed CORS comes from `cdk deploy -c frontendOrigin=...` (API Gateway + Function URL). Unset ⇒ the default localhost dev origins. |

For the demo, Cognito remains optional and OFF. With Cognito unset, conflict
visibility uses the frontend's demo `X-Role` header (and defaults to reviewer
for header-less compatibility). Cognito claims become authoritative only after
the backend `COGNITO_*` variables and frontend `VITE_USE_COGNITO=true` are set.

## 5. Frontend env vars

Template: `frontend/.env.example`. Set `VITE_API_BASE_URL` to the `ApiUrl`
output; set `VITE_AGENT_BASE_URL` to the `AgentFunctionUrl` output (see the
note below); for real sign-in set `VITE_USE_COGNITO=true` plus
`VITE_COGNITO_DOMAIN`, `VITE_COGNITO_CLIENT_ID`, `VITE_REDIRECT_URI`
(hosted UI values from the stack outputs). Unset ⇒ demo login unchanged.

Map `CognitoHostedUiUrl` to `VITE_COGNITO_DOMAIN`, `CognitoClientId` to
`VITE_COGNITO_CLIENT_ID`, `ApiUrl` to `VITE_API_BASE_URL`, and
`AgentFunctionUrl` to `VITE_AGENT_BASE_URL`.

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

Set `VITE_REDIRECT_URI` to the deployed frontend's exact callback URL, for
example `https://main.dXXXXXXXXXXXX.amplifyapp.com/auth/callback`. Once that
frontend origin is known, register the same origin in Cognito and both API CORS
policies by redeploying from the repository root:

```bash
source backend/.venv/bin/activate
cd infra
cdk deploy -c frontendOrigin=https://main.dXXXXXXXXXXXX.amplifyapp.com
```

Use the exact scheme and host with no trailing slash in `frontendOrigin`.

Hosting: connect the repo's `prod` branch to Amplify Hosting. The root
`amplify.yml` declares a monorepo application with `appRoot: frontend`, runs
`npm ci` / `npm run build`, and publishes `frontend/dist`. In the Amplify app's
environment variables, set `AMPLIFY_MONOREPO_APP_ROOT=frontend` along with the
`VITE_*` values above.

React Router and the Cognito callback require an Amplify SPA rewrite. In
**Hosting > Rewrites and redirects**, add this rule before any 404 rule:

| Source address | Target address | Type |
|---|---|---|
| `/<*>` | `/index.html` | `200 (Rewrite)` |

Without this rule, direct visits to `/auth/callback`, `/reviews`, `/chats`, and
other client routes return a hosting 404 before React can route them.

## 6. Verify end-to-end

1. `backend`: run the API locally with the env vars set — ask the service-credit
   question; expect KB-backed citations.
2. Upload a small PDF via the UI — status should go pending → ingesting → ready,
   then answer a question from it.
3. Sign in via the hosted UI as each demo user — employee vs reviewer routing
   should follow the Cognito group.

## 7. Catalog scrape

The catalog scraper is intentionally manual for the demo. Invoke it once for
the current 2026 catalog and once for exactly one archived edition. It writes
scraped Markdown to the corpus bucket and registers each page with its edition
metadata; archived-edition retrieval results remain eligible but are weighted
at 0.5 relative to current-edition results.

The Lambda's physical name is not a stack output. Find it after deployment:

```bash
export CATALOG_SCRAPER_FUNCTION="$(aws lambda list-functions \
  --query "Functions[?starts_with(FunctionName, 'PolicyIntelligenceStack-CatalogScraperFn')].FunctionName | [0]" \
  --output text)"
```

Invoke the current edition:

```bash
aws lambda invoke --function-name "$CATALOG_SCRAPER_FUNCTION" \
  --payload '{"url": "https://catalog.csub.edu/", "year": 2026, "is_current": true}' \
  --cli-binary-format raw-in-base64-out response-current.json
```

Then invoke the selected 2024–2025 archived edition without marking it current:

```bash
aws lambda invoke --function-name "$CATALOG_SCRAPER_FUNCTION" \
  --payload '{"url": "https://catalog.csub.edu/archivedcatalogs/2024-2025/", "year": 2024, "is_current": false}' \
  --cli-binary-format raw-in-base64-out response-archived.json
```

The scraper writes both the Markdown and Bedrock metadata sidecars under the
included `raw/` prefix. Start one Knowledge Base ingestion job after both
invocations so the new catalog pages become retrievable:

```bash
aws bedrock-agent start-ingestion-job \
  --knowledge-base-id <BedrockKbId> \
  --data-source-id <BedrockDataSourceId>
```

Local zero-AWS equivalents, run from the repository root:

```bash
cd backend
.venv/bin/python -m scripts.scrape_catalog \
  --url https://catalog.csub.edu/ --year 2026 --current --max-pages 15
.venv/bin/python -m scripts.scrape_catalog \
  --url https://catalog.csub.edu/archivedcatalogs/2024-2025/ --year 2024 --max-pages 15
cd ..
```

The local live network smoke test passed on 2026-07-15 using isolated data
roots: the current edition scraped 15 pages into 89 chunks, and the 2024–2025
archive scraped 15 pages into 83 chunks. Registry checks confirmed active,
current metadata for 2026 and active, non-current metadata for 2024. Repeat the
Lambda invocations after deployment to validate the AWS path.

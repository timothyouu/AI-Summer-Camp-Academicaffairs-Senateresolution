# infra/ — AWS CDK (Python) for the Policy Intelligence Assistant

One CDK stack (`PolicyIntelligenceStack`, defined in
`infra/stacks/policy_intelligence_stack.py`) implementing the target
architecture in `docs/archive/implementation2.md` §2 / §3 Phase A: S3 corpus bucket,
Bedrock Knowledge Base on an OpenSearch Serverless vector collection,
DynamoDB tables, Cognito, and an API Gateway HTTP API + Lambda.

See also `../AWS_SETUP.md` (ordered deploy runbook for this stack) and
`../implementation-aws.md` (AWS account/access onboarding, IAM setup).

The stack creates `ConflictLog` and `Uploads` directly. It imports five retained
application-memory tables by name—feedback, recurring questions, access
control, source registry, and draft versions—so Yaza's already provisioned data
is not replaced. Run `../scripts/setup_dynamodb_tables.sh` before using those
routes in AWS; the script is idempotent.

This file was written and verified with `python3 -m py_compile` only —
**`cdk synth`/`cdk deploy` have not been run**, because `aws-cdk-lib` is not
installed in this dev environment and installs are hook-blocked. Construct
and property names were cross-checked against AWS's CDK v2 Python API docs
and reference implementations (links below); treat the first real `cdk
synth` as the actual verification step.

## Lambda packaging — different asset roots, on purpose

`infra/` only owns `infra/`; the Lambda handlers it packages
(`backend/app/lambda_entry.py`, `backend/lambda_handlers/ingestion.py`,
`backend/lambda_handlers/catalog_scraper.py`) are backend code owned
elsewhere in this worktree — `catalog_scraper.py` in particular is Task 6's
handler and may not exist yet in a given checkout (`CatalogScraperFn`'s
asset will fail to bundle until it does; that is expected, not a bug in
this stack). They use different import styles, so the stack gives them
different `Code.from_asset` roots — get this wrong and `cdk deploy` will
succeed but the Lambda will 500 on cold start with an `ImportError`:

- **API Lambda** (`ApiFn`) — `lambda_entry.py` does a *relative* import
  (`from .main import app`), so the asset root is `backend/` itself
  (`app` ends up top-level in the zip) and the handler string is
  `app.lambda_entry.handler`. This is the **only** Lambda that serves API
  Gateway routes — it also serves the two long-running agent endpoints via
  a Function URL (see "Agent endpoints and the 29s cap" below), so there is
  no separate "agent Lambda" in this stack; PRD Round-2 env vars/grants are
  wired onto this one function.
- **Ingestion Lambda** (`IngestionFn`) — `ingestion.py` does an *absolute*
  import (`from backend.app.config import get_settings`), so the asset root
  is the **repo root** (with an exclude list keeping frontend/node_modules,
  `.git`, and local demo data out of the zip) and the handler string is
  `backend.lambda_handlers.ingestion.handler`.
- **Catalog scraper Lambda** (`CatalogScraperFn`) — packages `backend/` as
  its asset root, with handler `lambda_handlers.catalog_scraper.handler`, so
  its `app.catalog` import and shared backend dependencies resolve in Lambda.
  No S3/EventBridge trigger — invoke it manually per catalog edition (see
  "Catalog scraper — manual invoke payloads" below).

Env var names on the API and ingestion Lambdas are pinned to exactly what
`backend/app/config.py`'s `get_settings()` reads: `BEDROCK_KB_ID`,
`DDB_CONFLICTS_TABLE`, `DDB_UPLOADS_TABLE`, `DDB_REGISTRY_TABLE`,
`DDB_PERMISSIONS_TABLE`, `DDB_DRAFTS_TABLE`, `CORPUS_BUCKET`,
`COGNITO_USER_POOL_ID`, `COGNITO_CLIENT_ID` (the ingestion and catalog
scraper Lambdas only set the subset they actually use). `AWS_REGION` is
deliberately **not** set — it's a reserved Lambda runtime env var and
CloudFormation rejects stacks that try to set it explicitly; `boto3` picks
it up automatically from the runtime. `ingestion.py` also doesn't read a
`BEDROCK_DATA_SOURCE_ID` env var — it looks the data source id up at
runtime via `list_data_sources()` — so that value is only exposed as a
stack output (`BedrockDataSourceId`), for the manual `start-ingestion-job`
CLI command in "Post-deploy steps" below.

## Packaging note (dependency bundling — wired into the stack, Docker required)

Both `Code.from_asset(...)` calls now use `BundlingOptions` with the
runtime's official build image (`Runtime.PYTHON_3_12.bundling_image`), so
**`cdk synth`/`cdk deploy` require a running Docker daemon** — CDK spins up
the build container, pip-installs into `/asset-output`, copies the source
on top, and zips the result. No manual bundling step remains:

- **`ApiFn`** installs `backend/requirements.txt` with dev/server-only
  lines stripped (`pytest`, `uvicorn`, `httpx` — not needed inside Lambda,
  and `strands-agents`+`numpy` already push the zip toward the 250 MB
  unzipped limit; if a deploy ever hits that limit, move deps to a layer
  or switch to a container-image Lambda).
- **`IngestionFn`** installs only `pydantic>=2.8,<3` (its import chain —
  config → stores → models — reaches nothing else beyond the stdlib;
  `boto3` is imported lazily and ships in the Lambda runtime).
- **`CatalogScraperFn`** installs only `pydantic>=2.8,<3`, same reasoning as
  `IngestionFn`. Per docs/archive/implementation3.md Task 6, the scraper itself is
  stdlib-only (`urllib`/`html.parser`, no `requests`/`beautifulsoup4`), so
  nothing scraper-specific needs bundling.

On WSL2, make sure Docker Desktop (or a native dockerd) is running before
`cdk synth`. The first synth is slow (image pull + pip install); later
synths hit the CDK asset cache unless backend source or requirements
change.

## CORS and Cognito redirects: pass the frontend origin at deploy time

One CDK context value, `frontendOrigin`, drives two things that both need
the deployed frontend's exact URL:

1. **API CORS.** API Gateway HTTP APIs treat every CORS `allow_origins`
   entry as a **literal string** — a wildcard like
   `https://*.amplifyapp.com` never matches anything, so it is not used
   here. The stack always allows the two localhost dev origins
   (`http://localhost:5173`, `:5174`) and adds `frontendOrigin` when set.
2. **Cognito app client redirect URLs.** Cognito requires an exact match
   on `redirect_uri`. The frontend's PKCE flow
   (`frontend/src/auth/cognito.ts`) sends `VITE_REDIRECT_URI`, which
   `frontend/.env.example` documents as
   `http://localhost:5173/auth/callback` — so the stack registers
   `<origin>/auth/callback` as a callback URL and `<origin>/` as a logout
   URL for every allowed origin (both localhost ports, plus
   `frontendOrigin` when set). When deploying the frontend, set its
   `VITE_REDIRECT_URI` to `<frontendOrigin>/auth/callback` so the two
   sides keep matching.

Once the Amplify (or other hosting) URL exists, deploy with:

```bash
cdk deploy -c frontendOrigin=https://main.dXXXXXXXXXXXX.amplifyapp.com
```

Pass the exact scheme+host (no trailing slash, no path). Every later
`cdk deploy` must repeat the `-c frontendOrigin=...` flag, or the origin
drops back out of both the CORS allowlist and the Cognito redirect list —
to make it sticky, add `"frontendOrigin": "https://..."` to the `context`
block of `infra/cdk.json` instead.

## Deploy — exact ordered commands

Start from the repository root. Assumes Tim has already run `aws configure`
(or `aws sso login`) with an account that has Bedrock model access and
OpenSearch Serverless enabled in the target region, and that **Docker is
running** (required for Lambda dependency bundling — see the packaging
note above).

```bash
# 1. Activate the project virtualenv and install CDK's Python libraries.
#    AWS_SETUP.md creates this uncommitted virtualenv on a fresh checkout.
source backend/.venv/bin/activate
pip install -r infra/requirements.txt

# 2. Node CDK CLI, if not already installed globally
npm install -g aws-cdk

# 3. One-time per account/region (the remaining commands run from infra/)
cd infra
export AWS_REGION=us-west-2   # or wherever Bedrock + OpenSearch Serverless are enabled
cdk bootstrap aws://ACCOUNT_ID/us-west-2

# 4. Sanity-check the synthesized template before deploying
#    (needs Docker up — this step pip-installs the Lambda deps in a container)
cdk synth

# 5. Deploy. Add -c frontendOrigin=... once the hosted frontend URL exists
#    (see "CORS and Cognito redirects: pass the frontend origin at deploy time" above); without it only the
#    localhost dev origins are CORS-allowed.
cdk deploy
# later, with the real frontend URL:
# cdk deploy -c frontendOrigin=https://main.dXXXXXXXXXXXX.amplifyapp.com
```

`cdk deploy` will prompt to approve IAM policy changes (the KB service role,
Lambda roles, etc.) — approve them.

## Post-deploy steps (not expressible in CDK, or deferred to keep the demo scope tight)

1. **Upload the corpus from the repository root with the preparation helper.**
   The checked-in `data/corpus/` is mostly flat, while the Bedrock data source
   includes only `handbook/`, `cba/`, `resolutions/`, `synthetic/`, and
   `uploads/`. A raw recursive copy to the bucket root will therefore not be
   ingested. Use the explicit, fail-closed mapping instead:

   ```bash
   backend/.venv/bin/python infra/scripts/prepare_corpus.py
   export CORPUS_BUCKET="$(aws cloudformation describe-stacks \
     --stack-name PolicyIntelligenceStack \
     --query "Stacks[0].Outputs[?OutputKey=='CorpusBucketName'].OutputValue | [0]" \
     --output text)"
   export DDB_REGISTRY_TABLE="$(aws cloudformation describe-stacks \
     --stack-name PolicyIntelligenceStack \
     --query "Stacks[0].Outputs[?OutputKey=='DdbRegistryTable'].OutputValue | [0]" \
     --output text)"
   backend/.venv/bin/python infra/scripts/prepare_corpus.py \
     --bucket "$CORPUS_BUCKET" --registry-table "$DDB_REGISTRY_TABLE"
   ```

   The helper stages every declared source under an included prefix, writes
   a Bedrock `<document>.metadata.json` sidecar with `source`, `section`,
   `doc_type`, and `topic`, and seeds matching active rows in the source
   registry. It refuses to proceed when a checked-in source is missing or a
   new source has not been explicitly classified.
2. **Run the initial KB sync** (ingestion Lambda only fires on *new* uploads
   after the stack exists; the corpus copied in step 1 needs one manual
   sync):
   ```bash
   aws bedrock-agent start-ingestion-job \
     --knowledge-base-id <BedrockKbId> \
     --data-source-id <BedrockDataSourceId>
   ```
   Verify with a console `retrieve` test for "service credit tenure clock"
   per docs/archive/implementation2.md §3 Phase A step 2.
3. **Seed the DynamoDB conflict log.** The seed script is AWS-aware through
   `DDB_CONFLICTS_TABLE`; without this step the deployed table starts empty
   because Lambda startup intentionally does not seed AWS storage:

   ```bash
   export AWS_REGION=us-west-2
   export DDB_CONFLICTS_TABLE="$(aws cloudformation describe-stacks \
     --stack-name PolicyIntelligenceStack \
     --query "Stacks[0].Outputs[?OutputKey=='DdbConflictsTable'].OutputValue | [0]" \
     --output text)"
   backend/.venv/bin/python -m backend.scripts.seed_conflicts
   ```
4. **Create the three demo users** (CloudFormation/CDK cannot set a Cognito
   user's password — `AdminSetUserPassword` is an imperative API call, not a
   declarative resource):
   ```bash
   aws cognito-idp admin-create-user \
     --user-pool-id <CognitoUserPoolId> \
     --username employee@example.edu \
     --user-attributes Name=email,Value=employee@example.edu Name=email_verified,Value=true \
     --message-action SUPPRESS

   aws cognito-idp admin-set-user-password \
     --user-pool-id <CognitoUserPoolId> \
     --username employee@example.edu \
     --password '<ChooseAStrongPassword>' --permanent

   aws cognito-idp admin-add-user-to-group \
     --user-pool-id <CognitoUserPoolId> \
     --username employee@example.edu --group-name employees

   # Repeat for reviewer@example.edu with --group-name makers.
   # Repeat for source-admin@example.edu with --group-name admins. Admins can
   # manage permission grants and bypass per-source add/edit checks.
   ```
5. **Configure Amplify Hosting.** Connect the `prod` branch. The repository's
   root `amplify.yml` selects `appRoot: frontend`, runs `npm ci` and
   `npm run build`, and publishes `dist`. Set
   `AMPLIFY_MONOREPO_APP_ROOT=frontend` in the Amplify environment along with
   the documented `VITE_*` values. Under **Hosting > Rewrites and redirects**,
   add `/<*>` → `/index.html` as `200 (Rewrite)` before any 404 rule. This is
   required for direct React Router routes and Cognito's `/auth/callback`.
6. **Redeploy with the deployed frontend origin** once the frontend is
   hosted (Amplify or otherwise):
   `cdk deploy -c frontendOrigin=https://<frontend-host>` — this registers
   `<origin>/auth/callback` as a Cognito callback URL and adds the origin
   to the API's CORS allowlist in one shot (see "CORS and Cognito
   redirects" above). No console edits needed; localhost dev callbacks
   (`http://localhost:5173/auth/callback`, `:5174`) are registered from the
   first deploy.
7. **Paste stack outputs into the backend's env** (or Lambda console env
   vars if editing directly) — see the Outputs table below for which var
   maps to which output.

## Stack outputs

| CDK output | Backend env var | Notes |
|---|---|---|
| `AwsRegion` | `AWS_REGION` | us-west-2 by default |
| `CorpusBucketName` | `CORPUS_BUCKET` | prefixes: `handbook/`, `cba/`, `resolutions/`, `synthetic/`, `uploads/`, `raw/` |
| `BedrockKbId` | `BEDROCK_KB_ID` | |
| `BedrockDataSourceId` | *(not read by backend)* | not a backend env var — ingestion.py resolves it at runtime via `list_data_sources()`; use this output only for the manual `start-ingestion-job` CLI call in step 2 above |
| `DdbConflictsTable` | `DDB_CONFLICTS_TABLE` | table name is literally `ConflictLog` |
| `DdbUploadsTable` | `DDB_UPLOADS_TABLE` | table name is literally `Uploads` |
| `DdbRegistryTable` | `DDB_REGISTRY_TABLE` | `SourceRegistry` — source catalog (seeds + uploads + scraped entries) |
| `DdbPermissionsTable` | `DDB_PERMISSIONS_TABLE` | `SourcePermissions` — per-user, per-source-type access |
| `DdbDraftsTable` | `DDB_DRAFTS_TABLE` | `DraftVersions` — AI-drafting version history |
| `CognitoUserPoolId` | `COGNITO_USER_POOL_ID` | |
| `CognitoClientId` | `COGNITO_CLIENT_ID` | SPA app client, no secret |
| `CognitoHostedUiUrl` | `VITE_COGNITO_DOMAIN` (frontend) | hosted UI domain for the `VITE_USE_COGNITO` flow (docs/archive/LOOP.md decision 5) |
| `ApiUrl` | `VITE_API_BASE_URL` (frontend) | API Gateway HTTP API invoke URL |
| `AgentFunctionUrl` | `VITE_AGENT_BASE_URL` (frontend) | Lambda Function URL for the two long-running agent endpoints (`POST /api/chat`, `POST /api/check-resolution`) — see note below |

### Agent endpoints and the 29s cap

API Gateway HTTP API has a hard ~29s integration timeout. The chat and
check-resolution endpoints run retrieval plus the multi-agent Bedrock pipeline,
which can exceed it, so the stack adds a **Lambda Function URL on the same API
Lambda** (`_build_agent_function_url`) with `auth_type=NONE` and CORS scoped to
the frontend origins. Function URLs allow up to the 15-min Lambda max, and the
API Lambda's own timeout was raised from 29s to 120s (matching the frontend's
`AGENT_REQUEST_TIMEOUT_MS`) so the function can actually run past 29s. The
frontend sends only those two POSTs to `VITE_AGENT_BASE_URL`; everything else
still flows through the HTTP API and its Cognito JWT authorizer. Because the
Function URL bypasses that authorizer, the two endpoints validate the Cognito
token in-app (`backend/app/auth.py` `require_authenticated` / `require_reviewer`),
so they stay authenticated in AWS mode.

### Catalog scraper — manual invoke payloads

`CatalogScraperFn` has no S3 or EventBridge trigger — invoke it manually
per catalog edition with the AWS CLI (or the console "Test" tab). It writes
scraped pages into `CorpusBucketName` and upserts rows into
`DdbRegistryTable`; per docs/archive/implementation3.md Task 2, archived editions are
down-ranked (`ARCHIVED_EDITION_WEIGHT = 0.5`) relative to the current one.
The scraper writes Bedrock metadata sidecars under the data source's included
`raw/` prefix. After both editions finish, start one Knowledge Base ingestion
job so the pages become available to retrieval:

```bash
aws bedrock-agent start-ingestion-job \
  --knowledge-base-id <BedrockKbId> \
  --data-source-id <BedrockDataSourceId>
```

Current 2026 catalog (`is_current: true`):

```bash
aws lambda invoke --function-name <CatalogScraperFn-name> \
  --payload '{"url": "https://catalog.csub.edu/", "year": 2026, "is_current": true}' \
  --cli-binary-format raw-in-base64-out response.json
```

One archived edition (`is_current: false` — substitute the actual archived
edition root URL, e.g. an older `catalog.csub.edu` snapshot):

```bash
aws lambda invoke --function-name <CatalogScraperFn-name> \
  --payload '{"url": "<archived edition root>", "year": 2024, "is_current": false}' \
  --cli-binary-format raw-in-base64-out response.json
```

The Function name is not currently a stack output (only `CatalogScraperFn`'s
logical id is fixed); find the physical name with:

```bash
aws lambda list-functions --query "Functions[?starts_with(FunctionName, 'PolicyIntelligenceStack-CatalogScraperFn')].FunctionName" --output text
```

Get all outputs after deploy with:

```bash
aws cloudformation describe-stacks --stack-name PolicyIntelligenceStack \
  --query "Stacks[0].Outputs" --output table
```

## What could not be expressed as native CDK/CloudFormation resources

- **The OpenSearch Serverless vector index itself.** CloudFormation has a
  resource for the *collection* (`AWS::OpenSearchServerless::Collection`)
  but not for an *index* inside it — that's a data-plane operation on the
  collection's HTTPS endpoint, not a control-plane API. This stack creates
  it via a custom resource (`infra/lambda_src/vector_index_provider/index.py`)
  that signs a SigV4 request to `PUT https://<endpoint>/<index-name>` using
  only `boto3`/`botocore` (already in the Lambda runtime — no
  `opensearch-py` dependency needed, which matters since installs are
  hook-blocked in this repo). This is the standard community pattern; see
  the Medium writeup and AWS re:Post thread in Verification below.
- **Cognito demo user passwords.** `AWS::Cognito::UserPoolUser` (CFN) /
  `CfnUserPoolUser` (CDK) can create a user, but there's no declarative way
  to set a *permanent* password (`AdminSetUserPassword` is imperative-only).
  Documented as a post-deploy CLI step above instead of a second custom
  resource, to keep the stack's blast radius (and Tim's review surface)
  smaller — this is a two-command follow-up, not worth another Lambda.
- **The deployed frontend's CORS origin.** HTTP API CORS origins are
  literal strings, and the Amplify URL doesn't exist until the frontend is
  hosted — so it can't be hardcoded in the stack. Supplied at deploy time
  via `-c frontendOrigin=...` (see "CORS and Cognito redirects: pass the frontend origin at deploy time" above).

## Teardown

```bash
cd infra
cdk destroy
```

- **OpenSearch Serverless is the costly piece** — it bills for OCUs
  (OpenSearch Compute Units) continuously while the collection exists, even
  idle. Confirm it's gone after `cdk destroy`:
  `aws opensearchserverless list-collections`. If `cdk destroy` fails
  because the custom resource's index delete errored, manually delete the
  collection: `aws opensearchserverless delete-collection --id <id>`.
- The S3 corpus bucket and both DynamoDB tables are `RemovalPolicy.RETAIN`
  (deliberate — don't lose the corpus/conflict log data on a stack
  teardown). Delete them manually if a full account cleanup is wanted:
  `aws s3 rb s3://<CorpusBucketName> --force` and
  `aws dynamodb delete-table --table-name ConflictLog` /
  `Uploads`.
- The Cognito User Pool is also `RETAIN` for the same reason (demo user
  accounts). Delete via `aws cognito-idp delete-user-pool --user-pool-id ...`
  if wanted.
- Everything else (Lambdas, API Gateway, IAM roles, the vector index custom
  resource, log groups minus their 1-week retention tail) is deleted by
  `cdk destroy` normally. This includes the PRD Round-2 tables
  `SourceRegistry`, `SourcePermissions`, and `DraftVersions` — unlike
  `ConflictLog`/`Uploads` above, those three are `RemovalPolicy.DESTROY`
  (net-new demo tables, no production data to protect) and are wiped along
  with the rest of the stack; re-run the catalog scraper post-redeploy if
  the registry needs reseeding.

## Verification sources consulted (Bedrock KB + OpenSearch Serverless CDK patterns)

- AWS CDK Python API docs: `aws_cdk.aws_bedrock.CfnKnowledgeBase`,
  `CfnDataSource`, `aws_cdk.aws_opensearchserverless` (CfnCollection,
  CfnSecurityPolicy, CfnAccessPolicy) — confirmed property names
  (`embedding_model_arn`, `storage_configuration`,
  `opensearch_serverless_configuration`, `field_mapping`,
  `vector_ingestion_configuration.chunking_configuration.fixed_size_chunking_configuration`,
  `attr_collection_endpoint`, `attr_arn`).
- "Building a Knowledge Base with AWS CDK and OpenSearch Serverless" (Medium,
  Vipul Munot) and the AWS re:Post thread "How to deploy a Bedrock
  KnowledgeBase (using OpenSearch serverless) with CDK?" — confirmed the
  encryption/network/access-policy-then-collection-then-custom-resource-index
  ordering, and that a custom resource is the standard way to create the
  vector index.
- "Bedrock Knowledge Base with S3 Vector Index in AWS CDK" (codiply) —
  confirmed `CfnDataSource` chunking configuration shape and
  `VectorKnowledgeBaseConfigurationProperty(embedding_model_arn=...)`
  is top-level, not nested only under `embedding_model_configuration`.
- `aws-cdk-lib.aws_apigatewayv2_authorizers` docs / bobbyhadz walkthrough —
  confirmed `HttpUserPoolAuthorizer` + `HttpLambdaIntegration` are in the
  stable (non-alpha) `aws-cdk-lib` package as of the pinned version range.
- CDK asset-bundling docs + community examples — confirmed the
  `Code.from_asset(path, bundling=BundlingOptions(image=Runtime.PYTHON_3_12
  .bundling_image, command=["bash","-c","pip install -r requirements.txt
  -t /asset-output && cp -au . /asset-output"]))` pattern (core
  `aws_cdk.BundlingOptions`, container reads `/asset-input` cwd, writes
  `/asset-output`).

- `aws_cdk.aws_lambda.FunctionUrl` / `FunctionUrlCorsOptions` docs — confirmed
  `Function.add_function_url(auth_type=FunctionUrlAuthType.NONE, cors=...)`
  and the `FunctionUrlCorsOptions(allowed_origins, allowed_methods=[HttpMethod
  .POST], allowed_headers, allow_credentials, max_age)` shape are in stable
  `aws-cdk-lib.aws_lambda`; `.url` is the resulting invoke URL.

None of this was confirmed by an actual `cdk synth` — see the top of this
file. Run `cdk synth` yourself as the first real check once dependencies are
installed.

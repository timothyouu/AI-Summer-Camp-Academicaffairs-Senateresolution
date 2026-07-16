# AWS Setup Guide — Policy Intelligence Assistant

Companion to `implementation.md` (local demo) and `implementation2.md` (AWS migration plan, Phases A–D). This doc is the one-stop reference for **every teammate** to get access to the shared AWS account and stand up their own copy of, or contribute to, the services in the target architecture: S3, Bedrock (models + Knowledge Bases + Guardrails), OpenSearch Serverless, DynamoDB, Cognito, Lambda, API Gateway, Amplify, EventBridge, and the IAM permissions tying them together.

**Honesty check before you read further:** `aws sts get-caller-identity` still fails with `NoCredentials` on Tim's machine — there are no credentials configured here, and nothing in this doc has been verified live from this repo. That part hasn't changed. What has changed: as of 2026-07-16, Alyssa's `feature/rag` branch (merged into `prod` as `backend/rag/`, see its README) carries two real-looking Knowledge Base IDs — `HHFJ4IDG9M` (academic) and `87GR7ILJEF` (senate), both `us-west-2` — plus the exact Claude model id §3 recommends (`us.anthropic.claude-sonnet-4-5-20250929-v1:0`) hardcoded as a working default. That's evidence someone on the team has at least partly completed §3 (model access) and §4 (KB creation) on the shared account. It is **not** confirmation from Tim's machine — no credentials here means no way to run the verify commands below and check. Treat those two IDs as "probably real, provisioned by Alyssa," not "confirmed live." Every ARN, account ID, and resource name elsewhere in this doc that isn't one of those two IDs is still a `<placeholder>` — do not copy-paste anything else here expecting it to resolve. This is the guide for going from zero to working, together.

**Region decision: `us-west-2` for everything.** Every resource in this doc — S3 buckets, Bedrock model access, Knowledge Bases, OpenSearch Serverless collections, DynamoDB tables, Cognito user pool, Lambda, API Gateway, Amplify backend, Guardrails, EventBridge rules — goes in `us-west-2`. Bedrock foundation-model access and Knowledge Bases are region-scoped; mixing regions is the single most common cause of "it worked in the console but my CLI call fails."

---

## Quickstart checklist (do this first, every teammate)

1. Get account access from Tim (IAM Identity Center invite — see [Section 1](#0-getting-access-to-the-shared-account)).
2. Configure credentials: `aws configure sso` (Identity Center) and select your permission set.
3. Set your default region: confirm `~/.aws/config` has `region = us-west-2` for the profile you'll use.
4. Verify identity:
   ```
   aws sts get-caller-identity --profile <your-profile>
   ```
   Expect a JSON blob with your `Arn` ending in your username — not an error.
5. Verify Bedrock model access (only works once someone has completed [Section 3](#3-bedrock-foundation-model-access)) — `list-foundation-models` only proves you can reach Bedrock and see the catalog, it lists every model regardless of whether your account has been granted access, so the real access test is an actual `invoke-model` call:
   ```
   aws bedrock-runtime invoke-model \
     --region us-west-2 \
     --model-id amazon.titan-embed-text-v2:0 \
     --body '{"inputText":"quickstart check"}' \
     --cli-binary-format raw-in-base64-out \
     /tmp/quickstart-embed.json \
     --profile <your-profile>
   ```
   A populated `/tmp/quickstart-embed.json` with an `embedding` array means model access and IAM permissions are both correct. An `AccessDeniedException` here means either model access hasn't been requested yet (Section 3) or your permission set doesn't include the Bedrock invoke policy — the plain `list-foundation-models` call (below) can't tell you which.
   ```
   aws bedrock list-foundation-models --region us-west-2 \
     --query "modelSummaries[?contains(modelId,'titan-embed') || contains(modelId,'claude')].modelId" \
     --profile <your-profile>
   ```
   Treat this second command as a connectivity/permission sanity check only (it needs just `bedrock:ListFoundationModels`) — an empty or errored result means you can't even reach Bedrock; a full list does not mean you have model access.

If steps 4–5 both return clean output, you're unblocked for any phase of `implementation2.md`.

---

## Owner action items (Tim — unblocks everyone else)

- [ ] Set up team access: enable IAM Identity Center and invite teammates ([Section 0](#0-getting-access-to-the-shared-account)), or at minimum run `aws configure sso` (or `aws login`) yourself so the Phase 0 blocker clears.
- [ ] Verify: `aws sts get-caller-identity`, then the Titan `invoke-model` test in [Section 3](#3-bedrock-foundation-model-access).
- [ ] One person: request Bedrock model access in the console for Titan Text Embeddings V2 + Claude in `us-west-2` — this unlocks the whole account; Anthropic models need the one-time use-case form.
- [ ] Share this doc (`implementation-aws.md`) with the team.
- [ ] After judging: run the [Section 13](#13-cost-and-teardown) teardown — the OpenSearch Serverless collection is the ~$350/month item.

---

## 0. Getting access to the shared account

**Recommendation: AWS IAM Identity Center (successor to AWS SSO), not individual IAM users.** For a small team sharing one account for a few days, plain IAM users with long-lived access keys are tempting because they're one console click, but they mean managing per-user access keys (a leak risk, and a pain to rotate), no central place to see who has what, and no easy way to revoke someone at 6:59AM Friday. Identity Center gives everyone short-lived, auto-refreshing credentials via `aws configure sso`, a single browser login, and permission sets you can hand out by name ("give Sam the `PolicyAssistantDev` permission set") instead of hand-assembling IAM policies per person.

**One-time setup (whoever holds root/admin — likely Tim):**
1. AWS Console → IAM Identity Center → Enable (if not already enabled for this account; if the account is part of an existing AWS Organization, Identity Center may already be on — check first).
2. Identity Center → Users → Add user for each teammate (email, first/last name). They'll get an email to set a password and enable MFA.
3. Identity Center → Permission sets → Create permission set → Custom, attach the JSON policy from [Section 1.2](#12-least-privilege-policy-for-app-work) (or start with `PowerUserAccess` for hackathon speed and tighten later if time allows — see the trade-off note below).
4. Identity Center → AWS accounts → select this account → Assign users → pick each teammate + the permission set.
5. Note the **AWS access portal URL** (looks like `https://<d-xxxxxxxxxx>.awsapps.com/start`) and share it with the team — this is what `aws configure sso` will ask for.

**Trade-off note (hackathon reality):** `PowerUserAccess` (AWS managed policy, everything except IAM/Org management) is the fast path and is defensible for a 3-day hackathon on a throwaway account, provided nobody attaches IAM policies to themselves or creates new IAM users. Note the exclusion is real and will bite: `PowerUserAccess` explicitly denies IAM administration, so whoever ends up creating the Lambda execution role (Section 7) needs an IAM add-on beyond `PowerUserAccess` — see Section 1.1. If the team wants real least-privilege from the start, use the custom policy in Section 1.2 instead for read/runtime testing — but note that policy alone does not cover *provisioning* the resources in Phases A/B; see Section 1.1 for that.

**Per-teammate (after being added):**
```
aws configure sso
```
Follow the prompts: SSO start URL = the access portal URL above, SSO region = `us-east-2` or wherever Identity Center itself is hosted (Identity Center has its own home region, separate from `us-west-2` where your resources live — the CLI will tell you this during setup), then pick the account and permission set. Give the profile a name, e.g. `policy-assistant`.

Confirm your generated `~/.aws/config` profile has:
```ini
[profile policy-assistant]
sso_session = <session-name>
sso_account_id = <account-id>
sso_role_name = <permission-set-name>
region = us-west-2
output = json
```
If `region` isn't `us-west-2`, add it — this is the #1 source of "AccessDenied" or "resource not found" confusion when someone's shell defaults to `us-east-1`.

**Verify:**
```
aws sts get-caller-identity --profile policy-assistant
```

---

## 1. IAM — the permissions model

### 1.1 What each phase needs (AWS managed policies, by name)

Rather than hand-crafting a policy per phase, here's the fastest path using AWS managed policies, mapped to what `implementation2.md` Phase A–D actually touches:

| Phase | Managed policy | Covers |
|---|---|---|
| A (infra: S3, KB, DynamoDB, Cognito) | `AmazonS3FullAccess`, `AmazonBedrockFullAccess`, `AmazonDynamoDBFullAccess`, `AmazonCognitoPowerUser` | bucket + object ops, KB creation/sync, table CRUD, user pool + groups |
| A (OpenSearch Serverless, backs the KB) | **No AWS managed policy covers this** — `AmazonOpenSearchServiceFullAccess` grants `es:*` (the older, non-Serverless OpenSearch API namespace) and does **not** include `aoss:*`. Use a small custom policy for the person doing Phase A, e.g. `Action: ["aoss:*"], Resource: "*"` (or narrow to `aoss:CreateCollection`, `aoss:CreateSecurityPolicy`, `aoss:CreateAccessPolicy`, `aoss:BatchGetCollection`, `aoss:APIAccessAll` if you want it tighter) | collection + data-access policy creation |
| B (Lambda + API Gateway) | `AWSLambda_FullAccess`, `AmazonAPIGatewayAdministrator`, plus an IAM add-on to create the Lambda **execution role** (see the note below) | function deploy, HTTP API + JWT authorizer, role creation |
| C (Amplify) | `AdministratorAccess-Amplify` | Hosting app creation, build config, env vars |
| D (Guardrails, EventBridge) | included in `AmazonBedrockFullAccess`; `AmazonEventBridgeFullAccess` | Guardrail create/version, scheduled rules |

**IAM add-on for Phase B:** neither `PowerUserAccess` nor the managed-policy combination above includes IAM administration — `PowerUserAccess` explicitly excludes it. Whoever creates the Lambda execution role in Section 7 needs, at minimum, `iam:CreateRole`, `iam:AttachRolePolicy`, `iam:PutRolePolicy`, and `iam:PassRole` scoped to that role's ARN (so Lambda can assume it). Either grant `IAMFullAccess` to that one teammate for the provisioning step, or hand them a scoped inline policy with just those four actions on `arn:aws:iam::<account-id>:role/PolicyAssistantLambdaRole`.

Provisioning work (creating the actual Phase A/B resources) needs the managed policies in this table (or `PowerUserAccess` + the IAM add-on above) — the JSON policy in Section 1.2 is deliberately narrower and is **not** sufficient on its own for provisioning; see that section for what it's actually for.

If everyone just gets `PowerUserAccess` (see Section 0) plus the IAM add-on above for whoever runs Phase B, all of the above is covered and you can skip this table — it's here for anyone who wants a tighter permission set or is reviewing what the app itself (not a human) is allowed to do.

### 1.2 Runtime/read-test policy (not a provisioning policy)

This is a **runtime and verification** policy — attach it to a teammate's Identity Center permission set if their job is exercising the already-provisioned app (running the invoke/retrieve verify commands throughout this doc, testing the data path from the CLI) rather than creating infrastructure. It deliberately does **not** grant `s3:CreateBucket`, `dynamodb:CreateTable`, `bedrock:CreateKnowledgeBase`, or any other `Create*`/`Delete*` action — for provisioning Phases A/B, use the managed policies in Section 1.1 instead (or `PowerUserAccess` + the IAM add-on). Replace `<account-id>` and `<region>` — everything else is safe to use as-is:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "BedrockInvokeAndRetrieve",
      "Effect": "Allow",
      "Action": [
        "bedrock:InvokeModel",
        "bedrock:InvokeModelWithResponseStream",
        "bedrock:Retrieve",
        "bedrock:RetrieveAndGenerate",
        "bedrock:ListFoundationModels",
        "bedrock:GetFoundationModel",
        "bedrock:GetKnowledgeBase",
        "bedrock:ListKnowledgeBases",
        "bedrock:StartIngestionJob",
        "bedrock:GetIngestionJob",
        "bedrock:ListIngestionJobs"
      ],
      "Resource": "*"
    },
    {
      "Sid": "S3CorpusBucket",
      "Effect": "Allow",
      "Action": ["s3:GetObject", "s3:PutObject", "s3:ListBucket"],
      "Resource": [
        "arn:aws:s3:::<account-id>-policy-corpus",
        "arn:aws:s3:::<account-id>-policy-corpus/*"
      ]
    },
    {
      "Sid": "DynamoDBAppTables",
      "Effect": "Allow",
      "Action": [
        "dynamodb:GetItem",
        "dynamodb:PutItem",
        "dynamodb:UpdateItem",
        "dynamodb:Query",
        "dynamodb:Scan"
      ],
      "Resource": "arn:aws:dynamodb:<region>:<account-id>:table/PolicyAssistant-*"
    }
  ]
}
```

This is the **human/teammate** policy for exploring and testing the app's data path from the CLI. It is deliberately not the same thing as a service role (Section 1.3) — those are narrower and scoped to one resource, not a whole table prefix.

### 1.3 Service-role permission chains (who calls whom)

This is the part that trips people up: several AWS services act *as* other principals, and each hop needs its own explicit grant. Four chains matter for this project:

1. **Lambda execution role → Bedrock / DynamoDB / S3.** The Lambda function (FastAPI via Mangum, per `implementation2.md` Phase B) runs as an IAM role, not as you. That role needs `bedrock:InvokeModel` + `bedrock:Retrieve` (to call the KB), `dynamodb:*Item`/`Query` on the `ConflictLog`/`Uploads` tables, and `s3:GetObject`/`PutObject` on the corpus bucket (for presigned uploads). Attach `AWSLambdaBasicExecutionRole` (for CloudWatch Logs) plus an inline policy shaped like Section 1.2's Bedrock/DynamoDB/S3 statements, scoped to this Lambda's specific resources.
2. **S3 event notification → ingestion Lambda invoke permission → `bedrock:StartIngestionJob` on the KB.** Three separate grants: (a) the S3 bucket's event notification config needs `lambda:InvokeFunction` permission granted *to* S3 as a resource-based policy on the Lambda (`aws lambda add-permission --principal s3.amazonaws.com`), (b) the ingestion Lambda's own execution role needs `bedrock:StartIngestionJob` scoped to the specific Knowledge Base ARN, and (c) that Knowledge Base's own service role (next point) needs to actually be able to read the object that triggered it.
3. **Knowledge Base service role → S3 + OpenSearch Serverless data-access policy.** When you create a Bedrock Knowledge Base, Bedrock creates (or you provide) a service role that the KB assumes to do its own work — reading source objects from S3 and writing vectors to OpenSearch Serverless. That role needs `s3:GetObject`/`s3:ListBucket` on the corpus bucket **and** must be named in the OpenSearch Serverless collection's **data access policy** (a separate OpenSearch-native permissions object, not an IAM policy — see Section 4). Missing the data-access-policy entry is the most common KB-creation failure; the IAM role can be perfect and the sync will still fail with an OpenSearch authorization error if that role isn't in the collection's data access policy.
4. **API Gateway JWT authorizer → Cognito user pool.** The HTTP API's JWT authorizer is configured with the Cognito user pool's issuer URL and app client ID — it validates tokens directly against Cognito's public JWKS endpoint, no IAM role in between. The thing to get right here isn't IAM, it's config: issuer must be `https://cognito-idp.<region>.amazonaws.com/<user-pool-id>` exactly, and the app client used to mint tokens must match the `audience`.

### 1.4 Verify your own IAM setup

```
aws iam get-user --profile policy-assistant 2>/dev/null || aws sts get-caller-identity --profile policy-assistant
```
(Identity Center federated sessions don't have a classic IAM user, so `get-user` will fail — that's expected; `get-caller-identity` is the real check, already run in the Quickstart.)

---

## 2. Amazon S3 — corpus bucket

**Purpose:** raw sources (Handbook PDF, CBA, PolicyStat exports, synthetic files, scraped catalog Markdown) plus the trigger for auto-ingestion.

**Setup (CLI):**
```
aws s3 mb s3://<account-id>-policy-corpus --region us-west-2 --profile policy-assistant

aws s3api put-bucket-versioning \
  --bucket <account-id>-policy-corpus \
  --versioning-configuration Status=Enabled \
  --profile policy-assistant
```
Create prefixes as you upload (S3 prefixes aren't real folders, just key naming): `handbook/`, `cba/`, `resolutions/`, `synthetic/`, `catalog/`.

Upload the corpus:
```
aws s3 cp data/corpus/ s3://<account-id>-policy-corpus/ --recursive --profile policy-assistant
```

**Event notification (wired up in Phase B, once the ingestion Lambda exists):** configure `s3:ObjectCreated:*` to invoke the ingestion Lambda. Do this after the Lambda exists (Section 7) — creating the notification before the Lambda's resource policy grants S3 invoke permission will fail.

**Verify:**
```
aws s3 ls s3://<account-id>-policy-corpus/ --profile policy-assistant
```
Expect your uploaded prefixes listed back.

---

## 3. Bedrock foundation model access

**This is a console-only, one-time, per-account-per-region step — and it unlocks access for the whole team, not just the person who clicks it.** Model access in Bedrock is not an IAM permission; it's a separate account-level "I agree to the EULA for this model" toggle that AWS tracks per account per region. One person requesting access in `us-west-2` is sufficient — nobody else needs to repeat this.

**Steps (console):**
1. AWS Console → Bedrock → make sure the region selector (top right) is set to **US West (Oregon) / us-west-2**.
2. Left nav → Model access → Modify model access (or "Manage model access" depending on console version).
3. Check the boxes for:
   - **Amazon Titan Text Embeddings V2** (`amazon.titan-embed-text-v2:0`) — used for both the local-demo embeddings and the Knowledge Base's embedding model.
   - **Anthropic Claude** — recommend **Claude Sonnet 4.5** (model id `anthropic.claude-sonnet-4-5-20250929-v1:0`, accessed at runtime via the cross-region inference profile id `us.anthropic.claude-sonnet-4-5-20250929-v1:0`). It's Anthropic's current mid-tier model on Bedrock as of this writing — strong at structured JSON output (needed for the conflict/resolution-checker JSON contracts) and available via on-demand inference profiles, so no provisioned throughput purchase is needed. **Double-check the exact model id in the console's model catalog before wiring it into code** — Bedrock adds/retires model ids over time and the catalog is the source of truth, not this doc.
4. Submit. Amazon models (Titan) grant instantly. **Anthropic models are different: the first time your account requests access to an Anthropic model, AWS requires a one-time use-case/details form** (company name, intended use, etc.) before it grants access — budget a few extra minutes for this the first time anyone on the team requests Claude access; after that one approval, the whole account has it in this region.
5. Wait 1–2 minutes (longer if the Anthropic use-case form triggers a review), then verify below.

**Verify:**
```
aws bedrock list-foundation-models --region us-west-2 \
  --query "modelSummaries[?contains(modelId,'titan-embed') || contains(modelId,'claude')].modelId" \
  --profile policy-assistant
```
Treat this as a **connectivity/permission sanity check only** — it lists the model catalog regardless of whether your account has been granted access to any of them, so a full list here does **not** prove model access. To prove access end to end, run real invoke calls for both models:
```
aws bedrock-runtime invoke-model \
  --region us-west-2 \
  --model-id amazon.titan-embed-text-v2:0 \
  --body '{"inputText":"service credit tenure clock"}' \
  --cli-binary-format raw-in-base64-out \
  /tmp/embed-out.json \
  --profile policy-assistant
```
A populated `/tmp/embed-out.json` with an `embedding` array means Titan invoke works end to end. For Claude, invoke via the cross-region inference profile id (the plain model id alone often won't work for on-demand Claude access):
```
aws bedrock-runtime invoke-model \
  --region us-west-2 \
  --model-id us.anthropic.claude-sonnet-4-5-20250929-v1:0 \
  --body '{"anthropic_version":"bedrock-2023-05-31","max_tokens":50,"messages":[{"role":"user","content":"Reply with OK."}]}' \
  --cli-binary-format raw-in-base64-out \
  /tmp/claude-out.json \
  --profile policy-assistant
```
A populated `/tmp/claude-out.json` with a `content` array means Claude invoke access is live. As an extra check, `aws bedrock list-inference-profiles --region us-west-2 --profile policy-assistant` should list the `us.anthropic.*` profile — if it's missing, the inference profile isn't available in this region/account yet even if the underlying model shows access-granted.

---

## 4. Bedrock Knowledge Bases + OpenSearch Serverless (vector store)

**Purpose:** replaces the local NumPy index — managed chunking, embedding, and retrieval over the S3 corpus bucket.

**See also:** `backend/rag/README.md` documents Alyssa's Bedrock RAG spike, which already has two
provisioned-looking Knowledge Base IDs (see the honesty check at the top of this doc) and a
working config pattern for pointing scripts at a KB. It's a standalone verification harness, not
the app's retrieval path (that's `backend/app/retrieval.py`, one KB via `BEDROCK_KB_ID`) — but if
you're setting up KB access for the first time, its README and `config.py` defaults are a useful
second data point alongside the steps below.

**Setup (console is genuinely easier here — KB creation has several linked sub-resources the console wizard wires up for you):**
1. Bedrock console (region `us-west-2`) → Knowledge Bases → Create.
2. Data source: point at `s3://<account-id>-policy-corpus/`. Chunking strategy is a setting you select in the wizard, not a guaranteed default — choose fixed-size chunking at **~500 tokens / 20% overlap** to match `implementation2.md` Phase A.2's decision (the console's out-of-the-box default may differ, so set this explicitly rather than assuming it).
3. Embeddings model: **Titan Text Embeddings V2** (must already have model access from Section 3).
4. Vector store: choose "Quick create a new vector store" → **Amazon OpenSearch Serverless**. The console will create the collection, the KB's service role, and the OpenSearch data-access policy naming that role, all in one flow — this is the main reason to use the console instead of hand-rolling it via CLI.
5. Review and create. Then trigger an initial sync: Knowledge Bases → your KB → Data source → Sync.

**The one thing to check manually if sync fails:** OpenSearch Serverless → Collections → your collection → Data access policies. Confirm the KB's service role principal is listed with index/document-level permissions on the collection and its indexes — e.g. `aoss:CreateIndex`, `aoss:DescribeIndex`, `aoss:UpdateIndex`, `aoss:ReadDocument`, `aoss:WriteDocument`. This data-access-policy grant is a separate, OpenSearch-native permissions object (not IAM) — don't confuse it with `aoss:APIAccessAll`, which is a *different* thing: an IAM identity-policy action (used in Section 1.1's custom policy) that controls whether the role can call the OpenSearch Serverless data-plane API at all. You need both: the IAM side (the role is allowed to call the API) and the data-access-policy side (the collection allows that specific role to touch its indexes/documents) — missing either one produces the same OpenSearch authorization error during sync.

**Verify (console):** Knowledge Bases → your KB → "Test Knowledge Base" panel → query `service credit tenure clock` → confirm both a CBA-sourced chunk and a synthetic Handbook chunk appear in the results (this is the calibration case from `spec.md` §6 and `implementation.md` Phase 1.5).

**Verify (CLI, once you have the KB ID):**
```
aws bedrock-agent-runtime retrieve \
  --region us-west-2 \
  --knowledge-base-id <kb-id> \
  --retrieval-query '{"text":"service credit tenure clock"}' \
  --profile policy-assistant
```
Expect a JSON response with a `retrievalResults` array containing chunk text + source S3 URIs.

---

## 5. DynamoDB

**Purpose:** replaces SQLite. Tables per `implementation2.md` Phase A.3 and the Notion scope's access-control/registry additions:

| Table | Partition key | Notes |
|---|---|---|
| `PolicyAssistant-ConflictLog` | `id` (string) | no GSIs at demo scale — see note below |
| `PolicyAssistant-Uploads` | `id` (string) | ingestion status, S3 key |
| `PolicyAssistant-AccessControl` | `userId` (string), sort key `sourceType#sourceId` | `{canAdd, canEdit, grantedBy, grantedAt}` per Notion scope §"Implementation Notes" |
| `PolicyAssistant-CatalogRegistry` | `s3Key` (string) | `{title, canonical_url, source_type, owner, section_index, last_synced, status}` — also carries the archived/active flag from the Notion scope |

**Setup (CLI):**
```
aws dynamodb create-table \
  --table-name PolicyAssistant-ConflictLog \
  --attribute-definitions AttributeName=id,AttributeType=S \
  --key-schema AttributeName=id,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST \
  --region us-west-2 --profile policy-assistant

aws dynamodb create-table \
  --table-name PolicyAssistant-Uploads \
  --attribute-definitions AttributeName=id,AttributeType=S \
  --key-schema AttributeName=id,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST \
  --region us-west-2 --profile policy-assistant

aws dynamodb create-table \
  --table-name PolicyAssistant-AccessControl \
  --attribute-definitions AttributeName=userId,AttributeType=S AttributeName=sourceKey,AttributeType=S \
  --key-schema AttributeName=userId,KeyType=HASH AttributeName=sourceKey,KeyType=RANGE \
  --billing-mode PAY_PER_REQUEST \
  --region us-west-2 --profile policy-assistant

aws dynamodb create-table \
  --table-name PolicyAssistant-CatalogRegistry \
  --attribute-definitions AttributeName=s3Key,AttributeType=S \
  --key-schema AttributeName=s3Key,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST \
  --region us-west-2 --profile policy-assistant
```
Use on-demand (`PAY_PER_REQUEST`) billing — at hackathon-demo scale this is pennies and you don't want to think about provisioned capacity.

**On the `topic`/`status` GSIs:** the `create-table` command above does not create them (a real GSI needs `--attribute-definitions` and `--global-secondary-indexes` at creation time, or a later `update-table`). At hackathon-demo scale — a handful of conflict-log rows, pre-seeded plus a few detected live — filtering by `topic` or `status` with a `Scan` and a filter expression is simpler and fast enough; there's no need for the extra table-definition complexity under demo load. If the conflict log grows past a trivial size post-hackathon, add the GSIs then with `aws dynamodb update-table --table-name PolicyAssistant-ConflictLog --attribute-definitions AttributeName=topic,AttributeType=S --global-secondary-indexes '[{"Create":{"IndexName":"topic-index","KeySchema":[{"AttributeName":"topic","KeyType":"HASH"}],"Projection":{"ProjectionType":"ALL"}}}]'`.

`AccessControl` and `CatalogRegistry` are Phase-D/"later" per the Notion scope's own "Likely Needed Later" framing — create them now if time allows, but they aren't blocking the core demo path (chat, resolution checker, conflict log) that `implementation2.md` treats as never-cut.

**Verify:**
```
aws dynamodb list-tables --region us-west-2 --profile policy-assistant
```
Expect all four table names back. Then confirm a write/read round-trips:
```
aws dynamodb put-item --table-name PolicyAssistant-ConflictLog \
  --item '{"id":{"S":"test-1"},"topic":{"S":"smoke-test"}}' \
  --region us-west-2 --profile policy-assistant

aws dynamodb get-item --table-name PolicyAssistant-ConflictLog \
  --key '{"id":{"S":"test-1"}}' \
  --region us-west-2 --profile policy-assistant
```

---

## 6. Amazon Cognito — auth

**Target group model:** the Notion MVP scope specifies **Admin / Reviewer-Writer / Employee** as the three role groups, driving both dashboard routing and conflict-log visibility gating. `implementation2.md`'s architecture diagram (written earlier) only names two groups, **makers / employees** — treat that as the older, coarser version of the same idea. **Use Admin / Reviewer-Writer / Employee going forward**; if code or slides still say `makers`/`employees`, that's the two-group MVP simplification and should be read as `Reviewer-Writer` ≈ `maker` and `Employee` ≈ `employee`, with `Admin` as a new top tier (source-access permission panel, source archive/activate) that wasn't in the original two-group split.

**Setup (console — Cognito's hosted-UI config has enough interlocking pieces that the console wizard is worth it over raw CLI):**
1. Cognito console (region `us-west-2`) → User pools → Create user pool.
2. Sign-in options: email. Password policy: defaults are fine for a demo.
3. Skip MFA for demo speed (call this out on the architecture slide as a known simplification) or enable it if time allows.
4. App integration → hosted UI domain: pick a Cognito-provided domain (`<prefix>.auth.us-west-2.amazoncognito.com`) — fastest path, no custom domain/cert needed.
5. Create an app client: **public client, no client secret** (required for the Amplify `Authenticator` component / any browser-based SPA flow — a confidential client with a secret can't be used safely from JS).
6. Groups → create three groups: `Admin`, `Reviewer-Writer`, `Employee`. Precedence doesn't matter unless a user is ever in more than one group.
7. Users → create two (or three) demo users, one per group, matching the demo accounts already used in the local-demo `auth.py` (e.g. `reviewer@campus.edu` → `Reviewer-Writer`, `employee@campus.edu` → `Employee`). Set permanent passwords so the hosted UI doesn't force a first-login reset during the live demo.

**Frontend integration:** Amplify's `Authenticator` component (Section 8) points at this pool's ID + app client ID via environment variables; it renders Cognito's hosted UI (or its own themed UI) and returns a JWT containing a `cognito:groups` claim — that claim is what the backend and the API Gateway authorizer read for role routing (Section 7).

**Verify:**
```
aws cognito-idp list-user-pools --max-results 10 --region us-west-2 --profile policy-assistant

aws cognito-idp admin-list-groups-for-user \
  --user-pool-id <pool-id> \
  --username reviewer@campus.edu \
  --region us-west-2 --profile policy-assistant
```
Expect `Reviewer-Writer` in the groups list for that user.

---

## 7. Lambda + API Gateway (backend)

**Purpose:** hosts the FastAPI app (wrapped with Mangum per `implementation2.md` Phase B.1) behind an HTTP API with a Cognito JWT authorizer — this is what deletes the hardcoded `auth.py` accounts.

**Lambda execution role (create first):**
```
aws iam create-role \
  --role-name PolicyAssistantLambdaRole \
  --assume-role-policy-document '{
    "Version":"2012-10-17",
    "Statement":[{"Effect":"Allow","Principal":{"Service":"lambda.amazonaws.com"},"Action":"sts:AssumeRole"}]
  }' \
  --profile policy-assistant

aws iam attach-role-policy \
  --role-name PolicyAssistantLambdaRole \
  --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole \
  --profile policy-assistant
```
Then attach an inline policy shaped like Section 1.2's Bedrock/DynamoDB/S3 statements, scoped to this project's specific bucket/table/KB ARNs (see Section 1.3, chain 1).

**Deploy the function (assuming a zip or container image is already built by the app team):**
```
aws lambda create-function \
  --function-name policy-assistant-api \
  --runtime python3.12 \
  --role arn:aws:iam::<account-id>:role/PolicyAssistantLambdaRole \
  --handler app.main.handler \
  --zip-file fileb://backend.zip \
  --timeout 30 --memory-size 512 \
  --region us-west-2 --profile policy-assistant
```

**API Gateway HTTP API with Cognito JWT authorizer:**
```
aws apigatewayv2 create-api \
  --name policy-assistant-api \
  --protocol-type HTTP \
  --target arn:aws:lambda:us-west-2:<account-id>:function:policy-assistant-api \
  --region us-west-2 --profile policy-assistant

aws apigatewayv2 create-authorizer \
  --api-id <api-id> \
  --authorizer-type JWT \
  --identity-source '$request.header.Authorization' \
  --jwt-configuration Audience=<cognito-app-client-id>,Issuer=https://cognito-idp.us-west-2.amazonaws.com/<user-pool-id> \
  --name cognito-authorizer \
  --region us-west-2 --profile policy-assistant

aws lambda add-permission \
  --function-name policy-assistant-api \
  --statement-id apigateway-invoke \
  --action lambda:InvokeFunction \
  --principal apigateway.amazonaws.com \
  --source-arn "arn:aws:execute-api:us-west-2:<account-id>:<api-id>/*/*" \
  --profile policy-assistant
```
That last command is the resource-based permission grant referenced in Section 1.3 — without it, API Gateway can route to the Lambda but the invocation itself is denied.

**Creating the authorizer is not the same as attaching it — this step is easy to skip and easy to miss.** `create-api` with `--target` (quick-create mode) generates a `$default` route with `AuthorizationType: NONE`; the JWT authorizer you just created sits unused until you explicitly attach it to a route. Find the route, then update it:
```
aws apigatewayv2 get-routes --api-id <api-id> --region us-west-2 --profile policy-assistant

aws apigatewayv2 update-route \
  --api-id <api-id> \
  --route-id <route-id> \
  --authorization-type JWT \
  --authorizer-id <authorizer-id> \
  --region us-west-2 --profile policy-assistant
```
Repeat `update-route` for every route that should require auth (a route per resource, or just `$default` if the whole API sits behind one authorizer).

**Verify:**
```
aws apigatewayv2 get-apis --region us-west-2 --profile policy-assistant

curl -i https://<api-id>.execute-api.us-west-2.amazonaws.com/api/topics
```
Expect `401 Unauthorized` (no token) — but only *after* the `update-route` step above; before that, the route has `AuthorizationType: NONE` and will happily return `200` with no token, which looks like success but actually means the authorizer isn't wired up. Get a real token from a Cognito login and retry with `Authorization: Bearer <token>` for a `200`. Use the Cognito **access token**, not the ID token — the JWT authorizer's `Audience` is normally configured against the access token's `client_id` claim, and an ID-token/access-token mismatch (or an authorizer `Audience` that doesn't match the token you're sending) is the classic cause of a `401` that looks like a wiring bug but is actually a token-type mismatch.

---

## 8. AWS Amplify Hosting (frontend)

**Purpose:** git-connected build/deploy of `frontend/`, replacing the Vite dev server for the final demo.

**Setup (console is easiest — connecting a GitHub repo requires an OAuth handshake that's awkward via CLI):**
1. Amplify console (region `us-west-2`) → Create app → Host web app → connect the GitHub repo → select the branch to deploy.
2. Build settings: Amplify auto-detects a Vite app; confirm build command `npm run build` and output directory `frontend/dist` (adjust the app root if `frontend/` isn't the repo root Amplify assumes).
3. Environment variables (App settings → Environment variables): `VITE_API_BASE_URL` (the API Gateway invoke URL from Section 7), `VITE_COGNITO_USER_POOL_ID`, `VITE_COGNITO_CLIENT_ID`, `VITE_COGNITO_DOMAIN` (from Section 6).
4. Deploy. Amplify builds and serves over its own `*.amplifyapp.com` domain automatically — no separate CloudFront/S3 setup needed.

**Verify:**
```
aws amplify list-apps --region us-west-2 --profile policy-assistant

aws amplify get-app --app-id <app-id> --region us-west-2 --profile policy-assistant
```
Then open the app's default domain in a browser and confirm the Cognito hosted UI loads on the login route.

---

## 9. Bedrock Guardrails

**Purpose:** per the Notion MVP scope, the corpus legitimately covers sensitive topics (harassment, weapons-on-campus, misconduct) as *policy subject matter* — the guardrail has to let the assistant discuss the policy without discussing it in a way that violates the policy itself. Principle: **input filters strict, output filters loose** — never set every category to "everything HIGH," or the assistant will refuse to answer legitimate policy questions about, say, Title IX.

**Setup (console):**
1. Bedrock console (region `us-west-2`) → Guardrails → Create guardrail.
2. Content filters — set input/output strength per category exactly as scoped:

   | Category | Input | Output | Why |
   |---|---|---|---|
   | Hate | HIGH | MEDIUM | Output must explain anti-discrimination policy |
   | Insults | MEDIUM | LOW | Output covers grievance/civility policy language |
   | Sexual | HIGH | LOW–MEDIUM | Output must cover Title IX / sexual harassment policy |
   | Violence | HIGH | MEDIUM | Output covers weapons-on-campus / workplace-violence policy |
   | Misconduct | MEDIUM | LOW | Output discusses misconduct policy constantly |

3. Prompt attacks: set to **HIGH** (input only — this one has no "loose output" side, jailbreak attempts should always be blocked).
4. Contextual grounding check: enable, with high grounding and relevance thresholds — this is the anti-hallucination backstop tying the guardrail to the same "answers must be grounded in retrieved chunks" requirement already in the chat prompt contract (`implementation.md` Phase 2.3).
5. Sensitive information filters: enable PII masking, but configure it to **preserve citations** — mask personal PII (names, SSNs, emails) in generated prose while leaving source/section reference tokens (e.g. "CBA Article 12.3") untouched, since those aren't PII and are load-bearing for the product's core promise of cited answers.
6. Denied topics — add all eight, each with the shared blocked-message tone ("I can help you find and understand existing policy, but I can't help with that…"):
   - Legal Advice & Interpretation
   - Individual Personnel Decisions
   - Declaring a Conflict Winner
   - Policy Circumvention & Evasion
   - Personal Professional Advice
   - Confidential & Gated Content
   - Off-Topic General Requests
   - Opinions & Endorsements
7. Create a version once configured. Guardrails are draft-then-versioned, but the `DRAFT` version is itself attachable to a model invocation for iteration/testing — you don't strictly need a published numbered version to start wiring it in; publish a numbered version once you're happy with it so you have a stable, immutable reference for the actual demo (rather than a `DRAFT` that could change under you).

**Validation approach (from the Notion scope):** run one deliberately-worded query per content-filter category plus the ~10 calibration questions from `spec.md`/the Notion scope §7. If a legitimate policy question gets blocked, lower that category's **output** strength one notch and retest — don't touch input strength, since the goal is to keep the door strict on the way in and permissive on the way out once grounded in real policy text.

**Wiring in:** the request shape differs by API, so don't assume one shared field name. The **Converse API** takes a nested `guardrailConfig` object: `{"guardrailConfig": {"guardrailIdentifier": "<id>", "guardrailVersion": "<version-or-DRAFT>", "trace": "enabled"}}`. The lower-level **InvokeModel API** takes `guardrailIdentifier` and `guardrailVersion` as separate top-level request parameters, not nested. Whichever call `llm.py` (or its Lambda equivalent) uses, match that shape exactly. This also needs one IAM permission beyond plain `bedrock:InvokeModel`: add `bedrock:ApplyGuardrail` to the Lambda execution role's inline policy (Section 1.3, chain 1) — without it, guardrail-attached invocations fail even though ungated `InvokeModel` calls succeed. Also confirm your IAM policy doesn't scope `Resource` down to a specific model ARN in a way that excludes the guardrail resource type.

**Verify:**
```
aws bedrock list-guardrails --region us-west-2 --profile policy-assistant

aws bedrock get-guardrail --guardrail-identifier <guardrail-id> --region us-west-2 --profile policy-assistant
```
Expect the guardrail's config echoed back, including your denied topics list.

---

## 10. Amazon EventBridge

**Purpose:** per the Notion scope's "Likely Needed Later," a scheduled re-scrape of the course catalog (`catalog.csub.edu`) so newly published catalog editions get re-ingested without a manual trigger. This is explicitly a later/optional piece, not required for the core demo path.

**Setup (CLI):**
```
aws events put-rule \
  --name policy-assistant-catalog-rescrape \
  --schedule-expression "rate(7 days)" \
  --region us-west-2 --profile policy-assistant

aws lambda add-permission \
  --function-name catalog-scraper \
  --statement-id eventbridge-invoke \
  --action lambda:InvokeFunction \
  --principal events.amazonaws.com \
  --source-arn arn:aws:events:us-west-2:<account-id>:rule/policy-assistant-catalog-rescrape \
  --profile policy-assistant

aws events put-targets \
  --rule policy-assistant-catalog-rescrape \
  --targets "Id"="1","Arn"="arn:aws:lambda:us-west-2:<account-id>:function:catalog-scraper" \
  --region us-west-2 --profile policy-assistant
```
Same pattern as the S3-event chain in Section 1.3: the rule alone doesn't grant invoke rights, the `add-permission` call does.

**Verify:**
```
aws events describe-rule --name policy-assistant-catalog-rescrape --region us-west-2 --profile policy-assistant

aws events list-targets-by-rule --rule policy-assistant-catalog-rescrape --region us-west-2 --profile policy-assistant
```

---

## 11. Strands Agents SDK (not an AWS service — a library)

Flagging this explicitly because it's easy to assume everything in the architecture diagram needs console setup: **Strands Agents SDK is a Python library, not an AWS service.** There is nothing to "enable" in the AWS console. It ships as a pip package (`strands-agents` — do not install without listing it and getting sign-off first, per the team's dependency-approval norm) and runs *inside* the Lambda function from Section 7, orchestrating the retrieval/extraction/conflict/verifier/escalation agent pipeline described in the Notion scope §9.

Its only AWS-facing requirement is that the Lambda execution role it runs under (Section 7) already has `bedrock:InvokeModel` and `bedrock:Retrieve` — nothing additional. If a teammate goes looking for a "Strands" entry in the console, they won't find one; that's expected, not a setup failure.

---

## 12. Phase mapping (implementation2.md Phase A–D → this doc)

| Phase | What it needs from this doc |
|---|---|
| **A — Infrastructure** | Section 0 (account access), Section 1 (IAM), Section 2 (S3 bucket + corpus upload), Section 3 (Bedrock model access), Section 4 (Knowledge Base + OpenSearch Serverless), Section 5 (DynamoDB tables), Section 6 (Cognito user pool + groups + demo users) |
| **B — Backend on Lambda** | Section 1.3 chains 1–3 (Lambda role, S3→ingestion Lambda→KB sync, KB service role), Section 7 (Lambda + API Gateway + JWT authorizer), Section 11 (Strands in the Lambda) |
| **C — Frontend** | Section 6 (Cognito `Authenticator` wiring), Section 8 (Amplify Hosting + env vars) |
| **D — Rehearsal & Hardening** | Section 9 (Guardrails calibration pass), Section 10 (EventBridge, optional), Section 13 below (teardown before/after judging) |

---

## 13. Cost and teardown

At hackathon-demo scale, almost everything in this doc is near-free: S3 storage for a few dozen documents, DynamoDB on-demand billing for a handful of items, Lambda's free tier, API Gateway's per-request pricing, Amplify's free hosting tier, and Cognito's free tier (under 50,000 MAUs) will together run well under a dollar for the whole hackathon.

**The one standout cost is OpenSearch Serverless**, the vector store behind the Bedrock Knowledge Base. **Delete the collection right after judging — that's the headline action regardless of the exact dollar figure below.** The commonly-cited floor is roughly **2 OCUs (OpenSearch Compute Units)** even at rest, which works out to on the order of **$350+/month** if left running, accruing at an hourly rate the whole time the collection exists, demo or not. Treat that $350+ figure as a ballpark, not a guarantee: it assumes the standard minimum with redundancy enabled; AWS has introduced smaller fractional/dev-test OCU options in some accounts/regions that can bring the floor lower, while turning on standby-replica redundancy (recommended for production, unnecessary for a demo) pushes it higher. Check the actual OCU/pricing settings shown at collection-creation time rather than trusting this number precisely — but delete the collection either way.

**Teardown checklist (do this right after judging, don't wait):**
1. Bedrock console → Knowledge Bases → delete the KB (this does not automatically delete the underlying OpenSearch collection in all cases — check the next step).
2. OpenSearch Serverless console → Collections → delete the collection explicitly. This is the step that stops the ~$350+/month charge — confirm it actually shows "deleted," not just "the KB is gone."
3. Everything else (S3 bucket, DynamoDB tables, Lambda, API Gateway, Amplify app, Cognito pool, Guardrail, EventBridge rule) can be left running for a few extra days at negligible cost, but there's no reason to — delete them too once the team is done, especially the Cognito user pool and IAM roles, to shrink the account's attack surface.

**Verify teardown:**
```
aws opensearchserverless list-collections --region us-west-2 --profile policy-assistant
```
Expect an empty list (or absence of the project's collection name) once teardown is complete.

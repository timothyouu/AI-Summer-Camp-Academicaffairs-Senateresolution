# Policy Intelligence Assistant — Final Presentation Demo Plan (AWS)

Companion to `spec.md` and `implementation.md`. Where `implementation.md` gets us through tomorrow's customer demo on a local stack, this plan defines the **final demo presented to everyone (hackathon deadline: Friday 7AM)** running on the real AWS architecture from the PRD (§9). The local demo was deliberately AWS-shaped, so this is a migration, not a rewrite — every local component has a named AWS replacement.

## 1. What the Audience Sees (Presentation Flow, ~7 minutes)

1. **Problem (30s):** 167-page Handbook PDF, tribal knowledge, ~10 people / ~$10,000 manual review, summer committee couldn't finish substantive review.
2. **Sign in as an employee** (Cognito hosted UI) → land on the employee dashboard.
3. **Ask:** "Does service credit count toward the tenure clock?" → cited answer, amber conflict banner: CBA and Handbook disagree — "multiple answers available, consult your dean or the Provost's office." No forced winner.
4. **Ask:** "What is the GECCo Committee?" → correct answer even though source text uses the old, unexpanded name — semantic search beats Ctrl+F.
5. **Browse by topic** → Accessibility → the buried ATI appendix surfaces (existing-work visibility).
6. **Sign out, sign in as a reviewer** → role-gated dashboard visibly changes (Cognito groups, not if-statements anymore).
7. **The wow moment:** paste a draft "new AI policy" resolution into the Resolution Checker → agent traces show retrieval + conflict-detection + resolution-check agents working → verdict: existing policy already covers this, cited location, summary, recommendation to amend that section instead of drafting new.
8. **Conflict Log** → the conflict from step 3 was logged automatically (DynamoDB); show status workflow (open/under review/resolved) — this is the artifact that feeds real policy-resolution meetings.
9. **Live ingestion:** upload a small policy PDF → S3 event → ingestion Lambda → Knowledge Base sync → ask a question answered from it seconds later.
10. **Architecture slide (45s):** the AWS diagram below; close on cost/effort savings and the extension path (Senate resolution assessment, revision comparison).

Backup plan: a pre-recorded screen capture of steps 2–9 in case of venue Wi-Fi or AWS hiccups, plus the local-stack demo from `implementation.md` as a second fallback.

## 2. Target AWS Architecture (per PRD §9)

```
React SPA (Amplify Hosting)
   │  Cognito auth (User Pool, groups: makers / employees)
   ▼
API Gateway (HTTP API, JWT authorizer via Cognito)
   ▼
Lambda (FastAPI via Mangum, or per-route handlers)
   ├─ Strands Agents SDK orchestration:
   │    • Retrieval Agent      → Bedrock Knowledge Base (retrieve API)
   │    • Conflict Agent       → compares retrieved passages across sources
   │    • Resolution Agent     → overlap/duplicate/conflict verdict on drafts
   ├─ Bedrock: Claude (Converse) for generation, Titan Embeddings via KB
   ├─ DynamoDB: conflict log, upload registry, feedback
   └─ S3 (corpus bucket): raw sources + processed chunks
        └─ S3 event → Ingestion Lambda → KB ingestion job (auto-sync)
```

Local → AWS mapping (each is a lift, not a rebuild):

| Local demo (implementation.md) | Final demo |
|---|---|
| `data/corpus/` folder | S3 corpus bucket (prefixes: `handbook/`, `cba/`, `resolutions/`, `synthetic/`) |
| NumPy index + `retrieval.py` | Bedrock Knowledge Base (managed chunking + OpenSearch Serverless vector store), `retrieve` API |
| `llm.py` boto3 Bedrock calls | Unchanged (already real Bedrock) |
| Single chat/resolution prompt | Strands Agents SDK: retrieval / conflict / resolution agents in Lambda |
| SQLite | DynamoDB tables `ConflictLog`, `Uploads` (PK: id, GSI on topic/status) |
| Hardcoded `auth.py` | Cognito User Pool + hosted UI; API Gateway JWT authorizer; `makers` & `employees` groups drive role routing |
| `uvicorn` local server | API Gateway HTTP API + Lambda (FastAPI wrapped with Mangum keeps the codebase identical) |
| Vite dev server | Amplify Hosting (git-connected build of `frontend/`) |

## 3. Work Plan

### Phase A — Infrastructure (do first; everything else parallelizes)
1. S3 corpus bucket; upload the corpus (CBA subset, Handbook, synthetic files).
2. Bedrock Knowledge Base over the bucket (Titan Text Embeddings V2, default chunking ~500 tokens/20% overlap; OpenSearch Serverless). Run initial sync; verify with a console `retrieve` test for "service credit tenure clock".
3. DynamoDB tables + seed script (port `seed_conflicts.py` to `put_item`).
4. Cognito User Pool, two groups, two demo users (reviewer/employee), hosted UI or Amplify Auth UI.
5. Prefer IaC from the start if time allows (CDK or SAM, one stack) — else console now, export template later.

### Phase B — Backend on Lambda
1. Wrap the FastAPI app with **Mangum**; deploy as one Lambda behind an API Gateway HTTP API with Cognito JWT authorizer. Role comes from the token's `cognito:groups` claim — delete the hardcoded accounts.
2. Swap `retrieval.py` internals to `bedrock-agent-runtime.retrieve` (KB id from env). Response shape to the frontend stays identical.
3. Swap `conflicts.py`/`uploads.py` SQLite calls to DynamoDB.
4. **Strands agents** (`backend/app/agents.py`): retrieval tool (KB retrieve), conflict-detection agent (given passages from ≥2 sources, emit structured conflict), resolution-check agent (draft → overlaps/duplicates/conflicts/recommendation). Chat = retrieval + conflict agents; Check = all three. Capture agent traces and return them for the UI (presentation gold).
5. Ingestion Lambda: S3 `ObjectCreated` → `start_ingestion_job` on the KB → write status to `Uploads` table; upload endpoint now just does presigned-URL PUT to S3.

### Phase C — Frontend
1. Amplify Hosting connected to the repo; env vars for API base URL + Cognito config.
2. Replace the login page with Cognito auth (Amplify `Authenticator` component); route by group claim.
3. Add an "agent activity" panel to the Resolution Checker showing Strands trace steps.
4. Upload panel switches to presigned-URL flow with ingestion status polling.

### Phase D — Rehearsal & Hardening
1. Run the full §1 flow end-to-end twice; time it; trim to ~7 minutes.
2. Record the backup screen capture.
3. Pre-warm: one scripted request before presenting (Lambda cold start + KB first-query latency).
4. Cost/teardown note: OpenSearch Serverless is the only meaningfully costly piece — delete the collection after judging.
5. `/codex:review` on the final diff.

## 4. Cut Lines (if time runs short, in order)
1. Strands multi-agent → keep single-prompt orchestration in Lambda, still show the architecture slide honestly ("SDK slot ready").
2. Live S3-event ingestion → manual KB sync button.
3. Cognito → keep demo login, say so on the slide.
Never cut: cited conflict-aware chat, resolution checker, conflict log — those are the customer's three named pains.

## 5. Assumptions (flag if wrong)
- Frontend hosting on **Amplify** (vs S3+CloudFront) — fastest git-connected deploys.
- **Cognito is real** in the final demo (the if-statement shortcut was for tomorrow only).
- Region `us-west-2` (or wherever the account has Bedrock + OpenSearch Serverless availability).
- One AWS account with admin-ish access for the team; per-teammate IAM is out of scope.
- Knowledge Base managed chunking replaces our custom chunker; topic tags move to an ingestion-time metadata file per source (KB metadata filtering) rather than per-chunk LLM tagging.

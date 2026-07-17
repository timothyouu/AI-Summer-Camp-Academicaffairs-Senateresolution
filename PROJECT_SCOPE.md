# Project Scope — Policy Intelligence Assistant

The entry doc a cold AI or human session reads first. `CLAUDE.md` holds the working rules
and directives; the deeper operational runbooks live in the living docs listed below; the
full historical narrative lives in `docs/archive/` and `git log`.

## What the product is

A policy search assistant for a university (CSUB), built for the AI Summer Camp hackathon
(Academic Affairs / Senate Resolution track). Two role paths:

- **Employees** ask a chatbot policy questions and get cited, conflict-aware answers. Conflict
  detail is softened for them: non-clickable escalation guidance, raw conflict sources and IDs
  stripped.
- **Policy makers / reviewers** check draft resolutions for overlap/duplicates/conflicts, use a
  persistent drafting workspace, and review an accumulating conflict log with full detail.

The customer's three named pains — cited conflict-aware chat, the resolution checker, and the
conflict log — are the features that must never be cut.

## Where it stands

The customer demo was pitched **2026-07-15 (done)**. The remaining deadline is **hackathon
Friday 7AM**, presented on the real AWS architecture. Deployment target is **AWS-real, not
local**: most of the system runs on AWS; only sign-in stays local (hardcoded demo accounts in
`backend/app/auth.py`). Cognito stays OFF for the demo even though the Notion PRD lists it as a
core service — a deliberate override. The code is AWS-ready today; going non-local is deployment
config, not a code change, because every integration is gated on its own env var.

## Cut-line order if time runs short again (from archived implementation2.md)

If the team must triage before Friday, drop in this order: (1) Strands multi-agent →
single-prompt orchestration, still showing the architecture slide honestly; (2) live S3-event
ingestion → a manual KB-sync button; (3) Cognito → keep demo login, say so on the slide. Never
cut cited conflict-aware chat, the resolution checker, or the conflict log.

## Architecture — dual-mode local / AWS

- **Frontend:** React (Vite, TypeScript strict) + Tailwind CSS.
- **Backend:** FastAPI (typed Python), `Mangum` for Lambda (`backend/app/lambda_entry.py`).
- **Local default:** SQLite (conflict log, upload registry) + a NumPy/JSON on-disk vector index.
  `backend/app/llm.py` is the **local seam**: it builds deterministic hash-based embeddings and
  its `generate()` deliberately raises, so every route falls back to a source-backed deterministic
  builder and the demo needs zero AWS. `llm.py` holds **no boto3 Bedrock client** — it is not a
  Bedrock seam.
- **AWS mode:** retrieval goes to a Bedrock Knowledge Base (`backend/app/retrieval.py`,
  `bedrock-agent-runtime.retrieve`, gated on `BEDROCK_KB_ID`; the KB embeds with Titan Text
  Embeddings V2, configured in CDK not app code); generation goes through the Strands SDK
  (`backend/app/agents/factory.py::StrandsLLM` wrapping Bedrock); Bedrock Guardrails attach to
  generation when set. Gemini remains the designated fallback if Bedrock access falls through.
- **6-agent conflict pipeline** in `backend/app/agents/` emits `agent_trace`; Strands activates
  when `strands` is importable and `BEDROCK_KB_ID` is set.
- **Variance layer** (`backend/app/agents/variance.py`) is a soft re-labeling *over* the pipeline
  output — it reads `PipelineResult`, never re-implements retrieval or verification.
- **Store abstraction** (`backend/app/stores.py`) fronts SQLite or DynamoDB per table.
- **infra/** is a single CDK Python stack (`infra/stacks/policy_intelligence_stack.py`) that
  builds all 7 DynamoDB tables, S3 corpus bucket, Bedrock KB + Guardrail, OpenSearch Serverless,
  Lambda + API Gateway, and Cognito.

## Env-var gating table (nothing flips until its var is set)

| Env var | Flips on |
| --- | --- |
| `BEDROCK_KB_ID` | AWS retrieval via KB `retrieve`; disables local indexing; activates Strands |
| `BEDROCK_GUARDRAIL_ID` / `BEDROCK_GUARDRAIL_VERSION` | Guardrail attached to Strands generation |
| `DDB_CONFLICTS_TABLE` | Conflict log + variance logging to DynamoDB (reused, no new resource) |
| `DDB_REGISTRY_TABLE` (alias `DYNAMODB_SOURCE_REGISTRY_TABLE`) | Source registry to DynamoDB |
| `DDB_PERMISSIONS_TABLE` (alias `DYNAMODB_ACCESS_CONTROL_TABLE`) | Per-user permissions to DynamoDB |
| `DDB_DRAFTS_TABLE` (alias `DYNAMODB_DRAFT_VERSIONS_TABLE`) | Draft versions to DynamoDB + S3 `drafts/{id}/v{n}.md` |
| `DDB_UPLOADS_TABLE` | Uploads registry to DynamoDB |
| Feedback / recurring-questions tables | Answer feedback + recurring-questions aggregates to DynamoDB |
| `COGNITO_*` (backend) + `VITE_USE_COGNITO` (frontend) | Cognito Hosted-UI PKCE auth; both required; OFF for demo |
| `FRONTEND_ORIGINS` | Local-dev CORS origins (`config.py::allowed_origins()`); deployed CORS is CDK-driven |
| `VITE_AGENT_BASE_URL` | Routes `/api/chat` + `/api/check-resolution` to the Lambda Function URL (see below) |
| `DYNAMODB_ENDPOINT_URL` | Local DynamoDB endpoint; reaches all stores via `dynamodb_client.get_dynamodb_client()` |

Per-table `DDB_*_TABLE` gating is the **only** config system. `PersistenceSettings`,
`load_persistence_settings`, `StoreFactory`, `APP_ENV`, and `APP_PERSISTENCE_BACKEND` were
deleted — do not reintroduce them. Yaza's `DYNAMODB_*` names survive only as aliases.

`VITE_AGENT_BASE_URL` exists because API Gateway HTTP API has a hard ~29s integration cap that
the multi-agent Bedrock pipeline can exceed; a Lambda Function URL (`auth_type=NONE`, own in-app
Cognito JWT validation, 120s timeout) serves `/api/chat` and `/api/check-resolution` only. Unset,
both fall back to `VITE_API_BASE_URL` — fine locally, would 5xx at ~29s in real AWS.

## Verifier + frozen files

Run the backend tests with the Bedrock env unset (this shell injects Bedrock config via Claude
Code, which flips the app into AWS mode), and build the local index first:

```
python -m backend.scripts.build_index
env -u BEDROCK_KB_ID -u AWS_REGION -u AWS_PROFILE python -m pytest backend/tests -q
cd frontend && npx tsc --noEmit && npm run build
```

Current baseline: **152 backend tests** + tsc clean + vite build.

**Frozen verifier files — must not be modified and must keep passing:**
`backend/tests/conftest.py`, `backend/tests/test_api.py`, `backend/tests/test_ingest_retrieval.py`.

## Decision authority

When docs disagree: the **Notion PRD governs what exists** (features, fields); the archived
**implementation*.md docs governed how it was built** (keys, wiring); **CLAUDE.md records what was
actually done** and wins on any factual dispute about current state, since it is the newest and
most-maintained doc. Settled by council 2026-07-15.

## Living docs vs. archive

**Living (current, maintained):**
- `README.md` — run instructions, demo credentials, "Demo integrity" disclosure.
- `AWS_SETUP.md` — canonical ordered deploy runbook for this repo's CDK stack; env-var → integration table.
- `implementation-aws.md` — teammate onboarding: AWS account access, IAM Identity Center, per-service setup + verify.
- `infra/README.md` — CDK operating manual: Lambda asset roots, bundling, stack-outputs table, teardown policy.
- `backend/rag/README.md` — Alyssa's standalone Bedrock RAG spike (`backend/rag/`) and its boundary from the app.
- `demo workflow.md` — frame-to-frame navigation map (filename has a literal space; supersede its sidebar section with CLAUDE.md's).

**Archived under `docs/archive/` (historical; consult git log for provenance):**
- `spec.md` — original 2026-07-14 customer-demo spec.
- `implementation.md` — original phased local-demo plan (repo-layout tree now stale).
- `implementation2.md` — final AWS-demo migration plan (cut-lines, presentation script).
- `implementation3.md` — 2,229-line PRD round-2 TDD execution plan (12 tasks).
- `lambdaspec.md` — variance-layer spec (severity taxonomy, trigger conditions, 15 open questions).
- `LOOP.md` — prod-branch AWS-readiness loop contract (origin of "dual-mode" + "one stack" rules).
- `frontend-LOOP.md` (was `frontend/LOOP.md`) — 12-frame frontend build-loop methodology + palette hex codes.
- `PROGRESS.md` — frontend build ledger.
- `PROGRESS-AWS.md` — AWS-readiness + implementation3 orchestration log (commit SHAs).
- `updates.md` — implementation3 orchestration ledger (wave plan, cross-task bugs).
- `claude-handoff.md` — mid-task variance handoff; its §9 holds the resolved variance decisions.
- `Yaza_DynamoDB_Work_Summary.md` — Yaza's app-memory branch build record (pre-merge schema).

Note: `backend/app/agents/variance.py` and `infra/stacks/policy_intelligence_stack.py` carry
dense section-number comments citing `lambdaspec.md` and `implementation2.md`/`implementation3.md`.
Those become dangling path references once the files move; update them to `docs/archive/...` if
you touch those source files.

## Locked decisions and deliberate divergences (do not "fix")

- **Sign-in is hardcoded** — two demo accounts in `auth.py`, Cognito later. Reviewer role doubles
  as Admin for the demo; **there is deliberately no third role** (a three-group Cognito mapping is
  an AWS-mode-only concern, not a demo gap).
- **Single 96px icon-rail sidebar**, seven locked items: New chat, Search chats, Drafts, Reviews,
  Conflicts, Topics, Sources. Employees see only New chat / Search chats / Topics; reviewers see
  all seven. Do not reintroduce per-role layouts. `/catalog` is deliberately **not** on the rail —
  it is reached only via links from Topics/Sources.
- **Permission enforcement is identity-opt-in, not identity-required:** absence of identity headers
  silently means no enforcement, by design, to keep the frozen tests green. Headerless local
  requests resolve to `local-reviewer` and pass permission checks.
- **Service-credit / tenure-clock case is answered as *alignment*, not a conflict** — the CBA and
  Handbook genuinely both cap at two years in the supplied text. Manufacturing that conflict would
  violate demo honesty. The WPAF case (Handbook Appendix G vs RES 252644) is the real conflict demo.
- **Variance escalation wording** uses the PRD denied-topic string *"consult your dean, the
  Provost's office, or the appropriate office"* — NOT the customer's rejected "Faculty Affairs /
  Labor Relations" ask (lambdaspec.md §9), which contradicts the governing PRD.
- **`ARCHIVED_EDITION_WEIGHT = 0.5`** — retrieval drops archived sources and down-ranks non-current
  catalog editions by this factor. Registry seeding types corpus sources via `_SEED_TYPE_BY_STEM`
  in `registry.py`, which mirrors `CORPUS_SOURCES` in `infra/scripts/prepare_corpus.py` — a
  two-place taxonomy; keep them in step. Verified split: 3 handbook / 3 cba / 3 policystat / 7 uploads.
- **Guardrail output filters are deliberately looser than input** (see Notion §9) — a blanket HIGH
  would block the harassment/weapons/misconduct policies the assistant exists to explain.
  `PROMPT_ATTACK` output strength must stay `NONE` (the Bedrock API rejects any other value).
- **Two-KB topology (`backend/rag/`) is spike-only.** The app's retrieval seam keeps a single
  `BEDROCK_KB_ID`. Do not copy the two-KB pattern into the app.
- **Do not construct boto3 DynamoDB clients directly** — go through
  `dynamodb_client.get_dynamodb_client()` so `DYNAMODB_ENDPOINT_URL` reaches every store.
- The DynamoDB schema conflict is **settled toward prod** (`id`; `user_email`+`source_type`;
  `draft_id`+numeric `version`); the 7 tables were confirmed empty by Tim 2026-07-15. Do not re-open.

## Known deliberate gaps

Not implemented, on purpose (Notion §9 anti-hallucination list): self-consistency (run detection
2–3× and only surface reproducing conflicts) and negative controls — self-consistency would
triple Bedrock latency against the ~29s API Gateway cap. Deferred per lambdaspec.md §15: a
dedicated variance table (reuses the conflicts table instead), an async log-writer Lambda,
variance on `/api/check-resolution`, and section re-chunking + KB re-ingest. Already implemented:
programmatic span verification (`agents/verification.py`, the PRD's "single biggest lever"), blind
parallel extractors, structured outputs, and abstention.

## Tuning punch-list (soft/arbitrary choices flagged for revisit)

`EMPLOYEE_CONFLICT_GUIDANCE` copy, `POLICY_LINK_KEYWORDS` crawl filter,
`ARCHIVED_EDITION_WEIGHT = 0.5`, and the identity-opt-in permission enforcement. These are the
four spots to look at first if asked to tune the demo further.

## Environment notes

No AWS credentials are configured on this WSL machine — no live-AWS verification has been run from
this repo. Region decision is `us-west-2` for everything. The `backend/rag/` spike carries two
apparently-real Knowledge Base IDs (`HHFJ4IDG9M` academic, `87GR7ILJEF` senate, both `us-west-2`)
and model id `us.anthropic.claude-sonnet-4-5-20250929-v1:0` — recorded as evidence Alyssa has
Bedrock access somewhere, **not verified live from this repo**. Docker is required for `cdk
synth`/`cdk deploy`. The backend does not auto-load `.env`; `source` it explicitly before uvicorn.

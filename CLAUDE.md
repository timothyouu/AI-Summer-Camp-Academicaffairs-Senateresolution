# Project: Policy Intelligence Assistant (AI Summer Camp — Academic Affairs / Senate Resolution)

**Read `PROJECT_SCOPE.md` first** — it is the condensed entry doc (product, architecture, env
gating, verifier, locked decisions, living-docs map). This file holds the working rules and
directives. Full historical narrative lives in `docs/archive/` and `git log`.

## Purpose
Hackathon customer solution for CSUB: a policy search assistant with two role paths. Employees ask
a chatbot policy questions and get cited, conflict-aware answers; policy makers/reviewers check
draft resolutions for overlap/duplicates/conflicts and review a conflict log. **Customer demo
pitched 2026-07-15 — done.** Remaining deadline: hackathon Friday 7AM, on the real AWS architecture.

## Deployment Posture (decided 2026-07-15)
Target is **AWS-real, not local**. Per Tim: only sign-in stays local. On AWS: DynamoDB (conflict
log, uploads, registry, permissions, drafts, feedback, recurring questions), S3 corpus bucket,
Bedrock KB + Titan/Claude, API Gateway + Lambda, Strands agents. Stays local: sign-in only —
hardcoded demo accounts in `auth.py`. **Cognito stays OFF for the demo** even though Notion §9
lists it as core — a deliberate override. The code is AWS-ready today; going non-local is
deployment config, not a code change, because every integration is gated on its own env var. See
`AWS_SETUP.md` for the ordered steps.

**Decision authority when docs disagree:** the **Notion PRD governs what exists** (features,
fields); the archived **implementation*.md governed how it was built** (keys, wiring); **CLAUDE.md
records what was actually done** and wins any dispute about current state. Settled by council
2026-07-15 (`~/COUNCIL.md`).

## Stack
- Frontend: React (Vite, TypeScript strict) + Tailwind CSS.
- Backend: FastAPI (typed Python); Mangum for Lambda (`backend/app/lambda_entry.py`).
- Database: SQLite (conflict log, upload registry) + NumPy/JSON on-disk vector index locally;
  DynamoDB/S3 in AWS mode.
- AI/ML — dual-mode. **Local (default):** `backend/app/llm.py` is the local seam — deterministic
  hash-based embeddings, and its `generate()` deliberately raises, so every route falls back to a
  source-backed deterministic builder and the demo needs zero AWS. `llm.py` holds **no boto3
  Bedrock client — it is not a Bedrock seam.** **AWS mode:** retrieval → Bedrock KB
  (`backend/app/retrieval.py`, `bedrock-agent-runtime.retrieve`, gated on `BEDROCK_KB_ID`; the KB
  embeds with Titan Text Embeddings V2, configured in CDK not app code); generation → Strands SDK
  (`backend/app/agents/factory.py::StrandsLLM` wrapping Bedrock); Bedrock Guardrails attach to
  generation when `BEDROCK_GUARDRAIL_ID` is set. Gemini remains the designated fallback if Bedrock
  access falls through.
- Other: pypdf for PDF extraction.

## Project Structure
- `PROJECT_SCOPE.md` — condensed entry doc; `CLAUDE.md` — this file (working rules).
- `README.md`, `AWS_SETUP.md`, `implementation-aws.md`, `infra/README.md`,
  `backend/rag/README.md`, `demo workflow.md` — living operational docs.
- `docs/archive/` — superseded specs/plans/ledgers (`spec.md`, `implementation.md`,
  `implementation2.md`, `implementation3.md`, `lambdaspec.md`, `LOOP.md`, `frontend-LOOP.md`,
  `PROGRESS.md`, `PROGRESS-AWS.md`, `updates.md`, `claude-handoff.md`,
  `Yaza_DynamoDB_Work_Summary.md`).
- `backend/app/` — FastAPI app: `stores.py` (SQLite/DynamoDB abstraction), `dynamodb_client.py`
  (boto3 resource API), `agents/` (6-agent pipeline + `variance.py`), `registry.py`,
  `permissions.py`, `drafting.py`, `catalog.py`, `feedback.py`, `recurring_questions.py`,
  `retrieval.py`, `lambda_entry.py`. `infra/` — single CDK Python stack.

## Env-Var Gating (summary; full table in AWS_SETUP.md §4 and PROJECT_SCOPE.md)
Per-table `DDB_*_TABLE` gating is the **only** config system. `BEDROCK_KB_ID` flips retrieval to
the KB, disables local indexing, and activates Strands. `BEDROCK_GUARDRAIL_ID` /
`_VERSION` attach the guardrail. `DDB_CONFLICTS_TABLE`, `DDB_REGISTRY_TABLE`,
`DDB_PERMISSIONS_TABLE`, `DDB_DRAFTS_TABLE`, `DDB_UPLOADS_TABLE` flip each store to DynamoDB.
Cognito needs both backend `COGNITO_*` and frontend `VITE_USE_COGNITO` — OFF for the demo.
`FRONTEND_ORIGINS` sets local-dev CORS (`config.py::allowed_origins()`); deployed CORS is
CDK-driven. `VITE_AGENT_BASE_URL` routes `/api/chat` + `/api/check-resolution` to the Lambda
Function URL to dodge API Gateway's ~29s cap (unset → fall back to `VITE_API_BASE_URL`, which 5xxs
at ~29s in real AWS).
- **`PersistenceSettings` / `load_persistence_settings` / `StoreFactory` / `APP_ENV` /
  `APP_PERSISTENCE_BACKEND` are deleted — do not reintroduce.** Yaza's `DYNAMODB_*` names survive
  only as aliases (`DYNAMODB_SOURCE_REGISTRY_TABLE`→registry, `DYNAMODB_ACCESS_CONTROL_TABLE`→
  permissions, `DYNAMODB_DRAFT_VERSIONS_TABLE`→drafts).

## Verifier + Frozen Files
```
python -m backend.scripts.build_index
env -u BEDROCK_KB_ID -u AWS_REGION -u AWS_PROFILE python -m pytest backend/tests -q
cd frontend && npx tsc --noEmit && npm run build
```
Baseline: **152 backend tests** + tsc + vite build. This shell injects Bedrock config via Claude
Code (`CLAUDE_CODE_USE_BEDROCK=1`), which flips the app into AWS mode — run tests with those vars
unset as shown, and build the local index first.

**Frozen verifier files — must not be modified and must keep passing:**
`backend/tests/conftest.py`, `backend/tests/test_api.py`, `backend/tests/test_ingest_retrieval.py`.

## Active Constraints
- **Updated 2026-07-16 — AWS access:** this WSL uses the AWS IAM Identity Center profile
  `csub-senate`; region remains `us-west-2` (Oregon) for everything.
- **Updated 2026-07-16 — real corpus:** `CSUB University_Handbook_2025.pdf` and
  `Unit 3 CBA 2022-2026.pdf` are present in `data/corpus/` and declared in
  `infra/scripts/prepare_corpus.py::CORPUS_SOURCES`.
- **Demo honesty:** synthetic data disclosed to customer; no fabricated "real" sources. The
  `synthetic-*.md` corpus files are disclosed stand-ins — keep the naming. See README.md's "Demo
  integrity" paragraph for the public wording.
- **Sign-in is hardcoded** — two demo accounts in `auth.py` (`reviewer@campus.edu` /
  `employee@campus.edu`, both `demo123`; roles `maker`/`employee`). Reviewer doubles as Admin;
  **there is deliberately no third role** for the demo.
- Orchestration gotcha: the Codex sandbox mounts a worktree's `.git` read-only — Codex workers
  cannot commit; the orchestrator commits.
- **Non-goals (permanent fence):** Senate workflow / Robert's Rules automation, voting/signature
  tracking, a policy-editing suite, legal interpretation, deep archive search, personal-computer
  file ingestion.

## Do-Not-Fix / Locked Decisions
- **Single 96px icon-rail sidebar**, seven locked items (New chat, Search chats, Drafts, Reviews,
  Conflicts, Topics, Sources). Employees see New chat / Search chats / Topics only; reviewers see
  all seven. Do not reintroduce per-role layouts. **`/catalog` is deliberately NOT on the rail** —
  reached only via links from Topics/Sources.
- **Permission enforcement is identity-opt-in, not identity-required:** no identity headers →
  no enforcement, by design, to keep frozen tests green. Headerless local requests resolve to
  `local-reviewer` and pass permission checks (round-2 design).
- **Two-place taxonomy — keep `registry.py` and `infra/scripts/prepare_corpus.py` in step.**
  `registry.py::_SEED_TYPE_BY_STEM` mirrors `CORPUS_SOURCES`; verified split is 3 handbook / 3 cba
  / 3 policystat / 7 uploads. (`prepare_corpus.py`'s second field is an S3 prefix vocabulary, not
  the registry taxonomy — the "rtp/ taxonomy drift" flag was a false positive.)
- **`ARCHIVED_EDITION_WEIGHT = 0.5`** — retrieval drops archived sources and down-ranks
  non-current catalog editions by this factor.
- **Service-credit / tenure-clock case answers as *alignment*, not a conflict** (both sources cap
  at two years in the supplied text; `synthetic-handbook-service-credit.md` says so). The WPAF
  case (Handbook Appendix G vs RES 252644) is the real conflict demo. Do not manufacture the
  service-credit conflict — it would violate demo honesty.
- **Variance escalation wording** = the PRD denied-topic string *"consult your dean, the Provost's
  office, or the appropriate office"*, NOT the customer's rejected "Faculty Affairs / Labor
  Relations" ask (lambdaspec.md §9, which contradicts the governing PRD).
- **Guardrail output filters are deliberately looser than input** (Notion §9) — a blanket HIGH
  would block the harassment/weapons/misconduct policies the assistant explains. `PROMPT_ATTACK`
  output strength must stay `NONE` (Bedrock API rejects any other value).
- **`backend/rag/` two-KB topology is spike-only.** The app keeps a single `BEDROCK_KB_ID`. Do not
  copy the two-KB pattern into the app.
- **Variance `detect_variance` dedups on (source pair, topic)** and abstains unless ≥2 distinct
  grounded sources exist — mirrors the conflict store's idempotence key; the local-index path does
  not attach a variance signal (a reverted attempt, `ee7bb1e`). Do not "fix" either.
- The DynamoDB schema conflict is **settled toward prod** (`id`; `user_email`+`source_type`;
  `draft_id`+numeric `version`); the 7 tables were confirmed empty by Tim 2026-07-15. **Do not
  re-open.**

## DynamoDB / AWS Gotchas
- **Never construct boto3 DynamoDB clients directly** — go through
  `dynamodb_client.get_dynamodb_client()` so `DYNAMODB_ENDPOINT_URL` reaches every store.
- `_ddb_encode` emits `{"N":"True"}` for booleans (`bool` subclasses `int`) — test bools/ints
  first if you extend it; it cannot represent lists, which is why feedback/recurring use the
  resource API.
- `stores._timestamp` must parse Pydantic's trailing `Z` (`datetime.fromisoformat` only accepts it
  on 3.11+; this venv is 3.10) — use it, not `fromisoformat`, at every call site.
- `list_feedback`/`list_questions` use `_scan_all()` (pages to exhaustion, never passes `Limit` to
  a filtered Scan; callers sort then slice) — keep the regression tests.
- CDK builds all 7 tables (`_build_dynamodb_tables`); `setup_dynamodb_tables.sh` is the
  DynamoDB-only path when a full `cdk deploy` is too slow, and refuses to touch a mismatched table.
- Chat logs the recurring question **before** `shape_response_for_role`, so aggregates are
  role-independent. Draft routes are owner-scoped (403 on another user's draft unless `ADMIN_EMAIL`).
- Startup re-indexes the corpus every boot (a persisted index can be stale); AWS mode
  (`BEDROCK_KB_ID`) skips local indexing. `build_chunks` skips unreadable corpus files with a
  warning so a corrupt file can't crash startup.

## Merge & Decision History (condensed — full story in docs/archive/ + git log)
Five real merges landed on `main`/`prod`, each preserving the contributor's commits:
- **Yaza's DynamoDB app-memory** — added answer feedback (`feedback.py`), recurring questions
  (`recurring_questions.py`), `dynamodb_client.py`. Fixed four AWS-only bugs (see gotchas above).
- **PR #4 MVP** (source lifecycle, per-user permissions, citation links, drafting workspace) —
  `drafting.py::llm_revision` keeps the `llm: LLM` first param so revision reaches the pipeline's
  Bedrock LLM, plus the branch's `instruction` param. Draft owner-scoping regression-tested.
- **Feature/rag** (Alyssa's Bedrock RAG spike) — purely additive under `backend/rag/`, nothing in
  `backend/app/` imports it. Config reconciled to env-gated reads. Carries **unverified** KB IDs
  `HHFJ4IDG9M` (academic) / `87GR7ILJEF` (senate), both `us-west-2`, and model
  `us.anthropic.claude-sonnet-4-5-20250929-v1:0` — evidence Alyssa has Bedrock access, not verified
  live from this repo. See `backend/rag/README.md`.
- **Variance layer** (`lambdaspec.md`) — soft "policy variance" re-labeling *over* the pipeline,
  never a fork. `variance.py` derives `authority_rank` from a `doc_type` lookup (cba 100 > handbook
  60 > policystat 40 > catalog 20), no schema change, no LLM pass, reviewer-only. `log_variance`
  reuses the conflict store and downgrades a store failure to a warning. Live-path guards:
  `detect_variance` abstains under 2 sources; `AgentPipeline._verify` rejects unparseable *live*
  verify output (`context_valid=False`) but still accepts deterministic local analyses at 0.75.
- **AWS-readiness conformance pass** — built Bedrock Guardrails from scratch
  (`_build_guardrail()`); fixed drafting→Bedrock, role-switcher identity desync (`setDemoIdentity`
  keeps role+email in sync — if you change one, change both), and registry source-typing; made
  CORS configurable. Corrected the false "all Bedrock in llm.py" claim (it's the local seam).

Code comments in `backend/app/agents/variance.py` and
`infra/stacks/policy_intelligence_stack.py` cite archived docs by section number — update to
`docs/archive/...` if you touch those files.

## Deliberate Gaps
Not built, on purpose (Notion §9): self-consistency (would triple Bedrock latency vs. the ~29s
cap) and negative controls. Deferred per lambdaspec.md §15: a dedicated variance table (reuses the
conflicts table), an async log-writer Lambda, variance on `/api/check-resolution`, section
re-chunking + KB re-ingest. Implemented: programmatic span verification
(`agents/verification.py`, the PRD's "single biggest lever"), blind parallel extractors,
structured outputs, abstention. **Tuning punch-list** (soft choices flagged for revisit):
`EMPLOYEE_CONFLICT_GUIDANCE` copy, `POLICY_LINK_KEYWORDS` filter, `ARCHIVED_EDITION_WEIGHT = 0.5`,
identity-opt-in enforcement.

## Dependencies
Installed locally: fastapi, uvicorn, pypdf, numpy, python-multipart; Vite react-ts, tailwindcss,
react-router-dom. Approved but not yet installed (all imports lazy/guarded — tests pass without
them): boto3, mangum, strands-agents, aws-cdk-lib.

## Answer Synthesis + Generation Gate (2026-07-16, `lambda-variance-spec` branch)
Fixed a response-formatting regression where chat returned **raw retrieved chunks** as the
user-facing answer, and guaranteed helpful natural-language answers for **informational questions**
(which will be extremely common). Scope was **final answer assembly + the generation seam only** —
retrieval, variance thresholds, logging schema, and AWS infra are untouched. Verifier is now
**166 backend tests** (130 + 4 answer-synthesis + 4 informational-guarantee + 3 generation-gate,
minus overlaps; net counted live).
- **Answer prose is now LLM-synthesized from the retrieved passages**, not dumped verbatim.
  `chat.py::_synthesize(question, grounded, llm)` builds a plain-language answer via the pipeline's
  selected LLM under `_SYNTHESIS_SYSTEM` (summarize only supplied text; never "agree"/"align"; no
  conflict/variance commentary — that is appended separately). The banned string
  *"The most relevant supplied policy passages state"* and the `text[:360]` concatenation in
  `_local_index_answer` are **deleted**. When no model is available (local mode, `llm.generate`
  raises by design), both paths return a safe honest message (`_NO_SYNTHESIS_MESSAGE`) with the
  retrieved passages attached **as citations after** the answer — never a raw dump.
- **Informational questions no longer abstain.** `_agent_grounded_answer` previously answered and
  cited **only from extracted normative claims** (must/may/must_not), so "what is the purpose of…"
  questions (no such claims) hit *"could not extract a grounded policy claim… abstained"* with zero
  citations. It now synthesizes from `result.passages` (the full grounded source text) and, when
  there are no claims, derives citations from those passages. Conflict detection still uses claims;
  this governs only the user-facing prose. **Verified end-to-end against real Bedrock** (this shell's
  `converse`): the exact desired Handbook-purpose answer, cited, Handbook-only, no false conflict.
- **Two-gate tripwire CLOSED.** `create_pipeline` previously required `retrieval_aws` **and**
  `strands_available()` for authoritative mode, so naming `BEDROCK_KB_ID` **alone** gave real KB
  retrieval but left generation on `ModuleLLM` (which raises) → still no answers. Now a configured KB
  is sufficient: **Strands when installed, else a direct boto3 Bedrock `converse` seam**
  (`agents/factory.py::BedrockConverseLLM`, model from `BEDROCK_MODEL_ID`, default
  `us.anthropic.claude-sonnet-4-5-20250929-v1:0`; Guardrail attaches when `guardrails_aws`). This
  matches the existing boto3 retrieval seam and the "Gemini/fallback if Bedrock access falls through"
  spirit. `boto3` is a stated dependency; `strands` stays optional.
- **Live requirement for good answers (record this — it is a genuine tripwire):** the product needs
  `BEDROCK_KB_ID` set **+ AWS creds/Bedrock model access**. Strands is now optional (boto3 fallback).
  A KB ID with no model access still degrades to the safe message, not a crash.

## Last Updated
2026-07-16 — **Merged `origin/main` into `lambda-variance-spec` and resolved conflicts favoring the
`lambda-variance-spec` generation design** (KB alone → live answers via Strands or a boto3 `converse`
fallback; fast-model split; bounded Bedrock timeouts). `config.py`, `agents/factory.py`, and the
generation-coupled tests (`test_agents.py`, `test_guardrails.py`, `test_aws_modes.py`) were taken
from HEAD; `origin/main`'s discarded `BEDROCK_GENERATION_ENABLED` / `bedrock_streaming` gate and
`_DeterministicLLM` seam did not survive. `origin/main`'s docs reorg (below) was preserved.

2026-07-16 — **Docs reorganization** (from `origin/main`). Added `PROJECT_SCOPE.md` (the condensed
cold-start entry doc) and rewrote this `CLAUDE.md` down under 15KB, preserving every load-bearing
fact while compressing the five per-session merge narratives (DynamoDB, PR #4, feature/rag, variance,
conformance pass) into the "Merge & Decision History" section. Historical specs/plans/ledgers moved
to `docs/archive/`; living docs stayed in place. See `PROJECT_SCOPE.md` for the full
living-vs-archive map and `git log` for prior per-session detail.

Previous: 2026-07-16 — Answer synthesis + generation-gate fix on `lambda-variance-spec`: chat no longer dumps
raw retrieved chunks; informational questions get LLM-synthesized cited answers instead of abstaining
(verified against real Bedrock); the KB-without-Strands tripwire is closed via a boto3 `converse`
fallback. Verifier now **166 backend tests**. See the Answer Synthesis + Generation Gate section.

Previous: 2026-07-16 — Fixed two live-only variance defects on the `lambda-variance-spec` branch (no-variance false positive from a single grounded source; `_verify` 500 on a non-object verifier response). Verifier now **130 backend tests**. See the Variance Layer section.

Previous: 2026-07-16 — Merged teammate PR #4 (source lifecycle, per-user permissions, citation links, persistent
drafting workspace) into `main` and `prod`, resolved the `llm_revision` conflict, fixed merge seams,
added draft owner scoping + S3 draft-copy regression test. See the Teammate MVP Branch Merge section.

Previous: 2026-07-16 — Added `implementation-aws.md`: a team-facing AWS account/service setup guide (account
access via IAM Identity Center, per-service enable steps + IAM permissions + verification commands
for S3, Bedrock model access/Knowledge Bases/OpenSearch Serverless/Guardrails, DynamoDB, Cognito,
Lambda + API Gateway, Amplify, EventBridge). It's onboarding-oriented (get a new teammate to
working AWS access); `AWS_SETUP.md` remains the canonical ordered deploy runbook for this repo's
own stack — the two overlap by design and should be reconciled or merged later rather than treated
as duplicates. Committed and pushed directly to `prod` (`8c256fb`) rather than merged — the same
doc was independently committed and pushed to `demo` (`97afef6`, then `5512dd2` for this note);
`prod`'s CLAUDE.md has diverged too far from `demo`'s for a merge to make sense here.

Previous: 2026-07-15 (late) — AWS-readiness conformance pass: Bedrock Guardrails built from scratch, role-switcher
 identity desync + registry source-type fixes,
drafting→Bedrock defect fixed, CORS made configurable, false llm.py/Bedrock Stack claim corrected.
See the AWS-Readiness Conformance Pass section.

Previous: 2026-07-15 (evening) — Merged Yaza's DynamoDB app-memory branch into prod (feedback + recurring questions added; prod key schemas kept; single DDB_* config system; four AWS-only bugs fixed; stale README deploy instructions rewritten). Recorded post-pitch AWS-first deployment posture. See the DynamoDB App-Memory Merge section.

Previous: 2026-07-15 — PRD round-2 implementation documented, including source lifecycle and permissions UI, shared resource catalog, drafting assistant, live current/archive catalog smoke results, dark-mode/navigation, and AWS infrastructure.

2026-07-14 (evening) — Sidebar unified to one icon rail with persisted role + Library→Search chats (see Sidebar Unification section); verified via tsc, vite build, and Playwright click-through of both roles.

Previous: 2026-07-14 (later) — Frontend COMPLETE and verified: 12 pages (`frontend/src/pages/`), shared layout/sidebar/role-switcher components, typed mocks (`src/data/mock.ts`) behind `src/api.ts`. Verified via tsc --strict, vite build, and a Playwright click-through of all 6 demo paths plus frame-by-frame screenshot judgment (see PROGRESS.md, incl. WSL screenshot workaround). Run with `cd frontend && npm run dev`. Backend still not built.

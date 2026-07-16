# Project: Policy Intelligence Assistant (AI Summer Camp — Academic Affairs / Senate Resolution)

## Purpose
Hackathon customer solution for a university (CSUB): a policy search assistant with two role paths — employees ask a chatbot policy questions and get cited, conflict-aware answers; policy makers/reviewers check draft resolutions for overlap/duplicates/conflicts and review a conflict log. See `spec.md` (what/why) and `implementation.md` (how). **Customer demo was pitched 2026-07-15 — done.** Remaining deadline: hackathon Friday 7AM, presented on the real AWS architecture (implementation2.md §1).

## Deployment Posture (decided 2026-07-15, after the customer pitch)
Target is **AWS-real, not local**. Per Tim: "I want most of it to not be local. One of the few things that are local will just be purely the sign in, and anything within Notion that I did not list."
- **On AWS** (Notion §9 Core Services): DynamoDB (conflict log, uploads, registry, permissions, drafts, feedback, recurring questions), S3 corpus bucket, Bedrock KB + Titan/Claude, API Gateway + Lambda, Strands agents.
- **Stays local**: sign-in only — hardcoded demo accounts in `auth.py`. Cognito stays OFF (matches implementation3.md's "Cognito stays OFF for the demo"), even though Notion §9 lists it as core. This is a deliberate override.
- The code is AWS-ready today; going non-local is *deployment config*, not a code change. Every integration is gated on its own env var, so nothing flips until a table/bucket is named. See `AWS_SETUP.md` for the ordered steps.
- Decision authority when docs disagree: the **Notion PRD governs what exists** (features, fields); **implementation*.md governs how it is built** (keys, wiring). Settled by council 2026-07-15 — see `~/COUNCIL.md` log.

## Stack
- Frontend: React (Vite, TypeScript strict) + Tailwind CSS
- Backend: FastAPI (Python, typed)
- Database: SQLite (conflict log, upload registry); NumPy + JSON on-disk vector index
- AI/ML: dual-mode. **Local (default):** `backend/app/llm.py` builds deterministic hash-based embeddings, and its `generate()` deliberately raises — every route falls back to a source-backed deterministic builder, so the demo needs zero AWS. **AWS mode:** retrieval goes to a Bedrock Knowledge Base (`backend/app/retrieval.py`, `bedrock-agent-runtime.retrieve`, gated on `BEDROCK_KB_ID`); the KB does its own embedding with Titan Text Embeddings V2 (configured in the CDK stack, not in app code); generation goes through the Strands SDK (`backend/app/agents/factory.py::StrandsLLM`), which wraps Bedrock; Bedrock Guardrails attach to that generation when `BEDROCK_GUARDRAIL_ID` is set. Note: `llm.py` is the *local* seam, **not** a Bedrock client — no boto3 Bedrock call lives there. (Gemini remains the designated fallback if Bedrock access falls through.)
- Other: pypdf for PDF extraction

## Project Structure
- `spec.md` — demo spec, scope decisions, success criteria, assumptions
- `implementation.md` — phased plan, repo layout, verification steps
- `demo workflow.md` — frame-to-frame navigation map for the 12 UI frames (source of truth for routing)
- `PROGRESS.md` — frontend build task ledger (statuses so Claude/Codex can resume cold)
- `frontend/` — Vite + React-TS (strict) + Tailwind 3.4 SPA; hand-written scaffold (no `npm create`), `frontend/LOOP.md` holds the build-loop methodology
- `backend/`, `data/` — per the layout in implementation.md (not yet scaffolded)

## Architecture Notes
- Local-first demo deliberately mirroring the PRD's AWS target (FastAPI⇄API Gateway/Lambda, data/corpus⇄S3, NumPy index⇄Bedrock KB) so it ports without a rewrite.
- Sign-in is intentionally hardcoded (two demo accounts in `auth.py`) — agreed shortcut for the demo; Cognito later.
- Synthetic corpus files (`data/corpus/synthetic-*.md`) exist to make the PRD calibration cases fire deterministically; they are disclosed stand-ins, keep the naming.
- Conflict display decision: contextual flagging in chat + everything accumulates in the maker conflict log.

## Active Constraints
- No AWS credentials configured on this WSL machine yet (Phase 0 blocker — Tim must run aws configure/login and verify Bedrock model access). `aws` CLI v2.35 is installed but `aws configure list-profiles` returns nothing; the `csub-policy` profile used to provision the app-memory tables lives on Yaza's machine, so **no live-AWS verification has been run from this repo**.
- Handbook PDF not yet in `data/corpus/`; CBA source: `/mnt/c/Users/timot/Downloads/Unit 3 CBA 2022-2026.pdf`.
- Demo honesty: synthetic data disclosed to customer; no fabricated "real" sources.

## Dependencies
Planned (not yet installed — needs Tim's approval): fastapi, uvicorn, boto3, pypdf, numpy, python-multipart; Vite react-ts scaffold, tailwindcss, react-router-dom.

## Frontend Decisions (2026-07-14)
- Frontend-only for now: all content from typed mocks in `src/data/mock.ts` behind a typed `src/api.ts` facade shaped like implementation.md's endpoints (backend swap later touches one file).
- Design source of truth: 12 frame PNGs at `/mnt/c/Users/timot/.codex/generated_images/019f62e2-8e7b-7702-852c-c8336fb4affa/`; fidelity bar is close match, not pixel-diff.
- CSUB shield logo is a hand-built SVG approximation (`src/components/Logo.tsx`), not the official asset.
- Build orchestrated via Codex subagents (gpt-5.6-sol for complex pages, gpt-5.6-terra for simpler ones); Claude orchestrates and verifies with Playwright.

## Sidebar Unification (2026-07-14, evening)
- Single 96px icon-rail sidebar for both roles (the old wide 256px reviewer variant is deleted). Item order: New chat, Search chats, Drafts, Reviews, Conflicts, Topics, Sources — employee role shows only New chat / Search chats / Topics; reviewer shows all seven. Decided with Tim via alignment questions; do not reintroduce per-role layouts.
- Role now persists via RoleProvider (localStorage) instead of being forced by the route: shared routes (/chats, /chats/:id, /library, /topics, /topics/:slug) render under the current role (`SharedRoute` in App.tsx); maker-only routes still force reviewer (`WorkspaceRoute`).
- /library page is now "Search chats" (chats-only searchable history; Saved policies tab removed). The route and file name Library.tsx are unchanged.
- Note: `demo workflow.md`'s frame map predates this unification; the sidebar behavior above supersedes it where they conflict.

## AWS Readiness (prod branch, 2026-07-15)
- Branch `prod` (off `demo`) implements implementation2.md code-side: everything runs locally with zero AWS, and each integration flips to AWS via env vars — see `AWS_SETUP.md` (ordered manual steps) and `LOOP.md` (locked decisions). Verifier: `backend/.venv/bin/python -m pytest backend/tests -q` + `cd frontend && npx tsc --noEmit && npm run build`. (The "17 tests" figure once here was long stale — see the merge section below for the current count.)
- New: `backend/app/stores.py` (SQLite/DynamoDB store abstraction), `backend/app/agents/` (Notion-design 6-agent conflict pipeline with `agent_trace` output; Strands SDK activates when `strands` importable + `BEDROCK_KB_ID` set), `backend/app/lambda_entry.py` (Mangum), `backend/lambda_handlers/ingestion.py` (S3→KB sync), `infra/` (CDK Python stack, see infra/README.md), `frontend/src/auth/cognito.ts` + `AuthCallback.tsx` (Hosted UI PKCE behind `VITE_USE_COGNITO` — zero new npm deps; aws-amplify deliberately not used), `frontend/src/components/AgentActivity.tsx` (trace panel).
- Not yet installed (approved, pending Tim): boto3, mangum, strands-agents, aws-cdk-lib. All such imports are lazy/guarded; tests must keep passing without them.

## PRD Round-2 (2026-07-15)

- Source lifecycle is backed by a dual-mode SQLite/DynamoDB registry (`GET /api/sources`, `POST /api/sources/{id}/status`). Corpus seeds start active; documents arriving through uploads start archived. Retrieval drops archived sources after retrieval and down-ranks non-current catalog editions by 0.5.
- Source permissions attach per user and source type (`handbook`, `cba`, `policystat`, `catalog`, `uploads`) with independent `can_add` / `can_edit` flags. The demo reviewer is the admin and is seeded with full access; identified uploads require the `uploads` add grant. Local identity comes from `X-User-Email`; verified Cognito claims take over when Cognito is configured.
- Conflict responses are role-shaped: employees receive non-clickable escalation guidance with raw conflict sources and IDs removed, while reviewers retain full detail. Local role comes from `X-Role` and defaults to reviewer for compatibility; Cognito claims are authoritative in AWS mode.
- The reviewer-only drafting workspace supports save, list/reopen, conversational revisions, status, version history, unified comparison, and restore-as-new-version. Draft versions use SQLite locally or DynamoDB/S3 when `DDB_DRAFTS_TABLE` is set, with a deterministic zero-Bedrock fallback.
- Catalog ingestion is stdlib-only (`urllib.request` + `html.parser`). Run the current catalog plus exactly one archived edition through `backend/scripts/scrape_catalog.py` or the manually invoked `CatalogScraperFn`; edition metadata drives the retrieval weighting above.
- Frontend API bindings for registry, permissions, drafting, demo identity, and role headers are complete. The shared `/catalog` page is available to both roles; employees see active sources only, while reviewers also see lifecycle status. The Sources page supports archive/unarchive and per-source-type permissions. The reviewer Drafts page is a persistent drafting workspace, and the Resolution Checker mounts the same instruction-driven Draft Assistant.
- Dark mode uses CSS variables, defaults to light, persists in localStorage, and is controlled from the sidebar gear's settings popover. Shared back buttons are wired, and the sidebar emblem navigates to `/login`.
- AWS round-2 resources are independently env-gated with `DDB_REGISTRY_TABLE`, `DDB_PERMISSIONS_TABLE`, and `DDB_DRAFTS_TABLE`. Cognito stays optional and OFF for the demo unless both backend `COGNITO_*` values and frontend `VITE_USE_COGNITO` settings are enabled.

## DynamoDB App-Memory Merge (2026-07-15)
`integration/yaza-dynamodb-app-memory` (Yaza Myo Tun's work, originally branched off `demo`) is merged into `prod` as a real merge commit — his commits are in the history, not squashed. Verifier is now **107 backend tests** (was 87 pre-merge) + `cd frontend && npx tsc --noEmit && npm run build`.
- **New from that branch:** answer feedback (`backend/app/feedback.py`, `POST/GET /api/feedback`, wired-up thumbs in `ChatAnswer.tsx` — previously dead UI), recurring questions (`backend/app/recurring_questions.py`, `GET /api/recurring-questions`, chat `answer_id`), `backend/app/dynamodb_client.py` (boto3 *resource* API — required because feedback/recurring records hold lists that `_ddb_encode` cannot represent), and `scripts/setup_dynamodb_tables.sh` / `verify_dynamodb_tables.sh`. These cover the Notion Should-Have items "Answer feedback" and "Recurring questions hub".
- **Schema conflict resolved toward prod.** Both sides built conflicts/registry/permissions/drafts with incompatible keys. Prod's won (`id`; `user_email`+`source_type`; `draft_id`+numeric `version`) because those APIs and tests already worked and the AWS tables held no data. **Confirmed empty by Tim 2026-07-15** — and empty by construction for three of the four, since Yaza's §10 lists the access-control/source-registry/draft-version APIs as never implemented, so no code could write to them. Only `policy-intelligence-conflicts` could hold his manual test records, which `DEMO_CONFLICTS` + `backend/scripts/seed_conflicts.py` regenerate. The two tables that took real writes (feedback, recurring questions) kept their schemas, so their data was never at risk. **This question is settled — do not re-open it.** The scripts were retargeted; `policy-intelligence-uploads` added (the app-memory set lacked it).
- **One config system.** Per-table `DDB_*_TABLE` gating only. `PersistenceSettings` / `load_persistence_settings` / `StoreFactory` / `APP_ENV` / `APP_PERSISTENCE_BACKEND` are **deleted — do not reintroduce**. Yaza's `DYNAMODB_*` names survive as aliases in `get_settings()` (`DYNAMODB_SOURCE_REGISTRY_TABLE`→registry, `DYNAMODB_ACCESS_CONTROL_TABLE`→permissions, `DYNAMODB_DRAFT_VERSIONS_TABLE`→drafts) so his runbook still works.
- **CDK creates all 7 tables** (`_build_dynamodb_tables`); it does not import script-provisioned ones, because CloudFormation cannot adopt them. `setup_dynamodb_tables.sh` is the DynamoDB-only path for when a full `cdk deploy` (OpenSearch Serverless + Bedrock KB) is too slow/costly; it verifies key schemas and refuses to touch a mismatched table rather than silently leaving one the backend cannot read.
- **Latent bugs fixed (all AWS-only — none reachable on the SQLite path):**
  - `_timestamp` couldn't parse Pydantic's trailing `Z` (`datetime.fromisoformat` only accepts it on 3.11+; this venv is 3.10).
  - `_ddb_encode` emitted `{"N": "True"}` for booleans since `bool` subclasses `int`. Test bools/ints first if you extend it; it still cannot represent lists — that's why feedback/recurring use the resource API instead.
  - `list_feedback`/`list_questions` passed `Limit` to a **filtered** Scan and ignored `LastEvaluatedKey`. DynamoDB applies `Limit` to items *evaluated*, before filtering, so matches beyond the first page vanished silently. Both now use `_scan_all()`, which pages to exhaustion and never passes `Limit`; callers sort then slice. Regression tests in `test_feedback.py` fail against the old code — keep them.
  - All five low-level stores built `boto3.client("dynamodb", ...)` directly, so `DYNAMODB_ENDPOINT_URL` reached only 2 of 7 stores. Every store now goes through `dynamodb_client.get_dynamodb_client()`; **do not construct boto3 DynamoDB clients directly.**
- Found by a Codex review pass, which also caught that `README.md`'s DynamoDB section still documented the deleted `APP_ENV`/`APP_PERSISTENCE_BACKEND` switch and told operators to create the conflict table with a `conflict_id` key — both would have broken a real deploy. Section rewritten.
- Chat logs the recurring question **before** `shape_response_for_role`, so aggregates are role-independent.
- Stale doc warning: `Yaza_DynamoDB_Work_Summary.md` §3/§4/§7/§10/§11 describe the pre-merge design. Its top integration note is current; the body is kept as his build record.

## AWS-Readiness Conformance Pass (2026-07-15, late)
Audited the app against the Notion PRD + implementation2.md for "ready to connect to AWS".
The baseline was already green (107 tests, tsc clean, vite build), so these were conformance
and wiring gaps, not build breaks. Verifier is now **113 backend tests** (107 baseline, +2 drafting
regression, +3 guardrail gating, +1 registry source-type).
- **Bedrock Guardrails implemented — they did not exist at all** (`grep -ri guardrail` returned
  zero hits repo-wide despite Notion §9 specifying them in full). `infra/stacks/policy_intelligence_stack.py::_build_guardrail()`
  creates a `CfnGuardrail` + `CfnGuardrailVersion`: content filters (hate HIGH/MEDIUM, insults
  MEDIUM/LOW, sexual HIGH/LOW, violence HIGH/MEDIUM, misconduct MEDIUM/LOW, prompt-attack
  HIGH/NONE), all 8 denied topics, contextual grounding at 0.80, PII `ANONYMIZE`, and the PRD's
  verbatim blocked message. Gated by `BEDROCK_GUARDRAIL_ID` / `BEDROCK_GUARDRAIL_VERSION`
  (`Settings.guardrails_aws`); `StrandsLLM` builds a `BedrockModel` with the guardrail when set
  and is byte-for-byte unchanged when unset. **Output filters are deliberately looser than input**
  — a blanket HIGH would block the harassment/weapons/misconduct policies the assistant exists
  to explain. Do not "harden" them without re-reading Notion §9.
  - `PROMPT_ATTACK` output strength must stay `NONE`; the Bedrock API rejects any other value.
- **Fixed: AI-assisted drafting could never reach Bedrock.** `drafting.py::llm_revision` imported
  the module-level `llm.generate` (which always raises by design) instead of using the pipeline's
  selected LLM, so `revise_draft`'s `except Exception` silently fell back to deterministic text even
  with Strands + KB fully configured. It now takes an `LLM` param and `revise_draft` passes
  `pipeline.llm`. Regression tests in `test_drafting.py` fail against the old code — keep them.
- **CORS is now configurable** via `FRONTEND_ORIGINS` (`config.py::allowed_origins()`); it was
  hardcoded to four localhost origins, which broke any second worktree on a non-default Vite port.
  Defaults unchanged. Deployed CORS is unaffected — API Gateway + the Lambda Function URL handle
  it from `cdk deploy -c frontendOrigin=...`, so this seam is local-dev only.
- **Corrected a false Stack claim.** CLAUDE.md said "all Bedrock calls isolated in `llm.py` — Titan
  V2 + Claude Converse API". Untrue: `llm.py` is the *local* seam (hash embeddings; `generate()`
  raises) and holds no boto3 Bedrock client. Real Bedrock calls live in `retrieval.py` (KB
  `retrieve`) and via Strands in `agents/factory.py`; Titan V2 embedding is the KB's, configured in CDK.
- **Fixed: the in-app role switcher desynced identity from role.** `require_reviewer` resolves the
  demo role from `X-User-Email` **in preference to** `X-Role` (an if/elif chain in `auth.py`), but
  `RoleSwitcher.changeRole` only called `setRole()` and left `policy-intelligence.user-email` at
  whatever login stored. So logging in as Employee and clicking the prominent "Policy Maker view"
  button gave a reviewer *view* with an employee *identity* → every reviewer-only endpoint 403'd
  (`/api/permissions`, `/api/conflicts`), and Sources showed "No grants yet". `api.ts` now exports
  `setDemoIdentity(role)` / `demoEmailForRole(role)`, used by both `login()` and the switcher, so the
  two can't drift. Verified in-browser: employee → Policy Maker view now yields zero console errors
  and a populated permissions table. **If you change one, change both** — or keep using the helper.
- **Fixed: local registry seeding typed every corpus source as `uploads`.** `register_document`
  whitelists `source_type` to {handbook, cba, policystat, catalog, uploads}, but corpus front matter
  carries prose ("handbook excerpt") and PDFs carry none, so all 16 seeds silently degraded to
  `uploads` (Handbook shown as "UPLOADS", per-source-type permissions undemoable). `registry.py`
  now has `_SEED_TYPE_BY_STEM` mirroring the AWS authority in `infra/scripts/prepare_corpus.py`
  (`CORPUS_SOURCES`), applied by `seed_registry_from_corpus`. Verified live: counts became
  3 handbook / 3 cba / 3 policystat / 7 uploads. **Two-place taxonomy — keep registry.py and
  prepare_corpus.py in step.** (Tim chose this over editing corpus front matter, which wouldn't help PDFs.)
- **Verified in-browser (local, zero AWS)**: both roles across /login, /chats, /chats/:id, /library,
  /topics, /catalog, /sources, /conflicts, /reviews, /review, /drafts — zero console errors after the
  fix. Role-gated conflicts confirmed at the API: reviewer gets `sources` + `conflict_id`; employee
  gets the softened escalation with both stripped. PRD calibration case #2 (new AI policy) passes —
  it flags existing coverage and recommends amending, with the full 6-agent trace rendered.
- **PRD divergence, deliberate — do not "fix"**: Notion §7's headline calibration case expects
  *service credit toward the tenure clock* to be a CBA-vs-Handbook **conflict**. The app answers that
  the two sources **align** (both cap at two years), because they genuinely do in the supplied text.
  `data/corpus/synthetic-handbook-service-credit.md` says so explicitly: "It is intentionally not
  labeled a conflict." Manufacturing that conflict would violate the demo-honesty constraint. The
  WPAF case (Handbook Appendix G vs RES 252644) is the one that demos a real conflict.
- **Known deliberate gaps** (Notion §9 anti-hallucination list): self-consistency (run detection
  2–3× and only surface conflicts that reproduce) and negative controls are NOT implemented.
  Self-consistency would triple Bedrock latency against API Gateway's ~29s cap — hence
  `VITE_AGENT_BASE_URL`. Implemented already: programmatic span verification (`agents/verification.py`,
  the PRD's "single biggest lever"), blind parallel extractors, structured outputs, abstention.

## Last Updated
2026-07-16 — Added `implementation-aws.md`: a team-facing AWS account/service setup guide (account
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

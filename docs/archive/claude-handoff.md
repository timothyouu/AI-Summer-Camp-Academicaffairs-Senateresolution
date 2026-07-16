# Claude Handoff — Policy Variance Lambda Work

_Last updated: 2026-07-15. This file lets a fresh Claude session continue the
"policy variance detection" work without the prior chat history._

## 1. Project goal
Policy Intelligence Assistant for CSUB (hackathon customer solution). Two role paths:
- **Employees** ask a chatbot policy questions and get cited, conflict-aware answers.
- **Policy makers / reviewers** check draft resolutions for overlap/duplicates/conflicts
  and review a conflict log.

Customer demo was pitched 2026-07-15 (done). Remaining deadline: hackathon Friday 7AM,
presented on the real AWS architecture. Deployment posture is **AWS-real, not local**
(only sign-in stays local; Cognito stays OFF for the demo). The code is AWS-ready today;
going non-local is deployment config, not a code change — every integration is env-gated.

**Current sub-task:** implement the "policy variance" layer described in `lambdaspec.md`.
A plan has been agreed and three open decisions resolved (see §6, §9, §10). **No variance
code has been written yet** — only the spec exists and was refined.

## 2. Current branch
`lambda-variance-spec` (off `main`). Working tree is clean. Most recent commit:
`8c61ca9 add lambda variance implementation spec` (this committed `lambdaspec.md`
including the refinements described below).

## 3. Important docs to read first (in order)
1. `CLAUDE.md` — project instructions, stack, deployment posture, decision authority
   (Notion PRD governs *what exists*; `implementation*.md` govern *how it is built*).
   Also documents the DynamoDB app-memory merge and the frozen-verifier rule.
2. `lambdaspec.md` — the spec this work implements (see §4 below).
3. `implementation3.md` — newest/highest implementation doc; PRD round-2 plan. Its
   task structure, dual-mode store pattern, and frozen-file rules are the template to follow.
4. `implementation2.md` — AWS-readiness code-side plan (Lambda, KB, ingestion, cut lines).
5. `spec.md` / `implementation.md` — original demo scope.

## 4. What lambdaspec.md says (high level)
Defines the **Lambda-side behavior** for detecting, surfacing, and logging **policy
variance** across retrieved RAG results. Spec only — it changes no code. Key points:
- **Reuse, don't fork.** Layer variance over the existing 6-agent pipeline
  (`backend/app/agents/`) and the existing conflict log (`policy-intelligence-conflicts`
  DynamoDB table). The variance module reads `PipelineResult` and re-labels; it does not
  re-implement retrieval or verification.
- **Softer vocabulary + richer taxonomy.** User-facing text says "variance," not
  "conflict." Seven severity categories (`DIRECT_CONTRADICTION`, `DEADLINE_MISMATCH`,
  `ELIGIBILITY_MISMATCH`, `AUTHORITY_MISMATCH`, `OMISSION_OF_RIGHT_OR_PROTECTION`,
  `NUMERIC_MISMATCH`, `TERMINOLOGY_MISMATCH`) mapped onto the existing 4-value
  `ConflictTypology`.
- **Customer's headline case:** one source silent on an allowance, another grants a
  three-month extension → must fire as `DEADLINE_MISMATCH`/`OMISSION_OF_RIGHT_OR_PROTECTION`
  (soft language, still logged). The current pipeline treats this as a `gap` and would not fire.
- **Role-shaped output:** employees get soft escalation guidance only (no sources, no ids,
  no spans, no authority level); reviewers get full detail.
- **RAG tuning (added during refinement):** retrieval breadth raised to **k = 12–15**
  (a narrow top-k misses one side of a divergence); chunk by section/article; carry
  `authority_rank`/`effective_date` metadata (derived, reviewer-only).
- **MVP scope:** in-process module inside the existing request Lambda; no new deployable,
  no new table, no new dependency, no new IAM. Reuse `conflict_store().create_or_get`
  (idempotent) for logging.
- **§15 Open Questions** flag every place the customer ask diverges from the code and/or PRD.

## 5. Files changed so far
- `lambdaspec.md` — created and refined (committed in `8c61ca9`). Refinements added:
  §6 retrieval breadth (k=12–15) + section/article chunking + §6 item 2a derived
  `authority_rank`/`effective_date`; §7 wide-k + topic normalization; §5.2/§8/§10 authority
  fields (reviewer-only); §9 rule 4 hides authority from employees; §13 tests 11a + 14a;
  §15 Q11 (hybrid/rerank — defer), Q12 (re-ingest ownership), Q13 (authority display —
  RESOLVED reviewer-only).
- `claude-handoff.md` — this file.

**No application/backend code has been changed.** No commits touch `backend/`.

## 6. What has been implemented (already in the repo, reused by this work)
- 6-agent pipeline: `backend/app/agents/pipeline.py` (`AgentPipeline.run()` → `PipelineResult`
  with `verified_conflicts`, `analyses`, `escalation`, `agent_trace`). Blind per-source
  extraction → same-topic comparison → verification → escalation. Abstains, never fabricates.
- Schemas: `backend/app/agents/schemas.py` (`ConflictAnalysis`, `ConflictTypology` = 4 values
  + `none`, `Claim`, `VerifiedConflict`, `GroundedPassage`).
- Chat: `backend/app/chat.py` — `/api/chat`, `shape_response_for_role()` (already strips
  sources/ids/spans for employees — reused unchanged), `resolve_request_role()`,
  `_agent_grounded_answer()`, `_local_index_answer()` (retrieves `search(k=6)`).
- Conflict log: `backend/app/stores.py` `conflict_store()` (dual-mode SQLite/DynamoDB),
  `create_or_get` (idempotent on source pair + topic + description);
  `backend/app/conflicts.py` (`ConflictSignal` wire mapping, demo seed).
- Retrieval: `backend/app/retrieval.py` — `search()` (over-fetches `k*2`, applies registry
  filter), `_search_knowledge_base()` (Bedrock KB when `BEDROCK_KB_ID` set),
  `apply_registry_policy()` (drops archived, down-ranks non-current × 0.5). Pipeline retrieves
  at `k=10`.
- Lambda entry: `backend/app/lambda_entry.py` (Mangum → FastAPI, guarded import).
- Infra: `infra/stacks/policy_intelligence_stack.py` **already creates all 7 DynamoDB tables**
  and **already grants the API Lambda** `bedrock:Retrieve`, `bedrock:InvokeModel`/`Converse`,
  and `grant_read_write_data` on the conflicts table. So the variance MVP needs **zero new
  infra or IAM.**

## 7. What still needs to be implemented (the agreed plan)
**New files:**
- `backend/app/agents/variance.py`:
  - `VarianceSeverity` (Literal, 7 values), `VarianceItem`, `VarianceReport` (Pydantic).
  - `classify_severity(analysis) -> VarianceSeverity` — **pure**, unit-testable, no AWS.
  - `detect_variance(question, result: PipelineResult) -> VarianceReport` — reads pipeline
    output, classifies accepted contradictions + the guarded omission rule, builds soft language.
  - `soft_language(report, role)`, `log_variance(report)` (via `conflict_store().create_or_get`).
  - `VARIANCE_ESCALATION = "…consult your dean, the Provost's office, or the appropriate office."`
    (PRD denied-topic string — see §9 decision).
- `backend/tests/test_variance.py` — spec §13 cases (classification 1–7, shaping 8–11 + 11a,
  guardrails 12–14, retrieval breadth 14a, logging 15–16, fallback 17). Zero-AWS, mock
  `llm.generate`, follow the `RecordingLLM`/`MemoryStore` pattern in `test_agents.py`.

**Modified files:**
- `backend/app/chat.py` — call `detect_variance()` on the agent-grounded path; attach soft
  summary + escalation to `ConflictSignal.guidance`; log the variance record. Raise
  `search(k=6)` → `k=12`.
- `backend/app/agents/pipeline.py` — raise `search(topic, k=10)` → `k=12` (one line).
- `backend/app/retrieval.py` + `backend/app/agents/schemas.py` — add **defaulted, backward-
  compatible** `authority_rank`/`effective_date` to `SearchResult`/`GroundedPassage`, derived
  from `doc_type` + registry (no LLM). Carried into `VarianceItem`, stripped from the employee
  payload by the existing `shape_response_for_role`.
- `CLAUDE.md` — add a "Variance Layer" section; update the test count (107 → ~124) and
  Last Updated.

**Smallest MVP vertical slice (do this first):** `variance.py` with `classify_severity` +
`VarianceReport`; wire into the agent-grounded chat path only; raise the two `k` values;
`test_variance.py` for classification + employee/reviewer shaping + k regression guard.

**Deferred per §15 (do NOT build now):** dedicated variance table (Q4), async log-writer
Lambda (Q6), variance on `/api/check-resolution` (Q7), self-consistency N-run gate (Q10),
hybrid search / reranking (Q11), section re-chunking + KB re-ingest (Q12 — needs live AWS
this repo cannot run).

## 8. Known AWS resources and environment variables
**No new env vars or IAM are needed for the variance MVP.** It reuses:
- `BEDROCK_KB_ID` — turns on Bedrock KB retrieval (`settings.retrieval_aws`); unset → local
  NumPy index.
- `DDB_CONFLICTS_TABLE` (alias `DYNAMODB_CONFLICTS_TABLE`) — turns on the DynamoDB conflict/
  variance log (`settings.conflicts_aws`); unset → SQLite.
- Other existing per-table gates (all in `backend/app/config.py`): `DDB_UPLOADS_TABLE`,
  `DDB_REGISTRY_TABLE`, `DDB_PERMISSIONS_TABLE`, `DDB_DRAFTS_TABLE`, `DDB_FEEDBACK_TABLE`,
  `DDB_RECURRING_QUESTIONS_TABLE`, `CORPUS_BUCKET`, `COGNITO_USER_POOL_ID`/`COGNITO_CLIENT_ID`
  (Cognito OFF for demo), `AWS_REGION`, `DYNAMODB_ENDPOINT_URL`.
- **Config system:** one system only — per-table `DDB_*_TABLE` gating. Do NOT reintroduce
  `PersistenceSettings`/`APP_ENV`/`APP_PERSISTENCE_BACKEND` (deleted). `DYNAMODB_*` names
  survive as aliases.
- **DynamoDB tables (all 7 created by CDK):** `policy-intelligence-conflicts` (key `id`),
  uploads, registry, permissions (`user_email`+`source_type`), drafts (`draft_id`+numeric
  `version`), feedback, recurring-questions. Confirmed empty by Tim 2026-07-15.

## 9. Known blockers and open team questions
- **No live-AWS verification from this repo.** No AWS credentials on this machine; `aws
  configure list-profiles` returns nothing. The `csub-policy` provisioning profile lives on
  a teammate's (Yaza's) machine. Everything must pass with **zero AWS** (frozen-verifier rule).
- **Frozen files — never modify, must stay green:** `backend/tests/conftest.py`,
  `backend/tests/test_api.py`, `backend/tests/test_ingest_retrieval.py`. Behavior with no
  identity headers and no AWS env vars must stay byte-for-byte identical.
- **RESOLVED decisions (do not re-open):**
  1. **Escalation wording** → use the PRD denied-topic string *"consult your dean, the
     Provost's office, or the appropriate office."* (Not the customer's "Faculty Affairs /
     Labor Relations" wording, which contradicts the PRD.)
  2. **Omission rule** → **guarded single-pass**: fire only when one source affirmatively
     grants something material and another is silent on the *same topic*; never on a
     current-catalog-edition gap (that is normal retrieval behavior, not variance). Single
     detection run (no self-consistency gate for the MVP).
  3. **Authority fields** → include the **thin derived** `authority_rank`/`effective_date`
     (from `doc_type` + registry, no LLM), **reviewer-only** (customer: end users must not be
     confused by authority level; enforced by existing role-shaping, not new code).
- **Still open (deferred, not blocking MVP):** §15 Q1 (rename `conflict` field → `variance`,
  frontend-touching), Q4 (one table vs two), Q7 (variance on resolution-check), Q9 (Bedrock
  Guardrails interaction), Q10 (self-consistency), Q11 (hybrid/rerank), Q12 (who runs KB
  re-ingest for section chunking + authority metadata).

## 10. Exact next steps
1. Re-read `lambdaspec.md` (esp. §7 detection logic, §8 severities, §9 language, §13 tests)
   and `CLAUDE.md` (frozen-verifier rule, decision authority).
2. Write `backend/tests/test_variance.py` first (TDD, matching implementation3.md's task
   style). Cover the §13 cases; assert `VARIANCE_ESCALATION` = the PRD denied-topic string;
   assert employees never receive `authority_rank`/`effective_date` (test 11a).
3. Run the new tests to confirm they fail (module not found).
4. Implement `backend/app/agents/variance.py` (pure `classify_severity` first, then
   `detect_variance`/`soft_language`/`log_variance`).
5. Wire into `backend/app/chat.py` agent-grounded path; raise `search(k=6)`→`k=12` in
   `chat.py` and `search(topic, k=10)`→`k=12` in `agents/pipeline.py`.
6. Add defaulted `authority_rank`/`effective_date` to `retrieval.py` `SearchResult` and
   `schemas.py` `GroundedPassage` (backward-compatible defaults so frozen tests pass).
7. Run the verifier (must be fully green, zero AWS):
   - `backend/.venv/bin/python -m pytest backend/tests -q`
   - `cd frontend && npx tsc --noEmit && npm run build`
   (Frontend should need no changes — the `ConflictSignal` wire contract is unchanged.)
8. Update `CLAUDE.md` (Variance Layer section + test count + Last Updated).
9. Commit on the `lambda-variance-spec` branch. Do not push or open a PR unless asked.

**Verifier commands (canonical):**
`backend/.venv/bin/python -m pytest backend/tests -q` **and**
`cd frontend && npx tsc --noEmit && npm run build`.

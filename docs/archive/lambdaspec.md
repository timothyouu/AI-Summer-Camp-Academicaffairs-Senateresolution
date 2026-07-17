# Lambda Spec — Policy Variance Detection, Surfacing & Logging

Companion to `spec.md`, `implementation.md`, `implementation2.md`, and `implementation3.md`.
This document defines the **Lambda-side behavior** for detecting, surfacing, and logging
**policy variance** across retrieved RAG results. It is a spec only — no application code
is changed by this file.

> **Reading guide for teammates:** This spec deliberately reuses the existing 6-agent
> conflict pipeline (`backend/app/agents/`) and the existing conflict log
> (`policy-intelligence-conflicts` DynamoDB table) rather than inventing a parallel system.
> The main *new* asks from the customer — a softer "variance" vocabulary and a richer
> severity taxonomy — do not match what is already built. Every such gap is called out in
> **§15 Open Questions / Team Decisions** instead of being silently resolved.
>
> **Notion PRD reconciled (read 2026-07-15).** The Notion "Needs & MVP Scope" doc has now
> been read in full. Its §9 (Technical Architecture) confirms this exact stack — API Gateway
> + Lambda, Strands `extract → compare → verify`, DynamoDB (access-control, conflict log,
> draft versions, feedback, catalog registry), Cognito, S3, Bedrock — and its
> "Conflict-Detection Multi-Agent Workflow" matches the six agents already coded, with the
> **same four-value typology** (direct contradiction, numeric mismatch, scope overlap,
> CBA-vs-Handbook jurisdiction). Two customer asks in this task therefore extend *beyond* the
> PRD, not just beyond the code: (a) the seven-severity taxonomy (§8), and (b) the escalation
> wording — the PRD's canonical calibration answer is *"consult your dean or the Provost's
> office"*, so the requested "Faculty Affairs / Labor Relations / higher-level office" wording
> conflicts with **both** the code and the PRD (§9, §15 Q2). Per CLAUDE.md, the Notion PRD
> governs *what exists*; these are flagged for a team decision, not silently overridden.

---

## 1. Purpose and MVP Scope

### Purpose
When the RAG system retrieves two or more passages that appear to answer the same user
question *differently*, the assistant must **surface the divergence without adjudicating a
winner**, using soft, non-alarming "policy variance" language, and must **log the variance**
for policy makers to review later.

The customer's motivating example:

> One source says there is **no additional time** to perform an action; another source
> **allows three months**. This is not an egregious contradiction — but it is operational
> risk, because one source permits something the other is silent about.

That "silent-vs-permitted" case is exactly the kind of soft divergence the current pipeline
under-reports (it keys on `must` vs `must_not` and numeric mismatch). This spec adds an
**`OMISSION_OF_RIGHT_OR_PROTECTION`** and a **`DEADLINE_MISMATCH`** notion so the three-month
example fires.

### In Scope (MVP)
- A single request-path Lambda (already exists: FastAPI + Mangum in `backend/app/lambda_entry.py`)
  that, on `POST /api/chat`, runs retrieval → variance detection → soft-language response.
- Variance detection layered on the **existing** `AgentPipeline` (`backend/app/agents/pipeline.py`).
- Writing a **potential-variance record** to DynamoDB (the existing conflict log table).
- Role-shaped output: employees get soft escalation guidance; reviewers get full detail
  (mechanism already exists in `backend/app/chat.py`).

### Out of Scope (MVP)
- A separate standalone "variance Lambda" distinct from the FastAPI handler (see §3 —
  we recommend keeping it in-process for the demo).
- Cognito enforcement (stays OFF for the demo per CLAUDE.md).
- Live re-training / fine-tuning of any model.
- Automated resolution or "correct answer" selection — the product explicitly must **not**
  pick a winner.
- Cross-question aggregation dashboards beyond what the reviewer conflict log already shows.

---

## 2. Assumptions (Grounded in the Current Repo)

These are drawn from the code and `implementation*.md`, not invented:

1. **Backend runs as one Lambda.** `backend/app/lambda_entry.py` wraps the FastAPI app with
   Mangum. There is no per-route Lambda today; `implementation2.md` §2 lists "per-route
   handlers" only as an alternative. **This spec assumes the single-Lambda deployment.**
2. **Retrieval is Bedrock Knowledge Base in AWS mode.** `backend/app/retrieval.py`
   `_search_knowledge_base()` calls `bedrock-agent-runtime.retrieve` when `BEDROCK_KB_ID`
   is set; otherwise the local NumPy index answers. Response shape is identical either way
   (`SearchResult`).
3. **The 6-agent pipeline already does conflict detection.** Agents: `orchestrator`,
   `retrieval`, `extractor`, `conflict`, `verifier`, `escalation`
   (`backend/app/agents/pipeline.py`). It emits an `agent_trace` for the UI and abstains
   rather than guessing.
4. **A conflict log already exists.** DynamoDB table `policy-intelligence-conflicts`
   (env `DDB_CONFLICTS_TABLE`, alias `DYNAMODB_CONFLICTS_TABLE`), with `ConflictRecord`
   fields `id, source_a, source_b, topic, description, status, resolution_note, created_at,
   updated_at` (`backend/app/models.py`). SQLite is the local mirror.
5. **Soft escalation is already partly built.** `ESCALATION = "Multiple answers — consult
   your dean or the Provost's office."` (`agents/pipeline.py`) and
   `EMPLOYEE_CONFLICT_GUIDANCE` (`chat.py`) already soften conflict output for employees.
   The customer's requested wording differs — see §9 and §15.
6. **No new dependencies.** Per `implementation3.md` global constraints and `LOOP.md`:
   `boto3` imports stay lazy/guarded; every AWS integration is env-gated; tests must pass
   with zero AWS. This spec inherits those rules.
7. **Region / profile.** `us-west-2` (or wherever Bedrock + OpenSearch Serverless are
   available); the provisioning profile `csub-policy` lives on a teammate's machine
   (CLAUDE.md active constraints). No live-AWS verification has run from this repo yet.
8. **The existing typology enum is smaller than the customer's requested taxonomy.**
   Current `ConflictTypology` = `direct_contradiction | numeric_mismatch | scope_overlap |
   cba_vs_handbook_jurisdiction | none` (`agents/schemas.py`), and the **Notion PRD §9
   specifies exactly this four-value typology** — so the seven requested severity categories
   are a superset of both the code *and* the PRD. Reconciling them is a **team decision**
   (§8, §15 Q3).
9. **PRD-confirmed behaviors this spec must not break:** abstention ("no conflict" /
   "uncertain → escalate") is a first-class output; self-consistency (run detection 2–3× and
   only surface reproducing conflicts); citation-enforced generation; programmatic span
   verification; negative controls. The variance layer sits *downstream* of all of these — it
   re-labels verified output, it does not relax any guardrail.
10. **"Declaring a Conflict Winner" is a formal denied topic** in the PRD's Bedrock Guardrails
    section. The variance response must never state which source prevails — this reinforces,
    and is stricter than, the existing "no winner" escalation. If Bedrock Guardrails are
    enabled, the shared blocked-message tone is *"I can help you find and understand existing
    policy, but I can't help with that. Please contact your dean, the Provost's office, or the
    appropriate office."*
11. **Catalog "silence" is a PRD retrieval rule, not a variance signal.** The PRD says archived
    catalog editions surface "when the current edition is silent." That is edition down-ranking
    (already implemented via `is_current` + `edition_year`), *not* an omission/variance to
    escalate. The variance detector must not treat a current-edition gap that an archived
    edition fills as `OMISSION_OF_RIGHT_OR_PROTECTION` — see §7 guardrails and §15 Q5.

---

## 3. Lambda Functions Needed for Baseline Functionality

For the MVP demo we recommend **one request Lambda** (already deployed) plus the **existing
ingestion Lambda**, and treat "variance detection" as a module *inside* the request Lambda,
not a new function. This keeps the demo simple and avoids a new deployable.

| # | Function (logical) | New or existing | Trigger | Responsibility |
|---|---|---|---|---|
| 1 | **Request handler** (`lambda_entry.handler`, Mangum→FastAPI) | Existing | API Gateway `POST /api/chat`, `/api/check-resolution`, etc. | Runs retrieval + variance detection + soft-response shaping + variance logging. |
| 2 | **Variance detector module** (in-process) | New *module*, not a new Lambda | Called by #1 | Wraps the existing `AgentPipeline` and maps its output to variance severities + soft language. |
| 3 | **Ingestion Lambda** (`backend/lambda_handlers/ingestion.py`) | Existing | S3 `ObjectCreated` on the corpus bucket | Starts a Bedrock KB ingestion job so new sources become retrievable. Unchanged by this spec. |

**Optional (only if the team wants a decoupled write path — see §15 Q6):**

| 4 | **VarianceLogWriter Lambda** *(placeholder name)* | New Lambda | Async invoke / SQS from #1 | Persists variance records to DynamoDB off the request path so chat latency is unaffected. **Not recommended for the MVP** — the synchronous `conflict_store().create_or_get()` write is fast and already tested. |

---

## 4. Suggested Function / Symbol Names and Responsibilities

New code, if approved, should live beside the existing pipeline and follow its naming.
All names below are **suggestions**; existing names are marked *(exists)*.

| Symbol | Location (suggested) | Responsibility |
|---|---|---|
| `detect_variance(question, passages) -> VarianceReport` | `backend/app/agents/variance.py` (new) | Thin adapter: run `AgentPipeline.run(question)`, then classify each cross-source analysis into a `VarianceSeverity` and build soft language. |
| `classify_severity(analysis) -> VarianceSeverity` | same | Map a `ConflictAnalysis` (existing) → one of the seven severity categories (§8). Pure function, unit-testable with no AWS. |
| `soft_language(report, role) -> str` | same | Produce the customer's "policy variance" phrasing; role-aware. |
| `log_variance(report) -> str \| int` | same | Write to the conflict log via existing `conflict_store().create_or_get(ConflictCreate(...))`; return the record id. |
| `VARIANCE_ESCALATION` (constant) | same | The soft escalation sentence (see §9). Distinct from existing `ESCALATION` until §15 Q2 is decided. |
| `AgentPipeline.run` *(exists)* | `agents/pipeline.py` | Retrieval → blind extraction → same-topic comparison → quote/context verification → escalation. Unchanged. |
| `conflict_store()` / `create_or_get` *(exists)* | `backend/app/stores.py` | Dual-mode SQLite/DynamoDB conflict-log store. Reused as the variance log. |
| `shape_response_for_role` *(exists)* | `backend/app/chat.py` | Already strips raw sources/ids for employees; extend to carry variance language. |

**Design rule:** the variance module must be a *layer over* the pipeline, never a fork of it.
It reads `PipelineResult` and re-labels; it does not re-implement retrieval or verification.

---

## 5. Input and Output Schemas

### 5.1 Request handler input (unchanged, existing `ChatRequest`)
```json
{ "question": "Do I get extra time to submit my WPAF materials?" }
```
Headers (local demo): `X-Role: employee | reviewer`, optional `X-User-Email`.
In AWS mode, role/identity come from verified Cognito claims (currently OFF).

### 5.2 Internal: `VarianceReport` (new, proposed)
```json
{
  "question": "Do I get extra time to submit my WPAF materials?",
  "variance_detected": true,
  "items": [
    {
      "severity": "DEADLINE_MISMATCH",
      "source_a": "Unit 3 CBA 2022-2026",
      "section_a": "Article 15",
      "span_a": "no additional time shall be granted",
      "authority_rank_a": 100,
      "effective_date_a": "2022-07-01",
      "source_b": "CSUB Faculty Handbook",
      "section_b": "Appendix D",
      "span_b": "faculty may request up to three months",
      "authority_rank_b": 60,
      "effective_date_b": "2021-09-01",
      "topic": "WPAF submission timeline",
      "confidence": 0.72,
      "verified": true
    }
  ],
  "soft_summary": "The available policy sources appear to vary on this point.",
  "escalation": "Because this may affect an employment or procedural decision, please consult Faculty Affairs, Labor Relations, or the appropriate higher-level office."
}
```

**`authority_rank` / `effective_date` (new metadata, reviewer-only).** These per-source fields
carry the passage's authority weight (e.g. CBA = high for Unit 3 employment terms) and edition
date. They give `AUTHORITY_MISMATCH` (§8) a concrete field to key on and let the reviewer view
order sources by authority. They are **derived at retrieval time** from `doc_type` + the source
registry — **not** a new LLM extraction pass — so this adds no model cost and no new pipeline
agent. See §6 item 2a for the derivation and §8 for how `AUTHORITY_MISMATCH` consumes them.

> **Authority is a privileged-user signal only (customer requirement).** The customer does not
> want end users confused by authority levels. Therefore `authority_rank` / `effective_date`,
> like `source`/`section`/`span`, are **reviewer-only** and are stripped from the employee
> response by the *existing* `shape_response_for_role` — this is the same reviewer-only gate
> already applied in §9 rule 4, **not a new mechanism**. The employee still receives only the
> soft "sources appear to vary → please consult…" guidance, with no ranking, no "which source
> is stronger," and no winner (reinforced by §2 assumption 10, the PRD's "Declaring a Conflict
> Winner" denied topic). So this follow-up is satisfied by scoping the two new fields to the
> reviewer payload; no added complexity for the employee path.

### 5.3 Response handler output (existing `ChatResponse`, variance mapped onto `ConflictSignal`)
Reusing the existing wire contract avoids frontend changes:
```json
{
  "answer_id": "…",
  "answer": "…grounded answer with numbered citations…",
  "citations": [{ "id": 1, "source": "…", "section": "…", "excerpt": "…" }],
  "conflict": {
    "detected": true,
    "sources": ["Unit 3 CBA 2022-2026", "CSUB Faculty Handbook"],
    "guidance": "The available policy sources appear to vary on this point. …",
    "conflict_id": 42
  },
  "mode": "agent-grounded",
  "agent_trace": [ … ]
}
```
- **Employee role:** `sources` → `[]`, `conflict_id` → `null`, `guidance` → soft escalation
  text only (existing `shape_response_for_role` behavior; wording updated per §9).
- **Reviewer role:** full detail retained.

> **Note (§15 Q1):** the field is named `conflict`, not `variance`. Renaming it is a
> frontend-touching change; the MVP keeps the field name and softens only the *language*.

---

## 6. Bedrock Knowledge Base / Agent Interaction Assumptions

1. **Retrieval:** `bedrock-agent-runtime.retrieve` against `BEDROCK_KB_ID`, over-fetching
   `k*2` then applying the registry post-filter (`apply_registry_policy`, archived dropped /
   non-current down-ranked). Already implemented in `retrieval.py`.
   - **Retrieval breadth (tuning change, matters for variance).** Conflict/variance detection
     needs *both* diverging passages present in the same result set. A small top-k surfaces
     one source and silently misses the other, so no variance can fire. **Target k = 12–15**
     for the variance path (the practical floor for cross-document comparison; the customer's
     reference point is "top-k 3 will miss conflicts, use 12–20"). Today `chat.py` uses `k=6`
     and `pipeline.py` uses `k=10`; raising these is a **one-line-per-call-site config change**
     that does not touch pipeline logic or the frozen local-index defaults. Keep the existing
     `k*2` over-fetch so `apply_registry_policy` trimming does not starve the comparison.
2. **Chunking (ingestion requirement).** Chunk **by section / article**, not by arbitrary
   character count. Fixed-size character chunking splits an article across chunks and weakens
   the section-level claim comparison the pipeline depends on (§7 Step B/C keys on
   `section`/`topic`). The local index (`data/index/chunks.json`) is already section-aware;
   the Bedrock KB must be configured with **hierarchical / semantic chunking** (not the
   default fixed-size) so AWS retrieval matches local behavior. This is KB *config*, not code
   — but it requires a re-ingest (see §15 Q12).
   - **2a. Authority / recency metadata (thin, no new extractor).** Carry `authority_rank`
     (integer, higher = more authoritative) and `effective_date` on each passage. **Derive**
     them, do not extract them with an LLM: `authority_rank` is a small lookup keyed on
     `doc_type` (e.g. `cba` > `handbook` > `policystat` > `catalog`), and `effective_date`
     comes from the source registry's edition metadata (`edition_year` / `is_current`, already
     stored). This adds two fields to `SearchResult`/`GroundedPassage` and zero model calls.
     The snippet's richer per-rule fields (`actor`, `action`, `condition`, `deadline`,
     `right_or_obligation`) are **already** the pipeline's query-time `Claim` fields
     (`agents/schemas.py`), so they are intentionally *not* duplicated as retrieval metadata.
3. **Generation / claim extraction / comparison / verification:** Claude via the Bedrock
   **Converse** API, isolated in `backend/app/llm.py` (`generate(system, user, json_mode)`).
   The variance module calls the pipeline, which calls `llm.generate` — the module itself
   makes **no direct Bedrock calls**.
4. **Titan Text Embeddings V2** is used only at KB ingestion time; the request Lambda does not
   embed at query time in AWS mode. (Embeddings are computed over the section/article chunks
   from item 2, not fixed-size character windows.)
5. **Strands Agents SDK** is optional: the pipeline activates Strands only when `strands` is
   importable *and* `BEDROCK_KB_ID` is set; otherwise the same logic runs in-process. The
   variance module must not require Strands.
6. **No new model access is required** beyond what chat already uses (one Claude chat model +
   Titan embeddings). If Bedrock is unavailable, the pipeline's deterministic fallbacks
   (`_deterministic_claims`, `_deterministic_compare`) still produce a report — variance
   detection must degrade, never 500.
7. **Bedrock Agents (agents-for-bedrock):** *not* assumed. The design uses KB `retrieve` +
   Converse, matching current code. Marked as a placeholder should the team later adopt a
   managed Bedrock Agent.

### 6.1 Cognito-deferral pattern (shelve now, append later)

The Notion PRD lists Cognito as a Core Service, but CLAUDE.md and implementation3.md record a
deliberate decision to keep it **OFF for the demo**, gated behind env vars. This is not a
deviation from the docs — it is the documented seam, and it is **already built**. The variance
module inherits it for free by following one rule:

> **Design rule:** the variance module reads role **only** through `resolve_request_role(...)`
> and identity **only** through `identity_email(...)` (both in the existing codebase). It must
> **never** call Cognito, decode a token, or read a `COGNITO_*` setting directly.

Why this makes variance forward-compatible with zero rework:

- `resolve_request_role` already branches on `settings.cognito_aws` (which is just
  `bool(COGNITO_USER_POOL_ID and ...)`):
  - **Today (Cognito shelved):** `COGNITO_*` env vars unset → `cognito_aws` is false → role
    comes from the `X-Role` header, default `reviewer`. No Cognito code path executes.
  - **Later (Cognito appended):** set the backend `COGNITO_*` vars + frontend
    `VITE_USE_COGNITO` → the *same* function starts trusting verified token claims instead.
    **Zero variance-code change** — it is deployment config, not a code change.
- Because the function returns the identical `"employee"` / `"reviewer"` values in both modes,
  the variance layer never needs to know which mode is active. Shelving Cognito is literally
  "leave the env vars empty"; appending it is "fill them in."

This keeps the spec faithful to the PRD (Cognito remains the documented target and the seam is
real and wired) while letting the team ship the demo without it.

---

## 7. Conflict / Variance Detection Logic

Layered on the existing pipeline; **the pipeline is not modified**, the variance module
re-interprets its output.

**Step A — Retrieve (existing, but widen k).** `search(question, k)` → grounded passages,
archived sources filtered out. **Use k = 12–15 for the variance path** (§6 item 1): a narrow
top-k returns one side of a divergence and the other never enters the comparison, so no
variance can be detected. This is the single highest-leverage tuning change for the demo.

**Step B — Blind claim extraction (existing).** Each source is summarized into normative
`Claim`s (`subject, modality ∈ {must, may, must_not}, condition, value_threshold, scope,
citation_span`) by a per-source *blind* extractor that never sees the other sources — this
is what prevents the model from prematurely reconciling them.

**Step C — Same-topic comparison (existing; normalize topic first).** Retrieved passages are
first normalized to the topic taxonomy (`topics.TOPIC_TAXONOMY`) so that, e.g., a CBA
"Article 13" passage and a Handbook "305.1.3" passage on probationary-service credit group
under one topic before comparison. Only claims on the **same normalized topic** are compared;
each pair is classified `agreement | redundant_overlap | contradiction | gap` and given a
typology. Grouping by normalized topic (not raw section labels) is what lets cross-document
pairs meet at all.

**Step D — Verification (existing).** Each candidate contradiction is re-checked: quotes must
be grounded verbatim in a retrieved passage, and a context re-read must confirm both claims
apply to the same conditions. Confidence ≥ 0.5 required to accept.

**Step E — Variance mapping (NEW).** For each *accepted* contradiction **and** each
divergence that the customer cares about but the current classifier calls "gap/overlap",
`classify_severity()` assigns one of the seven categories (§8). Crucially, this step adds the
**silent-vs-permitted** rule the demo needs:

> If source A is **silent** on an allowance (no matching claim / `gap`) while source B
> **permits or grants** something material (a deadline extension, an eligibility, a right),
> emit `OMISSION_OF_RIGHT_OR_PROTECTION` (or `DEADLINE_MISMATCH` when the omitted item is a
> time window). This is *variance*, not *contradiction* — soft language, still logged.

**Step F — Soften & log (NEW + existing store).** Build soft language (§9), write a variance
record (§10), shape by role (existing), return.

**Anti-false-positive guardrails (inherited):**
- Never surface an unverified span.
- Never pick a winner or state which source "governs."
- Abstain when < 2 grounded same-topic claims.
- Same-source pairs are ignored.

---

## 8. Severity Categories

The customer requested these seven. The MVP maps them onto (and extends) the existing
`ConflictTypology`. **The mapping below is a proposal pending §15 Q3.**

| Requested severity | Meaning | Fires when | Maps to existing typology |
|---|---|---|---|
| `DIRECT_CONTRADICTION` | Sources assert opposite obligations | `must` vs `must_not` on same subject | `direct_contradiction` |
| `DEADLINE_MISMATCH` | Different time windows / one silent on time | numeric time values differ, **or** one grants a deadline extension the other omits | *new* (subset of `numeric_mismatch` + omission rule) |
| `ELIGIBILITY_MISMATCH` | Different who-qualifies rules | eligibility scope differs across sources | *new* (subset of `scope_overlap`) |
| `AUTHORITY_MISMATCH` | Sources disagree on who decides / which body governs | e.g. CBA vs Handbook jurisdiction; keys on the `authority_rank` gap (§5.2, §6 item 2a) | `cba_vs_handbook_jurisdiction` |
| `OMISSION_OF_RIGHT_OR_PROTECTION` | One source grants a right/protection the other never mentions | one `may/grants`, other `gap` on same topic | *new* (the customer's three-month example) |
| `NUMERIC_MISMATCH` | Different numeric thresholds (units, %, counts) | grounded numeric thresholds differ | `numeric_mismatch` |
| `TERMINOLOGY_MISMATCH` | Same concept, divergent defined terms (e.g. old vs new committee name) | synonymous subjects, differing labels | *new* (relates to the GECCo naming demo case) |

**Severity ordering (proposed, for display + log sort):**
`DIRECT_CONTRADICTION` > `AUTHORITY_MISMATCH` > `ELIGIBILITY_MISMATCH` >
`DEADLINE_MISMATCH` > `NUMERIC_MISMATCH` > `OMISSION_OF_RIGHT_OR_PROTECTION` >
`TERMINOLOGY_MISMATCH`.

Regardless of severity, **user-facing language stays soft** (§9). Severity drives logging,
reviewer prioritization, and the amber banner — never a harder tone toward the employee.

**Authority level is never shown to employees.** `AUTHORITY_MISMATCH` and the `authority_rank`
field it keys on are reviewer-only (§5.2). The customer specifically does not want end users
confused by authority levels, so the employee response never conveys ranking or which source
is more authoritative — only that sources vary and to whom to escalate. Privileged (reviewer)
users, who *can* analyze conflicting data, see the ranks and dates. This is enforced by the
existing role-shaping gate, not new code.

---

## 9. Soft-Response Language Requirements

The assistant must never say "conflict," "wrong," "violation," or name a governing source to
an employee. Required phrasings (customer-supplied):

- **Summary line:** "The available policy sources appear to vary on this point."
- **Alt summary:** "There may be some policy variance between these sources."
- **Escalation:** "Because this may affect an employment or procedural decision, please
  consult **Faculty Affairs, Labor Relations, or the appropriate higher-level office**."

Rules:
1. Soft summary is prepended/appended to the grounded answer, not replacing citations.
2. Escalation text is **non-clickable guidance** (no `mailto:`) — matches
   `implementation3.md` locked decision.
3. The word "variance" is preferred over "conflict" in **user-facing** text. Internal log,
   table name, and reviewer view may keep "conflict" for the MVP (§15 Q1/Q2).
4. Employees never see raw source names, section ids, spans, `conflict_id`, **or authority
   level** (`authority_rank` / `effective_date` — customer requirement, §5.2/§8).
5. Reviewers may see full detail plus the severity label and authority ranking.

> **Divergence from BOTH the code and the PRD (flag, do not silently override):** the existing
> constants escalate to *"your dean or the Provost's office"* — and the **Notion PRD's
> calibration example and Escalation/Resolution agent use that same wording**. The customer's
> new ask in this task is *"Faculty Affairs, Labor Relations, or the appropriate higher-level
> office."* These are different offices, and the new wording contradicts the governing PRD, not
> just the code. Per CLAUDE.md ("the Notion PRD governs what exists"), this cannot be silently
> applied. See §15 Q2. The PRD's denied-topic blocked message already names *"your dean, the
> Provost's office, or the appropriate office,"* which is a reasonable superset compromise if
> the team wants one string everywhere.

---

## 10. DynamoDB / Logging Schema for Potential Variance Records

**MVP recommendation: reuse the existing conflict log table** rather than create a new one —
it already has a dual-mode store, seed script, and reviewer UI.

- **Table (existing):** `policy-intelligence-conflicts` (env `DDB_CONFLICTS_TABLE`).
- **Existing keys/fields (do not change — settled in CLAUDE.md "DynamoDB App-Memory Merge"):**
  `id` (PK), `source_a`, `source_b`, `topic`, `description`, `status`
  (`Open | Under review | Resolved`), `resolution_note`, `created_at`, `updated_at`.

Variance records are written via `ConflictCreate` today. To carry severity + soft context,
add **optional, backward-compatible attributes** (DynamoDB is schemaless; SQLite needs an
additive migration):

| Attribute | Type | Notes |
|---|---|---|
| `severity` | string | One of §8. Optional; absent on legacy rows. |
| `variance_kind` | string | `contradiction` \| `variance` \| `omission` — soft vs hard. |
| `span_a`, `span_b` | string | Verified quoted spans (reviewer-only). |
| `section_a`, `section_b` | string | Section labels. |
| `confidence` | number | 0–1 from the verifier. |
| `authority_rank_a`, `authority_rank_b` | number | Per-source authority weight (§6 item 2a). Reviewer-only; drives reviewer sort. |
| `effective_date_a`, `effective_date_b` | string | Source edition dates (reviewer-only). |
| `detected_from` | string | `chat` \| `resolution-check`. |
| `question` | string | The user question that surfaced it (aggregatable). |

**If the team instead wants a dedicated table** *(placeholder name)*
`policy-intelligence-variance` — key it `id` (PK) with a GSI on `severity` or `status` for the
reviewer queue. **Not recommended for the MVP**; it duplicates the conflict log and its UI.
See §15 Q4.

**Write semantics:** use the existing `create_or_get` (idempotent on the source pair + topic)
so repeated questions about the same variance do not spam the log.

---

## 11. Error Handling

Inherits the pipeline's "abstain, never fabricate, never 500 on model failure" posture.

| Failure | Behavior |
|---|---|
| Bedrock `retrieve` error / KB unreachable | Fall back to local index if present; else return an honest "assistant unavailable" answer with empty citations. No variance claimed. |
| Claude / Converse error or invalid JSON | Pipeline already catches `RuntimeError/ValueError/JSONDecodeError/ValidationError` and uses deterministic extraction/comparison. Variance module must catch the same set. |
| Fewer than 2 grounded same-topic claims | Abstain: `variance_detected = false`. Not an error. |
| DynamoDB write failure (log) | Log-and-continue: the answer is still returned; variance write failure must **not** fail the chat response. Emit a CloudWatch warning. |
| Oversized / malformed request | FastAPI/Pydantic validation → 422, unchanged. |
| Lambda timeout risk (cold start + KB first query) | Pre-warm before the demo (implementation2.md §D.3); keep extractor concurrency bounded (existing `ThreadPoolExecutor(max_workers ≤ 8)`). |
| Partial pipeline (some agents warn) | Return whatever is grounded with a `warning`-status trace step; never invent to fill gaps. |

Principle: **a variance-detection failure degrades to "no variance surfaced," never to a
false variance and never to a 500.**

---

## 12. AWS IAM Permissions Needed

Scope to least privilege; resource ARNs are **placeholders** until the account/region/table
names are fixed. The request Lambda's execution role needs:

```jsonc
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "BedrockKnowledgeBaseRetrieve",
      "Effect": "Allow",
      "Action": ["bedrock:Retrieve"],
      "Resource": "arn:aws:bedrock:<region>:<account-id>:knowledge-base/<BEDROCK_KB_ID>"  // placeholder
    },
    {
      "Sid": "BedrockModelInvoke",
      "Effect": "Allow",
      "Action": ["bedrock:InvokeModel"],
      "Resource": [
        "arn:aws:bedrock:<region>::foundation-model/anthropic.claude-*",       // placeholder
        "arn:aws:bedrock:<region>::foundation-model/amazon.titan-embed-text-v2:0" // placeholder
      ]
    },
    {
      "Sid": "VarianceLogReadWrite",
      "Effect": "Allow",
      "Action": ["dynamodb:PutItem", "dynamodb:GetItem", "dynamodb:UpdateItem", "dynamodb:Query", "dynamodb:Scan"],
      "Resource": "arn:aws:dynamodb:<region>:<account-id>:table/policy-intelligence-conflicts"
    },
    {
      "Sid": "Logs",
      "Effect": "Allow",
      "Action": ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"],
      "Resource": "arn:aws:logs:<region>:<account-id>:*"
    }
  ]
}
```

- The **ingestion Lambda** additionally needs `bedrock:StartIngestionJob`,
  `bedrock:ListDataSources`, and `s3:GetObject`/`s3:DeleteObject` on the corpus bucket
  (already required by `backend/lambda_handlers/ingestion.py`).
- If a dedicated variance table is chosen (§15 Q4), duplicate the DynamoDB statement for its
  ARN + its GSI ARN.
- **Do not** grant `bedrock:*` or `dynamodb:*` — enumerate actions as above.

---

## 13. Local / Unit Test Cases

All must pass with **zero AWS** (mock `llm.generate`, use the local index / SQLite), per the
frozen-verifier rule. Add to a new `backend/tests/test_variance.py` (frozen files untouched).

**Severity classification (pure, no AWS):**
1. `must` vs `must_not`, same subject → `DIRECT_CONTRADICTION`.
2. "no additional time" (source A) vs "up to three months" (source B) → `DEADLINE_MISMATCH`
   **and** `variance_detected = true`. *(The customer's canonical example.)*
3. Source A silent, source B grants a right → `OMISSION_OF_RIGHT_OR_PROTECTION`.
4. "120 units" vs "126 units" → `NUMERIC_MISMATCH`.
5. CBA vs Handbook on who decides → `AUTHORITY_MISMATCH`.
6. Old committee name vs expanded name, same body → `TERMINOLOGY_MISMATCH`.
7. Different eligibility scope → `ELIGIBILITY_MISMATCH`.

**Behavioral / response shaping:**
8. Employee role → response has soft summary, empty `sources`, null `conflict_id`, no spans.
9. Reviewer role → full detail incl. severity retained.
10. Soft summary text exactly matches the approved phrasing (§9) — string assertion.
11. Escalation text contains "Faculty Affairs" and "Labor Relations" (once §15 Q2 is decided;
    until then, assert against whatever constant is chosen).
11a. **Authority hidden from employees.** An `AUTHORITY_MISMATCH` variance → employee response
    contains **no** `authority_rank`/`effective_date` and no "more/less authoritative" wording;
    the reviewer response retains both fields. *(Customer requirement, §5.2/§8/§9 rule 4.)*

**Detection guardrails:**
12. < 2 grounded same-topic claims → `variance_detected = false`, no log write.
13. Ungrounded / unverifiable span → not surfaced.
14. Same-source pair → ignored.

**Retrieval breadth (§6 item 1):**
14a. With two same-topic passages from different sources in the corpus, a variance-path
    retrieval at the widened k returns **both** (regression guard: a narrow k that drops one
    would make the variance undetectable). Runs against the local index, zero AWS.

**Logging:**
15. Accepted variance → exactly one `create_or_get` write; repeat question → idempotent (no
    duplicate row).
16. DynamoDB write raises → chat response still returns 200 (log-and-continue).

**Fallback:**
17. `llm.generate` raises → deterministic path still yields a report; endpoint never 500s.

---

## 14. Deployment Notes

1. **No new deployable for the MVP.** Variance detection ships inside the existing request
   Lambda (`lambda_entry.py`). Deploy = redeploy that Lambda after adding the variance module.
2. **Env-gated, zero-config default.** Behavior with no AWS env vars must be byte-for-byte
   identical to today (frozen-tests rule). Variance detection uses the local index + SQLite
   when `BEDROCK_KB_ID` / `DDB_CONFLICTS_TABLE` are unset.
3. **Dependencies:** none new. `boto3` stays lazy/guarded; `mangum` only loaded in Lambda.
4. **IaC:** the conflict/variance table is created by `backend/scripts/setup_dynamodb_tables.sh`
   or the CDK stack (`infra/stacks/policy_intelligence_stack.py`, `_build_dynamodb_tables`).
   No new table for the MVP means no IaC change unless §15 Q4 is chosen.
5. **Pre-warm before the demo:** one scripted `/api/chat` call to absorb Lambda cold start +
   KB first-query latency (implementation2.md §D.3).
6. **Verifier before commit:**
   `backend/.venv/bin/python -m pytest backend/tests -q` (currently 107 tests + new variance
   tests) **and** `cd frontend && npx tsc --noEmit && npm run build`.
7. **Cost/teardown:** OpenSearch Serverless (the KB vector store) is the only meaningfully
   costly piece — delete the collection after judging (implementation2.md §D.4).
8. **Cut line:** if time is short, keep single-prompt conflict detection and still show the
   architecture honestly (implementation2.md §4). Variance mapping is additive and can be the
   first thing cut without breaking chat.

---

## 15. Open Questions / Team Decisions

These are places where the customer's request diverges from the **existing implementation**
and/or the **governing Notion PRD**. Per the brief and CLAUDE.md, they are flagged rather than
guessed.

1. **`conflict` vs `variance` naming.** The wire contract, DynamoDB table, reviewer UI, **and
   the Notion PRD** all say "conflict." The customer wants softer "variance" language.
   **Proposal:** keep internal names ("conflict") for the MVP, change only user-facing *text*
   to "variance." Rename later if desired. — *Decision needed.*

2. **Which office to escalate to?** Existing code AND the Notion PRD both say *"your dean or the
   Provost's office"* (PRD calibration example + Escalation/Resolution agent). The customer's
   new ask is *"Faculty Affairs, Labor Relations, or the appropriate higher-level office."*
   These are materially different referrals, and the new wording **contradicts the governing
   PRD**, so it cannot be applied unilaterally. **Do not ship both.** — *Decision needed. The
   PRD's own denied-topic message ("your dean, the Provost's office, or the appropriate
   office") is a natural compromise string.*

3. **Severity taxonomy reconciliation.** The existing `ConflictTypology` enum has 5 values;
   the customer wants 7 named severities. §8 proposes a mapping that *extends* the enum.
   **Decision needed:** extend the existing `Literal` enum, or keep the pipeline's typology
   internal and layer severity purely in the variance module? (Spec recommends the latter to
   avoid touching frozen pipeline tests.)

4. **One table or two?** Reuse `policy-intelligence-conflicts` (recommended) vs a new
   `policy-intelligence-variance` table (placeholder). New table = duplicate UI + IaC +
   permissions for little MVP gain. — *Decision needed.*

5. **Softness vs the `OMISSION` demo case — the biggest open question.** The current pipeline
   AND the PRD are deliberately *conservative*: the PRD lists abstention and self-consistency
   as anti-hallucination levers, and classifies silence as `gap` (a first-class non-conflict).
   The customer's three-month example is exactly such a **gap/omission**, so today it would
   **not** fire. Implementing `OMISSION_OF_RIGHT_OR_PROTECTION` deliberately loosens detection
   in a way the PRD's design guards against. **Decision needed:** how aggressively to surface
   omissions without inflating the false-positive rate the PRD explicitly measures with
   negative controls? (Spec's guardrail: fire only when one source *affirmatively grants*
   something material and another is silent on the *same topic* — and **never** when the
   silence is just a current-catalog-edition gap that an archived edition fills, which is
   PRD-defined normal retrieval behavior, not variance.)
   This also intersects the PRD's own open question "Proactive full disclosure vs. contextual
   on-demand" — omission surfacing leans proactive, which the customer has not yet resolved.

6. **Sync vs async logging.** MVP writes the variance record synchronously via
   `conflict_store()`. A separate `VarianceLogWriter` Lambda (§3 #4, placeholder) would
   decouple it. Recommended: **synchronous for the demo.** — *Decision needed only if latency
   becomes a problem.*

7. **Does variance detection also run on `/api/check-resolution`?** The resolution checker
   already surfaces overlaps/duplicates/conflicts for drafts. Should reviewer draft-checking
   emit the same soft "variance" language, or keep its current reviewer-facing wording?
   — *Decision needed.*

8. **Cognito timing — resolved as a deferral, not an open risk.** All role gating assumes the
   local `X-Role` header for the demo (Cognito OFF per CLAUDE.md). The Cognito-deferral pattern
   in **§6.1** is the mechanism: the variance module reads role only via `resolve_request_role`,
   which already branches on `settings.cognito_aws`, so turning Cognito on later is deployment
   config with **zero variance-code change**. No variance-specific decision is needed here —
   this item is a *confirmation* that the §6.1 rule is followed, not an open question.

   The one thing to handle **at Cognito-enablement time** (not now): the PRD's Cognito groups
   are `Admin / Reviewer-Writer / Employee` (three), while the demo uses a two-role model where
   reviewer doubles as admin (CLAUDE.md). Variance response-shaping only ever needs
   *employee-vs-not-employee*, so the three groups must be mapped down to the two roles the
   shaping logic expects — `Admin` and `Reviewer-Writer` both collapse to `reviewer`,
   `Employee` maps to `employee`. That mapping belongs in `role_from_claims` (existing), **not**
   in the variance module, which keeps consuming the two-value result unchanged. This does not
   block the MVP; it is a note so the collapse is not forgotten when Cognito is appended.

9. **Bedrock Guardrails interaction (PRD §9).** The PRD mandates a Guardrail with "Declaring a
   Conflict Winner" as a denied topic and a contextual-grounding check paired with the verifier.
   Confirm the variance module's soft output cannot be misread by the Guardrail as "picking a
   winner" (it must not), and that the grounding filter does not strip cited variance spans for
   reviewers. Guardrails are not yet wired in this repo — flagged so it is not forgotten when
   they are. — *Decision/verification needed at Guardrail-enablement time.*

10. **Self-consistency for variance (PRD anti-hallucination lever).** The PRD calls for running
    detection 2–3× and only surfacing conflicts that reproduce. The current pipeline runs once.
    Should the *variance* layer (especially the looser omission rule) require reproduction
    across N runs before it surfaces or logs? Recommended for omissions given their higher
    false-positive risk; costs extra Bedrock calls per chat. — *Decision needed.*

11. **Hybrid search / reranking (snippet ask, deferred).** The customer reference suggests
    hybrid (keyword + vector) search with reranking on top of a wide top-k. Raising k (§6
    item 1) is the minimal, high-value change and is recommended now; hybrid/rerank needs an
    OpenSearch Serverless field config + a rerank model and is **not minimal**. **Proposal:**
    ship wide-k first, measure whether conflicts are still missed, add hybrid/rerank only if
    recall is insufficient. — *Decision needed only if wide-k proves inadequate.*

12. **Re-ingest ownership for section chunking + authority metadata (§6 items 2/2a).**
    Section/article chunking and `authority_rank`/`effective_date` both require re-ingesting the
    corpus into the Bedrock KB with the new chunking config + metadata. No live AWS has run from
    this repo (CLAUDE.md active constraints; `csub-policy` profile is on a teammate's machine),
    so **who runs the re-ingest and when** is open. The local index already carries section-aware
    chunks, so the demo works without it; this is an AWS-parity task. — *Decision needed: owner +
    timing.*

13. **Authority level visible to end users? — RESOLVED (customer decision).** The customer does
    **not** want end users confused by authority level. `authority_rank`/`effective_date` and any
    "which source is stronger" signal are therefore **reviewer-only**, enforced by the existing
    `shape_response_for_role` gate (§5.2, §8, §9 rule 4, test 11a) — privileged users who analyze
    conflicting data see it; employees never do. No new mechanism, no added employee-path
    complexity. Recorded here as settled, not open.

---

*Spec only — no application code changed. See the summary and recommended next steps in the
task response.*

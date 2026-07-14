# Policy Intelligence Assistant — Demo Spec

**Date:** 2026-07-14
**Milestone:** Customer demo tomorrow (2026-07-15). Closer-to-shippable than a mockup, but shortcuts are allowed where they don't touch the core value (e.g., hardcoded sign-in). Final polished demo comes later (hackathon deadline Friday 7AM).
**Sources:** Notion PRD "Policy Intelligence Assistant — Needs & MVP Scope", `challenge_overview.md` (Academic Affairs Policy Assistant), `challenge_overview (1).md` (Academic Senate Resolution Assistant).

## 1. Problem

Campus policy lives in a ~167-page Handbook PDF, PolicyStat, and the collective bargaining agreement (CBA). Employees can't find answers without tribal knowledge (renamed committees, unexpanded acronyms, buried appendices), so questions route through the AVP of Faculty Affairs. Policy makers draft new resolutions without knowing existing coverage, producing duplicates and contradictions; manual review costs ~10 people / ~$10,000 and the summer committee couldn't finish substantive review.

## 2. What We're Building for the Demo

A web app with one sign-in and two role-based paths:

- **Employees & Faculty** — a policy chatbot that answers plain-language questions with citations (source document + section), flags when sources conflict ("multiple answers available — consult your dean or the Provost's office") instead of picking a winner, and a browse-by-topic view.
- **Policy Makers & Reviewers** — everything employees get, plus: a **resolution checker** (paste a draft resolution, get overlap/duplicate/conflict analysis against the indexed corpus), a **conflict log** of detected contradictions, and a **document upload** page that ingests new files into the knowledge base.

### Demo scope decisions (real vs. simplified)

| Feature | Status for tomorrow |
|---|---|
| Sign-in | **Hardcoded** — if-statement check against 2 demo accounts (one per role). No real auth. |
| Policy chatbot with citations | **Real** — RAG over indexed corpus, answers generated with cited sources. |
| Conflict-aware answers | **Real** — retrieval pulls from all sources; when retrieved passages disagree, the answer surfaces both and recommends escalation. |
| Resolution checker | **Real** — this is the wow moment (the PRD's "new AI policy already covered" example). |
| Topic browsing | **Real but lightweight** — topics assigned at ingestion time (LLM-tagged chunks), rendered as a category grid with policy excerpts. |
| Conflict log | **Real persistence, pre-seeded** — conflicts found during chat/checking are appended to a stored log; seeded with 2–3 known conflicts so the page is never empty. |
| Document upload | **Wired end-to-end but demoed cautiously** — upload → parse → chunk → embed → searchable. If live ingestion feels risky in the room, demo with pre-indexed docs and show the upload UI. |
| Answer feedback, recurring-questions hub, smart term matching UI | **Cut for tomorrow** (term matching comes free via semantic search; no dedicated UI). |

### Non-goals (per PRD "Cut")

Senate workflow/Robert's Rules automation, voting/signature tracking, policy editing suite, legal interpretation, deep archive search, personal-computer file ingestion. Also not for tomorrow: real Cognito/RBAC, AWS deployment, revision comparison.

## 3. Users & Auth (demo)

Two hardcoded accounts checked in backend code:

- `reviewer@campus.edu` / `demo123` → role `maker` (full access)
- `employee@campus.edu` / `demo123` → role `employee` (chat + browse only)

Frontend stores the role from the login response and routes to the matching dashboard. No tokens/sessions beyond a value kept in client state — acceptable for demo, called out as replace-with-Cognito later.

## 4. Architecture

Local-first demo whose shape mirrors the PRD's AWS target so nothing is a rewrite later:

- **Frontend:** React (Vite, TypeScript strict, functional components + hooks) + Tailwind CSS. Two dashboards behind the role switch.
- **Backend:** FastAPI (Python, typed). Endpoints for login, chat, resolution check, topics, conflict log, upload.
- **LLM + embeddings:** **AWS Bedrock** via `boto3` — Titan Text Embeddings V2 for embeddings, Claude (e.g. `us.anthropic.claude-sonnet-5` or whichever Claude model is enabled in the account) for answer generation, conflict reasoning, and resolution analysis.
- **Vector store:** in-process — chunk embeddings held in a NumPy matrix, persisted to disk (`data/index/`) as `.npy` + JSON metadata. Cosine similarity top-k. No external vector DB for the demo; the PRD's "Bedrock Knowledge Bases / OpenSearch later" slot stays open.
- **Persistence:** SQLite (stdlib `sqlite3`) for the conflict log and uploaded-document registry. Raw files under `data/corpus/` (the local stand-in for S3).

**Mapping to the PRD's AWS diagram (talking point for the customer):** FastAPI ⇄ API Gateway + Lambda, `data/corpus/` ⇄ S3, NumPy index ⇄ Bedrock Knowledge Base / OpenSearch, Bedrock calls are already the real thing, hardcoded login ⇄ Cognito.

### Request flows

**Chat:** question → embed query (Titan) → top-k chunks with source metadata → single Claude call with a prompt that requires (a) answer grounded only in provided chunks, (b) inline citation markers mapped to source/section, (c) a structured `conflict` field when passages disagree, with escalation wording. Response JSON: `{answer, citations[], conflict: {detected, sources[], guidance} | null}`. Detected conflicts are appended to the conflict log.

**Resolution check:** draft text → embed → top-k similar chunks → Claude call returning structured JSON: `{overlaps[], duplicates[], conflicts[], recommendation}` — e.g., "existing policy already covers this; cite location; suggest modifying that section." Conflicts append to the log.

**Ingestion (startup script + upload endpoint):** PDF/MD/TXT → extract text (`pypdf` for PDFs) → chunk ~800 tokens with overlap, keeping page/section metadata → Titan embeddings → LLM-assign one topic per chunk from a fixed topic list (tenure & promotion, hiring, workload, curriculum, accessibility, Senate procedures, committees, CBA/labor) → persist to index.

## 5. Data / Corpus

- **Real:** `Unit 3 CBA 2022-2026.pdf` (found in `c:/Users/timot/Downloads/`) — the actual faculty CBA. Ingest a relevant subset (full doc is large; select articles like tenure/service credit if ingestion time is an issue).
- **Real, needs fetching:** University Handbook PDF — publicly hosted; Tim provides the URL or downloaded file (see Your Steps in the handoff).
- **Synthetic gap-fillers:** small authored policy excerpts (styled as Handbook sections / Senate resolutions / PolicyStat entries) engineered so every PRD calibration case fires deterministically in the demo:
  1. **Service credit / tenure clock conflict** — a Handbook snippet that contradicts the real CBA language → chat shows the "multiple answers, consult your dean/Provost" behavior.
  2. **Existing AI policy** — a resolution/appendix covering AI use, so checking a draft "new AI policy" flags existing coverage and suggests modifying it.
  3. **GECCo Committee** — content referring to the committee by its old unexpanded name, findable via semantic search when asked about "GECCo".
  4. **ATI website accessibility appendix** — buried compliance requirement surfaced by chat/browse.
  5. **Schools vs. departments** — two analogous overlapping procedures with no cross-reference, for the overlap demo.

Synthetic files are clearly named (`synthetic-*`) and disclosed to the customer as stand-ins for sources we haven't received yet.

## 6. Success Criteria (demo script)

1. Sign in as employee → ask "Does service credit count toward the tenure clock?" → cited answer flagging the CBA/Handbook conflict with escalation guidance.
2. Ask "What is the GECCo Committee?" → correct answer despite the old name in source text.
3. Browse topics → open Accessibility → see the ATI appendix.
4. Sign in as reviewer → paste a draft AI policy resolution → checker flags existing coverage, cites location, recommends modification instead of a new policy.
5. Open conflict log → see the seeded conflicts plus the one just detected in step 1.
6. (If stable) upload a small policy file → ask a question answered from it.

## 7. Assumptions & Open Items

These were asked but not yet answered; the demo proceeds on the defaults below — flag any you disagree with:

- **Demo scope defaults** (question unanswered): resolution checker and topic browse real; conflict log persisted but pre-seeded; upload wired but optional to demo live.
- **Contradiction display** (open question in PRD §14): contextual — conflicts are flagged when relevant to the question asked, and *all* accumulate in the maker-facing conflict log. Best of both without noisy chat answers.
- **Uploads go straight to the live index** for the demo (no staging/review area); staging is a stated follow-up in the maker path.
- **CSUB-only** scope assumed for the demo corpus.
- **Blocker:** AWS credentials are not configured on this machine (`aws sts get-caller-identity` fails) and Bedrock model access (Titan embeddings + a Claude model) is unverified. Without this, the demo cannot generate answers. Fallback if credentials can't be arranged in time: swap the two Bedrock call sites for Gemini (`GEMINI_API_KEY`) — the code isolates providers in one module to keep this a one-file change.
- Handbook PDF URL/file still needed from Tim.

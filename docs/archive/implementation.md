# Policy Intelligence Assistant — Implementation Plan

Companion to `spec.md`. Target: working customer demo by tomorrow (2026-07-15). Each phase ends in something runnable/verifiable.

## Repo Layout

```
backend/
  app/
    main.py            # FastAPI app, CORS, router registration
    auth.py            # hardcoded demo accounts, POST /api/login
    llm.py             # ALL Bedrock calls live here (embed_texts, generate) — single swap point
    ingest.py          # extract → chunk → embed → topic-tag → persist
    retrieval.py       # load index, cosine top-k with metadata
    chat.py            # POST /api/chat — RAG answer w/ citations + conflict detection
    resolution.py      # POST /api/check-resolution — overlap/duplicate/conflict analysis
    topics.py          # GET /api/topics, GET /api/topics/{name}
    conflicts.py       # GET/POST conflict log (SQLite)
    uploads.py         # POST /api/upload — file → ingest pipeline
    models.py          # Pydantic request/response models
  scripts/
    build_index.py     # one-shot: ingest data/corpus/ into data/index/
    seed_conflicts.py  # seed 2-3 known conflicts into SQLite
  requirements.txt
data/
  corpus/              # source docs (CBA subset, Handbook, synthetic-*.md)
  index/               # chunks.json + embeddings.npy (generated)
  app.db               # SQLite (generated)
frontend/
  src/
    api.ts             # typed fetch client
    App.tsx            # role-based routing
    pages/Login.tsx
    pages/EmployeeDashboard.tsx   # tabs: Chat | Browse Topics
    pages/MakerDashboard.tsx      # tabs: Chat | Check Resolution | Conflict Log | Upload | Browse
    components/Chat.tsx           # thread, citations panel, conflict banner
    components/ResolutionChecker.tsx
    components/TopicBrowser.tsx
    components/ConflictLog.tsx
    components/UploadPanel.tsx
spec.md / implementation.md / CLAUDE.md
```

## Dependencies (ask Tim before installing — hook-guarded)

- **Python (`backend/requirements.txt`):** `fastapi`, `uvicorn`, `boto3`, `pypdf`, `numpy`, `python-multipart` (upload), `pydantic` (comes with FastAPI).
- **Frontend:** Vite scaffold (`npm create vite@latest frontend -- --template react-ts`), `tailwindcss`, `react-router-dom`.

## Phase 0 — Unblock (Tim, before or in parallel with Phase 1)

1. AWS credentials: `! aws configure` (or `aws login` / SSO) with an account that has Bedrock access; set region (e.g. `us-west-2`).
2. Verify model access: `! aws bedrock list-foundation-models --region us-west-2 --query "modelSummaries[?contains(modelId,'titan-embed') || contains(modelId,'claude')].modelId"` — need Titan Text Embeddings V2 + any Claude chat model.
3. Provide Handbook PDF (URL or drop the file into `data/corpus/`).
4. Copy the CBA: `cp "/mnt/c/Users/timot/Downloads/Unit 3 CBA 2022-2026.pdf" data/corpus/`.
5. Approve dependency installs above.

**Fallback if Bedrock is not available by tonight:** implement `llm.py` against Gemini (`GEMINI_API_KEY`) with the same two function signatures; nothing else changes.

## Phase 1 — Corpus & Ingestion Pipeline

1. Author 5 synthetic corpus files in `data/corpus/` (see spec §5): `synthetic-handbook-service-credit.md`, `synthetic-resolution-ai-policy.md`, `synthetic-handbook-gecco.md`, `synthetic-appendix-ati-accessibility.md`, `synthetic-procedures-schools-departments.md`. Each has front-matter-style metadata (title, source type, section).
2. `llm.py`: `embed_texts(texts: list[str]) -> np.ndarray` (Titan, batched) and `generate(system: str, user: str, json_mode: bool = False) -> str` (Claude via Converse API). Retries + timeout.
3. `ingest.py`: extract (pypdf for PDF, plain read for md/txt) → chunk ~800 tokens / 150 overlap, carry `{source, section/page, doc_type}` → embed → one `generate` call per doc to topic-tag chunks from the fixed topic list → append to `data/index/chunks.json` + `embeddings.npy`.
4. `scripts/build_index.py` builds the full index; for the CBA, ingest a selected article subset if full ingestion is slow.
5. **Verify:** run build, then a throwaway script: embed "service credit tenure" → top-3 chunks include both the CBA and the synthetic Handbook snippet.

## Phase 2 — Backend API

1. `auth.py`: `POST /api/login` — if/else against the two demo accounts, returns `{role, name}`. 401 otherwise.
2. `retrieval.py`: load index at startup; `search(query: str, k: int = 8)` returns chunks + scores + metadata.
3. `chat.py`: retrieval → Claude prompt requiring grounded answer, numbered citations mapped to `{source, section}`, and structured conflict field (JSON output). On `conflict.detected`, insert into conflict log. Response: `{answer, citations, conflict}`.
4. `resolution.py`: draft text → retrieval (embed the draft, also embed an LLM-generated summary for better recall) → Claude JSON: `{overlaps[], duplicates[], conflicts[], recommendation}`. Log conflicts.
5. `topics.py`: `GET /api/topics` (topic → count), `GET /api/topics/{name}` (chunks grouped by source, with excerpts).
6. `conflicts.py`: SQLite table `conflicts(id, source_a, source_b, topic, description, status, created_at)`; `GET /api/conflicts`, plus `seed_conflicts.py`.
7. `uploads.py`: accept PDF/MD/TXT → save to `data/corpus/` → run ingest for that file → index hot-reloads (append in memory + persist).
8. **Verify:** `curl` each endpoint; run the spec §6 questions against `/api/chat` and confirm the conflict field fires on the service-credit question.

## Phase 3 — Frontend

1. Scaffold Vite React-TS + Tailwind; `api.ts` typed client; login page → role routing.
2. `Chat.tsx`: message thread, streaming optional (plain request/response is fine for demo), citation chips under each answer linking to source/section, amber conflict banner with escalation text.
3. `EmployeeDashboard`: Chat + TopicBrowser (category grid → policy excerpts with sources).
4. `MakerDashboard`: adds ResolutionChecker (textarea → results grouped as Overlaps / Duplicates / Conflicts / Recommendation), ConflictLog table, UploadPanel (drag-drop, ingestion status).
5. Visual bar: clean, credible, university-appropriate (Tailwind, consistent spacing, real empty/loading/error states on every fetch). No lorem ipsum anywhere.
6. **Verify:** full demo script from spec §6 in the browser, both roles.

## Phase 4 — Demo Hardening (time-permitting, in priority order)

1. Run all 6 demo-script steps twice; fix flakes (esp. prompt/JSON-parse robustness — wrap Claude JSON parsing with one retry-on-invalid).
2. Pre-seed conflict log; confirm chat-detected conflicts append live.
3. Error fallbacks: Bedrock failure → visible "assistant unavailable" state, not a blank screen.
4. README snippet with the two run commands (`uvicorn`, `npm run dev`) and demo accounts.
5. `/codex:review` pass on the finished diff (per Tim's workflow rules).

## Testing

Alongside implementation (not a separate phase): pytest for `ingest.chunk` (boundaries/overlap/metadata), `retrieval.search` (known-corpus top-k), auth (both accounts + reject), and chat/resolution response-shape validation with a mocked `llm.generate`. Bedrock calls are mocked in all tests; live calls only in Phase verify steps.

## Risks

- **Bedrock access (highest):** nothing works without Phase 0.1–0.2. Decide by tonight; Gemini fallback is one file.
- **Full CBA ingestion time/cost:** mitigate by ingesting selected articles.
- **LLM JSON output flakiness in a live demo:** retry-once + graceful degradation (show raw answer without structured extras).
- **Handbook not provided in time:** synthetic snippets already cover every scripted moment; demo remains honest by disclosing stand-ins.

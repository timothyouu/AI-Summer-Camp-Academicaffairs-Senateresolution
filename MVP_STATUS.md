# MVP Status — Policy Intelligence Assistant

_Last updated: 2026-07-16. Snapshot of demo readiness after resolving the broken mid-merge._

## TL;DR

The frontend was **already wired** to the backend chat endpoint (answer + citations +
conflict banner + loading/error states). The only thing blocking the demo was an **unfinished
git merge** (`origin/main` → `lambda-variance-spec`) that left conflict markers in
`backend/app/config.py`, so the backend couldn't even import. That merge is now **resolved**
(favoring the `lambda-variance-spec` generation design) and the app runs end-to-end locally
with **zero AWS required**.

Verifier is green: **177 backend tests pass**, `tsc --noEmit` clean, `vite build` succeeds.

---

## What works now

- **Backend imports and boots.** `uvicorn backend.app.main:app` starts, indexes 609 chunks
  from 16 corpus documents at startup.
- **Health check:** `GET /api/health` → `{"status":"ok","index_chunks":609,"provider":"local-hash-embedding"}`.
- **Chat with citations:** `POST /api/chat` returns a grounded answer, a `citations[]` array
  (source + section + excerpt), an optional `conflict` signal, a `mode`, and a full 6-agent
  `agent_trace`.
- **Conflict detection works:** the WPAF question (Handbook Appendix G vs RES 252644) returns
  `conflict.detected = true` with soft escalation guidance and a logged conflict ID.
- **Frontend is fully wired** to all of the above. `frontend/src/api.ts::askQuestion()` POSTs to
  `/api/chat` and `ChatAnswer.tsx` already renders: answer prose, a **CITED SOURCES** panel, a
  **Policy conflict** banner, loading state, and an error state. Feedback (👍/👎), recurring
  questions, topics, conflicts log, and the resolution checker are all wired too.
- **CORS is correct** for the Vite dev origin — preflight `OPTIONS /api/chat` from
  `http://localhost:5173` returns the expected `access-control-allow-origin` header. A real
  cross-origin browser POST returns `200`.
- **Role paths work:** `X-Role: reviewer` gets full conflict detail; `X-Role: employee` gets the
  softened escalation message with raw conflict sources stripped.
- **Two demo modes, both functional:**
  - **Local (default, no AWS):** calibrated + source-index-grounded answers with citations.
  - **AWS (set `BEDROCK_KB_ID` + Bedrock access):** live KB retrieval + LLM-synthesized answers
    (Strands if installed, else a direct boto3 `converse` fallback — a KB ID alone is enough).

## What is broken / missing / limited

- ~~Broken mid-merge (conflict markers in `config.py`, `factory.py`, `CLAUDE.md`)~~ — **FIXED.**
  Resolved favoring the `lambda-variance-spec` design; `origin/main`'s discarded
  `BEDROCK_GENERATION_ENABLED` / `bedrock_streaming` gate and `_DeterministicLLM` seam did not
  survive; its docs reorg (`PROJECT_SCOPE.md`, `docs/archive/`) was preserved.
- **The merge is resolved but NOT committed.** The working tree is clean of conflict markers and
  everything is staged, but no commit has been made — this is deliberate, pending owner sign-off
  (see "Remaining steps").
- **Local mode does not synthesize prose for arbitrary informational questions.** A
  *non-calibrated* "what is the purpose of…" question in local mode returns an honest safe
  message ("I found related policy sources but can't confidently summarize an answer here")
  **plus real citations** — never a raw chunk dump. Calibrated questions (service credit, FERP,
  WPAF, accessibility, GECCo, 960-hour, 180-day) return full prose. **AWS mode synthesizes prose
  for any question.** For the local demo, drive it with the calibrated questions below.
- **No live AWS verification from this machine.** No AWS credentials are configured here
  (`aws sts get-caller-identity` fails with `NoCredentials`), so the Bedrock path has not been
  exercised from this repo. The `backend/rag/` spike carries two probably-real KB IDs
  (`HHFJ4IDG9M`, `87GR7ILJEF`) but they are unverified live.
- **Cognito is intentionally OFF** for the demo — sign-in is two hardcoded accounts in `auth.py`.

## Exact commands — backend

```bash
# From repo root. Bedrock env MUST be unset for local mode, or the app flips to AWS mode.
python -m backend.scripts.build_index                       # builds the local vector index (once)
env -u BEDROCK_KB_ID -u AWS_REGION -u AWS_PROFILE -u CLAUDE_CODE_USE_BEDROCK \
  python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

Health check:
```bash
curl -s http://127.0.0.1:8000/api/health
```

Sample query:
```bash
curl -s -X POST http://127.0.0.1:8000/api/chat \
  -H "Content-Type: application/json" -H "X-Role: reviewer" \
  -d '{"question":"Does service credit count toward the tenure clock?"}'
```

## Exact commands — frontend

```bash
cd frontend
npm install                                                 # first time only
VITE_API_BASE_URL=http://127.0.0.1:8000 npm run dev -- --port 5173
# open http://localhost:5173
```

> **Important:** set `VITE_API_BASE_URL` so the frontend calls the real backend. Without it the
> frontend defaults to `http://localhost:8000` anyway, but setting it explicitly also makes
> backend failures surface honestly instead of silently falling back to mock answers.

Full verifier (before committing):
```bash
python -m backend.scripts.build_index
env -u BEDROCK_KB_ID -u AWS_REGION -u AWS_PROFILE -u CLAUDE_CODE_USE_BEDROCK python -m pytest backend/tests -q
cd frontend && npx tsc --noEmit && npm run build
```

## Exact env vars

**Local demo (zero AWS) — the recommended path:** leave all AWS vars unset. The only var that
matters is the frontend one:

| Var | Where | Value for local demo |
| --- | --- | --- |
| `VITE_API_BASE_URL` | frontend (Vite) | `http://127.0.0.1:8000` |
| `FRONTEND_ORIGINS` | backend | unset (defaults to localhost:5173/5174) |

**AWS mode (optional, only if Bedrock access is confirmed):** additionally set, in the backend
shell:

| Var | Purpose | Example |
| --- | --- | --- |
| `AWS_REGION` | region for all AWS calls | `us-west-2` |
| `AWS_PROFILE` | local creds (omit on Lambda) | `csub-senate` |
| `BEDROCK_KB_ID` | flips retrieval to the KB + enables live generation | _(from the provisioned KB)_ |
| `BEDROCK_MODEL_ID` | generation model | `us.anthropic.claude-sonnet-4-5-20250929-v1:0` |
| `BEDROCK_GUARDRAIL_ID` / `_VERSION` | optional guardrail | _(from CDK outputs)_ |

Placeholders live in `backend/.env.example`. No secrets are committed. The backend does **not**
auto-load `.env` — `source` it (or `env`-prefix) before `uvicorn`.

## Demo script (local mode, ~4 min)

1. **Start** backend + frontend (commands above). Open `http://localhost:5173`.
2. **Sign in** as the reviewer (`reviewer@campus.edu` / `demo123`).
3. **Cited answer:** ask _"Does service credit count toward the tenure clock?"_
   → grounded answer citing Handbook §304.4.1 and Unit 3 CBA Article 13.4. Expand a source card.
4. **Conflict-aware answer:** ask _"What are the WPAF personnel action file requirements?"_
   → answer plus a **Policy conflict** banner (Handbook Appendix G vs RES 252644). The conflict is
   logged.
5. **Employee view:** switch role to employee, re-ask the WPAF question → same answer but softened
   escalation guidance, raw conflict sources stripped (role-based shaping).
6. **Conflict log:** open the Conflicts page (reviewer only) → the WPAF conflict appears with full
   detail.
7. **Resolution checker:** open Reviews / paste a FERP-related draft → overlaps/duplicates/conflicts
   with a recommendation and the agent trace.

**Safe calibrated questions** (guaranteed full prose in local mode): service credit / tenure clock;
FERP work limits (960-hour); FERP 180-day waiting period; WPAF; accessibility / IMAP; GECCo.

## Remaining risks

- **The resolved merge is uncommitted.** Recommend committing once you've reviewed the resolution
  (favored the `lambda-variance-spec` design). Nothing from `origin/main` was lost except the
  deliberately-superseded generation gate.
- **Local informational-question gap.** If a judge asks a free-form "what is…" question outside the
  calibrated set in local mode, they get the honest safe message + citations, not synthesized prose.
  Mitigation: steer to the calibrated questions, or run AWS mode where synthesis is unconditional.
- **AWS path unverified from this machine.** If you intend to demo on AWS, verify Bedrock model
  access and the KB ID first (see `implementation-aws.md` §3–4 verify commands) — do not assume it
  works live. A KB ID with no model access degrades to the safe message, not a crash.
- **~29s API Gateway cap** in real AWS: the multi-agent Bedrock pipeline can exceed it. The Lambda
  Function URL path (`VITE_AGENT_BASE_URL`) exists to dodge this; unset, `/api/chat` would 5xx at
  ~29s in real AWS (irrelevant to the local demo).
- **Recommendation:** demo locally with the AWS-Bedrock architecture shown on a slide, rather than
  risk a live-AWS deploy under time pressure. The code is AWS-ready; deployment is config, not code.

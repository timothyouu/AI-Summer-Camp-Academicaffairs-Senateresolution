# Frontend Build Progress

Task ledger for the frontend loop. Any agent (Claude or Codex) picking this up cold:
read `frontend/LOOP.md` for methodology, `demo workflow.md` for navigation, and the
frame PNGs in `/mnt/c/Users/timot/.codex/generated_images/019f62e2-8e7b-7702-852c-c8336fb4affa/`.

Statuses: `todo` | `in-progress` | `built (unverified)` | `verified` | `blocked`

## Wave 0 — Scaffold (orchestrator, inline)
| Task | Status | Notes |
|---|---|---|
| PROGRESS.md + LOOP.md | verified | |
| Hand-written Vite/React-TS/Tailwind scaffold (package.json, configs, index.html, main.tsx, index.css) | verified | npm install done by Tim 2026-07-14 |
| Design tokens (navy/gold/cream palette in tailwind.config) | verified | |

## Wave 1 — Foundation (Codex gpt-5.6-sol)
| Task | Status | Notes |
|---|---|---|
| App shell: router (all 12 routes), sidebar (employee + reviewer variants), role switcher, Logo SVG, layout | verified | route table matches spec; browser click-through passed |
| Mock data module + typed api.ts facade (matches implementation.md endpoint shapes) | verified | resolveConflict mutation confirmed in browser |

## Wave 2 — Pages (parallel)
| Task | Tier | Status | Notes |
|---|---|---|---|
| login | terra | verified | screenshot judged vs frame: close match; both role paths navigate |
| chats + chats answer | sol | verified | close match; chip/submit nav, tabs, citations, conflict banner, follow-up append all pass |
| past chats (library) | terra | verified | close match; rows route to answer/topic |
| topic_list + topics | terra | verified | close match; breadcrumb + common-question nav pass |
| review overview | sol | verified | close match; all 5 outbound navigations pass |
| drafts (editor) + review (analysis results) | sol | verified | close match; breadcrumb→/reviews, check→/review, conflict finding→detail |
| conflict (log) + conflict review (detail) | terra | verified | close match; mark-resolved flips row to green Resolved |
| sources | terra | verified | close match; tabs/table/statuses present |

## Wave 3 — Verification loop (orchestrator judged; zero code kick-backs needed)
| Task | Status | Notes |
|---|---|---|
| `npm install` (Tim, `!` prefix) | verified | 137 packages; esbuild binary confirmed working |
| tsc --strict + vite build pass | verified | tsc exit 0; vite build ✓ 53 modules, 2026-07-14 |
| Playwright click-through: all 6 demo paths from demo workflow.md | verified | 24-step script: all navigations pass (2 early "fails" were test-selector issues, re-verified OK) |
| Frame-by-frame screenshot vs PNG judgment (12 frames) | verified | all 12 judged close-match by orchestrator; shots in session scratchpad |
| Mark-resolved state change (conflict review -> conflict shows Resolved) | verified | note + Mark resolved → log row shows Resolved pill |

## Decisions made (2026-07-14)
- Data: typed mocks behind `src/api.ts` facade; no backend calls.
- Logo: hand-built SVG approximation of CSUB shield.
- Fidelity bar: close match (layout/content/palette), not pixel-diff.
- Installs: Tim runs `! cd frontend && npm install` once scaffold lands.

## Verification environment notes (for future loops)
- WSL2 headless Chrome returns blank screenshots via the default Playwright MCP browser
  (GPU compositing). Workaround: launch a second Chrome via `browser_run_code_unsafe`
  with `channel: 'chrome'` and `--disable-gpu`; screenshots then work.
- Run the app: `cd frontend && npm run dev` (port 5173). Build check: `npm run build`.

## Done
Frontend loop complete 2026-07-14. All 12 frames built and verified; every transition in
demo workflow.md works. Backend (implementation.md Phases 0-2) intentionally not built.

## 2026-07-14 late evening - grounded customer-demo hardening
- DONE: Replaced generic history with 15 source-aware conversations covering FERP, CalPERS, WPAF, RTP/PTR, temporary-faculty evaluation, office hours, Emeriti, workload, Accessibility Appendix K, and a carefully limited GECCo answer.
- DONE: Corrected the service-credit record: Handbook 304.4.1 and CBA 13.4 align on up to two years of prior-service credit; the earlier fabricated conflict is no longer reopened by chat.
- DONE: Connected typed questions, chips, topic prompts, follow-ups, review samples, uploads, conflicts, and resolution notes through the typed static API facade. Unknown questions now show an honest calibrated-demo boundary.
- DONE: Added visible behavior for source menus, attachments, citation details, copy/feedback, bookmarks, history clearing, uploads, CSV export, conflict creation, and summary regeneration. Local demo conflicts/uploads persist without a backend.
- VERIFIED: `npm run typecheck` and `npm run build` pass (53 modules). All six demo paths passed in Chromium; fresh console warnings/errors: none.
- LIMITATION: This is intentionally a frontend-only static demo. FastAPI, Bedrock/AWS retrieval, and live indexing from implementation.md Phases 0-2 remain unimplemented.

## 2026-07-14 evening — Sidebar unification (goal session)
- DONE: Sidebar.tsx now renders one 96px icon rail for both roles (wide reviewer variant deleted). Employee items: New chat, Search chats, Topics. Reviewer items: New chat, Search chats, Drafts, Reviews, Conflicts, Topics, Sources.
- DONE: AppLayout margin fixed at ml-24; App.tsx shared routes (/chats, /chats/:id, /library, /topics/*) use SharedRoute (persisted role from RoleProvider), maker-only routes keep WorkspaceRoute forcing reviewer.
- DONE: Library.tsx converted to "Search chats" (chats-only, tabs removed, search + day grouping kept). Route/filename unchanged.
- Verified: tsc --noEmit clean, vite build clean, Playwright click-through of all routes in both roles — rail always 96px, correct item sets, role no longer flips on shared routes. Only console noise is pre-existing favicon 404 + React Router v7 future-flag warnings.
- Orchestration notes: Library page done by Codex; sidebar/routing done by Sonnet subagent (Codex forwarding was blocked by the shell guard hook pattern-matching the goal prompt).

## 2026-07-14 — `implementation.md` local backend integration
- DONE: Added the typed FastAPI API for hardcoded login, locally grounded chat, resolution checking, topic browsing, persistent/pre-seeded conflicts, source upload, and health reporting.
- DONE: Added deterministic local hash embeddings, chunked PDF/Markdown/text ingestion, persisted NumPy/JSON index, hot reload after upload, SQLite persistence, index/seed scripts, and pytest coverage. AWS Bedrock retrieval/generation is intentionally excluded by request.
- DONE: Copied the supplied Handbook, Unit 3 CBA, CalPERS guide, and seven RTP PDFs into the corpus. Added clearly disclosed search aids and demo stand-ins for gaps called out by `implementation.md`.
- DONE: Connected login, chat, resolution review, conflicts, topic browse, and upload from the frontend to the API with reviewed static fallback when the backend is unavailable.
- CORRECTED: Service credit is an alignment between Handbook 304.4.1 and CBA 13.4, not a fabricated conflict. The real WPAF paper/electronic mismatch remains the conflict demonstration.
- VERIFIED: frontend strict TypeScript/Vite production build, Python bytecode compilation, `git diff --check`, and reviewer login plus AI-resolution flow in Chromium. Backend pytest and live endpoint verification await the explicitly required approval to install the named Python dependencies into `backend/.venv`.
- OUT OF SCOPE: `implementation2.md` and AWS Bedrock retrieval/generation.

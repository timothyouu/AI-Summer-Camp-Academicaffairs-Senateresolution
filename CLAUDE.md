# Project: Policy Intelligence Assistant (AI Summer Camp — Academic Affairs / Senate Resolution)

## Purpose
Hackathon customer solution for a university (CSUB): a policy search assistant with two role paths — employees ask a chatbot policy questions and get cited, conflict-aware answers; policy makers/reviewers check draft resolutions for overlap/duplicates/conflicts and review a conflict log. See `spec.md` (what/why) and `implementation.md` (how). Customer demo 2026-07-15; hackathon deadline Friday 7AM.

## Stack
- Frontend: React (Vite, TypeScript strict) + Tailwind CSS
- Backend: FastAPI (Python, typed)
- Database: SQLite (conflict log, upload registry); NumPy + JSON on-disk vector index
- AI/ML: AWS Bedrock via boto3 — Titan Text Embeddings V2 + Claude (Converse API); all calls isolated in `backend/app/llm.py` (Gemini is the designated fallback if Bedrock access falls through)
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
- No AWS credentials configured on this machine yet (Phase 0 blocker — Tim must run aws configure/login and verify Bedrock model access).
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
- Branch `prod` (off `demo`) implements implementation2.md code-side: everything runs locally with zero AWS, and each integration flips to AWS via env vars — see `AWS_SETUP.md` (ordered manual steps) and `LOOP.md` (locked decisions). Verifier: `backend/.venv/bin/python -m pytest backend/tests -q` (17 tests) + `cd frontend && npx tsc --noEmit && npm run build`.
- New: `backend/app/stores.py` (SQLite/DynamoDB store abstraction), `backend/app/agents/` (Notion-design 6-agent conflict pipeline with `agent_trace` output; Strands SDK activates when `strands` importable + `BEDROCK_KB_ID` set), `backend/app/lambda_entry.py` (Mangum), `backend/lambda_handlers/ingestion.py` (S3→KB sync), `infra/` (CDK Python stack, see infra/README.md), `frontend/src/auth/cognito.ts` + `AuthCallback.tsx` (Hosted UI PKCE behind `VITE_USE_COGNITO` — zero new npm deps; aws-amplify deliberately not used), `frontend/src/components/AgentActivity.tsx` (trace panel).
- Not yet installed (approved, pending Tim): boto3, mangum, strands-agents, aws-cdk-lib. All such imports are lazy/guarded; tests must keep passing without them.

## Last Updated
2026-07-14 (evening) — Sidebar unified to one icon rail with persisted role + Library→Search chats (see Sidebar Unification section); verified via tsc, vite build, and Playwright click-through of both roles.

Previous: 2026-07-14 (later) — Frontend COMPLETE and verified: 12 pages (`frontend/src/pages/`), shared layout/sidebar/role-switcher components, typed mocks (`src/data/mock.ts`) behind `src/api.ts`. Verified via tsc --strict, vite build, and a Playwright click-through of all 6 demo paths plus frame-by-frame screenshot judgment (see PROGRESS.md, incl. WSL screenshot workaround). Run with `cd frontend && npm run dev`. Backend still not built.

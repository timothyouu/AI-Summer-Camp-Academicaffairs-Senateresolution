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
- `backend/`, `frontend/`, `data/` — per the layout in implementation.md (not yet scaffolded)

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

## Last Updated
2026-07-14 — Project created: spec.md, implementation.md, CLAUDE.md written from the Notion PRD and two challenge overview files. No code yet.

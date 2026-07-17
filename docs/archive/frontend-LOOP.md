# LOOP.md — Frontend build loop methodology

Read fresh every iteration. Mission does not change even if conversation context compacts.

## Goal
A Vite + React-TS (strict) + Tailwind SPA reproducing the 12 demo frames in
`/mnt/c/Users/timot/.codex/generated_images/019f62e2-8e7b-7702-852c-c8336fb4affa/`
with every transition in `../demo workflow.md` clickable. Frontend only; data comes
from typed mocks behind `src/api.ts` (endpoint shapes per `../implementation.md`).

## Modifiable artifact
`frontend/` only. Read-only: everything else in the repo, the frame PNGs, this file
(workers may not edit LOOP.md), `PROGRESS.md` is append/update-status only.

## Verifier (workers cannot modify)
1. `npx tsc --noEmit` — zero errors (strict mode).
2. `npm run build` — succeeds.
3. Playwright click-through of all 6 demo paths in `../demo workflow.md`
   (Employee Question, Topic Discovery, History, Draft Review, Conflict Resolution,
   Source Management) — every step navigates to the right frame.
4. Screenshot of each of the 12 frames judged by the orchestrator against the PNGs
   (close match: layout regions, labels, palette, typography feel). Workers never
   grade their own visuals.

## Stop rules
- Success: verifier steps 1–4 all pass.
- Budget: max 2 fix rounds per page; same failure twice in a row → stop, log in
  PROGRESS.md, escalate to orchestrator re-plan.
- If a task clearly won't finish in the current session, set its PROGRESS.md status
  and stop cleanly rather than leaving half-broken files.

## Conventions
- Palette (tailwind.config.js tokens): navy `#16305e`, blue `#1d4ed8`/`#2563eb`,
  gold `#f5b301`, cream page bg `#f7f5f1`, amber warning bg `#fef7e6`.
- One file per page in `src/pages/`; shared pieces in `src/components/`;
  all mock content in `src/data/mock.ts`; route map in `src/App.tsx`.
- No new npm dependencies beyond package.json without Tim's approval.
- No lorem ipsum; use the exact copy visible in the frames.

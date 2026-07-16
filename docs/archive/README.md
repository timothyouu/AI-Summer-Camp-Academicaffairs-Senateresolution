# Archived Docs

These files are historical — superseded, mission-complete, or otherwise no longer the
authoritative record. They are kept byte-identical to their pre-archive versions for provenance;
none were edited during the move. **`PROJECT_SCOPE.md` at the repo root is the current entry
point, and root `CLAUDE.md` is the authoritative record of current state** — when anything below
conflicts with either, those two win.

- **spec.md** — original 2026-07-14 customer-demo spec (problem statement, scope, demo script).
  Superseded by CLAUDE.md; kept for the synthetic-corpus-filename list and the non-goals fence.
- **implementation.md** — original phased local-stack build plan. Fully executed; its repo-layout
  tree is stale (many later modules like `registry.py`, `agents/` aren't in it).
- **implementation2.md** — local-to-AWS migration plan for the hackathon. Executed and recorded
  in CLAUDE.md's Deployment Posture and Merge & Decision History sections; kept for its cut-line
  triage ordering and demo script (cut-line order also in PROJECT_SCOPE.md).
- **implementation3.md** — follow-on AWS task list (T1–T11). Code-complete and merged; see
  CLAUDE.md and `updates.md` for the narrative record of what shipped.
- **lambdaspec.md** — spec for the policy variance detection layer. Superseded by the shipped
  `backend/app/agents/variance.py`; its customer-requested escalation wording (§9) was explicitly
  **not** adopted — the shipped string is in CLAUDE.md's Do-Not-Fix / Locked Decisions section and
  `claude-handoff.md` §9. Kept for the severity-taxonomy trigger-condition table (§8) and the
  omission-rule detection logic (§7 Step E), not restated elsewhere.
- **PROGRESS.md** — frontend build task ledger (Wave 0–3). Frontend loop completed 2026-07-14;
  content folded into CLAUDE.md's Do-Not-Fix / Locked Decisions section (sidebar lock).
- **PROGRESS-AWS.md** — append-only orchestration log for the AWS-readiness and implementation3
  loops. Pure commit-by-commit provenance; `updates.md` covers the implementation3 portion in
  richer narrative detail.
- **updates.md** — progress board for the implementation3.md orchestration loop (wave plan,
  file-collision reasoning, cross-task bugs found by browser verification). All 12 tasks
  code-complete and merged to `prod`. Operational gotcha recorded here because it survives the
  loop: the Codex sandbox mounts a worktree's `.git` read-only, so Codex workers **cannot commit**
  — the orchestrator must make the commits itself.
- **claude-handoff.md** — mid-task session handoff written while building the variance layer.
  Its "no variance code written yet" framing is now false (shipped 2026-07-16); kept for §9's
  three resolved design decisions (escalation wording, omission rule, derived authority fields),
  worded more precisely here than in CLAUDE.md.
- **Yaza_DynamoDB_Work_Summary.md** — Yaza Myo Tun's design/build record for the app-memory
  DynamoDB branch (feedback, recurring questions, access-control, source-registry, draft-versions)
  before merge. Nearly fully superseded by the "Yaza's DynamoDB app-memory" entry in CLAUDE.md's
  Merge & Decision History section, which is the reconciled, current record — do not reopen the schema question it describes.
- **LOOP.md** — loop contract for the orchestration run that implemented `implementation2.md` on
  the `prod` worktree. Mission complete; folded into CLAUDE.md's Merge & Decision History. Code
  comments in `infra/stacks/policy_intelligence_stack.py` still cite this file by name/section
  ("mirrors LOOP.md decision 3", "decision 5") — those citations now point at
  `docs/archive/LOOP.md`.
- **frontend-LOOP.md** (originally `frontend/LOOP.md`) — build-loop methodology contract for the
  original 12-frame frontend build. Frontend loop complete 2026-07-14; kept for the exact palette
  hex codes (navy `#16305e`, blue `#1d4ed8`/`#2563eb`, gold `#f5b301`, cream `#f7f5f1`, amber
  warning `#fef7e6`) not recorded elsewhere — `tailwind.config.js` is the real source of truth.

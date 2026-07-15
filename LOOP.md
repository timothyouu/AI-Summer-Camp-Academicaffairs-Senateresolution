# LOOP.md — prod branch: implementation2.md AWS-readiness loop

## Mission
Implement everything in `implementation2.md` on branch `prod` (worktree
`.claude/worktrees/prod`) so that connecting real AWS later is only:
`aws configure` + dependency installs + `cdk deploy` + setting env vars.
No AWS credentials exist on this machine; nothing may require live AWS to run.

## Locked decisions (Tim, 2026-07-15)
1. **Dual-mode**: every AWS integration behind env-driven config. Unset → current
   local stack (NumPy index, SQLite, demo auth) keeps working byte-for-byte.
   Set (KB id, DynamoDB table names, Cognito pool/client, region, bucket) → AWS path.
2. **Agents**: full Notion 6-agent Strands pipeline (orchestrator, retrieval/grounding,
   blind parallel extractors, conflict detector, verifier/adjudicator, escalation) with
   citation-enforced structured outputs, programmatic span verification, abstention as
   a first-class output. Single-prompt fallback preserved behind the same interface
   (implementation2.md cut line 1). Source of truth: Notion page
   "Policy Intelligence Assistant — Needs & MVP Scope" §9.
3. **IaC**: AWS CDK in Python, one stack under `infra/` (S3 corpus bucket + event,
   Bedrock KB + OpenSearch Serverless, DynamoDB ConflictLog/Uploads, Cognito pool +
   groups + hosted UI, Lambda + API Gateway HTTP API + JWT authorizer, ingestion Lambda).
4. **Packages**: none installed by agents (guard hooks block installs). Code against
   them with guarded/lazy imports; add to requirements/package files. boto3 is NOT
   installed in the venv — every boto3/strands/mangum/aws-cdk-lib import must be lazy
   or inside the AWS-mode branch so the verifier passes without them.
5. **Frontend Cognito**: Hosted UI redirect flow (zero new npm deps) behind
   `VITE_USE_COGNITO`; local demo login unchanged when unset. aws-amplify is approved
   but deferred — node_modules is symlinked to the demo tree and must not be mutated
   before today's customer demo.

## Artifact scope
Modifiable: everything in this worktree EXCEPT the verifier below.
Read-only context: `implementation2.md`, `implementation.md`, `spec.md`, `CLAUDE.md`.

## Verifier (locked — agents MUST NOT modify these files or commands)
Existing test files `backend/tests/conftest.py`, `backend/tests/test_api.py`,
`backend/tests/test_ingest_retrieval.py` are frozen. New test files may be added.

From worktree root:
1. `/home/tim/AI-Summer-Camp-Academicaffairs-Senateresolution/backend/.venv/bin/python -m pytest backend/tests -q`
2. `cd frontend && npx tsc --noEmit && npm run build`

Baseline (2026-07-15): 8 passed / tsc clean / build ok.

## Stop rules
- Success: all Phase A–C items of implementation2.md implemented code-side, verifier
  green, `AWS_SETUP.md` handoff doc exists and enumerates every manual step.
- Circuit breaker: the same goal fails its acceptance criteria twice → stop rerunning,
  re-plan or escalate tier (per fable-orchestration).
- Budget: 3 orchestration waves + 1 integration pass; anything left goes in the report.

## Progress log (append-only)
Orchestrator appends one line per goal result to `PROGRESS-AWS.md`:
`<timestamp> <goal-id> <tier> <hit|miss> <one-line evidence>`.

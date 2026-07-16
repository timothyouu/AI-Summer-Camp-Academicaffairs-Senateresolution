# backend/rag — Bedrock RAG spike

Standalone experiment built by Alyssa (GitHub: muldong-alyssa) on `feature/rag`, merged into
`prod` 2026-07-16 (merge `e0d65df`, her commit `063a259`). It is a verification harness for
Bedrock Knowledge Base retrieval plus a Strands agent on top of it — **not** the app's runtime
retrieval or generation path. Nothing under this directory is imported by `backend/app/`.

## What it is

A small, self-contained script set that:
- builds a Strands `Agent` (`agent.py`) wired to two retrieval tools (`retrieval/search.py`),
  one per Knowledge Base;
- exercises that agent against a list of test questions (`model_test.py`, `rag_test.py`,
  `run_tests.py` / `test_retrieval.py`);
- reads configuration from environment variables (`config.py`), with Alyssa's own provisioned
  values as defaults so the scripts run out of the box for her and fail loudly for anyone whose
  account doesn't have the same resources.

There's no FastAPI route, no import from `backend/app`, and no CDK wiring here. It's meant to be
run directly from a shell, not deployed.

## Running it

Run scripts from inside `backend/rag/` (they use flat imports — `from config import MODEL_ID`,
`from retrieval.search import ...` — not package-relative ones):

```
cd backend/rag
pip install -r requirements.txt   # strands-agents, boto3
python agent.py                   # single ad hoc question, prints the answer
python model_test.py              # runs the fixed list of test questions through the agent
```

You need real AWS credentials and Bedrock access for any of this to do something — there is no
local/offline fallback here the way `backend/app/llm.py` has one for the main app. Follow
`implementation-aws.md` §0–1 for account access and IAM, and §3 for Bedrock model access
(Claude + Titan) before running anything. §4 covers Knowledge Base creation if you're standing
up your own KBs rather than pointing at Alyssa's.

## Configuration

`config.py` reads everything from the environment, falling back to the values Alyssa used when
she built this:

| Variable | Default | Notes |
|---|---|---|
| `AWS_REGION` | `us-west-2` | Matches the account-wide region decision in `implementation-aws.md`. |
| `BEDROCK_MODEL_ID` | `us.anthropic.claude-sonnet-4-5-20250929-v1:0` | Cross-region inference profile id — the same model `implementation-aws.md` §3 recommends requesting access to. |
| `ACADEMIC_KB_ID` | `HHFJ4IDG9M` | Knowledge Base covering Academic Affairs policy. |
| `SENATE_KB_ID` | `87GR7ILJEF` | Knowledge Base covering Senate resolutions. |
| `BEDROCK_GUARDRAIL_ID` | unset | Optional; when unset, retrieval/generation runs without a guardrail attached. |
| `BEDROCK_GUARDRAIL_VERSION` | `"1"` | Only meaningful once `BEDROCK_GUARDRAIL_ID` is set. |

Retrieval calls use `vectorSearchConfiguration` against `bedrock-agent-runtime.retrieve`.

**Caveat:** the two Knowledge Base IDs and the model id above are evidence that Alyssa
provisioned real Bedrock resources in `us-west-2` under her own AWS access — they are not
verified as live from this repo. This machine has no AWS credentials configured
(`aws sts get-caller-identity` fails with `NoCredentials`), so nobody has confirmed these IDs
resolve to anything from here. Treat them as "someone did this work," not "this is confirmed
provisioned and current."

## How this maps to the app

This spike and the main app's Bedrock integration are separate seams that happen to talk to the
same AWS services. Don't confuse one for the other:

- **App retrieval** lives in `backend/app/retrieval.py`. It's a single, env-gated Knowledge Base
  lookup (`BEDROCK_KB_ID`) over one corpus bucket, per `implementation-aws.md` §4. There is one
  KB in the app's model, not two.
- **App generation** lives in `backend/app/agents/factory.py` (`StrandsLLM`), which wraps
  Bedrock through the Strands SDK and attaches Bedrock Guardrails when `BEDROCK_GUARDRAIL_ID` is
  set (see `implementation-aws.md` §9 and CLAUDE.md's AWS-Readiness Conformance Pass section).
- **This spike's two-KB split** (academic vs. senate) is Alyssa's own experiment topology —
  a way to test retrieval quality against two differently-scoped corpora side by side. It is not
  a design the app has adopted or is planning to adopt. If the app ever needs more than one KB,
  that's a separate decision to make deliberately, not an inherited default from this directory.

In short: read this directory as a retrieval/generation quality experiment that happened to get
merged in alongside the app, not as a second implementation of the app's RAG path.

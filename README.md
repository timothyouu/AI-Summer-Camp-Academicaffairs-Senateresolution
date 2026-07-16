# Policy Intelligence Assistant

I built this for the AI Summer Camp hackathon (Academic Affairs / Senate Resolution track), as a policy search assistant for CSUB. Employees ask a chatbot about academic policy and get cited, conflict-aware answers. Policy makers and reviewers check draft resolutions for overlap and conflicts against the existing policy corpus, and work from a persistent drafting workspace with a conflict log they can review in full.

I designed the whole system to run dual-mode. By default it's local: deterministic hash-based retrieval, SQLite for the conflict log and upload registry, and a NumPy/JSON on-disk vector index, so the demo needs zero AWS access. Setting the right environment variables flips individual pieces over to AWS (Bedrock, DynamoDB, S3, Cognito, the Strands agent pipeline) without touching the API contracts. Every integration is gated on its own env var, so I can bring pieces onto AWS one at a time instead of an all-or-nothing switch.

I enforce source governance at the API boundary, not just in the UI. Cognito admins manage per-user grants, source owners and reviewer/writers need `can_edit` to change an existing source, and `can_add` alone can't replace one. I gave registry entries canonical URLs plus a section-link index, and both chat citations and the shared resource catalog resolve through that same metadata so a citation always points somewhere real.

I made reviewer drafts persistent instead of browser-only. The Drafts workspace I built supports titled drafts, conversational revision instructions, status changes, version history, version comparison, and restoring an older version as a new one. SQLite backs this locally; setting `DDB_DRAFTS_TABLE` moves it to DynamoDB and S3.

## Tech stack

- **Frontend:** React (Vite, TypeScript strict) with Tailwind CSS.
- **Backend:** FastAPI, typed Python, with Mangum wrapping it for Lambda (`backend/app/lambda_entry.py`).
- **Local persistence:** SQLite for the conflict log and upload registry, plus a NumPy/JSON on-disk vector index for retrieval.
- **AWS persistence:** DynamoDB (conflict log, uploads, registry, permissions, drafts, feedback, recurring questions) and S3 for the corpus bucket and draft version bodies.
- **AI/ML, local:** `backend/app/llm.py` is my local seam. It builds deterministic hash-based embeddings and its `generate()` deliberately raises, so every route falls back to a source-backed deterministic builder. It holds no boto3 Bedrock client; it isn't a Bedrock seam.
- **AI/ML, AWS:** retrieval goes through a Bedrock Knowledge Base (`backend/app/retrieval.py`, gated on `BEDROCK_KB_ID`, embedding with Titan Text Embeddings V2), and generation runs through the Strands SDK wrapping Bedrock (`backend/app/agents/factory.py::StrandsLLM`). Bedrock Guardrails attach to generation when configured. Gemini is my fallback if Bedrock access falls through.
- **Infra:** a single CDK Python stack (`infra/stacks/policy_intelligence_stack.py`) that provisions all seven DynamoDB tables, the S3 corpus bucket, Bedrock KB and Guardrail, OpenSearch Serverless, Lambda plus API Gateway, and Cognito.
- **PDF ingestion:** pypdf for extraction.

## Architecture

I built a six-agent conflict pipeline (`backend/app/agents/`) that emits a full `agent_trace` for every check, and a variance layer (`backend/app/agents/variance.py`) that sits over the pipeline's output as a softer re-labeling pass, without re-implementing retrieval or verification. The pipeline activates Strands when the `strands` package is importable and `BEDROCK_KB_ID` is set; otherwise it stays on the local deterministic path.

A store abstraction (`backend/app/stores.py`) fronts either SQLite or DynamoDB per table, so I never had to write two separate code paths against the routes. Sign-in stays hardcoded and local for the demo (`backend/app/auth.py`, two demo accounts), a deliberate choice I made to keep Cognito off the critical path even though the product spec lists it as a core service.

## Run locally

From the repository root:

```bash
python3 -m venv backend/.venv
backend/.venv/bin/pip install -r backend/requirements.txt
backend/.venv/bin/python -m backend.scripts.build_index
backend/.venv/bin/python -m backend.scripts.seed_conflicts
backend/.venv/bin/uvicorn backend.app.main:app --reload --port 8000
```

In a second terminal:

```bash
cd frontend
npm run dev
```

Open `http://localhost:5173`. The role cards use these demo accounts through the backend when it is available and retain a reviewed static fallback for an offline presentation:

- Employee: `employee@campus.edu` / `demo123`
- Policy reviewer: `reviewer@campus.edu` / `demo123`

API documentation is available at `http://localhost:8000/docs`; health is at `http://localhost:8000/api/health`.

## DynamoDB setup

Every AWS integration is gated on its own environment variable: name a table and
that one store moves to DynamoDB, leave it unset and it stays on SQLite. There is
no global backend switch — an earlier `APP_ENV` / `APP_PERSISTENCE_BACKEND` pair
was removed when the app-memory branch merged, and setting them now does nothing.

The CDK stack (`infra/`) creates all seven tables and injects these variables into
the API Lambda, so a full `cdk deploy` needs none of the steps below. Use the
scripts when you want DynamoDB **on its own** — deploying the whole stack also
stands up OpenSearch Serverless and a Bedrock Knowledge Base, which is slow and
costly just to exercise persistence.

```bash
export AWS_PROFILE=csub-policy
export AWS_REGION=us-west-2

export DDB_CONFLICTS_TABLE=policy-intelligence-conflicts
export DDB_UPLOADS_TABLE=policy-intelligence-uploads
export DDB_REGISTRY_TABLE=policy-intelligence-source-registry
export DDB_PERMISSIONS_TABLE=policy-intelligence-access-control
export DDB_DRAFTS_TABLE=policy-intelligence-draft-versions
export DDB_FEEDBACK_TABLE=policy-intelligence-feedback
export DDB_RECURRING_QUESTIONS_TABLE=policy-intelligence-recurring-questions

./scripts/setup_dynamodb_tables.sh
./scripts/verify_dynamodb_tables.sh
```

The `DYNAMODB_*` names from `docs/archive/Yaza_DynamoDB_Work_Summary.md` §7 are accepted as
aliases for five of the above, so that runbook still works —
`DYNAMODB_SOURCE_REGISTRY_TABLE` sets the registry table,
`DYNAMODB_ACCESS_CONTROL_TABLE` the permissions table, and
`DYNAMODB_DRAFT_VERSIONS_TABLE` the drafts table. Where both spellings are set,
`DDB_*` wins. See `backend/.env.example` for the full list.

`setup_dynamodb_tables.sh` creates only missing tables, waits for ACTIVE, and
never deletes anything. It also checks each existing table's key schema and
**refuses** to proceed if one does not match what the backend reads, printing the
scan and delete commands rather than leaving a table the app cannot use. Tables
provisioned during the earlier app-memory round trip this check by design: their
keys (`conflict_id`, `source_id`, `user_id`+`source_key`, `draft_id`+`version_id`)
predate the merge. `verify_dynamodb_tables.sh` checks every table and GSI and
performs a conditional healthcheck write, deleting only the item it just created.

Do not hand-create these tables — the key schemas must match the stores exactly
(`id` for conflicts/uploads/registry, `user_email`+`source_type` for permissions,
`draft_id`+numeric `version` for drafts, `feedback_id`, `question_id`). Use the
setup script or CDK, both of which encode the correct schemas.

Credentials come from boto3's standard provider chain (AWS CLI profile, SSO, or
an IAM role on Lambda) and must never be committed. Omit `AWS_PROFILE` in
deployed environments so the execution role is used. `DYNAMODB_ENDPOINT_URL`
points every store at a local DynamoDB for offline testing.

List operations use table scans because this is a small demo-scale deployment;
the tables carry GSIs so query-based access patterns can be adopted later without
a rebuild.

## Demo integrity

The copied Handbook, Unit 3 CBA, and CalPERS PDFs are supplied source material. Files whose title contains “Demo stand-in” or “synthetic” are explicitly non-authoritative demo aids. The service-credit scenario is presented as alignment, not a conflict, because the supplied Handbook and CBA both permit up to two years of prior-service credit. Bedrock is not required for this demo.

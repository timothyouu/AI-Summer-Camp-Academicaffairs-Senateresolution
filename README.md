# Policy Intelligence Assistant

A customer-ready policy assistant for exploring CSUB academic policy, asking source-grounded questions, checking draft resolutions, recording conflicts, browsing topics, and uploading PDF/Markdown/text sources. It runs with deterministic local retrieval and SQLite by default; environment variables activate Bedrock, DynamoDB, S3, Cognito, and the Strands agent pipeline without changing API contracts.

Source governance is enforced at the API boundary: Cognito `admins` manage
per-user grants, source owners and reviewer/writers need `can_edit` to change
existing sources, and `can_add` alone cannot replace a source. Registry entries
carry canonical URLs plus a section-link index; chat citations and the shared
resource catalog resolve through that same metadata.

Reviewer drafts are persistent rather than browser-only. The Drafts workspace
supports titled drafts, conversational revision instructions, status changes,
version history, version comparison, and restoring an older version as a new
version. SQLite is used locally and `DDB_DRAFTS_TABLE` activates DynamoDB/S3.

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

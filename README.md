# Policy Intelligence Assistant

A customer-ready local demo for exploring CSUB academic policy, asking source-grounded questions, checking draft resolutions, recording conflicts, browsing topics, and uploading PDF/Markdown/text sources. The retrieval layer uses deterministic local embeddings; AWS Bedrock retrieval and generation are intentionally outside this implementation.

## Run locally

From the repository root in WSL:

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

Local development can continue to use SQLite with
`APP_PERSISTENCE_BACKEND=sqlite`. Production/final deployments must set
`APP_ENV=production` and `APP_PERSISTENCE_BACKEND=dynamodb`; the backend rejects
any production configuration that selects SQLite.

Use these settings for DynamoDB mode:

```bash
export AWS_PROFILE=csub-policy
export AWS_REGION=us-west-2
export APP_ENV=production
export APP_PERSISTENCE_BACKEND=dynamodb
export DYNAMODB_CONFLICTS_TABLE=policy-intelligence-conflicts
export DYNAMODB_FEEDBACK_TABLE=policy-intelligence-feedback
export DYNAMODB_RECURRING_QUESTIONS_TABLE=policy-intelligence-recurring-questions
export DYNAMODB_ACCESS_CONTROL_TABLE=policy-intelligence-access-control
export DYNAMODB_SOURCE_REGISTRY_TABLE=policy-intelligence-source-registry
export DYNAMODB_DRAFT_VERSIONS_TABLE=policy-intelligence-draft-versions

./scripts/setup_dynamodb_tables.sh
./scripts/verify_dynamodb_tables.sh
```

The setup script is idempotent: it creates only missing tables, including the
required GSIs for new tables, waits for them to become active, and never deletes
tables. The verification script checks every table and required GSI, performs a
conditional healthcheck write, and deletes only the item it just created.

For manual setup, create the conflict table outside the app. Use the setup
script above for the complete six-table configuration:

```bash
aws dynamodb create-table \
  --table-name policy-intelligence-conflicts \
  --attribute-definitions AttributeName=conflict_id,AttributeType=S \
  --key-schema AttributeName=conflict_id,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST \
  --region us-west-2
```

The answer-feedback API uses `DYNAMODB_FEEDBACK_TABLE` when DynamoDB is selected.
Create that table outside the app as well:

```bash
aws dynamodb create-table \
  --table-name policy-intelligence-feedback \
  --attribute-definitions AttributeName=feedback_id,AttributeType=S \
  --key-schema AttributeName=feedback_id,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST \
  --region us-west-2
```

Recurring-question tracking uses `DYNAMODB_RECURRING_QUESTIONS_TABLE` when
DynamoDB is selected. Create that table outside the app as well:

```bash
aws dynamodb create-table \
  --table-name policy-intelligence-recurring-questions \
  --attribute-definitions AttributeName=question_id,AttributeType=S \
  --key-schema AttributeName=question_id,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST \
  --region us-west-2
```

The DynamoDB list operations use table scans because this is a small
demo-scale deployment; add appropriate GSIs before using this access pattern
at larger scale.

Set `APP_PERSISTENCE_BACKEND=dynamodb` only after the required tables and AWS
credentials or profile are available. The backend uses boto3's standard
credential provider chain (AWS CLI profile, SSO, or IAM role); credentials must
not be committed to this repo.

## Demo integrity

The copied Handbook, Unit 3 CBA, and CalPERS PDFs are supplied source material. Files whose title contains “Demo stand-in” or “synthetic” are explicitly non-authoritative demo aids. The service-credit scenario is presented as alignment, not a conflict, because the supplied Handbook and CBA both permit up to two years of prior-service credit. Bedrock is not required for this demo.

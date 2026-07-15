# DynamoDB Work Summary

## 1. Overview

This branch implements the DynamoDB app-memory and control layer for the Policy
Intelligence Assistant. The work is deliberately DynamoDB-only: it provides
durable application records and operational table setup without changing the
policy corpus or retrieval pipeline.

S3 storage, Bedrock, Lambda deployment, Strands agents, retrieval logic, and
frontend redesign are outside this scope.

## 2. Why DynamoDB is Used

DynamoDB stores application-level records and metadata, not the underlying
policy documents themselves. It supports:

- Conflict-log records
- Answer feedback
- Recurring policy questions
- Source-access permissions
- Source registry and catalog metadata
- Draft-version metadata

Policy files and draft text remain separate concerns. Draft text should later
live in S3, while DynamoDB stores its searchable, auditable metadata and S3 key.

## 3. Tables Implemented and Provisioned

All tables below are provisioned and verified in AWS `us-west-2`.

### `policy-intelligence-conflicts`

- **Purpose:** Detected or manually created policy conflicts.
- **Primary key:** `conflict_id` (string).
- **Sort key / GSIs:** None.
- **Main fields:** `conflict_id`, `id`, `source_a`, `source_b`, `topic`,
  `description`, `status`, `resolution_note`, `origin`, `created_at`,
  `updated_at`.

### `policy-intelligence-feedback`

- **Purpose:** User feedback on policy answers.
- **Primary key:** `feedback_id` (string).
- **Sort key / GSIs:** None.
- **Main fields:** `feedback_id`, `answer_id`, `question`, `rating`, `comment`,
  `issue_type`, `role`, `citations_used`, `provider`, `created_at`.

### `policy-intelligence-recurring-questions`

- **Purpose:** Aggregates repeated questions asked through chat.
- **Primary key:** `question_id` (string).
- **Sort key / GSIs:** None.
- **Main fields:** `question_id`, `question_text`, `normalized_text`, `topic`,
  `ask_count`, `first_asked_at`, `last_asked_at`, `sample_answer_id`,
  `sample_citations`, `scope`, `visibility`, `created_at`, `updated_at`.

### `policy-intelligence-access-control`

- **Purpose:** Records who can add or edit a specific source or source type.
- **Primary key:** `user_id` (string).
- **Sort key:** `source_key` (string).
- **GSI:** `source-key-user-index` (`source_key`, `user_id`; `ALL` projection).
- **Main fields:** `user_id`, `source_key`, `source_type`, `source_id`,
  `can_add`, `can_edit`, `status`, `granted_by`, `granted_at`, `updated_at`.

### `policy-intelligence-source-registry`

- **Purpose:** Source/catalog registry metadata and active/archive lifecycle
  state.
- **Primary key:** `source_id` (string).
- **GSIs:**
  - `status-last-synced-index` (`status`, `last_synced`)
  - `source-type-last-synced-index` (`source_type`, `last_synced`)
  - `owner-last-synced-index` (`owner`, `last_synced`)
- **Main fields:** `source_id`, `title`, `canonical_url`,
  `canonical_url_normalized`, `source_type`, `owner`, `status`,
  `section_index`, `last_synced`, `s3_key`, `created_at`, `updated_at`,
  `archived_at`, `archived_by`, `activated_at`, `activated_by`, `is_current`,
  `edition_year`.

### `policy-intelligence-draft-versions`

- **Purpose:** Draft-version metadata only; draft text should live in S3 later.
- **Primary key:** `draft_id` (string).
- **Sort key:** `version_id` (string).
- **GSI:** `owner-updated-index` (`owner_user_id`, `updated_at`; `ALL`
  projection).
- **Main fields:** `draft_id`, `version_id`, `title`, `owner_user_id`,
  `created_by`, `status`, `source_ids`, `s3_key`, `parent_version_id`,
  `change_summary`, `created_at`, `updated_at`.

## 4. Backend Code Changes

The backend now includes:

- `boto3` in backend requirements.
- A lazy DynamoDB session/resource/client helper that uses boto3's standard
  credential provider chain and makes no AWS request on import.
- Environment-driven AWS region, profile, endpoint, and table-name settings.
- `APP_ENV` support, with `APP_ENV=production` requiring
  `APP_PERSISTENCE_BACKEND=dynamodb`.
- A store abstraction that selects SQLite or DynamoDB.
- DynamoDB stores for conflicts, feedback, and recurring questions.
- Existing conflict, feedback, and recurring-question endpoints wired through
  that store abstraction.
- Chat responses with `answer_id` and best-effort recurring-question logging.
- SQLite retained for local development and tests.

Relevant implementation files include:

- `backend/app/config.py`
- `backend/app/dynamodb_client.py`
- `backend/app/stores.py`
- `backend/app/conflicts.py`
- `backend/app/feedback.py`
- `backend/app/recurring_questions.py`
- `backend/app/chat.py`
- `backend/app/database.py`
- `backend/app/models.py`

## 5. Scripts Added or Updated

Two scripts manage the DynamoDB schema safely:

- `scripts/setup_dynamodb_tables.sh`
- `scripts/verify_dynamodb_tables.sh`

The setup script creates missing tables idempotently, uses on-demand
(`PAY_PER_REQUEST`) billing, waits for each table to become `ACTIVE`, creates
the required GSIs when a new table is created, and never deletes or recreates
existing tables.

The verification script checks AWS caller identity, lists and describes every
table, checks required GSI status, and writes then deletes one conditional
healthcheck item per table. It uses `AWS_PROFILE` and `AWS_REGION` from the
environment, defaulting to `csub-policy` and `us-west-2`. Neither script stores
or prints credentials.

## 6. AWS Verification Performed

AWS verification was completed using region `us-west-2` and the locally
configured `csub-policy` profile. No AWS account ID, ARN, access key, or other
credential is recorded in this document.

- All six tables were listed successfully.
- All six table healthcheck write/delete operations passed.
- All required GSIs are `ACTIVE`.
- Application-level writes were manually verified for:
  - `POST /api/feedback` to `policy-intelligence-feedback`
  - Conflict creation to `policy-intelligence-conflicts`
  - `POST /api/chat` recurring-question logging to
    `policy-intelligence-recurring-questions`

## 7. Environment Variables

Production DynamoDB mode uses these non-secret settings:

```bash
AWS_PROFILE=csub-policy
AWS_REGION=us-west-2
APP_ENV=production
APP_PERSISTENCE_BACKEND=dynamodb
DYNAMODB_CONFLICTS_TABLE=policy-intelligence-conflicts
DYNAMODB_FEEDBACK_TABLE=policy-intelligence-feedback
DYNAMODB_RECURRING_QUESTIONS_TABLE=policy-intelligence-recurring-questions
DYNAMODB_ACCESS_CONTROL_TABLE=policy-intelligence-access-control
DYNAMODB_SOURCE_REGISTRY_TABLE=policy-intelligence-source-registry
DYNAMODB_DRAFT_VERSIONS_TABLE=policy-intelligence-draft-versions
```

For a deployed production backend, omit `AWS_PROFILE` and use an IAM role.
AWS access keys must never be committed or placed in frontend code.

## 8. Local and Production Behavior

- Development can use SQLite.
- Production requires DynamoDB through `APP_ENV=production` and
  `APP_PERSISTENCE_BACKEND=dynamodb`.
- Public users never access DynamoDB directly.
- The frontend calls the backend API.
- The backend uses its AWS profile or IAM role to access DynamoDB.

## 9. Testing Completed

Reported verification and build checks to date:

- Backend tests passed.
- Frontend build passed after the feedback and recurring-question changes.
- `git diff --check` passed.
- The DynamoDB verification script passed after all tables became `ACTIVE`.

## 10. Known Limitations and Out of Scope

- DynamoDB `Scan` is acceptable for small/demo listings. Production-scale
  access patterns should use the designed GSIs where applicable.
- Access-control, source-registry, and draft-version backend APIs are not
  implemented yet.
- S3 upload, Bedrock generation, catalog scraping, Lambda deployment, Strands
  agents, retrieval filtering, and frontend administration panels are separate
  work.
- Draft text must not be stored in DynamoDB; store only metadata and an S3 key.

## 11. Suggested Next DynamoDB-Only Commits

1. Source-registry store and archive/activate API.
2. Access-control store and grant/revoke/list API.
3. Draft-version metadata store and version list/get/create API.
4. Optional user-role mapping only if local authentication needs durable role
   assignments.

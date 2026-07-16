from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
# Lambda's filesystem is read-only outside /tmp, and startup creates the data
# directories unconditionally — so on Lambda the default must live under /tmp.
_DEFAULT_DATA_ROOT = Path("/tmp/policy-data") if os.getenv("AWS_LAMBDA_FUNCTION_NAME") else REPO_ROOT / "data"
DATA_ROOT = Path(os.getenv("POLICY_DATA_ROOT", _DEFAULT_DATA_ROOT))
CORPUS_DIR = DATA_ROOT / "corpus"
INDEX_DIR = DATA_ROOT / "index"
DATABASE_PATH = Path(os.getenv("POLICY_DATABASE_PATH", DATA_ROOT / "app.db"))
UPLOAD_DIR = CORPUS_DIR / "uploads"
# Shared by the API upload endpoints and the ingestion Lambda (which must not
# import the FastAPI app), so it lives here rather than in uploads.py.
MAX_UPLOAD_BYTES = 20 * 1024 * 1024


@dataclass(frozen=True)
class Settings:
    aws_region: str | None = None
    aws_profile: str | None = None
    dynamodb_endpoint_url: str | None = None
    bedrock_kb_id: str | None = None
    ddb_conflicts_table: str | None = None
    ddb_uploads_table: str | None = None
    ddb_registry_table: str | None = None
    ddb_permissions_table: str | None = None
    ddb_drafts_table: str | None = None
    ddb_feedback_table: str | None = None
    ddb_recurring_questions_table: str | None = None
    corpus_bucket: str | None = None
    cognito_user_pool_id: str | None = None
    cognito_client_id: str | None = None

    @property
    def retrieval_aws(self) -> bool:
        return bool(self.bedrock_kb_id)

    @property
    def conflicts_aws(self) -> bool:
        return bool(self.ddb_conflicts_table)

    @property
    def uploads_aws(self) -> bool:
        return bool(self.ddb_uploads_table)

    @property
    def registry_aws(self) -> bool:
        return bool(self.ddb_registry_table)

    @property
    def permissions_aws(self) -> bool:
        return bool(self.ddb_permissions_table)

    @property
    def drafts_aws(self) -> bool:
        return bool(self.ddb_drafts_table)

    @property
    def feedback_aws(self) -> bool:
        return bool(self.ddb_feedback_table)

    @property
    def recurring_questions_aws(self) -> bool:
        return bool(self.ddb_recurring_questions_table)

    @property
    def corpus_aws(self) -> bool:
        return bool(self.corpus_bucket)

    @property
    def cognito_aws(self) -> bool:
        return bool(self.cognito_user_pool_id and self.cognito_client_id)


def get_settings() -> Settings:
    """Read mode switches at use time, which also keeps tests and workers predictable.

    Each table is gated independently: naming a table opts that one feature into
    DynamoDB and leaves the rest on SQLite. The DYNAMODB_* spellings are accepted
    as aliases so the table names provisioned by scripts/setup_dynamodb_tables.sh
    configure the same stores as the DDB_* names the CDK stack emits.
    """
    value = lambda name: os.getenv(name) or None
    first = lambda *names: next((candidate for name in names if (candidate := value(name))), None)
    return Settings(
        aws_region=value("AWS_REGION"), aws_profile=value("AWS_PROFILE"),
        dynamodb_endpoint_url=value("DYNAMODB_ENDPOINT_URL"),
        bedrock_kb_id=value("BEDROCK_KB_ID"),
        ddb_conflicts_table=first("DDB_CONFLICTS_TABLE", "DYNAMODB_CONFLICTS_TABLE"),
        ddb_uploads_table=first("DDB_UPLOADS_TABLE", "DYNAMODB_UPLOADS_TABLE"),
        ddb_registry_table=first("DDB_REGISTRY_TABLE", "DYNAMODB_SOURCE_REGISTRY_TABLE"),
        ddb_permissions_table=first("DDB_PERMISSIONS_TABLE", "DYNAMODB_ACCESS_CONTROL_TABLE"),
        ddb_drafts_table=first("DDB_DRAFTS_TABLE", "DYNAMODB_DRAFT_VERSIONS_TABLE"),
        ddb_feedback_table=first("DDB_FEEDBACK_TABLE", "DYNAMODB_FEEDBACK_TABLE"),
        ddb_recurring_questions_table=first("DDB_RECURRING_QUESTIONS_TABLE", "DYNAMODB_RECURRING_QUESTIONS_TABLE"),
        corpus_bucket=value("CORPUS_BUCKET"), cognito_user_pool_id=value("COGNITO_USER_POOL_ID"),
        cognito_client_id=value("COGNITO_CLIENT_ID"),
    )


def ensure_data_directories() -> None:
    for directory in (DATA_ROOT, CORPUS_DIR, INDEX_DIR, UPLOAD_DIR):
        directory.mkdir(parents=True, exist_ok=True)

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

# Vite's default port, plus the next port it falls back to when 5173 is taken.
DEFAULT_DEV_ORIGINS = (
    "http://localhost:5173", "http://127.0.0.1:5173",
    "http://localhost:5174", "http://127.0.0.1:5174",
)


def allowed_origins() -> list[str]:
    """Browser origins the API accepts, overridable for non-default dev ports.

    Deployed traffic is CORS-checked by API Gateway and the Lambda Function URL
    (both fed by the stack's `frontendOrigin` context), so this list only has to
    cover local dev — where a second worktree lands on an unexpected Vite port
    and would otherwise be blocked with no way to configure it.
    """
    configured = os.getenv("FRONTEND_ORIGINS")
    if not configured:
        return list(DEFAULT_DEV_ORIGINS)
    return [origin.strip().rstrip("/") for origin in configured.split(",") if origin.strip()]


@dataclass(frozen=True)
class Settings:
    aws_region: str | None = None
    aws_profile: str | None = None
    dynamodb_endpoint_url: str | None = None
    bedrock_kb_id: str | None = None
    bedrock_kb_search_mode: str = "vector"
    bedrock_model_id: str = "us.anthropic.claude-sonnet-4-5-20250929-v1:0"
    # Optional cheaper/faster model for the pipeline's mechanical JSON stages
    # (extract/detect/verify). Unset -> every stage uses bedrock_model_id, i.e.
    # today's behavior byte-for-byte. Set -> the mechanical stages use this model
    # while user-facing prose (answer synthesis, draft revision) stays on
    # bedrock_model_id. Lets Haiku carry the fan-out without touching answer
    # quality. See CLAUDE.md "Verify tuning follow-ups".
    bedrock_fast_model_id: str | None = None
    # Bounded so a throttled/stalled Bedrock socket fails fast instead of hanging
    # the worker. boto3 defaults (60s read x 4 retries ≈ 5 min) can wedge the
    # request thread — and the pipeline's ThreadPoolExecutor blocks on it.
    bedrock_connect_timeout: float = 5.0
    bedrock_read_timeout: float = 25.0
    bedrock_max_attempts: int = 2
    bedrock_guardrail_id: str | None = None
    bedrock_guardrail_version: str | None = None
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
    def guardrails_aws(self) -> bool:
        return bool(self.bedrock_guardrail_id)

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
        bedrock_kb_search_mode=(value("BEDROCK_KB_SEARCH_MODE") or "vector").strip().lower(),
        bedrock_model_id=value("BEDROCK_MODEL_ID") or "us.anthropic.claude-sonnet-4-5-20250929-v1:0",
        bedrock_fast_model_id=value("BEDROCK_FAST_MODEL_ID"),
        bedrock_connect_timeout=float(value("BEDROCK_CONNECT_TIMEOUT") or 5.0),
        bedrock_read_timeout=float(value("BEDROCK_READ_TIMEOUT") or 25.0),
        bedrock_max_attempts=int(value("BEDROCK_MAX_ATTEMPTS") or 2),
        bedrock_guardrail_id=value("BEDROCK_GUARDRAIL_ID"),
        bedrock_guardrail_version=value("BEDROCK_GUARDRAIL_VERSION"),
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


def bedrock_client_config(settings: Settings | None = None):  # type: ignore[no-untyped-def]
    """Bounded botocore Config for Bedrock clients (lazy botocore import).

    Keeps a single source of truth for the timeout/retry policy so both the
    runtime (generation) and agent-runtime (KB retrieval) clients fail fast
    instead of hanging the request thread on a stalled or throttled socket.
    """
    from botocore.config import Config  # Lazy: botocore only present in AWS mode.

    settings = settings or get_settings()
    return Config(
        connect_timeout=settings.bedrock_connect_timeout,
        read_timeout=settings.bedrock_read_timeout,
        retries={"max_attempts": settings.bedrock_max_attempts, "mode": "standard"},
    )


def ensure_data_directories() -> None:
    for directory in (DATA_ROOT, CORPUS_DIR, INDEX_DIR, UPLOAD_DIR):
        directory.mkdir(parents=True, exist_ok=True)

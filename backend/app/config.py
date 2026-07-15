from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


SUPPORTED_PERSISTENCE_BACKENDS = frozenset({"sqlite", "dynamodb"})
SUPPORTED_APP_ENVIRONMENTS = frozenset({"development", "production"})


class PersistenceConfigurationError(ValueError):
    """Raised when persistence environment configuration is unsupported."""


@dataclass(frozen=True)
class PersistenceSettings:
    """Environment-driven persistence settings shared by future stores."""

    app_env: str
    backend: str
    aws_region: str
    aws_profile: str | None
    dynamodb_endpoint_url: str | None
    dynamodb_conflicts_table: str
    dynamodb_feedback_table: str
    dynamodb_recurring_questions_table: str
    dynamodb_access_control_table: str
    dynamodb_source_registry_table: str
    dynamodb_draft_versions_table: str


def _optional_setting(values: Mapping[str, str], name: str) -> str | None:
    value = values.get(name, "").strip()
    return value or None


def _table_setting(
    values: Mapping[str, str], name: str, default: str, app_env: str
) -> str:
    """Use a default table name unless production explicitly supplies a blank value."""
    raw_value = values.get(name)
    if raw_value is None:
        return default
    value = raw_value.strip()
    if app_env == "production" and not value:
        raise PersistenceConfigurationError(
            f"{name} must be non-empty when APP_ENV=production."
        )
    return value or default


def load_persistence_settings(values: Mapping[str, str] | None = None) -> PersistenceSettings:
    """Read persistence configuration without making an AWS request."""
    environment = os.environ if values is None else values
    app_env = environment.get("APP_ENV", "development").strip().lower() or "development"
    if app_env not in SUPPORTED_APP_ENVIRONMENTS:
        supported = ", ".join(sorted(SUPPORTED_APP_ENVIRONMENTS))
        raise PersistenceConfigurationError(
            f"Unsupported APP_ENV={app_env!r}. Use one of: {supported}."
        )
    backend = environment.get("APP_PERSISTENCE_BACKEND", "sqlite").strip().lower()
    if backend not in SUPPORTED_PERSISTENCE_BACKENDS:
        supported = ", ".join(sorted(SUPPORTED_PERSISTENCE_BACKENDS))
        raise PersistenceConfigurationError(
            f"Unsupported APP_PERSISTENCE_BACKEND={backend!r}. Use one of: {supported}."
        )
    if app_env == "production" and backend != "dynamodb":
        raise PersistenceConfigurationError(
            "APP_ENV=production requires APP_PERSISTENCE_BACKEND=dynamodb."
        )

    return PersistenceSettings(
        app_env=app_env,
        backend=backend,
        aws_region=environment.get("AWS_REGION", "us-west-2").strip() or "us-west-2",
        aws_profile=_optional_setting(environment, "AWS_PROFILE"),
        dynamodb_endpoint_url=_optional_setting(environment, "DYNAMODB_ENDPOINT_URL"),
        dynamodb_conflicts_table=_table_setting(
            environment, "DYNAMODB_CONFLICTS_TABLE", "policy-intelligence-conflicts", app_env
        ),
        dynamodb_feedback_table=_table_setting(
            environment, "DYNAMODB_FEEDBACK_TABLE", "policy-intelligence-feedback", app_env
        ),
        dynamodb_recurring_questions_table=_table_setting(
            environment,
            "DYNAMODB_RECURRING_QUESTIONS_TABLE",
            "policy-intelligence-recurring-questions",
            app_env,
        ),
        dynamodb_access_control_table=_table_setting(
            environment,
            "DYNAMODB_ACCESS_CONTROL_TABLE",
            "policy-intelligence-access-control",
            app_env,
        ),
        dynamodb_source_registry_table=_table_setting(
            environment,
            "DYNAMODB_SOURCE_REGISTRY_TABLE",
            "policy-intelligence-source-registry",
            app_env,
        ),
        dynamodb_draft_versions_table=_table_setting(
            environment,
            "DYNAMODB_DRAFT_VERSIONS_TABLE",
            "policy-intelligence-draft-versions",
            app_env,
        ),
    )


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
    bedrock_kb_id: str | None = None
    ddb_conflicts_table: str | None = None
    ddb_uploads_table: str | None = None
    ddb_feedback_table: str | None = None
    ddb_recurring_questions_table: str | None = None
    ddb_access_control_table: str | None = None
    ddb_source_registry_table: str | None = None
    ddb_draft_versions_table: str | None = None
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
    """Read mode switches at use time, which also keeps tests and workers predictable."""
    value = lambda name: os.getenv(name) or None
    first = lambda *names: next((candidate for name in names if (candidate := value(name))), None)
    return Settings(
        aws_region=value("AWS_REGION"), bedrock_kb_id=value("BEDROCK_KB_ID"),
        ddb_conflicts_table=first("DDB_CONFLICTS_TABLE", "DYNAMODB_CONFLICTS_TABLE"),
        ddb_uploads_table=value("DDB_UPLOADS_TABLE"),
        ddb_feedback_table=first("DDB_FEEDBACK_TABLE", "DYNAMODB_FEEDBACK_TABLE"),
        ddb_recurring_questions_table=first("DDB_RECURRING_QUESTIONS_TABLE", "DYNAMODB_RECURRING_QUESTIONS_TABLE"),
        ddb_access_control_table=first("DDB_ACCESS_CONTROL_TABLE", "DYNAMODB_ACCESS_CONTROL_TABLE"),
        ddb_source_registry_table=first("DDB_SOURCE_REGISTRY_TABLE", "DYNAMODB_SOURCE_REGISTRY_TABLE"),
        ddb_draft_versions_table=first("DDB_DRAFT_VERSIONS_TABLE", "DYNAMODB_DRAFT_VERSIONS_TABLE"),
        corpus_bucket=value("CORPUS_BUCKET"), cognito_user_pool_id=value("COGNITO_USER_POOL_ID"),
        cognito_client_id=value("COGNITO_CLIENT_ID"),
    )


PERSISTENCE_SETTINGS = load_persistence_settings()

# Kept as module-level names for simple use by future DynamoDB stores.
APP_PERSISTENCE_BACKEND = PERSISTENCE_SETTINGS.backend
APP_ENV = PERSISTENCE_SETTINGS.app_env
AWS_REGION = PERSISTENCE_SETTINGS.aws_region
AWS_PROFILE = PERSISTENCE_SETTINGS.aws_profile
DYNAMODB_ENDPOINT_URL = PERSISTENCE_SETTINGS.dynamodb_endpoint_url
DYNAMODB_CONFLICTS_TABLE = PERSISTENCE_SETTINGS.dynamodb_conflicts_table
DYNAMODB_FEEDBACK_TABLE = PERSISTENCE_SETTINGS.dynamodb_feedback_table
DYNAMODB_RECURRING_QUESTIONS_TABLE = PERSISTENCE_SETTINGS.dynamodb_recurring_questions_table
DYNAMODB_ACCESS_CONTROL_TABLE = PERSISTENCE_SETTINGS.dynamodb_access_control_table
DYNAMODB_SOURCE_REGISTRY_TABLE = PERSISTENCE_SETTINGS.dynamodb_source_registry_table
DYNAMODB_DRAFT_VERSIONS_TABLE = PERSISTENCE_SETTINGS.dynamodb_draft_versions_table


def ensure_data_directories() -> None:
    for directory in (DATA_ROOT, CORPUS_DIR, INDEX_DIR, UPLOAD_DIR):
        directory.mkdir(parents=True, exist_ok=True)

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_ROOT = Path(os.getenv("POLICY_DATA_ROOT", REPO_ROOT / "data"))
CORPUS_DIR = DATA_ROOT / "corpus"
INDEX_DIR = DATA_ROOT / "index"
DATABASE_PATH = Path(os.getenv("POLICY_DATABASE_PATH", DATA_ROOT / "app.db"))
UPLOAD_DIR = CORPUS_DIR / "uploads"


@dataclass(frozen=True)
class Settings:
    aws_region: str | None = None
    bedrock_kb_id: str | None = None
    ddb_conflicts_table: str | None = None
    ddb_uploads_table: str | None = None
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
    def corpus_aws(self) -> bool:
        return bool(self.corpus_bucket)

    @property
    def cognito_aws(self) -> bool:
        return bool(self.cognito_user_pool_id and self.cognito_client_id)


def get_settings() -> Settings:
    """Read mode switches at use time, which also keeps tests and workers predictable."""
    value = lambda name: os.getenv(name) or None
    return Settings(
        aws_region=value("AWS_REGION"), bedrock_kb_id=value("BEDROCK_KB_ID"),
        ddb_conflicts_table=value("DDB_CONFLICTS_TABLE"), ddb_uploads_table=value("DDB_UPLOADS_TABLE"),
        corpus_bucket=value("CORPUS_BUCKET"), cognito_user_pool_id=value("COGNITO_USER_POOL_ID"),
        cognito_client_id=value("COGNITO_CLIENT_ID"),
    )


def ensure_data_directories() -> None:
    for directory in (DATA_ROOT, CORPUS_DIR, INDEX_DIR, UPLOAD_DIR):
        directory.mkdir(parents=True, exist_ok=True)

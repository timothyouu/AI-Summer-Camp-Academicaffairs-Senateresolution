from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager

from .config import DATABASE_PATH, ensure_data_directories


SCHEMA = """
CREATE TABLE IF NOT EXISTS conflicts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_a TEXT NOT NULL,
    source_b TEXT NOT NULL,
    topic TEXT NOT NULL,
    description TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'Open',
    resolution_note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(source_a, source_b, topic, description)
);
CREATE TABLE IF NOT EXISTS uploads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    upload_id TEXT NOT NULL UNIQUE,
    filename TEXT NOT NULL,
    status TEXT NOT NULL,
    chunks_added INTEGER NOT NULL,
    ingestion_job_id TEXT,
    error TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS registry (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    source_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'archived',
    canonical_url TEXT NOT NULL DEFAULT '',
    edition_year INTEGER,
    is_current INTEGER NOT NULL DEFAULT 1,
    s3_key TEXT NOT NULL DEFAULT '',
    passages INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS permissions (
    user_email TEXT NOT NULL,
    source_type TEXT NOT NULL,
    can_add INTEGER NOT NULL DEFAULT 0,
    can_edit INTEGER NOT NULL DEFAULT 0,
    granted_by TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_email, source_type)
);
CREATE TABLE IF NOT EXISTS drafts (
    draft_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    text TEXT NOT NULL,
    suggestion TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (draft_id, version)
);
"""


@contextmanager
def connection() -> Iterator[sqlite3.Connection]:
    ensure_data_directories()
    database = sqlite3.connect(DATABASE_PATH)
    database.row_factory = sqlite3.Row
    try:
        yield database
        database.commit()
    finally:
        database.close()


def initialize_database() -> None:
    with connection() as database:
        database.executescript(SCHEMA)
        columns = {str(row["name"]) for row in database.execute("PRAGMA table_info(uploads)").fetchall()}
        if "upload_id" not in columns:
            database.executescript("""
                ALTER TABLE uploads RENAME TO uploads_legacy;
                CREATE TABLE uploads (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    upload_id TEXT NOT NULL UNIQUE,
                    filename TEXT NOT NULL,
                    status TEXT NOT NULL,
                    chunks_added INTEGER NOT NULL,
                    ingestion_job_id TEXT,
                    error TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                INSERT INTO uploads(upload_id, filename, status, chunks_added, created_at)
                SELECT filename, filename, status, chunks_added, created_at FROM uploads_legacy;
                DROP TABLE uploads_legacy;
            """)

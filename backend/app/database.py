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
    filename TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL,
    chunks_added INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS feedback (
    feedback_id TEXT PRIMARY KEY,
    answer_id TEXT NOT NULL,
    question TEXT NOT NULL,
    rating TEXT NOT NULL,
    comment TEXT NOT NULL DEFAULT '',
    issue_type TEXT NOT NULL DEFAULT '',
    role TEXT NOT NULL DEFAULT '',
    citations_used TEXT NOT NULL DEFAULT '[]',
    provider TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS recurring_questions (
    question_id TEXT PRIMARY KEY,
    question_text TEXT NOT NULL,
    normalized_text TEXT NOT NULL,
    topic TEXT NOT NULL DEFAULT 'general',
    ask_count INTEGER NOT NULL DEFAULT 1,
    first_asked_at TEXT NOT NULL,
    last_asked_at TEXT NOT NULL,
    sample_answer_id TEXT NOT NULL DEFAULT '',
    sample_citations TEXT NOT NULL DEFAULT '[]',
    scope TEXT NOT NULL DEFAULT 'global',
    visibility TEXT NOT NULL DEFAULT 'published',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
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

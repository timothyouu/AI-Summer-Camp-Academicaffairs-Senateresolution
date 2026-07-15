from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


TEST_DATA_ROOT = Path(tempfile.mkdtemp(prefix="policy-intelligence-tests-"))
os.environ["POLICY_DATA_ROOT"] = str(TEST_DATA_ROOT)
os.environ["POLICY_DATABASE_PATH"] = str(TEST_DATA_ROOT / "app.db")

from backend.app.main import app  # noqa: E402


@pytest.fixture()
def client() -> TestClient:
    corpus = TEST_DATA_ROOT / "corpus"
    corpus.mkdir(parents=True, exist_ok=True)
    corpus.joinpath("test-policy.md").write_text(
        "---\ntitle: Test Policy\nsource_type: policy\nsection: Article 1\n---\n"
        "Prior service credit and tenure review are governed by the appointment record. "
        "FERP retirement work limits must satisfy the collective bargaining agreement.",
        encoding="utf-8",
    )
    with TestClient(app) as test_client:
        yield test_client

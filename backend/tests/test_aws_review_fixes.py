from __future__ import annotations

import sys
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from backend.app import auth, conflicts
from backend.app.main import app
from backend.app.models import ConflictUpdate
from backend.app.stores import DynamoDBConflictStore
from backend.lambda_handlers import ingestion


@pytest.mark.parametrize(
    ("method", "url", "payload"),
    [
        ("post", "/api/conflicts", {"source_a": "A", "source_b": "B", "topic": "T", "description": "D"}),
        ("patch", "/api/conflicts/1", {"status": "Resolved"}),
    ],
)
def test_cognito_employee_cannot_mutate_conflicts(
    client: TestClient, monkeypatch: Any, method: str, url: str, payload: dict[str, str],
) -> None:
    monkeypatch.setenv("COGNITO_USER_POOL_ID", "us-west-2_pool")
    monkeypatch.setenv("COGNITO_CLIENT_ID", "client")
    monkeypatch.setattr(auth, "decode_and_verify_token", lambda _token, _settings: {"cognito:groups": ["employees"]})

    response = getattr(client, method)(url, json=payload, headers={"Authorization": "Bearer employee-token"})

    assert response.status_code == 403
    assert response.json() == {"detail": "Reviewer role required"}


@pytest.mark.parametrize(
    ("method", "url", "payload"),
    [
        ("post", "/api/uploads/presign", {"filename": "policy.pdf", "content_type": "application/pdf"}),
        ("post", "/api/check-resolution", {"text": "A draft resolution about AI policy."}),
    ],
)
def test_cognito_employee_cannot_use_reviewer_workflows(
    client: TestClient, monkeypatch: Any, method: str, url: str, payload: dict[str, str],
) -> None:
    monkeypatch.setenv("COGNITO_USER_POOL_ID", "us-west-2_pool")
    monkeypatch.setenv("COGNITO_CLIENT_ID", "client")
    monkeypatch.setattr(auth, "decode_and_verify_token", lambda _token, _settings: {"cognito:groups": ["employees"]})

    response = getattr(client, method)(url, json=payload, headers={"Authorization": "Bearer employee-token"})

    assert response.status_code == 403
    assert response.json() == {"detail": "Reviewer role required"}


def test_ingestion_reuses_active_job_after_concurrent_job_conflict(monkeypatch: Any) -> None:
    class ConcurrentJobError(Exception):
        response = {"Error": {"Code": "ConflictException", "Message": "A concurrent ingestion job is already running"}}

    class Store:
        def __init__(self) -> None:
            self.calls: list[dict[str, object]] = []

        def register(
            self, filename: str, status: str, chunks_added: int = 0, upload_id: str | None = None,
            ingestion_job_id: str | None = None,
        ) -> str:
            self.calls.append({
                "filename": filename, "status": status, "chunks_added": chunks_added,
                "upload_id": upload_id, "ingestion_job_id": ingestion_job_id,
            })
            return upload_id or filename

    class BedrockClient:
        def __init__(self) -> None:
            self.start_calls = 0

        def list_data_sources(self, **kwargs: object) -> dict[str, object]:
            assert kwargs == {"knowledgeBaseId": "kb-123", "maxResults": 10}
            return {"dataSourceSummaries": [{"dataSourceId": "source-123"}]}

        def start_ingestion_job(self, **kwargs: object) -> dict[str, object]:
            self.start_calls += 1
            assert kwargs == {"knowledgeBaseId": "kb-123", "dataSourceId": "source-123"}
            raise ConcurrentJobError()

        def list_ingestion_jobs(self, **kwargs: object) -> dict[str, object]:
            assert kwargs == {"knowledgeBaseId": "kb-123", "dataSourceId": "source-123", "maxResults": 100}
            return {"ingestionJobSummaries": [{"ingestionJobId": "active-job", "status": "IN_PROGRESS"}]}

    store = Store()
    bedrock = BedrockClient()
    monkeypatch.setenv("AWS_REGION", "us-west-2")
    monkeypatch.setenv("BEDROCK_KB_ID", "kb-123")
    monkeypatch.setenv("DDB_UPLOADS_TABLE", "Uploads")
    monkeypatch.setattr(ingestion, "upload_store", lambda: store)
    monkeypatch.setitem(sys.modules, "boto3", SimpleNamespace(client=lambda *_args, **_kwargs: bedrock))

    response = ingestion.handler({"Records": [
        {"s3": {"object": {"key": "uploads%2Fhandbook.pdf"}}},
        {"s3": {"object": {"key": "uploads%2Fpolicy.md"}}},
    ]}, object())

    assert response == {"processed": 2}
    assert bedrock.start_calls == 1
    assert store.calls == [
        {"filename": "handbook.pdf", "status": "ingesting", "chunks_added": 0, "upload_id": "handbook.pdf", "ingestion_job_id": "active-job"},
        {"filename": "policy.md", "status": "ingesting", "chunks_added": 0, "upload_id": "policy.md", "ingestion_job_id": "active-job"},
    ]


def test_conditional_conflict_update_failure_becomes_api_not_found(monkeypatch: Any) -> None:
    class ConditionalCheckFailed(Exception):
        response = {"Error": {"Code": "ConditionalCheckFailedException", "Message": "The conditional request failed"}}

    class Client:
        def __init__(self) -> None:
            self.update_kwargs: dict[str, object] | None = None

        def update_item(self, **kwargs: object) -> dict[str, object]:
            self.update_kwargs = kwargs
            raise ConditionalCheckFailed()

    client = Client()
    monkeypatch.setenv("DDB_CONFLICTS_TABLE", "ConflictLog")
    store = DynamoDBConflictStore(client)
    monkeypatch.setattr(conflicts, "conflict_store", lambda: store)

    with TestClient(app) as test_client:
        response = test_client.patch("/api/conflicts/404", json=ConflictUpdate(status="Resolved").model_dump())

    assert response.status_code == 404
    assert response.json() == {"detail": "Conflict not found"}
    assert client.update_kwargs is not None
    assert client.update_kwargs["ConditionExpression"] == "attribute_exists(id)"

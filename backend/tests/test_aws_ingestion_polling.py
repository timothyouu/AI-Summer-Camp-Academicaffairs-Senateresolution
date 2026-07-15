from __future__ import annotations

import asyncio
import sys
from types import SimpleNamespace
from typing import Any

import pytest

from backend.app import uploads
from backend.app.stores import UploadRecord


@pytest.mark.parametrize("conflict", [False, True])
def test_pending_upload_poll_starts_own_job_or_retries(monkeypatch: Any, conflict: bool) -> None:
    class ConcurrentJobError(Exception):
        response = {"Error": {"Code": "ConflictException", "Message": "A concurrent ingestion job is already running"}}

    class Store:
        def __init__(self) -> None:
            self.record = UploadRecord("upload-123", "handbook.pdf", "pending", 0)
            self.calls: list[dict[str, object]] = []

        def get(self, upload_id: str) -> UploadRecord | None:
            return self.record if upload_id == self.record.upload_id else None

        def register(
            self, filename: str, status: str, chunks_added: int = 0, upload_id: str | None = None,
            ingestion_job_id: str | None = None, error: str | None = None,
        ) -> str:
            self.calls.append({
                "filename": filename, "status": status, "upload_id": upload_id,
                "ingestion_job_id": ingestion_job_id, "error": error,
            })
            return upload_id or filename

    class BedrockClient:
        def list_data_sources(self, **kwargs: object) -> dict[str, object]:
            assert kwargs == {"knowledgeBaseId": "kb-123", "maxResults": 10}
            return {"dataSourceSummaries": [{"dataSourceId": "source-123"}]}

        def start_ingestion_job(self, **kwargs: object) -> dict[str, object]:
            assert kwargs == {"knowledgeBaseId": "kb-123", "dataSourceId": "source-123"}
            if conflict:
                raise ConcurrentJobError()
            return {"ingestionJob": {"ingestionJobId": "job-new"}}

    store = Store()
    monkeypatch.setenv("AWS_REGION", "us-west-2")
    monkeypatch.setenv("BEDROCK_KB_ID", "kb-123")
    monkeypatch.setenv("DDB_UPLOADS_TABLE", "Uploads")
    monkeypatch.setattr(uploads, "upload_store", lambda: store)
    monkeypatch.setitem(sys.modules, "boto3", SimpleNamespace(client=lambda *_args, **_kwargs: BedrockClient()))

    response = asyncio.run(uploads.ingestion_status("upload-123"))

    if conflict:
        assert response.status == "pending"
        assert store.calls == []
    else:
        assert response.status == "ingesting"
        assert store.calls == [{
            "filename": "handbook.pdf", "status": "ingesting", "upload_id": "upload-123",
            "ingestion_job_id": "job-new", "error": None,
        }]


def test_pending_upload_poll_nonrecoverable_error_is_failed(monkeypatch: Any) -> None:
    class Store:
        record = UploadRecord("upload-123", "handbook.pdf", "pending", 0)

        def __init__(self) -> None:
            self.calls: list[dict[str, object]] = []

        def get(self, upload_id: str) -> UploadRecord | None:
            return self.record if upload_id == self.record.upload_id else None

        def register(self, filename: str, status: str, chunks_added: int = 0, upload_id: str | None = None,
                     ingestion_job_id: str | None = None, error: str | None = None) -> str:
            self.calls.append({"status": status, "error": error})
            return upload_id or filename

    class BedrockClient:
        def list_data_sources(self, **_kwargs: object) -> dict[str, object]:
            raise RuntimeError("data source unavailable")

    store = Store()
    monkeypatch.setenv("BEDROCK_KB_ID", "kb-123")
    monkeypatch.setenv("DDB_UPLOADS_TABLE", "Uploads")
    monkeypatch.setattr(uploads, "upload_store", lambda: store)
    monkeypatch.setitem(sys.modules, "boto3", SimpleNamespace(client=lambda *_args, **_kwargs: BedrockClient()))

    response = asyncio.run(uploads.ingestion_status("upload-123"))

    assert response.status == "failed"
    assert response.error == "data source unavailable"
    assert store.calls == [{"status": "failed", "error": "data source unavailable"}]


@pytest.mark.parametrize(
    ("bedrock_status", "failure_reasons", "expected_status", "expected_error"),
    [
        ("COMPLETE", [], "ready", None),
        ("FAILED", ["The source document could not be parsed."], "failed", "The source document could not be parsed."),
        ("STOPPED", [], "failed", "Bedrock ingestion job ended with status STOPPED"),
    ],
)
def test_aws_ingestion_polling_persists_terminal_status(
    monkeypatch: Any, bedrock_status: str, failure_reasons: list[str],
    expected_status: str, expected_error: str | None,
) -> None:
    class Store:
        def __init__(self) -> None:
            self.record = UploadRecord(
                upload_id="handbook.pdf", filename="handbook.pdf", status="ingesting", chunks_added=0,
                ingestion_job_id="job-123",
            )
            self.register_calls: list[dict[str, object]] = []

        def get(self, upload_id: str) -> UploadRecord | None:
            return self.record if upload_id == self.record.upload_id else None

        def register(
            self, filename: str, status: str, chunks_added: int = 0, upload_id: str | None = None,
            ingestion_job_id: str | None = None, error: str | None = None,
        ) -> str:
            self.register_calls.append({
                "filename": filename, "status": status, "chunks_added": chunks_added,
                "upload_id": upload_id, "ingestion_job_id": ingestion_job_id, "error": error,
            })
            return upload_id or filename

    class BedrockClient:
        def list_data_sources(self, **kwargs: object) -> dict[str, object]:
            assert kwargs == {"knowledgeBaseId": "kb-123", "maxResults": 10}
            return {"dataSourceSummaries": [{"dataSourceId": "source-123"}]}

        def get_ingestion_job(self, **kwargs: object) -> dict[str, object]:
            assert kwargs == {
                "knowledgeBaseId": "kb-123", "dataSourceId": "source-123", "ingestionJobId": "job-123",
            }
            return {"ingestionJob": {"status": bedrock_status, "failureReasons": failure_reasons}}

    store = Store()
    monkeypatch.setenv("AWS_REGION", "us-west-2")
    monkeypatch.setenv("BEDROCK_KB_ID", "kb-123")
    monkeypatch.setenv("DDB_UPLOADS_TABLE", "Uploads")
    monkeypatch.setattr(uploads, "upload_store", lambda: store)
    monkeypatch.setitem(sys.modules, "boto3", SimpleNamespace(client=lambda *_args, **_kwargs: BedrockClient()))

    response = asyncio.run(uploads.ingestion_status("handbook.pdf"))

    assert response.status == expected_status
    assert response.error == expected_error
    assert store.register_calls == [{
        "filename": "handbook.pdf", "status": expected_status, "chunks_added": 0,
        "upload_id": "handbook.pdf", "ingestion_job_id": "job-123", "error": expected_error,
    }]

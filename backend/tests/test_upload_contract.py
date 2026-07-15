from __future__ import annotations

import sys
from types import SimpleNamespace
from typing import Any

from fastapi.testclient import TestClient

from backend.app.stores import SQLiteUploadStore


def test_local_presign_direct_upload_and_status(client: TestClient, monkeypatch: Any) -> None:
    monkeypatch.delenv("CORPUS_BUCKET", raising=False)
    monkeypatch.delenv("DDB_UPLOADS_TABLE", raising=False)

    presign = client.post(
        "/api/uploads/presign",
        json={"filename": "Faculty Guidance.txt", "content_type": "text/plain"},
    )

    assert presign.status_code == 201
    assert presign.json() == {
        "upload_id": "Faculty-Guidance.txt",
        "upload_url": "http://testserver/api/upload?filename=Faculty-Guidance.txt",
        "headers": {},
    }
    pending = client.get("/api/uploads/Faculty-Guidance.txt")
    assert pending.status_code == 200
    assert pending.json() == {"upload_id": "Faculty-Guidance.txt", "status": "pending", "chunks_added": 0}

    direct_upload = client.put(
        "/api/upload?filename=Faculty-Guidance.txt",
        content=b"Faculty policy documents must be accessible.",
        headers={"Content-Type": "text/plain"},
    )
    assert direct_upload.status_code == 201
    assert direct_upload.json()["status"] == "ready"
    ready = client.get("/api/uploads/Faculty-Guidance.txt")
    assert ready.status_code == 200
    assert ready.json() == {"upload_id": "Faculty-Guidance.txt", "status": "ready", "chunks_added": 1}


def test_aws_presign_and_pending_status_use_lazy_boto3(client: TestClient, monkeypatch: Any) -> None:
    class S3Client:
        def __init__(self) -> None:
            self.calls: list[dict[str, object]] = []

        def generate_presigned_url(self, operation: str, **kwargs: object) -> str:
            self.calls.append({"operation": operation, **kwargs})
            return "https://uploads.example.test/presigned"

    s3 = S3Client()
    monkeypatch.setenv("CORPUS_BUCKET", "policy-corpus")
    monkeypatch.setenv("AWS_REGION", "us-west-2")
    monkeypatch.delenv("DDB_UPLOADS_TABLE", raising=False)
    monkeypatch.setitem(sys.modules, "boto3", SimpleNamespace(client=lambda service, **kwargs: s3))

    response = client.post(
        "/api/uploads/presign",
        json={"filename": "handbook.pdf", "content_type": "application/pdf"},
    )

    assert response.status_code == 201
    body = response.json()
    upload_id = body["upload_id"]
    assert body == {
        "upload_id": upload_id,
        "upload_url": "https://uploads.example.test/presigned",
        "headers": {"Content-Type": "application/pdf"},
    }
    assert s3.calls == [{
        "operation": "put_object",
        "Params": {"Bucket": "policy-corpus", "Key": f"uploads/{upload_id}/handbook.pdf", "ContentType": "application/pdf"},
        "ExpiresIn": 900,
    }]
    status = client.get(f"/api/uploads/{upload_id}")
    assert status.status_code == 200
    assert status.json() == {"upload_id": upload_id, "status": "pending", "chunks_added": 0}


def test_aws_presigns_same_filename_with_unique_ids_and_keys(client: TestClient, monkeypatch: Any) -> None:
    class S3Client:
        def __init__(self) -> None:
            self.keys: list[str] = []

        def generate_presigned_url(self, _operation: str, **kwargs: object) -> str:
            params = kwargs["Params"]
            assert isinstance(params, dict)
            self.keys.append(str(params["Key"]))
            return "https://uploads.example.test/presigned"

    s3 = S3Client()
    monkeypatch.setenv("CORPUS_BUCKET", "policy-corpus")
    monkeypatch.setenv("AWS_REGION", "us-west-2")
    monkeypatch.delenv("DDB_UPLOADS_TABLE", raising=False)
    monkeypatch.setitem(sys.modules, "boto3", SimpleNamespace(client=lambda *_args, **_kwargs: s3))

    first = client.post("/api/uploads/presign", json={"filename": "policy.pdf", "content_type": "application/pdf"}).json()
    second = client.post("/api/uploads/presign", json={"filename": "policy.pdf", "content_type": "application/pdf"}).json()

    assert first["upload_id"] != second["upload_id"]
    assert s3.keys == [
        f"uploads/{first['upload_id']}/policy.pdf",
        f"uploads/{second['upload_id']}/policy.pdf",
    ]
    store = SQLiteUploadStore()
    assert store.get(first["upload_id"]).filename == "policy.pdf"  # type: ignore[union-attr]
    assert store.get(second["upload_id"]).filename == "policy.pdf"  # type: ignore[union-attr]

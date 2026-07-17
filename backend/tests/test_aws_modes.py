from __future__ import annotations

import sys
from types import SimpleNamespace
from typing import Any

from backend.app.auth import role_from_claims
from backend.app.config import get_settings
from backend.app.models import ConflictCreate, ConflictUpdate
from backend.app.retrieval import search
from backend.app.stores import DynamoDBConflictStore, DynamoDBUploadStore


def test_mode_selection_is_per_integration(monkeypatch: Any) -> None:
    for name in ("AWS_REGION", "BEDROCK_KB_ID", "DDB_CONFLICTS_TABLE", "DDB_UPLOADS_TABLE", "CORPUS_BUCKET", "COGNITO_USER_POOL_ID", "COGNITO_CLIENT_ID"):
        monkeypatch.delenv(name, raising=False)
    assert not get_settings().retrieval_aws
    monkeypatch.setenv("BEDROCK_KB_ID", "KB1")
    assert get_settings().retrieval_aws
    assert not get_settings().conflicts_aws


def test_retrieval_maps_knowledge_base_response(monkeypatch: Any) -> None:
    class Client:
        def retrieve(self, **_: object) -> dict[str, object]:
            return {"retrievalResults": [{"content": {"text": "Policy passage"}, "score": 0.91, "location": {"s3Location": {"uri": "s3://bucket/handbook.pdf"}}, "metadata": {"section": "304.4.1", "doc_type": "handbook", "page": 42, "topic": "tenure & promotion"}}]}
    monkeypatch.setenv("AWS_REGION", "us-west-2")
    monkeypatch.setenv("BEDROCK_KB_ID", "KB1")
    monkeypatch.setitem(sys.modules, "boto3", SimpleNamespace(client=lambda *_args, **_kwargs: Client()))
    result = search("tenure", 3)[0]
    assert (result.text, result.source, result.section, result.page, result.score) == ("Policy passage", "handbook.pdf", "304.4.1", 42, 0.91)


class _RecordingKBClient:
    """Captures every retrieve() retrievalConfiguration for assertion."""

    def __init__(self) -> None:
        self.configs: list[dict[str, object]] = []

    def retrieve(self, **kwargs: object) -> dict[str, object]:
        self.configs.append(kwargs["retrievalConfiguration"])  # type: ignore[index]
        return {"retrievalResults": []}


class ValidationException(Exception):
    """Stand-in for botocore's ValidationException (matched by class name)."""


def test_bedrock_client_receives_bounded_timeout_config(monkeypatch: Any) -> None:
    # The KB client must be built with a bounded botocore Config so a stalled or
    # throttled socket fails fast instead of hanging the worker (default 60s x
    # retries ~= 5 min). Capture the config passed to boto3.client.
    captured: dict[str, object] = {}

    def fake_client(_service: str, **kwargs: object) -> _RecordingKBClient:
        captured.update(kwargs)
        return _RecordingKBClient()

    monkeypatch.setenv("AWS_REGION", "us-west-2")
    monkeypatch.setenv("BEDROCK_KB_ID", "KB1")
    monkeypatch.setenv("BEDROCK_READ_TIMEOUT", "25")
    monkeypatch.setitem(sys.modules, "boto3", SimpleNamespace(client=fake_client))
    search("tenure", 3)
    config = captured["config"]
    assert config.connect_timeout == 5.0  # type: ignore[attr-defined]
    assert config.read_timeout == 25.0  # type: ignore[attr-defined]
    assert config.retries == {"max_attempts": 2, "mode": "standard"}  # type: ignore[attr-defined]


def test_vector_mode_sends_vector_search_configuration(monkeypatch: Any) -> None:
    client = _RecordingKBClient()
    monkeypatch.setenv("AWS_REGION", "us-west-2")
    monkeypatch.setenv("BEDROCK_KB_ID", "KB1")
    monkeypatch.delenv("BEDROCK_KB_SEARCH_MODE", raising=False)  # default is vector
    monkeypatch.setitem(sys.modules, "boto3", SimpleNamespace(client=lambda *_a, **_k: client))
    search("tenure", 3)
    assert client.configs == [{"vectorSearchConfiguration": {"numberOfResults": 6}}]


def test_managed_mode_sends_managed_search_configuration(monkeypatch: Any) -> None:
    client = _RecordingKBClient()
    monkeypatch.setenv("AWS_REGION", "us-west-2")
    monkeypatch.setenv("BEDROCK_KB_ID", "KB1")
    monkeypatch.setenv("BEDROCK_KB_SEARCH_MODE", "managed")
    monkeypatch.setitem(sys.modules, "boto3", SimpleNamespace(client=lambda *_a, **_k: client))
    search("tenure", 3)
    assert client.configs == [{"managedSearchConfiguration": {"numberOfResults": 6}}]


def test_managed_kb_validation_triggers_one_managed_retry(monkeypatch: Any) -> None:
    class RetryingClient:
        def __init__(self) -> None:
            self.configs: list[dict[str, object]] = []

        def retrieve(self, **kwargs: object) -> dict[str, object]:
            config = kwargs["retrievalConfiguration"]  # type: ignore[index]
            self.configs.append(config)
            if "vectorSearchConfiguration" in config:
                raise ValidationException(
                    "Incompatible configuration: vectorSearchConfiguration is not supported "
                    "for managed knowledge bases. Use managedSearchConfiguration instead."
                )
            return {"retrievalResults": []}

    client = RetryingClient()
    monkeypatch.setenv("AWS_REGION", "us-west-2")
    monkeypatch.setenv("BEDROCK_KB_ID", "KB1")
    monkeypatch.delenv("BEDROCK_KB_SEARCH_MODE", raising=False)  # start in vector mode
    monkeypatch.setitem(sys.modules, "boto3", SimpleNamespace(client=lambda *_a, **_k: client))
    search("tenure", 3)
    assert client.configs == [
        {"vectorSearchConfiguration": {"numberOfResults": 6}},
        {"managedSearchConfiguration": {"numberOfResults": 6}},
    ]


def test_unrelated_validation_exception_is_reraised(monkeypatch: Any) -> None:
    class FailingClient:
        def __init__(self) -> None:
            self.calls = 0

        def retrieve(self, **_: object) -> dict[str, object]:
            self.calls += 1
            raise ValidationException("knowledgeBaseId 'KB1' failed to satisfy constraint.")

    client = FailingClient()
    monkeypatch.setenv("AWS_REGION", "us-west-2")
    monkeypatch.setenv("BEDROCK_KB_ID", "KB1")
    monkeypatch.delenv("BEDROCK_KB_SEARCH_MODE", raising=False)
    monkeypatch.setitem(sys.modules, "boto3", SimpleNamespace(client=lambda *_a, **_k: client))
    import pytest

    with pytest.raises(ValidationException):
        search("tenure", 3)
    assert client.calls == 1  # no retry for unrelated errors


def test_dynamodb_stores_use_low_level_items(monkeypatch: Any) -> None:
    class Client:
        def __init__(self) -> None:
            self.items: list[dict[str, object]] = []
        def put_item(self, **kwargs: object) -> dict[str, object]:
            self.items.append(kwargs)
            return {}
        def get_item(self, **_: object) -> dict[str, object]:
            return {}
        def scan(self, **_: object) -> dict[str, object]:
            return {"Items": [self.items[0]["Item"]]}
    client = Client()
    monkeypatch.setenv("AWS_REGION", "us-west-2")
    monkeypatch.setenv("DDB_CONFLICTS_TABLE", "ConflictLog")
    monkeypatch.setenv("DDB_UPLOADS_TABLE", "Uploads")
    conflicts = DynamoDBConflictStore(client)
    created = conflicts.create_or_get(ConflictCreate(source_a="A", source_b="B", topic="T", description="D"))
    assert conflicts.list()[0].id == created.id
    uploads = DynamoDBUploadStore(client)
    assert uploads.register("policy.pdf", "Pending")
    assert client.items[-1]["TableName"] == "Uploads"


def test_dynamodb_conflict_ids_use_string_partition_keys(monkeypatch: Any) -> None:
    class Client:
        def __init__(self) -> None:
            self.get_keys: list[dict[str, object]] = []
            self.put_items: list[dict[str, object]] = []
            self.update_keys: list[dict[str, object]] = []

        def get_item(self, **kwargs: object) -> dict[str, object]:
            self.get_keys.append(dict(kwargs["Key"]))  # type: ignore[index]
            return {}

        def put_item(self, **kwargs: object) -> dict[str, object]:
            self.put_items.append(dict(kwargs["Item"]))  # type: ignore[index]
            return {}

        def update_item(self, **kwargs: object) -> dict[str, object]:
            self.update_keys.append(dict(kwargs["Key"]))  # type: ignore[index]
            return {}

    monkeypatch.setenv("DDB_CONFLICTS_TABLE", "ConflictLog")
    store = DynamoDBConflictStore(Client())
    created = store.create_or_get(ConflictCreate(source_a="A", source_b="B", topic="T", description="D"))
    assert store.client.get_keys == [{"id": {"S": str(created.id)}}]  # type: ignore[attr-defined]
    assert store.client.put_items[0]["id"] == {"S": str(created.id)}  # type: ignore[attr-defined]
    store.update(created.id, ConflictUpdate(status="Resolved"))
    assert store.client.update_keys == [{"id": {"S": str(created.id)}}]  # type: ignore[attr-defined]


def test_dynamodb_conflict_list_paginates_scans(monkeypatch: Any) -> None:
    class Client:
        def __init__(self) -> None:
            self.items: list[dict[str, object]] = []
            self.scan_calls: list[dict[str, object]] = []

        def put_item(self, **kwargs: object) -> dict[str, object]:
            self.items.append(dict(kwargs["Item"]))  # type: ignore[index]
            return {}

        def get_item(self, **_: object) -> dict[str, object]:
            return {}

        def scan(self, **kwargs: object) -> dict[str, object]:
            self.scan_calls.append(kwargs)
            if "ExclusiveStartKey" not in kwargs:
                return {"Items": [self.items[0]], "LastEvaluatedKey": {"id": self.items[0]["id"]}}
            return {"Items": [self.items[1]]}

    monkeypatch.setenv("DDB_CONFLICTS_TABLE", "ConflictLog")
    store = DynamoDBConflictStore(Client())
    store.create_or_get(ConflictCreate(source_a="A", source_b="B", topic="T1", description="D1"))
    store.create_or_get(ConflictCreate(source_a="C", source_b="D", topic="T2", description="D2"))
    records = store.list()
    assert len(records) == 2
    assert len(store.client.scan_calls) == 2  # type: ignore[attr-defined]
    assert "ExclusiveStartKey" in store.client.scan_calls[1]  # type: ignore[attr-defined]


def test_cognito_group_role_mapping() -> None:
    assert role_from_claims({"cognito:groups": ["makers"]}) == "reviewer"
    assert role_from_claims({"cognito:groups": ["admins"]}) == "reviewer"
    assert role_from_claims({"cognito:groups": ["employees"]}) == "employee"


def test_dynamodb_conflict_create_race_returns_existing_record(monkeypatch: Any) -> None:
    class ConditionalCheckFailed(Exception):
        response = {"Error": {"Code": "ConditionalCheckFailedException", "Message": "conditional failed"}}

    class Client:
        def __init__(self) -> None:
            self.gets = 0
            self.stored: dict[str, object] | None = None

        def get_item(self, **kwargs: object) -> dict[str, object]:
            self.gets += 1
            if self.gets == 1:
                return {}
            assert self.stored is not None
            return {"Item": self.stored}

        def put_item(self, **kwargs: object) -> dict[str, object]:
            from backend.app.stores import _ddb_encode, _now
            self.stored = _ddb_encode({
                "id": "123", "source_a": "A", "source_b": "B", "topic": "T", "description": "D",
                "status": "Open", "resolution_note": "", "created_at": _now().isoformat(), "updated_at": _now().isoformat(),
            })
            raise ConditionalCheckFailed()

    monkeypatch.setenv("DDB_CONFLICTS_TABLE", "ConflictLog")
    store = DynamoDBConflictStore(Client())
    record = store.create_or_get(ConflictCreate(source_a="A", source_b="B", topic="T", description="D"))
    assert record.id == 123
    assert store.client.gets == 2  # type: ignore[attr-defined]

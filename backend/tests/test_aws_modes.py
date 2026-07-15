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
    assert role_from_claims({"cognito:groups": ["employees"]}) == "employee"

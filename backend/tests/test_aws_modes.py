from __future__ import annotations

import sys
from types import SimpleNamespace
from typing import Any

from backend.app.auth import role_from_claims
from backend.app.config import get_settings
from backend.app.models import ConflictCreate
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


def test_cognito_group_role_mapping() -> None:
    assert role_from_claims({"cognito:groups": ["makers"]}) == "reviewer"
    assert role_from_claims({"cognito:groups": ["employees"]}) == "employee"

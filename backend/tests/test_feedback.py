from __future__ import annotations

from copy import deepcopy
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from backend.app.models import FeedbackCreate
from backend.app.stores import (
    DynamoDBFeedbackStore,
    SQLiteFeedbackStore,
    feedback_store,
)


class FakeFeedbackTable:
    def __init__(self) -> None:
        self.items: dict[str, dict[str, object]] = {}

    def put_item(self, *, Item: dict[str, object]) -> dict[str, object]:
        self.items[str(Item["feedback_id"])] = deepcopy(Item)
        return {}

    def scan(self, **kwargs: object) -> dict[str, object]:
        items = list(self.items.values())
        values = kwargs.get("ExpressionAttributeValues", {})
        assert isinstance(values, dict)
        if ":rating" in values:
            items = [item for item in items if item["rating"] == values[":rating"]]
        if ":issue_type" in values:
            items = [item for item in items if item["issue_type"] == values[":issue_type"]]
        return {"Items": deepcopy(items)}


class FakeFeedbackResource:
    def __init__(self, table: FakeFeedbackTable) -> None:
        self.table = table
        self.table_names: list[str] = []

    def Table(self, table_name: str) -> FakeFeedbackTable:
        self.table_names.append(table_name)
        return self.table


def test_feedback_store_selects_sqlite_without_aws(monkeypatch: pytest.MonkeyPatch) -> None:
    def unexpected_resource(*_: object, **__: object) -> object:
        raise AssertionError("SQLite selection must not create a DynamoDB resource")

    monkeypatch.delenv("DDB_FEEDBACK_TABLE", raising=False)
    monkeypatch.delenv("DYNAMODB_FEEDBACK_TABLE", raising=False)
    monkeypatch.setattr("backend.app.stores.get_dynamodb_resource", unexpected_resource)

    assert isinstance(feedback_store(), SQLiteFeedbackStore)


def test_feedback_store_selects_dynamodb_lazily(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DDB_FEEDBACK_TABLE", "feedback-test")

    assert isinstance(feedback_store(), DynamoDBFeedbackStore)


def test_dynamodb_feedback_store_creates_and_lists_with_stubbed_table() -> None:
    table = FakeFeedbackTable()
    resource = FakeFeedbackResource(table)
    store = DynamoDBFeedbackStore(resource=resource, table_name="feedback-test")
    payload = FeedbackCreate(
        answer_id="answer-123",
        question="What is the workload rule?",
        rating="not_helpful",
        comment="Please cite the CBA article.",
        issue_type="missing_citation",
        role="employee",
        citations_used=["Unit 3 CBA • Article 20"],
        provider="local-index",
    )

    created = store.create_feedback(payload)
    listed = store.list_feedback(rating="not_helpful", issue_type="missing_citation")

    assert str(UUID(created.feedback_id)) == created.feedback_id
    assert created.answer_id == "answer-123"
    assert listed == [created]
    assert table.items[created.feedback_id]["provider"] == "local-index"
    assert resource.table_names and set(resource.table_names) == {"feedback-test"}


def test_feedback_api_persists_in_sqlite_and_chat_returns_answer_id(client: TestClient) -> None:
    chat = client.post("/api/chat", json={"question": "Does service credit count toward the tenure clock?"})
    assert chat.status_code == 200
    answer_id = chat.json()["answer_id"]
    assert str(UUID(answer_id)) == answer_id

    response = client.post(
        "/api/feedback",
        json={
            "answer_id": answer_id,
            "question": "Does service credit count toward the tenure clock?",
            "rating": "helpful",
            "role": "employee",
            "citations_used": ["CSUB University Handbook 2025 • Section 304.4.1"],
            "provider": "calibrated-static",
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert str(UUID(payload["feedback_id"])) == payload["feedback_id"]
    assert payload["answer_id"] == answer_id
    assert payload["rating"] == "helpful"
    assert payload["created_at"]

    listing = client.get("/api/feedback?rating=helpful&limit=10")
    assert listing.status_code == 200
    assert any(item["feedback_id"] == payload["feedback_id"] for item in listing.json())


def test_feedback_api_rejects_invalid_rating(client: TestClient) -> None:
    response = client.post(
        "/api/feedback",
        json={
            "answer_id": "answer-123",
            "question": "Is this answer useful?",
            "rating": "maybe",
        },
    )

    assert response.status_code == 422

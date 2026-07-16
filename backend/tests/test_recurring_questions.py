from __future__ import annotations

from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

from backend.app.stores import (
    DynamoDBRecurringQuestionStore,
    SQLiteRecurringQuestionStore,
    normalize_recurring_question,
    recurring_question_id,
    recurring_question_store,
)


class FakeRecurringQuestionTable:
    def __init__(self) -> None:
        self.items: dict[str, dict[str, object]] = {}

    def update_item(
        self,
        *,
        Key: dict[str, str],
        ExpressionAttributeValues: dict[str, object],
        **_: object,
    ) -> dict[str, object]:
        question_id = Key["question_id"]
        previous = self.items.get(question_id)
        item = dict(previous or {})
        item.update(
            {
                "question_id": question_id,
                "question_text": ExpressionAttributeValues[":question_text"],
                "normalized_text": ExpressionAttributeValues[":normalized_text"],
                "topic": ExpressionAttributeValues[":topic"],
                "last_asked_at": ExpressionAttributeValues[":now"],
                "sample_answer_id": ExpressionAttributeValues[":answer_id"],
                "sample_citations": ExpressionAttributeValues[":citations"],
                "scope": item.get("scope", ExpressionAttributeValues[":scope"]),
                "visibility": item.get("visibility", ExpressionAttributeValues[":visibility"]),
                "first_asked_at": item.get("first_asked_at", ExpressionAttributeValues[":now"]),
                "created_at": item.get("created_at", ExpressionAttributeValues[":now"]),
                "updated_at": ExpressionAttributeValues[":now"],
                "ask_count": int(item.get("ask_count", 0)) + int(ExpressionAttributeValues[":one"]),
            }
        )
        self.items[question_id] = item
        return {"Attributes": deepcopy(item)}

    def scan(self, **kwargs: object) -> dict[str, object]:
        items = [item for item in self.items.values() if item["visibility"] == "published"]
        values = kwargs.get("ExpressionAttributeValues", {})
        assert isinstance(values, dict)
        if ":topic" in values:
            items = [item for item in items if item["topic"] == values[":topic"]]
        return {"Items": deepcopy(items)}


class FakeRecurringQuestionResource:
    def __init__(self, table: FakeRecurringQuestionTable) -> None:
        self.table = table
        self.table_names: list[str] = []

    def Table(self, table_name: str) -> FakeRecurringQuestionTable:
        self.table_names.append(table_name)
        return self.table


def test_normalization_groups_case_and_punctuation_variations() -> None:
    first = normalize_recurring_question("What is the GECCo Committee?!")
    second = normalize_recurring_question("  what is the gecco committee  ")

    assert first == "what is the gecco committee"
    assert second == first
    assert recurring_question_id(first) == recurring_question_id(second)


def test_recurring_question_store_selects_sqlite_without_aws(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unexpected_resource(*_: object, **__: object) -> object:
        raise AssertionError("SQLite selection must not create a DynamoDB resource")

    monkeypatch.delenv("DDB_RECURRING_QUESTIONS_TABLE", raising=False)
    monkeypatch.delenv("DYNAMODB_RECURRING_QUESTIONS_TABLE", raising=False)
    monkeypatch.setattr("backend.app.stores.get_dynamodb_resource", unexpected_resource)

    assert isinstance(recurring_question_store(), SQLiteRecurringQuestionStore)


def test_dynamodb_recurring_question_store_records_and_aggregates_with_stubbed_table() -> None:
    table = FakeRecurringQuestionTable()
    resource = FakeRecurringQuestionResource(table)
    store = DynamoDBRecurringQuestionStore(resource=resource, table_name="recurring-questions-test")

    first = store.record_question(
        "What is the RTP process?",
        answer_id="answer-1",
        citations=["Handbook — Section 305"],
    )
    second = store.record_question(
        "what is the rtp process?!",
        answer_id="answer-2",
        citations=["Handbook — Section 305"],
    )

    assert first.question_id == second.question_id
    assert second.ask_count == 2
    assert store.list_questions() == [second]
    assert resource.table_names and set(resource.table_names) == {"recurring-questions-test"}


def test_chat_records_recurring_questions_and_listing_aggregates(client: TestClient) -> None:
    first = client.post("/api/chat", json={"question": "What is the GECCo Committee?!"})
    second = client.post("/api/chat", json={"question": " what is the gecco committee "})
    assert first.status_code == 200
    assert second.status_code == 200

    response = client.get("/api/recurring-questions?limit=50")
    assert response.status_code == 200
    records = response.json()
    record = next(item for item in records if item["normalized_text"] == "what is the gecco committee")
    assert record["ask_count"] == 2
    assert record["sample_answer_id"] == second.json()["answer_id"]
    assert record["sample_citations"]


def test_chat_survives_recurring_question_storage_failure(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    class BrokenStore:
        def record_question(self, **_: object) -> object:
            raise RuntimeError("DynamoDB is unavailable")

    monkeypatch.setattr("backend.app.chat.recurring_question_store", lambda: BrokenStore())

    response = client.post("/api/chat", json={"question": "Does service credit count toward the tenure clock?"})

    assert response.status_code == 200
    assert response.json()["answer"]

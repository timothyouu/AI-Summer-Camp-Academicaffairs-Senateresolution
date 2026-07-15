from __future__ import annotations

from copy import deepcopy
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from backend.app.config import PersistenceSettings, load_persistence_settings
from backend.app.models import ConflictCreate, ConflictUpdate
from backend.app.stores import (
    DynamoDBConflictStore,
    SQLiteConflictStore,
    get_conflict_store,
)


class FakeDynamoTable:
    def __init__(self) -> None:
        self.items: dict[str, dict[str, object]] = {}
        self.put_calls = 0

    def get_item(self, *, Key: dict[str, str]) -> dict[str, object]:
        item = self.items.get(Key["conflict_id"])
        return {} if item is None else {"Item": deepcopy(item)}

    def put_item(self, *, Item: dict[str, object]) -> dict[str, object]:
        self.put_calls += 1
        self.items[str(Item["conflict_id"])] = deepcopy(Item)
        return {}

    def scan(self, **kwargs: object) -> dict[str, object]:
        items = list(self.items.values())
        values = kwargs.get("ExpressionAttributeValues", {})
        assert isinstance(values, dict)
        if ":status" in values:
            items = [item for item in items if item["status"] == values[":status"]]
        if ":topic" in values:
            items = [item for item in items if item["topic"] == values[":topic"]]
        return {"Items": deepcopy(items)}

    def update_item(
        self,
        *,
        Key: dict[str, str],
        ExpressionAttributeValues: dict[str, str],
        **_: object,
    ) -> dict[str, object]:
        item = self.items[Key["conflict_id"]]
        if ":status" in ExpressionAttributeValues:
            item["status"] = ExpressionAttributeValues[":status"]
        if ":resolution_note" in ExpressionAttributeValues:
            item["resolution_note"] = ExpressionAttributeValues[":resolution_note"]
        item["updated_at"] = ExpressionAttributeValues[":updated_at"]
        return {"Attributes": deepcopy(item)}


class FakeDynamoResource:
    def __init__(self, table: FakeDynamoTable) -> None:
        self.table = table
        self.table_names: list[str] = []

    def Table(self, table_name: str) -> FakeDynamoTable:
        self.table_names.append(table_name)
        return self.table


def dynamodb_settings() -> PersistenceSettings:
    return load_persistence_settings(
        {
            "APP_PERSISTENCE_BACKEND": "dynamodb",
            "DYNAMODB_CONFLICTS_TABLE": "conflicts-test",
        }
    )


def test_conflict_store_factory_selects_sqlite_without_aws(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unexpected_resource(*_: object, **__: object) -> object:
        raise AssertionError("SQLite selection must not create a DynamoDB resource")

    monkeypatch.setattr("backend.app.stores.get_dynamodb_resource", unexpected_resource)

    store = get_conflict_store(load_persistence_settings({}))

    assert isinstance(store, SQLiteConflictStore)


def test_conflict_store_factory_selects_dynamodb_lazily() -> None:
    store = get_conflict_store(dynamodb_settings())

    assert isinstance(store, DynamoDBConflictStore)


def test_dynamodb_conflict_store_create_list_get_and_update() -> None:
    table = FakeDynamoTable()
    resource = FakeDynamoResource(table)
    store = DynamoDBConflictStore(dynamodb_settings(), resource=resource)
    payload = ConflictCreate(
        source_a="Handbook section 1",
        source_b="CBA article 2",
        topic="Workload",
        description="The two sources use different limits.",
    )

    created = store.create_conflict(payload, origin="chat")
    duplicate = store.create_conflict(payload, origin="chat")

    assert isinstance(created.id, str)
    assert str(UUID(created.id)) == created.id
    assert duplicate.id == created.id
    assert table.put_calls == 1
    assert table.items[created.id]["origin"] == "chat"

    listed = store.list_conflicts(status="Open", topic="Workload")
    assert [record.id for record in listed] == [created.id]
    assert store.get_conflict(created.id) == created
    assert store.get_conflict("missing") is None

    updated = store.update_conflict(
        created.id,
        ConflictUpdate(status="Resolved", resolution_note="Resolved by committee."),
    )
    assert updated is not None
    assert updated.status == "Resolved"
    assert updated.resolution_note == "Resolved by committee."
    assert store.update_conflict("missing", ConflictUpdate(status="Open")) is None
    assert resource.table_names and set(resource.table_names) == {"conflicts-test"}


def test_sqlite_conflict_routes_support_get_and_string_compatible_ids(client: TestClient) -> None:
    created = client.post(
        "/api/conflicts",
        json={
            "source_a": "Test source A",
            "source_b": "Test source B",
            "topic": "Store API test",
            "description": "Verify the SQLite route remains available.",
        },
    )
    assert created.status_code == 201
    conflict_id = created.json()["id"]

    fetched = client.get(f"/api/conflicts/{conflict_id}")
    updated = client.patch(
        f"/api/conflicts/{conflict_id}",
        json={"status": "Resolved", "resolution_note": "Checked in test."},
    )

    assert fetched.status_code == 200
    assert fetched.json()["id"] == conflict_id
    assert updated.status_code == 200
    assert updated.json()["status"] == "Resolved"
    assert client.get("/api/conflicts/not-an-integer").status_code == 404

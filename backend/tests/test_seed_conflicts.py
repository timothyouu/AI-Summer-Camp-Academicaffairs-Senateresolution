from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from backend.app import conflicts
from backend.app.models import ConflictCreate, ConflictRecord
from backend.scripts import seed_conflicts


class IdempotentConflictStore:
    def __init__(self) -> None:
        self.records: dict[tuple[str, str, str, str], ConflictRecord] = {}

    def create_or_get(self, payload: ConflictCreate) -> ConflictRecord:
        identity = (payload.source_a, payload.source_b, payload.topic, payload.description)
        if identity not in self.records:
            now = datetime.now(timezone.utc)
            self.records[identity] = ConflictRecord(
                id=len(self.records) + 1,
                created_at=now,
                updated_at=now,
                **payload.model_dump(),
            )
        return self.records[identity]


def test_explicit_aws_seed_is_idempotent(monkeypatch: Any) -> None:
    monkeypatch.setenv("DDB_CONFLICTS_TABLE", "ConflictLog")
    store = IdempotentConflictStore()
    monkeypatch.setattr(conflicts, "conflict_store", lambda: store)

    assert conflicts.seed_demo_conflicts() == []
    first = conflicts.seed_demo_conflicts(allow_aws=True)
    second = conflicts.seed_demo_conflicts(allow_aws=True)

    assert len(first) == len(second) == len(conflicts.DEMO_CONFLICTS)
    assert [record.id for record in first] == [record.id for record in second]
    assert len(store.records) == len(conflicts.DEMO_CONFLICTS)


def test_seed_command_explicitly_allows_aws(monkeypatch: Any, capsys: Any) -> None:
    calls: list[bool] = []
    monkeypatch.setattr(seed_conflicts, "initialize_database", lambda: None)
    monkeypatch.setattr(
        seed_conflicts,
        "seed_demo_conflicts",
        lambda *, allow_aws: calls.append(allow_aws) or [object(), object(), object()],
    )

    seed_conflicts.main()

    assert calls == [True]
    assert capsys.readouterr().out == "Conflict log contains 3 seeded demo records.\n"

# PRD Round-2 Features Implementation Plan (implementation3.md)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the newly added PRD items — source archive/activate lifecycle, source-access permission panel, conflict-visibility gating, AI-assisted drafting loop, catalog scraping with edition weighting, resource catalog page, dark mode, back buttons, and emblem-home navigation — on branch `prod`, keeping full local parity with env-var AWS flips.

**Architecture:** Every new datastore follows the existing `stores.py` dual-mode pattern (SQLite locally, DynamoDB when its `DDB_*_TABLE` env var is set). Archive/activate and edition weighting are enforced as a post-retrieval registry filter inside `retrieval.search()`, so the flip is instant in both NumPy-index and Bedrock-KB modes. Role/permission enforcement activates only when an identity exists (an `X-User-Email` / `X-Role` header locally, verified Cognito claims in AWS mode) so all frozen tests keep passing unchanged. The drafting loop wraps the existing 6-agent pipeline; the catalog scraper is stdlib-only (urllib + html.parser) and feeds the existing chunk/embed pipeline.

**Tech Stack:** FastAPI + Pydantic v2 + SQLite/NumPy (local), boto3/DynamoDB/S3/Bedrock KB (lazy, env-gated), React 18 + TypeScript strict + Tailwind 3.4, react-router-dom.

## Locked decisions (Tim, 2026-07-15, session Q&A)

- Reviewer role doubles as Admin for the demo; no third role. Cognito stays OFF for the demo (hardcoded demo accounts); Bedrock models, Bedrock KB + S3 + ingestion, and DynamoDB + API Gateway/Lambda are the live AWS pieces.
- Permissions attach **per source type** (`handbook`, `cba`, `policystat`, `catalog`, `uploads`) with `can_add` / `can_edit` per user.
- Catalog scrape: current catalog + exactly one archived edition, policy-relevant pages only, `is_current` + `edition_year` metadata; archived edition down-ranked (score × 0.5), never excluded.
- Full local parity: everything works with zero AWS; each integration flips via env vars (existing pattern).
- Employee conflict escalation is **non-clickable guidance text** (no mailto).
- Drafting UI **extends the Resolution Checker page** (`ReviewResults.tsx`), no new page.
- Archive lifecycle: corpus seeds start `active`; anything arriving via the upload flow starts `archived`.
- Dark mode: toggle lives in a **settings popover** on the sidebar gear; default light; persisted in localStorage.
- Resource catalog is a new shared route `/catalog` linked from the Topics page and the Sources page — the sidebar icon rail stays at the locked seven items.

## Global Constraints

- **No new dependencies.** Backend new code uses stdlib only (`urllib.request`, `html.parser`, `sqlite3`, `uuid`, `json`). boto3/strands/mangum imports must stay lazy/guarded (LOOP.md decision 4). Frontend adds zero npm packages.
- **Frozen verifier files:** `backend/tests/conftest.py`, `backend/tests/test_api.py`, `backend/tests/test_ingest_retrieval.py` must not be modified and must keep passing. New test files are allowed.
- **Verifier (run after every task):**
  1. `/home/tim/AI-Summer-Camp-Academicaffairs-Senateresolution/backend/.venv/bin/python -m pytest backend/tests -q`
  2. `cd frontend && npx tsc --noEmit && npm run build`
- **TypeScript strict**, no implicit any; Python type hints on all function signatures.
- Sidebar item order is locked: New chat, Search chats, Drafts, Reviews, Conflicts, Topics, Sources (employee sees the first two + Topics). Do not add or reorder items.
- Backend behavior with no identity headers and no AWS env vars must be byte-for-byte identical to today (this is what keeps frozen tests green).
- Demo honesty: catalog pages are scraped from the real public site; everything else synthetic stays disclosed.

## File Structure (new / modified)

| File | Responsibility |
|---|---|
| `backend/app/database.py` (modify) | Add `registry`, `permissions`, `drafts` tables to `SCHEMA` |
| `backend/app/models.py` (modify) | `SourceType`, `SourceRecord`, `PermissionRecord`, `DraftVersion`, request/response models, `x_role` support |
| `backend/app/config.py` (modify) | `ddb_registry_table`, `ddb_permissions_table`, `ddb_drafts_table` settings + properties |
| `backend/app/registry.py` (create) | Registry store (SQLite/DDB) + `/api/sources` router + corpus seeding |
| `backend/app/permissions.py` (create) | Permission store (SQLite/DDB) + `/api/permissions` router + `require_can_add_sources` dependency + identity helper |
| `backend/app/retrieval.py` (modify) | Registry-aware post-filter: drop archived, down-rank non-current |
| `backend/app/chat.py` (modify) | Role-shaped conflict responses (employee softening) |
| `backend/app/drafting.py` (create) | Draft store + `/api/draft/revise` + `/api/draft/{id}/versions` |
| `backend/app/catalog.py` (create) | HTML→Markdown converter, policy-link crawler, catalog ingestion |
| `backend/scripts/scrape_catalog.py` (create) | CLI entry for local scraping |
| `backend/lambda_handlers/catalog_scraper.py` (create) | Lambda entry writing scraped .md to S3 |
| `backend/app/main.py` (modify) | Include new routers; seed registry + permissions in lifespan |
| `backend/app/uploads.py` (modify) | Register uploads as `archived` in registry; permission enforcement |
| `frontend/src/api.ts` (modify) | Identity/role headers; registry, permissions, drafting endpoints |
| `frontend/src/state/theme.tsx` (create) | ThemeProvider (dark mode, persisted) |
| `frontend/src/components/SettingsMenu.tsx` (create) | Sidebar gear popover with dark-mode toggle |
| `frontend/src/components/BackButton.tsx` (create) | Shared back navigation |
| `frontend/src/components/DraftAssistant.tsx` (create) | Revise-with-AI panel used by ReviewResults |
| `frontend/src/components/SourcePermissions.tsx` (create) | Permission panel section on Sources page |
| `frontend/src/pages/Catalog.tsx` (create) | Resource catalog page (shared route) |
| `frontend/src/pages/Sources.tsx` (modify) | Archive tab, archive/unarchive actions, permissions section |
| `frontend/src/pages/ReviewResults.tsx` (modify) | Mount DraftAssistant |
| `frontend/src/components/Sidebar.tsx` (modify) | Emblem→/login, gear opens SettingsMenu |
| `frontend/tailwind.config.js` + `frontend/src/index.css` (modify) | CSS-variable palette with `.dark` overrides |
| `frontend/src/App.tsx` (modify) | `/catalog` route, ThemeProvider |
| `infra/stacks/policy_intelligence_stack.py` (modify) | 3 new DDB tables, scraper Lambda, env wiring |
| `AWS_SETUP.md`, `CLAUDE.md` (modify) | New env vars + docs |

---

### Task 1: Source registry store + archive/activate lifecycle (backend)

**Files:**
- Modify: `backend/app/database.py` (SCHEMA), `backend/app/config.py`, `backend/app/models.py`, `backend/app/main.py`, `backend/app/uploads.py`
- Create: `backend/app/registry.py`
- Test: `backend/tests/test_registry_lifecycle.py`

**Interfaces:**
- Consumes: `connection()` from database.py, `get_settings()` from config.py, `_ddb_encode`/`_ddb_decode`/`_ddb_error_code` from stores.py.
- Produces: `registry_store() -> RegistryStore` with `list() -> list[SourceRecord]`, `get(source_id: str) -> SourceRecord | None`, `upsert(record: SourceUpsert) -> SourceRecord`, `set_status(source_id: str, status: SourceStatus) -> SourceRecord | None`; `seed_registry_from_corpus() -> None`; routes `GET /api/sources`, `POST /api/sources/{source_id}/status`. Tasks 2, 5, 6, 7 depend on these names.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_registry_lifecycle.py
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from app.registry import registry_store, seed_registry_from_corpus
from app.models import SourceUpsert


def test_upsert_and_status_flip() -> None:
    store = registry_store()
    record = store.upsert(SourceUpsert(
        id="unit-3-cba", title="Unit 3 Collective Bargaining Agreement",
        source_type="cba", status="active", canonical_url="https://example.edu/cba",
    ))
    assert record.status == "active"
    flipped = store.set_status("unit-3-cba", "archived")
    assert flipped is not None and flipped.status == "archived"
    assert store.get("unit-3-cba").status == "archived"  # type: ignore[union-attr]


def test_set_status_unknown_source_returns_none() -> None:
    assert registry_store().set_status("nope", "active") is None


def test_sources_endpoint_lists_and_flips() -> None:
    with TestClient(app) as client:
        registry_store().upsert(SourceUpsert(
            id="handbook-2025", title="CSUB University Handbook 2025",
            source_type="handbook", status="active",
        ))
        listed = client.get("/api/sources")
        assert listed.status_code == 200
        assert any(item["id"] == "handbook-2025" for item in listed.json())
        flip = client.post("/api/sources/handbook-2025/status", json={"status": "archived"})
        assert flip.status_code == 200 and flip.json()["status"] == "archived"
        assert client.post("/api/sources/missing/status", json={"status": "active"}).status_code == 404


def test_seed_marks_uploads_archived(tmp_path, monkeypatch) -> None:
    # conftest already isolates POLICY_DATA_ROOT; create one corpus seed and one upload.
    from app.config import CORPUS_DIR, UPLOAD_DIR, ensure_data_directories
    ensure_data_directories()
    (CORPUS_DIR / "synthetic-demo.md").write_text("---\ntitle: Demo Seed\nsource_type: policystat\n---\nBody.", encoding="utf-8")
    (UPLOAD_DIR / "late-upload.md").write_text("---\ntitle: Late Upload\n---\nBody.", encoding="utf-8")
    seed_registry_from_corpus()
    records = {record.id: record for record in registry_store().list()}
    assert records["synthetic-demo"].status == "active"
    assert records["late-upload"].status == "archived"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `/home/tim/AI-Summer-Camp-Academicaffairs-Senateresolution/backend/.venv/bin/python -m pytest backend/tests/test_registry_lifecycle.py -q`
Expected: FAIL / ERROR with `ModuleNotFoundError: No module named 'app.registry'`.

- [ ] **Step 3: Add schema, settings, and models**

Append to `SCHEMA` in `backend/app/database.py` (inside the same triple-quoted string, after the `uploads` table):

```sql
CREATE TABLE IF NOT EXISTS registry (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    source_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'archived',
    canonical_url TEXT NOT NULL DEFAULT '',
    edition_year INTEGER,
    is_current INTEGER NOT NULL DEFAULT 1,
    s3_key TEXT NOT NULL DEFAULT '',
    passages INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

In `backend/app/config.py`, add to `Settings`: `ddb_registry_table: str | None = None` plus property `registry_aws` returning `bool(self.ddb_registry_table)`; add `ddb_registry_table=value("DDB_REGISTRY_TABLE")` in `get_settings()`. (Also add `ddb_permissions_table` / `ddb_drafts_table` fields, properties `permissions_aws` / `drafts_aws`, and their env reads now — Tasks 3 and 5 use them.)

In `backend/app/models.py`, add:

```python
SourceType = Literal["handbook", "cba", "policystat", "catalog", "uploads"]
SourceLifecycleStatus = Literal["active", "archived"]


class SourceUpsert(BaseModel):
    id: str = Field(min_length=1, max_length=200)
    title: str
    source_type: SourceType
    status: SourceLifecycleStatus = "archived"
    canonical_url: str = ""
    edition_year: int | None = None
    is_current: bool = True
    s3_key: str = ""
    passages: int = 0


class SourceRecord(SourceUpsert):
    updated_at: datetime


class SourceStatusUpdate(BaseModel):
    status: SourceLifecycleStatus
```

- [ ] **Step 4: Implement `backend/app/registry.py`**

```python
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from fastapi import APIRouter, Depends, HTTPException, status

from .auth import require_reviewer
from .config import CORPUS_DIR, UPLOAD_DIR, get_settings
from .database import connection
from .ingest import _parse_front_matter, discover_corpus_files
from .models import SourceLifecycleStatus, SourceRecord, SourceStatusUpdate, SourceUpsert
from .stores import _ddb_decode, _ddb_encode

router = APIRouter(prefix="/api/sources", tags=["source registry"])


def _record(values: dict[str, object]) -> SourceRecord:
    updated = values.get("updated_at")
    return SourceRecord(
        id=str(values["id"]), title=str(values["title"]), source_type=str(values["source_type"]),  # type: ignore[arg-type]
        status=str(values["status"]), canonical_url=str(values.get("canonical_url", "")),  # type: ignore[arg-type]
        edition_year=int(values["edition_year"]) if values.get("edition_year") not in (None, "") else None,
        is_current=bool(int(values.get("is_current", 1))), s3_key=str(values.get("s3_key", "")),
        passages=int(values.get("passages", 0)),
        updated_at=updated if isinstance(updated, datetime) else datetime.fromisoformat(str(updated)),
    )


class RegistryStore(Protocol):
    def list(self) -> list[SourceRecord]: ...
    def get(self, source_id: str) -> SourceRecord | None: ...
    def upsert(self, record: SourceUpsert) -> SourceRecord: ...
    def set_status(self, source_id: str, status: SourceLifecycleStatus) -> SourceRecord | None: ...


class SQLiteRegistryStore:
    def list(self) -> list[SourceRecord]:
        with connection() as database:
            rows = database.execute("SELECT * FROM registry ORDER BY title").fetchall()
        return [_record(dict(row)) for row in rows]

    def get(self, source_id: str) -> SourceRecord | None:
        with connection() as database:
            row = database.execute("SELECT * FROM registry WHERE id=?", (source_id,)).fetchone()
        return _record(dict(row)) if row is not None else None

    def upsert(self, record: SourceUpsert) -> SourceRecord:
        with connection() as database:
            database.execute(
                "INSERT INTO registry(id,title,source_type,status,canonical_url,edition_year,is_current,s3_key,passages) "
                "VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET title=excluded.title,"
                "source_type=excluded.source_type,status=excluded.status,canonical_url=excluded.canonical_url,"
                "edition_year=excluded.edition_year,is_current=excluded.is_current,s3_key=excluded.s3_key,"
                "passages=excluded.passages,updated_at=CURRENT_TIMESTAMP",
                (record.id, record.title, record.source_type, record.status, record.canonical_url,
                 record.edition_year, int(record.is_current), record.s3_key, record.passages),
            )
        stored = self.get(record.id)
        if stored is None:
            raise RuntimeError("Registry upsert did not persist")
        return stored

    def set_status(self, source_id: str, status: SourceLifecycleStatus) -> SourceRecord | None:
        if self.get(source_id) is None:
            return None
        with connection() as database:
            database.execute("UPDATE registry SET status=?, updated_at=CURRENT_TIMESTAMP WHERE id=?", (status, source_id))
        return self.get(source_id)


class DynamoDBRegistryStore:
    def __init__(self, client: object | None = None) -> None:
        settings = get_settings()
        if not settings.ddb_registry_table:
            raise ValueError("DDB_REGISTRY_TABLE is required")
        if client is None:
            import boto3  # type: ignore[import-not-found]
            client = boto3.client("dynamodb", region_name=settings.aws_region)
        self.client = client
        self.table = settings.ddb_registry_table

    def list(self) -> list[SourceRecord]:
        records: list[SourceRecord] = []
        start_key: dict[str, object] | None = None
        while True:
            kwargs: dict[str, object] = {"TableName": self.table}
            if start_key is not None:
                kwargs["ExclusiveStartKey"] = start_key
            response = self.client.scan(**kwargs)  # type: ignore[attr-defined]
            records.extend(_record(_ddb_decode(item)) for item in response.get("Items", []))
            start_key = response.get("LastEvaluatedKey")
            if not start_key:
                break
        return sorted(records, key=lambda value: value.title)

    def get(self, source_id: str) -> SourceRecord | None:
        item = self.client.get_item(TableName=self.table, Key={"id": {"S": source_id}}).get("Item")  # type: ignore[attr-defined]
        return _record(_ddb_decode(item)) if item else None

    def upsert(self, record: SourceUpsert) -> SourceRecord:
        now = datetime.now(timezone.utc).isoformat()
        values: dict[str, object] = {**record.model_dump(), "is_current": int(record.is_current),
                                     "edition_year": record.edition_year or "", "updated_at": now}
        self.client.put_item(TableName=self.table, Item=_ddb_encode(values))  # type: ignore[attr-defined]
        return _record({**values, "edition_year": record.edition_year})

    def set_status(self, source_id: str, status: SourceLifecycleStatus) -> SourceRecord | None:
        existing = self.get(source_id)
        if existing is None:
            return None
        return self.upsert(SourceUpsert(**{**existing.model_dump(exclude={"updated_at"}), "status": status}))


def registry_store() -> RegistryStore:
    return DynamoDBRegistryStore() if get_settings().registry_aws else SQLiteRegistryStore()


def _seed_id(path: Path) -> str:
    return path.stem.lower()


def register_document(path: Path, *, status: SourceLifecycleStatus, source_type: str | None = None,
                      canonical_url: str = "", edition_year: int | None = None, is_current: bool = True,
                      passages: int = 0) -> SourceRecord:
    """Create the registry entry for one corpus document, preserving an existing status."""
    text = path.read_text(encoding="utf-8", errors="replace") if path.suffix.lower() in {".md", ".txt"} else ""
    metadata, _ = _parse_front_matter(text)
    store = registry_store()
    existing = store.get(_seed_id(path))
    resolved_type = source_type or metadata.get("source_type", "uploads")
    if resolved_type not in {"handbook", "cba", "policystat", "catalog", "uploads"}:
        resolved_type = "uploads"
    return store.upsert(SourceUpsert(
        id=_seed_id(path), title=metadata.get("title", path.stem),
        source_type=resolved_type,  # type: ignore[arg-type]
        status=existing.status if existing is not None else status,
        canonical_url=canonical_url or metadata.get("canonical_url", ""),
        edition_year=edition_year, is_current=is_current,
        passages=passages or (existing.passages if existing is not None else 0),
    ))


def seed_registry_from_corpus() -> None:
    """Seeds start active; anything under uploads/ starts archived (locked decision)."""
    for path in discover_corpus_files(CORPUS_DIR):
        in_uploads = UPLOAD_DIR in path.parents or path.parent == UPLOAD_DIR
        register_document(path, status="archived" if in_uploads else "active")


@router.get("", response_model=list[SourceRecord])
def list_sources() -> list[SourceRecord]:
    return registry_store().list()


@router.post("/{source_id}/status", response_model=SourceRecord)
def update_source_status(source_id: str, payload: SourceStatusUpdate, _: None = Depends(require_reviewer)) -> SourceRecord:
    record = registry_store().set_status(source_id, payload.status)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source not found")
    return record
```

- [ ] **Step 5: Wire into main.py and uploads.py**

In `backend/app/main.py`: import `from . import registry`; add `registry.router` to the `include_router` loop; inside `lifespan` after `reload_index()`, add:

```python
from .registry import seed_registry_from_corpus
seed_registry_from_corpus()
```

In `backend/app/uploads.py` `_save_local_upload()`, after `upload_store().register(...)`, add:

```python
from .registry import register_document
register_document(destination, status="archived", source_type="uploads", passages=chunks_added)
```

and in the S3 presign paths (`upload` POST and `presign_upload`), after `upload_store().register(filename, "pending", upload_id=upload_id)`, register the future source as archived so the AWS path matches:

```python
from .registry import registry_store
from .models import SourceUpsert
registry_store().upsert(SourceUpsert(
    id=Path(filename).stem.lower(), title=Path(filename).stem, source_type="uploads",
    status="archived", s3_key=f"uploads/{upload_id}/{filename}",
))
```

- [ ] **Step 6: Run the new tests, then the full verifier**

Run: `/home/tim/AI-Summer-Camp-Academicaffairs-Senateresolution/backend/.venv/bin/python -m pytest backend/tests/test_registry_lifecycle.py -q` → PASS
Run: `/home/tim/AI-Summer-Camp-Academicaffairs-Senateresolution/backend/.venv/bin/python -m pytest backend/tests -q` → all pass (57+ tests).

- [ ] **Step 7: Commit**

```bash
git add backend/app/registry.py backend/app/database.py backend/app/config.py backend/app/models.py backend/app/main.py backend/app/uploads.py backend/tests/test_registry_lifecycle.py
git commit -m "feat: source registry with archive/activate lifecycle (SQLite + DynamoDB)"
```

---

### Task 2: Registry-aware retrieval (archive filter + edition down-ranking)

**Files:**
- Modify: `backend/app/retrieval.py`
- Test: `backend/tests/test_retrieval_registry.py`

**Interfaces:**
- Consumes: `registry_store()` and `SourceRecord` from Task 1.
- Produces: unchanged `search(query: str, k: int = 8) -> list[SearchResult]` signature — callers (chat, resolution, pipeline, topics) need no changes. Sources with no registry entry are kept untouched (this preserves frozen tests).

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_retrieval_registry.py
from __future__ import annotations

from app.models import SourceUpsert
from app.registry import registry_store
from app.retrieval import SearchResult, apply_registry_policy


def _result(source: str, score: float) -> SearchResult:
    return SearchResult(text="t", source=source, section="s", doc_type="md", page=None, topic="workload", score=score)


def test_archived_sources_are_filtered_out() -> None:
    registry_store().upsert(SourceUpsert(id="old-doc", title="Old Doc", source_type="policystat", status="archived"))
    kept = apply_registry_policy([_result("Old Doc", 0.9), _result("Unregistered", 0.5)], k=8)
    assert [item.source for item in kept] == ["Unregistered"]


def test_non_current_edition_is_down_ranked_not_dropped() -> None:
    registry_store().upsert(SourceUpsert(id="catalog-2024", title="CSUB Catalog 2024", source_type="catalog",
                                         status="active", is_current=False, edition_year=2024))
    registry_store().upsert(SourceUpsert(id="catalog-2026", title="CSUB Catalog 2026", source_type="catalog",
                                         status="active", is_current=True, edition_year=2026))
    kept = apply_registry_policy([_result("CSUB Catalog 2024", 0.8), _result("CSUB Catalog 2026", 0.6)], k=8)
    assert [item.source for item in kept] == ["CSUB Catalog 2026", "CSUB Catalog 2024"]
    assert kept[1].score == 0.4  # 0.8 * 0.5


def test_k_is_applied_after_filtering() -> None:
    kept = apply_registry_policy([_result(f"Doc {index}", 1.0 - index / 10) for index in range(6)], k=2)
    assert len(kept) == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.../python -m pytest backend/tests/test_retrieval_registry.py -q`
Expected: FAIL with `ImportError: cannot import name 'apply_registry_policy'`.

- [ ] **Step 3: Implement in `backend/app/retrieval.py`**

Add `from dataclasses import dataclass, replace` at the top (extend the existing dataclass import) and:

```python
ARCHIVED_EDITION_WEIGHT = 0.5


def apply_registry_policy(results: list[SearchResult], k: int) -> list[SearchResult]:
    """Drop archived sources and down-rank non-current editions using the registry.

    Sources without a registry entry pass through untouched so local test
    corpora and pre-registry indexes keep working byte-for-byte.
    """
    from .registry import registry_store  # Local import: avoids a module cycle with registry seeding.
    try:
        records = {record.title: record for record in registry_store().list()}
    except Exception:
        return results[:k]
    kept: list[SearchResult] = []
    for item in results:
        record = records.get(item.source)
        if record is not None and record.status == "archived":
            continue
        if record is not None and not record.is_current:
            item = replace(item, score=item.score * ARCHIVED_EDITION_WEIGHT)
        kept.append(item)
    return sorted(kept, key=lambda value: value.score, reverse=True)[:k]
```

Change the existing `search()` body to over-fetch then filter:

```python
def search(query: str, k: int = 8) -> list[SearchResult]:
    settings = get_settings()
    fetched = _search_knowledge_base(query, k * 2) if settings.retrieval_aws else INDEX.search(query, k * 2)
    return apply_registry_policy(fetched, k)
```

- [ ] **Step 4: Run new tests + full verifier** — both green (frozen `test_ingest_retrieval.py` passes because its sources have no registry rows).

- [ ] **Step 5: Commit**

```bash
git add backend/app/retrieval.py backend/tests/test_retrieval_registry.py
git commit -m "feat: registry-aware retrieval - archive filter and edition down-ranking"
```

---

### Task 3: Permission store, panel API, and upload enforcement

**Files:**
- Modify: `backend/app/database.py`, `backend/app/models.py`, `backend/app/main.py`, `backend/app/uploads.py`
- Create: `backend/app/permissions.py`
- Test: `backend/tests/test_permissions.py`

**Interfaces:**
- Consumes: `connection()`, `get_settings()` (`permissions_aws` property from Task 1 Step 3), `_ddb_encode`/`_ddb_decode`, `role_from_claims`/`decode_and_verify_token` from auth.py.
- Produces: `permission_store() -> PermissionStore` with `list() -> list[PermissionRecord]`, `get(user_email: str, source_type: SourceType) -> PermissionRecord | None`, `grant(update: PermissionUpdate, granted_by: str) -> PermissionRecord`; `identity_email(authorization: str | None, x_user_email: str | None) -> str | None`; FastAPI dependency `require_can_add_sources`; routes `GET/PUT /api/permissions`. Seed constant `ADMIN_EMAIL = "reviewer@campus.edu"` and `seed_default_permissions()`.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_permissions.py
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from app.models import PermissionUpdate
from app.permissions import ADMIN_EMAIL, permission_store, seed_default_permissions


def test_seed_grants_admin_everything() -> None:
    seed_default_permissions()
    for source_type in ("handbook", "cba", "policystat", "catalog", "uploads"):
        record = permission_store().get(ADMIN_EMAIL, source_type)  # type: ignore[arg-type]
        assert record is not None and record.can_add and record.can_edit


def test_grant_and_list_roundtrip() -> None:
    record = permission_store().grant(
        PermissionUpdate(user_email="colleague@campus.edu", source_type="uploads", can_add=True, can_edit=False),
        granted_by=ADMIN_EMAIL,
    )
    assert record.can_add and not record.can_edit and record.granted_by == ADMIN_EMAIL
    assert any(item.user_email == "colleague@campus.edu" for item in permission_store().list())


def test_permissions_endpoints() -> None:
    with TestClient(app) as client:
        saved = client.put("/api/permissions", json={
            "user_email": "colleague@campus.edu", "source_type": "cba", "can_add": True, "can_edit": True,
        }, headers={"X-User-Email": ADMIN_EMAIL})
        assert saved.status_code == 200
        listed = client.get("/api/permissions")
        assert listed.status_code == 200 and isinstance(listed.json(), list)


def test_upload_denied_without_can_add_identity() -> None:
    with TestClient(app) as client:
        seed_default_permissions()
        response = client.post(
            "/api/upload", files={"file": ("note.md", b"---\ntitle: Note\n---\nBody", "text/markdown")},
            headers={"X-User-Email": "stranger@campus.edu"},
        )
        assert response.status_code == 403


def test_upload_allowed_without_identity_header() -> None:
    # Backwards compatibility: no identity -> no enforcement (frozen tests rely on this).
    with TestClient(app) as client:
        response = client.post("/api/upload", files={"file": ("free.md", b"---\ntitle: Free\n---\nBody", "text/markdown")})
        assert response.status_code == 201
```

- [ ] **Step 2: Run tests to verify they fail** — `ModuleNotFoundError: No module named 'app.permissions'`.

- [ ] **Step 3: Schema + models**

Append to `SCHEMA` in database.py:

```sql
CREATE TABLE IF NOT EXISTS permissions (
    user_email TEXT NOT NULL,
    source_type TEXT NOT NULL,
    can_add INTEGER NOT NULL DEFAULT 0,
    can_edit INTEGER NOT NULL DEFAULT 0,
    granted_by TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_email, source_type)
);
```

Add to models.py:

```python
class PermissionUpdate(BaseModel):
    user_email: str = Field(min_length=3, max_length=254)
    source_type: SourceType
    can_add: bool
    can_edit: bool


class PermissionRecord(PermissionUpdate):
    granted_by: str = ""
    updated_at: datetime
```

- [ ] **Step 4: Implement `backend/app/permissions.py`**

```python
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Protocol
from urllib.error import URLError

from fastapi import APIRouter, Depends, Header, HTTPException, status

from .auth import decode_and_verify_token
from .config import get_settings
from .database import connection
from .models import PermissionRecord, PermissionUpdate, SourceType
from .stores import _ddb_decode, _ddb_encode

router = APIRouter(prefix="/api/permissions", tags=["permissions"])
ADMIN_EMAIL = "reviewer@campus.edu"
SOURCE_TYPES: tuple[SourceType, ...] = ("handbook", "cba", "policystat", "catalog", "uploads")


def _record(values: dict[str, object]) -> PermissionRecord:
    updated = values.get("updated_at")
    return PermissionRecord(
        user_email=str(values["user_email"]), source_type=str(values["source_type"]),  # type: ignore[arg-type]
        can_add=bool(int(values.get("can_add", 0))), can_edit=bool(int(values.get("can_edit", 0))),
        granted_by=str(values.get("granted_by", "")),
        updated_at=updated if isinstance(updated, datetime) else datetime.fromisoformat(str(updated)),
    )


class PermissionStore(Protocol):
    def list(self) -> list[PermissionRecord]: ...
    def get(self, user_email: str, source_type: SourceType) -> PermissionRecord | None: ...
    def grant(self, update: PermissionUpdate, granted_by: str) -> PermissionRecord: ...


class SQLitePermissionStore:
    def list(self) -> list[PermissionRecord]:
        with connection() as database:
            rows = database.execute("SELECT * FROM permissions ORDER BY user_email, source_type").fetchall()
        return [_record(dict(row)) for row in rows]

    def get(self, user_email: str, source_type: SourceType) -> PermissionRecord | None:
        with connection() as database:
            row = database.execute("SELECT * FROM permissions WHERE user_email=? AND source_type=?",
                                   (user_email.lower(), source_type)).fetchone()
        return _record(dict(row)) if row is not None else None

    def grant(self, update: PermissionUpdate, granted_by: str) -> PermissionRecord:
        with connection() as database:
            database.execute(
                "INSERT INTO permissions(user_email,source_type,can_add,can_edit,granted_by) VALUES (?,?,?,?,?) "
                "ON CONFLICT(user_email,source_type) DO UPDATE SET can_add=excluded.can_add,"
                "can_edit=excluded.can_edit,granted_by=excluded.granted_by,updated_at=CURRENT_TIMESTAMP",
                (update.user_email.lower(), update.source_type, int(update.can_add), int(update.can_edit), granted_by),
            )
        stored = self.get(update.user_email, update.source_type)
        if stored is None:
            raise RuntimeError("Permission grant did not persist")
        return stored


class DynamoDBPermissionStore:
    def __init__(self, client: object | None = None) -> None:
        settings = get_settings()
        if not settings.ddb_permissions_table:
            raise ValueError("DDB_PERMISSIONS_TABLE is required")
        if client is None:
            import boto3  # type: ignore[import-not-found]
            client = boto3.client("dynamodb", region_name=settings.aws_region)
        self.client = client
        self.table = settings.ddb_permissions_table

    def list(self) -> list[PermissionRecord]:
        records: list[PermissionRecord] = []
        start_key: dict[str, object] | None = None
        while True:
            kwargs: dict[str, object] = {"TableName": self.table}
            if start_key is not None:
                kwargs["ExclusiveStartKey"] = start_key
            response = self.client.scan(**kwargs)  # type: ignore[attr-defined]
            records.extend(_record(_ddb_decode(item)) for item in response.get("Items", []))
            start_key = response.get("LastEvaluatedKey")
            if not start_key:
                break
        return sorted(records, key=lambda value: (value.user_email, value.source_type))

    def get(self, user_email: str, source_type: SourceType) -> PermissionRecord | None:
        item = self.client.get_item(TableName=self.table, Key={  # type: ignore[attr-defined]
            "user_email": {"S": user_email.lower()}, "source_type": {"S": source_type},
        }).get("Item")
        return _record(_ddb_decode(item)) if item else None

    def grant(self, update: PermissionUpdate, granted_by: str) -> PermissionRecord:
        now = datetime.now(timezone.utc).isoformat()
        values: dict[str, object] = {
            "user_email": update.user_email.lower(), "source_type": update.source_type,
            "can_add": int(update.can_add), "can_edit": int(update.can_edit),
            "granted_by": granted_by, "updated_at": now,
        }
        self.client.put_item(TableName=self.table, Item=_ddb_encode(values))  # type: ignore[attr-defined]
        return _record(values)


def permission_store() -> PermissionStore:
    return DynamoDBPermissionStore() if get_settings().permissions_aws else SQLitePermissionStore()


def seed_default_permissions() -> None:
    """The demo reviewer doubles as Admin (locked decision): full access to every source type."""
    store = permission_store()
    for source_type in SOURCE_TYPES:
        if store.get(ADMIN_EMAIL, source_type) is None:
            store.grant(PermissionUpdate(user_email=ADMIN_EMAIL, source_type=source_type, can_add=True, can_edit=True),
                        granted_by="system-seed")


def identity_email(authorization: str | None, x_user_email: str | None) -> str | None:
    """Cognito claims win when configured; otherwise the local demo identity header."""
    settings = get_settings()
    if settings.cognito_aws and authorization and authorization.startswith("Bearer "):
        try:
            claims = decode_and_verify_token(authorization.removeprefix("Bearer ").strip(), settings)
            email = claims.get("email") or claims.get("username")
            return str(email).lower() if email else None
        except (ValueError, URLError, KeyError, json.JSONDecodeError):
            return None
    return x_user_email.lower().strip() if x_user_email else None


def require_can_add_sources(
    authorization: str | None = Header(default=None),
    x_user_email: str | None = Header(default=None),
) -> None:
    """Deny uploads for identified users without a can_add grant on 'uploads'.

    Requests with no identity at all pass through unchanged — local enforcement
    is opt-in via the X-User-Email header, mirroring how require_reviewer is a
    no-op outside Cognito mode.
    """
    email = identity_email(authorization, x_user_email)
    if email is None:
        return
    record = permission_store().get(email, "uploads")
    if record is None or not record.can_add:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No permission to add sources")


@router.get("", response_model=list[PermissionRecord])
def list_permissions(_: None = Depends(__import__("app.auth", fromlist=["require_reviewer"]).require_reviewer)) -> list[PermissionRecord]:
    return permission_store().list()


@router.put("", response_model=PermissionRecord)
def save_permission(
    payload: PermissionUpdate,
    authorization: str | None = Header(default=None),
    x_user_email: str | None = Header(default=None),
    _: None = Depends(__import__("app.auth", fromlist=["require_reviewer"]).require_reviewer),
) -> PermissionRecord:
    return permission_store().grant(payload, granted_by=identity_email(authorization, x_user_email) or "unknown")
```

(Use a plain `from .auth import require_reviewer` import at the top instead of the `__import__` shown inline — written out here only to keep the dependency explicit; the implementer should write `from .auth import require_reviewer` and use it directly.)

- [ ] **Step 5: Wire up**

In `backend/app/main.py`: add `permissions` to the router loop and call `seed_default_permissions()` in `lifespan` next to `seed_registry_from_corpus()` (skip when `settings.permissions_aws` is set, matching the conflicts seeding pattern: `if not settings.permissions_aws: seed_default_permissions()`).

In `backend/app/uploads.py`: add `require_can_add_sources` as a second dependency to `upload`, `direct_upload`, and `presign_upload`:

```python
from .permissions import require_can_add_sources
# e.g.
async def upload(file: UploadFile = File(...), _: None = Depends(require_reviewer),
                 __: None = Depends(require_can_add_sources)) -> UploadResponse:
```

- [ ] **Step 6: Run new tests + full verifier** — green.

- [ ] **Step 7: Commit**

```bash
git add backend/app/permissions.py backend/app/database.py backend/app/models.py backend/app/main.py backend/app/uploads.py backend/tests/test_permissions.py
git commit -m "feat: source-access permission store, panel API, and upload enforcement"
```

---

### Task 4: Conflict-visibility gating (role-shaped chat responses)

**Files:**
- Modify: `backend/app/chat.py`
- Test: `backend/tests/test_chat_gating.py`

**Interfaces:**
- Consumes: `ChatResponse`, `ConflictSignal`, `Role` from models.py; `role_from_claims`/`decode_and_verify_token` from auth.py; `ESCALATION` from agents/pipeline.py.
- Produces: `resolve_request_role(authorization: str | None, x_role: str | None) -> Role` and `shape_response_for_role(response: ChatResponse, role: Role) -> ChatResponse`, both importable by tests. The `/api/chat` endpoint gains optional `X-Role` header handling; default (no header, no Cognito) is `reviewer`, preserving current behavior for frozen tests.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_chat_gating.py
from __future__ import annotations

from fastapi.testclient import TestClient

from app.chat import EMPLOYEE_CONFLICT_GUIDANCE, resolve_request_role, shape_response_for_role
from app.main import app
from app.models import ChatResponse, Citation, ConflictSignal


def _conflicted_response() -> ChatResponse:
    return ChatResponse(
        answer="Full answer.\n\nMultiple answers — consult your dean or the Provost's office.",
        citations=[Citation(id=1, source="Handbook", section="G", excerpt="…")],
        conflict=ConflictSignal(detected=True, sources=["Handbook", "RES 252644"], guidance="Full reviewer guidance.", conflict_id=7),
    )


def test_default_role_is_reviewer_locally() -> None:
    assert resolve_request_role(None, None) == "reviewer"
    assert resolve_request_role(None, "employee") == "employee"
    assert resolve_request_role(None, "not-a-role") == "reviewer"


def test_reviewer_response_is_untouched() -> None:
    response = _conflicted_response()
    assert shape_response_for_role(response, "reviewer") is response


def test_employee_conflict_is_softened() -> None:
    shaped = shape_response_for_role(_conflicted_response(), "employee")
    assert shaped.conflict is not None and shaped.conflict.detected
    assert shaped.conflict.sources == []
    assert shaped.conflict.conflict_id is None
    assert shaped.conflict.guidance == EMPLOYEE_CONFLICT_GUIDANCE
    assert "Multiple answers — consult" not in shaped.answer
    assert shaped.citations  # citations stay: cited answers are a Must Have for both roles


def test_chat_endpoint_softens_for_employee_header() -> None:
    with TestClient(app) as client:
        response = client.post("/api/chat", json={"question": "What are the WPAF binder rules?"},
                               headers={"X-Role": "employee"})
        assert response.status_code == 200
        body = response.json()
        if body.get("conflict") is not None and body["conflict"]["detected"]:
            assert body["conflict"]["sources"] == []
            assert "contact" in body["conflict"]["guidance"].lower()
```

- [ ] **Step 2: Run tests to verify they fail** — `ImportError: cannot import name 'EMPLOYEE_CONFLICT_GUIDANCE'`.

- [ ] **Step 3: Implement in `backend/app/chat.py`**

Add near the top (after the imports; also import `Header` from fastapi, `Role` from `.models`, and `ESCALATION` from `.agents.pipeline`):

```python
EMPLOYEE_CONFLICT_GUIDANCE = (
    "More than one official source addresses this topic and they do not fully agree. "
    "For guidance that applies to your situation, contact your dean or the Provost's office."
)


def resolve_request_role(authorization: str | None, x_role: str | None) -> Role:
    """Cognito claims are authoritative when configured; otherwise trust the demo header.

    The local default is 'reviewer' so existing header-less calls (tests, curl,
    the pre-gating frontend) keep today's full-detail behavior.
    """
    settings = get_settings()
    if settings.cognito_aws and authorization and authorization.startswith("Bearer "):
        try:
            return role_from_claims(decode_and_verify_token(authorization.removeprefix("Bearer ").strip(), settings))
        except (ValueError, URLError, KeyError, json.JSONDecodeError):
            return "employee"
    return "employee" if x_role == "employee" else "reviewer"


def shape_response_for_role(response: ChatResponse, role: Role) -> ChatResponse:
    """Employees get an escalation-oriented message instead of raw conflict detail."""
    if role != "employee" or response.conflict is None or not response.conflict.detected:
        return response
    answer = response.answer.replace(f"\n\n{ESCALATION}", "").replace(f"\n\n{response.conflict.guidance}", "")
    trace = [
        step.model_copy(update={"detail": EMPLOYEE_CONFLICT_GUIDANCE}) if step.agent == "escalation" and step.status == "warning" else step
        for step in response.agent_trace
    ]
    return response.model_copy(update={
        "answer": answer,
        "conflict": ConflictSignal(detected=True, sources=[], guidance=EMPLOYEE_CONFLICT_GUIDANCE, conflict_id=None),
        "agent_trace": trace,
    })
```

Change the endpoint signature and wrap every return through the shaper:

```python
@router.post("/chat", response_model=ChatResponse)
def chat(
    payload: ChatRequest,
    authorization: str | None = Header(default=None),
    x_role: str | None = Header(default=None),
    _: None = Depends(require_authenticated),
) -> ChatResponse:
    role = resolve_request_role(authorization, x_role)
    pipeline = create_pipeline()
    if pipeline.authoritative:
        return shape_response_for_role(_agent_grounded_answer(pipeline.run(payload.question)), role)
    fixture = _calibrated(payload.question)
    if fixture is None:
        return shape_response_for_role(_local_index_answer(search(payload.question, k=6)), role)
    # ... existing calibrated branch unchanged, but final line becomes:
    return shape_response_for_role(ChatResponse(answer=fixture.answer, citations=_citations(fixture.citations), conflict=signal, mode="calibrated-static", agent_trace=pipeline_result.agent_trace), role)
```

Required new imports in chat.py: `import json`, `from urllib.error import URLError`, `from fastapi import APIRouter, Depends, Header`, `from .auth import require_authenticated, role_from_claims, decode_and_verify_token`, `from .config import get_settings`, `from .models import ... Role`, `from .agents.pipeline import ESCALATION`.

- [ ] **Step 4: Run new tests + full verifier** — green (frozen tests send no `X-Role`, default `reviewer` keeps responses identical).

- [ ] **Step 5: Commit**

```bash
git add backend/app/chat.py backend/tests/test_chat_gating.py
git commit -m "feat: role-gated conflict visibility - employees get escalation-oriented guidance"
```

---

### Task 5: AI-assisted drafting loop (backend)

**Files:**
- Modify: `backend/app/database.py`, `backend/app/models.py`, `backend/app/main.py`
- Create: `backend/app/drafting.py`
- Test: `backend/tests/test_drafting.py`

**Interfaces:**
- Consumes: `create_pipeline()` + `resolution_output()` from agents, `generate()` from llm.py (via the same `ModuleLLM` seam the pipeline uses), `require_reviewer`, `_ddb_encode`/`_ddb_decode`, settings `drafts_aws`/`corpus_aws`.
- Produces: `draft_store() -> DraftStore` with `add_version(draft_id: str, text: str, suggestion: str) -> DraftVersion` and `list_versions(draft_id: str) -> list[DraftVersion]`; routes `POST /api/draft/revise` → `DraftReviseResponse`, `GET /api/draft/{draft_id}/versions` → `list[DraftVersion]`. Task 8 (frontend) consumes both.

- [ ] **Step 1: Models + schema**

Append to `SCHEMA` in database.py:

```sql
CREATE TABLE IF NOT EXISTS drafts (
    draft_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    text TEXT NOT NULL,
    suggestion TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (draft_id, version)
);
```

Add to models.py:

```python
class DraftReviseRequest(BaseModel):
    text: str = Field(min_length=1, max_length=50_000)
    draft_id: str | None = None


class DraftVersion(BaseModel):
    draft_id: str
    version: int
    text: str
    suggestion: str = ""
    created_at: datetime


class DraftReviseResponse(BaseModel):
    draft_id: str
    version: int
    revised_text: str
    rationale: str
    overlaps: list[ResolutionFinding] = Field(default_factory=list)
    duplicates: list[ResolutionFinding] = Field(default_factory=list)
    conflicts: list[ResolutionFinding] = Field(default_factory=list)
    recommendation: str
    agent_trace: list[AgentTraceStep] = Field(default_factory=list)
```

- [ ] **Step 2: Write the failing tests**

```python
# backend/tests/test_drafting.py
from __future__ import annotations

from fastapi.testclient import TestClient

from app.drafting import draft_store, deterministic_revision
from app.main import app
from app.models import ResolutionFinding


def test_version_numbers_increment_per_draft() -> None:
    store = draft_store()
    first = store.add_version("draft-a", "v1 text", "sugg")
    second = store.add_version("draft-a", "v2 text", "sugg2")
    other = store.add_version("draft-b", "other", "")
    assert (first.version, second.version, other.version) == (1, 2, 1)
    assert [item.version for item in store.list_versions("draft-a")] == [1, 2]


def test_deterministic_revision_cites_findings() -> None:
    revised, rationale = deterministic_revision(
        "Faculty must keep a three-inch binder.",
        conflicts=[ResolutionFinding(source="RES 252644", section="WPAF", description="Electronic evidence replaces binders.")],
        recommendation="Replace the physical binder limit.",
    )
    assert "RES 252644" in rationale
    assert revised  # a non-empty revision is always produced


def test_revise_endpoint_persists_versions() -> None:
    with TestClient(app) as client:
        first = client.post("/api/draft/revise", json={"text": "Faculty must keep a three-inch binder for WPAF evidence."})
        assert first.status_code == 200
        body = first.json()
        assert body["version"] == 1 and body["revised_text"] and body["draft_id"]
        second = client.post("/api/draft/revise", json={"text": body["revised_text"], "draft_id": body["draft_id"]})
        assert second.status_code == 200 and second.json()["version"] == 2
        versions = client.get(f"/api/draft/{body['draft_id']}/versions")
        assert versions.status_code == 200 and len(versions.json()) == 2
```

- [ ] **Step 3: Run tests to verify they fail** — `ModuleNotFoundError: No module named 'app.drafting'`.

- [ ] **Step 4: Implement `backend/app/drafting.py`**

```python
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Protocol
from uuid import uuid4

from fastapi import APIRouter, Depends

from .agents import create_pipeline, resolution_output
from .auth import require_reviewer
from .config import get_settings
from .database import connection
from .models import DraftReviseRequest, DraftReviseResponse, DraftVersion, ResolutionFinding
from .stores import _ddb_decode, _ddb_encode

router = APIRouter(prefix="/api/draft", tags=["drafting"])


def _version(values: dict[str, object]) -> DraftVersion:
    created = values.get("created_at")
    return DraftVersion(
        draft_id=str(values["draft_id"]), version=int(values["version"]),  # type: ignore[arg-type]
        text=str(values["text"]), suggestion=str(values.get("suggestion", "")),
        created_at=created if isinstance(created, datetime) else datetime.fromisoformat(str(created)),
    )


class DraftStore(Protocol):
    def add_version(self, draft_id: str, text: str, suggestion: str) -> DraftVersion: ...
    def list_versions(self, draft_id: str) -> list[DraftVersion]: ...


class SQLiteDraftStore:
    def add_version(self, draft_id: str, text: str, suggestion: str) -> DraftVersion:
        with connection() as database:
            row = database.execute("SELECT COALESCE(MAX(version), 0) AS current FROM drafts WHERE draft_id=?",
                                   (draft_id,)).fetchone()
            next_version = int(row["current"]) + 1
            database.execute("INSERT INTO drafts(draft_id,version,text,suggestion) VALUES (?,?,?,?)",
                             (draft_id, next_version, text, suggestion))
            stored = database.execute("SELECT * FROM drafts WHERE draft_id=? AND version=?",
                                      (draft_id, next_version)).fetchone()
        return _version(dict(stored))

    def list_versions(self, draft_id: str) -> list[DraftVersion]:
        with connection() as database:
            rows = database.execute("SELECT * FROM drafts WHERE draft_id=? ORDER BY version", (draft_id,)).fetchall()
        return [_version(dict(row)) for row in rows]


class DynamoDBDraftStore:
    def __init__(self, client: object | None = None) -> None:
        settings = get_settings()
        if not settings.ddb_drafts_table:
            raise ValueError("DDB_DRAFTS_TABLE is required")
        if client is None:
            import boto3  # type: ignore[import-not-found]
            client = boto3.client("dynamodb", region_name=settings.aws_region)
        self.client = client
        self.table = settings.ddb_drafts_table

    def add_version(self, draft_id: str, text: str, suggestion: str) -> DraftVersion:
        existing = self.list_versions(draft_id)
        next_version = (existing[-1].version + 1) if existing else 1
        now = datetime.now(timezone.utc).isoformat()
        values: dict[str, object] = {"draft_id": draft_id, "version": next_version, "text": text,
                                     "suggestion": suggestion, "created_at": now}
        self.client.put_item(TableName=self.table, Item=_ddb_encode(values),  # type: ignore[attr-defined]
                             ConditionExpression="attribute_not_exists(draft_id) AND attribute_not_exists(version)")
        settings = get_settings()
        if settings.corpus_aws:  # PRD: draft text also lands in S3 for durable, resumable history.
            import boto3  # type: ignore[import-not-found]
            boto3.client("s3", region_name=settings.aws_region).put_object(
                Bucket=settings.corpus_bucket, Key=f"drafts/{draft_id}/v{next_version}.md",
                Body=text.encode("utf-8"), ContentType="text/markdown",
            )
        return _version(values)

    def list_versions(self, draft_id: str) -> list[DraftVersion]:
        response = self.client.query(  # type: ignore[attr-defined]
            TableName=self.table, KeyConditionExpression="draft_id = :draft",
            ExpressionAttributeValues={":draft": {"S": draft_id}},
        )
        return sorted((_version(_ddb_decode(item)) for item in response.get("Items", [])), key=lambda value: value.version)


def draft_store() -> DraftStore:
    return DynamoDBDraftStore() if get_settings().drafts_aws else SQLiteDraftStore()


def deterministic_revision(text: str, conflicts: list[ResolutionFinding],
                           recommendation: str) -> tuple[str, str]:
    """LLM-free fallback so the loop works with zero Bedrock access."""
    if not conflicts:
        return text, f"No verified conflict to revise against. {recommendation}"
    notes = "; ".join(f"{item.source} ({item.section}): {item.description}" for item in conflicts)
    revised = (f"{text}\n\n[Revision note — reconcile before advancing] "
               f"This draft conflicts with: {notes}")
    return revised, f"Flagged {len(conflicts)} verified conflict(s) for reconciliation: {notes}"


def llm_revision(text: str, conflicts: list[ResolutionFinding], recommendation: str) -> tuple[str, str]:
    from .llm import generate
    system = ("You revise draft university policy resolutions. Rewrite the draft so it no longer contradicts "
              "the cited existing policies, changing as little as possible. Return JSON only: "
              "{\"revised_text\": string, \"rationale\": string}. The rationale must cite each conflicting "
              "source by name. Never invent sources.")
    user = json.dumps({"draft": text, "verified_conflicts": [item.model_dump() for item in conflicts],
                       "recommendation": recommendation})
    raw = generate(system, user, json_mode=True)
    parsed = json.loads(raw)
    revised, rationale = str(parsed["revised_text"]), str(parsed["rationale"])
    if not revised.strip() or not rationale.strip():
        raise ValueError("Empty revision")
    return revised, rationale


@router.post("/revise", response_model=DraftReviseResponse)
def revise_draft(payload: DraftReviseRequest, _: None = Depends(require_reviewer)) -> DraftReviseResponse:
    draft_id = payload.draft_id or str(uuid4())
    pipeline = create_pipeline()
    result = pipeline.run(payload.text, draft=True)
    output = resolution_output(result)
    conflicts = [ResolutionFinding(source=item.source, section=item.section, description=item.description)
                 for item in output.conflicts]
    try:
        revised, rationale = llm_revision(payload.text, conflicts, output.recommendation)
    except Exception:
        revised, rationale = deterministic_revision(payload.text, conflicts, output.recommendation)
    version = draft_store().add_version(draft_id, payload.text, rationale)
    return DraftReviseResponse(
        draft_id=draft_id, version=version.version, revised_text=revised, rationale=rationale,
        overlaps=[ResolutionFinding(source=item.source, section=item.section, description=item.description) for item in output.overlaps],
        duplicates=[ResolutionFinding(source=item.source, section=item.section, description=item.description) for item in output.duplicates],
        conflicts=conflicts, recommendation=output.recommendation, agent_trace=result.agent_trace,
    )


@router.get("/{draft_id}/versions", response_model=list[DraftVersion])
def draft_versions(draft_id: str, _: None = Depends(require_reviewer)) -> list[DraftVersion]:
    return draft_store().list_versions(draft_id)
```

Wire `drafting.router` into main.py's router loop.

- [ ] **Step 5: Run new tests + full verifier** — green. (Locally with no Bedrock, `llm_revision` raises inside `generate` and the deterministic fallback fires — the endpoint never 500s.)

- [ ] **Step 6: Commit**

```bash
git add backend/app/drafting.py backend/app/database.py backend/app/models.py backend/app/main.py backend/tests/test_drafting.py
git commit -m "feat: AI-assisted drafting loop with versioned draft store"
```

---

### Task 6: Catalog scraper + edition-tagged ingestion

**Files:**
- Create: `backend/app/catalog.py`, `backend/scripts/__init__.py` (empty), `backend/scripts/scrape_catalog.py`, `backend/lambda_handlers/catalog_scraper.py`
- Test: `backend/tests/test_catalog.py`

**Interfaces:**
- Consumes: `append_to_index` from ingest.py, `register_document`/`registry_store` from Task 1, `CORPUS_DIR`, `reload_index`.
- Produces: `html_to_markdown(html: str) -> str`, `discover_policy_links(html: str, base_url: str) -> list[str]`, `scrape_edition(root_url: str, *, edition_year: int, is_current: bool, fetch: Callable[[str], str], max_pages: int = 40) -> list[CatalogPage]`, `ingest_catalog(pages: list[CatalogPage], *, edition_year: int, is_current: bool) -> int`. Stdlib only.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_catalog.py
from __future__ import annotations

from app.catalog import CatalogPage, discover_policy_links, html_to_markdown, ingest_catalog, scrape_edition
from app.registry import registry_store

HTML = """
<html><head><title>Academic Policies - CSUB Catalog</title></head><body>
<nav><a href="/misc/social.php">Follow us</a></nav>
<h1>Academic Policies</h1><h2>Grading</h2>
<p>Students <b>must</b> complete 120 units.</p>
<ul><li>First rule</li><li>Second rule</li></ul>
<a href="content.php?catoid=9&navoid=100">Grade Appeal Policy</a>
<a href="content.php?catoid=9&navoid=101">Degree Requirements</a>
<a href="/athletics.php">Basketball schedule</a>
</body></html>
"""


def test_html_to_markdown_keeps_structure_and_drops_tags() -> None:
    markdown = html_to_markdown(HTML)
    assert "# Academic Policies" in markdown
    assert "## Grading" in markdown
    assert "- First rule" in markdown
    assert "<p>" not in markdown and "<b>" not in markdown


def test_discover_policy_links_filters_by_keyword() -> None:
    links = discover_policy_links(HTML, "https://catalog.csub.edu/")
    assert "https://catalog.csub.edu/content.php?catoid=9&navoid=100" in links
    assert "https://catalog.csub.edu/content.php?catoid=9&navoid=101" in links
    assert all("athletics" not in link and "social" not in link for link in links)


def test_scrape_edition_crawls_with_fake_fetcher_and_respects_cap() -> None:
    calls: list[str] = []

    def fetch(url: str) -> str:
        calls.append(url)
        return HTML

    pages = scrape_edition("https://catalog.csub.edu/", edition_year=2026, is_current=True, fetch=fetch, max_pages=2)
    assert len(pages) == 2 and len(set(calls)) == 2  # no URL fetched twice


def test_ingest_catalog_registers_active_edition_tagged_sources() -> None:
    pages = [CatalogPage(url="https://catalog.csub.edu/x", title="Grade Appeal Policy", markdown="# Grade Appeal\nBody.")]
    added = ingest_catalog(pages, edition_year=2024, is_current=False)
    assert added >= 1
    record = next(item for item in registry_store().list() if item.source_type == "catalog")
    assert record.status == "active" and record.edition_year == 2024 and record.is_current is False
    assert record.canonical_url == "https://catalog.csub.edu/x"
```

- [ ] **Step 2: Run tests to verify they fail** — `ModuleNotFoundError: No module named 'app.catalog'`.

- [ ] **Step 3: Implement `backend/app/catalog.py`**

```python
from __future__ import annotations

import re
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Callable
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

from .config import CORPUS_DIR, ensure_data_directories, get_settings
from .ingest import append_to_index
from .registry import register_document
from .retrieval import reload_index

POLICY_LINK_KEYWORDS = ("polic", "academic", "regulation", "grade", "grading", "admission",
                        "registration", "degree", "requirement", "standing", "probation", "withdraw")
USER_AGENT = "CSUB-Policy-Intelligence-Demo/1.0 (hackathon; contact: campus IT)"


@dataclass(frozen=True)
class CatalogPage:
    url: str
    title: str
    markdown: str


class _MarkdownExtractor(HTMLParser):
    """Minimal HTML→Markdown: headings, paragraphs, list items, plain text. Skips script/style/nav."""

    SKIP = {"script", "style", "nav", "header", "footer"}
    HEADINGS = {"h1": "# ", "h2": "## ", "h3": "### ", "h4": "#### "}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.lines: list[str] = []
        self._buffer: list[str] = []
        self._prefix = ""
        self._skip_depth = 0
        self.title = ""
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self.SKIP:
            self._skip_depth += 1
        elif tag == "title":
            self._in_title = True
        elif tag in self.HEADINGS or tag == "p":
            self._flush()
            self._prefix = self.HEADINGS.get(tag, "")
        elif tag == "li":
            self._flush()
            self._prefix = "- "
        elif tag == "br":
            self._flush()

    def handle_endtag(self, tag: str) -> None:
        if tag in self.SKIP and self._skip_depth > 0:
            self._skip_depth -= 1
        elif tag == "title":
            self._in_title = False
        elif tag in self.HEADINGS or tag in {"p", "li", "ul", "ol"}:
            self._flush()

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        if self._in_title:
            self.title += data.strip()
            return
        self._buffer.append(data)

    def _flush(self) -> None:
        text = re.sub(r"\s+", " ", "".join(self._buffer)).strip()
        self._buffer = []
        if text:
            self.lines.append(f"{self._prefix}{text}")
        self._prefix = ""


def html_to_markdown(html: str) -> str:
    extractor = _MarkdownExtractor()
    extractor.feed(html)
    extractor._flush()
    return "\n\n".join(extractor.lines)


class _LinkExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str]] = []
        self._href: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            self._href = dict(attrs).get("href") or None
            self._text = []

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._href is not None:
            self.links.append((self._href, " ".join(self._text).strip()))
            self._href = None


def discover_policy_links(html: str, base_url: str) -> list[str]:
    extractor = _LinkExtractor()
    extractor.feed(html)
    host = urlparse(base_url).netloc
    found: list[str] = []
    for href, text in extractor.links:
        absolute = urljoin(base_url, href)
        haystack = f"{text} {absolute}".lower()
        if urlparse(absolute).netloc != host:
            continue
        if any(keyword in haystack for keyword in POLICY_LINK_KEYWORDS):
            if absolute not in found:
                found.append(absolute)
    return found


def _http_fetch(url: str) -> str:
    with urlopen(Request(url, headers={"User-Agent": USER_AGENT}), timeout=20.0) as response:  # noqa: S310
        return response.read().decode("utf-8", errors="replace")


def scrape_edition(root_url: str, *, edition_year: int, is_current: bool,
                   fetch: Callable[[str], str] = _http_fetch, max_pages: int = 40) -> list[CatalogPage]:
    queue: list[str] = [root_url]
    seen: set[str] = set()
    pages: list[CatalogPage] = []
    while queue and len(pages) < max_pages:
        url = queue.pop(0)
        if url in seen:
            continue
        seen.add(url)
        try:
            html = fetch(url)
        except Exception:
            continue
        markdown = html_to_markdown(html)
        extractor = _MarkdownExtractor()
        extractor.feed(html)
        title = extractor.title or url.rsplit("/", 1)[-1] or f"Catalog {edition_year}"
        if markdown.strip():
            pages.append(CatalogPage(url=url, title=title, markdown=markdown))
        for link in discover_policy_links(html, url):
            if link not in seen and link not in queue:
                queue.append(link)
    return pages


def _slug(title: str, edition_year: int, index: int) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:60] or f"page-{index}"
    return f"catalog-{edition_year}-{base}"


def ingest_catalog(pages: list[CatalogPage], *, edition_year: int, is_current: bool) -> int:
    """Write scraped pages as front-mattered .md into the corpus (or S3), index, and register them."""
    settings = get_settings()
    ensure_data_directories()
    added = 0
    for index, page in enumerate(pages):
        slug = _slug(page.title, edition_year, index)
        body = (f"---\ntitle: {page.title} ({edition_year} Catalog)\nsection: {page.title}\n"
                f"source_type: catalog\ncanonical_url: {page.url}\n---\n{page.markdown}\n")
        if settings.corpus_aws:
            import boto3  # type: ignore[import-not-found]
            boto3.client("s3", region_name=settings.aws_region).put_object(
                Bucket=settings.corpus_bucket, Key=f"raw/catalog/{edition_year}/{slug}.md",
                Body=body.encode("utf-8"), ContentType="text/markdown",
            )
            chunks = 1  # KB ingestion counts chunks server-side after sync.
        else:
            destination = CORPUS_DIR / "catalog" / str(edition_year) / f"{slug}.md"
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(body, encoding="utf-8")
            chunks = append_to_index(destination)
        register_document(
            (CORPUS_DIR / "catalog" / str(edition_year) / f"{slug}.md"),
            status="active", source_type="catalog", canonical_url=page.url,
            edition_year=edition_year, is_current=is_current, passages=chunks,
        ) if not settings.corpus_aws else _register_remote(slug, page, edition_year, is_current)
        added += chunks
    if not settings.corpus_aws:
        reload_index()
    return added


def _register_remote(slug: str, page: CatalogPage, edition_year: int, is_current: bool) -> None:
    from .models import SourceUpsert
    from .registry import registry_store
    registry_store().upsert(SourceUpsert(
        id=slug, title=f"{page.title} ({edition_year} Catalog)", source_type="catalog", status="active",
        canonical_url=page.url, edition_year=edition_year, is_current=is_current,
        s3_key=f"raw/catalog/{edition_year}/{slug}.md",
    ))
```

- [ ] **Step 4: CLI + Lambda entries**

`backend/scripts/scrape_catalog.py`:

```python
"""Scrape the CSUB course catalog into the policy corpus.

Usage (from backend/, venv active):
  python -m scripts.scrape_catalog --url https://catalog.csub.edu/ --year 2026 --current
  python -m scripts.scrape_catalog --url <one archived edition root from https://catalog.csub.edu/archivedcatalogs/> --year 2024
"""
from __future__ import annotations

import argparse

from app.catalog import ingest_catalog, scrape_edition


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--current", action="store_true")
    parser.add_argument("--max-pages", type=int, default=40)
    args = parser.parse_args()
    pages = scrape_edition(args.url, edition_year=args.year, is_current=args.current, max_pages=args.max_pages)
    added = ingest_catalog(pages, edition_year=args.year, is_current=args.current)
    print(f"Scraped {len(pages)} page(s), indexed {added} chunk(s) for the {args.year} catalog.")


if __name__ == "__main__":
    main()
```

`backend/lambda_handlers/catalog_scraper.py`:

```python
"""EventBridge/manual Lambda: scrape a catalog edition into the raw S3 corpus prefix."""
from __future__ import annotations

import os
from typing import Any

from app.catalog import ingest_catalog, scrape_edition


def handler(event: dict[str, Any], _context: object) -> dict[str, Any]:
    url = str(event.get("url") or os.environ["CATALOG_URL"])
    year = int(event.get("year") or os.environ["CATALOG_YEAR"])
    is_current = bool(event.get("is_current", os.environ.get("CATALOG_IS_CURRENT") == "true"))
    pages = scrape_edition(url, edition_year=year, is_current=is_current,
                           max_pages=int(event.get("max_pages", 40)))
    added = ingest_catalog(pages, edition_year=year, is_current=is_current)
    return {"pages": len(pages), "chunks": added, "edition_year": year, "is_current": is_current}
```

- [ ] **Step 5: Run new tests + full verifier** — green (tests never hit the network; they inject `fetch`).

- [ ] **Step 6: Live smoke test (local, requires network; do NOT put in pytest)**

Run: `cd backend && .venv/bin/python -m scripts.scrape_catalog --url https://catalog.csub.edu/ --year 2026 --current --max-pages 15`
Expected: `Scraped N page(s), indexed M chunk(s)` with N ≥ 5. Then repeat with one archived edition root picked from https://catalog.csub.edu/archivedcatalogs/ and `--year <that year>` (no `--current`). If embeddings are unavailable locally (no Bedrock), the index append fails — in that case verify pages+registry only and defer embedding to the AWS path; note the result in PROGRESS-AWS.md.

- [ ] **Step 7: Commit**

```bash
git add backend/app/catalog.py backend/scripts backend/lambda_handlers/catalog_scraper.py backend/tests/test_catalog.py
git commit -m "feat: stdlib catalog scraper with edition-tagged corpus ingestion"
```

---

### Task 7: Frontend API layer — identity, registry sources, permissions, drafting

**Files:**
- Modify: `frontend/src/api.ts`, `frontend/src/data/mock.ts` (add `"Archived"` to `SourceStatus` union)
- Test: `cd frontend && npx tsc --noEmit && npm run build`

**Interfaces:**
- Consumes: backend routes from Tasks 1, 3, 4, 5.
- Produces (used by Tasks 8–9): `RegistrySource`, `getRegistrySources(): Promise<RegistrySource[]>`, `setSourceStatus(id: string, status: "active" | "archived"): Promise<RegistrySource>`, `Permission`, `getPermissions(): Promise<Permission[]>`, `savePermission(p: Permission): Promise<Permission>`, `DraftRevision`, `reviseDraft(text: string, draftId?: string): Promise<DraftRevision>`; `askQuestion(text, role)` gains a role argument; `login()` stores the demo email under `policy-intelligence.user-email`.

- [ ] **Step 1: Identity + role headers**

In `login()`, after a successful result, persist the identity: `window.localStorage.setItem("policy-intelligence.user-email", email);` (and in the fallback branch too). In `backendRequest`, after the Cognito header block, add:

```ts
const demoEmail = window.localStorage.getItem("policy-intelligence.user-email");
if (authorizationToken === null && demoEmail !== null) headers.set("X-User-Email", demoEmail);
```

Change `askQuestion` to accept the caller's role and forward it:

```ts
export async function askQuestion(text: string, role: Role = "reviewer"): Promise<Answer> {
  // ... existing body; add to the POST init headers:
  headers: { "Content-Type": "application/json", "X-Role": role },
```

Update the call site (`ChatAnswer.tsx` uses `askQuestion`) to pass `useRole().role`.

- [ ] **Step 2: New endpoint bindings**

```ts
export interface RegistrySource {
  id: string;
  title: string;
  sourceType: "handbook" | "cba" | "policystat" | "catalog" | "uploads";
  status: "active" | "archived";
  canonicalUrl: string;
  editionYear: number | null;
  isCurrent: boolean;
  passages: number;
  updated: string;
}

interface BackendRegistrySource {
  id: string; title: string; source_type: RegistrySource["sourceType"];
  status: RegistrySource["status"]; canonical_url: string; edition_year: number | null;
  is_current: boolean; passages: number; updated_at: string;
}

const mapRegistrySource = (item: BackendRegistrySource): RegistrySource => ({
  id: item.id, title: item.title, sourceType: item.source_type, status: item.status,
  canonicalUrl: item.canonical_url, editionYear: item.edition_year, isCurrent: item.is_current,
  passages: item.passages, updated: new Date(item.updated_at).toLocaleDateString(),
});

export async function getRegistrySources(): Promise<RegistrySource[]> {
  const backend = await backendRequest<BackendRegistrySource[]>("/api/sources");
  return backend === null ? [] : backend.map(mapRegistrySource);
}

export async function setSourceStatus(id: string, status: "active" | "archived"): Promise<RegistrySource> {
  const backend = await backendRequest<BackendRegistrySource>(`/api/sources/${encodeURIComponent(id)}/status`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ status }),
  });
  if (backend === null) throw new Error("Unable to update the source status.");
  return mapRegistrySource(backend);
}

export interface Permission {
  userEmail: string;
  sourceType: RegistrySource["sourceType"];
  canAdd: boolean;
  canEdit: boolean;
}

interface BackendPermission { user_email: string; source_type: Permission["sourceType"]; can_add: boolean; can_edit: boolean; }

export async function getPermissions(): Promise<Permission[]> {
  const backend = await backendRequest<BackendPermission[]>("/api/permissions");
  return backend === null ? [] : backend.map((item) => ({
    userEmail: item.user_email, sourceType: item.source_type, canAdd: item.can_add, canEdit: item.can_edit,
  }));
}

export async function savePermission(permission: Permission): Promise<Permission> {
  const backend = await backendRequest<BackendPermission>("/api/permissions", {
    method: "PUT", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ user_email: permission.userEmail, source_type: permission.sourceType,
                           can_add: permission.canAdd, can_edit: permission.canEdit }),
  });
  if (backend === null) throw new Error("Unable to save the permission.");
  return { userEmail: backend.user_email, sourceType: backend.source_type, canAdd: backend.can_add, canEdit: backend.can_edit };
}

export interface DraftRevision {
  draftId: string;
  version: number;
  revisedText: string;
  rationale: string;
  findings: ReviewAnalysis["findings"];
  recommendation: string;
  agentTrace: AgentTraceStep[];
}

interface BackendDraftRevision {
  draft_id: string; version: number; revised_text: string; rationale: string;
  overlaps: BackendResolutionFinding[]; duplicates: BackendResolutionFinding[];
  conflicts: BackendResolutionFinding[]; recommendation: string; agent_trace: BackendAgentTrace[];
}

export async function reviseDraft(text: string, draftId?: string): Promise<DraftRevision> {
  const backend = await backendRequest<BackendDraftRevision>("/api/draft/revise", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, ...(draftId === undefined ? {} : { draft_id: draftId }) }),
  }, AGENT_REQUEST_TIMEOUT_MS, agentBaseUrl);
  if (backend === null) throw new Error("The drafting assistant is unavailable. Start the backend and try again.");
  return {
    draftId: backend.draft_id, version: backend.version, revisedText: backend.revised_text,
    rationale: backend.rationale, recommendation: backend.recommendation,
    findings: [
      ...backend.overlaps.map((finding) => ({ type: "Overlap" as const, source: `${finding.source} • ${finding.section}` })),
      ...backend.duplicates.map((finding) => ({ type: "Possible duplicate" as const, source: `${finding.source} • ${finding.section}` })),
      ...backend.conflicts.map((finding) => ({ type: "Conflict" as const, source: `${finding.source} • ${finding.section}` })),
    ],
    agentTrace: backend.agent_trace.map(({ citations, ...step }) => ({
      ...step,
      ...(citations === undefined ? {} : { citations: citations.map((citation) => ({ id: citation.id, title: citation.source, section: citation.section })) }),
    })),
  };
}
```

In `frontend/src/data/mock.ts`, extend the `SourceStatus` union with `"Archived"` and add it to `statusStyles` consumers (Task 8 updates Sources.tsx).

- [ ] **Step 3: Verify** — `cd frontend && npx tsc --noEmit && npm run build` → clean.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/api.ts frontend/src/data/mock.ts frontend/src/pages/ChatAnswer.tsx
git commit -m "feat: frontend API bindings for registry, permissions, drafting, and role headers"
```

---

### Task 8: Sources page — archive lifecycle + permission panel

**Files:**
- Modify: `frontend/src/pages/Sources.tsx`
- Create: `frontend/src/components/SourcePermissions.tsx`
- Test: tsc + build + manual Playwright click-through

**Interfaces:**
- Consumes: `getRegistrySources`, `setSourceStatus`, `getPermissions`, `savePermission` from Task 7.

- [ ] **Step 1: Archive tab and actions in Sources.tsx**

Change `type Tab = "Active" | "Archive" | "Processing";` (drop "Needs review", keep search). Load both legacy uploads (existing `getSources()` merge, unchanged fallback) and the registry:

```tsx
const [registry, setRegistry] = useState<RegistrySource[]>([]);
useEffect(() => { void getRegistrySources().then(setRegistry).catch(() => setRegistry([])); }, []);
```

When `registry.length > 0`, render the table from registry rows instead of the localStorage mock list: Document = `title` (with `editionYear` badge for catalog rows, e.g. `2024 edition` in a muted pill when `!isCurrent`), Type = `sourceType.toUpperCase()`, Coverage = `passages` , Status pill = `Active` (green, existing `Ready` style) or `Archived` (slate). Tab filter: `Active` → `status === "active"`, `Archive` → `status === "archived"`. Row action button replaces the `…` details button:

```tsx
<button type="button" onClick={() => { void toggleStatus(source); }}
  className="rounded-md border border-navy/25 px-4 py-1.5 text-sm text-brand-blue hover:bg-cream">
  {source.status === "active" ? "Archive" : "Unarchive"}
</button>
```

with

```tsx
const toggleStatus = async (source: RegistrySource) => {
  try {
    const updated = await setSourceStatus(source.id, source.status === "active" ? "archived" : "active");
    setRegistry((current) => current.map((item) => (item.id === updated.id ? updated : item)));
    setFeedback(updated.status === "active"
      ? `${updated.title} is live under Sources and retrievable.`
      : `${updated.title} moved to the Archive — stored but excluded from answers.`);
  } catch (reason) {
    setError(reason instanceof Error ? reason.message : "Unable to update the source status.");
  }
};
```

After a successful upload completes (`update.status === "ready"` in the poll callback), also call `getRegistrySources().then(setRegistry)` so the new file appears on the **Archive** tab (new uploads land archived), and set feedback: `` `${file.name} uploaded to the Archive. Unarchive it to make it retrievable.` ``. Keep the amber banner text and change it to: `New uploads land in the Archive and only power answers once unarchived.`

- [ ] **Step 2: Create `frontend/src/components/SourcePermissions.tsx`**

```tsx
import { useEffect, useState } from "react";
import { getPermissions, savePermission, type Permission } from "../api";

const SOURCE_TYPES: Permission["sourceType"][] = ["handbook", "cba", "policystat", "catalog", "uploads"];

export default function SourcePermissions() {
  const [permissions, setPermissions] = useState<Permission[]>([]);
  const [email, setEmail] = useState("");
  const [error, setError] = useState("");
  useEffect(() => { void getPermissions().then(setPermissions).catch(() => setPermissions([])); }, []);

  const users = [...new Set(permissions.map((item) => item.userEmail))];
  const cell = (user: string, sourceType: Permission["sourceType"]): Permission =>
    permissions.find((item) => item.userEmail === user && item.sourceType === sourceType)
      ?? { userEmail: user, sourceType, canAdd: false, canEdit: false };

  const toggle = async (user: string, sourceType: Permission["sourceType"], field: "canAdd" | "canEdit") => {
    const current = cell(user, sourceType);
    try {
      const saved = await savePermission({ ...current, [field]: !current[field] });
      setPermissions((existing) => [saved, ...existing.filter((item) => !(item.userEmail === user && item.sourceType === sourceType))]);
      setError("");
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Unable to save the permission."); }
  };

  const addUser = async () => {
    const clean = email.trim().toLowerCase();
    if (!clean.includes("@")) { setError("Enter a campus email address."); return; }
    try {
      const saved = await savePermission({ userEmail: clean, sourceType: "uploads", canAdd: true, canEdit: false });
      setPermissions((existing) => [saved, ...existing]);
      setEmail(""); setError("");
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Unable to add this user."); }
  };

  return (
    <section className="mt-12 rounded-xl border border-navy/15 bg-white p-7 shadow-card">
      <h2 className="text-2xl font-bold text-navy">Source access permissions</h2>
      <p className="mt-1 text-inkmuted">Grant reviewers and writers the ability to add or edit sources, per source type.</p>
      <div className="mt-5 flex gap-3">
        <input value={email} onChange={(event) => setEmail(event.target.value)} placeholder="reviewer email…"
          className="h-11 w-80 rounded-lg border border-navy/25 px-4 outline-none focus:border-brand-blue" />
        <button type="button" onClick={() => { void addUser(); }} className="rounded-md bg-navy px-5 text-white hover:bg-brand-blue">Grant upload access</button>
      </div>
      {error && <p role="alert" className="mt-3 text-sm text-red-700">{error}</p>}
      <table className="mt-6 w-full text-left text-sm">
        <thead className="border-b border-navy/15 text-slate-600">
          <tr><th className="py-3">User</th>{SOURCE_TYPES.map((sourceType) => <th key={sourceType} className="py-3 capitalize">{sourceType}</th>)}</tr>
        </thead>
        <tbody>
          {users.map((user) => (
            <tr key={user} className="border-b border-navy/10">
              <td className="py-3 font-medium text-navy">{user}</td>
              {SOURCE_TYPES.map((sourceType) => {
                const permission = cell(user, sourceType);
                return (
                  <td key={sourceType} className="py-3">
                    <label className="mr-3 inline-flex items-center gap-1"><input type="checkbox" checked={permission.canAdd}
                      onChange={() => { void toggle(user, sourceType, "canAdd"); }} />add</label>
                    <label className="inline-flex items-center gap-1"><input type="checkbox" checked={permission.canEdit}
                      onChange={() => { void toggle(user, sourceType, "canEdit"); }} />edit</label>
                  </td>
                );
              })}
            </tr>
          ))}
          {users.length === 0 && <tr><td colSpan={6} className="py-6 text-inkmuted">No grants yet — the backend seeds the demo reviewer automatically.</td></tr>}
        </tbody>
      </table>
    </section>
  );
}
```

Render `<SourcePermissions />` at the bottom of `Sources.tsx` (below the amber banner).

- [ ] **Step 3: Verify** — tsc + build clean; run backend + `npm run dev`, click Archive/Unarchive on a seeded source, ask a chat question touching an archived source and confirm it no longer surfaces; toggle a permission checkbox and re-load.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/Sources.tsx frontend/src/components/SourcePermissions.tsx
git commit -m "feat: Sources page archive lifecycle and source-access permission panel"
```

---

### Task 9: Drafting UI on Resolution Checker + Resource Catalog page

**Files:**
- Create: `frontend/src/components/DraftAssistant.tsx`, `frontend/src/pages/Catalog.tsx`
- Modify: `frontend/src/pages/ReviewResults.tsx`, `frontend/src/pages/TopicList.tsx`, `frontend/src/App.tsx`

**Interfaces:**
- Consumes: `reviseDraft`, `getRegistrySources` from Task 7; `checkResolution` (existing).

- [ ] **Step 1: `frontend/src/components/DraftAssistant.tsx`**

```tsx
import { useState } from "react";
import { reviseDraft, type DraftRevision } from "../api";
import { useRole } from "../state/role";

interface DraftAssistantProps {
  draftText: string;
  onAdoptRevision: (revisedText: string) => void;
}

export default function DraftAssistant({ draftText, onAdoptRevision }: DraftAssistantProps) {
  const { role } = useRole();
  const [revision, setRevision] = useState<DraftRevision | null>(null);
  const [history, setHistory] = useState<DraftRevision[]>([]);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState("");
  if (role !== "reviewer") return null;

  const suggest = async () => {
    setWorking(true); setError("");
    try {
      const next = await reviseDraft(draftText, revision?.draftId);
      setRevision(next);
      setHistory((current) => [next, ...current]);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Unable to draft a revision."); }
    finally { setWorking(false); }
  };

  return (
    <section className="mt-10 rounded-xl border border-navy/20 bg-white p-6 shadow-card">
      <div className="flex items-center justify-between">
        <div><h2 className="text-lg font-bold text-navy">Draft with AI</h2>
          <p className="mt-1 text-sm text-inkmuted">Iterate on this draft against the conflicting policies until it comes back clean.</p></div>
        <button type="button" disabled={working} onClick={() => { void suggest(); }}
          className="rounded-lg bg-navy px-5 py-2.5 text-sm font-semibold text-white hover:bg-navy-deep disabled:opacity-50">
          {working ? "Revising…" : revision === null ? "Suggest a revision" : "Revise again"}
        </button>
      </div>
      {error && <p role="alert" className="mt-3 text-sm text-red-700">{error}</p>}
      {revision && (
        <div className="mt-5">
          <p className="rounded-md border border-brand-blue/20 bg-blue-50 px-4 py-2 text-xs font-medium text-brand-blue">
            Version {revision.version} — {revision.findings.length} finding(s) referenced
          </p>
          <p className="mt-3 whitespace-pre-wrap text-sm leading-6 text-navy-text">{revision.revisedText}</p>
          <p className="mt-3 text-sm text-inkmuted"><span className="font-semibold text-navy">Why: </span>{revision.rationale}</p>
          <div className="mt-4 flex gap-3">
            <button type="button" onClick={() => onAdoptRevision(revision.revisedText)}
              className="rounded-md border border-navy/25 px-4 py-2 text-sm text-brand-blue hover:bg-cream">Adopt revision and re-check</button>
          </div>
          {history.length > 1 && (
            <ol className="mt-5 border-t border-navy/10 pt-3 text-xs text-inkmuted">
              {history.map((item) => <li key={`${item.draftId}-${item.version}`} className="py-1">v{item.version} — {item.findings.length} finding(s) · {item.recommendation.slice(0, 90)}</li>)}
            </ol>
          )}
        </div>
      )}
    </section>
  );
}
```

- [ ] **Step 2: Mount in `ReviewResults.tsx`**

After the findings/recommendation block (below the existing recommendation `<div>`), add:

```tsx
{submission !== null && analysis !== null && (
  <DraftAssistant draftText={submission.text} onAdoptRevision={(revisedText) => {
    const next = { ...submission, text: revisedText };
    saveReviewSubmission(next);
    setSubmission(next);
    setAnalysis(null);
    void checkResolution(revisedText).then(setAnalysis).catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "Unable to analyze this draft."));
  }} />
)}
```

(Import `DraftAssistant` and `saveReviewSubmission`.)

- [ ] **Step 3: `frontend/src/pages/Catalog.tsx`**

```tsx
import { useEffect, useMemo, useState } from "react";
import { getRegistrySources, type RegistrySource } from "../api";
import BackButton from "../components/BackButton";
import { useRole } from "../state/role";

export default function Catalog() {
  const { role } = useRole();
  const [sources, setSources] = useState<RegistrySource[]>([]);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  useEffect(() => {
    void getRegistrySources().then(setSources)
      .catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "Unable to load the resource catalog."));
  }, []);
  const visible = useMemo(
    () => sources.filter((source) => (role === "reviewer" || source.status === "active")
      && source.title.toLowerCase().includes(search.toLowerCase())),
    [sources, role, search],
  );

  return (
    <section className="mx-auto max-w-[1100px] pt-1 text-navy">
      <BackButton fallback="/topics" />
      <h1 className="text-[40px] font-bold leading-tight tracking-tight">Resource catalog</h1>
      <p className="mt-2 text-lg text-inkmuted">Every indexed source, with a link back to the canonical document.</p>
      <label className="relative mt-6 block w-[395px]">
        <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search resources…"
          className="h-[50px] w-full rounded-lg border border-navy/25 px-4 text-lg outline-none placeholder:text-inkmuted focus:border-brand-blue" />
      </label>
      {error && <p role="alert" className="mt-4 text-red-700">{error}</p>}
      <ul className="mt-6 divide-y divide-navy/10">
        {visible.map((source) => (
          <li key={source.id} className="flex items-center justify-between py-4">
            <div>
              <p className="text-lg font-medium">{source.title}
                {source.editionYear !== null && !source.isCurrent && <span className="ml-3 rounded-full bg-slate-100 px-3 py-0.5 text-xs text-slate-600">{source.editionYear} edition</span>}
              </p>
              <p className="text-sm text-inkmuted">{source.sourceType.toUpperCase()} · {source.passages.toLocaleString()} passages</p>
            </div>
            <div className="flex items-center gap-4">
              {role === "reviewer" && <span className={`rounded-full px-3 py-1 text-sm ${source.status === "active" ? "border border-green-300 bg-green-50 text-green-800" : "border border-slate-300 bg-slate-50 text-slate-700"}`}>{source.status}</span>}
              {source.canonicalUrl !== "" && <a href={source.canonicalUrl} target="_blank" rel="noreferrer" className="text-brand-blue hover:underline">Open source ↗</a>}
            </div>
          </li>
        ))}
        {visible.length === 0 && !error && <li className="py-8 text-inkmuted">No indexed resources yet — start the backend to load the registry.</li>}
      </ul>
    </section>
  );
}
```

- [ ] **Step 4: Route + entry links**

In `App.tsx`: `<Route path="/catalog" element={<SharedRoute><Catalog /></SharedRoute>} />`. In `TopicList.tsx`, add under the page heading: `<Link to="/catalog" className="text-brand-blue hover:underline">Browse the full resource catalog →</Link>` (import `Link` from react-router-dom). In `Sources.tsx` header area, add the same link. (BackButton is created in Task 10 — if executing tasks in order, create `frontend/src/components/BackButton.tsx` from Task 10 Step 1 now, or temporarily omit the `<BackButton />` line and add it in Task 10.)

- [ ] **Step 5: Verify** — tsc + build; dev-server click-through: Topics → catalog link → open-source links work; employee sees active-only with no status pills.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/DraftAssistant.tsx frontend/src/pages/Catalog.tsx frontend/src/pages/ReviewResults.tsx frontend/src/pages/TopicList.tsx frontend/src/pages/Sources.tsx frontend/src/App.tsx
git commit -m "feat: revise-with-AI drafting loop and shared resource catalog page"
```

---

### Task 10: Dark mode, back buttons, emblem→home

**Files:**
- Create: `frontend/src/state/theme.tsx`, `frontend/src/components/SettingsMenu.tsx`, `frontend/src/components/BackButton.tsx`
- Modify: `frontend/tailwind.config.js`, `frontend/src/index.css`, `frontend/src/App.tsx`, `frontend/src/components/Sidebar.tsx`, `frontend/src/pages/ChatAnswer.tsx`, `frontend/src/pages/TopicDetail.tsx`, `frontend/src/pages/ConflictReview.tsx`, `frontend/src/pages/ReviewResults.tsx`

- [ ] **Step 1: `frontend/src/components/BackButton.tsx`**

```tsx
import { useNavigate } from "react-router-dom";

export default function BackButton({ fallback }: { fallback: string }) {
  const navigate = useNavigate();
  const goBack = () => {
    if (window.history.length > 1) navigate(-1);
    else navigate(fallback);
  };
  return (
    <button type="button" onClick={goBack} aria-label="Go back"
      className="mb-4 inline-flex items-center gap-2 text-sm font-medium text-brand-blue hover:underline">
      <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M15 19 8 12l7-7" /></svg>
      Back
    </button>
  );
}
```

Mount at the top of the returned section in: `ChatAnswer.tsx` (`fallback="/chats"`), `TopicDetail.tsx` (`fallback="/topics"`), `ConflictReview.tsx` (`fallback="/conflicts"`), `ReviewResults.tsx` (`fallback="/reviews"`), and `Catalog.tsx` (already placed in Task 9).

- [ ] **Step 2: CSS-variable palette for dark mode**

In `frontend/tailwind.config.js`, set `darkMode: "class"` and switch the shared surface colors to variables:

```js
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        navy: { DEFAULT: "rgb(var(--c-navy) / <alpha-value>)", deep: "rgb(var(--c-navy-deep) / <alpha-value>)", text: "rgb(var(--c-navy-text) / <alpha-value>)" },
        brand: { blue: "rgb(var(--c-brand-blue) / <alpha-value>)", bright: "#2563eb" },
        gold: "#f5b301",
        cream: "rgb(var(--c-cream) / <alpha-value>)",
        amberbg: "rgb(var(--c-amberbg) / <alpha-value>)",
        inkmuted: "rgb(var(--c-inkmuted) / <alpha-value>)",
        white: "rgb(var(--c-white) / <alpha-value>)",
      },
      // fontFamily and boxShadow blocks unchanged
    },
  },
  plugins: [],
};
```

In `frontend/src/index.css` (top, before Tailwind layers or inside `@layer base`):

```css
:root {
  --c-navy: 22 48 94; --c-navy-deep: 18 42 84; --c-navy-text: 27 42 74;
  --c-brand-blue: 29 78 216; --c-cream: 247 245 241; --c-amberbg: 254 247 230;
  --c-inkmuted: 91 107 130; --c-white: 255 255 255;
}
.dark {
  --c-navy: 226 232 240; --c-navy-deep: 241 245 249; --c-navy-text: 214 222 235;
  --c-brand-blue: 96 165 250; --c-cream: 20 28 44; --c-amberbg: 51 44 24;
  --c-inkmuted: 148 163 184; --c-white: 15 23 42;
}
body { @apply bg-white text-navy-text; }
```

Because `bg-white`, `bg-cream`, `text-navy`, `text-inkmuted`, and `bg-amberbg` cover the app's surfaces, this flips every page without per-component `dark:` classes. Remaining stock-Tailwind grays (`text-slate-600`, `bg-slate-50`, `border-slate-300`, `bg-blue-50`, `bg-green-50`, `bg-red-50`) stay readable in dark mode; where a specific page looks off during the click-through, add a targeted `dark:` variant there (e.g. `dark:bg-slate-800/40` on `bg-slate-50` pills) rather than restructuring.

- [ ] **Step 3: `frontend/src/state/theme.tsx`**

```tsx
import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

type Theme = "light" | "dark";
const STORAGE_KEY = "policy-intelligence-theme";
const ThemeContext = createContext<{ theme: Theme; setTheme: (theme: Theme) => void } | null>(null);

function storedTheme(): Theme {
  return window.localStorage.getItem(STORAGE_KEY) === "dark" ? "dark" : "light";
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<Theme>(storedTheme);
  useEffect(() => {
    document.documentElement.classList.toggle("dark", theme === "dark");
  }, [theme]);
  const value = useMemo(() => ({
    theme,
    setTheme: (next: Theme) => { window.localStorage.setItem(STORAGE_KEY, next); setThemeState(next); },
  }), [theme]);
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme(): { theme: Theme; setTheme: (theme: Theme) => void } {
  const context = useContext(ThemeContext);
  if (context === null) throw new Error("useTheme must be used within ThemeProvider");
  return context;
}
```

Wrap the app in `App.tsx`: `return <ThemeProvider><RoleProvider>…</RoleProvider></ThemeProvider>;`.

- [ ] **Step 4: `frontend/src/components/SettingsMenu.tsx` + Sidebar changes**

```tsx
import { useEffect, useRef, useState } from "react";
import { useTheme } from "../state/theme";

export default function SettingsMenu() {
  const { theme, setTheme } = useTheme();
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const close = (event: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);

  return (
    <div ref={containerRef} className="relative flex flex-col items-center">
      <button type="button" onClick={() => setOpen((value) => !value)} aria-expanded={open} aria-haspopup="menu"
        className="flex flex-col items-center gap-1 py-3 text-xs text-navy hover:text-brand-blue">
        <svg className="h-7 w-7" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6"><circle cx="12" cy="12" r="3" /><path d="m19 13.5 2-1.5-2-1.5-.7-1.8.4-2.5-2.5-.4-1.7-1.3L13.5 2 12 4l-1.5-2-1 2.5-1.7 1.3-2.5.4.4 2.5L5 10.5 3 12l2 1.5.7 1.8-.4 2.5 2.5.4 1.7 1.3 1 2.5 1.5-2 1.5 2 1-2.5 1.7-1.3 2.5-.4-.4-2.5z" /></svg>
        <span>Settings</span>
      </button>
      {open && (
        <div role="menu" className="absolute bottom-14 left-16 z-30 w-52 rounded-xl border border-navy/15 bg-white p-4 shadow-card">
          <p className="text-xs font-semibold uppercase tracking-wide text-inkmuted">Appearance</p>
          <button type="button" role="menuitem" onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
            className="mt-2 flex w-full items-center justify-between rounded-md px-2 py-2 text-sm text-navy hover:bg-cream">
            <span>Dark mode</span>
            <span className={`flex h-5 w-9 items-center rounded-full px-0.5 transition-colors ${theme === "dark" ? "justify-end bg-brand-blue" : "bg-slate-300"}`}>
              <span className="h-4 w-4 rounded-full bg-white shadow" />
            </span>
          </button>
        </div>
      )}
    </div>
  );
}
```

In `Sidebar.tsx`: replace the static gear block (`<div className="flex flex-col items-center gap-1 py-3 text-xs text-navy"><Icon name="gear" /><span>Settings</span></div>`) with `<SettingsMenu />`, and wrap the emblem in a link to the role-selection home:

```tsx
import { NavLink, Link } from "react-router-dom";
// ...
<div className="flex h-24 items-center justify-center">
  <Link to="/login" aria-label="Return to role selection"><Logo size={45} /></Link>
</div>
```

- [ ] **Step 5: Verify** — tsc + build; click-through both roles in light and dark (login, chat with conflict, topics, catalog, sources, reviews + draft assistant, conflict log), checking every surface is legible; back buttons land correctly; emblem returns to `/login`.

- [ ] **Step 6: Commit**

```bash
git add frontend/tailwind.config.js frontend/src/index.css frontend/src/state/theme.tsx frontend/src/components/SettingsMenu.tsx frontend/src/components/BackButton.tsx frontend/src/components/Sidebar.tsx frontend/src/App.tsx frontend/src/pages/ChatAnswer.tsx frontend/src/pages/TopicDetail.tsx frontend/src/pages/ConflictReview.tsx frontend/src/pages/ReviewResults.tsx
git commit -m "feat: dark mode via settings popover, back buttons, emblem returns home"
```

---

### Task 11: Infra — DynamoDB tables, scraper Lambda, env wiring

**Files:**
- Modify: `infra/stacks/policy_intelligence_stack.py`, `infra/README.md`

**Interfaces:**
- Consumes: existing stack constructs (API Lambda, agent Lambda, corpus bucket, existing `dynamodb.Table` pattern for ConflictLog/Uploads).
- Produces: env vars `DDB_REGISTRY_TABLE`, `DDB_PERMISSIONS_TABLE`, `DDB_DRAFTS_TABLE` on the API + agent Lambdas; a `CatalogScraperFunction`; stack outputs for the three table names.

- [ ] **Step 1: Add tables** (follow the exact pattern the stack already uses for the conflicts/uploads tables — PAY_PER_REQUEST, `RemovalPolicy.DESTROY`):

```python
registry_table = dynamodb.Table(
    self, "SourceRegistry",
    partition_key=dynamodb.Attribute(name="id", type=dynamodb.AttributeType.STRING),
    billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
    removal_policy=RemovalPolicy.DESTROY,
)
permissions_table = dynamodb.Table(
    self, "SourcePermissions",
    partition_key=dynamodb.Attribute(name="user_email", type=dynamodb.AttributeType.STRING),
    sort_key=dynamodb.Attribute(name="source_type", type=dynamodb.AttributeType.STRING),
    billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
    removal_policy=RemovalPolicy.DESTROY,
)
drafts_table = dynamodb.Table(
    self, "DraftVersions",
    partition_key=dynamodb.Attribute(name="draft_id", type=dynamodb.AttributeType.STRING),
    sort_key=dynamodb.Attribute(name="version", type=dynamodb.AttributeType.NUMBER),
    billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
    removal_policy=RemovalPolicy.DESTROY,
)
```

- [ ] **Step 2: Wire env + grants** — for both the API Lambda and the agent Lambda (same place `DDB_CONFLICTS_TABLE` is set): add `DDB_REGISTRY_TABLE`, `DDB_PERMISSIONS_TABLE`, `DDB_DRAFTS_TABLE` environment entries and `grant_read_write_data` for each table; grant the API Lambda `corpus_bucket.grant_put` for the `drafts/*` prefix (drafts S3 copies).

- [ ] **Step 3: Scraper Lambda** — same bundling pattern as the ingestion Lambda, handler `lambda_handlers/catalog_scraper.handler`, timeout 10 minutes, memory 512 MB, env `CORPUS_BUCKET`, `DDB_REGISTRY_TABLE`, `AWS_REGION` implicit; grant `corpus_bucket.grant_put` and registry `grant_read_write_data`. No EventBridge schedule for the demo (invoke manually per edition); note in infra/README.md the two invoke payloads:

```json
{"url": "https://catalog.csub.edu/", "year": 2026, "is_current": true}
{"url": "<archived edition root>", "year": 2024, "is_current": false}
```

- [ ] **Step 4: Verify** — `python -m py_compile infra/stacks/policy_intelligence_stack.py` and run the existing infra tests: `/home/tim/AI-Summer-Camp-Academicaffairs-Senateresolution/backend/.venv/bin/python -m pytest infra/tests -q` (2 tests currently). `cdk synth` requires aws-cdk-lib which is not installed — do not attempt it.

- [ ] **Step 5: Commit**

```bash
git add infra/stacks/policy_intelligence_stack.py infra/README.md
git commit -m "feat: infra for registry/permissions/drafts tables and catalog scraper Lambda"
```

---

### Task 12: Docs + handoff

**Files:**
- Modify: `AWS_SETUP.md`, `CLAUDE.md`, `PROGRESS-AWS.md`

- [ ] **Step 1: AWS_SETUP.md** — in section 4 (backend env vars), add `DDB_REGISTRY_TABLE`, `DDB_PERMISSIONS_TABLE`, `DDB_DRAFTS_TABLE` (from the new stack outputs). Add a new section "7. Catalog scrape" with the two Lambda invoke payloads (current 2026 + one archived edition) and the local CLI equivalents from Task 6. Note that Cognito remains optional and OFF for the demo; conflict gating uses the demo role header until `VITE_USE_COGNITO`/`COGNITO_*` are set.

- [ ] **Step 2: CLAUDE.md** — add a "PRD Round-2 (2026-07-15)" section recording: registry/archive lifecycle (seeds active, uploads archived), per-source-type permissions with reviewer-as-admin, role-gated conflict softening (X-Role locally / claims in Cognito mode, default reviewer), drafting loop endpoints, catalog scraper (stdlib-only, current + one archived edition, 0.5 down-rank), `/catalog` shared route, dark mode via CSS variables + settings popover, sidebar emblem→/login. Update "Last Updated".

- [ ] **Step 3: Append one PROGRESS-AWS.md line** per completed task, same format as existing entries.

- [ ] **Step 4: Final verifier + commit**

Run both verifier commands one last time, then:

```bash
git add AWS_SETUP.md CLAUDE.md PROGRESS-AWS.md
git commit -m "docs: PRD round-2 handoff - env vars, catalog scrape steps, decisions"
```

---

## Self-Review (completed at plan time)

- **Spec coverage:** archive/activate → Tasks 1, 2, 8; permission panel → Tasks 3, 8; conflict gating → Task 4 (+ conflict log already reviewer-gated in Cognito mode via `require_reviewer` on `GET /api/conflicts`); AI drafting → Tasks 5, 9; catalog scrape + weighting + registry → Tasks 6, 2, 1; resource catalog UI → Task 9; dark mode / back buttons / emblem-home → Task 10; DynamoDB/Cognito core-services promotion → dual-mode stores everywhere + Task 11; docs → Task 12. Recurring-questions hub, smart term matching, answer feedback, and revision comparison remain out of scope (Should/Could-have, not requested for this round).
- **Type consistency check:** `SourceUpsert`/`SourceRecord` shared by registry, catalog, uploads; `ResolutionFinding` reused by drafting; `Role` reused by gating; frontend `RegistrySource.sourceType` union matches backend `SourceType` literal.
- **Known judgment calls baked in (flag to Tim, easy to tweak later):** `EMPLOYEE_CONFLICT_GUIDANCE` copy (Task 4), `POLICY_LINK_KEYWORDS` crawl filter (Task 6), `ARCHIVED_EDITION_WEIGHT = 0.5` (Task 2), permission enforcement being identity-opt-in locally (Task 3).

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Protocol
from urllib.error import URLError

from fastapi import APIRouter, Depends, Header, HTTPException, status

from .auth import DEMO_ACCOUNTS, decode_and_verify_token, role_from_claims
from .dynamodb_client import get_dynamodb_client
from .config import get_settings
from .database import connection, initialize_database
from .models import PermissionRecord, PermissionUpdate, SourceType
from .stores import _ddb_decode, _ddb_encode, _timestamp


router = APIRouter(prefix="/api/permissions", tags=["permissions"])
ADMIN_EMAIL = "reviewer@campus.edu"
SOURCE_TYPES: tuple[SourceType, ...] = ("handbook", "cba", "policystat", "catalog", "uploads")


def _record(values: dict[str, object]) -> PermissionRecord:
    updated = values.get("updated_at")
    return PermissionRecord(
        user_email=str(values["user_email"]),
        source_type=str(values["source_type"]),  # type: ignore[arg-type]
        can_add=bool(int(values.get("can_add", 0))),
        can_edit=bool(int(values.get("can_edit", 0))),
        granted_by=str(values.get("granted_by", "")),
        updated_at=_timestamp(updated),
    )


class PermissionStore(Protocol):
    def list(self) -> list[PermissionRecord]: ...
    def get(self, user_email: str, source_type: SourceType) -> PermissionRecord | None: ...
    def grant(self, update: PermissionUpdate, granted_by: str) -> PermissionRecord: ...


class SQLitePermissionStore:
    def __init__(self) -> None:
        initialize_database()

    def list(self) -> list[PermissionRecord]:
        with connection() as database:
            rows = database.execute("SELECT * FROM permissions ORDER BY user_email, source_type").fetchall()
        return [_record(dict(row)) for row in rows]

    def get(self, user_email: str, source_type: SourceType) -> PermissionRecord | None:
        with connection() as database:
            row = database.execute(
                "SELECT * FROM permissions WHERE user_email=? AND source_type=?",
                (user_email.lower(), source_type),
            ).fetchone()
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
            client = get_dynamodb_client(settings)
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
        item = self.client.get_item(  # type: ignore[attr-defined]
            TableName=self.table,
            Key={"user_email": {"S": user_email.lower()}, "source_type": {"S": source_type}},
        ).get("Item")
        return _record(_ddb_decode(item)) if item else None

    def grant(self, update: PermissionUpdate, granted_by: str) -> PermissionRecord:
        now = datetime.now(timezone.utc).isoformat()
        values: dict[str, object] = {
            "user_email": update.user_email.lower(),
            "source_type": update.source_type,
            "can_add": int(update.can_add),
            "can_edit": int(update.can_edit),
            "granted_by": granted_by,
            "updated_at": now,
        }
        self.client.put_item(TableName=self.table, Item=_ddb_encode(values))  # type: ignore[attr-defined]
        return _record(values)


def permission_store() -> PermissionStore:
    return DynamoDBPermissionStore() if get_settings().permissions_aws else SQLitePermissionStore()


def seed_default_permissions() -> None:
    """Grant the demo reviewer full access to every source type."""
    store = permission_store()
    for source_type in SOURCE_TYPES:
        if store.get(ADMIN_EMAIL, source_type) is None:
            store.grant(
                PermissionUpdate(
                    user_email=ADMIN_EMAIL,
                    source_type=source_type,
                    can_add=True,
                    can_edit=True,
                ),
                granted_by="system-seed",
            )


def identity_email(authorization: str | None, x_user_email: str | None) -> str | None:
    """Prefer Cognito claims when configured; otherwise use the demo identity header."""
    settings = get_settings()
    if settings.cognito_aws and authorization and authorization.startswith("Bearer "):
        try:
            claims = decode_and_verify_token(authorization.removeprefix("Bearer ").strip(), settings)
            email = claims.get("email") or claims.get("username")
            return str(email).lower() if email else None
        except (ValueError, URLError, KeyError, json.JSONDecodeError):
            return None
    return x_user_email.lower().strip() if x_user_email else None


def _verified_groups(authorization: str | None) -> set[str]:
    settings = get_settings()
    if not settings.cognito_aws or not authorization or not authorization.startswith("Bearer "):
        return set()
    try:
        claims = decode_and_verify_token(authorization.removeprefix("Bearer ").strip(), settings)
    except (ValueError, URLError, KeyError, json.JSONDecodeError):
        return set()
    groups = claims.get("cognito:groups", [])
    if isinstance(groups, str):
        groups = [groups]
    return {str(group) for group in groups}


def is_source_admin(authorization: str | None, x_user_email: str | None) -> bool:
    """Admins manage grants; the seeded local reviewer is the demo administrator."""
    if get_settings().cognito_aws:
        return "admins" in _verified_groups(authorization)
    email = identity_email(authorization, x_user_email)
    return email == ADMIN_EMAIL


def require_source_admin(
    authorization: str | None = Header(default=None),
    x_user_email: str | None = Header(default=None),
) -> None:
    if not is_source_admin(authorization, x_user_email):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Source administrator role required")


def _local_reviewer(x_user_email: str | None, x_role: str | None) -> bool:
    if x_user_email:
        account = DEMO_ACCOUNTS.get(x_user_email.lower().strip())
        if account is not None:
            return account[1] == "reviewer"
    return x_role == "reviewer"


def require_can_edit_source(
    source_id: str,
    authorization: str | None = Header(default=None),
    x_user_email: str | None = Header(default=None),
    x_role: str | None = Header(default=None),
) -> None:
    """Allow admins, source owners, or reviewer/writers with a can-edit grant."""
    email = identity_email(authorization, x_user_email)
    # Preserve header-less local command/test compatibility. AWS mode is still
    # protected by the app-wide Cognito middleware.
    if email is None and not get_settings().cognito_aws:
        return
    if is_source_admin(authorization, x_user_email):
        return
    groups = _verified_groups(authorization)
    reviewer = role_from_claims({"cognito:groups": list(groups)}) == "reviewer" if get_settings().cognito_aws else _local_reviewer(x_user_email, x_role)
    if not reviewer or email is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Reviewer/writer role required")

    from .registry import registry_store

    source = registry_store().get(source_id)
    if source is None:
        return
    if source.owner and source.owner.lower() == email:
        return
    grant = permission_store().get(email, source.source_type)
    if grant is None or not grant.can_edit:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No permission to edit this source")


def authorize_source_write(
    source_id: str,
    authorization: str | None,
    x_user_email: str | None,
) -> None:
    """Require can-add for a new upload and can-edit when replacing one."""
    email = identity_email(authorization, x_user_email)
    if email is None:
        return
    if is_source_admin(authorization, x_user_email):
        return

    from .registry import registry_store

    existing = registry_store().get(source_id)
    source_type: SourceType = existing.source_type if existing is not None else "uploads"
    grant = permission_store().get(email, source_type)
    allowed = grant is not None and (grant.can_edit if existing is not None else grant.can_add)
    if not allowed:
        action = "edit" if existing is not None else "add"
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"No permission to {action} this source")


@router.get("", response_model=list[PermissionRecord])
def list_permissions(_: None = Depends(require_source_admin)) -> list[PermissionRecord]:
    return permission_store().list()


@router.put("", response_model=PermissionRecord)
def save_permission(
    payload: PermissionUpdate,
    authorization: str | None = Header(default=None),
    x_user_email: str | None = Header(default=None),
    _: None = Depends(require_source_admin),
) -> PermissionRecord:
    granted_by = identity_email(authorization, x_user_email) or "unknown"
    return permission_store().grant(payload, granted_by=granted_by)

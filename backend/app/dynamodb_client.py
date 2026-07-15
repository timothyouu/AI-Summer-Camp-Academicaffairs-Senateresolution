"""Lazy DynamoDB client helpers for optional application-memory stores.

No AWS request is made when this module is imported. Credentials are resolved by
boto3 only when a caller asks for a DynamoDB resource or client.
"""

from __future__ import annotations

from typing import Any

from .config import PersistenceSettings, PERSISTENCE_SETTINGS


def _boto3() -> Any:
    """Import boto3 lazily so SQLite mode remains usable without AWS setup."""
    try:
        import boto3
    except ImportError as error:  # pragma: no cover - exercised only when dependency is absent
        raise RuntimeError(
            "DynamoDB support requires boto3. Install backend requirements before "
            "setting APP_PERSISTENCE_BACKEND=dynamodb."
        ) from error
    return boto3


def create_dynamodb_session(settings: PersistenceSettings | None = None) -> Any:
    """Create a boto3 session using the standard credential provider chain."""
    active_settings = settings or PERSISTENCE_SETTINGS
    boto3 = _boto3()
    if active_settings.aws_profile is not None:
        return boto3.Session(
            profile_name=active_settings.aws_profile,
            region_name=active_settings.aws_region,
        )
    return boto3.Session(region_name=active_settings.aws_region)


def get_dynamodb_resource(settings: PersistenceSettings | None = None) -> Any:
    """Return a DynamoDB resource without performing table operations."""
    active_settings = settings or PERSISTENCE_SETTINGS
    kwargs: dict[str, str] = {}
    if active_settings.dynamodb_endpoint_url is not None:
        kwargs["endpoint_url"] = active_settings.dynamodb_endpoint_url
    return create_dynamodb_session(active_settings).resource("dynamodb", **kwargs)


def get_dynamodb_client(settings: PersistenceSettings | None = None) -> Any:
    """Return a DynamoDB low-level client without performing API operations."""
    active_settings = settings or PERSISTENCE_SETTINGS
    kwargs: dict[str, str] = {}
    if active_settings.dynamodb_endpoint_url is not None:
        kwargs["endpoint_url"] = active_settings.dynamodb_endpoint_url
    return create_dynamodb_session(active_settings).client("dynamodb", **kwargs)

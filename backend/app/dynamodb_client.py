"""Lazy DynamoDB resource helpers for the application-memory stores.

No AWS request is made when this module is imported, and boto3 itself is only
imported when a caller actually asks for a session — so SQLite mode keeps working
on a machine with neither boto3 nor credentials installed.

The feedback and recurring-question stores use the boto3 *resource* API rather
than the low-level client used elsewhere in stores.py, because their records hold
lists (``citations_used``, ``sample_citations``) that the low-level ``_ddb_encode``
helper cannot represent.
"""

from __future__ import annotations

from typing import Any

from .config import Settings, get_settings


def _boto3() -> Any:
    """Import boto3 lazily so SQLite mode remains usable without AWS setup."""
    try:
        import boto3
    except ImportError as error:  # pragma: no cover - exercised only when dependency is absent
        raise RuntimeError(
            "DynamoDB support requires boto3. Install backend requirements before "
            "setting any DDB_*_TABLE environment variable."
        ) from error
    return boto3


def create_dynamodb_session(settings: Settings | None = None) -> Any:
    """Create a boto3 session using the standard credential provider chain."""
    active = settings or get_settings()
    boto3 = _boto3()
    if active.aws_profile is not None:
        return boto3.Session(profile_name=active.aws_profile, region_name=active.aws_region)
    return boto3.Session(region_name=active.aws_region)


def get_dynamodb_resource(settings: Settings | None = None) -> Any:
    """Return a DynamoDB resource without performing table operations."""
    active = settings or get_settings()
    kwargs: dict[str, str] = {}
    if active.dynamodb_endpoint_url is not None:
        kwargs["endpoint_url"] = active.dynamodb_endpoint_url
    return create_dynamodb_session(active).resource("dynamodb", **kwargs)


def get_dynamodb_client(settings: Settings | None = None) -> Any:
    """Return a DynamoDB low-level client without performing API operations."""
    active = settings or get_settings()
    kwargs: dict[str, str] = {}
    if active.dynamodb_endpoint_url is not None:
        kwargs["endpoint_url"] = active.dynamodb_endpoint_url
    return create_dynamodb_session(active).client("dynamodb", **kwargs)

"""Pure helpers for parsing CDK deployment context values."""

from __future__ import annotations


def boolean_context(value: object, *, default: bool = False) -> bool:
    """Parse a CDK boolean context value without silently enabling a feature."""
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "on"}:
            return True
        if normalized in {"false", "0", "no", "off"}:
            return False
    raise ValueError(f"Expected a boolean CDK context value, got {value!r}")

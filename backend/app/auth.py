from __future__ import annotations

import base64
import hashlib
import json
import time
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen

from fastapi import APIRouter, Header, HTTPException, status

from .config import Settings, get_settings
from .models import LoginRequest, LoginResponse, Role


router = APIRouter(prefix="/api", tags=["authentication"])
DEMO_ACCOUNTS: dict[str, tuple[str, Role, str]] = {
    "reviewer@campus.edu": ("demo123", "reviewer", "Jennifer D."),
    "employee@campus.edu": ("demo123", "employee", "Alex B."),
}


def role_from_claims(claims: dict[str, Any]) -> Role:
    groups = claims.get("cognito:groups", [])
    if isinstance(groups, str):
        groups = [groups]
    return "reviewer" if "makers" in groups else "employee"


def _decode_segment(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _verify_rs256(signing_input: bytes, signature: bytes, key: dict[str, Any]) -> bool:
    modulus = int.from_bytes(_decode_segment(str(key["n"])), "big")
    exponent = int.from_bytes(_decode_segment(str(key["e"])), "big")
    encoded = pow(int.from_bytes(signature, "big"), exponent, modulus).to_bytes((modulus.bit_length() + 7) // 8, "big")
    digest_info = bytes.fromhex("3031300d060960864801650304020105000420") + hashlib.sha256(signing_input).digest()
    expected = b"\x00\x01" + b"\xff" * (len(encoded) - len(digest_info) - 3) + b"\x00" + digest_info
    return encoded == expected


def decode_and_verify_token(token: str, settings: Settings | None = None) -> dict[str, Any]:
    settings = settings or get_settings()
    if not settings.cognito_aws:
        raise ValueError("Cognito is not configured")
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("Malformed JWT")
    header = json.loads(_decode_segment(parts[0]))
    claims: dict[str, Any] = json.loads(_decode_segment(parts[1]))
    if header.get("alg") != "RS256":
        raise ValueError("Unsupported JWT algorithm")
    region = settings.aws_region or str(settings.cognito_user_pool_id).split("_", 1)[0]
    issuer = f"https://cognito-idp.{region}.amazonaws.com/{settings.cognito_user_pool_id}"
    with urlopen(f"{issuer}/.well-known/jwks.json", timeout=5.0) as response:  # noqa: S310 - fixed Cognito issuer
        jwks = json.loads(response.read())
    key = next((item for item in jwks.get("keys", []) if item.get("kid") == header.get("kid")), None)
    if key is None or not _verify_rs256(f"{parts[0]}.{parts[1]}".encode(), _decode_segment(parts[2]), key):
        raise ValueError("Invalid JWT signature")
    audience = claims.get("client_id", claims.get("aud"))
    if claims.get("iss") != issuer or audience != settings.cognito_client_id or int(claims.get("exp", 0)) <= int(time.time()):
        raise ValueError("Invalid JWT claims")
    return claims


def _verified_claims_from_authorization(authorization: str | None, settings: Settings) -> dict[str, Any]:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Bearer token required")
    try:
        return decode_and_verify_token(authorization.removeprefix("Bearer ").strip(), settings)
    except (ValueError, URLError, KeyError, json.JSONDecodeError) as error:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Cognito token") from error


def verify_request_authorization(authorization: str | None, settings: Settings) -> None:
    """App-wide JWT check used by the auth middleware in Cognito mode."""
    _verified_claims_from_authorization(authorization, settings)


def require_reviewer(authorization: str | None = Header(default=None)) -> None:
    """Require a verified Cognito maker for protected mutations in AWS mode."""
    settings = get_settings()
    if settings.cognito_aws and role_from_claims(_verified_claims_from_authorization(authorization, settings)) != "reviewer":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Reviewer role required")


def require_authenticated(authorization: str | None = Header(default=None)) -> None:
    """Require any verified Cognito user in AWS mode; a no-op locally.

    The two long-running agent endpoints (POST /api/chat, POST
    /api/check-resolution) are served in AWS mode through a Lambda Function
    URL (auth_type=NONE) so they can run past API Gateway's 29s integration
    cap. Because the Function URL bypasses the gateway's Cognito JWT
    authorizer, the token is validated here in-app to keep the same
    authentication guarantee. Locally Cognito is unconfigured, so this stays
    a no-op and the demo endpoints remain open exactly as before.
    """
    settings = get_settings()
    if settings.cognito_aws:
        _verified_claims_from_authorization(authorization, settings)


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, authorization: str | None = Header(default=None)) -> LoginResponse:
    settings = get_settings()
    if settings.cognito_aws:
        claims = _verified_claims_from_authorization(authorization, settings)
        name = str(claims.get("name") or claims.get("email") or claims.get("username") or "Campus user")
        return LoginResponse(role=role_from_claims(claims), name=name)
    account = DEMO_ACCOUNTS.get(payload.email.lower().strip())
    if account is None or account[0] != payload.password:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid demo credentials")
    return LoginResponse(role=account[1], name=account[2])

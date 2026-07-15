"""Auth guarantees for the two long-running agent endpoints.

In AWS mode POST /api/chat and POST /api/check-resolution are served through a
Lambda Function URL (auth_type=NONE) to escape API Gateway's ~29s cap, so the
Cognito JWT is validated in-app instead of by the gateway authorizer. These
tests prove that guard holds in AWS mode and stays a no-op locally (so the
frozen local tests keep passing byte-for-byte).
"""
from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from backend.app import auth


def _enable_cognito(monkeypatch: Any) -> None:
    monkeypatch.setenv("COGNITO_USER_POOL_ID", "us-west-2_pool")
    monkeypatch.setenv("COGNITO_CLIENT_ID", "client123")


def test_chat_is_open_locally_without_a_token(client: TestClient) -> None:
    response = client.post("/api/chat", json={"question": "Does service credit count toward the tenure clock?"})
    assert response.status_code == 200
    assert response.json()["citations"]


def test_chat_requires_a_token_in_aws_mode(client: TestClient, monkeypatch: Any) -> None:
    _enable_cognito(monkeypatch)
    response = client.post("/api/chat", json={"question": "Does service credit count toward the tenure clock?"})
    assert response.status_code == 401


def test_chat_accepts_a_verified_token_in_aws_mode(client: TestClient, monkeypatch: Any) -> None:
    _enable_cognito(monkeypatch)
    monkeypatch.setattr(auth, "decode_and_verify_token", lambda *_a, **_k: {"cognito:groups": ["employees"], "email": "e@campus.edu"})
    response = client.post(
        "/api/chat",
        json={"question": "Does service credit count toward the tenure clock?"},
        headers={"Authorization": "Bearer valid.jwt.token"},
    )
    assert response.status_code == 200
    assert response.json()["citations"]


def test_check_resolution_still_requires_reviewer_in_aws_mode(client: TestClient, monkeypatch: Any) -> None:
    _enable_cognito(monkeypatch)
    monkeypatch.setattr(auth, "decode_and_verify_token", lambda *_a, **_k: {"cognito:groups": ["employees"]})
    forbidden = client.post(
        "/api/check-resolution",
        json={"text": "The WPAF must use a three-inch binder."},
        headers={"Authorization": "Bearer employee.jwt.token"},
    )
    assert forbidden.status_code == 403

    monkeypatch.setattr(auth, "decode_and_verify_token", lambda *_a, **_k: {"cognito:groups": ["makers"]})
    allowed = client.post(
        "/api/check-resolution",
        json={"text": "The WPAF must use a three-inch binder."},
        headers={"Authorization": "Bearer maker.jwt.token"},
    )
    assert allowed.status_code == 200
    assert allowed.json()["conflicts"]


def test_require_authenticated_is_a_noop_locally(monkeypatch: Any) -> None:
    for name in ("COGNITO_USER_POOL_ID", "COGNITO_CLIENT_ID"):
        monkeypatch.delenv(name, raising=False)
    assert auth.require_authenticated(authorization=None) is None


def test_cognito_middleware_guards_all_api_routes(client: TestClient, monkeypatch: Any) -> None:
    monkeypatch.setenv("COGNITO_USER_POOL_ID", "us-west-2_pool")
    monkeypatch.setenv("COGNITO_CLIENT_ID", "client")

    assert client.get("/api/conflicts").status_code == 401
    assert client.get("/api/topics").status_code == 401
    assert client.get("/api/uploads/some-id").status_code == 401
    assert client.get("/api/health").status_code == 200

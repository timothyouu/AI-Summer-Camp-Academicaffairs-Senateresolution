from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from types import ModuleType
from typing import Any


PROVIDER_PATH = Path(__file__).parents[1] / "lambda_src" / "vector_index_provider" / "index.py"


def _load_provider() -> ModuleType:
    spec = importlib.util.spec_from_file_location("vector_index_provider", PROVIDER_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Response:
    status = 200

    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    @staticmethod
    def read() -> bytes:
        return b"{}"


def _capture_request(monkeypatch: Any, method: str, body: dict[str, Any] | None) -> dict[str, Any]:
    provider = _load_provider()
    captured: dict[str, Any] = {}

    class _Session:
        @staticmethod
        def get_credentials() -> object:
            return object()

    class _Signer:
        def __init__(self, _credentials: object, _service: str, _region: str) -> None:
            pass

        @staticmethod
        def add_auth(request: Any) -> None:
            captured["signed_headers"] = dict(request.headers.items())

    def _urlopen(request: Any, timeout: int) -> _Response:
        assert timeout == 25
        captured["http_request"] = request
        return _Response()

    monkeypatch.setattr(provider.boto3, "Session", _Session)
    monkeypatch.setattr(provider, "SigV4Auth", _Signer)
    monkeypatch.setattr(provider.urllib.request, "urlopen", _urlopen)

    status, payload = provider._signed_request(
        method,
        "https://example.us-west-2.aoss.amazonaws.com/policy-index",
        "us-west-2",
        body,
    )

    assert status == 200
    assert payload == "{}"
    return captured


def test_signed_put_includes_nonempty_payload_hash(monkeypatch: Any) -> None:
    body = {"settings": {"index.knn": True}}
    captured = _capture_request(monkeypatch, "PUT", body)
    expected = hashlib.sha256(json.dumps(body).encode("utf-8")).hexdigest()

    assert captured["signed_headers"]["X-Amz-Content-Sha256"] == expected
    headers = {name.lower(): value for name, value in captured["http_request"].header_items()}
    assert headers["x-amz-content-sha256"] == expected


def test_signed_delete_includes_empty_payload_hash(monkeypatch: Any) -> None:
    captured = _capture_request(monkeypatch, "DELETE", None)
    expected = hashlib.sha256(b"").hexdigest()

    assert captured["signed_headers"]["X-Amz-Content-Sha256"] == expected
    headers = {name.lower(): value for name, value in captured["http_request"].header_items()}
    assert headers["x-amz-content-sha256"] == expected
    assert captured["http_request"].data is None

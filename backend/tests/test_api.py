from __future__ import annotations

from fastapi.testclient import TestClient


def test_demo_logins_and_reject(client: TestClient) -> None:
    reviewer = client.post("/api/login", json={"email": "reviewer@campus.edu", "password": "demo123"})
    employee = client.post("/api/login", json={"email": "employee@campus.edu", "password": "demo123"})
    rejected = client.post("/api/login", json={"email": "reviewer@campus.edu", "password": "wrong"})
    assert reviewer.status_code == 200 and reviewer.json()["role"] == "reviewer"
    assert employee.status_code == 200 and employee.json()["role"] == "employee"
    assert rejected.status_code == 401


def test_chat_response_is_grounded_and_service_credit_is_not_false_conflict(client: TestClient) -> None:
    response = client.post("/api/chat", json={"question": "Does service credit count toward the tenure clock?"})
    payload = response.json()
    assert response.status_code == 200
    assert payload["answer"]
    assert len(payload["citations"]) == 2
    assert payload["conflict"] is None


def test_resolution_response_shape_and_conflict_logging(client: TestClient) -> None:
    response = client.post("/api/check-resolution", json={"text": "The WPAF must use a three-inch binder."})
    payload = response.json()
    assert response.status_code == 200
    assert payload["conflicts"]
    conflicts = client.get("/api/conflicts")
    assert conflicts.status_code == 200
    assert any(item["topic"] == "WPAF evidence format" for item in conflicts.json())


def test_topics_health_and_upload(client: TestClient) -> None:
    health = client.get("/api/health")
    topics = client.get("/api/topics")
    upload = client.post("/api/upload", files={"file": ("new-guidance.txt", b"Accessible instructional technology requires an equally effective alternative.", "text/plain")})
    assert health.status_code == 200 and health.json()["provider"] == "local-hash-embedding"
    assert topics.status_code == 200 and topics.json()
    assert upload.status_code == 201 and upload.json()["chunks_added"] == 1


def test_upload_rejects_unsupported_type(client: TestClient) -> None:
    response = client.post("/api/upload", files={"file": ("notes.docx", b"not-a-docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")})
    assert response.status_code == 415

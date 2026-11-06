from __future__ import annotations

import io
import time
import zipfile
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from normocontrol.api.app import create_app
from normocontrol.api.jobs import QueueFullError
from normocontrol.config.settings import Settings
from normocontrol.dataset.generate import generate_sample
from normocontrol.profiles.loader import ProfileRegistry

DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(settings)) as test_client:
        yield test_client


@pytest.fixture
def document(registry: ProfileRegistry) -> bytes:
    data, _ = generate_sample(registry.get("kru-mi-049-2026"), seed=8, mutations=3)
    return data


def upload(client: TestClient, data: bytes, **form: Any) -> Any:
    fields = {"profile_id": "kru-mi-049-2026", **form}
    return client.post("/api/checks", files={"file": ("Курсовая.docx", data, DOCX)}, data=fields)


def wait(client: TestClient, check_id: str) -> dict[str, Any]:
    for _ in range(200):
        body: dict[str, Any] = client.get(f"/api/checks/{check_id}").json()
        if body["status"] in {"done", "failed"}:
            return body
        time.sleep(0.02)
    raise AssertionError("проверка не завершилась")


def test_full_check_flow(client: TestClient, document: bytes) -> None:
    created = upload(client, document, annotate="true")
    assert created.status_code == 202
    body = created.json()
    assert body["status"] == "queued"
    assert body["filename"] == "Курсовая.docx"
    assert len(body["id"]) >= 20
    assert created.headers["cache-control"] == "no-store"

    result = wait(client, body["id"])
    assert result["status"] == "done", result["error"]
    states = {step["id"]: step["state"] for step in result["steps"]}
    assert states == {
        "parse": "done",
        "rules": "done",
        "structure": "done",
        "llm": "skipped",
        "report": "done",
    }
    report = result["report"]
    assert report["profile"]["id"] == "kru-mi-049-2026"
    assert 0 <= report["score"] <= 100
    assert report["issues"]

    annotated = client.get(result["annotated_url"])
    assert annotated.status_code == 200
    assert annotated.headers["content-type"] == DOCX
    assert "filename*=UTF-8''" in annotated.headers["content-disposition"]
    with zipfile.ZipFile(io.BytesIO(annotated.content)) as archive:
        assert "word/comments.xml" in archive.namelist()

    assert client.delete(f"/api/checks/{body['id']}").status_code == 204
    gone = client.get(f"/api/checks/{body['id']}")
    assert gone.status_code == 404
    assert gone.json()["error"]["code"] == "check_not_found"


def test_without_annotation_no_download(client: TestClient, document: bytes) -> None:
    result = wait(client, upload(client, document).json()["id"])
    assert result["annotated_url"] is None
    missing = client.get(f"/api/checks/{result['id']}/annotated.docx")
    assert missing.status_code == 404


@pytest.mark.parametrize(
    ("filename", "content", "media", "status", "code"),
    [
        ("work.pdf", b"%PDF", "application/pdf", 415, "unsupported_media_type"),
        ("work.docx", b"%PDF", "image/png", 415, "unsupported_media_type"),
        ("work.docx", b"not a zip", "application/octet-stream", 422, "invalid_document"),
    ],
)
def test_upload_validation(
    client: TestClient, filename: str, content: bytes, media: str, status: int, code: str
) -> None:
    response = client.post(
        "/api/checks",
        files={"file": (filename, content, media)},
        data={"profile_id": "kru-mi-049-2026"},
    )
    assert response.status_code == status
    assert response.json()["error"]["code"] == code


def test_unknown_profile(client: TestClient, document: bytes) -> None:
    response = upload(client, document, profile_id="unknown")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "profile_not_found"


def test_missing_file(client: TestClient) -> None:
    response = client.post("/api/checks", data={"profile_id": "kru-mi-049-2026"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_file_too_large(settings: Settings, document: bytes) -> None:
    small = settings.model_copy(
        update={"api": settings.api.model_copy(update={"max_upload_mb": 0.01})}
    )
    with TestClient(create_app(small)) as client:
        response = upload(client, document)
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "file_too_large"


def test_queue_full(client: TestClient, document: bytes) -> None:
    state = client.app.state.normocontrol  # type: ignore[attr-defined]

    async def full(_: str) -> None:
        raise QueueFullError

    state.queue.enqueue = full
    response = upload(client, document)
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "queue_full"


def test_profiles(client: TestClient) -> None:
    profiles = client.get("/api/profiles").json()
    ids = {p["id"] for p in profiles}
    assert {"kru-mi-049-2026", "gost-7.32-2017", "kz-order-236-2023"} <= ids
    kru = next(p for p in profiles if p["id"] == "kru-mi-049-2026")
    assert kru["status"] == "active"
    assert kru["rag_sources"] == [{"source": "МИ 049-2026", "priority": 1}]
    detail = client.get("/api/profiles/kz-order-236-2023").json()
    assert detail["extends"] == "kz-rules-236-2023"
    assert detail["body_text"]["font_family"] == ["Times New Roman", "Arial"]
    assert client.get("/api/profiles/nope").json()["error"]["code"] == "profile_not_found"


def test_health_and_metrics(client: TestClient) -> None:
    assert client.get("/healthz").json()["status"] == "ok"
    ready = client.get("/readyz").json()
    assert ready["status"] == "ok"
    assert ready["components"]["queue"] == "ok"
    client.get("/api/checks/secret-check-id-123")
    client.get("/no/such/path")
    metrics = client.get("/metrics").text
    assert "normocontrol_http_request_duration_seconds" in metrics
    # в метках — шаблон маршрута, а не id проверки (иначе неограниченная кардинальность)
    assert 'route="/api/checks/{check_id}"' in metrics
    assert "secret-check-id-123" not in metrics
    assert 'route="unmatched"' in metrics


def test_security_headers_and_request_id(client: TestClient) -> None:
    response = client.get("/healthz", headers={"X-Request-ID": "abc"})
    assert response.headers["x-request-id"] == "abc"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"


def test_unknown_check_and_long_id(client: TestClient) -> None:
    assert client.get("/api/checks/doesnotexist").status_code == 404
    assert client.get("/api/checks/" + "x" * 100).status_code == 404


def test_openapi_documented(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    assert "/api/checks" in schema["paths"]
    assert "/api/checks/{check_id}/annotated.docx" in schema["paths"]

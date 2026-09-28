"""API tests. The real Gemini API is never called - the AI layer is mocked."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.ai_core.gemini_generator import (
    GeminiConfigurationError,
    GeminiDocumentGenerator,
    GeminiEmptyResponseError,
    GeminiServiceError,
)
from backend.main import app
from backend.routes import _build_generator, get_generator

VALID_PAYLOAD = {
    "document_type": "Freelance Work Contract",
    "parties": "Jane Doe (Service Provider), TechNova Inc. (Client)",
    "terms": "Payment within 7 days of invoice; Confidentiality must be maintained",
    "dates": "April 15, 2025",
}


class FakeGenerator:
    """Stand-in for GeminiDocumentGenerator (no network access)."""

    def __init__(self, result: str = "FREELANCE WORK CONTRACT\n\n1. PARTIES\n\nJane Doe.", error=None):
        self.result = result
        self.error = error
        self.calls: list[tuple] = []

    def generate_document(self, document_type, parties, terms, dates):
        self.calls.append((document_type, parties, terms, dates))
        if self.error:
            raise self.error
        return self.result


@pytest.fixture()
def client():
    """TestClient whose dependency overrides are always cleaned up."""
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def use_generator(fake) -> None:
    app.dependency_overrides[get_generator] = lambda: fake


# --------------------------------------------------------------------------
# Status endpoints
# --------------------------------------------------------------------------
def test_root(client):
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"application": "LegalEase", "status": "running", "api_docs": "/docs"}


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_docs_are_available(client):
    assert client.get("/docs").status_code == 200
    assert client.get("/redoc").status_code == 200
    assert "/generate" in client.get("/openapi.json").json()["paths"]


def test_cors_allows_streamlit_origin(client):
    response = client.options(
        "/generate",
        headers={"Origin": "http://localhost:8501", "Access-Control-Request-Method": "POST"},
    )
    assert response.headers.get("access-control-allow-origin") == "http://localhost:8501"


# --------------------------------------------------------------------------
# POST /generate - success
# --------------------------------------------------------------------------
def test_generate_success(client):
    fake = FakeGenerator()
    use_generator(fake)
    response = client.post("/generate", json=VALID_PAYLOAD)
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["document_type"] == "Freelance Work Contract"
    assert "PARTIES" in body["content"]
    assert fake.calls == [tuple(VALID_PAYLOAD[k] for k in ("document_type", "parties", "terms", "dates"))]


def test_generate_strips_whitespace(client):
    fake = FakeGenerator()
    use_generator(fake)
    payload = {key: f"  {value}  " for key, value in VALID_PAYLOAD.items()}
    assert client.post("/generate", json=payload).status_code == 200
    assert fake.calls[0][0] == "Freelance Work Contract"


# --------------------------------------------------------------------------
# POST /generate - validation
# --------------------------------------------------------------------------
@pytest.mark.parametrize("field", ["document_type", "parties", "terms", "dates"])
def test_generate_rejects_empty_and_whitespace(client, field):
    use_generator(FakeGenerator())
    for bad in ("", "   ", "\n\t"):
        response = client.post("/generate", json={**VALID_PAYLOAD, field: bad})
        assert response.status_code == 422, (field, bad)


@pytest.mark.parametrize("field", ["document_type", "parties", "terms", "dates"])
def test_generate_rejects_missing_field(client, field):
    use_generator(FakeGenerator())
    payload = {k: v for k, v in VALID_PAYLOAD.items() if k != field}
    assert client.post("/generate", json=payload).status_code == 422


@pytest.mark.parametrize(
    "field,limit", [("document_type", 100), ("parties", 2000), ("terms", 6000), ("dates", 100)]
)
def test_generate_rejects_too_long(client, field, limit):
    use_generator(FakeGenerator())
    response = client.post("/generate", json={**VALID_PAYLOAD, field: "x" * (limit + 1)})
    assert response.status_code == 422


def test_generate_rejects_wrong_types_and_bad_json(client):
    use_generator(FakeGenerator())
    assert client.post("/generate", json={**VALID_PAYLOAD, "terms": 123}).status_code == 422
    assert client.post("/generate", json={**VALID_PAYLOAD, "dates": None}).status_code == 422
    bad = client.post("/generate", content="{not json", headers={"Content-Type": "application/json"})
    assert bad.status_code == 422


# --------------------------------------------------------------------------
# POST /generate - error mapping
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "error,expected",
    [
        (GeminiConfigurationError("GEMINI_API_KEY is missing."), 503),
        (GeminiEmptyResponseError("empty"), 502),
        (GeminiServiceError("quota", 429), 429),
        (GeminiServiceError("bad gateway", 500), 502),
        (RuntimeError("boom secret-value"), 500),
    ],
)
def test_generate_error_mapping(client, error, expected):
    use_generator(FakeGenerator(error=error))
    response = client.post("/generate", json=VALID_PAYLOAD)
    assert response.status_code == expected
    assert "secret-value" not in response.text  # internals never leak


def test_generate_blank_ai_output_is_error(client):
    use_generator(FakeGenerator(result="   "))
    assert client.post("/generate", json=VALID_PAYLOAD).status_code == 502


def test_generate_without_api_key_returns_503(client, monkeypatch):
    """With no override and no key the API answers with a clear 503."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    _build_generator.cache_clear()
    response = client.post("/generate", json=VALID_PAYLOAD)
    _build_generator.cache_clear()
    assert response.status_code == 503
    assert "GEMINI_API_KEY" in response.json()["detail"]


# --------------------------------------------------------------------------
# GeminiDocumentGenerator with a fake client (still no network)
# --------------------------------------------------------------------------
class _FakeResponse:
    def __init__(self, text):
        self.text = text


class _FakeModels:
    def __init__(self, text=None, error=None):
        self.text, self.error, self.kwargs = text, error, None

    def generate_content(self, **kwargs):
        self.kwargs = kwargs
        if self.error:
            raise self.error
        return _FakeResponse(self.text)


class _FakeClient:
    def __init__(self, text=None, error=None):
        self.models = _FakeModels(text, error)


def test_generator_missing_key_raises(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(GeminiConfigurationError):
        GeminiDocumentGenerator()


def test_generator_success_cleans_text_and_adds_notice():
    client = _FakeClient(text="**SERVICE AGREEMENT**\n\n1. PARTIES\n\n* Jane Doe")
    generator = GeminiDocumentGenerator(model="test-model", client=client)
    text = generator.generate_document("Service Agreement", "Jane", "Pay on time", "Today")
    assert "**" not in text
    assert text.rstrip().endswith("before use.")
    assert "REVIEW NOTICE" in text
    assert client.models.kwargs["model"] == "test-model"
    prompt = client.models.kwargs["contents"]
    assert "Jane" in prompt and "Pay on time" in prompt


def test_generator_empty_response_raises():
    generator = GeminiDocumentGenerator(client=_FakeClient(text=None))
    with pytest.raises(GeminiEmptyResponseError):
        generator.generate_document("NDA", "A and B", "Keep secrets", "Today")


def test_generator_wraps_unexpected_errors_without_leaking():
    generator = GeminiDocumentGenerator(client=_FakeClient(error=TimeoutError("key=SECRET123")))
    with pytest.raises(GeminiServiceError) as info:
        generator.generate_document("NDA", "A and B", "Keep secrets", "Today")
    assert "SECRET123" not in str(info.value)

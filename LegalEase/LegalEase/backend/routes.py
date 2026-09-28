"""API routes for LegalEase (document generation)."""

from __future__ import annotations

import logging
from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException, status

from backend.ai_core.gemini_generator import (
    GeminiConfigurationError,
    GeminiDocumentGenerator,
    GeminiEmptyResponseError,
    GeminiServiceError,
)
from backend.models import DocumentRequest, DocumentResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Document generation"])


@lru_cache(maxsize=1)
def _build_generator() -> GeminiDocumentGenerator:
    """Create (and cache) the generator. Failures are not cached."""
    return GeminiDocumentGenerator()


def get_generator() -> GeminiDocumentGenerator:
    """FastAPI dependency returning the Gemini generator.

    Tests replace this with a fake via ``app.dependency_overrides``.
    """
    try:
        return _build_generator()
    except GeminiConfigurationError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from None


@router.post(
    "/generate",
    response_model=DocumentResponse,
    summary="Generate an AI-assisted legal document draft",
    description=(
        "Sends the document type, parties, terms and effective date to Google Gemini and "
        "returns a plain-text legal document draft. The result is an **AI-assisted draft** "
        "and must be reviewed by a qualified legal professional before real-world use."
    ),
    responses={
        422: {"description": "Validation error (empty, too long or malformed input)."},
        429: {"description": "Gemini rate limit or quota exceeded."},
        502: {"description": "Gemini API error or empty response."},
        503: {"description": "Backend is not configured (e.g. GEMINI_API_KEY missing)."},
        500: {"description": "Unexpected server error."},
    },
)
def generate_legal_document(
    request: DocumentRequest,
    generator: GeminiDocumentGenerator = Depends(get_generator),
) -> DocumentResponse:
    """Generate a legal document draft from the validated request."""
    try:
        content = generator.generate_document(
            request.document_type, request.parties, request.terms, request.dates
        )
    except GeminiConfigurationError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from None
    except GeminiEmptyResponseError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from None
    except GeminiServiceError as exc:
        code = (
            status.HTTP_429_TOO_MANY_REQUESTS
            if exc.http_status == 429
            else status.HTTP_502_BAD_GATEWAY
        )
        raise HTTPException(code, detail=str(exc)) from None
    except Exception as exc:  # noqa: BLE001 - never leak internals to the client
        logger.error("Unexpected error during generation: %s", type(exc).__name__)
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while generating the document.",
        ) from None

    if not content or not content.strip():
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, detail="The AI service returned an empty document."
        )

    return DocumentResponse(
        success=True, document_type=request.document_type, content=content
    )

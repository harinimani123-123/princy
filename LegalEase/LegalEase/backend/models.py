"""Pydantic request/response models for the LegalEase API."""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Input limits (shared with the Streamlit frontend).
MAX_DOCUMENT_TYPE_LENGTH = 100
MAX_PARTIES_LENGTH = 2000
MAX_TERMS_LENGTH = 6000
MAX_DATES_LENGTH = 100

# Control characters except tab/newline are never valid in user text.
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class DocumentRequest(BaseModel):
    """Input required to generate a legal document draft."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "document_type": "Freelance Work Contract",
                "parties": "Jane Doe (Service Provider), TechNova Inc. (Client)",
                "terms": (
                    "Work must be delivered by May 15, 2025; Payment will be made within "
                    "7 days of invoice; The client retains intellectual property rights; "
                    "Confidentiality must be maintained at all times"
                ),
                "dates": "April 15, 2025",
            }
        }
    )

    document_type: str = Field(
        ..., min_length=1, max_length=MAX_DOCUMENT_TYPE_LENGTH,
        description="Type of legal document, e.g. 'Lease Agreement'.",
    )
    parties: str = Field(
        ..., min_length=1, max_length=MAX_PARTIES_LENGTH,
        description="Names and roles of the parties involved.",
    )
    terms: str = Field(
        ..., min_length=1, max_length=MAX_TERMS_LENGTH,
        description="Terms and conditions, separated by semicolons or new lines.",
    )
    dates: str = Field(
        ..., min_length=1, max_length=MAX_DATES_LENGTH,
        description="Effective date of the document.",
    )

    @field_validator("document_type", "parties", "terms", "dates", mode="before")
    @classmethod
    def _clean_and_require_text(cls, value):
        """Strip whitespace/control characters and reject blank input."""
        if not isinstance(value, str):
            raise ValueError("must be a string")
        cleaned = _CONTROL_CHARS.sub("", value).strip()
        if not cleaned:
            raise ValueError("must not be empty or whitespace only")
        return cleaned


class DocumentResponse(BaseModel):
    """Generated document returned by ``POST /generate``."""

    success: bool = Field(..., description="True when the document was generated.")
    document_type: str = Field(..., description="Echo of the requested document type.")
    content: str = Field(..., description="The generated document text (plain text).")

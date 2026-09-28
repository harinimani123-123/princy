"""LegalEase FastAPI application entry point.

Run from the project root:
    uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
"""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.routes import router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

DESCRIPTION = """
**LegalEase** generates AI-assisted legal document drafts with Google Gemini.

> Generated documents are **AI-assisted drafts** and must be reviewed by a qualified
> legal professional before real-world use.
"""

app = FastAPI(
    title="LegalEase - AI Legal Document Generator",
    description=DESCRIPTION,
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Allow the local Streamlit frontend to call the API from the browser.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8501", "http://127.0.0.1:8501"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/", tags=["Status"], summary="Application status")
def home() -> dict:
    """Return basic application information."""
    return {"application": "LegalEase", "status": "running", "api_docs": "/docs"}


@app.get("/health", tags=["Status"], summary="Health check")
def health() -> dict:
    """Liveness probe used by the frontend and monitoring tools."""
    return {"status": "healthy"}


if __name__ == "__main__":  # pragma: no cover
    import uvicorn

    uvicorn.run("backend.main:app", host="127.0.0.1", port=8000, reload=True)

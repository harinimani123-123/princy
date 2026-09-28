"""Tests for text utilities and the TXT / DOCX / PDF formatters."""

from __future__ import annotations

from io import BytesIO

import pytest
from docx import Document

from backend.utils.document_formatter import (
    format_docx,
    format_pdf,
    format_txt,
    parse_document,
)
from backend.utils.text_utils import (
    REVIEW_NOTICE_TEXT,
    clean_whitespace,
    count_missing_information,
    ensure_review_notice,
    is_heading,
    normalize_dashes,
    normalize_quotes,
    remove_excessive_blank_lines,
    sanitize_text,
    split_terms,
    strip_markdown,
)

SAMPLE = (
    "FREELANCE WORK CONTRACT\n\n"
    "Effective Date: April 15, 2025\n\n"
    "1. PARTIES\n\n"
    "Jane Doe (Service Provider) and TechNova Inc. (Client).\n\n"
    "2. PAYMENT\n\n"
    "(a) Payment is due within 7 days of invoice.\n"
    "- Late payments: [MISSING INFORMATION]\n\n"
    "SIGNATURES\n\n"
    "______________________\n"
    "Jane Doe\n\n"
    "REVIEW NOTICE\n\n" + REVIEW_NOTICE_TEXT
)


# --------------------------------------------------------------------------
# text_utils
# --------------------------------------------------------------------------
def test_clean_whitespace():
    assert clean_whitespace("a   b\t c \r\n  d  \r e\u00a0f\u200b") == "a b c\nd\ne f"


def test_normalize_quotes():
    assert normalize_quotes("\u201cHello\u201d it\u2019s \u2018ok\u2019") == "\"Hello\" it's 'ok'"


def test_normalize_dashes():
    assert normalize_dashes("10\u201320") == "10-20"
    assert normalize_dashes("yes\u2014no") == "yes - no"


def test_remove_excessive_blank_lines():
    assert remove_excessive_blank_lines("a\n\n\n\n\nb") == "a\n\nb"
    assert remove_excessive_blank_lines("a\n\nb") == "a\n\nb"
    assert remove_excessive_blank_lines("a\n\n\nb", max_blank_lines=0) == "a\nb"


def test_strip_markdown_keeps_signature_lines():
    text = "## Title\n**bold** and *italic*\n* item\n---\n__________"
    cleaned = strip_markdown(text)
    assert "TITLE" in cleaned
    assert "**" not in cleaned and "*italic*" not in cleaned
    assert "- item" in cleaned
    assert "__________" in cleaned


def test_sanitize_text_pipeline():
    raw = "\u201cQuoted\u201d \u2014 text   \r\n\r\n\r\n\r\n**Bold**  "
    assert sanitize_text(raw) == '"Quoted" - text\n\nBold'
    assert sanitize_text(None) == ""
    assert sanitize_text("") == ""


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("A; B; C", ["A", "B", "C"]),
        ("A;;  ; B;", ["A", "B"]),
        ("First\nSecond; Third", ["First", "Second", "Third"]),
        ("- one; \u2022 two", ["one", "two"]),
        ("", []),
        (None, []),
        ("   ;  ; ", []),
    ],
)
def test_split_terms(raw, expected):
    assert split_terms(raw) == expected


def test_is_heading():
    assert is_heading("1. PAYMENT TERMS")
    assert is_heading("REVIEW NOTICE")
    assert is_heading("2. Payment Terms")
    assert not is_heading("The Client shall pay within 7 days.")
    assert not is_heading("[MISSING INFORMATION]")
    assert not is_heading("")


def test_ensure_review_notice_adds_and_replaces():
    added = ensure_review_notice("SOME DOCUMENT\n\nBody text.")
    assert added.endswith(REVIEW_NOTICE_TEXT)
    replaced = ensure_review_notice("Body\n\nREVIEW NOTICE\n\nSomething the model invented.")
    assert replaced.count("REVIEW NOTICE") == 1
    assert "invented" not in replaced
    assert replaced.endswith(REVIEW_NOTICE_TEXT)


def test_count_missing_information():
    assert count_missing_information("a [MISSING INFORMATION] b [MISSING INFORMATION]") == 2


# --------------------------------------------------------------------------
# TXT
# --------------------------------------------------------------------------
def test_format_txt_returns_utf8_bytes():
    data = format_txt("Rent: \u20b9 25,000 \u2014 monthly")
    assert isinstance(data, bytes)
    assert data.decode("utf-8").strip() == "Rent: \u20b9 25,000 \u2014 monthly"


def test_format_txt_rejects_empty():
    with pytest.raises(ValueError):
        format_txt("   ")


# --------------------------------------------------------------------------
# parse_document
# --------------------------------------------------------------------------
def test_parse_document_title_and_blocks():
    title, blocks = parse_document(SAMPLE, "Ignored Type")
    assert title == "FREELANCE WORK CONTRACT"
    kinds = [b.kind for b in blocks if b.kind != "blank"]
    assert "heading" in kinds and "bullet" in kinds and "subclause" in kinds and "body" in kinds


def test_parse_document_falls_back_to_doc_type():
    title, _ = parse_document("This agreement is made today.", "Lease Agreement")
    assert title == "Lease Agreement"


# --------------------------------------------------------------------------
# DOCX
# --------------------------------------------------------------------------
def test_format_docx_basic():
    data = format_docx(SAMPLE, "Freelance Work Contract")
    assert data[:2] == b"PK"  # a .docx is a zip archive
    doc = Document(BytesIO(data))
    text = "\n".join(p.text for p in doc.paragraphs)
    assert "FREELANCE WORK CONTRACT" in text
    assert "Payment is due within 7 days" in text
    assert REVIEW_NOTICE_TEXT in text
    footer_text = "".join(p.text for p in doc.sections[0].footer.paragraphs)
    assert "AI-assisted draft" in footer_text


def test_format_docx_terms_table():
    data = format_docx(SAMPLE, "Freelance Work Contract", terms="Pay in 7 days; Keep secrets; Deliver on time")
    doc = Document(BytesIO(data))
    assert len(doc.tables) == 1
    rows = [[c.text for c in row.cells] for row in doc.tables[0].rows]
    assert rows[0] == ["No.", "Term / Condition"]
    assert rows[1] == ["1", "Pay in 7 days"]
    assert len(rows) == 4


def test_format_docx_no_table_for_single_term():
    doc = Document(BytesIO(format_docx(SAMPLE, "X", terms="Only one term")))
    assert len(doc.tables) == 0


def test_format_docx_rejects_empty():
    with pytest.raises(ValueError):
        format_docx("", "X")


# --------------------------------------------------------------------------
# PDF
# --------------------------------------------------------------------------
def test_format_pdf_basic():
    data = format_pdf(SAMPLE, "Freelance Work Contract")
    assert data.startswith(b"%PDF")
    assert b"%%EOF" in data[-1024:]
    assert len(data) > 1500


def test_format_pdf_escapes_markup_characters():
    nasty = "SPECIAL <b>CHARS</b> & <unclosed\n\nClause with <tags>, & ampersands, 5 < 6 > 4.\n\nRent \u20b9 25,000"
    data = format_pdf(nasty, "Test", terms="A < B; C & D")
    assert data.startswith(b"%PDF")


def test_format_pdf_multi_page_and_terms_table():
    body = "TITLE\n\n" + "\n\n".join(f"{i}. CLAUSE\n\n" + ("Lorem ipsum dolor sit amet. " * 40) for i in range(1, 25))
    data = format_pdf(body, "Long", terms="One; Two; Three")
    assert data.startswith(b"%PDF")
    assert data.count(b"/Type /Page\n") + data.count(b"/Type /Page ") >= 3


def test_format_pdf_rejects_empty():
    with pytest.raises(ValueError):
        format_pdf("  \n ", "X")

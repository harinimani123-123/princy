"""Export helpers: turn plain-text legal drafts into TXT, DOCX and PDF bytes.

All three ``format_*`` functions take the (possibly user-edited) document
text and return ``bytes`` that can be handed straight to Streamlit's
``st.download_button``.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Mm, Pt, RGBColor
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    Image as RLImage,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from backend.utils.text_utils import is_heading, split_terms

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
LOGO_PATH = PROJECT_ROOT / "assets" / "logo.png"

FOOTER_NOTE = "AI-assisted draft - review by a qualified legal professional before use."
TERMS_HEADING = "SUMMARY OF KEY TERMS (AS PROVIDED)"

_BULLET_RE = re.compile(r"^\s*(?:[-*\u2022\u25cf\u25aa])\s+(.*)$")
_SUBCLAUSE_RE = re.compile(r"^(?:\(?[a-zA-Z]\)|\((?:[ivxIVX]+|\d+)\)|\d+\.\d+)\s")
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


# ---------------------------------------------------------------------------
# Parsing shared by DOCX and PDF
# ---------------------------------------------------------------------------
@dataclass
class Block:
    """One renderable unit of the document."""

    kind: str  # "heading" | "bullet" | "subclause" | "body" | "blank"
    text: str = ""


def _require_text(text: str) -> str:
    if text is None or not str(text).strip():
        raise ValueError("Document content is empty; nothing to export.")
    return _CONTROL_RE.sub("", str(text)).replace("\r\n", "\n").replace("\r", "\n")


def parse_document(text: str, doc_type: str = "") -> tuple[str, list[Block]]:
    """Split raw text into a title and a list of :class:`Block` objects.

    The first non-empty line becomes the title when it looks like a heading;
    otherwise ``doc_type`` (or a generic title) is used.
    """
    lines = text.split("\n")
    title = (doc_type or "").strip() or "Legal Document"

    first = next((i for i, line in enumerate(lines) if line.strip()), None)
    if first is not None:
        candidate = lines[first].strip()
        if is_heading(candidate) and not re.match(r"^\d", candidate):
            title = candidate.rstrip(":")
            lines = lines[first + 1:]

    blocks: list[Block] = []
    for raw in lines:
        line = raw.strip()
        if not line:
            if blocks and blocks[-1].kind != "blank":
                blocks.append(Block("blank"))
            continue
        bullet = _BULLET_RE.match(line)
        if is_heading(line):
            blocks.append(Block("heading", line.rstrip(":")))
        elif bullet:
            blocks.append(Block("bullet", bullet.group(1).strip()))
        elif _SUBCLAUSE_RE.match(line):
            blocks.append(Block("subclause", line))
        else:
            blocks.append(Block("body", line))
    while blocks and blocks[-1].kind == "blank":
        blocks.pop()
    return title, blocks


# ---------------------------------------------------------------------------
# TXT
# ---------------------------------------------------------------------------
def format_txt(text: str) -> bytes:
    """Return the document as UTF-8 encoded plain text."""
    cleaned = _require_text(text).strip()
    return (cleaned + "\n").encode("utf-8")


# ---------------------------------------------------------------------------
# DOCX
# ---------------------------------------------------------------------------
DOCX_FONT = "Times New Roman"


def _set_style_font(style, name: str, size: float | None = None, bold: bool | None = None,
                    color: RGBColor | None = None) -> None:
    """Set a style's font, removing theme-font overrides that would win."""
    style.font.name = name
    if size is not None:
        style.font.size = Pt(size)
    if bold is not None:
        style.font.bold = bold
    if color is not None:
        style.font.color.rgb = color
    rpr = style.element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.append(rfonts)
    for attr in ("w:ascii", "w:hAnsi", "w:eastAsia", "w:cs"):
        rfonts.set(qn(attr), name)
    for attr in ("w:asciiTheme", "w:hAnsiTheme", "w:eastAsiaTheme", "w:cstheme"):
        if rfonts.get(qn(attr)) is not None:
            del rfonts.attrib[qn(attr)]


def _add_field(run, instruction: str) -> None:
    """Append a Word field (e.g. PAGE / NUMPAGES) to ``run``."""
    begin = OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = f" {instruction} "
    separate = OxmlElement("w:fldChar")
    separate.set(qn("w:fldCharType"), "separate")
    placeholder = OxmlElement("w:t")
    placeholder.text = "1"
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    for element in (begin, instr, separate, placeholder, end):
        run._r.append(element)


def _shade_cell(cell, fill_hex: str) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    shading = OxmlElement("w:shd")
    shading.set(qn("w:val"), "clear")
    shading.set(qn("w:color"), "auto")
    shading.set(qn("w:fill"), fill_hex)
    tc_pr.append(shading)


def _docx_add_terms_table(doc, terms: list[str]) -> None:
    heading = doc.add_heading(TERMS_HEADING, level=2)
    heading.paragraph_format.space_before = Pt(6)
    table = doc.add_table(rows=1, cols=2)
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    widths = (Inches(0.6), Inches(5.6))
    for column, width in zip(table.columns, widths):
        column.width = width  # also updates the table grid so Word/LibreOffice respect it

    header = table.rows[0].cells
    for cell, label, width in zip(header, ("No.", "Term / Condition"), widths):
        cell.width = width
        cell.text = ""
        run = cell.paragraphs[0].add_run(label)
        run.bold = True
        _shade_cell(cell, "D9E2F3")

    for index, term in enumerate(terms, start=1):
        cells = table.add_row().cells
        cells[0].width, cells[1].width = widths
        cells[0].text = str(index)
        cells[1].text = term
    for row in table.rows:
        for cell in row.cells:
            for par in cell.paragraphs:
                par.paragraph_format.space_before = Pt(2)
                par.paragraph_format.space_after = Pt(2)
    doc.add_paragraph().paragraph_format.space_after = Pt(2)


def format_docx(text: str, doc_type: str = "", terms: str | None = None,
                include_logo: bool = True) -> bytes:
    """Build a Word document (.docx) and return it as bytes.

    Args:
        text: The document body (plain text).
        doc_type: Used as the title when the text has no title line.
        terms: Optional semicolon-separated terms; rendered as a table.
        include_logo: Place ``assets/logo.png`` at the top when it exists.
    """
    text = _require_text(text)
    title, blocks = parse_document(text, doc_type)

    doc = Document()
    section = doc.sections[0]
    section.page_width, section.page_height = Mm(210), Mm(297)  # A4
    section.left_margin = section.right_margin = Inches(1)
    section.top_margin = section.bottom_margin = Inches(1)

    styles = doc.styles
    _set_style_font(styles["Normal"], DOCX_FONT, size=11)
    _set_style_font(styles["Heading 1"], DOCX_FONT, size=16, bold=True, color=RGBColor(0, 0, 0))
    _set_style_font(styles["Heading 2"], DOCX_FONT, size=12, bold=True, color=RGBColor(0, 0, 0))
    _set_style_font(styles["List Bullet"], DOCX_FONT, size=11)
    _set_style_font(styles["Footer"], DOCX_FONT, size=8)  # page-number fields inherit this

    doc.core_properties.title = title
    doc.core_properties.author = "LegalEase"
    doc.core_properties.comments = "AI-assisted draft. Review by a qualified legal professional."

    # Logo (optional - the document is still produced if it cannot be loaded)
    if include_logo and LOGO_PATH.exists():
        try:
            doc.add_picture(str(LOGO_PATH), width=Inches(1.8))
            doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
        except Exception as exc:  # noqa: BLE001 - logo must never break export
            logger.warning("Could not embed logo in DOCX: %s", type(exc).__name__)

    title_par = doc.add_heading(title, level=1)
    title_par.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title_par.paragraph_format.space_after = Pt(14)

    term_items = split_terms(terms)
    if len(term_items) >= 2:
        _docx_add_terms_table(doc, term_items)

    for block in blocks:
        if block.kind == "blank":
            continue
        if block.kind == "heading":
            heading = doc.add_heading(block.text, level=2)
            heading.paragraph_format.space_before = Pt(12)
            heading.paragraph_format.space_after = Pt(4)
            heading.paragraph_format.keep_with_next = True
        elif block.kind == "bullet":
            par = doc.add_paragraph(block.text, style="List Bullet")
            par.paragraph_format.space_after = Pt(3)
        else:
            par = doc.add_paragraph(block.text)
            par.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
            par.paragraph_format.space_after = Pt(6)
            par.paragraph_format.line_spacing = 1.15
            if block.kind == "subclause":
                par.paragraph_format.left_indent = Inches(0.35)

    # Footer: disclaimer + "Page X of Y"
    footer_par = section.footer.paragraphs[0]
    footer_par.alignment = WD_ALIGN_PARAGRAPH.CENTER
    note = footer_par.add_run(FOOTER_NOTE + "    Page ")
    note.font.size = Pt(8)
    note.italic = True
    page_run = footer_par.add_run()
    page_run.font.size = Pt(8)
    _add_field(page_run, "PAGE")
    of_run = footer_par.add_run(" of ")
    of_run.font.size = Pt(8)
    total_run = footer_par.add_run()
    total_run.font.size = Pt(8)
    _add_field(total_run, "NUMPAGES")

    buffer = BytesIO()
    doc.save(buffer)
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------
# (regular, bold) TrueType candidates, first match wins. TrueType fonts cover
# symbols such as the Indian Rupee sign that the built-in Helvetica lacks.
_FONT_CANDIDATES = [
    ("C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/arialbd.ttf"),
    ("C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/segoeuib.ttf"),
    ("/Library/Fonts/Arial.ttf", "/Library/Fonts/Arial Bold.ttf"),
    ("/System/Library/Fonts/Supplemental/Arial.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    ("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
     "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"),
]

_ASCII_FALLBACKS = {"\u20b9": "INR ", "\u20ac": "EUR ", "\u2264": "<=", "\u2265": ">="}


@lru_cache(maxsize=1)
def _pdf_fonts() -> tuple[str, str, bool]:
    """Return ``(regular_name, bold_name, is_unicode)`` for ReportLab."""
    for regular, bold in _FONT_CANDIDATES:
        if Path(regular).exists() and Path(bold).exists():
            try:
                pdfmetrics.registerFont(TTFont("LegalEaseSans", regular))
                pdfmetrics.registerFont(TTFont("LegalEaseSans-Bold", bold))
                return "LegalEaseSans", "LegalEaseSans-Bold", True
            except Exception as exc:  # noqa: BLE001
                logger.warning("Could not load font %s: %s", regular, type(exc).__name__)
    return "Helvetica", "Helvetica-Bold", False


def _pdf_safe(text: str) -> str:
    """Make text safe for ReportLab Paragraphs: no control chars, XML-escaped."""
    _, _, unicode_ok = _pdf_fonts()
    text = _CONTROL_RE.sub("", text)
    if not unicode_ok:
        for char, replacement in _ASCII_FALLBACKS.items():
            text = text.replace(char, replacement)
        text = text.encode("cp1252", errors="replace").decode("cp1252")
    return xml_escape(text)  # escapes & < >


class _NumberedCanvas(canvas.Canvas):
    """Canvas that draws a footer with 'Page X of Y' on every page."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states: list[dict] = []

    def showPage(self):  # noqa: N802 - ReportLab API name
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self._draw_footer(total)
            super().showPage()
        super().save()

    def _draw_footer(self, total_pages: int) -> None:
        regular, _, _ = _pdf_fonts()
        width = self._pagesize[0]
        self.setStrokeColor(colors.HexColor("#999999"))
        self.setLineWidth(0.4)
        self.line(2.2 * cm, 1.6 * cm, width - 2.2 * cm, 1.6 * cm)
        self.setFont(regular, 7.5)
        self.setFillColor(colors.HexColor("#555555"))
        self.drawString(2.2 * cm, 1.15 * cm, FOOTER_NOTE)
        self.drawRightString(width - 2.2 * cm, 1.15 * cm, f"Page {self._pageNumber} of {total_pages}")


def format_pdf(text: str, doc_type: str = "", terms: str | None = None,
               include_logo: bool = True) -> bytes:
    """Build an A4 PDF with ReportLab and return it as bytes."""
    text = _require_text(text)
    title, blocks = parse_document(text, doc_type)
    regular, bold, _ = _pdf_fonts()

    title_style = ParagraphStyle("LE_Title", fontName=bold, fontSize=16, leading=20,
                                 alignment=TA_CENTER, spaceAfter=14, spaceBefore=6)
    heading_style = ParagraphStyle("LE_Heading", fontName=bold, fontSize=11.5, leading=15,
                                   spaceBefore=12, spaceAfter=4, keepWithNext=1)
    body_style = ParagraphStyle("LE_Body", fontName=regular, fontSize=10.5, leading=15,
                                alignment=TA_JUSTIFY, spaceAfter=6)
    sub_style = ParagraphStyle("LE_Sub", parent=body_style, leftIndent=18)
    bullet_style = ParagraphStyle("LE_Bullet", parent=body_style, leftIndent=22,
                                  bulletIndent=8, spaceAfter=3)
    cell_style = ParagraphStyle("LE_Cell", fontName=regular, fontSize=9.5, leading=13)
    cell_bold = ParagraphStyle("LE_CellBold", parent=cell_style, fontName=bold)

    story: list = []

    if include_logo and LOGO_PATH.exists():
        try:
            from PIL import Image as PILImage

            with PILImage.open(LOGO_PATH) as img:
                px_w, px_h = img.size
            logo_w = 4.5 * cm
            logo = RLImage(str(LOGO_PATH), width=logo_w, height=logo_w * px_h / px_w)
            logo.hAlign = "CENTER"
            story.append(logo)
            story.append(Spacer(1, 6))
        except Exception as exc:  # noqa: BLE001 - logo must never break export
            logger.warning("Could not embed logo in PDF: %s", type(exc).__name__)

    story.append(Paragraph(_pdf_safe(title), title_style))

    term_items = split_terms(terms)
    if len(term_items) >= 2:
        story.append(Paragraph(_pdf_safe(TERMS_HEADING), heading_style))
        rows = [[Paragraph("No.", cell_bold), Paragraph("Term / Condition", cell_bold)]]
        rows += [[Paragraph(str(i), cell_style), Paragraph(_pdf_safe(t), cell_style)]
                 for i, t in enumerate(term_items, start=1)]
        frame_width = A4[0] - 4.4 * cm  # page width minus left/right margins
        table = Table(rows, colWidths=[1.3 * cm, frame_width - 1.3 * cm], repeatRows=1)
        table.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#888888")),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#D9E2F3")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(table)
        story.append(Spacer(1, 8))

    for block in blocks:
        if block.kind == "blank":
            story.append(Spacer(1, 4))
        elif block.kind == "heading":
            story.append(Paragraph(_pdf_safe(block.text), heading_style))
        elif block.kind == "bullet":
            story.append(Paragraph(_pdf_safe(block.text), bullet_style, bulletText="\u2022"))
        elif block.kind == "subclause":
            story.append(Paragraph(_pdf_safe(block.text), sub_style))
        else:
            story.append(Paragraph(_pdf_safe(block.text), body_style))

    buffer = BytesIO()
    pdf = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=2.2 * cm,
        rightMargin=2.2 * cm,
        topMargin=2.0 * cm,
        bottomMargin=2.4 * cm,
        title=_CONTROL_RE.sub("", title),
        author="LegalEase",
        subject="AI-assisted legal document draft",
        creator="LegalEase",
    )
    pdf.build(story, canvasmaker=_NumberedCanvas)
    return buffer.getvalue()

"""
Genuine PDF & Scanned PDF Redaction Engine using PyMuPDF (fitz).
Removes underlying character glyphs from native PDF content streams AND destroys underlying
image pixels in scanned pages and embedded figures, while sanitizing PDF metadata and XMP streams.
"""
from __future__ import annotations

from typing import Dict, List
import fitz  # PyMuPDF

from app.models import PIIFinding, ReviewStatus


def redact_pdf_document(content: bytes, findings: List[PIIFinding]) -> bytes:
    """
    Apply genuine redaction to a PDF (native text, scanned pages, or hybrid):
    1. Group active findings by page number.
    2. Locate exact PDF Rect via finding.bbox and/or page.search_for(entity_text).
    3. Add redaction annotations with replacement labels.
    4. Call page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_PIXELS) to permanently remove
       both vector text glyphs and underlying raster pixels.
    5. Scrub PDF document info dictionary and XML/XMP metadata streams, and save with garbage=4.
    """
    doc = fitz.open(stream=content, filetype="pdf")
    try:
        by_page: Dict[int, List[PIIFinding]] = {}
        for f in findings:
            if f.review_status == ReviewStatus.REJECTED_FALSE_POSITIVE:
                continue
            if f.source_type == "metadata":
                continue
            by_page.setdefault(f.page_or_slide, []).append(f)

        for page_no, p_findings in by_page.items():
            if not (1 <= page_no <= len(doc)):
                continue
            page = doc[page_no - 1]
            has_Native_text = len(page.get_text("text").strip()) >= 25

            for f in p_findings:
                target_rects: List[fitz.Rect] = []

                # If native text page, first check exact text search intersecting the block bbox
                if has_Native_text and f.source_type in {"paragraph", "header", "footer", "table_cell"}:
                    search_hits = page.search_for(f.entity_text)
                    if search_hits:
                        if f.bbox is not None:
                            block_rect = fitz.Rect(
                                f.bbox.x0 - 15, f.bbox.y0 - 8, f.bbox.x1 + 15, f.bbox.y1 + 8
                            )
                            filtered = [r for r in search_hits if r.intersects(block_rect)]
                            target_rects = filtered if filtered else search_hits
                        else:
                            target_rects = search_hits

                # Fallback or Scanned/Embedded OCR bounding box
                if not target_rects and f.bbox is not None:
                    pad = 1.5
                    target_rects = [
                        fitz.Rect(
                            f.bbox.x0 - pad,
                            f.bbox.y0 - pad,
                            f.bbox.x1 + pad,
                            f.bbox.y1 + pad,
                        )
                    ]

                for r in target_rects:
                    page.add_redact_annot(
                        r,
                        text=f.replacement_label,
                        fontsize=7.0,
                        fill=(0.93, 0.95, 0.98),
                        text_color=(0.12, 0.23, 0.54),
                    )

            # Permanently apply redactions: removes native text tokens AND blanks underlying image pixels
            page.apply_redactions(
                images=fitz.PDF_REDACT_IMAGE_PIXELS,
                graphics=fitz.PDF_REDACT_LINE_ART_NONE,
            )

        # Scrub all PDF metadata and XMP streams
        doc.set_metadata(
            {
                "title": "Sanitized Cadence Document (Redacted)",
                "author": "",
                "subject": "",
                "keywords": "",
                "creator": "Cadence Privacy Gate Redactor",
                "producer": "Cadence Privacy Gate Redactor",
            }
        )
        try:
            doc.del_xml_metadata()
        except Exception:
            pass

        return doc.tobytes(garbage=4, deflate=True, clean=True)
    finally:
        doc.close()

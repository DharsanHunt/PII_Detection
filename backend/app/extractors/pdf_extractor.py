"""Format-aware PDF Extractor supporting both Native Text PDFs, Scanned PDFs, and Embedded Figure Images."""
from __future__ import annotations

import io
from typing import List, Tuple
import fitz  # PyMuPDF
from PIL import Image

from app.config import get_policy
from app.extractors.ocr_engine import cached_ocr_call
from app.models import BoundingBox, ExtractionProfile, TextBlockSegment


METADATA_KEYS_OF_INTEREST = ("author", "title", "subject", "keywords", "creator", "producer")


def _ocr_image_to_pdf_segments(
    img_bytes: bytes,
    img_w: float,
    img_h: float,
    target_rect: fitz.Rect,
    page_no: int,
    source_type: str,
    location_prefix: str,
    block_id_prefix: str,
    image_ref: str | None = None,
) -> List[TextBlockSegment]:
    """Run OCR on an image and map pixel bounding boxes into PDF page points (target_rect)."""
    results = cached_ocr_call(img_bytes)
    if not results or img_w <= 0 or img_h <= 0:
        return []

    raw_items = []
    for box, text, conf in results:
        if not text or not str(text).strip():
            continue
        xs = [float(pt[0]) for pt in box]
        ys = [float(pt[1]) for pt in box]
        px0, px1 = min(xs), max(xs)
        py0, py1 = min(ys), max(ys)

        # Map pixel coordinates [0..img_w, 0..img_h] to PDF page Rect coordinates
        rx0 = target_rect.x0 + (px0 / img_w) * target_rect.width
        ry0 = target_rect.y0 + (py0 / img_h) * target_rect.height
        rx1 = target_rect.x0 + (px1 / img_w) * target_rect.width
        ry1 = target_rect.y0 + (py1 / img_h) * target_rect.height

        raw_items.append((rx0, ry0, rx1, ry1, str(text).strip(), float(conf)))

    # Sort top-to-bottom (8pt vertical bands), then left-to-right
    raw_items.sort(key=lambda item: (round(item[1] / 8.0), item[0]))

    # Group horizontally adjacent OCR boxes on the same line into coherent line blocks
    # when they are close horizontally, OR keep individual boxes when separated by table columns.
    segments: List[TextBlockSegment] = []
    merged_items: List[Tuple[float, float, float, float, str, float]] = []
    for item in raw_items:
        rx0, ry0, rx1, ry1, txt, conf = item
        if merged_items:
            px0, py0, px1, py1, ptxt, pconf = merged_items[-1]
            same_line = abs(ry0 - py0) <= 5.0 and abs((ry1 - ry0) - (py1 - py0)) <= 5.0
            horiz_gap = rx0 - px1
            if same_line and -2.0 <= horiz_gap <= 5.0:
                new_txt = f"{ptxt} {txt}"
                new_conf = (pconf + conf) / 2.0
                merged_items[-1] = (
                    min(px0, rx0),
                    min(py0, ry0),
                    max(px1, rx1),
                    max(py1, ry1),
                    new_txt,
                    new_conf,
                )
                continue
        merged_items.append(item)

    for idx, (rx0, ry0, rx1, ry1, text, conf) in enumerate(merged_items):
        loc = f"{location_prefix} · Line {idx + 1}"
        if image_ref:
            loc = f"{location_prefix} · Figure ({image_ref}) · Line {idx + 1}"
        segments.append(
            TextBlockSegment(
                block_id=f"{block_id_prefix}_p{page_no}_b{idx + 1}",
                source_type=source_type,  # type: ignore[arg-type]
                page_or_slide=page_no,
                location_ref=loc,
                text=text,
                bbox=BoundingBox(
                    x0=round(rx0, 2),
                    y0=round(ry0, 2),
                    x1=round(rx1, 2),
                    y1=round(ry1, 2),
                    page_or_slide=page_no,
                    coord_system="pdf_points",
                ),
                ocr_confidence=round(conf, 4),
                image_ref=image_ref,
            )
        )
    return segments


def extract_pdf_document(content: bytes) -> Tuple[List[TextBlockSegment], ExtractionProfile]:
    """
    Extract text, layout, tables, metadata, and OCR segments from a PDF document.
    Automatically detects per-page whether native text extraction or scanned-page OCR is required,
    and also inspects embedded images on native pages.
    """
    policy = get_policy()
    doc = fitz.open(stream=content, filetype="pdf")
    segments: List[TextBlockSegment] = []

    ocr_pages: List[int] = []
    native_pages: List[int] = []
    total_tables = 0
    total_paragraphs = 0
    total_embedded_images = 0
    ocr_embedded_images_with_text = 0
    metadata_count = 0

    try:
        # 1. Extract PDF document metadata
        meta = doc.metadata or {}
        for k in METADATA_KEYS_OF_INTEREST:
            val = (meta.get(k) or "").strip()
            if val:
                metadata_count += 1
                segments.append(
                    TextBlockSegment(
                        block_id=f"pdf_meta_{k}",
                        source_type="metadata",
                        page_or_slide=1,
                        location_ref=f"PDF Metadata · {k}",
                        text=val,
                        metadata_key=k,
                    )
                )

        # 2. Process each page
        for p_idx in range(len(doc)):
            page_no = p_idx + 1
            page = doc[p_idx]
            page_rect = page.rect
            page_h = max(1.0, page_rect.height)

            raw_text = page.get_text("text").strip()
            page_images = page.get_images(full=True)
            total_embedded_images += len(page_images)

            if len(raw_text) >= 25:
                # Native text page
                native_pages.append(page_no)
                try:
                    tabs = page.find_tables()
                    if tabs and tabs.tables:
                        total_tables += len(tabs.tables)
                except Exception:
                    pass

                blocks = page.get_text("blocks")
                # Sort blocks in reading order
                blocks_sorted = sorted(blocks, key=lambda b: (round(b[1] / 10.0), b[0]))
                for b_idx, b in enumerate(blocks_sorted):
                    bx0, by0, bx1, by1, btext, block_no, block_type = b[:7]
                    if block_type != 0:
                        continue
                    clean_txt = " ".join(
                        line.strip() for line in str(btext).splitlines() if line.strip()
                    )
                    if not clean_txt:
                        continue
                    total_paragraphs += 1

                    # Classify header / footer vs body paragraph
                    if by1 <= page_h * 0.08:
                        stype = "header"
                        loc = f"Page {page_no} · Header · Block {b_idx + 1}"
                    elif by0 >= page_h * 0.92:
                        stype = "footer"
                        loc = f"Page {page_no} · Footer · Block {b_idx + 1}"
                    else:
                        stype = "paragraph"
                        loc = f"Page {page_no} · Block {b_idx + 1}"

                    segments.append(
                        TextBlockSegment(
                            block_id=f"pdf_p{page_no}_b{b_idx + 1}",
                            source_type=stype,  # type: ignore[arg-type]
                            page_or_slide=page_no,
                            location_ref=loc,
                            text=clean_txt,
                            bbox=BoundingBox(
                                x0=round(float(bx0), 2),
                                y0=round(float(by0), 2),
                                x1=round(float(bx1), 2),
                                y1=round(float(by1), 2),
                                page_or_slide=page_no,
                                coord_system="pdf_points",
                            ),
                        )
                    )

                # Also run OCR on embedded screenshots/figures on native pages if enabled
                if policy.enable_ocr_on_embedded_images and page_images:
                    for img_idx, img_info in enumerate(page_images):
                        xref = img_info[0]
                        img_w, img_h = img_info[2], img_info[3]
                        if img_w < 80 or img_h < 40:
                            continue
                        rects = page.get_image_rects(xref)
                        if not rects:
                            continue
                        target_rect = rects[0]
                        try:
                            pix = fitz.Pixmap(doc, xref)
                            if pix.n - pix.alpha > 3:
                                pix = fitz.Pixmap(fitz.csRGB, pix)
                            img_bytes = pix.tobytes("png")
                            ocr_segs = _ocr_image_to_pdf_segments(
                                img_bytes=img_bytes,
                                img_w=float(pix.width),
                                img_h=float(pix.height),
                                target_rect=target_rect,
                                page_no=page_no,
                                source_type="ocr_embedded_image",
                                location_prefix=f"Page {page_no}",
                                block_id_prefix=f"pdf_emb_x{xref}",
                                image_ref=f"xref_{xref}",
                            )
                            if ocr_segs:
                                ocr_embedded_images_with_text += 1
                                segments.extend(ocr_segs)
                        except Exception:
                            continue
            else:
                # Scanned / Image-based PDF Page
                ocr_pages.append(page_no)
                if policy.enable_ocr_on_scanned_pages:
                    # Render page at 130 DPI (approx 1075x1520 px for A4) for optimal speed + accuracy
                    pix = page.get_pixmap(dpi=130, alpha=False)
                    img_bytes = pix.tobytes("jpg")
                    ocr_segs = _ocr_image_to_pdf_segments(
                        img_bytes=img_bytes,
                        img_w=float(pix.width),
                        img_h=float(pix.height),
                        target_rect=page_rect,
                        page_no=page_no,
                        source_type="ocr_page",
                        location_prefix=f"Page {page_no} (Scanned OCR)",
                        block_id_prefix="pdf_scan",
                    )
                    total_paragraphs += len(ocr_segs)
                    segments.extend(ocr_segs)

        is_scanned = len(ocr_pages) > 0 and len(native_pages) == 0
        notes = []
        if is_scanned:
            notes.append(
                f"All {len(doc)} pages lack selectable text streams and were processed via Scanned PDF OCR pipeline."
            )
        elif ocr_pages:
            notes.append(
                f"Hybrid PDF: {len(native_pages)} native text pages and {len(ocr_pages)} scanned OCR pages."
            )
        else:
            notes.append(f"Digitally native PDF across all {len(doc)} pages.")

        if ocr_embedded_images_with_text > 0:
            notes.append(
                f"Recovered embedded text via OCR from {ocr_embedded_images_with_text} embedded figure image(s)."
            )

        profile = ExtractionProfile(
            detected_format="SCANNED_PDF" if is_scanned else "PDF",
            mime_type="application/pdf",
            is_scanned_document=is_scanned,
            total_pages_or_slides=len(doc),
            ocr_pages_list=ocr_pages,
            native_text_pages_list=native_pages,
            tables_count=total_tables,
            paragraphs_count=total_paragraphs,
            embedded_images_count=total_embedded_images,
            ocr_embedded_images_with_text=ocr_embedded_images_with_text,
            metadata_fields_extracted=metadata_count,
            extraction_notes=notes,
        )
        return segments, profile
    finally:
        doc.close()

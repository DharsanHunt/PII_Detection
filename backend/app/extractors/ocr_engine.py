"""OCR Engine wrapper using RapidOCR (PaddleOCR PP-OCRv4 via ONNX Runtime) with sub-box span mapping and SHA-256 caching."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from rapidocr_onnxruntime import RapidOCR

from app.config import TEMP_STORAGE_DIR
from app.models import BoundingBox, TextBlockSegment

_OCR_INSTANCE: Optional[RapidOCR] = None
_OCR_MEM_CACHE: Dict[str, List[Tuple[List[List[float]], str, float]]] = {}
_CACHE_FILE = TEMP_STORAGE_DIR / "ocr_sha256_cache.json"
_CACHE_LOADED = False


def get_ocr_engine() -> RapidOCR:
    """Lazy-loaded singleton RapidOCR engine to avoid repeated ONNX initialization."""
    global _OCR_INSTANCE
    if _OCR_INSTANCE is None:
        _OCR_INSTANCE = RapidOCR()
    return _OCR_INSTANCE


def cached_ocr_call(image_bytes: bytes) -> List[Tuple[List[List[float]], str, float]]:
    """Run RapidOCR on image_bytes with in-memory and local temp SHA-256 bounding-box caching."""
    global _CACHE_LOADED
    if not _CACHE_LOADED:
        _CACHE_LOADED = True
        if _CACHE_FILE.exists():
            try:
                raw_data = json.loads(_CACHE_FILE.read_text(encoding="utf-8"))
                for k, v in raw_data.items():
                    _OCR_MEM_CACHE[k] = [(item[0], str(item[1]), float(item[2])) for item in v]
            except Exception:
                pass

    digest = hashlib.sha256(image_bytes).hexdigest()
    if digest in _OCR_MEM_CACHE:
        return _OCR_MEM_CACHE[digest]

    ocr = get_ocr_engine()
    try:
        results, _ = ocr(image_bytes)
    except Exception:
        return []

    parsed: List[Tuple[List[List[float]], str, float]] = []
    if results:
        for box, text, conf in results:
            if text and str(text).strip():
                coords = [[float(pt[0]), float(pt[1])] for pt in box]
                parsed.append((coords, str(text).strip(), float(conf)))

    _OCR_MEM_CACHE[digest] = parsed
    try:
        TEMP_STORAGE_DIR.mkdir(parents=True, exist_ok=True)
        _CACHE_FILE.write_text(json.dumps(_OCR_MEM_CACHE), encoding="utf-8")
    except Exception:
        pass
    return parsed


def run_ocr_on_image_bytes(
    image_bytes: bytes,
    page_or_slide: int = 1,
    location_prefix: str = "Page 1",
    source_type: str = "ocr_page",
    image_ref: Optional[str] = None,
    block_id_prefix: str = "ocr",
) -> List[TextBlockSegment]:
    """
    Run OCR on raw image bytes and return normalized TextBlockSegments with bounding boxes
    sorted in top-to-bottom, left-to-right reading order.
    """
    results = cached_ocr_call(image_bytes)
    if not results:
        return []

    raw_items: List[Tuple[float, float, float, float, str, float]] = []
    for box, text, conf in results:
        if not text or not str(text).strip():
            continue
        xs = [ float(pt[0]) for pt in box ]
        ys = [ float(pt[1]) for pt in box ]
        x0, x1 = min(xs), max(xs)
        y0, y1 = min(ys), max(ys)
        raw_items.append((x0, y0, x1, y1, str(text).strip(), float(conf)))

    # Sort into natural reading order: group vertically within ~12px bands, then left-to-right
    raw_items.sort(key=lambda item: (round(item[1] / 14.0), item[0]))

    segments: List[TextBlockSegment] = []
    for idx, (x0, y0, x1, y1, text, conf) in enumerate(raw_items):
        loc = f"{location_prefix} · OCR Box {idx + 1}"
        if image_ref:
            loc = f"{location_prefix} · Image ({image_ref}) · Box {idx + 1}"
        segments.append(
            TextBlockSegment(
                block_id=f"{block_id_prefix}_p{page_or_slide}_b{idx + 1}",
                source_type=source_type,  # type: ignore[arg-type]
                page_or_slide=page_or_slide,
                location_ref=loc,
                text=text,
                bbox=BoundingBox(
                    x0=round(x0, 2),
                    y0=round(y0, 2),
                    x1=round(x1, 2),
                    y1=round(y1, 2),
                    page_or_slide=page_or_slide,
                    coord_system="pixels",
                ),
                ocr_confidence=round(conf, 4),
                image_ref=image_ref,
            )
        )
    return segments


def interpolate_subspan_bbox(
    full_bbox: Optional[BoundingBox],
    full_text_len: int,
    char_start: int,
    char_end: int,
) -> Optional[BoundingBox]:
    """
    Compute the horizontal bounding sub-box for a character span [char_start, char_end]
    within an OCR or PDF text block bounding box, adding a proportional-glyph safety margin
    so variable-width character strokes (e.g. 'M', 'W') are completely covered during pixel redaction.
    """
    if full_bbox is None or full_text_len <= 0:
        return full_bbox

    span_len = max(1, char_end - char_start)
    if span_len / full_text_len >= 0.72:
        return full_bbox

    total_w = max(1.0, full_bbox.x1 - full_bbox.x0)
    start_ratio = max(0.0, min(1.0, char_start / full_text_len))
    end_ratio = max(start_ratio, min(1.0, char_end / full_text_len))

    # Add a 6% or 8pt horizontal safety margin to account for variable-width proportional fonts
    margin_x = max(7.0, total_w * 0.06)
    sub_x0 = max(full_bbox.x0, full_bbox.x0 + total_w * start_ratio - margin_x)
    sub_x1 = min(full_bbox.x1, full_bbox.x0 + total_w * end_ratio + margin_x)

    return BoundingBox(
        x0=round(sub_x0, 2),
        y0=round(max(0.0, full_bbox.y0 - 1.5), 2),
        x1=round(sub_x1, 2),
        y1=round(full_bbox.y1 + 1.5, 2),
        page_or_slide=full_bbox.page_or_slide,
        coord_system=full_bbox.coord_system,
    )

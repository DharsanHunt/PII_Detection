"""Standalone Image (.png, .jpg, .jpeg) Extractor using OCR and EXIF metadata inspection."""
from __future__ import annotations

import io
from typing import List, Tuple
from PIL import Image, ExifTags

from app.extractors.ocr_engine import run_ocr_on_image_bytes
from app.models import ExtractionProfile, TextBlockSegment


def extract_image_document(
    content: bytes, detected_format: str, mime_type: str
) -> Tuple[List[TextBlockSegment], ExtractionProfile]:
    """
    Extract text and pixel bounding boxes from standalone PNG/JPG images using OCR,
    plus inspect any textual EXIF metadata tags.
    """
    segments: List[TextBlockSegment] = []
    metadata_count = 0

    try:
        img = Image.open(io.BytesIO(content))
        exif = img.getexif()
        if exif:
            for tag_id, value in exif.items():
                tag_name = str(ExifTags.TAGS.get(tag_id, tag_id))
                if tag_name in {"Artist", "XPAuthor", "Copyright", "ImageDescription", "UserComment"}:
                    val_str = str(value).strip()
                    if val_str:
                        metadata_count += 1
                        segments.append(
                            TextBlockSegment(
                                block_id=f"img_exif_{tag_name}",
                                source_type="metadata",
                                page_or_slide=1,
                                location_ref=f"Image EXIF · {tag_name}",
                                text=val_str,
                                metadata_key=tag_name,
                            )
                        )
    except Exception:
        pass

    ocr_segs = run_ocr_on_image_bytes(
        image_bytes=content,
        page_or_slide=1,
        location_prefix="Image Page 1",
        source_type="ocr_page",
        block_id_prefix="img_ocr",
    )
    segments.extend(ocr_segs)

    profile = ExtractionProfile(
        detected_format=detected_format,
        mime_type=mime_type,
        is_scanned_document=True,
        total_pages_or_slides=1,
        ocr_pages_list=[1],
        native_text_pages_list=[],
        tables_count=0,
        paragraphs_count=len(ocr_segs),
        embedded_images_count=1,
        ocr_embedded_images_with_text=1 if ocr_segs else 0,
        metadata_fields_extracted=metadata_count,
        extraction_notes=[
            f"Standalone {detected_format} artifact processed via OCR ({len(ocr_segs)} text regions detected)."
        ],
    )
    return segments, profile

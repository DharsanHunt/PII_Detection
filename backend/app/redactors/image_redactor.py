"""Pixel-level image redaction engine that permanently destroys sensitive pixels and strips EXIF metadata."""
from __future__ import annotations

import io
from typing import List
from PIL import Image, ImageDraw, ImageFont

from app.models import BoundingBox, PIIFinding, ReviewStatus


def redact_image_bytes_with_boxes(
    image_bytes: bytes,
    boxes_and_labels: List[tuple[BoundingBox, str]],
    output_format: str = "PNG",
) -> bytes:
    """
    Modify underlying pixels in an image for each (BoundingBox, replacement_label) pair,
    and strip EXIF/metadata chunks by encoding a clean pixel buffer.
    """
    orig = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    # Create a brand-new RGB canvas without copying EXIF/info metadata
    clean_img = Image.new("RGB", orig.size)
    clean_img.paste(orig)

    draw = ImageDraw.Draw(clean_img)
    font = ImageFont.load_default()

    for bbox, label in boxes_and_labels:
        x0 = max(0, int(bbox.x0) - 2)
        y0 = max(0, int(bbox.y0) - 2)
        x1 = min(clean_img.width, int(bbox.x1) + 2)
        y1 = min(clean_img.height, int(bbox.y1) + 2)
        if x1 <= x0 or y1 <= y0:
            continue

        # 1. Permanently overwrite sensitive pixels with opaque navy-slate fill
        draw.rectangle([x0, y0, x1, y1], fill=(238, 242, 249), outline=(30, 58, 138), width=1)

        # 2. Draw replacement token inside box if height permits
        box_h = y1 - y0
        box_w = x1 - x0
        if box_h >= 9 and box_w >= 28:
            display_label = label
            max_chars = max(4, int(box_w / 5.5))
            if len(display_label) > max_chars:
                display_label = display_label[: max_chars - 1] + "]"
            text_y = y0 + max(0, (box_h - 10) // 2)
            draw.text((x0 + 3, text_y), display_label, fill=(30, 58, 138), font=font)

    out_buf = io.BytesIO()
    fmt = "JPEG" if output_format.upper() in {"JPG", "JPEG"} else "PNG"
    clean_img.save(out_buf, format=fmt, quality=94)
    return out_buf.getvalue()


def redact_standalone_image(
    content: bytes,
    findings: List[PIIFinding],
    detected_format: str,
) -> bytes:
    """Redact active PII findings in a standalone PNG/JPG image."""
    active_boxes: List[tuple[BoundingBox, str]] = []
    for f in findings:
        if f.review_status == ReviewStatus.REJECTED_FALSE_POSITIVE:
            continue
        if f.bbox is not None:
            active_boxes.append((f.bbox, f.replacement_label))

    return redact_image_bytes_with_boxes(
        image_bytes=content,
        boxes_and_labels=active_boxes,
        output_format=detected_format,
    )

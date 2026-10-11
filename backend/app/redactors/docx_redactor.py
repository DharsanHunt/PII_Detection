"""
Format-Preserving Word (.docx) Redaction Engine.
Handles PII split across multiple formatting runs without leaving fragments behind,
preserves paragraph and table styles, sanitizes metadata, and pixel-redacts embedded images.
"""
from __future__ import annotations

import io
import zipfile
from typing import Dict, List, Set, Tuple
import docx

from app.models import BoundingBox, PIIFinding, ReviewStatus
from app.redactors.image_redactor import redact_image_bytes_with_boxes


def replace_spans_across_runs(
    runs: list,
    spans: List[Tuple[int, int, str]],
    para: object | None = None,
) -> None:
    """
    Replace character offset spans [(char_start, char_end, replacement_label), ...]
    across a sequence of python-docx or python-pptx Runs while preserving run formatting
    and ensuring zero fragments of the sensitive value remain in adjacent runs.
    """
    if not spans:
        return
    if not runs:
        if para is not None and hasattr(para, "text"):
            txt = getattr(para, "text") or ""
            full_strip = txt.strip()
            for s_idx, e_idx, rep in sorted(spans, key=lambda s: s[0], reverse=True):
                full_strip = full_strip[:s_idx] + rep + full_strip[e_idx:]
            setattr(para, "text", full_strip)
        return

    # Sort spans in descending order of start offset so earlier replacements do not shift indices
    sorted_spans = sorted(spans, key=lambda s: s[0], reverse=True)

    for start_idx, end_idx, replacement in sorted_spans:
        if end_idx <= start_idx:
            continue

        # Map each run to its current [r_start, r_end) character interval
        run_intervals: List[Tuple[int, int, object]] = []
        cursor = 0
        for r in runs:
            r_txt = r.text or ""
            r_len = len(r_txt)
            run_intervals.append((cursor, cursor + r_len, r))
            cursor += r_len

        # Account for potential leading/trailing whitespace strip differences between paragraph.text.strip() and paragraph.text
        full_concat = "".join(r.text or "" for r in runs)
        leading_ws = len(full_concat) - len(full_concat.lstrip())
        adj_start = start_idx + leading_ws
        adj_end = end_idx + leading_ws

        overlapping = [
            (r_start, r_end, r)
            for (r_start, r_end, r) in run_intervals
            if max(adj_start, r_start) < min(adj_end, r_end)
        ]
        if not overlapping:
            continue

        first_start, first_end, first_run = overlapping[0]
        last_start, last_end, last_run = overlapping[-1]

        prefix = (first_run.text or "")[: max(0, adj_start - first_start)]
        suffix = (last_run.text or "")[max(0, adj_end - last_start) :]

        if len(overlapping) == 1:
            first_run.text = prefix + replacement + suffix
        else:
            first_run.text = prefix + replacement
            for _, _, mid_run in overlapping[1:-1]:
                mid_run.text = ""
            last_run.text = suffix


def redact_docx_document(content: bytes, findings: List[PIIFinding]) -> bytes:
    """
    Apply format-preserving redaction to a Word (.docx) document:
    1. Group active findings by block_id.
    2. Apply run-spanning replacement on body paragraphs, table cells, headers, and footers.
    3. Sanitize core_properties metadata (author, last_modified_by, comments).
    4. Pixel-redact any embedded screenshots (word/media/*) where OCR detected PII.
    """
    doc = docx.Document(io.BytesIO(content))

    by_block: Dict[str, List[Tuple[int, int, str]]] = {}
    by_image: Dict[str, List[Tuple[BoundingBox, str]]] = {}

    for f in findings:
        if f.review_status == ReviewStatus.REJECTED_FALSE_POSITIVE:
            continue
        if f.source_type == "ocr_embedded_image" and f.image_ref and f.bbox:
            by_image.setdefault(f.image_ref, []).append((f.bbox, f.replacement_label))
        elif f.source_type != "metadata":
            by_block.setdefault(f.block_id, []).append(
                (f.char_start, f.char_end, f.replacement_label)
            )

    # 1. Headers & Footers
    for s_idx, section in enumerate(doc.sections):
        if section.header:
            for p_idx, p in enumerate(section.header.paragraphs):
                bid = f"docx_sec{s_idx}_hdr_p{p_idx}"
                if bid in by_block:
                    replace_spans_across_runs(p.runs, by_block[bid])
        if section.footer:
            for p_idx, p in enumerate(section.footer.paragraphs):
                bid = f"docx_sec{s_idx}_ftr_p{p_idx}"
                if bid in by_block:
                    replace_spans_across_runs(p.runs, by_block[bid])

    # 2. Body Paragraphs
    for p_idx, p in enumerate(doc.paragraphs):
        bid = f"docx_p_{p_idx}"
        if bid in by_block:
            replace_spans_across_runs(p.runs, by_block[bid])

    # 3. Table Cells (applying across all cells, including merged references that share text)
    for t_idx, table in enumerate(doc.tables):
        seen_tcs: List[object] = []
        for r_idx, row in enumerate(table.rows):
            for c_idx, cell in enumerate(row.cells):
                tc_obj = cell._tc
                if any(tc_obj is existing for existing in seen_tcs):
                    continue
                seen_tcs.append(tc_obj)
                for cp_idx, cp_para in enumerate(cell.paragraphs):
                    bid = f"docx_t{t_idx}_r{r_idx}_c{c_idx}_p{cp_idx}"
                    if bid in by_block:
                        replace_spans_across_runs(cp_para.runs, by_block[bid], cp_para)

    # 4. Sanitize Core Properties Metadata
    cp = doc.core_properties
    cp.author = ""
    cp.last_modified_by = ""
    cp.comments = ""

    intermediate_buf = io.BytesIO()
    doc.save(intermediate_buf)
    docx_bytes = intermediate_buf.getvalue()

    # 5. If any embedded images in word/media/* contained PII, pixel-redact them inside the archive
    if not by_image:
        return docx_bytes

    out_zip_buf = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(docx_bytes), "r") as zin:
        with zipfile.ZipFile(out_zip_buf, "w", compression=zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                raw_data = zin.read(item.filename)
                if item.filename in by_image:
                    ext = "JPG" if item.filename.lower().endswith((".jpg", ".jpeg")) else "PNG"
                    raw_data = redact_image_bytes_with_boxes(
                        image_bytes=raw_data,
                        boxes_and_labels=by_image[item.filename],
                        output_format=ext,
                    )
                zout.writestr(item, raw_data)

    return out_zip_buf.getvalue()

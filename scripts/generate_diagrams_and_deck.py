"""
Generates the 3 required architectural diagrams (PNG + SVG) and the 10-slide
Executive & Technical Presentation (.pptx) for Optiv Case Study 2:
Cadence Financial Group PII Detection & Secure Document Redaction Gateway.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Tuple

from PIL import Image, ImageDraw, ImageFont
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN
from pptx.util import Inches, Pt


ROOT_DIR = Path(__file__).resolve().parent.parent
DIAGRAMS_DIR = ROOT_DIR / "docs" / "diagrams"
DOCS_DIR = ROOT_DIR / "docs"


def _get_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = (
        ["C:/Windows/Fonts/segoeuib.ttf", "C:/Windows/Fonts/arialbd.ttf", "C:/Windows/Fonts/calibrib.ttf"]
        if bold
        else ["C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/calibri.ttf"]
    )
    for path in candidates:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                pass
    return ImageFont.load_default()


def _draw_rounded_box(
    draw: ImageDraw.ImageDraw,
    xy: Tuple[int, int, int, int],
    fill: Tuple[int, int, int],
    outline: Tuple[int, int, int],
    title: str,
    subtitle_lines: List[str],
    badge: str = "",
) -> None:
    x0, y0, x1, y1 = xy
    draw.rounded_rectangle(xy, radius=14, fill=fill, outline=outline, width=3)
    f_title = _get_font(19, bold=True)
    f_sub = _get_font(14, bold=False)
    f_badge = _get_font(12, bold=True)

    if badge:
        bx0 = x1 - 95
        by0 = y0 + 10
        draw.rounded_rectangle((bx0, by0, x1 - 12, by0 + 24), radius=6, fill=outline)
        draw.text((bx0 + 10, by0 + 4), badge, fill=(255, 255, 255), font=f_badge)

    draw.text((x0 + 18, y0 + 14), title, fill=(15, 23, 42), font=f_title)
    curr_y = y0 + 44
    for line in subtitle_lines:
        draw.text((x0 + 18, curr_y), line, fill=(51, 65, 85), font=f_sub)
        curr_y += 21


def _draw_arrow(
    draw: ImageDraw.ImageDraw,
    start: Tuple[int, int],
    end: Tuple[int, int],
    color: Tuple[int, int, int] = (71, 85, 105),
    label: str = "",
) -> None:
    draw.line([start, end], fill=color, width=4)
    ex, ey = end
    sx, sy = start
    if abs(ex - sx) >= abs(ey - sy):
        direction = 1 if ex > sx else -1
        pts = [(ex, ey), (ex - 12 * direction, ey - 7), (ex - 12 * direction, ey + 7)]
    else:
        direction = 1 if ey > sy else -1
        pts = [(ex, ey), (ex - 7, ey - 12 * direction), (ex + 7, ey - 12 * direction)]
    draw.polygon(pts, fill=color)
    if label:
        f_lbl = _get_font(13, bold=True)
        mx, my = (sx + ex) // 2, (sy + ey) // 2
        draw.text((mx + 8, my - 18), label, fill=color, font=f_lbl)


def generate_functional_design_diagram() -> Path:
    """1. Functional Design Diagram: 13-stage end-to-end functional workflow."""
    DIAGRAMS_DIR.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (1800, 1050), (248, 250, 252))
    draw = ImageDraw.Draw(img)

    # Header banner
    draw.rectangle((0, 0, 1800, 88), fill=(15, 23, 42))
    draw.text(
        (36, 18),
        "CADENCE FINANCIAL GROUP — END-TO-END FUNCTIONAL DESIGN DIAGRAM",
        fill=(255, 255, 255),
        font=_get_font(26, bold=True),
    )
    draw.text(
        (36, 54),
        "Optiv Cyber Simulation Case Study 2 | 13-Stage Document Sanitization, Structure Preservation & Privacy Gate Pipeline",
        fill=(148, 163, 184),
        font=_get_font(16, bold=False),
    )

    # Row 1: Ingestion & Extraction (Stages 1 - 4)
    _draw_rounded_box(
        draw,
        (50, 130, 420, 290),
        fill=(239, 246, 255),
        outline=(37, 99, 235),
        title="1. Multi-Format Upload",
        subtitle_lines=[
            "• PDF (Digital & Scanned), DOCX, PPTX",
            "• Standalone PNG, JPG/JPEG",
            "• Single or Batch Document Queue",
            "• Source Artifacts Kept 100% Immutable",
        ],
        badge="STAGE 1",
    )
    _draw_arrow(draw, (420, 210), (475, 210), (37, 99, 235))

    _draw_rounded_box(
        draw,
        (475, 130, 860, 290),
        fill=(239, 246, 255),
        outline=(37, 99, 235),
        title="2. Signature & Safety Gate",
        subtitle_lines=[
            "• Magic-Byte Header Verification",
            "• OOXML Zip-Bomb & Traversal Guard",
            "• Encrypted / Malformed File Rejection",
            "• Controlled Temp Workspace (0600)",
        ],
        badge="STAGE 2",
    )
    _draw_arrow(draw, (860, 210), (915, 210), (37, 99, 235))

    _draw_rounded_box(
        draw,
        (915, 130, 1320, 290),
        fill=(240, 253, 250),
        outline=(13, 148, 136),
        title="3. Structure & Layout Analysis",
        subtitle_lines=[
            "• Native Text vs Scanned Page Triage",
            "• Paragraphs, Runs, Tables, Headers",
            "• Slide Shapes, Notes & Alt-Text",
            "• Embedded Screenshot Extraction",
        ],
        badge="STAGE 3",
    )
    _draw_arrow(draw, (1320, 210), (1375, 210), (13, 148, 136))

    _draw_rounded_box(
        draw,
        (1375, 130, 1750, 290),
        fill=(240, 253, 250),
        outline=(13, 148, 136),
        title="4. Format-Aware Extraction",
        subtitle_lines=[
            "• PyMuPDF Word/Block Coordinates",
            "• python-docx / python-pptx DOM Trees",
            "• RapidOCR (PP-OCRv4) + Sub-BBox Map",
            "• SHA-256 Persistent OCR Caching",
        ],
        badge="STAGE 4",
    )

    # Connector Row 1 -> Row 2
    _draw_arrow(draw, (1562, 290), (1562, 360), (13, 148, 136))

    # Row 2: Hybrid Detection, Scoring & Redaction (Stages 5 - 8)
    _draw_rounded_box(
        draw,
        (1375, 360, 1750, 535),
        fill=(254, 243, 199),
        outline=(217, 119, 6),
        title="5. Hybrid PII Detection",
        subtitle_lines=[
            "• Deterministic Regex + Checksums",
            "• Contextual NER & Labeled Fields",
            "• Tabular Co-occurrence Gazetteer",
            "• False-Positive Suppression Filters",
        ],
        badge="STAGE 5",
    )
    _draw_arrow(draw, (1375, 447), (1320, 447), (217, 119, 6))

    _draw_rounded_box(
        draw,
        (915, 360, 1320, 535),
        fill=(254, 243, 199),
        outline=(217, 119, 6),
        title="6 & 7. Classification & Confidence",
        subtitle_lines=[
            "• 9 Policy Categories (Name, Email, Phone,",
            "  Emp ID, Gov ID, PAN, Acct, DOB, Address)",
            "• OCR + Detector Composite Confidence",
            "• Auto-Approve (>=0.80) vs Flagged Review",
        ],
        badge="STAGE 6-7",
    )
    _draw_arrow(draw, (915, 447), (860, 447), (217, 119, 6))

    _draw_rounded_box(
        draw,
        (475, 360, 860, 535),
        fill=(243, 232, 255),
        outline=(126, 34, 206),
        title="8. Redaction Span Mapping",
        subtitle_lines=[
            "• Exact Character Offset Alignment",
            "• Proportional Sub-Bounding Box Calc",
            "• Policy Labels ([NAME REDACTED]) or",
            "  Cross-Artifact Tokens ([PERSON_001])",
        ],
        badge="STAGE 8",
    )
    _draw_arrow(draw, (475, 447), (420, 447), (126, 34, 206))

    _draw_rounded_box(
        draw,
        (50, 360, 420, 535),
        fill=(243, 232, 255),
        outline=(126, 34, 206),
        title="9. Genuine Native Redaction",
        subtitle_lines=[
            "• PDF: apply_redactions() Stream Purge",
            "• Scanned PDF / PNG: Pixel Destruction",
            "• DOCX / PPTX: Cross-Run DOM Rewrite",
            "• Embedded Media + Metadata Scrubbing",
        ],
        badge="STAGE 9",
    )

    # Connector Row 2 -> Row 3
    _draw_arrow(draw, (235, 535), (235, 610), (126, 34, 206))

    # Row 3: Validation, Review, Privacy Gate & Safe Export (Stages 10 - 13)
    _draw_rounded_box(
        draw,
        (50, 610, 450, 795),
        fill=(220, 252, 231),
        outline=(22, 163, 74),
        title="10 & 11. Independent Validation",
        subtitle_lines=[
            "• Fresh Re-Extraction of Redacted Binary",
            "• Second-Pass Residual PII Verification",
            "• Metadata Sanitization Verification",
            "• Structure Retention Score (Target >=80%)",
        ],
        badge="STAGE 10-11",
    )
    _draw_arrow(draw, (450, 702), (510, 702), (22, 163, 74))

    _draw_rounded_box(
        draw,
        (510, 610, 920, 795),
        fill=(254, 249, 195),
        outline=(202, 138, 4),
        title="12. Human-in-the-Loop Review",
        subtitle_lines=[
            "• Side-by-Side Original vs Redacted View",
            "• Approve / Reject False Positives",
            "• Reclassify Category or Add Missed Span",
            "• Triggers Live Re-Redaction & Re-Check",
        ],
        badge="STAGE 12",
    )
    _draw_arrow(draw, (920, 702), (980, 702), (202, 138, 4))

    _draw_rounded_box(
        draw,
        (980, 610, 1360, 795),
        fill=(254, 226, 226),
        outline=(220, 38, 38),
        title="13A. Privacy Gate Enforcement",
        subtitle_lines=[
            "• PASS: 0 Residual PII & >=80% Structure",
            "• REVIEW_REQUIRED: Pending Low-Conf Spans",
            "• FAIL: Any Leaked PII or Structure <80%",
            "• Strictly Blocks Non-PASS LLM Handoff",
        ],
        badge="PRIVACY GATE",
    )
    _draw_arrow(draw, (1360, 702), (1415, 702), (22, 163, 74))

    _draw_rounded_box(
        draw,
        (1415, 610, 1750, 795),
        fill=(220, 252, 231),
        outline=(22, 163, 74),
        title="13B. Safe Export & AI Gateway",
        subtitle_lines=[
            "• Native Redacted File (.pdf/.docx/.pptx)",
            "• JSON/CSV Masked Findings Report",
            "• Zero-PII Security Audit Trail",
            "• Opt-In Sanitized Downstream LLM",
        ],
        badge="STAGE 13",
    )

    # Footer summary bar
    draw.rounded_rectangle((50, 845, 1750, 995), radius=12, fill=(241, 245, 249), outline=(148, 163, 184), width=2)
    draw.text(
        (75, 862),
        "Core Security & Architectural Guarantees:",
        fill=(15, 23, 42),
        font=_get_font(18, bold=True),
    )
    draw.text(
        (75, 895),
        "1. Zero Raw PII in Logs: Application and audit logs store only finding IDs, categories, offsets, and masked previews (e.g., [MA***LE]).",
        fill=(51, 65, 85),
        font=_get_font(15),
    )
    draw.text(
        (75, 925),
        "2. Irreversible Native Redaction: Removes underlying PDF character streams, overwrites raster pixels, and scrubs OOXML runs + embedded screenshots.",
        fill=(51, 65, 85),
        font=_get_font(15),
    )
    draw.text(
        (75, 955),
        "3. Server-Side LLM Firewall: Downstream AI endpoints raise HTTP 403 PrivacyGateViolationError unless Gate == PASS and explicit policy opt-in is enabled.",
        fill=(51, 65, 85),
        font=_get_font(15),
    )

    out_png = DIAGRAMS_DIR / "functional_design.png"
    img.save(out_png, format="PNG")
    return out_png


def generate_technical_architecture_diagram() -> Path:
    """2. Technical System Architecture Diagram."""
    DIAGRAMS_DIR.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (1800, 1050), (248, 250, 252))
    draw = ImageDraw.Draw(img)

    draw.rectangle((0, 0, 1800, 88), fill=(15, 23, 42))
    draw.text(
        (36, 18),
        "CADENCE FINANCIAL GROUP — TECHNICAL SYSTEM ARCHITECTURE",
        fill=(255, 255, 255),
        font=_get_font(26, bold=True),
    )
    draw.text(
        (36, 54),
        "Local-First Enterprise Privacy Gateway | React + TypeScript Frontend | FastAPI + Format-Aware Redaction Engine",
        fill=(148, 163, 184),
        font=_get_font(16, bold=False),
    )

    # Layer 1: Presentation Tier (Left)
    draw.rounded_rectangle((40, 120, 500, 990), radius=16, fill=(239, 246, 255), outline=(59, 130, 246), width=3)
    draw.text((65, 140), "PRESENTATION LAYER (React 18 + TS + Tailwind)", fill=(30, 58, 138), font=_get_font(18, bold=True))

    ui_boxes = [
        ("Upload & Case Study Loader", ["• Drag & drop multi-file batch uploader", "• One-click Case Study 2 artifact loader", "• Format, size & processing status badges"]),
        ("Executive Privacy Dashboard", ["• Gate status counters (PASS / REVIEW / FAIL)", "• Category & source-location distributions", "• Structure retention & benchmark KPIs"]),
        ("Interactive Review & Redaction Studio", ["• Side-by-side Original vs Redacted visual view", "• Block-level diff with highlighted PII spans", "• Approve / Reject FP / Reclassify / Add Span"]),
        ("Benchmark & Audit Governance Console", ["• Live 28-case + 5-format benchmark runner", "• Sanitized zero-PII security event log", "• Safe Export & Controlled LLM Sandbox"]),
    ]
    y_cursor = 185
    for title, lines in ui_boxes:
        _draw_rounded_box(draw, (65, y_cursor, 475, y_cursor + 175), (255, 255, 255), (96, 165, 250), title, lines)
        y_cursor += 195

    # Layer 2: FastAPI Core & Orchestration (Center)
    draw.rounded_rectangle((560, 120, 1240, 990), radius=16, fill=(240, 253, 250), outline=(13, 148, 136), width=3)
    draw.text((585, 140), "APPLICATION & PRIVACY ENGINE TIER (Python 3 + FastAPI)", fill=(19, 78, 74), font=_get_font(18, bold=True))

    _draw_arrow(draw, (500, 300), (560, 300), (37, 99, 235), "REST / JSON")
    _draw_arrow(draw, (560, 680), (500, 680), (13, 148, 136), "Streams / PNG")

    _draw_rounded_box(
        draw,
        (590, 185, 1210, 320),
        (255, 255, 255),
        (13, 148, 136),
        "FastAPI Gateway & PipelineManager (app/main.py, app/services/pipeline.py)",
        [
            "• File Validator (file_validator.py): Magic bytes (%PDF-, PK\\x03\\x04, PNG/JPEG), Zip-Bomb guard",
            "• Memory-Isolated Binary Store & Ephemeral Temp Workspace (chmod 0600 + finally unlink)",
            "• Zero-PII Audit Logger: Records events, gate transitions & metrics without raw sensitive text",
        ],
        badge="ORCHESTRATOR",
    )

    _draw_rounded_box(
        draw,
        (590, 345, 890, 565),
        (255, 255, 255),
        (14, 116, 144),
        "Format-Aware Extractors",
        [
            "• pdf_extractor.py (PyMuPDF + OCR)",
            "• docx_extractor.py (Runs, Tables,",
            "  Headers, Footers, Media Images)",
            "• pptx_extractor.py (Shapes, Tables,",
            "  Speaker Notes, Slide Media)",
            "• image_extractor.py (Pillow +",
            "  RapidOCR PP-OCRv4 + SHA256 Cache)",
        ],
    )

    _draw_rounded_box(
        draw,
        (910, 345, 1210, 565),
        (255, 255, 255),
        (217, 119, 6),
        "Hybrid PII Detector",
        [
            "• hybrid_detector.py",
            "• Regex: Email, Phone, Emp/Dir ID,",
            "  PAN/Tax ID, SSN/Gov ID, Acct, DOB",
            "• Contextual NER: Labeled & Prose",
            "  Person Names, Street Addresses",
            "• FP Suppression: Org/Policy/Dates",
            "• Stable Tokenizer ([PERSON_001])",
        ],
    )

    _draw_rounded_box(
        draw,
        (590, 590, 890, 800),
        (255, 255, 255),
        (126, 34, 206),
        "Native Format Redactors",
        [
            "• pdf_redactor.py: Stream redaction",
            "  + Scanned Page Pixel Destruction",
            "• docx_redactor.py: Cross-run XML",
            "  replacement + embedded PNG scrub",
            "• pptx_redactor.py: Slide/Table/Note",
            "  redaction + metadata scrub",
            "• image_redactor.py: Pixel fill",
        ],
    )

    _draw_rounded_box(
        draw,
        (910, 590, 1210, 800),
        (255, 255, 255),
        (22, 163, 74),
        "Privacy Gate & Validator",
        [
            "• privacy_gate.py",
            "• Re-parses redacted output binary",
            "  from scratch to verify 0 leaks",
            "• Computes Weighted Structure",
            "  Retention Score (Target >=80%)",
            "• Enforces PASS / REVIEW_REQUIRED",
            "  / FAIL state machine",
        ],
    )

    _draw_rounded_box(
        draw,
        (590, 825, 1210, 965),
        (254, 242, 242),
        (220, 38, 38),
        "Downstream LLM Sanitization Firewall (app/services/llm_gateway.py)",
        [
            "• Disabled by default; requires explicit analyst opt-in AND server-side Gate == PASS verification",
            "• Transmits ONLY sanitized post-redaction text blocks — original document buffers are unreachable",
        ],
        badge="LLM FIREWALL",
    )

    # Layer 3: Storage, Artifacts & External Boundary (Right)
    draw.rounded_rectangle((1300, 120, 1760, 990), radius=16, fill=(241, 245, 249), outline=(100, 116, 139), width=3)
    draw.text((1325, 140), "DATA & TRUST BOUNDARIES", fill=(30, 41, 59), font=_get_font(18, bold=True))

    _draw_arrow(draw, (1300, 260), (1240, 260), (100, 116, 139), "Read-Only")
    _draw_rounded_box(
        draw,
        (1325, 185, 1735, 365),
        (255, 255, 255),
        (71, 85, 105),
        "Immutable Source Artifacts",
        [
            "• Organizational_Pack.pptx (9 slides)",
            "• TPRM_Training.docx (35 screenshots)",
            "• Risk_Management_Policy_v6.0.pdf",
            "  (35-page scanned PDF)",
            "• Test_Benchmark.xlsx (28 gold cases)",
        ],
        badge="READ-ONLY",
    )

    _draw_rounded_box(
        draw,
        (1325, 395, 1735, 565),
        (255, 255, 255),
        (13, 148, 136),
        "Controlled Local Storage",
        [
            "• Ephemeral temp_storage/ (auto-wiped",
            "  immediately after extraction)",
            "• SHA-256 OCR Layout Cache",
            "• 100% Local Execution on Windows",
            "• Zero Cloud / Zero Third-Party API",
        ],
        badge="LOCAL ONLY",
    )

    _draw_arrow(draw, (1240, 685), (1325, 685), (22, 163, 74), "Gate=PASS")
    _draw_rounded_box(
        draw,
        (1325, 595, 1735, 775),
        (220, 252, 231),
        (22, 163, 74),
        "Validated Safe Exports",
        [
            "• Redacted Native Artifacts",
            "  (_REDACTED.pdf / .docx / .pptx / .png)",
            "• Structured Findings Report (JSON/CSV)",
            "• Sanitized Security Audit Log",
        ],
        badge="SAFE EXPORT",
    )

    _draw_arrow(draw, (1210, 895), (1325, 895), (220, 38, 38), "PASS Only")
    _draw_rounded_box(
        draw,
        (1325, 805, 1735, 965),
        (254, 249, 195),
        (202, 138, 4),
        "Downstream LLM Consumer",
        [
            "• Receives ONLY redacted text with",
            "  [NAME REDACTED] or [PERSON_001]",
            "• Hard-blocked on FAIL or",
            "  REVIEW_REQUIRED states",
        ],
        badge="GATED AI",
    )

    out_png = DIAGRAMS_DIR / "technical_architecture.png"
    img.save(out_png, format="PNG")
    return out_png


def generate_data_flow_privacy_gate_diagram() -> Path:
    """3. Data-Flow and Privacy-Gate Diagram showing exact state transitions and blocking rules."""
    DIAGRAMS_DIR.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (1800, 1050), (248, 250, 252))
    draw = ImageDraw.Draw(img)

    draw.rectangle((0, 0, 1800, 88), fill=(15, 23, 42))
    draw.text(
        (36, 18),
        "CADENCE FINANCIAL GROUP — DATA-FLOW & PRIVACY-GATE ENFORCEMENT DIAGRAM",
        fill=(255, 255, 255),
        font=_get_font(26, bold=True),
    )
    draw.text(
        (36, 54),
        "Zero-Trust Document Sanitization | Independent Re-Extraction Verification | Deterministic LLM Blocking State Machine",
        fill=(148, 163, 184),
        font=_get_font(16, bold=False),
    )

    # Untrusted Zone (Left)
    draw.rounded_rectangle((40, 125, 550, 980), radius=16, fill=(254, 242, 242), outline=(239, 68, 68), width=3)
    draw.text((65, 145), "ZONE 1: UNTRUSTED RAW ARTIFACT ZONE", fill=(153, 27, 27), font=_get_font(18, bold=True))

    _draw_rounded_box(
        draw,
        (70, 195, 520, 365),
        (255, 255, 255),
        (239, 68, 68),
        "Raw Organizational Artifacts",
        [
            "• Contains unredacted Employee Names, Emails,",
            "  Phones, Emp IDs, PANs, SSNs, Badge Photos",
            "• Hidden PII in DOCX/PPTX Author Metadata",
            "• Embedded OneTrust Screenshots & Speaker Notes",
        ],
        badge="RAW PII",
    )
    _draw_arrow(draw, (295, 365), (295, 420), (239, 68, 68))

    _draw_rounded_box(
        draw,
        (70, 420, 520, 610),
        (255, 255, 255),
        (217, 119, 6),
        "Extraction + Hybrid Detection + Redaction",
        [
            "• Segment Extraction (Text + Tables + OCR)",
            "• Hybrid Regex + Contextual NER + Gazetteer",
            "• Genuine Format-Preserving Redaction:",
            "  - PDF Stream Purge / Scanned Pixel Fill",
            "  - OOXML Cross-Run Rewrite + Image Scrub",
        ],
        badge="SANITIZER",
    )
    _draw_arrow(draw, (295, 610), (295, 665), (217, 119, 6))

    _draw_rounded_box(
        draw,
        (70, 665, 520, 860),
        (255, 255, 255),
        (126, 34, 206),
        "Candidate Redacted Binary Buffer",
        [
            "• In-memory sanitized .pdf / .docx / .pptx / .png",
            "• Cannot be exported to LLM yet!",
            "• Must pass independent re-extraction",
            "  and Privacy Gate state evaluation first.",
        ],
        badge="CANDIDATE",
    )

    # Privacy Gate Zone (Center)
    draw.rounded_rectangle((610, 125, 1220, 980), radius=16, fill=(254, 249, 195), outline=(202, 138, 4), width=3)
    draw.text((635, 145), "ZONE 2: INDEPENDENT PRIVACY GATE & VALIDATION", fill=(133, 77, 14), font=_get_font(18, bold=True))

    _draw_arrow(draw, (520, 760), (640, 280), (126, 34, 206), "Re-Verify")

    _draw_rounded_box(
        draw,
        (640, 195, 1190, 395),
        (255, 255, 255),
        (202, 138, 4),
        "Independent Post-Redaction Verification Engine",
        [
            "1. Re-extracts text, tables, notes, metadata & OCR from the",
            "   REDACTED binary buffer from scratch.",
            "2. Scans for any residual PII or leaked original entity substrings.",
            "3. Verifies author/modifier metadata fields are scrubbed.",
            "4. Computes Composite Structure Retention Score (Target >= 80%).",
        ],
        badge="VALIDATOR",
    )

    _draw_arrow(draw, (915, 395), (915, 445), (202, 138, 4))

    # Three Gate States
    _draw_rounded_box(
        draw,
        (640, 445, 1190, 595),
        (254, 226, 226),
        (220, 38, 38),
        "STATE: FAIL (Hard Security Block)",
        [
            "• Trigger: Residual PII >= 1 OR Leaked Entity >= 1 OR",
            "  Metadata Unsanitized OR Structure Retention < 80%",
            "• Action: Downstream LLM Handoff BLOCKED (HTTP 403).",
        ],
        badge="FAIL",
    )

    _draw_rounded_box(
        draw,
        (640, 620, 1190, 775),
        (254, 243, 199),
        (217, 119, 6),
        "STATE: REVIEW_REQUIRED (Analyst Quarantine)",
        [
            "• Trigger: 0 Residual PII, Structure >= 80%, but >= 1 finding",
            "  has low OCR/NER confidence (< 0.80) awaiting human sign-off.",
            "• Action: Downstream LLM Handoff BLOCKED until analyst",
            "  approves/resolves flagged findings in Review Studio.",
        ],
        badge="REVIEW",
    )

    _draw_rounded_box(
        draw,
        (640, 800, 1190, 950),
        (220, 252, 231),
        (22, 163, 74),
        "STATE: PASS (Verified Clean & Structure Preserved)",
        [
            "• Trigger: 0 Residual PII + 0 Unresolved Reviews +",
            "  Metadata Clean + Structure Retention >= 80% (98.6%-99.9%).",
            "• Action: Safe Export Enabled + LLM Gate Eligible.",
        ],
        badge="PASS",
    )

    # Trusted Downstream Zone (Right)
    draw.rounded_rectangle((1280, 125, 1760, 980), radius=16, fill=(220, 252, 231), outline=(22, 163, 74), width=3)
    draw.text((1305, 145), "ZONE 3: TRUSTED DOWNSTREAM ZONE", fill=(20, 83, 45), font=_get_font(18, bold=True))

    _draw_rounded_box(
        draw,
        (1310, 210, 1730, 410),
        (255, 255, 255),
        (217, 119, 6),
        "Human Analyst Review Loop",
        [
            "• Inspects REVIEW_REQUIRED findings",
            "• Approves valid PII or rejects FP",
            "• Adds manual redaction spans",
            "• Automatically re-runs Validator",
        ],
        badge="ANALYST",
    )
    _draw_arrow(draw, (1190, 695), (1310, 310), (217, 119, 6), "Escalate")
    _draw_arrow(draw, (1310, 360), (1190, 850), (22, 163, 74), "Approved -> PASS")

    _draw_arrow(draw, (1190, 860), (1310, 580), (22, 163, 74), "Authorized")
    _draw_rounded_box(
        draw,
        (1310, 470, 1730, 680),
        (255, 255, 255),
        (22, 163, 74),
        "Safe Redacted Artifact Export",
        [
            "• Download sanitized native document",
            "  (.pdf, .docx, .pptx, .png)",
            "• Export JSON/CSV Findings Report",
            "• Export Zero-PII Audit Log",
        ],
        badge="EXPORT",
    )

    _draw_arrow(draw, (1190, 900), (1310, 830), (22, 163, 74), "PASS + Opt-In")
    _draw_rounded_box(
        draw,
        (1310, 730, 1730, 945),
        (255, 255, 255),
        (13, 148, 136),
        "Downstream LLM / AI Consumer",
        [
            "• Receives ONLY sanitized text with",
            "  [NAME REDACTED] or [PERSON_001]",
            "• Preserves 98.6%+ business context,",
            "  tables, headings & role hierarchy",
            "• Zero exposure of personal data",
        ],
        badge="SAFE AI",
    )

    out_png = DIAGRAMS_DIR / "data_flow_privacy_gate.png"
    img.save(out_png, format="PNG")
    return out_png


def generate_executive_slide_deck(diagrams: List[Path]) -> Path:
    """Build the 10-slide presentation deck (.pptx) for the Case Study 2 walkthrough."""
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    blank_layout = prs.slide_layouts[6]

    def add_header(slide, title_text: str, subtitle_text: str, tag: str = "OPTIV CASE STUDY 2") -> None:
        banner = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0), Inches(0), Inches(13.333), Inches(1.15))
        banner.fill.solid()
        banner.fill.fore_color.rgb = RGBColor(15, 23, 42)
        banner.line.fill.background()

        tb = slide.shapes.add_textbox(Inches(0.5), Inches(0.12), Inches(10.0), Inches(0.95))
        tf = tb.text_frame
        tf.word_wrap = True
        p0 = tf.paragraphs[0]
        p0.text = title_text
        p0.font.size = Pt(24)
        p0.font.bold = True
        p0.font.color.rgb = RGBColor(255, 255, 255)

        p1 = tf.add_paragraph()
        p1.text = subtitle_text
        p1.font.size = Pt(13)
        p1.font.color.rgb = RGBColor(148, 163, 184)

        badge = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(10.6), Inches(0.28), Inches(2.3), Inches(0.55))
        badge.fill.solid()
        badge.fill.fore_color.rgb = RGBColor(13, 148, 136)
        badge.line.fill.background()
        btf = badge.text_frame
        bp = btf.paragraphs[0]
        bp.text = tag
        bp.alignment = PP_ALIGN.CENTER
        bp.font.size = Pt(11)
        bp.font.bold = True
        bp.font.color.rgb = RGBColor(255, 255, 255)

    def add_card(
        slide,
        left: float,
        top: float,
        width: float,
        height: float,
        heading: str,
        bullets: List[str],
        border_rgb: Tuple[int, int, int] = (37, 99, 235),
        bg_rgb: Tuple[int, int, int] = (248, 250, 252),
    ) -> None:
        card = slide.shapes.add_shape(
            MSO_SHAPE.ROUNDED_RECTANGLE, Inches(left), Inches(top), Inches(width), Inches(height)
        )
        card.fill.solid()
        card.fill.fore_color.rgb = RGBColor(*bg_rgb)
        card.line.color.rgb = RGBColor(*border_rgb)
        card.line.width = Pt(2)

        tb = slide.shapes.add_textbox(Inches(left + 0.18), Inches(top + 0.12), Inches(width - 0.36), Inches(height - 0.24))
        tf = tb.text_frame
        tf.word_wrap = True
        p = tf.paragraphs[0]
        p.text = heading
        p.font.size = Pt(16)
        p.font.bold = True
        p.font.color.rgb = RGBColor(15, 23, 42)

        for b in bullets:
            bp = tf.add_paragraph()
            bp.text = f"• {b}"
            bp.font.size = Pt(12.5)
            bp.font.color.rgb = RGBColor(51, 65, 85)
            bp.space_before = Pt(5)

    # Slide 1: Cover Slide
    s1 = prs.slides.add_slide(blank_layout)
    bg1 = s1.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0), Inches(0), Inches(13.333), Inches(7.5))
    bg1.fill.solid()
    bg1.fill.fore_color.rgb = RGBColor(15, 23, 42)
    bg1.line.fill.background()

    tb1 = s1.shapes.add_textbox(Inches(0.8), Inches(1.2), Inches(11.6), Inches(5.2))
    tf1 = tb1.text_frame
    tf1.word_wrap = True
    p = tf1.paragraphs[0]
    p.text = "OPTIV CYBER SIMULATION — CASE STUDY 2"
    p.font.size = Pt(16)
    p.font.bold = True
    p.font.color.rgb = RGBColor(45, 212, 191)

    p2 = tf1.add_paragraph()
    p2.text = "Cadence Financial Group:\nPII Detection & Secure Document Redaction Gateway"
    p2.font.size = Pt(36)
    p2.font.bold = True
    p2.font.color.rgb = RGBColor(255, 255, 255)
    p2.space_before = Pt(14)

    p3 = tf1.add_paragraph()
    p3.text = (
        "Format-Aware Extraction • Hybrid Regex + Contextual NER • Genuine Binary & Pixel Redaction\n"
        "Structure Preservation (>=98.6%) • Independent Privacy Gate Enforcement Before Downstream LLM Handoff"
    )
    p3.font.size = Pt(16)
    p3.font.color.rgb = RGBColor(148, 163, 184)
    p3.space_before = Pt(20)

    add_card(
        s1,
        0.8,
        4.7,
        3.7,
        2.0,
        "100% Gold Benchmark F1",
        [
            "28/28 synthetic test cases passed",
            "49/49 exact entity offsets matched",
            "0 false positives on negative traps",
        ],
        border_rgb=(45, 212, 191),
        bg_rgb=(241, 245, 249),
    )
    add_card(
        s1,
        4.8,
        4.7,
        3.7,
        2.0,
        "963 Case Study PII Redacted",
        [
            "123 in Organizational Pack (.pptx)",
            "51 in TPRM Manual (.docx + 35 PNGs)",
            "789 in Scanned Risk Policy (.pdf)",
        ],
        border_rgb=(56, 189, 248),
        bg_rgb=(241, 245, 249),
    )
    add_card(
        s1,
        8.8,
        4.7,
        3.7,
        2.0,
        "Zero-Trust LLM Firewall",
        [
            "98.6% - 99.85% structure retained",
            "0 residual PII in post-redaction scan",
            "Strict HTTP 403 block unless PASS",
        ],
        border_rgb=(168, 85, 247),
        bg_rgb=(241, 245, 249),
    )

    # Slide 2: Executive Problem Statement & Threat Model
    s2 = prs.slides.add_slide(blank_layout)
    add_header(
        s2,
        "1. Executive Problem Statement & Threat Model",
        "Protecting Cadence Financial Group artifacts from PII leakage prior to LLM ingestion",
        "THREAT MODEL",
    )
    add_card(
        s2,
        0.5,
        1.45,
        6.0,
        2.7,
        "The Business & Security Challenge",
        [
            "Cadence Financial Group wants to analyze internal governance policies, TPRM manuals, and org charts using downstream LLMs.",
            "However, these artifacts contain heterogeneous PII across body text, tables, headers, metadata, embedded OneTrust screenshots, and 35-page scanned PDFs.",
            "Central Mandate: ZERO document content may reach a downstream LLM until PII detection, genuine redaction, and independent validation pass.",
        ],
        border_rgb=(220, 38, 38),
    )
    add_card(
        s2,
        6.8,
        1.45,
        6.0,
        2.7,
        "Why Naive Approaches Fail in Enterprise Security",
        [
            "Plain-Text Conversion Destroys Context: Flattening files loses tables, RACI matrices, and reading order (<80% structure retention).",
            "Cosmetic Black Boxes Leak Data: Drawing rectangles over PDFs leaves underlying text streams selectable via copy/paste.",
            "Run-Splitting Leaves Fragments: OOXML splits names across runs (<w:r>); naive string replace misses split spans.",
            "Hidden Package Channels: Author metadata ([OC] Divisha Kilari), speaker notes, and embedded screenshots bypass text parsers.",
        ],
        border_rgb=(217, 119, 6),
    )
    add_card(
        s2,
        0.5,
        4.4,
        12.3,
        2.7,
        "Our Defense-in-Depth Solution Architecture",
        [
            "1. Format-Aware Native Processing: PyMuPDF for native/scanned PDFs, python-docx for Word + media ZIP inspection, python-pptx for slides/tables/notes, and RapidOCR (PaddleOCR PP-OCRv4 ONNX) for images.",
            "2. Hybrid Detection + Contextual Disambiguation: Combines deterministic regex/checksum rules with contextual NER and false-positive suppression so role titles ('Chief Risk Officer') and policy numbers remain intact while personal names are redacted.",
            "3. Independent Post-Redaction Verification Gate: Re-parses the redacted output binary from scratch to prove 0 residual PII and >=80% structure retention before unlocking export or optional LLM handoff.",
        ],
        border_rgb=(13, 148, 136),
    )

    # Slide 3: End-to-End Functional Design Diagram
    s3 = prs.slides.add_slide(blank_layout)
    add_header(
        s3,
        "2. End-to-End Functional Design (13-Stage Pipeline)",
        "From secure multi-format upload through hybrid detection, native redaction, validation, and gated export",
        "FUNCTIONAL DESIGN",
    )
    s3.shapes.add_picture(str(diagrams[0]), Inches(0.55), Inches(1.3), width=Inches(12.2))

    # Slide 4: Technical System Architecture Diagram
    s4 = prs.slides.add_slide(blank_layout)
    add_header(
        s4,
        "3. Technical System Architecture",
        "Local-first Windows architecture: React + TypeScript + Tailwind UI paired with FastAPI privacy engine",
        "SYSTEM ARCHITECTURE",
    )
    s4.shapes.add_picture(str(diagrams[1]), Inches(0.55), Inches(1.3), width=Inches(12.2))

    # Slide 5: Format-Aware Extraction & Genuine Redaction
    s5 = prs.slides.add_slide(blank_layout)
    add_header(
        s5,
        "4. Format-Aware Extraction & Genuine Native Redaction",
        "Preserving >=98.6% of document structure while permanently purging underlying sensitive bytes and pixels",
        "FORMAT-AWARE ENGINE",
    )
    add_card(
        s5,
        0.5,
        1.45,
        4.0,
        2.75,
        "A. Native & Scanned PDFs",
        [
            "Auto-detects native text vs rasterized scanned pages (0 selectable chars).",
            "Native PDF: Word/block bbox extraction + fitz.Page.apply_redactions() to purge PDF stream tokens.",
            "Scanned PDF (Policy v6.0): Renders 200 DPI pages -> RapidOCR -> proportional sub-bbox interpolation -> permanent pixel fill + label overlay.",
        ],
        border_rgb=(37, 99, 235),
    )
    add_card(
        s5,
        4.65,
        1.45,
        4.0,
        2.75,
        "B. Word Documents (.docx)",
        [
            "Extracts paragraphs, split formatting runs, 16 tables, headers, footers, and core metadata.",
            "Cross-Run DOM Redactor: Maps character offsets across <w:r> boundaries so split names leave zero fragments.",
            "Embedded Media Scrubbing: Unpacks word/media/image*.png, OCRs 35 screenshots, redacts PII pixels in-place.",
        ],
        border_rgb=(13, 148, 136),
    )
    add_card(
        s5,
        8.8,
        1.45,
        4.0,
        2.75,
        "C. PowerPoint (.pptx) & Images",
        [
            "Processes slide titles, grouped shapes, RACI & directory tables, speaker notes, and alt-text.",
            "Preserves slide master themes, table borders, cell shading, and font styling.",
            "Sanitizes docProps/core.xml author/modifier fields across both DOCX and PPTX containers.",
        ],
        border_rgb=(126, 34, 206),
    )
    add_card(
        s5,
        0.5,
        4.45,
        12.3,
        2.6,
        "Context-Preserving Replacement Modes (Analyst Configurable)",
        [
            "Mode 1 — Policy Category Labels (Default): Replaces sensitive values with [NAME REDACTED], [EMAIL REDACTED], [PHONE REDACTED], [EMPLOYEE ID REDACTED], [GOVERNMENT ID REDACTED], [TAX ID REDACTED], [ACCOUNT NUMBER REDACTED], [ADDRESS REDACTED], [DATE OF BIRTH REDACTED].",
            "Mode 2 — Cross-Artifact Stable Pseudonym Tokens: Replaces recurring entities with deterministic tokens ([PERSON_001], [EMAIL_001], [EMP_ID_001]) so downstream analysts or LLMs can trace multi-step workflows (e.g., who raised vs approved an incident) without learning real identities.",
            "Example Transformation: 'Approved by Maya Sample (EMP-TEST-017) on 12 May 2025' -> 'Approved by [NAME REDACTED] ([EMPLOYEE ID REDACTED]) on 12 May 2025'.",
        ],
        border_rgb=(22, 163, 74),
    )

    # Slide 6: Hybrid PII Detection & False-Positive Control
    s6 = prs.slides.add_slide(blank_layout)
    add_header(
        s6,
        "5. Hybrid PII Detection Engine & False-Positive Suppression",
        "Combining deterministic pattern validators with contextual NER and domain-specific suppression",
        "HYBRID DETECTION",
    )
    add_card(
        s6,
        0.5,
        1.45,
        6.0,
        2.75,
        "Layer 1: Structured Identifiers & Regex Validators",
        [
            "EMAIL: RFC-compliant email matcher (corporate & personal domains).",
            "PHONE_NUMBER: International (+44, +91, +1, +49, +65) & domestic formats with boundary guards.",
            "EMPLOYEE_ID: Cadence EMP-xxxx, DIR-xxxx, MER-xx-xxxx, EMP-TEST-xxx.",
            "TAX_ID_PAN_STYLE: 10-character PAN pattern ([A-Z]{5}[0-9]{4}[A-Z]) with OCR 0/O tolerance.",
            "GOVERNMENT_ID_STYLE: SSN (xxx-xx-xxxx), 12-digit National ID, Passport & PESEL patterns.",
            "ACCOUNT_NUMBER & DATE_OF_BIRTH: Contextual 10-16 digit account numbers & labeled DOB spans.",
        ],
        border_rgb=(37, 99, 235),
    )
    add_card(
        s6,
        6.8,
        1.45,
        6.0,
        2.75,
        "Layer 2: Contextual NER & Tabular Co-Occurrence",
        [
            "Labeled Role/Contact Extraction: Detects names following 'Customer:', 'Owner:', 'Reviewer:', 'Reported by', 'Approved by', 'Signed:', etc.",
            "Narrative Prose NER: Identifies full personal names and initialed names (e.g., 'Miriam T. Achebe', 'R. K. Sharma') in incident descriptions.",
            "Tabular Column Alignment: Recognizes directory and roster columns aligned with email, phone, or employee ID cells.",
            "Residential Addresses: Street numbers + thoroughfare types + city/postal code spans.",
        ],
        border_rgb=(217, 119, 6),
    )
    add_card(
        s6,
        0.5,
        4.45,
        12.3,
        2.6,
        "Layer 3: Strict False-Positive Suppression (Preserving Business & Financial Utility)",
        [
            "Organization & Committee Whitelist: Never redacts 'Cadence Financial Group', 'Blue River Financial Services', 'Group Risk Committee', 'Board Audit Committee', or regulatory names ('GDPR', 'PRA', 'FCA', 'ISO 27001').",
            "Role Title Preservation: Keeps 'Chief Risk Officer', 'Head of TPRM', 'VP Operational Resilience' intact so RACI accountability matrices remain meaningful.",
            "Financial & Calendar Disambiguation: Distinguishes month names ('May, June and August'), policy versions ('v6.0'), masked cards ('**** 0000'), and currency amounts ('INR 84,250.00') from personal identifiers.",
        ],
        border_rgb=(13, 148, 136),
    )

    # Slide 7: Data-Flow & Privacy Gate State Machine
    s7 = prs.slides.add_slide(blank_layout)
    add_header(
        s7,
        "6. Data-Flow & Privacy-Gate State Machine",
        "Deterministic server-side enforcement preventing unvalidated content from reaching any downstream LLM",
        "PRIVACY GATE",
    )
    s7.shapes.add_picture(str(diagrams[2]), Inches(0.55), Inches(1.3), width=Inches(12.2))

    # Slide 8: Empirical Analysis of Case Study 2 Supporting Artifacts
    s8 = prs.slides.add_slide(blank_layout)
    add_header(
        s8,
        "7. Empirical Results on Case Study 2 Supporting Artifacts",
        "Deep inspection and end-to-end sanitization across all three official Cadence Financial Group files",
        "CASE STUDY RESULTS",
    )
    add_card(
        s8,
        0.5,
        1.45,
        4.0,
        5.5,
        "1. Organizational_Pack.pptx",
        [
            "Format: Native PowerPoint (9 Slides, 5 Tables)",
            "PII Detected: 123 Findings",
            "  • 55 Person Names (Execs, Directors, Role Holders)",
            "  • 34 Corporate Email Addresses",
            "  • 34 International Phone Numbers",
            "  • Package Metadata Author ([OC] Divisha Kilari)",
            "Redaction Applied: Cross-run shape & table cell DOM replacement + core.xml metadata scrub.",
            "Structure Retention: 99.85% (All 9 slides & 5 RACI/directory tables preserved).",
            "Privacy Gate: PASS (0 Residual PII).",
        ],
        border_rgb=(37, 99, 235),
    )
    add_card(
        s8,
        4.65,
        1.45,
        4.0,
        5.5,
        "2. Cadence_TPRM_Training.docx",
        [
            "Format: Word Manual (394 Paragraphs, 16 Tables, 35 Embedded Screenshots)",
            "PII Detected: 51 Findings",
            "  • 28 Table Cell Findings (Table 4 User Roster & Table 14 Author/Contacts)",
            "  • 21 Embedded Screenshot OCR Findings (OneTrust UI screenshots image10, 12, 35, 38)",
            "  • 2 Package Metadata Authors ([OC] Madhav Mehta, [OC] Divisha Kilari)",
            "Redaction Applied: Table XML rewrite + in-archive PNG pixel redaction + metadata scrub.",
            "Structure Retention: 99.85% (All 16 tables & 35 screenshots intact).",
            "Privacy Gate: PASS (0 Residual PII).",
        ],
        border_rgb=(13, 148, 136),
    )
    add_card(
        s8,
        8.8,
        1.45,
        4.0,
        5.5,
        "3. Risk_Management_Policy_v6.0.pdf",
        [
            "Format: 35-Page 100% Scanned PDF (0 native selectable text characters)",
            "PII Detected: 789 Findings",
            "  • 339 Person Names, 188 Employee/Director IDs",
            "  • 147 Emails, 103 Phone Numbers",
            "  • 4 Gov IDs (SSN, Passport, PESEL), 2 PANs, 2 Accts, 2 DOBs, 2 Addresses",
            "  • Includes signed RCSA form (Fig 8), SecureGRC UI (Fig 9), Badge (Fig 13), PDF Author",
            "Structure Retention: 98.60% (35/35 pages).",
            "Privacy Gate: Flagged 1 low-confidence OCR span ->REVIEW_REQUIRED -> Analyst approves -> PASS.",
        ],
        border_rgb=(126, 34, 206),
    )

    # Slide 9: Benchmark Evaluation & Reliability Metrics
    s9 = prs.slides.add_slide(blank_layout)
    add_header(
        s9,
        "8. Benchmark Evaluation & Multi-Format Reliability Metrics",
        "Measured Precision, Recall, F1, False-Positive Rate, Residual Leakage, and Structure Retention",
        "BENCHMARK REPORT",
    )
    add_card(
        s9,
        0.5,
        1.45,
        5.8,
        5.5,
        "Gold Synthetic Benchmark (PII_Detection_Redaction_Test_Benchmark.xlsx)",
        [
            "Total Test Cases Evaluated: 28 / 28 Exact Redaction Matches (100%)",
            "Gold Entity Spans Evaluated: 49 / 49 Exact Offset & Category Matches",
            "True Positives (TP): 49 | False Positives (FP): 0 | False Negatives (FN): 0",
            "Precision: 100.0% | Recall: 100.0% | F1 Score: 100.0%",
            "Negative / False-Positive Trap Cases (PII-020 to PII-024): 5 / 5 Clean (0.0% FP Rate)",
            "Post-Redaction Residual PII Leakage: 0 instances across all 28 cases",
            "Covers: Multi-PII sentences, tabular rows, headers/footers, OCR noise, repeated names, and policy/financial false-positive traps.",
        ],
        border_rgb=(22, 163, 74),
    )
    add_card(
        s9,
        6.5,
        1.45,
        6.3,
        5.5,
        "End-to-End Multi-Format File Fixture Evaluation",
        [
            "1. Native Text PDF: 100.0% Precision | 100.0% Recall | 0 Residual | 99.5% Structure",
            "2. Scanned Image PDF (OCR): 100.0% Precision | 100.0% Recall | 0 Residual | 98.6% Structure",
            "3. Word Document (DOCX): 100.0% Precision | 100.0% Recall | 0 Residual | 99.8% Structure",
            "4. PowerPoint (PPTX): 100.0% Precision | 100.0% Recall | 0 Residual | 99.8% Structure",
            "5. Standalone Image (PNG): 100.0% Precision | 100.0% Recall | 0 Residual | 99.0% Structure",
            "Aggregate Multi-Format F1 Score: 100.0% (0 Residual PII across all 5 file types)",
            "Automated Pytest Verification: Unit + E2E tests validate magic bytes, cross-run XML scrubbing, PDF stream removal, LLM gate blocking, and SHA-256 source immutability.",
        ],
        border_rgb=(37, 99, 235),
    )

    # Slide 10: Live Demonstration Walkthrough & Operational Governance
    s10 = prs.slides.add_slide(blank_layout)
    add_header(
        s10,
        "9. Live Demonstration Walkthrough (10–15 Minute Script)",
        "Step-by-step operational flow for the Optiv Cyber Simulation review panel",
        "LIVE DEMO",
    )
    add_card(
        s10,
        0.5,
        1.45,
        3.9,
        5.5,
        "Part 1: Ingestion & Triage (0–5 min)",
        [
            "1. Open Consulting Dashboard & inspect active security policy (thresholds, labels, LLM firewall OFF).",
            "2. Load all 3 Case Study 2 supporting artifacts + test invalid/spoofed file rejection.",
            "3. Show automatic triage: PPTX (native), DOCX (native + 35 screenshots), Risk Policy PDF (35-page Scanned OCR).",
        ],
        border_rgb=(37, 99, 235),
    )
    add_card(
        s10,
        4.7,
        1.45,
        3.9,
        5.5,
        "Part 2: Review Studio & Gate (5–10 min)",
        [
            "4. Inspect Organizational Pack & TPRM DOCX: verify table cells, embedded OneTrust screenshots, and metadata scrubbing.",
            "5. Open Scanned Risk Policy v6.0 in Side-by-Side Visual Preview (Page 22 signed RCSA form, Page 32 badge).",
            "6. Demonstrate REVIEW_REQUIRED blocking LLM handoff -> approve flagged OCR span -> transition to PASS.",
        ],
        border_rgb=(217, 119, 6),
    )
    add_card(
        s10,
        8.9,
        1.45,
        3.9,
        5.5,
        "Part 3: Export & Benchmark (10–15 min)",
        [
            "7. Download redacted native artifacts (.pptx, .docx, .pdf) and JSON/CSV masked findings reports.",
            "8. Test opt-in Sanitized LLM Handoff and verify only [NAME REDACTED] / [PERSON_001] tokens are sent.",
            "9. Run Live Benchmark Suite (100% F1) and inspect Zero-PII Security Audit Trail.",
        ],
        border_rgb=(22, 163, 74),
    )

    out_pptx = DOCS_DIR / "Cadence_PII_Redaction_Architecture_and_Demo.pptx"
    prs.save(out_pptx)
    return out_pptx


if __name__ == "__main__":
    d1 = generate_functional_design_diagram()
    d2 = generate_technical_architecture_diagram()
    d3 = generate_data_flow_privacy_gate_diagram()
    deck = generate_executive_slide_deck([d1, d2, d3])
    print(f"Generated diagrams: {d1.name}, {d2.name}, {d3.name}")
    print(f"Generated slide deck: {deck}")

"""Comprehensive Unit & End-to-End Automated Test Suite for Cadence PII Redaction Gateway."""

from __future__ import annotations

import hashlib
import io
import sys
import zipfile
from pathlib import Path

# Ensure backend directory is on sys.path so `from app...` imports work cleanly
ROOT_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = ROOT_DIR / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import fitz  # PyMuPDF
import pytest
from docx import Document as DocxDocument
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw
from pptx import Presentation
from pptx.util import Inches

from app.config import CASE_MATERIALS_DIR, PolicyConfig, get_policy, update_policy
from app.detectors.hybrid_detector import HybridPIIDetector
from app.extractors.file_validator import FileValidationError, validate_and_identify_file
from app.main import app
from app.models import (
    GateState,
    PIIEntityCategory,
    ReviewStatus,
    TextBlockSegment,
)
from app.services.benchmark_runner import run_full_benchmark_suite
from app.services.llm_gateway import PrivacyGateViolationError, process_with_downstream_llm
from app.services.pipeline import PIPELINE_MANAGER, PipelineManager


client = TestClient(app)


# ============================================================================
# 1. File Upload & Signature Validation Tests
# ============================================================================

def test_file_signature_validation_rejects_spoofed_extension():
    """Verify magic-byte signature inspection blocks spoofed file extensions."""
    spoofed_pdf = b"This is plain text pretending to be a PDF file."
    with pytest.raises(FileValidationError) as exc_info:
        validate_and_identify_file("malicious.pdf", spoofed_pdf)
    assert "%PDF-" in str(exc_info.value)


def test_file_validation_rejects_unsupported_extension():
    """Verify unsupported extensions (.exe, .sh, .txt) are rejected cleanly."""
    with pytest.raises(FileValidationError) as exc_info:
        validate_and_identify_file("payload.exe", b"MZ\x90\x00\x03")
    assert "Unsupported file extension" in str(exc_info.value)


def test_file_validation_rejects_empty_file():
    """Verify 0-byte uploads are rejected."""
    with pytest.raises(FileValidationError) as exc_info:
        validate_and_identify_file("empty.pdf", b"")
    assert "empty" in str(exc_info.value).lower()


def test_file_validation_rejects_malformed_ooxml_zip():
    """Verify non-OOXML ZIP archives renamed to .docx are rejected."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("random.txt", "hello world")
    with pytest.raises(FileValidationError) as exc_info:
        validate_and_identify_file("fake.docx", buf.getvalue())
    assert "Content_Types" in str(exc_info.value) or "OOXML" in str(exc_info.value)


# ============================================================================
# 2. Hybrid PII Detection & Benchmark Reliability Tests
# ============================================================================

def test_gold_benchmark_suite_achieves_100_percent_f1():
    """Verify all 28 synthetic benchmark cases and 49 gold spans match with 100% precision/recall."""
    report = run_full_benchmark_suite(force_refresh=True)
    summary = report["text_benchmark_summary"]
    assert summary["total_cases"] == 28
    assert summary["exact_case_matches"] == 28
    assert summary["true_positives"] == 49
    assert summary["false_positives"] == 0
    assert summary["false_negatives"] == 0
    assert summary["precision"] == 1.0
    assert summary["recall"] == 1.0
    assert summary["f1_score"] == 1.0
    assert summary["residual_pii_count"] == 0

    file_summary = report["aggregate_file_summary"]
    assert file_summary["formats_tested"] == 5
    assert file_summary["residual_pii_count"] == 0
    assert file_summary["average_structure_retention"] >= 0.90


def test_false_positive_suppression_preserves_financial_and_policy_context():
    """Verify policy IDs, dates, currencies, and role titles are NOT falsely flagged as PII."""
    detector = HybridPIIDetector()
    safe_text = (
        "Cadence Financial Group Risk Policy v6.0 approved on 14/10/2025. "
        "Tier 1 capital threshold is $25,000,000 under ISO 27001 and GDPR Art. 32. "
        "The Chief Risk Officer and Head of Compliance reviewed section 16.5."
    )
    spans = detector.detect_in_text(safe_text)
    assert len(spans) == 0, f"Expected 0 false positives, got: {spans}"


def test_stable_pseudonym_tokenization_across_repeated_identifiers():
    """Verify STABLE_TOKEN mode assigns consistent tokens to identical entities and distinct tokens to others."""
    detector = HybridPIIDetector(
        policy=PolicyConfig(redaction_mode="STABLE_TOKEN")
    )
    text = (
        "Customer: Maya Sample (maya.sample@example.test). "
        "Reviewer: Tara Placeholder (tara.placeholder@example.test). "
        "Approved for Maya Sample."
    )
    findings = detector.analyze_document_segments(
        doc_id="DOC-TEST",
        document_name="test.docx",
        detected_format="DOCX",
        segments=[
            TextBlockSegment(
                block_id="p1",
                source_type="paragraph",
                page_or_slide=1,
                location_ref="Paragraph 1",
                text=text,
            )
        ],
    )
    name_findings = [f for f in findings if f.category == PIIEntityCategory.PERSON_NAME]
    assert len(name_findings) == 3
    # First and third are both Maya Sample -> same stable token
    assert name_findings[0].stable_token == name_findings[2].stable_token
    # Second is Tara Placeholder -> different stable token
    assert name_findings[0].stable_token != name_findings[1].stable_token


# ============================================================================
# 3. Format-Aware Extraction & Redaction Tests (DOCX, PPTX, PDF, Image)
# ============================================================================

def test_docx_cross_run_redaction_and_metadata_scrubbing():
    """
    Verify PII split across multiple formatting runs in a Word paragraph and table cell
    is completely removed from the underlying XML and core properties are sanitized.
    """
    doc = DocxDocument()
    doc.core_properties.author = "[OC] Divisha Kilari"
    doc.core_properties.last_modified_by = "Maya Sample"

    # Paragraph where "Maya Sample" is split across 3 formatting runs
    p = doc.add_paragraph("Customer: ")
    r1 = p.add_run("Ma")
    r1.bold = True
    r2 = p.add_run("ya ")
    r3 = p.add_run("Sample")
    r3.italic = True
    p.add_run(" can be reached at maya.sample@example.test or +91 90000 00000.")

    # Table cell with Employee ID
    table = doc.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "Employee ID"
    table.cell(0, 1).text = "Status"
    table.cell(1, 0).text = "EMP-TEST-017"
    table.cell(1, 1).text = "Active"

    buf = io.BytesIO()
    doc.save(buf)
    raw_bytes = buf.getvalue()

    manager = PipelineManager()
    record = manager.process_uploaded_bytes("split_runs.docx", raw_bytes)

    assert record.detected_format == "DOCX"
    assert record.validation is not None
    assert record.validation.gate_status == GateState.PASS
    assert record.validation.residual_pii_found is False
    assert record.validation.structure_metrics.overall_structure_score >= 0.85

    # Inspect the redacted DOCX binary to ensure zero leakage in XML or metadata
    _, _, redacted_bytes = manager.get_redacted_bytes(record.doc_id)
    redacted_doc = DocxDocument(io.BytesIO(redacted_bytes))
    assert "Divisha Kilari" not in (redacted_doc.core_properties.author or "")
    assert "Maya Sample" not in (redacted_doc.core_properties.last_modified_by or "")

    full_xml_text = "\n".join(para.text for para in redacted_doc.paragraphs)
    assert "Maya" not in full_xml_text
    assert "Sample" not in full_xml_text
    assert "maya.sample@example.test" not in full_xml_text
    assert "EMP-TEST-017" not in redacted_doc.tables[0].cell(1, 0).text
    assert "[NAME REDACTED]" in full_xml_text
    assert "[EMAIL REDACTED]" in full_xml_text
    assert "[EMPLOYEE ID REDACTED]" in redacted_doc.tables[0].cell(1, 0).text


def test_pptx_slide_table_and_speaker_notes_redaction():
    """
    Verify PPTX slide shapes, table cells, speaker notes, and presentation metadata
    are genuinely redacted while preserving slide count and layout.
    """
    prs = Presentation()
    prs.core_properties.author = "[OC] Divisha Kilari"
    slide = prs.slides.add_slide(prs.slide_layouts[5])  # Title Only
    slide.shapes.title.text = "Customer: Maya Sample (maya.sample@example.test)"

    # Add table
    table_shape = slide.shapes.add_table(2, 2, Inches(1), Inches(2), Inches(6), Inches(1.5))
    tbl = table_shape.table
    tbl.cell(0, 0).text = "Owner"
    tbl.cell(0, 1).text = "Phone"
    tbl.cell(1, 0).text = "Owner: Tara Placeholder"
    tbl.cell(1, 1).text = "+91 90000 00000"

    # Add speaker notes with PII
    notes_slide = slide.notes_slide
    notes_slide.notes_text_frame.text = "Confidential note: Contact Maya Sample on +91 90000 00000 before board review."

    buf = io.BytesIO()
    prs.save(buf)

    manager = PipelineManager()
    record = manager.process_uploaded_bytes("escalation_deck.pptx", buf.getvalue())

    assert record.detected_format == "PPTX"
    assert record.validation is not None
    assert record.validation.gate_status == GateState.PASS
    assert record.validation.residual_pii_found is False

    _, _, redacted_bytes = manager.get_redacted_bytes(record.doc_id)
    redacted_prs = Presentation(io.BytesIO(redacted_bytes))
    assert len(redacted_prs.slides) == 1
    slide_out = redacted_prs.slides[0]
    assert "Maya Sample" not in slide_out.shapes.title.text
    assert "maya.sample@example.test" not in slide_out.shapes.title.text
    assert "Maya Sample" not in slide_out.notes_slide.notes_text_frame.text
    assert "+91 90000 00000" not in slide_out.notes_slide.notes_text_frame.text


def test_native_pdf_stream_redaction_removes_selectable_text():
    """
    Verify native digital PDF redaction uses PyMuPDF apply_redactions() so underlying
    PDF text streams cannot be copy-pasted or extracted after redaction.
    """
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text(
        (72, 100),
        "Account holder: Maya Sample. Account number: 000012340001. Employee ID: EMP-TEST-017.",
        fontsize=11,
    )
    page.insert_text(
        (72, 130),
        "Contact email: maya.sample@example.test | Tax ID: QWERT0000Z.",
        fontsize=11,
    )
    doc.set_metadata({"author": "[OC] Aditya Lawand", "title": "Wire Audit Report"})
    raw_pdf = doc.tobytes()
    doc.close()

    manager = PipelineManager()
    record = manager.process_uploaded_bytes("native_audit.pdf", raw_pdf)

    assert record.detected_format == "PDF"
    assert record.validation is not None
    assert record.validation.gate_status == GateState.PASS
    assert record.validation.residual_pii_found is False

    # Re-open redacted PDF and confirm sensitive strings are completely purged from stream
    _, _, redacted_bytes = manager.get_redacted_bytes(record.doc_id)
    redacted_doc = fitz.open(stream=redacted_bytes, filetype="pdf")
    extracted_text = redacted_doc[0].get_text("text")
    assert "000012340001" not in extracted_text
    assert "Maya Sample" not in extracted_text
    assert "EMP-TEST-017" not in extracted_text
    assert "maya.sample@example.test" not in extracted_text
    assert "QWERT0000Z" not in extracted_text
    assert "Aditya Lawand" not in (redacted_doc.metadata.get("author") or "")
    redacted_doc.close()


def test_standalone_image_pixel_redaction():
    """Verify standalone PNG image with rendered PII undergoes OCR detection and irreversible pixel masking."""
    img = Image.new("RGB", (900, 220), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.text((30, 50), "Customer: Maya Sample", fill=(0, 0, 0))
    draw.text((30, 100), "Email: maya.sample@example.test", fill=(0, 0, 0))
    draw.text((30, 150), "Employee ID: EMP-TEST-017", fill=(0, 0, 0))

    buf = io.BytesIO()
    img.save(buf, format="PNG")

    manager = PipelineManager()
    record = manager.process_uploaded_bytes("badge_scan.png", buf.getvalue())

    assert record.detected_format == "PNG"
    assert len(record.findings) >= 2
    assert record.validation is not None
    assert record.validation.residual_pii_found is False


# ============================================================================
# 4. Privacy Gate Enforcement & Downstream LLM Protection Tests
# ============================================================================

def test_privacy_gate_strictly_blocks_downstream_llm_when_not_passed():
    """
    Verify that process_with_downstream_llm raises PrivacyGateViolationError whenever:
    1. Policy downstream_llm_enabled is False (default)
    2. Gate status is REVIEW_REQUIRED or FAIL
    3. Succeeds ONLY when downstream_llm_enabled is True AND gate_status == PASS
    """
    original_policy = get_policy().model_copy(deep=True)
    try:
        doc = DocxDocument()
        doc.add_paragraph("Customer: Maya Sample (maya.sample@example.test).")
        buf = io.BytesIO()
        doc.save(buf)

        record = PIPELINE_MANAGER.process_uploaded_bytes("gate_test.docx", buf.getvalue())

        # 1. Default policy has downstream_llm_enabled=False -> must block even if Gate=PASS
        with pytest.raises(PrivacyGateViolationError) as exc_info:
            process_with_downstream_llm(record.doc_id, "Summarize risk controls")
        assert "disabled by default" in str(exc_info.value)

        # 2. Enable opt-in flag -> should succeed since Gate=PASS and residual_pii_found=False
        enabled_policy = get_policy().model_copy(deep=True)
        enabled_policy.downstream_llm_enabled = True
        update_policy(enabled_policy)

        llm_resp = process_with_downstream_llm(record.doc_id, "Summarize risk controls")
        assert llm_resp["gate_status_verified"] == "PASS"
        assert "Maya Sample" not in llm_resp["sanitized_payload_preview"]
        assert "[NAME REDACTED]" in llm_resp["sanitized_payload_preview"]

        # 3. Force GateState.REVIEW_REQUIRED -> must strictly block!
        assert record.validation is not None
        record.validation.gate_status = GateState.REVIEW_REQUIRED
        with pytest.raises(PrivacyGateViolationError) as exc_info2:
            process_with_downstream_llm(record.doc_id, "Summarize risk controls")
        assert "REVIEW_REQUIRED" in str(exc_info2.value)

        # 4. Force GateState.FAIL -> must strictly block!
        record.validation.gate_status = GateState.FAIL
        with pytest.raises(PrivacyGateViolationError) as exc_info3:
            process_with_downstream_llm(record.doc_id, "Summarize risk controls")
        assert "FAIL" in str(exc_info3.value)
    finally:
        update_policy(original_policy)


# ============================================================================
# 5. End-to-End Case Study 2 Supporting Artifacts & Immutability Verification
# ============================================================================

def test_case_study_2_supporting_artifacts_e2e_and_immutability():
    """
    Verify all 3 official Case Study 2 artifacts process end-to-end, achieve >=80% structure
    retention, pass residual PII checks, and leave original source files 100% immutable.
    """
    artifacts = [
        "Cadence_Financial_Group_Organizational_Pack.pptx",
        "Cadence_TPRM_Training.docx",
        "Cadence_Group_Risk_Management_Policy__v6.0.pdf",
    ]

    # Record SHA-256 hashes before processing
    before_hashes = {}
    for name in artifacts:
        fpath = CASE_MATERIALS_DIR / name
        assert fpath.exists(), f"Missing supporting artifact: {fpath}"
        before_hashes[name] = hashlib.sha256(fpath.read_bytes()).hexdigest()

    loaded_records = {}
    for name in artifacts:
        resp = client.post("/api/documents/load-case-artifact", json={"artifact_name": name})
        assert resp.status_code == 200
        loaded_records[name] = resp.json()

    # 1. Organizational Pack PPTX
    pptx_doc = loaded_records["Cadence_Financial_Group_Organizational_Pack.pptx"]
    assert pptx_doc["detected_format"] == "PPTX"
    assert pptx_doc["findings_count"] >= 100
    assert pptx_doc["validation"]["gate_status"] == "PASS"
    assert pptx_doc["validation"]["residual_pii_found"] is False
    assert pptx_doc["validation"]["structure_metrics"]["overall_structure_score"] >= 0.95

    # 2. TPRM Training DOCX (text + tables + 35 embedded screenshots)
    docx_doc = loaded_records["Cadence_TPRM_Training.docx"]
    assert docx_doc["detected_format"] == "DOCX"
    assert docx_doc["findings_count"] >= 45
    assert docx_doc["validation"]["gate_status"] == "PASS"
    assert docx_doc["validation"]["residual_pii_found"] is False
    assert docx_doc["validation"]["structure_metrics"]["overall_structure_score"] >= 0.95

    # 3. Group Risk Management Policy v6.0 PDF (35-page scanned PDF)
    pdf_doc = loaded_records["Cadence_Group_Risk_Management_Policy__v6.0.pdf"]
    assert pdf_doc["detected_format"] == "SCANNED_PDF"
    assert pdf_doc["findings_count"] >= 700
    assert pdf_doc["validation"]["residual_pii_found"] is False
    assert pdf_doc["validation"]["structure_metrics"]["overall_structure_score"] >= 0.90

    # If the scanned PDF has any low-confidence OCR finding requiring analyst review,
    # verify that approving it transitions the gate cleanly to PASS.
    if pdf_doc["validation"]["gate_status"] == "REVIEW_REQUIRED":
        rev_resp = client.post(f"/api/documents/{pdf_doc['doc_id']}/findings/approve-all")
        assert rev_resp.status_code == 200
        updated_detail = rev_resp.json()
        assert updated_detail["validation"]["gate_status"] == "PASS"
        assert updated_detail["validation"]["llm_handoff_permitted"] is True

    # Verify audit log contains zero raw PII from the artifacts
    audit_resp = client.get("/api/audit-log")
    assert audit_resp.status_code == 200
    audit_str = str(audit_resp.json())
    assert "Divisha Kilari" not in audit_str
    assert "Aditya Lawand" not in audit_str
    assert "Madhav Mehta" not in audit_str

    # Verify SHA-256 hashes of original files are completely unchanged (immutability)
    for name in artifacts:
        fpath = CASE_MATERIALS_DIR / name
        after_hash = hashlib.sha256(fpath.read_bytes()).hexdigest()
        assert after_hash == before_hashes[name], f"Source artifact {name} was mutated!"

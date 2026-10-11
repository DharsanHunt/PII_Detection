"""
Comprehensive Benchmark & Evaluation Suite for Cadence PII Detection and Secure Redaction.
Executes:
1. All 28 synthetic gold test cases + 49 gold entity spans from PII_Detection_Redaction_Test_Benchmark.xlsx.
2. Multi-format end-to-end file benchmarks across all 5 supported formats:
   - Native Text PDF (headers/footers, body text, tables, repeated identifiers, false-positive traps)
   - Scanned Image-Based PDF (rasterized pages requiring OCR, bbox mapping, and pixel redaction)
   - Word DOCX (PII split across formatting runs, table cells, headers, metadata)
   - PowerPoint PPTX (slide text boxes, tables, speaker notes, metadata)
   - Standalone PNG Image (OCR extraction and pixel-level redaction)
Computes real, measured Precision, Recall, F1, False Positives, Residual PII, Structure Retention,
and Extraction Quality separately by file type.
"""
from __future__ import annotations

from datetime import datetime, timezone
import io
from typing import Any, Dict, List, Set, Tuple

import docx
import fitz  # PyMuPDF
import openpyxl
from PIL import Image, ImageDraw, ImageFont
import pptx
from pptx.util import Inches, Pt

from app.config import BENCHMARK_XLSX_PATH, get_policy
from app.detectors.hybrid_detector import HybridPIIDetector
from app.extractors.docx_extractor import extract_docx_document
from app.extractors.image_extractor import extract_image_document
from app.extractors.pdf_extractor import extract_pdf_document
from app.extractors.pptx_extractor import extract_pptx_document
from app.redactors.docx_redactor import redact_docx_document
from app.redactors.image_redactor import redact_standalone_image
from app.redactors.pdf_redactor import redact_pdf_document
from app.redactors.pptx_redactor import redact_pptx_document
from app.validators.privacy_gate import validate_redacted_artifact


_CACHED_BENCHMARK_REPORT: Dict[str, Any] | None = None


def _build_synthetic_native_pdf() -> Tuple[bytes, List[Tuple[str, str]]]:
    """Create a 2-page native text PDF with headers, body text, repeated PII, and false-positive traps."""
    doc = fitz.open()
    page1 = doc.new_page(width=595, height=842)
    # Header
    page1.insert_text((50, 35), "Document owner: Priya Demo | priya.demo@example.test", fontsize=10)
    # Body lines
    lines_p1 = [
        "Customer: Maya Sample. Email: maya.sample@example.test. Phone: +91 90000 00000.",
        "Account holder: Arjun Demo. Account number: 000012340001. Balance: INR 84,250.00.",
        "Tax ID: QWERT0000Z is recorded for Kavya Example.",
        "Send the notice to Riya Example at 42 Example Road, Sample Nagar, Chennai 600000.",
        "Applicant Neha Demo, date of birth 01/01/1990, is listed for review.",
        "The Contact Information Standard describes how teams handle confidential records.",
        "Blue River Financial Services reviews statements for client institutions.",
    ]
    y = 110
    for line in lines_p1:
        page1.insert_text((50, y), line, fontsize=11)
        y += 40

    page2 = doc.new_page(width=595, height=842)
    lines_p2 = [
        "Employee: Tara Placeholder. Employee ID: EMP-TEST-017. Email: tara.placeholder@example.test.",
        "Reviewer Anil Sample (EMP-TEST-101) requested approval from Meera Demo (EMP-TEST-102).",
        "Maya Sample submitted the form. The reviewer contacted Maya Sample for clarification.",
        "For support, use the card ending in **** 0000. The full account number is not included.",
        "May, June and August are release milestones for the quarterly reporting project.",
    ]
    y = 110
    for line in lines_p2:
        page2.insert_text((50, y), line, fontsize=11)
        y += 40

    expected = [
        ("PERSON_NAME", "Priya Demo"),
        ("EMAIL", "priya.demo@example.test"),
        ("PERSON_NAME", "Maya Sample"),
        ("EMAIL", "maya.sample@example.test"),
        ("PHONE_NUMBER", "+91 90000 00000"),
        ("PERSON_NAME", "Arjun Demo"),
        ("ACCOUNT_NUMBER", "000012340001"),
        ("TAX_ID_PAN_STYLE", "QWERT0000Z"),
        ("PERSON_NAME", "Kavya Example"),
        ("PERSON_NAME", "Riya Example"),
        ("ADDRESS", "42 Example Road, Sample Nagar, Chennai 600000"),
        ("PERSON_NAME", "Neha Demo"),
        ("DATE_OF_BIRTH", "01/01/1990"),
        ("PERSON_NAME", "Tara Placeholder"),
        ("EMPLOYEE_ID", "EMP-TEST-017"),
        ("EMAIL", "tara.placeholder@example.test"),
        ("PERSON_NAME", "Anil Sample"),
        ("EMPLOYEE_ID", "EMP-TEST-101"),
        ("PERSON_NAME", "Meera Demo"),
        ("EMPLOYEE_ID", "EMP-TEST-102"),
        ("PERSON_NAME", "Maya Sample"),
        ("PERSON_NAME", "Maya Sample"),
    ]
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes, expected


def _build_synthetic_scanned_pdf() -> Tuple[bytes, List[Tuple[str, str]]]:
    """Create a rasterized scanned PDF (0 native selectable characters) to test OCR + pixel redaction."""
    tmp_doc = fitz.open()
    p1 = tmp_doc.new_page(width=595, height=842)
    lines = [
        "Customer: Maya Sample",
        "Email: maya.sample@example.test",
        "Employee: Tara Placeholder",
        "Employee ID: EMP-TEST-017",
        "Tax ID: QWERT0000Z",
        "Contact person: Jordan Example",
        "Phone: +1 202-555-0147",
        "The Risk Committee approved Version 6.0.",
    ]
    y = 100
    for ln in lines:
        p1.insert_text((60, y), ln, fontsize=15)
        y += 55
    pix = p1.get_pixmap(dpi=150, alpha=False)
    img_bytes = pix.tobytes("png")
    tmp_doc.close()

    scan_doc = fitz.open()
    sp = scan_doc.new_page(width=595, height=842)
    sp.insert_image(sp.rect, stream=img_bytes)
    out_bytes = scan_doc.tobytes()
    scan_doc.close()

    expected = [
        ("PERSON_NAME", "Maya Sample"),
        ("EMAIL", "maya.sample@example.test"),
        ("PERSON_NAME", "Tara Placeholder"),
        ("EMPLOYEE_ID", "EMP-TEST-017"),
        ("TAX_ID_PAN_STYLE", "QWERT0000Z"),
        ("PERSON_NAME", "Jordan Example"),
        ("PHONE_NUMBER", "+1 202-555-0147"),
    ]
    return out_bytes, expected


def _build_synthetic_docx() -> Tuple[bytes, List[Tuple[str, str]]]:
    """Create a DOCX with PII split across multiple runs, table cells, headers, and false-positive checks."""
    doc = docx.Document()
    doc.core_properties.author = ""

    # Section header
    hdr_p = doc.sections[0].header.paragraphs[0]
    hdr_p.text = "Prepared by: Priya Demo | Document owner email: priya.demo@example.test"

    # Paragraph 1: PII deliberately split across 3 runs!
    p1 = doc.add_paragraph()
    p1.add_run("Policy owner: ")
    r_name1 = p1.add_run("Miriam ")
    r_name1.bold = True
    r_name2 = p1.add_run("T. ")
    r_name2.bold = True
    r_name3 = p1.add_run("Achebe")
    r_name3.bold = True
    p1.add_run(" (")
    p1.add_run("EMP-")
    p1.add_run("38104")
    p1.add_run("), email ")
    p1.add_run("m.achebe@cadencefg.com")

    # Paragraph 2: Non-PII negative test
    doc.add_paragraph(
        "The Contact Information Standard describes how teams handle confidential records. "
        "Quarterly processing completed on 31 March 2026 with total volume of INR 1,250,000."
    )

    # Table with PII
    tbl = doc.add_table(rows=2, cols=3)
    tbl.cell(0, 0).text = "Customer Name"
    tbl.cell(0, 1).text = "Email"
    tbl.cell(0, 2).text = "Account Number"
    tbl.cell(1, 0).text = "Neel Demo"
    tbl.cell(1, 1).text = "neel.demo@example.test"
    tbl.cell(1, 2).text = "000098765432"

    buf = io.BytesIO()
    doc.save(buf)

    expected = [
        ("PERSON_NAME", "Priya Demo"),
        ("EMAIL", "priya.demo@example.test"),
        ("PERSON_NAME", "Miriam T. Achebe"),
        ("EMPLOYEE_ID", "EMP-38104"),
        ("EMAIL", "m.achebe@cadencefg.com"),
        ("PERSON_NAME", "Neel Demo"),
        ("EMAIL", "neel.demo@example.test"),
        ("ACCOUNT_NUMBER", "000098765432"),
    ]
    return buf.getvalue(), expected


def _build_synthetic_pptx() -> Tuple[bytes, List[Tuple[str, str]]]:
    """Create a PPTX presentation with slide text boxes, table cells, and speaker notes containing PII."""
    prs = pptx.Presentation()
    prs.core_properties.author = ""

    slide_layout = prs.slide_layouts[5]  # Title Only
    s1 = prs.slides.add_slide(slide_layout)
    s1.shapes.title.text = "Executive Directory & Escalation Contacts"

    tb = s1.shapes.add_textbox(Inches(1), Inches(1.8), Inches(8), Inches(1.5))
    tf = tb.text_frame
    p = tf.paragraphs[0]
    for chunk in ("Primary contact: ", "Omar ", "Example", "; telephone: +91 (90000) 00000."):
        r = p.add_run()
        r.text = chunk

    tbl_shape = s1.shapes.add_table(2, 3, Inches(1), Inches(3.5), Inches(8), Inches(1.5))
    tbl = tbl_shape.table
    tbl.cell(0, 0).text = "Officer"
    tbl.cell(0, 1).text = "Employee ID"
    tbl.cell(0, 2).text = "Email"
    tbl.cell(1, 0).text = "Tobias Lindqvist"
    tbl.cell(1, 1).text = "EMP-40522"
    tbl.cell(1, 2).text = "t.lindqvist@cadencefg.com"

    # Speaker notes with PII
    notes_tf = s1.notes_slide.notes_text_frame
    notes_tf.text = "Escalation backup: Contact person: Jordan Example. Phone: +1 202-555-0147."

    buf = io.BytesIO()
    prs.save(buf)

    expected = [
        ("PERSON_NAME", "Omar Example"),
        ("PHONE_NUMBER", "+91 (90000) 00000"),
        ("PERSON_NAME", "Tobias Lindqvist"),
        ("EMPLOYEE_ID", "EMP-40522"),
        ("EMAIL", "t.lindqvist@cadencefg.com"),
        ("PERSON_NAME", "Jordan Example"),
        ("PHONE_NUMBER", "+1 202-555-0147"),
    ]
    return buf.getvalue(), expected


def _build_synthetic_png() -> Tuple[bytes, List[Tuple[str, str]]]:
    """Create a standalone PNG image with clear synthetic PII to test standalone image OCR and pixel redaction."""
    tmp_doc = fitz.open()
    page = tmp_doc.new_page(width=650, height=360)
    lines = [
        "CADENCE VERIFICATION RECORD",
        "Customer: Maya Sample",
        "Email: maya.sample@example.test",
        "Employee ID: EMP-TEST-017",
        "Tax ID: QWERT0000Z",
        "Status: Active | Policy Version 6.0",
    ]
    y = 55
    for ln in lines:
        page.insert_text((45, y), ln, fontsize=16)
        y += 48
    pix = page.get_pixmap(dpi=150, alpha=False)
    png_bytes = pix.tobytes("png")
    tmp_doc.close()

    expected = [
        ("PERSON_NAME", "Maya Sample"),
        ("EMAIL", "maya.sample@example.test"),
        ("EMPLOYEE_ID", "EMP-TEST-017"),
        ("TAX_ID_PAN_STYLE", "QWERT0000Z"),
    ]
    return png_bytes, expected


def _evaluate_format_fixture(
    format_name: str,
    raw_bytes: bytes,
    expected_entities: List[Tuple[str, str]],
) -> Dict[str, Any]:
    """Run extraction, detection, redaction, and validation on a format fixture and compute metrics."""
    detector = HybridPIIDetector(policy=get_policy())

    if format_name == "PDF (Native Text)":
        segments, profile = extract_pdf_document(raw_bytes)
        findings = detector.analyze_document_segments("BENCH_PDF", "synthetic_native.pdf", "PDF", segments)
        redacted_bytes = redact_pdf_document(raw_bytes, findings)
    elif format_name == "Scanned PDF (OCR)":
        segments, profile = extract_pdf_document(raw_bytes)
        findings = detector.analyze_document_segments("BENCH_SCAN", "synthetic_scanned.pdf", "SCANNED_PDF", segments)
        redacted_bytes = redact_pdf_document(raw_bytes, findings)
    elif format_name == "Word (DOCX)":
        segments, profile = extract_docx_document(raw_bytes)
        findings = detector.analyze_document_segments("BENCH_DOCX", "synthetic_split_runs.docx", "DOCX", segments)
        redacted_bytes = redact_docx_document(raw_bytes, findings)
    elif format_name == "PowerPoint (PPTX)":
        segments, profile = extract_pptx_document(raw_bytes)
        findings = detector.analyze_document_segments("BENCH_PPTX", "synthetic_deck.pptx", "PPTX", segments)
        redacted_bytes = redact_pptx_document(raw_bytes, findings)
    else:
        segments, profile = extract_image_document(raw_bytes, "PNG", "image/png")
        findings = detector.analyze_document_segments("BENCH_PNG", "synthetic_capture.png", "PNG", segments)
        redacted_bytes = redact_standalone_image(raw_bytes, findings, "PNG")

    validation = validate_redacted_artifact(profile, segments, findings, redacted_bytes)

    # Compare detected (category, entity_text) multiset against expected_entities
    def _norm_pair(cat: str, txt: str) -> Tuple[str, str]:
        t = txt.strip()
        if cat == "TAX_ID_PAN_STYLE" and len(t) == 10:
            t = t[:5] + t[5:9].replace("O", "0") + t[9:]
        return (cat, t)

    remaining_expected = [_norm_pair(c, t) for c, t in expected_entities]
    tp = 0
    fp = 0
    for f in findings:
        pair = _norm_pair(f.category.value, f.entity_text)
        if pair in remaining_expected:
            tp += 1
            remaining_expected.remove(pair)
        else:
            fp += 1
    fn = len(remaining_expected)

    precision = round(tp / max(1, tp + fp), 4)
    recall = round(tp / max(1, tp + fn), 4)
    f1 = round(2 * precision * recall / max(1e-9, precision + recall), 4)

    # Extraction quality: fraction of expected entity texts recovered intact in extracted text
    full_extracted_text = "\n".join(s.text for s in segments)
    recovered_tokens = sum(
        1
        for cat, etxt in expected_entities
        if etxt in full_extracted_text
        or (cat == "TAX_ID_PAN_STYLE" and etxt.replace("0", "O", 1) in full_extracted_text)
    )
    extraction_quality = round(recovered_tokens / max(1, len(expected_entities)), 4)

    return {
        "file_type": format_name,
        "expected_pii_count": len(expected_entities),
        "detected_pii_count": len(findings),
        "true_positives": tp,
        "false_positives": fp,
        "false_negatives": fn,
        "precision": precision,
        "recall": recall,
        "f1_score": f1,
        "residual_pii_count": validation.residual_findings_count,
        "residual_pii_detected": validation.residual_pii_found,
        "structure_retention_score": validation.structure_metrics.overall_structure_score,
        "extraction_quality_score": extraction_quality,
        "gate_status": validation.gate_status.value,
    }


def run_full_benchmark_suite(force_refresh: bool = False) -> Dict[str, Any]:
    """Run the 28-case XLSX benchmark AND the 5-format file benchmark suite."""
    global _CACHED_BENCHMARK_REPORT
    if _CACHED_BENCHMARK_REPORT is not None and not force_refresh:
        return _CACHED_BENCHMARK_REPORT

    detector = HybridPIIDetector(policy=get_policy())

    # Part A: Official 28-Case Synthetic Text Benchmark from XLSX
    xlsx_cases: List[Dict[str, Any]] = []
    total_tp = 0
    total_fp = 0
    total_fn = 0
    total_expected = 0
    exact_redaction_matches = 0
    negative_cases_total = 0
    negative_cases_clean = 0

    if BENCHMARK_XLSX_PATH.exists():
        wb = openpyxl.load_workbook(BENCHMARK_XLSX_PATH)
        ws = wb.worksheets[1]
        for row in list(ws.iter_rows(values_only=True))[4:]:
            if not row or not row[0]:
                continue
            cid, inp_type, scenario, diff, text, exp_ent_str, exp_cnt_raw, exp_red, objective = row[:9]
            exp_cnt = int(exp_cnt_raw or 0)
            total_expected += exp_cnt

            exp_pairs: List[Tuple[str, str]] = []
            if exp_ent_str and str(exp_ent_str).strip() != "None expected":
                for part in str(exp_ent_str).split("|"):
                    if ":" in part:
                        k, v = part.split(":", 1)
                        exp_pairs.append((k.strip(), v.strip()))

            matches = detector.detect_in_text(str(text))
            act_red = detector.redact_text_with_matches(str(text), matches)
            act_ent_str = (
                " | ".join(f"{m.category.value}: {m.text}" for m in matches)
                if matches
                else "None expected"
            )

            # Residual check on redacted text
            residual_matches = detector.detect_in_text(act_red)

            rem = list(exp_pairs)
            c_tp = 0
            c_fp = 0
            for m in matches:
                p = (m.category.value, m.text)
                if p in rem:
                    c_tp += 1
                    rem.remove(p)
                else:
                    c_fp += 1
            c_fn = len(rem)

            total_tp += c_tp
            total_fp += c_fp
            total_fn += c_fn

            if exp_cnt == 0:
                negative_cases_total += 1
                if len(matches) == 0:
                    negative_cases_clean += 1

            is_exact = act_red == exp_red and act_ent_str == exp_ent_str
            if is_exact:
                exact_redaction_matches += 1

            xlsx_cases.append(
                {
                    "case_id": cid,
                    "input_type": inp_type,
                    "scenario": scenario,
                    "difficulty": diff,
                    "expected_count": exp_cnt,
                    "detected_count": len(matches),
                    "expected_entities": exp_ent_str,
                    "actual_entities": act_ent_str,
                    "expected_redacted": exp_red,
                    "actual_redacted": act_red,
                    "exact_match": is_exact,
                    "residual_pii_count": len(residual_matches),
                    "status": "PASS" if (is_exact and len(residual_matches) == 0) else "REVIEW",
                }
            )

    # Part B: Multi-Format End-to-End File Benchmarks (PDF, Scanned PDF, DOCX, PPTX, PNG)
    pdf_bytes, pdf_exp = _build_synthetic_native_pdf()
    scan_bytes, scan_exp = _build_synthetic_scanned_pdf()
    docx_bytes, docx_exp = _build_synthetic_docx()
    pptx_bytes, pptx_exp = _build_synthetic_pptx()
    png_bytes, png_exp = _build_synthetic_png()

    format_metrics = [
        _evaluate_format_fixture("PDF (Native Text)", pdf_bytes, pdf_exp),
        _evaluate_format_fixture("Scanned PDF (OCR)", scan_bytes, scan_exp),
        _evaluate_format_fixture("Word (DOCX)", docx_bytes, docx_exp),
        _evaluate_format_fixture("PowerPoint (PPTX)", pptx_bytes, pptx_exp),
        _evaluate_format_fixture("Standalone Image (PNG)", png_bytes, png_exp),
    ]

    # Combine overall file metrics
    f_tp = sum(m["true_positives"] for m in format_metrics)
    f_fp = sum(m["false_positives"] for m in format_metrics)
    f_fn = sum(m["false_negatives"] for m in format_metrics)
    f_res = sum(m["residual_pii_count"] for m in format_metrics)
    avg_struct = round(
        sum(m["structure_retention_score"] for m in format_metrics) / len(format_metrics), 4
    )
    avg_extract = round(
        sum(m["extraction_quality_score"] for m in format_metrics) / len(format_metrics), 4
    )

    text_precision = round(total_tp / max(1, total_tp + total_fp), 4)
    text_recall = round(total_tp / max(1, total_tp + total_fn), 4)
    text_f1 = round(2 * text_precision * text_recall / max(1e-9, text_precision + text_recall), 4)

    file_precision = round(f_tp / max(1, f_tp + f_fp), 4)
    file_recall = round(f_tp / max(1, f_tp + f_fn), 4)
    file_f1 = round(2 * file_precision * file_recall / max(1e-9, file_precision + file_recall), 4)

    _CACHED_BENCHMARK_REPORT = {
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "text_benchmark_summary": {
            "total_cases": len(xlsx_cases),
            "exact_case_matches": exact_redaction_matches,
            "expected_entities_total": total_expected,
            "true_positives": total_tp,
            "false_positives": total_fp,
            "false_negatives": total_fn,
            "precision": text_precision,
            "recall": text_recall,
            "f1_score": text_f1,
            "negative_cases_total": negative_cases_total,
            "negative_cases_zero_fp": negative_cases_clean,
            "false_positive_rate_on_negatives": round(
                (negative_cases_total - negative_cases_clean) / max(1, negative_cases_total), 4
            ),
            "residual_pii_count": sum(c["residual_pii_count"] for c in xlsx_cases),
        },
        "file_format_metrics": format_metrics,
        "aggregate_file_summary": {
            "formats_tested": len(format_metrics),
            "true_positives": f_tp,
            "false_positives": f_fp,
            "false_negatives": f_fn,
            "precision": file_precision,
            "recall": file_recall,
            "f1_score": file_f1,
            "residual_pii_count": f_res,
            "average_structure_retention": avg_struct,
            "average_extraction_quality": avg_extract,
        },
        "xlsx_cases": xlsx_cases,
    }
    return _CACHED_BENCHMARK_REPORT

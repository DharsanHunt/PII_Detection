"""
End-to-End Document Processing, Redaction, Validation, and Audit Pipeline.
Guarantees:
- Original source files remain 100% immutable.
- Raw document text and raw PII are NEVER written to application or audit logs.
- Controlled temporary storage is automatically cleaned up.
- Every analyst review edit re-triggers genuine format-preserving redaction and independent Privacy Gate validation.
"""
from __future__ import annotations

from datetime import datetime, timezone
import os
import shutil
import time
import uuid
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import fitz  # PyMuPDF

from app.config import CASE_MATERIALS_DIR, TEMP_STORAGE_DIR, get_policy
from app.detectors.hybrid_detector import HybridPIIDetector, RawSpanMatch, _mask_preview
from app.extractors.docx_extractor import extract_docx_document
from app.extractors.file_validator import validate_and_identify_file
from app.extractors.image_extractor import extract_image_document
from app.extractors.pdf_extractor import extract_pdf_document
from app.extractors.pptx_extractor import extract_pptx_document
from app.models import (
    AuditEvent,
    BlockComparisonItem,
    DocumentRecord,
    ExtractionProfile,
    FindingUpdateRequest,
    GateState,
    ManualFindingCreateRequest,
    PIIEntityCategory,
    PIIFinding,
    ReviewStatus,
    TextBlockSegment,
)
from app.redactors.docx_redactor import redact_docx_document
from app.redactors.image_redactor import redact_standalone_image
from app.redactors.pdf_redactor import redact_pdf_document
from app.redactors.pptx_redactor import redact_pptx_document
from app.validators.privacy_gate import validate_redacted_artifact


class PipelineManager:
    """Manages processed document state, memory-isolated binary buffers, and zero-PII audit logs."""

    def __init__(self) -> None:
        self.documents: Dict[str, DocumentRecord] = {}
        self._source_binaries: Dict[str, bytes] = {}
        self._redacted_binaries: Dict[str, bytes] = {}
        self._source_segments: Dict[str, List[TextBlockSegment]] = {}
        self.audit_log: List[AuditEvent] = []
        self.detector = HybridPIIDetector()
        self._ensure_temp_dir()

    def _ensure_temp_dir(self) -> None:
        TEMP_STORAGE_DIR.mkdir(parents=True, exist_ok=True)

    def record_audit(
        self,
        stage: str,
        action: str,
        doc_id: Optional[str] = None,
        document_name: Optional[str] = None,
        gate_status: Optional[str] = None,
        details: Optional[Dict[str, object]] = None,
    ) -> None:
        """Record a security audit event. Raw PII values are strictly prohibited in details."""
        evt = AuditEvent(
            event_id=f"AUD-{uuid.uuid4().hex[:8].upper()}",
            timestamp=datetime.now(timezone.utc).isoformat(),
            doc_id=doc_id,
            document_name=document_name,
            stage=stage,
            action=action,
            gate_status=gate_status,
            details=dict(details or {}),
        )
        self.audit_log.insert(0, evt)

    def process_uploaded_bytes(
        self,
        filename: str,
        content: bytes,
        is_case_study_artifact: bool = False,
    ) -> DocumentRecord:
        """
        Execute the full 13-stage privacy pipeline on a document byte stream:
        Upload -> File-Type Validation -> Format-Aware Extraction -> Hybrid PII Detection ->
        Classification & Confidence Scoring -> Format-Preserving Redaction ->
        Residual PII & Structure Validation -> Privacy Gate Decision.
        """
        t0 = time.perf_counter()
        policy = get_policy()
        self.detector.policy = policy

        # Stage 1 & 2: File-Type Identification & Signature Validation
        clean_name, base_format, mime_type = validate_and_identify_file(filename, content)
        doc_id = f"DOC-{uuid.uuid4().hex[:8].upper()}"

        # Write to controlled temporary workspace during processing, then remove in finally block
        temp_file = TEMP_STORAGE_DIR / f"{doc_id}_{clean_name}"
        try:
            temp_file.write_bytes(content)
            try:
                os.chmod(temp_file, 0o600)
            except Exception:
                pass

            self.record_audit(
                stage="FILE_VALIDATION",
                action="Validated file extension, magic signature, and archive safety.",
                doc_id=doc_id,
                document_name=clean_name,
                details={
                    "file_size_bytes": len(content),
                    "base_format": base_format,
                    "mime_type": mime_type,
                },
            )

            # Stage 3 & 4: Format-Aware Structure & Layout Extraction
            if base_format == "PDF":
                segments, profile = extract_pdf_document(content)
            elif base_format == "DOCX":
                segments, profile = extract_docx_document(content)
            elif base_format == "PPTX":
                segments, profile = extract_pptx_document(content)
            else:
                segments, profile = extract_image_document(content, base_format, mime_type)

            detected_format = profile.detected_format

            self.record_audit(
                stage="EXTRACTION",
                action=f"Completed format-aware extraction ({detected_format}).",
                doc_id=doc_id,
                document_name=clean_name,
                details={
                    "total_pages_or_slides": profile.total_pages_or_slides,
                    "segments_extracted": len(segments),
                    "tables_count": profile.tables_count,
                    "ocr_pages_count": len(profile.ocr_pages_list),
                    "embedded_images_count": profile.embedded_images_count,
                },
            )

            # Stage 5, 6, 7, 8: Hybrid PII Detection, Classification, Confidence & Mapping
            findings = self.detector.analyze_document_segments(
                doc_id=doc_id,
                document_name=clean_name,
                detected_format=detected_format,
                segments=segments,
            )

            # Stage 9, 10, 11: Secure Redaction, Residual PII Validation, Structure Validation
            redacted_bytes = self._apply_format_redaction(
                detected_format=detected_format,
                source_bytes=content,
                findings=findings,
            )

            validation = validate_redacted_artifact(
                source_profile=profile,
                source_segments=segments,
                findings=findings,
                redacted_bytes=redacted_bytes,
            )

            block_comparisons = self._build_block_comparisons(segments, findings)
            cat_counts, src_counts, active_count = self._summarize_findings(findings)

            limitations: List[str] = []
            if profile.is_scanned_document:
                limitations.append(
                    "Scanned/rasterized document: PII detection relies on OCR glyph recognition; extreme image degradation or handwriting may require manual analyst verification."
                )
            if profile.embedded_images_count > 0:
                limitations.append(
                    f"Contains {profile.embedded_images_count} embedded media image(s); raster regions with detected PII are pixel-destroyed in place."
                )

            elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)

            record = DocumentRecord(
                doc_id=doc_id,
                filename=clean_name,
                file_size_bytes=len(content),
                detected_format=detected_format,  # type: ignore[arg-type]
                mime_type=mime_type,
                upload_timestamp=datetime.now(timezone.utc).isoformat(),
                status="VALIDATED",
                processing_time_ms=elapsed_ms,
                extraction_profile=profile,
                findings_count=len(findings),
                active_findings_count=active_count,
                findings_by_category=cat_counts,
                findings_by_source_type=src_counts,
                findings=findings,
                block_comparisons=block_comparisons,
                validation=validation,
                limitations=limitations,
                is_case_study_artifact=is_case_study_artifact,
            )

            self.documents[doc_id] = record
            self._source_binaries[doc_id] = content
            self._redacted_binaries[doc_id] = redacted_bytes
            self._source_segments[doc_id] = segments

            self.record_audit(
                stage="PRIVACY_GATE",
                action=f"Completed redaction and independent validation. Gate={validation.gate_status.value}",
                doc_id=doc_id,
                document_name=clean_name,
                gate_status=validation.gate_status.value,
                details={
                    "findings_total": len(findings),
                    "active_redactions": active_count,
                    "findings_by_category": cat_counts,
                    "residual_pii_found": validation.residual_pii_found,
                    "unresolved_review_count": validation.unresolved_review_count,
                    "structure_retention_score": validation.structure_metrics.overall_structure_score,
                    "llm_handoff_permitted": validation.llm_handoff_permitted,
                    "processing_time_ms": elapsed_ms,
                },
            )
            return record
        finally:
            # Always clean up temporary intermediate files on disk
            if temp_file.exists():
                try:
                    temp_file.unlink()
                except Exception:
                    pass

    def _apply_format_redaction(
        self,
        detected_format: str,
        source_bytes: bytes,
        findings: List[PIIFinding],
    ) -> bytes:
        if detected_format in {"PDF", "SCANNED_PDF"}:
            return redact_pdf_document(source_bytes, findings)
        if detected_format == "DOCX":
            return redact_docx_document(source_bytes, findings)
        if detected_format == "PPTX":
            return redact_pptx_document(source_bytes, findings)
        return redact_standalone_image(source_bytes, findings, detected_format)

    @staticmethod
    def _summarize_findings(
        findings: List[PIIFinding],
    ) -> Tuple[Dict[str, int], Dict[str, int], int]:
        by_cat: Dict[str, int] = {}
        by_src: Dict[str, int] = {}
        active = 0
        for f in findings:
            if f.review_status == ReviewStatus.REJECTED_FALSE_POSITIVE:
                continue
            active += 1
            by_cat[f.category.value] = by_cat.get(f.category.value, 0) + 1
            by_src[f.source_type] = by_src.get(f.source_type, 0) + 1
        return by_cat, by_src, active

    @staticmethod
    def _build_block_comparisons(
        segments: List[TextBlockSegment],
        findings: List[PIIFinding],
    ) -> List[BlockComparisonItem]:
        by_block: Dict[str, List[PIIFinding]] = {}
        for f in findings:
            if f.review_status == ReviewStatus.REJECTED_FALSE_POSITIVE:
                continue
            by_block.setdefault(f.block_id, []).append(f)

        items: List[BlockComparisonItem] = []
        for seg in segments:
            b_findings = by_block.get(seg.block_id, [])
            red_text = seg.text
            for bf in sorted(b_findings, key=lambda x: x.char_start, reverse=True):
                red_text = (
                    red_text[: bf.char_start]
                    + bf.replacement_label
                    + red_text[bf.char_end :]
                )
            items.append(
                BlockComparisonItem(
                    block_id=seg.block_id,
                    page_or_slide=seg.page_or_slide,
                    source_type=seg.source_type,
                    location_ref=seg.location_ref,
                    original_text=seg.text,
                    redacted_text=red_text,
                    has_pii=len(b_findings) > 0,
                    pii_count=len(b_findings),
                )
            )
        return items

    def update_finding(
        self, doc_id: str, finding_id: str, req: FindingUpdateRequest
    ) -> DocumentRecord:
        """Allow analyst to approve/reject a finding or recategorize it, then re-redact & re-validate."""
        if doc_id not in self.documents:
            raise KeyError(f"Document {doc_id} not found.")
        record = self.documents[doc_id]
        policy = get_policy()

        target: Optional[PIIFinding] = None
        for f in record.findings:
            if f.finding_id == finding_id:
                target = f
                break
        if target is None:
            raise KeyError(f"Finding {finding_id} not found in document {doc_id}.")

        if req.review_status is not None:
            target.review_status = req.review_status
        if req.category is not None:
            target.category = req.category
            target.replacement_label = policy.replacement_labels.get(
                req.category.value, f"[{req.category.value} REDACTED]"
            )
        if req.replacement_label is not None:
            target.replacement_label = req.replacement_label

        return self._reprocess_redaction_and_validation(
            doc_id=doc_id,
            audit_action=f"Analyst updated finding {finding_id} (status={target.review_status.value}, category={target.category.value}).",
        )

    def approve_all_flagged_findings(self, doc_id: str) -> DocumentRecord:
        """Allow analyst to bulk-approve all FLAGGED_REVIEW findings in a document after inspection."""
        if doc_id not in self.documents:
            raise KeyError(f"Document {doc_id} not found.")
        record = self.documents[doc_id]
        updated_count = 0
        for f in record.findings:
            if f.review_status == ReviewStatus.FLAGGED_REVIEW:
                f.review_status = ReviewStatus.APPROVED
                updated_count += 1

        return self._reprocess_redaction_and_validation(
            doc_id=doc_id,
            audit_action=f"Analyst reviewed and approved {updated_count} flagged finding(s).",
        )

    def add_manual_finding(
        self, doc_id: str, req: ManualFindingCreateRequest
    ) -> DocumentRecord:
        """Allow analyst to manually add a missed PII entity in a specific block and re-redact."""
        if doc_id not in self.documents:
            raise KeyError(f"Document {doc_id} not found.")
        record = self.documents[doc_id]
        segments = self._source_segments.get(doc_id, [])
        policy = get_policy()

        target_seg: Optional[TextBlockSegment] = None
        for s in segments:
            if s.block_id == req.block_id:
                target_seg = s
                break
        if target_seg is None:
            raise ValueError(f"Block {req.block_id} not found in document.")

        needle = req.exact_text.strip()
        if not needle:
            raise ValueError("exact_text cannot be empty.")

        pos = target_seg.text.find(needle)
        if pos < 0:
            raise ValueError(f"Specified text span not found in block {req.block_id}.")

        new_idx = len(record.findings) + 1
        fid = f"{doc_id}_M{new_idx:04d}"
        rep_label = policy.replacement_labels.get(
            req.category.value, f"[{req.category.value} REDACTED]"
        )

        new_finding = PIIFinding(
            finding_id=fid,
            document_id=doc_id,
            document_name=record.filename,
            page_or_slide=target_seg.page_or_slide,
            source_type=target_seg.source_type,
            block_id=target_seg.block_id,
            location_ref=target_seg.location_ref,
            char_start=pos,
            char_end=pos + len(needle),
            bbox=target_seg.bbox,
            category=req.category,
            entity_text=needle,
            masked_preview=_mask_preview(needle),
            replacement_label=rep_label,
            stable_token=f"[MANUAL_{new_idx:03d}]",
            confidence=1.0,
            detection_method="Manual Analyst Annotation",
            rationale=req.rationale,
            redaction_method="Analyst-Directed Native Redaction",
            review_status=ReviewStatus.MANUAL_ADDED,
            context_before=target_seg.text[max(0, pos - 30) : pos],
            context_after=target_seg.text[pos + len(needle) : pos + len(needle) + 30],
            image_ref=target_seg.image_ref,
        )
        record.findings.append(new_finding)

        return self._reprocess_redaction_and_validation(
            doc_id=doc_id,
            audit_action=f"Analyst manually added finding {fid} ({req.category.value}) in {target_seg.location_ref}.",
        )

    def _reprocess_redaction_and_validation(
        self, doc_id: str, audit_action: str
    ) -> DocumentRecord:
        record = self.documents[doc_id]
        source_bytes = self._source_binaries[doc_id]
        segments = self._source_segments[doc_id]

        redacted_bytes = self._apply_format_redaction(
            detected_format=record.detected_format,
            source_bytes=source_bytes,
            findings=record.findings,
        )
        validation = validate_redacted_artifact(
            source_profile=record.extraction_profile,
            source_segments=segments,
            findings=record.findings,
            redacted_bytes=redacted_bytes,
        )

        cat_counts, src_counts, active_count = self._summarize_findings(record.findings)
        record.findings_count = len(record.findings)
        record.active_findings_count = active_count
        record.findings_by_category = cat_counts
        record.findings_by_source_type = src_counts
        record.block_comparisons = self._build_block_comparisons(segments, record.findings)
        record.validation = validation
        self._redacted_binaries[doc_id] = redacted_bytes

        self.record_audit(
            stage="HUMAN_REVIEW_REVALIDATION",
            action=audit_action,
            doc_id=doc_id,
            document_name=record.filename,
            gate_status=validation.gate_status.value,
            details={
                "active_findings_count": active_count,
                "unresolved_review_count": validation.unresolved_review_count,
                "residual_pii_found": validation.residual_pii_found,
                "gate_status": validation.gate_status.value,
            },
        )
        return record

    def get_redacted_bytes(self, doc_id: str) -> Tuple[str, str, bytes]:
        """Return (redacted_filename, mime_type, redacted_bytes) for safe download."""
        if doc_id not in self.documents or doc_id not in self._redacted_binaries:
            raise KeyError(f"Document {doc_id} not found.")
        rec = self.documents[doc_id]
        stem = Path(rec.filename).stem
        ext = Path(rec.filename).suffix
        out_name = f"{stem}_REDACTED{ext}"
        self.record_audit(
            stage="SAFE_EXPORT",
            action=f"Exported sanitized artifact '{out_name}'.",
            doc_id=doc_id,
            document_name=rec.filename,
            gate_status=rec.validation.gate_status.value if rec.validation else "UNKNOWN",
            details={"export_filename": out_name, "bytes": len(self._redacted_binaries[doc_id])},
        )
        return out_name, rec.mime_type, self._redacted_binaries[doc_id]

    def get_page_preview_png(
        self, doc_id: str, version: str = "redacted", page_no: int = 1
    ) -> bytes:
        """Render a visual PNG preview of a PDF page or standalone image (original or redacted)."""
        if doc_id not in self.documents:
            raise KeyError(f"Document {doc_id} not found.")
        rec = self.documents[doc_id]
        raw_bytes = (
            self._source_binaries[doc_id]
            if version == "original"
            else self._redacted_binaries[doc_id]
        )

        if rec.detected_format in {"PDF", "SCANNED_PDF"}:
            doc = fitz.open(stream=raw_bytes, filetype="pdf")
            try:
                idx = max(0, min(len(doc) - 1, page_no - 1))
                pix = doc[idx].get_pixmap(dpi=120, alpha=False)
                return pix.tobytes("png")
            finally:
                doc.close()

        if rec.detected_format in {"PNG", "JPG"}:
            return raw_bytes

        raise ValueError(f"Visual page raster preview not applicable to {rec.detected_format}.")

    def load_case_study_artifact(self, artifact_name: str) -> DocumentRecord:
        """Load one of the official Case Study 2 supporting files in read-only mode without modifying it."""
        allowed = {
            "Cadence_Financial_Group_Organizational_Pack.pptx",
            "Cadence_Group_Risk_Management_Policy__v6.0.pdf",
            "Cadence_TPRM_Training.docx",
        }
        if artifact_name not in allowed:
            raise ValueError(f"Unknown case study artifact: {artifact_name}")

        target_path = CASE_MATERIALS_DIR / artifact_name
        if not target_path.exists():
            raise FileNotFoundError(f"Case study artifact not found at {target_path}")

        # Return existing processed record if already loaded
        for rec in self.documents.values():
            if rec.filename == artifact_name and rec.is_case_study_artifact:
                return rec

        raw_bytes = target_path.read_bytes()
        return self.process_uploaded_bytes(
            filename=artifact_name,
            content=raw_bytes,
            is_case_study_artifact=True,
        )


PIPELINE_MANAGER = PipelineManager()

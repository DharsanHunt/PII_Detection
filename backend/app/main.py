"""FastAPI Application for Cadence PII Detection and Secure Document Redaction."""
from __future__ import annotations

import csv
import io
import json
from typing import Any, Dict, List
from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import BaseModel

from app.config import CASE_MATERIALS_DIR, PolicyConfig, get_policy, update_policy
from app.extractors.file_validator import FileValidationError
from app.models import (
    DocumentRecord,
    FindingUpdateRequest,
    GateState,
    ManualFindingCreateRequest,
    ReviewStatus,
)
from app.services.benchmark_runner import run_full_benchmark_suite
from app.services.llm_gateway import PrivacyGateViolationError, process_with_downstream_llm
from app.services.pipeline import PIPELINE_MANAGER

app = FastAPI(
    title="Cadence Financial Group — PII Detection & Secure Redaction Gateway",
    description=(
        "Enterprise document sanitization, hybrid PII detection, format-preserving redaction, "
        "and privacy gate validation system for Optiv Case Study 2."
    ),
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class LoadCaseArtifactRequest(BaseModel):
    artifact_name: str


class LLMHandoffRequest(BaseModel):
    prompt_instruction: str = "Summarize key governance, risk appetite, and control owners without PII."


@app.get("/api/health")
def health_check() -> Dict[str, Any]:
    return {
        "status": "healthy",
        "service": "Cadence PII Detection & Secure Redaction Gateway",
        "policy": get_policy().model_dump(),
    }


@app.get("/api/policy", response_model=PolicyConfig)
def read_policy() -> PolicyConfig:
    return get_policy()


@app.put("/api/policy", response_model=PolicyConfig)
def modify_policy(new_policy: PolicyConfig) -> PolicyConfig:
    updated = update_policy(new_policy)
    PIPELINE_MANAGER.detector.policy = updated
    PIPELINE_MANAGER.record_audit(
        stage="POLICY_CONFIG",
        action="Updated detection thresholds, redaction mode, or LLM gate policy.",
        details={
            "auto_redact_threshold": updated.auto_redact_threshold,
            "redaction_mode": updated.redaction_mode,
            "downstream_llm_enabled": updated.downstream_llm_enabled,
        },
    )
    return updated


@app.get("/api/case-artifacts")
def list_available_case_artifacts() -> List[Dict[str, Any]]:
    """List the supporting Case Study 2 artifacts available locally."""
    expected = [
        {
            "filename": "Cadence_Financial_Group_Organizational_Pack.pptx",
            "title": "Cadence Financial Group — Organizational Reference Pack",
            "format": "PPTX",
            "description": "9-slide leadership org chart, RACI accountability matrices, role holder directory, and metadata.",
        },
        {
            "filename": "Cadence_TPRM_Training.docx",
            "title": "Cadence OneTrust TPRM Training & Configuration Manual",
            "format": "DOCX",
            "description": "16-table Word manual with 35 embedded OneTrust screenshots, user group rosters, and metadata.",
        },
        {
            "filename": "Cadence_Group_Risk_Management_Policy__v6.0.pdf",
            "title": "Cadence Group Risk Management Policy v6.0",
            "format": "SCANNED_PDF",
            "description": "35-page scanned/image-based PDF containing risk registers, narrative incident prose, RCSA forms, and badge exhibits.",
        },
    ]
    out = []
    for item in expected:
        fpath = CASE_MATERIALS_DIR / item["filename"]
        already_loaded = next(
            (
                r.doc_id
                for r in PIPELINE_MANAGER.documents.values()
                if r.filename == item["filename"] and r.is_case_study_artifact
            ),
            None,
        )
        out.append(
            {
                **item,
                "present_on_disk": fpath.exists(),
                "file_size_bytes": fpath.stat().st_size if fpath.exists() else 0,
                "loaded_doc_id": already_loaded,
            }
        )
    return out


@app.post("/api/documents/load-case-artifact", response_model=DocumentRecord)
def load_case_artifact(req: LoadCaseArtifactRequest) -> DocumentRecord:
    try:
        return PIPELINE_MANAGER.load_case_study_artifact(req.artifact_name)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/documents/upload")
async def upload_documents(files: List[UploadFile] = File(...)) -> Dict[str, Any]:
    """Accept one or multiple files in a batch, validate signatures, extract, detect, redact, and validate."""
    processed: List[DocumentRecord] = []
    errors: List[Dict[str, str]] = []

    for upload in files:
        fname = upload.filename or "unnamed_artifact"
        try:
            content = await upload.read()
            rec = PIPELINE_MANAGER.process_uploaded_bytes(filename=fname, content=content)
            processed.append(rec)
        except FileValidationError as exc:
            PIPELINE_MANAGER.record_audit(
                stage="FILE_VALIDATION",
                action=f"Rejected unsafe or unsupported upload '{fname}'.",
                document_name=fname,
                gate_status="REJECTED",
                details={"reason": str(exc)},
            )
            errors.append({"filename": fname, "error": str(exc)})
        except Exception as exc:
            errors.append({"filename": fname, "error": f"Processing failure: {exc}"})

    if not processed and errors:
        raise HTTPException(status_code=400, detail={"processed": [], "errors": errors})

    return {
        "processed": [r.model_dump() for r in processed],
        "errors": errors,
    }


@app.get("/api/dashboard/summary")
def get_dashboard_summary() -> Dict[str, Any]:
    """Return aggregate consulting dashboard metrics across all processed documents."""
    docs = list(PIPELINE_MANAGER.documents.values())
    total_files = len(docs)
    total_pii = sum(d.active_findings_count for d in docs)

    by_category: Dict[str, int] = {}
    by_source_type: Dict[str, int] = {}
    by_format: Dict[str, int] = {}

    pass_count = 0
    review_count = 0
    fail_count = 0
    structure_scores: List[float] = []

    for d in docs:
        by_format[d.detected_format] = by_format.get(d.detected_format, 0) + 1
        for k, v in d.findings_by_category.items():
            by_category[k] = by_category.get(k, 0) + v
        for k, v in d.findings_by_source_type.items():
            by_source_type[k] = by_source_type.get(k, 0) + v
        if d.validation:
            structure_scores.append(d.validation.structure_metrics.overall_structure_score)
            if d.validation.gate_status == GateState.PASS:
                pass_count += 1
            elif d.validation.gate_status == GateState.REVIEW_REQUIRED:
                review_count += 1
            else:
                fail_count += 1

    avg_structure = (
        round(sum(structure_scores) / len(structure_scores), 4)
        if structure_scores
        else 1.0
    )

    return {
        "files_uploaded": total_files,
        "files_processed": total_files,
        "total_pii_detected": total_pii,
        "entities_by_category": by_category,
        "entities_by_source_type": by_source_type,
        "files_by_format": by_format,
        "gate_counts": {
            "PASS": pass_count,
            "REVIEW_REQUIRED": review_count,
            "FAIL": fail_count,
        },
        "files_requiring_review": review_count,
        "average_structure_retention": avg_structure,
        "documents": [
            {
                "doc_id": d.doc_id,
                "filename": d.filename,
                "file_size_bytes": d.file_size_bytes,
                "detected_format": d.detected_format,
                "upload_timestamp": d.upload_timestamp,
                "status": d.status,
                "processing_time_ms": d.processing_time_ms,
                "findings_count": d.active_findings_count,
                "unresolved_review_count": (
                    d.validation.unresolved_review_count if d.validation else 0
                ),
                "gate_status": d.validation.gate_status.value if d.validation else "UNKNOWN",
                "structure_retention_score": (
                    d.validation.structure_metrics.overall_structure_score
                    if d.validation
                    else 1.0
                ),
                "residual_pii_found": (
                    d.validation.residual_pii_found if d.validation else False
                ),
                "is_case_study_artifact": d.is_case_study_artifact,
            }
            for d in docs
        ],
    }


@app.get("/api/documents", response_model=List[DocumentRecord])
def list_documents() -> List[DocumentRecord]:
    return list(PIPELINE_MANAGER.documents.values())


@app.get("/api/documents/{doc_id}", response_model=DocumentRecord)
def get_document_detail(doc_id: str) -> DocumentRecord:
    if doc_id not in PIPELINE_MANAGER.documents:
        raise HTTPException(status_code=404, detail=f"Document {doc_id} not found.")
    return PIPELINE_MANAGER.documents[doc_id]


@app.get("/api/documents/{doc_id}/preview/{version}/{page_no}")
def get_document_page_preview(
    doc_id: str, version: str, page_no: int = 1
) -> Response:
    if version not in {"original", "redacted"}:
        raise HTTPException(status_code=400, detail="version must be 'original' or 'redacted'")
    try:
        png_bytes = PIPELINE_MANAGER.get_page_preview_png(
            doc_id=doc_id, version=version, page_no=page_no
        )
        return Response(content=png_bytes, media_type="image/png")
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.patch(
    "/api/documents/{doc_id}/findings/{finding_id}",
    response_model=DocumentRecord,
)
def update_finding_endpoint(
    doc_id: str, finding_id: str, req: FindingUpdateRequest
) -> DocumentRecord:
    try:
        return PIPELINE_MANAGER.update_finding(doc_id, finding_id, req)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post(
    "/api/documents/{doc_id}/findings/approve-all",
    response_model=DocumentRecord,
)
def approve_all_flagged_endpoint(doc_id: str) -> DocumentRecord:
    try:
        return PIPELINE_MANAGER.approve_all_flagged_findings(doc_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post(
    "/api/documents/{doc_id}/findings/manual",
    response_model=DocumentRecord,
)
def add_manual_finding_endpoint(
    doc_id: str, req: ManualFindingCreateRequest
) -> DocumentRecord:
    try:
        return PIPELINE_MANAGER.add_manual_finding(doc_id, req)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/documents/{doc_id}/export/artifact")
def download_redacted_artifact(doc_id: str) -> Response:
    """Download the redacted document in its native file format (.pdf, .docx, .pptx, .png, .jpg)."""
    try:
        out_name, mime_type, data = PIPELINE_MANAGER.get_redacted_bytes(doc_id)
        return Response(
            content=data,
            media_type=mime_type,
            headers={
                "Content-Disposition": f'attachment; filename="{out_name}"',
            },
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/documents/{doc_id}/export/findings-report")
def export_findings_report(
    doc_id: str,
    format: str = Query(default="json", pattern="^(json|csv)$"),
    include_raw_pii: bool = Query(default=False),
) -> Response:
    """
    Export the PII findings report for a document.
    By default, exports masked previews ([MA***LE]) and replacement tokens rather than raw PII
    to maintain audit hygiene.
    """
    if doc_id not in PIPELINE_MANAGER.documents:
        raise HTTPException(status_code=404, detail=f"Document {doc_id} not found.")
    rec = PIPELINE_MANAGER.documents[doc_id]

    rows = []
    for f in rec.findings:
        rows.append(
            {
                "finding_id": f.finding_id,
                "document_name": f.document_name,
                "page_or_slide": f.page_or_slide,
                "source_type": f.source_type,
                "location_ref": f.location_ref,
                "char_start": f.char_start,
                "char_end": f.char_end,
                "category": f.category.value,
                "masked_preview": f.entity_text if include_raw_pii else f.masked_preview,
                "replacement_label": f.replacement_label,
                "stable_token": f.stable_token,
                "confidence": f.confidence,
                "detection_method": f.detection_method,
                "rationale": f.rationale,
                "redaction_method": f.redaction_method,
                "review_status": f.review_status.value,
            }
        )

    if format == "csv":
        buf = io.StringIO()
        if rows:
            writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
        return Response(
            content=buf.getvalue().encode("utf-8"),
            media_type="text/csv",
            headers={
                "Content-Disposition": f'attachment; filename="{rec.doc_id}_findings_report.csv"'
            },
        )

    report_payload = {
        "doc_id": rec.doc_id,
        "filename": rec.filename,
        "detected_format": rec.detected_format,
        "upload_timestamp": rec.upload_timestamp,
        "extraction_profile": rec.extraction_profile.model_dump(),
        "total_findings": rec.findings_count,
        "active_findings": rec.active_findings_count,
        "findings_by_category": rec.findings_by_category,
        "findings_by_source_type": rec.findings_by_source_type,
        "validation_summary": rec.validation.model_dump() if rec.validation else None,
        "findings": rows,
    }
    return Response(
        content=json.dumps(report_payload, indent=2).encode("utf-8"),
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="{rec.doc_id}_findings_report.json"'
        },
    )


@app.get("/api/audit-log")
def get_sanitized_audit_log() -> List[Dict[str, Any]]:
    """Return the complete security audit trail (guaranteed free of raw PII values)."""
    return [evt.model_dump() for evt in PIPELINE_MANAGER.audit_log]


@app.post("/api/documents/{doc_id}/llm-handoff")
def downstream_llm_handoff(doc_id: str, req: LLMHandoffRequest) -> Dict[str, Any]:
    """Execute optional downstream LLM processing ONLY if Privacy Gate == PASS and opt-in is enabled."""
    try:
        return process_with_downstream_llm(doc_id, req.prompt_instruction)
    except PrivacyGateViolationError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/benchmark/run")
def execute_benchmark(refresh: bool = Query(default=False)) -> Dict[str, Any]:
    """Execute the synthetic PII benchmark across 28 text cases and 5 multi-format file fixtures."""
    return run_full_benchmark_suite(force_refresh=refresh)

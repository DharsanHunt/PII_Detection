"""Pydantic data models for extraction, PII detection, redaction, validation, and audit."""
from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field


class PIIEntityCategory(str, Enum):
    PERSON_NAME = "PERSON_NAME"
    EMAIL = "EMAIL"
    PHONE_NUMBER = "PHONE_NUMBER"
    ACCOUNT_NUMBER = "ACCOUNT_NUMBER"
    EMPLOYEE_ID = "EMPLOYEE_ID"
    GOVERNMENT_ID_STYLE = "GOVERNMENT_ID_STYLE"
    TAX_ID_PAN_STYLE = "TAX_ID_PAN_STYLE"
    ADDRESS = "ADDRESS"
    DATE_OF_BIRTH = "DATE_OF_BIRTH"


class ReviewStatus(str, Enum):
    APPROVED = "APPROVED"
    FLAGGED_REVIEW = "FLAGGED_REVIEW"
    REJECTED_FALSE_POSITIVE = "REJECTED_FALSE_POSITIVE"
    MANUAL_ADDED = "MANUAL_ADDED"


class GateState(str, Enum):
    PASS = "PASS"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    FAIL = "FAIL"


class BoundingBox(BaseModel):
    x0: float
    y0: float
    x1: float
    y1: float
    page_or_slide: int = 1
    coord_system: str = "points_or_pixels"


class TextBlockSegment(BaseModel):
    block_id: str
    source_type: Literal[
        "paragraph",
        "table_cell",
        "header",
        "footer",
        "slide_title",
        "slide_text",
        "speaker_note",
        "alt_text",
        "ocr_page",
        "ocr_embedded_image",
        "metadata",
    ]
    page_or_slide: int = 1
    location_ref: str
    text: str
    bbox: Optional[BoundingBox] = None
    ocr_confidence: Optional[float] = None
    image_ref: Optional[str] = None
    metadata_key: Optional[str] = None
    table_coords: Optional[Dict[str, int]] = None


class PIIFinding(BaseModel):
    finding_id: str
    document_id: str
    document_name: str
    page_or_slide: int
    source_type: str
    block_id: str
    location_ref: str
    char_start: int
    char_end: int
    bbox: Optional[BoundingBox] = None
    category: PIIEntityCategory
    entity_text: str
    masked_preview: str
    replacement_label: str
    stable_token: str
    confidence: float = Field(ge=0.0, le=1.0)
    detection_method: str
    rationale: str
    redaction_method: str
    review_status: ReviewStatus = ReviewStatus.APPROVED
    context_before: str = ""
    context_after: str = ""
    image_ref: Optional[str] = None


class StructureMetrics(BaseModel):
    source_pages_or_slides: int = 1
    output_pages_or_slides: int = 1
    page_retention_ratio: float = 1.0

    source_paragraphs: int = 0
    output_paragraphs: int = 0
    paragraph_retention_ratio: float = 1.0

    source_tables: int = 0
    output_tables: int = 0
    table_retention_ratio: float = 1.0

    source_text_blocks: int = 0
    output_text_blocks: int = 0
    text_block_distribution_score: float = 1.0

    reading_order_score: float = 1.0
    formatting_preservation_score: float = 1.0
    overall_structure_score: float = 1.0
    meets_80_percent_target: bool = True
    formula_explanation: str = (
        "Weighted composite: 25% Page/Slide Count Parity + 20% Table Structure Parity + "
        "20% Paragraph/Shape Block Parity + 20% Reading Order & Context Preservation + "
        "15% Native Formatting/Style Retention."
    )


class ResidualFindingSummary(BaseModel):
    location_ref: str
    category: str
    detection_method: str
    description: str


class ValidationResult(BaseModel):
    gate_status: GateState
    residual_pii_found: bool = False
    residual_findings_count: int = 0
    residual_findings: List[ResidualFindingSummary] = Field(default_factory=list)
    previously_detected_leaked_count: int = 0
    unresolved_review_count: int = 0
    low_confidence_count: int = 0
    metadata_sanitized: bool = True
    metadata_remaining_issues: List[str] = Field(default_factory=list)
    structure_metrics: StructureMetrics
    reasons: List[str] = Field(default_factory=list)
    llm_handoff_permitted: bool = False
    validated_at: str


class ExtractionProfile(BaseModel):
    detected_format: str
    mime_type: str
    is_scanned_document: bool = False
    total_pages_or_slides: int = 1
    ocr_pages_list: List[int] = Field(default_factory=list)
    native_text_pages_list: List[int] = Field(default_factory=list)
    tables_count: int = 0
    paragraphs_count: int = 0
    embedded_images_count: int = 0
    ocr_embedded_images_with_text: int = 0
    metadata_fields_extracted: int = 0
    extraction_notes: List[str] = Field(default_factory=list)


class BlockComparisonItem(BaseModel):
    block_id: str
    page_or_slide: int
    source_type: str
    location_ref: str
    original_text: str
    redacted_text: str
    has_pii: bool = False
    pii_count: int = 0


class DocumentRecord(BaseModel):
    doc_id: str
    filename: str
    file_size_bytes: int
    detected_format: Literal["PDF", "SCANNED_PDF", "DOCX", "PPTX", "PNG", "JPG"]
    mime_type: str
    upload_timestamp: str
    status: Literal[
        "UPLOADED",
        "EXTRACTING",
        "DETECTING",
        "REDACTED",
        "VALIDATED",
        "ERROR",
    ]
    processing_time_ms: float = 0.0
    extraction_profile: ExtractionProfile
    findings_count: int = 0
    active_findings_count: int = 0
    findings_by_category: Dict[str, int] = Field(default_factory=dict)
    findings_by_source_type: Dict[str, int] = Field(default_factory=dict)
    findings: List[PIIFinding] = Field(default_factory=list)
    block_comparisons: List[BlockComparisonItem] = Field(default_factory=list)
    validation: Optional[ValidationResult] = None
    limitations: List[str] = Field(default_factory=list)
    error_message: Optional[str] = None
    is_case_study_artifact: bool = False


class FindingUpdateRequest(BaseModel):
    review_status: Optional[ReviewStatus] = None
    category: Optional[PIIEntityCategory] = None
    replacement_label: Optional[str] = None


class ManualFindingCreateRequest(BaseModel):
    block_id: str
    exact_text: str
    category: PIIEntityCategory
    rationale: str = "Analyst manual addition during review"


class AuditEvent(BaseModel):
    event_id: str
    timestamp: str
    doc_id: Optional[str] = None
    document_name: Optional[str] = None
    stage: str
    action: str
    gate_status: Optional[str] = None
    details: Dict[str, Any] = Field(default_factory=dict)

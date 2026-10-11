"""Configuration and Policy Management for Cadence PII Detection & Secure Redaction."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, Literal
from pydantic import BaseModel, Field

BASE_DIR = Path(__file__).resolve().parent.parent.parent
CASE_MATERIALS_DIR = BASE_DIR / "case_study_materials" / "extracted" / "Case Study 2 Supporting Material"
BENCHMARK_XLSX_PATH = BASE_DIR / "case_study_materials" / "PII_Detection_Redaction_Test_Benchmark.xlsx"
TEMP_STORAGE_DIR = BASE_DIR / "backend" / "temp_storage"

DEFAULT_REPLACEMENT_LABELS: Dict[str, str] = {
    "PERSON_NAME": "[NAME REDACTED]",
    "EMAIL": "[EMAIL REDACTED]",
    "PHONE_NUMBER": "[PHONE REDACTED]",
    "ACCOUNT_NUMBER": "[ACCOUNT NUMBER REDACTED]",
    "EMPLOYEE_ID": "[EMPLOYEE ID REDACTED]",
    "GOVERNMENT_ID_STYLE": "[GOVERNMENT ID REDACTED]",
    "TAX_ID_PAN_STYLE": "[TAX ID REDACTED]",
    "ADDRESS": "[ADDRESS REDACTED]",
    "DATE_OF_BIRTH": "[DATE OF BIRTH REDACTED]",
}


class PolicyConfig(BaseModel):
    """Configurable security, detection, redaction, and privacy gate settings."""

    max_file_size_mb: int = Field(default=50, ge=1, le=200)
    max_page_count: int = Field(default=100, ge=1, le=500)
    max_processing_time_sec: int = Field(default=300, ge=10, le=1800)

    # Confidence thresholds
    auto_redact_threshold: float = Field(default=0.80, ge=0.1, le=1.0)
    review_required_threshold: float = Field(default=0.50, ge=0.05, le=0.99)

    # Structure target
    min_structure_retention: float = Field(default=0.80, ge=0.50, le=1.0)

    # Redaction token mode: CATEGORY_LABEL ([NAME REDACTED]) or STABLE_TOKEN ([PERSON_001])
    redaction_mode: Literal["CATEGORY_LABEL", "STABLE_TOKEN"] = "CATEGORY_LABEL"
    replacement_labels: Dict[str, str] = Field(
        default_factory=lambda: dict(DEFAULT_REPLACEMENT_LABELS)
    )

    # OCR and deep inspection toggles
    enable_ocr_on_scanned_pages: bool = True
    enable_ocr_on_embedded_images: bool = True
    sanitize_metadata_and_comments: bool = True

    # Downstream LLM Gate (disabled by default per security requirements)
    downstream_llm_enabled: bool = False
    downstream_llm_provider: str = "Local-Mock-Summarizer (No External Data Egress)"


GLOBAL_POLICY = PolicyConfig()


def get_policy() -> PolicyConfig:
    return GLOBAL_POLICY


def update_policy(new_policy: PolicyConfig) -> PolicyConfig:
    global GLOBAL_POLICY
    GLOBAL_POLICY = new_policy
    return GLOBAL_POLICY

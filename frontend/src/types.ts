export type PIIEntityCategory =
  | 'PERSON_NAME'
  | 'EMAIL'
  | 'PHONE_NUMBER'
  | 'ACCOUNT_NUMBER'
  | 'EMPLOYEE_ID'
  | 'GOVERNMENT_ID_STYLE'
  | 'TAX_ID_PAN_STYLE'
  | 'ADDRESS'
  | 'DATE_OF_BIRTH';

export type ReviewStatus =
  | 'APPROVED'
  | 'FLAGGED_REVIEW'
  | 'REJECTED_FALSE_POSITIVE'
  | 'MANUAL_ADDED';

export type GateState = 'PASS' | 'REVIEW_REQUIRED' | 'FAIL';

export interface BoundingBox {
  x0: number;
  y0: number;
  x1: number;
  y1: number;
  page_or_slide: number;
  coord_system: string;
}

export interface PIIFinding {
  finding_id: string;
  document_id: string;
  document_name: string;
  page_or_slide: number;
  source_type: string;
  block_id: string;
  location_ref: string;
  char_start: number;
  char_end: number;
  bbox?: BoundingBox | null;
  category: PIIEntityCategory;
  entity_text: string;
  masked_preview: string;
  replacement_label: string;
  stable_token: string;
  confidence: number;
  detection_method: string;
  rationale: string;
  redaction_method: string;
  review_status: ReviewStatus;
  context_before: string;
  context_after: string;
  image_ref?: string | null;
}

export interface StructureMetrics {
  source_pages_or_slides: number;
  output_pages_or_slides: number;
  page_retention_ratio: number;
  source_paragraphs: number;
  output_paragraphs: number;
  paragraph_retention_ratio: number;
  source_tables: number;
  output_tables: number;
  table_retention_ratio: number;
  source_text_blocks: number;
  output_text_blocks: number;
  text_block_distribution_score: number;
  reading_order_score: number;
  formatting_preservation_score: number;
  overall_structure_score: number;
  meets_80_percent_target: boolean;
  formula_explanation: string;
}

export interface ResidualFindingSummary {
  location_ref: string;
  category: string;
  detection_method: string;
  description: string;
}

export interface ValidationResult {
  gate_status: GateState;
  residual_pii_found: boolean;
  residual_findings_count: number;
  residual_findings: ResidualFindingSummary[];
  previously_detected_leaked_count: number;
  unresolved_review_count: number;
  low_confidence_count: number;
  metadata_sanitized: boolean;
  metadata_remaining_issues: string[];
  structure_metrics: StructureMetrics;
  reasons: string[];
  llm_handoff_permitted: boolean;
  validated_at: string;
}

export interface ExtractionProfile {
  detected_format: string;
  mime_type: string;
  is_scanned_document: boolean;
  total_pages_or_slides: number;
  ocr_pages_list: number[];
  native_text_pages_list: number[];
  tables_count: number;
  paragraphs_count: number;
  embedded_images_count: number;
  ocr_embedded_images_with_text: number;
  metadata_fields_extracted: number;
  extraction_notes: string[];
}

export interface BlockComparisonItem {
  block_id: string;
  page_or_slide: number;
  source_type: string;
  location_ref: string;
  original_text: string;
  redacted_text: string;
  has_pii: boolean;
  pii_count: number;
}

export interface DocumentRecord {
  doc_id: string;
  filename: string;
  file_size_bytes: number;
  detected_format: 'PDF' | 'SCANNED_PDF' | 'DOCX' | 'PPTX' | 'PNG' | 'JPG';
  mime_type: string;
  upload_timestamp: string;
  status: string;
  processing_time_ms: number;
  extraction_profile: ExtractionProfile;
  findings_count: number;
  active_findings_count: number;
  findings_by_category: Record<string, number>;
  findings_by_source_type: Record<string, number>;
  findings: PIIFinding[];
  block_comparisons: BlockComparisonItem[];
  validation: ValidationResult | null;
  limitations: string[];
  error_message?: string | null;
  is_case_study_artifact: boolean;
}

export interface DashboardSummary {
  files_uploaded: number;
  files_processed: number;
  total_pii_detected: number;
  entities_by_category: Record<string, number>;
  entities_by_source_type: Record<string, number>;
  files_by_format: Record<string, number>;
  gate_counts: {
    PASS: number;
    REVIEW_REQUIRED: number;
    FAIL: number;
  };
  files_requiring_review: number;
  average_structure_retention: number;
  documents: Array<{
    doc_id: string;
    filename: string;
    file_size_bytes: number;
    detected_format: string;
    upload_timestamp: string;
    status: string;
    processing_time_ms: number;
    findings_count: number;
    unresolved_review_count: number;
    gate_status: GateState;
    structure_retention_score: number;
    residual_pii_found: boolean;
    is_case_study_artifact: boolean;
  }>;
}

export interface CaseArtifactInfo {
  filename: string;
  title: string;
  format: string;
  description: string;
  present_on_disk: boolean;
  file_size_bytes: number;
  loaded_doc_id: string | null;
}

export interface PolicyConfig {
  max_file_size_mb: number;
  max_page_count: number;
  max_processing_time_sec: number;
  auto_redact_threshold: number;
  review_required_threshold: number;
  min_structure_retention: number;
  redaction_mode: 'CATEGORY_LABEL' | 'STABLE_TOKEN';
  replacement_labels: Record<string, string>;
  enable_ocr_on_scanned_pages: boolean;
  enable_ocr_on_embedded_images: boolean;
  sanitize_metadata_and_comments: boolean;
  downstream_llm_enabled: boolean;
  downstream_llm_provider: string;
}

export interface AuditEvent {
  event_id: string;
  timestamp: string;
  doc_id?: string | null;
  document_name?: string | null;
  stage: string;
  action: string;
  gate_status?: string | null;
  details: Record<string, unknown>;
}

export interface BenchmarkReport {
  evaluated_at: string;
  text_benchmark_summary: {
    total_cases: number;
    exact_case_matches: number;
    expected_entities_total: number;
    true_positives: number;
    false_positives: number;
    false_negatives: number;
    precision: number;
    recall: number;
    f1_score: number;
    negative_cases_total: number;
    negative_cases_zero_fp: number;
    false_positive_rate_on_negatives: number;
    residual_pii_count: number;
  };
  file_format_metrics: Array<{
    file_type: string;
    expected_pii_count: number;
    detected_pii_count: number;
    true_positives: number;
    false_positives: number;
    false_negatives: number;
    precision: number;
    recall: number;
    f1_score: number;
    residual_pii_count: number;
    residual_pii_detected: boolean;
    structure_retention_score: number;
    extraction_quality_score: number;
    gate_status: string;
  }>;
  aggregate_file_summary: {
    formats_tested: number;
    true_positives: number;
    false_positives: number;
    false_negatives: number;
    precision: number;
    recall: number;
    f1_score: number;
    residual_pii_count: number;
    average_structure_retention: number;
    average_extraction_quality: number;
  };
  xlsx_cases: Array<{
    case_id: string;
    input_type: string;
    scenario: string;
    difficulty: string;
    expected_count: number;
    detected_count: number;
    expected_entities: string;
    actual_entities: string;
    expected_redacted: string;
    actual_redacted: string;
    exact_match: boolean;
    residual_pii_count: number;
    status: string;
  }>;
}

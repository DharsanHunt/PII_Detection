# Technical Methodology: Format-Aware PII Detection, Genuine Redaction & Structure Preservation

**Client:** Cadence Financial Group (Optiv Cyber Simulation — Case Study 2)

---

## 1. Methodology Overview

Enterprise documents rarely store sensitive information in a single uniform text layer. Our initial forensic inspection of Cadence Financial Group’s supporting artifacts revealed three distinct document archetypes:
1. **`Cadence_Financial_Group_Organizational_Pack.pptx`**: A 9-slide presentation containing executive org charts, RACI matrices, a 25-row role holder directory table, and package metadata (`[OC] Divisha Kilari`).
2. **`Cadence_TPRM_Training.docx`**: A 394-paragraph Word manual with 16 tables (including user group rosters in Table 4 and document contacts in Table 14), package metadata (`[OC] Madhav Mehta`, `[OC] Divisha Kilari`), and **35 embedded PNG screenshots** of the OneTrust TPRM web interface (`word/media/image*.png`), four of which (`image10.png`, `image12.png`, `image35.png`, `image38.png`) display visible employee names and emails inside UI tables.
3. **`Cadence_Group_Risk_Management_Policy__v6.0.pdf`**: A **35-page 100% scanned/rasterized PDF** (`0` selectable characters on every page) containing dense governance text, risk registers, narrative breach reports (Sections 16.5 & 16.8), a signed RCSA form (Figure 8), a SecureGRC screenshot (Figure 9), an employee physical access badge with DOB and emergency phone (Figure 13), and PDF dictionary author metadata (`[OC] Aditya Lawand`).

To sanitize these artifacts without flattening them into plain text, we engineered a **13-stage format-aware pipeline** implemented in [`backend/app/services/pipeline.py`](file:///c:/Users/dhars/Projects/PII%20remover/backend/app/services/pipeline.py).

---

## 2. File Validation & Security Hygiene

Implemented in [`backend/app/extractors/file_validator.py`](file:///c:/Users/dhars/Projects/PII%20remover/backend/app/extractors/file_validator.py):
- **Extension & Magic-Byte Verification:** Every upload is checked against both its filename extension and its binary header signature (`%PDF-` for PDFs, `PK\x03\x04` with `[Content_Types].xml` and `word/document.xml` or `ppt/presentation.xml` for OOXML packages, `\x89PNG\r\n\x1a\n` for PNG, and `\xff\xd8\xff` for JPEG).
- **Archive & Zip-Bomb Protection:** OOXML archives (`.docx`, `.pptx`) are inspected member-by-member to block path traversal (`..` or leading slashes) and enforce a maximum uncompressed size ceiling ($250\text{ MB}$) to prevent decompression bombs.
- **Encryption & Policy Limits:** Encrypted/password-protected PDFs, 0-byte files, and files exceeding configurable size ($50\text{ MB}$), page count ($100\text{ pages}$), or processing time limits are rejected with structured error messages.
- **Controlled Ephemeral Storage:** Uploaded bytes are written to [`backend/temp_storage/`](file:///c:/Users/dhars/Projects/PII%20remover/backend/temp_storage) with restricted `0600` permissions and unlinked inside a `finally` block as soon as processing completes. Original Case Study 2 files are opened in read-only mode and never modified.

---

## 3. Format-Aware Extraction & OCR Coordinate Mapping

Each supported format uses a dedicated extractor that emits normalized [`TextBlockSegment`](file:///c:/Users/dhars/Projects/PII%20remover/backend/app/models.py#L43-L66) records containing exact character text, structural provenance (`paragraph`, `table_cell`, `header`, `footer`, `slide_title`, `slide_text`, `speaker_note`, `ocr_page`, `ocr_embedded_image`, `metadata`), page/slide number, and bounding-box coordinates (`BoundingBox`).

### A. Native Text PDFs & Scanned PDFs ([`pdf_extractor.py`](file:///c:/Users/dhars/Projects/PII%20remover/backend/app/extractors/pdf_extractor.py))
- For each page in a PDF, we inspect `page.get_text("blocks")` and `page.get_images()`.
- **Native Text Pages:** When selectable text is present, blocks are sorted in top-to-bottom, left-to-right reading order with exact PDF point coordinates `(x0, y0, x1, y1)` and classified into `header`, `footer`, or `paragraph` based on vertical page position.
- **Scanned / Image-Based Pages:** When a page has `< 15` native characters and contains a full-page raster image (such as all 35 pages of `Cadence_Group_Risk_Management_Policy__v6.0.pdf`), the page is rendered at `150–200 DPI` and passed to our local [`RapidOCR` engine](file:///c:/Users/dhars/Projects/PII%20remover/backend/app/extractors/ocr_engine.py).
- **Proportional Sub-Bounding-Box Interpolation:** Because OCR engines return bounding boxes for entire detected text lines (e.g., `"Owner: Vikram Nair | EMP-1048"`), redacting the entire OCR line would destroy the label `"Owner:"`. Our function [`interpolate_subspan_bbox`](file:///c:/Users/dhars/Projects/PII%20remover/backend/app/extractors/ocr_engine.py#L106-L148) calculates character-width-weighted horizontal sub-boxes so only `"Vikram Nair"` and `"EMP-1048"` are pixel-redacted while `"Owner:"` remains visible!

### B. Word Documents ([`docx_extractor.py`](file:///c:/Users/dhars/Projects/PII%20remover/backend/app/extractors/docx_extractor.py))
- Extracts body paragraphs, section headers and footers, and all tables/rows/cells (preserving `(table_idx, row_idx, col_idx)` coordinates and deduplicating merged Word grid cells by explicit `(r_idx, c_idx)` tracking).
- Extracts package metadata (`author`, `last_modified_by`, `title`, `subject`, `comments`).
- **Embedded Screenshot OCR:** Iterates over `word/media/image*.(png|jpg|jpeg)` inside the `.docx` ZIP container. Screenshots exceeding minimum UI dimensions are passed through `RapidOCR`, mapping any visible PII inside application screenshots back to exact pixel bounding boxes inside that specific archive member.

### C. PowerPoint Presentations ([`pptx_extractor.py`](file:///c:/Users/dhars/Projects/PII%20remover/backend/app/extractors/pptx_extractor.py))
- Traverses every slide in presentation order, extracting slide titles, text frames, grouped shapes, table cells, speaker notes (`notes_slide`), shape alt-text, package metadata, and embedded slide images (`ppt/media/*`).

### D. Standalone Images ([`image_extractor.py`](file:///c:/Users/dhars/Projects/PII%20remover/backend/app/extractors/image_extractor.py))
- Extracts EXIF/text metadata and runs `RapidOCR` to recover text lines, confidence scores, and pixel bounding boxes.

---

## 4. Hybrid PII Detection, Classification & Confidence Scoring

Implemented in [`backend/app/detectors/hybrid_detector.py`](file:///c:/Users/dhars/Projects/PII%20remover/backend/app/detectors/hybrid_detector.py), our detection engine combines four complementary layers across **9 policy PII categories**:

| Category | Detection Strategy | Replacement Label | Stable Token Prefix |
| :--- | :--- | :--- | :--- |
| `PERSON_NAME` | Labeled role/contact cues, narrative prose contextual NER, abbreviated initial patterns (`Miriam T. Achebe`), tabular column alignment, and organizational directory gazetteer | `[NAME REDACTED]` | `[PERSON_xxx]` |
| `EMAIL` | RFC-5322-aligned regex matcher with boundary validation | `[EMAIL REDACTED]` | `[EMAIL_xxx]` |
| `PHONE_NUMBER` | International (`+44`, `+91`, `+1`, `+49`, `+65`) & domestic parenthesized/hyphenated patterns with date/version exclusion guards | `[PHONE REDACTED]` | `[PHONE_xxx]` |
| `EMPLOYEE_ID` | Cadence identifier rules (`EMP-\d{3,6}`, `EMP-TEST-\d{3}`, `DIR-\d{4}`, `MER-[A-Z]{2}-\d{4}`) | `[EMPLOYEE ID REDACTED]` | `[EMP_ID_xxx]` |
| `GOVERNMENT_ID_STYLE` | US SSN (`\d{3}-\d{2}-\d{4}`), 12-digit national ID (`\d{4}\s\d{4}\s\d{4}`), Passport references, Polish PESEL, contextual SSN last-4 | `[GOVERNMENT ID REDACTED]` | `[GOV_ID_xxx]` |
| `TAX_ID_PAN_STYLE` | 10-character PAN format (`[A-Z]{5}[0-9]{4}[A-Z]`) with OCR `O`/`0` substitution tolerance | `[TAX ID REDACTED]` | `[TAX_ID_xxx]` |
| `ACCOUNT_NUMBER` | Contextual 10–16 digit account numbers & customer correspondence card/account ending digits (excluding masked `**** 0000`) | `[ACCOUNT NUMBER REDACTED]` | `[ACCOUNT_xxx]` |
| `ADDRESS` | Street number + thoroughfare suffix (`Road`, `Street`, `Lane`, `Avenue`, `Crescent`, `Court`) + locality + postal code (excluding corporate HQ address) | `[ADDRESS REDACTED]` | `[ADDRESS_xxx]` |
| `DATE_OF_BIRTH` | Contextual DOB matcher following `date of birth`, `DOB`, `born on`, or badge DOB fields (never flags ordinary policy effective dates) | `[DATE OF BIRTH REDACTED]` | `[DOB_xxx]` |

### False-Positive Suppression
To prevent over-redaction that would degrade downstream LLM comprehension:
- **Role & Governance Whitelist:** Titles such as *Chief Risk Officer*, *Head of Third-Party Risk*, *Group Risk Committee*, *Cadence Financial Group*, and *Blue River Financial Services* are explicitly excluded from `PERSON_NAME` matches.
- **Numeric & Calendar Guards:** Currency values (`INR 84,250.00`, `$25,000,000`), policy version numbers (`v6.0`), ISO/regulatory citations (`ISO 27001`), masked card numbers (`**** 0000`), and calendar month lists (`May, June and August`) are suppressed.

### Confidence Assessment & Routing
Each finding receives a composite confidence score $C \in [0.0, 1.0]$ combining detector certainty with OCR line confidence (when extracted from images):
- **$C \ge 0.80$ (Auto-Redact Threshold):** Automatically marked `APPROVED` and redacted.
- **$0.50 \le C < 0.80$ (Review Threshold):** Redacted in the candidate output AND marked `FLAGGED_REVIEW`, placing the document into `GateStatus.REVIEW_REQUIRED` until an analyst approves or rejects the finding.

---

## 5. Genuine Format-Preserving Redaction Engine

We strictly reject cosmetic masking (such as drawing a visual rectangle over selectable text). Each format redactor permanently purges the underlying sensitive data:

1. **PDF Redactor ([`pdf_redactor.py`](file:///c:/Users/dhars/Projects/PII%20remover/backend/app/redactors/pdf_redactor.py)):**
   - **Native PDF Pages:** Uses `page.add_redact_annot(rect, text=label)` followed by `page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_PIXELS)` to permanently remove characters from the PDF content stream.
   - **Scanned PDF Pages:** Renders the raster page, overwrites the exact interpolated bounding box pixels with a solid dark redaction fill + crisp replacement label (`[NAME REDACTED]`), and rebuilds the page image so original pixels are destroyed.
   - **PDF Metadata Scrubbing:** Clears `author`, `creator`, `producer`, `subject`, and `keywords` in the PDF Info dictionary and strips XMP XML packets.
2. **Word DOCX Redactor ([`docx_redactor.py`](file:///c:/Users/dhars/Projects/PII%20remover/backend/app/redactors/docx_redactor.py)):**
   - **Cross-Run DOM Replacement (`_replace_spans_across_runs`):** Concatenates paragraph run texts (`<w:r>`), locates the exact `[char_start, char_end]` span even when a name or email is split across bold/italic/font-size formatting runs, places the replacement token in the starting run, and slices out all covered characters from subsequent runs while keeping each run’s `rPr` styling intact.
   - **Embedded Media Scrubbing:** Opens the `.docx` archive, applies pixel-level redaction to any `word/media/image*.png` screenshot containing OCR-detected PII, and repackages the `.docx`.
   - **Core Properties Scrubbing:** Sanitizes `core_properties.author`, `last_modified_by`, and `comments`.
3. **PowerPoint PPTX Redactor ([`pptx_redactor.py`](file:///c:/Users/dhars/Projects/PII%20remover/backend/app/redactors/pptx_redactor.py)):**
   - Applies cross-run replacement across slide titles, text boxes, grouped shapes, table cells, and speaker notes, scrubs `ppt/media/*` images if needed, and sanitizes `core_properties`.
4. **Standalone Image Redactor ([`image_redactor.py`](file:///c:/Users/dhars/Projects/PII%20remover/backend/app/redactors/image_redactor.py)):**
   - Overwrites bounding-box pixels in-place using `ImageDraw.rectangle` and strips EXIF metadata by saving a clean pixel buffer.

---

## 6. Structure Preservation & Independent Privacy Gate Validation

Implemented in [`backend/app/validators/privacy_gate.py`](file:///c:/Users/dhars/Projects/PII%20remover/backend/app/validators/privacy_gate.py):

### Independent Re-Extraction Verification
Rather than trusting that redaction succeeded, the validator takes the **redacted output byte stream** and runs it back through the format-specific extractor (`extract_pdf_document`, `extract_docx_document`, `extract_pptx_document`, `extract_image_document`) and `HybridPIIDetector`:
1. **Residual PII Scan:** Checks if any new or remaining PII pattern exists in the redacted output (ignoring our own `[... REDACTED]` and `[PERSON_001]` tokens).
2. **Known-Entity Leak Check:** Verifies that none of the approved original PII strings (`len >= 4`) survive anywhere in the redacted text or table cells.
3. **Metadata Verification:** Confirms `author` and `last_modified_by` no longer contain personal names.

### Quantitative Structure Retention Formula (Target $\ge 80\%$)
We compute a transparent, weighted composite **Overall Structure Retention Score**:
$$\text{Structure Score} = 0.25 \cdot R_{\text{pages}} + 0.20 \cdot R_{\text{tables}} + 0.20 \cdot R_{\text{paragraphs}} + 0.20 \cdot R_{\text{reading\_order}} + 0.15 \cdot R_{\text{formatting}}$$
where:
- $R_{\text{pages}} = 1 - \frac{|P_{\text{out}} - P_{\text{src}}|}{\max(1, P_{\text{src}})}$ measures page/slide count parity ($1.00$ across all 3 Case Study artifacts).
- $R_{\text{tables}} = 1 - \frac{|T_{\text{out}} - T_{\text{src}}|}{\max(1, T_{\text{src}})}$ measures table structure parity ($1.00$ across all 16 DOCX tables and 5 PPTX tables).
- $R_{\text{paragraphs}}$ measures paragraph/text-block count parity.
- $R_{\text{reading\_order}}$ measures non-PII surrounding context retention across blocks.
- $R_{\text{formatting}}$ measures preservation of native container styles and layout dimensions.
All three Case Study 2 documents achieve **$98.60\%$ to $99.85\%$** structure retention—well above the $80\%$ requirement.

# 10–15 Minute Live Demonstration & Presentation Script

**Title:** Optiv Cyber Simulation — Case Study 2: Cadence Financial Group PII Detection & Secure Document Redaction Gateway  
**Companion Slide Deck:** [`docs/Cadence_PII_Redaction_Architecture_and_Demo.pptx`](file:///c:/Users/dhars/Projects/PII%20remover/docs/Cadence_PII_Redaction_Architecture_and_Demo.pptx)

---

## Agenda & Timing Breakdown (12–15 Minutes Total)

| Segment | Duration | Focus Area |
| :--- | :---: | :--- |
| **1. Executive Context & Threat Model** | `0:00 – 2:30` | Why Cadence Financial Group needs format-aware binary/pixel redaction and a strict server-side Privacy Gate before any LLM handoff (Slides 1–2). |
| **2. Architecture & Hybrid Engine Walkthrough** | `2:30 – 5:30` | The 13-stage pipeline, format-specific extractors/redactors, proportional OCR sub-bounding-box mapping, and false-positive suppression (Slides 3–7). |
| **3. Live Application Demo: Ingestion & Triage** | `5:30 – 8:30` | Loading the 3 Case Study 2 supporting artifacts, demonstrating spoofed-file rejection, and inspecting the Consulting Dashboard. |
| **4. Live Application Demo: Review Studio & Privacy Gate** | `8:30 – 12:00` | Inspecting PPTX RACI tables, DOCX embedded OneTrust screenshots, and the 35-page Scanned Risk Policy PDF; resolving `REVIEW_REQUIRED` $\rightarrow$ `PASS` and testing the Downstream LLM Firewall. |
| **5. Benchmark Evaluation & Audit Governance** | `12:00 – 14:30` | Running the 28-case Gold Benchmark + 5-format reliability suite ($100\%$ F1) and verifying the Zero-PII Security Audit Trail (Slides 8–10). |

---

## Detailed Speaker Script & Demonstration Steps

### Segment 1: Executive Context & Threat Model (`0:00 – 2:30`)
* **[Display Slides 1 & 2 of `Cadence_PII_Redaction_Architecture_and_Demo.pptx`]**
* **Talking Points:**
  - *"Welcome. Today we are presenting our engineering solution for Cadence Financial Group under Optiv Case Study 2: Text Analysis and PII Detection within Artifacts."*
  - *"Cadence wants to leverage Large Language Models to analyze internal organizational documents—org charts, TPRM training manuals, and risk management policies. However, our forensic inspection of their artifacts revealed 963 instances of sensitive PII hidden across four distinct layers: native body text and tables, package author metadata, 35 embedded OneTrust UI screenshots inside a Word manual, and a 35-page 100% scanned PDF containing zero selectable characters."*
  - *"If we simply flatten documents to plain text, we lose tables, RACI accountability matrices, and layout structure. Conversely, if we draw cosmetic black rectangles over a PDF or perform naive substring replacement in Word, underlying text streams, split XML runs, and embedded screenshots still leak PII."*
  - *"Our architecture enforces one non-negotiable security invariant: **No document content can ever reach a downstream LLM until format-aware PII detection, genuine binary/pixel redaction, and independent post-redaction re-extraction validation have passed (`Gate == PASS`).**"*

---

### Segment 2: Architecture, Format-Aware Redaction & Hybrid Detection (`2:30 – 5:30`)
* **[Display Slides 3, 4, 5, 6, and 7]**
* **Talking Points:**
  - *"Slide 3 illustrates our 13-stage pipeline. Every upload first passes magic-byte signature verification and zip-bomb checks before entering a format-specific extractor."*
  - *"For **Word (`.docx`)** and **PowerPoint (`.pptx`)**, we built a cross-run OOXML DOM redactor (`_replace_spans_across_runs`) that tracks character offsets across split `<w:r>` and `<a:r>` formatting runs so names split by bold/italic tags are completely removed without breaking table borders or slide themes. Crucially, our extractor also unpacks `word/media/` and `ppt/media/` images, runs offline `RapidOCR` (PaddleOCR PP-OCRv4 ONNX), and overwrites sensitive pixels inside embedded screenshots in-place."*
  - *"For **PDFs**, our engine automatically distinguishes native text pages from rasterized scanned pages. On scanned pages—such as all 35 pages of `Cadence_Group_Risk_Management_Policy__v6.0.pdf`—OCR returns line-level bounding boxes like `'Owner: Vikram Nair | EMP-1048'`. Rather than blacking out the entire line and destroying `'Owner:'`, our `interpolate_subspan_bbox()` algorithm calculates character-width-weighted horizontal sub-boxes so only `'Vikram Nair'` and `'EMP-1048'` are pixel-destroyed while surrounding context stays readable."*
  - *"Slide 6 shows our Hybrid Detection Engine: deterministic regexes for Emails, Phones, Employee/Director IDs, PAN Tax IDs (with OCR `0`/`O` tolerance), Government IDs, Account Numbers, and DOBs, paired with contextual NER for personal names and addresses, plus strict false-positive suppression so committee names, role titles ('Chief Risk Officer'), currency figures, and policy versions ('v6.0') are never over-redacted."*

---

### Segment 3: Live Application Demo — Ingestion, Security Gate & Dashboard (`5:30 – 8:30`)
* **[Switch to Browser at `http://localhost:5173` — Upload & Case Study Tab]**
* **Live Actions:**
  1. Point out the top security header showing **Local Processing Only** and the active policy controls (`CATEGORY_LABEL` mode `[NAME REDACTED]` vs `STABLE_TOKEN` mode `[PERSON_001]`).
  2. Click **"Load All 3 Case Study Artifacts"** (or click Load on each of the 3 official Cadence files: `Cadence_Financial_Group_Organizational_Pack.pptx`, `Cadence_TPRM_Training.docx`, and `Cadence_Group_Risk_Management_Policy__v6.0.pdf`).
  3. Switch to the **Executive Dashboard** tab:
     - Highlight the **963 total PII findings** across the 3 documents.
     - Show the breakdown by category (`PERSON_NAME`, `EMPLOYEE_ID`, `EMAIL`, `PHONE_NUMBER`, `GOVERNMENT_ID_STYLE`, `TAX_ID_PAN_STYLE`, `ACCOUNT_NUMBER`, `ADDRESS`, `DATE_OF_BIRTH`) and by structural source (`ocr_page`, `table_cell`, `slide_text`, `ocr_embedded_image`, `metadata`).
     - Highlight the **Average Structure Retention Score ($99.4\%$)**—far exceeding the $80\%$ requirement.

---

### Segment 4: Live Application Demo — Review Studio, Embedded Screenshots & Privacy Gate (`8:30 – 12:00`)
* **[Switch to the Document Review Studio Tab]**
* **Live Actions:**
  1. **Inspect `Cadence_Financial_Group_Organizational_Pack.pptx`:**
     - Show that `123` findings were redacted across all 9 slides and 5 tables (`99.85%` structure retention, `GateStatus = PASS`).
     - In the **Block-by-Block Comparison** view, show how RACI roles (`Chief Risk Officer`, `Head of Compliance`) remain untouched while personal names, emails, and phones are replaced with `[NAME REDACTED]`, `[EMAIL REDACTED]`, and `[PHONE REDACTED]`.
  2. **Inspect `Cadence_TPRM_Training.docx`:**
     - Filter findings by source type `ocr_embedded_image` and `metadata`.
     - Point out that `21` findings were detected inside embedded OneTrust screenshots (`word/media/image10.png`, `image12.png`, `image35.png`, `image38.png`) and `2` in package metadata (`[OC] Madhav Mehta`, `[OC] Divisha Kilari`), alongside `28` findings in Tables 4 and 14.
  3. **Inspect `Cadence_Group_Risk_Management_Policy__v6.0.pdf` (35-Page Scanned PDF):**
     - Point out the **`REVIEW_REQUIRED`** badge: out of `789` OCR findings across 35 scanned pages, `1` finding had noisy OCR confidence below `0.80` and was automatically quarantined for human review.
     - Open the **Visual Page Preview (Original vs Redacted)** and navigate to **Page 1** (Document Control Table), **Page 22** (Figure 8 Signed RCSA Form), and **Page 32** (Figure 13 Employee Access Badge). Show how the redacted page permanently replaces the employee name, ID, DOB, and phone number in the image pixels while preserving the table grid and surrounding policy text!
     - **Test the Privacy Gate Block:** Try clicking **"Run Sanitized LLM Summary"** while the document is in `REVIEW_REQUIRED`. Show that the server immediately blocks the request.
     - **Approve the Flagged Finding:** Click **"Approve All Flagged"** (or approve the pending finding in the table). Watch the backend re-run redaction and independent re-extraction validation, transitioning the document from **`REVIEW_REQUIRED` $\rightarrow$ `PASS`**.
     - **Download Safe Exports:** Click **"Download Redacted Artifact"** (`.pdf`, `.docx`, `.pptx`) and **"Export JSON/CSV Findings Report"**.
     - **Optional Sanitized LLM Handoff:** Enable the opt-in LLM toggle in Policy Settings, click **"Run Sanitized LLM Summary"** on the `PASS` document, and show the exact sanitized payload preview verifying zero raw PII is ever transmitted.

---

### Segment 5: Live Benchmark Evaluation & Zero-PII Audit Log (`12:00 – 14:30`)
* **[Switch to the Benchmark & Reliability Tab, then Security Audit Log Tab]**
* **Live Actions:**
  1. Click **"Run Benchmark Suite"**:
     - Show **`28 / 28` Exact Case Matches** and **`49 / 49` Gold Entity Spans** (`100.0%` Precision, `100.0%` Recall, `100.0%` F1, `0` False Positives on negative trap cases `PII-020` to `PII-024`).
     - Show the **Per-Format Reliability Table** across Native PDF, Scanned PDF, DOCX, PPTX, and PNG (`100.0%` F1, `0` Residual PII, `98.6%–99.8%` structure retention).
  2. Switch to the **Security Audit Log** tab:
     - Demonstrate that every upload, validation, analyst review, export, and blocked/allowed LLM gate decision is recorded with timestamps and finding IDs, while **zero raw PII strings** appear anywhere in the logs.

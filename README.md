# Cadence Financial Group — PII Detection & Secure Document Redaction Gateway

**Optiv Cyber Simulation — Case Study 2: Text Analysis and PII Detection within Artifacts**

An enterprise-grade, local-first document sanitization, hybrid PII detection, format-preserving redaction, and server-side **Privacy Gate** enforcement system engineered for **Cadence Financial Group**.

> **Core Security Mandate:** *No document content is ever transmitted to a downstream Large Language Model (LLM) until format-aware PII detection, genuine underlying binary/pixel redaction, and independent post-redaction validation checks have passed (`GateStatus == PASS`).*

---

## 1. Executive Summary & Problem Statement

Cadence Financial Group requires an automated yet auditable security gateway capable of analyzing internal organizational documents—including leadership slide decks, third-party risk management (TPRM) training manuals, and scanned risk management policies—while preventing Personally Identifiable Information (PII) from leaking into downstream AI/LLM workflows.

Unlike simple text-stripping scripts or cosmetic visual overlays, this platform solves four critical enterprise document security challenges:
1. **Format Diversity & Hidden Channels:** Extracts and sanitizes text across **native PDFs**, **scanned/rasterized PDFs** (`0` native text characters), **Word documents (`.docx`)** including split formatting runs and **embedded UI screenshots**, **PowerPoint presentations (`.pptx`)** including tables and speaker notes, **standalone images (`.png`, `.jpg`)**, and **package metadata** (`docProps/core.xml`, PDF Info dictionaries).
2. **Context-Preserving Hybrid Detection:** Combines deterministic regular expressions and format validators with contextual Named Entity Recognition (NER), tabular column co-occurrence, and domain-specific false-positive suppression so business context (role titles, committee names, policy numbers, financial figures) remains intact.
3. **Genuine Irreversible Redaction:** Permanently removes underlying PDF character streams via `PyMuPDF` `apply_redactions()`, overwrites sensitive pixels in scanned pages and embedded `.docx`/`.pptx` media images, and rewrites OOXML `<w:r>` / `<a:r>` DOM runs without leaving fragments.
4. **Independent Post-Redaction Privacy Gate:** Re-parses the redacted output binary from scratch to verify **0 residual PII** and **$\ge 80\%$ structure retention** ($98.6\% - 99.85\%$ achieved on Case Study 2 artifacts) before unlocking safe export or optional LLM handoff.

---

## 2. Architecture & Visual Diagrams

Detailed architectural diagrams are available in [`docs/diagrams/`](file:///c:/Users/dhars/Projects/PII%20remover/docs/diagrams) and documented in [`architecture.md`](file:///c:/Users/dhars/Projects/PII%20remover/architecture.md):

- **Functional Design Diagram:** [`docs/diagrams/functional_design.png`](file:///c:/Users/dhars/Projects/PII%20remover/docs/diagrams/functional_design.png)
- **Technical System Architecture Diagram:** [`docs/diagrams/technical_architecture.png`](file:///c:/Users/dhars/Projects/PII%20remover/docs/diagrams/technical_architecture.png)
- **Data-Flow & Privacy-Gate Diagram:** [`docs/diagrams/data_flow_privacy_gate.png`](file:///c:/Users/dhars/Projects/PII%20remover/docs/diagrams/data_flow_privacy_gate.png)
- **Executive Presentation Deck (`.pptx`):** [`docs/Cadence_PII_Redaction_Architecture_and_Demo.pptx`](file:///c:/Users/dhars/Projects/PII%20remover/docs/Cadence_PII_Redaction_Architecture_and_Demo.pptx)

### Technology Stack

| Layer | Technology | Purpose |
| :--- | :--- | :--- |
| **Frontend** | React 18, TypeScript, Vite, Tailwind CSS, Lucide Icons | Consulting dashboard, batch uploader, side-by-side Original vs Redacted review studio, benchmark console, audit log viewer |
| **Backend API** | Python 3, FastAPI, Pydantic v2, Uvicorn | RESTful API, policy management, memory-isolated document buffers, zero-PII audit trail, server-side LLM firewall |
| **PDF Engine** | PyMuPDF (`fitz`) | Native text/table extraction, word/block bounding boxes, native stream redaction (`apply_redactions`), scanned page rendering |
| **Office Engines** | `python-docx`, `python-pptx`, `zipfile` | Paragraph/run DOM traversal, cross-run PII replacement, table/speaker-note scrubbing, embedded `word/media/*` & `ppt/media/*` image sanitization, metadata scrubbing |
| **OCR & Vision** | `RapidOCR` (PaddleOCR PP-OCRv4 ONNX), `Pillow` | Local offline OCR for scanned PDFs, embedded screenshots, and standalone PNG/JPG images with proportional character sub-bounding-box interpolation |
| **Testing** | `pytest`, `fastapi.testclient`, `openpyxl` | 13 automated unit & E2E test suites + 28-case Gold Benchmark evaluator |

---

## 3. Supported Formats & Case Study 2 Artifact Results

All three official Case Study 2 supporting artifacts located in `case_study_materials/extracted/Case Study 2 Supporting Material/` were inspected and verified end-to-end (with original files kept **100% immutable**):

| Supporting Artifact | Detected Format | Structural Profile | PII Findings Detected | Structure Retained | Residual PII | Privacy Gate Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **`Cadence_Financial_Group_Organizational_Pack.pptx`** | `PPTX` | 9 slides, 5 tables (Leadership Org Chart, RACI Matrices, Role Directory), package metadata | **123** (`55` Names, `34` Emails, `34` Phones, metadata author `[OC] Divisha Kilari`) | **99.85%** | `0` | **`PASS`** |
| **`Cadence_TPRM_Training.docx`** | `DOCX` | 394 paragraphs, 16 tables, **35 embedded OneTrust screenshots** (`word/media/image*.png`), metadata | **51** (`28` Table cells in Tables 4 & 14, `21` OCR findings in screenshots `image10/12/35/38`, `2` metadata authors) | **99.85%** | `0` | **`PASS`** |
| **`Cadence_Group_Risk_Management_Policy__v6.0.pdf`** | `SCANNED_PDF` | **35-page 100% rasterized scanned PDF** (`0` native text chars), risk registers, narrative incidents, signed RCSA form (Fig. 8), SecureGRC UI (Fig. 9), Access Badge (Fig. 13) | **789** (`339` Names, `188` Emp/Dir IDs, `147` Emails, `103` Phones, `4` Gov IDs, `2` PANs, `2` Accts, `2` DOBs, `2` Addresses) | **98.60%** | `0` | **`REVIEW_REQUIRED` $\rightarrow$ `PASS`** *(1 low-conf OCR span flagged for human sign-off)* |

### Gold Benchmark Evaluation (`PII_Detection_Redaction_Test_Benchmark.xlsx`)
- **Synthetic Text Cases:** **28 / 28 Exact Case Matches (100%)**
- **Gold Entity Spans:** **49 / 49 Exact Offset & Category Matches** (`TP = 49, FP = 0, FN = 0`)
- **Precision / Recall / F1 Score:** **100.0% / 100.0% / 100.0%**
- **Negative False-Positive Trap Cases (`PII-020` to `PII-024`):** **0 False Positives**
- **Multi-Format End-to-End Fixtures (Native PDF, Scanned PDF, DOCX, PPTX, PNG):** **100.0% F1, 0 Residual PII, 99.34% Average Structure Retention**

---

## 4. Quick Start & Installation (Windows Local Environment)

### Prerequisites
- **Python 3.10+** (tested on Python 3.14.2)
- **Node.js 18+** and **npm** (tested on Node v24.13.0)

### 1. Install Backend Python Dependencies
From the project root (`c:\Users\dhars\Projects\PII remover`):
```powershell
python -m pip install -r requirements.txt
```

### 2. Install Frontend Dependencies
```powershell
cd frontend
npm install
cd ..
```

### 3. Run the Application (One-Command Startup)
You can launch both the FastAPI backend (`http://localhost:8000`) and the React + Vite frontend (`http://localhost:5173`) using the provided PowerShell startup script:
```powershell
.\start_app.ps1
```
Or start each server in its own terminal:

**Terminal 1 — FastAPI Backend:**
```powershell
$env:PYTHONPATH="backend"
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

**Terminal 2 — React + Vite Frontend:**
```powershell
cd frontend
npm run dev -- --port 5173
```
Open **`http://localhost:5173`** in your browser.

---

## 5. Running the Automated Test Suite & Benchmark

Run the full `pytest` suite (13 comprehensive unit & E2E tests covering magic-byte validation, zip-bomb rejection, gold benchmark accuracy, cross-run DOCX redaction, PPTX speaker notes/table scrubbing, native PDF stream redaction, standalone image pixel redaction, Privacy Gate LLM blocking, and Case Study 2 artifact immutability):

```powershell
python -m pytest tests/test_pipeline_and_gate.py -v
```

---

## 6. Key Documentation & Deliverables Index

- [`README.md`](file:///c:/Users/dhars/Projects/PII%20remover/README.md) — Setup, usage, architecture overview, and empirical summary.
- [`methodology.md`](file:///c:/Users/dhars/Projects/PII%20remover/methodology.md) — Deep dive into format-aware extraction, OCR sub-box interpolation, hybrid detection, confidence scoring, native redaction, structure retention formula, and human-in-the-loop review.
- [`architecture.md`](file:///c:/Users/dhars/Projects/PII%20remover/architecture.md) — Detailed system components, data flows, trust boundaries, ephemeral storage hygiene, Privacy Gate state machine, and Mermaid + PNG diagrams.
- [`docs/test_results_report.md`](file:///c:/Users/dhars/Projects/PII%20remover/docs/test_results_report.md) — Complete empirical test and benchmark report across all 28 gold test cases, 5 format fixtures, and 3 Case Study 2 artifacts.
- [`docs/demo_script.md`](file:///c:/Users/dhars/Projects/PII%20remover/docs/demo_script.md) — 10–15 minute live demonstration walkthrough and speaker script.
- [`docs/Cadence_PII_Redaction_Architecture_and_Demo.pptx`](file:///c:/Users/dhars/Projects/PII%20remover/docs/Cadence_PII_Redaction_Architecture_and_Demo.pptx) — 10-slide executive and technical presentation deck.
#   P I I _ D e t e c t i o n  
 
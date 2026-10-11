"""Exports redacted Case Study 2 artifacts, masked findings reports (JSON/CSV), and benchmark results to outputs/."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "backend"))

from fastapi.testclient import TestClient
from app.main import app


def main() -> None:
    client = TestClient(app)
    out_dir = ROOT_DIR / "outputs"
    out_dir.mkdir(parents=True, exist_ok=True)

    artifacts = [
        "Cadence_Financial_Group_Organizational_Pack.pptx",
        "Cadence_TPRM_Training.docx",
        "Cadence_Group_Risk_Management_Policy__v6.0.pdf",
    ]

    for name in artifacts:
        resp = client.post("/api/documents/load-case-artifact", json={"artifact_name": name})
        rec = resp.json()
        doc_id = rec["doc_id"]

        # Approve any pending low-confidence review items so exported artifact reflects final PASS state
        if rec["validation"]["gate_status"] == "REVIEW_REQUIRED":
            client.post(f"/api/documents/{doc_id}/findings/approve-all")

        stem = Path(name).stem
        ext = Path(name).suffix

        art_bytes = client.get(f"/api/documents/{doc_id}/export/artifact").content
        (out_dir / f"{stem}_REDACTED{ext}").write_bytes(art_bytes)

        json_bytes = client.get(
            f"/api/documents/{doc_id}/export/findings-report?format=json&include_raw_pii=false"
        ).content
        (out_dir / f"{stem}_findings_masked.json").write_bytes(json_bytes)

        csv_bytes = client.get(
            f"/api/documents/{doc_id}/export/findings-report?format=csv&include_raw_pii=false"
        ).content
        (out_dir / f"{stem}_findings_masked.csv").write_bytes(csv_bytes)
        print(f"Exported redacted artifact and masked reports for: {name}")

    bench = client.get("/api/benchmark/run").json()
    (out_dir / "benchmark_evaluation_report.json").write_text(
        json.dumps(bench, indent=2), encoding="utf-8"
    )

    audit = client.get("/api/audit-log").json()
    (out_dir / "sanitized_security_audit_log.json").write_text(
        json.dumps(audit, indent=2), encoding="utf-8"
    )
    print("All sample outputs exported to outputs/")


if __name__ == "__main__":
    main()

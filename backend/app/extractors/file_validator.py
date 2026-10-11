"""Secure file-type identification, magic-byte signature validation, and archive safety checks."""
from __future__ import annotations

import io
import os
import re
import zipfile
from pathlib import Path
from typing import Tuple

import fitz  # PyMuPDF
from PIL import Image

from app.config import get_policy


SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".pptx", ".png", ".jpg", ".jpeg"}


class FileValidationError(ValueError):
    """Raised when an uploaded file fails security, signature, or policy validation."""


def sanitize_filename(filename: str) -> str:
    """Prevent path traversal and strip unsafe characters from uploaded filenames."""
    if not filename:
        raise FileValidationError("Filename cannot be empty.")
    base = os.path.basename(filename.replace("\\", "/"))
    clean = re.sub(r"[^A-Za-z0-9._\-\s()]", "_", base).strip()
    if not clean or clean in {".", ".."}:
        raise FileValidationError("Invalid or unsafe filename.")
    return clean


def validate_and_identify_file(
    filename: str, content: bytes
) -> Tuple[str, str, str]:
    """
    Validate file extension, magic bytes, container integrity, encryption status, and limits.
    Returns (sanitized_filename, detected_format, mime_type).
    """
    policy = get_policy()
    clean_name = sanitize_filename(filename)
    ext = Path(clean_name).suffix.lower()

    if ext not in SUPPORTED_EXTENSIONS:
        raise FileValidationError(
            f"Unsupported file extension '{ext}'. Supported formats: PDF, DOCX, PPTX, PNG, JPG/JPEG."
        )

    if len(content) == 0:
        raise FileValidationError("Uploaded file is empty (0 bytes).")

    max_bytes = policy.max_file_size_mb * 1024 * 1024
    if len(content) > max_bytes:
        raise FileValidationError(
            f"File size ({len(content) / (1024 * 1024):.2f} MB) exceeds policy limit of {policy.max_file_size_mb} MB."
        )

    # 1. PDF signature check
    if ext == ".pdf":
        if not content.startswith(b"%PDF-"):
            raise FileValidationError(
                "File extension is .pdf, but file header does not match %PDF- magic bytes."
            )
        try:
            doc = fitz.open(stream=content, filetype="pdf")
        except Exception as exc:
            raise FileValidationError(f"Malformed or corrupted PDF document: {exc}") from exc

        try:
            if doc.is_encrypted:
                raise FileValidationError(
                    "Encrypted or password-protected PDF files cannot be processed without decryption."
                )
            if len(doc) == 0:
                raise FileValidationError("PDF contains 0 pages.")
            if len(doc) > policy.max_page_count:
                raise FileValidationError(
                    f"PDF page count ({len(doc)}) exceeds policy limit ({policy.max_page_count})."
                )
        finally:
            doc.close()
        return clean_name, "PDF", "application/pdf"

    # 2. OOXML (DOCX / PPTX) signature and zip-bomb / path-traversal checks
    if ext in {".docx", ".pptx"}:
        if not content.startswith(b"PK\x03\x04"):
            raise FileValidationError(
                f"File extension is {ext}, but file signature is not a valid ZIP/OOXML container."
            )
        try:
            with zipfile.ZipFile(io.BytesIO(content), "r") as zf:
                names = set(zf.namelist())
                total_uncompressed = 0
                for info in zf.infolist():
                    if ".." in info.filename or info.filename.startswith(("/", "\\")):
                        raise FileValidationError(
                            "Unsafe archive member path detected inside OOXML package."
                        )
                    total_uncompressed += info.file_size
                    if total_uncompressed > max_bytes * 15:
                        raise FileValidationError(
                            "Archive uncompressed size exceeds safety threshold (potential zip bomb)."
                        )

                if "[Content_Types].xml" not in names:
                    raise FileValidationError(
                        f"Malformed {ext.upper()} package: missing [Content_Types].xml."
                    )

                if ext == ".docx":
                    if "word/document.xml" not in names:
                        raise FileValidationError(
                            "File has .docx extension but does not contain word/document.xml."
                        )
                    return clean_name, "DOCX", (
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                    )
                else:
                    if "ppt/presentation.xml" not in names:
                        raise FileValidationError(
                            "File has .pptx extension but does not contain ppt/presentation.xml."
                        )
                    slide_count = sum(
                        1
                        for n in names
                        if n.startswith("ppt/slides/slide") and n.endswith(".xml")
                    )
                    if slide_count > policy.max_page_count:
                        raise FileValidationError(
                            f"Presentation slide count ({slide_count}) exceeds limit ({policy.max_page_count})."
                        )
                    return clean_name, "PPTX", (
                        "application/vnd.openxmlformats-officedocument.presentationml.presentation"
                    )
        except FileValidationError:
            raise
        except Exception as exc:
            raise FileValidationError(f"Corrupted or unreadable {ext.upper()} archive: {exc}") from exc

    # 3. Standalone Images (PNG / JPG / JPEG)
    if ext == ".png":
        if not content.startswith(b"\x89PNG\r\n\x1a\n"):
            raise FileValidationError(
                "File extension is .png, but file header does not match PNG magic signature."
            )
        detected_fmt, mime = "PNG", "image/png"
    else:
        if not content.startswith(b"\xff\xd8\xff"):
            raise FileValidationError(
                f"File extension is {ext}, but file header does not match JPEG magic signature."
            )
        detected_fmt, mime = "JPG", "image/jpeg"

    try:
        img = Image.open(io.BytesIO(content))
        img.verify()
        if img.width * img.height > 64_000_000:
            raise FileValidationError("Image dimensions exceed maximum safe pixel limit.")
    except FileValidationError:
        raise
    except Exception as exc:
        raise FileValidationError(f"Malformed or corrupted image file: {exc}") from exc

    return clean_name, detected_fmt, mime

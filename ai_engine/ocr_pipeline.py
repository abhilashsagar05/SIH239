"""
OCR Pipeline — Core document text extraction engine.

Handles:
  - Image preprocessing (deskew, denoise, binarize, upscale)
  - Tesseract OCR with configurable PSM modes
  - Structured field extraction per document type
  - Integration with downstream matcher and fraud detector
  - DB result persistence
"""
from __future__ import annotations

import io
import logging
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

import boto3
import cv2
import numpy as np
import pytesseract
from PIL import Image

# sqlalchemy.orm.Session only needed for type hints — avoid hard runtime import
# when ai_engine is used standalone (e.g. test_runner.py)
if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger("mota.ocr")


def _get_s3_config() -> dict[str, str | None]:
    """
    Read S3 credentials from environment variables.
    This keeps ai_engine fully decoupled from the backend `app` package.
    When running inside FastAPI/Celery, these are set via .env.
    When running the test_runner CLI, export them manually.
    """
    return {
        "endpoint_url": os.environ.get("S3_ENDPOINT_URL"),
        "aws_access_key_id": os.environ.get("AWS_ACCESS_KEY_ID"),
        "aws_secret_access_key": os.environ.get("AWS_SECRET_ACCESS_KEY"),
        "bucket": os.environ.get("S3_BUCKET", "mota-documents"),
    }

# ── Tesseract Configuration ───────────────────────────────────────────────────
# PSM 6 = Assume uniform block of text (best for certificates)
# PSM 11 = Sparse text (good for Aadhaar cards with mixed layout)
TESS_CONFIG_BLOCK = "--oem 3 --psm 6 -l eng+hin"
TESS_CONFIG_SPARSE = "--oem 3 --psm 11 -l eng+hin"
TESS_CONFIG_SINGLE_LINE = "--oem 3 --psm 7 -l eng"


# ── Document Type → Extraction Config ────────────────────────────────────────
EXTRACTION_CONFIGS: dict[str, dict] = {
    "AADHAAR_CARD": {
        "psm_config": TESS_CONFIG_SPARSE,
        "fields": ["name", "dob", "aadhaar_number", "address", "gender"],
        "required_patterns": {
            "aadhaar_number": r"\b\d{4}\s?\d{4}\s?\d{4}\b",
            "dob": r"\b(\d{2}/\d{2}/\d{4}|\d{2}-\d{2}-\d{4})\b",
            "gender": r"\b(MALE|FEMALE|Male|Female|पुरुष|महिला)\b",
            "name": r"(?:^|\n)([A-Z][a-z]+(?:\s[A-Z][a-z]+){1,3})",
        },
    },
    "INCOME_CERTIFICATE": {
        "psm_config": TESS_CONFIG_BLOCK,
        "fields": ["applicant_name", "income_amount", "issue_date", "authority"],
        "required_patterns": {
            "income_amount": r"(?:Rs\.?|INR|₹)\s?[\d,]+(?:\.\d{2})?",
            "issue_date": r"\b(\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4})\b",
            "financial_year": r"\b\d{4}\s*-\s*\d{2,4}\b",
        },
    },
    "CASTE_CERTIFICATE": {
        "psm_config": TESS_CONFIG_BLOCK,
        "fields": ["applicant_name", "caste_category", "issue_date", "authority"],
        "required_patterns": {
            "caste_category": r"\b(Scheduled Tribe|ST|Scheduled Caste|SC|OBC|General)\b",
            "issue_date": r"\b(\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4})\b",
        },
    },
    "MARKSHEET_10": {
        "psm_config": TESS_CONFIG_BLOCK,
        "fields": ["student_name", "marks_obtained", "total_marks", "percentage", "year", "board"],
        "required_patterns": {
            "percentage": r"(\d{2,3}(?:\.\d{1,2})?)\s*%",
            "year": r"\b(20\d{2})\b",
        },
    },
    "MARKSHEET_12": {
        "psm_config": TESS_CONFIG_BLOCK,
        "fields": ["student_name", "marks_obtained", "total_marks", "percentage", "year", "board"],
        "required_patterns": {
            "percentage": r"(\d{2,3}(?:\.\d{1,2})?)\s*%",
            "year": r"\b(20\d{2})\b",
        },
    },
    "MARKSHEET_UG": {
        "psm_config": TESS_CONFIG_BLOCK,
        "fields": ["student_name", "cgpa", "percentage", "year", "university", "degree"],
        "required_patterns": {
            "percentage": r"(\d{2,3}(?:\.\d{1,2})?)\s*%",
            "cgpa": r"\b([0-9]\.\d{1,2})\b",
        },
    },
    "MARKSHEET_PG": {
        "psm_config": TESS_CONFIG_BLOCK,
        "fields": ["student_name", "cgpa", "percentage", "year", "university", "degree"],
        "required_patterns": {
            "percentage": r"(\d{2,3}(?:\.\d{1,2})?)\s*%",
            "cgpa": r"\b([0-9]\.\d{1,2})\b",
        },
    },
    "ADMISSION_LETTER": {
        "psm_config": TESS_CONFIG_BLOCK,
        "fields": ["student_name", "course_name", "institution_name", "admission_year"],
        "required_patterns": {
            "admission_year": r"\b(20\d{2}[-/]\d{2,4})\b",
        },
    },
    "BANK_PASSBOOK": {
        "psm_config": TESS_CONFIG_SPARSE,
        "fields": ["account_holder_name", "account_number", "ifsc_code", "bank_name"],
        "required_patterns": {
            "account_number": r"\b\d{9,18}\b",
            "ifsc_code": r"\b[A-Z]{4}0[A-Z0-9]{6}\b",
        },
    },
    "PASSPORT": {
        "psm_config": TESS_CONFIG_SPARSE,
        "fields": ["surname", "given_names", "dob", "passport_number", "expiry_date", "nationality"],
        "required_patterns": {
            "passport_number": r"\b[A-Z]\d{7}\b",
            "dob": r"\b(\d{2}\s[A-Z]{3}\s\d{4})\b",
        },
    },
}
DEFAULT_CONFIG = {
    "psm_config": TESS_CONFIG_BLOCK,
    "fields": [],
    "required_patterns": {},
}


# ── Image Preprocessing ───────────────────────────────────────────────────────

def preprocess_image(image_bytes: bytes) -> tuple[np.ndarray, dict[str, Any]]:
    """
    Full preprocessing pipeline for OCR quality enhancement.

    Steps:
      1. Decode image
      2. Convert to grayscale
      3. Upscale if small
      4. Deskew
      5. Adaptive thresholding (binarization)
      6. Noise reduction

    Returns:
      processed_image: numpy array ready for Tesseract
      meta: dict with preprocessing metadata (original_size, blur_score, etc.)
    """
    # Decode
    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Failed to decode image. Possibly corrupt or unsupported format.")

    original_h, original_w = img.shape[:2]
    meta: dict[str, Any] = {
        "original_size": (original_w, original_h),
        "preprocessing_steps": [],
    }

    # Grayscale
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    meta["preprocessing_steps"].append("grayscale")

    # Blur score (Laplacian variance — lower = blurrier)
    blur_score = cv2.Laplacian(gray, cv2.CV_64F).var()
    meta["blur_score"] = round(float(blur_score), 2)
    meta["is_blurry"] = blur_score < 100  # threshold

    # Upscale if resolution is too low
    if original_w < 800 or original_h < 600:
        scale = max(800 / original_w, 600 / original_h)
        gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        meta["preprocessing_steps"].append(f"upscaled_{scale:.1f}x")

    # Deskew
    gray, skew_angle = _deskew(gray)
    meta["skew_angle"] = round(skew_angle, 2)
    if abs(skew_angle) > 0.5:
        meta["preprocessing_steps"].append(f"deskewed_{skew_angle:.1f}deg")

    # Adaptive threshold (handles uneven lighting)
    binary = cv2.adaptiveThreshold(
        gray, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY, 21, 10
    )
    meta["preprocessing_steps"].append("adaptive_threshold")

    # Morphological noise removal
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 1))
    clean = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
    meta["preprocessing_steps"].append("morphological_denoise")

    return clean, meta


def _deskew(gray: np.ndarray) -> tuple[np.ndarray, float]:
    """Detect and correct document skew using Hough line transform."""
    edges = cv2.Canny(gray, 50, 150, apertureSize=3)
    lines = cv2.HoughLines(edges, 1, np.pi / 180, threshold=100)

    if lines is None or len(lines) == 0:
        return gray, 0.0

    angles = []
    for rho, theta in lines[:, 0]:
        angle = np.degrees(theta) - 90
        if -45 <= angle <= 45:
            angles.append(angle)

    if not angles:
        return gray, 0.0

    median_angle = float(np.median(angles))
    if abs(median_angle) < 0.5:
        return gray, median_angle

    h, w = gray.shape
    center = (w // 2, h // 2)
    M = cv2.getRotationMatrix2D(center, median_angle, 1.0)
    rotated = cv2.warpAffine(gray, M, (w, h), flags=cv2.INTER_CUBIC,
                             borderMode=cv2.BORDER_REPLICATE)
    return rotated, median_angle


# ── OCR Extraction ────────────────────────────────────────────────────────────

def extract_text(processed_img: np.ndarray, config: str) -> tuple[str, float]:
    """
    Run Tesseract OCR and return (raw_text, ocr_confidence).
    confidence = mean word confidence from Tesseract's detailed output.
    """
    # Get detailed data with confidence scores
    data = pytesseract.image_to_data(
        processed_img,
        config=config,
        output_type=pytesseract.Output.DICT,
    )

    raw_text = pytesseract.image_to_string(processed_img, config=config)

    # Compute mean confidence (ignoring -1 entries)
    confidences = [int(c) for c in data["conf"] if int(c) > 0]
    ocr_confidence = float(np.mean(confidences)) if confidences else 0.0

    return raw_text.strip(), ocr_confidence


def extract_structured_fields(raw_text: str, doc_type: str) -> dict[str, Any]:
    """
    Apply document-type-specific regex patterns to extract key fields from OCR text.

    Returns a dict of {field_name: extracted_value}.
    """
    config = EXTRACTION_CONFIGS.get(doc_type, DEFAULT_CONFIG)
    patterns = config.get("required_patterns", {})
    extracted: dict[str, Any] = {}

    for field, pattern in patterns.items():
        match = re.search(pattern, raw_text, re.IGNORECASE | re.MULTILINE)
        if match:
            value = match.group(1) if match.lastindex else match.group(0)
            extracted[field] = value.strip()

    # ── Document-specific post-processing ────────────────────────────────────

    if doc_type == "INCOME_CERTIFICATE" and "income_amount" in extracted:
        # Normalize income to integer
        raw_amount = re.sub(r"[Rs\.INR₹,\s]", "", extracted["income_amount"])
        try:
            extracted["income_amount_normalized"] = int(float(raw_amount))
        except ValueError:
            pass

    if doc_type in ("MARKSHEET_10", "MARKSHEET_12", "MARKSHEET_UG", "MARKSHEET_PG"):
        if "percentage" in extracted:
            try:
                pct = float(re.sub(r"[%\s]", "", extracted["percentage"]))
                extracted["percentage_normalized"] = round(pct, 2)
            except ValueError:
                pass

    if doc_type == "AADHAAR_CARD" and "aadhaar_number" in extracted:
        # Normalize: remove spaces
        extracted["aadhaar_number_clean"] = re.sub(r"\s", "", extracted["aadhaar_number"])

    if doc_type in ("INCOME_CERTIFICATE", "CASTE_CERTIFICATE") and "issue_date" in extracted:
        # Parse and check staleness
        date_str = extracted["issue_date"]
        try:
            parsed_date = _parse_date(date_str)
            extracted["issue_date_parsed"] = parsed_date.isoformat() if parsed_date else None
            if parsed_date:
                from datetime import date
                age_days = (date.today() - parsed_date).days
                extracted["document_age_days"] = age_days
                extracted["is_stale"] = age_days > 180  # older than 6 months
        except Exception:
            pass

    return extracted


def _parse_date(date_str: str):
    """Attempt to parse various date formats found in Indian certificates."""
    from datetime import date as date_cls
    formats = [
        "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y",
        "%d/%m/%y", "%d-%m-%y",
        "%B %d, %Y", "%d %B %Y",
        "%d %b %Y",
    ]
    date_str = date_str.strip()
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue
    return None


# ── S3 Document Fetch ──────────────────────────────────────────────────────────

def fetch_document_bytes(storage_key: str, bucket: str) -> bytes:
    """Download document bytes from S3-compatible storage."""
    cfg = _get_s3_config()
    kwargs: dict = {}
    if cfg["endpoint_url"]:
        kwargs["endpoint_url"] = cfg["endpoint_url"]
    if cfg["aws_access_key_id"]:
        kwargs["aws_access_key_id"] = cfg["aws_access_key_id"]
        kwargs["aws_secret_access_key"] = cfg["aws_secret_access_key"]

    s3 = boto3.client("s3", **kwargs)
    response = s3.get_object(Bucket=bucket, Key=storage_key)
    return response["Body"].read()


def _pdf_to_image_bytes(pdf_bytes: bytes) -> bytes:
    """Convert first page of PDF to PNG bytes for OCR processing."""
    try:
        import pymupdf  # PyMuPDF >= 1.24 — replaces deprecated 'import fitz'
        doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
        page = doc.load_page(0)
        mat = pymupdf.Matrix(2.0, 2.0)  # 2x upscale for better OCR resolution
        pix = page.get_pixmap(matrix=mat)
        return pix.tobytes("png")
    except ImportError:
        # Fallback: return bytes as-is (Pillow will attempt to open directly)
        return pdf_bytes


# ── Main Pipeline Entry Point ─────────────────────────────────────────────────

def run_ocr_pipeline(document_id: str, db: Session) -> dict[str, Any]:
    """
    Full OCR pipeline for a single document.

    Flow:
      1. Fetch document record + bytes from S3
      2. Preprocess image
      3. Run Tesseract OCR
      4. Extract structured fields
      5. Detect fraud signals
      6. Match against application form data
      7. Compute final confidence score
      8. Persist results to DB
      9. Check if all application documents processed → update application

    Returns:
      result dict with all scores and flags
    """
    from app.models import Document, Application, DocumentStatus, ApplicationStatus, Notification
    from ai_engine.fraud_detector import detect_fraud
    from ai_engine.document_matcher import match_document_to_form
    from ai_engine.confidence_scorer import compute_confidence_score

    t_start = time.monotonic()
    logger.info(f"[OCR] Starting pipeline for document {document_id}")

    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        return {"error": f"Document {document_id} not found in DB"}

    app = db.query(Application).filter(Application.id == doc.application_id).first()
    if not app:
        return {"error": "Parent application not found"}

    result: dict[str, Any] = {
        "document_id": document_id,
        "document_type": doc.document_type,
    }

    try:
        # ── 1. Fetch file ──────────────────────────────────────────────────────
        raw_bytes = fetch_document_bytes(doc.storage_key, doc.storage_bucket)

        # Convert PDF to image if needed
        if doc.mime_type == "application/pdf":
            raw_bytes = _pdf_to_image_bytes(raw_bytes)

        # ── 2. Preprocess ──────────────────────────────────────────────────────
        processed_img, pre_meta = preprocess_image(raw_bytes)

        # ── 3. OCR ────────────────────────────────────────────────────────────
        doc_config = EXTRACTION_CONFIGS.get(doc.document_type, DEFAULT_CONFIG)
        raw_text, ocr_confidence = extract_text(processed_img, doc_config["psm_config"])
        logger.info(f"[OCR] Extracted {len(raw_text)} chars, OCR confidence: {ocr_confidence:.1f}%")

        # ── 4. Field Extraction ────────────────────────────────────────────────
        extracted_fields = extract_structured_fields(raw_text, doc.document_type)
        logger.info(f"[OCR] Extracted fields: {list(extracted_fields.keys())}")

        # ── 5. Fraud Detection ─────────────────────────────────────────────────
        fraud_result = detect_fraud(
            image_bytes=raw_bytes,
            processed_img=processed_img,
            pre_meta=pre_meta,
            raw_text=raw_text,
            doc_type=doc.document_type,
        )

        # ── 6. Data Matching ───────────────────────────────────────────────────
        form_data = _build_form_data_snapshot(app)
        match_result = match_document_to_form(
            extracted_fields=extracted_fields,
            form_data=form_data,
            doc_type=doc.document_type,
        )

        # ── 7. Confidence Score ────────────────────────────────────────────────
        confidence = compute_confidence_score(
            ocr_confidence=ocr_confidence,
            extracted_fields=extracted_fields,
            match_result=match_result,
            fraud_result=fraud_result,
            doc_type=doc.document_type,
        )

        # ── 8. Build AI Flags ──────────────────────────────────────────────────
        ai_flags = _build_ai_flags(fraud_result, match_result, extracted_fields, doc.document_type)

        # Determine final document status
        if fraud_result["is_tampered"] or fraud_result["is_blurry"]:
            final_status = DocumentStatus.FLAGGED
        elif confidence["overall"] < 40:
            final_status = DocumentStatus.FLAGGED
        elif match_result["critical_mismatches"]:
            final_status = DocumentStatus.FLAGGED
        else:
            final_status = DocumentStatus.VERIFIED

        # ── 9. Persist to DB ───────────────────────────────────────────────────
        doc.extracted_text = raw_text
        doc.extracted_fields = extracted_fields
        doc.confidence_score = round(confidence["overall"], 2)
        doc.match_score = round(match_result["overall_match_score"], 2)
        doc.ocr_engine = "tesseract_v5"
        doc.ocr_processed_at = datetime.now(timezone.utc)
        doc.ai_flags = ai_flags
        doc.is_blurry = pre_meta["is_blurry"]
        doc.is_tampered = fraud_result["is_tampered"]
        doc.status = final_status

        db.flush()

        # ── 10. Update Application AI summary ─────────────────────────────────
        _update_application_ai_summary(app, db)

        t_elapsed = round((time.monotonic() - t_start) * 1000, 1)
        logger.info(
            f"[OCR] ✅ Document {document_id} done in {t_elapsed}ms | "
            f"Confidence: {confidence['overall']:.1f}% | Status: {final_status.value}"
        )

        result.update({
            "status": final_status.value,
            "ocr_confidence": round(ocr_confidence, 2),
            "confidence_score": round(confidence["overall"], 2),
            "match_score": round(match_result["overall_match_score"], 2),
            "is_blurry": pre_meta["is_blurry"],
            "is_tampered": fraud_result["is_tampered"],
            "flags_count": len(ai_flags),
            "elapsed_ms": t_elapsed,
        })
        return result

    except Exception as e:
        logger.exception(f"[OCR] ❌ Failed for document {document_id}: {e}")
        doc.status = DocumentStatus.FLAGGED
        doc.ai_flags = [{"type": "PROCESSING_ERROR", "message": str(e), "severity": "HIGH"}]
        db.flush()
        return {"error": str(e), "document_id": document_id}


def _build_form_data_snapshot(app) -> dict[str, Any]:
    """Build a normalized dict of the applicant's typed form data for matching."""
    return {
        "name": app.applicant_name or "",
        "dob": app.applicant_dob.strftime("%d/%m/%Y") if app.applicant_dob else "",
        "gender": str(app.applicant_gender).replace("Gender.", "") if app.applicant_gender else "",
        "income": float(app.annual_family_income) if app.annual_family_income else 0.0,
        "percentage_10": float(app.percentage_10) if app.percentage_10 else None,
        "percentage_12": float(app.percentage_12) if app.percentage_12 else None,
        "percentage_ug": float(app.percentage_ug) if app.percentage_ug else None,
        "percentage_pg": float(app.percentage_pg) if app.percentage_pg else None,
        "aadhaar_last4": app.aadhaar_last4 or "",
        "bank_ifsc": app.bank_ifsc or "",
        "institution_name": app.institution_name or "",
        "course_name": app.course_name or "",
    }


def _build_ai_flags(
    fraud_result: dict,
    match_result: dict,
    extracted_fields: dict,
    doc_type: str,
) -> list[dict[str, Any]]:
    """Compile a list of structured flag objects for the AI flags column."""
    flags = []

    if fraud_result["is_blurry"]:
        flags.append({
            "type": "BLURRY_IMAGE",
            "severity": "HIGH",
            "message": f"Document image is too blurry (score: {fraud_result['blur_score']:.1f}). Please upload a clearer scan.",
            "action_required": "REUPLOAD",
        })

    if fraud_result["is_tampered"]:
        for signal in fraud_result.get("tamper_signals", []):
            flags.append({
                "type": "TAMPER_DETECTED",
                "severity": "CRITICAL",
                "message": signal,
                "action_required": "MANUAL_REVIEW",
            })

    for mismatch in match_result.get("critical_mismatches", []):
        flags.append({
            "type": "DATA_MISMATCH",
            "severity": "HIGH",
            "field": mismatch["field"],
            "message": mismatch["message"],
            "form_value": mismatch.get("form_value"),
            "extracted_value": mismatch.get("extracted_value"),
            "action_required": "REUPLOAD",
        })

    for warning in match_result.get("warnings", []):
        flags.append({
            "type": "DATA_WARNING",
            "severity": "MEDIUM",
            "message": warning,
            "action_required": "REVIEW",
        })

    # Staleness check (income/caste certs > 6 months)
    if doc_type in ("INCOME_CERTIFICATE", "CASTE_CERTIFICATE"):
        if extracted_fields.get("is_stale"):
            age_days = extracted_fields.get("document_age_days", 0)
            flags.append({
                "type": "STALE_DOCUMENT",
                "severity": "HIGH",
                "message": f"Document is {age_days} days old (issued {age_days} days ago). Income/Caste certificates must be less than 6 months old.",
                "action_required": "REUPLOAD",
            })

    return flags


def _update_application_ai_summary(app, db) -> None:
    """
    After all documents are processed, compute the overall application AI score
    and decide whether it should move to MANUAL_SCRUTINY or stay DEFICIENT.
    """
    from app.models import Document, DocumentStatus, ApplicationStatus, Notification

    all_docs = db.query(Document).filter(Document.application_id == app.id).all()
    processed_docs = [d for d in all_docs if d.status not in (DocumentStatus.PENDING, DocumentStatus.PROCESSING)]

    if len(processed_docs) < len(all_docs):
        return  # Still processing

    # Compute weighted average confidence across all documents
    scores = [float(d.confidence_score) for d in processed_docs if d.confidence_score is not None]
    overall_score = round(float(np.mean(scores)), 2) if scores else 0.0

    # Collect all flags
    all_flags = []
    for d in processed_docs:
        if d.ai_flags:
            for flag in d.ai_flags:
                flag["document_id"] = str(d.id)
                flag["document_type"] = d.document_type
                all_flags.append(flag)

    critical_flags = [f for f in all_flags if f.get("severity") == "CRITICAL"]
    high_flags = [f for f in all_flags if f.get("severity") == "HIGH"]

    app.overall_ai_score = overall_score
    app.ai_flags = all_flags
    app.ai_processing_done = True
    app.ai_reviewed_at = datetime.now(timezone.utc)

    # Decide next status
    scheme_threshold = 75.0
    if app.scheme:
        try:
            scheme_threshold = float(app.scheme.ai_confidence_threshold or 75.0)
        except Exception:
            pass

    has_reupload_flags = any(f.get("action_required") == "REUPLOAD" for f in all_flags)

    if critical_flags or (len(high_flags) >= 3) or has_reupload_flags:
        # Move to DEFICIENT — notify applicant with precise deficiency list
        app.status = ApplicationStatus.DEFICIENT
        deficiency_notes = [
            {"document_id": f.get("document_id"), "document_type": f.get("document_type"),
             "message": f["message"], "action": f.get("action_required", "REVIEW")}
            for f in all_flags if f.get("action_required") in ("REUPLOAD", "MANUAL_REVIEW")
        ]
        app.deficiency_notes = deficiency_notes

        db.add(Notification(
            user_id=app.applicant_id,
            application_id=app.id,
            channel="IN_APP",
            subject="Action Required: Document Issues Found",
            body=(
                f"Our AI has detected issues with {len(deficiency_notes)} document(s) "
                f"in your application {app.application_number}. "
                f"Please visit the Deficiency section and re-upload the flagged documents."
            ),
        ))
    elif overall_score >= scheme_threshold:
        app.status = ApplicationStatus.MANUAL_SCRUTINY
        db.add(Notification(
            user_id=app.applicant_id,
            application_id=app.id,
            channel="IN_APP",
            subject="Application Under Review",
            body=(
                f"Your application {app.application_number} has passed AI verification "
                f"(Score: {overall_score:.1f}%) and is now under manual scrutiny by our reviewers."
            ),
        ))
    else:
        # Low confidence — send to DEFICIENT for manual check
        app.status = ApplicationStatus.DEFICIENT
        app.deficiency_notes = [{
            "message": f"AI confidence score ({overall_score:.1f}%) is below the required threshold ({scheme_threshold}%). Additional verification needed.",
            "action": "MANUAL_REVIEW",
        }]

    db.flush()
    logger.info(
        f"[OCR] Application {app.id} → status={app.status.value}, "
        f"ai_score={overall_score:.1f}%, flags={len(all_flags)}"
    )

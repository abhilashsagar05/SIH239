"""
Confidence Scorer — Aggregates all signals into a single document confidence score.

Score breakdown (0-100):
  Component               Weight    Description
  ─────────────────────── ───────── ─────────────────────────────────────────
  OCR Quality             30%       Tesseract word-level confidence mean
  Field Match Score       40%       Data matched vs. application form
  Fraud/Integrity         20%       Inverse of fraud penalty
  Field Coverage          10%       Fraction of expected fields extracted

Final score mapping:
  ≥ 85  → Very High Confidence (auto-approve eligible)
  70-84 → High Confidence (route to manual review)
  50-69 → Medium Confidence (flag for closer review)
  30-49 → Low Confidence (likely deficient → re-upload)
  < 30  → Very Low (possible fraud or corrupt document)
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("mota.scorer")

# Component weights (must sum to 1.0)
WEIGHTS = {
    "ocr_quality": 0.30,
    "field_match": 0.40,
    "integrity": 0.20,
    "field_coverage": 0.10,
}

# Expected fields per document type (for coverage scoring)
EXPECTED_FIELDS: dict[str, list[str]] = {
    "AADHAAR_CARD":         ["name", "dob", "aadhaar_number", "gender"],
    "INCOME_CERTIFICATE":   ["income_amount", "issue_date", "name"],
    "CASTE_CERTIFICATE":    ["caste_category", "issue_date", "name"],
    "MARKSHEET_10":         ["percentage", "year", "name"],
    "MARKSHEET_12":         ["percentage", "year", "name"],
    "MARKSHEET_UG":         ["percentage", "year", "name"],
    "MARKSHEET_PG":         ["percentage", "year", "name"],
    "ADMISSION_LETTER":     ["student_name", "course_name", "admission_year"],
    "BANK_PASSBOOK":        ["account_number", "ifsc_code", "name"],
    "PASSPORT":             ["passport_number", "dob", "name", "expiry_date"],
    "DOMICILE_CERTIFICATE": ["name", "issue_date"],
    "PHOTOGRAPH":           [],  # No OCR fields required
    "OTHER":                [],
}


def compute_confidence_score(
    ocr_confidence: float,
    extracted_fields: dict[str, Any],
    match_result: dict[str, Any],
    fraud_result: dict[str, Any],
    doc_type: str,
) -> dict[str, Any]:
    """
    Compute the final confidence score for a processed document.

    Args:
        ocr_confidence:   Raw Tesseract confidence (0-100)
        extracted_fields: Fields extracted by OCR pipeline
        match_result:     Output from document_matcher.match_document_to_form()
        fraud_result:     Output from fraud_detector.detect_fraud()
        doc_type:         Document type string

    Returns:
        {
            "overall": float,          # Final 0-100 score
            "grade": str,              # "VERY_HIGH" | "HIGH" | "MEDIUM" | "LOW" | "VERY_LOW"
            "components": dict,        # Breakdown of each component
            "penalty_reasons": list,   # Human-readable reasons for score reduction
            "recommendation": str,     # "AUTO_APPROVE" | "MANUAL_REVIEW" | "FLAG" | "REJECT"
        }
    """
    components: dict[str, float] = {}
    penalty_reasons: list[str] = []

    # ── Component 1: OCR Quality (0-100) ──────────────────────────────────────
    ocr_score = max(0.0, min(100.0, float(ocr_confidence)))
    components["ocr_quality"] = round(ocr_score, 2)
    if ocr_score < 60:
        penalty_reasons.append(
            f"Poor OCR quality ({ocr_score:.0f}%). The document may be blurry, skewed, or low resolution."
        )

    # ── Component 2: Field Match Score (0-100) ────────────────────────────────
    match_score = float(match_result.get("overall_match_score", 0.0))
    components["field_match"] = round(match_score, 2)
    if match_result.get("critical_mismatches"):
        n_mis = len(match_result["critical_mismatches"])
        penalty_reasons.append(
            f"{n_mis} critical field mismatch(es) detected between document and application form."
        )
    if match_score < 50:
        penalty_reasons.append(
            f"Low field match score ({match_score:.0f}%). Several values in the document "
            "do not match what was entered in the form."
        )

    # ── Component 3: Fraud/Integrity Score (0-100) ────────────────────────────
    integrity_score = float(fraud_result.get("integrity_score", 100.0))
    components["integrity"] = round(integrity_score, 2)
    if fraud_result.get("is_tampered"):
        penalty_reasons.append("Document integrity check failed — possible tampering detected.")
    if fraud_result.get("is_blurry"):
        penalty_reasons.append("Document is too blurry to verify reliably.")

    # ── Component 4: Field Coverage (0-100) ───────────────────────────────────
    expected = EXPECTED_FIELDS.get(doc_type, [])
    if expected:
        extracted_keys = set(extracted_fields.keys())
        covered = sum(1 for f in expected if any(f in k for k in extracted_keys))
        coverage_pct = (covered / len(expected)) * 100
    else:
        coverage_pct = 100.0  # No expected fields (e.g., PHOTOGRAPH)

    components["field_coverage"] = round(coverage_pct, 2)
    if coverage_pct < 60 and expected:
        missing_fields = [f for f in expected if not any(f in k for k in extracted_fields.keys())]
        penalty_reasons.append(
            f"Only {coverage_pct:.0f}% of expected fields extracted. "
            f"Missing: {', '.join(missing_fields[:3])}."
        )

    # ── Stale Document Penalty ────────────────────────────────────────────────
    stale_penalty = 0.0
    if extracted_fields.get("is_stale") and doc_type in ("INCOME_CERTIFICATE", "CASTE_CERTIFICATE"):
        age_days = extracted_fields.get("document_age_days", 181)
        stale_penalty = min(25.0, (age_days - 180) / 30 * 5)  # 5 pts per extra month
        penalty_reasons.append(
            f"Document is {age_days} days old. "
            "Income and Caste certificates must be issued within the last 6 months."
        )

    # ── Weighted Aggregation ──────────────────────────────────────────────────
    raw_score = (
        ocr_score    * WEIGHTS["ocr_quality"] +
        match_score  * WEIGHTS["field_match"] +
        integrity_score * WEIGHTS["integrity"] +
        coverage_pct * WEIGHTS["field_coverage"]
    )

    # Apply stale document penalty
    final_score = max(0.0, raw_score - stale_penalty)

    # Critical flags cause hard cap
    if fraud_result.get("is_tampered"):
        final_score = min(final_score, 30.0)
    if match_result.get("critical_mismatches") and len(match_result["critical_mismatches"]) >= 2:
        final_score = min(final_score, 45.0)

    final_score = round(final_score, 2)

    # ── Grade Assignment ──────────────────────────────────────────────────────
    grade, recommendation = _assign_grade(final_score, fraud_result, match_result)

    logger.info(
        f"[SCORER] {doc_type}: overall={final_score:.1f}% | grade={grade} | "
        f"components={components} | penalties={len(penalty_reasons)}"
    )

    return {
        "overall": final_score,
        "grade": grade,
        "recommendation": recommendation,
        "components": components,
        "weights_used": WEIGHTS,
        "stale_penalty": round(stale_penalty, 2),
        "penalty_reasons": penalty_reasons,
    }


def _assign_grade(
    score: float,
    fraud_result: dict,
    match_result: dict,
) -> tuple[str, str]:
    """Map numeric score to qualitative grade and action recommendation."""

    # Hard overrides
    if fraud_result.get("is_tampered"):
        return "VERY_LOW", "REJECT"

    n_critical = len(match_result.get("critical_mismatches", []))
    if n_critical >= 2:
        return "LOW", "FLAG"

    # Score-based grading
    if score >= 85:
        return "VERY_HIGH", "AUTO_APPROVE"
    elif score >= 70:
        return "HIGH", "MANUAL_REVIEW"
    elif score >= 50:
        return "MEDIUM", "MANUAL_REVIEW"
    elif score >= 30:
        return "LOW", "FLAG"
    else:
        return "VERY_LOW", "FLAG"


def compute_application_overall_score(document_scores: list[dict]) -> dict[str, Any]:
    """
    Aggregate individual document confidence scores into a single
    application-level AI confidence score.

    Documents with higher individual weight (e.g., Aadhaar = identity anchor)
    contribute more to the final score.
    """
    DOC_IMPORTANCE: dict[str, float] = {
        "AADHAAR_CARD": 1.5,
        "INCOME_CERTIFICATE": 1.3,
        "CASTE_CERTIFICATE": 1.3,
        "MARKSHEET_10": 1.0,
        "MARKSHEET_12": 1.0,
        "MARKSHEET_UG": 1.1,
        "MARKSHEET_PG": 1.1,
        "ADMISSION_LETTER": 0.9,
        "BANK_PASSBOOK": 0.8,
        "PASSPORT": 1.0,
        "DOMICILE_CERTIFICATE": 0.7,
        "PHOTOGRAPH": 0.5,
        "OTHER": 0.5,
    }

    weighted_sum = 0.0
    total_weight = 0.0
    doc_count = 0
    all_critical_mismatches = []
    all_flags = []

    for doc in document_scores:
        doc_type = doc.get("document_type", "OTHER")
        score = doc.get("confidence_score", 0.0)
        importance = DOC_IMPORTANCE.get(doc_type, 1.0)

        weighted_sum += score * importance
        total_weight += importance
        doc_count += 1

        # Aggregate flags
        all_critical_mismatches.extend(doc.get("critical_mismatches", []))
        all_flags.extend(doc.get("ai_flags", []))

    if total_weight == 0 or doc_count == 0:
        return {"overall_score": 0.0, "grade": "VERY_LOW", "recommendation": "FLAG"}

    overall = round(weighted_sum / total_weight, 2)
    grade, recommendation = _assign_grade(
        overall,
        {"is_tampered": any(f.get("type") == "TAMPER_DETECTED" for f in all_flags)},
        {"critical_mismatches": all_critical_mismatches},
    )

    return {
        "overall_score": overall,
        "grade": grade,
        "recommendation": recommendation,
        "documents_processed": doc_count,
        "total_critical_mismatches": len(all_critical_mismatches),
        "total_flags": len(all_flags),
    }

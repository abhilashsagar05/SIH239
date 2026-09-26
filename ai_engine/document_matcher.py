"""
Document-to-Form Data Matcher — NLP-based semantic field matching.

Compares OCR-extracted fields from documents against the data the applicant
typed into the application form, producing per-field match scores and surfacing
critical mismatches for human review.

Uses:
  - RapidFuzz for fuzzy string matching (name comparison)
  - Exact / near-exact comparisons for structured fields (DOB, IFSC, amounts)
  - Semantic tolerance for known OCR transcription errors
"""
from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any

from rapidfuzz import fuzz, process

logger = logging.getLogger("mota.matcher")


# ── Match thresholds ──────────────────────────────────────────────────────────
NAME_MATCH_THRESHOLD = 75       # Fuzzy token sort ratio for names
AMOUNT_TOLERANCE_PCT = 0.05     # 5% tolerance for income amounts
PERCENTAGE_TOLERANCE = 2.0      # ±2 percentage points for marks


# ── Field match results ───────────────────────────────────────────────────────

def _name_match(ocr_name: str, form_name: str) -> dict[str, Any]:
    """Fuzzy name comparison using token sort ratio (handles word order differences)."""
    if not ocr_name or not form_name:
        return {"score": 0, "matched": False, "note": "Missing value"}

    # Normalize
    ocr_clean = _normalize_name(ocr_name)
    form_clean = _normalize_name(form_name)

    token_sort_score = fuzz.token_sort_ratio(ocr_clean, form_clean)
    token_set_score = fuzz.token_set_ratio(ocr_clean, form_clean)
    partial_score = fuzz.partial_ratio(ocr_clean, form_clean)

    # Take best of the three strategies
    best_score = max(token_sort_score, token_set_score, partial_score)

    return {
        "score": best_score,
        "matched": best_score >= NAME_MATCH_THRESHOLD,
        "ocr_value": ocr_name,
        "form_value": form_name,
        "token_sort": token_sort_score,
        "token_set": token_set_score,
    }


def _normalize_name(name: str) -> str:
    """Normalize a name for comparison: lowercase, strip titles and extra spaces."""
    name = name.lower().strip()
    # Remove common titles
    titles = r"\b(mr|mrs|ms|dr|shri|smt|ku|kumari|late)\b\.?"
    name = re.sub(titles, "", name, flags=re.IGNORECASE)
    # Collapse whitespace
    name = re.sub(r"\s+", " ", name).strip()
    return name


def _dob_match(ocr_dob: str, form_dob: str) -> dict[str, Any]:
    """Parse and compare dates of birth from different format strings."""
    if not ocr_dob or not form_dob:
        return {"score": 0, "matched": False, "note": "Missing DOB"}

    ocr_parsed = _parse_dob(ocr_dob)
    form_parsed = _parse_dob(form_dob)

    if ocr_parsed is None or form_parsed is None:
        return {
            "score": 40,
            "matched": False,
            "note": f"Could not parse one or both dates: OCR='{ocr_dob}', Form='{form_dob}'",
        }

    if ocr_parsed == form_parsed:
        return {"score": 100, "matched": True, "ocr_value": ocr_dob, "form_value": form_dob}

    # Partial match: same year+month but day differs (common OCR error)
    if ocr_parsed.year == form_parsed.year and ocr_parsed.month == form_parsed.month:
        return {
            "score": 60,
            "matched": False,
            "note": f"Year and month match but day differs: OCR={ocr_parsed}, Form={form_parsed}",
            "ocr_value": str(ocr_parsed),
            "form_value": str(form_parsed),
        }

    return {
        "score": 0,
        "matched": False,
        "note": f"DOB mismatch: OCR={ocr_parsed}, Form={form_parsed}",
        "ocr_value": str(ocr_parsed),
        "form_value": str(form_parsed),
    }


def _parse_dob(date_str: str):
    """Try multiple date formats commonly found in Indian documents."""
    from datetime import date
    date_str = date_str.strip()
    formats = [
        "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y",
        "%d/%m/%y", "%d-%m-%y",
        "%Y-%m-%d",
        "%d %b %Y", "%d %B %Y",
        "%B %d, %Y",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue
    return None


def _income_match(ocr_income: int | None, form_income: float | None) -> dict[str, Any]:
    """
    Compare income amounts with a tolerance band.
    OCR amount within ±5% of form amount → matched.
    """
    if ocr_income is None or form_income is None or form_income == 0:
        return {"score": 0, "matched": False, "note": "Missing income value"}

    diff = abs(ocr_income - form_income)
    pct_diff = diff / form_income if form_income else 1.0

    if pct_diff <= AMOUNT_TOLERANCE_PCT:
        score = 100
        matched = True
    elif pct_diff <= 0.15:
        score = int(70 - (pct_diff - AMOUNT_TOLERANCE_PCT) * 300)
        matched = False
    else:
        score = 0
        matched = False

    return {
        "score": max(0, score),
        "matched": matched,
        "ocr_value": ocr_income,
        "form_value": form_income,
        "difference_pct": round(pct_diff * 100, 1),
    }


def _percentage_match(ocr_pct: float | None, form_pct: float | None) -> dict[str, Any]:
    """
    Compare academic percentages with a ±2 point tolerance.
    Also catches CGPAto-% conversion errors.
    """
    if ocr_pct is None or form_pct is None:
        return {"score": 0, "matched": False, "note": "Missing percentage"}

    diff = abs(ocr_pct - form_pct)
    if diff <= PERCENTAGE_TOLERANCE:
        score = 100
        matched = True
    elif diff <= 5.0:
        score = int(70 - (diff - PERCENTAGE_TOLERANCE) * 10)
        matched = False
    else:
        score = max(0, int(40 - diff * 2))
        matched = False

    return {
        "score": score,
        "matched": matched,
        "ocr_value": ocr_pct,
        "form_value": form_pct,
        "difference": round(diff, 2),
    }


def _aadhaar_last4_match(ocr_aadhaar: str | None, form_last4: str | None) -> dict[str, Any]:
    """Compare only the last 4 digits of Aadhaar (never store full number)."""
    if not ocr_aadhaar or not form_last4:
        return {"score": 0, "matched": False, "note": "Missing Aadhaar data"}

    # Extract last 4 from OCR result
    clean_aadhaar = re.sub(r"\s", "", ocr_aadhaar)
    ocr_last4 = clean_aadhaar[-4:] if len(clean_aadhaar) >= 4 else clean_aadhaar

    matched = ocr_last4 == form_last4
    return {
        "score": 100 if matched else 0,
        "matched": matched,
        "ocr_last4": ocr_last4,
        "form_last4": form_last4,
    }


def _ifsc_match(ocr_ifsc: str | None, form_ifsc: str | None) -> dict[str, Any]:
    """Exact IFSC code comparison."""
    if not ocr_ifsc or not form_ifsc:
        return {"score": 0, "matched": False, "note": "Missing IFSC"}

    ocr_clean = ocr_ifsc.strip().upper()
    form_clean = form_ifsc.strip().upper()
    matched = ocr_clean == form_clean

    # Partial match (first 4 chars = bank code correct, branch differs)
    if not matched and len(ocr_clean) == 11 and len(form_clean) == 11:
        bank_match = ocr_clean[:4] == form_clean[:4]
        return {
            "score": 50 if bank_match else 0,
            "matched": False,
            "ocr_value": ocr_ifsc,
            "form_value": form_ifsc,
            "note": "Bank code matches but branch code differs" if bank_match else "IFSC mismatch",
        }

    return {"score": 100 if matched else 0, "matched": matched}


# ── Document Type → Match Logic Mapping ──────────────────────────────────────

MATCH_RULES: dict[str, list[dict]] = {
    "AADHAAR_CARD": [
        {"field": "name", "extractor_key": "name", "form_key": "name",
         "matcher": _name_match, "critical": True, "weight": 0.4},
        {"field": "dob", "extractor_key": "dob", "form_key": "dob",
         "matcher": _dob_match, "critical": True, "weight": 0.4},
        {"field": "aadhaar_last4", "extractor_key": "aadhaar_number_clean", "form_key": "aadhaar_last4",
         "matcher": _aadhaar_last4_match, "critical": True, "weight": 0.2},
    ],
    "INCOME_CERTIFICATE": [
        {"field": "name", "extractor_key": "name", "form_key": "name",
         "matcher": _name_match, "critical": True, "weight": 0.3},
        {"field": "income_amount", "extractor_key": "income_amount_normalized", "form_key": "income",
         "matcher": _income_match, "critical": True, "weight": 0.5},
        {"field": "issue_date_staleness", "extractor_key": "is_stale", "form_key": None,
         "matcher": None, "critical": False, "weight": 0.2},
    ],
    "CASTE_CERTIFICATE": [
        {"field": "name", "extractor_key": "name", "form_key": "name",
         "matcher": _name_match, "critical": True, "weight": 0.6},
        {"field": "caste_category", "extractor_key": "caste_category", "form_key": None,
         "matcher": None, "critical": False, "weight": 0.4},
    ],
    "MARKSHEET_10": [
        {"field": "student_name", "extractor_key": "name", "form_key": "name",
         "matcher": _name_match, "critical": True, "weight": 0.4},
        {"field": "percentage", "extractor_key": "percentage_normalized", "form_key": "percentage_10",
         "matcher": _percentage_match, "critical": True, "weight": 0.6},
    ],
    "MARKSHEET_12": [
        {"field": "student_name", "extractor_key": "name", "form_key": "name",
         "matcher": _name_match, "critical": True, "weight": 0.4},
        {"field": "percentage", "extractor_key": "percentage_normalized", "form_key": "percentage_12",
         "matcher": _percentage_match, "critical": True, "weight": 0.6},
    ],
    "MARKSHEET_UG": [
        {"field": "student_name", "extractor_key": "name", "form_key": "name",
         "matcher": _name_match, "critical": True, "weight": 0.4},
        {"field": "percentage", "extractor_key": "percentage_normalized", "form_key": "percentage_ug",
         "matcher": _percentage_match, "critical": True, "weight": 0.6},
    ],
    "MARKSHEET_PG": [
        {"field": "student_name", "extractor_key": "name", "form_key": "name",
         "matcher": _name_match, "critical": True, "weight": 0.4},
        {"field": "percentage", "extractor_key": "percentage_normalized", "form_key": "percentage_pg",
         "matcher": _percentage_match, "critical": True, "weight": 0.6},
    ],
    "BANK_PASSBOOK": [
        {"field": "account_holder_name", "extractor_key": "name", "form_key": "name",
         "matcher": _name_match, "critical": True, "weight": 0.5},
        {"field": "ifsc_code", "extractor_key": "ifsc_code", "form_key": "bank_ifsc",
         "matcher": _ifsc_match, "critical": True, "weight": 0.5},
    ],
    "PASSPORT": [
        {"field": "name", "extractor_key": "name", "form_key": "name",
         "matcher": _name_match, "critical": True, "weight": 0.5},
        {"field": "dob", "extractor_key": "dob", "form_key": "dob",
         "matcher": _dob_match, "critical": True, "weight": 0.5},
    ],
}


def match_document_to_form(
    extracted_fields: dict[str, Any],
    form_data: dict[str, Any],
    doc_type: str,
) -> dict[str, Any]:
    """
    Run field-by-field matching between OCR-extracted values and typed form data.

    Returns:
      {
        "overall_match_score": float,     # 0-100
        "field_results": dict,            # per-field match details
        "critical_mismatches": list[dict], # fields that must match but don't
        "warnings": list[str],
        "matched_fields": int,
        "total_fields": int,
      }
    """
    rules = MATCH_RULES.get(doc_type, [])
    field_results: dict[str, Any] = {}
    critical_mismatches: list[dict] = []
    warnings: list[str] = []
    weighted_score = 0.0
    total_weight = 0.0

    for rule in rules:
        field = rule["field"]
        extractor_key = rule["extractor_key"]
        form_key = rule["form_key"]
        matcher = rule["matcher"]
        is_critical = rule["critical"]
        weight = rule["weight"]

        if matcher is None:
            # Non-matcher rules (e.g., staleness) — handled by flags
            continue

        ocr_val = extracted_fields.get(extractor_key)
        form_val = form_data.get(form_key) if form_key else None

        if ocr_val is None:
            field_results[field] = {
                "score": 0,
                "matched": False,
                "note": f"Field '{extractor_key}' could not be extracted from document",
            }
            warnings.append(
                f"Could not extract '{field}' from the document. "
                "Ensure the document is clear and contains the required information."
            )
            total_weight += weight
            continue

        # Run matcher
        match_result = matcher(ocr_val, form_val)
        field_results[field] = match_result

        score = match_result.get("score", 0)
        weighted_score += score * weight
        total_weight += weight

        if not match_result.get("matched") and is_critical:
            critical_mismatches.append({
                "field": field,
                "message": _build_mismatch_message(
                    field, match_result, doc_type
                ),
                "form_value": str(match_result.get("form_value") or form_val or "N/A"),
                "extracted_value": str(match_result.get("ocr_value") or ocr_val or "N/A"),
            })

    overall_score = (weighted_score / total_weight) if total_weight > 0 else 0.0

    matched_count = sum(1 for r in field_results.values() if r.get("matched"))
    total_count = len(field_results)

    logger.info(
        f"[MATCH] {doc_type}: score={overall_score:.1f}% | "
        f"matched={matched_count}/{total_count} | "
        f"critical_mismatches={len(critical_mismatches)}"
    )

    return {
        "overall_match_score": round(overall_score, 2),
        "field_results": field_results,
        "critical_mismatches": critical_mismatches,
        "warnings": warnings,
        "matched_fields": matched_count,
        "total_fields": total_count,
    }


def _build_mismatch_message(field: str, match_result: dict, doc_type: str) -> str:
    """Generate a human-readable mismatch message for the applicant."""
    field_labels = {
        "name": "Applicant Name",
        "student_name": "Student Name",
        "account_holder_name": "Account Holder Name",
        "dob": "Date of Birth",
        "income_amount": "Annual Family Income",
        "percentage": "Academic Percentage",
        "aadhaar_last4": "Aadhaar Last 4 Digits",
        "ifsc_code": "Bank IFSC Code",
    }
    label = field_labels.get(field, field.replace("_", " ").title())
    note = match_result.get("note", "")
    ocr_val = match_result.get("ocr_value", "N/A")
    form_val = match_result.get("form_value", "N/A")

    msg = f"**{label}** mismatch in {doc_type.replace('_', ' ').title()}."

    if field in ("name", "student_name", "account_holder_name"):
        score = match_result.get("score", 0)
        msg += f" Name in document ('{ocr_val}') does not match the name in your form ('{form_val}'). Match score: {score}%."
    elif field == "dob":
        msg += f" Date of birth in document ({ocr_val}) does not match your form ({form_val}). {note}"
    elif field == "income_amount":
        diff_pct = match_result.get("difference_pct", 0)
        msg += (
            f" Income amount in document (₹{ocr_val:,.0f}) differs from form (₹{form_val:,.0f}) "
            f"by {diff_pct:.1f}%. Please ensure the income certificate reflects the family income "
            "as declared in your application."
        )
    elif field == "percentage":
        diff = match_result.get("difference", 0)
        msg += (
            f" Marks in document ({ocr_val}%) differ from your form ({form_val}%) "
            f"by {diff:.1f} points. Please re-upload the correct marksheet."
        )
    elif field == "aadhaar_last4":
        msg += " The last 4 digits of Aadhaar in the document do not match what you entered."
    elif field == "ifsc_code":
        msg += f" IFSC code in passbook ({ocr_val}) does not match form ({form_val})."
    else:
        msg += f" {note}"

    return msg

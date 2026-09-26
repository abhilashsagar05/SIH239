"""
Standalone OCR Pipeline Test Runner
====================================
Use this script to test the AI pipeline without running the full FastAPI server.

Usage:
    python -m ai_engine.test_runner --image ./sample_docs/income_cert.jpg \
           --type INCOME_CERTIFICATE \
           --name "Ramesh Kumar" \
           --income 250000

Requires Tesseract installed:
    Windows: https://github.com/UB-Mannheim/tesseract/wiki
    Linux:   sudo apt install tesseract-ocr tesseract-ocr-hin
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path


def run_test(
    image_path: str,
    doc_type: str,
    form_name: str = "Test User",
    form_dob: str = "01/01/1995",
    form_income: float = 200000.0,
    form_percentage: float | None = None,
    form_aadhaar_last4: str = "1234",
    form_bank_ifsc: str = "SBIN0001234",
):
    print(f"\n{'='*60}")
    print(f"  MoTA OCR Pipeline — Test Runner")
    print(f"{'='*60}")
    print(f"  Document: {image_path}")
    print(f"  Type: {doc_type}")
    print(f"{'='*60}\n")

    image_bytes = Path(image_path).read_bytes()

    # ── Step 1: Preprocess ────────────────────────────────────────────────────
    print("[1/5] Preprocessing image...")
    from ai_engine.ocr_pipeline import preprocess_image, extract_text, extract_structured_fields, EXTRACTION_CONFIGS, DEFAULT_CONFIG

    t0 = time.monotonic()
    processed_img, pre_meta = preprocess_image(image_bytes)
    print(f"      ✓ Done in {(time.monotonic()-t0)*1000:.0f}ms")
    print(f"      Original size: {pre_meta['original_size']}")
    print(f"      Blur score: {pre_meta['blur_score']:.1f} (blurry: {pre_meta['is_blurry']})")
    print(f"      Skew angle: {pre_meta.get('skew_angle', 0):.1f}°")
    print(f"      Steps: {', '.join(pre_meta['preprocessing_steps'])}")

    # ── Step 2: OCR ───────────────────────────────────────────────────────────
    print("\n[2/5] Running Tesseract OCR...")
    t0 = time.monotonic()
    doc_config = EXTRACTION_CONFIGS.get(doc_type, DEFAULT_CONFIG)
    raw_text, ocr_confidence = extract_text(processed_img, doc_config["psm_config"])
    elapsed_ms = (time.monotonic() - t0) * 1000
    print(f"      ✓ Done in {elapsed_ms:.0f}ms")
    print(f"      OCR Confidence: {ocr_confidence:.1f}%")
    print(f"      Characters extracted: {len(raw_text)}")
    print(f"\n      ── Raw Text (first 500 chars) ──")
    print(f"      {raw_text[:500].replace(chr(10), ' | ')}")

    # ── Step 3: Field Extraction ──────────────────────────────────────────────
    print("\n[3/5] Extracting structured fields...")
    t0 = time.monotonic()
    extracted = extract_structured_fields(raw_text, doc_type)
    print(f"      ✓ Done in {(time.monotonic()-t0)*1000:.0f}ms")
    print(f"      Extracted fields:")
    for k, v in extracted.items():
        print(f"        {k}: {v}")

    # ── Step 4: Fraud Detection ───────────────────────────────────────────────
    print("\n[4/5] Running fraud detection checks...")
    from ai_engine.fraud_detector import detect_fraud

    t0 = time.monotonic()
    fraud = detect_fraud(
        image_bytes=image_bytes,
        processed_img=processed_img,
        pre_meta=pre_meta,
        raw_text=raw_text,
        doc_type=doc_type,
    )
    print(f"      ✓ Done in {(time.monotonic()-t0)*1000:.0f}ms")
    print(f"      Checks: {', '.join(fraud['checks_performed'])}")
    print(f"      Integrity score: {fraud['integrity_score']:.1f}%")
    print(f"      Is blurry: {fraud['is_blurry']}")
    print(f"      Is tampered: {fraud['is_tampered']}")
    print(f"      ELA score: {fraud.get('ela_score', 0):.2f}")
    if fraud["tamper_signals"]:
        print(f"      ⚠️  Signals:")
        for sig in fraud["tamper_signals"]:
            print(f"        - {sig}")

    # ── Step 5: Matching + Confidence ─────────────────────────────────────────
    print("\n[5/5] Matching against form data and scoring...")
    from ai_engine.document_matcher import match_document_to_form
    from ai_engine.confidence_scorer import compute_confidence_score

    form_data = {
        "name": form_name,
        "dob": form_dob,
        "income": form_income,
        "percentage_10": form_percentage,
        "percentage_12": form_percentage,
        "percentage_ug": form_percentage,
        "percentage_pg": form_percentage,
        "aadhaar_last4": form_aadhaar_last4,
        "bank_ifsc": form_bank_ifsc,
        "institution_name": "",
        "course_name": "",
        "gender": "MALE",
    }

    t0 = time.monotonic()
    match = match_document_to_form(extracted, form_data, doc_type)
    confidence = compute_confidence_score(ocr_confidence, extracted, match, fraud, doc_type)
    print(f"      ✓ Done in {(time.monotonic()-t0)*1000:.0f}ms")

    # ── Final Report ──────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"  📊 FINAL CONFIDENCE REPORT")
    print(f"{'='*60}")
    print(f"  Overall Score:    {confidence['overall']:.1f}%")
    print(f"  Grade:            {confidence['grade']}")
    print(f"  Recommendation:   {confidence['recommendation']}")
    print(f"\n  Component Breakdown:")
    for k, v in confidence["components"].items():
        bar = "█" * int(v / 5) + "░" * (20 - int(v / 5))
        print(f"    {k:<20} [{bar}] {v:.1f}%")

    print(f"\n  Match Score:      {match['overall_match_score']:.1f}%")
    print(f"  Matched Fields:   {match['matched_fields']}/{match['total_fields']}")

    if match["critical_mismatches"]:
        print(f"\n  ❌ Critical Mismatches ({len(match['critical_mismatches'])}):")
        for m in match["critical_mismatches"]:
            print(f"     [{m['field']}] {m['message'][:120]}")

    if confidence["penalty_reasons"]:
        print(f"\n  ⚠️  Score Penalties:")
        for r in confidence["penalty_reasons"]:
            print(f"     - {r[:120]}")

    print(f"\n{'='*60}\n")

    return {
        "overall_confidence": confidence["overall"],
        "grade": confidence["grade"],
        "recommendation": confidence["recommendation"],
        "match_score": match["overall_match_score"],
        "is_tampered": fraud["is_tampered"],
        "is_blurry": pre_meta["is_blurry"],
        "extracted_fields": extracted,
        "critical_mismatches": match["critical_mismatches"],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MoTA OCR Pipeline Test Runner")
    parser.add_argument("--image", required=True, help="Path to document image or PDF")
    parser.add_argument("--type", required=True,
                        choices=list(["AADHAAR_CARD", "INCOME_CERTIFICATE", "CASTE_CERTIFICATE",
                                     "MARKSHEET_10", "MARKSHEET_12", "MARKSHEET_UG",
                                     "MARKSHEET_PG", "ADMISSION_LETTER", "BANK_PASSBOOK", "PASSPORT"]),
                        help="Document type")
    parser.add_argument("--name", default="Test Applicant", help="Applicant name (from form)")
    parser.add_argument("--dob", default="01/01/1995", help="Date of birth (DD/MM/YYYY)")
    parser.add_argument("--income", type=float, default=200000.0, help="Annual family income")
    parser.add_argument("--percentage", type=float, default=None, help="Academic percentage")
    parser.add_argument("--aadhaar-last4", default="1234", help="Aadhaar last 4 digits")
    parser.add_argument("--ifsc", default="SBIN0001234", help="Bank IFSC code")
    parser.add_argument("--json", action="store_true", help="Output as JSON")

    args = parser.parse_args()

    if not Path(args.image).exists():
        print(f"❌ Error: File not found: {args.image}", file=sys.stderr)
        sys.exit(1)

    result = run_test(
        image_path=args.image,
        doc_type=args.type,
        form_name=args.name,
        form_dob=args.dob,
        form_income=args.income,
        form_percentage=args.percentage,
        form_aadhaar_last4=args.aadhaar_last4,
        form_bank_ifsc=args.ifsc,
    )

    if args.json:
        print(json.dumps(result, indent=2, default=str))

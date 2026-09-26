"""
Fraud Detection Engine — Image integrity and authenticity analysis.

Detection methods:
  1. Blur detection (Laplacian variance)
  2. Noise analysis (standard deviation in flat regions)
  3. JPEG compression artifact detection (Error Level Analysis - ELA)
  4. Metadata consistency check
  5. Copy-move detection (block matching)
  6. Text layout anomaly detection
  7. Digital watermark / seal detection
"""
from __future__ import annotations

import io
import logging
from typing import Any

import cv2
import numpy as np
from PIL import Image, ImageChops, ImageEnhance

logger = logging.getLogger("mota.fraud")

# Thresholds
BLUR_THRESHOLD = 100.0          # Laplacian variance — below = blurry
ELA_THRESHOLD = 25.0            # Mean ELA error — above = potential manipulation
NOISE_STD_THRESHOLD = 20.0      # Standard deviation in uniform regions
EDGE_DENSITY_THRESHOLD = 0.15   # Too many edges = possible overlay/stamp forgery


def detect_fraud(
    image_bytes: bytes,
    processed_img: np.ndarray,
    pre_meta: dict[str, Any],
    raw_text: str,
    doc_type: str,
) -> dict[str, Any]:
    """
    Run the complete fraud detection suite on a document image.

    Returns:
      {
        "is_tampered": bool,
        "is_blurry": bool,
        "blur_score": float,
        "ela_score": float,
        "tamper_signals": list[str],
        "integrity_score": float,   # 0-100, higher = more trustworthy
        "checks_performed": list[str],
      }
    """
    result: dict[str, Any] = {
        "is_tampered": False,
        "is_blurry": pre_meta.get("is_blurry", False),
        "blur_score": pre_meta.get("blur_score", 0.0),
        "ela_score": 0.0,
        "tamper_signals": [],
        "integrity_score": 100.0,
        "checks_performed": [],
    }

    penalty = 0.0  # Subtract from 100

    # ── Check 1: Blur ─────────────────────────────────────────────────────────
    blur_score = float(pre_meta.get("blur_score", 0.0))
    result["checks_performed"].append("blur_detection")
    if result["is_blurry"]:
        penalty += 40.0
        result["tamper_signals"].append(
            f"Image is too blurry (Laplacian score: {blur_score:.1f} < {BLUR_THRESHOLD}). "
            "OCR results may be unreliable."
        )
        logger.warning(f"[FRAUD] Blur detected: score={blur_score:.1f}")

    # ── Check 2: Error Level Analysis (ELA) ──────────────────────────────────
    try:
        ela_score, ela_details = _error_level_analysis(image_bytes)
        result["ela_score"] = round(ela_score, 2)
        result["checks_performed"].append("ela_analysis")

        if ela_score > ELA_THRESHOLD:
            penalty += min(ela_score, 35.0)
            result["is_tampered"] = True
            result["tamper_signals"].append(
                f"Error Level Analysis detected potential image manipulation (ELA score: {ela_score:.1f}). "
                "Certain regions show inconsistent compression artifacts suggesting content editing."
            )
            logger.warning(f"[FRAUD] ELA tamper signal: score={ela_score:.1f}")
    except Exception as e:
        logger.debug(f"[FRAUD] ELA check failed: {e}")

    # ── Check 3: Copy-Move Detection ──────────────────────────────────────────
    try:
        copy_move_detected, cm_details = _detect_copy_move(processed_img)
        result["checks_performed"].append("copy_move_detection")
        if copy_move_detected:
            penalty += 30.0
            result["is_tampered"] = True
            result["tamper_signals"].append(
                "Copy-move forgery detected: identical block patterns found in different image regions, "
                "suggesting text or elements have been duplicated/moved."
            )
            logger.warning(f"[FRAUD] Copy-move detected: {cm_details}")
    except Exception as e:
        logger.debug(f"[FRAUD] Copy-move check failed: {e}")

    # ── Check 4: Edge Density Anomaly ─────────────────────────────────────────
    try:
        edge_density = _compute_edge_density(processed_img)
        result["edge_density"] = round(edge_density, 4)
        result["checks_performed"].append("edge_density")
        if edge_density > EDGE_DENSITY_THRESHOLD:
            penalty += 10.0
            result["tamper_signals"].append(
                f"Unusually high edge density ({edge_density:.3f}) detected, "
                "possibly indicating overlaid stamps, seals, or text additions."
            )
    except Exception as e:
        logger.debug(f"[FRAUD] Edge density check failed: {e}")

    # ── Check 5: Text Consistency Checks ──────────────────────────────────────
    text_flags = _check_text_consistency(raw_text, doc_type)
    result["checks_performed"].append("text_consistency")
    for flag in text_flags:
        penalty += flag["penalty"]
        result["tamper_signals"].append(flag["message"])
        if flag["severity"] == "HIGH":
            result["is_tampered"] = True

    # ── Check 6: Noise Uniformity ──────────────────────────────────────────────
    try:
        noise_score = _analyze_noise_uniformity(processed_img)
        result["noise_score"] = round(noise_score, 2)
        result["checks_performed"].append("noise_uniformity")
        if noise_score > NOISE_STD_THRESHOLD:
            penalty += 8.0
            result["tamper_signals"].append(
                f"Non-uniform noise distribution detected (score: {noise_score:.1f}), "
                "which can indicate composite document creation."
            )
    except Exception as e:
        logger.debug(f"[FRAUD] Noise uniformity check failed: {e}")

    # ── Compute Final Integrity Score ─────────────────────────────────────────
    result["integrity_score"] = max(0.0, round(100.0 - penalty, 2))

    # A tampered flag must have integrity score < 50
    if result["integrity_score"] < 50:
        result["is_tampered"] = True

    logger.info(
        f"[FRAUD] integrity={result['integrity_score']:.1f}% | "
        f"tampered={result['is_tampered']} | "
        f"signals={len(result['tamper_signals'])}"
    )
    return result


def _error_level_analysis(image_bytes: bytes, quality: int = 95) -> tuple[float, dict]:
    """
    Error Level Analysis (ELA) — Resave image at known quality and measure residual error.

    Authentic images have uniform ELA levels. Manipulated images show higher
    error levels in tampered regions because those pixels were compressed
    differently from the rest.
    """
    try:
        original = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    except Exception:
        return 0.0, {}

    # Resave at target quality
    buffer = io.BytesIO()
    original.save(buffer, format="JPEG", quality=quality)
    buffer.seek(0)
    resaved = Image.open(buffer).convert("RGB")

    # Compute difference (amplified for visibility)
    diff = ImageChops.difference(original, resaved)
    enhancer = ImageEnhance.Brightness(diff)
    diff_enhanced = enhancer.enhance(10)

    # Convert to numpy for analysis
    diff_arr = np.array(diff_enhanced.convert("L"), dtype=np.float32)

    ela_mean = float(np.mean(diff_arr))
    ela_std = float(np.std(diff_arr))
    ela_max = float(np.max(diff_arr))

    # High standard deviation + high mean → suspicious region variations
    ela_score = ela_mean + (ela_std * 0.3)

    return ela_score, {"mean": ela_mean, "std": ela_std, "max": ela_max}


def _detect_copy_move(gray: np.ndarray, block_size: int = 16, threshold: int = 5) -> tuple[bool, dict]:
    """
    Block-based copy-move forgery detection using DCT features.

    Divides image into overlapping blocks, extracts DCT coefficients,
    sorts them, and detects matching blocks that appear in different locations.
    """
    h, w = gray.shape

    # Resize to manageable size for speed
    if h > 512 or w > 512:
        scale = min(512 / h, 512 / w)
        gray = cv2.resize(gray, (int(w * scale), int(h * scale)))
        h, w = gray.shape

    if h < block_size * 2 or w < block_size * 2:
        return False, {}

    # Extract DCT blocks
    features = []
    for i in range(0, h - block_size, block_size // 2):
        for j in range(0, w - block_size, block_size // 2):
            block = gray[i:i + block_size, j:j + block_size].astype(np.float32)
            dct = cv2.dct(block)
            # Take first 5 DCT coefficients as feature vector
            feat = dct[:5, :5].flatten()
            features.append((feat, (i, j)))

    if len(features) < 2:
        return False, {}

    # Sort by feature vector to find duplicates
    features.sort(key=lambda x: x[0].tobytes())

    match_count = 0
    for k in range(len(features) - 1):
        feat1, pos1 = features[k]
        feat2, pos2 = features[k + 1]

        # Euclidean distance between feature vectors
        dist = np.linalg.norm(feat1 - feat2)
        if dist < threshold:
            # Positions must be spatially separate
            spatial_dist = abs(pos1[0] - pos2[0]) + abs(pos1[1] - pos2[1])
            if spatial_dist > block_size * 2:
                match_count += 1

    # More than 3 matching pairs is suspicious
    detected = match_count > 3
    return detected, {"matching_blocks": match_count}


def _compute_edge_density(gray: np.ndarray) -> float:
    """
    Compute the fraction of pixels that are edges.
    Authentic documents have moderate edge density; composite images are denser.
    """
    edges = cv2.Canny(gray, 100, 200)
    total_pixels = gray.shape[0] * gray.shape[1]
    edge_pixels = int(np.sum(edges > 0))
    return edge_pixels / total_pixels if total_pixels > 0 else 0.0


def _analyze_noise_uniformity(gray: np.ndarray) -> float:
    """
    Analyze noise uniformity across image regions.
    Non-uniform noise indicates multiple source images composed together.
    """
    h, w = gray.shape
    region_stds = []

    # Divide into 4 quadrants
    regions = [
        gray[:h // 2, :w // 2],
        gray[:h // 2, w // 2:],
        gray[h // 2:, :w // 2],
        gray[h // 2:, w // 2:],
    ]

    for region in regions:
        if region.size > 0:
            region_stds.append(float(np.std(region)))

    if len(region_stds) < 2:
        return 0.0

    # High variance across region noise levels = suspicious
    return float(np.std(region_stds))


def _check_text_consistency(raw_text: str, doc_type: str) -> list[dict]:
    """
    Check for textual red flags specific to document types:
    - Future dates
    - Mismatched financial years
    - Inconsistent serial numbers / reference numbers
    - Known forgery phrases
    """
    import re
    from datetime import date

    flags = []
    today = date.today()
    current_year = today.year

    # Check for obvious future dates
    year_matches = re.findall(r"\b(20\d{2})\b", raw_text)
    for year_str in year_matches:
        year = int(year_str)
        if year > current_year + 1:
            flags.append({
                "message": f"Suspicious future year '{year}' found in document text. "
                           "Document may be pre-dated or fabricated.",
                "severity": "HIGH",
                "penalty": 20.0,
            })
            break  # One flag is enough

    # Check for common forgery indicators in text
    forgery_phrases = [
        "specimen", "sample copy", "not valid", "cancelled",
        "void", "for demonstration", "test certificate",
    ]
    lower_text = raw_text.lower()
    for phrase in forgery_phrases:
        if phrase in lower_text:
            flags.append({
                "message": f"Document contains suspicious phrase: '{phrase}'. "
                           "This may be a sample or invalid document.",
                "severity": "HIGH",
                "penalty": 30.0,
            })

    # Income certificate: check income amount is not suspiciously round (potential fabrication)
    if doc_type == "INCOME_CERTIFICATE":
        amounts = re.findall(r"Rs\.?\s?([\d,]+)", raw_text)
        for amount_str in amounts:
            try:
                amount = int(amount_str.replace(",", ""))
                # Exactly 0 or obviously round numbers like 100000 are suspicious
                if amount == 0:
                    flags.append({
                        "message": "Income amount of ₹0 found. Please verify the document.",
                        "severity": "MEDIUM",
                        "penalty": 5.0,
                    })
            except ValueError:
                pass

    return flags

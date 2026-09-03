"""Receipt text extraction: OCR when available, regex fallback."""

import re
from datetime import datetime


def parse_receipt_text(text: str) -> dict:
    text = text or ""
    amount = None
    for pattern in (
        r"(?:total|amount|grand\s*total|amt)[:\s]*₹?\s*([\d,]+\.?\d*)",
        r"₹\s*([\d,]+\.?\d*)",
        r"([\d,]+\.\d{2})\s*(?:INR|Rs)?",
    ):
        m = re.search(pattern, text, re.I)
        if m:
            try:
                amount = float(m.group(1).replace(",", ""))
                break
            except ValueError:
                continue

    date_val = None
    for pattern in (
        r"(\d{4}-\d{2}-\d{2})",
        r"(\d{2}/\d{2}/\d{4})",
        r"(\d{2}-\d{2}-\d{4})",
    ):
        m = re.search(pattern, text)
        if m:
            raw = m.group(1)
            for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
                try:
                    date_val = datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
                    break
                except ValueError:
                    continue
            if date_val:
                break

    merchant = None
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if lines:
        merchant = lines[0][:80]

    description = merchant or "Receipt purchase"
    return {
        "amount": amount,
        "date": date_val or datetime.now().strftime("%Y-%m-%d"),
        "description": description,
        "merchant": merchant,
        "raw_text": text[:2000],
    }


def extract_from_image(file_storage) -> dict:
    """Try Tesseract OCR; fall back to empty text + message."""
    try:
        from PIL import Image
        import pytesseract
    except ImportError:
        return {
            "amount": None,
            "date": datetime.now().strftime("%Y-%m-%d"),
            "description": "Receipt upload",
            "merchant": None,
            "raw_text": "",
            "ocr_available": False,
            "message": "Install Pillow and pytesseract (and Tesseract OCR) for image scanning.",
        }

    try:
        image = Image.open(file_storage.stream)
        text = pytesseract.image_to_string(image)
        result = parse_receipt_text(text)
        result["ocr_available"] = True
        result["message"] = "OCR completed. Review fields before saving."
        return result
    except Exception as exc:
        return {
            "amount": None,
            "date": datetime.now().strftime("%Y-%m-%d"),
            "description": "Receipt upload",
            "merchant": None,
            "raw_text": "",
            "ocr_available": False,
            "message": f"OCR failed: {exc}",
        }

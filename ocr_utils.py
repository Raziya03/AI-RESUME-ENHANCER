import fitz  # PyMuPDF
import pytesseract
import cv2
import numpy as np
from PIL import Image


def preprocess_image(image):
    """
    Preprocess image for better OCR accuracy
    """
    img = np.array(image)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY)[1]
    return gray


def extract_text_from_pdf(pdf_path):
    """
    Fast text extraction from digitally created PDFs
    """
    text = ""
    try:
        doc = fitz.open(pdf_path)
        for page in doc:
            text += page.get_text()
    except Exception:
        return ""
    return text.strip()


def extract_text_from_image(image_path):
    """
    OCR for image resumes (JPG / PNG)
    """
    try:
        image = Image.open(image_path)
        processed = preprocess_image(image)
        return pytesseract.image_to_string(processed)
    except Exception:
        return ""


def extract_text(file_path):
    """
    Main extractor used by Flask app
    Priority:
    1. Native PDF text (FAST)
    2. Image OCR (SAFE)
    """

    # ---- PDF ----
    if file_path.lower().endswith(".pdf"):
        text = extract_text_from_pdf(file_path)

        # If PDF contains real text, return it
        if len(text) > 100:
            return text

        # If scanned PDF → return warning text (avoid hanging OCR)
        return (
            "This resume appears to be a scanned PDF. "
            "For best results, please upload a text-based PDF or image resume."
        )

    # ---- IMAGE ----
    return extract_text_from_image(file_path)

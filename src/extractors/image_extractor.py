from io import BytesIO
import os
import platform

import pytesseract
from PIL import Image
from fastapi import HTTPException, status

from src.config import settings


def extract_text_from_image(file_bytes: bytes) -> str:
    """
    Extract text from an image using Tesseract OCR.

    Works for:
    - Local Windows system with installed Tesseract
    - Linux/Render if Tesseract is installed in the environment
    - Optional custom path through TESSERACT_CMD or settings.tesseract_cmd
    """

    # 1) Prefer env var if explicitly provided
    tesseract_cmd = os.getenv("TESSERACT_CMD")

    # 2) Else use app config if present
    if not tesseract_cmd and getattr(settings, "tesseract_cmd", None):
        tesseract_cmd = settings.tesseract_cmd

    # 3) Else only on Windows use default local path
    if tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
    elif platform.system() == "Windows":
        pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

    try:
        image = Image.open(BytesIO(file_bytes))
        image = image.convert("RGB")
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to open image: {str(exc)}",
        )

    try:
        text = pytesseract.image_to_string(image)
        return text.strip()
    except pytesseract.TesseractNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "OCR processing failed: Tesseract is not installed or not available in this environment. "
                "On Windows, install Tesseract and set TESSERACT_CMD if needed. "
                "On Render/Linux, install the tesseract-ocr system package."
            ),
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"OCR processing failed: {str(exc)}",
        )
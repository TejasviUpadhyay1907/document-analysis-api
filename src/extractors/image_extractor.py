from io import BytesIO
import os
import platform
import shutil

import pytesseract
from PIL import Image
from fastapi import HTTPException, status

from src.config import settings


def _configure_tesseract() -> None:
    """Set pytesseract binary path. Explicit is better than relying on PATH."""
    # 1) Explicit env var always wins
    cmd = os.getenv("TESSERACT_CMD") or getattr(settings, "tesseract_cmd", None)
    if cmd:
        pytesseract.pytesseract.tesseract_cmd = cmd
        return

    # 2) On Linux/Mac — find via shutil.which (works on Render/Docker)
    if platform.system() != "Windows":
        found = shutil.which("tesseract")
        if found:
            pytesseract.pytesseract.tesseract_cmd = found
            return
        # Common Linux fallback paths
        for path in ["/usr/bin/tesseract", "/usr/local/bin/tesseract"]:
            if os.path.isfile(path):
                pytesseract.pytesseract.tesseract_cmd = path
                return

    # 3) Windows default
    if platform.system() == "Windows":
        pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"


def extract_text_from_image(file_bytes: bytes) -> str:
    """Extract text from an image using Tesseract OCR."""
    _configure_tesseract()

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
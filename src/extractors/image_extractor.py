from io import BytesIO
import pytesseract
from PIL import Image
from fastapi import HTTPException, status
from src.config import settings


def extract_text_from_image(file_bytes: bytes) -> str:
    """
    Extract text from an image using Tesseract OCR.

    - Loads image from bytes
    - Optionally sets custom Tesseract path
    - Runs OCR
    - Returns extracted text
    """

    # Set custom Tesseract path if provided (useful for Windows)
    if settings.tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = settings.tesseract_cmd

    try:
        image = Image.open(BytesIO(file_bytes))

        # Convert to RGB to avoid issues with some formats (e.g., PNG with alpha)
        image = image.convert("RGB")

    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to open image: {str(exc)}",
        )

    try:
        text = pytesseract.image_to_string(image)
        return text.strip()

    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"OCR processing failed: {str(exc)}",
        )
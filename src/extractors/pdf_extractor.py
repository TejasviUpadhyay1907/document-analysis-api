import io
import os
import platform
import shutil
import fitz
import pytesseract
from fastapi import HTTPException, status
from PIL import Image


def _configure_tesseract_for_pdf() -> None:
    """Set tesseract path correctly for the current platform."""
    cmd = os.getenv("TESSERACT_CMD")
    if cmd:
        pytesseract.pytesseract.tesseract_cmd = cmd
        return
    if platform.system() != "Windows":
        found = shutil.which("tesseract")
        if found:
            pytesseract.pytesseract.tesseract_cmd = found
            return
        for path in ["/usr/bin/tesseract", "/usr/local/bin/tesseract"]:
            if os.path.isfile(path):
                pytesseract.pytesseract.tesseract_cmd = path
                return
    else:
        pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"


def _ocr_page(page: fitz.Page) -> str:
    _configure_tesseract_for_pdf()
    pix = page.get_pixmap(matrix=fitz.Matrix(3, 3))
    image_bytes = pix.tobytes("png")
    image = Image.open(io.BytesIO(image_bytes))

    image = image.convert("L")

    text = pytesseract.image_to_string(image, config="--psm 6")
    return text.strip()


def extract_text_from_pdf(file_bytes: bytes) -> str:
    try:
        with fitz.open(stream=file_bytes, filetype="pdf") as doc:
            pages_text = []

            for page in doc:
                text = page.get_text("text")
                if text and text.strip():
                    pages_text.append(text.strip())

            combined_text = "\n".join(pages_text).strip()

            # Better check
            if len(combined_text.split()) >= 20:
                return combined_text

            # OCR fallback
            ocr_pages_text = []
            for page in doc:
                text = _ocr_page(page)
                if text:
                    ocr_pages_text.append(text)

            return "\n".join(ocr_pages_text).strip()

    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to extract text from PDF: {str(exc)}",
        )
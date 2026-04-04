from io import BytesIO
from docx import Document
from fastapi import HTTPException, status


def extract_text_from_docx(file_bytes: bytes) -> str:
    """
    Extract text from a DOCX file using python-docx.

    - Loads document from bytes
    - Extracts non-empty paragraphs
    - Returns cleaned combined text
    """
    try:
        doc = Document(BytesIO(file_bytes))

        paragraphs = [
            p.text.strip()
            for p in doc.paragraphs
            if p.text and p.text.strip()
        ]

        return "\n".join(paragraphs).strip()

    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to extract text from DOCX: {str(exc)}",
        )
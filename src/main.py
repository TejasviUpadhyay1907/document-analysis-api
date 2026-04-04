import logging
import shutil
import subprocess
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from src.auth import verify_api_key
from src.extractors.docx_extractor import extract_text_from_docx
from src.extractors.image_extractor import extract_text_from_image
from src.extractors.pdf_extractor import extract_text_from_pdf
from src.schemas import DocumentAnalyzeRequest, DocumentAnalyzeResponse, EntitiesModel
from src.services.entity_extractor import extract_entities
from src.services.llm_analyzer import analyze_with_llm
from src.services.output_finalizer import finalize_output
from src.services.text_cleaner import clean_text
from src.utils.file_utils import decode_base64_file

logger = logging.getLogger(__name__)

_FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

app = FastAPI(
    title="AI Document Analysis API",
    description="Extracts, classifies, and structures PDF, DOCX, and image documents.",
    version="5.0.0",
)

if _FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(_FRONTEND_DIR)), name="static")


@app.get("/ui", include_in_schema=False)
async def serve_ui():
    return FileResponse(str(_FRONTEND_DIR / "index.html"))


@app.get("/")
async def health_check():
    tesseract_path = shutil.which("tesseract")
    tesseract_version = None
    if tesseract_path:
        try:
            result = subprocess.run(
                ["tesseract", "--version"],
                capture_output=True, text=True, timeout=5
            )
            tesseract_version = result.stdout.splitlines()[0] if result.stdout else result.stderr.splitlines()[0]
        except Exception:
            pass
    return {
        "status": "ok",
        "message": "AI Document Analysis API is running.",
        "version": "5.0.0",
        "tesseract_installed": tesseract_path is not None,
        "tesseract_path": tesseract_path,
        "tesseract_version": tesseract_version,
    }


def _extract_by_file_type(file_type: str, file_bytes: bytes) -> str:
    if file_type == "pdf":
        return extract_text_from_pdf(file_bytes)
    if file_type == "docx":
        return extract_text_from_docx(file_bytes)
    if file_type == "image":
        return extract_text_from_image(file_bytes)
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Unsupported file type.",
    )


@app.post(
    "/api/document-analyze",
    response_model=DocumentAnalyzeResponse,
    dependencies=[Depends(verify_api_key)],
)
async def document_analyze(request: DocumentAnalyzeRequest):
    """
    Analyze a Base64-encoded document.
    Pipeline: decode -> extract -> clean -> LLM (optional) -> finalize -> respond
    """
    # 1. Decode Base64
    try:
        file_bytes = decode_base64_file(request.fileBase64)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid Base64 file data: {str(exc)}",
        ) from exc

    # 2. Extract raw text
    try:
        raw_text = _extract_by_file_type(request.fileType, file_bytes)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Extraction failed: {str(exc)}",
        ) from exc

    # 3. Clean text
    extracted_text = clean_text(raw_text)
    if not extracted_text:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No text could be extracted from the provided document.",
        )

    # 4. Rule-based entity extraction (always runs as baseline)
    rule_entities = extract_entities(extracted_text)
    rule_based = {"entities": rule_entities}

    # 5. LLM analysis (optional, used as suggestion)
    llm_result = analyze_with_llm(extracted_text)

    # 6. Final correction layer — deterministic override
    final = finalize_output(
        text=extracted_text,
        llm_result=llm_result,
        rule_based=rule_based,
    )

    return DocumentAnalyzeResponse(
        status="success",
        fileName=request.fileName,
        documentType=final["documentType"],
        extractedText=extracted_text,
        summary=final["summary"],
        entities=EntitiesModel(**final["entities"]),
        sentiment=final["sentiment"],
        documentData=final["documentData"],
    )

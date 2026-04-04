import logging
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from src.auth import verify_api_key
from src.extractors.docx_extractor import extract_text_from_docx
from src.extractors.image_extractor import extract_text_from_image
from src.extractors.pdf_extractor import extract_text_from_pdf
from src.schemas import DocumentAnalyzeRequest, DocumentAnalyzeResponse, EntitiesModel
from src.services.document_classifier import detect_document_type
from src.services.document_parsers.article_parser import parse_article
from src.services.document_parsers.incident_parser import parse_incident
from src.services.document_parsers.invoice_parser import parse_invoice
from src.services.document_parsers.resume_parser import parse_resume
from src.services.entity_extractor import extract_entities
from src.services.llm_analyzer import analyze_with_llm
from src.services.summarizer import generate_summary
from src.services.text_cleaner import clean_text
from src.utils.file_utils import decode_base64_file

logger = logging.getLogger(__name__)

_ALLOWED_DOC_TYPES = {"resume", "invoice", "incident_report", "article", "general"}
_FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

app = FastAPI(
    title="AI Document Analysis API",
    description="Extracts, classifies, and structures PDF, DOCX, and image documents.",
    version="4.0.2",
)

# Serve frontend static files
if _FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(_FRONTEND_DIR)), name="static")


@app.get("/ui", include_in_schema=False)
async def serve_ui():
    """Serve the demo frontend."""
    return FileResponse(str(_FRONTEND_DIR / "index.html"))


@app.get("/")
async def health_check():
    return {
        "status": "ok",
        "message": "AI Document Analysis API is running.",
        "version": "4.0.2",
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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


def _rule_based_parse(doc_type: str, text: str) -> dict:
    """Route to the correct rule-based parser. Never raises."""
    try:
        if doc_type == "resume":
            return parse_resume(text)
        if doc_type == "incident_report":
            return parse_incident(text)
        if doc_type == "invoice":
            return parse_invoice(text)
        if doc_type == "article":
            return parse_article(text)
    except Exception as exc:
        logger.warning("Rule-based parser failed for type=%s: %s", doc_type, exc)

    return {}


def _detect_sentiment(text: str, doc_type: str) -> str:
    """
    Lightweight fallback sentiment detection.

    Rules:
    - Incident reports are usually negative
    - Strongly positive language => positive
    - Everything else defaults to neutral
    """
    low = text.lower()

    if doc_type == "incident_report":
        return "negative"

    if any(word in low for word in ["success", "growth", "positive", "improved", "benefit", "innovation"]):
        return "positive"

    return "neutral"


def _rule_based_analysis(extracted_text: str) -> dict:
    """Full rule-based analysis pipeline. Used when LLM is unavailable or invalid."""
    doc_type = detect_document_type(extracted_text)
    entities = extract_entities(extracted_text)
    summary = generate_summary(extracted_text, doc_type)
    document_data = _rule_based_parse(doc_type, extracted_text)
    sentiment = _detect_sentiment(extracted_text, doc_type)

    return {
        "documentType": doc_type,
        "summary": summary,
        "entities": entities,
        "documentData": document_data,
        "sentiment": sentiment,
    }


def _is_valid_llm_result(result: dict | None) -> bool:
    """Basic validation so weak/broken LLM responses do not bypass fallback."""
    if not isinstance(result, dict):
        return False

    doc_type = result.get("documentType")
    summary = result.get("summary")
    entities = result.get("entities")
    document_data = result.get("documentData")
    sentiment = result.get("sentiment")

    if doc_type not in _ALLOWED_DOC_TYPES:
        return False

    if not isinstance(summary, str) or not summary.strip():
        return False

    if not isinstance(entities, dict):
        return False

    if not isinstance(document_data, dict):
        return False

    if sentiment not in {"positive", "neutral", "negative"}:
        return False

    required_entity_keys = {"names", "organizations", "dates", "amounts", "emails", "phones"}
    if not required_entity_keys.issubset(entities.keys()):
        return False

    return True


# ---------------------------------------------------------------------------
# Main endpoint
# ---------------------------------------------------------------------------

@app.post(
    "/api/document-analyze",
    response_model=DocumentAnalyzeResponse,
    dependencies=[Depends(verify_api_key)],
)
async def document_analyze(request: DocumentAnalyzeRequest):
    """
    Analyze a Base64-encoded document and return:
    - document type classification
    - professional summary
    - structured entities
    - sentiment
    - type-specific structured data

    Uses LLM analysis (OpenRouter) when configured, with automatic
    fallback to rule-based analysis if the LLM is unavailable or invalid.
    """
    # Step 1: Decode Base64
    try:
        file_bytes = decode_base64_file(request.fileBase64)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid Base64 file data: {str(exc)}",
        ) from exc

    # Step 2: Extract raw text
    try:
        raw_text = _extract_by_file_type(request.fileType, file_bytes)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Extraction failed: {str(exc)}",
        ) from exc

    # Step 3: Clean text
    extracted_text = clean_text(raw_text)
    if not extracted_text:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No text could be extracted from the provided document.",
        )

    # Step 4: Analyze - LLM primary, rule-based fallback
    llm_result = analyze_with_llm(extracted_text)

    if _is_valid_llm_result(llm_result):
        logger.info("LLM analysis succeeded for file: %s", request.fileName)
        doc_type = llm_result["documentType"]
        summary = llm_result["summary"]
        entities = EntitiesModel(**llm_result["entities"])
        sentiment = llm_result.get("sentiment", "neutral")
        document_data = llm_result["documentData"]
    else:
        logger.info("Using rule-based fallback for file: %s", request.fileName)
        rb = _rule_based_analysis(extracted_text)
        doc_type = rb["documentType"]
        summary = rb["summary"]
        entities = EntitiesModel(**rb["entities"])
        sentiment = rb.get("sentiment", "neutral")
        document_data = rb["documentData"]

    return DocumentAnalyzeResponse(
        status="success",
        fileName=request.fileName,
        documentType=doc_type,
        extractedText=extracted_text,
        summary=summary,
        entities=entities,
        sentiment=sentiment,
        documentData=document_data,
    )
from __future__ import annotations

from typing import Any, Dict, List, Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Request Model
# ---------------------------------------------------------------------------

class DocumentAnalyzeRequest(BaseModel):
    fileName: str = Field(
        ...,
        description="Name of the uploaded file",
        example="resume.docx",
        min_length=1,
    )

    fileType: Literal["pdf", "docx", "image"] = Field(
        ...,
        description="Type of document",
        example="docx",
    )

    fileBase64: str = Field(
        ...,
        description="Base64-encoded file content",
        example="JVBERi0xLjQKJ...",
        min_length=10,
    )


# ---------------------------------------------------------------------------
# Entities Model
# ---------------------------------------------------------------------------

class EntitiesModel(BaseModel):
    names: List[str] = Field(default_factory=list, description="Person names")
    organizations: List[str] = Field(default_factory=list, description="Organizations")
    dates: List[str] = Field(default_factory=list, description="Dates or years")
    amounts: List[str] = Field(default_factory=list, description="Currency values")
    emails: List[str] = Field(default_factory=list, description="Email addresses")
    phones: List[str] = Field(default_factory=list, description="Phone numbers")


# ---------------------------------------------------------------------------
# Response Model
# ---------------------------------------------------------------------------

class DocumentAnalyzeResponse(BaseModel):
    status: str = Field(..., example="success")

    fileName: str = Field(
        ...,
        example="resume.docx",
    )

    documentType: str = Field(
        ...,
        description="Detected document type",
        example="resume",
    )

    extractedText: str = Field(
        ...,
        description="Cleaned extracted text from document",
        example="Full extracted text...",
    )

    summary: str = Field(
        ...,
        description="Short human-readable summary",
        example="Short meaningful summary.",
    )

    entities: EntitiesModel = Field(
        default_factory=EntitiesModel,
        description="Generic extracted entities",
    )

    sentiment: Literal["Positive", "Neutral", "Negative"] = Field(
        default="Neutral",
        description="Overall sentiment of the document",
        example="Neutral",
    )

    documentData: Dict[str, Any] = Field(
        default_factory=dict,
        description="Type-specific structured data (varies by documentType)",
    )
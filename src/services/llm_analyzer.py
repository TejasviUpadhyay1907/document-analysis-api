"""
llm_analyzer.py
---------------
LLM-powered document analysis via OpenRouter.

Returns:
- normalized structured result on success
- None on failure, weak output, or invalid output

Fallback is handled in main.py.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

import httpx

from src.config import settings

logger = logging.getLogger(__name__)

_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
_MAX_TEXT_CHARS = 4000   # reduced to speed up LLM response
_TIMEOUT_SECONDS = 15    # reduced from 30 — fail fast, use rule-based fallback
_MAX_RETRIES = 1         # reduced from 3 — one attempt only, then fallback

_ALLOWED_DOC_TYPES = {"resume", "invoice", "incident_report", "article", "general"}
_ALLOWED_SENTIMENTS = {"positive", "neutral", "negative"}

_SYSTEM_PROMPT = """
You are an advanced AI Document Intelligence Engine.

You analyze noisy real-world document text extracted from PDFs, DOCX files, or OCR images.

The input text may contain:
- formatting issues
- missing punctuation
- merged lines
- OCR errors
- inconsistent structure

Your job is to understand the content and return a clean structured JSON output.

TASKS:
1. Identify the correct document type
2. Generate a professional summary
3. Extract clean entities
4. Determine overall sentiment
5. Extract document-specific structured data

DOCUMENT TYPE:
Classify into EXACTLY one of:
- "resume"
- "invoice"
- "incident_report"
- "article"
- "general"

CLASSIFICATION RULES:
- Resume: personal profile, education, skills, experience, projects, contact info
- Invoice: billing, amount, vendor, customer, date, payment details
- Incident Report: attack, breach, failure, investigation, cause, impact
- Article: long informative or analytical content discussing a topic
- General: anything else

SUMMARY RULES:
- Maximum 2 sentences
- Human-readable and professional
- Do NOT copy raw text verbatim
- Do NOT include emails, phone numbers, or URLs
- Explain what the document is about
- Avoid repeating titles
- Do not infer completed qualifications if the document shows an ongoing degree or future graduation year
- For ongoing education, describe the person as a student, not a graduate

ENTITY EXTRACTION RULES:
- names: real human names only, usually 2-4 words
- organizations: real companies, institutions, agencies
- dates: meaningful dates or years
- amounts: monetary values
- emails: valid email addresses present in text
- phones: valid phone numbers present in text
- Exclude headings, random words, long sentences, skills misclassified as names or organizations, and OCR junk
- Only include entities clearly present in the text

PHONE NUMBER RULES:
- Preserve valid phone numbers
- If a country code is clearly present without '+', you may normalize it by adding '+'
- Do not guess missing country codes
- Remove obvious formatting noise

SENTIMENT RULES:
- Return EXACTLY one of: "positive", "neutral", "negative"
- Informational documents like articles, resumes, invoices, and factual reports are usually "neutral"
- Incident reports describing breaches, failures, or attacks are often "negative"
- If unclear, return "neutral"

DOCUMENT-SPECIFIC DATA:
If documentType is "resume":
{
  "name": "",
  "education": [],
  "skills": [],
  "projects": [],
  "experience": []
}

If documentType is "invoice":
{
  "invoice_id": "",
  "vendor": "",
  "customer": "",
  "date": "",
  "amount": ""
}

If documentType is "incident_report":
{
  "incident_type": "",
  "affected_entities": [],
  "cause": [],
  "impact": []
}

If documentType is "article":
{
  "topic": "",
  "key_points": []
}

If documentType is "general":
{}

OUTPUT RULES:
- Return ONLY valid JSON
- No markdown
- No code fences
- No explanations
- No extra text before or after the JSON

Required JSON shape:
{
  "documentType": "",
  "summary": "",
  "entities": {
    "names": [],
    "organizations": [],
    "dates": [],
    "amounts": [],
    "emails": [],
    "phones": []
  },
  "sentiment": "",
  "documentData": {}
}
""".strip()


def _truncate_text(text: str) -> str:
    text = text.strip()
    if len(text) <= _MAX_TEXT_CHARS:
        return text
    return text[:_MAX_TEXT_CHARS] + "\n[... text truncated for analysis ...]"


def _extract_json(content: str) -> dict[str, Any]:
    content = content.strip()
    content = re.sub(r"^```(?:json)?\s*", "", content, flags=re.IGNORECASE)
    content = re.sub(r"\s*```$", "", content)

    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", content, flags=re.DOTALL)
    if not match:
        raise json.JSONDecodeError("No JSON object found", content, 0)

    return json.loads(match.group(0))


def _safe_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []

    result: list[str] = []
    seen: set[str] = set()

    for item in value:
        if isinstance(item, str):
            cleaned = re.sub(r"\s+", " ", item).strip(" ,.;:-")
            key = cleaned.lower()
            if cleaned and key not in seen:
                seen.add(key)
                result.append(cleaned)

    return result


def _normalize_phone(phone: str) -> str:
    phone = phone.strip()
    digits = re.sub(r"\D", "", phone)

    if not digits:
        return phone

    if len(digits) == 10:
        return digits

    if len(digits) == 12 and digits.startswith("91"):
        return f"+{digits}"

    if phone.startswith("+"):
        return f"+{digits}"

    return digits


def _normalize_phones(values: list[str]) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()

    for value in values:
        digits = re.sub(r"\D", "", value)
        if not (10 <= len(digits) <= 13):
            continue

        normalized = _normalize_phone(value)
        key = normalized.lower()
        if normalized and key not in seen:
            seen.add(key)
            cleaned.append(normalized)

    return cleaned


def _has_ongoing_education(document_data: dict[str, Any]) -> bool:
    education = document_data.get("education", [])
    if not isinstance(education, list):
        return False

    for item in education:
        text = ""
        if isinstance(item, dict):
            text = " ".join(str(v) for v in item.values() if v)
        elif isinstance(item, str):
            text = item

        match = re.search(r"(20\d{2})\s*[-–—]\s*(20\d{2})", text)
        if match:
            start_year = int(match.group(1))
            end_year = int(match.group(2))
            if end_year >= start_year:
                return True

    return False


def _fix_resume_summary(summary: str, document_type: str, document_data: dict[str, Any]) -> str:
    if document_type != "resume" or not summary:
        return summary

    if _has_ongoing_education(document_data):
        summary = re.sub(r"\bgraduate\b", "student", summary, flags=re.IGNORECASE)
        summary = re.sub(r"\bgraduated\b", "studying", summary, flags=re.IGNORECASE)

    return summary.strip()


def _normalize_response(data: dict[str, Any]) -> dict[str, Any]:
    entities = data.get("entities", {})
    if not isinstance(entities, dict):
        entities = {}

    document_type = str(data.get("documentType", "general")).strip().lower()
    if document_type == "generic":
        document_type = "general"
    if document_type not in _ALLOWED_DOC_TYPES:
        document_type = "general"

    sentiment = str(data.get("sentiment", "neutral")).strip().lower()
    if sentiment not in _ALLOWED_SENTIMENTS:
        sentiment = "neutral"

    document_data = data.get("documentData", {})
    if not isinstance(document_data, dict):
        document_data = {}

    summary = str(data.get("summary", "")).strip()
    summary = _fix_resume_summary(summary, document_type, document_data)
    summary = re.sub(r"\s+", " ", summary).strip()

    return {
        "documentType": document_type,
        "summary": summary,
        "entities": {
            "names": _safe_list(entities.get("names")),
            "organizations": _safe_list(entities.get("organizations")),
            "dates": _safe_list(entities.get("dates")),
            "amounts": _safe_list(entities.get("amounts")),
            "emails": _safe_list(entities.get("emails")),
            "phones": _normalize_phones(_safe_list(entities.get("phones"))),
        },
        "sentiment": sentiment,
        "documentData": document_data,
    }


def _call_openrouter(payload: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
    last_error: Exception | None = None

    for attempt in range(_MAX_RETRIES):
        try:
            with httpx.Client(timeout=_TIMEOUT_SECONDS) as client:
                response = client.post(_OPENROUTER_URL, json=payload, headers=headers)
                response.raise_for_status()
                return response.json()
        except Exception as exc:
            last_error = exc
            logger.warning("OpenRouter attempt %s failed: %s", attempt + 1, exc)

    raise RuntimeError(f"All OpenRouter attempts failed: {last_error}")


def analyze_with_llm(text: str) -> dict[str, Any] | None:
    api_key = getattr(settings, "openrouter_api_key", "").strip() if getattr(settings, "openrouter_api_key", None) else ""
    model = getattr(settings, "openrouter_model", "").strip() if getattr(settings, "openrouter_model", None) else ""
    model = model or "arcee-ai/trinity-mini:free"

    if not text or not text.strip():
        return None

    if not api_key:
        logger.debug("OPENROUTER_API_KEY not set; skipping LLM analysis.")
        return None

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    "Analyze the following extracted document text and return only the required JSON.\n\n"
                    f"{_truncate_text(text)}"
                ),
            },
        ],
        "temperature": 0.1,
        "max_tokens": 1200,
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/ai-document-analysis",
        "X-Title": "AI Document Analysis API",
    }

    try:
        result = _call_openrouter(payload, headers)
        content = result["choices"][0]["message"]["content"]
        parsed = _extract_json(content)
        normalized = _normalize_response(parsed)

        if not normalized["summary"].strip():
            logger.warning("LLM returned empty summary; using fallback instead.")
            return None

        return normalized

    except httpx.HTTPStatusError as exc:
        logger.warning("OpenRouter HTTP error %s: %s", exc.response.status_code, exc.response.text[:300])
    except httpx.RequestError as exc:
        logger.warning("OpenRouter request failed: %s", exc)
    except (json.JSONDecodeError, KeyError, ValueError, TypeError) as exc:
        logger.warning("OpenRouter response parse failed: %s", exc)
    except Exception as exc:
        logger.warning("LLM analysis unexpected error: %s", exc)

    return None
"""
document_classifier.py
----------------------
Generic rule-based document type detection.

Returns one of:
- resume
- incident_report
- invoice
- article
- general

Design goals:
- generic, not sample-specific
- additive signals, not brittle exact matching
- safe priority order
"""

from __future__ import annotations

import re


RESUME_KEYWORDS = {
    "education",
    "skills",
    "experience",
    "projects",
    "achievements",
    "certifications",
    "objective",
    "summary",
    "linkedin",
    "github",
    "portfolio",
    "contact",
    "internship",
    "gpa",
    "cgpa",
    "degree",
    "bachelor",
    "master",
    "university",
    "school",
}

INCIDENT_KEYWORDS = {
    "incident",
    "breach",
    "attack",
    "vulnerability",
    "affected",
    "impact",
    "threat",
    "malware",
    "ransomware",
    "phishing",
    "unauthorized",
    "compromised",
    "security",
    "mitigation",
    "remediation",
    "investigation",
    "cybersecurity",
    "data breach",
    "risk",
    "failure",
    "outage",
    "contamination",
    "hazard",
    "public health",
}

INVOICE_KEYWORDS = {
    "invoice",
    "bill",
    "billing",
    "total",
    "subtotal",
    "amount due",
    "payment",
    "gst",
    "tax",
    "vendor",
    "customer",
    "due date",
    "purchase order",
    "receipt",
    "quantity",
    "unit price",
    "grand total",
    "net amount",
    "payable",
    "invoice number",
    "invoice no",
    "billed to",
    "issued by",
}

ARTICLE_KEYWORDS = {
    "analysis",
    "industry",
    "market",
    "trend",
    "growth",
    "technology",
    "innovation",
    "global",
    "research",
    "study",
    "report",
    "economic",
    "development",
    "experts",
    "institutions",
    "companies",
    "government agencies",
    "sector",
    "investment",
    "applications",
    "opportunities",
    "challenges",
}


def _normalize(text: str) -> str:
    text = text.replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{2,}", "\n", text)
    return text.strip()


def _lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


def _contains_phrase(text_lower: str, phrase: str) -> bool:
    return re.search(rf"\b{re.escape(phrase.lower())}\b", text_lower) is not None


def _keyword_score(text_lower: str, keywords: set[str]) -> int:
    return sum(1 for kw in keywords if _contains_phrase(text_lower, kw))


def _count_upper_headings(lines: list[str]) -> int:
    count = 0
    for line in lines[:30]:
        cleaned = line.strip(":- ").strip()
        if cleaned.isupper() and 1 <= len(cleaned.split()) <= 5:
            count += 1
    return count


def _has_contact_signal(text_lower: str) -> bool:
    return any(
        token in text_lower
        for token in (
            "@",
            "linkedin",
            "github",
            "portfolio",
            "email",
            "phone",
            "contact",
        )
    )


def _has_name_like_first_line(lines: list[str]) -> bool:
    if not lines:
        return False

    first = lines[0].strip()
    words = first.split()

    if not (2 <= len(words) <= 4):
        return False
    if "@" in first:
        return False
    if any(ch.isdigit() for ch in first):
        return False

    cleaned_words = [re.sub(r"[^A-Za-z]", "", word) for word in words]
    if not all(cleaned_words):
        return False

    # ALL CAPS name like TEJASVI UPADHYAY
    if first.isupper():
        return all(word.isalpha() for word in cleaned_words)

    # Title Case name like Nina Lane
    return all(word[:1].isupper() and word[1:].islower() for word in cleaned_words)


def _looks_like_resume(text: str) -> bool:
    text_lower = text.lower()
    lines = _lines(text)

    resume_score = _keyword_score(text_lower, RESUME_KEYWORDS)
    contact_signal = _has_contact_signal(text_lower)
    heading_count = _count_upper_headings(lines)
    first_line_name_like = _has_name_like_first_line(lines)

    section_hits = sum(
        1
        for word in (
            "education",
            "skills",
            "projects",
            "experience",
            "achievements",
            "portfolio",
            "certifications",
        )
        if _contains_phrase(text_lower, word)
    )

    # Avoid classifying short ID-like text as resume
    id_card_signals = sum(
        1
        for token in ("dob", "blood group", "id", "roll no", "enrollment", "branch")
        if _contains_phrase(text_lower, token)
    )

    strong_resume_structure = (
        section_hits >= 2
        and contact_signal
        and (first_line_name_like or heading_count >= 2)
    )

    return (
        id_card_signals <= 2
        and (
            strong_resume_structure
            or (resume_score >= 5 and contact_signal)
        )
    )


def _looks_like_incident_report(text: str) -> bool:
    text_lower = text.lower()
    score = _keyword_score(text_lower, INCIDENT_KEYWORDS)

    strong_phrases = sum(
        1
        for phrase in (
            "data breach",
            "unauthorized access",
            "cybersecurity incident",
            "security researchers",
            "public health",
            "lead contamination",
            "regulatory authorities",
            "affected systems",
            "affected customers",
        )
        if _contains_phrase(text_lower, phrase)
    )

    return score >= 4 or strong_phrases >= 2


def _looks_like_invoice(text: str) -> bool:
    text_lower = text.lower()
    score = _keyword_score(text_lower, INVOICE_KEYWORDS)

    amount_like = bool(
        re.search(r"(₹|\$|€|£|rs\.?|inr)\s?\d[\d,]*(\.\d{1,2})?", text_lower)
    )

    invoice_id_like = bool(
        re.search(
            r"\binvoice\s*(?:no|number|#|id)?\s*[:#\-]?\s*[a-z0-9][a-z0-9\-\/]*\b",
            text_lower,
        )
    )

    party_signal = any(
        phrase in text_lower
        for phrase in ("billed to", "issued by", "vendor", "customer", "bill to")
    )

    total_signal = any(
        phrase in text_lower
        for phrase in ("total", "subtotal", "grand total", "amount due", "net amount")
    )

    return (
        (score >= 3 and amount_like)
        or (invoice_id_like and amount_like)
        or ("invoice" in text_lower and amount_like and (party_signal or total_signal))
    )


def _looks_like_article(text: str) -> bool:
    text_lower = text.lower()
    lines = _lines(text)

    score = _keyword_score(text_lower, ARTICLE_KEYWORDS)
    paragraph_like = len(lines) >= 8
    long_text = len(text) > 900

    structured_form_signals = sum(
        1
        for token in (
            "education",
            "skills",
            "experience",
            "projects",
            "invoice",
            "bill to",
            "notice",
            "roll no",
            "dob",
            "blood group",
        )
        if _contains_phrase(text_lower, token)
    )

    return score >= 3 and structured_form_signals <= 1 and (paragraph_like or long_text)


def detect_document_type(text: str) -> str:
    """
    Detect document type using generic heuristic signals.

    Priority matters:
    1. resume
    2. incident_report
    3. invoice
    4. article
    5. general
    """
    if not text or not text.strip():
        return "general"

    text = _normalize(text)

    if _looks_like_resume(text):
        return "resume"

    if _looks_like_incident_report(text):
        return "incident_report"

    if _looks_like_invoice(text):
        return "invoice"

    if _looks_like_article(text):
        return "article"

    return "general"
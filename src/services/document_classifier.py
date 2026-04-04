"""
document_classifier.py
----------------------
Robust rule-based document type detection.

Returns one of:
- resume
- incident_report
- invoice
- article
- general
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
    "internship",
    "gpa",
    "degree",
    "bachelor",
    "master",
    "portfolio",
    "contact",
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
    "financial institutions",
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
}


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


def _keyword_score(text_lower: str, keywords: set[str]) -> int:
    return sum(1 for kw in keywords if kw in text_lower)


def _count_upper_headings(lines: list[str]) -> int:
    count = 0
    for line in lines[:25]:
        if line.isupper() and 1 <= len(line.split()) <= 4:
            count += 1
    return count


def _has_resume_sections(text_lower: str) -> bool:
    hits = 0
    for word in ("education", "skills", "projects", "experience", "achievements", "portfolio", "contact"):
        if word in text_lower:
            hits += 1
    return hits >= 2


def _looks_like_resume(text: str) -> bool:
    text_lower = text.lower()
    lines = _lines(text)

    first_line_name_like = False
    if lines:
        first = lines[0]
        first_line_name_like = (
            2 <= len(first.split()) <= 4
            and "@" not in first
            and not any(ch.isdigit() for ch in first)
        )

    contact_signals = (
        "linkedin" in text_lower
        or "github" in text_lower
        or "portfolio" in text_lower
        or "email" in text_lower
        or "phone" in text_lower
    )

    strong_sections = _has_resume_sections(text_lower)
    heading_count = _count_upper_headings(lines)

    # Resume should have person/contact/sections structure.
    return (
        (first_line_name_like and contact_signals and strong_sections)
        or (strong_sections and heading_count >= 2 and contact_signals)
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
            "affected institutions",
            "regulatory authorities",
        )
        if phrase in text_lower
    )

    return score >= 3 or strong_phrases >= 2


def _looks_like_invoice(text: str) -> bool:
    text_lower = text.lower()
    score = _keyword_score(text_lower, INVOICE_KEYWORDS)

    amount_like = bool(re.search(r"(₹|\$|€|£)\s?\d", text))
    invoice_id_like = bool(re.search(r"invoice\s*(?:no|number|#|id)?", text_lower))
    party_like = bool(
        any(token in text_lower for token in ("vendor", "customer", "billed to", "issued by", "invoice to"))
    )

    # Keep stricter so incident/article docs do not become invoices.
    return (score >= 3 and (amount_like or invoice_id_like or party_like)) or (invoice_id_like and amount_like)


def _looks_like_article(text: str) -> bool:
    text_lower = text.lower()
    score = _keyword_score(text_lower, ARTICLE_KEYWORDS)

    paragraph_like = len(_lines(text)) >= 8
    long_text = len(text) > 900

    return (score >= 3 and paragraph_like) or (long_text and score >= 2)


def detect_document_type(text: str) -> str:
    """
    Detect document type using robust heuristics.
    Priority matters.
    """
    if not text or not text.strip():
        return "general"

    text = _normalize(text)

    # Priority order:
    # 1. Resume
    # 2. Incident report
    # 3. Invoice
    # 4. Article
    # 5. General
    if _looks_like_resume(text):
        return "resume"

    if _looks_like_incident_report(text):
        return "incident_report"

    if _looks_like_invoice(text):
        return "invoice"

    if _looks_like_article(text):
        return "article"

    return "general"
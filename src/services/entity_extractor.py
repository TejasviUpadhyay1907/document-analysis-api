"""
entity_extractor.py
-------------------
Generic, pattern-based entity extractor.
Designed to stay stable across resumes, articles, notices, invoices, and OCR text.
"""

from __future__ import annotations

import logging
import re
from typing import TypedDict

logger = logging.getLogger(__name__)

_nlp = None
_SPACY_AVAILABLE = False

try:
    import spacy  # type: ignore
    try:
        _nlp = spacy.load("en_core_web_sm")
        _SPACY_AVAILABLE = True
    except OSError:
        logger.warning("spaCy model not found.")
except ImportError:
    logger.warning("spaCy not installed.")


class Entities(TypedDict):
    names: list[str]
    organizations: list[str]
    dates: list[str]
    amounts: list[str]
    emails: list[str]
    phones: list[str]


RE_EMAIL = re.compile(r"\b[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}\b")
RE_PHONE = re.compile(
    r"(?:\+91[-\s]?)?[6-9]\d{9}\b"
    r"|"
    r"(?:\+?1[\s\-]?)?(?:\d{3}[\s\-]?\d{3}[\s\-]?\d{4})\b"
)
RE_YEAR = re.compile(r"\b(?:19\d{2}|20\d{2}|21\d{2})\b")
RE_AMOUNT = re.compile(
    r"(?:₹|\$|€|£)\s?\d[\d,]*(?:\.\d{1,2})?"
    r"|"
    r"\b\d[\d,]*(?:\.\d{1,2})?\s*(?:rupees|inr|usd|eur|gbp)\b",
    re.I,
)
RE_URL = re.compile(r"(https?://\S+|www\.\S+)")
RE_TITLE_NAME = re.compile(r"^[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2}$")
RE_ALLCAPS_NAME = re.compile(r"^[A-Z]+(?:\s+[A-Z]+){1,3}$")

ORG_HINTS = {
    "institute", "school", "college", "university", "agency", "trust",
    "corporation", "corp", "inc", "ltd", "pvt", "bank", "media",
    "department", "office", "committee", "authority"
}

ROLE_WORDS = {
    "engineer", "designer", "developer", "captain", "analyst",
    "director", "manager", "student", "professor", "prof", "dr"
}

HEADING_WORDS = {
    "summary", "report", "analysis", "problem", "statement", "skills",
    "education", "projects", "achievements", "interests", "contact",
    "experience", "portfolio", "tools", "technologies", "challenges"
}


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip(" ,.;:()[]{}|-_")


def _dedupe(items: list[str]) -> list[str]:
    seen = set()
    out: list[str] = []
    for item in items:
        cleaned = _clean(item)
        if cleaned and cleaned.lower() not in seen:
            seen.add(cleaned.lower())
            out.append(cleaned)
    return out


def _normalize_text(text: str) -> str:
    text = re.sub(r"[^\w\s@.+:/&,\-()']", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _looks_like_heading(text: str) -> bool:
    words = [w.lower() for w in text.split()]
    return any(w in HEADING_WORDS for w in words)


def _looks_like_role(text: str) -> bool:
    words = [w.lower() for w in text.split()]
    return any(w in ROLE_WORDS for w in words)


def _is_valid_person_name(text: str) -> bool:
    text = _clean(text)
    if not text:
        return False

    if any(ch.isdigit() for ch in text):
        return False

    if "/" in text or "&" in text or "@" in text:
        return False

    words = text.split()
    if not (2 <= len(words) <= 4):
        return False

    if _looks_like_heading(text):
        return False

    if _looks_like_role(text):
        return False

    if RE_TITLE_NAME.match(text):
        return True

    if RE_ALLCAPS_NAME.match(text):
        return True

    return False


def _is_valid_org(text: str) -> bool:
    text = _clean(text)
    if not text:
        return False

    lowered = text.lower()

    if len(text.split()) > 8:
        return False

    if "@" in text:
        return False

    if _is_valid_person_name(text):
        return False

    if _looks_like_heading(text) and not any(h in lowered for h in ORG_HINTS):
        return False

    if any(h in lowered for h in ORG_HINTS):
        return True

    # allow clean major orgs detected by spaCy or common pattern
    if 1 <= len(text.split()) <= 4 and text[0].isupper() and not _looks_like_role(text):
        return True

    return False


def _extract_emails(text: str) -> list[str]:
    return _dedupe(RE_EMAIL.findall(text))


def _extract_phones(text: str) -> list[str]:
    safe = RE_URL.sub(" ", text)
    phones: list[str] = []

    for match in RE_PHONE.findall(safe):
        digits = re.sub(r"\D", "", match)

        if len(digits) == 12 and digits.startswith("91"):
            phones.append(f"+91-{digits[2:]}")
        elif len(digits) == 10 and digits[0] in "6789":
            phones.append(f"+91-{digits}")
        elif len(digits) == 11 and digits.startswith("1"):
            phones.append(f"+1 {digits[1:4]} {digits[4:7]}-{digits[7:]}")
        elif len(digits) == 10 and digits[0] not in "6789":
            phones.append(f"+1 {digits[:3]} {digits[3:6]}-{digits[6:]}")

    return _dedupe(phones)


def _extract_dates(text: str) -> list[str]:
    return _dedupe(RE_YEAR.findall(text))


def _extract_amounts(text: str) -> list[str]:
    return _dedupe(RE_AMOUNT.findall(text))


def _extract_resume_name(text: str) -> list[str]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for line in lines[:5]:
        line = _clean(line)
        if _is_valid_person_name(line):
            return [line.title() if line.isupper() else line]
    return []


def _fallback_names(text: str) -> list[str]:
    resume_name = _extract_resume_name(text)
    if resume_name:
        return resume_name

    names: list[str] = []
    lines = [line.strip() for line in text.splitlines() if line.strip()]

    for line in lines[:20]:
        line = _clean(line)
        if _is_valid_person_name(line):
            names.append(line.title() if line.isupper() else line)

    return _dedupe(names)[:6]


def _fallback_orgs(text: str) -> list[str]:
    orgs: list[str] = []
    lines = [line.strip() for line in text.splitlines() if line.strip()]

    for line in lines[:50]:
        line = _clean(line)
        if _is_valid_org(line):
            orgs.append(line)

    return _dedupe(orgs)[:10]


def _extract_spacy(text: str):
    if not _SPACY_AVAILABLE or _nlp is None:
        return _fallback_names(text), _fallback_orgs(text)

    try:
        doc = _nlp(text[:100000])
        names: list[str] = []
        orgs: list[str] = []

        for ent in doc.ents:
            value = _clean(ent.text)

            if ent.label_ == "PERSON" and _is_valid_person_name(value):
                names.append(value.title() if value.isupper() else value)

            elif ent.label_ == "ORG" and _is_valid_org(value):
                orgs.append(value)

        for item in _fallback_names(text):
            if item not in names:
                names.append(item)

        for item in _fallback_orgs(text):
            if item not in orgs:
                orgs.append(item)

        return _dedupe(names), _dedupe(orgs)

    except Exception:
        return _fallback_names(text), _fallback_orgs(text)


def extract_entities(text: str) -> Entities:
    try:
        normalized_text = _normalize_text(text)

        emails = _extract_emails(normalized_text)
        phones = _extract_phones(normalized_text)
        dates = _extract_dates(normalized_text)
        amounts = _extract_amounts(normalized_text)

        names, orgs = _extract_spacy(normalized_text)

        org_lower = {o.lower() for o in orgs}
        names = [n for n in names if n.lower() not in org_lower]

        return {
            "names": names,
            "organizations": orgs,
            "dates": dates,
            "amounts": amounts,
            "emails": emails,
            "phones": phones,
        }

    except Exception as e:
        logger.error(f"Entity extraction failed: {e}")
        return {
            "names": [],
            "organizations": [],
            "dates": [],
            "amounts": [],
            "emails": [],
            "phones": [],
        }
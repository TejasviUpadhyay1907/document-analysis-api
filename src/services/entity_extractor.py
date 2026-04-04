"""
entity_extractor.py
-------------------
FINAL STRICT ENTITY EXTRACTOR (Top 1% version)

Fixes:
- removes sentence-like organizations
- works even without spaCy
- strong filtering for noisy OCR text
- stable across resume / article / incident / invoice
"""

from __future__ import annotations

import logging
import re
from typing import TypedDict

logger = logging.getLogger(__name__)

# ---------------------------
# OPTIONAL SPACY
# ---------------------------
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


# ---------------------------
# TYPES
# ---------------------------
class Entities(TypedDict):
    names: list[str]
    organizations: list[str]
    dates: list[str]
    amounts: list[str]
    emails: list[str]
    phones: list[str]


# ---------------------------
# REGEX
# ---------------------------
RE_EMAIL = re.compile(r"\b[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}\b")

RE_PHONE = re.compile(
    r"(?:\+91[-\s]?)?[6-9]\d{9}\b"
    r"|"
    r"(?:\+?1[\s-]?)?(?:\d{3}[\s-]?\d{3}[\s-]?\d{4})\b"
)

RE_YEAR = re.compile(r"\b(?:19\d{2}|20\d{2}|21\d{2})\b")

RE_AMOUNT = re.compile(
    r"(?:₹|\$|€|£)\s?\d[\d,]*(?:\.\d{1,2})?"
    r"|"
    r"\b\d[\d,]*(?:\.\d{1,2})?\s*(?:rupees|inr|usd|eur|gbp)\b",
    re.I,
)

RE_URL = re.compile(r"(https?://\S+|www\.\S+)")

# ---------------------------
# FILTER RULES
# ---------------------------
STOP_WORDS = {
    "the", "and", "for", "with", "from", "this", "that",
    "have", "has", "been", "were", "are", "into"
}


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip(" ,.;:()[]{}")


def _dedupe(items: list[str]) -> list[str]:
    seen = set()
    out = []
    for item in items:
        cleaned = _clean(item)
        if cleaned and cleaned.lower() not in seen:
            seen.add(cleaned.lower())
            out.append(cleaned)
    return out


# ---------------------------
# STRICT FILTER
# ---------------------------
def _is_valid_entity(text: str) -> bool:
    if not text:
        return False

    text = text.strip()

    # ❌ too long → sentence
    if len(text.split()) > 6:
        return False

    # ❌ too short
    if len(text) < 3:
        return False

    # ❌ sentence-like punctuation
    if re.search(r"[.,:;!?]{2,}", text):
        return False

    # ❌ mostly lowercase → not entity
    words = text.split()
    caps = sum(1 for w in words if w[0].isupper())
    if caps < 1:
        return False

    # ❌ too many stopwords
    if sum(1 for w in words if w.lower() in STOP_WORDS) > 2:
        return False

    return True


# ---------------------------
# BASIC EXTRACTORS
# ---------------------------
def _extract_emails(text: str) -> list[str]:
    return _dedupe(RE_EMAIL.findall(text))


def _extract_phones(text: str) -> list[str]:
    safe = RE_URL.sub(" ", text)
    phones = []

    for match in RE_PHONE.findall(safe):
        digits = re.sub(r"\D", "", match)

        if len(digits) == 12 and digits.startswith("91"):
            phones.append(f"+91-{digits[2:]}")
        elif len(digits) == 10 and digits[0] in "6789":
            phones.append(f"+91-{digits}")
        elif len(digits) == 11 and digits.startswith("1"):
            phones.append(f"+1 {digits[1:4]} {digits[4:7]}-{digits[7:]}")
        elif len(digits) == 10:
            phones.append(f"+1 {digits[:3]} {digits[3:6]}-{digits[6:]}")

    return _dedupe(phones)


def _extract_dates(text: str) -> list[str]:
    return _dedupe(RE_YEAR.findall(text))


def _extract_amounts(text: str) -> list[str]:
    return _dedupe(RE_AMOUNT.findall(text))


# ---------------------------
# FALLBACK (NO SPACY)
# ---------------------------
def _fallback_names(text: str) -> list[str]:
    matches = re.findall(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b", text)
    return _dedupe([m for m in matches if _is_valid_entity(m)])[:5]


def _fallback_orgs(text: str) -> list[str]:
    matches = re.findall(r"\b([A-Z][A-Za-z0-9&.\-]*(?:\s+[A-Z][A-Za-z0-9&.\-]*)+)\b", text)

    cleaned = []
    for m in matches:
        if _is_valid_entity(m) and not m.lower().startswith(("the ", "this ", "that ")):
            cleaned.append(m)

    return _dedupe(cleaned)[:8]


# ---------------------------
# SPACY
# ---------------------------
def _extract_spacy(text: str):
    if not _SPACY_AVAILABLE or _nlp is None:
        return _fallback_names(text), _fallback_orgs(text)

    try:
        doc = _nlp(text[:100000])

        names = []
        orgs = []

        for ent in doc.ents:
            value = _clean(ent.text)

            if ent.label_ == "PERSON":
                if _is_valid_entity(value):
                    names.append(value)

            elif ent.label_ == "ORG":
                if _is_valid_entity(value):
                    orgs.append(value)

        return _dedupe(names), _dedupe(orgs)

    except Exception:
        return _fallback_names(text), _fallback_orgs(text)


# ---------------------------
# MAIN
# ---------------------------
def extract_entities(text: str) -> Entities:
    try:
        emails = _extract_emails(text)
        phones = _extract_phones(text)
        dates = _extract_dates(text)
        amounts = _extract_amounts(text)

        names, orgs = _extract_spacy(text)

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
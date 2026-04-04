"""
incident_parser.py
------------------
Structured parser for cybersecurity / incident report documents.

Goals:
- detect likely incident type
- identify affected entities
- extract likely cause / impact / recommendations
- work on paragraph-heavy reports and OCR text
- remain deterministic and offline
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

INCIDENT_TYPES = [
    "data breach",
    "ransomware",
    "phishing",
    "ddos",
    "malware",
    "unauthorized access",
    "insider threat",
    "sql injection",
    "zero-day",
    "credential theft",
    "supply chain attack",
]

CAUSE_KEYWORDS = [
    "caused by",
    "due to",
    "root cause",
    "resulted from",
    "exploited",
    "through a vulnerability",
    "through vulnerability",
    "triggered by",
]

IMPACT_KEYWORDS = [
    "affected",
    "compromised",
    "exposed",
    "disrupted",
    "lost",
    "leaked",
    "impact",
    "breach exposed",
    "data exposed",
]

RECOMMENDATION_KEYWORDS = [
    "recommend",
    "should",
    "must",
    "advised",
    "mitigate",
    "patch",
    "update",
    "implement",
    "improve",
    "strengthen",
]

ENTITY_KEYWORDS = [
    "bank",
    "banks",
    "institution",
    "institutions",
    "provider",
    "providers",
    "company",
    "companies",
    "platform",
    "platforms",
    "service",
    "services",
    "agency",
    "agencies",
]

MAX_ITEMS = 5
MAX_SENTENCE_LEN = 280


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _dedupe(items: list[str]) -> list[str]:
    seen = set()
    out = []
    for item in items:
        cleaned = _normalize(item).strip(" ,.;:")
        if cleaned and cleaned.lower() not in seen:
            seen.add(cleaned.lower())
            out.append(cleaned)
    return out


def _split_sentences(text: str) -> list[str]:
    """
    Split text into readable sentence-like chunks.
    """
    raw = re.split(r"(?<=[.!?])\s+", text)
    cleaned = []

    for sentence in raw:
        s = _normalize(sentence)
        if not s:
            continue
        if len(s) > MAX_SENTENCE_LEN:
            s = s[:MAX_SENTENCE_LEN].rsplit(" ", 1)[0] + "..."
        cleaned.append(s)

    return cleaned


def _detect_incident_type(text_lower: str) -> str:
    for incident_type in INCIDENT_TYPES:
        if incident_type in text_lower:
            return incident_type.title()
    return "Security Incident"


def _extract_matching_sentences(sentences: list[str], keywords: list[str]) -> list[str]:
    matches = []
    for sentence in sentences:
        sentence_lower = sentence.lower()
        if any(keyword in sentence_lower for keyword in keywords):
            matches.append(sentence)
    return _dedupe(matches)[:MAX_ITEMS]


def _extract_affected_entities(text: str, sentences: list[str]) -> list[str]:
    """
    Try multiple heuristics:
    1. Capitalized entities after words like affected/targeted
    2. Noun phrases that include common organization/entity words
    """
    found: list[str] = []

    # Heuristic 1: direct phrases after affected/targeted/etc.
    pattern = re.compile(
        r"(?:affected|compromised|targeted|impacted)\s+"
        r"([A-Z][A-Za-z0-9&,\- ]{3,60})"
    )
    for match in pattern.findall(text):
        candidate = _normalize(match).rstrip(",")
        found.append(candidate)

    # Heuristic 2: look for noun-like entity phrases in matching sentences
    for sentence in sentences:
        low = sentence.lower()
        if any(word in low for word in ("affected", "targeted", "compromised", "impacted")):
            for keyword in ENTITY_KEYWORDS:
                if keyword in low:
                    found.append(sentence)

    cleaned = []
    for item in _dedupe(found):
        # Remove overly long noisy lines
        if len(item.split()) > 12:
            continue
        cleaned.append(item)

    return cleaned[:MAX_ITEMS]


def _extract_cause(sentences: list[str]) -> list[str]:
    return _extract_matching_sentences(sentences, CAUSE_KEYWORDS)


def _extract_impact(sentences: list[str]) -> list[str]:
    return _extract_matching_sentences(sentences, IMPACT_KEYWORDS)


def _extract_recommendations(sentences: list[str]) -> list[str]:
    return _extract_matching_sentences(sentences, RECOMMENDATION_KEYWORDS)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_incident(text: str) -> dict:
    """
    Parse cybersecurity / incident report text into structured documentData.
    """
    try:
        cleaned_text = _normalize(text)
        text_lower = cleaned_text.lower()
        sentences = _split_sentences(cleaned_text)

        return {
            "incident_type": _detect_incident_type(text_lower),
            "affected_entities": _extract_affected_entities(cleaned_text, sentences),
            "cause": _extract_cause(sentences),
            "impact": _extract_impact(sentences),
            "recommendations": _extract_recommendations(sentences),
        }

    except Exception as exc:
        logger.warning("incident_parser failed: %s", exc)
        return {}
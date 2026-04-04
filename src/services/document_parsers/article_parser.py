"""
article_parser.py
-----------------
Structured parser for article / report / analysis text.

Goals:
- extract a clean topic/title
- extract 3-5 strong key points
- work on articles, industry reports, analytical writeups
- stay deterministic and offline
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

TOPIC_STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "in", "on", "at",
    "to", "for", "of", "with", "by", "from", "is", "are", "was",
    "were", "be", "been", "being", "as", "that", "this", "these",
}

SIGNAL_KEYWORDS = [
    "key", "important", "significant", "major", "critical",
    "highlight", "finding", "findings", "result", "results",
    "conclude", "shows", "show", "reveals", "reveal",
    "indicates", "indicate", "report", "according",
    "growth", "impact", "trend", "market", "technology",
    "industry", "analysis", "research",
]

MAX_KEY_POINTS = 5
MIN_SENTENCE_LEN = 35
MAX_SENTENCE_LEN = 260


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _dedupe(items: list[str]) -> list[str]:
    seen = set()
    output = []
    for item in items:
        cleaned = _normalize(item).strip(" ,.;:")
        if cleaned and cleaned.lower() not in seen:
            seen.add(cleaned.lower())
            output.append(cleaned)
    return output


def _extract_lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


def _split_sentences(text: str) -> list[str]:
    raw = re.split(r"(?<=[.!?])\s+", text)
    sentences = []

    for sentence in raw:
        cleaned = _normalize(sentence)
        if len(cleaned) < MIN_SENTENCE_LEN:
            continue
        if len(cleaned) > MAX_SENTENCE_LEN:
            cleaned = cleaned[:MAX_SENTENCE_LEN].rsplit(" ", 1)[0] + "..."
        sentences.append(cleaned)

    return sentences


# ---------------------------------------------------------------------------
# Topic extraction
# ---------------------------------------------------------------------------

def _looks_like_title(line: str) -> bool:
    """
    A strong title is usually:
    - near the top
    - not too short / long
    - title-like, not just a sentence fragment
    """
    text = _normalize(line)
    if not text:
        return False

    if len(text) < 8 or len(text) > 120:
        return False

    # Prefer lines without sentence-ending punctuation.
    if text.endswith((".", "?", "!")):
        return False

    # Avoid lines that are too numeric-heavy.
    digit_ratio = sum(ch.isdigit() for ch in text) / max(len(text), 1)
    if digit_ratio > 0.2:
        return False

    return True


def _extract_topic(text: str) -> str:
    lines = _extract_lines(text)

    # Prefer first title-like line in top few lines
    for line in lines[:6]:
        if _looks_like_title(line):
            return line

    # Fallback: first 10 meaningful words
    words = []
    for word in re.split(r"\s+", text.strip()):
        clean = word.strip(" ,.;:()[]{}").lower()
        if not clean or clean in TOPIC_STOPWORDS:
            continue
        words.append(word.strip(" ,.;:()[]{}"))
        if len(words) >= 10:
            break

    return " ".join(words)


# ---------------------------------------------------------------------------
# Key point extraction
# ---------------------------------------------------------------------------

def _sentence_score(sentence: str) -> int:
    """
    Score sentence importance using signal keywords and structure.
    """
    low = sentence.lower()
    score = 0

    for keyword in SIGNAL_KEYWORDS:
        if keyword in low:
            score += 2

    # Sentences mentioning entities or quantitative claims often matter more.
    if re.search(r"\b\d+(?:\.\d+)?%?\b", sentence):
        score += 1

    if any(name in low for name in ("company", "companies", "government", "industry", "market")):
        score += 1

    return score


def _extract_key_points(text: str) -> list[str]:
    sentences = _split_sentences(text)
    if not sentences:
        return []

    scored = [(sentence, _sentence_score(sentence), idx) for idx, sentence in enumerate(sentences)]

    # Sort by score desc, then original order asc
    ranked = sorted(scored, key=lambda item: (-item[1], item[2]))

    selected = []
    for sentence, score, _idx in ranked:
        # Prefer stronger sentences first, but allow fallback later
        if score > 0 or len(selected) < 3:
            selected.append(sentence)
        if len(selected) >= MAX_KEY_POINTS:
            break

    # Preserve original reading order
    selected_set = set(selected)
    ordered = [sentence for sentence in sentences if sentence in selected_set]

    return _dedupe(ordered)[:MAX_KEY_POINTS]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_article(text: str) -> dict:
    """
    Parse article/report text into structured documentData.
    """
    try:
        normalized = _normalize(text)

        return {
            "topic": _extract_topic(normalized),
            "key_points": _extract_key_points(normalized),
        }

    except Exception as exc:
        logger.warning("article_parser failed: %s", exc)
        return {}
"""
summarizer.py
-------------
FINAL SMART SUMMARIZER (Top 1% Hackathon Version)

Supports:
- resume
- article
- incident_report
- invoice
- generic fallback
"""

from __future__ import annotations
import logging
import re

logger = logging.getLogger(__name__)

MAX_CHARS = 320

SECTION_HEADERS = {
    "education", "skills", "projects", "achievements", "interests",
    "experience", "summary", "objective", "certifications",
    "contact", "portfolio"
}

COMMON_SKILLS = {
    "python", "java", "c++", "c", "sql", "javascript", "typescript",
    "react", "node", "fastapi", "django", "flask", "html", "css",
    "git", "github", "machine learning", "deep learning", "ai",
    "data analysis", "pandas", "numpy", "matplotlib", "photoshop",
    "figma", "design", "aws", "docker", "mongodb", "mysql"
}


# ----------------------------
# CLEAN
# ----------------------------
def _clean(text: str) -> str:
    text = text.replace("\r", "\n")
    text = re.sub(r"\n{2,}", "\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def _truncate(text: str) -> str:
    text = text.strip()
    if len(text) <= MAX_CHARS:
        return text
    cut = text[:MAX_CHARS]
    last_space = cut.rfind(" ")
    if last_space > 0:
        cut = cut[:last_space]
    return cut.rstrip(" ,.;:") + "..."


def _split_sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]


def _looks_like_heading(line: str) -> bool:
    return line.strip().lower() in SECTION_HEADERS


def _dedupe_words(text: str) -> str:
    words = text.split()
    seen = set()
    result = []

    for w in words:
        lw = w.lower()
        if lw not in seen:
            seen.add(lw)
            result.append(w)

    return " ".join(result)


# ----------------------------
# RESUME SUMMARY
# ----------------------------
def _resume_summary(text: str) -> str | None:
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    if len(lines) < 3:
        return None

    name = lines[0]

    role = ""
    education = ""
    skills_found = []

    for i, line in enumerate(lines[:30]):
        low = line.lower()

        # Role detection
        if not role:
            if (
                1 <= i <= 4
                and len(line.split()) <= 8
                and "@" not in line
                and not re.search(r"\d{3,}", line)
                and not _looks_like_heading(line)
                and not any(k in low for k in ["college", "school", "university", "institute"])
            ):
                role = line

        # Education detection
        if not education and any(k in low for k in ["university", "college", "school", "institute"]):
            education = line

        # Skill detection (strict)
        for skill in COMMON_SKILLS:
            if re.search(rf"\b{re.escape(skill)}\b", low):
                if skill not in skills_found:
                    skills_found.append(skill)

    parts = [name]

    if role:
        parts.append(f"is a {role.lower()}")

    if education:
        parts.append(f"associated with {education}")

    if skills_found:
        parts.append(f"with skills in {', '.join(skills_found[:5])}")

    if len(parts) == 1:
        return None

    summary = " ".join(parts)
    summary = _dedupe_words(summary)

    if not summary.endswith("."):
        summary += "."

    return _truncate(summary)


# ----------------------------
# INCIDENT SUMMARY
# ----------------------------
def _incident_summary(text: str) -> str:
    sentences = _split_sentences(text)

    priority = [
        "breach", "attack", "incident", "compromised",
        "malware", "ransomware", "phishing", "leak",
        "unauthorized access", "vulnerability"
    ]

    key = [s for s in sentences if any(word in s.lower() for word in priority)]

    if not key:
        key = sentences[:2]

    return _truncate(" ".join(key[:2]))


# ----------------------------
# ARTICLE SUMMARY
# ----------------------------
def _article_summary(text: str) -> str:
    sentences = _split_sentences(text)

    score_words = [
        "ai", "technology", "industry", "research", "analysis",
        "platform", "system", "model", "innovation", "study",
        "results", "development", "market", "solution"
    ]

    scored = []

    for s in sentences:
        low = s.lower()
        score = sum(1 for w in score_words if w in low)

        if 8 <= len(s.split()) <= 40:
            score += 1

        if len(s.split()) > 40:
            score -= 2  # penalty

        scored.append((score, s))

    scored.sort(key=lambda x: x[0], reverse=True)

    best = [s for score, s in scored[:2] if s]

    if not best:
        best = sentences[:2]

    return _truncate(" ".join(best))


# ----------------------------
# INVOICE SUMMARY
# ----------------------------
def _invoice_summary(text: str) -> str:
    invoice_no = ""
    amount = ""
    date = ""
    vendor = ""

    lines = [l.strip() for l in text.splitlines() if l.strip()]

    for line in lines[:25]:
        low = line.lower()

        if not invoice_no:
            m = re.search(r"(invoice\s*(no|number)?[:#]?\s*[a-zA-Z0-9\-\/]+)", line, re.I)
            if m:
                invoice_no = m.group(1)

        if not amount:
            m = re.search(r"((rs\.?|inr|\$|€)\s?\d[\d,]*(\.\d{1,2})?)", line, re.I)
            if m:
                amount = m.group(1)

        if not date:
            m = re.search(r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}-\d{2}-\d{2})\b", line)
            if m:
                date = m.group(1)

        if not vendor:
            if (
                len(line.split()) <= 6
                and line[0].isupper()
                and not any(x in low for x in ["invoice", "amount", "date", "bill"])
                and "@" not in line
            ):
                vendor = line

    parts = ["Invoice summary"]

    if invoice_no:
        parts.append(f"for {invoice_no}")
    if vendor:
        parts.append(f"from {vendor}")
    if amount:
        parts.append(f"with amount {amount}")
    if date:
        parts.append(f"dated {date}")

    return _truncate(" ".join(parts) + ".")


# ----------------------------
# GENERIC SUMMARY
# ----------------------------
def _generic_summary(text: str) -> str:
    lines = [l.strip() for l in text.splitlines() if l.strip()]

    filtered = [
        l for l in lines
        if not _looks_like_heading(l)
        and len(l) > 2
    ]

    excerpt = " ".join(filtered[:4])

    if not excerpt:
        excerpt = "Content available but could not be summarized clearly."

    return _truncate(excerpt)


# ----------------------------
# MAIN (IMPORTANT CHANGE)
# ----------------------------
def generate_summary(text: str, doc_type: str = "general") -> str:
    if not text.strip():
        return "No content available."

    try:
        text = _clean(text)

        if doc_type == "resume":
            return _resume_summary(text) or _generic_summary(text)

        if doc_type == "invoice":
            return _invoice_summary(text)

        if doc_type == "incident_report":
            return _incident_summary(text)

        if doc_type == "article":
            return _article_summary(text)

        return _generic_summary(text)

    except Exception as e:
        logger.warning(f"Summary error: {e}")
        return _truncate(text)
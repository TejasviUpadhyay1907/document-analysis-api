import re


SECTION_WORDS = {
    "education",
    "skills",
    "projects",
    "project",
    "experience",
    "achievements",
    "awards",
    "certifications",
    "interests",
    "intrests",
    "portfolio",
    "contact",
    "summary",
    "objective",
    "employment",
    "internship",
    "work experience",
}


# ----------------------------
# NORMALIZATION
# ----------------------------
def _normalize_quotes(text: str) -> str:
    return (
        text.replace("’", "'")
        .replace("‘", "'")
        .replace("“", '"')
        .replace("”", '"')
        .replace("–", "—")
    )


def _fix_common_ocr_words(text: str) -> str:
    replacements = {
        "Web Desigh": "Web Design",
        "INTRESTS": "INTERESTS",
        "oO) Interests": "Interests",
        "fo banners": "to banners",
        "eco friendly": "eco-friendly",
        "real time": "real-time",
        "third party": "third-party",
        "large scale": "large-scale",
    }

    for wrong, right in replacements.items():
        text = text.replace(wrong, right)

    return text


# ----------------------------
# LINE CLEANING
# ----------------------------
def _strip_leading_noise(line: str) -> str:
    line = re.sub(r"^[^A-Za-z0-9]+", "", line).strip()
    line = re.sub(r"^[A-Za-z]{0,2}[)\]}]+\s*", "", line).strip()
    return line


def _strip_trailing_noise(line: str) -> str:
    line = re.sub(r"\s*[—–-]+(?:\s*[_=~|@()•●■□<>-]*)?$", "", line).strip()
    line = re.sub(r"\s*[_=~|@()•●■□<>-]+$", "", line).strip()
    return line


def _is_symbol_only(line: str) -> bool:
    return re.fullmatch(r"[\W_]+", line or "") is not None


def _looks_like_heading(line: str) -> bool:
    low = line.lower().strip()
    return low in SECTION_WORDS or (line.isupper() and 1 <= len(line.split()) <= 4)


def _is_contact_line(line: str) -> bool:
    low = line.lower()
    digits = re.sub(r"\D", "", line)

    return (
        "@" in line
        or "linkedin" in low
        or "github" in low
        or "www." in low
        or "email" in low
        or "phone" in low
        or "website" in low
        or len(digits) >= 10
    )


# ----------------------------
# MERGING LOGIC (CRITICAL FIX)
# ----------------------------
def _should_merge_with_next(line: str) -> bool:
    if not line:
        return False

    if _looks_like_heading(line):
        return False

    if _is_contact_line(line):
        return False

    # prevent merging structured lines (resume safe)
    if ":" in line:
        return False

    if line.endswith((".", "!", "?", ":")):
        return False

    # allow merge only for real sentence fragments
    return len(line.split()) >= 4


def _is_sentence_continuation(line: str) -> bool:
    if not line:
        return False

    if _looks_like_heading(line):
        return False

    if _is_contact_line(line):
        return False

    if line[0].islower():
        return True

    # prevent merging role/company lines in resumes
    if "|" in line:
        return False

    return len(line.split()) >= 5


# ----------------------------
# MAIN CLEAN FUNCTION
# ----------------------------
def clean_text(text: str) -> str:
    """
    FINAL TEXT CLEANER (Stable + Generic)

    Fixes:
    - prevents resume structure break
    - avoids over-merging lines
    - improves OCR cleanup
    - keeps classification stable
    """

    if not text or not isinstance(text, str):
        return ""

    text = text.replace("\t", " ").replace("\r", "\n")
    text = _normalize_quotes(text)
    text = _fix_common_ocr_words(text)

    raw_lines = text.split("\n")
    cleaned_lines: list[str] = []

    for raw_line in raw_lines:
        line = raw_line.strip()
        if not line:
            continue

        line = _strip_leading_noise(line)
        line = _strip_trailing_noise(line)

        line = re.sub(r"[ ]{2,}", " ", line).strip()

        if not line or _is_symbol_only(line):
            continue

        cleaned_lines.append(line)

    # remove duplicates
    deduped = []
    prev = None
    for line in cleaned_lines:
        if line != prev:
            deduped.append(line)
        prev = line

    # controlled merging
    merged = []
    i = 0

    while i < len(deduped):
        current = deduped[i]

        if i + 1 < len(deduped):
            nxt = deduped[i + 1]

            if _should_merge_with_next(current) and _is_sentence_continuation(nxt):
                combined = f"{current} {nxt}"
                combined = re.sub(r"\s+", " ", combined).strip()
                merged.append(combined)
                i += 2
                continue

        merged.append(current)
        i += 1

    # final cleanup
    final = []
    prev = None
    for line in merged:
        line = re.sub(r"[ ]{2,}", " ", line).strip()
        if line and line != prev:
            final.append(line)
        prev = line

    return "\n".join(final).strip()
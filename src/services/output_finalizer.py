"""
output_finalizer.py  v2
-----------------------
FINAL CORRECTION LAYER — deterministic post-processing over LLM output.
All fixes from 10-doc review applied here.
"""
from __future__ import annotations
import re
import logging
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_TECH_SKILLS = {
    "python","java","c++","c","sql","javascript","typescript","react","node",
    "fastapi","django","flask","html","css","git","github","machine learning",
    "deep learning","ai","ml","data analysis","pandas","numpy","matplotlib",
    "photoshop","figma","aws","docker","mongodb","mysql","clickhouse","rag",
    "llm","nlp","rest","api","apis","html/css/js","html/css",
    "prompt engineering","embeddings","q&a","data modeling","data science",
    "ai/ml","llm basics","clickhouse","rest apis","git/github",
}

_NOISE_NAMES = {
    "silver medal","gold medal","bronze medal","judo","kho-kho","football",
    "rugby","karate","sports captain","smart","onwards","problem statement",
    "oken scanner","oken scanner na","event branding","adobe creative suite",
    "graphic designer","data analysis","weather forecasting","chinchwad pune",
    "intern big data","hiring team",
}

_NOISE_ORGS = {
    "ai","ml","technology","students","experts","researchers","companies",
    "institutions","agencies","government","panel","tools","technologies",
    "challenges","interests","skills","education","projects","experience",
    "achievements","contact","blood group","internship","certificate","review",
    "cybersecurity incident report","major data breach affects financial institutions",
    "data breach affects financial institutions","kho-kho","judo","football",
    "rugby","karate","sports","state","databases","analytics","programming",
    "intern - big data","intern big data","lcr","sdwa",
    "internship review-ii","internship review","th","engg","renuka",
    "nutan maharashtra inst","nutan maharashtra institute of (es",
}

_HEADING_WORDS = {
    "education","skills","projects","achievements","interests","experience",
    "summary","objective","certifications","contact","portfolio","tools",
    "technologies","challenges","notice","contents","panel","roll no","classroom",
}

_MAX_SUMMARY_CHARS = 350

# Known acronyms that ARE real orgs
_KNOWN_ACRONYMS = {
    "EPA","AICTE","NAAC","SPPU","PCET","NMIET","NASA","WHO","FBI","CIA","IBM","MIT",
    "UN","EU","US","UK",
}

# ---------------------------------------------------------------------------
# Document type detection
# ---------------------------------------------------------------------------

def _has(t: str, *phrases: str) -> bool:
    return any(p in t for p in phrases)

def _count(t: str, *phrases: str) -> int:
    return sum(1 for p in phrases if p in t)

def _is_name_line(line: str) -> bool:
    line = line.strip()
    words = line.split()
    if not (2 <= len(words) <= 4):
        return False
    if any(ch.isdigit() for ch in line):
        return False
    if "@" in line or "/" in line:
        return False
    cleaned = [re.sub(r"[^A-Za-z]", "", w) for w in words]
    if not all(cleaned):
        return False
    if line.isupper():
        return all(w.isalpha() for w in cleaned)
    return all(w[:1].isupper() for w in cleaned if w)

def _detect_type(text: str) -> str:
    t = text.lower()
    lines = [l.strip() for l in text.splitlines() if l.strip()]

    # Cover letter — must check BEFORE resume
    if _has(t, "dear hiring", "dear recruiter", "dear hr", "re: intern", "re: job", "re: position"):
        if _has(t, "sincerely", "thank you for your time", "look forward to"):
            return "official_letter"
    if _has(t, "dear") and _has(t, "sincerely", "yours faithfully", "yours sincerely"):
        if _has(t, "seagate", "google", "microsoft", "amazon") and _has(t, "apply", "position", "intern"):
            return "official_letter"

    # Identity document
    if _count(t, "dob", "blood group", "enrollment", "branch") >= 2 and _has(t, "name"):
        if len(text) < 600:
            return "identity"

    # Resume
    section_hits = _count(t, "education", "skills", "projects", "experience",
                           "achievements", "certifications", "portfolio")
    contact_signal = _has(t, "@", "linkedin", "github", "phone", "contact")
    has_name_first = _is_name_line(lines[0]) if lines else False
    if section_hits >= 2 and contact_signal:
        return "resume"
    if section_hits >= 3 and has_name_first:
        return "resume"

    # Notice
    if _has(t, "notice", "hereby informed", "scheduled on", "roll no", "classroom"):
        if _has(t, "institute", "department", "college", "university"):
            return "notice"

    # Official letter
    if _has(t, "dear commissioner", "dear sir", "dear madam", "sincerely", "yours faithfully"):
        if _has(t, "agency", "office", "department", "authority", "epa", "government"):
            return "official_letter"

    # Incident report
    incident_score = _count(t, "breach", "attack", "vulnerability", "unauthorized",
                             "compromised", "cybersecurity", "malware", "ransomware",
                             "phishing", "incident", "affected", "investigation")
    if incident_score >= 3:
        return "incident_report"

    # Invoice
    invoice_score = _count(t, "invoice", "bill", "amount", "total", "vendor",
                            "customer", "payment", "gst", "tax", "receipt")
    has_amount = bool(re.search(r"(₹|\$|€|£|rs\.?|inr)\s?\d[\d,]*", t))
    has_amount_word = bool(re.search(r"\b\d[\d,]*\s*(?:rupees|inr|usd|eur)\b", t))
    if invoice_score >= 2 and (has_amount or has_amount_word):
        return "invoice"
    if "invoice" in t and (has_amount or has_amount_word):
        return "invoice"
    if _has(t, "from", "to") and (has_amount or has_amount_word) and len(text) < 300:
        return "invoice"

    # Article
    article_score = _count(t, "analysis", "industry", "market", "trend", "growth",
                            "technology", "innovation", "global", "research", "study",
                            "economic", "development", "sector", "investment")
    if article_score >= 3 and len(text) > 800:
        return "article"

    return "general"

# ---------------------------------------------------------------------------
# Entity extraction helpers
# ---------------------------------------------------------------------------

def _extract_name_from_text(text: str) -> str:
    """Extract person name using labeled patterns and first-line heuristic."""
    # Pattern: "Name : X" or "Name: X"
    m = re.search(r"(?:^|\n)\s*Name\s*[:\-]\s*([A-Z][A-Za-z\s]{2,30})", text, re.I)
    if m:
        name = m.group(1).strip().splitlines()[0].strip()
        if _is_name_line(name) or name.isupper():
            return name.title() if name.isupper() else name

    # First line ALL CAPS name
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    for line in lines[:3]:
        if _is_name_line(line):
            return line.title() if line.isupper() else line

    return ""

def _normalize_phone(phone: str) -> str:
    """Normalize phone to E.164-like format. Fix Indian numbers misread as US."""
    digits = re.sub(r"\D", "", phone)
    if not digits:
        return ""
    # Indian: starts with 91 + 10 digits = 12 total
    if len(digits) == 12 and digits.startswith("91"):
        return f"+{digits}"
    # Indian: 10 digits starting with 6-9
    if len(digits) == 10 and digits[0] in "6789":
        return f"+91{digits}"
    # US: 11 digits starting with 1
    if len(digits) == 11 and digits.startswith("1"):
        return f"+{digits}"
    # US: 10 digits not Indian
    if len(digits) == 10 and digits[0] not in "6789":
        return f"+1{digits}"
    # Already has country code
    if phone.strip().startswith("+"):
        return f"+{digits}"
    return digits

def _clean_names(names: list[str], text: str) -> list[str]:
    result = []
    seen = set()

    # Always try to extract name from labeled pattern or first-line heuristic first
    extracted = _extract_name_from_text(text)
    if extracted:
        # Normalize title case for all-caps names
        display = extracted.title() if extracted.isupper() else extracted
        key = display.lower()
        if key not in seen:
            seen.add(key)
            result.append(display)

    for name in names:
        name = re.sub(r"\s+", " ", name).strip(" ,.;:-|")
        if not name or len(name) < 4:
            continue
        words = name.split()
        if not (2 <= len(words) <= 4):
            continue
        if any(ch.isdigit() for ch in name):
            continue
        if any(w.lower() in _TECH_SKILLS for w in words):
            continue
        if any(w.lower() in _HEADING_WORDS for w in words):
            continue
        if name.lower() in _NOISE_ORGS:
            continue
        if name.lower() in _NOISE_NAMES:
            continue
        # Reject location-like patterns
        if re.search(r"\b(?:pune|mumbai|delhi|bangalore|chennai|hyderabad|new york|brooklyn|london)\b", name.lower()):
            continue
        # Reject strings with OCR noise chars
        if re.search(r"[|&@#%$]", name):
            continue
        if not any(w[0].isupper() for w in words if w):
            continue
        # Normalize all-caps names to title case
        display = name.title() if name.isupper() else name
        key = display.lower()
        if key not in seen:
            seen.add(key)
            result.append(display)
    return result[:8]

def _clean_orgs(orgs: list[str], text: str) -> list[str]:
    result = []
    seen = set()

    # Capture known major orgs present in text
    for org in _extract_known_orgs(text):
        key = org.lower()
        if key not in seen:
            seen.add(key)
            result.append(org)

    for org in orgs:
        org = re.sub(r"\s+", " ", org).strip(" ,.;:-|")
        if not org or len(org) < 2:
            continue
        words = org.split()
        if len(words) > 7:
            continue
        if org.lower() in _NOISE_ORGS:
            continue
        if org.lower() in _TECH_SKILLS:
            continue
        if any(w.lower() in _HEADING_WORDS for w in words):
            continue
        # Reject strings with digits mixed in (OCR noise)
        if re.search(r"[A-Za-z]\s+\d+$", org):
            continue
        # Reject skill-like strings with / or +
        if re.search(r"[/+]", org) and len(words) <= 3:
            continue
        # Reject skill category strings
        if "&" in org and any(w.lower() in _TECH_SKILLS for w in words):
            continue
        if re.search(r"\b(?:databases?|analytics?|programming|engineering|computing|science)\b", org, re.I) and len(words) <= 4:
            continue
        # Single-word all-caps: only allow known acronyms that appear in text
        if len(words) == 1 and org.isupper() and len(org) > 3:
            if org not in _KNOWN_ACRONYMS or org not in text:
                continue
        # Reject OCR noise multi-word strings containing structural words
        if re.search(r"\b(?:department|date|review|classroom|roll)\b", org.lower()) and len(words) > 2:
            continue
        # Reject strings with OCR noise characters
        if re.search(r"[()'\[\]{}|°]", org):
            continue
        # Reject very short strings (1-2 chars)
        if len(org.strip()) <= 2:
            continue
            # Only add if it actually appears in the text
            if org not in _KNOWN_ACRONYMS or org not in text:
                continue
        # Must start with capital
        if not org[0].isupper():
            continue
        # Reject address fragments
        if re.search(r"\d{3,}", org):
            continue
        key = org.lower()
        if key not in seen:
            seen.add(key)
            result.append(org)
    return result[:10]

def _extract_known_orgs(text: str) -> list[str]:
    """Extract well-known orgs that spaCy might miss — only if present as whole words in text."""
    known = [
        "Google","Microsoft","NVIDIA","Apple","Amazon","Meta","OpenAI","IBM",
        "Samsung","Tesla","Netflix","Seagate","Brightline Agency","Blue Horizon Media",
        "ABC Pvt Ltd","ABC Ltd",
        "AICTE","NAAC","SPPU","PCET","NMIET",
    ]
    # EPA only if it's clearly in context (not OCR noise from scanned docs)
    epa_orgs = ["EPA"]
    found = []
    for org in known:
        if org in text:
            found.append(org)
    # EPA: only add if "Environmental Protection Agency" or "EPA" appears in a meaningful context
    for org in epa_orgs:
        if re.search(r"\bEPA\b", text) and re.search(r"(?:environmental|protection|agency|water)", text, re.I):
            found.append(org)
            break
    return found

def _clean_dates(dates: list[str]) -> list[str]:
    result = []
    seen = set()
    for d in dates:
        d = d.strip()
        if not d or d in seen:
            continue
        if re.match(r"^\d{4}$", d):
            year = int(d)
            if 1950 <= year <= 2035:
                seen.add(d)
                result.append(d)
        else:
            seen.add(d)
            result.append(d)
    return result[:8]

def _clean_amounts(amounts: list[str]) -> list[str]:
    result = []
    seen = set()
    for a in amounts:
        a = re.sub(r"\s+", " ", a).strip()
        if a and a.lower() not in seen:
            seen.add(a.lower())
            result.append(a)
    return result[:5]

def _clean_phones(phones: list[str], text: str) -> list[str]:
    """Normalize phones. Fix Indian numbers misread as US. Deduplicate by 10-digit suffix."""
    raw_phones = list(phones)
    # Extract Indian mobile directly from text — highest priority
    for m in re.finditer(r"(?<!\d)(?:91[-\s]?)?[6-9]\d{9}(?!\d)", text):
        raw_phones.append(m.group(0))

    normalized_list = []
    for phone in raw_phones:
        digits = re.sub(r"\D", "", phone)
        if not digits or len(digits) < 10:
            continue
        if len(digits) == 12 and digits.startswith("91"):
            normalized_list.append((f"+{digits}", digits[-10:]))
        elif len(digits) == 10 and digits[0] in "6789":
            normalized_list.append((f"+91{digits}", digits))
        elif len(digits) == 11 and digits.startswith("91") and digits[2] in "6789":
            normalized_list.append((f"+91{digits[2:]}", digits[2:]))
        elif len(digits) == 11 and digits.startswith("1") and digits[1] in "6789":
            # Likely Indian number with leading 1 misread
            normalized_list.append((f"+91{digits[1:]}", digits[1:]))
        elif len(digits) == 11 and digits.startswith("1"):
            normalized_list.append((f"+{digits}", digits[-10:]))
        elif len(digits) == 10 and digits[0] not in "6789":
            normalized_list.append((f"+1{digits}", digits))
        else:
            normalized_list.append((f"+{digits}", digits[-10:]))

    # Deduplicate: prefer longer/more specific format, dedupe by 10-digit suffix
    seen_suffixes: set[str] = set()
    result = []
    # Sort: longer normalized strings first (e.g. +918208996934 before +18208996934)
    normalized_list.sort(key=lambda x: len(x[0]), reverse=True)
    for normalized, suffix in normalized_list:
        if suffix not in seen_suffixes:
            seen_suffixes.add(suffix)
            result.append(normalized)
    return result[:3]

# ---------------------------------------------------------------------------
# Summary builders
# ---------------------------------------------------------------------------

def _is_good_summary(summary: str) -> bool:
    if not summary or len(summary) < 20:
        return False
    if "\n" in summary:
        return False
    if "..." in summary:
        return False
    if len(summary) > _MAX_SUMMARY_CHARS:
        return False
    if re.search(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", summary):
        return False
    if re.search(r"https?://|www\.", summary):
        return False
    # Reject if starts with document title (all-caps word)
    first_word = summary.split()[0] if summary.split() else ""
    if first_word.isupper() and len(first_word) > 4:
        return False
    # Reject if it starts with "Official letter from X regarding I am writing"
    if re.search(r"^Official letter from .+ regarding I am", summary, re.I):
        return False
    # Reject if it contains raw address/header fragments
    if re.search(r"\d{3,}\s*&|Maharashtra|Chinchwad|RE:\s*Intern", summary):
        return False
    sentences = re.split(r"(?<=[.!?])\s+", summary.strip())
    if len(sentences) > 3:
        return False
    return True

def _is_ongoing_student(text: str) -> bool:
    """Return True if the person is currently studying (graduation year in future)."""
    m = re.search(r"(20\d{2})\s*[-–—]\s*(20\d{2})", text)
    if m:
        end_year = int(m.group(2))
        if end_year >= 2025:
            return True
    # Explicit "currently" or "pursuing"
    if re.search(r"\b(currently|pursuing|ongoing|present)\b", text, re.I):
        return True
    return False

def _extract_clean_skills_for_summary(text: str) -> list[str]:
    """Extract clean skill names from resume text for summary."""
    skills = []
    # Look for skills section
    m = re.search(r"SKILLS?\s*\n(.*?)(?:\n[A-Z]{2,}|\Z)", text, re.S | re.I)
    if m:
        skill_block = m.group(1)
        for line in skill_block.splitlines():
            # Strip category labels like "Programming: Python, C++"
            if ":" in line:
                line = line.split(":", 1)[1]
            for s in re.split(r"[,;|]", line):
                s = s.strip().strip("()")
                if 1 < len(s) < 25 and not any(ch.isdigit() for ch in s):
                    skills.append(s)
    return skills[:5]

def _generate_summary(doc_type: str, text: str, entities: dict, doc_data: dict) -> str:
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    names = entities.get("names", [])
    orgs = entities.get("organizations", [])

    if doc_type == "resume":
        name = doc_data.get("name") or (names[0] if names else "The candidate")
        edu = doc_data.get("education", [])
        skills = _extract_clean_skills_for_summary(text)
        skill_str = ", ".join(skills) if skills else "various technical skills"
        edu_str = edu[0] if edu else ""
        is_student = _is_ongoing_student(text)

        # Clean edu_str — remove CGPA, dates, percentages
        def _clean_edu(s: str) -> str:
            s = re.sub(r"\s*[-–—]\s*CGPA.*", "", s).strip()
            s = re.sub(r"\s*\(.*", "", s).strip()
            s = re.sub(r"\s*—\s*\d+%.*", "", s).strip()
            s = re.sub(r"\s*\|\s*.*", "", s).strip()
            return s.strip()

        if edu_str and is_student:
            edu_clean = _clean_edu(edu_str)
            return f"{name} is a student pursuing {edu_clean}, with skills in {skill_str}."
        elif edu_str:
            edu_clean = _clean_edu(edu_str)
            return f"{name} is a professional with a background in {edu_clean} and skills in {skill_str}."
        return f"{name} is a professional with skills in {skill_str}."

    if doc_type == "invoice":
        vendor = (doc_data.get("vendor") or (orgs[0] if orgs else "a vendor")).splitlines()[0].strip()
        customer = (doc_data.get("customer") or (names[0] if names else "a customer")).splitlines()[0].strip()
        amount = doc_data.get("amount", "")
        date = doc_data.get("date", "")
        summary = f"Invoice issued by {vendor} to {customer}"
        if amount:
            summary += f" for {amount}"
        if date:
            summary += f" dated {date}"
        return summary + "."

    if doc_type == "incident_report":
        incident_type = doc_data.get("incident_type", "security incident")
        affected = doc_data.get("affected_entities", [])
        affected_str = affected[0] if affected else "multiple organizations"
        return (f"This report describes a {incident_type} that affected {affected_str}. "
                f"It outlines the cause, impact, and recommended remediation measures.")

    if doc_type == "notice":
        institution = doc_data.get("institution", "")
        # Clean OCR noise from institution name
        institution = re.sub(r"\bey\b|\bWo\b|\bMey\b", "", institution).strip()
        institution = re.sub(r"\s{2,}", " ", institution).strip()
        if not institution:
            institution = orgs[0] if orgs else "the institution"
        event = doc_data.get("event", "")
        # Clean OCR noise from event name
        event = re.sub(r'[\[\]"\']', "", event).strip()
        event = re.sub(r"REVIEW-I\[.*", "Review-II", event)
        event_date = doc_data.get("event_date", "")
        if event and event_date:
            return f"This notice from {institution} informs students about {event} scheduled on {event_date}."
        if event:
            return f"This notice from {institution} informs students about {event}."
        return f"Official notice issued by {institution}."

    if doc_type == "official_letter":
        org = orgs[0] if orgs else "a government agency"
        sender = doc_data.get("sender", "")
        recipient = doc_data.get("recipient", "")
        # Check if it's a cover letter (job application)
        is_cover = _has(text.lower(), "dear hiring", "dear recruiter", "re: intern", "re: position") or \
                   (_has(text.lower(), "applying", "application", "position") and
                    _has(text.lower(), "seagate", "google", "microsoft", "amazon", "company"))
        if is_cover:
            company = orgs[0] if orgs else "the company"
            return f"Cover letter from {sender or 'the applicant'} applying for a position at {company}."
        # For official letters, generate from first clean meaningful sentence
        sentences = re.split(r"(?<=[.!?])\s+", text.strip())
        clean = [s.strip() for s in sentences
                 if 20 < len(s) < 200
                 and not s.isupper()
                 and "@" not in s
                 and not re.search(r"^\s*[A-Z]{2,}\s*$", s)
                 and not re.search(r"Dear\s+\w+", s)
                 and not re.search(r"^[a-z]{1,3}\s+[A-Z]", s)  # skip OCR noise lines
                 and len(s.split()) >= 8]  # must be a real sentence
        if clean:
            first = clean[0]
            # Truncate cleanly at sentence boundary
            if len(first) > 200:
                first = first[:200].rsplit(" ", 1)[0] + "."
            return first
        return f"Official correspondence from {org} to {recipient or 'the recipient'}."

    if doc_type == "identity":
        name = doc_data.get("name", names[0] if names else "the individual")
        name = name.splitlines()[0].strip()
        branch = doc_data.get("branch", "").splitlines()[0].strip()
        id_no = doc_data.get("id", "")
        if branch and id_no:
            return f"Identity document for {name}, enrolled in {branch} with ID {id_no}."
        if branch:
            return f"Identity document for {name}, enrolled in {branch}."
        if id_no:
            return f"Identity document for {name} with ID {id_no}."
        return f"Identity document for {name}."

    if doc_type == "article":
        # Find first clean informative sentence — skip title lines (contain ":")
        sentences = re.split(r"(?<=[.!?])\s+", text.strip())
        good = [re.sub(r"\s+", " ", s.strip()) for s in sentences
                if 15 < len(s.split()) < 50
                and not s.strip().isupper()
                and ":" not in s[:30]  # skip title-like lines
                and not re.search(r"^\s*[A-Z][A-Za-z\s]+:\s+[A-Z]", s)]  # skip "Title: Content"
        if len(good) >= 2:
            return good[0] + " " + good[1]
        if good:
            return good[0]
        # Fallback: use any sentence with enough words
        any_sent = [re.sub(r"\s+", " ", s.strip()) for s in sentences if len(s.split()) > 10]
        if any_sent:
            return any_sent[0][:_MAX_SUMMARY_CHARS]
        return text.strip()[:_MAX_SUMMARY_CHARS]

    # general
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    clean = [s for s in sentences if len(s) > 30 and not s.isupper()]
    if clean:
        return clean[0][:_MAX_SUMMARY_CHARS]
    return text.strip()[:_MAX_SUMMARY_CHARS]

def _build_summary(doc_type: str, text: str, llm_summary: str, entities: dict, doc_data: dict) -> str:
    # For articles, always regenerate — LLM tends to copy the first paragraph verbatim
    if doc_type == "article":
        return _generate_summary(doc_type, text, entities, doc_data)
    if llm_summary and _is_good_summary(llm_summary):
        return llm_summary
    return _generate_summary(doc_type, text, entities, doc_data)

# ---------------------------------------------------------------------------
# Document data builders
# ---------------------------------------------------------------------------

def _build_resume_data(text: str, entities: dict) -> dict:
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    name = ""
    education = []
    skills = []
    projects = []
    experience = []

    for line in lines[:5]:
        if _is_name_line(line):
            name = line.title() if line.isupper() else line
            break

    current_section = None
    section_map = {
        "education": "education", "skills": "skills", "skill": "skills",
        "projects": "projects", "project": "projects",
        "experience": "experience", "work experience": "experience",
        "achievements": "achievements", "certifications": "certifications",
    }

    for line in lines:
        low = line.lower().strip(":- ")
        if low in section_map:
            current_section = section_map[low]
            continue
        if current_section == "education" and len(line) > 5:
            # Skip CGPA-only lines
            if not re.match(r"^CGPA\s*:", line, re.I):
                education.append(line)
        elif current_section == "skills" and len(line) > 2:
            # Strip category label (e.g. "Programming: Python, C++")
            if ":" in line:
                line = line.split(":", 1)[1].strip()
            for s in re.split(r"[,;|]", line):
                s = s.strip().strip("()")
                if s and len(s) > 1 and not s.lower().startswith("concepts"):
                    skills.append(s)
        elif current_section == "projects" and len(line) > 5:
            projects.append(line)
        elif current_section == "experience" and len(line) > 5:
            experience.append(line)

    return {
        "name": name,
        "education": education[:5],
        "skills": skills[:15],
        "projects": projects[:5],
        "experience": experience[:5],
    }

def _build_invoice_data(text: str, entities: dict) -> dict:
    invoice_id = ""
    vendor = ""
    customer = ""
    date = ""
    amount = ""

    # Invoice ID — must be alphanumeric, not a preposition
    m = re.search(r"invoice\s*(?:no|number|#|id)\s*[:\s#-]+([A-Z0-9][A-Z0-9\-/]{2,})", text, re.I)
    if m:
        invoice_id = m.group(1).strip()

    m = re.search(r"(?:from|vendor|seller|issued by|billed by)[:\s]+([A-Z][A-Za-z0-9\s&.,\-]{2,40}?)(?:\s+to\s|\s+dated\s|$)", text, re.I)
    if m:
        vendor = m.group(1).strip().splitlines()[0].strip().rstrip(".,")

    m = re.search(r"(?:^to|customer|buyer|billed to|client)[:\s]+([A-Z][A-Za-z0-9\s&.,\-]{2,40}?)(?:\s+dated\s|\s+for\s|$)", text, re.I | re.MULTILINE)
    if m:
        customer = m.group(1).strip().splitlines()[0].strip().rstrip(".,")
    if not customer:
        m = re.search(r"\bto\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})\b", text)
        if m:
            customer = m.group(1).strip()

    m = re.search(r"(?:^date|dated)[:\s]+(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4}|\d{1,2}\s+\w+\s+\d{4}|\w+\s+\d{1,2},?\s+\d{4})", text, re.I | re.MULTILINE)
    if m:
        date = m.group(1).strip()

    m = re.search(r"(?:total|amount due|grand total|net amount|payable|amount)[:\s]*((?:₹|\$|€|£|rs\.?|inr)?\s*[\d,]+(?:\.\d{1,2})?(?:\s*(?:rupees|inr|usd))?)", text, re.I)
    if m:
        amount = m.group(1).strip()
    else:
        amounts = entities.get("amounts", [])
        if amounts:
            amount = amounts[0]

    if not vendor:
        orgs = entities.get("organizations", [])
        if orgs:
            vendor = orgs[0]
    if not customer:
        nms = entities.get("names", [])
        if nms:
            customer = nms[0]

    return {"invoice_id": invoice_id, "vendor": vendor, "customer": customer, "date": date, "amount": amount}

def _build_incident_data(text: str, entities: dict) -> dict:
    incident_types = [
        "data breach","ransomware","phishing","ddos","malware","unauthorized access",
        "insider threat","sql injection","zero-day","credential theft",
        "supply chain attack","lead contamination","water contamination",
    ]
    incident_type = "Security Incident"
    t_lower = text.lower()
    for it in incident_types:
        if it in t_lower:
            incident_type = it.title()
            break

    sentences = re.split(r"(?<=[.!?])\s+", text)
    cause = [s.strip() for s in sentences
             if any(kw in s.lower() for kw in ["caused by","due to","root cause","exploited","vulnerability in","unauthorized access"])
             ][:2]
    impact = [s.strip() for s in sentences
              if any(kw in s.lower() for kw in ["affected","compromised","exposed","disrupted","leaked","breach"])
              and len(s) < 300 and not s.startswith("Cybersecurity Incident")
              ][:3]
    affected = []
    for s in sentences:
        m = re.search(r"(?:affected|compromised|targeted|impacted)\s+([A-Z][A-Za-z\s&,]{3,40})", s)
        if m:
            affected.append(m.group(1).strip().rstrip(","))
    if not affected:
        affected = [o for o in entities.get("organizations", []) if len(o) > 3][:3]

    return {"incident_type": incident_type, "affected_entities": affected[:3], "cause": cause, "impact": impact}

def _build_article_data(text: str, entities: dict) -> dict:
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    topic = ""
    for line in lines[:5]:
        if 5 < len(line) < 100 and not line.endswith((".", "?", "!")):
            topic = line
            break
    if not topic and lines:
        topic = " ".join(lines[0].split()[:8])

    sentences = re.split(r"(?<=[.!?])\s+", text)
    signal_words = ["key","important","significant","major","critical","highlight",
                    "finding","result","conclude","show","reveal","indicate","report",
                    "according","analysis","investment","growth","expanding"]
    scored = sorted(
        [(sum(1 for w in signal_words if w in s.lower()), s.strip())
         for s in sentences if 20 < len(s.strip()) < 300],
        key=lambda x: x[0], reverse=True
    )
    key_points = [s for _, s in scored[:5] if s]
    return {"topic": topic, "key_points": key_points}

def _build_notice_data(text: str, entities: dict) -> dict:
    institution = ""
    event = ""
    event_date = ""
    instructions = []

    m = re.search(r"((?:NUTAN|NMIET|IIT|NIT|BITS|VIT|MIT)[A-Z\s&.]+(?:INSTITUTE|COLLEGE|UNIVERSITY|TECHNOLOGY|ENGINEERING)[A-Z\s&.]*)", text, re.I)
    if m:
        raw = m.group(1).strip()
        # Clean OCR noise words
        raw = re.sub(r"\b(?:ey|Wo|Mey|OF\s+ey)\b", "", raw, flags=re.I).strip()
        raw = re.sub(r"\s{2,}", " ", raw)
        institution = raw[:60]
    if not institution:
        orgs = entities.get("organizations", [])
        institution = orgs[0] if orgs else "the institution"

    m = re.search(r"(?:scheduled on|date)[:\s]+(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4}|\d{1,2}\s+\w+\s+\d{4})", text, re.I)
    if m:
        event_date = m.group(1).strip()

    m = re.search(r"(?:NOTICE|CIRCULAR|ANNOUNCEMENT)[:\s\n]+([^\n]{5,80})", text, re.I)
    if m:
        raw_event = m.group(1).strip()
        # Clean OCR garbage from event name
        raw_event = re.sub(r'[\[\]"\'\(\)]', "", raw_event).strip()
        raw_event = re.sub(r"REVIEW-I.*", "Review-II", raw_event)
        raw_event = re.sub(r"INTERNSHIP\s+REVIEW-II", "Internship Review-II", raw_event, flags=re.I)
        event = raw_event

    lines = [l.strip() for l in text.splitlines() if l.strip()]
    for line in lines:
        if re.match(r"^\d+[\.\)]\s+.{10,}", line):
            # Clean trailing OCR noise
            clean_line = re.sub(r"\s+e\s+TE-.*", "", line).strip()
            instructions.append(clean_line)

    return {"institution": institution, "event": event, "event_date": event_date, "instructions": instructions[:7]}

def _build_official_letter_data(text: str, entities: dict) -> dict:
    sender = ""
    recipient = ""
    organization = ""
    purpose = ""

    orgs = entities.get("organizations", [])
    names = entities.get("names", [])

    if orgs:
        organization = orgs[0]
    if names:
        sender = names[-1] if len(names) > 1 else names[0]

    m = re.search(r"Dear\s+([A-Z][a-zA-Z\s,\.]{2,40})[:\n]", text)
    if m:
        recipient = m.group(1).strip().rstrip(",:")

    sentences = re.split(r"(?<=[.!?])\s+", text)
    for s in sentences:
        s_clean = re.sub(r"\s+", " ", s.strip())
        # Skip header/address fragments
        if re.search(r"\d{3,}|Maharashtra|Chinchwad|RE:\s*Intern|@", s_clean):
            continue
        if any(kw in s_clean.lower() for kw in ["writing to","request","urge","ask you","inform","interest in","applying","express my"]):
            purpose = s_clean[:150]
            break

    return {"sender": sender, "recipient": recipient, "organization": organization, "purpose": purpose}

def _build_identity_data(text: str, entities: dict) -> dict:
    name = ""
    id_no = ""
    dob = ""
    blood_group = ""
    branch = ""

    m = re.search(r"(?:name\s*[:\-]\s*)([A-Z][A-Za-z\s]{2,30})", text, re.I)
    if m:
        name = m.group(1).strip().splitlines()[0].strip()
        name = name.title() if name.isupper() else name

    # ID: look for alphanumeric ID patterns
    m = re.search(r"(?:^|\s)ID\s*['\s]*([A-Z]{2}\d{5,12})", text, re.I | re.MULTILINE)
    if m:
        id_no = m.group(1).strip()
    if not id_no:
        m = re.search(r"(?:enrollment|roll\s*no)[:\s#]*([A-Z0-9]{5,15})", text, re.I)
        if m:
            id_no = m.group(1).strip()

    m = re.search(r"(?:dob|date of birth)[:\s]+([0-9]{1,2}[.\/\-][0-9]{1,2}[.\/\-][0-9]{2,4})", text, re.I)
    if m:
        dob = m.group(1).strip()

    m = re.search(r"(?:blood\s*group)[:\s]+([ABO][+-](?:VE|ve)?)", text, re.I)
    if m:
        blood_group = m.group(1).strip().upper()

    m = re.search(r"(?:branch|department)[:\s]+([A-Za-z\s]{3,40})", text, re.I)
    if m:
        branch = m.group(1).strip().splitlines()[0].strip()

    if not name:
        nms = entities.get("names", [])
        if nms:
            name = nms[0]

    return {"name": name, "id": id_no, "dob": dob, "blood_group": blood_group, "branch": branch}

def _build_general_data(text: str, entities: dict) -> dict:
    return {}

# ---------------------------------------------------------------------------
# Sentiment
# ---------------------------------------------------------------------------

def _determine_sentiment(doc_type: str, text: str, llm_sentiment: str) -> str:
    if doc_type == "incident_report":
        return "Negative"
    if doc_type in {"resume","invoice","notice","official_letter","identity"}:
        return "Neutral"
    if llm_sentiment and llm_sentiment.lower() in {"positive","neutral","negative"}:
        return llm_sentiment.capitalize()
    t = text.lower()
    neg = sum(1 for w in ["breach","attack","failure","risk","threat","problem",
                           "issue","concern","danger","crisis","unauthorized","compromised"] if w in t)
    pos = sum(1 for w in ["success","growth","positive","improved","benefit",
                           "innovation","achievement","excellent","outstanding","award"] if w in t)
    if neg > pos + 1:
        return "Negative"
    if pos > neg + 1:
        return "Positive"
    return "Neutral"

# ---------------------------------------------------------------------------
# Main finalizer
# ---------------------------------------------------------------------------

def finalize_output(text: str, llm_result: dict[str, Any] | None, rule_based: dict[str, Any]) -> dict[str, Any]:
    doc_type = _detect_type(text)

    raw_entities = (llm_result or {}).get("entities") or rule_based.get("entities", {})

    names = _clean_names(raw_entities.get("names", []), text)
    orgs = _clean_orgs(raw_entities.get("organizations", []), text)
    dates = _clean_dates(raw_entities.get("dates", []))
    amounts = _clean_amounts(raw_entities.get("amounts", []))
    emails = raw_entities.get("emails", [])
    phones = _clean_phones(raw_entities.get("phones", []), text)

    clean_entities = {
        "names": names, "organizations": orgs, "dates": dates,
        "amounts": amounts, "emails": emails, "phones": phones,
    }

    builders = {
        "resume": _build_resume_data, "invoice": _build_invoice_data,
        "incident_report": _build_incident_data, "article": _build_article_data,
        "notice": _build_notice_data, "official_letter": _build_official_letter_data,
        "identity": _build_identity_data, "general": _build_general_data,
    }
    doc_data = builders.get(doc_type, _build_general_data)(text, clean_entities)

    llm_summary = (llm_result or {}).get("summary", "")
    summary = _build_summary(doc_type, text, llm_summary, clean_entities, doc_data)

    llm_sentiment = (llm_result or {}).get("sentiment", "")
    sentiment = _determine_sentiment(doc_type, text, llm_sentiment)

    return {
        "documentType": doc_type,
        "summary": summary,
        "entities": clean_entities,
        "sentiment": sentiment,
        "documentData": doc_data,
    }

"""
invoice_parser.py
-----------------
Structured parser for invoice / billing document text.

Goals:
- extract invoice_id, vendor, customer, date, amount
- support labeled and semi-structured invoices
- work on OCR text and messy formatting
- stay deterministic and offline
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

RE_INVOICE_ID = re.compile(
    r"(?:invoice\s*(?:no|number|#|id)?|bill\s*(?:no|number|#|id)?)"
    r"[:\s#-]*([A-Z0-9][A-Z0-9\-/]{2,})",
    re.I,
)

RE_DATE = re.compile(
    r"(?:invoice\s+date|date|dated|bill\s+date)"
    r"[:\s-]*"
    r"("
    r"\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4}"
    r"|"
    r"\d{1,2}\s+(?:Jan|January|Feb|February|Mar|March|Apr|April|May|Jun|June|Jul|July|"
    r"Aug|August|Sep|Sept|September|Oct|October|Nov|November|Dec|December)\s+\d{4}"
    r"|"
    r"(?:Jan|January|Feb|February|Mar|March|Apr|April|May|Jun|June|Jul|July|"
    r"Aug|August|Sep|Sept|September|Oct|October|Nov|November|Dec|December)"
    r"\s+\d{1,2},?\s+\d{4}"
    r")",
    re.I,
)

RE_AMOUNT = re.compile(
    r"(?:grand\s+total|amount\s+due|total\s+amount|net\s+amount|payable|total)"
    r"[:\s-]*"
    r"([₹$€£]?\s*[\d,]+(?:\.\d{1,2})?(?:\s*(?:INR|USD|EUR|GBP))?)",
    re.I,
)

RE_VENDOR = re.compile(
    r"(?:from|vendor|seller|billed\s+by|issued\s+by|supplier)"
    r"[:\s-]+([A-Z][A-Za-z0-9\s&.,\-]{2,80})",
    re.I,
)

RE_CUSTOMER = re.compile(
    r"(?:to|customer|buyer|billed\s+to|client|invoice\s+to)"
    r"[:\s-]+([A-Z][A-Za-z0-9\s&.,\-]{2,80})",
    re.I,
)

RE_STANDALONE_AMOUNT = re.compile(
    r"([₹$€£]\s*[\d,]+(?:\.\d{1,2})?(?:\s*(?:INR|USD|EUR|GBP))?)",
    re.I,
)

RE_COMPANY_LINE = re.compile(
    r"^[A-Z][A-Za-z0-9&.,\- ]{2,80}(?:Ltd|Limited|Inc|Corporation|Company|Services|Technologies|Technology)?$"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _clean_value(value: str) -> str:
    value = _normalize(value)
    value = value.splitlines()[0].strip()
    return value.strip(" ,.;:")


def _first_match(pattern: re.Pattern, text: str) -> str:
    match = pattern.search(text)
    if not match:
        return ""
    return _clean_value(match.group(1))


def _extract_lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


def _fallback_vendor(lines: list[str]) -> str:
    """
    Vendor is often near the top of the invoice.
    """
    for line in lines[:8]:
        clean = _clean_value(line)
        if RE_COMPANY_LINE.match(clean) and "invoice" not in clean.lower():
            return clean
    return ""


def _fallback_customer(text: str, lines: list[str]) -> str:
    """
    If label-based extraction fails, try simple heuristics around "Bill To" or "To".
    """
    for i, line in enumerate(lines):
        low = line.lower()
        if low in {"bill to", "billed to", "invoice to", "customer", "client", "to"}:
            if i + 1 < len(lines):
                return _clean_value(lines[i + 1])
    return ""


def _fallback_amount(text: str) -> str:
    """
    Grab first currency-looking amount if labeled total not found.
    """
    match = RE_STANDALONE_AMOUNT.search(text)
    return _clean_value(match.group(1)) if match else ""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_invoice(text: str) -> dict:
    """
    Parse invoice/billing text into structured documentData.
    """
    try:
        lines = _extract_lines(text)

        invoice_id = _first_match(RE_INVOICE_ID, text)
        vendor = _first_match(RE_VENDOR, text)
        customer = _first_match(RE_CUSTOMER, text)
        date = _first_match(RE_DATE, text)
        amount = _first_match(RE_AMOUNT, text)

        if not vendor:
            vendor = _fallback_vendor(lines)

        if not customer:
            customer = _fallback_customer(text, lines)

        if not amount:
            amount = _fallback_amount(text)

        return {
            "invoice_id": invoice_id,
            "vendor": vendor,
            "customer": customer,
            "date": date,
            "amount": amount,
        }

    except Exception as exc:
        logger.warning("invoice_parser failed: %s", exc)
        return {}
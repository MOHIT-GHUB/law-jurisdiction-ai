"""
utils/pii.py — Redact high-sensitivity PII from user text.

A legal intake tool legitimately needs names, addresses, dates, and incident
details to do its job, so we deliberately do NOT strip those. We DO strip
structured secrets that add no legal-analysis value but are dangerous to store in
our DB or send to a third-party LLM: SSNs, payment-card numbers, emails, phones.

redact_pii() is applied at the input boundary (routers/chat.py) so raw secrets
never reach Postgres or OpenAI. Redaction is intentionally conservative (requires
separators / Luhn-valid cards) to avoid clobbering legal facts like dates,
dollar amounts, or statute citations.
"""

import re

# SSN: requires separators so we don't redact arbitrary 9-digit numbers.
_SSN = re.compile(r"\b\d{3}[-\s]\d{2}[-\s]\d{4}\b")
_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
# US phone: digit lookarounds (not \b) so the leading "(" is captured and dates
# ("2024-03-15", 4-2-2 digits) don't match.
_PHONE = re.compile(r"(?<!\d)(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]\d{4}(?!\d)")
# Candidate card: 13–19 digits with optional spaces/dashes — confirmed via Luhn.
_CARD = re.compile(r"\b(?:\d[ -]?){13,19}\b")


def _luhn_ok(digits: str) -> bool:
    total, parity = 0, len(digits) % 2
    for i, ch in enumerate(digits):
        d = int(ch)
        if i % 2 == parity:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def _redact_cards(text: str) -> str:
    def repl(match: re.Match) -> str:
        digits = re.sub(r"\D", "", match.group())
        if 13 <= len(digits) <= 19 and _luhn_ok(digits):
            return "[REDACTED CARD]"
        return match.group()  # not a real card (e.g. a long case/docket number)

    return _CARD.sub(repl, text)


def redact_pii(text: str) -> str:
    """Return text with SSNs, payment cards, emails, and phone numbers masked."""
    if not text:
        return text
    text = _SSN.sub("[REDACTED SSN]", text)
    text = _redact_cards(text)
    text = _EMAIL.sub("[REDACTED EMAIL]", text)
    text = _PHONE.sub("[REDACTED PHONE]", text)
    return text

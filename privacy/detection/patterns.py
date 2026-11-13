"""Pattern-based and heuristic recognizers for Indian enterprise documents.

Supplements Presidio and NER with regex and context heuristics for
phone, email, date of birth, bank account, credit card, other synthetic IDs,
and Indian address cues.
"""

from __future__ import annotations

import re

from app.contracts import DetectedEntity, EntityType

_ADDR_RE = re.compile(
    r"(?:Residential\s+address|Current\s+address|Permanent\s+address|Address|Pata|Location)\s*:\s*([^\n\r]+)",
    re.IGNORECASE,
)
_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_PHONE_RE = re.compile(
    r"(?:\+91[\s\-]?)?[0-9]{5}[\s\-]?[0-9]{5}\b|\b0\d{10}\b|\b(?:\+91[\s\-]?)?[6-9]\d{9}\b"
)
_DOB_RE = re.compile(
    r"\b\d{1,2}(?:st|nd|rd|th)?[\s\-/](?:January|February|March|April|May|June|July|August|September|October|November|December|[A-Za-z]{3}|\d{1,2})[\s\-/]\d{2,4}\b|\b\d{4}[\-/]\d{1,2}[\-/]\d{1,2}\b",
    re.IGNORECASE,
)
_CARD_RE = re.compile(r"\b\d{4}[\s\-]?\d{4}[\s\-]?\d{4}[\s\-]?\d{4}\b")
_OTHER_RE = re.compile(r"\b(?:POL|CUST|TICK|CLAIM|ACC|REF)[-_]\d{4,8}\b")
_BANK_CONTEXTS = ("bank", "account", "a/c", "disbursal", "settlement")
_CARD_CONTEXTS = ("card", "credit", "debit", "premium", "visa", "mastercard")


def extract(text: str) -> list[DetectedEntity]:
    """Extract heuristic and regex entities from text."""
    hits: list[DetectedEntity] = []

    # 1. Address heuristic
    for m in _ADDR_RE.finditer(text):
        raw = m.group(1)
        lstrip = len(raw) - len(raw.lstrip())
        rstrip = len(raw) - len(raw.rstrip())
        start = m.start(1) + lstrip
        end = m.end(1) - rstrip
        if end > start:
            hits.append(
                DetectedEntity(
                    type=EntityType.ADDRESS,
                    start=start,
                    end=end,
                    text=text[start:end],
                    score=0.90,
                    source="heuristic",
                )
            )

    # 2. Email
    for m in _EMAIL_RE.finditer(text):
        hits.append(
            DetectedEntity(
                type=EntityType.EMAIL,
                start=m.start(),
                end=m.end(),
                text=m.group(),
                score=0.95,
                source="regex",
            )
        )

    # 3. Phone
    for m in _PHONE_RE.finditer(text):
        hits.append(
            DetectedEntity(
                type=EntityType.PHONE,
                start=m.start(),
                end=m.end(),
                text=m.group(),
                score=0.85,
                source="regex",
            )
        )

    # 4. DOB
    for m in _DOB_RE.finditer(text):
        hits.append(
            DetectedEntity(
                type=EntityType.DOB,
                start=m.start(),
                end=m.end(),
                text=m.group(),
                score=0.85,
                source="regex",
            )
        )

    # 5. Bank Account (context-gated)
    for m in re.finditer(r"\b\d{9,18}\b", text):
        start, end = m.start(), m.end()
        window = text[max(0, start - 40) : min(len(text), end + 40)].lower()
        if any(c in window for c in _BANK_CONTEXTS):
            hits.append(
                DetectedEntity(
                    type=EntityType.BANK_ACCOUNT,
                    start=start,
                    end=end,
                    text=text[start:end],
                    score=0.85,
                    source="regex",
                )
            )

    # 6. Credit Card (context-gated)
    for m in _CARD_RE.finditer(text):
        start, end = m.start(), m.end()
        window = text[max(0, start - 40) : min(len(text), end + 40)].lower()
        if any(c in window for c in _CARD_CONTEXTS):
            hits.append(
                DetectedEntity(
                    type=EntityType.CREDIT_CARD,
                    start=start,
                    end=end,
                    text=text[start:end],
                    score=0.85,
                    source="regex",
                )
            )

    # 7. Other identifiers (POL-*, CUST-*, etc.)
    for m in _OTHER_RE.finditer(text):
        hits.append(
            DetectedEntity(
                type=EntityType.OTHER,
                start=m.start(),
                end=m.end(),
                text=m.group(),
                score=0.85,
                source="regex",
            )
        )

    return hits

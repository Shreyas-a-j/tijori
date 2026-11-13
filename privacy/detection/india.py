"""India-specific PII recognizers built on Presidio ``PatternRecognizer``."""

from __future__ import annotations

import re
from typing import Any

from app.contracts import EntityType
from presidio_analyzer import AnalyzerEngine, PatternRecognizer
from presidio_analyzer.pattern import Pattern
from presidio_analyzer.recognizer_registry import RecognizerRegistry

AADHAAR_REGEX = r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}\b"
PAN_REGEX = r"\b[A-Z]{5}[0-9]{4}[A-Z]\b"
GSTIN_REGEX = r"\b\d{2}[ \t]?[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]\b"
VOTER_ID_REGEX = r"\b[A-Z]{3}[0-9]{7}\b"
PASSPORT_REGEX = r"\b[A-Z][0-9]{7}\b"

AADHAAR_CONTEXTS = (
    "aadhaar",
    "aadhar",
    "uidai",
    "आधार",
    "aadhaar number",
    "number of applicants",
    "number of bases",
    "based number",
    "id number",
    "identity number",
)
PAN_CONTEXTS = ("pan", "income tax", "pan card")
GSTIN_CONTEXTS = ("gstin", "gstn", "gst", "goods and services tax")
VOTER_ID_CONTEXTS = (
    "voter",
    "voters",
    "epic",
    "election",
    "electoral",
    "voting",
    "voter id",
)
PASSPORT_CONTEXTS = (
    "passport",
    "passports",
    "passport number",
    "pass number",
)

RECOGNIZER_SPECS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("AADHAAR", AADHAAR_REGEX, AADHAAR_CONTEXTS),
    ("PAN", PAN_REGEX, PAN_CONTEXTS),
    ("GSTIN", GSTIN_REGEX, GSTIN_CONTEXTS),
    ("VOTER_ID", VOTER_ID_REGEX, VOTER_ID_CONTEXTS),
    ("PASSPORT", PASSPORT_REGEX, PASSPORT_CONTEXTS),
)


def _as_type_name(value: Any) -> str:
    return str(getattr(value, "value", value) or value)


def _as_context(entity_type: str) -> tuple[str, ...]:
    for name, _regex, context in RECOGNIZER_SPECS:
        if name == entity_type:
            return context
    return ()


def _context_regex(context_word: str) -> str:
    if re.match(r"[\u0900-\u097F]", context_word):
        return re.escape(context_word)
    # Tolerate plurals that machine translation produces ("Passports:",
    # "voters") without turning the context word into a prefix that matches
    # unrelated words such as "panel" for "pan".
    return r"\b" + re.escape(context_word) + r"(?:s|es)?\b"


def _has_context(text: str, start: int, end: int, context: tuple[str, ...]) -> bool:
    """True when a context word appears near the detected span."""
    window = text[max(0, start - 40) : min(len(text), end + 40)].lower()
    for word in context:
        if not word:
            continue
        if re.search(_context_regex(word), window, re.IGNORECASE):
            return True
    return False


def _is_valid_aadhaar(start: int, end: int, text: str) -> bool:
    digits = re.sub(r"[\s-]", "", text[start:end])
    return len(digits) == 12 and digits[0] in "23456789"


_VERHOEFF_D = (
    (0, 1, 2, 3, 4, 5, 6, 7, 8, 9),
    (1, 2, 3, 4, 0, 6, 7, 8, 9, 5),
    (2, 3, 4, 0, 1, 7, 8, 9, 5, 6),
    (3, 4, 0, 1, 2, 8, 9, 5, 6, 7),
    (4, 0, 1, 2, 3, 9, 5, 6, 7, 8),
    (5, 9, 8, 7, 6, 0, 4, 3, 2, 1),
    (6, 5, 9, 8, 7, 1, 0, 4, 3, 2),
    (7, 6, 5, 9, 8, 2, 1, 0, 4, 3),
    (8, 7, 6, 5, 9, 3, 2, 1, 0, 4),
    (9, 8, 7, 6, 5, 4, 3, 2, 1, 0),
)
_VERHOEFF_P = (
    (0, 1, 2, 3, 4, 5, 6, 7, 8, 9),
    (1, 5, 7, 6, 2, 8, 3, 0, 9, 4),
    (5, 8, 0, 3, 7, 9, 6, 1, 4, 2),
    (8, 9, 1, 6, 0, 4, 3, 5, 2, 7),
    (9, 4, 5, 3, 1, 2, 6, 8, 7, 0),
    (4, 2, 8, 6, 5, 7, 3, 9, 0, 1),
    (2, 7, 9, 3, 8, 0, 6, 4, 1, 5),
    (7, 0, 4, 6, 9, 1, 3, 2, 5, 8),
)


def _verhoeff_ok(digits: str) -> bool:
    """True when ``digits`` carries a valid Verhoeff check digit (UIDAI)."""

    checksum = 0
    for index, character in enumerate(reversed(digits)):
        checksum = _VERHOEFF_D[checksum][_VERHOEFF_P[index % 8][int(character)]]
    return checksum == 0


_GSTIN_ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def _gstin_checksum_ok(value: str) -> bool:
    """True when ``value`` carries a valid GSTIN mod-36 check digit."""

    compact = re.sub(r"\s", "", value).upper()
    if len(compact) != 15 or any(character not in _GSTIN_ALPHABET for character in compact):
        return False
    total = 0
    for index, character in enumerate(compact[:14]):
        product = _GSTIN_ALPHABET.index(character) * (1 if index % 2 == 0 else 2)
        total += product // 36 + product % 36
    return (36 - total % 36) % 36 == _GSTIN_ALPHABET.index(compact[14])


def _make_recognizer(entity_type: str, regex: str, context: tuple[str, ...]) -> PatternRecognizer:
    return PatternRecognizer(
        supported_entity=entity_type,
        patterns=[Pattern(name=entity_type.lower(), regex=regex, score=0.85)],
        context=list(context),
    )


_RECOGNIZERS: list[PatternRecognizer] = [
    _make_recognizer(entity_type, regex, context)
    for entity_type, regex, context in RECOGNIZER_SPECS
]

_ENGINE: AnalyzerEngine | None = None


def get_engine() -> AnalyzerEngine:
    global _ENGINE
    if _ENGINE is None:
        registry = RecognizerRegistry(recognizers=_RECOGNIZERS)
        _ENGINE = AnalyzerEngine(registry=registry)
    return _ENGINE


def recognize(text: str) -> list[dict[str, Any]]:
    """Run the India recognizers over ``text`` and return normalized hits."""
    engine = get_engine()
    results = engine.analyze(text=text, language="en", entities=[e for e, _, _ in RECOGNIZER_SPECS])

    hits: list[dict[str, Any]] = []
    for result in results:
        entity_type = _as_type_name(result.entity_type)
        entity = EntityType(entity_type)
        start = int(result.start)
        end = int(result.end)
        context = _as_context(entity_type)
        if entity is EntityType.AADHAAR and not _is_valid_aadhaar(start, end, text):
            continue
        if context and not _has_context(text, start, end, context):
            # A checksum-valid identifier is self-identifying, so machine
            # translation cannot break detection by renaming the label.
            span = text[start:end]
            if entity is EntityType.AADHAAR:
                # Only the grouped form (4-4-4) is accepted without a label:
                # contiguous 12-digit numbers collide with bank accounts, and
                # UIDAI prints Aadhaar in groups.
                if not re.search(r"[\s-]", span) or not _verhoeff_ok(
                    re.sub(r"[\s-]", "", span)
                ):
                    continue
            elif entity is EntityType.GSTIN:
                if not _gstin_checksum_ok(span):
                    continue
            else:
                continue
        hits.append(
            {
                "type": entity,
                "start": start,
                "end": end,
                "score": float(result.score),
                "source": "presidio",
            }
        )
    return hits

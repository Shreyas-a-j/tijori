"""Local masking for spans that on-device translation could not convert.

NLLB leaves proper nouns (names, street names, state names) in the source
script. Forwarding them would send native-script personal data to the model, but
refusing the whole document makes routine Tamil and Kannada uploads unusable.

Instead, replace each surviving native-script run with a local placeholder such
as ``<NATIVE_1>`` before the gateway runs, and substitute the original text back
into the final answer. The model never sees the native characters; the user
still gets the complete document back.
"""

from __future__ import annotations

import re

from ingest.language import NATIVE_RANGES, contains_supported_non_latin_script
from ingest.translate import TranslationUnavailable

_NATIVE_CHAR = (
    "["
    + "".join(f"\\U{low:08X}-\\U{high:08X}" for low, high in NATIVE_RANGES)
    + "]+"
)
_NATIVE_RUN = re.compile(_NATIVE_CHAR)
_TOKEN = "<NATIVE_{}>"


def mask_native_spans(text: str) -> tuple[str, dict[str, str]]:
    """Replace every native-script run with a placeholder.

    Returns the masked text and the placeholder-to-original mapping. The mapping
    stays in the UI process; it is never sent to the gateway or written to the
    audit table.
    """

    mapping: dict[str, str] = {}

    def replace(match: re.Match[str]) -> str:
        token = _TOKEN.format(len(mapping) + 1)
        mapping[token] = match.group(0)
        return token

    masked = _NATIVE_RUN.sub(replace, text)
    if contains_supported_non_latin_script(masked):
        # Fail closed: an unmasked native word would reach the gateway.
        raise TranslationUnavailable("native-script text survived local masking")
    return masked, mapping


def restore_native_spans(text: str, mapping: dict[str, str]) -> str:
    """Put the original native-script runs back into a finished answer."""

    if not text or not mapping:
        return text
    # Longest first so <NATIVE_1> cannot eat the prefix of <NATIVE_10>.
    for token in sorted(mapping, key=len, reverse=True):
        text = text.replace(token, mapping[token])
    return text

"""Local masking of native-script runs that NLLB leaves untranslated."""

from __future__ import annotations

from ingest.native import mask_native_spans, restore_native_spans

MIXED = (
    "Residential address: E-11, வைஶாலி நகர், அஜ்மர் சாலை, Jaipur, ராஜஸ்தான் 302021"
)


def test_masks_each_native_run_and_keeps_latin_text() -> None:
    masked, mapping = mask_native_spans(MIXED)

    assert masked == (
        "Residential address: E-11, <NATIVE_1> <NATIVE_2>, <NATIVE_3> "
        "<NATIVE_4>, Jaipur, <NATIVE_5> 302021"
    )
    assert mapping["<NATIVE_1>"] == "வைஶாலி"
    assert not any("\u0B80" <= ch <= "\u0BFF" for ch in masked)


def test_restore_round_trips() -> None:
    masked, mapping = mask_native_spans(MIXED)

    assert restore_native_spans(masked, mapping) == MIXED


def test_restore_handles_nested_gateway_output() -> None:
    masked, mapping = mask_native_spans("Address: <NATIVE_1>, Bengaluru")

    answer = "The applicant lives at <ADDRESS_1> and works nearby."
    restored = restore_native_spans(
        answer.replace("<ADDRESS_1>", "வைஶாலி நகர், Bengaluru"), mapping
    )

    assert restored == "The applicant lives at வைஶாலி நகர், Bengaluru and works nearby."


def test_english_text_is_untouched() -> None:
    masked, mapping = mask_native_spans("Hello, my Aadhaar is 1234 5678 9012.")

    assert masked == "Hello, my Aadhaar is 1234 5678 9012."
    assert mapping == {}


def test_restore_without_mapping_returns_input() -> None:
    assert restore_native_spans("text", {}) == "text"

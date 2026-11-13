"""India-specific Presidio recognizer tests (positive + negative per type)."""

from __future__ import annotations

from app.contracts import EntityType
from privacy.detection.india import recognize

AADHAAR_POSITIVE = "My aadhaar number is 2234 5678 9012 and I filed it."
AADHAAR_NO_CONTEXT = "The number 223456789012 looks fine today."
AADHAAR_BAD_FIRST_DIGIT = "My aadhaar number is 123456789012 filed today."

PAN_POSITIVE = "Income tax PAN is ABCDE1234F for the filing."
PAN_NO_CONTEXT = "The code ABCDE1234F appears in the letter."

GSTIN_POSITIVE = "GSTIN 27AAPFU0939F1ZV was issued to the company."
GSTIN_BAD_CHECKSUM = "27AAPFU0939F1ZW"
GSTIN_NO_CONTEXT = f"The code {GSTIN_BAD_CHECKSUM} looks fine today."

VOTER_ID_POSITIVE = "My voter id is ABC1234567 and I voted."
VOTER_ID_NO_CONTEXT = "The id ABC1234567 looks fine today."

PASSPORT_POSITIVE = "Passport number J1234567 was submitted."
PASSPORT_NO_CONTEXT = "The number J1234567 looks fine today."


def _types(text: str) -> list[str]:
    return [hit["type"].value for hit in recognize(text)]


def _hits(text: str, entity_type: EntityType):
    return [h for h in recognize(text) if h["type"] == entity_type]


def test_aadhaar_positive_detected() -> None:
    hits = _hits(AADHAAR_POSITIVE, EntityType.AADHAAR)
    assert len(hits) == 1
    assert hits[0]["start"] < hits[0]["end"]
    assert hits[0]["end"] - hits[0]["start"] > 0


def test_aadhaar_without_context_not_detected() -> None:
    assert EntityType.AADHAAR.value not in _types(AADHAAR_NO_CONTEXT)


def test_aadhaar_translated_labels_are_detected() -> None:
    for text in (
        "The number of applicants: 8987 9730 9114",
        "Based number: 8987 9730 9114",
        "The number of bases: 6252 4776 4728",
        "Aadhaar numbers: 8987 9730 9114",
    ):
        assert EntityType.AADHAAR.value in _types(text)


def test_aadhaar_unlabelled_grouped_number_is_not_detected() -> None:
    # Fails the Verhoeff check, so it is not a UIDAI number; without a label it
    # stays unmasked rather than over-triggering.
    assert EntityType.AADHAAR.value not in _types(
        "The total is 8987 9730 9115"
    )


def test_aadhaar_checksum_valid_number_without_label_is_detected() -> None:
    # UIDAI numbers carry a Verhoeff check digit, so a translated label is not
    # required to recognise one.
    assert EntityType.AADHAAR.value in _types("Reference 3465-9085-3805 on file.")


def test_aadhaar_contiguous_number_without_label_is_not_detected() -> None:
    # Bank accounts share the 12-digit shape; only the grouped Aadhaar form is
    # accepted without a label.
    assert EntityType.AADHAAR.value not in _types("Reference 732080737028 on file.")


def test_aadhaar_invalid_first_digit_not_detected() -> None:
    assert EntityType.AADHAAR.value not in _types(AADHAAR_BAD_FIRST_DIGIT)


def test_pan_positive_detected() -> None:
    hits = _hits(PAN_POSITIVE, EntityType.PAN)
    assert len(hits) == 1
    assert hits[0]["start"] < hits[0]["end"]


def test_pan_shape_without_context_not_detected() -> None:
    assert EntityType.PAN.value not in _types(PAN_NO_CONTEXT)


def test_pan_context_is_not_matched_by_prefix_words() -> None:
    assert EntityType.PAN.value not in _types("The panel code ABCDE1234F appears.")


def test_gstin_positive_detected() -> None:
    hits = _hits(GSTIN_POSITIVE, EntityType.GSTIN)
    assert len(hits) == 1


def test_gstin_without_context_not_detected() -> None:
    assert EntityType.GSTIN.value not in _types(GSTIN_NO_CONTEXT)


def test_gstin_translated_label_variants_are_detected() -> None:
    for text in (
        "Business GSTN: 07INSPP8851Q1ZH",
        "Trade GSTN: 33OWWPR9440I1ZD",
        "Business GSTIN: 09NRNPK2288M1ZN",
    ):
        assert EntityType.GSTIN.value in _types(text)


def test_gstin_split_by_a_space_is_detected() -> None:
    text = "Trade GSTIN: 19 USCPN3937R1ZD Amount of loan requested: Rs 7,50,000"
    hits = _hits(text, EntityType.GSTIN)
    assert len(hits) == 1
    assert "USCPN3937R1ZD" in text[hits[0]["start"] : hits[0]["end"]]


def test_voter_id_positive_detected() -> None:
    hits = _hits(VOTER_ID_POSITIVE, EntityType.VOTER_ID)
    assert len(hits) == 1


def test_voter_id_without_context_not_detected() -> None:
    assert EntityType.VOTER_ID.value not in _types(VOTER_ID_NO_CONTEXT)


def test_passport_positive_detected() -> None:
    hits = _hits(PASSPORT_POSITIVE, EntityType.PASSPORT)
    assert len(hits) == 1


def test_passport_without_context_not_detected() -> None:
    assert EntityType.PASSPORT.value not in _types(PASSPORT_NO_CONTEXT)


def test_plural_passport_context_is_detected() -> None:
    assert EntityType.PASSPORT.value in _types("Passports: Q9238128")


def test_translated_pass_number_label_is_detected() -> None:
    assert EntityType.PASSPORT.value in _types("Pass number: J6312624")

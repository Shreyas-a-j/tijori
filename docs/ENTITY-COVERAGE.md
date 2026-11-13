# PII entity coverage vs Microsoft Presidio

Reference taxonomy: [Presidio supported entities](https://github.com/microsoft/presidio/blob/main/docs/supported_entities.md)
(checked November 2026). Contract taxonomy: `CONTRACT.md` §2 and
`app/contracts.py::EntityType`.

Tijori uses Presidio as the recognizer framework but registers **its own India
patterns** (`privacy/detection/india.py`) rather than enabling Presidio's
prebuilt India recognizers, so that validation (Aadhaar Verhoeff, GSTIN checksum)
is under our control.

## Summary

| Category | Presidio entities | Tijori types | Covered |
|---|---|---|---|
| India-specific | 6 | 5 | **5 / 6** — `IN_VEHICLE_REGISTRATION` missing |
| Global person/contact | 4 | 4 | 4 / 4 (`PERSON`, `LOCATION`→`ADDRESS`, `PHONE_NUMBER`→`PHONE`, `EMAIL_ADDRESS`→`EMAIL`) |
| Global financial | 3 | 2 | 2 / 3 (`CREDIT_CARD`; `IBAN_CODE` missing) |
| Global technical | 6 | 0 | 0 / 6 (`IP_ADDRESS`, `URL`, `UUID`, `MAC_ADDRESS`, `CRYPTO`, `NRP`) |
| Global other | 3 | 1 | 1 / 3 (`DATE_TIME`→`DOB`; `MEDICAL_LICENSE` missing) |
| Tijori-only | — | 3 | `BANK_ACCOUNT`, `ADDRESS` heuristic, `OTHER` |

## India-specific entities

| Presidio entity | Tijori type | Recognizer | Validation | Status |
|---|---|---|---|---|
| `IN_AADHAAR` | `AADHAAR` | 12 digits with optional spaces/hyphens; context-gated unless the grouped form passes the checksum | First digit 2–9, Verhoeff checksum, non-palindrome | **Covered** |
| `IN_PAN` | `PAN` | `[A-Z]{5}[0-9]{4}[A-Z]`, context-gated | Format + context | **Covered** |
| `IN_GSTIN` | `GSTIN` | 15 chars: state code + PAN + entity + `Z` + check char; accepts a single space after the state code | Format + state/PAN structure + checksum | **Covered** |
| `IN_VOTER` | `VOTER_ID` | EPIC: 3 letters + 7 digits, context-gated | Format + context | **Covered** |
| `IN_PASSPORT` | `PASSPORT` | 1 letter + 7 digits, context-gated | Format + context | **Covered** |
| `IN_VEHICLE_REGISTRATION` | — | — | — | **Gap** |

`IN_VEHICLE_REGISTRATION` (RC number, e.g. `MH12AB1234`) is personal data when
linked to a vehicle owner, and it appears in Indian KYC, insurance and support
documents. It is currently missed; the demo dataset contains none, so the
measured recall numbers do not reflect this gap.

## Global entities

| Presidio entity | Tijori type | Status | Note |
|---|---|---|---|
| `PERSON` | `PERSON` | Covered | GLiNER + spaCy union |
| `LOCATION` | `ADDRESS` | Covered (custom) | Address heuristic in `patterns.py`; `LOCATION` is broader than an address |
| `PHONE_NUMBER` | `PHONE` | Covered | Indian mobile/landline patterns; recall 0.947 |
| `EMAIL_ADDRESS` | `EMAIL` | Covered | RFC-ish pattern |
| `CREDIT_CARD` | `CREDIT_CARD` | Covered | Luhn checksum |
| `DATE_TIME` | `DOB` | Partial | Only dates near birth/DOB context; generic dates are not personal data by default |
| `IBAN_CODE` | — | Not covered | Not present in Indian retail documents |
| `IP_ADDRESS` | — | Not covered | Personal data in some contexts; low priority for the demo |
| `URL` | — | Not covered | Not personal data by itself |
| `UUID` | — | Not covered | Identifier only if mapped to a person |
| `MAC_ADDRESS` | — | Not covered | Not in scope |
| `CRYPTO` | — | Not covered | Not in scope |
| `NRP` | — | Not covered | Sensitive attribute; DPDP does not create a special category, but context matters |
| `MEDICAL_LICENSE` | — | Not covered | Not in dataset |
| `MEDICAL_*` (NER) | — | Not covered | Requires the Presidio medical model; out of scope |

## Tijori-only entities

| Type | Basis |
|---|---|
| `BANK_ACCOUNT` | Indian account-number heuristics near "account"/"A/c" context |
| `ADDRESS` | Multi-line Indian address heuristic (pin code, locality keywords) |
| `OTHER` | Residual identifiers (policy/customer ids) — low precision by design |

## Evidence from the evaluation run

Gold spans in `data/dataset.jsonl` (50 documents):

| Type | Gold | Recall |
|---|---|---|
| AADHAAR | 32 | 1.000 |
| PAN | 32 | 1.000 |
| GSTIN | 10 | 1.000 |
| VOTER_ID | 13 | 1.000 |
| PASSPORT | 14 | 1.000 |
| PERSON | 50 | 1.000 |
| ADDRESS | 42 | 1.000 |
| PHONE | 38 | 0.947 |
| EMAIL | 38 | 1.000 |
| CREDIT_CARD | 12 | 1.000 |
| BANK_ACCOUNT | 19 | 1.000 |
| DOB | 38 | 1.000 |
| OTHER | 24 | 0.500 |

These are exact-span, exact-type scores on synthetic data. They show the pipeline
works; they are not a production benchmark.

## Adding a missing type (post-freeze)

`EntityType` and `MASKED_TYPES`/`PLACEHOLDER_PATTERN` in `app/contracts.py` are
frozen by the contract. Adding a type (for example `VEHICLE_REG`) requires:

1. `app/contracts.py`: add the enum member, priority position, placeholder
   pattern, and literal.
2. `privacy/detection/`: a Presidio `PatternRecognizer` with an Indian state
   code list and format check (`^[A-Z]{2}[0-9]{1,2}[A-Z]{1,3}[0-9]{4}$` plus
   Bharat Series `YY BH #### XX`).
3. `data/dataset.jsonl` + `data/generate.py`: gold examples, including the
   Bharat Series format.
4. `evaluation/run.py`: the per-type table picks the new type up automatically.
5. Tests: positive, negative (PAN-like strings), overlap with `OTHER`.

Estimate: 1–2 hours. Do this only after the demo is frozen; it changes the frozen
taxonomy and invalidates the current metrics table.

## Recommendation

| Priority | Gap | Why |
|---|---|---|
| P1 | `IN_VEHICLE_REGISTRATION` | Common in Indian KYC/insurance; high identifiability |
| P2 | API auth + audit retention/purge | Rule 6(1)(b), 6(1)(e) — see `DPDP-ALIGNMENT.md` |
| P3 | `IP_ADDRESS` | Only when logs are processed |
| — | `IBAN`, `CRYPTO`, `MAC`, `URL`, `UUID` | Not in scope for Indian enterprise documents |

# Multilingual intake evaluation

- Generated: 2026-11-13T03:01:29+00:00
- Commit: `1c0040b`
- Documents: 10
- Target languages: Tamil, Telugu, Kannada, Hindi
- Translation model: `facebook/nllb-200-distilled-600M` (CPU, on-device)
- Gateway: reachable

## What this measures

The English dataset text is translated to each target language, passed
through the local extractor and script detector, translated back to
English, and then sent to `/v1/sanitize`. Surviving native-script runs
(names and address words NLLB will not transliterate) are replaced with
local `<NATIVE_n>` placeholders first, exactly as the UI does, so no
native characters reach the gateway. The report measures translation
survival, digit preservation, leakage on the translated path, and recall
for numeric identifiers whose digits survived translation.

It does **not** measure detection precision/recall for native text: there
are no native-language gold labels. Reporting such a number would be
dishonest.

## Per-language results

| Language | Attempts | Translation success | Digit preservation | Leakage | Numeric-ID recall | Native spans masked |
|---|---|---|---|---|---|---|
| Tamil | 10 | 100.0% | 80.8% | 0 | 92.3% | 30 |
| Telugu | 10 | 100.0% | 94.0% | 0 | 100.0% | 5 |
| Kannada | 10 | 100.0% | 96.4% | 0 | 92.9% | 20 |
| Hindi | 10 | 100.0% | 92.8% | 0 | 100.0% | 0 |

## Overall

| Metric | Result |
|---|---|
| Translation success rate | 100.0% |
| Digit-preservation rate | 91.0% |
| Leakage count on translated path | 0 |
| Numeric-ID recall | 96.4% |
| Native-script spans masked locally | 55 |

**Leakage gate:** 0 gold value occurrences in the sanitized translated text. This is the required result for the slice.

## Caveats

- The dataset is English/Hindi-English. Translation quality, not
  detection quality, dominates the round-trip numbers.
- `eng_Latn` is used as the source for Hinglish documents; NLLB may
  leave code-mixed phrases partly untranslated.
- Numeric-ID recall excludes identifiers whose digits did not survive
  translation. Those are translation failures, not detector misses.
- Native-language answers (back-translation of the model output) are
  out of scope; see `docs/INGEST.md`.
- Surviving native-script runs are replaced with local `<NATIVE_n>`
  placeholders before the gateway runs. The model cannot read or
  summarise those spans; it can only repeat the placeholder, which the
  UI restores locally.

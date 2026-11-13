# Prompt — fix multilingual leakage in PR #9 and make it mergeable

You are working in the Tijori repository, a local privacy gateway: it detects
Indian PII in English text, replaces it with typed placeholders
(`<AADHAAR_1>`), sends only sanitized text to an OpenAI-compatible LLM,
reinserts originals locally, and writes a PII-free audit row.

Stack: Python 3.14 `.venv`, FastAPI, Streamlit, SQLite, Presidio + GLiNER +
spaCy, local Ollama (`qwen2.5:3b`).

Read first: `README.md`, `CONTRACT.md`, `docs/INGEST.md`,
`docs/DPDP-ALIGNMENT.md`, `privacy/detection/india.py`,
`privacy/detection/__init__.py`, `ingest/translate.py`, `ingest/language.py`,
`evaluation/multilingual.py`, `reports/multilingual.md`.

## Current state

PR #9 (`piyu859/tijori`, branch `agent/multilingual-ingest`) adds multilingual
intake: local extraction, Indic script detection, on-device NLLB translation,
fail-closed UI, `source_lang` in the audit table. Extraction and security code
are sound. It is a **draft** and must not be merged: its own report fails the
gate with **31** gold values surviving into sanitized text.

```bash
gh pr checkout 9
git switch -c fix/multilingual-leakage
```

Prerequisites on this machine (verify, do not reinstall): `.venv`,
`transformers`, `torch`, `sentencepiece`, cached
`facebook/nllb-200-distilled-600M`, Ollama with `qwen2.5:3b` pulled,
`pdftotext`, `pdftoppm`, `tesseract`.

Start the gateway for evaluation:

```bash
source .venv/bin/activate
uvicorn app.main:app --port 8000 &
```

## Root causes already reproduced (do not re-derive from scratch)

Two round-trips were traced end to end (`loan_001`, Tamil and Hindi); both
translations came back clean with **no native-script letters**, and the
sanitized payload still contained the identifiers. Both are **detector context
gates breaking on machine-translated English**, not translation loss:

1. `AADHAAR='8987 9730 9114'` survives because NLLB rendered the label as
   `"The number of applicants:"` (Tamil) and `"Based number:"` (Hindi). The
   `±40`-character context window in `privacy/detection/india.py` looks for
   `aadhaar|aadhar|uidai` and no longer finds it, so the pattern recognizer
   abstains.
2. `PASSPORT='Q9238128'` survives because the label came back as
   `"Passports:"`. `_has_context` matches with `\bpassport\b`, and the plural
   has no word boundary after `passport`.

A third failure mode is visible in the report: **22 of 40** attempts refused with
`"on-device translation left native-script text in its output"`, including
Tamil at 20 % success. The validator
(`contains_supported_non_latin_script`) fails on **any** native character, so a
single Devanagari danda, a Tamil punctuation mark, or a native digit glyph is
enough to reject an otherwise usable English translation. Your job includes
confirming that hypothesis with the actual rejected outputs before changing it.

## Method

Reproduce → measure → fix → measure again. Do not change detection constants
until you have printed the failing document, the back-translation, and the
sanitized payload.

Add this to `evaluation/multilingual.py` as part of the work, not as a throwaway
script: per-leak detail rows (`document`, `language`, `type`, `value`,
`occurrences`, sanitized context excerpt) and a "Leak detail" section in
`reports/multilingual.md`. Add `--docs`, `--langs`, `--limit` CLI flags so a
single document and language can be debugged without a full run.

## Fixes to implement

Smallest change that makes the failure disappear, with a test per fix.

1. **Context matching must tolerate inflection and paraphrase.**
   Match context words as prefixes/substrings where English morphology demands
   it (plural `passports`, `voters`, `numbers`), and widen the context list for
   Aadhaar to labels NLLB commonly produces: `number of applicants`,
   `based number`, `id number`, `identity number`, `aadhaar number`. Keep the
   `±40` window. Do not drop context requirements entirely — an unlabelled
   12-digit number is not an Aadhaar, and the English false-positive rate is
   measured in `reports/metrics.md`.

2. **Where the value shape is unambiguous, do not require context.**
   A 12-digit number in `4-4-4` grouping is very unlikely to be anything else,
   and a PAN (`[A-Z]{5}[0-9]{4}[A-Z]`) is a fixed shape. Consider a
   high-confidence no-context path for these two only, validated against
   `data/dataset.jsonl` plus a negative sample so the English suite does not
   regress. Justify whichever way you choose in the PR body; do not silently
   lower the bar for `PASSPORT` or `VOTER_ID`, whose shapes collide with
   ordinary numbers and words.

3. **Native-script validator: reject letters, not typography.**
   Fail only when the translation still contains native-script **letters**
   (`unicodedata.category(c).startswith("L")`), plus a small proportion guard
   (for example, reject when native letters exceed ~1 % of letters). Native
   punctuation, dashes, dandas, and native digit glyphs must not block a usable
   English translation. Keep failing closed: real untranslated sentences must
   still raise `TranslationUnavailable`. Do not add a retry loop unless the
   measurement shows it earns its cost.

4. **Default translation off.**
   `TIJORI_TRANSLATE_ENABLED` must default to `0` in `app/config.py` and
   `.env.example`, so an early merge cannot enable the translated path. Update
   the UI copy and `docs/INGEST.md` to say the path is opt-in until the report
   reaches zero leakage.

Before touching any of this, run the existing multilingual evaluation once and
record the baseline numbers so your final report has a real before/after.

## Tests first

Write the failing test before the fix, in the style already used by the repo:

- `tests/platform/test_detection_context.py` (or the existing detection test
  module): `"The number of applicants: 8987 9730 9114"`, `"Based number: 8987
  9730 9114"`, `"Passports: Q9238128"`, and the matching negative cases
  (`"The total is 8987 9730 9114"` must stay unmasked) — assert the same
  behaviour for the ordinary English phrasing so nothing regresses.
- `tests/ingest/test_translate.py`: validator accepts English text with a
  stray danda or a Tamil digit, rejects a sentence that is still mostly Tamil
  letters, and still raises on genuinely untranslated output.
- Keep the existing `tests/ingest`, `tests/demo`, `tests/platform` suites green.

## Acceptance

```bash
source .venv/bin/activate
pytest tests/ingest tests/demo tests/platform -q
pytest -q                                  # full suite, exit 0
python -m evaluation.multilingual          # rewrite reports/multilingual.md
```

Required results:

- Leakage on the translated path: **0** gold value occurrences.
- Translation success rate credible for at least Tamil and Hindi (target
  ≥ 90 %); report Telugu and Kannada honestly, whatever they are.
- Digit preservation reported per language, unchanged methodology.
- `TIJORI_TRANSLATE_ENABLED=0` still refuses a Tamil upload with a clear
  message; English uploads keep working.
- No `/tmp` residue: `ls /tmp | grep -i tijori` is empty after runs.
- `reports/metrics.md` untouched — English detection numbers stay valid, and
  you must prove that by running whatever produced them or by not changing
  English-path behaviour at all.
- `docs/INGEST.md`, `README.md`, and `docs/DPDP-ALIGNMENT.md` reflect the new
  default and the validator semantics.

## Guardrails

- No new Python packages. No cloud OCR, cloud translation, or new network
  dependency.
- Do not modify `CONTRACT.md`, `app/contracts.py` (beyond what PR #9 already
  adds), `app/pipeline/pipeline.py`, or the provider.
- Do not persist extracted or translated text anywhere. Temp files stay `0600`
  inside a per-call `TemporaryDirectory`.
- Do not weaken `leak_occurrences` or the leakage gate to make the number pass.
  If a hit is a false positive, prove it in the report with the context excerpt
  and say so explicitly.
- Do not mark the PR ready or merge it. Hand the human the commands.

## Deliverable

Commit on `fix/multilingual-leakage` with one commit per fix plus one for the
report and docs. Then either push and update PR #9, or give the human:

```bash
git push -u origin fix/multilingual-leakage
gh pr create --base agent/multilingual-ingest --head fix/multilingual-leakage \
  --title "fix(ingest): zero leakage on the translated path" \
  --body "<before/after table, root causes, tests, evidence>"
```

Report at the end: baseline vs final leakage and success rates, the exact
detection and validator changes, and anything still failing. Do not claim zero
leakage unless `reports/multilingual.md` says zero.

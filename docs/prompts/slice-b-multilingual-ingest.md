# Slice B prompt — Multilingual intake and document upload

You are implementing Tijori's multilingual ingest layer on a machine that
already has the project working. Work on a branch, run the tests, open a pull
request, and merge it when green.

## Context you are inheriting

Tijori is a local privacy gateway: it detects Indian PII in English text,
replaces it with typed placeholders (`<AADHAAR_1>`), sends only the sanitized
payload to an OpenAI-compatible LLM, reinserts the originals locally, and writes
a PII-free audit row. Stack: Python 3.14 `.venv`, FastAPI, Streamlit, SQLite,
Presidio + GLiNER + spaCy, local Ollama (`qwen2.5:3b`).

Known-good baseline on `main`:

```bash
source .venv/bin/activate
pytest -q                 # 108 collected, exit 0
uvicorn app.main:app --port 8000
streamlit run ui/app.py
```

Read before writing code: `README.md`, `CONTRACT.md`, `app/contracts.py`,
`privacy/reinsertion/__init__.py`, `ui/app.py`, `tests/demo/test_ui_instruction.py`,
`docs/DPDP-ALIGNMENT.md`, `.env.example`.

Already installed on the target machine (verify, do not reinstall):
`transformers`, `torch`, `sentencepiece`, `PIL`, and the binaries `pdftotext`,
`pdftoppm`, `tesseract`, plus Ollama with the model pulled. There is **no**
`pypdf`, `python-docx`, `pytesseract` — and you must not add them.

## Goal

A user uploads a document from their own machine in a major Indic script
(Tamil, Telugu, Kannada, Malayalam, Hindi, Marathi, Bengali, Gujarati, Punjabi,
Odia). Tijori extracts the text (OCR when the file is a scan), translates it to
English **entirely on-device**, and then runs the existing gateway unchanged, so
the English answer comes back with every identifier restored.

```
upload → extract (local) → detect script → translate to English (local NLLB)
       → existing gateway: detect → mask → LLM → reinsert → English answer
```

## Invariants — tests must enforce these

1. **Nothing leaves the machine.** No network calls in the new code except the
   one-time Hugging Face model download. No cloud OCR, no cloud translation.
2. **Fail closed.** If the text is not English and translation is unavailable or
   failed, refuse with a clear message. Never forward un-translated Indic text to
   the gateway — detection would miss native-script PII and the request would be
   a silent leak.
3. **No persistence of user content.** Extracted and translated text live in
   memory only. Do not add them to the audit table, logs, or disk. Temp files
   (OCR images, `pdftoppm` output) are created `0600` inside a per-call
   `tempfile.TemporaryDirectory()` and removed in a `finally` block.
4. **Do not change existing behaviour.** No edits to detection, masking,
   reinsertion, provider, or the existing request/response fields. No contract
   changes in this slice.
5. **No new Python packages.** DOCX via stdlib `zipfile`, PDF via `pdftotext`,
   images via the `tesseract` CLI, translation via `transformers`.
6. **System packages only with human approval.** Indic OCR needs traineddata
   that this machine does not have. Ask your human to run:

   ```bash
   sudo apt-get install -y tesseract-ocr-tam tesseract-ocr-tel tesseract-ocr-kan \
     tesseract-ocr-mal tesseract-ocr-hin tesseract-ocr-mar tesseract-ocr-ben \
     tesseract-ocr-guj tesseract-ocr-pan tesseract-ocr-ori
   tesseract --list-langs
   ```

   Ask before downloading the ~2.4 GB NLLB weights too. If approval is refused,
   ship text extraction + translation and leave OCR behind a clear "not
   installed" error.

## Milestones

Commit at the end of each milestone. Stop and report if a milestone's acceptance
fails twice.

### M1 — Extraction and upload (target: 2 h)

New package `ingest/`:

```python
# ingest/extract.py
@dataclass(frozen=True)
class Extraction:
    text: str
    filename: str
    pages: int
    ocr_used: bool
    ocr_langs: tuple[str, ...]
    warnings: tuple[str, ...]

class ExtractionError(ValueError): ...

def extract(filename: str, data: bytes) -> Extraction: ...
```

- Limits: 10 MB, 20 pages, 200 000 characters. Reject anything else with a
  human-readable `ExtractionError`.
- Dispatch on lower-cased suffix. Reject path separators in `filename`.
- `.txt`, `.md`, `.csv`: UTF-8 with `errors="replace"`, strip a BOM.
- `.docx`: `zipfile` → `word/document.xml` → regex/`ElementTree` to text,
  `</w:p>` becomes `\n`, `</w:tr>` becomes `\n`. No third-party parser.
- `.pdf`: `pdftotext -layout -enc UTF-8 <tmp> -` (60 s timeout). If the result is
  under ~20 characters per page, treat it as scanned: `pdftoppm -r 200 -png`
  (page cap applied) then OCR each page.
- `.png/.jpg/.jpeg/.tif/.tiff`: OCR directly.
- OCR helper: `subprocess.run(["tesseract", path, "stdout", "-l", langs], ...)`,
  no `shell=True`, 120 s timeout. Build `langs` from `eng` plus installed Indic
  packs (cache `tesseract --list-langs` once per process). Multi-language OCR is
  acceptable because script detection runs on the output.
- Never write the uploaded bytes anywhere except the per-call temp dir.

`tests/ingest/test_extract.py`: txt/md with BOM, DOCX built in-test with
`zipfile`, PDF built by writing a minimal text PDF or skipped if none is
available, unsupported suffix, oversize, empty scan → `ExtractionError`,
temp-dir cleanup (no files left in `/tmp`). OCR test marked `@pytest.mark.slow`
and skipped when Indic langs are absent.

Acceptance: `pytest tests/ingest -q` green; a real DOCX and a real text-layer PDF
extract correctly in a manual check.

### M2 — Script detection and local translation (target: 2.5 h)

```python
# ingest/language.py
@dataclass(frozen=True)
class DetectedLanguage:
    code: str        # "ta", "hi", "en", ...
    script: str      # "Tamil", "Devanagari", ...
    nllb: str        # "tam_Taml", "hin_Deva", "eng_Latn"
    tesseract: str   # "tam", ...
    is_english: bool

def detect_language(text: str) -> DetectedLanguage: ...
```

- Unicode-block counting over a fixed table: Devanagari→hi, Tamil→ta,
  Telugu→te, Kannada→kn, Malayalam→ml, Bengali→bn, Gujarati→gu, Gurmukhi→pa,
  Odia→or, Arabic→ur. Latin-dominant → `en`.
- Document the limitation: romanised Indic ("vanakkam") is classified `en`.

```python
# ingest/translate.py
@dataclass(frozen=True)
class Translation:
    text: str
    source_lang: str
    model: str
    duration_ms: int
    warnings: tuple[str, ...]

class TranslationUnavailable(RuntimeError): ...

def translate_to_english(text: str, detected: DetectedLanguage) -> Translation: ...
```

- `facebook/nllb-200-distilled-600M`, lazy singleton, `torch.inference_mode()`,
  `torch.set_num_threads(4)`, float32, CPU. Load inside the Streamlit process,
  not the gateway: the gateway keeps running unchanged and memory stays flat.
- Split on blank lines and single newlines, translate each chunk with
  `max_length=512`, `num_beams=2`, `forced_bos_token_id=tokenizer.convert_tokens_to_ids("eng_Latn")`,
  rejoin preserving line structure.
- Short-circuit when `is_english` (return the input, zero duration).
- `warnings` must include any digit sequence present in the source but missing
  from the output — the UI shows this, and a missing Aadhaar number is a red flag.
- Map `OSError`/`ImportError`/model download failure to `TranslationUnavailable`;
  never let a raw traceback reach the UI.
- Config in `app/config.py` (read-only addition): `TIJORI_TRANSLATE_MODEL`
  (default above), `TIJORI_TRANSLATE_ENABLED` (default `1`). Document both in
  `.env.example`.

`tests/ingest/test_language.py`: one case per script plus English and romanised
input. `tests/ingest/test_translate.py`: English short-circuit is free and makes
no model call (monkeypatch the model to assert it is untouched); digit-preservation
warning logic; `TranslationUnavailable` mapping. One `@pytest.mark.slow` test that
translates a short Tamil sentence and asserts the output is Latin script and
non-empty — skip when weights are absent.

Acceptance: `pytest tests/ingest -q` green; a manual run translates a real
Tamil paragraph in under ~10 s on CPU.

### M3 — UI wiring and audit language (target: 1.5 h)

`ui/app.py` (sidebar, above the sample loader):

- `st.file_uploader("Upload document", type=["txt","md","csv","docx","pdf","png","jpg","jpeg","tif","tiff"])`.
- On upload: extract → detect → translate, with a spinner. Put the **English**
  text into the editable document box; show the native original and the
  extraction metadata (`pages`, OCR used, language) in an expander.
- Badge the detected language next to the box ("Tamil → English, on-device").
- Render translation warnings (lost digit sequences, OCR empty) as `st.warning`.
- Disable **Run gateway** while translation is pending or failed; show the
  fail-closed message from invariant 2.
- Existing behaviour must not regress: offline path, 401 handling, instruction
  field, audit browser, no key or document text in widgets.

`source_lang` (optional, additive, drop first if behind): add
`source_lang: str = "en"` to `SanitizeRequest`/`ProcessRequest`, store it in a new
audit column with a guarded `ALTER TABLE ... ADD COLUMN` migration
(`PRAGMA table_info`), expose it in the audit browser as a "language" column, and
default to `"en"` everywhere so existing rows and clients keep working.

`tests/demo/test_ui_upload.py` using `AppTest` with `ingest` monkeypatched (no
model load): upload populates the English box, the language badge appears, a
failed translation blocks the run, and the existing offline/auth tests still pass.

Acceptance: `pytest tests/demo tests/ingest -q` green; one manual end-to-end run
from a Tamil `.txt`.

### M4 — Evaluation, docs, PR (target: 1.5 h)

- `evaluation/multilingual.py` → `reports/multilingual.md`. Use 10 dataset
  documents, translate each to Tamil, Telugu, Kannada and Hindi with the local
  model, then run extract → translate → `/v1/sanitize` and report:
  translation success rate, digit-preservation rate, **leakage count on the
  translated path (must be 0)**, and numeric-ID recall. Do not report detection
  precision/recall for native text — you have no native-language gold labels, and
  saying otherwise would be dishonest.
- `docs/INGEST.md`: supported formats, size/page limits, language table, OCR
  install, privacy notes (temp-file handling, no audit persistence, fail-closed),
  and the romanised-script limitation.
- `README.md`: one "Multilingual intake" subsection under Capabilities and a
  short "Uploading documents" block in the demo section. Keep the existing
  licence and structure.
- `docs/DPDP-ALIGNMENT.md`: one sentence — translation and OCR are on-device, so
  no new data processor is introduced; extracted text is never persisted.
- **Do not regenerate `reports/metrics.md`.** Detection on English is unchanged
  and those numbers stay valid.

## Test and acceptance protocol

```bash
source .venv/bin/activate
pytest tests/ingest -q      # new
pytest tests/demo -q        # no regressions
pytest -q                   # 108 + new, exit 0
```

Manual evidence to record in the PR body:

1. Upload a Tamil text document → English summary, all IDs restored.
2. Upload a DOCX and a text-layer PDF → same.
3. Upload a scanned Indic PDF or image → OCR text appears (or the documented
   "tesseract pack not installed" message, if approval was refused).
4. Kill the translation model path (`TIJORI_TRANSLATE_ENABLED=0`) → native
   upload is refused with a clear message; English uploads still work.
5. Confirm no stray files: `ls /tmp | grep -i tijori` is empty after runs.

## Pull request and merge

```bash
git checkout -b agent/multilingual-ingest origin/main
# ... milestone commits ...
git push -u origin agent/multilingual-ingest
gh pr create --base main --head agent/multilingual-ingest \
  --title "feat(ingest): multilingual document upload with on-device translation" \
  --body "<summary, the five evidence items, test counts, model and OCR installs>"
```

Merge only after the full suite and the manual checks pass:

```bash
gh pr merge --squash --delete-branch
```

If your harness blocks `git push` or `gh`, stop and hand the exact commands to
the human instead of working around it. Never force-push `main`.

## Out of scope — do not build

- Native-language **answers** (back-translation). It requires translating the
  masked model output inside the gateway and exposing it before reinsertion; note
  it as a follow-up in `docs/INGEST.md` and leave the pipeline alone.
- Cloud translation, cloud OCR, or any new network dependency.
- Romanised Indic detection, handwriting, tables, spreadsheet formats, `.doc`.
- Changes to detection, masking, reinsertion, the provider, or `reports/metrics.md`.

## Definition of done

- [ ] Upload works for txt/md/csv/docx/pdf/image from the user's machine.
- [ ] Indic text is translated on-device; no request leaves the machine.
- [ ] Translation failure blocks native input instead of leaking it.
- [ ] Temp files are always cleaned up; nothing sensitive is persisted or logged.
- [ ] `pytest -q` green, including the new `tests/ingest` suite.
- [ ] `reports/multilingual.md` shows zero leakage through the translation path.
- [ ] `docs/INGEST.md` and the README section exist.
- [ ] PR merged to `main` (or the human has the exact commands).

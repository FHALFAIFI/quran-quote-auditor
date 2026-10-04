# Arabic OCR benchmark (roadmap Stage 3.2)

**Status (4 Oct 2026, challenge period): no benchmark pages exist; no engine has been measured. OCR is absent from the
interface and off in production.** This folder holds the format, the scorer and a local Tesseract runner only. The
decision framework is in [docs/OCR_DECISION.md](../../docs/OCR_DECISION.md).

Nothing here is imported by `app/`. No OCR text reaches the editor, the audit or the UI. No cloud engine is called
by any script in this folder.

## Files

| File | What it is |
|---|---|
| `manifest.schema.json` | JSON Schema (draft 2020-12) of the benchmark manifest |
| `score_ocr.py` | Scores one engine's run record against the manifest (CER, WER, WER inside Quran quotations, diacritic error rate, "plausible wrong word" rate, time and cost as recorded) |
| `run_tesseract.py` | Runs `tesseract <image> - -l ara` per page **if Tesseract is installed**, and writes a run record. It installs nothing; without `tesseract` on PATH (or without its `ara` data) it exits with code 3 and writes nothing |
| `tests/test_ocr_score.py` (repository root) | Unit tests with tiny synthetic strings; no images |

## What stays out of git

- **Page images** stay outside the repository (a folder passed as `--pages-dir`) unless that page's rights record has
  `may_commit_image: true`. Record `image_sha256` so a run can be tied to the exact file.
- **Ground truth** is a transcription of someone's page and carries the same rights. Keep it outside the repository
  (inline in a manifest kept outside, or files under `--data-dir`) unless `may_commit_ground_truth: true`.
- **Run records and reports** contain the engine's text of the pages: keep them with the pages, not in git, unless
  every page allows its ground truth in.
- `score_ocr.py` refuses a manifest whose uncleared image path or ground truth resolves inside the repository.

## Manifest

One JSON file per frozen set. Example of one page (synthetic; the real set is the owner's to build):

```json
{
  "schema_version": 1,
  "set_id": "ocr-bench-v1",
  "frozen_on": "YYYY-MM-DD",
  "pages": [
    {
      "page_id": "news-001",
      "image_path": "news-001.png",
      "image_sha256": "<64 hex>",
      "category": "newspaper",
      "script": "naskh",
      "diacritics": "partial",
      "ground_truth_path": "gt/news-001.txt",
      "ground_truth_checked_by": ["typist-1", "checker-2"],
      "rights": {
        "source": "<publication, issue, page; or who took the photo>",
        "licence": "<licence or written permission>",
        "cleared_by": "<who checked the rights>",
        "cleared_on": "YYYY-MM-DD",
        "may_commit_image": false,
        "may_commit_ground_truth": false,
        "may_send_to_cloud_engines": false,
        "evidence": "<where the written permission is filed>"
      },
      "quran_spans": [
        {"start": 120, "end": 151, "surah": 94, "ayah_start": 5, "script": "naskh", "printed_as_on_page": true}
      ]
    }
  ]
}
```

Rules:

- `category`: `newspaper`, `bulletin` (mosque bulletins), `book`, `phone_photo`, `screenshot` (social posts), `other`.
  `script` is the script of the Quran quotations (`naskh`, `uthmani`, `mixed`, `other`); `diacritics` is how the page is
  printed (`none`, `partial`, `full`).
- **Ground truth reproduces the page**, including any misprint in a verse; it is never "corrected" to the mushaf. A
  misprint is written in the span's `notes`. Typed by one person and checked against the page by a second person
  (`ground_truth_checked_by` needs two different entries; the scorer enforces it).
- **Spans** are character offsets into the ground truth exactly as stored (Python string indices, end exclusive), with
  the surah and ayah range. They must not overlap and must lie inside the text; the ayah range is checked against the
  Hafs verse counts in `app/surahs.py`. A span that cuts a word in half triggers a warning and the whole word is counted.
- A page whose rights do not allow sending it to a third party (`may_send_to_cloud_engines` not `true`) is run only on
  self-hosted engines; a cloud run that skips it reports it as failed, so its score is not comparable unless the same
  pages are used. Compare engines on the same page list.
- Freeze the manifest (and a `.sha256` of it) before the first engine run; do not edit it afterwards. A later fix is a
  new `set_id`.

## Run record (one per engine run)

```json
{
  "engine": {"name": "tesseract", "version": "...", "lang": "ara", "args": [], "deployment": "self-hosted"},
  "started_at": "2026-...Z",
  "host": {"platform": "...", "cpus": 8},
  "cost_note": "...",
  "pages": [
    {"page_id": "news-001", "text": "...", "seconds": 3.2, "cost": null, "error": null}
  ]
}
```

`text` may be replaced by `text_path` (relative to `--data-dir`). `cost` is `{"amount": <number>, "currency": "<ISO
code>"}` when the run can state it (for a cloud engine: the provider's invoice or usage report for exactly this run);
otherwise `null`. The scorer never estimates a price. A page missing from the run, or with an `error`, is scored as if
the engine returned nothing (every word deleted) and listed under `pages_failed`; it is never skipped.

## Metrics (score_ocr.py)

Words are runs of letters, digits and diacritics; punctuation, brackets (﴿ ﴾ « »), tatweel, zero-width characters and
Quranic pause/annotation marks are not counted (they go through `app.arabic.literal`). Arabic-Indic and ASCII digits
compare equal. Rates pool counts over pages (never an average of per-page rates); the report also gives every page and
groups by `category`, `script` and `diacritics`.

| Metric | Definition |
|---|---|
| `cer_strict`, `cer_letters` | Character edit distance / ground-truth characters, on the words joined by single spaces; strict keeps diacritics, letters removes them |
| `wer_strict`, `wer_letters` | (substitutions + deletions + insertions) / ground-truth words, each from its own word-level Levenshtein alignment |
| `wer_in_quran_spans` | The OCR words are aligned to the ground-truth words (letters level) and each span is projected through the alignment: errors on span words, plus OCR words inserted **between two words of the same span**, / span words. `wer_outside_quran_spans` is the rest. `spans_word_perfect_share` is the share of quotations with no word error |
| `diacritic_error_rate` | For each aligned word pair (match or substitution), base letters are aligned and their sets of marks compared: letters whose marks differ / letters where either side has a mark. Missing and extra marks are also counted. Given separately inside spans |
| `plausible_wrong_*` | A substituted OCR word whose folded form differs from the truth's **and** is in a word list built at run time from the cached Quran text (the app's Quranpedia cache, if present) plus all ground truth of the set. **Approximate**: the list is not a dictionary, misses most Arabic words and may contain rare forms; it undercounts. A substitution that differs only in a folded letter form (hamza seat, ة/ه, ى/ي) is counted as `sub_spelling_variant`, not as plausible-wrong. Per 100 words, as a share of substitutions, and inside spans |
| `time_and_cost` | Seconds and cost per page **as recorded in the run record**; pages without a value are counted as unrecorded |

What it does not measure: reading order across columns beyond what the word alignment absorbs, loss of quotation
brackets ﴿ ﴾ (which the audit uses to find marked quotations), line-break hyphenation, layout, or per-word confidence.
Add them before a decision if the reviewer asks.

## Commands

```bash
# Score an engine run (the app's Quran cache is used for the word list if it exists; nothing is fetched)
python eval/ocr/score_ocr.py --manifest /path/outside/git/manifest.json --run /path/outside/git/run-tesseract.json \
       --out /path/outside/git/report-tesseract.json

# Run Tesseract locally, only if it is installed (this script installs nothing)
python eval/ocr/run_tesseract.py --manifest /path/outside/git/manifest.json --pages-dir /path/outside/git/pages \
       --out /path/outside/git/run-tesseract.json [--psm 6]

# Unit tests
python -m pytest -q tests/test_ocr_score.py
```

On 4 Oct 2026 `which tesseract` found nothing on the development machine, so `run_tesseract.py` has not been run
against any image. A cloud engine needs its own runner written after the owner provides an account, a region and a
signed data-processing agreement (docs/OCR_DECISION.md); none exists.

# Arabic OCR: decision framework (roadmap Stage 3.2)

**Status, 4 Oct 2026 (challenge period): No benchmark pages exist; no engine has been measured; OCR is absent from the
UI and off in production.** This document says how an engine would be chosen, what the owner must provide first, and
what would stop OCR altogether. It records no result.

What exists: the benchmark format, a scorer and a local Tesseract runner in [`eval/ocr/`](../eval/ocr/README.md), with
unit tests on synthetic strings (`tests/test_ocr_score.py`). Tesseract is not installed on the development machine
(`which tesseract` found nothing on 4 Oct 2026), so even the runner has not been run against an image.

## 1. Fixed rules (from the roadmap and the owner)

- OCR text is the writer's text. It goes into the editor as editable text and is audited only after an explicit action.
  **No OCR word is ever replaced by a Quran word without a decision card**; an OCR misreading inside a verse is reported
  by the audit as a *difference* and corrected only if the writer approves.
- No OCR control appears in the interface until the full workflow (Stage 3.3) works and its end-to-end tests pass.
- Order: 3.1 text files → **3.2 this benchmark** → 3.3 scanned PDFs and images. 3.3 starts only if 3.2 finds an engine
  that a reviewer accepts. If none does, OCR stops here.

## 2. Candidates

| Engine | Deployment | Where the page goes | Notes |
|---|---|---|---|
| **Tesseract** with `ara` data | Self-hosted (our server or a worker) | Nowhere outside our host | Open source; check the licence of the exact version and of the `ara` traineddata used. Runner exists (`eval/ocr/run_tesseract.py`). Memory and time per page on a Render instance: not measured |
| **Google Document AI** (Enterprise Document OCR) | Cloud API | The whole image/PDF to Google, in the processor's region | Needs a Google Cloud project, billing, a processor in a chosen region, a service account. Runner not written |
| **Azure AI Document Intelligence** (Read model) | Cloud API | The whole image/PDF to Microsoft, in the resource's region | Needs an Azure subscription, a resource in a chosen region, a key. Runner not written |
| Others the team proposes (for example another self-hosted open-source engine, or a regional provider) | Either | Depends | Added to the same benchmark, on the same pages, with a run record in the same format |

Arabic support, region availability and data-retention terms of each cloud service were **not checked** for this
document; they are to be read on the provider's own pages when an account is opened, with the date of reading.

### Prices (read on the provider's page, or "not read")

| Engine | Price | Read where, when |
|---|---|---|
| Tesseract | No licence fee; cost is our own compute (not measured) | — |
| Azure AI Document Intelligence, Read | Free tier (F0): "0 - 500 pages free per month". Paid tier (S0) per-1,000-page price: **not rendered** when read (the page showed "$-") | https://azure.microsoft.com/en-us/pricing/details/ai-document-intelligence/, read 4 Oct 2026 |
| Google Document AI, Enterprise Document OCR | **Not read** (the page's text was truncated in the tool used on 4 Oct 2026) | https://cloud.google.com/document-ai/pricing, attempted 4 Oct 2026 |

Cost per page in the decision must come from a run record (the provider's usage report for that run), not from a
price list.

## 3. Metrics (computed by `eval/ocr/score_ocr.py`)

1. **WER inside Quran quotations** (`wer_in_quran_spans`) — the deciding metric, with `spans_word_perfect_share`.
2. **"Plausible wrong word" rate**, overall and inside quotations — the dangerous error: an OCR word that is a different
   valid word looks like the writer's own misquotation. Measured approximately (word list from the Quran text plus the
   set's ground truth; it undercounts).
3. **Diacritic error rate**, overall and inside quotations (matters for fully vowelled Quran text).
4. CER and WER overall (strict and letters-only).
5. Time per page and cost per page, from the run record.
6. Every metric broken down by page category (newspaper, bulletin, book, phone photo, screenshot), script (Naskh,
   Uthmani) and diacritics level. An engine that is good on print and fails on phone photos is reported that way.

## 4. Acceptance threshold — a proposal for a reviewer to confirm or change

These numbers are **proposals by the author's coding assistant, not validated values**; a reviewer (the owner or a
person the owner names) confirms or replaces them **before** any engine is run, and the confirmed values are written
here with the reviewer's name and date.

| Gate | Proposed threshold | Why |
|---|---|---|
| WER inside Quran quotations, pooled over the 60 pages | ≤ 2% | Each wrong word becomes a decision card the writer must settle; above this the writer spends more time correcting OCR than checking quotations |
| WER inside quotations, worst category (e.g. phone photos) | ≤ 5%, or that category is declared unsupported in `/limitations` | Avoid one good category hiding a bad one |
| Plausible-wrong words inside quotations | ≤ 0.5 per 100 quotation words | These look like real misquotations by the writer |
| Diacritic error rate inside fully vowelled quotations | Reported; no gate unless the reviewer sets one | The audit already compares letters separately from marks |
| Overall WER (letters) | Reported; no gate | Prose errors are the writer's to fix and do not affect quotation checks |
| Pages failed | 0 on pages the engine is allowed to see | A failure is scored as all words deleted anyway |
| Time per page | ≤ 15 s median on the deployment target | The audit itself takes up to about 25 s for 20,000 characters on the free server |
| Cost | Within a monthly page cap the owner sets | The owner decides who pays |

If no engine passes the confirmed thresholds, the written outcome is "OCR not adopted", with the numbers, and Stage 3.3
does not start.

## 5. The 60-page set: rights requirements

At least 60 pages: newspaper columns, mosque bulletins, printed books, phone photos of print, screenshots of social
posts; Quran quotations in Naskh and Uthmani fonts, with and without diacritics.

For **every** page, before it is used:

- a rights record in the manifest: source, licence or written permission, who cleared it, date (schema in
  `eval/ocr/manifest.schema.json`);
- whether the image and the transcription may be published in the public repository (`may_commit_image`,
  `may_commit_ground_truth`); by default **no**, and both stay outside git;
- whether the page may be sent to a third-party OCR service (`may_send_to_cloud_engines`). A page without that
  permission is used only for self-hosted engines, and engines are compared only on pages all of them were allowed to
  see;
- no page showing private individuals' names, faces, phone numbers or addresses unless they agreed; a screenshot of a
  social post needs the author's agreement or a licence that covers it, not only the platform's terms;
- ground truth typed by one person and checked against the page by a second person; misprints reproduced, not fixed.

Material of uncertain rights is not used, and is never committed (project rule; see SOURCES.md).

## 6. Privacy and transfer, per engine

| Engine | Transfer | What `/privacy` would have to say before the flag is on |
|---|---|---|
| Tesseract, self-hosted | None: the image stays on our host, in memory only (to be checked with a tmpfs probe and a log grep, roadmap 3.3) | That the image is processed on our server, not stored, and not sent elsewhere |
| Google Document AI | The whole image/PDF to Google, in the chosen region, under Google Cloud's terms and a signed data-processing agreement | The provider, the region, the retention setting, and that an image can contain far more than the article (names, faces, letterheads) |
| Azure Document Intelligence | The whole image/PDF to Microsoft, in the chosen region, under Microsoft's terms and a signed data-processing agreement | Same as above |

Today `/privacy` says nothing about OCR because there is none. It must change in the same commit that turns any OCR
flag on. A PDPL review is needed before a cloud engine is used on users' files (roadmap Stage 4).

## 7. What the owner must decide and provide

Nothing below exists; no assistant session can create it.

1. **The 60 rights-cleared pages**, with a rights record for each (who cleared them and when), and where they are kept
   outside git.
2. **Ground truth** for each page, typed by one person and checked by a second (two named people or role codes), and
   the Quran-quotation spans marked with surah and ayah.
3. **A reviewer** who confirms or changes the thresholds in §4 before any engine is run.
4. For **Tesseract**: a machine where it may be installed (the development machine has none), and later an instance
   with enough memory (not measured).
5. For each **cloud engine**: an account, billing, a resource or processor in a chosen region, a key or service
   account (stored as a secret, never in git), a signed data-processing agreement, the retention setting, and a page
   cap for the benchmark run.
6. The decision on who pays per page in production and the monthly page cap.

## 8. Exit record (to be filled when the benchmark is run)

| Field | Value |
|---|---|
| Set id and manifest checksum | — |
| Thresholds confirmed by, date | — |
| Engines run (name, version, region, date) | — |
| Results per engine (report files, kept outside git) | — |
| Chosen engine, or "OCR not adopted" | — |
| Rejected options and why | — |
| Reviewer sign-off | — |

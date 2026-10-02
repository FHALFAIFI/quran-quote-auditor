# مدقق الاقتباسات القرآنية — Quran Quotation Auditor

An Arabic, right-to-left web tool that checks the **wording** and the **reference** of Quran quotations in a short
Arabic article or social post against the Hafs text served by [Quranpedia](https://quranpedia.net), proposes corrections
taken only from that text, and lets an editor approve them one by one.

**AI Challenge Serving Islamic Content 2026 — Track 4: knowledge and verification tools.**

| | |
|---|---|
| **Live demo** | https://quran-quote-auditor.onrender.com (Render Free sleeps when idle: one measurement after 18 idle minutes took 23 s for the first page, so allow up to a minute; open it, wait for the page, then audit) |
| **Source code** | https://github.com/FHALFAIFI/quran-quote-auditor |
| **Licence** | MIT (code). The Quran text is not included. See [SOURCES.md](SOURCES.md) |

> **Pre-challenge work.** Everything in this repository was built **before 4 October 2026**: the git tag
> `pre-challenge-baseline` marks the first baseline commit, and every later commit dated before 4 October (the Groq
> provider, the editor workflow, the unmarked-phrase search, the boundary rules, the AI-provenance rules, the Uthmani-script matching and the interface revision of 2 October) is also
> pre-challenge work. Only work committed during 4–6 October 2026 counts as challenge work.
> See [BASELINE.md](BASELINE.md) and [CHANGELOG.md](CHANGELOG.md).
> Built by one participant with Claude Code as a coding assistant; Claude is not used at runtime.

## What it does

You paste an Arabic article or post. The app:

1. finds likely Quran quotations: marked ones (﴿﴾, {}, «» after a cue or before a reference), and unmarked phrases, shown as a *candidate* or as «قد يكون اقتباسًا قرآنيًا — يحتاج مراجعة» (*possible*). It also finds the surah/ayah reference written next to a quotation;
2. checks each quotation's **wording** and **reference** against Quranpedia's Hafs text;
3. shows one review list, with what needs the editor first: the quotation in the article, the source verse, the exact difference, the reference status and the action asked of the editor. A quotation copied in the **Uthmani script** of a mushaf site or app (`ٱلصَّلَوٰةَ`, `ءَامَنُوا۟`) is matched when its words are the source's words, and gets no correction ([docs/UTHMANI.md](docs/UTHMANI.md));
4. proposes **source-backed corrections** only when the source supports both the text and the location. The editor **approves or rejects each one**; a before/after preview and a copy button give the corrected text;
5. offers a printable **review record** («سجل مراجعة الاقتباسات») and a copy-only reply draft. The app never posts anything.

Optionally a language model (Groq) proposes *where* quotations may be. It is never a source of Quran text, references or verdicts.

## Try it (about two minutes)

1. Open https://quran-quote-auditor.onrender.com. **Render Free sleeps when idle**: if the page is slow (23 s in the one measurement I made, so allow up to a minute), wait for it, and expect the first audit afterwards to take a few seconds more (the Quran text is downloaded once).
2. Paste this post into the text box (or pick a sample from «مثال جاهز») and press «دقّق الاقتباسات»:

```
الصبر والعمل الصالح مفتاح الفرج.

قال تعالى: ﴿وافعلوا الشر لعلكم تفلحون﴾ [الحج: 77]

وقال سبحانه: ﴿فإن مع العسر يسرا﴾ [الشرح: 6]

وتذكّر قول الله تعالى إن الله مع الصابرين.
```

3. Expected (deterministic, with or without the model): three findings, all marked «يحتاج مراجعة». (1) «الشر» is not in the verse: the card shows the closest verse, the word difference and a proposed replacement «الخير» taken from the source. (2) The reference «الشرح: 6» does not match the quoted verse; the proposed fix is «الشرح: 5». (3) «إن الله مع الصابرين» «may be a quotation» and occurs in two verses (البقرة: 153, الأنفال: 46), so **no correction is proposed until you choose the verse** with «هذا هو الموضع».
4. Approve the proposals you accept, look at the before/after preview, and press «نسخ المقال المعدّل». Nothing changes without your approval.
5. A notice at the top of the results says whether the AI model responded. If Groq's free tier answered 429 it says so and the audit continues without the model. On the live demo the model sometimes proposes nothing for this post; the notice then says so, and the result is the deterministic one.

## What it does not claim

- It does **not** say an article or post is "verified" or ready to publish. It checks only the quotations it found.
- **Detection is not complete.** Short unmarked misquotations may be only «possible» or missed; ordinary prose can reuse Quran words and be shown as «possible»; the start or end of an unmarked quotation may need the editor's confirmation (shown as «غير محسوم — حدود الاقتباس»); a model can fail (see "AI use"). The editor can highlight any phrase and check it by hand.
- A «possible» phrase is **not** a verified quotation, and gets no replacement text until the editor confirms it and picks the verse.
- **Uthmani script is recognised only as far as the documented rules go** ([docs/UTHMANI.md](docs/UTHMANI.md)). Before the change on 2 October 2026 (pre-challenge) a correct Uthmani quotation was shown as «difference» or «uncertain» and could get a wrong correction (30 of 41 on the frozen Uthmani set). Now 37 of those 41 read «matched», and none of the other 8 wrong quotations is. The rules explain 99.2% of the verses of the Tanzil Uthmani text (SOURCES.md §1b) and 98.8% of Quranpedia's Uthmani edition; about 50 rare spellings are not covered and read «uncertain» with no replacement. The held-out set was no longer untouched after its first run, and it contains label errors, so these figures are not an independent accuracy rate. A genuinely changed word, a different vowel or a wrong reference in Uthmani text is still flagged.
- It does not proofread Arabic, interpret verses, translate, or give religious rulings.
- **No measured accuracy.** The only numbers are from small, author-written, labelled sets (below). They are not independent measurements, and the labels are still awaiting review by an Arabic specialist ([docs/LABEL_REVIEW.md](docs/LABEL_REVIEW.md)).
- **No measured AI benefit.** On the live demo sample the model proposed the same 7 quotations that the deterministic path found without it. In the labelled sets, with the phrase search in place, it added one quotation (a 3-word misquotation) in one run on one set, and none on the other two.

## Results observed so far (all pre-challenge, no AI; code as of `cccd084`)

Rerun on 2 October 2026 with `eval/run_eval.py --mode fallback`; labels unchanged, checksums verified. For the first three sets the **rows are byte-identical to the run on `976395e`** (before the Uthmani layer), so the Uthmani layer changed nothing for plain-spelling or imla'i-vocalised text. Raw files in `eval/results/`.

| Set (author-written, small) | Quotations | Found | Notes |
|---|---|---|---|
| Main, 14 articles (development data) | 28 | 27 | 0 false "matched" wording; 6/6 wording errors given a correct source-backed fix; 0 corrections proposed for correct text |
| Held-out, 4 articles (development data) | 6 | 6 | 3 of 6 read "uncertain" (boundary not settled) |
| Frozen, 49 articles (written and checksummed before the search was built) | 32 unmarked | 30 | 2 missed; 12 of the 30 found read "uncertain"; 2 of 28 non-Quran texts shown as «possible», none shown as confirmed; 0 misquotations reported "matched" |
| **Uthmani, 50 articles** (excerpts of the Tanzil Uthmani text, SOURCES.md §1b; written and checksummed before any Uthmani code; **no longer untouched after its first run; the labels were not edited after the freeze and 4 of them disagree with the program: `u32`, `u09`, `u10`, `u19`, see docs/UTHMANI.md**) | 49 (41 correct, 8 wrong) | 48 | correct: 37 «matched», 2 «uncertain» (boundary rule), 1 «difference» (label error: the quote omits a word), 1 not found (formula); wrong-labelled: 8 «difference», **0 «matched»**; wrong references flagged 4/4; automatic corrections given to correct quotations **30 → 1** (that one is the label error). Before the change: 1 «matched», 30 corrections |

Costs of the cautious rules: many correct unmarked quotations after prose read "uncertain" and need one click to confirm.
Ordinary Islamic-topic prose produces about 2–3 «possible» items per 1,000 words (Arabic Wikipedia sample, local only). Details, runs that did not count, and limits: [docs/EVALUATION.md](docs/EVALUATION.md). Dated end-to-end logs, including the live Render checks: [docs/TEST_LOG.md](docs/TEST_LOG.md).

---

## ملخص بالعربية

أداة تساعد المحررين والمراجعين على التحقق من الآيات المقتبسة في المقالات العربية القصيرة.
تستخرج الأداة الاقتباسات المحتملة وإحالاتها، ثم تقارنها بنص مصحف حفص من «الموسوعة القرآنية»
(Quranpedia)، وتعرض لكل اقتباس ما يلي:
- حالة الألفاظ: مطابق (حرفيًا، أو بتجاهل التشكيل، أو بعد توحيد الرسم)، أو اختلاف، أو غير محسوم.
- حالة الإحالة: مطابقة، أو غير مذكورة، أو خاطئة، أو غير محسومة.

دور الذكاء الاصطناعي محصور في **اقتراح مواضع الاقتباس** فقط. لا يُعتمد عليه مصدرًا لنص القرآن
ولا حكمًا على الصحة. وكل مطابقة تقريبية تُعلَّم «يحتاج مراجعة»، ولا توصف أبدًا بأنها «مطابقة».

### What "verified" means here

- **Verified** refers only to a quotation's **wording** and **reference**, checked by deterministic code
  against the Hafs text from Quranpedia. Every Quran word, surah/ayah number and correction shown comes
  from that text.
- **AI only proposes candidate quotations** (where a quotation might be). It never supplies Quran text, a
  reference or a verdict, and a candidate that is not literally in the article is discarded.
- **A model's proposal is not evidence that a span is a Quran quotation.** A span that only the model proposed
  is graded with the same deterministic rules as an unmarked span found by the phrase search: an exact,
  distinctive phrase is a "candidate"; a short or common phrase, a formula, a phrase whose words differ from the
  text, or ordinary prose is only a "possible quotation", shown with no replacement text until the editor confirms
  it. It counts as established only when the writer's own reference points at the matched verse or a lead-in such as
  «قال تعالى» comes right before it. The model never raises a tier the phrase search already assigned.
- **Provenance is per finding.** "Proposed by the model alone" is shown only for a finding that would be absent
  without the model; when a marker or the phrase search found the same span, the card says the model proposed it
  too, and the audit banner counts both numbers (`ai.added_only`, `ai.also_found`).
- **A model span never replaces a finding the program made.** If it overlaps a marked quotation, the editor's own
  selection or a phrase-search hit without being the same span (wider, narrower or shifted), that finding keeps its
  span, tier, verdict and proposed changes exactly as without the model, and the model's span is shown beside it
  (`detection.ai_role: "overlap"`, `detection.ai_spans`, `ai.overlapped`). A model span that overlaps nothing the
  program found is still its own "possible" finding.
- **AI status is reported per audit.** If the model does not respond (rate limit 429, timeout, bad key or
  bad JSON), the result says so, the deterministic fallback is used, and nothing is labelled as found by AI.
  "Configured" (a key is set) is never presented as "working".
- An approximate (fuzzy) match is never called verified. The app never says the whole article is verified.

---

## How it works

```
article ──► candidate extraction ──► locate in article ──► attach reference ──► verify ──► propose fixes ──► editor approves ──► revised article
            │ AI provider (Groq or     (reject anything      (regex parser,       (Quranpedia    (source words     (browser only)      + review record
            │   Gemini, one per audit)  not literally          nearest quote)       Hafs text,     only; none if
            │ marked ﴿…﴾ {…} «…»        present)                                   deterministic) span ambiguous)
            │ unmarked phrase search (seed-and-extend over the word index)
            │ manual highlight (POST /api/phrase, no AI)
```

| Stage | What it does | Trust |
|---|---|---|
| **AI extraction** (`app/extraction/groq.py`, `gemini.py`) | The model returns JSON `{candidates:[{quote, reference_text}]}` copied from the article (Groq: strict `json_schema`). | Untrusted. Each quote is re-located in the article (diacritic- and spelling-insensitive); the finding's text is always the article's own substring, and anything not found is discarded and counted. |
| **Marked extraction** (`app/extraction/marked.py`) | ﴿…﴾ (in either order), {…}, and «…» / "…" / ((…)) when preceded by a cue such as «قال تعالى» or followed by a reference. | Deterministic. |
| **Phrase search** (`app/phrases.py`) | Unmarked phrases of ≥ 3 words that occur in the Quran after normalization, plus near matches (a word substituted, added or left out, or spelled slightly differently). Seed-and-extend over the existing word index; no phrase index is built. | Deterministic. A *detection* only: it says where a Quran phrase may be and how sure it is that a quotation was meant (`candidate` / `possible`); the verifier then compares with the source. |
| **Reference parser** (`app/references.py`) | `البقرة: 255`, `[البقرة ٢٥٥]`, `سورة البقرة، الآية 255`, `الآية 255 من سورة البقرة`, `2:255`, ranges, surah-only, common alternative surah names. Range-checked against verse counts. | Deterministic. |
| **Verifier** (`app/verifier.py`) | Exact search at three normalization levels, fuzzy alignment when nothing exact exists, word diffs, and reference checks. | Deterministic. Quranpedia text only. |
| **Corrections** (`app/verifier.py` `propose_wording`, `app/corrections.py`) | Turns a verdict into proposed changes with exact character offsets. | Deterministic. Replacement words come only from Quranpedia; see "Editor workflow". |
| **Revision** (`app/static/revision.js`) | Applies only the approved changes in the browser. | No server state. Refuses a change whose original text is no longer at its offsets, and overlapping changes. |

### Unmarked phrases: candidate, "maybe", or hidden

Finding a phrase and verifying it are separate steps. Each finding has a **detection** (how it was found and how sure we are that a quotation was meant) and a **verdict** (how the words compare with the Hafs text).

| Shown as | When | What the editor gets |
|---|---|---|
| مرشَّح لاقتباس قرآني (*candidate*) | Exact match (after normalization) of a distinctive phrase: at least 4 words of words that are rare in the Quran (or 5+ words), not an everyday formula, not introduced as hadith/du'a/proverb | The normal card and source-backed proposals (each needs approval). Several verses → the choices are listed and none is picked. |
| قد يكون اقتباسًا قرآنيًا — يحتاج مراجعة (*maybe*) | A short or common exact phrase, a near match (one or two words differ), a formula after a Quran cue, or a phrase after a hadith/du'a/proverb cue | The match is shown, but the green «matched» chip is replaced by the «maybe» label and **no replacement text is proposed** until the editor confirms it is a Quran quotation and picks the verse. The reply draft never names an unconfirmed «maybe». |
| Not listed | Exact phrases too short or too common to tell from ordinary Arabic, and bare everyday formulae (بسملة، «إن شاء الله»، «رضي الله عنه» …) | Counted in a notice. The editor can highlight the phrase in the text box and press «افحص المقطع المحدَّد», then choose its verse. One- and two-word phrases may be impossible to place reliably without context. |

Known gap: the search cannot know where a writer's quotation ends, so a wrong **last** word looks like prose after the quotation. The card then shows the verse's next word beside the article's next word, with no verdict.

### Matching levels (shown to the user)

| Level | Meaning |
|---|---|
| `literal` — مطابق حرفيًا | Same letters **and** diacritics. Only Quranic pause/sajdah/hizb marks, tatweel and invisible characters are ignored. |
| `diacritics` — بتجاهل التشكيل | Same letters. The article's diacritics are absent or partial but never contradict the source. |
| `normalized` — بعد توحيد الرسم | Differs only by simplified letter forms (for example ا for أ/إ/آ, ي↔ى, ه for ة). Each change is listed. |
| difference (diacritics / letters) | Letters match a unique verse, but a diacritic contradicts the source (e.g. «يخشى اللهُ»), or a hamza seat changed (إن ↔ أن). |
| difference (`fuzzy`) — أقرب موضع مقترح | Not found exactly, so the closest passage is shown with a word diff. **Always flagged “needs human review”, never shown as verified.** |
| uncertain — غير محسوم | Fewer than 3 words, found in several verses without a disambiguating reference, not found, or source unavailable. **Also:** for an unmarked span chosen by the program or the AI, when the quotation's start or end is not settled (the article word touching the span differs from the verse's neighbouring word and no punctuation, lead-in or reference marks the boundary). That means the boundary could not be established, not that the wording is wrong; the editor confirms or adjusts it. Brackets and manual highlights are never questioned. |

### Reference statuses

`matched` · `missing` · `incorrect` (wrong verse, wrong surah, or a number outside the surah's range) ·
`uncertain` (the reference covers only part of a multi-verse quotation, the location is fuzzy, or the source is unavailable).

### Editor workflow: proposals, approval and the revised article

A correction is **proposed only when the source supports both the text and the location**:

| Situation | What is proposed |
|---|---|
| Exact match at one location, but a letter form differs significantly (e.g. «إن» for «أن») | Replace only the differing word(s), written in the article's own style (no diacritics added to an unvocalized quote). |
| Exact letters, but a written diacritic contradicts the source | Replace only the conflicting word(s); labelled «تصحيح التشكيل» with a warning that printed mushafs differ in some marks. |
| Correct quote without diacritics | **Not an error.** An optional «ضبط كامل بتشكيل المصحف» change is offered as an explicit editor choice, covering only the quoted words. |
| Not found exactly (fuzzy), unique closest passage, similarity ≥ 0.8 — or ≥ 0.75 with a reference that points to it | Minimal word edits (replace / insert / remove) inside the excerpt. The excerpt is never expanded to the whole verse. |
| Fuzzy with several similar verses and no ayah-level reference that singles one out, a reference that points elsewhere, low similarity, a short phrase, a repeated phrase, or source unavailable | **No replacement.** The card says «لا يُقترح تصحيح تلقائي» and why, and the quotation stays marked unresolved. |
| Wrong reference, or a reference that covers only part of a multi-verse excerpt, when the location is certain | Replace only the reference text, keeping the writer's style (digits, «سورة … الآية …», numeric `2:255`). |
| Missing reference, location certain | Optional insertion of «[السورة: الآية]» after the closing bracket. |

Each change carries its offsets, the original and replacement text, the reason, the surah/ayah and
Quranpedia links. In the browser the editor approves or rejects each one. Nothing changes without
approval, and every character outside approved changes (prose, punctuation, line breaks, even markup)
is preserved. Decisions live only in that tab (memory + `sessionStorage`); nothing is sent to or stored
on the server. The preview marks deletions, insertions and **unresolved quotations**. The app never
states that the whole article is verified or ready to publish.

**Review record.** «سجل مراجعة الاقتباسات» is a print/PDF view generated in the browser: approved
changes (original, replacement, reason, surah/ayah, source link), rejected and undecided changes,
unresolved items, the source retrieval time, and whether AI extraction actually ran on this audit.
It is labelled as an editorial aid, not a certificate of religious or textual correctness.

**Reply draft for a social post (optional).** Under the editor card, «مسودة رد على منشور» builds a short,
editable Arabic reply from the *approved* corrections and the unresolved quotations only, ending with
«هذا فحص للاقتباسات التي رُصدت فقط، وليس حكمًا على المنشور كله». The editor copies and posts it manually;
the app never posts anything. An X bot is deliberately not built (see docs/CONTINUATION.md).

---

## Run locally

Requirements: Python 3.12+ (Node.js is optional: it runs the revision-engine tests and the browser scripts).

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt      # runtime-only: requirements.txt

# optional: enable AI extraction (see "AI use")
cp .env.example .env        # then edit .env; it is git-ignored
set -a; source .env; set +a

uvicorn app.main:app --reload --port 8000
# open http://localhost:8000
```

The first audit downloads the Hafs text from Quranpedia (one request, about 1.6 MB). Without `GROQ_API_KEY` or `GEMINI_API_KEY` the app runs in
**reduced mode** and a yellow banner says so: marked quotations are checked and the rest of the text is searched for phrases of 3 or more words
that match the Quran, so **some short unmarked quotations can still be missed**; the editor can select them by hand.

### Environment variables (names only; see `.env.example`; set secrets in the host's dashboard or a git-ignored `.env`, never in the code)

| Variable | Purpose | Default |
|---|---|---|
| `AI_PROVIDER` | `auto` (Groq if its key is set, else Gemini if set, else none), `groq`, `gemini`, or `none` | `auto` |
| `GROQ_API_KEY` | Groq key (secret). Without it Groq is not used | unset |
| `GROQ_MODEL` | Groq model; the live demo uses `qwen/qwen3.8-27b` (a Groq *preview* model) | `qwen/qwen3.8-27b` |
| `EXTRACTION_PROMPT` | prompt version in `app/extraction/prompts.py` | `v2` |
| `GROQ_MAX_COMPLETION_TOKENS`, `GROQ_REASONING_EFFORT` | advanced Groq tuning. Leave unset: a 512-token cap was tried and may truncate longer answers | unset |
| `GEMINI_API_KEY`, `GEMINI_MODEL`, `GEMINI_FALLBACK_MODELS` | optional alternative provider; never succeeded in our tests (503/429) | unset |
| `AI_TIMEOUT_SECONDS`, `AI_ATTEMPT_TIMEOUT_SECONDS`, `AI_COOLDOWN_SECONDS` | AI time budget and pause after a failure | 12, 8, 60 |
| `MAX_ARTICLE_CHARS`, `MAX_CANDIDATES`, `RATE_LIMIT_PER_MINUTE` | input limit, candidate cap, per-IP rate limit (per instance) | 6000, 40, 10 |
| `SOURCE_TIMEOUT_SECONDS`, `QURAN_CACHE_DIR`, `QURANPEDIA_CONTACT` | Quranpedia timeout, cache directory, optional contact e-mail added to the User-Agent as Quranpedia's policy requests | 20, temp dir, unset |

### Tests

```bash
python -m pytest -q                      # 343 tests offline (a 36-verse excerpt in tests/fixtures/), including the Node tests of the revision engine if node is installed;
                                         # tests/test_phrases_full.py also runs against the real text if a local copy is cached (else skipped)
node --test tests/revision.test.mjs      # the revision engine alone

# browser end-to-end (Playwright installed in any scratch dir, not a project dependency)
NODE_PATH=/path/to/scratch/node_modules node scripts/ui_e2e.mjs http://localhost:8000 ./shots
NODE_PATH=/path/to/scratch/node_modules node scripts/ui_phrase_e2e.mjs --shots ./shots   # unmarked-phrase workflow: starts its own server with AI off (no Groq call possible)
NODE_PATH=/path/to/scratch/node_modules node scripts/ui_phrase_e2e.mjs --live-ai https://<service> # opt-in: ONE audit = one Groq call; exit 2 = model did not answer
NODE_PATH=/path/to/scratch/node_modules node scripts/ui_boundary_e2e.mjs http://localhost:8000 ./shots   # uncertain-boundary workflow (AI_PROVIDER=none; wait 60 s between browser scripts: rate limit)
python scripts/measure_resources.py [--server]       # startup time and peak memory in fresh processes (needs a cached Quran text)
python eval/validate_phrases.py                       # the frozen phrase set against the Hafs text
python eval/run_eval.py --mode fallback               # labelled evaluation without any AI (--cases eval/heldout.json | eval/phrases_frozen.json)
python scripts/e2e_check.py http://localhost:8000   # API checks, samples, files that must not be served
```

## Deploy (Render Free; the live demo)

The live demo runs on Render's free web service from this repository's `main` branch: build `pip install -r requirements.txt`, start
`uvicorn app.main:app --host 0.0.0.0 --port $PORT`, health check `/api/health`, Python 3.12 from `.python-version`.
Exact settings, environment-variable names and the checks to run afterwards: [docs/RENDER_DEPLOY.md](docs/RENDER_DEPLOY.md); a Blueprint is in `render.yaml`
(its secret values are entered in the dashboard only).
A first Vercel deployment (pre-challenge baseline) was blocked from deploying newer commits, so Vercel is not used for the current demo; `vercel.json` is kept only for that route.

## AI use

- **What it does.** One request per audit goes to Groq (`qwen/qwen3.8-27b`, strict JSON schema). The model returns the passages that look like quotations, copied from the article, and any nearby reference text. Each passage is then re-located in the article (anything not literally there is discarded) and graded by the same deterministic rules as any other candidate.
- **What it never does.** It never supplies Quran text, a reference, a verdict or a correction. All of those come from the Hafs text.
- **When it fails** (rate limit 429 on Groq's free tier, timeout, bad key or bad JSON) the result shows a visible notice, the deterministic path still runs, and nothing is labelled as AI-found. After a failure the app skips AI for 60 s (120 s after a 429), and a later notice says it is waiting.
- **Which key.** The deployer supplies `GROQ_API_KEY` as an environment variable on the host. Do not paste keys into issues, commits, screenshots or videos. If a key is exposed, revoke it at https://console.groq.com/keys and create a new one.
- **Check.** `/api/health` shows `ai_configured`, the provider, and `ai_last_call.outcome` (`never_called`, `ok` or `failed`); "configured" is not "working".
- **Replacing the provider.** Implement `ExtractionProvider` (`app/extraction/base.py`: `available()` and `extract(article)`), register it in `get_provider()` and select it with `AI_PROVIDER=<name>`. The rest of the pipeline treats provider output as untrusted. A Gemini adapter exists (`app/extraction/gemini.py`) but no real Gemini call has succeeded in our tests.
- Groq lists `qwen/qwen3.8-27b` as a **preview** model that can change or be withdrawn; `GROQ_MODEL=openai/gpt-oss-20b` is a production model with strict JSON schema.

---

## Quran source, caching and outages

- Source: Quranpedia API v1, Hafs mushaf `GET https://api.quranpedia.net/v1/mushafs/1`,
  a single documented request that returns all 6,236 verses.
- A process keeps the text in memory for up to 24 h, matching the API's own `Cache-Control`,
  so Quranpedia's ongoing corrections arrive within a day. It also writes a copy to the
  machine's temp directory. Nothing is re-published and the text is not committed to Git.
- If a refresh fails, a copy younger than 7 days **on the same machine** is used with a
  visible warning. Otherwise every quotation is marked *uncertain — source unavailable*.
  The app never substitutes AI-generated or hard-coded Quran text.
- **Actual limits on Render Free (and any hosting without shared storage):** memory and the temp directory belong to one instance and disappear when it restarts or sleeps. In practice:
  - every cold instance fetches the full text once (locally: about 1.2 s including the index build; on Render, one measurement after 18 idle minutes took 23 s for the first page, and the first audit after that adds the one-time download, a few seconds) and warm requests reuse it;
  - the 24 h refresh and the 7-day fallback only apply while the same instance stays alive;
  - a cold instance that cannot reach Quranpedia reports the source as unavailable rather than guessing.

  Quranpedia serves this endpoint through Cloudflare with a 24 h CDN cache, which softens origin outages. One retry is made for transient network/5xx errors.
  `/api/health` shows `loaded_from` (`network` or `disk`), the text's age and the instance start time. A cross-instance cache would need an external store; it is deliberately not used.
- Every source verse links to Quranpedia (`api.quranpedia.net/embed?surah=…&ayah=…`)
  and to its API record. Attribution appears in the page footer.
- Test and evaluation data in Uthmani script (never read by the app): **Quran text: Tanzil Project, https://tanzil.net** (Tanzil Quran Text, Uthmani v1.1, CC BY 3.0; verbatim, with its notice kept inside the data files; see SOURCES.md §1b).

## Security, privacy and hosting limits

- Input is capped at 6,000 characters (the body size is checked too), with a per-IP rate limit of 10 requests/minute per instance (best effort).
- **Privacy.** Articles are processed in memory and never written to disk or logged by the app; error handlers log only the exception type and the response does not echo the article. Decisions on corrections stay in the browser tab (memory + `sessionStorage`). **When AI is on, the article text is sent to Groq** (US servers) to propose quotation locations; Groq states that it does not retain inference data by default, except up to 30 days for reliability and abuse monitoring (https://console.groq.com/docs/your-data, read 30 Sep 2026), and Zero Data Retention is an organisation setting. Do not paste non-public or sensitive text into the live demo. Quranpedia receives no article text, only one download of the mushaf. Visitors' browsers load fonts from Google Fonts. The host (Render) sees ordinary web-request metadata. The page footer states the main points in Arabic.
- The frontend inserts all text with `textContent` (never `innerHTML`), and a strict CSP blocks inline scripts. Secrets come only from environment variables; `.env` is git-ignored.
- **Hosting limits.** Render Free sleeps after about 15 minutes idle (first request up to about a minute, plus one Quran download), has no persistent disk, and shares CPU; Groq's free tier answers 429 when audits come in quick succession (about 2 minutes apart is safe). A production deployment would need a paid host, a paid Groq tier (or Zero Data Retention) and a shared cache. Memory and timing numbers in `docs/EVALUATION.md` were measured locally, not on Render.
- Time limits: AI gets 12 s total per audit (one request, no retry chain); Quranpedia calls time out after 20 s; the unmarked-phrase search has a fixed work budget and reports when it was cut off.

## Known limitations

- **No general accuracy claims.** The numbers above come from three small, author-written sets, single runs, labels awaiting specialist review. AI-mode numbers (Groq, earlier local runs, one run per set) are in `docs/EVALUATION.md`; they were not repeated for the current code.
- **Detection is not complete.** Unmarked phrases of one or two words, phrases made only of common words, near matches with fewer than 4 matched words, a wrong first or last word of an unmarked quotation (reported only as "uncertain: boundary not settled", with the neighbouring words shown), quotations with omissions and rare Uthmani spellings can be missed or shown only as «possible» or «uncertain». Frozen set: 30 of 32 unmarked quotations found, 2 missed.
- **«Possible» is not verified.** Ordinary prose can reuse Quran words (about 2–3 «possible» items per 1,000 words of Islamic-topic prose, 44 outside brackets in 19,794 untuned Wikipedia words). Close paraphrases such as «لا تحزن إن الله معنا دائما» (5 of 6 words from التوبة: 40) are reported as a candidate whose end is "uncertain".
- **A short unmarked misquotation** (e.g. «إن الله مع الصابرون» with no reference and no «قال تعالى») is indistinguishable from prose by evidence: it is listed only as «possible» with its closest verse and a one-click confirm, or missed.
- **Boundaries.** The tool cannot know where an unmarked quotation starts or ends, so the editor may need to confirm («حدود الاقتباس صحيحة») or adjust them. This makes many correct quotations read "uncertain".
- **AI may fall back.** On Groq's free tier a 429 can happen; the notice says so and the result is the deterministic one. A model can also propose prose or nothing.
- **Speed.** A full-size article (about 1,000 words) took about 0.1–0.4 s locally with the phrase search; Render's CPU will be slower (not measured). Memory: a real `uvicorn` process peaked at 94.1 MB locally.
- Automatic corrections are deliberately conservative: a short fuzzy quote, or a phrase found in several verses, gets review information but no replacement.
- The source is Quranpedia's Hafs text in standard (imla'i) spelling with full diacritics. Uthmani spellings (e.g. «الصلوة») are matched through documented rules; about 50 rare spellings are not covered, and a few words the imla'i text joins or splits differently (`بَعْدَ مَا` / `بعدما`) are not either: such a quotation reads «uncertain» without a replacement. The Uthmani rasm writes some different imla'i words identically (a plural verb and a singular verb ending in waw), so that confusion cannot be detected in Uthmani text. Only Hafs is supported. Diacritic conventions vary between printed mushafs, so a diacritics difference is a prompt to check, not proof of error.
- Quotations with omissions («…») are compared as one span, so they show missing words and need review. Quotations under 3 words are never confirmed without a reference and are not searched for automatically (select them by hand). Reference parsing covers common Arabic forms, not every style.
- Gemini: no real Gemini call has succeeded (503/429), so that adapter is unverified.

## Repository map

```
app/
  main.py            FastAPI app, API routes, security headers, rate limit
  audit.py           pipeline orchestration (incl. the manual phrase check)
  phrases.py         unmarked-phrase search: seed-and-extend over the word index, tiers, formula and cue lists
  verifier.py        wording/reference verification (deterministic)
  references.py      reference detection & parsing
  arabic.py          normalization levels, tokenization with offsets
  quran_source.py    Quranpedia client, cache, search index
  surahs.py          surah names, aliases, verse counts (metadata only)
  corrections.py     proposed changes with exact offsets (source words only)
  extraction/        provider interface, Groq + Gemini providers, call tracker, marked-quote extractor
  static/            index.html, styles.css, app.js, revision.js (browser revision engine), samples/*.txt
tests/               verifier, references, normalization, pipeline, source, Gemini, Groq, corrections,
                     revision-engine (Node) tests
scripts/e2e_check.py end-to-end API check of a running instance (samples, errors, files not served)
scripts/ui_e2e.mjs   Playwright browser check of the editor workflow, desktop + mobile
scripts/ui_phrase_e2e.mjs Playwright check of candidate / "maybe" cards, confirming a verse, manual selection (own AI-off server);
                     `--live-ai URL`: model-on assertions that do not assume a finding count
scripts/ui_boundary_e2e.mjs Playwright check of the "uncertain boundary" workflow
scripts/measure_resources.py startup time and peak memory (in-process and real uvicorn server)
docs/LABEL_REVIEW.md checklist for a human reviewer of the evaluation labels
docs/CONTINUATION.md plan for 4–6 October and beyond (incl. the X use case)
docs/EVALUATION.md   labelled evaluation: method, fallback results, limits
docs/TEST_LOG.md     dated end-to-end observations (local + live)
docs/RENDER_DEPLOY.md Render settings, deploy steps and checks (the live demo's host)
render.yaml          optional Render Blueprint with the same settings (no secret values)
vercel.json, .vercelignore  only for the earlier Vercel baseline deployment
eval/                labelled cases, frozen phrase set (+ SHA-256), label validators, scorer, raw results
SOURCES.md           sources, licences and attribution record
BASELINE.md          pre-challenge baseline declaration
```

Sample articles are in `app/static/samples/` and can be loaded from the «مثال جاهز» menu.
Each contains some deliberately wrong quotations or references so every status can be demonstrated.

## Dependencies and licences

Code: MIT (see [LICENSE](LICENSE)). The Quran text is **not** included in this repository; it is fetched from Quranpedia under its usage policy (free, no authentication, one documented request per instance, attribution in the page footer).
Runtime dependencies are pinned in `requirements.txt` (FastAPI, Starlette, Pydantic, httpx, uvicorn and their dependencies: MIT or BSD-3-Clause; `certifi` is MPL-2.0; `typing_extensions` is PSF-2.0); test dependencies in `requirements-dev.txt` (pytest and plugins: MIT, BSD-2-Clause, Apache-2.0/BSD-2-Clause).
Fonts (Readex Pro, Amiri Quran) are SIL Open Font License 1.1, loaded from Google Fonts. The organizer's PDFs and PowerPoint template are not included. Groq and Quranpedia are third-party services governed by their own terms.
Every source, licence and attribution is listed in [SOURCES.md](SOURCES.md).

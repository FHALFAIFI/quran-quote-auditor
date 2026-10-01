# مدقق الاقتباسات القرآنية — Quran Quotation Auditor

> **Pre-challenge work.** Everything in this repository was built **before
> 4 October 2026**: the git tag `pre-challenge-baseline` marks the first baseline
> commit, and every later commit dated before 4 October (including the Groq
> provider and the editor workflow added on 29 September) is also pre-challenge
> work. Only work committed during 4–6 October 2026 counts as challenge work.
> See [BASELINE.md](BASELINE.md) and [CHANGELOG.md](CHANGELOG.md).
>
> **AI status (30 Sep 2026): the Groq service responds; a small benefit was observed locally.** Groq (`qwen/qwen3.8-27b`) answered
> on every labelled case. With the original prompt it found nothing the deterministic path had missed. With prompt v2
> (now the default) it found one more unmarked quotation on the labelled set (26/28, unmarked 2/4) and one on a new
> held-out set (4/6 vs 3/6), with no false "matched" verdicts or false fixes. These are single runs on small
> author-written sets, and short unmarked quotations are still missed. Not yet live: `GROQ_API_KEY` is not set on
> Vercel, and the Render deployment is prepared ([docs/RENDER_DEPLOY.md](docs/RENDER_DEPLOY.md)) but not created.
> See [docs/EVALUATION.md](docs/EVALUATION.md) and [docs/TEST_LOG.md](docs/TEST_LOG.md).

> **Unmarked phrases (30 Sep 2026, pre-challenge, no AI needed): short quotations without brackets are now searched for, and shown with the right level of doubt.**
> A memory-light phrase search (`app/phrases.py`) finds Quran phrases in plain text. A distinctive exact match is shown as «مرشَّح لاقتباس قرآني»;
> a short, common or approximate phrase says «قد يكون اقتباسًا قرآنيًا — يحتاج مراجعة» and gets **no** proposed replacement until the editor confirms it
> and picks the verse; a phrase found in several verses lists the choices; the editor can also highlight a missed phrase and choose its verse.
> Observed (deterministic path, same labels): main 25/28 → 27/28 (unmarked 1/4 → 3/4), held-out 3/6 → 6/6 (both are development data); on a new set
> written and frozen before any tuning (run twice; two bug fixes of mine followed the first run, both disclosed), 30/32 unmarked quotations were found (18/32 before), no non-Quran text or everyday formula was shown as confirmed
> (2 → 0), and **2 misquotations are still reported "matched"** because their wrong words are at the end of the quotation. Detection is not complete.
> **AI compared separately** (Groq, same labels, one run per set): with the phrase search in place it adds one quotation on the main set (a 3-word misquotation: 28/28 vs 27/28)
> and none on the held-out (6/6) or frozen (30/32) sets, so the earlier small AI benefit (26/28, 4/6) is now mostly covered by the deterministic search.
> Memory and timing (real server peak 94.1 MB vs 112.8 MB before; a full-size article takes ~0.1–0.4 s locally) and all limits: [docs/EVALUATION.md](docs/EVALUATION.md).

**AI Challenge Serving Islamic Content 2026 — Track 4: knowledge and verification tools.**

An Arabic, right-to-left web app for editors and reviewers. You paste a short Arabic
article, and the app:

1. finds likely Quran quotations — marked ones, unmarked phrases (shown as a *candidate* or as «قد يكون اقتباسًا قرآنيًا — يحتاج مراجعة») — and any nearby surah/ayah reference; detection is not complete,
2. checks each quotation's **wording** and **reference** against the Hafs text served
   live by [Quranpedia](https://quranpedia.net),
3. shows one review list with each quotation's location in the article, the quoted text,
   the canonical source verse, word-level differences, the reference status, and which
   cases **need human review**,
4. proposes **source-backed corrections** (only when Quranpedia supports the text and the
   location), which the editor **approves or rejects one by one**, and
5. builds the **revised article** (only approved changes; every other character kept) with a
   before/after preview, a copy button, and a printable **review record**
   («سجل مراجعة الاقتباسات»).

**Scope:** Quran quotations and their references only. The app does not proofread
ordinary Arabic, interpret verses, translate, or issue religious rulings.

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

Requirements: Python 3.12+.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt

# optional: enable AI extraction (see "Runtime API key" below)
cp .env.example .env        # then edit .env; it is git-ignored
set -a; source .env; set +a

uvicorn app.main:app --reload --port 8000
# open http://localhost:8000
```

Without `GROQ_API_KEY` or `GEMINI_API_KEY`, the app runs in **reduced mode**. A yellow banner says so. Explicitly marked quotations
are checked, and the rest of the text is searched for phrases of 3 or more words that match the Quran (see "Unmarked phrases"), so
**some short unmarked quotations can still be missed**; the editor can select them by hand.

Run the tests (offline; they use a 36-verse excerpt in `tests/fixtures/`):

```bash
python -m pytest -q                      # Python tests + Node tests of the revision engine (if node is installed);
                                         # tests/test_phrases_full.py also runs against the real text if a local copy is cached (else skipped)
node --test tests/revision.test.mjs      # the revision engine alone

# browser end-to-end (Playwright installed in any scratch dir, not a project dependency)
NODE_PATH=/path/to/scratch/node_modules node scripts/ui_e2e.mjs http://localhost:8000 ./shots
NODE_PATH=/path/to/scratch/node_modules node scripts/ui_phrase_e2e.mjs --shots ./shots   # unmarked-phrase workflow: starts its own server with AI off (no Groq call possible)
NODE_PATH=/path/to/scratch/node_modules node scripts/ui_phrase_e2e.mjs --live-ai https://<service> # opt-in: properties that must hold with the model on; ONE audit = one Groq call; exit 2 = model did not answer
NODE_PATH=/path/to/scratch/node_modules node scripts/ui_boundary_e2e.mjs http://localhost:8000 ./shots   # uncertain-boundary workflow (use AI_PROVIDER=none; wait 60 s between browser scripts: rate limit)
python scripts/measure_resources.py [--server]       # startup time and peak memory in fresh processes (needs a cached Quran text)
python eval/validate_phrases.py                       # the frozen phrase set against the Hafs text
python scripts/e2e_check.py http://localhost:8000   # API checks, samples, files that must not be served
```

## Deploy to Render (prepared, not yet created)

Exact settings, environment-variable names and the steps to deploy commit `3273078`:
[docs/RENDER_DEPLOY.md](docs/RENDER_DEPLOY.md). Build `pip install -r requirements.txt`, start
`uvicorn app.main:app --host 0.0.0.0 --port $PORT`, health check `/api/health`, Python 3.12 from `.python-version`.

## Deploy to Vercel

Live demo: **https://quran-quote-auditor.vercel.app** (pre-challenge baseline deployment).

The app runs as one Vercel Function using Vercel's FastAPI support (entrypoint
`app/main.py`, exporting `app`). `vercel.json` only declares `"framework": "fastapi"`.
Without it, a project created from the CLI had no preset and the build produced nothing
(every path returned 404). The default Fluid-compute timeout is longer than the app's own
limits (12 s AI + 20 s source). `.vercelignore` keeps `.env`, `.env.local`, tests and local
files out of the upload, because the Vercel CLI does not read `.gitignore`.

Using the dashboard:

1. Push this repository to GitHub (public, as the challenge requires).
2. On Vercel, choose **Add New → Project** and import the repository. The framework comes from `vercel.json`.
3. Add the environment variables described below, then deploy.
4. Open `https://<your-app>.vercel.app/api/health` and confirm `"mode": "ai"`.

Using the CLI (as used for the live demo):

```bash
npx vercel link --yes --project quran-quote-auditor
printf %s "$GEMINI_API_KEY" | npx vercel env add GEMINI_API_KEY production --sensitive
printf %s "gemini-3.5-flash-lite,gemini-3.1-flash-lite" | npx vercel env add GEMINI_FALLBACK_MODELS production
npx vercel deploy --prod
python scripts/e2e_check.py https://<your-app>.vercel.app   # samples + error cases
```

**If Vercel reports the deployment as "Blocked"** (the commit author email isn't linked to
the Vercel account), the live demo was deployed from a clean export of the committed tree,
with no `.git` metadata and no `.env`:

```bash
E=$(mktemp -d); git archive HEAD | tar -x -C "$E"; mkdir "$E/.vercel"; cp .vercel/project.json "$E/.vercel/"
(cd "$E" && npx vercel deploy --prod --yes)
```

## Runtime API key — Groq (default when set)

1. Sign in at **https://console.groq.com/keys** and choose **Create API Key**. Copy it once.
2. **Local:** open `.env` (git-ignored) in an editor and add a line `GROQ_API_KEY=<your key>`.
   Then `set -a; source .env; set +a` before starting uvicorn. Never paste the key into chat,
   code, commits, screenshots or the video.
3. **Production:** Vercel → Project *quran-quote-auditor* → Settings → Environment Variables →
   add `GROQ_API_KEY`, tick **Sensitive**, environment **Production**, save, then redeploy. Or from a
   terminal: `npx vercel env add GROQ_API_KEY production --sensitive` (it prompts for the value).
4. Check `/api/health`: `ai_configured: true`, `provider_name: "groq"`, and `ai_last_call.outcome`
   shows `never_called`, `ok` or `failed` — configured is not the same as working.
5. Groq lists `qwen/qwen3.8-27b` as a **preview** model; it may change or be withdrawn. Set
   `GROQ_MODEL=openai/gpt-oss-20b` (a production model that also supports strict JSON schema) if needed.

The Groq adapter makes **one** request per audit (no retry chain), with the `AI_TIMEOUT_SECONDS`
budget, and skips AI for `AI_COOLDOWN_SECONDS` after a failure (longer after 429 or a rejected key).
Groq's data-handling terms: https://console.groq.com/docs/your-data.

## Runtime API key (Gemini)

Your Claude subscription is only for building the app. The deployed app uses its own
provider key, read from the `GEMINI_API_KEY` environment variable. With `AI_PROVIDER=auto`,
Gemini is used only when no Groq key is set.

1. Sign in at **https://aistudio.google.com/apikey** and create an API key in a
   dedicated Google Cloud project for this app.
2. In Google Cloud Console → *APIs & Services → Credentials*, restrict the key to
   the **Generative Language API**. Set a quota or budget alert on the project.
3. **Production:** go to Vercel → Project → Settings → Environment Variables and add
   `GEMINI_API_KEY`, marked **Sensitive**, for the Production (and Preview, if you
   want) environments. Redeploy.
4. **Local:** put the key in `.env`, which is git-ignored, or `export` it in your shell.
   Never paste it into code, issues, commits, screenshots or the demo video.
5. If a key is ever exposed, delete it in AI Studio immediately and create a new one.

Privacy: the deployed app uses **Groq** (`AI_PROVIDER=groq`), and the page footer names Groq. When AI
extraction is enabled, the article text is sent to Groq, which by default does not retain inference data except
for up to 30 days when troubleshooting errors or investigating abuse (https://console.groq.com/docs/your-data,
checked 30 Sep 2026). If you switch to Gemini, update the footer text in `app/static/index.html`, and
check Google's current Gemini API terms for your tier; on some unpaid tiers,
submitted content may be used to improve Google's products. A paid tier is advisable
for real editorial content. The app itself does not store or log articles.

Optional variables: `GEMINI_MODEL` (default `gemini-3.8-flash`), `GEMINI_FALLBACK_MODELS`
(comma-separated; tried after one retry when the primary model returns 503), `AI_TIMEOUT_SECONDS`
(12), `AI_ATTEMPT_TIMEOUT_SECONDS` (8), `AI_COOLDOWN_SECONDS` (60),
`MAX_ARTICLE_CHARS` (6000), `RATE_LIMIT_PER_MINUTE` (10 per instance), and
`QURANPEDIA_CONTACT`, a contact e-mail added to the User-Agent as Quranpedia's policy requests.
See `.env.example`.

### Replacing the AI provider

Implement `ExtractionProvider` (`app/extraction/base.py`), which has `available()` and
`extract(article) -> list[RawSuggestion]`. Register it in `get_provider()` and select it
with `AI_PROVIDER=<name>`. The rest of the pipeline treats provider output as untrusted,
so no other changes are needed.

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
- **Actual limits on Vercel (serverless):** memory and `/tmp` belong to one function
  instance and disappear with it. They are not shared between instances and do not survive
  redeploys. In practice:
  - every cold instance fetches the full text once (measured locally: about 1.2 s including
    index build, 1.6 MB of JSON, roughly 180 MB of process memory), and warm requests reuse it;
  - the 24 h refresh and the 7-day fallback only apply while the same instance stays alive;
  - a cold instance that cannot reach Quranpedia reports the source as unavailable rather than guessing.

  Quranpedia serves this endpoint through Cloudflare with a 24 h CDN cache, which softens
  origin outages. One retry is made for transient network/5xx errors.
  `/api/health` shows `loaded_from` (`network` or `disk`), the text's age and the instance
  start time, so this behavior can be observed. A cross-instance cache would need an external
  store (e.g. Vercel Blob or Redis). It is deliberately not used in this version.
- Every source verse links to Quranpedia (`api.quranpedia.net/embed?surah=…&ayah=…`)
  and to its API record. Attribution appears in the page footer.

## Security and privacy

- Input is capped at 6,000 characters (body size is also checked), with per-IP rate limiting.
- AI extraction has a 12 s total budget per audit. Groq gets one request; Gemini at most 8 s per request. A model that hangs is not
  retried; the next fallback model is tried instead. After a failure the instance skips AI
  for 60 s (120 s after a quota error), so a demo is never stuck waiting twice. Measured with
  a hanging endpoint: first audit 12.0 s, then immediate. Quranpedia calls time out after 20 s.
  Malformed model JSON raises a handled error. In every AI failure (including 429) the app falls back to
  marked quotations plus the unmarked phrase search, shows a warning in the result, and tags no finding as AI.
  These limits may cut off a slow but working Gemini response; that has not been observed
  yet, because no real Gemini call has succeeded (see docs/TEST_LOG.md).
- Articles are processed in memory and never written to disk or logged. Error handlers log
  only the exception type, and the API response does not echo the article back.
- The frontend inserts all text with `textContent` (never `innerHTML`), and a strict CSP blocks inline scripts.
- Secrets come only from environment variables. `.env` is git-ignored.

## Known limitations

- **No general accuracy claims.** On a small author-written labelled set (single runs, local): without AI,
  25/28 detected; with Groq `qwen/qwen3.8-27b` + prompt v2, 26/28, and 4/6 vs 3/6 on a held-out set.
  Both had 0 false "matched" verdicts and 0 corrections proposed for correct quotes or references.
  See [docs/EVALUATION.md](docs/EVALUATION.md) for its limits. No real Gemini call has succeeded (503/429).
- **Detection is not complete.** Unmarked phrases of one or two words, phrases made only of common words, near matches with fewer than 4 matched words,
  a wrong first or last word of a quotation (it is reported as a match of the rest, with a hint), Uthmani spellings and quotations with omissions can be missed
  or shown only as «maybe». On the frozen set: 30/32 unmarked quotations found, 2 of 12 misquotations still reported "matched", 2 missed.
  Islamic-topic prose yields about 2–3 «maybe» items per 1,000 words (44 outside brackets in 19,794 untuned words). See [docs/EVALUATION.md](docs/EVALUATION.md).
- **Speed and memory.** Searching for unmarked phrases makes a full-size article (about 1,000 words) take roughly 0.1–0.4 s on the development machine (Python 3.12), against milliseconds before; Render's CPU will be slower (untested). Memory went *down*: a real `uvicorn` process peaked at 94.1 MB (112.8 MB before), because the old 4-word phrase dictionary was removed. Measured locally, not on Render; see [docs/EVALUATION.md](docs/EVALUATION.md).
- Automatic corrections are deliberately conservative: a short fuzzy quote, or a phrase found in
  several verses, gets review information but no replacement.
- The source is Quranpedia's Hafs text in standard (imla'i) spelling with full diacritics.
  Quotations copied from Uthmani-script editions (e.g. «الصلوة», «السموت», small
  letters) may appear as *differences* needing review.
- Diacritics conventions vary between printed mushafs (e.g. idgham shadda in «وَقُل رَّبِّ»),
  so a diacritics difference is a prompt to check, not proof of error.
- Quotations with omissions («…») are compared as one span, so they show missing words and need review.
- Quotations under 3 words are never confirmed without a reference, and are not searched for automatically (select them by hand).
- Reference parsing covers common Arabic forms, not every possible style. Numeric forms
  like `10:30` are only used when adjacent to a quotation.
- The rate limiter is per serverless instance (best effort).

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
scripts/measure_resources.py startup time and peak memory (in-process and real uvicorn server)
docs/LABEL_REVIEW.md checklist for a human reviewer of the evaluation labels
docs/CONTINUATION.md plan for 4–6 October and beyond (incl. the X use case)
docs/EVALUATION.md   labelled evaluation: method, fallback results, limits
docs/TEST_LOG.md     dated end-to-end observations (local + live)
docs/RENDER_DEPLOY.md Render settings and deploy steps (prepared, not yet used)
render.yaml          optional Render Blueprint with the same settings
eval/                labelled cases, frozen phrase set (+ SHA-256), label validators, scorer, raw results
SOURCES.md           sources, licences and attribution record
BASELINE.md          pre-challenge baseline declaration
```

Sample articles are in `app/static/samples/` and can be loaded from the «مثال جاهز» menu.
Each contains some deliberately wrong quotations or references so every status can be demonstrated.

## Challenge submission checklist

- [ ] Live demo URL (Vercel), with `GROQ_API_KEY` set, `/api/health` showing `"ai_configured": true`,
      **and** a real audit whose `ai.responded` is `true` recorded in docs/TEST_LOG.md
- [ ] Public GitHub repository, with the `pre-challenge-baseline` tag pushed
- [ ] Source documentation: this README, [SOURCES.md](SOURCES.md) and [BASELINE.md](BASELINE.md)
- [ ] Demo video ≤ 2 minutes, with no API keys visible on screen
- [ ] Final PDF/PPT presentation (organizer template or matching identity)
- [x] Labelled evaluation, fallback mode (docs/EVALUATION.md)
- [x] Editor workflow: proposals, approve/reject, revised article, review record (local, browser-tested)
- [x] Labelled evaluation, AI mode (Groq, local, 14/14 responded; single runs, docs/EVALUATION.md)
- [ ] Human review of the evaluation labels (docs/LABEL_REVIEW.md)

## Licence

Code: MIT (see [LICENSE](LICENSE)). The Quran text is not included; it is fetched from
Quranpedia under its usage policy. Third-party sources and licences are listed in [SOURCES.md](SOURCES.md).

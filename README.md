# مدقق الاقتباسات القرآنية — Quran Quotation Auditor

> **Pre-challenge baseline.** Everything in this repository up to the git tag
> `pre-challenge-baseline` was built **before 4 October 2026**. Only work
> committed during 4–6 October 2026 counts as challenge work. See
> [BASELINE.md](BASELINE.md).

**AI Challenge Serving Islamic Content 2026 — Track 4: knowledge and verification tools.**

An Arabic, right-to-left web app for editors and reviewers. You paste a short Arabic
article, and the app:

1. finds every likely Quran quotation and any nearby surah/ayah reference,
2. checks each quotation's **wording** and **reference** against the Hafs text served
   live by [Quranpedia](https://quranpedia.net),
3. shows one review list with each quotation's location in the article, the quoted text,
   the canonical source verse, word-level differences, the reference status, and which
   cases **need human review**.

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

---

## How it works

```
article ──► candidate extraction ──► locate in article ──► attach reference ──► verify ──► review list
            │ AI provider (Gemini)     (reject anything      (regex parser,       (Quranpedia
            │ marked ﴿…﴾ {…} «…»       not literally          nearest quote)       Hafs text,
            │ exact-run index scan      present)                                   deterministic)
```

| Stage | What it does | Trust |
|---|---|---|
| **AI extraction** (`app/extraction/gemini.py`) | Gemini returns JSON `{candidates:[{quote, reference_text}]}` copied from the article. | Untrusted. Each quote is re-located in the article (diacritic- and spelling-insensitive), and anything not found is discarded and counted. |
| **Marked extraction** (`app/extraction/marked.py`) | ﴿…﴾ (in either order), {…}, and «…» / "…" / ((…)) when preceded by a cue such as «قال تعالى» or followed by a reference. | Deterministic. |
| **Index scan** (`app/audit.py`) | Unmarked runs of ≥ 5 article words that occur verbatim (after normalization) in the Quran. | Deterministic. |
| **Reference parser** (`app/references.py`) | `البقرة: 255`, `[البقرة ٢٥٥]`, `سورة البقرة، الآية 255`, `الآية 255 من سورة البقرة`, `2:255`, ranges, surah-only, common alternative surah names. Range-checked against verse counts. | Deterministic. |
| **Verifier** (`app/verifier.py`) | Exact search at three normalization levels, fuzzy alignment when nothing exact exists, word diffs, and reference checks. | Deterministic. Quranpedia text only. |

### Matching levels (shown to the user)

| Level | Meaning |
|---|---|
| `literal` — مطابق حرفيًا | Same letters **and** diacritics. Only Quranic pause/sajdah/hizb marks, tatweel and invisible characters are ignored. |
| `diacritics` — بتجاهل التشكيل | Same letters. The article's diacritics are absent or partial but never contradict the source. |
| `normalized` — بعد توحيد الرسم | Differs only by simplified letter forms (for example ا for أ/إ/آ, ي↔ى, ه for ة). Each change is listed. |
| difference (diacritics / letters) | Letters match a unique verse, but a diacritic contradicts the source (e.g. «يخشى اللهُ»), or a hamza seat changed (إن ↔ أن). |
| difference (`fuzzy`) — أقرب موضع مقترح | Not found exactly, so the closest passage is shown with a word diff. **Always flagged “needs human review”, never shown as verified.** |
| uncertain — غير محسوم | Fewer than 3 words, found in several verses without a disambiguating reference, not found, or source unavailable. |

### Reference statuses

`matched` · `missing` · `incorrect` (wrong verse, wrong surah, or a number outside the surah's range) ·
`uncertain` (the reference covers only part of a multi-verse quotation, the location is fuzzy, or the source is unavailable).

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

Without `GEMINI_API_KEY`, the app runs in **reduced mode**. A yellow banner says so, and
only explicitly marked quotations plus verbatim runs of 5 or more words are checked.

Run the tests (offline; they use a 36-verse excerpt in `tests/fixtures/`):

```bash
python -m pytest -q
```

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

## Runtime API key (Gemini)

Your Claude subscription is only for building the app. The deployed app uses its own
provider key, read from the `GEMINI_API_KEY` environment variable.

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

Privacy: when AI extraction is enabled, the article text is sent to Google Gemini.
Check Google's current Gemini API terms for your tier; on some unpaid tiers,
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
- AI extraction has a 12 s total budget with at most 8 s per request. A model that hangs is not
  retried; the next fallback model is tried instead. After a failure the instance skips AI
  for 60 s (120 s after a quota error), so a demo is never stuck waiting twice. Measured with
  a hanging endpoint: first audit 12.0 s, then immediate. Quranpedia calls time out after 20 s.
  Malformed model JSON raises a handled error. In every AI failure the app falls back to
  marked-only extraction with a notice.
  These limits may cut off a slow but working Gemini response; that has not been observed
  yet, because no real Gemini call has succeeded (see docs/TEST_LOG.md).
- Articles are processed in memory and never written to disk or logged. Error handlers log
  only the exception type, and the API response does not echo the article back.
- The frontend inserts all text with `textContent` (never `innerHTML`), and a strict CSP blocks inline scripts.
- Secrets come only from environment variables. `.env` is git-ignored.

## Known limitations

- **No accuracy claims yet.** A labelled evaluation has not been run. See
  [docs/EVALUATION.md](docs/EVALUATION.md) for the plan.
- The source is Quranpedia's Hafs text in standard (imla'i) spelling with full diacritics.
  Quotations copied from Uthmani-script editions (e.g. «الصلوة», «السموت», small
  letters) may appear as *differences* needing review.
- Diacritics conventions vary between printed mushafs (e.g. idgham shadda in «وَقُل رَّبِّ»),
  so a diacritics difference is a prompt to check, not proof of error.
- Quotations with omissions («…») are compared as one span, so they show missing words and need review.
- Quotations under 3 words are never confirmed without a reference. In reduced mode,
  unmarked quotations under 5 words or with wording errors are not detected.
- Reference parsing covers common Arabic forms, not every possible style. Numeric forms
  like `10:30` are only used when adjacent to a quotation.
- The rate limiter is per serverless instance (best effort).

## Repository map

```
app/
  main.py            FastAPI app, API routes, security headers, rate limit
  audit.py           pipeline orchestration
  verifier.py        wording/reference verification (deterministic)
  references.py      reference detection & parsing
  arabic.py          normalization levels, tokenization with offsets
  quran_source.py    Quranpedia client, cache, search index
  surahs.py          surah names, aliases, verse counts (metadata only)
  extraction/        provider interface, Gemini provider, marked-quote extractor
  static/            index.html, styles.css, app.js, samples/*.txt
tests/               verifier, references, normalization, pipeline, source, Gemini tests
scripts/e2e_check.py end-to-end check of a running instance (samples + error cases)
docs/EVALUATION.md   plan for the labelled evaluation (not yet performed)
SOURCES.md           sources, licences and attribution record
BASELINE.md          pre-challenge baseline declaration
```

Sample articles are in `app/static/samples/` and can be loaded from the «مثال جاهز» menu.
Each contains some deliberately wrong quotations or references so every status can be demonstrated.

## Challenge submission checklist

- [ ] Live demo URL (Vercel), with `GEMINI_API_KEY` set and `/api/health` showing `"mode": "ai"`
- [ ] Public GitHub repository, with the `pre-challenge-baseline` tag pushed
- [ ] Source documentation: this README, [SOURCES.md](SOURCES.md) and [BASELINE.md](BASELINE.md)
- [ ] Demo video ≤ 2 minutes, with no API keys visible on screen
- [ ] Final PDF/PPT presentation (organizer template or matching identity)
- [ ] Labelled evaluation results (docs/EVALUATION.md), only once actually measured

## Licence

Code: MIT (see [LICENSE](LICENSE)). The Quran text is not included; it is fetched from
Quranpedia under its usage policy. Third-party sources and licences are listed in [SOURCES.md](SOURCES.md).

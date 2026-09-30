# مدقق الاقتباسات القرآنية — Quran Quotation Auditor

> **Pre-challenge work.** Everything in this repository was built **before
> 4 October 2026**: the git tag `pre-challenge-baseline` marks the first baseline
> commit, and every later commit dated before 4 October (including the Groq
> provider and the editor workflow added on 29 September) is also pre-challenge
> work. Only work committed during 4–6 October 2026 counts as challenge work.
> See [BASELINE.md](BASELINE.md) and [CHANGELOG.md](CHANGELOG.md).
>
> **AI status (30 Sep 2026): responds, adds nothing yet.** Groq (`qwen/qwen3.8-27b`) answered on all
> 3 samples and all 14 labelled cases, but proposed no quotation that the deterministic path had not already
> found (unmarked quotes still 1/4). Not yet live: the Vercel deploy is blocked and `GROQ_API_KEY` is not
> set there. See [docs/TEST_LOG.md](docs/TEST_LOG.md) and [docs/EVALUATION.md](docs/EVALUATION.md).

**AI Challenge Serving Islamic Content 2026 — Track 4: knowledge and verification tools.**

An Arabic, right-to-left web app for editors and reviewers. You paste a short Arabic
article, and the app:

1. finds every likely Quran quotation and any nearby surah/ayah reference,
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

---

## How it works

```
article ──► candidate extraction ──► locate in article ──► attach reference ──► verify ──► propose fixes ──► editor approves ──► revised article
            │ AI provider (Groq or     (reject anything      (regex parser,       (Quranpedia    (source words     (browser only)      + review record
            │   Gemini, one per audit)  not literally          nearest quote)       Hafs text,     only; none if
            │ marked ﴿…﴾ {…} «…»        present)                                   deterministic) span ambiguous)
            │ exact-run index scan
```

| Stage | What it does | Trust |
|---|---|---|
| **AI extraction** (`app/extraction/groq.py`, `gemini.py`) | The model returns JSON `{candidates:[{quote, reference_text}]}` copied from the article (Groq: strict `json_schema`). | Untrusted. Each quote is re-located in the article (diacritic- and spelling-insensitive); the finding's text is always the article's own substring, and anything not found is discarded and counted. |
| **Marked extraction** (`app/extraction/marked.py`) | ﴿…﴾ (in either order), {…}, and «…» / "…" / ((…)) when preceded by a cue such as «قال تعالى» or followed by a reference. | Deterministic. |
| **Index scan** (`app/audit.py`) | Unmarked runs of ≥ 5 article words that occur verbatim (after normalization) in the Quran. | Deterministic. |
| **Reference parser** (`app/references.py`) | `البقرة: 255`, `[البقرة ٢٥٥]`, `سورة البقرة، الآية 255`, `الآية 255 من سورة البقرة`, `2:255`, ranges, surah-only, common alternative surah names. Range-checked against verse counts. | Deterministic. |
| **Verifier** (`app/verifier.py`) | Exact search at three normalization levels, fuzzy alignment when nothing exact exists, word diffs, and reference checks. | Deterministic. Quranpedia text only. |
| **Corrections** (`app/verifier.py` `propose_wording`, `app/corrections.py`) | Turns a verdict into proposed changes with exact character offsets. | Deterministic. Replacement words come only from Quranpedia; see "Editor workflow". |
| **Revision** (`app/static/revision.js`) | Applies only the approved changes in the browser. | No server state. Refuses a change whose original text is no longer at its offsets, and overlapping changes. |

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

Without `GROQ_API_KEY` or `GEMINI_API_KEY`, the app runs in **reduced mode**. A yellow banner says so, and
only explicitly marked quotations plus verbatim runs of 5 or more words are checked, so
**short unmarked quotations can be missed**.

Run the tests (offline; they use a 36-verse excerpt in `tests/fixtures/`):

```bash
python -m pytest -q                      # Python tests + Node tests of the revision engine (if node is installed)
node --test tests/revision.test.mjs      # the revision engine alone

# browser end-to-end (Playwright installed in any scratch dir, not a project dependency)
NODE_PATH=/path/to/scratch/node_modules node scripts/ui_e2e.mjs http://localhost:8000 ./shots
python scripts/e2e_check.py http://localhost:8000   # API checks, samples, files that must not be served
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
  Malformed model JSON raises a handled error. In every AI failure the app falls back to
  marked-only extraction with a notice.
  These limits may cut off a slow but working Gemini response; that has not been observed
  yet, because no real Gemini call has succeeded (see docs/TEST_LOG.md).
- Articles are processed in memory and never written to disk or logged. Error handlers log
  only the exception type, and the API response does not echo the article back.
- The frontend inserts all text with `textContent` (never `innerHTML`), and a strict CSP blocks inline scripts.
- Secrets come only from environment variables. `.env` is git-ignored.

## Known limitations

- **No general accuracy claims.** A small author-written labelled set has been run in fallback
  mode only: 25/28 detected, 0 false "matched" verdicts, and 0 corrections proposed for correct
  quotes or references. See [docs/EVALUATION.md](docs/EVALUATION.md) for its limits. AI-mode results
  do not exist yet, because no real AI call has succeeded (Gemini 503/429; Groq key not yet set).
- Without working AI extraction, **short unmarked quotations (under 5 words) are missed**.
- Automatic corrections are deliberately conservative: a short fuzzy quote, or a phrase found in
  several verses, gets review information but no replacement.
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
  corrections.py     proposed changes with exact offsets (source words only)
  extraction/        provider interface, Groq + Gemini providers, call tracker, marked-quote extractor
  static/            index.html, styles.css, app.js, revision.js (browser revision engine), samples/*.txt
tests/               verifier, references, normalization, pipeline, source, Gemini, Groq, corrections,
                     revision-engine (Node) tests
scripts/e2e_check.py end-to-end API check of a running instance (samples, errors, files not served)
scripts/ui_e2e.mjs   Playwright browser check of the editor workflow, desktop + mobile
docs/LABEL_REVIEW.md checklist for a human reviewer of the evaluation labels
docs/CONTINUATION.md plan for 4–6 October and beyond (incl. the X use case)
docs/EVALUATION.md   labelled evaluation: method, fallback results, limits
docs/TEST_LOG.md     dated end-to-end observations (local + live)
eval/                labelled cases, label validator, scorer, raw results
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
- [ ] Labelled evaluation, AI mode — only after a real successful AI call on every case
- [ ] Human review of the evaluation labels (docs/LABEL_REVIEW.md)

## Licence

Code: MIT (see [LICENSE](LICENSE)). The Quran text is not included; it is fetched from
Quranpedia under its usage policy. Third-party sources and licences are listed in [SOURCES.md](SOURCES.md).

# End-to-end test log

> **Real AI extraction is UNVERIFIED as of the baseline.** No Gemini request has
> succeeded yet (Google returned 503 “high demand”, then a 429 quota error). All results
> below come from the deterministic marked/scan extraction, and only the AI *failure*
> handling has been exercised against the real service.

These are observations from running the app. They are **not** an accuracy evaluation:
three hand-written sample articles cannot measure accuracy. See `EVALUATION.md`.

## 2026-09-28 — pre-challenge baseline

Tool: `scripts/e2e_check.py` (the three samples in `app/static/samples/` plus error cases).
Environments: local (macOS, Python 3.14) and Vercel production
`https://quran-quote-auditor.vercel.app` (Python 3.12, Fluid compute, build region iad1).

### Gemini availability — AI extraction NOT yet verified end to end

No Gemini request succeeded on 2026-09-28, so AI candidate extraction has **not** been
observed working with a real model. Only its failure handling has been exercised live.

| When (UTC+3) | Where | Result |
|---|---|---|
| ~19:05 | local | `gemini-3.8-flash`: HTTP 503 “model is currently experiencing high demand” on all 3 samples |
| ~19:10 | direct API probe | 503 for gemini-3.8/3.7/3.5-flash, 3.5/3.1-flash-lite and flash-lite-latest; 429 quota for flash-latest (and later for 3.8-flash after repeated probes); 404 “no longer available to new users” for gemini-2.5-flash |
| ~19:30 | Vercel | 503 from the primary model, its retry, and both fallback models on all 3 samples |
| ~19:31 | Vercel, new instance | Gemini call hung until the 25 s AI time limit, then fell back (first audit took 27 s) |
| 19:33, 19:35 | Vercel (sample 3) | primary 503 → retry 503 → fallback `gemini-3.5-flash-lite` hung until the 25 s limit; fallback shown |
| 19:38 | Vercel (sample 3) | 429 quota exceeded on `gemini-3.8-flash` (free-tier quota used up, partly by the diagnostic probes); retries stopped |
| ~19:40 | local, direct | our extraction request to `gemini-3.5-flash-lite` with a 90 s limit: no answer (timeout); a one-line prompt got 503 in 2.6 s and our prompt without schema got 503 in 11.6 s. So the failures are Google-side capacity, not the request format. |

In every failed case the app fell back to reduced extraction (explicitly marked quotations
plus verbatim runs of 5 or more words) and showed a warning notice. It did not claim AI
extraction had run.

### Wording and reference results (identical locally and on Vercel)

These are marked/scan detections, since AI extraction was unavailable.

| Sample | Quotations | Observed verdicts (all as intended by the sample's design) |
|---|---|---|
| 1 — العلم | 5 | 4 matched (2 literal, 2 ignoring diacritics). «وَقُل رَّبِّ زِدْنِي عِلْمًا»: diacritics difference (idgham shadda) and reference «طه: 141» flagged as out of range (expected 114). |
| 2 — الصبر | 7 | «إن الله مع الصابرون»: fuzzy difference (الصابرون→الصابرين), needs review. «البقرة: 156» for a 155–156 quotation: uncertain. «الشرح: 6» for «فإن مع العسر يسرا»: incorrect (expected 5). Missing references reported. |
| 3 — no brackets | 3 of 4 | The three unmarked quotations of 5+ words were found by the index scan. «الإسراء: 32» was flagged incorrect (expected 23). «سورة الحجرات» was accepted as a surah-only reference. **Missed:** «وافعلوا الخير لعلكم تفلحون» (4 words), which reduced mode cannot detect by design; AI extraction is needed for it. |

### Error handling (local and Vercel)

- Empty article → 400. Over 6,000 characters → 400. Wrong JSON field → 422. Malformed JSON body → 422.
- Markup in the article → 200, and the article is not echoed back.
- Invalid Gemini key (local) → Gemini 400 → `ai_failed` fallback with a notice.
- Paths `/.env`, `/.env.local`, `/app/config.py`, `/requirements.txt` and the test fixture all return 404 on Vercel.
- Vercel function logs for the test period contained no Arabic text and no key material.

### Quran source caching on Vercel (observed)

- Cold `/api/health` on a fresh instance: 0.66 s. The Quran text loads on the first audit (locally about 1.2 s to fetch and index).
- One Quranpedia request per instance. Later requests on the same instance reused the in-memory copy (`instance_started` unchanged, one `GET /v1/mushafs/1` in the logs).
- A redeploy started a new instance (`instance_started` changed), which fetched the text again. The cache does not persist across instances or deployments; see README “Actual limits on Vercel”.

### Fallback wait reduced (after the baseline commit, still 2026-09-28)

The 25–27 s wait before fallback was too long for a live demo. The new defaults are a 12 s
total AI budget, 8 s per attempt, no retry of a model that hung, and a 60 s per-instance
cooldown after a failure (120 s after 429). Measured locally against an endpoint that never
replies: first audit **12.0 s**, next audit **0.0 s** (AI skipped during the cooldown, with a notice).

### Independent live check by the project owner (2026-09-28)

The project owner ran the live «مقال عن الصبر» sample in the browser. Gemini failed and the
app fell back, showing **7 findings, 3 needing review, in about 1.9 s**. This matches the
scripted runs above (7 findings, 3 needing review).

### Labelled fallback evaluation

See `EVALUATION.md`: 25/28 gold quotations detected, 0 false "matched" wording or
references, and 0 findings on 5 non-Quran negatives. The three misses are short unmarked quotes
that need AI extraction.

### Deployment of the AI-status banner (2026-09-28)

- Vercel blocked CLI deployments of commits `07a777a` and later: the commit author (a GitHub
  no-reply address) could not be matched to the Vercel account, even after the owner connected GitHub.
- With the owner's approval, the app was deployed from a `git archive` export of the commit
  (identical files, no `.git`, no `.env`). Commit `2860743` is live.
- Verified on the live URL with a page load only (no audit, so no Gemini call). The banner reads
  «الاستخراج بالذكاء الاصطناعي مُعَدّ — Google Gemini (gemini-3.8-flash). لم يُستدعَ بعدُ على هذا الخادم…».
  `/api/health` shows `ai_last_call.outcome = "never_called"`. There were no console errors and no POST requests.

## 2026-09-29 — single post-reset Gemini check

- At 10:07:12 (UTC+3), after the daily free-tier quota reset, **exactly one** minimal request was sent: `gemini-3.8-flash`, prompt "Reply with ok".
- Result: **HTTP 503 UNAVAILABLE** in 1.5 s, «This model is currently experiencing high demand. Spikes in demand are usually temporary.»
- Following the agreed plan, no further diagnostic calls were made, and the end-to-end runs were not repeated.
- **AI extraction remains UNVERIFIED.** No Gemini request has succeeded with this key so far.

## 2026-09-29 (evening) — Groq adapter and editor workflow (pre-challenge)

### Real AI calls: none

- **No `GROQ_API_KEY` exists** in the environment, `.env` or `.env.local`, so **no real Groq request was made**.
  The Groq adapter is covered only by offline tests with a mocked HTTP transport. Those tests prove the
  request shape (strict `json_schema`, `reasoning_effort: "none"`, bearer header) and the failure handling
  (429/401/498/5xx/400/404, timeout, malformed or truncated JSON, cooldown, one call per audit). **They do
  not show that the real model extracts quotations.**
- Following the plan after the 10:07 check, **no further Gemini calls** were made.
- `python eval/run_eval.py --mode ai` was run once with no key configured: it refused ("NOT AN AI RUN"), exit code 2.
- **AI extraction remains UNVERIFIED** for both providers.

### Offline tests

`python -m pytest -q` → **125 passed** (Python 3.14, macOS). New since the baseline: Groq provider (25 incl.
provider selection and health), corrections (26: offsets, repeated phrases, multi-verse excerpts, ambiguous
fuzzy matches, pinpointing references, diacritics, hamza, short phrases, missing references, source outage,
AI failure, AI-invented text, markup, emoji/CRLF offsets, preservation of all non-change text, reference
formatting) and the browser revision engine under Node (9 Node tests run by 1 pytest wrapper: approval gating, code-point offsets with emoji,
stale offsets refused, overlaps refused, repeated text, byte-identical preservation, preview, unresolved logic;
plus 1 added later for the social-post reply draft → 10).

### Local end-to-end (reduced mode — no AI key)

- `python scripts/e2e_check.py http://localhost:8765` → 0 failures. The three samples give the same verdicts as
  on 28 Sep (5 / 7 / 3 findings). Proposed changes observed, all with offsets matching the article:
  - sample 1: «رَّبِّ» → «رَبِّ» (diacritics, flagged as a possible print-convention difference) and «طه: 141» → «طه: 114»;
  - sample 2: «الشرح: 6» → «الشرح: 5», «البقرة: 156» → «البقرة: 155-156», optional «[الشرح: 6]» insertion;
    «إن الله مع الصابرون» gets **no** automatic fix because several verses are equally close and no ayah is cited;
  - sample 3: «الإسراء: 32» → «الإسراء: 23», optional «(المائدة: 2)» insertion;
  - optional full-vocalization changes for correct unvocalized quotes (never counted as errors).
- Files that must not be served (`/.env`, `/.env.local`, `/.env.example`, `/app/config.py`, `/requirements.txt`,
  `/eval/cases.json`, the test fixture, `/.git/config`, `/.vercel/project.json`, a `%2e%2e` traversal) → all 404.
- Browser (Playwright, Chromium 1440×900 and 390×844 mobile): `scripts/ui_e2e.mjs` → **26/26 checks passed** (24 at first, 2 added for the reply draft):
  sample 2 audit (7 findings); revised article identical to the input before any approval; approving
  «الشرح: 6» → «الشرح: 5» changes only that span (line count unchanged); rejecting an optional change;
  before/after preview with deletions, insertions and unresolved marks; copy to clipboard; review-only
  filter (3 of 7); print record contents (title, "not a certificate", approved change, source link, source
  time, AI status, unresolved items) and an A4 PDF; decisions restored after reload; markup pasted into the
  article is shown as text and never executed; no horizontal scroll on mobile; no console errors.

### Labelled evaluation (fallback)

See `EVALUATION.md`. Same labels, same detection results as 28 Sep; new correction scoring: 6/6 detected
wording/diacritics errors receive a fix that re-verifies against Quranpedia, 4 correct reference fixes,
2 reference problems left for review, **0 fixes proposed for correct quotes or references**.

### Deployment attempt (29 Sep, ~20:55 UTC+3)

- Set a non-secret production variable `AI_PROVIDER=groq`, so that the new code will not call Gemini
  (the production Gemini key and two fallback models would otherwise be tried on every audit). It takes
  effect only after a successful deploy; the Gemini adapter stays available (`AI_PROVIDER=gemini`).
- `npx vercel deploy --prod` from the repository → deployment `dpl_gPoudmAxLk4B3UscEdFduVcQ3oXu` **Blocked**:
  «The deployment was blocked because the commit author doesn't have permission to create deployments
  for this project.» As instructed, no workaround was used (no archive upload, no change of commit author).
- The live site therefore still serves commit `2860743` (28 Sep). Read-only check: `/api/health` → `mode: ai`,
  Gemini, `ai_last_call.never_called`; `/static/revision.js` → 404 (new code not live). **No public audits
  were run**, because they would have spent Gemini calls on the old code.

### Submission drafts (local, git-ignored `submission/`)

- Deck updated and exported to PDF; rendered with Readex Pro and inspected slide by slide.
- Video draft `submission/video/demo-B-draft.mp4`: **1:44**, H.264/AAC 1280×720, recorded with Playwright from
  the local app in reduced mode, synthetic narration (macOS voice "Majed"). Frames checked for each scene.
  It is variant B only (no AI shown).

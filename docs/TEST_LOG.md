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

## 2026-09-30 — first real Groq calls (pre-challenge: dated before 4 October)

### Minimal call

- 16:58:13 (UTC+3), local, key from `.env` (not printed): `qwen/qwen3.8-27b`, prompt "Reply with ok",
  `max_completion_tokens` 8, `reasoning_effort: "none"` → **HTTP 200 in 0.76 s**, reply `ok`, finish `stop`,
  17 tokens. Account limits in the response headers: 1,000 requests and 8,000 tokens per minute.
- **AI extraction is now verified to respond**. It is **not** shown to add detections (see below).

### Three samples, local, `AI_PROVIDER=groq` (`scripts/e2e_check.py http://localhost:8765`)

| Sample | AI outcome | Model candidates (proposed / located / discarded) | Findings |
|---|---|---|---|
| 1 — العلم | ok, HTTP 200, 753 ms | 5 / 5 / 0 | 5 (same verdicts as 28–29 Sep) |
| 2 — الصبر | ok, HTTP 200, 278 ms | **0** / 0 / 0 | 7 (same) |
| 3 — no brackets | ok, HTTP 200, 346 ms | **0** / 0 / 0 | 3 (same). «وافعلوا الخير لعلكم تفلحون» is **still missed**. |

- The UI shows `mode = ai` and names Groq. Error cases and the must-not-serve paths: all as expected, 0 failures.
- One extra direct request with the app's exact request body for sample 3 returned `{"candidates": []}`
  (464 prompt tokens, 7 completion tokens, finish `stop`). The empty result is the model's answer, not a parsing loss.

### Labelled evaluation, AI mode (unchanged labels and scoring)

`python eval/run_eval.py --mode ai` → all **14/14 cases responded** (HTTP 200, 258–507 ms per call); raw output
`eval/results/ai-20260930-165858.json`. Every detection, verdict and correction number is **identical to fallback**:
25/28 detected, unmarked 1/4, 0 false "matched", 0 fixes for correct text. The model proposed 16 candidates
in total (all located, 0 discarded), only in cases whose quotations are already marked. It proposed **nothing**
for c11 and c12 (the unmarked short quotes it is meant to add), nor for c05, c06, c07 and c13 (c13 has only non-Quran negatives, so empty is correct there). See `EVALUATION.md`.

### Browser workflow, local with Groq live

`scripts/ui_e2e.mjs http://localhost:8765` → **26/26 passed** (approve/reject, revised article, preview, copy,
reply draft, filter, review record, reload, markup safety, mobile, no console errors). `pytest` → 125 passed.

### Deployment — blocked again; live workflow not tested

- `GROQ_API_KEY` is **not** in the Vercel project's variables (`vercel env ls`: only `AI_PROVIDER`,
  `GEMINI_API_KEY`, `GEMINI_FALLBACK_MODELS`, all Production).
- `npx vercel deploy --prod` (account `fhalfaifi`, commit `f51bbc3`) → deployment `dpl_EVKfRAaDXspKgYm2Gh4zimrvCfra`
  **Blocked**: «the commit author doesn't have permission to create deployments for this project». The commit author is
  `281715064+FHALFAIFI@users.noreply.github.com`. No workaround was used. The live site still serves `2860743` (28 Sep),
  so the editor workflow was **not** tested on the live URL.

## 2026-09-30 (evening) — short unmarked quotations experiment (pre-challenge)

Full tables: `docs/EVALUATION.md`, "Experiment". Labels unchanged (`git diff eval/cases.json` empty).

- 17:40 raw probe, qwen + v1, c11/c12: both `{"candidates": []}` (HTTP 200, 1514 / 304 ms).
- 17:41 new held-out set `eval/heldout.json` written and validated (`validate_labels.py eval/heldout.json` → labels OK)
  before any prompt or model change was run. Fallback baselines: labelled 25/28, held-out 3/6.
- 17:41 raw probe, qwen + v2, c11/c12: c11 `[]`; c12 both quotations including «ادعوني أستجيب لكم».
- 17:41 qwen + v2 full run → **stopped at c03, HTTP 429** (not saved; the runner saved stopped runs only from 17:43).
- 17:43 qwen + v2, 10 s pacing → stopped at c02, 429 (`stopped-20260930-174303-qwen-v2.json`).
- **Cause of the 429s:** the Groq error body says *output tokens per minute (OTPM): Limit 1000, Requested 1457*.
  Groq counts an *expected* output per request (≈1,300–1,450 here, while the real output was ≈80 tokens), so
  requests close together are rejected. The same request succeeds when spaced out. `x-ratelimit-*` headers show only
  the 8,000 tokens/min and 1,000 requests limits, not this one. **Live impact:** two audits within about a minute
  can make the second fall back (announced in the UI as a quota error). Not fixed; lowering `max_completion_tokens`
  was not tested.
- 17:52 qwen + v2, 30 s pacing → 14/14 responded: **26/28, unmarked 2/4** (`ai-20260930-175238-qwen-v2.json`).
- 17:53 raw probe, gpt-oss-120b + v2 (`reasoning_effort` low): c11 «وافعَلوا الخير» (diacritic added), c12 only the Nahl quote.
- 18:00 gpt-oss-120b + v2 → 14/14: **26/28, unmarked 2/4** (`ai-20260930-180026-gptoss120b-v2.json`).
- 18:01–18:05 held-out: qwen v1 stopped (429, h02); qwen v2 stopped (429, h03); gpt-oss v2 → 3/6.
- 18:10 held-out qwen v1, 65 s pacing → 3/6, 0 candidates. 18:14 qwen v2, 65 s → stopped (429, h04).
- 18:24 held-out qwen v2, 120 s pacing → **4/6, unmarked 3/5**.
- Chosen: qwen + v2, now the default. `pytest` → 126 passed.

## 2026-09-30 — Vercel deployment block: diagnosis

- GitHub attributes `71769ae` and `f51bbc3` to **FHALFAIFI** (id 281715064). The author address is
  `281715064+FHALFAIFI@users.noreply.github.com`, the ID-based private address format. The Settings → Emails page itself
  could not be read (the CLI token lacks the `user` scope).
- The Vercel project is owned by user `fhalfaifi` (Hobby, OWNER of team `fahad-dce3`). The project has no Git link.
  The owner confirmed that GitHub **FHALFAIFI is already connected** under that Vercel login.
- Pattern across the last 10 production deployments: every **BLOCKED** one carried git metadata with the noreply
  author, and every **READY** one had no git metadata.
- 17:48 deploy of committed `71769ae` from a clean git worktree → `dpl_7m3aDYoWRPCKfnAMi9iq4meH1ZY1` **READY**.
  But the CLI attached **no git metadata** from the worktree, so this deploy **did not go through the author check**.
  It does not show the block is fixed. Live now serves `71769ae`, reduced mode (`GROQ_API_KEY` not set).
- 18:3x ordinary `vercel deploy --prod` from the main checkout, clean tree, commit `3273078` →
  **`dpl_9HzjDrVyKBmLBy8UAw2bUfZs3Qbf` BLOCKED** again, although the GitHub connection is confirmed. Findings and a
  support message are prepared (local, `submission/VERCEL_SUPPORT.md`). Live still serves `71769ae` (prompt v1, no key).

## 2026-09-30 (19:0x UTC+3) — completion-token reservation experiment (pre-challenge)

Question: does a smaller `max_completion_tokens` avoid the 429 seen at 17:43 (*OTPM: Limit 1000, Requested 1457*)?
`max_completion_tokens` is now configurable (`GROQ_MAX_COMPLETION_TOKENS`, default unchanged at 4096).
`eval/experiments/token_reservation.py 4096 1024 512 256`: qwen + v2, all 14 labelled + 4 held-out cases (18 per size, 72 calls) sent
back-to-back, 65 s between reservations. Raw: `eval/experiments/raw/20260930-190941-reservation-qwen_qwen3.8-27b-v2.json`.

| Reservation | 200 OK | finish `stop` + JSON parses | Max real output | First 429 | Limit in the 429 body |
|---|---|---|---|---|---|
| 4096 | 13 (≈7 s) | 13/13 | 91 tokens | c14 | **ITPM** 7,000 (used ≈6,700, requested 587) |
| 1024 | 13 | 13/13 | 91 | c14 | ITPM |
| 512 | 13 | 13/13 | 91 | c14 | ITPM |
| 256 | 13 | 13/13 | 91 | c14 | ITPM |

- **No OTPM 429 in any run, including 4096**: 13 calls in about 7 s, 631 real output tokens. The limit hit was
  **input** tokens per minute (each audit sends ≈550–615 prompt tokens, so ≈11–12 audits per minute).
  The smaller reservation made no difference, so the hypothesis is **not supported** today. The 17:43 OTPM body was
  not saved (only the text in this log), so the difference cannot be re-examined.
- Complete, schema-valid JSON came back at every size down to 256 on these short articles. Real output reached
  91 tokens; an article at the 6,000-character limit with many quotations could need more, so a small reservation
  risks `finish_reason: length`, which the app treats as a failure. **Default kept at 4096.**
- c14 and the 4 held-out cases (6 quotations) got HTTP 429 at every size: 5 failures per size, 20 of 72 calls in total, all ITPM. They were not scored and no held-out output exists from this experiment. One case (c10) returned 2 candidates at 512 and
  0 at the other sizes, although `temperature` is 0: output is not fully deterministic.
- `pytest` → 126 passed.

**Conclusion (reviewed 30 Sep, 20:3x; no further Groq calls).** Re-tabulated from the raw file: 72/72 calls recorded.
At every size, the 13 cases that returned 200 had `finish_reason: stop`, JSON the app parses, and the same candidate
count as at 4096. The one difference, c10 at 512 (2 candidates vs 0), is a *gain*, and it is attributed to
call-to-call variation rather than to the reservation. So no size lost a candidate. The evidence is still **inconclusive for choosing a smaller value**:
- The reservation had no effect on the 429s, so a smaller value has no benefit today.
- Every test article is 70–228 characters, under 4% of the 6,000-character limit. Real output was 7 tokens for an empty list
  plus 18–46 tokens per candidate. At the cap of 40 candidates that is roughly 700–1,850 tokens, which can exceed
  1,024 and would far exceed 256 or 512.
- The 5 rate-limited cases per size, including all held-out cases, were never observed.
- Each size ran once.

**`GROQ_MAX_COMPLETION_TOKENS` stays at 4096.** Revisit only with long articles and repeated runs.
- Also added (offline): `test_rate_limit_is_a_visible_fallback_never_an_ai_result`. A 429 gives `mode: ai_failed`,
  a visible warning, and no finding tagged `ai`. The next audit is skipped during the cooldown. `pytest` → 127 passed.


## 2026-09-30 (20:3x UTC+3) — Render start command, local (pre-challenge; no Render service yet)

Clean `git archive 3273078` in a temp dir, Python 3.12.13 (from `.python-version` `3.12`), `requirements.txt`
installed into a fresh venv (uv), then the Render start command `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
with `PORT=10000`, `AI_PROVIDER=none`, no keys: `/api/health` 200 (`mode: reduced`), `/` 200, `POST /api/audit`
with sample 2 → 200, 7 quotations, 3 need review, source available. No Groq call. Steps for tomorrow: `docs/RENDER_DEPLOY.md`.

## 2026-09-30 (evening) — unmarked phrase search (pre-challenge)

Full tables and method: `docs/EVALUATION.md`, "Experiment — unmarked phrase search". Labels of `eval/cases.json` and `eval/heldout.json` unchanged (`git diff` empty).

**Deterministic path first (no Groq calls):**
- 20:45 baseline of the unchanged code (`8a4b8b7`), fallback mode: main 25/28 (unmarked 1/4), held-out 3/6 (2/5). Raw: `fallback-20260930-204519-baseline-cases.json`, `…204520-baseline-heldout.json`.
  The four unmarked quotations that AI mode (Groq `qwen/qwen3.8-27b`, prompt v2) still missed: c11 ×2, h02, h03; without AI two more (c12 «ادعوني أستجيب لكم», h01 «وقل رب زدني علما»).
- 20:49 baseline resources (`scripts/measure_resources.py`, fresh processes, macOS, Python 3.14): index load 0.45 s, peak 97.6 MB in-process (`eval/results/resources-baseline-8a4b8b7.json`).
- 20:55 **frozen set** `eval/phrases_frozen.json` written and validated (`eval/validate_phrases.py`, `validate_labels.py` both "labels OK"), baseline run of the unchanged code:
  18/32 detected, **8 misquotations reported "matched"**, 1 negative and 1 formula shown as confirmed (`…205537-baseline-phrases-frozen.json`). SHA-256 in `eval/phrases_frozen.sha256`; committed as `7ac49a3` **before any detection code**.
- 21:0x–21:2x development on other data: a 1,704-case synthetic benchmark, 31 secular + 20 Islamic-topic Wikipedia articles (local, not committed). Parameter sweeps
  (mass floor 10–16, candidate mass 18–22, near-match mass 12–22, minimum near-match words 3–5) and the intermediate runs on the main/held-out sets are in `eval/results/dev-iterations/`.
  Wikipedia answered HTTP 429 when asked too fast; the download job paused and retried.
- 21:17 **frozen run 1**: 30/32 detected; 1 misquotation "matched"; 2 negatives shown as `possible`; 0 shown as confirmed. It exposed two defects (a correct quotation stretched over a neighbouring
  prose word through one weak near-match word; a pre-filter that rejected a one-letter change inside a word). Fixed without changing any threshold; tests added.
- 21:20 **frozen run 2**: 30/32 detected; 2 misquotations "matched" (wrong words at the end of the quotation); 2 negatives shown as `possible`; 0 as confirmed. Both runs kept (`…211719-phrases-frozen-run1.json`, `…212006-phrases-frozen-run2.json`).
- 21:49 final deterministic runs on main, held-out and the frozen set (run 3, after lowering the work budget): 27/28 (unmarked 3/4), 6/6 (5/5), 30/32 — identical in every finding, tier, verdict and source to the runs before the budget change
  (`…214906-final2-cases.json`, `…214913-final2-heldout.json`, `…214914-phrases-frozen-run3-after-budget-change.json`).
- Untuned prose (never used for tuning): 5 secular articles 18,612 words → 1 candidate, 0 "maybe"; 7 Islamic-topic articles 19,794 words → 188 candidates (185 vocalized/bracketed), 57 possible-exact (36 outside brackets), 10 possible-near (8 outside), 43 hidden.
- Tests: `pytest` 167 passed (incl. fuzz of offsets, `tests/test_phrases_full.py` against the cached real text); `node --test tests/revision.test.mjs` 11 passed.
  Browser: `scripts/ui_e2e.mjs` (old workflow) all PASS on the new code; `scripts/ui_phrase_e2e.mjs` (candidate vs maybe, confirm a verse, manual selection, mobile) all PASS. A 2,500-article fuzz (real phrases, mutations, punctuation, digits, ﷺ) gave
  4,286 findings and 3,252 proposed changes with 0 offset errors, 0 overlaps and 0 changes attached to an unconfirmed «maybe» (slowest audit 0.15 s).

- **Resources** (fresh processes, median of 5, macOS/arm64, Python 3.12.13 = Render's version; `eval/results/resources-py312-*.json`): in-process peak 93.8 MB → 75.7 MB, index 93.0 → 69.9 MB; real `uvicorn` server peak 112.8 MB → 94.1 MB,
  process start → first audit 0.74 s → 0.72 s; 6,000-char unmarked mushaf run 0.023 s → 0.395 s; frequent-word soup 0.007 s → 0.803 s (cut off by the work budget).
  Earlier Python 3.14 measurements: baseline in-process peak 97.6 MB, baseline server 120.6 MB, phrase search server 103.2 MB (`resources-baseline-8a4b8b7.json`, `resources-py314-*.json`; the "rss_after_all" field of the 3.14 baseline server run read the `time` wrapper, not the server, and is ignored).
- **Full-size articles** (in-process, Python 3.12, whole audit of ~900–1,000-word Wikipedia chunks, final code): secular prose median 130 ms / p95 ≤ 0.22 s (129 chunks); Islamic-topic prose median 247–297 ms / p95 ≤ 0.40 s / max 0.43 s (92 chunks). Much slower than the old scan; Render's CPU will be slower still (untested).
- **Work budget:** the first worst-case measurement (frequent-word soup) took 1.9 s with a 400,000-step budget; real text needed at most 41,131 steps (religious prose) / 1,957 (evaluation articles), so the budget was lowered to 80,000 (soup 0.8 s). Results on all three sets were identical afterwards.

**AI compared separately (Groq `qwen/qwen3.8-27b`, prompt v2, after the deterministic runs; free tier):**
- 21:21 frozen set, pace 12 s → **stopped at f18, HTTP 400** after 17 successful cases (`stopped-20260930-212439-phrases-frozen-ai.json`, not an AI result). One diagnostic call for the same article immediately afterwards returned 200 with an empty list, so the 400 was not reproducible.
- 21:25 main set, default settings, 14/14 responded: 28/28 detected, unmarked 4/4 (`ai-20260930-212840-ai-cases-new-pipeline.json`). 21:30 held-out set, 4/4 responded: 6/6, unmarked 5/5 (`ai-20260930-213033-ai-heldout-new-pipeline.json`).
- 21:39 frozen set again, pace 12 s → **stopped at f03, HTTP 429** (`stopped-20260930-213957-phrases-frozen-ai-attempt2.json`). The 429 body: *output tokens per minute (OTPM): Limit 1000, Requested 1100* (input budget untouched: `x-ratelimit-remaining-tokens: 8000`).
  A single probe with `GROQ_MAX_COMPLETION_TOKENS=512` succeeded. (Earlier, on the input-token limit, the cap made no difference; this time it did for one probe. Not a controlled test.)
- 21:40 frozen set with `GROQ_MAX_COMPLETION_TOKENS=512`, pace 15 s → **stopped at f09, HTTP 400** after 8 successes (`stopped-20260930-214251-phrases-frozen-ai-attempt3-maxtok512.json`).
- Added `--retry-400 N` to `eval/run_eval.py` (retries only HTTP 400, every retry recorded, 429 and other failures still stop the run).
- 21:43 fourth attempt (cap 512, pace 15 s, `--retry-400 1`): **completed — 49/49 responded, one case (f18) retried after a transient 400** (`ai-20260930-215601-phrases-frozen-ai-attempt4-maxtok512-retry400.json`):
  30/32 unmarked detected, same two misses (f21, f29); 4 candidates proposed (3 located, 1 discarded: «لا تزر وازرة وزر أخرى», the article has «ولا تزر…»); 2 findings on negatives, both `possible`, 0 shown as confirmed;
  2 misquotations still "matched". The AI re-labelled 3 findings (f07, f15 vocalized exact; f26 misquotation) as found-by-AI; no new detection.
- Groq calls made for this comparison: 101 in total — frozen attempt 1: 18 (17 ok + the 400), main 14, held-out 4, attempt 2: 3 (2 ok + the 429), attempt 3: 9 (8 ok + the 400), attempt 4: 50 (49 + 1 retry), and 3 single diagnostic calls (the f18 article; the 429 probe; the 512-token probe).
- Main (21:25) and held-out (21:30) AI passes used the defaults (completion cap 4096, pace 12 s, no retries); the frozen pass used cap 512, pace 15 s, one retry on 400 (temperature 0, so the cap only matters if an output exceeded 512 tokens).

## 2026-10-01 — end-boundary release blocker (Pre-challenge, no Groq call)

- Trace of f23/f32 and the rule: `docs/EVALUATION.md`, "Release blocker". Before the change, on HEAD `d7cf6cd`: frozen run → 2 misquotations "matched" (`eval/results/fallback-20261001-054703-boundary-before-d7cf6cd-phrases_frozen.json`).
- New tests: 7 end-boundary tests in `tests/test_phrases.py` (wrong last word; dropped words; correct partial quotation closed by a full stop / line break / article end / bracketed or bare reference; verse end; quotation followed by prose, comma vs full stop;
  reference "matched" beside wording "uncertain"; marked, manual and AI-chosen ends), 2 real-text tests for f23 and f32 in `tests/test_phrases_full.py`, 5 Groq error-body tests. Run against the old `audit.py`, 9 of them failed; with the change `pytest` → 183 passed. `node --test tests/revision.test.mjs` 11 passed.
- Browser: `scripts/ui_phrase_e2e.mjs` 0 failures (22 checks), `scripts/ui_e2e.mjs` 0 failures, `AI_PROVIDER=none`.
- Rerun, fallback mode, labels unchanged, `eval/phrases_frozen.sha256` OK: false "matched" wording 2 → 0 (frozen), 0 → 0 (main, held-out); detection and tiers identical; correct quotations read "matched": main 18 → 17, held-out 6 → 5, frozen 15 → 6 (of 15 expected). Raw: `…-boundary-after-fix-*.json`.
- Groq: the bodies of the two HTTP 400s had never been recorded (the adapter dropped them), so they could not be inspected. Adapter and harness changed as described in `docs/EVALUATION.md`. No Groq call was made.

- **Clean build of commit `01dcdc5`** (`git archive` into an empty directory, uv, Python 3.12.13): `requirements-dev.txt` → `pytest` 183 passed; `requirements.txt` only → `uvicorn app.main:app --host 0.0.0.0 --port 10000` (the Render start command, no AI key, `AI_PROVIDER=none`):
  `/api/health` 200, `/` 200, `POST /api/audit` on f08, f23, f32 → wording "uncertain" with end boundary "uncertain" (f23/f32 are no longer "matched"). The three sets rerun from the clean tree gave rows identical to the pre-commit rerun (false "matched" wording 0 / 0 / 0, reference 0); `eval/phrases_frozen.sha256` verifies. Nothing was deployed. The follow-up commit that records this changes only this file.

## 2026-10-01 — start-boundary rule (Pre-challenge, no Groq call)

- Rule and result: `docs/EVALUATION.md`, "The start of an unmarked quotation". Rerun, fallback mode, on unchanged HEAD `df94548` (before) and after the change: correct quotations read "matched" 28 → 25 (main 17 → 17, held-out 5 → 3, frozen 6 → 5); detection, tiers, labels and reference verdicts identical row by row; false "matched" 0 everywhere. Raw: `eval/results/fallback-*-start-before-df94548-*.json`, `…-start-after-boundary-*.json`. `eval/phrases_frozen.sha256` OK.
- New tests: 9 in `tests/test_phrases.py` (wrong first word; correct quotation after prose, comma and not; opened by full stop / colon / quotation mark / «قال تعالى» / «في القرآن الكريم» / preceding reference / article start; verse start; a lead-in that does not touch; both ends uncertain; wording "uncertain" beside reference "matched"; marked, manual and AI-chosen starts; the confirm-boundaries round trip), 2 real-text tests in `tests/test_phrases_full.py` (frozen f07, held-out h01). Against the unchanged `app/`, 11 of them fail; with the change `pytest` → 194 passed (Python 3.14 venv). `node --test tests/revision.test.mjs` 11 passed.
- Browser (`AI_PROVIDER=none`, local): new `scripts/ui_boundary_e2e.mjs` 20 checks passed (explanation, previous words, adjust → span selected and check button enabled, confirm → «مطابق»); `scripts/ui_phrase_e2e.mjs` 22 PASS, `scripts/ui_e2e.mjs` 0 failures. (A back-to-back run hit the app's own 60 s rate limit once; rerun after a minute.)
- Clean build of `9db8336` (`git archive`, no `.venv`, Python 3.12.13 via uv, `requirements-dev.txt`): `pytest` 194 passed; `uvicorn app.main:app --host 0.0.0.0 --port 10000` with `AI_PROVIDER=none`: `/api/health` 200, `/` 200, `scripts/e2e_check.py` failures: 0 (sample 3: 4 quotations, 1 matched, 3 uncertain; before: 2 and 2). Nothing was run on Render itself at this point.

## 2026-10-02 — live checks on Render (Pre-challenge)

Service `https://quran-quote-auditor.onrender.com`, user-reported deploy of commit `91f6a30` (code `9db8336`). The instance reports no commit, so the deployed commit was **not** read from Render; what was observed is below.
Checks ran from the local machine (`scripts/e2e_check.py`, the three `scripts/ui_*_e2e.mjs` with Playwright, two direct API probes). No Groq call was made by me and none could be made: the service has no AI key.

**Live failure: AI is not configured on the deployed service.** `/api/health` (three reads, 0.4–0.6 s): `mode: "reduced"`, `ai_configured: false`, `provider: null`, `provider_name: null`, `ai_selection: "auto"`, `ai_last_call: null`.
That is what an instance without `AI_PROVIDER=groq` / `GROQ_API_KEY` looks like (`docs/RENDER_DEPLOY.md`, "Environment variables"). Every audit returned `ai: {configured: false, responded: false, outcome: "not_configured"}` and `mode: "reduced"`. So the "one real Groq audit" step is **not done**, and no live request used AI.

**Which requests used AI: none.** All 3 samples, the 3 error cases, the 2 direct probes, the `/api/phrase` call and every browser flow ran in the deterministic fallback (`mode: reduced`). `/api/phrase` never calls Groq by design.
Findings carry `detected_by` of `marked`, `phrase` or `manual` only; none carries `ai`. Fallback is therefore the only behaviour observed live. Nothing about AI on Render is verified.

**Which code is live (indirect).** `/`, `/static/app.js`, `/static/revision.js`, `/static/styles.css` are byte-identical (SHA-256) to the files in `91f6a30`. Backend: sample 3 → 4 quotations, 1 matched, 3 uncertain (start/end boundary rules of `01dcdc5`/`9db8336`; before them 2 and 2), identical to the clean-build result for `9db8336`. This is consistent with `91f6a30`, not proof of the hash.

**Source and cold start.** First audit after the instance started (`instance_started` 2026-10-01 21:00:39 UTC = 2026-10-02 00:00 Riyadh, about 2 minutes before the first request; Quran text fetched 21:03:01 UTC): sample 1, 8.9 s (Quran text fetched from Quranpedia, `loaded_from: network`, 6,236 ayahs, `last_error: null`); later audits 0.5–0.8 s. Health before the first audit: `source.loaded: false`.

**API (`e2e_check.py`): failures 0.** Sample 1: 5 quotations, 4 matched, 1 difference (طه: 141 → 114 reference error and a diacritic). Sample 2: 7 quotations, 6 matched, 1 difference («الصابرون» → «الصابرين», no automatic fix, manual choice offered), 3 needing review. Sample 3: 4 quotations, 1 matched, 3 uncertain, each uncertain one with its boundary explanation, 1 reference wrong (الإسراء: 32 → 23). Error cases: empty 400, too long 400, wrong field 422, malformed JSON 422, markup 200 without echoing the article. 11 sensitive paths (`/.env`, `/app/config.py`, `/.git/config`, …) all 404.

**Wrong word.**
- Marked, `﴿وافعلوا الشر لعلكم تفلحون﴾ [الحج: 77]`: wording `difference/fuzzy`, diff `replace الشر → الْخَيْرَ`, needs review. Marked sample-2 quotation «إن الله مع الصابرون» likewise `difference/fuzzy`.
- Unmarked, same words without marks (`وقال تعالى: وافعلوا الشر لعلكم تفلحون (الحج: 77) …`): **0 findings, not detected** (live and locally with `AI_PROVIDER=none`). A four-word phrase with one wrong word is below the unmarked search's mass floor; with AI configured the model might propose it, which is untested. This is a known limit, not a new regression.
- Wrong first/last word of an unmarked quotation (sample 3): reported "uncertain", never "matched" (see above).

**Manual boundary.** Browser, live: `ui_boundary_e2e.mjs` 20 checks all PASS (uncertain chip, explanation with article's and the Quran's neighbouring word, «عدّل الحدود بنفسك» selects exactly the span, «افحص المقطع المحدَّد» enabled, «حدود الاقتباس صحيحة» turns it «مطابق»); `ui_phrase_e2e.mjs` 22 PASS, 0 failures (candidate vs maybe, confirm a verse, manual selection, mobile); `ui_e2e.mjs` (old workflow: sample, approve/reject, revised article, review record) 26 PASS, 0 failures. Direct `POST /api/phrase` with a highlighted span and surah 5, ayah 2: 200, `detected_by: manual`, wording `matched/diacritics`, source المائدة: 2, reference missing.

**Rate limit.** The app allows 10 requests/min per IP; the scripts were spaced ≥ 70 s apart and no 429 occurred.

**Not done / open:** (1) AI on Render: needs `AI_PROVIDER=groq`, `GROQ_API_KEY`, `GROQ_MODEL=qwen/qwen3.8-27b`, `EXTRACTION_PROMPT=v2` in the Render dashboard (user's step), then `/api/health` should read `mode: ai`, `ai_configured: true`, `ai_last_call: never_called`, and one audit (about 550–615 input tokens) logged. (2) The deployed commit hash from the Render Events tab. (3) Latency/memory on Render beyond the cold start above.

### 2026-10-02 (later) — same service, AI now configured (Pre-challenge)

The user saved `AI_PROVIDER=groq`, `GROQ_API_KEY`, `GROQ_MODEL=qwen/qwen3.8-27b`, `EXTRACTION_PROMPT=v2` in Render; the instance restarted (`instance_started` 21:15:34 UTC, 2026-10-01 = 00:15 Riyadh on 2 Oct). The key never appeared in any output (grep of all raw outputs: 0 hits).
**Deployed commit:** still not readable from Render. Same indirect evidence as above: `/`, `app.js`, `revision.js`, `styles.css` byte-identical to `91f6a30` (HEAD); sample 3 → 4 quotations, 1 matched, 3 uncertain. Hash to be confirmed from Render's Events tab.

**Health before any audit:** `mode: ai`, `ai_configured: true`, `provider: "Groq (qwen/qwen3.8-27b)"`, `ai_selection: groq`, `ai_last_call: {outcome: never_called}` (no Groq call made by health).

**The one real Groq audit** (sample 2, «مقال عن الصبر», 21:17 UTC; this was also the first audit on the new instance, so it loaded the Quran text, 7.6 s server time):
`ai: {configured: true, responded: true, outcome: "ok", http_status: 200, model: "qwen/qwen3.8-27b", elapsed_ms: 843, proposed: 7, located: 7, discarded: 0, error: null}`; `mode: ai`; health afterwards `ai_last_call: ok, 200, 843 ms`.
Findings: 7, all `marked+ai(+phrase)`; stats identical to the fallback run of the same sample (total 7, matched 6, difference 1, needs review 3, reference matched 3 / missing 2 / incorrect 1 / uncertain 1). The model proposed the same 7 quotations; it added nothing new here.

**Remaining live checks (spaced ≥ 70 s, one script at a time; `ai_last_call` read after each step: `ok` every time, `cooldown_seconds: 0`, so no 429 and no fallback occurred in any step):**
- `scripts/e2e_check.py`: failures 0. Groq responded on all three samples (`outcome ok`, HTTP 200): sample 1 proposed/located 5/5 (370–1,036 ms across samples), sample 2 7/7, **sample 3 0/0** (the model proposed nothing; its 4 findings are `phrase` only, 1 matched, 3 uncertain as before). Error cases (400, 400, 422, 422), markup case (200, article not echoed), 11 sensitive paths 404. Groq calls: 3 samples + the markup article = 4 (error cases are rejected before any AI call).
- `ui_boundary_e2e.mjs`: 20/20 PASS. `ui_e2e.mjs` (old workflow): 26 PASS, failures 0.
- **`ui_phrase_e2e.mjs`: FAILED (1 FAIL, then a 30 s timeout, exit 1) — not a service fault, but it means the candidate/«maybe» tiers cannot be shown live with AI on.** The script's first assertions assume `AI_PROVIDER=none` (its header says so): "two findings" and a «مرشَّح»/«قد يكون اقتباسًا» chip. A diagnostic audit of the script's article on the live service (1 more Groq call, outcome ok) returned **3** findings, all with `ai` among `detected_by`:
  «ادعوا ربكم تضرعا وخفية» (`ai+phrase`, uncertain, الأعراف: 55), «وبشر المؤمنين الذين إذا أصابتهم مصيبة…» (`ai+phrase`, difference, البقرة: 155–156), and «كونوا مع الصابرين» (`ai` only, difference, البقرة: 153). Local run of the same article with `AI_PROVIDER=none`: 2 findings, `phrase` only, 1 candidate + 1 possible. So with AI the phrase search's own tiers are replaced by AI-stated findings.
  Observation, not a verdict: «كونوا مع الصابرين» is the writer's ordinary prose (two words, the script designed it as a phrase the search must not report); the model proposed it and it was linked to البقرة: 153 («إن الله مع الصابرين») as a "difference" needing review. A writer sees a review item for a phrase that is probably not a quotation. The script was not changed; the earlier all-PASS live run of `ui_phrase_e2e.mjs` (22 checks, reduced mode, before the key was set) and the local runs remain the evidence for the candidate/«maybe» flow.
- Groq calls on the live service in this round: 1 (sample 2) + 4 (`e2e_check`) + 1 (diagnostic) + the audits made by the three browser scripts (not counted per request; every `ai_last_call` after them was `ok`).

**Open:** deployed commit hash from Render; unmarked wrong-word case with AI (`وافعلوا الشر لعلكم تفلحون`) not retried (it would cost a further Groq call).

## 2026-10-02 — fix for the live AI finding (Pre-challenge)

**Cause, traced (local reproduction with a fake provider returning the same three spans Groq returned; no Groq call).**
1. `audit._detection` gave every span the model proposed `tier: "stated"` (an established quotation, no "maybe" gating), ranked above the phrase search's own tier. So a model-proposed span skipped the deterministic evidence rules entirely.
2. «كونوا مع الصابرين» (3 words, `ai` only) matched no verse exactly; the verifier's fuzzy alignment found البقرة: 153 («إن الله مع الصابرين») on 2 of 3 words (مع، الصابرين; similarity 0.667, above the 0.6 acceptance line). Words that common are the whole "evidence" for the "difference" verdict. Rarity mass of the matched words 11.1, below the search's own floor (12) for even an exact phrase.
3. Worse, found in the same trace: «وبشر المؤمنين…» is only a "possible" quotation by deterministic search (no replacement text), but with the model proposing the same span it became "stated" and **two automatic changes were offered**. The model's agreement overrode a weakness the search had found.
4. The "AI-found" label was the chip «استخراج بالذكاء الاصطناعي» in "طريقة الرصد", printed for every finding the model also proposed (including marker- and search-found spans), i.e. it claimed AI discovery where the model added nothing.

**Change.** A span only the model proposed is graded by the phrase search's own rules (`phrases.grade_exact` / `grade_approximate`, extracted from `classify`, behaviour unchanged): exact + distinctive → "candidate"; short/common, formula, hadith cue, differing words, or no match → "possible" (shown, no replacement text, verse choices offered). It becomes "stated" only on the writer's own evidence: a written reference with an ayah number that points at the matched verse, or a Quran lead-in («قال تعالى»…) right before the span. A span the search also found keeps the search's tier (the model never raises or lowers it). Marked and manual spans are untouched. No threshold was tuned; no new constant was added.
Provenance: `detection.ai_role` = `only` (would be absent without the model) / `also` (a marker or the phrase search found it too) / null; `ai.added_only`, `ai.also_found`; chip text «اقترحه الذكاء الاصطناعي وحده (لم يجده البحث الآلي)» vs «اقترح الذكاء الاصطناعي المقطع نفسه أيضًا»; the banner and the print record state both counts; a result restored from an older session claims neither.

**Local verification (Python 3.14 venv, no Groq).**
- `pytest`: 214 passed (194 before + 20 new in `tests/test_ai_tiers.py`: the live prose, three more prose samples incl. one matching nothing, the genuine short misquotation «إن الله مع الصابرون» with a reference / with a lead-in / with a reference to another verse / with neither (listed as "possible", then confirmed through `run_phrase` → proposal «الصابرين»), marked + model, model agreeing with the search changes nothing, source outage, and on the full text: the live «وبشر المؤمنين…» case, four prose samples, a phrase the search "missed" graded like the search grades it, `وافعلوا الشر لعلكم تفلحون (الحج: 77)` still corrected). Against the previous `app/` all 20 fail; one existing test (`test_ai_text_never_used_as_replacement`, the same misquotation with a reference) caught my first, too blunt version and led to the reference/lead-in rule. `node --test tests/revision.test.mjs`: 11 passed.
- Deterministic search unchanged: `eval/run_eval.py --mode fallback` on `cases.json`, `heldout.json`, `phrases_frozen.json` before vs after the change: every row and summary identical except the timestamp (frozen set SHA-256 `OK`; the three parity runs were not saved as result files; they are not new evaluation runs). AI mode was **not** re-evaluated, so no AI-mode numbers in `docs/EVALUATION.md` describe this code.
- `scripts/ui_phrase_e2e.mjs` (rewritten): default mode starts its own uvicorn on a free port with `AI_PROVIDER=none`, API keys removed from its environment and a high rate limit, and first asserts `/api/health` says `mode: reduced, ai_configured: false`; against a server with AI on it refuses (verified with a local fake-provider server: exit 1). Deterministic checks are the previous 22, unchanged, plus that precondition: **23 PASS, 0 FAIL**. New `--live-ai URL` part: one audit, count-free assertions (quotes equal the article text at their offsets; `proposed = located + discarded`; per-finding provenance matches `detected_by` and the chip text; counters match the findings; every possible quotation has no change, no green chip, the «maybe» chip; ordinary prose «كونوا مع الصابرين» is never established, absent is valid; the deterministic findings are not downgraded and the misquoted phrase is not upgraded; confirming a verse still works; no console errors); exit 2 and "INCONCLUSIVE" if the model did not answer. Exercised locally with a fake provider: same three spans as the live run → 22 PASS / 0 FAIL; with an extra invented and a formula span → 22 / 0; provider failing → INCONCLUSIVE, exit 2. Against the **previous** `app/` the same assertions give 7 FAIL (prose "stated", no `ai_role`, misquoted phrase upgraded).
- Other browser/API checks, local AI-off server: `ui_e2e.mjs` 26 PASS / 0 FAIL, `ui_boundary_e2e.mjs` 20 PASS / 0 FAIL, `e2e_check.py` failures 0.

**Known limits (stated, not fixed).**
- A genuine short, unmarked misquotation (e.g. «إن الله مع الصابرون» with no reference and no lead-in) is indistinguishable from prose by evidence: it is listed as "possible" with its closest verse and a one-click confirm, not as an established difference. Without the model it would not be listed at all.
- ~~`merge` still lets a model span replace an overlapping phrase-search span~~ — fixed on 2026-10-02 (see the next section).
- Prose that closely paraphrases a verse (e.g. «لا تحزن إن الله معنا دائما», 5 of 6 words from التوبة: 40) is reported as "possible", with no changes; it cannot be told from a loose quotation.

### 2026-10-02 — live checks of the fix on Render (Pre-challenge)

**Deployed commit.** Service `https://quran-quote-auditor.onrender.com` served the new files about 40 s after `5d27b51` was pushed (the dashboard evidently auto-deploys; `render.yaml` says `autoDeployTrigger: "off"`, which I could not check, and I have no Render access). The instance still reports no commit; what was observed: `/`, `/static/app.js`, `/static/revision.js`, `/static/styles.css` are byte-identical (SHA-256) to `5d27b51`, and the audit response carries the new `ai.added_only` / `ai.also_found` fields, which only the new backend produces. Consistent with `5d27b51`; the hash itself is still to be read from the Render Events tab.

**AI response status.**
- `ui_phrase_e2e.mjs --live-ai` (one audit, one Groq call): `outcome: ok`, HTTP **200**, 608 ms, proposed 3, located 3, discarded 0, `added_only` 1, `also_found` 2, 3 findings. **23 PASS, 0 FAIL** (exit 0).
- Then, 75 s later, `e2e_check.py`: sample 1 Groq answered **HTTP 429** ("quota temporarily exceeded", 149 ms); the app's cooldown (120 s) then skipped AI for samples 2 and 3 (`mode: ai_failed`, no further Groq request). So `e2e_check.py` (failures 0) and the 5 samples/markup case ran in the deterministic fallback: sample 1 5 quotations (4 matched, 1 difference), sample 2 7 quotations (6 matched, 1 difference, 3 needing review, same as before), sample 3 4 quotations (1 matched, 3 uncertain), error cases 400/400/422/422, 11 sensitive paths 404. This is **not** evidence about AI on samples 1–3 after the fix.
- `ui_boundary_e2e.mjs` (75 s later): 20/20 PASS, but `ai_last_call` read afterwards was `failed 429, cooldown 32 s`, so that run was also fallback. `ui_e2e.mjs` (75 s later): 26 PASS, 0 FAIL; `ai_last_call` afterwards `ok 200, cooldown 0`.
- Groq requests I caused: 1 (live-ai, 200) + 1 (`e2e_check` sample 1, 429) + the audits of the two browser scripts (boundary: cooldown, none sent or rejected; `ui_e2e`: not counted per request, last call ok). The 429 is consistent with the free-tier limit documented earlier (Render has no `GROQ_MAX_COMPLETION_TOKENS`, so the default 4096 reservation applies; the notes show 512 avoided OTPM 429s); I did not diagnose it from this run and did not retry, to avoid more calls.

**False-positive result (live, real model).** The ordinary prose «كونوا مع الصابرين» was proposed by the model again (`detected_by: ai` only). It is now reported as `possible` (chip «قد يكون اقتباسًا قرآنيًا — يحتاج مراجعة»), wording shown only as "if it is a quotation: difference" against البقرة: 153, **no change offered**, no green chip, labelled «اقترحه الذكاء الاصطناعي وحده». Before the fix the same finding was an established quotation with a "difference" verdict. «وبشر المؤمنين…» (model + search) stayed `possible` with no change (before: two automatic changes); «ادعوا ربكم تضرعا وخفية» (model + search) stayed a candidate.
**What the model added on this run:** the same quotations the search found plus the one prose phrase, which the program now treats as a possibility. It found no genuine quotation the search had missed, so **this run does not show that AI improves detection**; the earlier live audit of sample 2 (7 of 7 marked, nothing added) says the same.

**Remaining limitations.** (1) Groq free-tier 429s: back-to-back audits within about two minutes can fall back to the deterministic mode (the app reports it, and results stay correct but may miss short unmarked quotations); presenting live, space audits or set `GROQ_MAX_COMPLETION_TOKENS=512` in Render (user's dashboard step; untested live). (2) AI on samples 1–3 was not re-observed after the fix on Render (429); local fake-provider runs and the one live audit above are the evidence. (3) Deployed commit hash not read from Render. (4) The three limits listed under the fix above (short unmarked misquotation is "possible" without a reference/lead-in; AI span can replace an overlapping search span; close paraphrases are "possible"). (5) AI mode was not re-evaluated on the labelled sets, so no AI-mode accuracy numbers describe this code.

## 2026-10-02 — model spans can no longer replace or suppress a deterministic finding (Pre-challenge)

**Cause (local reproduction, fake provider, 36-verse fixture; no Groq call).** `audit.merge` kept candidates in priority marked/manual > ai > phrase and folded an overlapping lower-priority span into the kept one. So a model span that overlapped a phrase-search hit *replaced* it. Article «ومن هنا قيل وتعاونوا على البر والتقوى ولا تعاونوا على الإثم والعدوان وهذا أصل.», the search alone: one finding, tier "candidate", المائدة: 2, one proposed change. With the model proposing (a) a wider span «ومن هنا قيل … وهذا», (b) a narrower «على البر والتقوى ولا», (c) a shifted «قيل وتعاونوا على البر»: the finding became the model's span, tier "possible", wording "difference"/"uncertain", **no changes**. The misquotation variant (الشر for الإثم) behaved the same. Marked quotations were never replaced, but a different model span was reported as "the model proposed the same span" (`ai_role: also`).

**Change.** `merge` ranks marked/manual > phrase > ai. A model span that overlaps a kept non-model span only adds `ai` to its sources when it is the *same* span; otherwise it is stored on the kept candidate (`Candidate.ai_spans`: start, end, quote, relation wider / narrower / shifted) and surfaces as `detection.ai_spans`, `detection.ai_role: "overlap"`, `ai.overlapped`, and a note on the card; the finding's span, tier, wording verdict, reference verdict and changes are exactly what they are without the model. A phrase-search finding's tier is read from the search (`c.phrase.tier`), never recomputed from the model's proposal. Model spans that overlap nothing the program found are unchanged (graded by the phrase search's own rules, "possible" unless the writer's reference/lead-in backs them). `PRIORITY` (the order of `detected_by`) is unchanged.

**Local gates (Python 3.14 venv, no Groq).**
- `pytest`: 238 passed (214 before + 24 new in `tests/test_ai_overlap.py`). The new tests compare the whole source-based verdict of the finding with and without the model: correct quotation and misquotation × wider / narrower / shifted model span, the model's span covering almost the whole article, the same span (agreement only), marked correct quotation and marked misquotation (the correction الشر → الإثم stays) × overlapping spans, a model span elsewhere in the article (still its own "possible" finding), and `merge` directly (any input order, one model span over two deterministic spans, same-span dedup, marked over phrase). Against the previous `app/`, 20 of the 24 fail (the rest check behaviour that did not change).
- One existing test had to change, and it is a finding: `test_full_text_prose_is_not_established` included «لا تحزن إن الله معنا دائما», which passed only because the model's wider span hid the phrase search's own finding. The search alone reports «لا تحزن إن الله معنا» (5 literal words of التوبة: 40) as a "candidate" (wording "uncertain": the end is not settled; the only offered change is the optional full vocalization). That case now has its own test asserting that the model changes nothing about it. In AI mode this sentence is therefore reported as in AI-off mode; it is ordinary prose that closely reuses a verse, and the search cannot tell it from a quotation (known limit, unchanged).
- `eval/run_eval.py --mode fallback` on `cases.json`, `heldout.json`, `phrases_frozen.json`: every row identical to the saved results of the previous code (summary differs only in the timestamp / one timing); frozen-set SHA-256 `OK`; the three parity runs were not kept as result files. AI mode was **not** re-evaluated.
- Local AI-off server: `scripts/ui_phrase_e2e.mjs` (own server) 0 failures, `ui_e2e.mjs` 0 failures, `ui_boundary_e2e.mjs` all checks passed, `e2e_check.py` failures 0.

**Live (Render, one audit, one Groq call).** Code `801051f` pushed to `main` shortly before 01:17:46 (UTC+3, exact push time not recorded); the Render `/static/app.js` still differed from the commit's file at 01:17:46 and was byte-identical (SHA-256) at 01:18:07. `/api/health` before the audit: `mode: ai`, Groq `qwen/qwen3.8-27b`, `ai_last_call: never_called` (fresh instance). One audit of `app/static/samples/sample-2.txt`: HTTP 200 in 8.3 s wall (cold start included), **`ai.outcome: "ok"`**, `http_status: 200`, `elapsed_ms: 1036`, proposed 7 / located 7 / discarded 0, `added_only 0`, `also_found 7`, `overlapped 0`; 7 findings, 6 matched, 1 difference, 0 possible, 9 proposed changes — the same shape as the earlier live audit of this sample. The new overlap path was **not** exercised live (the model proposed exactly the spans the markers found); it is covered offline only. **The deployed commit hash was not read:** the service does not expose it, GitHub shows no Render status/check/deployment for the commit, and I have no Render access; read it on the service's Events/Deploys page (expected `801051f`).


## 2026-10-02 (night) — final pre-submission review, live checks and release record (Pre-challenge)

All of this is pre-challenge work (dated before 4 October 2026).

**Release preserved.** `75b0e28` (docs only) was pushed to `main`. Render redeployed itself within about a minute: `/` 200 (0.4–0.6 s, three reads), `/api/health` `status: ok`, `mode: ai`, `source.loaded: true`; the four static files were byte-identical (SHA-256) to the repository; `instance_started` moved to just after the push. The service does not expose its commit hash and I have no access to Render's dashboard, so **the deployed hash was never read by me**: the user's Events/Deploys screenshot is still needed. The same pattern held for every later push (below): static files identical to the pushed commit within ~45 s, and the instance start time 30–40 s after the commit time (for `065ec76`: committed 01:48:02, `instance_started` 01:48:39, UTC+3).

**Final review of the live workflow (Arabic RTL, desktop 1440 × 900 and mobile 390 × 844, fresh browser contexts without stored data).** Walked: paste a post, audit, a marked error, an uncertain phrase, choose a verse, approve, preview, copy, the AI-fallback notice (local fake provider that fails, no Groq), print record not re-checked. Four concrete defects found and fixed (each with a deploy and a live re-check):
1. *Summary tiles.* Nine tiles in a 7–8 column grid left one orphan tile on a second row on desktop (and on mobile a 2-column block with one orphan). Now one row ≥ 1000 px, a 3 × 3 block below. Added to `scripts/ui_e2e.mjs`.
2. *Copy feedback.* «نسخ المقال المعدّل» confirmed only in a status line at the top of the page, out of view. The button now reads «✓ تم النسخ» and a note appears beside it; a failed copy selects the text and says so. Added to `scripts/ui_e2e.mjs`.
3. *Manual check took a neighbouring quotation's reference* (found live on Render). After choosing a verse for the uncertain phrase in my demo post, `POST /api/phrase` reported the phrase with the reference «الشرح: 6» that belongs to the quotation above it ("wrong reference", plus a change overlapping that quotation's own reference change). Cause: `run_phrase` attached references with only the highlighted span in the list, whereas a full audit gives each reference to one quotation. Fix in `app/audit.py` (`_manual_reference`): the marked and phrase-search neighbours are rebuilt (no AI) and the browser sends the spans of the findings it shows (`others`). Live before the redeploy: reference status `incorrect`; after: `missing`. 2 regression tests (`tests/test_phrases.py`). Residual limit: a neighbour that only a model proposed and that the browser does not list (an old client, or a direct API call) cannot be known to the server.
4. *AI notice legibility.* The model name broke across lines (`qwen3.8-` / `27b`) and, when the model answered with no candidates, the notice was a row of Arabic-Indic zeros that read like punctuation. The name now stays on one line, the notice says «لم يقترح أي مقطع، فاعتمد الرصد على العلامات والبحث الآلي»; counts use the right plural.
Not changed (noted): the boundary-uncertain card says the same thing in three places (verdict, reason list, "no automatic fix"); verbose but correct.

**Local gates on the final code `065ec76` (Python 3.12.13 venv; AI off, no Groq call).** `pytest` **240 passed**; `node --test tests/revision.test.mjs` 11 passed; `scripts/e2e_check.py` (local) failures 0; `scripts/ui_phrase_e2e.mjs` 23 PASS / 0 FAIL; `scripts/ui_boundary_e2e.mjs` 20 PASS / 0 FAIL; `scripts/ui_e2e.mjs` 29 PASS / 0 FAIL (26 + 3 new); `ui_phrase_e2e.mjs --live-ai` against a local fake provider 0 failures. Rerun of the three evaluation sets (`eval/run_eval.py --mode fallback`, `eval/results/fallback-20261002-*-head-801051f-*.json`): rows identical to the previous logged run (`…233623/4/5…`), only timestamp and timing differ; frozen-set SHA-256 `OK`. Main 27/28 found, held-out 6/6, frozen 30/32 unmarked found; false "matched" wording 0 on all three; misquotations reported "matched" 0; frozen 12 of 30 found read "uncertain" (boundary not settled); frozen false suggestions 2 (both «possible»), false confirmed 0. These sets are small, author-written development/frozen data, not independent accuracy.

**Live checks on Render (no AI needed).** `/` 200 with a CSP; `/api/health` no key in the body; 9 sensitive paths (`/.env`, `/.git/config`, `/app/config.py`, `/requirements.txt`, `/render.yaml`, test fixtures, `/static/../app/config.py`, `/submission/README.md`, `/.vercel/project.json`) all 404; `POST /api/audit` empty 400, wrong field 422, malformed JSON 422, 6,001 characters 413 (all rejected before any AI call); `POST /api/phrase` 200.

**Real Groq calls made in this round: 4 live audits** (my demo post, three screenshot/capture sessions and the video recording), each in a fresh browser and spaced ≥ 2.5 minutes apart. **All four: HTTP 200, `ai.outcome: "ok"`, 313–669 ms, `proposed: 0`, `located: 0`** — the model answered but proposed nothing for the three-quotation demo post each time (the earlier live audit of sample 2 proposed 7, all already found by the deterministic path). No 429 and no fallback occurred in these four. Everything the product showed for that post came from the deterministic path; the notice said so. No measured benefit from the model on any live audit; the README and deck say so. The video narrates the "responded, proposed nothing" branch.
Demo post findings (identical in all four): 3 findings, 1 matched, 1 difference (الشر → الخير, source-backed), 1 «possible» («إن الله مع الصابرين», 2 verses: البقرة: 153, الأنفال: 46, no change until the editor chooses), reference «الشرح: 6» incorrect (→ 5), 3 proposed changes. Corrected post copied from the clipboard after approving both fixes and choosing البقرة: 153 (`submission/video/final/corrected-post.txt`).

**Cold start.** First audit after a redeploy (new instance): 6.6–7.4 s wall (Quran text download included); later audits 0.3–0.7 s. **Wake-up from idle, measured once** (no request for 18 minutes, then one timed `GET /`, 23:20 UTC): HTTP 200, time to first byte **22.9 s**; `/api/health` right afterwards: instance age 6 s, `source.loaded: false` (the Quran text is downloaded by the first audit). One measurement only, so the README says to allow up to a minute.

**Security and licence review (tracked files and all 30 commits).** The two secrets present in the local, git-ignored `.env` and `.env.local` (Groq key, Vercel token): 0 occurrences in any commit or in the working tree. Key-pattern scan (Groq, Google, OpenAI-style, GitHub, Slack, AWS, Render, private-key blocks, JWTs): 0 hits. Personal e-mail address and local user name: 0 hits in files and in commit messages; every commit's author and committer is the GitHub noreply address. Files that must not be public (`.env*` except `.env.example`, organizer PDFs and template, `submission/`, `.vercel/`, `.pptx`, `.mp4`, keys): never tracked. 137 files tracked. Dependencies: licences read from the installed metadata match `SOURCES.md` (MIT, BSD-3, BSD-2, PSF-2.0, MPL-2.0 for `certifi`, Apache-2.0 or BSD-2 for `packaging`). Project licence: MIT. The Quran text is not in the repository (a 36-verse test fixture from Quranpedia, credited in the file and in `SOURCES.md`).

**Commits of this round and what Render served.** Code/doc commits: `b15b2a2` (tiles, copy feedback, README, docs), `4e83a9e` (manual-check reference), `065ec76` (AI notice); this entry and the README "Try it" section are a docs-only commit after `065ec76`. Final tested commit = `065ec76` (all gates above). Deployed commit: not readable by me; expected `065ec76` code plus the docs-only commit(s) after it, which do not change a served file. If Render's Events page shows the docs-only hash, that is the same code as `065ec76`; if it shows `065ec76`, the docs commit has not yet been picked up. Either is correct.

**Remaining limitations (unchanged and stated in the README).** Short unmarked misquotations may be only «possible» or missed; ordinary prose can reuse Quran words; start/end boundaries may need the editor's confirmation (many correct quotations read "uncertain"); Groq's free tier can answer 429 and the app then shows its notice and continues deterministically; no measured accuracy beyond the small author-written sets; labels still await specialist review; Gemini never succeeded; memory and timing were measured locally, not on Render; the video uses a synthetic voice.

## 2026-10-02 (early morning, Riyadh) — independent audit of the delivery package (Pre-challenge, docs only)

All of this is pre-challenge work (dated before 4 October 2026). No product code was changed; `065ec76` remains the last code commit.

**Git and links.** `main` = `origin/main` = `0337267`, working tree clean; tag `pre-challenge-baseline` is an annotated tag on `532e965` (28 Sep 2026 19:40 +03). Anonymous GitHub API: repository public, licence recognised as MIT, topics set, "website" field empty; the repo page and the tag page answer 200.

**Clean clone of the public repository** (fresh `git clone`, Python 3.12.13, `requirements-dev.txt`): `pytest` **240 passed** (the README said 238, now corrected); the app started with no `GROQ_API_KEY`/`GEMINI_API_KEY` answers `/api/health` `mode: reduced`; `scripts/e2e_check.py` against it: failures 0 (11 sensitive paths 404). The deterministic workflow needs no key.

**Live Render (served files).** `index.html`, `app.js`, `styles.css`, `revision.js` and the three samples are byte-identical (SHA-256) to the repository. The Python code behind them is not observable from outside; the deployed commit hash is still not directly observed.

**Live user journey (fresh Chromium contexts, desktop 1366 × 800 and mobile 390 × 844, Arabic locale, no stored data).** Pasted the demo post, audited, read the three cards, approved the two source-backed changes, chose البقرة: 153 for the uncertain phrase, copied the corrected article. The clipboard held exactly the expected text («الخير», «الشرح: 5», the third sentence unchanged); the button read «✓ تم النسخ». `html dir=rtl lang=ar`, no horizontal overflow at 390 px, no console errors, no failed requests. **This one live audit made one real Groq call, which answered 429**: the page showed the amber notice «تعذّر الاستخراج بالذكاء الاصطناعي (تجاوزت خدمة الذكاء الاصطناعي حد الاستخدام (الحصة) مؤقتًا)… عُرضت الاقتباسات المعلَّمة صراحةً والعبارات المطابقة لنص المصحف فقط»; the deterministic result was identical to the earlier runs (3 findings, 2 proposed changes). The mobile run, seconds later, made no Groq call (the app was in its cooldown): its notice read «ستُعاد المحاولة بعد 107 ث». So the 429 path and the cooldown notice are both observed live and are understandable; the model itself was not exercised in this round.

**Video.** `quran-quote-auditor-demo.mp4`: 111.48 s, H.264/AAC 1280 × 720, decodes fully with no errors, mean volume −17.4 dB (max −1.0 dB), only 2.6 s of leading silence and one 1.3 s pause. Frames inspected every 4 s plus full-size stills: captions burned in and legible, the page shown is the live Render site, the AI notice shown says the model answered with no new passages. An independent speech-to-text pass (faster-whisper "small", Arabic) recognised the synthetic narration and matched the captions (key words «الشر», «الخير», «الشرح ستة», «خمسة» recognised); the narration contains no recited verse. I did not listen to it myself.

**Deck.** 13 slides inspected one by one in the PDF. Changed after the inspection: slide 7 (three tighter crops of the live screenshots, text about twice as large), slide 8 (the «6 of 6 wording errors corrected» figure is for the main set only; the Uthmani limit added), slide 10 («faster review» removed: speed was never measured), slide 3 (card text aligned), and the template's leftover speaker notes (authoring instructions) removed from all slides.

**Newly measured limitation: Uthmani-script quotations.** A correct quotation copied from a mushaf site is usually in Uthmani script. Local run (AI off) on three correct quotations in Uthmani spelling (آل عمران: 200, البقرة: 153, البقرة: 43): wording **difference (fuzzy)**, **difference (fuzzy)** with one proposed wording change, and **uncertain**; the same verse in plain spelling is «matched». None was reported "matched" wrongly and every one needed review, so this is the cautious direction, but it is the first thing a visitor who pastes from a Quran app will meet. Not fixed here on purpose: it is the planned first challenge-period change (`docs/CONTINUATION.md`, priority 5), and an improvement must be committed on 4–6 October.

**Secrets and history (33 commits).** Values of the two local secret files (Groq key, Vercel token): 0 occurrences in any commit. Token-pattern scan (Groq, Google, OpenAI-style, GitHub, Slack, private keys, Render, Vercel, AWS, bearer): 0 hits. The only e-mail address in files and commit metadata is GitHub's noreply address; no phone numbers; no file of these kinds was ever tracked: `.env*`, `submission/`, organizer PDFs/PPTX, videos, decks, `.vercel/`; no blob over 1 MB. Details of the secret values were not printed.

**Docs fixed in this commit.** README test count 238 → 240; README cold-start sentence aligned with the one measurement (23 s for the first page after 18 idle minutes) instead of "about 9 s"; the Uthmani limit added to «What it does not claim»; `.env.example` no longer tells readers to use Vercel; SOURCES lists the tools compared in the deck and the local-only submission materials.


## 2026-10-02 (morning, Riyadh) — Uthmani-script matching, interface revision, release gate and live checks (Pre-challenge)

Work done before 4 October 2026 and recorded as pre-challenge. Commits: `1bc8cbf` (held-out Uthmani set frozen + baseline), `0eacaaa` (matching layer), `cccd084` (interface), `1783cfe` (SOURCES; pushed). Details and numbers: `docs/UTHMANI.md`, `docs/EVALUATION.md`.

**Local gate on code `cccd084` (Python 3.14.7 venv; AI off; no Groq call).** `pytest` **343 passed** (240 before + 103 in `tests/test_uthmani.py`); `node --test tests/revision.test.mjs` 11 passed; `scripts/e2e_check.py` (local) failures 0; `scripts/ui_e2e.mjs` 29 PASS / 0 FAIL; `scripts/ui_boundary_e2e.mjs` all checks passed; `scripts/ui_phrase_e2e.mjs` failures 0; new `scripts/ui_uthmani_e2e.mjs` 37 PASS / 0 FAIL (desktop 1280 and mobile 390: no horizontal overflow, RTL, one primary button on the first screen, help collapsed, three primary figures, finding order = article markers, the correct Uthmani quotation is a collapsed row with no correction card, optional formatting apart/neutral/not counted, Tab order, keyboard approval, revised text differs only in approved spans, copy feedback). `eval/validate_labels.py`, `validate_phrases.py`, `validate_uthmani.py` OK. SHA-256 of `eval/phrases_frozen.json` and `eval/uthmani_heldout.json` verified; `git diff` of `eval/cases.json`, `eval/heldout.json`, `eval/phrases_frozen.json` against `976395e` and of `eval/uthmani_heldout.json` against `1bc8cbf`: 0 lines. The three older sets re-run: rows, negative hits, formula hits, extra findings **identical** to the run on `976395e`.

**What was changed in the three e2e scripts:** the mode banner now sits in the collapsed help, the secondary counts are inside «أعداد أخرى», and optional formatting and compact rows are in collapsed `<details>`; the scripts open them before reading. No assertion about behaviour was removed.

**Push and live checks.** `git push origin main` (`976395e..1783cfe`). About 30 s later the served `/static/app.js`, `index.html`, `styles.css`, `revision.js` and `/` were **byte-identical** to the local files (`cmp`). The Python code is not served, so the deployed commit hash was **not read from Render** (the instance reports none; the Render dashboard was not accessible to me); what is known is that the served static files equal those of `1783cfe` and that the behaviour below was observed. Deterministic live probes (`POST /api/phrase`, no model): a correct Uthmani quotation with a correct reference → wording «matched / uthmani», reference matched, **no required change**, one optional `script` change; the same with one word changed → «difference», one `wording` correction; correct words with a wrong reference (البقرة: 154) → «matched / uthmani», reference `incorrect`, one `reference` correction. End-to-end through the real page (`ui_uthmani_e2e.mjs --live URL --only desktop`, one audit): 18 PASS / 0 FAIL (the mobile pass was run on the local server only: the static files are byte-identical). **Model calls on the live service:** 4 audits (2 video takes, 2 screenshot/e2e runs; the first video take was discarded because its caption said the model «proposed places», see below); all HTTP 200 with `proposed 3, located 3, discarded 0, added_only 0, also_found 3` (the model proposed the three marked quotations the program had found anyway, it added none); no 429 (the audits were about 2–4 minutes apart).

**Video.** The upload copy had narration made with the macOS «Majed» system voice. Apple's macOS licence restricts using system voices for public sharing, so it was removed from `UPLOAD/` (the voiced files are in `archive/DO-NOT-UPLOAD-system-voice/`) and no other synthetic voice was used. The earlier captions-only file was the interim upload; it was then replaced by a new **captions-only recording of the revised live interface** (`submission/video/v2/`, 1:47, 1280×720, H.264, **no audio stream**, 9 captions, SRT kept): the first take's caption said «the model proposed possible places», which overstated an audit in which the model proposed only what the markers had found; the recorder now says «the model proposed the same places the markers found and added none» (branch chosen from the audit response). Frames inspected at 4 s steps and at full size; the page shown is the live Render site.

**Deck.** Slides 6, 7 and 8 changed (the Uthmani limit removed, the new Uthmani figures with their label problems stated, two screenshots of the revised live interface at 2× instead of three older crops), the other slides unchanged. PDF re-exported with LibreOffice and each changed slide viewed.

## 2026-10-02 (evening, Riyadh) — Uthmani test data re-sourced from Tanzil, history of six commits rebuilt (Pre-challenge, local verification)

Documentation and data provenance only; `app/` is byte-identical to the previous head (`git diff --stat` empty). AI off, no Groq call, no Render access.

* **Rebuild.** Commits `845844d` … `cdf151b` rebuilt on `976395e` as `1bc8cbf` … `3a5ba42` (old → new map in `CHANGELOG.md`; the push of that day was made under the old IDs, so the `976395e..` ranges named in the entries above refer to the rebuilt commits). Backups of the original history (mirror clone and bundle) were made before the rebuild.
* **Tests.** `pytest` 343 passed on the rebuilt head; each rebuilt commit tested on its own: 240 passed on the freeze commit (before the Uthmani tests exist), 343 on each of the other five.
* **Checksums.** `eval/phrases_frozen.sha256` OK; `eval/uthmani_heldout.sha256` OK (new value, see `docs/UTHMANI.md`); `eval/cases.json`, `eval/heldout.json`, `eval/phrases_frozen.json` and the results of those sets byte-identical to `976395e`.
* **Re-runs on Tanzil-sourced data.** Held-out and dev Uthmani sets in fallback mode: rows and counts identical to the recorded final run; whole-text rule analysis (3 modes): identical numbers; `eval/validate_uthmani.py`: OK on both sets.
* **Scan.** No tracked file in any of the rebuilt commits contains the other site's name, its API host or its field name, apart from `SOURCES.md` §1b «History of this data» (added in the last commit on purpose). No Uthmani verse text outside the fixture, the two evaluation sets and the result files that quote them.
* **Quranpedia fixture check (documentation only).** `tests/fixtures/hafs_subset.json`: 36 verses, 552 words, 17 surahs; all 36 identical to the live endpoint on 2026-10-02 (BOM/whitespace aside); `SOURCES.md` §1 and the README now say it is a committed, frozen, credited partial copy and quote the policy; the file itself was not changed.

## 2026-10-02 (late evening, Riyadh) — presentation pass on the live journey and demonstration article (Pre-challenge, local checks)

**Reviewed** the journey paste/load sample → audit → findings → approve/reject → preview → copy at 1366 px and at 390 px (Playwright, Chromium, no Groq call: server without keys, so `mode: reduced`) and with axe-core 4 (WCAG 2 A/AA + best-practice) at 320, 390 and 1366 px with every `<details>` opened. Axe findings on the code of `3a5ba42`: colour contrast 3.26:1 on the ayah numbers inside source verses (3 nodes), and the scrollable preview region not reachable by keyboard (at 320 px). Other observations: two stacked notice boxes (AI mode, source retrieval time) ahead of the results; approve/reject buttons and `<summary>` rows 24–28 px high on a phone; the raw error text of a failed AI call inside a warning.

**Changed** (`7ee0c49`): one quiet line plus «تفاصيل هذا التدقيق»; touch targets of 44 px on phones; ayah-number colour; `tabindex="0"` + label on the preview; footer privacy note folded into a `<details>` with the cold-start sentence; Tanzil credit in the footer; the AI-failure warning text no longer contains the exception text (kept in `ai.error` and shown in the details). A first version of the sample names overflowed 390 px by 11 px (`window.innerWidth` 401 vs `clientWidth` 390); caught by the script, fixed by shortening the names and letting the select shrink.

**After:** axe: 0 violations at 320/390/1366 px; no horizontal overflow at 320/390; `pytest` 344 passed; `node --test tests/revision.test.mjs` 11 passed; `scripts/ui_e2e.mjs`, `ui_phrase_e2e.mjs`, `ui_boundary_e2e.mjs`, `ui_uthmani_e2e.mjs` all pass (run against the local server, 60 s apart because of the app's own rate limit).

**Demonstration article** (`app/static/samples/sample-demo.txt`, four quotations, chosen for showing every state the story needs; both mistakes are deliberate user misquotations written for the demo, not Quran text). Observed locally (deterministic path, source = Quranpedia mushaf 1 read live on 2 Oct 2026):

| # | Quotation | Wording | Reference | Proposed changes |
|---|---|---|---|---|
| 1 | 2:153 in Uthmani script, byte copy of Tanzil v1.1 | matched, level `uthmani` | matched | none required (one optional formatting offer) |
| 2 | 2:156, byte copy of the Quranpedia text | matched, level `literal` | matched | none |
| 3 | «إنما يجزى الصابرون أجرهم بغير حساب» [الزمر: 10] | difference, closest location (fuzzy, not confirmed) | uncertain | one: «يجزى» → «يوفى» (Quranpedia 39:10 has «يُوَفَّى») |
| 4 | «فإن مع العسر يسرا» [الشرح: 6] | matched (vowel marks ignored) | incorrect | one: «الشرح: 6» → «الشرح: 5» (94:5 «فَإِنَّ مَعَ الْعُسْرِ يُسْرًا»; 94:6 is «إِنَّ مَعَ …») |

Verified against the stated sources on 2 Oct 2026: Tanzil XML (SHA-256 `c5052534…1244`) `2:153` equals quotation 1 byte for byte; the Quranpedia mushaf-1 text of 2:156, 39:10, 94:5 and 94:6 was fetched once and read; quotation 2 equals the fixture's 2:156. `tests/test_demo_article.py` pins the table. Not claimed: that a one-word substitution is always graded like #3 (any wording change is reported as «اختلاف — أقرب موضع مقترح», never as a confirmed match, because the text is not found letter for letter), nor that the model would add anything: four live Groq audits of an earlier demo post proposed nothing.

## 2026-10-02 (night, Riyadh) — remediation push, live deployment checks, live journey, video and deck stills (Pre-challenge)

**Push.** After the gates (344 tests, 11 Node tests, `shasum -c` for `eval/phrases_frozen.sha256` and `eval/uthmani_heldout.sha256`, `git diff 976395e HEAD -- eval/cases.json eval/heldout.json eval/phrases_frozen.json` empty, none of the six old commit IDs reachable from the branch, content scan of every blob reachable from the branch and the baseline tag, secret/e-mail/organiser-file scans of that history — one author identity, the GitHub no-reply address) `git push --force-with-lease=main:cdf151b… origin clean:main` replaced `cdf151b` with `1b8ee59` (`git ls-remote` before: `cdf151b`; after: `1b8ee59`; tag `pre-challenge-baseline` still `55b7350…` → `532e965`). The first rebuilt version of the code commit had carried the demo article in an older letter-for-letter variant of a Tanzil verse (different mark order) that the scan flagged; the code commits were folded before the push so that only the byte-exact version exists in history.

**Deployment.** Render redeployed on its own. Served static files byte-identical to the repository (`shasum` of `app.js`, `styles.css`, `revision.js`, `index.html`, `sample-demo.txt`); `app/main.py`, `.env`, `submission/README.md`, `template.pptx` answer 404. `/api/health` gained `build` (Render's `RENDER_GIT_COMMIT`) and read `5768387…` right after that push and `9da90c3…` after the next, so the deployed commit is readable from the service itself.

**Live journey (`scripts/live_smoke.mjs`, one audit = one Groq call).** Page load 1.5 s (warm instance); first audit after the redeploy 9.0 s wall (Quran text download included). Four quotations found; tiles ٢ needs review / ٢ proposed changes / ٤ detected; quotation 1 «مطابق — رسم عثماني» with matched reference, quotation 2 matched, 3 «اختلاف», 4 reference «خاطئة»; before any decision the revised text equals the article; after approving the two required changes it equals the article with exactly «يجزى»→«يوفى» and «الشرح: 6»→«الشرح: 5»; the clipboard holds it; no console errors. Status line: the model `qwen/qwen3.8-27b` answered in 0.8 s, proposed 4 spans, 4 located, 0 discarded, **0 added** (all 4 also found by the markers). 18 checks, all PASS.

**Video** (`submission/build/record_demo3.mjs`, local, git-ignored): two live takes, one audit each (both HTTP 200, proposed 4, added 0, also found 4). Take 1 showed the model details with Latin digits (the live page then lacked the `toArabicDigits` fix, pushed as `9da90c3`) and the caption covered the audit button; take 2 (the one used) is after both fixes: 101 s raw, trimmed to 93.0 s, 1280×720, no audio track. 31 frames at 3-second spacing and the key frames were inspected. **Deck stills** (`stills.mjs`) replay the recorded live response through the live page at 2× (no second Groq call). Page content is zoomed 125% in the recording so the text is larger on a phone (not tested on a real phone).

**Known gaps found and left:** the first audit after Render wakes from idle takes longer (23 s once for the page; Render says about a minute) and that is stated, not hidden; at 390 px the `[الشرح: 6]` reference can wrap its closing bracket onto the next line inside the article view (bidi wrapping of the user's own text); the «افحص المقطع المحدَّد» button needs a text selection, which is awkward on a phone.

## 2026-10-02 (night, Riyadh) — first journey revised for a first-time judge (Pre-challenge, local checks; NOT deployed)

**Request:** keep the audit logic and visual identity; make the demonstration a visible one-click action; lead with the verdict and take the user to the first item needing review; show the decisive difference first with clear decision buttons and the rest under details; verify that the model/source notices are folded in the deployed version; make «نسخ المقال المعدّل» the obvious final action; test at desktop and phone widths.

**Deployed version, before any change (`/api/health` build `e6e33e9`, = `HEAD`).** Two real audits of the demonstration article on the Render service (desktop 1366×900, then phone 390×844 with touch, 130 s apart: **two Groq calls**). In both, the notice region above the findings was **one line plus the closed summary «تفاصيل هذا التدقيق»**: 56 px high on desktop, 100 px on the phone, `<details>` closed, **0** `.notice` warnings. So the model and source details *were* collapsed on that build; I could not reproduce long notices in the normal path. Two paths can still put a long text there: a model failure (a two-line warning, by design) and the reduced mode (a one-line caveat). On the empty page the unused text box took 375 px of the 900 px first screen and the demonstration was reachable only through the small list.

**What changed (front end only: `index.html`, `app.js`, `styles.css`; no change in `app/*.py`, `revision.js` or any evaluation set).**
- Empty page: «جرّب المقال التجريبي» (large, first screen at 1366/390/320 px); one click loads **and** audits; the empty box is 104 px high; the audit button stays and turns secondary while the box is empty; the list is now «أمثلة أخرى».
- Verdict card above the notices: «وجدنا ٤ اقتباسات؛ يحتاج اثنان إلى قرارك» (number agreement written for 0, 1, 2, 3–10, 11+), «الفحص يشمل الاقتباسات التي رُصدت فقط، وليس حكمًا على المقال كله», and, for the demonstration article, the disclosure that the two mistakes are deliberate. The three counters moved into «أعداد التدقيق» (still in the DOM).
- After an audit the page scrolls to the first quotation that needs the editor (the verdict too, when both fit one screen), gives it focus, honours `prefers-reduced-motion`, and waits for web fonts first (without that the landing was off by about 40 px).
- Required corrections (`decisionCard`): «يجزى ← يوفى» and «الشرح: ٦ ← ٥» first (old value red/struck, new green, `sr-only` «من … إلى …»), then the review reasons («مطابقة تقريبية: الموضع المقترح يحتاج إلى تأكيد بشري» and the unsettled reference stay in view, as do the chips «إحالة غير محسومة» and «يحتاج مراجعة»), the source link, **«اعتماد التصحيح» / «اترك كما هو»**. The whole quotation before/after and the reason are one click away; the verse, the similarity percentage (٨٣٪), the API links, the status boxes, optional formatting and how it was detected are folded under «التفاصيل». Items without a button decision (uncertain boundary, possible phrase, choices) keep the previous layout.
- Notices: when a model answered, the whole «how this audit was made» line is folded behind «تفاصيل هذا التدقيق (النموذج والمصدر)»; the info notice about discarded model spans moved into it; warnings and errors (model failed, omitted short phrases, search limit) and the reduced-mode caveat stay visible. Measured with mocked `/api/audit` payloads (no Groq call): model answered with nothing 30 px (desktop) / 50 px (phone); with one discarded span 30 / 50; model failed 78 / 170 (the warning, by design).
- Review dock (sticky, bottom): first the verdict and «قراراتك: ٠ من ٢» with «التالي»; then progress; after the last decision «اكتملت قراراتك (٢ من ٢) — اعتمدتَ ٢. المقال المعدّل جاهز للنسخ» with the primary **«نسخ المقال المعدّل»**, and a warning if something is still unresolved; the editor's own copy button is highlighted. After copying, the dock repeats that only the quotations were checked.

**Checks (local, AI off, no Groq call; Python 3.14.7 venv).**
`pytest` **344 passed**; `node --test tests/revision.test.mjs` 11 passed; new `scripts/ui_journey_e2e.mjs` **172 checks, 0 failures** (1366×900, 390×844, 320×640; includes: keyboard Tab + Enter approves, «التالي», changing a decision, clipboard equals the article with exactly «يجزى»→«يوفى» and «الشرح: 6»→«الشرح: 5», touch targets ≥ 44 px, no horizontal overflow, reload restores the decisions); `ui_e2e.mjs` 29 PASS; `ui_boundary_e2e.mjs` 20 PASS; `ui_uthmani_e2e.mjs` 39 PASS; `ui_phrase_e2e.mjs` 23 PASS; rewritten `live_smoke.mjs` 22 PASS at desktop and with `--phone` (against the local server). axe-core 4 (WCAG 2 A/AA, 2.1 A/AA, best-practice) at 320/390/1366 px in four states (empty, landing, details open, both decided): **0 violations**.
Test edits: `ui_uthmani_e2e.mjs` (first-screen description and card order now describe the new layout; added a colour check of the difference), `ui_phrase_e2e.mjs` (`.ch-after` now sits inside the folded details: read with `textContent`, and `.d-after` checked), `live_smoke.mjs` (new flow).

**Not done, and why.** Nothing was committed or pushed, so **the deployed service still serves `e6e33e9` with the old first journey**. The submitted video (recorded on the live service) and slide 7 of the deck («لقطات من الخدمة الحية») therefore still show the old interface. `submission/build/record_demo4.mjs` (one-click flow) and `stills.mjs` (new flow) were run only against a local server, output in scratch space, not in `submission/UPLOAD`; regenerating them faithfully needs the revised front end deployed first (one more Groq call for the video). The caption bar of the video covers the dock in a few scenes; to be judged on the final take. The new texts are unreviewed by anyone but the author; the AI-mode behaviour above was exercised with mocked payloads, not with a live model after this change.

## 2026-10-02 (evening, Riyadh) — first journey pushed, deployed and checked live; video and deck rebuilt (Pre-challenge)

**Commit and deployment.** `caff275` (the first-journey revision above, front end only) was pushed to `main` (`e6e33e9..caff275`, fast-forward, no force). Gates before the push: 344 tests passed. `/api/health` `build` read `e6e33e9…` and then, about 30 s later, `caff275690a39e58858d4afcd2589e10f52123c8`; `app.js`, `styles.css` and `index.html` served by Render are byte-identical to the repository (first 16 hex characters of `shasum` equal for the three).

**Live journey (`scripts/live_smoke.mjs`, desktop 1366×900, one audit = one Groq call).** 22 checks, all PASS: page loaded in 1.4 s (warm instance); one click on «جرّب المقال التجريبي» loaded and audited the article in 9.0 s wall; verdict «وجدنا ٤ اقتباسات؛ يحتاج اثنان إلى قرارك»; the first item needing review on screen and focused with «يجزى ← يوفى»; four quotations, two required changes; the notice region 30 px with «تفاصيل هذا التدقيق (النموذج والمصدر)» closed; after approving both items the dock offers «نسخ المقال المعدّل»; revised text equals the article except exactly «يجزى»→«يوفى» and «الشرح: 6»→«الشرح: 5»; clipboard equal; no horizontal overflow; no console errors. Model `qwen/qwen3.8-27b` answered in 0.8 s, proposed 4, located 4, discarded 0, **added 0**. The `--phone` run was not repeated live (local only, earlier).

**Video (`submission/build/record_demo4.mjs`).** Caption placement changed first: the caption bar now measures the page's sticky review dock every 200 ms and sits above it. A local trial (AI off, no Groq call) was recorded and its frames at 3-second spacing inspected: the caption never covers the dock; in a few scenes it covers the lower part of the cards, but the item being described (the «يجزى ← يوفى» tile, the two buttons, the preview, the copy button) is in the upper part of the screen in each. Then one real take on the live service (HTTP 200, proposed 4, added 0, also found 4; the caption therefore says the model proposed the same places and added none): 100.1 s raw, first 1.9 s cut (the page before the 125% zoom), **98.2 s**, 1280×720, no audio stream. Six contact sheets inspected, plus the start and the end card.

**Deck.** Slide 7 stills regenerated by `stills.mjs` against the live page (the recorded response replayed; no second Groq call): the decision card and the before/after preview. The deck was rebuilt with `final_deck3.py` and the PDF exported with LibreOffice; all 13 pages looked at as a contact sheet and slide 7 at full size. PowerPoint itself was still not used to open the file.

**Not changed or not checked.** No evaluation set and no Python file changed. The model is still not shown to improve detection. The first audit after an idle sleep takes longer on Render Free (stated in the video's end card). Nothing was submitted to the portal.


## 2026-10-02 (night, Riyadh) — editorial interface: the writer's decisions beside the article (Pre-challenge)

**Inspected first (current live code `5be1ac3`, screenshots of the empty, loading, results, uncertain, no-findings, model-failed, completed and near-limit states at 1366, 390 and 320 px).** Where a writer has to stop: (1) the verdict card printed the text «null» whenever nothing needed a decision or the article was not the demo (`replaceChildren(null)`); (2) the pasted text and a second copy of it were both on the page, so on a phone the writer scrolled past the whole article to reach the first card; (3) every card carried three or four badges and a paragraph on what «غير محسوم» means; (4) a boundary question had two buttons, one of which sent the writer to a text box far above, to select with the mouse, then press a third button; (5) a possible quotation had one button («أؤكد أنه اقتباس…») and no way to say «ليس اقتباسًا» or name another verse; (6) location was «السطر ٧، الحرف ٢٣٤» with no surrounding words; (7) the bottom bar counted corrections only («قراراتك: ٠ من ١») while the verdict said 8 needed a decision, and it covered the lower part of cards; (8) «نسخ المقال المعدّل» was in the bar, before any before/after check.

**Changed (front end; no Python file under `app/` changed).** Decision panel beside the article (above it on a phone) showing one quotation at a time: the quoted words in their sentence, the paragraph, the likely surah and ayah with the Quranpedia link, then the exact change before its two buttons («غيّر إلى «يوفى»» / «أبقِ «يجزى»»). One plain state word per quotation instead of stacked chips. Possible quotation: «هل قصدتَ اقتباس هذه الآية؟» with the suggested verse, «نعم، هذه الآية» / «آية أخرى» (a surah + ayah form) / «ليس اقتباسًا» (reversible: the mark leaves the article, the item moves to «استبعدتَها», the reply draft, the final check and the record follow, «تراجع» restores it); no replacement text before confirmation. Uncertain boundary: «أين يبدأ/ينتهي الاقتباس؟» with the article's word and the verse's word; «نعم، هذا هو الاقتباس كاملًا» / ««X» من الاقتباس» / a word-level editor; each undoable. A phrase the search missed is selected in the article itself («افحص المحدَّد»). Review sequence: the count waiting, «التالي»/«السابق», automatic move to the next waiting item with what was done and «تراجع»; the list shows the open items first and keeps unresolved ones visible. Final step «المراجعة الأخيرة قبل النسخ»: what will be copied, each change in its sentence, quotations still open, the statement that only the quotations found were checked; copy is there, not in the bar. The bar (≤ 900 px only) shows the count and one next step, reserves its height as `scroll-padding-bottom` (`--dock-h`). Gradients, glows, the stat tiles, the status pills of the old editor card and the marketing sentences were removed; article text is set in Noto Naskh Arabic at a 42 rem measure; URLs and Latin references inside Arabic text are isolated runs (`<bdi dir="ltr">`). Cold start: after 7 s the status says the free host may need a minute; a failed or timed-out audit keeps the text and offers «أعد المحاولة» (the timeout is 100 s instead of 60 s).

**Frozen before changing anything about detection:** `eval/articles_frozen.json` (`efb6fe8`), results in `docs/EVALUATION.md`. Detection was not changed.

**Gates (local, Python 3.14.7 venv, AI off, no Groq call).** `pytest` **345 passed** (344 + `tests/test_surahs_js.py`: the browser's surah list equals `app/surahs.py`); `node --test tests/revision.test.mjs` 11 passed; the five existing sets re-run: rows identical to the previous final run; `ui_journey_e2e` (1366/390/320) all pass; `ui_boundary_e2e` all pass; `ui_phrase_e2e` all pass; `ui_e2e` all pass; `ui_uthmani_e2e` all pass; new `ui_long_e2e` (5,809-character article; sequence in article order; no focused control under the bar, with 150 controls focused and 70 real Tab presses per phone width; bar ≤ 16% of the screen; URL isolated; slow then failing server then retry; no findings; model failed) all pass; new `ui_a11y_check` (axe-core, WCAG 2.0–2.2 A/AA + best practice, eight states × 320/390/1366 px): **0 violations**. A negative control confirms the bar test can fail: with `scroll-padding-bottom` forced to 0, 7 of 38 controls end up under the bar; with it, 0.

**A defect found by the video trial, fixed in the next commit.** In `e548553` (pushed and live for a few minutes) the final check printed the word «null» when nothing was open (`replaceChildren(null)`: the same mistake as the verdict card's «null» in the old interface), and so did the printable record when no optional change or dismissal existed. The browser checks had not looked for it. Fix: one helper (`fill`) that leaves out empty slots; `ui_journey_e2e.mjs` now fails on any «null», «undefined» or «[object …]» in the page text with everything decided and in the record, and `ui_long_e2e.mjs` does the same for the no-findings state. Negative control: the new check fails (3 of 3 viewports) on the `e548553` `app.js` and passes on the fixed one. All other checks re-run: `pytest` 345, the six browser checks and axe all pass.

**Push and live checks (`e548553`, then the fix `3d9b34c`).** `git push origin main` (`5be1ac3..e548553`, then `e548553..3d9b34c`, fast-forwards, no force). `/api/health` → `"build"` read `5be1ac3…` for about 20–40 s after each push and then the new commit (`e5485532…`, later `3d9b34c8…`). After the second push the served `index.html`, `app.js`, `styles.css`, `revision.js`, `surahs.js` and `samples/sample-demo.txt` were byte-identical to the repository (`shasum`). **Live journey** (`scripts/live_smoke.mjs`, desktop 1366×900, on `e548553`; one audit = one Groq call): all checks PASS; page 1.4 s warm; one click loaded and audited in 9.0 s wall; the model answered HTTP 200 in 0.8 s, proposed 4 spans (all 4 the same ones the program found), added 0; the audit-method notice is one folded line. **Video**: two real takes on `3d9b34c` (`submission/video/v5-take1-buttons-under-caption/`, `submission/video/v5/`); in both the model answered **HTTP 429** (`ai_failed`, 230 ms), so the take shows the model-failed state on the live site and the page says so in one plain line (the video's caption says the model did not respond, nothing more). The first take was rejected because its caption bar covered the buttons during two scenes; the second scrolls the buttons clear of it. Every scene action ran without error; frames inspected as contact sheets. The raw take is 102.0 s; the first 1.9 s (a blank page while it loads) are cut, so the upload file is 100.08 s (1:40), 1280×720 H.264, no audio stream. **Deck**: slide 7's two stills (the panel beside the article; the final check after two approvals) are the live page rendering that response (replayed; no extra Groq call); the deck was rebuilt with 345 tests on slide 8 and nothing else changed.

**Last live check, on `101f04b` (docs on top of `3d9b34c`; the served files are byte-identical to the repository).** `scripts/live_smoke.mjs` desktop: all 20 checks PASS, page 1.5 s, load + audit 8.4 s wall, model HTTP 200 in 0.9 s, proposed 4 (the same 4 the program found), added 0. I ran this script twice by mistake (the second run only to count the checks: 20 PASS), so this session made **two** Groq calls in a minute, both answered 200; together with the two video takes (both 429) and the earlier smoke run on `e548553` that is five live audits in about 35 minutes. The model has still never added a detection in any audit, and no AI benefit is claimed.


## 2026-10-03 (early morning, Riyadh) — final pass: the correction gap and the last UI QA (Pre-challenge)

**Correction gap.** Cause, change, tests and the rerun of all six frozen sets: `docs/EVALUATION.md`, «Long-article set, run 2». In one line: a marked three-word quotation with one wrong word and a correct ayah reference could never get replacement text because word-level similarity tops out at 0.667 for three words and the floor is 0.75; the floor is now waived only for a stated boundary + ayah-level reference + no close rival + exactly one word swapped. `pytest` **351 passed** (345 + 6 new, 2 of them fail without the fix).

**Review aids.** Neither an accessibility skill nor a web-design-guidelines skill is installed in this environment (the only design skill is `apple-design`; an old accessibility plugin sits in the plugin trash and was not used), so the pass was manual: axe-core, Playwright (Chromium) at 1366×900, 390×844 and 320×640, the rendered pages looked at as images, and a keyboard-only run. **No claim is made that this proves the page is accessible**: automated checks find only a part of the problems, and no screen reader, no real phone and no user was involved.

**New script `scripts/ui_final_qa.mjs` (144 checks).** The five states (empty; a possible quotation; a correction; an error; the final check) at the three widths: no horizontal overflow, the deciding controls on screen and above the bottom bar, no stray null/undefined/NaN text, controls at least 24×24 px (WCAG 2.2, 2.5.8), the error state announced (role/aria-live) with a working retry. Keyboard only: the article typed in with Tab and the keyboard, every pending quotation decided with Tab and Enter (the 4-quotation demo: 2 decisions; the 12-quotation long article: 8 decisions of 4 kinds: boundary confirmed, change approved, «I reviewed it», verse chosen), then the copy button reached and activated; **every Tab stop** (20 to 65 per run) checked to be inside the window, topmost at its centre (not covered by the bottom bar or the selection bar) and to have a visible focus indicator.

**Findings, all fixed in CSS (no visual redesign):**
1. The «قرآنبيديا ↗» source link in each card was 22 px high, below the 24 px minimum target; it now has 2 px of vertical padding.
2. At ≤ 900 px the card header's «السابق/التالي» buttons are hidden because the bottom bar offers the same step, but the bar is the last element in the page, so after settling a boundary a keyboard user needed **26 Tab presses** (12-quotation article) to reach it, and a desktop browser at 400 % zoom gets the same layout. Those buttons now stay in the tab order, visually hidden, and are shown while one of them has focus: Shift+Tab from the card reaches «التالي» in 2 presses at every width, and pointer users see no change.
Two false alarms of my own script (a hidden first button on desktop; a tall card that takes programmatic focus) were corrected in the script, not in the page.

**Looked at and found acceptable.** The correction card at 320 px shows the sentence, the place, the change and the reason; the buttons are one scroll below the first screen on a 640 px-high window, and scrolling and keyboard focus keep them clear of the bar (checked by the script). The empty state's first screen at 320 px has the demo button and the text box. The error state keeps the article and shows one retry button below the box. The final check lists the change in its sentence and the seven undecided items with their reasons.

**Not covered.** No screen reader (VoiceOver/NVDA), no real phone, no forced-colours/high-contrast mode, no 400 % zoom on a real desktop browser (the 320 px viewport stands in for it), no test with the keyboard on iOS. The six other browser suites were re-run on the final CSS and pass: `ui_journey_e2e` 167, `ui_long_e2e` 94, `ui_a11y_check` 21 (axe-core WCAG 2.0–2.2 A/AA + best practice, 0 violations on the states it opens), `ui_e2e` 27, `ui_phrase_e2e` 38, `ui_boundary_e2e` 46, `ui_uthmani_e2e` 32.

**Push, live checks, the one planned AI take (3 Oct, after `4bc152c`).** `git push origin main` (`7d098a3..4bc152c`, fast-forward, no force). `/api/health` → `"build"` read `7d098a3…` for about 20 s and then `4bc152c092dd…`; `index.html`, `app.js`, `styles.css`, `revision.js`, `surahs.js` and `samples/sample-demo.txt` served by Render are byte-identical to the repository (`shasum`). The live writer journey is the recording itself (`submission/build/record_demo5.mjs` against the deployed service): one click on «جرّب المقال التجريبي» loads and audits the demo article, two approvals, the final check, «نسخ المقال المعدّل»; no scene action failed, and the copied text equals the previous take's (`diff` empty).

**The AI attempt: one Groq call, HTTP 429 again.** Before it, no Groq call was made at all (the dry run of the recorder used a local AI-off server; all evaluations and browser suites run with AI off). The single audit on the live service returned `ai.outcome = "failed"`, `http_status 429`, 307 ms, `proposed 0`, so the model proposed nothing and added no finding; the audit continued with the markers and the Quran search (4 quotations, 2 changes proposed) and the page and the video's caption say only that the model did not respond. **Groq's own message is not about a time window:** «Request too large for model `qwen/qwen3.8-27b` … on output tokens per minute (OTPM): Limit 1000, Requested 1673. The request's expected output tokens exceed the enforced limit; reduce max_tokens». The previous take's 429 said «Requested 1994». So the per-request output reservation (our `max_completion_tokens` is 4096 by default) is above this account's 1000 OTPM limit for the model, and **waiting does not clear it**; an earlier live audit that returned 200 on `e548553` shows it is not always so, which this record cannot explain. Nothing was changed about it (the owner's earlier instruction not to set `GROQ_MAX_COMPLETION_TOKENS=512` stands; a lower reservation was not tested live). No AI benefit is claimed.

**Video (upload file).** The raw take is 101.68 s; the first 1.9 s (page loading before the zoom) are cut: 99.76 s (1:39.8), 1280×720 H.264, one video stream, **no audio stream**; Arabic captions burned in; contact sheet at 4-second spacing inspected (buttons and the final check clear of the caption bar, no stray «null», no key or dashboard on screen). Phone check of the captions: frames downscaled to 844 px wide (a phone playing it full screen in landscape) and 390 px wide (inline in portrait): at 844 px the caption text is about 16 px high and legible; at 390 px it is about 7 px, hard to read, and a larger font would not fix that, so the captions are legible full screen and not inline in portrait. The participant guide says only «فيديو … لا يتجاوز دقيقتين» (nothing about sound, narration or captions in the text of the guide), so a silent captioned video satisfies it; an optional narration script is `submission/NARRATION_SCRIPT.md`.

**Deck.** `final_deck4.py … 351`: only the test count (slide 8) and the date on slide 12 changed («قبل 4 أكتوبر 2026», instead of «حتى 2 أكتوبر») ; the stills on slide 7 are the 2 Oct ones (the interface the stills show did not change except the 2 px of padding on the source link). All 13 exported pages (LibreOffice PDF, 1440×810 pt) were looked at as images: no overflow or clipped text; the tag `pre-challenge-baseline` on slide 12 no longer breaks at its hyphen. PowerPoint itself was not used.


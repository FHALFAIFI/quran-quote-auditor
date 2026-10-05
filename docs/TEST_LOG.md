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


## 3 Oct 2026 — Groq output-token limit: what is current (docs-only note; earlier entries above are history and were not edited)

- **What was observed.** Audits of the live service answered HTTP 429 «Request too large for model `qwen/qwen3.8-27b` … on output tokens per minute (OTPM): Limit 1000, Requested N» with N between 1100 and 1994 (earlier entries: 1457, 1100; video takes of 2–3 Oct: 1648, 1994, 1673) while the app reserved the default `max_completion_tokens` 4096. Groq's N was never 4096 and its estimate is not documented. Earlier entries here that say the default "stays at 4096" or that a lower reservation "made no difference" describe 30 Sep results (input-token limit hit, no OTPM 429 in that run) and are left as they were.
- **What was done.** The user set `GROQ_MAX_COMPLETION_TOKENS=800` on Render (not readable from outside; `/api/health` does not show it). Two live calls, both on build `82c919c`, both HTTP 200, `ai.outcome` ok, proposed 4, located 4, discarded 0, added by the model 0, no error, not truncated: one audit of the demonstration article (929 ms) and, about 2.5 minutes later, one recorded video take (760 ms). That is two calls and no controlled test; it does not prove the 429 cannot return. The demonstration article needs about 75–90 output tokens; an answer longer than the cap is treated as a failure (the AI result is dropped, the deterministic result stands, AI is skipped for the cooldown).
- **Current-limit wording corrected** in `README.md` (variable table and a note), `docs/RENDER_DEPLOY.md` (variables table and Groq limits), `docs/PILOT.md` (cost table) and `.env.example` (commented line), which had said only 8,000 (or 7,000 input) tokens/minute or «leave unset». The code default is unchanged at 4096 and `render.yaml` is unchanged.
- **No Groq call was made for this note** and no media or code changed. The model still added no detection in any audit; no AI benefit is claimed.


## 3 Oct 2026 (Riyadh, ~05:15–06:00) — overnight re-verification of `99a97ac`; the interface patch was not received (pre-challenge work)

- **Patch.** `0001-Pre-challenge-focus-the-Arabic-review-interface.patch` (expected SHA-256 `2f4523e4…16aa`) was **not available on this machine**: no file of that name, and no `.patch`/`.diff` anywhere searched matched that hash. Nothing was applied, nothing reconstructed from pasted text, no UI code changed. The old interface stays live; the upload trio (`bcd3b926…`, `68190197…`, `65bb988b…`) is unchanged.
- **Checkpoint.** Local `main`, `origin/main` and Render `/api/health` `build` were all `99a97ac0cdbdac380da608b0eced4188b0b3e407`; tag `pre-challenge-baseline` → `532e965`; the live root answered 200 after 22.9 s (cold start); `ai_last_call` was `never_called`: no Groq call was made tonight.
- **Python:** 351 passed. **Node revision tests:** 11 passed. **Browser (Playwright 1.63, own AI-off server):** `ui_journey_e2e`, `ui_e2e`, `ui_phrase_e2e`, `ui_boundary_e2e`, `ui_long_e2e`, `ui_uthmani_e2e`, `ui_final_qa`, `ui_a11y_check` all «all checks passed» (axe: 0 violations in the states they cover). **API:** `e2e_check.py` against a local AI-off server: failures 0; 12 sensitive paths (`/.env`, `/.git/config`, `/app/main.py`, encoded `..` forms, `/requirements.txt`, `/eval/…`, `/submission/…`) all 404.
- **Frozen evaluations, fallback mode, rerun.** SHA-256 of `articles_frozen`, `phrases_frozen`, `uthmani_heldout` equal their `.sha256` files; the four label validators print OK. The six sets (`cases`, `heldout`, `phrases_frozen`, `articles_frozen`, `uthmani_dev`, `uthmani_heldout`) were run again (`eval/results/fallback-20261003-0527*-recheck-*`): rows, summaries, negative hits, formula hits and extra findings are **identical** to the recorded runs `…014049–014053-gapafter-*` apart from the timestamp and per-article seconds. Reminder of what they measure: author-labelled sets, not an independent accuracy rate; the Uthmani held-out set has one `false_wording_fix_on_correct_quote` (u32, mixed Uthmani and plain spelling), disclosed earlier. AI mode was not rerun (no Groq call).
- **Fresh public clone** (`git clone` of GitHub at `99a97ac`, new venv from `requirements-dev.txt`, environment emptied, no key): server starts in `mode: reduced`, `/api/audit` of a marked 94:5 quotation with the right reference → wording matched, reference matched. `pytest`: 330 passed and 21 skipped on first run (those tests need the local copy of the Quranpedia text, which the app downloads on first start), **351 passed** on the second.
- **Secret and private-file scan.** No key-shaped string in any tracked file across all history; no `.env`, organizer PDF, template or `.vercel` file tracked; no e-mail address in tracked text.
- **Rights finding.** Six of the `eval/results/*uthmani-{heldout,dev}.json` files (written 2–3 Oct) quoted Tanzil excerpts without Tanzil's notice, contrary to what `SOURCES.md` §1b said. The notice was added to those six files (only keys added; every other value verified unchanged against `HEAD`) and `eval/run_eval.py` now copies `_text_source` and `_notice` from the case file into the result. GitHub still serves all six old SHAs (`845844d`, `7d78577`, `5f0613d`, `e3aaa4b`, `2df2e34`, `cdf151b`) by API and web (HTTP 200 on 3 Oct); they have not been purged; 0 forks, 0 PRs, no `refs/pull/*`.
- **Current interface, observed (screenshots at 1366, 390, 320 px of the journey and final-QA scripts), for comparison with the patch later:** the verdict banner stacks three text blocks and a separate note repeats the scope; on desktop the written reference `[الزمر: 10]` breaks across two lines; the dark navy header and footer are the old palette. The decision panel, the old/new word, the source link and the uncertainty line are already beside the article.

## 3 Oct 2026 — editorial interface revision (written 3 Oct 03:56 as pre-challenge work; integrated afterwards)

- **Origin and dates.** The patch was written on 3 Oct 2026 at 03:56 (+03:00) as local commit `9618f04` on top of `99a97ac`, on a different machine (Git for Windows), before any challenge-period work. It did not reach this machine until it was published on the branch `editorial-redesign-handoff` (commit `ccfa04b`, 3 Oct 05:39); that branch only stores the patch file and was not merged. The patch file's SHA-256 `2f4523e4…16aa` was verified, the patch was read in full, and it was applied here with `git am --3way` on top of `573b53f`; the only conflict was this file (two sections appended at the same place), resolved by keeping both. Integration time and push time are recorded in the entry below.

- **Observation.** A fresh live audit had multiple competing containers for the same review: a result banner, decision card, expanded queue, article view and final check. The prior purple/navy treatment, pills and nested cards made the writing task harder to scan. The existing user-owned live tab was left untouched.
- **Change.** A narrower, quieter entry screen; warm paper and dark ink; one restrained green action color; a compact header and footer; flat queue rows; the article and current decision as the primary view. One uncertainty reason stays next to the decision, with the full reasons and verse evidence in its disclosure. The source and privacy links remain. No verse text, detector or evaluation label changed.
- **Interaction.** A delayed `/api/phrase` response previously took focus back to the older quotation after the writer moved on. The result now updates the older finding while preserving the current card. `scripts/ui_async_navigation_e2e.mjs` holds the response until after navigation and checks both properties.
- **Local checks (AI off, no Groq calls).** 351 Python tests; 11 Node revision tests; `ui_journey_e2e`, `ui_long_e2e`, `ui_phrase_e2e`, `ui_e2e`, `ui_boundary_e2e`, `ui_uthmani_e2e`, `ui_final_qa` and the new delayed-response check all pass. The first long run exposed a footer disclosure that could sit behind the mobile dock; footer spacing was corrected and the full long run passed on rerun. Axe-core WCAG 2.0–2.2 A/AA found 0 violations on entry, audit and final states at 1366, 390 and 320 px. Windows clipboard line endings were normalised in two browser assertions; the copied text itself was unchanged.
- **Release boundary (as written in the patch).** The patch author's note: not merged or deployed; the submission video and slide screenshots depict the previous interface and need a new take if the design is published. (Superseded by the integration entry below.)

## 3 Oct 2026 (Riyadh, 05:46 onward) — integration of the editorial interface revision (pre-challenge work)

- **Dates.** Patch written 3 Oct 03:56 (+03:00) (author date of `6b57015` preserved by `git am`); published as a patch file on branch `editorial-redesign-handoff` 05:39; applied to local `main` on top of `573b53f` at 05:46 (commit date of `6b57015`); pushed to `main` once, later the same day (3 Oct 2026, Riyadh) together with this entry. The push time is not written here because a docs commit after the push would redeploy; Render's build (`/api/health`) and GitHub's push event hold it.
- **Review before applying.** SHA-256 `2f4523e4…16aa` matched; the 604-line patch was read in full: CSS/HTML/JS of the interface, two clipboard line-ending assertions, one new browser script, CHANGELOG and TEST_LOG. No detector, verse text, evaluation file, dependency or secret. The footer lost its line «عمل ما قبل التحدي — …»; that status remains stated in the README, BASELINE.md, CHANGELOG and this file.
- **Conflict.** `docs/TEST_LOG.md` only (both commits appended at the end): both sections kept.
- **Two findings at integration, both fixed in `6c8c5cb`.** (1) `ui_phrase_e2e` failed on the patched tree (two failures, repeatable, passing on `573b53f`): the patch kept the writer on the card they had moved to by comparing the current card with the request's finding id, but a selection that overlaps no finding gets a new id, so its result was never shown. Fix: compare with where the writer was when the request started. The patch's own delayed-response test uses an existing card and did not catch this. (2) `ui_a11y_check` reported one axe `target-size` violation at 390 px (and once at 320 px) in the span editor on the patched tree (3 of 3 runs; 0 of 3 on `573b53f`). Cause: the audit ran while the editor was still scrolling into view and the sticky bottom bar covered a word chip. Measured after the scroll settled: 0 chips under the bar at 390 and 320 px. The script now waits 1.5 s first. This is a change to the check, made after seeing it fail; the settled-state measurement is what supports it.
- **Gates on the final code** (AI off, no Groq call): 351 Python tests; 11 Node tests; `ui_journey_e2e` 167, `ui_e2e` 27, `ui_phrase_e2e` 38, `ui_boundary_e2e` 46, `ui_uthmani_e2e` 32, `ui_async_navigation_e2e` 4, `ui_long_e2e` 94, `ui_final_qa` 144 checks, no failures; `ui_a11y_check` 21 states, 0 axe violations; `scripts/e2e_check.py` against a local AI-off server 0 failures. No sampled-screenshot review replaces these: desktop, 390 and 320 px screens were looked at (entry, first decision, final check) and show the article and current decision first.
- **Docs touched:** `SOURCES.md` (the challenge palette is no longer used by the web interface), `README.md` (new script), `CHANGELOG.md`.
- **Not yet done at the time of this entry:** the live journey on Render, the new video, slides and PDF (they depict the previous interface until rebuilt).

## 3 Oct 2026 (Riyadh, ~06:50–07:00, recorded afterwards) — live journey on build `503ec13` and three Groq HTTP 429s; the journey assertion corrected (pre-challenge work)

- **Live journey, desktop (1366×900) and phone (390×844, touch), `scripts/live_smoke.mjs` against https://quran-quote-auditor.onrender.com, build `503ec130224018057dc670c4e957bb9da37202e3` (confirmed 06:51:35; `app.js`, `index.html`, `styles.css` byte-identical to the repository).** Every functional check passed at both widths: one click loads and audits the demonstration article; the verdict «وجدنا ٤ اقتباسات؛ يحتاج اثنان إلى قرارك»; the first decision on screen and focused with «يجزى ← يوفى» and its two buttons; four quotations (two matched, two waiting); the panel moves on to the second decision by itself; the final check lists both changes in their sentences and says it does not certify the whole article; the revised text and the clipboard hold exactly «يجزى»→«يوفى» and «الشرح: 6»→«الشرح: 5»; no horizontal overflow; no console or page error. **One check failed at the time:** «what is visible of the audit-method notice is one short line». The script chose its length limit from `/api/health` (`mode: ai` ⇒ at most 70 characters) and so expected the quiet line shown when the model answers. The model had not answered, so the page correctly showed the visible model-failure warning («تعذّر اقتراح الذكاء الاصطناعي هذه المرة. فُحص المقال بالعلامات وبالبحث في المصحف، وقد تفوت عبارة قصيرة بلا علامات؛ حدّدها في المقال لتفحصها.» and the folded «تفاصيل هذا التدقيق»; 159 characters when the saved response is replayed). That was a wrong expectation in the script, not a defect in the page. The phone run came inside the app's own failure cooldown and made no Groq call. The per-check console output of that run was not saved; this entry is written from the run's result, its screenshots (not committed) and the numbers in the next bullet.
- **Groq answered HTTP 429 in all three live calls that morning:** 06:52:01 (this journey, desktop), 06:55:49 (video take 1) and 06:58:39 (video take 2), each in about 226–249 ms; the page said «تجاوزت خدمة الذكاء الاصطناعي حد الاستخدام (الحصة) مؤقتًا» and `/api/health` shows `ai_last_call` outcome `failed`, `http_status` 429, 226 ms at 06:58:39. The body kept for take 2 reads «Request too large for model `qwen/qwen3.8-27b` … on output tokens per minute (OTPM): Limit 1000, Requested 1027»; the bodies of the other two were not kept. Two calls at about 02:40 the same night, with `GROQ_MAX_COMPLETION_TOKENS=800`, had answered HTTP 200. **The cause is not established.** The value on Render is not readable from outside; Groq's «Requested» figure is its own undocumented estimate (1027 here, 1100–1994 before); a limit that "resets" is not what the message describes (it is a per-request size check). The audit itself finished each time (the journey found the four quotations; take 2's saved response has `mode` `ai_failed`, nothing proposed, nothing added by the model); take 1's response was not kept. In no audit has the model added a detection; no AI benefit is claimed.
- **Assertion corrected (`scripts/live_smoke.mjs`; no app code changed).** The script now records the audit response's own `mode` and applies the expectation for what that audit did: `ai` ⇒ the quiet line (at most 70 characters, unchanged); `reduced` ⇒ at most 140 (unchanged); `ai_failed` ⇒ the warning must be visible, must begin with «تعذّر اقتراح الذكاء الاصطناعي هذه المرة» and say the markers and the Quran search were used, the visible notice must stay within 200 characters, and the response must agree (`ai.responded` false, nothing proposed, nothing added by the model). An unknown mode fails. All other checks are untouched. Verified **without any Groq call**: against a local AI-off server (`reduced`) desktop and phone all checks pass; against the same server behind a proxy that replays the recorded take-2 response (`ai_failed`, HTTP 429) desktop and phone all checks pass (notice 159 characters); with the replayed response altered to «proposed 2» the new agreement check fails and everything else passes.
- **Not re-run live.** The corrected script was not run against Render afterwards, because a live audit is one Groq call and the console that would show whether the limit changed was not available. The recorded submission video therefore stays the 3 Oct take 2, which shows the model-failure branch and says only that the model did not respond.

## 3 Oct 2026 (Riyadh, 15:16 → evening) — writing workspace: baseline, review of the tree found, gates, measurements (pre-challenge work)

- **Baseline, verified (not assumed) at 15:16 +03:00.** Local `main` = `origin/main` = `fe7ef19`; live `/api/health` → `build: fe7ef19ea116855b73c5c63a7932fa7d3d45c945`, `max_chars: 6000`, `ai_configured: true`, `ai_last_call: never_called` (a fresh instance), source not yet loaded (cold). The three upload files in `submission/UPLOAD/` hash to the values in `SUBMISSION_CHECKLIST.md` (`2dce2a03…`, `4b114c97…`, `595ff8f6…`). The limits named in the task were all still true: a 6,000-character limit; the current article in `sessionStorage`; decisions reset by every new audit (`decisions = {}` in `runAudit`); short unmarked misquotations only "possible" (README, unchanged); evaluation sets author-written; Groq 429s not retested (**no Groq call was made today**).
- **Provenance of the work found in the tree.** Branch `writing-workspace` (created 14:51:50 from `main`) held ~730 uncommitted changed lines and 15 new files (`app/suggest.py`, `workspace.js`, `suggest-ui.js`, three stub trust pages, a suggestion set and its builder/validators, a long-article validator) last modified between 14:59 and 15:15. The last Claude session in this project had ended at 14:20 and its transcript does not contain them; the author is **not established** (another tool or session on the machine is possible; an attempt to look at another tool's session files was refused by the permission layer and I did not pursue it). I read the code, ran it, wrote the missing tests and changed it (CHANGELOG, commit `57d1c02`). Anything those files said about themselves, notably that suggestion set A was "written blind before the feature existed", is treated as **unverified** (see EVALUATION).
- **What the first run of the tree showed.** 352 Python tests passed, but all nine browser suites failed against the new layout (selectors for the moved decision card; checks of the old fold-away input). Rendered: a literal «null» in the suggestion box; the box docked at the top of a phone, far from the caret; the brief's own example «…إلا لعبادتي» returned nothing; an exact continuation from the wrong verse (SG-046) for a wrong last word; passages beyond 150 dropped silently; the explicit «أكمل من المصحف» held to a stricter word bar than automatic suggestions; a textarea with no focus outline; 18 px checkboxes; contrast failures in the suggestion box (axe); a debounced render that could let a fast «copy» use the previous text. All fixed and covered by tests (commits `57d1c02`, `3bbf94b` and the following one).
- **Gates on the final code** (AI off, no Groq call, local server on `:8765`; superseded by the final run in the later entry below): 392 Python tests at that point; browser suites as listed there.
- **Frozen files.** `shasum -c` OK for all six sidecars; `git diff` of `cases.json`, `heldout.json`, `phrases_frozen.json`, `articles_frozen.json`, `uthmani_*.json` empty. Re-running the six older sets in fallback mode on the final code gives **rows identical** to the last recorded runs (`…gapafter-*`) for all six (the result files of this rerun were not kept).
- **Evaluation and measurement** (details, caveats and the four "matched" references in `docs/EVALUATION.md`): suggestion set B (blind-authored, run once) 71/76 suggestions, 0/39 false, 14/14 ambiguous safe, 19/22 corrections; dev set A 74/76, 0/39, 22/22 after two disclosed rule changes; long-article set 186/191 detected, 0 misquotations "matched"; audit of 20,000 characters 1.2 s, 87 MB, ≤ 0.6 MB response (local). Raw files `eval/results/suggest-20261003-*`, `fallback-20261003-164630-long-20261003-first-run.json`, `length-20261003-local.json`.
- **Not done / not measured.** Render performance with a long article (measured after the deployment, below); Safari, Firefox, a real phone keyboard, a screen reader; any user study or time saving; an AI benefit (the model is never involved in suggestions, and in every earlier audit proposed nothing the deterministic path had not found); independent review of any label.

### 3 Oct 2026, later — an independent review of the branch, and the same journey in WebKit and Firefox (pre-challenge)

- **Independent review.** I ran the `code-review` skill (high effort) on `main..HEAD` before the release. It reported ten issues; I checked each against the code and **all ten were real or valid hardening**, fixed with tests: (1) `requestPhrase`/`applyPhrase` applied an answer to text edited after the request left (offsets for the old text) — now dropped with a visible message; (2) no guard for a document replaced («مسح», a sample, a draft) while an audit or phrase check was in flight — a `docGen` token drops the late answer; (3) «اقتراح الآيات أثناء الكتابة» off did not stop the opt-in «العبارة المميزة» mode from sending text; (4) the «جارٍ البحث…» line could stay forever when its answer was dropped; (5) the stale zone looked 48 characters back for a lead-in while the server looks 70–80 (`quran_cue` 70, `audit.py` 80) — now 80; (6) the rate limiter's keys could grow without bound under spoofed `X-Forwarded-For` — now bounded (the header is still client-supplied: best effort, as documented); (7) an insertion after a word typed with «،» and no space had no leading space; (8) a failed `sessionStorage` write was silent and stored the article three times; draft autosave parsed `localStorage` on every keystroke; (9) a dead conditional in `suggest.py` and a client/server mismatch on «!» and «?» as sentence ends; (10) `/api/suggest` accepted twice the text it then silently cut (offsets would be shifted) — now refused (422).
- **Two further defects I found while writing tests for those fixes.** An explicit «أكمل من المصحف» request showed «جارٍ البحث…» and then lost it (and sometimes its answer): the textarea's blur handler hid the box even though focus had already returned, and a debounced automatic request from earlier typing cancelled the explicit one. Both fixed (`ui_suggest_e2e` now delays the answer 1.5 s and checks that it still arrives).
- **WebKit (Safari's engine) and Firefox, `scripts/ui_crossbrowser.mjs`** (Playwright's builds; desktop and a 390 px touch profile; same journey as above plus the highlight-layer alignment): the first run **found a real bug** — on the touch profile WebKit never sent the `click` for a tap on «أدرج», because the box cancelled `pointerdown` (meant to keep the keyboard open). Removed; `mousedown` is still cancelled (touch browsers emit an emulated one). WebKit's native undo takes back the whole typing run together with the insertion (Chromium takes back just the insertion); the test checks only that the word is gone. Firefox here is the cached Nightly build of a different Playwright revision (`FIREFOX_BIN`). **Still untested: Safari itself, a real phone and its keyboard, VoiceOver/TalkBack.**
- **Final gate run on the release code (after the review fixes and the WebKit tap fix; AI off, no Groq call):** 395 Python tests + 24 Node tests (13 edit-tracking, 11 revision engine); browser PASS counts, all with 0 FAIL: `ui_journey_e2e` 167, `ui_e2e` 27, `ui_phrase_e2e` 38, `ui_boundary_e2e` 46, `ui_uthmani_e2e` 32, `ui_long_e2e` 91, `ui_async_navigation_e2e` 4, `ui_suggest_e2e` 137, `ui_workspace_e2e` 136, `ui_final_qa` 144, `ui_a11y_check` 42 (axe: 0 violations), `ui_crossbrowser` 60 (Chromium, WebKit, Firefox × desktop and phone); `scripts/e2e_check.py` 0 failures.

### 3 Oct 2026, 17:39–17:55 +03 — release `a844fc3` to Render, live checks, and the one Groq call (pre-challenge)

- **Push.** Fast-forward `fe7ef19..a844fc3` on `main` at 17:39:24 (and the branch `writing-workspace`). **Render served `build: a844fc3c3f69401a645c78f707ef66baa3e595a9` ~35 s later** (polled every 10 s). Served `index.html`, `app.js`, `styles.css`, `revision.js`, `workspace.js`, `suggest-ui.js`, `surahs.js`, `sources.html`, `privacy.html`, `limitations.html`, `samples/sample-demo.txt`, and the pages `/`, `/sources`, `/privacy`, `/limitations`: **byte-identical (SHA-256) to the repository files**. `/api/health`: `status ok`, `max_chars 20000`, `ai_max_chars 6000`, `ai_configured true`.
- **Live journey, `scripts/live_workspace.mjs`** (desktop 1366×900 and 390×844 touch; the writer unticks «استخدام الذكاء الاصطناعي» first, and the script stops if it cannot): all checks passed on both: limit shown, the three pages linked from header and footer, the paste box links to the privacy page, suggestion «ليعبدون / الذاريات» appears and Tab/tap inserts it, «لعبادتي ← ليعبدون» is offered and not applied, the demonstration article (4 quotations, 2 need a decision), an edit inside a quotation makes it stale, the recheck keeps the approval of the untouched one, a 17,532-character article is audited (16.0 s desktop, 17.5 s phone), no console errors. **Every audit response said `ai.outcome: skipped_writer`; `ai_last_call` stayed `never_called`** — no model call.
- **Render timings** (table in `docs/EVALUATION.md`): about 1 ms per character, 8–15 s for realistic 8–15k-character articles, ~25 s at 20,000. One earlier run of the measuring script timed out once at 180 s, cause unknown (see there).
- **The one Groq call of this work, made on purpose at 17:54:15 +03** to confirm the optional path on the released build: `POST /api/audit` with the demonstration article, model left on. **Groq answered HTTP 429** (214 ms; the app's message «تجاوزت خدمة الذكاء الاصطناعي حد الاستخدام (الحصة) مؤقتًا»); the audit still returned **HTTP 200 in 1.5 s with all 4 findings**, `mode: ai_failed`, the visible warning, `proposed 0`; `/api/health` then showed `ai_last_call failed / 429 / cooldown 119 s`. Cause of the 429 not investigated (the account limit, as on 3 Oct morning). No other Groq call was made today by this work, and none is planned: the recorded video has the model off.


## 3 Oct 2026 — interface in the challenge's navy and mint, review branch `ux-redesign-2026` (pre-challenge work, not deployed)

- **Starting point.** `main` = live = `e014e1b`. A Codex proposal (commit `4531bd6`, written on a Windows checkout and never pushed) was received as a pasted patch. Its code hunks were applied to a scratch worktree and screenshotted against `main`, never committed. The two sets plus this branch were captured at 1366×900, 390×844 and 320×640 over the same journey: empty page, demo first decision, first approval, final check, edit making a quotation stale, recheck, long article (frozen L1), possible quotation (L2), live verse suggestion (one verse; several verses), and `/sources`, `/privacy`, `/limitations`. The screenshots and comparison sheets are kept locally (`submission/assets/ux-review-2026-10-03/`, git-ignored).
- **Problems found.** (1) On `main`, primary buttons used the same green as "matches the source", so an action looked like a verified state. (2) A quotation kept as written, or one the writer only reviewed, was drawn in the same green as an exact match. (3) A possible quotation (`يحتاج تأكيدك`) looked the same as a proposed correction. (4) In a long article the first open quotation sat far below the verdict, out of view next to its card. (5) «٢٠٠٠٠» rendered as «٢····» because the Arabic zero is a dot. (6) The state legend was at the bottom of the page, away from the decisions. In the proposal: (7) a navy banner with numbered steps and an eyebrow line put five navy blocks on the page and read as a landing page; the banner was wider than the centred article on the empty page; it used Latin «01 02 03» while the page uses Arabic-Indic digits. (8) It used four action colours (navy, teal, green, mint), and the mint «التالي» was the loudest element on the phone, inviting the writer to skip a pending decision. (9) Its shorter hint dropped «مقالك لا يُحفظ على الخادم» and the ﴿ ﴾ glyphs. (10) Its footer line misnamed the challenge («لخدمة» instead of «في خدمة») and called the project a participant before anything was submitted.
- **What changed.** `app/static/styles.css`, `index.html`, `app.js`, and the footers and icons of the three trust pages. No audit, suggestion, verse-source, AI or correction rule changed. Details are in the CHANGELOG row of the same date.
- **Gates (macOS, Python 3.14.7 venv, Node with Playwright and axe-core from a scratch `node_modules`; every server started with AI switched off; no Groq call, no Render call).** `pytest` **395 passed**; `node --test tests/revision.test.mjs tests/workspace.test.mjs` **24 passed**. Chromium suites: `ui_journey_e2e` 167, `ui_final_qa` 144, `ui_e2e` 27, `ui_workspace_e2e` 137 (run twice, before and after the CRLF change), `ui_suggest_e2e` 137, `ui_long_e2e` 91, `ui_phrase_e2e` 38, `ui_boundary_e2e` 46, `ui_uthmani_e2e` 32, `ui_async_navigation_e2e` 4 — **0 failures**. `ui_crossbrowser` (Chromium, Firefox Nightly 1543 and WebKit, desktop and phone) **60, 0 failures**. `ui_a11y_check` (axe-core, WCAG 2.0–2.2 A/AA + best practice): **0 violations in 42 checks** (14 states × 320/390/1366). Keyboard: real Tab presses on the empty page and on the panel head, bottom bar and footer at 1366 and 390. Focus rings are mint (3 px) on navy and deep teal on paper. The only new tab stop is «كيف نتحقق؟» before the demo button. `git diff --check` clean. Three test expectations were changed for the grouped counter («٢٠٬٠٠٠»): `ui_long_e2e`, `ui_workspace_e2e`, `live_workspace`. From the proposal, the test harness took the `PLAYWRIGHT_CHROME_PATH` override (a local browser on Windows) and a copy check that normalises CRLF.
- **Limits.** These are automated and visual checks on one Mac; they are not a study with writers (`docs/UX_REVIEW_PLAN.md` is a plan, not run). No real phone, Safari on iOS or screen reader was used. The submission video, deck and PDF still show the deployed interface (`e014e1b`), and must be rebuilt before this branch reaches `main` (a push to `main` redeploys Render).

### 3 Oct 2026, night — Arabic counts in the final review, before release (branch `ux-redesign-2026`, pre-challenge, not deployed)

- **Defect.** The final review before copying read «سيُنسخ مقالك بعد ٢ تغييرين اعتمدتَهما» (Arabic says the dual without a numeral) and, after one change was kept, «أبقيتَ ١ كما كتبتَ» (a bare number with no counted noun). It was visible in the submission video and in the final-review screenshot. Four browser scripts had pinned the wrong wording.
- **Fix (`app/static/app.js` only).** One helper, `countAr(n, one, two, few, many)`: one and two without a numeral, 3–10 with the plural, 11 and above with the singular accusative; each form is a whole phrase, so the pronoun after the noun agrees with it. Applied to the approved-change count, the kept-as-written count (now counted as places: «وأبقيتَ موضعًا واحدًا كما كتبتَه» / «موضعين كما كتبتَهما» / «٣ مواضع كما كتبتَها» / «١١ موضعًا كما كتبتَها»), the dismissed count, the stale-place counts, the refused-change notice and the copy note. The existing `maqatiAr` now uses the helper (same output). Counts of 100 and above follow the 11+ form (the last two digits are not considered); no article is expected to reach that.
- **Test.** New `scripts/ui_counts_e2e.mjs`: an article quoting Az-Zumar 10 twelve times with «يجزى», decisions set in the page state, the sentence read for approved 1, 2, 3, 10, 11, 12; kept 1, 2, 3, 10, 11; dismissed 1, 2, 3, 11 — **17 PASS, 0 FAIL**. Negative control: the same script on the previous `app.js` fails 10 of 17. Updated assertions: `ui_journey_e2e` (1 and 2 approved, 1 kept), `ui_phrase_e2e` (1 dismissed), `ui_uthmani_e2e`, `live_smoke`.
- **Gates (AI off on every server, no Groq call, no Render call).** `pytest` 395 passed; `node --test` 24 passed; Chromium: `ui_counts_e2e` 17, `ui_journey_e2e` 167, `ui_phrase_e2e` 38, `ui_uthmani_e2e` 32, `ui_workspace_e2e` 137, `ui_e2e` 27, `ui_final_qa` 144, `ui_long_e2e` 91, `ui_boundary_e2e` 46, `ui_async_navigation_e2e` 4, `ui_suggest_e2e` 137, `ui_a11y_check` 42 (axe: 0 violations); `ui_crossbrowser` 60 (Chromium, WebKit, Firefox); `live_smoke.mjs` against a local server 21 (desktop) and 21 (`--phone`) — **0 failures**.

### 3 Oct 2026 — automatic model attempt; no writer switch (pre-challenge)

- **Product change.** The per-audit AI checkbox was removed. The browser sends only the article. The API rejects `ai:false` with 422 and accepts `ai:true` only for an older cached page. A configured model is attempted on every short audit and recheck; articles over 6,000 characters, an unavailable model and failed calls still receive the source-based audit with an explicit status. The model only proposes locations. The privacy page now warns that a short article goes to Groq automatically when the service is configured.
- **Offline gates (Windows checkout, no Groq call).** `pytest`: 395 passed. `node --test`: 24 passed. `git diff --check`: clean. The local writing-workspace and journey browser scripts passed their functional assertions, including no AI switch, article-only audit requests, and no horizontal overflow at desktop and phone widths. Their console-error assertions failed because this sandbox denied loading the existing Google Fonts resource (`net::ERR_NETWORK_ACCESS_DENIED`); this was not an application exception. The full browser suites have therefore not been recorded as clean passes in this environment.
- **Live model behaviour.** Not established by these offline gates; record one audit response after deployment, including `ai.outcome`, and keep a failed or rate-limited response distinct from a model answer.

### 3 Oct 2026 — editorial interface revision (review branch `ui-editorial-2026-10`, pre-challenge; not merged, not deployed)

- **Base.** `main` at `47f224e` (automatic model attempt, no switch), which is live. Every server below had `AI_PROVIDER=none` and no key, so **no Groq call and no Render call** were made. States that need a configured model (failed, over the limit, answered) were produced by rewriting the audit answer in the browser, as `ui_long_e2e` already does.
- **Screens.** `scripts/ui_screens.mjs` was run before and after the change at 1366×860, 390×844 and 320×640. It covers: empty page, suggestion, first correction, possible quotation, last decision, final review, a 14,654-character article over the model's limit (simulated), a failed model (simulated), and the three trust pages. Output is in `submission/assets/ui-editorial-2026-10-03/{before,after,compare}` (git-ignored).
- **Measured entry screen** (Chromium, a fresh page, top of the `#article` box):

  | Width | Before | After |
  |---|---|---|
  | 1366 | 374 px | 209 px |
  | 390 | 561 px | 273 px |
  | 320 | 636 px (bottom of a 640 px screen) | 347 px |

  Words of text above the box: 83 before, 35 after. The demonstration button is still on the first screen at all three widths (`ui_journey_e2e`).
- **Manual first-time-writer walkthrough** (390 px, touch, a new article not in any set). Steps: typed «قال تعالى: إن الله يأمركم أن تؤدوا الأمانات», tapped «أدرج», added a wrong reference [النساء: 85] and a marked Az-Zumar 10, audited, approved the reference, edited inside the second quotation, rechecked, went to the final review, copied. Findings:
  - **(fixed)** after the edit, two filled «أعد التدقيق» buttons were visible; now only the one beside the stale note is filled.
  - **(not fixed: suggestion logic, not layout)** «أدرج» inserted «إلى أهلها وإذا حكمتم», going on past where the writer would stop, so the writer has to delete «وإذا حكمتم».
  - **(observed, correct)** the recheck kept the approved reference and asked again about the edited quotation. The copy note said one quotation was left undecided and copied as written.
  - No page errors.
- **Tests.** One Python assertion was updated: «استُبعد 1» became «استُبعد مقطع واحد اقترحه», because server notices now count in words. No browser assertion was changed.
- **Gates.**
  - `pytest` 395 passed; `node --test` 24 passed.
  - Chromium suites, all with 0 failures: `ui_counts_e2e` 17, `ui_journey_e2e` 167, `ui_phrase_e2e` 38, `ui_uthmani_e2e` 32, `ui_workspace_e2e` 137, `ui_e2e` 27, `ui_final_qa` 144 (keyboard-only runs included), `ui_long_e2e` 91, `ui_boundary_e2e` 46, `ui_async_navigation_e2e` 4, `ui_suggest_e2e` 137, `ui_a11y_check` 42 (axe: 0 violations).
  - `ui_crossbrowser` 60 (Chromium, WebKit, Firefox 151; Firefox was installed for this run after the first run skipped it).
  - `live_smoke.mjs` against a local server: 21 (desktop) and 21 (`--phone`).
  - `git diff --check` clean.
- **Not tested.** Real phones, VoiceOver/TalkBack, Safari on iOS, and any session with a real writer. The walkthrough above was run by the coding assistant, not by a writer. Passing these gates does not make the interface production-ready (see `docs/PRODUCTION_ROADMAP.md`, Stage 4).

## 4 Oct 2026 — defects from the first-time-writer walkthrough (review branch `ui-editorial-2026-10`, draft PR #2; pre-challenge work before 09:00 Riyadh; not merged, not deployed)

Every server below had `AI_PROVIDER=none` and no key: **no Groq call and no Render call** were made. The branch was pushed at 00:08 (+03) and draft PR #2 opened; `/api/health` on Render still reported `build 47f224e` (the push of a non-`main` branch does not deploy).

### Defect 1 — «أدرج» inserted past the writer's stopping point

- **Reproduced** (`app/suggest.py` on the full cached Quranpedia text): after «قال تعالى: إن الله يأمركم أن تؤدوا الأمانات» the first piece was «إلى أهلها وإذا حكمتم»; after «﴿إن الله يأمركم» it was «أن تؤدوا الأمانات إلى» (ending on a preposition) and «أن تذبحوا بقرة قالوا» (into the next speaker's words).
- **Cause.** `_chunk_bounds` offered a fixed four words (`CHUNK_WORDS`) from the middle of a verse, or the rest when five or fewer remained, without looking at the verse.
- **Fix.** The first piece stops at the Hafs text's own pause sign (read from `Ayah.text`, since `Ayah.words` has the signs removed; all 6,236 verses align), or before a word that opens a new clause (a closed list: «وإذا», «ثم», «قالوا», «ولا», «ولكن» …), once two words are offered; it never ends on a particle that governs the next word («إلى», «أن», «الذين», «إلا» …), and six words before a stop come as three and three. The box now says before acceptance where the piece stops («يُدرَج حتى «أهلها»، ثم نقترح ما يليه من الآية»), and after an accepted piece the next one is offered at once, also when the first came from «أكمل من المصحف» with no Quran cue in the sentence (quietly: no «searching» line, no hint if nothing follows). «إلى نهاية الآية» still inserts the rest in one step.
- **Tests.** New `tests/test_suggest_chunks.py` (19): placeholder-word unit tests of the rule; the committed fixture offline («جميعا ولا تفرقوا» stops at ۚ, no pause sign is ever inserted; «قالوا إنا لله» then «وإنا إليه راجعون»); and on the full text the example (piece after piece reproduces exactly the rest of 4:58), short verses («الكوثر», «علما», «يسرا»), the ambiguous «﴿إن الله يأمركم» (two verses, each its own short piece), punctuation («…» and a comma), and the property over every word position of every verse. `scripts/ui_suggest_e2e.mjs` section 13 (Tab at 1366, tap at 390 and 320): the box marks exactly «إِلَىٰ أَهْلِهَا», the insertion stops there, the next piece follows, Escape keeps «… إلى أهلها», «إلى نهاية الآية», the explicit path, the ambiguous choice by arrow or tap, punctuation, a short verse — **200 PASS, 0 FAIL** (137 before).
- **Evaluation.** Both suggestion sets rerun (A development, B post-hoc after a rule change; `docs/EVALUATION.md`): 0 wrong verse, 0 false suggestion, ambiguity 14/14 safe and corrections unchanged in both; hits A 74→71 and B 71→69, all five changes being a one-word piece before a source pause sign (a correct prefix of the two gold words).
- **First failing checks, kept here:** two placeholder-sentence unit tests were wrong about their own word counts, and the offline fixture's 36 verses made the rarity gate refuse (the tests now use the writer's explicit request); the first browser run failed one check because a Tab with no verse chosen moved focus out of the editor, as it should.

### Defect 2 — the phone's bottom bar offered «المراجعة الأخيرة» while that review was on screen

- **Cause.** `renderDock()` knew only whether anything was pending, not where the writer was: with nothing pending it always offered «المراجعة الأخيرة», including while the writer was reading it, and the sticky bar sat over the review's lower lines.
- **Fix (`app/static/app.js`).** The page notes whether the final review is on screen (entered when its top passes 60% of the screen, left at 75% or once scrolled past, so the bar does not flicker). With nothing pending and the review on screen, the bar is hidden and reserves no space; with decisions still open it stays and offers «التالي» back to them. If the bar's own button had keyboard focus when it hides, focus goes to the review's heading, never to a hidden button.
- **Test.** New `scripts/ui_dock_e2e.mjs` at 390×844 and 320×640 with touch: the bar before and after decisions, in the review with and without open decisions, tapping «التالي» and «المراجعة الأخيرة», the copy/print/reset buttons uncovered at the bottom of the screen, no sideways scroll, scrolling back up and down in steps (the bar hides once, no flicker), Enter on the bar's button (focus on the heading), eight Tabs through the review (no focused control under the bar), and «إلغاء كل القرارات» bringing the bar back — **34 PASS, 0 FAIL**. Negative control: the same script on the previous `app.js` fails 6 (the bar visible over the review at 63 px in both widths, never hiding while scrolling, and one focused control under the bar).
- `ui_journey_e2e` 167, `ui_final_qa` 144, `ui_long_e2e` 91, `ui_workspace_e2e` 137 — unchanged, 0 failures.

### Defect 3 — an approved correction did not visibly change the box

- **Why the box is not rewritten.** The box holds the writer's own text: the edit tracking (`workspace.js`), «تراجع», the recheck's carrying of decisions and the final copy (`revision.js`, which applies approved changes to the current text) all rely on it. Writing the correction into it would make every later edit an edit of our text, not theirs.
- **What changed (`app/static/app.js`, `styles.css`, `index.html`).** Before the first approval in an audit, the card says under its buttons where the result goes: «عند الاعتماد يظهر «يوفى» فوق ما كتبتَه في المربع، ويُكتب مكانه في النسخة التي تنسخها.» (the approve button is described by it). After approval, the source's word is drawn small above the writer's word in the box, like a proofreader's mark (the highlight layer's `.fix` span; the box's text is unchanged); the line above the next card says the same; with the caret in that quotation a screen reader hears «يُكتب «يوفى» في النسخة التي تنسخها، ونصّك هنا كما كتبتَه». References are drawn the same way («الشرح: ٥» over «الشرح: 6»). The legend says it too.
- **A defect found by the new test and fixed.** «تراجع» after an approval restored the decision but redrew only the panel: the final review (and the marks) kept showing the undone correction until something else refreshed them. The clipboard was right, because copying recomputes first. The undo now redraws everything.
- **Test.** New `scripts/ui_approved_e2e.mjs` at 1366, 390 and 320 px: before approval (no mark, the note, `aria-describedby`, the copy says «يجزى»), after it (the box unchanged, «يوفى» drawn above «يجزى» and inside the box, the line above the card, the copy says «يوفى», the note not repeated, the quotation not drawn as a match, the caret announcement), the reference mark, «تراجع» (only that mark goes, the copy reverts), an edit inside the approved quotation (the mark and the decision fall, the quotation is stale, the copy keeps the writer's edit), and the recheck (asked again, nothing drawn) — **66 PASS, 0 FAIL**. On the previous code the approval checks fail at the first width. Its first run failed 6 checks at «تراجع»: that was the redraw defect above.
- `ui_journey_e2e` 167, `ui_e2e` 27, `ui_workspace_e2e` 137, `ui_counts_e2e` 17 — unchanged, 0 failures.

### Defect 4 — ordinary prose «في كل عام» was the first item to decide in a long article

- **Diagnosis.** `LA01` of `eval/articles_long_20261003.json`, source-based path: finding 1, «في كل عام», `detected_by: phrase`, tier «possible», codes `["common"]`, an exact match of التوبة 126 with no marker, cue or reference. The interface opened the first pending item in article order, so a coin-flip phrase led the review ahead of ten concrete decisions, and the headline counted it among «وجدنا ٢٧ اقتباسًا».
- **What the tier holds** (`eval/possible_tier_composition.py`, the two labelled article sets (`articles_frozen`: 5 articles of 434–5,809 characters; `articles_long_20261003`: 10 of 8,060–14,700), `eval/results/possible-tier-20261004-005103.json`): `common` 10 overlapping a gold quotation / 14 not; `approximate` 27 / 5; `non_quran_cue` 4 / 1; both 1 / 1. In `LA01`, five of its seven `common` items are real quotations. **No threshold was changed**: lowering or raising one for «في كل عام» would trade real quotations for one example.
- **Fix (`app/static/app.js`, presentation only).** An unconfirmed item whose codes include `common` and not `approximate` waits behind the concrete decisions: the first card after an audit and «التالي» take the decisions first (in article order), then these phrases. They keep their mark in the text («possible», dotted), their row («يحتاج تأكيدك») in a group of their own, «عبارات للتأكيد: قد تكون اقتباسات», and their card. The headline counts them apart: «وجدنا ٢٠ اقتباسًا؛ تحتاج ١٠ منها إلى قرارك» and «و٧ عبارات تشبه آيات ولم نتأكد أنها اقتباسات، تنتظر تأكيدك»; the panel, the bar and the final review say «١٠ اقتباسات تنتظر قرارك، و٧ عبارات للتأكيد»; the copy note and the print record count them separately. Copying is marked ready when no concrete decision is left (an unconfirmed phrase is never changed without the writer).
- **Frozen sets rerun (fallback, no model):** `cases`, `heldout`, `phrases_frozen`, `articles_frozen`, `articles_long_20261003`, `uthmani_dev`, `uthmani_heldout` — rows, negative hits, formula hits and extra findings **identical** to the recorded runs (`…-recheck-*`, `…-long-20261003-first-run`, `…-gapafter-uthmani-*`); only timings differ. Real unmarked and partial quotations remain detected exactly as before.
- **Test.** New `scripts/ui_possible_order_e2e.mjs` on `LA01` at 1366 and 390: the headline counts 20 quotations and names the 7 phrases apart; the first card is a concrete decision, not «في كل عام»; «في كل عام» is still marked, listed (27 rows in all) and says «يحتاج تأكيدك»; «التالي» visits the ten decisions and none of the phrases, then comes round; once they are decided it goes to the phrases; the panel, the bar and the final review name them; no sideways scroll — **33 PASS, 0 FAIL** (35 after the dash check below was added).
- **An existing expectation changed, on purpose:** `ui_long_e2e` asserted that «التالي» walks *every* waiting item in article order. Its first run after the change failed that check at all three widths (2→3→4→5→9→12→2…, which now skips the phrases while decisions remain); the assertion now covers the concrete decisions, and the phrases' order is checked in `ui_possible_order_e2e`.
- **A keyboard defect the new order exposed, fixed.** The full battery after this change failed `ui_final_qa`'s keyboard journey on `L1` at all three widths: confirming the last phrase («هذه الآية») sends a verse check to the server and disabled the focused button, which drops focus to the page until the answer is drawn (about half a second on this article; longer under load). It had always happened, but earlier in the sequence, where the next card took focus. `requestPhrase` now moves focus to the card itself and marks it `aria-busy` before disabling its buttons. The test now waits for the busy card to be drawn before deciding where to go (it had moved on after a fixed 500 ms); two reruns before that change still failed at 390 px for that timing reason.
- **Two test expectations changed with the wording:** `ui_async_navigation_e2e` looked for «٧ اقتباسات» in the progress line, now checks that the open count fell by one; `ui_long_e2e` counted `.q-group.need li`, which the new group briefly shared (it now has its own class, `maybe`).
- **Also:** dates in the audit details use Arabic-Indic digits like the rest of the page (`ar-u-nu-arab`); a new `scripts/ui_model_notices_e2e.mjs` checks the model wording (below).
- **Limit, stated plainly.** «في كل عام» is still shown as a possible quotation (dotted, «يحتاج تأكيدك»), now after the decisions. It is never presented as a verified quotation and proposes no change; telling such prose from a real short quotation needs better evidence than these sets give (roadmap, Stage 1.2, set C).

### What the page says about the model, in each state (simulated where a model is needed)

- New `scripts/ui_model_notices_e2e.mjs`, at 1366 and 390. The server has **no model configured**, so the unconfigured state is the real server answer; the other states are **simulated** by rewriting `/api/health` and `/api/audit` answers in the browser and are printed «SIMULATED». They test the page's wording and layout only; **they prove nothing about a live Groq call**, and none was made.
- Checked: unconfigured — before sending, «لا نموذج لغوي مهيّأ على هذا الخادم، فلا يُرسَل مقالك عند التدقيق إلى جهة خارجية…» with the privacy link beside the editor; after, one calm line «دون ذكاء اصطناعي: …», no error styling, the record says the model was not used. Over the limit (simulated) — before the audit «أطول من ٦٬٠٠٠ حرف: يُدقَّق كاملًا دون النموذج اللغوي», after it the reason, the record says why the model was not called. Failed, HTTP 429 (simulated) — one line «تعذّر اقتراح الذكاء الاصطناعي هذه المرة… أو أعد التدقيق لاحقًا», the status only inside the closed «تفاصيل هذا التدقيق», no second warning banner, nowhere a claim that the model answered, the review complete, the record says «لا». Answered (simulated) — the details say it proposed places only and added none; answered with nothing (simulated) — said as such. **50 PASS, 0 FAIL.**
- First run: 2 failures, a fault in the test (paragraphs inside a closed `<details>` still have an `offsetParent` in this Chromium; it now uses `checkVisibility()`), not in the page.

### Screens, comparison sheets and a second first-time-writer walkthrough (4 Oct)

- **Screens.** `scripts/ui_screens.mjs` gained today's states (the first piece of a verse and the next one, an approved correction drawn in the box, a long article at its first decision and its phrases to confirm, an edit after an approval). It was run on this branch and, in a temporary worktree, on `main` (`47f224e`), at 1366×860, 390×844 and 320×640: `submission/assets/ui-editorial-2026-10-04/{before-main,after}` (63 images each), 19 comparison sheets in `…/compare/` (git-ignored, local only). States marked `sim-` have a rewritten audit answer; none is a live call and none was taken on Render.
- **Found by looking at them, fixed:** the panel's position marker used a middle dot before an Arabic digit («· ٣ من ٤»), which reads as «٣٠ من ٤» because the Arabic-Indic zero is a dot (visible in the 3 Oct shots too). It is now a dash («— ٣ من ٤»), with a check in `ui_possible_order_e2e`.
- **Walkthrough** (by the coding assistant, not by a writer; 390×844 touch, fresh storage, an article written for it): typed «الأمانة خلق المؤمن. قال تعالى: إن الله يأمركم أن تؤدوا الأمانات», tapped «أدرج» — **«إلى أهلها» was inserted and nothing after it**, the next piece «وإذا حكمتم بين الناس» was offered and dismissed; added a wrong reference [النساء: 85] and a marked misquotation «… وكونوا مع الصادقون﴾ [التوبة: 119]»; audited: «وجدنا اقتباسين؛ يحتاج كلاهما إلى قرارك»; the first card said before approval where «النساء: ٥٨» would appear; approved both; both were drawn above the writer's words in the box; the bar offered «المراجعة الأخيرة» and was gone once the review was on screen; copying gave exactly the two approved changes. No page errors. «وفي كل يوم» was not flagged.
- **Still confusing (recorded, not fixed):** (1) at 320–390 px, when there is no room below the caret, the suggestion box — one line taller now — is placed over the line being typed; its verse line shows those words, but the writer's sentence is covered. (2) The drawn correction can touch the bottom rule of the line above, and for a reference it sits at the reference's start rather than centred over it. (3) On a phone, approving moves to the next card, so the drawn correction is seen only after scrolling back up (the line above the card says where it went). (4) That line is three lines long at 390 px.

### Final gates on this branch (4 Oct, about 01:10–01:50 +03; macOS, Python 3.14.7 venv, Playwright 1.63 and axe-core 4.13 in a scratch `node_modules`; every server with `AI_PROVIDER=none`, no key: no Groq call, no Render call)

- `pytest`: **414 passed** (395 + 19 in `tests/test_suggest_chunks.py`). `node --test tests/revision.test.mjs tests/workspace.test.mjs`: **24 passed**.
- Browser suites, run one after another, **0 failures, 0 skipped**: `ui_journey_e2e` 167, `ui_e2e` 27, `ui_phrase_e2e` 38, `ui_boundary_e2e` 46, `ui_uthmani_e2e` 32, `ui_long_e2e` 91, `ui_async_navigation_e2e` 4, `ui_suggest_e2e` 200, `ui_workspace_e2e` 137, `ui_final_qa` 141 (includes the keyboard-only journeys on the demo and on `L1` at 1366, 390 and 320; it has fewer «التالي» checks than before because fewer decisions leave the same card on screen), `ui_counts_e2e` 17, `ui_dock_e2e` 34, `ui_approved_e2e` 66, `ui_possible_order_e2e` 35, `ui_model_notices_e2e` 50 (unconfigured real; other model states simulated), `ui_a11y_check` **54, axe 0 violations** (18 states × 3 widths; four states added today), `ui_crossbrowser` **87** (Chromium, Firefox and WebKit × desktop and phone; today's piece insertion by Tab and tap, drawn correction and bar added). Total 1,226 checks.
- Against a local AI-off server: `live_smoke.mjs` 21 (desktop) and 21 (`--phone`); `live_workspace.mjs` 35; `scripts/e2e_check.py` 0 failures.
- Frozen sets: every `eval/*.sha256` matches; the seven detection sets rerun with identical rows (above); the suggestion sets rerun and disclosed (`docs/EVALUATION.md`). `git diff 47f224e..HEAD` touches no label file, no fixture and no Quran source code. `git diff --check` clean. The local Groq key, searched for by value, is in neither the diff nor the branch's history.
- One flaky failure seen today and explained: a 317 ms frame gap in `ui_workspace_e2e`'s typing check while another browser script ran at the same time; alone it passed (worst gap under 250 ms).
- **Not tested:** real phones, Safari on iOS, VoiceOver/TalkBack, a live model call, the deployed service with this code, and any session with a real writer.

### Independent diff review and its fixes (4 Oct, about 01:50–02:27)

A separate reviewer agent (no context from this work) read `git diff 47f224e..HEAD` against the product rules. **High: none** (it checked that `_chunk_bounds` only slices `a.words`, the chain never inserts, the textarea is never rewritten, no wording claims a model answer, and no detection threshold changed; it re-ran `test_suggest_chunks.py` + `test_suggest_full.py`, 58 passed). Medium and low findings, all fixed except where stated:

1. **A correction that adds a missing word was never drawn**, though the card promised it (`approvedFixes` dropped zero-length changes; the note then repeated on every card). Insertions are now drawn at their place as «+ رب». `ui_approved_e2e`: «﴿الحمد لله العالمين﴾» → «+ رب» drawn inside the box, copy «الحمد لله رب العالمين».
2. **The headline went stale** after a phrase was dismissed or its verse pinned. `renderAll` and `dismiss` now redraw it. `ui_possible_order_e2e` checks 7 → 6 after a dismissal (its first run after the fix still failed: `dismiss` returned through `goTo` before `renderAll`; fixed in `dismiss` itself).
3. **Focus was still lost when a verse or boundary check failed**: the error paths redrew the card with `focus: false`. They now keep focus on the card if it had it. `ui_async_navigation_e2e` adds a simulated 500 answer.
4. **«التالي» could reopen the same card** (one decision open plus phrases). The panel's «التالي/السابق» are shown only when they lead to another quotation; checked.
5. **The dual in the copy note** («وعبارتان للتأكيد نُسخت كما كتبتَها») → «نُسختا كما كتبتَهما»; checked.
6. **The printed record counted the phrases among «غير محسومة»** and the preview called them «اقتباس لم يُحسم». The record now lists them under their own heading and leaves them out of that count; the preview names them as phrases; checked.
7. **«إليّ», «عليّ», «بيّن» were taken for particles** (the list was compared on folded forms). Now compared on letters; mid-verse pieces ending on a governing particle: 5 of 50,900 (was reported as 31). Suggestion sets rerun (`docs/EVALUATION.md`): summaries identical.
8. **«the two labelled long-article sets»** was wrong: `articles_frozen` holds short articles. The docs now name both sets and their lengths.
9. **A long correction label could be clipped at 320 px** (plausible). Labels are now cut at 24 characters with «…», and the test measures the label itself, not only the word under it. A label can still run past the box edge for a word at the very start of a line; recorded as a remaining limit.
10. **The over-limit notice was repeated in the details as «٦٠٠٠»** (no separator, reads as a zero run). It is no longer repeated, and server notices group four-digit numbers («٦٬٠٠٠»); `ui_model_notices_e2e` now includes the server's own notice (simulated).
11. **The bar's on-screen flag could go stale after a redraw without a scroll** (plausible). `render` and `renderAll` now re-measure it.
12. **Overlapping approved changes**: the box sorted them by start only, the copy by start and end (plausible edge case). Same order now.
- **Gates after these fixes (about 02:10–02:27 +03, same setup, no model or Render call):** `pytest` 415 passed (one new test); `node --test` 24; browser suites 0 failures, 0 skipped — `ui_journey_e2e` 167, `ui_e2e` 27, `ui_phrase_e2e` 38, `ui_boundary_e2e` 46, `ui_uthmani_e2e` 32, `ui_long_e2e` 91, `ui_async_navigation_e2e` 5, `ui_suggest_e2e` 200, `ui_workspace_e2e` 137, `ui_final_qa` 141, `ui_counts_e2e` 17, `ui_dock_e2e` 34, `ui_approved_e2e` 78, `ui_possible_order_e2e` 45, `ui_model_notices_e2e` 52, `ui_a11y_check` 54 (axe 0 violations), `ui_crossbrowser` 87 — 1,251 checks. `git diff --check` clean.

## 4 Oct 2026 — release review of PR #2: the six remaining writer-facing issues (branch `ui-editorial-2026-10`; pre-challenge work before 09:00 Riyadh)

Every server below had `AI_PROVIDER=none` and no key: **no Groq call and no Render call** were made for this section. Starting state, checked at 06:36: PR #2 draft, head `ed6b96b`, base `main` = `origin/main` = live `/api/health` build `47f224e`; tree clean; upload trio hashes equal to `submission/SHA256SUMS.txt`.

### 1. The verse suggestion box could hide the line being typed (phones)

- **Measured first** (a probe over 5 screens × caret near the top, middle and bottom of the screen and in a short article × start of a line or its left edge): at 390×844, 390×450 and 320×640 the box was beside the line in every case; at **320×360 and 320×300** (screens made short the way a phone's keyboard makes them) the 372 px box was taller than the screen and `fit()` scrolled the page by the overflow, pushing the typed line off the top (line at −58 px, box from −20 px).
- **Fix (`suggest-ui.js` `fit()`, `styles.css`).** In order: under the line; over it; under it after scrolling the page only as far as needed while the line stays on screen; the same without the full verse line (`sg-compact`: the words to insert, the reference, «أدرج» and where the piece stops stay); last, the box scrolls inside itself under the line. The phone's bottom bar and the selection bar are kept clear where they really cover the screen, and the box is placed again when the visual viewport resizes (a keyboard opening).
- **Test.** New `scripts/ui_suggest_place_e2e.mjs`: 6 screens × 4 places × 2 line positions, plus two phone screens after an audit with the bottom bar showing: the typed line in sight, no overlap, the gap at most 12 px, «أدرج» on screen, the full verse kept wherever the screen is at least 640 px high, an insertion still works. **Negative control:** the same script on `ed6b96b`'s `suggest-ui.js` fails 16 checks (every 320×360 and 320×300 case).

### 2–4. The approved correction drawn in the box

- **Measured first** (zoomed captures at 1366/390/320 of the demo article and of a three-word correction «ولا تكن في ضيق مما يكيدون» → «ولا تك في ضيق مما يمكرون»): the label (`::before` of the `.fix` span) overlapped the type area of the line above by up to 7 px at 390 and 320; for a correction that wraps onto a second line the label was drawn away from where the change starts and over the line above; nothing in the box said which of the writer's words would change.
- **Fix (`app.js`, `styles.css`).** The box still holds only the writer's text. In the highlight layer under it: the writer's words that change are struck through in the «before» red (only those: a longest common run of words with the replacement keeps «في ضيق مما» unstruck; an addition strikes nothing); the source's text is a real element (`.fix-to`) in a layer under the textarea, so the writer's text is always drawn over it, placed above where the change starts (the right end of its first line), moved inside the box at an edge, never over an earlier label on the same line, and cut with «…» only when wider than the box. While any correction is drawn the editor's line height opens from 2.15 (desktop) / 2.05 (phone) to 2.4 (`.editor.has-fixes`), which is what clears the line above; with none drawn it closes again. Cost, said plainly: while corrections are drawn the writing box is about 12% taller on desktop and 17% on a phone (line height 2.4 against 2.15 and 2.05).
- **Wording.** Before the first approval: «عند الاعتماد يبقى نصّك في المربع ويظهر «يوفى» فوقه، ويُكتب مكانه في النسخة التي تنسخها». After it: «اعتمدتَ «يوفى» مكان «يجزى» (الاقتباس ٣) في النسخة التي تنسخها؛ نصّك في المربع لم يُمحَ» with «تراجع». On the approved card: «اعتمدتَه: يُكتب «يوفى» في النسخة المنسوخة، ونصّك في المربع باقٍ تحته مشطوبًا. للتراجع اضغط زر الاعتماد أعلاه مرة أخرى». The final review lists each approved change with **«تراجع عنه»** (named for screen readers; focus stays in the review on the next change; an undone addition says «لن تُضاف إلى النسخة المنسوخة»). The legend says the same.
- **Test.** `scripts/ui_approved_e2e.mjs` rewritten for the new layer and extended: the struck words, the label above the start of the change, inside the box (all four edges), clear of the line above (gap ≥ 1 px), the line height opening and closing, the final review's «تراجع عنه» (and the undo of it), ten copies of the long correction at every position on the line (at 390 and 320 at least one had to be moved inside the box), two corrections close together never overlapping, focus after undoing the third of twelve, an optional addition undone. **Negative control:** on `ed6b96b` the script fails 10 checks before it stops.

### 5. «Possible» common phrases such as «في كل عام» (presentation only; no detection change)

- Already ordered after the decisions (`aca9616`). What still made them look like decisions: the same amber «يحتاج تأكيدك» badge, the same shading in the text, their group open by default, and a card titled «الاقتباس».
- **Changed:** state «تأكيد اختياري» in a neutral style; no shading in the text (a grey dotted line); the group «عبارات للتأكيد (اختياري): قد تكون اقتباسات» is closed while concrete decisions wait (open if it holds the open card or the writer opened it); the card is titled «العبارة ٣» with «عبارة شائعة توافق لفظ آية، وقد تكون كلامًا عاديًا. أكّدها إن قصدتَ الآية؛ وإن تركتها نُسخت كما كتبتَها»; announcements and the bottom bar say «العبارة» too; the headline says «…؛ تأكيدها اختياري»; the copy note no longer calls them unresolved.
- **Frozen sets rerun before merging** (fallback): the seven detection sets and the two suggestion sets have rows identical to the recorded runs (`docs/EVALUATION.md`, «Later on 4 Oct»). `ui_possible_order_e2e` updated for the new wording and extended (no shading, group closed, card title, group open once decisions are done). **Negative control:** fails 16 checks on `ed6b96b`.

### 6. Checked after the fixes

- The phone's final-review bar (`ui_dock_e2e` 34), the two-decision demo flow (`ui_journey_e2e`, `live_smoke` local), the first verse piece («إلى أهلها», then «وإذا حكمتم بين الناس») — unchanged and passing.
- **Walkthrough by the coding assistant** (not a writer; 1366 keyboard, 390 and 320 touch): typed «الأمانة خلق المؤمن. قال تعالى: إن الله يأمركم أن تؤدوا الأمانات», inserted «إلى أهلها» (next piece offered, dismissed), added «[النساء: 85]» and «… وكونوا مع الصادقون﴾ [التوبة: 119]», audited («وجدنا اقتباسين؛ يحتاج كلاهما إلى قرارك»), approved both, saw «85» and «الصادقون» struck with «النساء: ٥٨» and «الصادقين» above, undid one from the final review (focus stayed there) and approved it again, copied: the clipboard equals the article with exactly those two changes, at all three widths; no page errors. Found on the way and fixed: the copy note said «وما بقي غير محسوم يحتاج مراجعتك» when nothing was left.
- Undo links in the final review and the undo line are 36 px high on phones (24 px elsewhere, the WCAG 2.2 minimum).

### Independent review of this diff (a separate reviewer agent, no context from this work)

No High finding. Medium, all fixed: the undo message of an optional addition said «—» would be copied; focus after «تراجع عنه» went to the first change, not the next; the box reserved the bottom bar's height even where the bar is not over the screen. Low, fixed: labels on one line could overlap; an addition inside a range struck every word; the approved note did not name the button; a width change without a resize did not re-sync the textarea height; «الاقتباس» in announcements for an unconfirmed phrase; the optional group re-closed after each decision; the copy note called optional phrases unresolved; a sentence on `/limitations` had no main clause; a double announcement of the undo; one test no longer checked the label's top edge. Each has a check in the suites above.

### Gates before merging (4 Oct, 07:51–08:12 +03; macOS, Python 3.14.7, Playwright 1.61, axe-core in a scratch `node_modules`; every server with `AI_PROVIDER=none`, no key)

- `pytest` **415 passed**; `node --test tests/revision.test.mjs tests/workspace.test.mjs` **24 passed**; `git diff --check` clean.
- Browser suites, one after another, **0 failures, 0 skipped**: `ui_journey_e2e` 167, `ui_e2e` 27, `ui_phrase_e2e` 38, `ui_boundary_e2e` 46, `ui_uthmani_e2e` 32, `ui_long_e2e` 91, `ui_async_navigation_e2e` 5, `ui_suggest_e2e` 200, `ui_suggest_place_e2e` 80 (new), `ui_workspace_e2e` 137, `ui_final_qa` 141 (keyboard-only journeys at 1366/390/320), `ui_counts_e2e` 17, `ui_dock_e2e` 34, `ui_approved_e2e` 146, `ui_possible_order_e2e` 53, `ui_model_notices_e2e` 52 (unconfigured real; other model states simulated), `ui_a11y_check` 54 (**axe: 0 violations**), `ui_crossbrowser` 87 (Chromium, Firefox, WebKit × desktop and phone). **Total 1,407 checks.**
- Against a local AI-off server: `live_smoke.mjs` 21 (desktop) and 21 (`--phone`), also in `--save-audit`/`--replay` mode (replay: one audit request answered from the file, none reached the server); `live_workspace.mjs` 35; `scripts/e2e_check.py` 0 failures.
- Frozen data: every `eval/*.sha256` matches; `git diff 47f224e..HEAD` touches no label file, fixture or Quran-source code; `pre-challenge-baseline` = `55b7350` locally and on GitHub; detection and suggestion sets rerun with identical rows (above).
- Secrets: the two local keys (`.env`, `.env.local`), searched for by value, are in neither the diff, the working tree nor `git log --all -p`; no `gsk_`/`AIza`/`sk-` pattern anywhere in the history.
- Screens: `scripts/ui_screens.mjs` at 1366/390/320 (now with the suggestion on a 320×360 and 390×450 screen) in `submission/assets/ui-release-2026-10-04/after/` (65 images), with three-way sheets (`main` 47f224e · PR #2 as first reviewed · this release) in `…/compare/` (57). Git-ignored, local.
- **Not tested:** real phones, Safari on iOS, VoiceOver/TalkBack, a live model call (made after the merge, below), and any session with a real writer.

### After the merge (4 Oct 2026, Riyadh time): deployment, live journeys, the one model call, media

- **Merge.** PR #2 marked ready and merged the way PR #1 was: `main` fast-forwarded to the reviewed head `5edfc6e` (`git push origin 5edfc6e:main`, no force) at **08:10:23**; GitHub records PR #2 as merged with that commit. `main` = `origin/main` = `5edfc6e`.
- **Deployment.** `/api/health` read `"build":"5edfc6ea8c29e8994fcfec7e702ccc6d5de07378"`, `status ok`, `mode ai`, `ai_last_call: never_called` at 08:11:03 (about 40 s after the push). The 14 files under `app/static/` (served from `/static/…`) and `/`, `/sources`, `/privacy`, `/limitations` are **byte-identical** to the commit (`cmp`).
- **The one deliberate live audit that could call Groq** (08:11:33–08:11:49, `scripts/live_smoke.mjs <live> --save-audit`, demo article, desktop 1366): audit **HTTP 200**, `mode ai`, `ai.outcome ok`, `responded true`, `http_status 200`, **proposed 4, located 4, discarded 0, added_only 0, also_found 4, overlapped 0**; model 1,120 ms (`ai_last_call.elapsed_ms` 1,114 at 08:11:44); whole audit 8,950 ms server-side (this instance fetched the Quranpedia text during the call); 9.5 s from click to card. Visible notice: one folded line «كيف جرى هذا التدقيق؟ (النموذج والمصدر)»; opened, it says the model proposed four passages, all found in the article, none added. The journey passed every check: «وجدنا ٤ اقتباسات؛ يحتاج اثنان إلى قرارك», both decisions, the final review, and a clipboard equal to the article with exactly «يجزى»→«يوفى» and «الشرح: 6»→«الشرح: 5». One HTTP 200 does not show that the 429s seen earlier are gone.
- **Phone-width live journey** (390×844, touch, `--phone --replay` with the answer saved above): the page, scripts and `/api/health` from the live service; the audit request was answered from the saved file and **not sent to the server**. All checks passed; `ai_last_call` afterwards was still the 08:11:44 call, so no second Groq call was made.
- **No other live audit was made.** `scripts/live_workspace.mjs` was not run live: since `47f224e` every audit of a short article attempts the model, so it would have made more Groq calls.
- **Media (git-ignored `submission/`).** Stills (`submission/build/stills_release.mjs`) and the captions-only video (`submission/build/record_release.mjs`) were taken on the live service with the demonstration audit **replayed** from the 08:11 answer (0 audits sent; said on slide 7 and the video's end card). Take 1 was rejected: the recorder enlarged the page with CSS `zoom`, and inside a CSS-zoomed element the drawn correction (placed from `getBoundingClientRect`) landed a line too low; the app is not affected by browser zoom, and the take was re-recorded at 1024×576 scaled to 1280×720 without CSS zoom. Take 2 was rejected: the caption covered decision 1's buttons for a few seconds before that decision was described, and the end card's last line read ambiguously in RTL. Take 3: 105.0 s, 1280×720, no audio, decoded without error, frames inspected.

## 2026-10-04 (evening, Riyadh) — provider failure harness against a fake Groq (challenge period)

Branch `ai-provider-harness`, code commit `ae32992` (from `main` @ `05e34d5`). Roadmap §1.4. Not merged, not deployed.

**Every result in this section is from a SIMULATED provider.** `tests/fake_groq.py` replaces `httpx` inside the provider module with an `httpx.MockTransport` that answers like Groq (bodies copied from Groq's documented shapes and this project's earlier logs; account id and limits invented) and records every request. **No Groq or Gemini call was made**, no real key was set (the key is the sentinel `gsk_TEST_SENTINEL_…`), and nothing here says how well a real model finds quotations.

Article (in `tests/fake_groq.py`): a bracketed quotation with its reference, a bracketed quotation with a wrong reference, an unmarked distinctive misquotation, a short common phrase (hidden), plus the writer's own prose. With `AI_PROVIDER=none` it gives 3 findings with proposed changes; every scenario must give exactly the same `findings`, `stats`, `phrases`, `candidates_capped` and `source` (36-verse offline fixture, audits through the FastAPI app with `TestClient`).

| Scenario (fake answer) | `mode` / `ai.outcome` (audit 1) | `ai.http_status` | Requests: audit 1 / audit 2 / after cooldown | Notice shown | Cooldown |
|---|---|---|---|---|---|
| 429 RPM, `retry-after: 2` | ai_failed / failed | 429 | 1 / 0 / 1 | failure warning; page line «تعذّر اقتراح الذكاء الاصطناعي هذه المرة…» | 120 s |
| 429 RPD, `retry-after: 864` | ai_failed / failed | 429 | 1 / 0 / 1 | same | 864 s (retry-after honoured; was 120) |
| 429 request too large (TPM 1000) | ai_failed / failed | 429 | 1 / 0 / 1 | same | 120 s |
| ReadTimeout | ai_failed / failed | null | 1 / 0 / 1 | same | 60 s |
| ConnectError | ai_failed / failed | null | 1 / 0 / 1 | same | 60 s |
| 500 / 502 (HTML body) / 503 | ai_failed / failed | 500 / 502 / 503 | 1 / 0 / 1 | same | 60 s |
| 401 invalid key | ai_failed / failed | 401 | 1 / 0 / 1 | same | 300 s |
| 200, malformed JSON | ai_failed / failed | 200 | 1 / 0 / 1 | same | 60 s |
| 200, `finish_reason: length` | ai_failed / failed | 200 | 1 / 0 / 1 | same | 60 s |
| 200, `choices: []` / content null / content "" | ai_failed / failed | 200 | 1 / 0 / 1 | same | 60 s |
| 400 `json_validate_failed`, `failed_generation` echoing the article and an invented verse | ai_failed / failed (`generation_failure` true) | 400 | 1 / 0 / 1 | same | 60 s |
| unexpected client error (RuntimeError quoting article and key) | ai_failed / failed | null | 1 / 0 / 1 | same | 60 s |
| 200 `{"candidates": []}` (answered with nothing) | ai / ok, proposed 0 | 200 | 1 / 1 / – | none (details: «لم يقترح أي مقطع…») | none |
| 200, two spans not in the article | ai / ok, proposed 2, discarded 2, located 0 | 200 | 1 / 1 / – | info «استُبعد مقطعان…» | none |

Audit 2 in every failure row: `mode` reduced, `ai.outcome` **skipped_cooldown**, `http_status` null, `cooldown_seconds` the seconds left, info notice «لم يُسأل الذكاء الاصطناعي في هذا التدقيق لأن استدعاءً سابقًا له تعذّر قبل قليل، ويُسأل من جديد بعد نحو N ث؛ …», no failure warning; `/api/health` still reports the failed call with its status. "After cooldown": the cooldown clock (`app.extraction.status.time`) moved past the cooldown, then one request. 25 sequential plus 12 concurrent audits after a 429: 1 request in total. `/api/health`, the answer and the log records at DEBUG (root, auditor, httpx, httpcore, uvicorn.*, starlette, fastapi) were searched for the key, the article lines, the error-body sentinels, `failed_generation`'s text and the organisation id: none in health or logs; the answer holds the article's own quotations (findings) and the provider's `type/code/message` only. Gemini (not deployed): 429, 401, 500, 400, malformed, blocked, connect error — 1 request, the identical source audit, then 0 requests and `skipped_cooldown`; its 503/timeout retry plan (more than one request by design) is covered only by `tests/test_gemini.py`.

Defects found (the new tests fail on `05e34d5`; checked by running them in a detached worktree of `05e34d5`, 36 of 36 failed there, partly because of the new `cooldown_seconds` field):

1. **A cooldown skip was reported as a failure.** The audit after a 429 said `outcome: failed`, `http_status: 429` (the earlier call's) and the failure warning, though it sent nothing. Fixed: `ProviderCoolingDown` → `skipped_cooldown` as above; the page's line «لم يُسأل النموذج اللغوي هذه المرة لأنه تعذّر قبل قليل. فُحص المقال بالعلامات وبالبحث في المصحف، وقد تفوت عبارة قصيرة بلا علامات؛ حدّدها في المقال لتفحصها.», the wait behind «تفاصيل هذا التدقيق», and the printed record «لا — لم يُسأل groq في هذا التدقيق…». `tests/test_groq.py::test_rate_limit_is_a_visible_fallback_never_an_ai_result` had asserted the old behaviour and was updated.
2. **A traceback in the server log could quote the article.** Starlette re-raises after the app's `Exception` handler; uvicorn then logged «Exception in ASGI application» with the traceback. On `05e34d5`, with a real uvicorn on 127.0.0.1, the log contained `KeyError: 'وهذا أصل في العمل الجماعي المشترك gsk_TEST_SENTINEL_…'`. Fixed: the HTTP middleware answers the error and logs only `unhandled error on <path>: <type>`, which is what `/privacy` already said (its wording was not changed; it was not true before this fix).
3. **An unexpected (non-httpx) error in the provider call gave HTTP 500 and no audit.** Fixed in `groq.py` (one attempt, cooldown) and in `run_audit` (any provider exception: the source audit, a cooldown, the type logged).
4. **`ai.error_body` returned Groq's `failed_generation`** (model text: on `05e34d5` it carried the invented verse) **and the organisation id.** Decision: only `failed_generation_chars` is kept; `org_…`/`gsk_…`-shaped ids are redacted. Rationale in the docstring of `tests/test_provider_failures.py`. The provider's message (e.g. «Rate limit reached … RPM …») still goes back to the requester only.
5. **429 `retry-after` ignored** (a daily limit was retried every 120 s); now `max(cooldown, 120, retry-after)`, capped at 3,600 s.
6. **Gemini** started no cooldown after 4xx/5xx, malformed or blocked answers (every audit asked again); now it does.

Commands and counts (all local, `AI_PROVIDER=none` servers for the browser):

- `.venv/bin/python -m pytest -q` → **451 passed** (415 before; 36 new in `tests/test_provider_failures.py`).
- `node --test tests/*.test.mjs` → 24 pass, 0 fail.
- `node scripts/ui_model_notices_e2e.mjs` → all checks passed, **78 PASS** (new: SIMULATED timeout and SIMULATED cooldown states, desktop and phone; the cooldown line is 173 rendered characters with its summary).
- `node scripts/ui_journey_e2e.mjs` → 167 PASS, 0 FAIL. `node scripts/ui_a11y_check.mjs` → 54 PASS, 0 FAIL.
- `scripts/live_smoke.mjs` and `scripts/live_workspace.mjs` learned the `skipped_cooldown` state; **neither was run** (they would call the live model).

Not done / open: **concurrent first calls are not single-flighted.** In a local probe (not committed), 8 audits sent at the same moment, before the first 429 arrived, made 8 requests; the cooldown only stops audits that start after a failure has been recorded. Bounded by the per-address limit (10/min) and the number of simultaneous writers; a one-in-flight guard was not added because it would leave a second simultaneous writer without the model. The cooldown is per process (per instance), not shared. No live probe was made.
## 2026-10-04 (evening, Riyadh) — hard quotations: retrieval anchored on the writer's cues (challenge period)

Branch `hard-quotations` (from `main` @ `05e34d5`; code `365b78d`, `b8d866b`). **Commit ids:** the branch was later rebased onto `d65befa` (the provider-harness release): `365b78d` → `b473e22`, `e296825` → `c2dc304`, `b8d866b` → `9c4acf3`, `08401bc` → `c217422`. The detection files and the evaluation files are byte-identical across the rebase (`git diff 08401bc c217422 -- app/cues.py app/phrases.py app/verifier.py app/extraction/marked.py eval/` is empty); the pre-rebase commits are kept on the pushed branch `hard-quotations-pre-rebase`. Fallback only: **no Groq call** was made for this work.
Write-up, tables and disclosure of what was tuned on what: `docs/EVALUATION.md`, section «Hard quotations».

- **Baseline first.** The seven frozen detection sets rerun on the unchanged `05e34d5` (`eval/results/fallback-20261004-1951*-challenge-baseline-05e34d5-*`):
  rows identical to the 4 Oct release runs (`eval/compare_runs.py`, new: compares two result files row by row, timings ignored).
- **Diagnostic set** `eval/hard_quotes_{dev,heldout}_20261004.json` (assistant-authored development data, frozen by SHA-256 in `e296825`;
  the validator prints `labels OK`). New scorer `eval/run_hard_quotes.py` (recall, false possibilities, wrong «matched», correction safety
  before and after a simulated confirmation, reported apart).
- **Held-out split: one run**, `eval/results/hard-20261004-202752-…-heldout-only-run-b8d866b.json`; the same split on `05e34d5` for comparison
  (`…-heldout-baseline-05e34d5.json`). Dev runs kept: `…-baseline-05e34d5`, `…-cue-v4` (before the bracket fix), `…-final-b8d866b`.
- **Seven sets after** (`…-cue-final-*`): 0 misquotations «matched», 0 wrong fixes, 0 new fixes on correct text, 0 new false suggestions,
  on every set; long set detected 186 → 188, right fixes 29 → 49; 71 changed rows in all, listed by `compare_runs.py`.
- **pytest** 431 passed (415 + 16 in `tests/test_cues.py`; `test_ai_overlap` gained the new method in its priority table; one model-only
  grading test now also switches the cue retrieval off, since its premise is "the source search found nothing").
- **Browser suites** (local AI-off servers, code `365b78d` plus the later changes in progress — rerun on the release head below): ui_e2e 27,
  ui_journey_e2e 167, ui_final_qa 141 (the same 141 checks on `05e34d5`), ui_phrase_e2e 38, ui_boundary_e2e 46, ui_long_e2e 91,
  ui_counts_e2e 17, ui_approved_e2e 146, ui_uthmani_e2e 32, ui_workspace_e2e 137, ui_suggest_e2e 200, ui_suggest_place_e2e 80, ui_dock_e2e 34,
  ui_async_navigation_e2e 5, ui_model_notices_e2e 52, ui_a11y_check 54, ui_crossbrowser 87 — 0 failures.
  **ui_possible_order_e2e: 15 failures**, all pinned counts of `LA01` (20 quotations and 7 optional phrases): the retrieval now reads two of
  those phrases («أفلا يتدبرون القرآن», «واتقوا الله ويعلمكم الله») as quotations the writer announced, so LA01 has 22 and 5. The expected
  numbers were updated with a comment; the behaviour the script tests (optional phrases after the decisions, «في كل عام» first and optional)
  is unchanged.
- **Demo samples:** one finding changes tier (a lead-in quotation, «candidate» → «stated»); nothing else.
## 2026-10-04 (evening, Riyadh) — Stage 4 code-level gates: self-hosted fonts, CSP and headers, body cap, log scrubbing, monitor fields, load test (challenge period)

Branch `hardening` from `main` @ `05e34d5`; commits `efbca20` (fonts, CSP, headers, body cap), `e6bcd46` (log scrubbing), `240e78a` (monitor fields) and a docs/load-test commit. Not reviewed, not merged, not deployed. macOS (Apple M2, 8 cores), Python 3.14.7 (Render uses 3.12), Playwright 1.63, axe-core 4.13. Every server was local with `AI_PROVIDER=none` and no key. **No model call and no request to the live service were made.**

### 1. Self-hosted fonts

- Files: the Arabic and Latin WOFF2 subsets that `fonts.googleapis.com/css2?family=Amiri+Quran&family=Noto+Naskh+Arabic:wght@400;500;600&family=Readex+Pro:wght@300;400;500;600;700&display=swap` gives a Chrome user agent, fetched once from `fonts.gstatic.com` at 19:51: Amiri Quran v19 (45,688 + 12,264 bytes), Noto Naskh Arabic v44, variable 400–700 (93,960 + 19,732), Readex Pro v27, variable 160–700 (22,764 + 31,392). **225,800 bytes in all**, the same six files the browser fetched from Google before, plus Google's stylesheet (26,705 bytes, now gone); `styles.css` grows by 2,488 bytes of `@font-face` rules (`font-display: swap`, Google's Arabic and Latin `unicode-range`s).
- Coverage checked with fontTools: every one of the 55 characters at or above U+0600 in the cached Quranpedia Hafs text is in the Amiri Quran and Noto Naskh Arabic files (U+FEFF falls in the Latin subset's range); ﴾ ﴿ and Arabic-Indic digits are in all three.
- Licences (read 4 Oct 2026, 19:52): `license: "OFL"` in `github.com/google/fonts` `ofl/{amiriquran,notonaskharabic,readexpro}/METADATA.pb`; the `OFL.txt` beside each (copied into `app/static/fonts/<font>/OFL.txt`); GitHub's licence API reports `OFL-1.1` for `aliftype/amiri`, `notofonts/arabic` and `ThomasJockin/readexpro`. Readex Pro's OFL reserves the name «RevReading Lexend», which is not used.
- `node scripts/ui_selfhost_e2e.mjs` (new; Chromium, 1366×900 and 390×844): load → demo article (audits) → approve both changes → copy → `/sources`, `/privacy`, `/limitations`. **45 PASS, 0 FAIL.** Per width: 55 requests, all to the local origin, 0 to another host; 0 CSP violations; all three families `status loaded` with `document.fonts.check` true for Arabic text; the six font files fetched from `/static/fonts/` (225,800 bytes); on each trust page the first Tab shows the skip link and the next focus has a 3 px solid outline. A control in a separate, uncounted context shows the listener works: an injected `<style>`, a `style` attribute in markup and a `fonts.gstatic.com` font are each refused and reported (`style-src-elem`, `style-src-attr`, `font-src`), while `element.style` (CSSOM, which the app uses) is not. Screenshots at both widths were looked at (scratch directory, not committed): the interface in Readex Pro, the article in Noto Naskh Arabic, source words in Amiri Quran.

### 2. CSP and headers

Final policy, on every response (API, pages, `/static/*`, 404, 413, 422, and the 500 answer, which is sent outside the middleware and so carries the headers itself):

`default-src 'self'; script-src 'self'; style-src 'self'; font-src 'self'; img-src 'self' data:; connect-src 'self'; worker-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'`

plus `Permissions-Policy: camera=(), microphone=(), geolocation=()`, `Cross-Origin-Opener-Policy: same-origin`, `Cross-Origin-Resource-Policy: same-origin`, the existing `nosniff` / `no-referrer` / `DENY`, and `Strict-Transport-Security: max-age=31536000` only when the request came over HTTPS (`x-forwarded-proto: https` from Render's proxy, or an https scheme). No page has a `<style>` block or `style` attribute; the JavaScript sets styles only through CSSOM. `_ui_common.mjs` now listens for `securitypolicyviolation` and for any request to another host on every page every suite opens, and `finish()` fails the suite if either count is not 0 (`ui_crossbrowser` does the same in Firefox and WebKit).

### 3. Bounded requests

- The old middleware checked `Content-Length` only; a chunked POST had none and was not capped. Now a pure ASGI middleware counts the body as it arrives and answers 413 once it passes `MAX_BODY_BYTES` (80,024 bytes); a body under the cap is buffered and replayed to the app. Tested with a generator body (httpx sends `Transfer-Encoding: chunked`, no `Content-Length`) on `/api/audit`, `/api/phrase` and `/api/suggest`, and in a real uvicorn process.
- Bounds confirmed: `others` ≤ 200 pairs, `surah` 1–114, `finding_id` ≤ 10,000, `before` ≤ 800 and `after` ≤ 120 characters (422 beyond). JSON nested 40,000 deep, a 30,000-digit integer, `1e400`, ±1e308 offsets, a lone surrogate and invalid UTF-8 all give 4xx, never 500, on all three POST endpoints.

### 4. Article text in logs

`app/logging_safety.py` replaces any run of more than 20 Arabic letters in a log record (message, arguments, traceback, stack; percent- or plus-encoded text decoded first) with `[Arabic text removed: N letters]`, as a log-record factory and as a filter on the root and uvicorn handlers. uvicorn's access log writes method, path, status and client address, never a body. **What the real-process test found before the fix:** article text put in a query string (`/?q=…`) reached uvicorn's access log percent-encoded, and the traceback uvicorn logs after an unhandled exception would carry any text in the exception message. Both are now scrubbed. `tests/test_log_safety.py`: the scrubber, uvicorn's access formatter, tracebacks, `caplog` over an audit / validation error / 413 / unhandled exception, and a real uvicorn process whose combined log is searched for a sentinel article (absent, also percent-encoded) while the access lines and the error type are present.

### 5. Monitor fields

`/api/health` adds `source_ok` (loaded and not stale; `?deep=1` loads the text first, at most one Quranpedia request per 24 h or per failure back-off; without `deep` nothing is fetched) and `ai_recent` (`calls`, `ok`, `failed`, `rate_limited`, `since`; counted in `CallTracker.record`, so provider code is unchanged; cooldown skips are not counted; `null` with no model). The keywords documented in `docs/RENDER_DEPLOY.md` (`"source_ok":true`, `"http_status":429`) are tested against the raw JSON. **No uptime service was signed up for and no alert was fired**; that remains the Stage 4 evidence to record.

### 6. Load test (LOCAL numbers: this laptop, Python 3.14.7; not Render)

`python scripts/load_test.py` starts its own AI-off server (rate limit raised for the run) and posts the ten long evaluation articles cut to 5,994–5,999 characters (10–20 findings each). The script refuses `onrender.com`, any other non-local URL without `--allow-remote`, and any server with a model configured. 20:11–20:12:

| Run | Requests | Errors | p50 | p95 | max | wall per round |
|---|---|---|---|---|---|---|
| `--k 1 --rounds 10` (sequential) | 10 | 0 | 0.337 s | 0.496 s | 0.496 s | 0.31–0.50 s |
| `--k 10 --rounds 3` (1 process) | 30 | 0 | 3.428 s | 3.571 s | 3.574 s | 3.40–3.58 s |
| `--k 10 --rounds 3 --workers 2` (experiment) | 30 | 0 | 2.639 s | 3.625 s | 3.645 s | 2.64–3.65 s |
| `--k 10 --rounds 3 --workers 4` (experiment) | 30 | 0 | 1.989 s | 3.369 s | 3.425 s | 2.20–3.43 s |

Observed: the routes are synchronous and run in the threadpool, and the audit is CPU-bound Python, so under the GIL ten concurrent audits are served together in about ten times one audit's time; every request finishes near the end of the round (p50 ≈ p95 ≈ 10 × 0.34 s). Several uvicorn worker processes help only partly here (the first rounds include each process loading its own Quran index, and macOS spreads connections unevenly), so the experiment is **not** a measurement of the fix. Proposal, not implemented: on a paid instance with several CPUs, measure `uvicorn --workers N` there (each process holds its own index, about 94 MB, and its own rate limiter and counters) or run `run_audit` in a process pool. Render Free's shared CPU is slower than this laptop; the Stage 4 gate (p95 of 10 concurrent 6,000-character audits on the chosen instance) is still open.

### 7. Accessibility

`ui_a11y_check` covers the three trust pages at 320, 390 and 1366 px: 0 violations (56 PASS). All four pages have `lang="ar" dir="rtl"` (also a pytest), a skip link, and a 3 px focus outline (checked by keyboard in `ui_selfhost_e2e`). No fix was needed. Real devices, VoiceOver and TalkBack: not tested.

### 8. Dependency audit

`pip-audit` 2.10.1 in a scratch venv (not the project's), 20:04: `pip-audit -r requirements.txt` → "No known vulnerabilities found"; `-r requirements-dev.txt` → same, with the PyPI service and with `--vulnerability-service osv`. No version changed.

### Gates on the branch

- `pytest` **458 passed** (415 before; +29 `test_security_headers`, +7 `test_log_safety`, +7 `test_health_monitor`); also 444 at `efbca20` and 451 at `e6bcd46`. `node --test tests/*.test.mjs` **24 passed**. `git diff --check` clean. Every `eval/*.sha256` matches; no eval file touched.
- Browser suites, each with its own AI-off server, 0 FAIL, 0 SKIP (counts include the two new CSP / other-host checks where the suite calls `finish()`): `ui_journey_e2e` 169, `ui_final_qa` 143, `ui_a11y_check` 56, `ui_workspace_e2e` 139, `ui_crossbrowser` 89 (Chromium, Firefox, WebKit; desktop and phone), `ui_suggest_e2e` 202, `ui_selfhost_e2e` 45; and the other suites, since every page they open is now watched: `ui_e2e` 29, `ui_phrase_e2e` 38, `ui_boundary_e2e` 48, `ui_uthmani_e2e` 34, `ui_long_e2e` 93, `ui_async_navigation_e2e` 7, `ui_approved_e2e` 148, `ui_counts_e2e` 19, `ui_dock_e2e` 36, `ui_model_notices_e2e` 54, `ui_possible_order_e2e` 55, `ui_suggest_place_e2e` 82. Run 19:58–20:20 (Riyadh).

### Not done / still open

Own domain and TLS (HSTS is only sent over HTTPS, so it takes effect on Render's HTTPS today, not on a domain of our own); a paid always-on host and the load test on it; signing up an external monitor and firing one alert; an error-reporting service; zero data retention at the model provider; real-device accessibility review. The live service still runs `main` with Google Fonts until this branch is reviewed and released.
## 2026-10-04 (evening, Riyadh) — importing an article from a file (challenge period)

Commit `8106cd0` on branch `import-text` (from `main` @ `05e34d5`); not merged, not deployed. Roadmap §3.1, first part: **TXT and DOCX only. PDF is left out**: pdf.js (Apache-2.0) is large, and it could not be vendored, pinned, reviewed, run in a worker under the page's CSP and tested properly tonight. A PDF is recognised by its first bytes and refused with «ملفات PDF غير مدعومة بعد…».

### What was built

- `app/static/import.js` (no third-party code): magic-byte sniffing; TXT by `TextDecoder` with `fatal: true` (UTF-8, or UTF-16 with a BOM; anything else is refused, Windows-1256 included, with a binary/encoding distinction by the share of control bytes); DOCX by reading the ZIP central directory by hand, inflating only `[Content_Types].xml`, `word/document.xml`, `word/footnotes.xml`, `word/endnotes.xml` with `DecompressionStream('deflate-raw')` fed in 2 KB pieces and stopped as soon as a part gives more than it declared, then a CRC-32 and size check; WordprocessingML read by a small scanner (DOMParser does not exist in workers; a DOCTYPE is refused, only the five XML entities and character references are expanded). The same file is the Web Worker (`new Worker("/static/import.js")`, allowed by the existing `script-src 'self'`; no CSP change, no blob: worker) and the module loaded by the Node tests.
- `app/static/app.js` / `index.html` / `styles.css`: one outlined button «استورد نصًّا من ملف» with a one-line hint in the row under the editor (beside «أمثلة أخرى»); its messages and the replace / cancel question appear under it; the worker is created when the button is first pressed (before the chooser opens) and terminated after 10 s; on success the text goes in through the same `setEditorText` as a sample, the notice goes in the sheet's status line and the editor gets the focus (caret at the start). No audit, no suggestion request (the editor's `input` event is not fired).
- Decisions: **long text** — refused whole with the count («في الملف ٢٠٬٠٠١ حرف، وحدّ المقال ٢٠٬٠٠٠ حرف. لم يُدرَج شيء…»), never cut (a cut could fall inside a verse); **footnotes / endnotes** — listed after a `__________` line as «(1) …» in the order the text refers to them, reference marks removed from the body (so no digit is glued to a word), a note whose reference was deleted (tracked) not listed; **tracked changes** — accepted (w:del, w:moveFrom, deleted paragraph marks out; w:ins, w:moveTo in) and said in the notice; **presentation forms** — U+FB50–FDFF and U+FE70–FEFE replaced by their NFKC letters only when those are Arabic letters or marks (the space NFKC puts before an isolated mark is dropped); ﴾ ﴿ (U+FD3E/F) and U+FDF0–FDFF (ﷲ ﷺ ﷻ ﷽ …) kept; counted and said in the notice; **kept as written**: diacritics, tatweel, «», bidi marks, ZWNJ/ZWJ, tabs in TXT (a DOCX tab becomes a space); every U+FEFF removed; blank lines before the first line and white space after the last dropped. Hidden text (w:vanish) is read like any other; headers, footers, comments are not read.

### Fixtures (`tests/fixtures/import/fixtures.mjs`; every one through `node --test` and through the page)

| Fixture | Expected |
|---|---|
| `txt-arabic` (diacritics, ﴿﴾, «», tatweel, RLM) | text, unchanged |
| `txt-bom-crlf` | text; BOM 1, CRLF 4 counted |
| `txt-controls` (BEL, ESC, NEL) | text; 3 controls removed and counted |
| `txt-utf16` (UTF-16LE with BOM) | text |
| `txt-presentation`, `docx-presentation` | «قال تعالى: ﴿إن الله مع الصابرين﴾ لا ﷺ»; 25 forms replaced, ﴿﴾ and ﷺ kept |
| `txt-1256` | refused `not_utf8` |
| `txt-nul`, `gzip-renamed` | refused `binary` |
| `png-renamed` (.txt) | refused `image` |
| `zip-renamed` (.txt), `zip-no-document` | refused `zip_not_docx` |
| `pdf` | refused `pdf` |
| `txt-20000` / `txt-20001` | text / refused `too_long` |
| `txt-empty` / `txt-blank` | refused `empty` / `no_text` |
| `docx-quran` (runs split inside a word, tab, line break, tab stops, table, hyperlink, PAGE field, text box written twice in mc:Choice/mc:Fallback, w:sym, entities) | text; field code and fallback copy not read |
| `docx-tracked` (w:del/w:ins, deleted paragraph mark, moveFrom/moveTo, pPrChange) | the accepted text; tracked = true |
| `docx-footnotes` (two footnotes, one endnote, one deleted reference, separators) | body without digits + 3 notes after the rule |
| `docx-selfclosing` (self-closing children inside skipped elements: VML shapetype in the fallback, run properties in moveFrom/del, a deleted footnote reference, an empty `<w:pPr/>`, a moved paragraph mark) | text with nothing leaked back (added after the review below) |
| `docx-stored` (method 0) | text |
| `docx-corrupt`, `docx-truncated`, `docx-bad-crc`, `docx-doctype` (entity expansion attempt) | refused `corrupt` |
| `docx-encrypted-entry` (flag bit 0), `ole-encrypted` (CFB with `EncryptedPackage`) | refused `encrypted` |
| `ole-doc` (CFB without it) | refused `doc_old` |
| `docm` (vbaProject.bin), `docm-type` (macroEnabled content type) | refused `macro` |
| `zip-bomb` (50 MB of zeros deflated to ~50 KB, honest sizes) | refused `unzipped_too_big` before inflating |
| `zip-bomb-lying` (same data, declares 900 KB) | stopped after 900 KB of output → `corrupt` |
| `lo-article.docx` (LibreOffice 26.x from `office/lo-article.fodt`: tracked deletion + insertion, footnote, tab, line break, empty paragraph) | the accepted text + 1 note |
| `textutil-article.docx` (macOS `textutil` from `office/textutil-article.html`) | text |

The two office files are 6 KB and 4 KB, made by us from our own text with `tests/fixtures/import/office/make.sh`. **Simulated, not real:** the encrypted Office file is a synthetic Compound File header with the stream name, not a file encrypted by Word (LibreOffice's command line wrote an unencrypted file when asked for a password); no DOCX written by Microsoft Word itself and no writer's real file was tested.

### Results (4 Oct, 19:50–20:41 +03; final gate 20:28–20:41; macOS, Node 24.16, Python 3.14.7, Playwright 1.63; every server `AI_PROVIDER=none`, no key; no model call)

- `node --test tests/*.test.mjs` **70 passed** (import 46: one per fixture + 11 others — zip bomb time and memory, no Quran correction, kept characters, presentation forms, line ends, the page's limit, 5 MB, declared ratio, the notice, no digit in the body, linear trim). The zip bomb is refused in under 120 ms; the lying one in about 3 ms with array buffers growing by under 20 MB.
- `pytest -q` **415 passed**.
- `scripts/ui_import_e2e.mjs`: **589 PASS, 0 FAIL in each of Chromium, Firefox and WebKit** (run one after another). Per width (1366, 390, 320): Tab (Option+Tab in WebKit on macOS) reaches the button, Enter and Space open the chooser; every fixture through the real file input (`setInputFiles`), the editor's text equal to the expected text code point for code point, the notice and its parts, or the refusal message with «لم يتغيّر شيء في المحرر.» and an unchanged editor; no audit; axe 0 violations after an import, with a refusal shown and with the replace question open; the question (focus on it, Escape cancels and returns focus, Tab → «استبدل النص» → Enter replaces, wording when an audit exists, the audit result cleared, no new audit); no sideways scroll; no console error. Time limit: a worker that never answers (served by a test route) is stopped after 10.05–10.93 s (limit 10 s) and the next import works.
- **Network during import:** every request from `setInputFiles` until the text is in the editor, and for 1.5 s after (1.2 s for each fixture), is recorded: **no network request in any browser**. The worker's script is fetched once when the button is first pressed, before a file is chosen, and is checked separately. WebKit reports the worker's own read of the File as a `blob:` "request"; it is listed apart (it is the browser's memory, not the network). axe itself fetches the page's Google Fonts stylesheet (blocked by `connect-src`), so its runs are excluded from those windows.
- Existing suites after the change, one after another, 0 failures, 0 skipped: `ui_journey_e2e` 167, `ui_final_qa` 141, `ui_a11y_check` 54, `ui_workspace_e2e` 137, `ui_crossbrowser` 87.
- One flaky run: with the three browsers' import runs started **at the same time**, Chromium once timed out waiting for the file chooser (5 s); it passed alone twice and in the sequential run above (the wait is now 10 s).

### Independent review of the diff (a separate reviewer agent, read-only)

- **High, fixed:** inside a skipped element a self-closing child closed the skip one level early, so ordinary Word XML (`<w:rPr><w:rFonts/>…`, the VML `<v:shapetype>` of a text box's fallback copy) leaked moved-away text, deleted tabs and line breaks, a second copy of a text box and a deleted footnote back into the text. Every opened element now counts one level; fixture `docx-selfclosing` fails on the old code and passes now.
- **Low, fixed:** a quadratic `/\s+$/` trim (a file of ~160 KB of spaces reached the time limit) → `trimEnd()`; a late answer of an audit started before an import cleared the import notice → it is restored; a paragraph mark moved away (`w:moveFrom` in its properties) now runs on like a deleted one; «مسح» closes an open replace question.
- **Low, not changed:** hidden text is read (said on `/limitations`); the question stays open if the writer edits the editor meanwhile (its wording stays true).
- No finding on memory (a 4.9 MB DOCX with ~12 MB of text: refused as too long in 390 ms, ~32 MB peak), regex backtracking (linear), entities, or any path to `innerHTML` or the network.

### Not done

PDF (any kind); OCR; drag and drop; files from Microsoft Word itself, from real writers, or encrypted by Word; real phones, Safari, screen readers.

## 2026-10-04 (21:5x Riyadh) — an ayah number written as a word is read as a reference (challenge period)

Branch `reference-ordinals`. Found in the internal inspection of the pilot tasks (see the section of that name): in `LA03` the writer
cites «وهي الآية الخامسة عشرة من سورة النور», and `app/references.py` read only digits. New pattern: «الآية/آية» + a feminine ordinal
1–99 written in words (الأولى … العاشرة، الحادية عشرة … التاسعة عشرة، العشرون … التاسعة والتسعون) + «من/في سورة» + a surah name. Required
context keeps prose out («الحالة الخامسة عشرة من سورة حياته», «الآية الخامسة من كتاب الأدب» give nothing; tested). An ordinal beyond the
surah's length is a reference with a problem (tested). No AI call.

- pytest 511 (one new test in `tests/test_references.py`).
- Seven frozen sets, compared with the release runs `…-cue-final-*` (`eval/results/fallback-*-ordinals-*`): six identical; `articles_long_20261003`
  **one row**: `LA03` «وتحسبونه هينا وهو عند الله عظيم» reference «missing» → «matched» (the label's expectation), tier «candidate» → «stated»
  (the writer's ayah reference names the verse). This change was made after seeing that article in a walkthrough, so the row is not independent
  evidence. Hard dev split: rows identical. The held-out split was not rerun.
## 2026-10-04 (evening, Riyadh) — writer pilot kit and OCR benchmark harness (challenge period)

Branch `pilot-ocr-docs` from `main` @ `05e34d5`; not merged, not deployed. No change under `app/`, no frozen set or `.sha256` touched, no model call, no network call by any new script.

- **What was added.** `docs/WRITER_PILOT.md` (+ `docs/WRITER_PILOT_SHEET.csv`, `.github/ISSUE_TEMPLATE/pilot_observation.md`); `eval/ocr/README.md`, `eval/ocr/manifest.schema.json`, `eval/ocr/score_ocr.py`, `eval/ocr/run_tesseract.py`; `tests/test_ocr_score.py`; `docs/OCR_DECISION.md`.
- **Pilot: not run.** No participant was recruited or contacted and no message was sent. To write the task cards, the coding assistant opened the app once on a local AI-off server (`AI_PROVIDER=none`, Playwright, Chromium 1366 px): typed «قال تعالى: ﴿إن الله مع» (no suggestion: an opening shared by many verses, as `/limitations` says) and ran the demonstration article to read the card labels. **This is not a pilot result** (WRITER_PILOT.md §1) and found no bug. The consent script's data paragraph was matched by hand to `app/static/privacy.html` as of 4 Oct 2026.
- **OCR: nothing measured.** `which tesseract` → not found; `run_tesseract.py` was therefore not run on any image (its missing-Tesseract exit is unit-tested with a patched `shutil.which`). No cloud engine was called. Prices: Azure's pricing page (read 4 Oct 2026) showed the free tier "0 - 500 pages free per month" and no paid figure ("$-"); Google's Document AI pricing page could not be read (truncated). Recorded in `docs/OCR_DECISION.md`.
- **Synthetic smoke of the scorer (local, not a benchmark):** `eval/ocr/score_ocr.py` on one page made of `app/static/samples/sample-1.txt` ×3 (1,950 characters, 307 words) against a copy with ~8% of words truncated by a script; it ran in 0.6 s, built a 14,672-form word list from the local Quranpedia cache plus that text, and reported plausible rates (letters WER 0.061). Files in the session scratchpad only.
- **Tests (20:01 +03, macOS, Python 3.14.7):** `pytest -q` **433 passed** (415 before + 18 new in `tests/test_ocr_score.py`); `node --test tests/*.test.mjs` **24 passed**; `git diff --check` clean; every `eval/*.sha256` verifies. Browser suites were not rerun (no file they load changed).
- **Not done:** any session with a real writer; any OCR page, ground truth or engine run; confirmation of the proposed OCR thresholds by a reviewer.

## 2026-10-04 (21:2x Riyadh) — internal inspection of the pilot tasks (challenge period; NOT a user study)

**What this is.** The assistant (Claude) ran the seven tasks of `docs/WRITER_PILOT.md` with a script (`scripts/walkthrough_shots.mjs`)
on the integrated code of branch `import-text` (main `aee587c` + file import), on a local AI-off server, at 1366×900 and 390×844, and looked
at every screenshot. It is an internal inspection by the builder's assistant. It is **not** pilot evidence, has no participant, and does
not count towards the "Interface sign-off" gate. **Not tested with users.**

| Task | What happened | Observation |
|---|---|---|
| 1 Start an article | typed text sits in «مقالك»; the counter shows `٦٣ / ٢٠٬٠٠٠ حرف` | — |
| 2 Insert a verse suggestion | after «قال تعالى: إن مع العسر» the box offered «يسرا» (الشرح: 6) with the verse line; Tab inserted it | the box sits below the typed line, does not cover it |
| 3 Audit a long article (LA03, 14,700 characters) | first decision card 0.8 s after «دقّق الاقتباسات» (local; the free host took 25.7 s for the same article, cold source, measured live today); «وجدنا ٢١ اقتباسًا؛ يحتاج ١١ منها إلى قرارك» | — |
| 4 Settle an uncertain quotation | a boundary card for «وتحسبونه هينا وهو عند الله عظيم» asks whether «منه» belongs to the quotation (the verse has «علم» there) | **finding:** the article gives the reference in words, «وهي الآية الخامسة عشرة من سورة النور», which the reference parser did not read (only digits), so that reference did not help; **fixed later the same evening** (PR #8, `4cd0746`: ordinals 1–99 before «من/في سورة …») |
| 5 Approve, then undo | «يجزى → يوفى» approved: struck word and source word drawn, undo line «اعتمدتَ «يوفى» مكان «يجزى» … تراجع»; undo restored it | a card that proposes a fix also shows the amber line «مطابقة تقريبية: الموضع المقترح يحتاج إلى تأكيد بشري» — a writer may read it as the tool doubting its own proposal; a question for the pilot, not changed |
| 6 Final review | «سيُنسخ مقالك بعد تغيير واحد اعتمدتَه», the change in its sentence with «تراجع عنه», one item still pending, the "not a certificate" line | — |
| 7 Copy | the clipboard held the article with «يوفى» (402 characters) | — |

No defect that blocks a task was found; the reference-in-words gap was fixed (PR #8).

## 2026-10-04 (evening, Riyadh) — real Groq calls tonight: ledger (challenge period)

Every call below went to Groq (`qwen/qwen3.8-27b`) from this laptop through the project's code, except the two live probes, which the
deployed service made. Raw answers, timings, usage and rate-limit headers are in a private evidence folder outside the repository; only
aggregates are published (`docs/EVALUATION.md`, «The model's measured contribution and failures»).

| What | When | Calls | Outcome |
|---|---|---|---|
| Extraction answers for the paired replay (`eval/ai_record.py`, 800 tokens reserved, 65 s apart) | 19:54–21:16 | 76 | 75 × 200; 1 × 400 `json_validate_failed` (phrases_frozen f41) |
| Live probe on `aee587c` (`scripts/live_smoke.mjs --save-audit`, one audit) | 21:17:12 | 1 | 429 OTPM «Requested 1556» (a local call < 1 min earlier) |
| Triage prototype, run 1 (300 tokens reserved) | 21:17–21:29 | 12 | 12 × 200 |
| Live probe on `91568af` | 21:33:40 | 1 | 429 OTPM «Requested 2834» (no local call in the previous 4 min) |
| Triage prototype, run 2 (rule unchanged) | 21:35–22:43 | 64 | 64 × 200 |
| Extraction answers for the two hard-quotation sets, part 1 | 22:44–22:56 | 12 | see the hard-set entry |
| Live probe on `bee3e03` (after PR #10: default reservation 800; recorder paused, 100 s with no call) | 22:57:59 | 1 | **200**, 920 ms, proposed 4 / located 4 / discarded 0, added_only 0, also_found 4; journey 22 PASS |
| Extraction answers for the two hard-quotation sets, part 2 (resumed; recorded articles are not sent again) | 23:00–00:53 | 107 | 99 × 200; 4 × 400 `json_validate_failed`; 3 timeouts and 1 connection failure (00:33–00:52) |
| Pacing experiment (two calls through the production adapter, 800 reserved, 20 s apart, after 4 min with no call) | 00:57:05, 00:57:26 | 2 | **200, 200** (4 proposals each, 910 tokens each). A second request inside a minute is **not** refused at 800, so the one-request-a-minute guard prepared on branch `groq-pacing` (local, never pushed) was **not** released: it would withhold model calls for no reason. |

**Total real Groq calls tonight: 276** = 195 extraction answers for the paired replay (76 + 119) + 76 triage calls (12 + 64) + 3 live probes (two HTTP 429 at the old 4,096 reservation, one HTTP 200 at 800) + 2 pacing-experiment calls. None was retried after a failure; the account's day counter read 738 of 1,000 requests remaining after the last one.

Both live probes: the page showed the complete source-based audit and the calm failure line; `live_smoke` 24 PASS, 0 FAIL each time. The
service's cooldown (≥ 120 s after a 429) applied. **Live probes were then stopped** (no retry after repeated 429s). The difference between the
local calls (all 200 at 800 reserved) and the two live calls suggests the service's own reservation setting; it cannot be read from here,
so `/api/health` now reports `ai_max_completion_tokens`.

## 2026-10-04 (22:5x Riyadh) — the live 429s explained: the service reserved 4,096 output tokens (challenge period)

After PR #9, `/api/health` on the live service reported **`ai_max_completion_tokens: 4096`**: the `GROQ_MAX_COMPLETION_TOKENS=800` recorded on
3 Oct is not in effect on Render (the variable is not set there now; how it was lost is not known from here). Against the account's 1,000
output-tokens/minute limit for `qwen/qwen3.8-27b`, that fits both live 429s of tonight; locally, 75 of 76 calls at 800 answered. The largest
answer measured tonight used **341** output tokens (median 7). Change (branch `groq-reservation`): the code default is now **800** (README,
`.env.example`, `docs/RENDER_DEPLOY.md` updated; one test). No other behaviour changed. pytest 531.

## 2026-10-04 (evening, Riyadh) — releases of the challenge period: what was verified live (challenge period)

Each release was a fast-forward push of the PR's head to `main` (no merge commits; as for PRs #1–#2). Render deployed each within about a
minute. For every release: `/api/health` `build` = the pushed commit, and every file under `app/static` served by the live service
(pages via `/`, `/privacy`, `/sources`, `/limitations`) was compared byte for byte (SHA-256) with that commit.

| PR | Branch | `main` → | Pushed | Live build seen | Served files identical | Live journey (no model call unless stated) |
|---|---|---|---|---|---|---|
| #3 | `ai-provider-harness` | `d65befa` | 20:24 | 20:25 | 14 / 14 | — (its probe was folded into the next release's) |
| #5 | `hard-quotations` | `070263b` | 20:51 | 20:52:45 | 14 / 14 | `LA03` (14,700 characters, over the model limit, `skipped_length`): 21 findings, 25.7 s; «ما يلفظ … رقيب شهيد (ق: 18)» stated, fix «شهيد → عتيد» |
| #6 | `hardening` | `aee587c` | 21:09 | 21:10:57 | 23 / 23 (fonts included) | headers: the strict CSP, HSTS, COOP, CORP, Permissions-Policy present; one model probe: **429** (ledger above) |
| #7 | `import-text` | `91568af` | 21:32 | 21:33:07 | 24 / 24 | a TXT and a DOCX (tracked change, footnote) imported through the real file input: exact text in the editor, the notice, **0 requests during import**, 0 audits; one model probe: **429** |
| #8 | `reference-ordinals` | `4cd0746` | 22:06 | 22:07:24 | 24 / 24 | `LA03` again: «وتحسبونه هينا وهو عند الله عظيم» reference «الآية الخامسة عشرة من سورة النور» matched; 21.8 s |
| #9 | `pilot-ocr-docs` | `317228d` | 22:51 | 22:52:22 | 24 / 24 | `/api/health`: `ai_max_completion_tokens` **4096** — the cause of the live 429s |
| #10 | `groq-reservation` | `bee3e03` | 22:55 | 22:56:14 | (no static file changed) | `ai_max_completion_tokens` 800; one model probe: **HTTP 200**, 4 proposed, 4 located, 0 added |

Not merged: draft PR #4 (`accounts-flag`, accounts behind an off flag; owner's project and decisions needed).

## 2026-10-04 (23:2x Riyadh) — final verification of the code on `main` (`bee3e03`) (challenge period)

On branch `docs-final` (= `bee3e03` + documentation only), local AI-off servers: pytest **531 passed**; node **70 pass**; every `eval/*.sha256`
(8) verifies; the two suggestion sets rerun with results identical to the 4 Oct release runs apart from timings. Browser suites: ui_e2e 29,
ui_journey_e2e 169, ui_final_qa 143, ui_phrase_e2e 38, ui_boundary_e2e 48, ui_long_e2e 93, ui_possible_order_e2e 55, ui_counts_e2e 19,
ui_approved_e2e 148, ui_uthmani_e2e 34, ui_workspace_e2e 139, ui_suggest_e2e 202, ui_suggest_place_e2e 82, ui_dock_e2e 36,
ui_async_navigation_e2e 7, ui_model_notices_e2e 80, ui_a11y_check 56 (axe 0 violations, trust pages included), ui_crossbrowser 89,
ui_selfhost_e2e 45, ui_import_e2e 591 in Chromium, 591 in Firefox, 591 in WebKit — **3,285 checks, 0 failures, 0 skipped**. Every suite also
fails on any CSP violation or any request to another host. Not covered: real phones, Safari itself, screen readers, real writers.

## 2026-10-05 (06:10–07:30 Riyadh) — the running release checked, and four defects fixed (challenge period)

**Starting state, verified (not taken from the previous report).** `main` = `origin/main` = `8278476`, working tree clean; PRs #3, #5–#11
merged, #4 draft. Live `/api/health`: build `8278476`, `ai_max_completion_tokens` 800, model configured. The 11 files under `app/static`
(fonts and samples aside) served by Render are byte-identical to `main`; `/`, `/sources`, `/privacy`, `/limitations` answer 200.
Every `eval/*.sha256` (8) verifies. The seven frozen sets and the two hard-quotation sets rerun on `8278476` give the 4 Oct results
(`compare_runs.py`: identical; the long set differs from `cue-final` only by PR #8's LA03 row, identical to the `ordinals` run).

**Internal inspection (not a user study).** An article with a marked verse and reference, a lead-in quotation with one wrong word
(«ولا تحسبن الله غافلا عما يفعل الظالمون»), a quotation with a missing word and its reference («… اصبروا وصابروا واتقوا الله …
(آل عمران: 200)»), a reference written in words («(سورة الشرح، الآية السادسة)») and ordinary prose («في كل عام نجتمع …») was pasted,
imported as TXT and as DOCX (LibreOffice), edited, audited, confirmed, approved, undone, reviewed, copied, edited again and rechecked, at
1366, 390 and 320 px on a local AI-off server (Playwright, scratch script). Live, without any model call: verse suggestion while typing
and «أدرج» at the three widths, and an 8,382-character article (`LA04`, over the 6,000-character model limit) audited in 8.4–9.4 s,
the page saying the model was not asked; `/api/health` `ai_recent.calls` stayed 0. What was found:

1. **The intended verse was not offered** (`HD-017` «كل نفس بما كسبت رهين» → المدثر 38). Four places tie on whole words; the three-place
   cut in `verifier.fuzzy_candidates` dropped the phrase search's own place. Fix: on a tie, the place whose differing word is spelt
   like the writer's comes first (`docs/EVALUATION.md`). `tests/test_verse_ties.py` (3; the ordering test fails on `8278476`).
2. **«أبقِ «—»»** on a correction that adds a word the writer left out («ورابطوا»), and **«غيّر إلى «»»** on one that removes a word
   the writer added («هو»). Now «أضف «ورابطوا»» / «لا تُضِف شيئًا» and «احذف «هو»» / «أبقِ «هو»», with matching lines after the decision.
3. Found while reviewing fix 2: an approved removal's note said «اعتمدتَه: يُكتب «» …», the caret announcement «يُكتب «» …», and an empty
   label was drawn above the struck word. New `scripts/ui_add_remove_e2e.mjs` (11 checks per width at 1366, 390 and 320 px, plus the CSP and other-host checks: 35) fails 27 of them on `8278476`.
4. **A soft hyphen inside a word** (U+00AD, common in text pasted from web pages) turned a correct quotation into a «difference»
   (probe of ten invisible characters; bidi marks, ZWJ/ZWNJ, NBSP and tatweel were already ignored). U+00AD, U+2060 and U+034F are now
   ignored like them. `tests/test_arabic.py` (1; fails on `8278476`).

Checked and **not changed**: short phrases with no cue («أضغاث أحلام», «خلق عظيم») are not shown, by design — selected by hand,
«افحص المحدَّد» lists يوسف 44 / الأنبياء 5 for the first and القلم 4 for the second; an unmarked substitution of common words
(«إنهم كانوا يتسابقون في الخيرات») is not found unless selected (then it gets the source's «يسارعون» for approval); «في كل عام» stays an
optional «possible» item. Recheck after an edit kept the decision on the unchanged quotation («حُفظ ١ من قراراتك»).

**First failure while gating.** `ui_approved_e2e` failed 3 checks (one per width): it required the old note for an added word
(«ويظهر «رب» فوقه، ويُكتب مكانه»), which fix 2 changed on purpose (an addition replaces nothing: «فوق موضعه، ويُضاف …»). The check
now requires the new wording; its intent (the card says where the word will appear) is unchanged.

**Sets after the fixes** (fallback, no model): `HD-017` is the only changed row of nine detection sets; the two suggestion sets are
identical apart from timings; every safety count unchanged.

**Gate on `4d40e4b`** (07:05–07:40 Riyadh, a clean worktree of the commit; local AI-off servers; macOS, Python 3.14.7, Node 24, Playwright
1.63): pytest **535 passed** (531 + 4 new); node **70 pass**; browser suites ui_a11y_check 56, ui_add_remove_e2e 35, ui_approved_e2e 148, ui_async_navigation_e2e 7, ui_boundary_e2e 48, ui_counts_e2e 19, ui_crossbrowser 89, ui_dock_e2e 36, ui_e2e 29, ui_final_qa 143, ui_import_e2e 591, ui_journey_e2e 169, ui_long_e2e 93, ui_model_notices_e2e 80, ui_phrase_e2e 38, ui_possible_order_e2e 55, ui_selfhost_e2e 45, ui_suggest_e2e 202, ui_suggest_place_e2e 82, ui_uthmani_e2e 34, ui_workspace_e2e 139, ui_import_e2e-firefox 591, ui_import_e2e-webkit 591 — **3,320 checks, 0 failures, 0 skipped**
(every suite also fails on a CSP violation or a request to another host). Not covered: real phones, Safari itself, screen readers, real writers.

## 2026-10-05 — writer feedback: referenced omission and wrong word (challenge period)

The marked quotation «إنما يجزى الصابرون بغير حساب» with its own reference to الزمر: 10 previously showed a word diff but no correction. The proposed wording gate rejected its combination of one changed word and one omitted source word. A narrow exception now permits a reviewable, source-backed suggestion only when at least three words align, there is exactly one one-word replacement and one omitted source word, the quotation is bounded, the writer's reference points to the verse, and there is no close rival. The suggested result is «إنما يوفى الصابرون أجرهم بغير حساب». Nothing is applied without the writer's approval. A wrong-reference regression case remains review-only.

The interface now shortens the first-screen explanation and review cards, keeping source links and uncertainty warnings visible and moving routine rationale into details. `/roadmap` distinguishes working features from possible future work and names the current model and its limited measured benefit. The server-side AI path is unchanged. This branch did not make a Groq call.

Offline checks: full pytest **539 passed**; correction tests 34 passed. An initial Windows run had four setup errors because parametrized malformed-JSON test IDs exceeded the temporary-path limit; after assigning short, descriptive IDs all cases passed. The seven saved fallback evaluation sets and two hard-quotation sets were rerun and their rows were identical to their prior `ties-v1` runs (the Windows `cases_file` path metadata differed). The new screenshot case is covered by regression tests, not those labelled sets. API checks had 0 failures. The first-journey, long-article, approved-correction, model-notice and new screenshot-case browser suites passed at their tested desktop and phone widths; the model-answer states in the notice suite were simulated, not real Groq calls. Accessibility checks found zero axe violations in the tested states, including `/roadmap`.

Exploratory two-word search was **not released**. In the frozen and long articles it found desired unmarked phrases, but also surfaced ordinary prose such as «جملة واحدة», «الأموال والأولاد» and «حياة طيبة». Increasing rarity thresholds would miss «فاستبقوا الخيرات». The remaining short-phrase gap needs a labelled precision study and careful contextual triage before enabling broad automatic detection.

## 2026-10-05 (evening, macOS) — the feedback branch finished: patch applied, review fixes, two-word quotations, gate

**Patch.** `0001-…two-edit-v.patch` (pasted into the session; its 22 post-image blob hashes all equal the patch's `index` lines) applied with
`git am --3way` on `ee3f7a2` as `8230f11` (GitHub `main` had not moved). On this Mac: pytest 539 passed; the seven fallback sets and two
hard sets identical to `ties-v1` (`base12fd`, timings ignored). The Windows run had not included two suites, and both failed here:
`ui_add_remove_e2e` (3: the shorter approved note no longer named a removed word — fixed in `8e68ab3`) and `ui_suggest_place_e2e`
(3, at 320 px: the suggestion box was placed while 338 px tall and then grew to 372 px, covering the typed line after an audit; and a
131.16 px scroll moved 131, so the full verse was folded away — fixed in `7a6edc6`; `main` passed only because the font subset was
already loaded and the editor sat 0.6 px higher).

**Review of the copy.** `/sources` and `/roadmap` had said the model was chosen for speed; the 30 Sep record (`docs/EVALUATION.md`,
«Choice») says it gained one quotation on each small set where gpt-oss-120b did not, was faster, and kept the safety counts at zero. Both
pages now say so, use the exact id `qwen/qwen3.8-27b`, and give the 9 failed calls of 195 next to the 1 true addition in 54,056
characters. `/roadmap` no longer says the draft stays in the browser unless audited (suggestions send up to 700 characters).

**Two-word quotations.** Protocol `docs/SHORT_PHRASE_PROTOCOL_20261005.md`; result and every changed row in `docs/EVALUATION.md`
(«Unmarked two-word quotations»). No Groq call was made by this branch.

**Gate on `e767e8a`** (clean detached worktree, local AI-off servers; Python 3.14.7 venv, Node 24, Playwright 1.63): pytest **550 passed**
(539 + 11 `tests/test_pairs.py`); node **70 pass**; `e2e_check.py` 0 failures (includes `/roadmap`); browser suites ui_a11y_check 59,
ui_add_remove_e2e 35, ui_approved_e2e 148, ui_async_navigation_e2e 7, ui_boundary_e2e 48, ui_counts_e2e 19, ui_crossbrowser 89,
ui_dock_e2e 36, ui_e2e 29, ui_feedback_e2e 20, ui_final_qa 143, ui_import_e2e 591, ui_journey_e2e 169, ui_long_e2e 93,
ui_model_notices_e2e 80 (model states simulated), ui_pair_e2e 38 (new), ui_phrase_e2e 38, ui_possible_order_e2e 55, ui_selfhost_e2e 50,
ui_suggest_e2e 202, ui_suggest_place_e2e 82, ui_uthmani_e2e 34, ui_workspace_e2e 139 — **2,204 checks, 0 failures**; `ui_screens` photographed
65 states at 1366, 390 and 320 px, looked at by eye (first screen, correction card, approved word in the box, long-article phrases,
trust pages, `/roadmap`): no overlap or sideways scroll seen; one bidi glitch («بـgpt-oss-120b» on `/sources`) fixed after the gate.
Not covered: real phones, Safari itself, screen readers, real writers.

**PR #13 self-review** (after the gate): a manual check («افحص المحدَّد») rebuilt its neighbours from the phrase search without the pair
marker, so an optional pair could reserve the reference written for the selected quotation. Pairs are now left out there too
(`tests/test_pairs.py::test_a_pair_does_not_take_the_reference_of_a_selected_span`, which fails without the fix). Rerun: pytest **551**,
ui_phrase_e2e 38, ui_pair_e2e 38, ui_boundary_e2e 48, ui_journey_e2e 169, 0 failures; both hard-quotation sets (whose scorer confirms
through the same endpoint) identical to `pairs-eb00ae0`.

**Release (PR #13).** `main` fast-forwarded `ee3f7a2..1825065` at 20:17:17 Riyadh (the PR #1–#12 method; no merge commit). Render served
build `1825065c68bb…` at 20:18:17; 17 served files (12 static files and the pages `/`, `/sources`, `/privacy`, `/limitations`, `/roadmap`)
byte-identical to the commit. **Live journey** `scripts/live_feedback.mjs` (new) at 20:19:43: **one** audit at 1366 px = **one Groq call:
`ai.outcome` ok, HTTP 200, proposed 1, located 1, added_only 0, 737 ms** (`/api/health` `ai_last_call` agrees). The screenshot case offered
«غيّر إلى «يوفى الصابرون أجرهم»» with الزمر ١٠; approving left the draft as written; the copy held exactly the source correction; «فاستبقوا
الخيرات» was an optional pair; «حياة طيبة» was not listed; `/roadmap` and `/sources` served the new copy. The 390 and 320 px runs **replayed**
that answer (no request reached the server). No other live audit was made.

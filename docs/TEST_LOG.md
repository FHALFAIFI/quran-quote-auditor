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


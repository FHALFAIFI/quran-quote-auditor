# Continuation plan

Everything in the repository today is **pre-challenge work** (see `BASELINE.md`). This file lists what is
planned, separated into the scored challenge days and later work. Items marked *pre-challenge* were done
before 4 October and are not challenge work; everything else is not done yet.

## A. During the challenge (4–6 October 2026) — realistic scope

Each item must be committed during 4–6 October and listed in `CHANGELOG.md` under "Challenge period".

| Priority | Change | Done when |
|---|---|---|
| 1 | **Live AI extraction** on the deployed app (Render, `docs/RENDER_DEPLOY.md`) with the Groq key. *Local verification is pre-challenge: 14/14 responded, 30 Sep.* | `/api/health` and one real audit on the live URL are logged in `docs/TEST_LOG.md` (commit, model, status, candidates, discarded). |
| 2 | Repeat the AI-mode evaluation (three runs, paced under Groq's 7,000 input tokens/minute) to check repeatability. *Single runs are pre-challenge: 26/28 and 4/6 vs 25/28 and 3/6.* | Mean and range in `docs/EVALUATION.md`; every run, including rate-limited ones, listed. |
| 3 | Human review of the labels by an Arabic reader/specialist using `docs/LABEL_REVIEW.md`; log any correction with reason and source. | Checklist ticked; corrections log filled; evaluation re-run. |
| 4 | Handle quotations with an ellipsis («…») as two excerpts in the correction logic, so the omitted part is not flagged as missing words. | Tests for «…» inside ﴿﴾ pass; no automatic insertion of omitted words. |
| 5 | Uthmani-script input: map common Uthmani spellings (e.g. «الصلوة», small alef) so correct Uthmani quotes are not shown as differences. | Tests with Uthmani quotes; no new false fixes on the labelled set. |
| 6 | Demo polish from real evidence: final screenshots, video variant A or B (per `submission/VIDEO_SCRIPT.md`), final PDF deck. | Video ≤ 2:00 and deck show only observed behaviour and numbers. |
| 7 | Test the existing reply draft (built pre-challenge, section C step 1) with real posts pasted by an editor; adjust wording. | Feedback recorded; still copy-only, no API. |

Added to the plan from the 30 Sep phrase-search work (*pre-challenge* results are in `docs/EVALUATION.md`; everything below is not done):

| Priority | Change | Done when |
|---|---|---|
| 8 | Human review of `eval/phrases_frozen.json` with the same checklist as the other sets; check the formula list and the hadith/du'a cue words in `app/phrases.py` | Corrections (if any) logged with reason; all three sets re-run |
| 9 | A quotation whose **last or first word** is wrong is reported as matched with only a hint (2 of 12 misquotations in the frozen set). Decide with an editor whether to treat a one-word tail that ends a sentence as part of the quotation | A labelled case set for edge-word errors; false "matched" on it reported |
| 10 | Real articles by Islamic-content writers (with permission) to measure "maybe" volume; Wikipedia prose is only a proxy | Counts per 1,000 words on the real sample |

Out of scope for the challenge days: new AI providers, server-side storage of articles, accounts, any automatic posting.

## B. After the challenge — product hardening

- Cross-instance Quran text cache (e.g. Vercel Blob) so cold instances do not each download the mushaf.
- Paid AI tier or Zero Data Retention settings before processing real editorial content; monitor quota and cost.
- Larger, independently sourced evaluation set (with permission), reviewed by specialists, with repeated AI runs.
- Accessibility review (screen reader order of the before/after preview), and an English interface option.
- Browser-extension or CMS plug-in (e.g. WordPress) that sends the article to the same API and returns the review list.

## C. X (Twitter) use case — deliberately not built yet

A bot that replies to posts quoting the Quran needs work and approvals that a hackathon night cannot provide safely:

- a separate X developer account and paid API access (credits), with its rate limits;
- **opt-in only** (e.g. the author mentions the bot, or an organisation connects its own account), never unsolicited replies;
- idempotency (one reply per post, stored post IDs, retries without duplicates);
- a human approval step before anything public is posted, a kill switch, and an audit log;
- wording that never says the post "is verified", only which quotations were checked and against which source.

Staged plan:

1. **Copy-ready reply draft (no API) — exists as a pre-challenge draft (29 Sep):** in the app, a button produces a short Arabic text for a pasted post,
   e.g. «راجعتُ الاقتباس القرآني في المنشور: ورد «الشرح: 6» والصواب «الشرح: 5» (قرآنبيديا: …). فحصُ الاقتباسات فقط، وليس حكمًا على المنشور كله.»
   The editor copies and posts it manually.
2. **Opt-in review queue:** mentions of an official account are fetched, audited, and queued for a human to approve.
3. **Assisted replies:** only after 2 has run safely, approved replies are posted by the API with idempotency keys.

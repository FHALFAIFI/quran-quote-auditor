# Continuation plan

Everything in the repository today is **pre-challenge work** (see `BASELINE.md`). This file lists what is
planned, separated into the scored challenge days and later work. Items marked *pre-challenge* were done
before 4 October and are not challenge work; everything else is not done yet.

## A. During the challenge (4–6 October 2026) — realistic scope

Each item must be committed during 4–6 October and listed in `CHANGELOG.md` under "Challenge period".

| Priority | Change | Done when |
|---|---|---|
| 1 | **Live AI extraction** on the deployed app. *Done before the challenge (1–2 Oct 2026, so not challenge work): the Render service answers with real Groq calls (HTTP 200, one 429 on back-to-back audits), and the notice says what the model did. No benefit from the model has been measured live (it proposed the same quotations the deterministic path found, or nothing).* Challenge-day work: repeat it under the same logging if the service or model changes. | One real audit per change logged in `docs/TEST_LOG.md` (commit, model, status, candidates, discarded). |
| 2 | Repeat the AI-mode evaluation (three runs, paced under Groq's 7,000 input tokens/minute) to check repeatability. *Single runs are pre-challenge: 26/28 and 4/6 vs 25/28 and 3/6.* | Mean and range in `docs/EVALUATION.md`; every run, including rate-limited ones, listed. |
| 3 | Human review of the labels by an Arabic reader/specialist using `docs/LABEL_REVIEW.md`; log any correction with reason and source. | Checklist ticked; corrections log filled; evaluation re-run. |
| 4 | Handle quotations with an ellipsis («…») as two excerpts in the correction logic, so the omitted part is not flagged as missing words. | Tests for «…» inside ﴿﴾ pass; no automatic insertion of omitted words. |
| 5 | ~~Uthmani-script input.~~ **Done before the challenge (2 Oct 2026, so it is not challenge work)**: `app/uthmani.py`, frozen held-out set, results and limits in `docs/UTHMANI.md`. Remaining, if time: have an Arabic specialist review the Uthmani labels (four labels disagree with the program: `u32`, `u09`, `u10`, `u19`; none was edited), add real articles pasted from Quran apps, and cover the ~50 rare spellings that read «uncertain». | Labels reviewed; evaluation re-run with the label errors corrected in a new, dated file (the frozen one stays as it is). |
| 6 | Demo polish. *Pre-challenge versions exist (2 Oct 2026): deck and video built from the live service.* Challenge days: only re-record or update if the product changes, and show only observed behaviour and numbers. | Video ≤ 2:00 and deck match the deployed version. |
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

## D. Future direction (idea only — not built, not started, not tested): sharing a post from an iPhone

> **This is not a feature and nothing here works today.** The app takes **pasted text only** (up to 20,000 characters since 3 Oct 2026; 6,000 before) in the browser. It does **not** import a URL or fetch a post, it has no share-sheet or Shortcuts integration, and there is **no iPhone app**. The live demo and the video show none of this.

The idea: an editor who reads a draft or a post on an iPhone could send it to the checker without copying it by hand, and get the same review list back.

Routes that could be examined, in order of how little they need (feasibility on iOS is **unverified** for all of them; none has been tried):

1. **Paste on the phone, as today.** The page works at 390 px and 320 px (tested in a desktop browser at those widths, not on a real phone). The first thing to learn from a pilot is whether editors even work on phones.
2. **An iOS Shortcut** that receives shared text and opens the page with it. This would need the page or API to accept text from outside, which it does not yet do; the text must not travel in a URL query string (it would be logged), so a POST or a URL fragment would be needed.
3. **URL import** (give a link, the server fetches the post). Not planned: many posts sit behind a login or a platform's terms, a server that fetches arbitrary URLs needs protection against abuse (server-side request forgery), and it would send other people's content through the service. Pasted text avoids all of that.
4. **A native iOS share extension / app.** Needs an Apple developer account, App Review, and a maintained second code base; justified only if a pilot shows steady phone use.

Before any of these: always-on hosting, a model setting that does not retain content (see [PILOT.md](PILOT.md)), and evidence from the pilot that editors want it. The plan promises no date and no deliverable.

## E. Roadmap after the writing workspace (written 3 Oct 2026; priority order, none of it done)

1. **A specialist reads the labels.** All evaluation sets, including the two verse-suggestion sets and the long-article set, are AI-written and unreviewed (`docs/LABEL_REVIEW.md`). Until then no accuracy claim beyond "observed on these sets".
2. **Teach the cue vocabulary, and measure it on a fresh set C.** Set B showed silence for «في التنزيل العزيز», «في كتاب الله» and a lead-in followed by extra words before the colon. Any change must be measured on a new frozen set, not on A or B.
3. **Decide the surah-only policy with an editor.** A surah named in the prose («في سورة الإسراء: …») currently confirms an unambiguous quotation's reference ("matched"); the long-set labeller expected "missing". Four references in the long set fall on this.
4. **A pilot with real editors** (permission first): do they accept suggestions, how many «possible» items per article annoy them, how long a review takes. No time saving is claimed today.
5. **Self-host the three fonts** (SIL OFL) so a visit sends nothing to Google, then tighten the CSP; the privacy page currently states the Google Fonts request.
6. **Accuracy between 14,700 and 20,000 characters, and Render under load.** Time and memory were measured to 20,000 characters, accuracy only to 14,700; the host is the free tier.
7. **Real devices and assistive technology:** Safari, Firefox, a phone keyboard, VoiceOver/TalkBack. Only Chromium, axe and keyboard were tested.
8. **Smarter stale handling:** restore a decision if an edit is undone, invalidate only the changed boundary word, an outline of paragraphs with open items for very long articles.
9. **Before real unpublished content:** a model account with zero data retention (or no model), a cross-instance Quran cache, and a paid host.
10. **Measure the model before claiming anything about it.** In every audit so far it proposed nothing the deterministic path did not already find; keep it optional.


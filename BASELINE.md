# Pre-challenge baseline declaration

The organizer's FAQ allows earlier work if the starting version is documented,
and only work done during **4–6 October 2026** is scored. This file is that record.

| | |
|---|---|
| Baseline date | 2026-09-28 |
| Git marker | tag **`pre-challenge-baseline`** (first baseline commit). Every commit dated before 2026-10-04 is pre-challenge work. |
| Built by | the solo participant, with Claude Code as an AI coding assistant |

## What already exists at the baseline

- A FastAPI backend and an Arabic RTL frontend (HTML/CSS/JS) in the challenge's colours.
- Quranpedia Hafs source client with 24 h caching, stale-cache warning and outage handling.
- Arabic normalization with three levels (literal / diacritics ignored / script-normalized) and offset-preserving tokenization.
- Candidate extraction:
  - Gemini provider (JSON schema, timeout, malformed-output handling) behind a replaceable interface;
  - reduced no-AI mode for explicitly marked quotations;
  - verbatim-run scan against the Quran index.
- Verification that every AI candidate occurs in the article.
- Verifier: exact matching of partial and multi-verse quotations, diacritic-conflict and hamza-seat detection, fuzzy closest-verse suggestion with word diff (always “needs review”), and handling of repeated phrases and short phrases.
- Reference parser (named, numeric, ranges, surah-only, aliases) and reference checks (matched / missing / incorrect / uncertain).
- Review-list UI with article highlighting, source verse, diffs, statuses, review reasons, and Quranpedia links.
- Security basics: input limits, rate limit, no article logging, CSP, text-only DOM insertion, secrets via environment variables only.
- 67 offline tests, three sample articles, and README / SOURCES / LICENSE.

## What does NOT exist at the baseline

- No labelled accuracy evaluation. No accuracy numbers are claimed.
- **AI extraction not verified with the real Gemini service** (it returned 503/429 during every test; see docs/TEST_LOG.md).
- At the baseline a deployment existed on Vercel (https://quran-quote-auditor.vercel.app); there was no demo video or presentation yet. (The live demo for submission now runs on Render, set up on 1–2 Oct 2026: also pre-challenge.)
- (Added after the tag, see below: editor workflow and Groq adapter — also pre-challenge.)

## Pre-challenge work after the tag (still before 4 October 2026)

Everything below was also built before the challenge and must **not** be counted as challenge work.
The commits are listed in `CHANGELOG.md` under "Pre-challenge work".

- 28 Sep: shorter AI failure wait, labelled evaluation set (14 articles, 28 gold quotations, 5 negatives), fallback results, AI-status banner.
- 29 Sep:
  - Groq extraction provider (strict JSON schema) next to Gemini, `AI_PROVIDER=auto`, per-audit record of whether AI actually responded, `/api/health` separating "configured" from the last real outcome.
  - Editor workflow: source-backed correction proposals, approve/reject per change, before/after preview, copy of the revised article, unresolved quotations marked, print-friendly review record.
  - Correction-safety scoring in the evaluation, browser end-to-end script, more tests.
  - Presentation and video-script drafts updated.
- 30 Sep: first real Groq calls (local): the service responds; prompt v2 becomes the default after a small, single-run gain
  (26/28 and 4/6 vs 25/28 and 3/6). Completion-token reservation experiment (inconclusive, default kept). Render deployment
  files prepared.
- 30 Sep (later): unmarked-phrase search without AI (`app/phrases.py`), a frozen evaluation set written before it, manual phrase selection, resource measurements;
  the AI comparison is separate (`docs/EVALUATION.md`). Still not done before the challenge: AI extraction on the live site; no successful Gemini call.
- 1–2 Oct: end- and start-of-quotation boundary rules, the Render service (live URL https://quran-quote-auditor.onrender.com), AI provenance rules (a model's proposal is not evidence of a quotation; a model's span never replaces a deterministic finding), live checks with real Groq calls, usability fixes found in the final review, README, presentation and video drafts, public repository. All pre-challenge; see `CHANGELOG.md` and `docs/TEST_LOG.md`.

- 3 Oct (afternoon): the writing workspace — the article stays editable during review, verse suggestion while typing from the Quranpedia text (no model), stale-decision handling and recheck, the 20,000-character limit, three trust pages, two new evaluation sets and a long-article set, length measurements. Committed on 3 Oct 2026 before 09:00 on 4 Oct: **pre-challenge** (see `CHANGELOG.md`).

## How to see challenge-period changes

```bash
git log --since="2026-10-04" --oneline
git diff pre-challenge-baseline..HEAD --stat
```

Commits made during the challenge should be listed in `CHANGELOG.md` under “Challenge period (4–6 October 2026)”.

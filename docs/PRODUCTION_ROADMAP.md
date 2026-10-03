# Production roadmap

Written 3 October 2026, on branch `ui-editorial-2026-10` (from `main` at `47f224e`). **Nothing in this file is built.**
It is a plan with exit tests. A stage is finished only when its tests pass and their evidence is recorded in `docs/TEST_LOG.md`.
"Planned", "would" and "must" here mean exactly that. They are not claims about the service.

Rules that apply to every stage:

- **The source comes first.** A language model may only propose *where* a quotation is. Verse text and every proposed correction come from the Quranpedia text (Hafs). The writer approves each change one by one. No stage may weaken this, and none may restore a per-audit AI on/off switch. Whether a model is used is a server decision, and the page must say clearly when the model failed or was not asked.
- **Guest use stays.** Writing, suggesting, auditing, deciding, copying and printing the record keep working with no account and no upload of anything beyond what `/privacy` already lists.
- **Nothing is shown before it works.** No sign-in button, cloud-save control, import button or OCR option appears in the interface until its backend and its end-to-end tests pass on the deployed service. They stay behind a server flag, off by default. There are no placeholders or "coming soon" items.
- **Separate pull requests.** The interface revision, accounts and OCR are three separate branches and PRs. Each PR updates `CHANGELOG.md`, `docs/TEST_LOG.md` and the three trust pages wherever it changes what is sent or stored.
- **Prices are dated.** Figures below were read on 3 Oct 2026. Some come from the provider's page and some only from third-party summaries, as marked. Re-read the provider's page before budgeting. Render's prices were reported to have changed twice in September 2026.

---

## Stage 1 — Audit quality and AI reliability

**Goal:** know, with evidence an outsider would accept, how often the audit is right. Know what the model adds, and keep the service calm and correct when the provider refuses.

### 1.1 Independent Arabic label review (blocking for any accuracy claim)

Every evaluation set so far was written by the same AI-assisted workflow as the app and has not been reviewed by a person (`docs/LABEL_REVIEW.md`).

- **Work:** an Arabic reader with Quranic-studies training reviews `eval/cases.json`, `heldout.json`, `phrases_frozen.json`, `articles_frozen.json`, `articles_long_20261003.json` and the Uthmani sets, using the checklist in `docs/LABEL_REVIEW.md`. Corrections go into a new version of each set. Frozen files are never edited in place.
- **Decision for the editor or reviewer:** the surah-only policy. When a surah is named in the prose («في سورة الإسراء: …»), is the reference "matched" or "missing/uncertain"? Four references in the long set depend on this.
- **Exit test:** every set has a signed review record (reviewer's name or role, date, items changed). `eval/run_eval.py` is re-run on the reviewed labels and the results are reported next to the old ones, without overwriting them.
- **Needed:** a named reviewer (none is engaged), and the reviewer's agreement to be credited or to stay anonymous.

### 1.2 Partial and wrong-word quotations

Known gaps (`docs/EVALUATION.md`):

- short repeated phrases are missed («وبالوالدين إحسانا», «فاستبقوا الخيرات»);
- an unmarked near-miss gets no replacement until its boundary is settled;
- ordinary prose is shown as «possible» about once per 6,800 characters. For example, «في كل عام» is the first open item of `LA01`; the interface review on 3 Oct shows it as the first decision.

- **Work:** a new frozen set C, written blind by someone who has not read the detector. It must contain:
  - at least 60 partial quotations,
  - at least 40 one-word-wrong quotations of 3–6 words,
  - at least 30 two-word repeated phrases,
  - at least 40 prose look-alikes.
  
  Any rule change is measured on C once, after it is frozen.
- **Exit tests:**
  - 0 wrong replacements and 0 "matched" verdicts on a misquotation (unchanged gates);
  - detection and «possible»-noise rates reported with 95% intervals;
  - no regression on the six existing sets (`eval/*.sha256` verified).
- **Not allowed:** lowering a threshold to recover a single case, or tuning on C after it has been run.

### 1.3 Long articles

Accuracy was measured only up to 14,700 characters. Time and memory were measured up to 20,000 (`scripts/measure_length.py`). On Render Free, 15,000 characters took about 15 s and 20,000 took about 25 s.

- **Work:** five reviewed articles of 15,000–20,000 characters. Run each locally and on the production host. Record the time to first card, memory, and the candidate cap (`max_candidates`).
- **Exit test:** on the paid instance (Stage 4), p95 time to first card is at most 30 s at 20,000 characters, and no article silently stops early. The cap notice must appear whenever the cap is reached (already tested in `tests/`).
- **Interface:** open items in a very long article are reached through the list and «التالي». A paragraph outline is deferred until the pilot shows it is needed.

### 1.4 Provider limits and failure states

What has been observed:

- Groq's free tier answered HTTP 429 «request too large» while the app reserved 4,096 output tokens. Our account met a 1,000 output-token/minute limit for `qwen/qwen3.8-27b`. `GROQ_MAX_COMPLETION_TOKENS=800` is set on Render. Two 200 answers followed, which is not a controlled test.
- Live `/api/health` on 3 Oct, after `47f224e` was deployed, reported its last call as **failed, HTTP 429**.

Work and tests:

- **Work:** a provider test harness run against a recorded fake (no network) for: 429 (rate), 429 (too large), 5xx, timeout, malformed JSON, a truncated answer, and an empty answer. Each case must end in a complete source-based audit, the calm status line «تعذّر اقتراح الذكاء الاصطناعي هذه المرة…», and no retry storm. The cooldown must be honoured.
- **Interface (done in the UI PR, see below):**
  - an article over the model limit says before the audit that it will be checked in full without the model;
  - after the audit, the status names the reason (length, failure, or no model on the server);
  - «أعد التدقيق» stays available after a failure.
- **Exit test:** the fake-provider suite passes in CI. A live probe on the deployed service makes **one** labelled call per release, never a loop, and logs `ai.outcome`, `http_status` and the elapsed time in `TEST_LOG`.
- **Needed:** a decision on the Groq plan. The free tier has 1,000 requests/day and 8,000 tokens/min according to Groq's page (read 2 Oct). The Developer plan price was not read. If unpublished articles are expected, also decide on zero-data-retention.

### 1.5 Measured incremental value of the model

In every audit so far the model proposed nothing that the deterministic path had not already found (`ai.added_only = 0`). Since `47f224e` the model is attempted on every short audit, so it is sent text on every audit. That has to be justified.

- **Work:** run set C and the long sets twice, once with the model off and once on (same code, one run each, results kept). For every finding, record `ai_role`: only, also or overlap. Count true quotations found **only** by the model, and false «possible» items added **only** by the model.
- **Decision rule (agreed before the run):** keep the model on by default only if it adds at least 2 true quotations per 10,000 characters with no more than 1 extra false item per 10,000 characters. Otherwise, switch it off on the server (`AI_PROVIDER=none`) and update `/privacy`.
- **Exit test:** the result and the decision are recorded in `docs/EVALUATION.md`. The privacy page matches the decision.
- **Cost of the test:** about 30 articles × 2 runs within Groq's free limits (it may need several days because of the daily cap). There is no paid spend.

---

## Stage 2 — Optional managed accounts and private cloud drafts (separate PR)

**Goal:** a writer who wants to can sign in and keep several private drafts with their decisions, preferences, export and deletion. A guest notices no difference.

### Architecture (proposed)

```
browser (static app, unchanged for guests)
   │  HTTPS, Authorization: Bearer <access token>  (only when signed in)
   ▼
FastAPI on the paid host ──verifies JWT (JWKS, issuer, audience, expiry)──► managed auth (e.g. Supabase Auth)
   │  server-side queries with the user id taken from the verified token, never from the request body
   ▼
managed Postgres (e.g. Supabase Pro), Row-Level Security on every table as a second guard
   tables: drafts(id uuid, user_id, title, body text, decisions jsonb, audited_text text, updated_at, version int)
           preferences(user_id, suggest_on bool, distinct_on bool, updated_at)
           deletion_log(user_id hash, requested_at, completed_at)   ← no content
```

- **Sign-in:** an email magic link first, with no passwords to store. Google or Apple sign-in come only if asked for, because each needs its own OAuth client and review.
- **Drafts:** an explicit «احفظ في حسابي» saves the editor text and the decisions (the same shape as today's `exportDecisions()` JSON). Autosave is opt-in and debounced. A draft is never sent to the model except when the writer audits it, exactly as for a guest.
- **Conflicts:** an optimistic `version` column. A stale save is refused and the writer chooses which copy to keep. There is no silent overwrite.
- **Export:** one draft or all drafts as TXT and JSON, generated in the browser from the API response.
- **Deletion:** delete a draft, or delete the account. Account deletion removes the auth user and every row in one transaction, then confirms by email. Backups that still hold deleted rows expire with the provider's retention (Supabase Pro daily backups, kept 7 days, as read on 3 Oct). `/privacy` must say this.
- **Feature flag:** `ACCOUNTS_ENABLED=false` by default. While it is false, the page loads no auth script and shows no control.

### Data flows and privacy

- **New personal data:** an email address, draft text (which may be unpublished work), decisions and timestamps.
- **Processor:** the auth/database provider, in the region chosen at project creation.
- **Logs:** application logs must never contain draft text, only ids and status codes. A test greps the logs.
- **Saudi Arabia:** the PDPL (SDAIA) applies to the personal data of people in the Kingdom. Choosing a non-Saudi region means a cross-border transfer. **Legal review is needed before launch.** This plan does not settle it.
- **Pages to rewrite before the flag is turned on:** `/privacy` (what is stored, where, for how long, how to delete, who the controller is) and `/limitations`.

### Acceptance tests (all must pass on the deployed service before the flag is turned on)

1. **Guest unchanged.** The guest journey suites (`ui_journey_e2e`, `ui_final_qa`, `ui_a11y_check`) pass with the flag on and no sign-in, and the network log shows no auth request.
2. **Cross-user isolation.**
   - User A cannot read, list, update, delete or export user B's draft.
   - Tested through the API by guessing ids, swapping the `user_id` in the body, and replaying A's token after A's deletion.
   - Tested directly against Postgres with RLS, using B's token.
   - Every case must give 404 or 403 and leak nothing.
3. **Token checks:** expired, wrong-audience, wrong-issuer, unsigned (`alg:none`) and tampered tokens are all refused.
4. **Deletion:** after account deletion, no row with that user id remains, the magic link no longer works, and the export endpoint returns 401.
5. **Export round trip:** export, delete, re-import gives the same text and decisions.
6. **Conflict:** two tabs edit the same draft, and the second save is refused with a visible choice.
7. **Rate limits and size:** each draft is limited to 20,000 characters and at most 200 drafts per user (proposal). Exceeding either gives a clear refusal.
8. **Accessibility:** the sign-in and draft list pass axe with 0 violations and pass a keyboard-only run at 1366 / 390 / 320 px.
9. **Backup restore drill:** restore a backup into a scratch project and read one draft back. Record it.

### Costs (read 3 Oct 2026; re-check before buying)

| Item | Figure | Source |
|---|---|---|
| Supabase Free | $0, 50,000 MAU, 500 MB database, **paused after one week without activity, no automatic backups**, so **not usable for production** | supabase.com/pricing |
| Supabase Pro | from $25/month: 100,000 MAU, 8 GB disk, daily backups kept 7 days; point-in-time recovery an extra $100/month per 7 days of retention | supabase.com/pricing |
| Email for magic links | the provider's built-in sender is rate-limited. A production sender (own SMTP or a transactional email service) is needed; **price not read** | — |
| Host | see Stage 4 | — |

### Credentials and external decisions still needed (none exist today)

- Choice of auth/database provider (Supabase is the proposal; an alternative is acceptable if it gives RLS-equivalent isolation and an EU/KSA region option).
- A project created by the owner. Then:
  - `SUPABASE_URL`, the public anon key, and the JWKS/issuer for server-side verification, stored in Render environment variables;
  - the **service-role key** only on the server, if it is needed at all, never in the browser.
- A sender domain with SPF/DKIM for magic-link email.
- The data controller's legal identity and a contact address for privacy requests.
- The region, and a PDPL review of cross-border transfer.
- The retention period for inactive accounts, and an age policy.
- Terms of use for stored drafts.

---

## Stage 3 — Import and OCR (separate PR from accounts and from the UI)

**Goal:** bring text that already exists into the editor. Recognised text is always the writer's text to check and edit **before** the audit. OCR never decides a verse.

### 3.1 Text import: TXT, DOCX, PDF with a text layer (no OCR)

- **Architecture: in the browser, no upload.**
  - TXT is read with `FileReader`.
  - DOCX is read with a vetted parser (for example mammoth.js, pinned and served from our origin).
  - A text-layer PDF is read with pdf.js (pinned, self-hosted).
  - The extracted text is put into the editor as an ordinary paste. The server sees nothing until the writer audits, which keeps today's privacy statement true.
- **Arabic-specific risks to test:**
  - PDFs that store Arabic in presentation forms (U+FE70–FEFF) or in visual (reversed) order;
  - lost spaces between words;
  - kashida/tatweel;
  - footnote numbers merged into words;
  - Quran fonts whose glyphs map to private-use code points.
- **Fixes:** normalisation to logical order and base letters before insertion, followed by a warning line in the editor («استُخرج النص من ملف؛ راجعه قبل التدقيق») when anything was normalised.
- **Acceptance tests:**
  - a fixture folder of real-shaped files (Word with ﴿﴾ and diacritics, a Word file with tracked changes, a PDF exported from Word, a PDF with presentation forms, a reversed-order PDF, a password-protected PDF, a 20,001-character file, a renamed binary);
  - for each fixture, the extracted text equals the expected text code point for code point, or the file is refused with a clear reason;
  - no network request is made during import (checked in Playwright);
  - axe and keyboard runs on the import control.
- **Cost:** none beyond development; the parsers are open source (check each licence before adding it).

### 3.2 Arabic OCR benchmark (before any OCR reaches the interface)

- **Set:** at least 60 pages, with the rights cleared to use them:
  - newspaper columns, mosque bulletins, printed books, phone photos of print, and screenshots of social posts;
  - with Quran quotations in Naskh and in Uthmani fonts, with and without diacritics;
  - ground truth typed and checked by two people.
- **Candidates:**
  - Tesseract `ara` (self-hosted, open source);
  - Google Document AI Enterprise OCR (third-party reports: $1.50 per 1,000 pages for 1–5 M pages/month, first 1,000 pages/month free; **not read on Google's page**);
  - Azure Document Intelligence Read (500 free pages/month on Azure's page; the per-page price did not render when read);
  - any other engine the team wants.
- **Metrics:**
  - character and word error rate overall;
  - **inside Quran quotations** separately;
  - diacritic error rate;
  - the rate of "plausible wrong word" errors (an OCR word that is a different valid word);
  - time per page and cost per page.
- **Exit test:** a written choice of engine, with numbers and the rejected options. If no engine reaches a word error rate inside quotations that a reviewer accepts, OCR stops here.

### 3.3 Scanned PDF and image support

Architecture:

```
browser ─(upload, after an explicit notice)─► FastAPI /api/ocr (memory only, size/page caps, file-type sniffing)
          ─► OCR engine (self-hosted worker, or the chosen cloud API in a fixed region)
          ◄─ text + per-word confidence
browser: text goes into the editor with low-confidence words underlined, a banner «نص مستخرج آليًا — راجعه قبل التدقيق», nothing audited yet
writer edits ─► «دقّق الاقتباسات» (unchanged audit)
```

- **Never a silent verse replacement.** The OCR text is treated exactly as the writer's text. If OCR misread a Quran word, the audit reports a *difference* with the source and proposes the correction for approval, as for any typo. The record marks the article as OCR-derived. A test makes sure that no OCR word is ever changed to a Quran word without a decision card.
- **Privacy:**
  - images and PDFs may contain far more than the article (names, faces, letterheads);
  - with a cloud engine, they are sent to that provider under its retention terms (a DPA and a region are needed);
  - with Tesseract, nothing leaves the host.
  - `/privacy` must gain a row before the flag is turned on.
- **Acceptance tests:**
  - the benchmark pages run end to end in the browser;
  - low-confidence underlining matches the engine output;
  - the audit runs only after an explicit action;
  - caps are enforced (proposal: 10 pages, 10 MB);
  - encrypted, corrupted and multi-hundred-page files are refused with a reason;
  - nothing is written to disk (checked with a tmpfs probe);
  - logs contain no text;
  - cost per article is measured on the deployed service.
- **Credentials and decisions needed:**
  - the engine choice from 3.2;
  - for a cloud engine: a billing account, a project or resource in a chosen region, a key or service account stored as a Render secret, and a signed DPA;
  - for Tesseract: an instance with enough memory (not measured);
  - who pays per page, and the monthly page cap.

---

## Stage 4 — Hosting, monitoring, backups, privacy, rights and accessibility (release gates)

Each item below is a gate. A public "production" label needs all of them.

| Gate | What must be true | Evidence |
|---|---|---|
| Host | A paid always-on instance with no 15-minute spin-down. Third-party pages put Render Starter at about $7/month (0.5 vCPU, 512 MB); **re-check render.com/pricing**. Memory at a 20,000-character audit is measured on it. | `/api/health` build equals the released commit; a load test of 10 concurrent 6,000-character audits records p95 time |
| Domain and TLS | Own domain, HTTPS only, HSTS | header check |
| Security headers | CSP without `unsafe-inline` once the three fonts are self-hosted (SIL OFL), so a visit sends nothing to Google; dependency audit clean | `curl -I`, `pip-audit`, the page network log |
| Monitoring | An external uptime check of `/api/health`; error reporting that **scrubs article text**; an alert when the Quranpedia source is stale or unreachable, and when the model's 429 rate passes a threshold | an alert test fired once and recorded |
| Backups | Only when Stage 2 is on: daily backups, a restore drill each quarter | the drill record |
| Model data | A Groq account setting of zero data retention, or the model off (see 1.5); `/privacy` names the setting | a screenshot of the provider setting in the release record |
| Privacy | `/privacy` matches the code for every flag that is on; a named controller and a contact; PDPL review done if accounts or OCR are on | review sign-off |
| Rights | Written answers from Quranpedia (service use, attribution), and from Tanzil and Quran Foundation if their text or data are used. Drafts exist in `submission/RIGHTS_INQUIRIES_DRAFT.md`; **unsent**. Old commit SHAs still fetchable until GitHub Support acts (draft unsent). | the replies, filed |
| Accessibility | WCAG 2.2 AA review by a person using VoiceOver (iOS/macOS) and TalkBack on real devices, in addition to axe; Safari and Firefox on real phones | a review report; today only axe, a keyboard run and Playwright WebKit/Firefox exist |
| Interface sign-off | A first-time-writer study with at least 5 Arabic writers (not the author) on their own articles; the tasks, time and failures recorded | a study note. **Automated tests passing is not this gate.** |

---

## The interface revision on this branch (what it does and does not settle)

Done in the UI PR (`ui-editorial-2026-10`):

- the empty page leads with the article sheet;
- the explanation is cut to one sentence;
- the demonstration article is a secondary action under the sheet;
- an approved correction is no longer drawn as a source match;
- the model's state (failed, over the limit, or not configured) is named in a calm line;
- informational notices are folded.

It does **not** settle the 1.2 noise. The first open item of a long article can still be ordinary prose shown as «possible». It also does not settle any Stage 4 accessibility gate.

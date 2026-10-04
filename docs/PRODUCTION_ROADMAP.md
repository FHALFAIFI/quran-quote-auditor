# Production roadmap

Written 3 October 2026 and revised 4 October 2026, on branch `ui-editorial-2026-10` (from `main` at `47f224e`). **Accounts, cloud drafts, file import
and OCR are not built.** This file is a plan with exit tests. A stage is finished only when its tests pass and their evidence is recorded in `docs/TEST_LOG.md`.
"Planned", "would" and "must" here mean exactly that. They are not claims about the service.

Rules that apply to every stage:

- **The source comes first.** A language model may only propose *where* a quotation is. Verse text and every proposed correction come from the Quranpedia text (Hafs). The writer approves each change one by one. No stage may weaken this, and none may restore a per-audit AI on/off switch. Whether a model is used is a server decision, and the page must say clearly when the model failed or was not asked.
- **Guest use stays.** Writing, suggesting, auditing, deciding, copying and printing the record keep working with no account and no upload of anything beyond what `/privacy` already lists.
- **Nothing is shown before it works.** No sign-in button, cloud-save control, import button or OCR option appears in the interface until its backend and its end-to-end tests pass on the deployed service. They stay behind a server flag, off by default. There are no placeholders or "coming soon" items.
- **Separate pull requests.** The interface revision (draft PR #2), accounts and import/OCR are three separate branches and PRs. Each PR updates `CHANGELOG.md`, `docs/TEST_LOG.md` and the three trust pages wherever it changes what is sent or stored.
- **Costs are estimates, not commitments.** A price or limit appears below only if it was read on the provider's own page on the date given. Figures that were known only from third-party summaries, or that did not render on the provider's page, were removed on 4 Oct. Read each page again before budgeting or buying.

---

## Stage 1 — Audit quality and AI reliability

**Goal:** know, with evidence an outsider would accept, how often the audit is right. Know what the model adds, and keep the service calm and correct when the provider refuses.

### 1.1 Independent Arabic label review (blocking for any accuracy claim)

Every evaluation set so far was written by the same AI-assisted workflow as the app and has not been reviewed by a person (`docs/LABEL_REVIEW.md`).

- **Work:** an Arabic reader with Quranic-studies training reviews `eval/cases.json`, `heldout.json`, `phrases_frozen.json`, `articles_frozen.json`, `articles_long_20261003.json`, the two suggestion sets and the Uthmani sets, using the checklist in `docs/LABEL_REVIEW.md`. Corrections go into a new version of each set. Frozen files are never edited in place.
- **Decision for the editor or reviewer:** the surah-only policy. When a surah is named in the prose («في سورة الإسراء: …»), is the reference "matched" or "missing/uncertain"? Four references in the long set depend on this.
- **Exit test:** every set has a signed review record (reviewer's name or role, date, items changed). `eval/run_eval.py` is re-run on the reviewed labels and the results are reported next to the old ones, without overwriting them.
- **Needed:** a named reviewer (none is engaged), and the reviewer's agreement to be credited or to stay anonymous.

### 1.2 Partial and wrong-word quotations, and prose shown as «possible»

Known gaps (`docs/EVALUATION.md`):

- short repeated phrases are missed («وبالوالدين إحسانا», «فاستبقوا الخيرات»);
- an unmarked near-miss gets no replacement until its boundary is settled;
- ordinary prose that matches a verse exactly is shown as «possible» about once per 6,800 characters. On 4 Oct, «في كل عام» (the first open item of `LA01`) was diagnosed: tier «possible», code `common`. On the two labelled article sets (`articles_frozen`, `articles_long_20261003`) an exact-but-common «possible» item is a real quotation 11 times in 26 (`eval/possible_tier_composition.py`). Draft PR #2 changed only where these appear (after the concrete decisions, as «عبارات للتأكيد») and how they are counted; **it did not change detection and does not reduce this noise**.

- **Work:** a new frozen set C, written blind by someone who has not read the detector. It must contain:
  - at least 60 partial quotations,
  - at least 40 one-word-wrong quotations of 3–6 words,
  - at least 30 two-word repeated phrases,
  - at least 40 prose look-alikes, including exact matches of common phrases («في كل عام», «من كل شيء»).

  Any rule change is measured on C once, after it is frozen.
- **Exit tests:**
  - 0 wrong replacements and 0 "matched" verdicts on a misquotation (unchanged gates);
  - detection and «possible»-noise rates reported with 95% intervals, separately for `approximate` and `common` items;
  - no regression on the existing sets (`eval/*.sha256` verified).
- **Not allowed:** lowering or raising a threshold to recover or suppress a single case, or tuning on C after it has been run.

### 1.3 Long articles

Accuracy was measured only up to 14,700 characters. Time and memory were measured up to 20,000 (`scripts/measure_length.py`). On Render Free, 15,000 characters took about 15 s and 20,000 took about 25 s (3 Oct).

- **Work:** five reviewed articles of 15,000–20,000 characters. Run each locally and on the production host. Record the time to first card, memory, and the candidate cap (`max_candidates`).
- **Exit test:** on the paid instance (Stage 4), p95 time to first card is at most 30 s at 20,000 characters, and no article silently stops early. The cap notice must appear whenever the cap is reached (already tested in `tests/`).
- **Interface:** open items in a very long article are reached through the list and «التالي» (decisions first, then phrases to confirm). A paragraph outline is deferred until the pilot shows it is needed.

### 1.4 Provider limits and failure states

What has been observed:

- Groq's free tier answered HTTP 429 «request too large» while the app reserved 4,096 output tokens; the error body named a 1,000 output-tokens-per-minute limit for `qwen/qwen3.8-27b` on our account (that figure is from the error body, not from Groq's page). `GROQ_MAX_COMPLETION_TOKENS=800` is set on Render. Two 200 answers followed, which is not a controlled test.
- Live `/api/health` on 3 Oct, after `47f224e` was deployed, reported its last call as **failed, HTTP 429**.
- Groq's rate-limit page (console.groq.com/docs/rate-limits, read 4 Oct 2026) lists for `qwen/qwen3.8-27b` on the free plan: 30 requests/minute, 1,000 requests/day, 8,000 tokens/minute, 200,000 tokens/day. It says the Developer plan has higher limits; **its price was not read**.

Work and tests:

- **Work:** a provider test harness run against a recorded fake (no network) for: 429 (rate), 429 (too large), 5xx, timeout, malformed JSON, a truncated answer, and an empty answer. Each case must end in a complete source-based audit, the calm status line «تعذّر اقتراح الذكاء الاصطناعي هذه المرة…», and no retry storm. The cooldown must be honoured.
- **Interface (in the UI PR):** an article over the model limit says before the audit that it will be checked in full without the model; after the audit the status names the reason (length, failure, or no model on the server); «أعد التدقيق» stays available after a failure; technical detail (the HTTP status) sits behind «تفاصيل هذا التدقيق». The answered, failed, over-length and unconfigured states are checked in the browser with **simulated** audit answers only.
- **Exit test:** the fake-provider suite passes in CI. A live probe on the deployed service makes **one** labelled call per release, never a loop, and logs `ai.outcome`, `http_status` and the elapsed time in `TEST_LOG`.
- **Needed:** a decision on the Groq plan, and, if unpublished articles are expected, on zero data retention (Stage 4).

### 1.5 Measured incremental value of the model

In every audit so far the model proposed nothing that the deterministic path had not already found (`ai.added_only = 0`). Since `47f224e` the model is attempted on every short audit, so it is sent text on every audit. That has to be justified.

- **Work:** run set C and the long sets twice, once with the model off and once on (same code, one run each, results kept). For every finding, record `ai_role`: only, also or overlap. Count true quotations found **only** by the model, and false «possible» items added **only** by the model.
- **Decision rule (agreed before the run):** keep the model on by default only if it adds at least 2 true quotations per 10,000 characters with no more than 1 extra false item per 10,000 characters. Otherwise, switch it off on the server (`AI_PROVIDER=none`) and update `/privacy`.
- **Exit test:** the result and the decision are recorded in `docs/EVALUATION.md`. The privacy page matches the decision.
- **Cost of the test:** about 30 articles × 2 runs within the free limits above (the daily request cap may spread it over days). No paid spend is planned.

---

## Stage 2 — Optional managed accounts and private cloud drafts (separate PR, after the UI PR)

**Goal:** a writer who wants to can sign in and keep several private drafts with their decisions and preferences, export them and delete them. A guest notices no difference, and nothing is stored in the cloud unless the writer chooses it.

### Architecture (proposed)

```
browser (static app, unchanged for guests)
   │  HTTPS; Authorization: Bearer <short-lived access token> only when signed in
   ▼
FastAPI on the paid host ──verifies the JWT (JWKS, issuer, audience, expiry)──► managed auth (proposal: Supabase Auth)
   │  queries scoped by the user id from the verified token, never from the request body
   ▼
managed Postgres (proposal: Supabase), Row-Level Security on every table as a second guard
   tables: drafts(id uuid, user_id, title, body text, decisions jsonb, audited_text text, created_at, updated_at, version int)
           preferences(user_id, suggest_on bool, distinct_on bool, updated_at)
           deletion_log(user_id hash, requested_at, completed_at)   ← no content
```

### What the writer gets

- **Optional managed sign-in.** An email magic link first (no passwords stored by us). Google or Apple sign-in only if asked for, since each needs its own OAuth client and review. The sign-in control appears only when `ACCOUNTS_ENABLED=true`; with the flag off, the page loads no auth script.
- **Multiple private drafts.** A list of the writer's drafts (title, last saved, length), with open, rename and delete. Proposal: up to 200 drafts of up to 20,000 characters each.
- **Explicit cloud-save choice.** Nothing goes to the account by itself. «احفظ في حسابي» saves the current text and decisions (the shape of today's `exportDecisions()` JSON). Signing in never uploads the tab's current article; the writer is asked. Autosave is a separate opt-in per draft, debounced, and says when it last saved. A draft is sent to the model only when the writer audits it, exactly as for a guest.
- **Saved preferences.** The two suggestion options (`opt-suggest`, `opt-distinct`) follow the account when signed in; a guest keeps them in this browser only, as today.
- **Export.** One draft or all drafts as TXT and JSON, generated in the browser from the API response.
- **Delete.** One draft, or the whole account. Account deletion removes the auth user and every row in one transaction and confirms by email. Backups that still hold deleted rows expire with the provider's backup retention (Supabase Pro: daily backups kept 7 days, read on supabase.com/pricing on 4 Oct 2026). `/privacy` must say this.

### Session behaviour

- Short-lived access token (proposal: 1 hour) with a rotating refresh token; "sign out" ends this browser's session, "sign out everywhere" revokes all refresh tokens.
- When a token expires or is revoked mid-edit, **the text stays in the editor**; the next save fails visibly («لم يُحفظ: سجّل الدخول من جديد») and nothing is lost or silently retried with another identity.
- Signing out clears the account's drafts from the page and from `sessionStorage`; a draft the writer saved in this browser as a guest (`localStorage`) is left alone and not uploaded.
- Two tabs on the same draft: an optimistic `version` column; a stale save is refused and the writer chooses which copy to keep. No silent overwrite.
- Tokens are kept in memory or an `HttpOnly`, `Secure`, `SameSite` cookie, never in `localStorage`; the CSP forbids inline script (Stage 4).

### Data flows and privacy

- **New personal data:** an email address, draft text (which may be unpublished work), decisions, preferences and timestamps.
- **Processor:** the auth/database provider, in the region chosen at project creation.
- **Logs:** application logs never contain draft text, only ids and status codes. A test greps the logs.
- **Saudi Arabia:** the PDPL (SDAIA) applies to the personal data of people in the Kingdom. Choosing a non-Saudi region means a cross-border transfer. **Legal review is needed before launch.** This plan does not settle it.
- **Pages to rewrite before the flag is turned on:** `/privacy` (what is stored, where, for how long, how to delete, who the controller is) and `/limitations`.

### Acceptance tests (all must pass on the deployed service before the flag is turned on)

1. **Guest unchanged.** The guest journey suites (`ui_journey_e2e`, `ui_final_qa`, `ui_a11y_check`) pass with the flag on and no sign-in, and the network log shows no auth request.
2. **Cross-user isolation.**
   - User A cannot read, list, update, delete or export user B's draft or preferences.
   - Tested through the API by guessing ids, swapping the `user_id` in the body, replaying A's token after A signs out and after A's deletion, and with B's id in a query string.
   - Tested directly against Postgres with RLS, using B's token, and with the anon key alone.
   - Every case must give 404 or 403 and leak nothing (not even whether the id exists).
3. **Token checks:** expired, wrong-audience, wrong-issuer, unsigned (`alg:none`) and tampered tokens are all refused.
4. **Session:** expiry mid-edit keeps the text and shows the refusal; "sign out everywhere" ends a second browser's session within the access-token lifetime.
5. **Explicit save:** after sign-in with text in the editor, nothing is uploaded until «احفظ في حسابي»; the network log proves it.
6. **Deletion:** after account deletion, no row with that user id remains, the magic link no longer works, and the export endpoint returns 401.
7. **Export round trip:** export, delete, re-import gives the same text and decisions.
8. **Conflict:** two tabs edit the same draft, and the second save is refused with a visible choice.
9. **Limits:** exceeding the draft size or count gives a clear refusal.
10. **Accessibility:** the sign-in and draft list pass axe with 0 violations and a keyboard-only run at 1366 / 390 / 320 px.
11. **Backup restore drill:** restore a backup into a scratch project and read one draft back. Record it.

### Costs (estimates, not commitments)

| Item | Figure | Source |
|---|---|---|
| Supabase Free | $0; 50,000 monthly active users; 500 MB database; **projects paused after 1 week of inactivity**; backups not stated for this plan. **Not usable for production.** | supabase.com/pricing, read 4 Oct 2026 |
| Supabase Pro | from $25/month; 100,000 monthly active users; 8 GB disk per project; daily backups kept 7 days; point-in-time recovery $100/month per 7 days of retention | supabase.com/pricing, read 4 Oct 2026 |
| Email for magic links | a production sender (own SMTP or a transactional email service) is needed; **no price read** | — |
| Host | see Stage 4 | — |

### Credentials and decisions needed (none exist today)

- Choice of auth/database provider (Supabase is the proposal; an alternative is acceptable if it gives RLS-equivalent isolation and a suitable region).
- A project created by the owner. Then `SUPABASE_URL`, the public anon key and the JWKS/issuer stored in Render environment variables; the service-role key only on the server, if needed at all, never in the browser.
- A sender domain with SPF/DKIM for magic-link email.
- The data controller's legal identity and a contact address for privacy requests.
- The region, and a PDPL review of cross-border transfer.
- The retention period for inactive accounts, and an age policy.
- Terms of use for stored drafts.

### Stage 2 status (4 Oct 2026, challenge period) — implemented behind a flag on branch `accounts-flag`; **not merged, not live**

**Where it stands.** The code, tests and SQL exist on the branch `accounts-flag` only. The flag `ACCOUNTS_ENABLED` is **off by default** and was never turned on outside local tests. No Supabase project, region, sender domain, controller identity, retention decision or privacy review exists, so nothing has been tried against the real service. This is **not** production-ready, and it is not a claim that Stage 2 is done.

**With the flag off (the default), nothing changes:** no `/api/account/*` route is registered (404), the page loads no account script or stylesheet and shows no control, no request goes to an auth service, the CSP is unchanged, the JWT/store modules are not imported, and `/api/health` only gains `"accounts_enabled": false`. A half-configured flag (no HTTPS `SUPABASE_URL` or no anon key) stays off.

**What exists (flag on):**

| Part | File(s) |
|---|---|
| Token verification: JWKS signature (ES256/RS256 only; `none` and `HS*` refused before any key is used; key type must match), `iss`, `aud`, `exp`/`nbf`/`iat` with 30 s leeway, `sub` must be a UUID, `role` (if present) must be `authenticated`; JWKS cached 10 min, refetched on an unknown `kid` at most once per 30 s | `app/accounts/tokens.py` |
| `DraftStore`: `PostgrestStore` (Supabase REST over httpx with the **writer's own token** + anon key; every query also filtered by the verified id; never the service-role key) and `MemoryStore` (tests only; enforces isolation itself) | `app/accounts/store.py` |
| API: `GET/POST /api/account/drafts`, `GET/PUT/DELETE /api/account/drafts/{id}` (PUT needs `version`; stale → 409 with both versions' metadata), `GET/PUT /api/account/preferences`, `GET /api/account/export`, `POST /api/account/signout`, `DELETE /api/account`, `GET /api/account/config` (URL + public anon key). User id only from the verified token; another user's draft is 404; limits 20,000 characters and 200 drafts with Arabic messages; 60 requests/min per address; logs: method, route template, draft id, status | `app/accounts/api.py`, `app/main.py` |
| Schema and RLS (reviewed, **not executed**) and the owner's steps with the 11 live checks (all NOT RUN) | `deploy/supabase/001_drafts.sql`, `deploy/supabase/README.md` |
| Browser: one quiet section «حسابك (اختياري)» inside «الخيارات والمسودة»; magic link; explicit «احفظ في حسابي»; list with open / rename / delete; JSON export; sign out; delete account; options follow the account; 409 choice; expiry keeps the text | `app/static/account.js`, `app/static/account.css` (loaded only when `/api/health` says the flag is on) |
| A local fake of Supabase Auth + PostgREST for the browser test (imitated RLS, not Postgres) | `scripts/fake_supabase.py` |

**Security decisions.**
- *Token storage:* the access token is kept in a JavaScript variable only — never `localStorage`, `sessionStorage` or a cookie set by script (the browser test asserts it). The refresh token in the magic-link fragment is discarded, and the fragment is removed from the address bar at once. **Trade-off:** a page reload means signing in again, and a session ends when the access token expires (1 hour). The magic link usually opens a new tab; that tab hands the session to the tab that asked for the link over a `BroadcastChannel` (memory to memory, matched by a random nonce carried in the link), so the writer's text stays where it was.
- *Future work (not built):* a server-side session endpoint that exchanges the refresh token for an `HttpOnly; Secure; SameSite=Strict` cookie scoped to that endpoint, rotates it on every use, and returns a fresh access token to memory; it needs CSRF protection (SameSite plus an Origin check) and a revocation path. Until then there is no "stay signed in".
- *Verification:* the server checks every token itself; PostgREST checks it again; RLS is the second guard on every row.
- *Isolation:* the user id comes only from the verified `sub`; ids in the body, query or path are ignored; every lookup is scoped by that id; a foreign, missing or malformed id gives the same 404.
- *Sign-out and deletion:* a JWT stays valid at the provider until it expires, so the server keeps an in-memory denylist (per instance, best effort) for a token after sign-out and for every token of a deleted account; on another instance a replayed token finds no rows.
- *Service-role key:* optional, server-only, used only to delete the auth identity and write a content-free `deletion_log` line; never sent to the browser or logged.

**Not built (each would be its own change):** "sign out everywhere" as a separate control (with memory-only tokens and no refresh, every browser's session already ends within the access-token lifetime; account deletion calls the provider's global logout); per-draft opt-in autosave; per-draft TXT export from the list (the existing «نزّل المقال (نص)» works after opening a draft); **re-import** of an export (acceptance test 7 cannot pass yet); an email confirming deletion; deleting rows and the auth user in **one** transaction (today: rows through PostgREST, then the auth user through the admin API; the foreign keys cascade if only the second step runs). Opening a saved draft restores its text; its saved decisions are kept in its record but are not re-applied — the writer audits again, as with a local draft.

**Acceptance tests (the Stage 2 list above):**

| # | Ran locally (4 Oct) | Against what | Needs the owner's project |
|---|---|---|---|
| 1 Guest unchanged | `ui_journey_e2e`, `ui_final_qa`, `ui_a11y_check`, `ui_workspace_e2e` pass with the flag off **and** with the flag on (no sign-in); `ui_account_e2e` checks the guest network log (flag off and on) | local servers; fake | yes, on the deployed service |
| 2 Isolation | through the API (ids guessed, `user_id` in body and query, replay after sign-out and deletion) | MemoryStore | **RLS directly against Postgres: not tested** (no database) |
| 3 Tokens | expired, not-yet-valid, wrong audience/issuer, `alg:none`, HS256 with the public key, tampered, unknown kid, missing sub | local ES256/RS256 keys, fake JWKS | yes |
| 4 Session | expiry mid-edit keeps the text and shows «لم يُحفظ: سجّل الدخول من جديد» | fake | yes; "sign out everywhere" not built |
| 5 Explicit save | nothing uploaded before «احفظ في حسابي» (network log) | fake | yes |
| 6 Deletion | no rows left, link refused, export 401 | MemoryStore; fake | yes |
| 7 Export round trip | export only | fake | re-import not built |
| 8 Conflict | 409 and a three-way choice with two pages | MemoryStore; fake | yes |
| 9 Limits | 20,001 characters, 201st draft, title, decisions size | MemoryStore | yes |
| 10 Accessibility | axe 0 on the account section and keyboard-only at 1366/390/320 | fake | yes; plus real screen readers (Stage 4) |
| 11 Backup restore drill | — | — | yes |

**Prepared page text for when the flag is ON** (the live `/privacy` and `/limitations` are **unchanged**, because the flag is off; publish these only together with turning it on, after the owner fills the bracketed parts and the legal review):

*`/privacy`, replacing «لا حسابات…» and adding a section «إن أنشأتَ حسابًا (اختياري)»:*

> الحساب اختياري، والكتابة والاقتراح والتدقيق تعمل كلها دونه. إن طلبتَ رابط دخول فإننا نحفظ لدى [مزوّد الخدمة: Supabase، في منطقة: …] عنوان بريدك، وما تختار حفظه بزر «احفظ في حسابي» فقط: نص المسودة وعنوانها وسجل قراراتها ونص آخر تدقيق، وخياري الاقتراح، وأوقات الحفظ. الدخول لا يرفع شيئًا من مقالك. رمز الدخول يبقى في ذاكرة الصفحة فقط، ولا يُكتب في متصفحك؛ إعادة تحميل الصفحة تعني الدخول من جديد. يمكنك تنزيل كل مسوداتك (JSON)، وحذف أي مسودة، وحذف الحساب كله من «الخيارات والمسودة»؛ يحذف ذلك مسوداتك وتفضيلاتك [وحساب الدخول نفسه]. النسخ الاحتياطية لدى المزوّد تبقى حتى تنتهي مدة احتفاظه بها ([٧ أيام في خطة Pro]). سجل الخادم يكتب معرّف المسودة ورمز الاستجابة فقط، لا نصها ولا رمز الدخول. المسؤول عن هذه البيانات: [الاسم القانوني]، للتواصل: [العنوان]. مدة الاحتفاظ بالحسابات غير النشطة: […].

*`/limitations`, one added item:*

> الحساب الاختياري يحفظ النص والقرارات كما هي، ولا يعيد تطبيق القرارات عند فتح المسودة: أعد التدقيق. لا يبقى الدخول بعد إعادة تحميل الصفحة. إن حُفظت المسودة نفسها من تبويبين، يُرفض الحفظ الثاني وتختار أنت النسخة التي تبقى.

---

## Stage 3 — Import, then OCR (separate PR from accounts and from the UI)

**Goal:** bring text that already exists into the editor. Imported or recognised text is always the writer's text to check and edit **before** the audit. Import and OCR never decide or correct a verse.

The order is fixed: **3.1 text files (no OCR) → 3.2 an Arabic OCR benchmark → 3.3 scanned PDFs and images**, and 3.3 starts only if 3.2 finds an acceptable engine.

### 3.1 TXT, DOCX and PDF with embedded text (no OCR, no upload)

- **Architecture: in the browser.** TXT is read with `FileReader`; DOCX with a vetted parser (for example mammoth.js) and a text-layer PDF with pdf.js, both pinned, self-hosted and run in a Web Worker. The extracted text is put into the editor as an ordinary paste. The server sees nothing until the writer audits, which keeps today's privacy statement true.
- **Controls on the file (proposal):**
  - accepted types `.txt`, `.docx`, `.pdf`, checked by their first bytes (not the extension or the browser's MIME type);
  - at most 5 MB per file and 50 PDF pages; a DOCX whose uncompressed parts exceed 20 MB is refused (zip-bomb guard);
  - encrypted or password-protected files are refused with a reason; embedded scripts, macros, links and images are ignored, never run or fetched;
  - the parser runs in a worker with a time limit (proposal: 10 s) and is stopped if it exceeds it;
  - the result is cut at the article limit (20,000 characters) with a visible note, never silently.
- **Retention and transfer:** none. The file stays in the browser tab; nothing is sent to us or to a third party by importing.
- **Arabic-specific risks to test:** presentation forms (U+FE70–FEFF) and visual (reversed) order in PDFs; lost spaces; kashida/tatweel; footnote numbers merged into words; Quran fonts mapped to private-use code points.
- **Normalisation:** to logical order and base letters before insertion, then a line in the editor («استُخرج النص من ملف؛ راجعه قبل التدقيق») when anything was normalised. A verse is never "repaired" against the Quran text at this step.
- **Acceptance tests:** a fixture folder of real-shaped files (Word with ﴿﴾ and diacritics, Word with tracked changes, a PDF exported from Word, a presentation-forms PDF, a reversed-order PDF, a password-protected PDF, a 20,001-character file, a renamed binary, a zip bomb); for each, the extracted text equals the expected text code point for code point, or the file is refused with a clear reason; no network request during import (Playwright); axe and keyboard runs on the import control.
- **Cost:** development only; check each parser's licence before adding it.

### 3.2 Arabic OCR benchmark (before any OCR reaches the interface)

- **Set:** at least 60 pages with the rights cleared to use them: newspaper columns, mosque bulletins, printed books, phone photos of print and screenshots of social posts; Quran quotations in Naskh and Uthmani fonts, with and without diacritics; ground truth typed and checked by two people.
- **Candidates:** Tesseract `ara` (self-hosted, open source); Google Document AI (Enterprise OCR); Azure AI Document Intelligence (Read); any other engine the team wants. Prices: Azure's page lists **500 free pages per month** on the free tier (read 4 Oct 2026); its paid per-page price and Google's did not render when read, so **no paid price is given here**.
- **Metrics:** character and word error rate overall; **inside Quran quotations** separately; diacritic error rate; the rate of "plausible wrong word" errors (an OCR word that is a different valid word); time and cost per page.
- **Exit test:** a written choice of engine, with numbers and the rejected options. If no engine reaches a word error rate inside quotations that a reviewer accepts, OCR stops here.

### 3.3 Scanned PDFs and images

```
browser ─(upload, only after an explicit notice naming where the file goes)─► FastAPI /api/ocr (memory only)
          ─► OCR engine (self-hosted worker, or the chosen cloud API in a fixed region)
          ◄─ text + per-word confidence
browser: the text goes into the editor as editable text, low-confidence words underlined, a banner «نص مستخرج آليًا — راجعه قبل التدقيق», nothing audited yet
writer edits ─► «دقّق الاقتباسات» (unchanged audit)
```

- **Never a silent verse correction.** OCR text is treated exactly as the writer's text. If OCR misread a Quran word, the audit reports a *difference* and proposes the correction for approval, as for any typo. The record marks the article as OCR-derived. A test makes sure no OCR word is ever changed to a Quran word without a decision card.
- **Upload controls (proposal):** PNG, JPEG, WebP and PDF only, checked by content; at most 10 MB and 10 pages per request; image dimensions capped before decoding (decompression-bomb guard); encrypted, corrupted and multi-hundred-page files refused with a reason; the request is rate-limited per address (and per account when Stage 2 is on); the OCR worker runs with no network access other than the chosen engine, a memory limit and a time limit; nothing is written to disk.
- **Retention:** our server keeps nothing after the response (checked with a tmpfs probe and log grep). With a cloud engine, the provider's retention applies under its terms and a signed DPA; the chosen setting is named on `/privacy`.
- **Third-party transfer:** with a cloud engine, the whole image or PDF goes to that provider in its region; images may contain far more than the article (names, faces, letterheads), and `/privacy` must say so before the flag is on. With Tesseract, nothing leaves our host.
- **Acceptance tests:** the benchmark pages end to end in the browser; low-confidence underlining matches the engine output; the audit runs only after an explicit action; every cap enforced; logs contain no text; cost per article measured on the deployed service.
- **Credentials and decisions needed:** the engine choice from 3.2; for a cloud engine, a billing account, a project or resource in a chosen region, a key or service account stored as a Render secret, and a signed DPA; for Tesseract, an instance with enough memory (not measured); who pays per page and the monthly page cap.

---

## Stage 4 — Hosting, monitoring, backups, privacy, rights and accessibility (release gates)

Each item below is a gate. A public "production" label needs all of them.

| Gate | What must be true | Evidence |
|---|---|---|
| Host | A paid always-on instance. Render's docs (render.com/docs/free, read 4 Oct 2026): a Free web service spins down after 15 minutes without traffic, takes about a minute to spin up, and a workspace gets 750 free instance hours a month. Render's paid instance prices did not render when read on 4 Oct, so **no price is given**; read render.com/pricing before buying. Memory at a 20,000-character audit is measured on the chosen instance. | `/api/health` build equals the released commit; a load test of 10 concurrent 6,000-character audits records p95 time |
| Domain and TLS | Own domain, HTTPS only, HSTS | header check |
| Security headers | CSP without `unsafe-inline` once the three fonts are self-hosted (SIL OFL), so a visit sends nothing to Google; dependency audit clean | `curl -I`, `pip-audit`, the page network log |
| Monitoring | An external uptime check of `/api/health`; error reporting that **scrubs article text**; an alert when the Quranpedia source is stale or unreachable, and when the model's 429 rate passes a threshold | an alert test fired once and recorded |
| Backups | Only when Stage 2 is on: daily backups, a restore drill each quarter | the drill record |
| Model data | A provider setting of zero data retention, or the model off (see 1.5); `/privacy` names the setting | a screenshot of the provider setting in the release record |
| Privacy | `/privacy` matches the code for every flag that is on; a named controller and a contact; PDPL review done if accounts or OCR are on | review sign-off |
| Rights | Written answers from Quranpedia (service use, attribution), and from Tanzil and Quran Foundation if their text or data are used. Drafts exist in `submission/RIGHTS_INQUIRIES_DRAFT.md`; **unsent**. Old commit SHAs still fetchable until GitHub Support acts (draft unsent). | the replies, filed |
| Accessibility | WCAG 2.2 AA review by a person using VoiceOver (iOS/macOS) and TalkBack on real devices, in addition to axe; Safari and Firefox on real phones | a review report; today only axe, keyboard runs and Playwright WebKit/Firefox exist |
| Interface sign-off | A first-time-writer study with at least 5 Arabic writers (not the author) on their own articles; the tasks, time and failures recorded | a study note. **Automated tests and assistant walkthroughs are not this gate.** |

---

## What a true live test needs (accounts, credentials and decisions that only the owner can provide)

Nothing below exists in the repository, and no assistant session can create it.

| For | Needed from the owner |
|---|---|
| A live model test of a release | Access to the Groq account (key already on Render); a decision on the plan and on zero data retention; agreement to make the **one** labelled call per release |
| Render production | A paid instance chosen and paid for; the commit to deploy chosen after review (a push to `main` deploys today) |
| Accounts (Stage 2) | The auth/database provider and region; a project; the anon key and JWKS in Render; a sender domain with SPF/DKIM; the controller's legal identity and contact; PDPL review; retention and age policies; terms for stored drafts; two test accounts that are not real people's |
| OCR (Stage 3.3) | The engine from 3.2; for a cloud engine, a billing account, a resource in a chosen region, a secret in Render and a signed DPA; a monthly page cap |
| Evaluation | A named Arabic/Quranic reviewer for the labels (1.1); a blind author for set C (1.2) |
| Rights and history | Sending the rights inquiries and the GitHub Support request (drafts unsent) |
| Interface sign-off | At least five Arabic writers, not the author, and their consent to record tasks and timings |

---

## The interface revision of PR #2 (`ui-editorial-2026-10`): what it does and does not settle

Done in the UI PR, 3–4 Oct:

- the empty page leads with the article sheet; the explanation is one sentence; the demonstration article is a secondary action under the sheet;
- the first verse insertion stops at the source's pause sign or before a new clause, says where it stops, and the next piece follows one action later;
- an approved correction strikes through only the writer's words that change and draws the source's text above where the change starts (the box keeps their text; the label stays inside the box and clear of the line above); the final review offers «تراجع عنه» on each approved change;
- the verse suggestion box never covers or pushes off-screen the line being typed, including on a screen made short by a phone's keyboard (it drops the full verse line there, keeping the words, the reference and «أدرج»);
- the phone's bottom bar follows where the writer is and does not cover the final review;
- an exact but common «possible» phrase waits behind the concrete decisions as «عبارات للتأكيد (اختياري)», is not counted as a quotation found, and is drawn lighter than a decision («تأكيد اختياري», no shading, its group closed while decisions wait, its card titled «العبارة»);
- the model's state (answered, failed, over the limit, or not configured) is named in a calm line, with detail behind disclosure.

It does **not** reduce the 1.2 noise (it changes order and counting only), does not settle any Stage 4 gate, and adds no sign-in, cloud-save, import or OCR control.

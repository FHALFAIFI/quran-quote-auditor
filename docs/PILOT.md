# Writer pilot: tester guide, reporting, metrics and operations

Status: written 5 Oct 2026 (challenge period) for a small, unmoderated pilot with a few Arabic writers on the public site
https://quran-quote-auditor.onrender.com. **No pilot result exists yet**: every number in §4 is a definition of what will be counted,
not a measurement. The moderated usability protocol (consent, scripted tasks, recording sheet) is a separate kit:
[WRITER_PILOT.md](WRITER_PILOT.md). The 2 Oct 2026 proposal for a pilot with a publishing team (always-on hosting, a zero-retention
model setting, label review first) is kept unchanged in [PILOT_PROPOSAL.md](PILOT_PROPOSAL.md) (with [PRODUCTION_ROADMAP.md](PRODUCTION_ROADMAP.md) Stage 4); none
of it is arranged.

## 1. What the tester is asked to do (about 15 minutes)

Send the tester this:

> **مهمة التجربة.** افتح https://quran-quote-auditor.onrender.com (قد يستغرق أول فتح نحو دقيقة لأن الخادم المجاني ينام).
> 1. اضغط «جرّب المقال التجريبي» واقرأ النتيجة.
> 2. اضغط «مسح» واكتب «قال تعالى: ﴿» ثم بداية آية تحفظها، وانظر هل تقترح الأداة تكملتها من المصحف.
> 3. ألصق مقالًا **منشورًا** لك أو نصًا كتبته للتجربة، أو استورده بزر «استورد نصًّا من ملف» (TXT أو DOCX)، ثم اضغط «دقّق الاقتباسات».
> 4. افتح كل اقتباس، وافتح رابط قرآنبيديا في واحد منها على الأقل، واعتمد التصحيح أو ارفضه، ثم جرّب «تراجع».
> 5. عدّل جملة في المقال بعد التدقيق، ثم اضغط «أعد التدقيق».
> 6. اضغط «إلى المراجعة الأخيرة» ثم «نسخ المقال المعدّل»، والصقه في محررك وقارنه بما قررتَه.
> 7. إن رأيت ما يستحق الإبلاغ فاستعمل «أبلغ عن مشكلة» أسفل الصفحة **بمثال قصير تكتبه أنت، لا بنص مقالك**.
>
> **لا تلصق مسودة غير منشورة أو سرية.** الأداة لا تحفظ مقالك على خادمها، لكن المقال (حتى ٦٬٠٠٠ حرف) يُرسَل إلى مزوّد النموذج اللغوي Groq، وقد يحتفظ به مؤقتًا (صفحة «الخصوصية»).

What the tester should see:

| Step | Expected |
|---|---|
| 1 | Four quotations; two deliberate mistakes (a wrong word, a wrong reference), each with a proposed source correction; the page says the article was written for the demonstration. |
| 2 | After «قال تعالى: ﴿» and two distinctive words, a box offers the next words with the surah and ayah, «من نص قرآنبيديا»; nothing is inserted until accepted. Very common openings («يا أيها الذين آمنوا») get no guess. |
| 3 | Every quotation in ﴿ ﴾ or « » is listed. An unmarked quotation may be listed, listed as needing review, or missed (§3). An imported file's text appears in the editor unchanged and is not audited until asked. |
| 4 | «مطابق للمصحف» only for wording equal to the Quranpedia text; a difference shows the source wording and a proposal; the link opens that verse at Quranpedia. Nothing changes until the writer approves; «تراجع» takes a decision back. |
| 5 | Quotations the edit touched are marked as edited; the recheck keeps the decisions on untouched quotations and says how many it kept. |
| 6 | The copied text is the writer's text with exactly the approved changes; the text in the editor stays as the writer wrote it. |
| 7 | The report form opens on GitHub (it needs a GitHub account). Without one, send the same fields to the person who invited you. |

A reload of the tab keeps the text and the decisions. Closing the tab loses them unless the writer chose «احفظ المسودة في هذا المتصفح»
(in «الخيارات والمسودة») or downloaded the article; the writer's original stays in their own editor or file, which the tool never touches.

## 2. Privacy guidance for testers

- Use published text, or text written for the test. Do not paste unpublished, confidential or personal material.
- What leaves the browser, and to whom: [/privacy](https://quran-quote-auditor.onrender.com/privacy). In short: the article goes to the
  tool's server only when audited (processed in memory, not stored or logged); up to 6,000 characters of it also go to Groq, whose
  terms allow retention for up to 30 days unless the service account has zero-retention enabled (not verified for this account);
  a verse suggestion sends at most 700 characters before the caret and 100 after.
- Reports are public GitHub issues. **Never paste the article**; write a short example that shows the same behaviour. The form
  (`.github/ISSUE_TEMPLATE/pilot_report.yml`) asks for that example, the steps, the expected and actual result, the browser and
  device, and whether a correction was approved.

## 3. Known limitations and known misses (tell testers before they start)

- **Detection is conservative.** Short unmarked quotations are often missed, notably two-word phrases of common words («خلق عظيم»,
  «مودة ورحمة») and an unmarked quotation with a changed word. The rule for unmarked two-word phrases found 18 of 36 on its held-out
  set, exactly its preregistered threshold of half; it must not be broadened without a separately defined precision and recall gate
  ([EVALUATION.md](EVALUATION.md), «Unmarked two-word quotations»).
- A partial quotation whose **first or last word** is wrong can be reported as matched with only a hint (EVALUATION, frozen-set misses).
- Ordinary prose that equals Quran words («في كل عام») can appear as an *optional* item; it is never counted as a quotation or changed
  unless the writer confirms it.
- **The model** (`qwen/qwen3.8-27b` on Groq) only proposes places to look; it never writes verse text or overrides the source check.
  Measured added-only gain: one true quotation in 54,056 characters; 9 of 195 calls failed. No general improvement is claimed. Each
  result says whether the model answered, failed, was skipped during a cooldown, or was not asked because the article is longer than
  6,000 characters.
- Hafs text from Quranpedia only; no other qira'at, no hadith, no grammar checking. The evaluation sets were written with AI help and
  are not reviewed by an independent specialist, so there is **no general accuracy figure**.
- Free hosting: the first request after 15 idle minutes can take about a minute. Tested in Chromium (desktop, 390 and 320 px) with
  shorter checks in Firefox and WebKit; not on Safari itself, real phones or a real screen reader.

## 4. Pilot metrics (definitions; none measured yet)

Counted from reports and, where a moderator is present, from the WRITER_PILOT recording sheet. Each count is reported with its
denominator and source; nothing is extrapolated.

| Metric | Definition | Source |
|---|---|---|
| Journey completion | testers who reached a copied revised article ÷ testers who started | tester's answer / moderator sheet |
| Wrong automatic fixes | text changed in the copy without the writer's approval, or an approved change whose wording is not the Quranpedia verse | reports («النص المنسوخ غير صحيح», «تصحيح مقترح خاطئ»), each reproduced |
| False «matched» | a quotation shown «مطابق للمصحف» whose wording or reference differs from the source | reports, reproduced on the synthetic example |
| Missed quotations | a Quran quotation in the tester's text that the audit did not list | reports, per tester |
| False optional suggestions | ordinary prose shown as a possible or optional quotation | reports and moderator sheet |
| Provider failures | results that say the model failed or was skipped, and `ai_recent.failed` / `rate_limited` on `/api/health` | `/api/health` (counters restart with the instance) and reports |
| Time to first decision | from pressing «دقّق الاقتباسات» to the first approve or reject | moderator stopwatch only; not collected in unmoderated use |

Any confirmed wrong automatic fix or false «matched» pauses the pilot until it is reproduced, fixed with a regression test and released.

## 5. Operations

### Checking the live service

1. `https://quran-quote-auditor.onrender.com/api/health`: `build` equals the released commit on `main`; for the model path
   `ai_configured` true and `ai_max_completion_tokens` 800; the key never appears. A health check makes no Groq call.
2. `…/api/health?deep=1` loads the Quran text if needed: `source_ok` true, `source.ayahs` 6236, `source.stale` false. If Quranpedia is
   unreachable, `source.last_error` names the error type and the results say an older cached copy was used.
3. Provider outcome: `ai_last_call.outcome` (`ok`, `failed` with `http_status`, `skipped_cooldown`, `never_called`) and the `ai_recent`
   counters since the last restart. One live audit costs one Groq call; leave at least 70 s after any other call on the same Groq
   account, and do not retry a refused probe.
4. Cold start: after 15 idle minutes the first request wakes the instance (about a minute); `source.instance_started` shows the restart,
   and the first audit after it downloads the text once.
5. Static files: compare the served `/`, `/static/*.js`, `/static/styles.css` and the trust pages with the commit (TEST_LOG release
   records do this byte for byte).

### Release gate

- CI on the pull request (`.github/workflows/ci.yml`): pytest on Python 3.12 and 3.14, the Node tests, the API script, eleven Chromium
  suites at 1366/390/320 px and the import suite in Firefox and WebKit, against a reduced-mode server that holds only the 36-verse test excerpt, with Quranpedia and Groq blocked.
- Locally, with the whole text: every `scripts/ui_*.mjs` suite (README «Tests»), `ui_import_e2e` in Firefox and WebKit,
  `ui_a11y_check`, `scripts/e2e_check.py`, and every saved evaluation set compared row by row (`eval/compare_runs.py`). Any new false
  «matched» or wrong automatic fix blocks the release.

### Rollback

Render deploys `main` about a minute after each push. To return to the last good release:

1. Find the last good commit (the previous `build` recorded in TEST_LOG, or `git log --first-parent main`).
2. Fastest: Render dashboard → the service → **Manual Deploy → Deploy a specific commit** → that hash; check `/api/health` `build`.
   This holds until the next push to `main`.
3. Lasting: a PR that reverts the bad commits (`git revert --no-edit <first-bad>^..<last-bad>`), CI green, then fast-forward `main`
   to it. Never force-push `main`; never move the tag `pre-challenge-baseline`.
4. Repeat «Checking the live service» and record the rollback in TEST_LOG.

## 6. Decisions only the owner can make

- Inviting testers, and whether anyone is named in a report.
- Enabling Groq zero-data-retention for the service account, or switching the model off for the pilot (`AI_PROVIDER=none` on Render).
- An always-on Render instance (removes the cold start; price not checked).
- Contacting Quranpedia or Tanzil (SOURCES.md says what is settled and what is open).

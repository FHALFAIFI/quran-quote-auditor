# مدقق الاقتباسات القرآنية — Quran Quotation Auditor

An Arabic, right-to-left **writing workspace** for people who quote the Quran. You write or paste an article (up to 20,000 characters);
when you start a verse after «قال تعالى» or inside ﴿ ﴾ it can suggest the next words **from the Hafs text served by [Quranpedia](https://quranpedia.net)**,
and when you ask for a check it compares the **wording** and the **reference** of every quotation with that text, proposes corrections taken only from it,
and lets you approve them one by one while the article stays on the page and editable. On a configured service, every audit of an article up to 6,000 characters attempts model-based location proposals. The model is never a source of Quran text.

**AI Challenge Serving Islamic Content 2026 — Track 4: knowledge and verification tools.**

| | |
|---|---|
| **Live demo** | https://quran-quote-auditor.onrender.com (Render Free sleeps when idle: one measurement after 18 idle minutes took 23 s for the first page, so allow up to a minute; open it, wait for the page, then audit) |
| **Source code** | https://github.com/FHALFAIFI/quran-quote-auditor |
| **Licence** | MIT (code). The Quran text is not included. See [SOURCES.md](SOURCES.md) |

> **Pre-challenge work.** Everything in this repository was built **before 4 October 2026**: the git tag
> `pre-challenge-baseline` marks the first baseline commit, and every later commit dated before 4 October (the Groq
> provider, the editor workflow, the unmarked-phrase search, the boundary rules, the AI-provenance rules, the Uthmani-script matching and the interface revision of 2 October) is also
> pre-challenge work. Only work committed during 4–6 October 2026 counts as challenge work.
> The **writing workspace** (verse suggestion while typing, editing and rechecking after an audit, the 20,000-character limit, the three trust pages) was built on **3 October 2026** and is also pre-challenge if committed before 4 October 09:00 Riyadh: the commit dates in `git log` and the CHANGELOG decide, not this sentence.
> See [BASELINE.md](BASELINE.md) and [CHANGELOG.md](CHANGELOG.md).
> Built by one participant with Claude Code as a coding assistant; Claude is not used at runtime.

## Who it is for, and what it changes

| Question | Answer |
|---|---|
| **Primary user** | An Arabic content editor or proofreader who prepares an article or social post that quotes the Quran (a publisher, a content team, a social-media desk). Not a general reader, and not a scholar. |
| **The task that creates the problem** | Before publishing, every quotation needs its wording, spelling and surah:ayah reference checked against a mushaf. It is usually done by searching each verse by hand, or by trusting text copied from somewhere else. A misquoted word or a wrong verse number is easy to miss and embarrassing to publish. |
| **What manual checking and generic tools leave unresolved** | Manual lookup is repeated for every quotation and easy to skip when the deadline is near. A general chat assistant can produce a verse that looks right and is not, and does not say how sure it is. Some tools check or correct verses (for example quran-validator and Qalam, SOURCES.md §6); I have **not** compared them with this app side by side, so I make no claim to be better. |
| **The exact benefit for the editor** | One review list for the whole article: each quotation next to the source verse, the exact word or reference that differs, and a plain statement of what is *not* settled. Every proposed change waits for the editor's approval; the revised text is copied only after that, with a printable record of what was changed and where the source is. |
| **What AI does, and what stays source-based or human** | A language model may *propose where* quotations are. All Quran text, references, verdicts and corrections come from Quranpedia's Hafs text through deterministic code. The editor approves or rejects each change and resolves everything marked uncertain. |
| **Evidence for each claim** | Small, author-written labelled sets and dated end-to-end logs (below, [docs/EVALUATION.md](docs/EVALUATION.md), [docs/TEST_LOG.md](docs/TEST_LOG.md)). No independent evaluation, no user study, no measured time saving. |
| **Resources to continue** | [docs/PILOT.md](docs/PILOT.md): a proposed pilot with one content team, what would be measured, what it costs to host and call the model, and what is still unknown. No partner, user, funding or organisation exists today. |

Value innovation, kept to four moves: **remove** unapproved automatic changes; **reduce** repeated manual checking (not measured, so no time-saving figure is claimed); **raise** source visibility and honesty about uncertainty (each verse links to Quranpedia; «غير محسوم» and «يحتاج مراجعة» are first-class states); **create** an approval-based path from the original text to a revised text and a review record.

## Writing workspace (3 Oct 2026)

| Before (build `fe7ef19`) | Now |
|---|---|
| The article was pasted, audited, then folded away; a second look meant re-pasting. 6,000 characters. | The article stays on the page, editable, with the quotations marked behind the words; click or move the caret into a mark and its decision opens beside it. Up to **20,000 characters** (about 3,000 words; measured below). |
| Nothing helped while writing. | After «قال تعالى» or ﴿ and the first words of a verse, a box under the caret offers the next words **from the Quranpedia text** with the surah and ayah. **Tab**, a click or a tap inserts; typing on, moving the caret or Esc dismisses. «لعبادتي» after «إلا» is shown as a *possible* correction «لعبادتي ← ليعبدون», never applied by itself; ambiguous openings list several verses and preselect none; a short excerpt is offered, the rest of the verse only on request. «أكمل من المصحف» (or Alt+Q) asks on demand. |
| A fresh audit reset every decision. | **Recheck** keeps a decision only for a quotation whose words, place and neighbourhood did not change; a quotation you edited is marked stale, loses its decision and says so. The copied text and the printable record always describe the latest text. |
| Drafts lived in the tab. | Saving a draft in the browser is an explicit button (plus delete and export); nothing is stored on the server. |
| No privacy or limits page. | Separate pages: [المصادر](app/static/sources.html), [الخصوصية](app/static/privacy.html), [الحدود](app/static/limitations.html) (served at `/sources`, `/privacy`, `/limitations`), linked from the header, the footer and the paste box. |

On a service with Groq configured, an audit of an article up to 6,000 characters automatically attempts the model. Longer articles, unavailable providers and failed model calls continue through source-based checks with a visible explanation. **The model is never involved in suggestions while writing.** The full short article is sent to Groq for audit proposals; see the privacy page before using the service with sensitive text.

## What it does

You paste an Arabic article or post. The app:

1. finds likely Quran quotations: marked ones (﴿﴾, {}, «» after a cue or before a reference), and unmarked phrases, shown as a *candidate* or as «قد يكون اقتباسًا قرآنيًا — يحتاج مراجعة» (*possible*). It also finds the surah/ayah reference written next to a quotation;
2. checks each quotation's **wording** and **reference** against Quranpedia's Hafs text;
3. shows one review list, with what needs the editor first: the quotation in the article, the source verse, the exact difference, the reference status and the action asked of the editor. A quotation copied in the **Uthmani script** of a mushaf site or app (`ٱلصَّلَوٰةَ`, `ءَامَنُوا۟`) is matched when its words are the source's words, and gets no correction ([docs/UTHMANI.md](docs/UTHMANI.md));
4. proposes **source-backed corrections** only when the source supports both the text and the location. The editor **approves or rejects each one**; a before/after preview and a copy button give the corrected text;
5. offers a printable **review record** («سجل مراجعة الاقتباسات») and a copy-only reply draft. The app never posts anything.
6. **imports an article from a file** («استورد نصًّا من ملف»; challenge period, 4 Oct 2026): a `.txt` (UTF-8, or UTF-16 with a byte-order mark) or a `.docx`, up to 5 MB, recognised by its first bytes and read **in the browser** by a Web Worker (`app/static/import.js`, no third-party library), never uploaded. The text goes into the editor like a paste, with a one-line notice of what was changed (only: byte-order mark, line ends, invisible control characters, Arabic presentation forms such as ﻻ → لا); nothing is audited and no Quran word is corrected until the writer presses «دقّق الاقتباسات». If the editor already has text, the writer is asked first (replace / cancel). From a `.docx`: the text as it reads with tracked changes accepted; footnotes and endnotes listed at the end under a rule, their reference marks removed from the body; headers, footers and comments left out; text formatted as hidden is read like any other. A text longer than the 20,000-character limit is refused whole, never cut. Refused with a reason: PDF (no PDF support yet), images, old `.doc`, `.docm`, password-protected or encrypted files, Windows-1256 text, corrupt files and zip bombs (20 MB uncompressed cap, checked while inflating). The worker is stopped after 10 s.

Optionally a language model (Groq) proposes *where* quotations may be. It is never a source of Quran text, references or verdicts.

## Try it (about two minutes)

1. Open https://quran-quote-auditor.onrender.com. **Render Free sleeps when idle**: Render says a spin-up takes about a minute (I measured 23 s once); wait for the page, and expect the first audit afterwards to take a few seconds more (the Quran text is downloaded once per instance).
2. Press **«جرّب المقال التجريبي»** on the empty page: one click loads the demonstration article (file: `app/static/samples/sample-demo.txt`) and audits it, announces «وجدنا ٤ اقتباسات؛ يحتاج اثنان إلى قرارك» and shows the first item that needs your decision **beside your article** (on a phone: above it). The card shows the quoted words inside their sentence, the likely surah and ayah with its Quranpedia link, then the exact change before its two buttons («غيّر إلى «يوفى»» / «أبقِ «يجزى»»); the full verse, the similarity percentage, the API links and the model/source notice sit under the details. After each decision the panel moves on to the next waiting item and says what it did, with «تراجع». The article has four quotations; **the two mistakes in it are deliberate misquotations written for the demo, not Quran text**:

| # | In the article | Expected result (deterministic; the model, if it answers, changes nothing here) |
|---|---|---|
| 1 | Ayah 2:153 in Uthmani script, copied letter for letter from Tanzil's text (credit below), reference «البقرة: 153» | «مطابق — رسم عثماني», reference matched, **no correction** (only an optional formatting offer) |
| 2 | Ayah 2:156 with full vowel marks, reference «البقرة: 156» | «مطابق حرفيًا», reference matched, nothing to do |
| 3 | «إنما **يجزى** الصابرون أجرهم بغير حساب» [الزمر: 10] | «اختلاف — أقرب موضع مقترح» (not a confirmed match); proposal: «يجزى» → «يوفى», taken from Quranpedia's 39:10; the reference stays «غير محسومة» until the wording is settled |
| 4 | «فإن مع العسر يسرا» [**الشرح: 6**] | words match 94:5; reference «خاطئة»; proposal: «الشرح: 6» → «الشرح: 5» |

3. Decide both items. The panel then leads to **«المراجعة الأخيرة قبل النسخ»**: what will be copied, each change shown in its sentence (old struck, new marked), and every quotation still not settled; only there is «نسخ المقال المعدّل». Nothing changes without your approval; the page says it covers the quotations found, not the whole article. `tests/test_demo_article.py` pins these results.
4. «تفاصيل هذا التدقيق» (under the status line) says whether the AI model answered, what it proposed and when the Quran text was fetched. If Groq's free tier answers 429 or is unavailable, a warning says so and the audit continues without the model. On the live demo the model has so far proposed nothing for this kind of post; the details then say so, and the result is the deterministic one.

Earlier samples are still in the list («مثال: العلم», «مثال: الصبر (أخطاء شائعة)», «مثال: مقال بلا أقواس») and exercise unmarked quotations and the "possible" tier. The Uthmani quotation in the demo is a verbatim copy of **Tanzil** text (Tanzil Project, https://tanzil.net, CC BY 3.0, version 1.1); the page footer carries the credit and link.

## What it does not claim

- It does **not** say an article or post is "verified" or ready to publish. It checks only the quotations it found.
- **Detection is not complete.** Short unmarked misquotations may be only «possible» or missed; ordinary prose can reuse Quran words and be shown as «possible»; the start or end of an unmarked quotation may need the editor's confirmation (the card asks «أين يبدأ الاقتباس؟» / «أين ينتهي الاقتباس؟» and settles it in one tap); a model can fail (see "AI use"). The editor can highlight any phrase and check it by hand.
- A «possible» phrase is **not** a verified quotation, and gets no replacement text until the editor confirms it and picks the verse.
- **Uthmani script is recognised only as far as the documented rules go** ([docs/UTHMANI.md](docs/UTHMANI.md)). Before the change on 2 October 2026 (pre-challenge) a correct Uthmani quotation was shown as «difference» or «uncertain» and could get a wrong correction (30 of 41 on the frozen Uthmani set). Now 37 of those 41 read «matched», and none of the other 8 wrong quotations is. The rules explain 99.2% of the verses of the Tanzil Uthmani text (SOURCES.md §1b) and 98.8% of Quranpedia's Uthmani edition; about 50 rare spellings are not covered and read «uncertain» with no replacement. The held-out set was no longer untouched after its first run, and it contains label errors, so these figures are not an independent accuracy rate. A genuinely changed word, a different vowel or a wrong reference in Uthmani text is still flagged.
- It does not proofread Arabic, interpret verses, translate, or give religious rulings.
- **No measured accuracy.** The only numbers are from small, author-written, labelled sets (below). They are not independent measurements, and the labels are still awaiting review by an Arabic specialist ([docs/LABEL_REVIEW.md](docs/LABEL_REVIEW.md)).
- **No measured AI benefit.** On the live demo sample the model proposed the same 7 quotations that the deterministic path found without it. In the labelled sets, with the phrase search in place, it added one quotation (a 3-word misquotation) in one run on one set, and none on the other two.

## Results observed so far (all pre-challenge, no AI; code as of `cccd084`)

Rerun on 2 October 2026 with `eval/run_eval.py --mode fallback`; labels unchanged, checksums verified. For the first three sets the **rows are byte-identical to the run on `976395e`** (before the Uthmani layer), so the Uthmani layer changed nothing for plain-spelling or imla'i-vocalised text. Raw files in `eval/results/`.

| Set (author-written, small) | Quotations | Found | Notes |
|---|---|---|---|
| Main, 14 articles (development data) | 28 | 27 | 0 false "matched" wording; 6/6 wording errors given a correct source-backed fix; 0 corrections proposed for correct text |
| Held-out, 4 articles (development data) | 6 | 6 | 3 of 6 read "uncertain" (boundary not settled) |
| Frozen, 49 articles (written and checksummed before the search was built) | 32 unmarked | 30 | 2 missed; 12 of the 30 found read "uncertain"; 2 of 28 non-Quran texts shown as «possible», none shown as confirmed; 0 misquotations reported "matched" |
| **Uthmani, 50 articles** (excerpts of the Tanzil Uthmani text, SOURCES.md §1b; written and checksummed before any Uthmani code; **no longer untouched after its first run; the labels were not edited after the freeze and 4 of them disagree with the program: `u32`, `u09`, `u10`, `u19`, see docs/UTHMANI.md**) | 49 (41 correct, 8 wrong) | 48 | correct: 37 «matched», 2 «uncertain» (boundary rule), 1 «difference» (label error: the quote omits a word), 1 not found (formula); wrong-labelled: 8 «difference», **0 «matched»**; wrong references flagged 4/4; automatic corrections given to correct quotations **30 → 1** (that one is the label error). Before the change: 1 «matched», 30 corrections |
| **Long articles, 10 (8,060–14,700 characters; AI-written, unreviewed; run once, no AI)** (`eval/articles_long_20261003.json`) | 191 (95 unmarked) | 186 (90 of the 95 unmarked) | 0 misquotations reported "matched"; 0 wrong corrections; 15 extra «possible» items in 102,356 characters; 4 references "matched" where the label says "missing" (the prose names the right surah: label vs documented policy, docs/EVALUATION.md) |
| **Verse suggestion, set B (blind-authored by a subagent, run once, no AI)** (`eval/suggest_cases_b_20261003.json`) | 76 expected suggestions, 39 expected silences, 14 ambiguous | 71 suggestions right | 0 of 39 false suggestions; 0 confident single choice on 14 ambiguous; corrections 19 of 22, all shown as «possible», none as exact. Development set A: 74/76, 0/39, 22/22 (rules were changed after its first run; docs/EVALUATION.md) |

Costs of the cautious rules: many correct unmarked quotations after prose read "uncertain" and need one click to confirm.
Ordinary Islamic-topic prose produces about 2–3 «possible» items per 1,000 words (Arabic Wikipedia sample, local only). Details, runs that did not count, and limits: [docs/EVALUATION.md](docs/EVALUATION.md). Dated end-to-end logs, including the live Render checks: [docs/TEST_LOG.md](docs/TEST_LOG.md).

---

## ملخص بالعربية

أداة تساعد المحررين والمراجعين على التحقق من الآيات المقتبسة في المقالات العربية القصيرة.
تستخرج الأداة الاقتباسات المحتملة وإحالاتها، ثم تقارنها بنص مصحف حفص من «الموسوعة القرآنية»
(Quranpedia)، وتعرض لكل اقتباس ما يلي:
- حالة الألفاظ: مطابق (حرفيًا، أو بتجاهل التشكيل، أو بعد توحيد الرسم)، أو اختلاف، أو غير محسوم.
- حالة الإحالة: مطابقة، أو غير مذكورة، أو خاطئة، أو غير محسومة.

دور الذكاء الاصطناعي محصور في **اقتراح مواضع الاقتباس** فقط. لا يُعتمد عليه مصدرًا لنص القرآن
ولا حكمًا على الصحة. وكل مطابقة تقريبية تُعلَّم «يحتاج مراجعة»، ولا توصف أبدًا بأنها «مطابقة».

### What "verified" means here

- **Verified** refers only to a quotation's **wording** and **reference**, checked by deterministic code
  against the Hafs text from Quranpedia. Every Quran word, surah/ayah number and correction shown comes
  from that text.
- **AI only proposes candidate quotations** (where a quotation might be). It never supplies Quran text, a
  reference or a verdict, and a candidate that is not literally in the article is discarded.
- **A model's proposal is not evidence that a span is a Quran quotation.** A span that only the model proposed
  is graded with the same deterministic rules as an unmarked span found by the phrase search: an exact,
  distinctive phrase is a "candidate"; a short or common phrase, a formula, a phrase whose words differ from the
  text, or ordinary prose is only a "possible quotation", shown with no replacement text until the editor confirms
  it. It counts as established only when the writer's own reference points at the matched verse or a lead-in such as
  «قال تعالى» comes right before it. The model never raises a tier the phrase search already assigned.
- **Provenance is per finding.** "Proposed by the model alone" is shown only for a finding that would be absent
  without the model; when a marker or the phrase search found the same span, the card says the model proposed it
  too, and the audit banner counts both numbers (`ai.added_only`, `ai.also_found`).
- **A model span never replaces a finding the program made.** If it overlaps a marked quotation, the editor's own
  selection or a phrase-search hit without being the same span (wider, narrower or shifted), that finding keeps its
  span, tier, verdict and proposed changes exactly as without the model, and the model's span is shown beside it
  (`detection.ai_role: "overlap"`, `detection.ai_spans`, `ai.overlapped`). A model span that overlaps nothing the
  program found is still its own "possible" finding.
- **AI status is reported per audit.** If the model does not respond (rate limit 429, timeout, bad key or
  bad JSON), the result says so, the deterministic fallback is used, and nothing is labelled as found by AI.
  "Configured" (a key is set) is never presented as "working".
- An approximate (fuzzy) match is never called verified. The app never says the whole article is verified.

---

## How it works

```
article ──► candidate extraction ──► locate in article ──► attach reference ──► verify ──► propose fixes ──► editor approves ──► revised article
            │ AI provider (Groq or     (reject anything      (regex parser,       (Quranpedia    (source words     (browser only)      + review record
            │   Gemini, one per audit)  not literally          nearest quote)       Hafs text,     only; none if
            │ marked ﴿…﴾ {…} «…»        present)                                   deterministic) span ambiguous)
            │ unmarked phrase search (seed-and-extend over the word index)
            │ manual highlight (POST /api/phrase, no AI)
```

| Stage | What it does | Trust |
|---|---|---|
| **AI extraction** (`app/extraction/groq.py`, `gemini.py`) | The model returns JSON `{candidates:[{quote, reference_text}]}` copied from the article (Groq: strict `json_schema`). | Untrusted. Each quote is re-located in the article (diacritic- and spelling-insensitive); the finding's text is always the article's own substring, and anything not found is discarded and counted. |
| **Marked extraction** (`app/extraction/marked.py`) | ﴿…﴾ (in either order), {…}, and «…» / "…" / ((…)) when preceded by a cue such as «قال تعالى» or followed by a reference. | Deterministic. |
| **Phrase search** (`app/phrases.py`) | Unmarked phrases of ≥ 3 words that occur in the Quran after normalization, plus near matches (a word substituted, added or left out, or spelled slightly differently). Seed-and-extend over the existing word index; no phrase index is built. | Deterministic. A *detection* only: it says where a Quran phrase may be and how sure it is that a quotation was meant (`candidate` / `possible`); the verifier then compares with the source. |
| **Reference parser** (`app/references.py`) | `البقرة: 255`, `[البقرة ٢٥٥]`, `سورة البقرة، الآية 255`, `الآية 255 من سورة البقرة`, `2:255`, ranges, surah-only, common alternative surah names. Range-checked against verse counts. | Deterministic. |
| **Verifier** (`app/verifier.py`) | Exact search at three normalization levels, fuzzy alignment when nothing exact exists, word diffs, and reference checks. | Deterministic. Quranpedia text only. |
| **Corrections** (`app/verifier.py` `propose_wording`, `app/corrections.py`) | Turns a verdict into proposed changes with exact character offsets. | Deterministic. Replacement words come only from Quranpedia; see "Editor workflow". |
| **Revision** (`app/static/revision.js`) | Applies only the approved changes in the browser. | No server state. Refuses a change whose original text is no longer at its offsets, and overlapping changes. |

### Unmarked phrases: candidate, "maybe", or hidden

Finding a phrase and verifying it are separate steps. Each finding has a **detection** (how it was found and how sure we are that a quotation was meant) and a **verdict** (how the words compare with the Hafs text).

| Shown as | When | What the editor gets |
|---|---|---|
| مرشَّح لاقتباس قرآني (*candidate*) | Exact match (after normalization) of a distinctive phrase: at least 4 words of words that are rare in the Quran (or 5+ words), not an everyday formula, not introduced as hadith/du'a/proverb | The normal card and source-backed proposals (each needs approval). Several verses → the choices are listed and none is picked. |
| قد يكون اقتباسًا قرآنيًا — يحتاج مراجعة (*maybe*) | A short or common exact phrase, a near match (one or two words differ), a formula after a Quran cue, or a phrase after a hadith/du'a/proverb cue | The match is shown, but the green «matched» chip is replaced by the «maybe» label and **no replacement text is proposed** until the editor confirms it is a Quran quotation and picks the verse. The reply draft never names an unconfirmed «maybe». |
| Not listed | Exact phrases too short or too common to tell from ordinary Arabic, and bare everyday formulae (بسملة، «إن شاء الله»، «رضي الله عنه» …) | Counted in a notice. The editor can highlight the phrase in the text box and press «افحص المقطع المحدَّد», then choose its verse. One- and two-word phrases may be impossible to place reliably without context. |

Known gap: the search cannot know where a writer's quotation ends, so a wrong **last** word looks like prose after the quotation. The card then shows the verse's next word beside the article's next word, with no verdict.

### Matching levels (shown to the user)

| Level | Meaning |
|---|---|
| `literal` — مطابق حرفيًا | Same letters **and** diacritics. Only Quranic pause/sajdah/hizb marks, tatweel and invisible characters are ignored. |
| `diacritics` — بتجاهل التشكيل | Same letters. The article's diacritics are absent or partial but never contradict the source. |
| `normalized` — بعد توحيد الرسم | Differs only by simplified letter forms (for example ا for أ/إ/آ, ي↔ى, ه for ة). Each change is listed. |
| difference (diacritics / letters) | Letters match a unique verse, but a diacritic contradicts the source (e.g. «يخشى اللهُ»), or a hamza seat changed (إن ↔ أن). |
| difference (`fuzzy`) — أقرب موضع مقترح | Not found exactly, so the closest passage is shown with a word diff. **Always flagged “needs human review”, never shown as verified.** |
| uncertain — غير محسوم | Fewer than 3 words, found in several verses without a disambiguating reference, not found, or source unavailable. **Also:** for an unmarked span chosen by the program or the AI, when the quotation's start or end is not settled (the article word touching the span differs from the verse's neighbouring word and no punctuation, lead-in or reference marks the boundary). That means the boundary could not be established, not that the wording is wrong; the editor confirms or adjusts it. Brackets and manual highlights are never questioned. |

### Reference statuses

`matched` · `missing` · `incorrect` (wrong verse, wrong surah, or a number outside the surah's range) ·
`uncertain` (the reference covers only part of a multi-verse quotation, the location is fuzzy, or the source is unavailable).

### Editor workflow: proposals, approval and the revised article

A correction is **proposed only when the source supports both the text and the location**:

| Situation | What is proposed |
|---|---|
| Exact match at one location, but a letter form differs significantly (e.g. «إن» for «أن») | Replace only the differing word(s), written in the article's own style (no diacritics added to an unvocalized quote). |
| Exact letters, but a written diacritic contradicts the source | Replace only the conflicting word(s); labelled «تصحيح التشكيل» with a warning that printed mushafs differ in some marks. |
| Correct quote without diacritics | **Not an error.** An optional «ضبط كامل بتشكيل المصحف» change is offered as an explicit editor choice, covering only the quoted words. |
| Not found exactly (fuzzy), unique closest passage, similarity ≥ 0.8 — or ≥ 0.75 with a reference that points to it | Minimal word edits (replace / insert / remove) inside the excerpt. The excerpt is never expanded to the whole verse. |
| Fuzzy with several similar verses and no ayah-level reference that singles one out, a reference that points elsewhere, low similarity, a short phrase, a repeated phrase, or source unavailable | **No replacement.** The card says «لا يُقترح تصحيح تلقائي» and why, and the quotation stays marked unresolved. |
| Wrong reference, or a reference that covers only part of a multi-verse excerpt, when the location is certain | Replace only the reference text, keeping the writer's style (digits, «سورة … الآية …», numeric `2:255`). |
| Missing reference, location certain | Optional insertion of «[السورة: الآية]» after the closing bracket. |

Each change carries its offsets, the original and replacement text, the reason, the surah/ayah and
Quranpedia links. In the browser the editor approves or rejects each one. Nothing changes without
approval, and every character outside approved changes (prose, punctuation, line breaks, even markup)
is preserved. Decisions live only in that tab (memory + `sessionStorage`); nothing is sent to or stored
on the server. The preview marks deletions, insertions and **unresolved quotations**. The app never
states that the whole article is verified or ready to publish.

**Review record.** «سجل مراجعة الاقتباسات» is a print/PDF view generated in the browser: approved
changes (original, replacement, reason, surah/ayah, source link), rejected and undecided changes,
unresolved items, the source retrieval time, and whether AI extraction actually ran on this audit.
It is labelled as an editorial aid, not a certificate of religious or textual correctness.

**Reply draft for a social post (optional).** Under the editor card, «مسودة رد على منشور» builds a short,
editable Arabic reply from the *approved* corrections and the unresolved quotations only, ending with
«هذا فحص للاقتباسات التي رُصدت فقط، وليس حكمًا على المنشور كله». The editor copies and posts it manually;
the app never posts anything. An X bot is deliberately not built (see docs/CONTINUATION.md).

---

## Run locally

Requirements: Python 3.12+ (Node.js is optional: it runs the revision-engine tests and the browser scripts).

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt      # runtime-only: requirements.txt

# optional: enable AI extraction (see "AI use")
cp .env.example .env        # then edit .env; it is git-ignored
set -a; source .env; set +a

uvicorn app.main:app --reload --port 8000
# open http://localhost:8000
```

The first audit downloads the Hafs text from Quranpedia (one request, about 1.6 MB). Without `GROQ_API_KEY` or `GEMINI_API_KEY` the app runs in
**reduced mode** and a yellow banner says so: marked quotations are checked and the rest of the text is searched for phrases of 3 or more words
that match the Quran, so **some short unmarked quotations can still be missed**; the editor can select them by hand.

### Environment variables (names only; see `.env.example`; set secrets in the host's dashboard or a git-ignored `.env`, never in the code)

| Variable | Purpose | Default |
|---|---|---|
| `AI_PROVIDER` | `auto` (Groq if its key is set, else Gemini if set, else none), `groq`, `gemini`, or `none` | `auto` |
| `GROQ_API_KEY` | Groq key (secret). Without it Groq is not used | unset |
| `GROQ_MODEL` | Groq model; the live demo uses `qwen/qwen3.8-27b` (a Groq *preview* model) | `qwen/qwen3.8-27b` |
| `EXTRACTION_PROMPT` | prompt version in `app/extraction/prompts.py` | `v2` |
| `GROQ_MAX_COMPLETION_TOKENS` | output tokens the app asks Groq to reserve per request. **If your Groq account limits this model to 1,000 output tokens/minute (the free tier did for us), set `800`**; see the note below. 512 was tried earlier and may truncate longer answers | 4096 |
| `GROQ_REASONING_EFFORT` | advanced Groq tuning; leave unset | unset |
| `GEMINI_API_KEY`, `GEMINI_MODEL`, `GEMINI_FALLBACK_MODELS` | optional alternative provider; never succeeded in our tests (503/429) | unset |
| `AI_TIMEOUT_SECONDS`, `AI_ATTEMPT_TIMEOUT_SECONDS`, `AI_COOLDOWN_SECONDS` | AI time budget and pause after a failure | 12, 8, 60 |
| `MAX_ARTICLE_CHARS`, `AI_MAX_ARTICLE_CHARS`, `MAX_CANDIDATES` | audit input limit; the longest article the model is asked about (Groq's free tier refuses larger requests; longer articles are audited without it); passages listed (more are reported, not dropped silently) | 20000, 6000, 150 |
| `RATE_LIMIT_PER_MINUTE`, `SUGGEST_RATE_LIMIT_PER_MINUTE` | per-IP allowance (per instance) for audits / phrase checks and for verse-suggestion lookups | 10, 240 |
| `SOURCE_TIMEOUT_SECONDS`, `QURAN_CACHE_DIR`, `QURANPEDIA_CONTACT` | Quranpedia timeout, cache directory, optional contact e-mail added to the User-Agent as Quranpedia's policy requests | 20, temp dir, unset |

> **Note on the Groq output-token limit (3 Oct 2026).** Groq answered HTTP 429 («Request too large … output tokens per minute (OTPM): Limit 1000, Requested 1100–1994») to audits of the live service on 30 Sep–3 Oct 2026 while the app reserved the default 4096 output tokens per request; Groq's own «Requested» figure was never 4096 and its estimate is not documented, so the cause is observed, not proven. On 3 Oct 2026 `GROQ_MAX_COMPLETION_TOKENS=800` was set on Render and two live audits of the demonstration article (one audit, one video take) both answered HTTP 200 (`ai.outcome` ok, 4 proposed, 4 located, 0 added by the model). That is two calls, not a controlled test. The demonstration article needs about 75–90 output tokens, but an answer longer than the cap is cut off and the whole AI result is dropped (the deterministic result stands, AI is skipped for the cooldown), so an article with many quotations may need a higher value. Without a model the app still works and the audit is deterministic. See `docs/TEST_LOG.md` (3 Oct 2026 note) for the record.

### Tests

```bash
python -m pytest -q                      # 415 tests offline (a 36-verse excerpt in tests/fixtures/), including the Node tests of the revision engine if node is installed;
                                         # tests/test_phrases_full.py also runs against the real text if a local copy is cached (else skipped)
node --test tests/revision.test.mjs      # the revision engine alone
node --test tests/import.test.mjs        # file import (.txt/.docx): 35 fixtures (33 built in code, 2 made by LibreOffice and textutil) (tests/fixtures/import/), code point for code point or the refusal

# browser end-to-end (Playwright installed in any scratch dir, not a project dependency)
NODE_PATH=/path/to/scratch/node_modules node scripts/ui_journey_e2e.mjs --shots ./shots   # the judge's first journey at 1366, 390 and 320 px: starts its own server with AI off
NODE_PATH=/path/to/scratch/node_modules node scripts/ui_e2e.mjs --shots ./shots   # editor workflow, record, XSS, reload (own AI-off server; --server URL for yours)
NODE_PATH=/path/to/scratch/node_modules node scripts/ui_long_e2e.mjs --shots ./shots   # 5,809-character article, review sequence, keyboard focus vs the bottom bar, 320 px, URLs in Arabic text, slow/failed server, no findings, model failed
NODE_PATH=/path/to/scratch/node_modules node scripts/ui_suggest_e2e.mjs --shots ./shots   # verse suggestion while typing: when it speaks, Tab/click/tap, Esc, correction, several verses, stale answers, RTL insertion, IME, 390/320 px
NODE_PATH=/path/to/scratch/node_modules node scripts/ui_workspace_e2e.mjs --shots ./shots   # edit after an audit, stale decisions, recheck, copy/record of the latest text, drafts, a 17,500-character article (typing latency, navigation)
NODE_PATH=/path/to/scratch/node_modules node scripts/ui_import_e2e.mjs [--browser firefox|webkit]   # every import fixture through the real file input at 1366/390/320 px: exact text, notice, refusals, no network request, no audit, keyboard, axe, the 10 s limit
NODE_PATH=/path/to/scratch/node_modules node scripts/ui_crossbrowser.mjs   # the same journey in WebKit and Firefox as well (FIREFOX_BIN=<path> if only another Firefox revision is cached)
python scripts/measure_length.py [--url https://host]   # audit time, memory and response size at 6,000-20,000 characters (--url never calls a model)
python eval/run_suggest_eval.py eval/suggest_cases_b_20261003.json --tag mine   # score the verse-suggestion sets (no AI)
NODE_PATH=/path/to/scratch/node_modules node scripts/ui_a11y_check.mjs   # axe-core (WCAG 2.2 AA + best practice) over 14 states (incl. the suggestion box, the stale state and the three trust pages) at 320/390/1366 px (needs axe-core installed beside playwright)
NODE_PATH=/path/to/scratch/node_modules node scripts/ui_phrase_e2e.mjs --shots ./shots   # unmarked-phrase workflow: starts its own server with AI off (no Groq call possible)
NODE_PATH=/path/to/scratch/node_modules node scripts/ui_phrase_e2e.mjs --live-ai https://<service> # opt-in: ONE audit = one Groq call; exit 2 = model did not answer
NODE_PATH=/path/to/scratch/node_modules node scripts/ui_boundary_e2e.mjs --shots ./shots   # uncertain-boundary question: confirm, take the word in, choose the words, undo
NODE_PATH=/path/to/scratch/node_modules node scripts/ui_async_navigation_e2e.mjs   # a slow phrase check finishing after the writer opened another quotation (own AI-off server)
python scripts/measure_resources.py [--server]       # startup time and peak memory in fresh processes (needs a cached Quran text)
python eval/validate_phrases.py                       # the frozen phrase set against the Hafs text
python eval/run_eval.py --mode fallback               # labelled evaluation without any AI (--cases eval/heldout.json | eval/phrases_frozen.json)
python scripts/e2e_check.py http://localhost:8000   # API checks, samples, files that must not be served
```

## Deploy (Render Free; the live demo)

The live demo runs on Render's free web service from this repository's `main` branch: build `pip install -r requirements.txt`, start
`uvicorn app.main:app --host 0.0.0.0 --port $PORT`, health check `/api/health`, Python 3.12 from `.python-version`.
Exact settings, environment-variable names and the checks to run afterwards: [docs/RENDER_DEPLOY.md](docs/RENDER_DEPLOY.md); a Blueprint is in `render.yaml`
(its secret values are entered in the dashboard only).
A first Vercel deployment (pre-challenge baseline) was blocked from deploying newer commits, so Vercel is not used for the current demo; `vercel.json` is kept only for that route.

## AI use

- **What it does.** One request per audit goes to Groq (`qwen/qwen3.8-27b`, strict JSON schema). The model returns the passages that look like quotations, copied from the article, and any nearby reference text. Each passage is then re-located in the article (anything not literally there is discarded) and graded by the same deterministic rules as any other candidate.
- **What it never does.** It never supplies Quran text, a reference, a verdict or a correction. All of those come from the Hafs text.
- **When it fails** (rate limit 429 on Groq's free tier, timeout, bad key or bad JSON) the result shows a visible notice, the deterministic path still runs, and nothing is labelled as AI-found. After a failure the app skips AI for 60 s (120 s after a 429), and a later notice says it is waiting.
- **Which key.** The deployer supplies `GROQ_API_KEY` as an environment variable on the host. Do not paste keys into issues, commits, screenshots or videos. If a key is exposed, revoke it at https://console.groq.com/keys and create a new one.
- **Check.** `/api/health` shows `ai_configured`, the provider, and `ai_last_call.outcome` (`never_called`, `ok` or `failed`); "configured" is not "working". For an external uptime monitor it also gives `source_ok` (the Quran text is loaded and not a stale copy; `?deep=1` loads it first) and `ai_recent` (counts of model calls, failures and 429s since the process started; counts only). How to point a monitor at it: `docs/RENDER_DEPLOY.md`.
- **Replacing the provider.** Implement `ExtractionProvider` (`app/extraction/base.py`: `available()` and `extract(article)`), register it in `get_provider()` and select it with `AI_PROVIDER=<name>`. The rest of the pipeline treats provider output as untrusted. A Gemini adapter exists (`app/extraction/gemini.py`) but no real Gemini call has succeeded in our tests.
- Groq lists `qwen/qwen3.8-27b` as a **preview** model that can change or be withdrawn; `GROQ_MODEL=openai/gpt-oss-20b` is a production model with strict JSON schema.

---

## Quran source, caching and outages

- Source: Quranpedia API v1, Hafs mushaf `GET https://api.quranpedia.net/v1/mushafs/1`,
  a single documented request that returns all 6,236 verses.
- A process keeps the text in memory for up to 24 h, matching the API's own `Cache-Control`,
  so Quranpedia's ongoing corrections arrive within a day. It also writes a copy to the
  machine's temp directory. The app does not re-publish or export it, and the whole text is not committed to Git; the only copy in the repository is a 36-verse, credited test fixture (`tests/fixtures/hafs_subset.json`, see SOURCES.md §1).
- If a refresh fails, a copy younger than 7 days **on the same machine** is used with a
  visible warning. Otherwise every quotation is marked *uncertain — source unavailable*.
  The app never substitutes AI-generated or hard-coded Quran text.
- **Actual limits on Render Free (and any hosting without shared storage):** memory and the temp directory belong to one instance and disappear when it restarts or sleeps. In practice:
  - every cold instance fetches the full text once (locally: about 1.2 s including the index build; on Render, one measurement after 18 idle minutes took 23 s for the first page, and the first audit after that adds the one-time download, a few seconds) and warm requests reuse it;
  - the 24 h refresh and the 7-day fallback only apply while the same instance stays alive;
  - a cold instance that cannot reach Quranpedia reports the source as unavailable rather than guessing.

  Quranpedia serves this endpoint through Cloudflare with a 24 h CDN cache, which softens origin outages. One retry is made for transient network/5xx errors.
  `/api/health` shows `loaded_from` (`network` or `disk`), the text's age and the instance start time. A cross-instance cache would need an external store; it is deliberately not used.
- Every source verse links to Quranpedia (`api.quranpedia.net/embed?surah=…&ayah=…`)
  and to its API record. Attribution appears in the page footer.
- Test and evaluation data in Uthmani script (never read by the app): **Quran text: Tanzil Project, https://tanzil.net** (Tanzil Quran Text, Uthmani v1.1, CC BY 3.0; verbatim, with its notice kept inside the data files; see SOURCES.md §1b).

## Security, privacy and hosting limits

- Input is capped at 20,000 characters (the request body is capped too, counted as it arrives, so a chunked upload without `Content-Length` is refused with 413 as well), with a per-IP rate limit of 10 audits/phrase checks and 240 suggestion lookups per minute per instance (best effort). Suggestions send only the words around the caret (700 before, 100 after) and only on a Quran cue, an open quotation mark, an explicit request or the writer's own opt-in. What goes where is on the [privacy page](app/static/privacy.html).
- **Privacy.** Articles are processed in memory and never written to disk or logged by the app; error handlers log only the exception type and the response does not echo the article. As defence in depth, `app/logging_safety.py` removes any run of more than 20 Arabic letters from every log record (message, arguments, traceback, percent-encoded query strings) before it is written. An imported file is read in the browser and never uploaded; its text is sent only when the writer audits, like typed text. Decisions on corrections stay in the browser tab (memory + `sessionStorage`). **When AI is on, the article text is sent to Groq** (US servers) to propose quotation locations; Groq states that it does not retain inference data by default, except up to 30 days for reliability and abuse monitoring (https://console.groq.com/docs/your-data, read 30 Sep 2026), and Zero Data Retention is an organisation setting. Do not paste non-public or sensitive text into the live demo. Quranpedia receives no article text, only one download of the mushaf. The three fonts are served by the app itself, so a visit contacts no other host. The host (Render) sees ordinary web-request metadata. The page footer states the main points in Arabic.
- The frontend inserts all text with `textContent` (never `innerHTML`). Every response (API, pages, static files) carries `Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self'; font-src 'self'; img-src 'self' data:; connect-src 'self'; worker-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'` (no `unsafe-inline`), `Permissions-Policy`, `Cross-Origin-Opener-Policy` and `Cross-Origin-Resource-Policy: same-origin`, and `Strict-Transport-Security` when the request came over HTTPS (tests: `tests/test_security_headers.py`; in the browser: `scripts/ui_selfhost_e2e.mjs`). `pip-audit` on `requirements-dev.txt` found no known vulnerability on 4 Oct 2026. Secrets come only from environment variables; `.env` is git-ignored.
- **Hosting limits.** Render Free sleeps after about 15 minutes idle (first request up to about a minute, plus one Quran download), has no persistent disk, and shares CPU; Groq's free tier answers 429 when audits come in quick succession (about 2 minutes apart is safe). A production deployment would need a paid host, a paid Groq tier (or Zero Data Retention) and a shared cache. Memory and timing numbers in `docs/EVALUATION.md` were measured locally, not on Render.
- Time limits: AI gets 12 s total per audit (one request, no retry chain); Quranpedia calls time out after 20 s; the unmarked-phrase search has a fixed work budget and reports when it was cut off.

## What still needs human review

The tool is an aid to an editor, not a substitute for one. A person still has to:

- read every quotation marked «يحتاج مراجعة» or «غير محسوم» and decide; nothing marked «غير محسوم» comes with a replacement;
- read the parts of the article the tool did not recognise as quotations (a short or unmarked quotation can be missed, or listed only as «possible»);
- decide whether a quotation is *used* correctly. The tool checks wording and reference only; it does not interpret verses, judge context or give religious rulings;
- check wording the tool calls «مطابق» when it matters: a match means the words agree with Quranpedia's Hafs text at the shown level (literal, vowel marks ignored, spelling unified, or Uthmani script), and mushaf editions differ in a few marks;
- check any text in Quranpedia's source itself that is later corrected (it is corrected weekly; the app reads it live, but a stale cached copy can be used when Quranpedia is unreachable, and the details say so);
- review the labelled evaluation sets: they were written by the author, partly self-labelled, and no Arabic specialist has reviewed them yet ([docs/LABEL_REVIEW.md](docs/LABEL_REVIEW.md)).

## Known limitations

- **Free hosting.** The live demo runs on Render Free: it sleeps after 15 minutes without traffic and the first request afterwards can take about a minute (23 s in the one measurement). No keep-alive is used to hide this.

- **No general accuracy claims.** The numbers above come from three small, author-written sets, single runs, labels awaiting specialist review. AI-mode numbers (Groq, earlier local runs, one run per set) are in `docs/EVALUATION.md`; they were not repeated for the current code.
- **Detection is not complete.** Unmarked phrases of one or two words, phrases made only of common words, near matches with fewer than 4 matched words, a wrong first or last word of an unmarked quotation (reported only as "uncertain: boundary not settled", with the neighbouring words shown), quotations with omissions and rare Uthmani spellings can be missed or shown only as «possible» or «uncertain». Frozen set: 30 of 32 unmarked quotations found, 2 missed.
- **«Possible» is not verified.** Ordinary prose can reuse Quran words (about 2–3 «possible» items per 1,000 words of Islamic-topic prose, 44 outside brackets in 19,794 untuned Wikipedia words). Close paraphrases such as «لا تحزن إن الله معنا دائما» (5 of 6 words from التوبة: 40) are reported as a candidate whose end is "uncertain".
- **A short unmarked misquotation** (e.g. «إن الله مع الصابرون» with no reference and no «قال تعالى») is indistinguishable from prose by evidence: it is listed only as «possible» with its closest verse and a one-click confirm, or missed.
- **Boundaries.** The tool cannot know where an unmarked quotation starts or ends, so the editor may need to confirm («نعم، هذا هو الاقتباس كاملًا»), take the neighbouring word into the quotation, or choose the words by hand. This makes many correct quotations read "uncertain".
- **AI may fall back.** On Groq's free tier a 429 can happen; the notice says so and the result is the deterministic one. A model can also propose prose or nothing.
- **Length.** Limit 20,000 characters. Measured locally (macOS, Python 3.14, AI off): 8,000–14,700 characters of realistic articles 0.4–0.8 s; 20,000 characters 1.2 s; process memory 87 MB; the response of a dense article up to 0.6 MB (`docs/EVALUATION.md`). Accuracy was evaluated only up to 14,700 characters. On Render Free, measured on the released build, it is about 1 ms per character: 8–15 s for realistic 8,000–15,000-character articles and about 25 s at 20,000 (`docs/EVALUATION.md`); memory there was not measured. An article with more than 150 candidate passages lists the first 150 and says how many were left out.
- **Verse suggestion.** It speaks only after a Quran cue, an open quotation mark, an explicit request or the writer's opt-in, and needs two distinctive words. Its cue vocabulary is incomplete: on the blind set B it stayed silent for «في التنزيل العزيز» and «في كتاب الله» (71 of 76 suggestions given, 0 of 39 false, 19 of 22 corrections; `docs/EVALUATION.md`). Both sets are AI-written and unreviewed by a specialist.
- **Editing after an audit.** An edit that touches a quotation, its reference or the neighbouring word makes it stale and drops its decision, also if you undo the edit; the decision is not restored. Pasting over the whole article stales everything. The quotation is read again on «أعد التدقيق».
- **Browsers.** Tested in Chromium (desktop, 390 and 320 px) with Playwright, axe and the keyboard; a shorter smoke test (`scripts/ui_crossbrowser.mjs`: suggestion with Tab and tap, correction, audit, stale edit, recheck, highlight alignment) also runs in Playwright's WebKit and Firefox builds, which found and fixed a real bug (a tap on «أدرج» did nothing in WebKit). Not tested: Safari itself, a real phone and its keyboard, a real screen reader.
- Automatic corrections are deliberately conservative: a short fuzzy quote, or a phrase found in several verses, gets review information but no replacement.
- The source is Quranpedia's Hafs text in standard (imla'i) spelling with full diacritics. Uthmani spellings (e.g. «الصلوة») are matched through documented rules; about 50 rare spellings are not covered, and a few words the imla'i text joins or splits differently (`بَعْدَ مَا` / `بعدما`) are not either: such a quotation reads «uncertain» without a replacement. The Uthmani rasm writes some different imla'i words identically (a plural verb and a singular verb ending in waw), so that confusion cannot be detected in Uthmani text. Only Hafs is supported. Diacritic conventions vary between printed mushafs, so a diacritics difference is a prompt to check, not proof of error.
- Quotations with omissions («…») are compared as one span, so they show missing words and need review. Quotations under 3 words are never confirmed without a reference and are not searched for automatically (select them by hand). Reference parsing covers common Arabic forms, not every style.
- Gemini: no real Gemini call has succeeded (503/429), so that adapter is unverified.

## Repository map

```
app/
  main.py            FastAPI app, API routes, security headers, rate limit
  audit.py           pipeline orchestration (incl. the manual phrase check)
  phrases.py         unmarked-phrase search: seed-and-extend over the word index, tiers, formula and cue lists
  verifier.py        wording/reference verification (deterministic)
  references.py      reference detection & parsing
  arabic.py          normalization levels, tokenization with offsets
  quran_source.py    Quranpedia client, cache, search index
  surahs.py          surah names, aliases, verse counts (metadata only)
  corrections.py     proposed changes with exact offsets (source words only)
  extraction/        provider interface, Groq + Gemini providers, call tracker, marked-quote extractor
  suggest.py         verse suggestions from the loaded Quranpedia text (no model): triggers, ranking, ambiguity
  static/            index.html, styles.css, app.js, revision.js (decisions engine), workspace.js (edit tracking, stale handling, decision carry-over), suggest-ui.js (the box under the caret), sources.html / privacy.html / limitations.html, surahs.js, samples/*.txt
tests/               verifier, references, normalization, pipeline, source, Gemini, Groq, corrections,
                     revision-engine (Node) tests
scripts/live_smoke.mjs one focused journey of the demonstration article on a running instance (one audit; one Groq call if a model is configured; `--phone` for 390 px)
scripts/ui_journey_e2e.mjs Playwright check of the first journey (demo action, verdict, first item, decisive difference, folded details, decisions, final check, copy) at 1366/390/320 px, own AI-off server
scripts/ui_long_e2e.mjs Playwright check of a near-limit article, sequence, keyboard focus against the bottom bar, bidi, slow/failed server, no-findings and model-failed states
scripts/ui_a11y_check.mjs axe-core pass (WCAG 2.2 AA) over eight states at three widths
scripts/_ui_common.mjs shared helpers of the browser checks
scripts/e2e_check.py end-to-end API check of a running instance (samples, errors, files not served)
scripts/ui_e2e.mjs   Playwright browser check of the editor workflow, desktop + mobile
scripts/ui_phrase_e2e.mjs Playwright check of candidate / "maybe" cards, confirming a verse, manual selection (own AI-off server);
                     `--live-ai URL`: model-on assertions that do not assume a finding count
scripts/ui_boundary_e2e.mjs Playwright check of the "uncertain boundary" workflow
scripts/ui_async_navigation_e2e.mjs Playwright check: a late phrase result must not pull the writer back to an earlier quotation
scripts/measure_resources.py startup time and peak memory (in-process and real uvicorn server)
scripts/measure_length.py audit time / memory / response size at 6,000-20,000 characters
scripts/ui_suggest_e2e.mjs, scripts/ui_workspace_e2e.mjs Playwright checks of suggestion while typing, and of editing, stale decisions, recheck, drafts and a long article
docs/LABEL_REVIEW.md checklist for a human reviewer of the evaluation labels
docs/CONTINUATION.md plan for 4–6 October and beyond (incl. the X use case)
docs/PILOT.md       proposed pilot, operating costs, unknowns (nothing of it has happened)
docs/EVALUATION.md   labelled evaluation: method, fallback results, limits
docs/TEST_LOG.md     dated end-to-end observations (local + live)
docs/RENDER_DEPLOY.md Render settings, deploy steps and checks (the live demo's host)
render.yaml          optional Render Blueprint with the same settings (no secret values)
vercel.json, .vercelignore  only for the earlier Vercel baseline deployment
eval/                labelled cases, frozen phrase set and frozen long-article sets (+ SHA-256), two verse-suggestion sets (A development, B blind), label validators, scorers (`run_eval.py`, `run_suggest_eval.py`), raw results
SOURCES.md           sources, licences and attribution record
BASELINE.md          pre-challenge baseline declaration
```

Sample articles are in `app/static/samples/` and can be loaded from the «أمثلة أخرى» menu; the demonstration article is also the one-click «جرّب المقال التجريبي» action on the empty page.
Each contains some deliberately wrong quotations or references so every status can be demonstrated.

## Dependencies and licences

Code: MIT (see [LICENSE](LICENSE)). The Quran text is **not** included in this repository; it is fetched from Quranpedia under its usage policy (free, no authentication, one documented request per instance, attribution in the page footer).
Runtime dependencies are pinned in `requirements.txt` (FastAPI, Starlette, Pydantic, httpx, uvicorn and their dependencies: MIT or BSD-3-Clause; `certifi` is MPL-2.0; `typing_extensions` is PSF-2.0); test dependencies in `requirements-dev.txt` (pytest and plugins: MIT, BSD-2-Clause, Apache-2.0/BSD-2-Clause).
Fonts (Readex Pro, Amiri Quran, Noto Naskh Arabic) are SIL Open Font License 1.1, self-hosted in `app/static/fonts/` (the Arabic and Latin subsets Google Fonts serves, copied on 4 Oct 2026, each with its `OFL.txt`). The organizer's PDFs and PowerPoint template are not included. Groq and Quranpedia are third-party services governed by their own terms.
Every source, licence and attribution is listed in [SOURCES.md](SOURCES.md).

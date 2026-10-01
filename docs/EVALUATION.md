# Evaluation

**What these numbers are and are not.**

- The labelled set is small (14 articles, 28 gold quotations, 5 non-Quran negatives).
- The articles were written by the project author for this test, using the same AI-assisted workflow that built the app. They are not an independent sample of real articles.
- A human reviewer still needs to confirm the labels (checklist: `docs/LABEL_REVIEW.md`).
- The results show how the pipeline behaves on the listed case types. They are **not** a general accuracy figure.
- **AI mode (Groq, 30 Sep 2026):** with the original prompt it responded on every case but added no detections; with prompt v2 it added one quotation on each set (see "Experiment").

## Labelled set (`eval/cases.json`, v1)

| Case type | Gold quotations |
|---|---|
| Marked (﴿﴾, {}) | 24 |
| Unmarked | 4 (3 of them short, under 5 words) |
| Wrong wording (e.g. «أستجيب» for «أستجب», «ربي» for «رب», «قبائلاً») | 4 |
| Wrong diacritics (e.g. «يخشى اللهُ … العلماءَ», «إبراهيمُ ربَّه», «ورسولِه») | 3 |
| Repeated phrases (occur in several verses) | 6 |
| Missing references | 6 |
| Incorrect references (wrong verse, wrong surah, out of range) | 4 |
| Reference covering only part of a quotation | 1 |
| Surah-only reference | 1 |
| Quotations spanning verses | 3 |
| Negatives: hadith, du'a, proverb, legal maxim | 5 |

**Label checking.** `eval/validate_labels.py` checks every label against the Quranpedia Hafs
text, using its own normalization rather than the app's verdict logic. It confirms that:
- the gold verse contains the correct wording;
- "correct" quotes match that wording and error quotes don't;
- diacritics errors differ only in diacritics;
- "repeated" phrases really occur in more than one verse;
- each reference label agrees with the written reference;
- the negatives don't occur in the Quran.

**Label correction (disclosed).** The first fallback run exposed one labelling error. In case c07 the
article names the surah («تتكرر في سورة الرحمن آية …»), but the reference was labelled
"missing". It was relabelled `surah_only`, and the change is recorded in the case's `label_note`.
The article itself was not changed.

## Scoring rules (`eval/run_eval.py`)

- **Detected:** a finding overlaps at least 50% of the gold span.
- **Wording and reference verdicts:** each one is graded *correct*, *abstained* (the app said "uncertain") or *wrong*.
- **Critical safety counts:**
  - a false "matched" wording verdict on a quote that has an error;
  - a false "matched" reference verdict on a reference that is wrong.
- **Expected verdicts:**
  - a correct quote is expected "matched", unless it is a repeated or under-3-word phrase without a pinpointing reference, which is expected "uncertain";
  - wording or diacritics errors are expected "difference";
  - references map as: correct → matched; incorrect or out of range → incorrect; missing → missing; partial → uncertain; surah-only → matched, or uncertain if the phrase repeats.

## Results — fallback mode (no AI), 2026-09-28

Command: `python eval/run_eval.py --mode fallback`. Raw output: `eval/results/fallback-20260928-195343.json`.
The run is deterministic (no model involved), and all 14 cases ran with `mode = reduced`.

| Measure | Result |
|---|---|
| Gold quotations detected | **25 / 28** |
| · marked | 24 / 24 |
| · unmarked | 1 / 4 (the long unmarked quote was found by the verbatim scan; the three short ones were missed) |
| Wording verdicts on detected quotes | 25 correct, 0 abstained, 0 wrong |
| **False "matched" wording** (quote with an error reported as matching) | **0** |
| Reference verdicts on detected quotes | 22 correct, 3 abstained, 0 wrong |
| **False "matched" reference** | **0** |
| Verse location (where it could be scored) | 22 / 22 correct |
| Findings on non-Quran negatives | 0 / 5 |
| Other unexpected findings | 0 |
| Time per article (local, cached source) | mean 0.03 s, max 0.44 s (the first one includes index loading) |

**What the misses and abstentions show:**

- **Missed (3):**
  - «وافعلوا الخير لعلكم تفلحون», «ولا تنسوا الفضل بينكم» and «ادعوني أستجيب لكم» are unmarked and under 5 words.
  - Reduced mode cannot find these by design; they are exactly what AI extraction is meant to add.
  - The last one also has a wording error.
- **Abstained references (3):**
  - The three marked quotations with wording errors (c03 ×2, c04) cite the right verse, but the app matched them only approximately.
  - It therefore reports the reference as "uncertain" rather than "matched", which is the intended conservative behaviour.

## Results — proposed corrections, fallback mode, 2026-09-29

Same command and the **same unchanged labels**; raw output `eval/results/fallback-20260929-205031.json`.
Detection and verdict numbers are identical to the 2026-09-28 run (25/28 detected, 0 false "matched").
New scoring of the editor workflow's *proposed, non-optional* corrections:

| Measure | Result |
|---|---|
| Detected quotes with a wording or diacritics error | 6 (3 wording, 3 diacritics) |
| · a fix was proposed whose corrected excerpt re-verifies as "matched" at the gold location and equals the gold wording | **6 / 6** |
| · wrong fixes | 0 |
| Detected reference problems (incorrect, partial, or unresolvable) | 6 |
| · reference fix proposed and equal to the gold surah/ayah | 4 (3 wrong verse, 1 partial range → 5-6) |
| · left for human review (repeated phrase, location not pinned) | 2 |
| **Fixes proposed for a quote labelled correct** | **0** |
| **Reference fixes proposed for a reference labelled correct** | **0** |

How fixes are checked (`grade_corrections` in `eval/run_eval.py`): the corrected excerpt is run through the
verifier again with the gold location as reference, and must fold-equal the gold wording. Optional changes
(full vocalization, adding a missing reference) are not counted as corrections.

Limits: 6 wording errors and 6 reference problems are far too few to estimate a correction accuracy.
One fix (c04, «وقبائلاً» → «وَقَبَائِلَ») is fully vocalized because the writer had vocalized that word;
this is consistent with the style rule but looks mixed in an otherwise unvocalized sentence.

## Results — AI mode (Groq), 2026-09-30

Command: `python eval/run_eval.py --mode ai` with `AI_PROVIDER=groq`, model `qwen/qwen3.8-27b`, `reasoning_effort: "none"`,
**same unchanged labels and scoring**. Raw output: `eval/results/ai-20260930-165858.json`. One run only.

| Measure | Fallback (29 Sep) | AI mode (30 Sep) |
|---|---|---|
| Cases where the AI responded | — | **14 / 14** (HTTP 200, 258–507 ms) |
| Gold quotations detected | 25 / 28 | **25 / 28** |
| · unmarked | 1 / 4 | **1 / 4** |
| False "matched" wording / reference | 0 / 0 | 0 / 0 |
| Findings on non-Quran negatives | 0 / 5 | 0 / 5 |
| Wording fixes that re-verify / wrong | 6 / 0 | 6 / 0 |
| Fixes proposed for correct text or references | 0 | 0 |
| Model candidates proposed / discarded | — | 16 / 0 |

**Observed:** the model proposed candidates only in 8 cases, all with already-marked quotations. It returned an
empty list for c11 and c12, the unmarked short quotes that AI extraction is meant to add, and for 4 other
cases. On this set, AI extraction with the current prompt and model therefore **adds nothing** over fallback. The good
news is that it also added no false findings. Whether a different prompt, `reasoning_effort` or model does better is
untested; any change must be re-run on these same labels and reported as a separate run.

## Experiment — short unmarked quotations (2026-09-30)

Goal: can AI extraction find the short unmarked quotations that fallback misses (c11 ×2, c12 «ادعوني أستجيب لكم»)?
Rules: labels and scoring unchanged; one prompt revision; at most one other Groq model; every run logged;
a held-out set written **before** any change was tried, used only for the final choice. Quranpedia remains the
only authority for wording and references; the model only points at substrings.

**Diagnosis (v1).** Raw responses (`eval/experiments/raw/20260930-174033-qwen_qwen3.8-27b-v1.json`): `{"candidates": []}`
for both c11 and c12, HTTP 200, finish `stop`. The model is answering, but chooses nothing when there are no
brackets or reference.

**Prompt v2** (`app/extraction/prompts.py`): v1 plus a paragraph on where unmarked quotes hide (inside a sentence,
after «والله يقول»/«قوله», or with no introduction; ≥ 3 words), one positive and one negative example that are not in
either evaluation file, and the statement that a missed quotation is worse than a candidate the server later
rejects. Rules 1–6 unchanged.

**Other model:** `openai/gpt-oss-120b`, `reasoning_effort: "low"`, with prompt v2.

### Labelled set (`eval/cases.json`, 14 cases, 28 quotations — unchanged)

| Version | Detected | Unmarked | Short | False "matched" | False fixes | Non-Quran hits | Candidates / discarded | Raw result |
|---|---|---|---|---|---|---|---|---|
| Fallback (no AI) | 25/28 | 1/4 | 0/3 | 0 | 0 | 0/5 | — | `fallback-20260930-174118-cases-check.json` |
| qwen3.8-27b + v1 | 25/28 | 1/4 | 0/3 | 0 | 0 | 0/5 | 16 / 0 | `ai-20260930-165858.json` |
| qwen3.8-27b + **v2** | **26/28** | **2/4** | 1/3 | 0 | 0 | 0/5 | 21 / 0 | `ai-20260930-175238-qwen-v2.json` |
| gpt-oss-120b + v2 | 26/28 | 2/4 | 1/3 | 0 | 0 | 0/5 | 24 / 0 | `ai-20260930-180026-gptoss120b-v2.json` |

- qwen + v2 adds c12 «ادعوني أستجيب لكم» (graded *difference*, correctly: the mushaf has «أستجب»; review only, no
  automatic fix). c11 is still empty. Every other row is identical to v1.
- gpt-oss + v2 adds c11 «وافعلوا الخير لعلكم تفلحون» instead, and misses «ادعوني». Mean 1.33 s per article (max 3.5 s)
  against ≈ 0.4 s for qwen. In a separate probe of the same c11 input it returned «وافعَلوا الخير» (a diacritic
  not in the article), so output varies between calls even at temperature 0.
- «ولا تنسوا الفضل بينكم» (c11) was found by no version.

### Held-out set (`eval/heldout.json`, 4 cases, 6 quotations of which 5 unmarked, 4 non-Quran negatives)

| Version | Detected | Unmarked | False "matched" | False fixes | Non-Quran hits | Candidates / discarded | Raw result |
|---|---|---|---|---|---|---|---|
| Fallback (no AI) | 3/6 | 2/5 | 0 | 0 | 0/4 | — | `fallback-20260930-174118-heldout.json` |
| qwen3.8-27b + v1 | 3/6 | 2/5 | 0 | 0 | 0/4 | 0 / 0 | `ai-20260930-181015-heldout-qwen-v1.json` |
| qwen3.8-27b + **v2** | **4/6** | **3/5** | 0 | 0 | 0/4 | 2 / 0 | `ai-20260930-182414-heldout-qwen-v2.json` |
| gpt-oss-120b + v2 | 3/6 | 2/5 | 0 | 0 | 0/4 | 3 / 1 | `ai-20260930-180534-heldout-gptoss120b-v2.json` |

- qwen + v2 adds «رب زدني علما» (h01). Missed by all: «وتعاونوا على البر والتقوى», «ادعوا ربكم تضرعا وخفية».
- gpt-oss proposed «لا يكلف الله نفسا إلا وسهها», a misspelling that is not in the article; the server discarded it,
  as designed. Its other proposals were already found by fallback.
- Four runs stopped on HTTP 429 and were **not** counted (`eval/results/stopped-*.json`, plus one at 17:41 before
  stopped runs were saved). See the rate-limit note in `TEST_LOG.md`.

### Choice

**qwen3.8-27b + prompt v2** is now the default (`EXTRACTION_PROMPT=v2`). It is the only version that gained on
both sets (+1 quotation each), is the fastest, and kept every safety count at zero. The gain is small and each number comes from one
run on author-written sets, with visible call-to-call variation. So this is **"a small observed benefit on these
sets"**, not a measured detection rate. Most short unmarked quotations (4 of 7 across both sets) are still missed.

## Experiment — unmarked phrase search (2026-09-30, deterministic path first)

Goal: find short unmarked quotations (no brackets, quotation marks or reference) without AI, show them with the
right level of doubt, and keep hadith, du'a, proverbs and ordinary Arabic from being presented as confirmed verses.
Labels of `eval/cases.json` and `eval/heldout.json` are unchanged (`git diff` empty); scoring rules are unchanged.
The harness only gained counters (detection tier, false suggestions, false confirmations, whether the gold verse is shown).

### The four misses that started it

With the default AI mode (Groq `qwen/qwen3.8-27b`, prompt v2) four unmarked quotations were still missed on the two
sets (raw results `ai-20260930-175238-qwen-v2.json`, `ai-20260930-182414-heldout-qwen-v2.json`):
«وافعلوا الخير لعلكم تفلحون» and «ولا تنسوا الفضل بينكم» (c11), «وتعاونوا على البر والتقوى» (h02) and
«ادعوا ربكم تضرعا وخفية» (h03). Without AI, two more are missed: «ادعوني أستجيب لكم» (c12, misquoted) and «وقل رب زدني علما» (h01).
All four are 4-word phrases made of words that are rare in the Quran; the old scan needed 5 words.

**Baseline of the unchanged code** (commit `8a4b8b7`, no AI; raw `fallback-20260930-204519-baseline-cases.json`,
`…204520-baseline-heldout.json`, `…205537-baseline-phrases-frozen.json`): main 25/28 (unmarked 1/4), held-out 3/6 (2/5).

### What was built (`app/phrases.py`)

- **Seed and extend over the existing word index.** Each article word that is rare in the Quran (occurs in at most 300 of the 6,236 verses)
  is looked up in `QuranIndex.positions`; every place it occurs is extended left and right along that surah's word stream.
  Nothing is indexed per phrase. The 4-word dictionary the old scan used (`QuranIndex.ngrams`, about 21 MB of the index) was removed.
- **Runs stop at punctuation** (full stop, quotation mark, bracket, digit, line break); commas and semicolons do not stop a run.
- **Normalization is for searching only** (`arabic.folded`). The text shown, compared and copied comes from the source through the verifier;
  article offsets are kept, and a proposed correction replaces only the words of the quoted span (tested).
- **Near matches.** Inside a phrase, one or two words that differ are tolerated (a substituted, extra or omitted word, or a word that
  is spelled or inflected slightly differently). The wrong word stays **inside** the span, so the verifier reports a difference; the old scan
  cut it off and called the correct remainder "matched". Whatever lies beyond a replaced/extra/omitted word must be backed by two matched
  words or one rare exact word, so a single neighbouring prose word is not absorbed.
- **Detection tier** (separate from the verification verdict): `candidate` = exact, (at least 4 words and rarity mass ≥ 20, or at least 5 words and mass ≥ 16; mass = sum of
  ln(6,236 ÷ verses containing the word)), not a formula, not introduced as a hadith/du'a/proverb. `possible` («قد يكون اقتباسًا قرآنيًا — يحتاج مراجعة»)
  = anything else that is reported: short or common exact phrases (mass ≥ 12), near matches (≥ 4 matched words, mass ≥ 16), or a phrase after a
  hadith/du'a/proverb cue. Exact phrases below the floor are **not reported** (counted and announced instead). Everyday formulas (بسملة، حمدلة،
  شهادة، استرجاع، «إن شاء الله»، «رضي الله عنه» …) are hidden unless a Quran cue such as «قال تعالى» precedes them.
- **Nothing is replaced silently.** A `possible` finding shows the match but proposes **no** replacement text until the editor confirms it is a
  Quran quotation and picks the verse. If a phrase occurs in several verses, all are listed as choices and none is picked. A fuzzy match is never
  called matched. A manual path lets the editor highlight a missed phrase and choose its verse (`POST /api/phrase`; no AI call).
- **Hint for the last word.** The search cannot know where a writer's quotation ends, so a wrong last word looks like prose after the quotation.
  When a phrase ends inside a verse and the next article word differs from the verse's next word, the card shows both words side by side
  (no verdict, no edit).
- Candidates are merged with bracketed and AI candidates by overlap (priority: manual/bracketed > AI > phrase); tests cover the merge.

### How the parameters were chosen (and what was and was not held out)

1. **The frozen set was written first.** `eval/phrases_frozen.json` (49 cases: 20 short exact unmarked quotations, 12 slightly misquoted ones,
   12 negatives — hadith, du'a, proverbs, maxims, ordinary Arabic, of which 3 are "hard" because they share a 3–6 word run with the Quran —
   and 5 everyday formulae) was written and validated by `eval/validate_phrases.py` (independent of the app's matching) **before any detection
   code existed**. Its SHA-256 is in `eval/phrases_frozen.sha256` and in commit `7ac49a3`. It is author-written with the same AI-assisted workflow,
   and its labels are pending human review like the others.
2. **Tuning used other data only:** the main and held-out sets (which had already been used and inspected), a synthetic benchmark (random Quran
   phrases of 3–8 words placed in Arabic Wikipedia paragraphs, exact and with one substituted/omitted/extra word or a changed ending/spelling —
   random n-grams are less distinctive than the phrases people really quote, so it compares settings and is not a recall figure),
   and ordinary Arabic prose from Arabic Wikipedia (31 secular articles, about 101,000 words, and 20 Islamic-topic articles, about 70,000 words;
   fetched once for local measurement, not committed or redistributed). Choices: rarity-mass floor 12 (function-word coincidences such as «في كثير من»,
   «ما هي إلا», «حتى لا تكون» score 9–11.7), candidate mass 20, near-match mass 16 with at least 4 matched words (religious prose showed that 3-word and
   low-mass near matches were mostly noise: 98 → 58 near-match "maybes" in 70,000 words, and 43 after the two fixes described next, while synthetic recall of 5+ word misquotations moved only 715 → 704 of 720).
3. **Post-freeze defect fixes, disclosed.** The frozen set was run **twice**. Run 1 (first code that could run it) exposed two defects of mine, both
   code bugs rather than threshold choices: (a) one fully correct 5-word quotation was stretched over a neighbouring prose word (joined through a
   comma and one near-match word; the same pattern had shown up in the development prose, e.g. «لا شريك له، وألا»), and (b) my cheap pre-filter for near matches
   rejected a one-letter change in the middle of a word (مذكر/مدكر). I fixed both, re-checked the development data, and ran again (run 2). **Both runs are reported below; run 2 is not untouched.**
   No threshold was changed after run 1.
4. **Never tuned on:** the frozen set's thresholds, the 5 secular and 7 Islamic-topic Wikipedia articles used for the "untuned prose" rows below.

### Results — deterministic path (no AI), same labels

| Set | Measure | Baseline `8a4b8b7` | Phrase search |
|---|---|---|---|
| Main (`cases.json`, dev data) | gold detected | 25/28 | **27/28** |
| | unmarked detected | 1/4 | **3/4** (still missed: «ادعوني أستجيب لكم», a 3-word misquotation) |
| | false "matched" wording / reference | 0 / 0 | 0 / 0 |
| | findings on non-Quran negatives | 0 | 0 |
| Held-out (`heldout.json`, dev data) | gold detected | 3/6 | **6/6** |
| | unmarked detected | 2/5 | **5/5** |
| | false "matched" / findings on negatives | 0 / 0 | 0 / 0 |
| **Frozen** (`phrases_frozen.json`) — run 1 | unmarked quotations detected | 18/32 | **30/32** |
| Frozen — run 2 (after the two fixes) | unmarked quotations detected | — | **30/32** |
| Frozen, run 2 | · short exact quotations (20) | 9/20 | **20/20** — 13 as `candidate`, 7 as `possible` |
| | · slightly misquoted (12) | 9/12 | **10/12** — 8 as `possible`, 2 as `candidate` (see next row) |
| | misquotations reported "matched" (false verified wording) | **8** | **2** in run 2 (1 in run 1) |
| | wrong verse shown as confirmed | 0 | 0 |
| | gold verse shown (proposed, or listed among choices for repeated phrases) | — | 30/30 |
| | findings on the 28 non-Quran negatives | 1 (shown as confirmed) | 2, **both shown as `possible`**, none as confirmed |
| | findings on the 5 everyday formulae | 1 (shown as confirmed) | 0 (hidden and counted) |
| | **false suggestions** (any finding on a negative, formula or unlabelled text) | 2 | **2** |
| | **false confirmed** (negative/formula/unlabelled text shown as confirmed) | 2 | **0** |

What the remaining errors are (frozen set, run 2):
- **Missed (2):** «إن الله يحب المحسنون» and «فبأي نعم ربكما تكذبان». Both are 4-word phrases made of common words with one changed word; the
  near-match rules (at least 4 matched words and mass 16) reject them on purpose.
- **Misquotations reported "matched" (2):** «إن الله لا يغير ما بقوم حتى يغيروا أنفسهم» and «وما خلقت الجن والإنس إلا لعبادتي». In both the wrong words are at the **end**
  of the quotation; the search reports the correct opening as a `candidate`, and the card shows the hint «بعد هذا المقطع في المصحف: … وبعده في المقال: …». A wrong edge word cannot be told apart from
  prose after a quotation, so this is a known limit, not a fixed one. **Superseded on 2026-10-01:** these two are no longer reported "matched"; see "Release blocker" below.
- **The 2 negatives shown:** «من كان يؤمن بالله واليوم الآخر» (a hadith that begins with a 6-word Quran run, shown as `possible` because «وجاء في الحديث» precedes it)
  and «إقامة الصلاة وإيتاء الزكاة» (shown as `possible`, common phrase).

### Results — ordinary prose that was never tuned on

| Sample | Words | Candidate | Possible (exact) | Possible (near) | Hidden short/common |
|---|---|---|---|---|---|
| 5 secular Wikipedia articles (Medicine, Arabic poetry, Egyptian cuisine, Astronomy, Chemistry) | 18,612 | 1 (a verse quoted in the text) | 0 | 0 | 6 |
| 7 Islamic-topic Wikipedia articles | 19,794 | 188 (185 are vocalized or bracketed verses; the other 3 are real Quran phrases: «ظلمات بعضها فوق بعض», «الميتة والدم ولحم الخنزير», «من كل فاكهة زوجان») | 57, of which 36 are outside brackets and quotation marks | 10, of which 8 are outside brackets and quotation marks | 43 |

I read every unbracketed, unvocalized candidate in the religious samples: 20 on the tuning sample (read at an earlier code version, before the two fixes) and the 3 above on the untuned sample. All 23 were Quran text that the article itself quotes or alludes to; I found no candidate that was plain prose (my judgement, not a labelled test).
The "maybe" items in religious prose are real Quran phrases used as ordinary religious wording («لا شريك له»، «على كثير من»…), which is why they are not candidates.
Islamic-topic prose therefore yields about 2–3 "maybes" per 1,000 words (44 outside brackets and quotation marks in the 19,794 untuned words, 67 counting bracketed ones); secular prose almost none.

### Memory and startup

Measured with `scripts/measure_resources.py` in **fresh processes** (median of 5), on one macOS/arm64 machine with **Python 3.12.13** (the version Render uses, from `.python-version`), cached Quran text on disk, no AI.
Not measured on Render. Workload: all 67 evaluation articles plus two 6,000-character worst cases. Raw: `eval/results/resources-py312-*.json`.

| | Baseline `8a4b8b7` | Phrase search |
|---|---|---|
| RSS after importing the app (audit module only) | 30.6 MB | 30.8 MB |
| RSS after the Quran index is built | 93.0 MB | **69.9 MB** |
| **Peak RSS, in-process, after all articles** | 93.8 MB | **75.7 MB** |
| Index load (build from the cached text) | 0.475 s | 0.399 s |
| **Real `uvicorn` server, peak RSS** (`/usr/bin/time -l`; FastAPI included; 67 articles + 31 more + a worst case) | 112.8 MB | **94.1 MB** |
| **Real server: process start → first audit answered** (import, index build from disk; excludes the one Quranpedia download a cold Render instance also makes) | 0.74 s | **0.72 s** |
| Audit time per article, in-process (mean / max over the evaluation articles) | 0.6 ms / 5.5 ms | 5.6 ms / 17.9 ms |
| Audit time per article over HTTP (mean / max; max = first request) | 9.1 ms / 0.50 s | 14.5 ms / 0.47 s |
| Worst case: 6,000 chars of real mushaf text with no markers, in-process | 0.023 s | 0.395 s |
| Worst case: 5,900 chars of the most frequent Quran words (cut off by the work budget and reported) | 0.007 s | 0.803 s |

The search allocates nothing per phrase: removing the 4-word dictionary more than paid for it (the index is ~23 MB smaller), and a test asserts that searching does not change the index's size.
The short evaluation articles take milliseconds, but a **full-size article is much slower** than the old scan: in-process, Python 3.12, for ~900–1,000-word (6,000-character) Wikipedia chunks the whole audit took a median of 130 ms (secular prose, 129 chunks), 247 ms and 297 ms (Islamic-topic prose, 71 and 21 chunks), p95 ≤ 0.40 s, maximum 0.43 s. The work budget is 80,000 seed visits per article;
the largest real chunk needed 41,131, so none of the evaluated articles was cut off (the three evaluation sets gave identical results before and after lowering the budget from 400,000).
On Render Free (512 MB, shared CPU) memory has a large margin on these numbers, but its CPU is slower than this machine, so times there will be higher; that is untested.

### Results — AI mode compared separately (Groq `qwen/qwen3.8-27b`, prompt v2, after the deterministic runs)

Run **after** all deterministic results were fixed, with `AI_PROVIDER=groq`, `qwen/qwen3.8-27b`, prompt v2, `reasoning_effort: "none"`, free tier, same labels and scoring,
through the same pipeline (the AI candidates are merged with the phrase-search candidates). A run counts as AI only if the model responded on **every** case. One run per set.

| Set | Deterministic (no AI) | With Groq | What the AI added |
|---|---|---|---|
| Main (14 cases) | 27/28, unmarked 3/4 | **28/28**, unmarked 4/4 (14/14 responded, 21 candidates proposed, 0 discarded) | «ادعوني أستجيب لكم» (3-word misquotation), found by the AI alone |
| Held-out (4 cases) | 6/6, unmarked 5/5 | 6/6, unmarked 5/5 (4/4 responded, 2 proposed) | nothing: both proposals were already found by the phrase search |
| Frozen (49 cases) | 30/32 (run 3) | 30/32 (49/49 responded, 4 proposed, 1 discarded) | no new detection; the same two misses (f21, f29). For 3 findings the AI vouching changed the label from `candidate`/`possible` to "found by the AI", so for the misquotation f26 the "confirm this is a quotation" step is skipped and source-backed corrections are proposed at once (each still needs the editor's approval; this is the pre-existing rule that an AI-proposed span counts as a stated quotation) |
| Frozen: findings on negatives and formulas | 2, both `possible` | 2, both `possible` | — |
| Frozen: misquotations reported "matched" | 2 | 2 | — |

Before the phrase search the same model had added one unmarked quotation on each set (26/28 and 4/6, `ai-20260930-175238-qwen-v2.json`, `…182414-heldout-qwen-v2.json`).
With the phrase search in place it adds one on the main set and none on the other two, so **on these sets the deterministic search already finds what the model found, except one 3-word misquotation.**
Single runs, small author-written sets: this shows no measurable benefit beyond that one case, and cannot show that the model never helps; output also varies between calls even at temperature 0.

Runs that did not count (kept, `eval/results/stopped-*.json`): the frozen-set pass **stopped three times** before it completed: HTTP 400 at f18 after 17 cases; HTTP 429 at f03
(*output tokens per minute: limit 1000, requested 1100*; the input-token budget was untouched); HTTP 400 at f09 after 8 cases. A diagnostic call for the f18 article made right after the first 400 returned 200,
so the 400s look like intermittent schema-validation failures, which I did not confirm. To finish, I added `--retry-400 N` to the harness (retries only HTTP 400, every retry recorded; 429 and other failures still stop the run)
and used `GROQ_MAX_COMPLETION_TOKENS=512` (real outputs stay under 100 tokens; one probe succeeded at 512 right after a 429 at the default 4096, which is not a controlled test). The completed pass (attempt 4) had one
retried case (f18, 400 then 200). The main and held-out passes ran with the defaults (4096, no retries). Total Groq calls for this comparison: 101 (counted passes 49 + 14 + 4, the stopped attempts, the one retry and three single diagnostic calls).

### Release blocker: the end of an unmarked quotation (2026-10-01, fallback only, no Groq)

**Problem.** Two misquotations of the frozen set (f23 «إن الله لا يغير ما بقوم حتى يغيروا أنفسهم», f32 «وما خلقت الجن والإنس إلا لعبادتي») were reported with wording "matched",
which tells an editor the quotation is right. Tracing each case (full text, no AI):

| Step | f23 | f32 |
|---|---|---|
| Phrase span chosen (`phrases.py`: longest exact run, then trimmed) | «الله لا يغير ما بقوم حتى يغيروا» (the leading «فإن» does not fold to «إن», so it is not in the run either) | «وما خلقت الجن والإنس إلا» |
| Why the run stops | the article's next word «أنفسهم» ≠ the verse's next word «ما» | «لعبادتي» ≠ «ليعبدون» |
| Verifier (`verifier.py`) | the span aligns word for word with الرعد: 11, so "matched" — correctly, *for that span* | same, الذاريات: 56 |
| What was wrong | the span's end was never checked: the wrong words are *outside* the span, where a writer's own prose would also be. `_continuation` saw the differing next word but only drew a hint | same |

**Change (`app/audit.py::_end_boundary`; no threshold, tier or search rule changed — `app/phrases.py` is untouched, `eval/phrases_frozen.sha256` still verifies).**
A span whose end was chosen by the program or by the AI may be "matched" only if its end is settled:
(a) it reaches the end of its verse, or (b) a full stop, quotation mark, bracket, digit or line break follows, or the article ends, or (c) the reference attached to it follows at once.
Otherwise the next article word touches the span and the verse says something else at that point, so the end is **uncertain**: wording becomes "uncertain" (never "difference": nothing was shown to be wrong),
`needs_review` is set, the card keeps the candidate and the existing hint «بعد هذا المقطع في المصحف … وبعده في المقال …», `end_boundary` records the basis, and the optional reference insertion (which would go after a word that may be wrong) is withheld.
The reference verdict is computed separately and is untouched (a correct reference stays "matched" beside an uncertain wording). Spans stated by the writer (brackets, quotation marks) or highlighted by the editor are not questioned.
A comma does **not** settle the end (the search itself reads through commas). The same rule applies to an AI-chosen span; AI mode was not rerun.
**Not covered:** the same problem at the *start* of a span (a wrong first word) is unchanged and remains a known limit.

**Rerun of the unchanged sets, no Groq, labels untouched** (before = HEAD `d7cf6cd` code run today, after = this change; raw files `eval/results/fallback-20261001-*-boundary-before-d7cf6cd-*.json` and `…-boundary-after-fix-*.json`):

| Set | Wording "matched" among detected quotations (before → after) | False "matched" wording | Detection, tiers, gold verse shown, reference verdicts, corrections, negatives |
|---|---|---|---|
| Main (28 gold) | 18 → 17 (c11 «ولا تنسوا الفضل بينكم» → uncertain) | 0 → 0 | identical |
| Held-out (6) | 6 → 5 (h02 «وتعاونوا على البر والتقوى» → uncertain) | 0 → 0 | identical |
| **Frozen (32)** | 17 → **6** (of the 15 correct quotations expected "matched": 15 → **6**) | **2 → 0** (f23, f32 → uncertain) | identical (30/32 detected, 15 candidate / 15 possible, 30/30 gold verse shown, references 30 correct); the hadith negative f34 changed from wording "matched" to "uncertain" (still only a `possible`) |

Changed rows on the frozen set: f02, f05, f06, f08, f10, f11, f15, f17, f18 (correct quotations, prose touches the end) and f23, f32 (the misquotations).
Detection and the false-suggestion counts did not change; nothing was hidden or relabelled.

**What this costs.** An unmarked quotation that runs on into the writer's own words without punctuation is now "uncertain" (9 of the 15 correct ones on the frozen set), because that case and a wrong last word look the same.
The editor can settle it by highlighting the quotation (manual path: the end is then stated). This is the intended conservative behaviour, not an accuracy gain.

**The two HTTP 400s from Groq (f18 in attempt 1, f09 in attempt 3).** Their bodies were **not recorded**: the adapter discarded the response body of every 4xx, so the exact text cannot be inspected and I did not guess it. What is known: the request was identical for all cases and 17 and 8 earlier calls
succeeded, and a replay of f18 returned 200, so it was not a statically malformed request. Groq documents one structured-output 400 — «Generated JSON does not match the expected schema» (checked 2026-10-01) — which would be a model-generation failure, but nothing proves these were that.
Changes: the adapter now keeps the shortened error body (type, code, message, failed generation; never the key) in the per-audit `ai` record and in the evaluation log (not in `/api/health`), and marks a 400 as a generation failure **only** when the body says so;
`run_eval.py --retry-400` now retries only that marked case (before: any 400). Any other 400 stops the run and needs a code fix. No Groq call was made for this work; the next 400, if any, will show its body.

### Limits of these results

- The frozen set is small (32 gold quotations, 28 negatives, 5 formulae), author-written with an AI-assisted workflow, and its labels are pending human review.
  Differences of one or two items are not evidence of a better method.
- The main and held-out numbers are **development data**: they were inspected before and while the search was designed. They show the change works on those examples, not that it generalizes.
- The frozen set was run twice and run 2 followed two fixes (see above); no threshold changed between the runs.
- The synthetic benchmark and the Wikipedia prose are proxies. Articles by Islamic-content writers may differ from Wikipedia prose.
- Detection is not complete: phrases of one or two words, phrases made only of common words, near matches of fewer than 4 matched words, a wrong first word of a quotation (a wrong last word is no longer reported "matched" but only "uncertain, end not settled"),
  Uthmani spellings and quotations with omissions are missed or reported only as "maybe". The interface says so and offers manual selection.
- Memory and timing are from one macOS machine with Python 3.14; Render's Python and CPU differ.

## Next steps

1. A human reviewer (ideally someone with Quranic studies background) reviews every label in `eval/cases.json`.
2. Add real, independently sourced articles (with permission), including Uthmani-script quotations and quotations with omissions («…»).
3. Run AI mode three times to check repeatability, then report the mean and range.

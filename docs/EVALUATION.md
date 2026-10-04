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
**Not covered:** the same problem at the *start* of a span (a wrong first word) was unchanged here; **addressed later the same day** ("The start of an unmarked quotation" below).

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
- Detection is not complete: phrases of one or two words, phrases made only of common words, near matches of fewer than 4 matched words, a wrong first word of a quotation (a wrong first or last word is no longer reported "matched" but only "uncertain, start/end not settled"; the wrong word itself is still not found),
  Uthmani spellings and quotations with omissions are missed or reported only as "maybe". The interface says so and offers manual selection.
- Memory and timing are from one macOS machine with Python 3.14; Render's Python and CPU differ.

## Next steps

1. A human reviewer (ideally someone with Quranic studies background) reviews every label in `eval/cases.json`.
2. Add real, independently sourced articles (with permission), including Uthmani-script quotations and quotations with omissions («…»).
3. Run AI mode three times to check repeatability, then report the mean and range.

### The start of an unmarked quotation (2026-10-01, fallback only, no Groq)

**Why.** The end rule above has a mirror. The search starts at the first word that matches the Quran, so a quotation whose FIRST word is wrong
(known gap, listed above) is found from its second word, and the same span also arises when a correct, mid-verse quotation follows ordinary prose.
`app/audit.py::_start_boundary` applies the mirror of the end rule to spans chosen by the program or the AI. Brackets, quotation marks and an editor's highlight state their own start and are never questioned.

**Rule.** The start is *settled* when the span begins at its verse's first word, or the article's first word, or after punctuation / a line break (a comma or «؛» does NOT settle it, as for the end),
or right after a Quran lead-in (`ends_with_quran_cue`: «قال تعالى», «في القرآن الكريم»… the same list the tiers use), or right after the reference that belongs to it. Otherwise the article word touching the span differs from the verse's previous word
and the wording is **"uncertain"** (needs review), never "matched". Only "matched" is held back; "difference" stays "difference"; the reference verdict is computed separately. The card shows the verse's previous word beside the article's (`lead_in`).
No threshold, tier, label or `phrases.py` search code changed (one read-only helper was added there).

**Result** (`eval/results/fallback-*-start-before-df94548-*` = unchanged HEAD `df94548`, `…-start-after-boundary-*` = this change; labels untouched, `eval/phrases_frozen.sha256` OK; per-row comparison of detection, tier, kind, location, references and grades):

| Set | Correct quotations read "matched" before → after | Moved matched → uncertain | Detection / tiers / labels / references |
|---|---|---|---|
| Main (14 cases) | 17 → 17 | 0 | identical |
| Held-out (4 cases) | 5 → 3 | 2 (h01 «ومن يتق الله يجعل له مخرجا» after «فتذكر»; «وقل رب زدني علما» after «داعيًا») | identical |
| Frozen (49 cases) | 6 → 5 | 1 (f07 «ألا بذكر الله تطمئن القلوب» after «المال،») | identical |
| **Total** | **28 → 25** | **3** | **no change** |

False "matched" wording stays 0 on every set. Why so few moves: most correct frozen quotations that follow prose were already "uncertain" because of the end rule (9 of the 15 correct frozen quotations read "uncertain" before this change,
10 after it); the start rule adds a second reason to 6 spans there (f02, f05, f06, f11, f15, f18) and is the only reason for f07. All three moved quotations are correct quotations that follow ordinary prose, which is the cost of the rule: they cannot be told from a wrong first word.
The comma case (f07: «…المال، ألا بذكر…») is the most common real-world form and the rule leaves it "uncertain" on purpose, to stay symmetric with the end rule and not tune against the frozen set; the editor settles it with one click.
Not measured: there is no labelled wrong-FIRST-word case in the frozen set (f21 and f29 are missed, not matched), so the rule is tested on synthetic and real-text regression cases only, not on an evaluation set. AI mode was not rerun.

The three demo samples (`app/static/samples`, fallback mode): sample 1 and 2 unchanged (4/5 and 6/7 "matched"); sample 3, the one without brackets, 2 → 1 "matched" (uncertain 2 → 3). Expect more yellow cards on unbracketed text.

**Interface.** An uncertain finding says «غير محسوم — حدود الاقتباس» and «يحتاج مراجعة», explains that this means the quotation boundary could not be established (not that the wording is wrong), shows the neighbouring words, and offers
«حدود الاقتباس صحيحة» (re-checks the same span as the editor's own highlight, with the proposed verse) and «عدّل الحدود بنفسك» (selects the span in the article box, ready for «افحص المقطع المحدَّد»). A note under the summary counts them.
*(Superseded on 2 October evening: the card now asks «أين يبدأ/ينتهي الاقتباس؟», shows the article's word and the verse's word, and offers «نعم، هذا هو الاقتباس كاملًا», ««X» من الاقتباس» and a word-level editor; the detection behind it is unchanged. See the next section.)*


## Uthmani-script quotations (2026-10-02, fallback only, no Groq) — pre-challenge

Full write-up, rules, disclosure and reproduction commands: [UTHMANI.md](UTHMANI.md). Summary of the runs (`eval/results/`):

| Run | Code | Held-out Uthmani set: correct quotations given a wrong correction | Notes |
|---|---|---|---|
| baseline | `976395e` | 30 of 41 | 38 of the 46 detected were graded wrong; run before any Uthmani code, after the set was frozen in `1bc8cbf` |
| run 1 `after-uthmani-layer` | working copy before `0eacaaa` | 11 (one of them the label error) | `madd_sign` and `idgham_shadda` conventions missing |
| run 2 `after-uthmani-layer2` | working copy before the exact-letters rule (a unit test showed that equivalence was still decided at the search-fold level, which equates `أَمَنُوا` and `ءَامَنُوا`; equivalence now requires identical letters, hamza seats included) | 1 | the one is the label error `u32` |
| final `after-uthmani-final` | `0eacaaa` (matching code, unchanged since) | 1 (the label error) | same counts as run 2 |

The three earlier sets (`cases`, `heldout`, `phrases_frozen`) re-run on the final code: rows, negative hits, formula hits and extra findings **identical** to the run on `976395e`
(`eval/results/*before-uthmani-976395e-*` vs `*after-uthmani-final-*`). AI mode was not re-evaluated.
The rules were checked against whole Uthmani texts, with the held-out verses excluded: `eval/check_uthmani_rules.py`, `eval/results/uthmani-rules-*-excl-heldout.json`.


## Long articles with partial, unmarked and one-word-wrong quotations (2026-10-02 night, fallback only, no Groq) — pre-challenge

**What was added.** `eval/articles_frozen.json` (SHA-256 in `eval/articles_frozen.sha256`, commit `efb6fe8`): five articles, 25 gold quotations, 11 sentences that resemble Quran wording but are not Quran text (negatives), 4 everyday formulae. It was **written and frozen before the app was run on any of its articles**, and no detection code was changed afterwards: `git diff` of `app/*.py` between the freezing commit and the interface commit is empty. L1 is 5,809 characters (limit 6,000) with 11 quotations (marked and unmarked, complete and cut short, one wrong word, one wrong ayah number, a whole surah without marks, a short phrase next to prose words) and two look-alike sentences; L2 orphan care; L3 a social post (emoji, a URL, a Latin reference); L4 governance prose; L5 ordinary prose with no quotation. Quran words were read from the Quranpedia text by `eval/build_articles.py`; every label is checked by `eval/validate_articles.py` (own normalisation, not the app's matching code). Like the other sets it was written by the same AI-assisted workflow as the app, so it is **not an independent sample** and probably favours wordings that workflow finds natural; labels still await a human reviewer.

**Run 1 (`eval/results/fallback-20261002-220008-articles-frozen-run1-before-ui.json`, AI off, code `5be1ac3`'s detection = today's).** The only run; nothing was tuned against it.

| Observed | Result |
|---|---|
| Gold quotations detected (any tier, verse shown) | 24 / 25 (marked 11/11; unmarked 13/14; incomplete 7/7; one wrong word 6/6; wrong ayah number 2/2) |
| Missed | 1: «وبالوالدين إحسانا» (two words, occurs in five verses; counted in the notice «لم تُعرض … عبارة قصيرة»; the writer can select it) |
| Of the 14 unmarked: shown as «candidate» / as «possible» | 11 / 2 (one missed) |
| False «matched» wording on a misquotation | 0 |
| Findings on the 11 look-alike sentences or on formulae | 0 / 0 |
| Other findings on unlabelled text | 1: «بعضهم على بعض» (3 words that are in the Quran), «possible», no replacement |
| Wording graded as expected / as an abstention (uncertain) | 16 / 8 |
| Replacement text proposed for the 6 one-word-wrong quotations | 2 (both marked, long enough); 4 only as a difference or «possible» with the verse shown |
| Wrong replacement proposed | 0 |
| Reference | 20 correct, 3 abstained, 1 wrong (see below) |

**What this says and does not say.** Most unmarked quotations are *found*, but 8 of 24 get an abstention, and for the unmarked ones the reason is almost always the boundary rule: a comma or an adjacent prose word does not settle where a quotation ends, so the card asks the writer. That is the design (see the boundary sections above), and it is why the interface now settles it in one step. It is **not** evidence that the search is better than before: the three earlier sets were re-run on the same code and give rows, negative hits, formula hits and extra findings **identical** to the previous final run (`eval/results/fallback-*after-ui-revision-*` vs `*after-uthmani-final-*`; `eval/phrases_frozen.sha256`, `eval/uthmani_heldout.sha256` verify).

**Label problem found after the run (not corrected, per the freeze).** L1's whole-surah quotation (103:1–3, unmarked) follows the words «سورة العصر:» in the article; I labelled its reference «missing», but the page names the surah, so the app reads a surah-only reference as matched. The scorer counts that as one `false_verified_reference`; it is a label ambiguity, not a wrong verdict. The frozen file stays as written.

**Remaining misses and false suggestions on this set:** the missed two-word phrase above; «بعضهم على بعض» shown as «possible» (a true Quran phrase the writer did not mean as a quotation); four one-word-wrong passages get no replacement (three unmarked and one marked three-word quotation, «واستعينوا بالصبر الصلاة», reported as a difference with the verse and no proposed text). None of the 11 look-alike sentences produced any suggestion.

**AI mode was not run on this set.** No claim is made that the model improves detection on long articles.

**Interface (front end only).** Reproduction of every interface state is in `scripts/ui_*_e2e.mjs` (below, TEST_LOG).


### Long-article set, run 2 (2026-10-03): the three-word correction gap — a change made after seeing run 1

**This is a post-hoc change, disclosed as such.** Run 1 above showed six one-word-wrong quotations found but only two given replacement text. I looked at the marked one, «واستعينوا بالصبر الصلاة» (a three-word quotation in ﴿ ﴾ with the correct reference [البقرة: 45]; the Quran has «والصلاة»), and traced it: the quotation boundary is stated by the writer, the reference points at the closest verse, two of three words are equal in order, and yet `propose_wording` stopped at «الفرق كبير بين الاقتباس وأقرب موضع». The cause is the word-level similarity floor `FUZZY_PROPOSE_WITH_REF = 0.75`: a quotation of three words with one word written for another scores 2/3 = 0.667 at most, so **no three-word quotation could ever receive a correction, whatever else was confirmed**; the same case with four words (0.75) does. The floor is a sound guard in general; this is a criterion that cannot be met by construction for one length.

**What changed (`app/verifier.py`, `app/audit.py`; no threshold was lowered).** The floor is waived only when all of these hold: the span's boundaries are stated by a marker or by the writer's own selection (`bounded`: marked or manual, never a span the phrase search or the model chose); a reference **with an ayah number** (or the verse the writer chose) points at the closest passage; no rival passage is close (both pre-existing checks); at least two words are equal in order and **exactly one word differs, written in place of one word** (`_one_word_swapped`). Every other path is untouched, and every proposal is still approved by the writer one by one. Six tests (`tests/test_corrections.py`): the positive case (the article is rebuilt with only that word changed), and the same quotation without a marker, without an ayah number (none, and surah-only), with a reference pointing elsewhere, with two words different, and in a manual selection with and without a chosen verse. The two positive tests fail on the previous code.

**Rerun (fallback, AI off, no Groq call; the six sets, same labels, SHA-256 files verified).** Before: `eval/results/fallback-20261003-0139*-gapbefore-*`; after: `eval/results/fallback-20261003-0140*-gapafter-*`. The main, held-out, phrases-frozen and both Uthmani sets are **identical** (every row, apart from the timestamp). On the long-article set **exactly one row changed**: «واستعينوا بالصبر الصلاة» went from `review_only` to `proposed`, and the harness verifies the corrected excerpt as matched at the gold location. Replacement text proposed for the six one-word-wrong quotations: **2 → 3**; wrong replacements 0; replacement on a correct quotation 0; the other counters unchanged (24 / 25 detected, one extra finding, one missed).

**What is deliberately still not offered, and why.** (1) «ومن يتق الله يجعل له فرجا» (unmarked): the span stops before the wrong last word and its end is not settled, so the card asks about the boundary first. (2) «ألا بذكر الله تطمئن النفوس» (unmarked): both boundaries are unsettled. (3) «إنما نطعمكم … أجرا ولا شكورا» (unmarked, near match): shown as «possible»; no replacement until the writer says it is a quotation. All three are possibilities that need the writer's choice. (4) «وبالوالدين إحسانا» stays missed (two words, occurs in five verses): no threshold was lowered for it. The fallback is manual selection, checked on the real article: selecting the words lists the candidate verses (البقرة: 83، النساء: 36، الأنعام: 151، الإسراء: 23) and choosing الإسراء: 23 gives a matched result with the vocalised form as an optional change.

**How far this can be trusted.** The fix was written after seeing this case in this set, so the 3 / 6 is **not** an independent measurement: it shows that one concrete defect is gone and that nothing else moved on the 121 labelled quotations of the five other sets; it says nothing about how often real three-word misquotations occur. The sets are small, author-written (same workflow as the app) and still await a human reviewer.


## Verse suggestion while writing (3 Oct 2026, no AI, no network but the cached Quranpedia text) — pre-challenge

`POST /api/suggest` (`app/suggest.py`) looks the words before the caret up in the loaded Quranpedia text and proposes the next words of a verse
(*continue*), the end of a word being typed (*complete_word*), a probable correction of the last word (*replace*) or words left out (*insert*). It never
calls a model. Two frozen sets of 129 cases each (76 expect a suggestion, 14 are ambiguous or repeated openings, 39 expect silence), scored by
`eval/run_suggest_eval.py` (judging rules in its docstring; label validity by `eval/validate_suggest_cases.py`, independent of the app's matching code).

**Neither set is independent evidence.** Both were written by AI-assisted workflows and **no human Arabic or Quran specialist has reviewed the labels**.

| Set | File (SHA-256 sidecar) | Provenance | Status |
|---|---|---|---|
| A | `eval/suggest_cases_20261003.json` | Found uncommitted in the working tree at 15:16 on 3 Oct, author not established. It claimed to be "blind to the implementation", but its file time is later than `app/suggest.py`'s, so that claim is **unverified and not relied on**. The claim was replaced by this statement in its `_about` before freezing. | **Development set.** Rules were changed after run 1 (below). |
| B | `eval/suggest_cases_b_20261003.json` | Written by a separate AI subagent in a fresh context, instructed not to read `app/suggest.py`, `suggest-ui.js`, `app.js`, the suggestion tests or call the endpoint; gold ayahs disjoint from A's. The agent reported it opened none of them; I cannot prove it. Frozen (checksum) before it was run. | **Run once**, on the final rules, after which no rule was touched. |

### Set A, four runs (a development set: the changes between runs are listed, so the later numbers are not held-out)

| Run | Code | Hits (of 76) | False suggestions on the 39 silence cases | Ambiguous/repeated (14): safe | Corrections right (of 22) |
|---|---|---|---|---|---|
| 1 | the code as found | 71 (1 *wrong verse*, 4 missed) | 0 | 14 (0 confident single choice) | 20; **1 was an exact continuation from the wrong verse** (SG-046) |
| 2 | + a long exact beginning beats a short match of the whole run elsewhere; a wrong last word is a probable correction also while it is still being typed (the brief's «لعبادتي ← ليعبدون» had returned nothing) | 73 | 0 | 14 | 22 |
| 3 | + an explicit request gets the lowest word bar (it had been held to the 3-word bar of "a Quran cue earlier in the sentence") | 74 | 0 | 14 | 22 |
| 4 | final, nothing changed since 3 | 74 | 0 | 14 | 22 (0 shown as exact) |

Changes 2 and 3 were made because of defects found while exercising the feature (the brief's own example, SG-044/046, then a UI test of the explicit action),
not by lowering a threshold. Result files: `eval/results/suggest-20261003-*-suggest_cases_20261003-*.json`.
The two remaining misses (SG-012, SG-109) are conservative silences («قل هو الله» is common; a phrase containing the formula «محمد رسول الله» is held back).

### Set B, one run on the final rules

| Measure | Result |
|---|---|
| Detection: expected suggestion given, right verse, right words, right kind | **71 of 76 (93.4%)**; 0 wrong words, 0 wrong verse |
| False suggestions where silence was expected (hadith/du'a/proverb cues, everyday formulas, text after a closed quotation, no cue, complete verses, one word) | **0 of 39** (32 of the 39 end in a Quran-looking sequence) |
| Ambiguous and repeated openings | **14 of 14 safe**: 11 offered several verses and flagged them, 3 stayed silent; 0 answered with one confident choice |
| Correction quality (wrong word, left-out word) | **19 of 22 (86.4%)**; all 19 shown as *probable*; none as exact; 3 missed |
| Lookup time (in-process, this laptop) | median 1.4 ms, p95 2.7 ms, max 14 ms |

The five misses are all silences, never a wrong suggestion. SG-009 and SG-055: the cue vocabulary does not know «في التنزيل العزيز» or «في كتاب الله»; SG-010: «وقوله تعالى حكايةً عن يعقوب:»
is not read as a lead-in when extra words come before the colon; SG-047 and SG-061: a three-word anchor made of common words falls under the rarity bar for a correction (SG-061 is checked only as far as
`best_anchor` = 3 words; I did not trace the mass value). **Not fixed, deliberately**, so that B stays untouched; they are the first item of the roadmap (fresh set C needed to measure any change).

### 4 Oct 2026: where the first insertion stops (a rule change after both sets had been run; disclosed reruns)

A first-time-writer walkthrough (3 Oct, `docs/TEST_LOG.md`) found that «أدرج» after «… أن تؤدوا الأمانات» inserted «إلى أهلها وإذا حكمتم»: a fixed four
words that ran into the next clause. The first piece is now chosen from the verse's structure (`_chunk_bounds` in `app/suggest.py`): it stops at the
pause sign the Hafs text itself carries, or before a word that opens a new clause, and never ends on a particle that governs the next word; the rest of
the verse is offered next (one more Tab) or at once («إلى نهاية الآية»). Every inserted word is still a word of the chosen verse. No detection, place,
trigger or correction rule changed.

Across every word position of the 6,236 verses (a property of the rule, not an accuracy measurement):

| | Old rule (four words) | New rule |
|---|---|---|
| First pieces that run across a pause sign of the Hafs text | 10,813 | 0 |
| Mid-verse pieces ending on a governing particle («إلى», «أن», «الذين», «إلا» …) | 10,572 of 48,578 | 5 of 50,900 (2 at the five-word ceiling, 3 at the source's saktah mark) |

Both frozen sets were rerun on the final rule. **Set A is a development set; set B had been run once (above) and this is a post-hoc rerun after a rule
change, so neither number is held-out evidence.** Set B was also run once on an intermediate version of the rule (whose last piece could end on «عن» and
which split «ومن يتوكل على الله | فهو حسبه» too early); its summary was the same as the final one, and its result file was not kept. Neither set was used
to choose the rule: the two fixes after the intermediate run came from reading the pieces the rule produced, which the sets list.

| Set | Hits (of 76) | Wrong words | Wrong verse | False suggestions (of 39) | Ambiguous safe (of 14) | Corrections (of 22), shown as exact |
|---|---|---|---|---|---|---|
| A, run 4 (3 Oct) | 74 | 0 | 0 | 0 | 14 | 22, 0 |
| A, 4 Oct | **71** | **3** | 0 | 0 | 14 | 22, 0 |
| B, only run (3 Oct) | 71 | 0 | 0 | 0 | 14 | 19, 0 |
| B, 4 Oct (post-hoc) | **69** | **2** | 0 | 0 | 14 | 19, 0 |

The five new *wrong words* are one pattern: the source has a pause sign right after the next word, so the first piece is that word alone, which is
a correct prefix of the two gold words the scorer requires: «والأرض ۚ» (A: SG-004), «لأزيدنكم ۖ» (SG-027), «مصباح ۖ» (SG-107), «السيئة ۚ» (B: SG-006),
«لهم ۖ» (SG-014). Stopping there is the intended behaviour (the defect was going on into «ولئن كفرتم»), so the rule was kept and the labels and the
scorer were left as they are. Result files: `eval/results/suggest-20261004-*-chunk-final.json`.

**A further run after an independent review (4 Oct, ~02:10).** The review found that the particle list was compared on folded words, so «إليّ», «عليّ»
(a pronoun ending, which can end a phrase) and «بيّن» (a verb) were taken for «إلى», «على», «بين»; 29 of the 31 pieces counted above ended on them at a
pause sign, and pieces stopped needlessly before them. The list is now compared on letters (and «بيّن» by its shadda). Both sets were run again
(`…-chunk-letters.json`): **summaries identical** to the runs above; one row in B changed its piece («بَشَرٌ مِثْلُكُمْ يُوحَىٰ» → «… يُوحَىٰ إِلَيَّ»),
still «ok_choices». This is a third run of set B overall and the second after its first; it was not used to choose anything.

### What these numbers do not show

Whether a writer accepts, ignores or is annoyed by a suggestion (no user study); behaviour on text outside these sets; the effect of a writer's own spelling habits beyond the cases written; any gain in speed.
The browser behaviour (acceptance only by Tab/click/tap, dismissal, stale answers cancelled, no request during ordinary prose) is covered by `scripts/ui_suggest_e2e.mjs`, not by these sets.

## Long articles, second set (3 Oct 2026, fallback only, no Groq) — pre-challenge

`eval/articles_long_20261003.json` (SHA-256 in the `.sha256` sidecar; validator `eval/validate_articles_long_20261003.py`, independent of the app's matching code, prints `labels OK`):
10 articles of 8,060–14,700 characters (102,356 in all), 191 gold quotations from 65 surahs (96 marked, 95 unmarked; 123 worded correctly, 68 with an error; 8 in Uthmani script), 45 negatives, 33 formulas.
Written by a separate AI subagent in a fresh context under the same "do not read the detector" rules as suggestion set B (it reports it did not open `app/audit.py`, `phrases.py`, `verifier.py`, `suggest.py`), **disjoint from the gold ayahs of `articles_frozen.json`**.
Its `_about` discloses that a few prose passages were reworded after the validator listed Quran-like runs in them. AI-written, **not human-reviewed**; run once, nothing tuned afterwards.
It is the first set with articles longer than 6,000 characters; the longest is 14,700, so **nothing between 14,700 and 20,000 characters was evaluated for accuracy** (that range was only measured for time and memory, below).

Run: `python eval/run_eval.py --mode fallback --cases eval/articles_long_20261003.json --tag long-20261003-first-run` → `eval/results/fallback-20261003-164630-long-20261003-first-run.json`.

| Measure | Result |
|---|---|
| Detection (a finding at the right place) | **186 of 191 (97.4%)**; marked 96/96; unmarked **90/95**; short quotations 20/24; Uthmani 8/8 |
| Wording: a misquotation reported "matched" | **0** |
| Wording graded right / abstained («غير مؤكد») / wrong | 169 / 17 / 0 of the 186 detected |
| Corrections offered | wording: 29 right, **0 wrong**, 38 review-only; reference: 12 right, **0 wrong**; 0 corrections proposed to a correct quotation or reference |
| Confirmed verdicts on negatives or formulas | **0** (2 negatives and 3 formula fragments were shown as «possible», never as confirmed) |
| Other Quran-like phrases shown as «possible» that are ordinary prose | 15 in 102,356 characters (about one per 6,800 characters), none confirmed |
| Reference "matched" where the label says "missing" | **4 by the runner's count** (see below) |
| Time per article (in-process, this laptop) | mean 0.58 s, max 1.18 s |

**The four references.** In each (`LA01` «ولا تقف ما ليس لك به علم», `LA06` «وأنزلنا من السماء ماء طهورا», `LA07` «وَجَعَلْنَا اللَّيْلَ وَالنَّهَارَ آيَتَيْنِ» and «أَوَلَمْ نُعَمِّرْكُمْ…») the prose names the **correct surah** just before the quotation
(«في سورة الإسراء: …»). The author labelled the reference "missing" while the program, under the policy of the older sets (`eval/run_eval.py`: a surah named without an ayah confirms an unambiguous quotation), reports "matched".
They are a disagreement between a label and a documented policy, not a wrong ayah; I did not change the frozen labels, and a reviewer may reasonably prefer "uncertain" for a surah-only mention (roadmap).
**Five missed quotations** (e.g. «فَاسْتَبِقُوا الْخَيْرَاتِ», two words, repeated in the Quran, footnote reference) are short or repeated phrases without markers; they are the known limit of the unmarked search.
Reference abstentions (50) are mostly «difference» quotations: the reference stays «غير محسومة» until the wording is settled, by design.

### 4 Oct 2026: what the «possible» tier holds, and where the interface puts it (no detection change)

The interface review found ordinary prose, «في كل عام» (an exact match of التوبة 126, three common words, no marker, no reference), as the first item to decide in
`LA01`. It comes from the unmarked-phrase search, tier «possible», reason code `common`. To decide whether such an item should lead the queue,
`eval/possible_tier_composition.py` counted what the «possible» tier holds on the two labelled article sets (`articles_frozen`: 5 articles of 434–5,809 characters; `articles_long_20261003`: 10 of 8,060–14,700) (`eval/results/possible-tier-20261004-005103.json`):

| Reason code of the «possible» item | Overlaps a gold quotation | Does not |
|---|---|---|
| `approximate` (a near miss: some words differ) | 27 | 5 |
| `common` (exact, but short or common) | 10 | 14 |
| `non_quran_cue` (a hadith/du'a cue precedes it) | 4 | 1 |
| `non_quran_cue` + `common` | 1 | 1 |

So an exact-but-common item is a real quotation about two times in five on these sets (11 of 26), and in `LA01` itself five of its seven are real
(«وقل رب زدني» and «وما يعقلها إلا» are misquotations). Hiding them, or raising a threshold, would lose real quotations; nothing was changed in detection
(the seven detection sets were rerun on 4 Oct and their rows are identical to the recorded runs). What changed is the order and the wording in the interface:
an unconfirmed `common` item without `approximate` is listed as «عبارات للتأكيد: قد تكون اقتباسات», still marked in the text and reachable, after the
concrete decisions; the headline counts it apart («و٧ عبارات تشبه آيات ولم نتأكد أنها اقتباسات، تنتظر تأكيدك») instead of among the quotations found.
`approximate` items stay in the main queue (27 of 32 real, mostly misquotations). These counts are from author-written, unreviewed labels on development data;
they guided an ordering decision and are not a precision estimate.

**Later on 4 Oct (release review of PR #2), presentation only.** The same items now also *look* optional: the group reads «عبارات للتأكيد (اختياري): قد تكون اقتباسات» and is
closed while concrete decisions wait, each row says «تأكيد اختياري» in a neutral style instead of the decisions' amber «يحتاج تأكيدك», the phrase is not shaded in the text
(a grey dotted line only), its card is titled «العبارة» rather than «الاقتباس» and says it may be ordinary prose and is copied as written if left alone, and the headline says
«…؛ تأكيدها اختياري». No detection code changed. Before merging, the seven detection sets were rerun in fallback mode (`eval/results/fallback-20261004-0722*-release-20261004-*.json`)
and the two suggestion sets (`eval/results/suggest-20261004-072257-*-release-20261004.json`): rows, negative hits, formula hits and extra findings are identical to the
recorded runs (`…-recheck-*`, `…-long-20261003-first-run`, `…-gapafter-uthmani-*`, `…-chunk-letters`); only the run times differ. Suggestion hits stay A 71/76 and B 69/76, 0 of 39 false.

### Length: measured, not assumed (`scripts/measure_length.py`, `eval/results/length-20261003-local.json`; macOS arm64, Python 3.14, AI off, median of 3, fresh process)

| Input | Characters | Audit time | Findings | Response | Process memory |
|---|---|---|---|---|---|
| Real long articles (set above) | 8,060–14,700 | 0.40–0.76 s | 16–27 | 59–102 KB | 86.8 MB at the end of all runs |
| Dense (the older eval articles joined: 64 quotations per 6,000 characters) | 6,000 / 10,000 / 15,000 / 20,000 | 0.39 / 0.62 / 0.95 / 1.21 s | 64 / 107 / 150 / 150 | up to 581 KB | 83–86 MB |
| 20,000 characters of running mushaf text, no markers | 20,000 | 1.18 s | 2 | 59 KB | 86.7 MB |
| Pathological: the 60 most frequent Quran words in a row | 6,000–20,000 | 1.37–1.47 s | 0 | 1 KB | 86.8 MB; **stops at the search's work budget and says so** |

Findings: time grows about linearly (about 60 µs per character); one source download per server start whatever the length (no per-quotation network call); the dense input reached the 150-passage cap, which previously dropped the rest **silently**
(fixed: a warning now says how many passages were left out and the line where the list stops). `MAX_SEED_STEPS` was doubled (80,000 → 160,000) for the 20,000-character limit; the test that real mushaf text of that length is searched in full still passes.
**Not measured: Render.** Render Free has far less CPU than this laptop; the numbers are local. The limit is therefore stated as measured here and re-checked on Render after deployment (see TEST_LOG).
The model is asked only about articles up to 6,000 characters (`AI_MAX_ARTICLE_CHARS`), because Groq's free tier refuses larger requests; a longer article is audited in full without it and the result says so.

### Length on Render Free (3 Oct 2026, 17:42–17:53 +03, build `a844fc3`; `scripts/measure_length.py --url … --runs 1`, `"ai": false`, `eval/results/length-20261003-live.json`)

| Input | Characters | Time to the answer (client side) | Server `elapsed_ms` |
|---|---|---|---|
| Real long articles (set above), 7 of 10 | 8,050–8,820 | 8.1–10.4 s | — |
| Real long articles, the 3 longest | 14,190–14,700 | 14.4–15.2 s | — |
| Dense (older eval articles joined) | 6,000 / 10,000 / 15,000 / 20,000 | 8.7 / 14.4 / 19.0 / **24.0 s** | 7.6 s at 6,000; 13.0 s at 10,000 |
| 20,000 characters of running mushaf text | 20,000 | 25.4 s | — |
| Pathological (most frequent words), stops at the search budget | 6,000–20,000 | 27.8–29.4 s | — |

About **1 ms per character** on the free host, roughly 20 times slower than this laptop (0.06 ms): a realistic 8,000–15,000-character article is audited in 8–15 s, the 20,000-character limit in about 25 s, and the worst input I could build in under 30 s. No timeout in this run.
**An earlier run of the same script timed out at 180 s on one request.** That run printed its table only at the end, so I do not know which input it was; the script now prints each row as it goes and records a failure as a result. The rerun completed all 22 inputs. I did not find the cause (a cold or restarting instance is possible); treat "no timeout" as one clean run, not a guarantee.
Memory on Render was **not** measured (the host does not expose it); locally the process peaks at 87 MB. A live journey (`scripts/live_workspace.mjs`, desktop and 390 px, model off by the writer) audited a 17,532-character article in 16.0 s and 17.5 s; the page now says, after 7 s, that a long article takes tens of seconds on the free host.



## Hard quotations: retrieval anchored on the writer's own cues (4 Oct 2026 evening, challenge period, fallback only, no Groq)

**Problem.** The unmarked-phrase search must keep ordinary Arabic from looking like a verse, so it ignores short, common or loosely
matching phrases. That is right for running prose, but it also drops quotations that the writer announced: «قال تعالى: إن الله لا يضيع
أجر المصلحين» (the verse has «المحسنين»), «وقل رب زدني فهما [طه: 114]», «… رقيب شهيد (ق: 18)» (the verse ends «عتيد»). Exploratory probes
(not evidence) showed four failure points: (1) a near match after a lead-in was cut at the wrong word or matched to a neighbouring verse;
(2) a short misquotation right before its own ayah reference was reported only as its correct part, or not at all; (3) quotation marks
without a lead-in were not used at all; (4) a citation verb («فلنتأمل قوله ربنا آتنا …») was read as a misspelt «يقول» of the verse, so a
correct quotation read as a «difference».

**What was built (`app/cues.py`; wired in `app/audit.py`).** Windows the writer announced: the words right after a lead-in (the
phrase search's list plus «يقول الله عز وجل», «في كتاب الله», «بقوله» …; nouns such as «القرآن», «الآية» only before a colon), the words
right before a reference in citation form (brackets, a dash, or «طه: 114»; «… في سورة العنكبوت» in running prose does not count), the
words right after «… الآية 11:», and the words inside «…», "…", “…”. Each window is aligned word by word to the source: to the named verse
and its neighbours, the named surah, or (lead-in, quotation marks) the whole text. Acceptance needs two exact words and a similarity of 0.6,
plus: with an ayah reference, two or three matched words next to it; a named surah, three words and rarity mass 8; a lead-in, three words and
mass 12; quotation marks, three words, mass 12 and most of the quote. The span shown is the aligned hull, widened by one unmatched word only
at an edge the cue states (after the lead-in, before the reference, inside the marks), and only where the verse has a word there.
Grading is the audit's usual one, with one rule extended from model-only spans to the search: the writer's own words vouch for a span —
an exact phrase announced by a lead-in or by an ayah-level reference to that verse is the writer's stated quotation; a **near match** is
stated only when an adjacent ayah reference names the matched verse **and both edges are settled**; anything else stays «possible», with
the verse choices and no replacement until the writer confirms. Safety additions: an unmarked span never gets a deletion proposed at its
first or last word (`verifier.propose_wording`); a cue span inside brackets is dropped; a doubled bracket («﴿﴿ … ﴾﴾») counts as one
(`extraction/marked.py`; before, it put the pairing out of step and made a paragraphs-long «quotation»). Model spans still rank below all of
these and cannot replace or suppress them.

**Diagnostic set, written before tuning** (`eval/hard_quotes_dev_20261004.json`, `…_heldout_…`, SHA-256 sidecars, validator
`eval/validate_hard_quotes_20261004.py`, builder `eval/build_hard_quotes_20261004.py`, commit `e296825`). **Assistant-authored development
data**: written by an AI subagent (Claude) in a fresh context, told not to read the detector; not human-reviewed; not independent. Dev: 71
articles, 81 gold quotations (39 correct, 42 misquoted: substitution 13, omission 9, wrong first word 6, wrong last word 9, extra word 2, two
errors 3), 38 negatives. Held-out: 48 articles, 56 quotations, 27 negatives; gold verses disjoint from dev and from the older sets. Contexts:
none, lead-in, ayah reference, surah reference, quotation marks, brackets, Uthmani-like, footnote reference; three/two long articles of
2,500–6,000 characters. Known artefacts: the builder wrapped every marked quotation twice («﴿﴿ ﴾﴾», «««»»»), which is not how most writers
type (it exposed the doubled-bracket defect above); its «Uthmani» cases are Quranpedia words with Uthmani marks added, not real Uthmani
spelling; hadith and du'a negatives were written from memory.
Scorer: `eval/run_hard_quotes.py` (four measures reported apart; a simulated confirmation step: the writer selects the gold span and
picks the gold verse among the choices shown, through `run_phrase`).

**Order of work (so the reader can judge what was tuned on what).** The retrieval was written from exploratory probes and committed
(`365b78d`) before the dev split was opened. Its rules were tightened **after** the seven frozen sets were rerun against `05e34d5` and showed
two new false «possible» items, one reference taken from a neighbouring quotation, two wrong corrections (a deletion of the edge word) and
one correct quotation read as a difference (noun cues need a colon; citation form for a reference before the words; lead-in mass 10 → 12;
a gap in the alignment must be backed by two matched words or one rare exact word; phrase places used as hints are widened; the edge-deletion
guard). That is tuning on frozen data, disclosed here; the rows it changed are all listed by `eval/compare_runs.py`. After the dev split was
opened: the doubled-bracket fix and the "both edges settled" condition. The held-out split was run **once**, on `b8d866b`, after which no rule
changed.

**Results (fallback; same labels; "detected" = a finding covers half the gold span and offers the gold verse).**

| Measure | Dev, `05e34d5` | Dev, `b8d866b` | Held-out, `05e34d5` | **Held-out, `b8d866b` (only run)** |
|---|---|---|---|---|
| 1. Detected (of all gold) | 64 / 81 | 73 / 81 | 49 / 56 | **54 / 56** |
| · required (marked, announced or 4+ distinctive words) | 62 / 74 | 71 / 74 | 46 / 50 | **49 / 50** |
| · desirable (2–3 word unmarked) | 2 / 7 | 2 / 7 | 3 / 6 | **5 / 6** |
| · found, but the gold verse not offered | 12 | 2 | 6 | **1** |
| 2. False possibilities (negatives / unlabelled text; none shown as confirmed) | 2 / 1 | 2 / 1 | 2 / 1 | **2 / 1** (2.2 per 10,000 characters) |
| 3. Misquotations reported "matched" | 0 of 42 | 0 of 41 | 0 of 27 | **0 of 27** |
| · correct quotations read as «difference» | 0 | 0 | 2 | **2** (the same two; «possible», no fix offered) |
| 4. Fixes before the writer acts: right / wrong / on correct text | 3 / 0 / 0 | 3 / 0 / 0 | 2 / 0 / 0 | **2 / 0 / 0** |
| · a fix where the label says "not before confirmation" | 1 | 1 | 0 | **0** |
| · replacement words or references not from the finding's own verse | 0 | 0 | 0 | **0** |
| After a simulated confirmation: misquotes right fix / wrong fix / no fix | 33 / 0 / 5 | 33 / 0 / 6 | 22 / 0 / 4 | **23 / 0 / 4** |
| · writer actions needed (1 = pick the verse, 2 = adjust a boundary then pick) | 41×1, 7×2 | 47×1, 6×2 | 32×1, 4×2 | **35×1, 4×2** |

The one dev fix "where the label forbids" (HD-037, «إنك لا تهدي من تحب …» right before «(سورة القصص، الآية 56)») is the right fix
(«تحب» → «أحببت»); the label's contract asked for a marker as well, the product accepts an adjacent ayah reference plus settled edges.
That is a disagreement with a pre-registered label, reported rather than relabelled.

**Seven frozen detection sets** (fallback, labels and checksums unchanged; before `05e34d5` = `eval/results/fallback-*-challenge-baseline-05e34d5-*`,
identical to the 4 Oct release runs; after = `…-cue-final-*`; every changed row: `python eval/compare_runs.py --tags challenge-baseline-05e34d5 cue-final`):

| Set | Detected | False «matched» wording | Wording right / abstained | Fixes right / wrong / on correct text | Review-only misquotes | False suggestions (shown as confirmed) | Rows changed |
|---|---|---|---|---|---|---|---|
| `cases` | 27/28 | 0 | 26 / 1 | 6 / 0 / 0 | 0 | 0 (0) | 3 |
| `heldout` | 6/6 | 0 | 3 / 3 | 0 / 0 / 0 | 0 | 0 (0) | 1 |
| `phrases_frozen` | 30/32 | 0 | 18 / 12 | 0 / 0 / 0 | 10 | 2 (0) | 1 |
| `articles_frozen` | 24/25 | 0 | 16 / 8 → **17 / 7** | 3 / 0 / 0 | 3 | 1 (0) | 3 |
| `articles_long_20261003` | 186/191 → **188/191** | 0 | 169 / 17 → **174 / 14** | 29 / 0 / 0 → **49 / 0 / 0** | 38 → **18** | 20 (0) → **19 (0)** | 57 |
| `uthmani_dev` | 6/6 | 0 | 6 / 0 | 0 / 0 / 0 | 0 | 0 (0) | 0 |
| `uthmani_heldout` | 48/49 | 0 | 45 / 2 | 8 / 0 / 1 | 1 | 0 (0) | 6 |

(The one fix on correct text in `uthmani_heldout` is the known label error `u32`, unchanged.) Most changed rows are a distinctive phrase
after a lead-in or with its ayah reference moving from «candidate» to «stated» (no change of wording or fix). On the long set, 20 near
misses with an adjacent ayah reference now get the right source fix before the writer acts (review-only 38 → 18); two missed quotations are
found («إن الله غفور رحيم», «فصبر جميل», both announced); one formula fragment («وقال حسبنا الله ونعم الوكيل») is no longer suggested. Two
references read «uncertain» instead of «matched» because their quotation now reads as a «difference» (by design: a reference is not
confirmed while the wording is in question). Time per long article (local): mean 0.57 → 0.61 s, max 1.15 → 1.22 s.

**What this does not show.** The sets are small, assistant-written and unreviewed; the dev numbers are development data; the held-out
numbers are one run on 56 quotations, so a difference of a few items is not a rate. Not solved: two- and three-word famous phrases with no
cue («أضغاث أحلام», «كن فيكون») are still missed by design; an unmarked substitution made of common words («إنهم كانوا يتسابقون في
الخيرات») is missed; a wrong last word that ties with a neighbouring verse can offer the wrong verse first (HD-017 «… رهين»); ordinary prose
that is a short Quran run («في كل عام», «كما ربياني صغيرًا») is still shown as optional «possible». No real writer has used it.


## The model's measured contribution and failures (4 Oct 2026 evening, challenge period)

**Why.** Since `47f224e` every audit of an article up to 6,000 characters sends it to the model automatically, so the model has to earn
that transfer. Earlier evidence was anecdotal (live demo calls: `added_only = 0`; occasional HTTP 429).

### 1. Failures, simulated (no network)

`tests/test_provider_failures.py` with a fake Groq (`tests/fake_groq.py`), released in PR #3 (`d65befa`): 429 rate limit (minute and
day), 429 request too large, timeout, connection failure, 500/502/503, 401, malformed JSON, truncated output, empty answer, 400
`json_validate_failed`, an unexpected client error, an answer with nothing, an answer with spans not in the article. Every case ends in
the same complete source-based audit as `AI_PROVIDER=none`, one request per audit, none during the cooldown, one after it, and nothing
leaked to `/api/health` or the logs. Six defects were fixed (details in `docs/TEST_LOG.md`), among them a cooldown skip reported as a
failure and a traceback that could put article text in the server log.

### 2. Contribution, paired (same articles, same code, with and without the model's answer)

Method (`eval/ai_record.py`, `eval/ai_contribution.py`): each article was sent to Groq **once** through the production adapter
(`qwen/qwen3.8-27b`, prompt v2, `reasoning_effort: none`, 800 output tokens reserved, calls 65 s apart, stop after two consecutive 429s); the
answer was stored in a private evidence folder outside the repository; the audit was then run in-process twice on the current code
(`070263b`'s detection): without a model, and with a stand-in provider that returns exactly the recorded answer. Sample: every article of the
labelled sets that the service would send to the model (≤ 6,000 characters): the four demonstration samples, `cases` (14), `heldout` (4),
`articles_frozen` (5), `phrases_frozen` (49) — 76 articles, 21,423 characters. These are author-written evaluation sets, not real articles.

| | Result |
|---|---|
| Groq calls | 76: **75 HTTP 200**, **1 HTTP 400** (`json_validate_failed`, «Failed to generate JSON» — the first 400 whose body was kept; a model structured-output failure) |
| Latency (answered calls) | median 428 ms, max 1,619 ms; 47,967 tokens in all (median 551 per call) |
| Answers with no proposal | 56 of 75 |
| Proposals / found in the article / discarded | 54 / 53 / 1 |
| Proposals the source search had also found (same span) | 50 |
| Proposals overlapping a deterministic finding (kept as evidence only) | 2 |
| **Findings only the model proposed** | **1**: «ادعوني أستجيب لكم» (`cases` c12), a real misquotation; shown «possible», no replacement |
| False «possible» items added by the model | **0** |
| Deterministic findings changed by the model (harm check) | **0** |

So on these sets the model added **one real quotation in 21,423 characters (≈ 0.5 per 10,000)** and nothing false. The roadmap's rule
(§1.5, fixed before this run) keeps the model on by default only at ≥ 2 true additions and ≤ 1 false addition per 10,000 characters: **the
rule is not met**. The roadmap's consequence would be to switch the model off on the server (`AI_PROVIDER=none`) and say so on `/privacy`.
**That was not done**: the owner asked to decide it. Recorded for the decision: the model costs one transfer of each short article to Groq;
it found one quotation the search missed and harmed nothing; when it fails the audit is complete without it.

### 3. Live probes (one labelled call per released code increment)

| Build | When (Riyadh) | Result |
|---|---|---|
| `aee587c` (harness + detection + hardening) | 21:17:12 | **HTTP 429**, 240 ms, «Request too large … output tokens per minute (OTPM): Limit 1000, Requested 1556»; outcome failed; page showed the full source audit and the calm failure line (24 journey checks PASS). A local call had been made less than a minute earlier on the same Groq organisation, so this one may be the minute window. |
| `91568af` (+ import) | 21:33:40 | **HTTP 429**, 234 ms, same message, «Requested 2834»; no local call in the 4 minutes before. Not explained by spacing. |
| `bee3e03` (default reservation 800, PR #10) | 22:57:59 | **HTTP 200**, model 920 ms, proposed 4, located 4, discarded 0, `added_only` 0, `also_found` 4; audit 8.9 s (cold source). The local recorder was paused and no call was made in the 100 s before. |

Both live calls failed while 75 local calls with an 800-token reservation succeeded, so the service's own configuration is the first thing
to check (`GROQ_MAX_COMPLETION_TOKENS` on Render; `/api/health` reports it as `ai_max_completion_tokens` from this release on).
Live probes were stopped after these two (rule: no retry after repeated 429s). After PR #9, `/api/health` on the live service reported **`ai_max_completion_tokens: 4096`**: the 800 recorded on 3 Oct was not in effect on Render. PR #10 made 800 the code default (the largest answer measured tonight used 341 output tokens), and the one probe of that release answered HTTP 200 (row above). One answered call shows the setting works; it is not a reliability rate.

### 4. A narrower role, prototyped (not in the product): triage of «possible» phrases

`eval/ai_triage_experiment.py`. For each «possible» item the current code shows, the model sees only the sentence around it (≤ 280
characters, never the whole article) and answers quote / prose / unsure. It never sees or writes verse text and decides nothing; the
decision rule was written into the script **before any call**: worth building only if it says "prose" for at least half of the items that
are not quotations and for at most one in ten of the real quotations.

| Run | Items (real quotation / prose) | "prose" for prose items | "prose" for real quotations (the harmful error) | Rule |
|---|---|---|---|---|
| 1: `articles_frozen` + `articles_long_20261003` (12 calls, 21:17–21:29) | 19 / 20 | **17 of 20** | **1 of 19** | passes |
| 2: `hard_quotes_dev` + `hard_quotes_heldout` (64 calls, 21:35–22:43; rule and prompt unchanged) | 65 / 6 | **5 of 6** | **4 of 65** | passes |
| Both | 84 / 26 | 22 of 26 (85%) | 5 of 84 (6%; Wilson 95% upper bound ≈ 13%) | — |

All 76 calls answered HTTP 200 (300 output tokens reserved); no "unsure" answers. Results: `eval/results/ai-triage-20261004-213000-existing-sets.json`,
`…-224349-hard-sets-confirmation.json`; raw answers in the private evidence folder.

**What this does and does not show.** On two small runs the model separated the writer's own prose from recited verses well enough to pass the rule fixed in advance,
which the extraction role (section 2) does not. But: the sets are author-written and unreviewed; 26 prose items and 84 quotations are too
few (the upper bound of the harmful rate is above the 10% bar); and its errors fall on the items that matter most — two clear recitations
(«واصبر لحكم الله فإنك بأعيننا» after «وتردد:», «إنما نطعمكم لوجه الله …») were called prose, and most of the real items are near-miss
misquotations, which a demotion would push out of the main decision flow. It would also be a new transfer: sentences of articles of any
length would go to Groq. **Not built into the product.** If the owner wants it, the safe shape is an ordering hint for exact, common
phrases only (never for near misses), the item always visible, after a larger held-out check written by someone else.

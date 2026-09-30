# Evaluation

**What these numbers are and are not.**

- The labelled set is small (14 articles, 28 gold quotations, 5 non-Quran negatives).
- The articles were written by the project author for this test, using the same AI-assisted workflow that built the app. They are not an independent sample of real articles.
- A human reviewer still needs to confirm the labels (checklist: `docs/LABEL_REVIEW.md`).
- The results show how the pipeline behaves on the listed case types. They are **not** a general accuracy figure.
- **AI mode (Groq, 30 Sep 2026) responded on every case but added no detections**; see "Results — AI mode".

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

## Next steps

1. A human reviewer (ideally someone with Quranic studies background) reviews every label in `eval/cases.json`.
2. Add real, independently sourced articles (with permission), including Uthmani-script quotations and quotations with omissions («…»).
3. Run AI mode three times to check repeatability, then report the mean and range.

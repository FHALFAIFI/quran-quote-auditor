# Label review checklist (for an Arabic reader or Quranic-studies specialist)

**Purpose.** The evaluation set in `eval/cases.json` (v1) was written by the project author with an
AI-assisted workflow. `eval/validate_labels.py` cross-checks the labels mechanically against the Quranpedia
Hafs text, but a qualified human has **not yet reviewed them**. Until that happens, results on this set must
be described as "on a small author-written set whose labels are pending human review".

**Rules for the reviewer**
- Use the King Fahd Complex mushaf (Hafs) or https://quranpedia.net as the reference text.
- Do **not** change a label to improve a metric. Change it only if it is wrong, and record the reason and source below.
- Do not edit the article text of a case. If an article is unrealistic or misleading, note it instead.
- Tick ☐ → ☑ when a row is confirmed.

## What to confirm for each quotation

1. **Location**: the gold surah:ayah (range) is where this wording occurs.
2. **Wording label**: `correct` (same words as the mushaf; missing diacritics are *not* an error),
   `wording_error` (a word differs), or `diacritics_error` (letters right, a written vowel contradicts the mushaf).
3. **Ambiguous**: `yes` only if the exact phrase occurs in more than one verse.
4. **Reference label**: `correct`, `incorrect` (wrong verse/surah), `out_of_range` (number beyond the surah),
   `missing`, `partial` (covers only part of a multi-verse quote), or `surah_only`.
5. **Marked/unmarked**: whether the quote is inside ﴿﴾ / {} / quotation marks with a cue.

| # | Case | Quote (exact article substring) | Gold location | Wording | Ambiguous | Written reference → label | Marking | Confirmed | Existing note |
|---|---|---|---|---|---|---|---|---|---|
| 1 | `c01-marked-correct` | «إِنَّ اللَّهَ لَا يُغَيِّرُ مَا بِقَوْمٍ حَتَّىٰ يُغَيِّرُوا مَا بِأَنْفُسِهِمْ» | الرعد 13:11 | correct | no | «الرعد: 11» → correct | marked | ☐ |  |
| 2 | `c01-marked-correct` | «وتعاونوا على البر والتقوى» | المائدة 5:2 | correct | no | «المائدة: 2» → correct | marked | ☐ |  |
| 3 | `c02-multi-verse` | «والعصر إن الإنسان لفي خسر إلا الذين آمنوا وعملوا الصالحات وتواصوا بالحق وتواصوا بالصبر» | العصر 103:1–3 | correct | no | «العصر: 1-3» → correct | marked | ☐ |  |
| 4 | `c02-multi-verse` | «قل أعوذ برب الناس ملك الناس إله الناس» | الناس 114:1–3 | correct | no | «الناس: 1-3» → correct | marked | ☐ |  |
| 5 | `c03-wording-errors` | «وقال ربكم ادعوني أستجيب لكم» | غافر 40:60 | wording_error | no | «غافر: 60» → correct | marked | ☐ |  |
| 6 | `c03-wording-errors` | «وقل ربي زدني علما» | طه 20:114 | wording_error | no | «طه: 114» → correct | marked | ☐ |  |
| 7 | `c04-wording-error-grammar` | «يا أيها الناس إنا خلقناكم من ذكر وأنثى وجعلناكم شعوباً وقبائلاً لتعارفوا» | الحجرات 49:13 | wording_error | no | «الحجرات: 13» → correct | marked | ☐ |  |
| 8 | `c05-diacritics-errors` | «إنما يخشى اللهُ من عباده العلماءَ» | فاطر 35:28 | diacritics_error | no | «فاطر: 28» → correct | marked | ☐ |  |
| 9 | `c05-diacritics-errors` | «وَإِذِ ابْتَلَى إِبْرَاهِيمُ رَبَّهُ بِكَلِمَاتٍ» | البقرة 2:124 | diacritics_error | no | «البقرة: 124» → correct | marked | ☐ |  |
| 10 | `c05-diacritics-errors` | «أَنَّ اللَّهَ بَرِيءٌ مِنَ الْمُشْرِكِينَ وَرَسُولِهِ» | التوبة 9:3 | diacritics_error | no | «التوبة: 3» → correct | marked | ☐ |  |
| 11 | `c06-repeated-with-ref` | «ولا تزر وازرة وزر أخرى» | الإسراء 17:15 | correct | yes | «الإسراء: 15» → correct | marked | ☐ |  |
| 12 | `c06-repeated-with-ref` | «الْحَمْدُ لِلَّهِ رَبِّ الْعَالَمِينَ» | الفاتحة 1:2 | correct | yes | «الفاتحة: 2» → correct | marked | ☐ |  |
| 13 | `c06-repeated-with-ref` | «ويل يومئذ للمكذبين» | المرسلات 77:15 | correct | yes | «المرسلات: 15» → correct | marked | ☐ |  |
| 14 | `c07-repeated-without-ref` | «فبأي آلاء ربكما تكذبان» | الرحمن 55:13 | correct | yes | «سورة الرحمن» → surah_only | marked | ☐ | Corrected after the first fallback run (2026-09-28): the article names the surah before the quote, so the original label "missing" was an author labelling error. |
| 15 | `c07-repeated-without-ref` | «إن الله غفور رحيم» | البقرة 2:173 | correct | yes | «—» → missing | marked | ☐ |  |
| 16 | `c08-missing-refs` | «ومن يتق الله يجعل له مخرجا» | الطلاق 65:2 | correct | no | «—» → missing | marked | ☐ |  |
| 17 | `c08-missing-refs` | «ألا بذكر الله تطمئن القلوب» | الرعد 13:28 | correct | no | «—» → missing | marked | ☐ |  |
| 18 | `c09-incorrect-refs` | «ومن يتوكل على الله فهو حسبه» | الطلاق 65:3 | correct | no | «الطلاق: 2» → incorrect | marked | ☐ |  |
| 19 | `c09-incorrect-refs` | «إن الصلاة تنهى عن الفحشاء والمنكر» | العنكبوت 29:45 | correct | no | «العنكبوت: 54» → incorrect | marked | ☐ |  |
| 20 | `c09-incorrect-refs` | «وقولوا للناس حسنا» | البقرة 2:83 | correct | no | «البقرة: 383» → out_of_range | marked | ☐ |  |
| 21 | `c10-repeated-wrong-surah-and-partial` | «كل نفس ذائقة الموت» | آل عمران 3:185 | correct | yes | «البقرة: 185» → incorrect | marked | ☐ |  |
| 22 | `c10-repeated-wrong-surah-and-partial` | «فإن مع العسر يسرا إن مع العسر يسرا» | الشرح 94:5–6 | correct | no | «الشرح: 5» → partial | marked | ☐ |  |
| 23 | `c11-unmarked-short` | «وافعلوا الخير لعلكم تفلحون» | الحج 22:77 | correct | no | «—» → missing | unmarked | ☐ |  |
| 24 | `c11-unmarked-short` | «ولا تنسوا الفضل بينكم» | البقرة 2:237 | correct | no | «—» → missing | unmarked | ☐ |  |
| 25 | `c12-unmarked-long-and-error` | «إن الله يأمر بالعدل والإحسان وإيتاء ذي القربى» | النحل 16:90 | correct | no | «النحل: 90» → correct | unmarked | ☐ |  |
| 26 | `c12-unmarked-long-and-error` | «ادعوني أستجيب لكم» | غافر 40:60 | wording_error | no | «—» → missing | unmarked | ☐ |  |
| 27 | `c14-mixed` | «واصبروا إن الله مع الصابرين» | الأنفال 8:46 | correct | no | «الأنفال: 46» → correct | marked | ☐ |  |
| 28 | `c14-mixed` | «وجادلهم بالتي هي أحسن» | النحل 16:125 | correct | no | «النحل: 125» → correct | marked | ☐ |  |

## Negatives (must NOT be Quran text)

| Case | Passage | Check |
|---|---|---|
| `c13-negatives` | «إنما الأعمال بالنيات» | ☐ not in the Quran |
| `c13-negatives` | «اللهم إني أسألك العفو والعافية» | ☐ not in the Quran |
| `c13-negatives` | «العلم في الصغر كالنقش على الحجر» | ☐ not in the Quran |
| `c13-negatives` | «لا ضرر ولا ضرار» | ☐ not in the Quran |
| `c14-mixed` | «المسلم من سلم المسلمون من لسانه ويده» | ☐ not in the Quran |

## Corrections log

Record every label change here **before** re-running the evaluation, and keep the old value.

| Date | Case / # | Field | Old value | New value | Reason | Source (mushaf page / Quranpedia link) | Reviewer |
|---|---|---|---|---|---|---|---|
| 2026-09-28 | c07 | reference | missing | surah_only | The article names the surah («تتكرر في سورة الرحمن آية …»); found by the first fallback run. Article text unchanged. | Article text of c07 | project author (pre-challenge) |

## After the review

1. Run `python eval/validate_labels.py` (must print `labels OK`).
2. Re-run `python eval/run_eval.py --mode fallback` and, if an AI key works, `--mode ai`.
3. Update `docs/EVALUATION.md` with the reviewer's name/role (with permission) and the date.

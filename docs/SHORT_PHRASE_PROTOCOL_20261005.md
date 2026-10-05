# Unmarked two-word quotations: protocol written before the held-out run (5 Oct 2026, challenge period)

Written about 19:00 Riyadh on 5 Oct 2026, while the two new sets below were still being written and before either had been opened.
Nothing here changes the running service. A change is released only if it passes the rule in «Decision».

## Question

The phrase search (`app/phrases.py`) needs three matched words, so an unmarked two-word quotation such as «فاستبقوا الخيرات» is never
found unless the writer marks it, names the verse or selects it. An earlier trial on Windows (5 Oct, `docs/TEST_LOG.md`) surfaced
every rare two-word pair and also surfaced ordinary prose («جملة واحدة», «الأموال والأولاد», «حياة طيبة»); a stricter rarity threshold
then missed «فاستبقوا الخيرات». Rarity *in the Quran* cannot separate these: «حياة طيبة» is as rare there as «فاستبقوا الخيرات».

Hypothesis: rarity *in ordinary Arabic* can. A writer who uses «فاستبقوا» or «وعاشروهن» is almost always quoting, while «حياة» and
«جملة» are everyday words. If one word of an exact two-word Quran pair is rare in ordinary Arabic and the other is not a function word,
the pair can be offered as an **optional** confirmation (the existing «possible» tier for common phrases: no replacement, nothing
changes, drawn lighter and grouped as «عبارات للتأكيد»).

## Signal

- Ordinary-Arabic frequency: `wordfreq` 3.1.1 (Robyn Speer; data CC BY-SA 4.0), Zipf scale, Arabic. For each folded Quran word form,
  the highest value over the plain spellings that fold to it.
- The pair occurs contiguously in the Quran (folded) in at most a few ayahs; it is not inside a formula of `phrases._FORMULAS`; no
  hadith/du'a/proverb cue precedes it; it overlaps no hit (reported or suppressed) of the existing search.
- Thresholds are tuned on development data only, then frozen in code before the held-out run.

## Data

- Development: the nine saved sets (their four two-word unmarked quotations); split **A**, written blind by an assistant subagent that
  was not allowed to read this repository (30 articles, quotations from surahs 1–20); and the even-`pageid` half of a random sample of
  Arabic Wikipedia lead sections (CC BY-SA, kept locally, not committed).
- Held-out, run **once** after the thresholds are frozen: split **B**, written blind the same way in parallel (quotations from
  surahs 21–114), and the odd-`pageid` half of the Wikipedia sample. I do not open B before that run.
- Both splits are assistant-written, not reviewed by a person, and are development evidence, not an accuracy claim.

## Measures

- **Recall:** two-word spans labelled `quote` (unmarked, deliberate) that a surfaced pair overlaps.
- **False items:** surfaced pairs that overlap no span labelled `quote`, `marked` or `allusion`, per 10,000 characters. Pairs over an
  `allusion` are counted apart. On Wikipedia every surfaced pair counts as false, even where the article itself quotes the Quran.
- **Safety on the nine saved sets:** detection, wording, reference and correction rows identical except for added optional items, which
  are listed; zero new false «matched» wordings and zero new automatic fixes.

## Decision (fixed now)

Release only if, on the held-out run: recall on B's two-word quotations **≥ 50 %**; false items **≤ 1.5 per 10,000 characters** on B
and **≤ 1.0 per 10,000** on the Wikipedia half; and the safety condition holds. Otherwise keep the current behaviour, record the
result and the precise gap in `docs/EVALUATION.md`, and say on `/limitations` that unmarked two-word quotations are not found
automatically.

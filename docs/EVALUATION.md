# Evaluation plan (not yet performed)

**Status: no labelled evaluation has been run. The project makes no accuracy claims.**

## Proposed labelled set

- 30–50 short Arabic articles (or paragraphs) from varied sources, with permission or written for the test.
- For each quotation, a human reviewer records:
  the exact span; the correct surah:ayah (from Quranpedia); whether the wording is correct;
  the error type (diacritics / letters / missing word / extra word / substituted word / paraphrase);
  and the reference as written (correct / wrong / missing / out of range).
- Include negatives: hadith, du'a, poetry, and ordinary sentences that share Quranic words.

## Metrics

| Aspect | Metric |
|---|---|
| Detection | Precision / recall of quotation spans, by detection method (AI / marked / scan) and by mode (AI vs reduced) |
| Wording | Accuracy of matched / difference / uncertain against the labels, and **false “matched” rate** (must be ~0) |
| Reference | Accuracy of matched / missing / incorrect |
| Review routing | Share of true errors that are either flagged “needs review” or reported as a difference |
| Robustness | Behaviour when Quranpedia is unreachable, the AI times out, or the model returns malformed JSON |

## Procedure

1. Freeze the labelled set in `eval/` (not yet created) before looking at system output.
2. Run the pipeline in both AI and reduced mode, and store raw outputs.
3. Score them with a script. Report numbers with the set size and date, including failures.

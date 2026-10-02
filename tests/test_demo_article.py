"""The built-in demonstration article (``app/static/samples/sample-demo.txt``) keeps the results the presentation shows.

Offline, with the 36-verse Quranpedia fixture and no AI. Both mistakes in the article are deliberate user misquotations
written for the demonstration; they are not Quran text. Nothing here is a measure of accuracy.
"""

from pathlib import Path

from app.audit import run_audit

ARTICLE = (Path(__file__).parent.parent / "app" / "static" / "samples" / "sample-demo.txt").read_text(encoding="utf-8").strip()


def test_demo_article_shows_two_correct_quotations_one_wording_issue_and_one_wrong_reference(use_source):
    res = run_audit(ARTICLE)
    f1, f2, f3, f4 = res["findings"]
    # 1: Uthmani-script copy of 2:153 -> matched through the documented equivalences, no correction
    assert f1["wording"]["status"] == "matched" and f1["wording"]["level"] == "uthmani" and f1["reference"]["status"] == "matched"
    assert not [c for c in f1["changes"] if not c["optional"]]
    # 2: a correct quotation in ordinary script with full vowel marks (2:156)
    assert f2["wording"]["status"] == "matched" and f2["reference"]["status"] == "matched" and not f2["needs_review"]
    # 3: «يجزى» for «يوفى» (39:10): a difference, with a source-backed proposal that waits for approval
    assert f3["wording"]["status"] == "difference" and f3["needs_review"]
    fixes = [c for c in f3["changes"] if not c["optional"]]
    assert [(c["original"], c["replacement"]) for c in fixes] == [("يجزى", "يوفى")]  # one word, in the writer's own unvocalised style
    # 4: the words of 94:5 under the reference 94:6 -> the reference is wrong, the words are right
    assert f4["wording"]["status"] == "matched" and f4["reference"]["status"] == "incorrect"
    ref_fixes = [c for c in f4["changes"] if not c["optional"]]
    assert [(c["original"], c["replacement"]) for c in ref_fixes] == [("الشرح: 6", "الشرح: 5")]
    # the page claims nothing about the rest of the article
    assert res["stats"]["total"] == 4 and res["stats"]["needs_review"] == 2

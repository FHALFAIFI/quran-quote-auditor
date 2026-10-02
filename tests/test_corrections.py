"""Correction proposals: offsets, minimal edits, ambiguity, preservation (offline fixture)."""

import pytest

import app.audit as audit
from app.audit import run_audit
from app.corrections import format_reference
from app.extraction.base import ExtractionError, ExtractionProvider, RawSuggestion
from app.references import parse_reference


def apply(article: str, changes: list[dict]) -> str:
    """Reference implementation of applying approved changes (mirrors static/revision.js)."""
    out, pos = [], 0
    for c in sorted(changes, key=lambda c: (c["start"], c["end"])):
        assert c["start"] >= pos, "changes overlap"
        assert article[c["start"]:c["end"]] == c["original"]
        out += [article[pos:c["start"]], c["replacement"]]
        pos = c["end"]
    return "".join(out + [article[pos:]])


def outside_spans_identical(before: str, after: str, changes: list[dict]) -> bool:
    """Every character outside the changed spans is kept, in order."""
    pos, rebuilt = 0, []
    for c in sorted(changes, key=lambda c: c["start"]):
        rebuilt.append(before[pos:c["start"]])
        rebuilt.append("\x00")
        pos = c["end"]
    rebuilt.append(before[pos:])
    parts = "".join(rebuilt).split("\x00")
    # after = parts[0] + repl0 + parts[1] + repl1 + ...
    idx = 0
    for part, c in zip(parts, sorted(changes, key=lambda c: c["start"]) + [None]):
        if not after.startswith(part, idx):
            return False
        idx += len(part)
        if c is not None:
            if not after.startswith(c["replacement"], idx):
                return False
            idx += len(c["replacement"])
    return idx == len(after)


def changes_of(res, kinds=None, include_optional=True):
    out = [c for f in res["findings"] for c in f["changes"]]
    if kinds:
        out = [c for c in out if c["kind"] in kinds]
    if not include_optional:
        out = [c for c in out if not c["optional"]]
    return out


def test_incorrect_reference_replaced_in_place(use_source):
    article = "مقدمة.\nقال سبحانه: {فإن مع العسر يسرا} [الشرح: 6]، ثم قال.\n\nخاتمة!"
    res = run_audit(article)
    (ch,) = changes_of(res, {"reference"})
    assert (ch["original"], ch["replacement"]) == ("الشرح: 6", "الشرح: 5")
    assert ch["surah"] == 94 and ch["ayah_start"] == 5 and ch["source_urls"]
    after = apply(article, [ch])
    assert after == article.replace("[الشرح: 6]", "[الشرح: 5]")
    assert outside_spans_identical(article, after, [ch])


def test_repeated_phrase_changes_only_the_right_occurrence(use_source):
    article = "{فإن مع العسر يسرا} [الشرح: 5] ثم كرر: {فإن مع العسر يسرا} [الشرح: 6] انتهى"
    res = run_audit(article)
    refs = changes_of(res, {"reference"})
    assert len(refs) == 1
    second_ref_at = article.rindex("الشرح: 6")
    assert refs[0]["start"] == second_ref_at
    assert apply(article, refs) == "{فإن مع العسر يسرا} [الشرح: 5] ثم كرر: {فإن مع العسر يسرا} [الشرح: 5] انتهى"


def test_partial_excerpt_is_never_expanded_to_whole_verse(use_source):
    article = "قال تعالى: ﴿إن الله مع الصابرين﴾ [البقرة: 153]."
    res = run_audit(article)
    f = res["findings"][0]
    assert f["wording"]["status"] == "matched"
    assert not changes_of(res, include_optional=False)  # unvocalized but correct: not an error
    (voc,) = changes_of(res, {"vocalize"})
    assert voc["optional"] is True
    assert len(voc["replacement"].split()) == 4  # only the 4 quoted words, not all of 2:153
    assert "استعينوا" not in voc["replacement"]


def test_fuzzy_ambiguous_without_reference_gets_no_replacement(use_source):
    res = run_audit("ومن الأخطاء: ﴿إن الله مع الصابرون﴾ والصواب ما في المصحف.")
    f = res["findings"][0]
    assert f["wording"]["level"] == "fuzzy"
    assert f["correction"]["status"] == "review_only" and f["changes"] == []
    assert f["needs_review"]


def test_fuzzy_with_pinpointing_reference_is_corrected_minimally(use_source):
    article = "ومن الأخطاء: ﴿إن الله مع الصابرون﴾ [البقرة: 153] والصواب."
    res = run_audit(article)
    (ch,) = changes_of(res, {"wording"})
    assert (ch["original"], ch["replacement"]) == ("الصابرون", "الصابرين")
    assert apply(article, [ch]) == article.replace("الصابرون", "الصابرين")


def test_reference_pointing_elsewhere_blocks_fuzzy_fix(use_source):
    res = run_audit("﴿إن الله مع الصابرون﴾ [الإخلاص: 2]")
    f = res["findings"][0]
    assert f["changes"] == [] and f["correction"]["status"] == "review_only"


def test_multi_verse_excerpt_reference_range_and_wording(use_source):
    article = "قال: ﴿فإن مع العسر يسرا إن مع العسر يسرى﴾ [الشرح: 5]."
    res = run_audit(article)
    f = res["findings"][0]
    assert f["source"]["ayah_start"] == 5 and f["source"]["ayah_end"] == 6
    wording = changes_of(res, {"wording"})
    reference = changes_of(res, {"reference"})
    assert len(wording) == 1 and wording[0]["original"] == "يسرى" and wording[0]["replacement"] == "يسرا"
    assert len(reference) == 1 and reference[0]["replacement"] == "الشرح: 5-6"
    after = apply(article, wording + reference)
    assert after == "قال: ﴿فإن مع العسر يسرا إن مع العسر يسرا﴾ [الشرح: 5-6]."


def test_missing_word_is_inserted_without_touching_neighbours(use_source):
    article = "قالوا: ﴿الذين إذا أصابتهم مصيبة قالوا إنا لله إليه راجعون﴾ [البقرة: 156]، وصبروا."
    res = run_audit(article)
    (ch,) = changes_of(res, {"wording"})
    after = apply(article, [ch])
    assert after == "قالوا: ﴿الذين إذا أصابتهم مصيبة قالوا إنا لله وإنا إليه راجعون﴾ [البقرة: 156]، وصبروا."
    assert outside_spans_identical(article, after, [ch])


def test_short_fuzzy_quote_below_threshold_is_review_only(use_source):
    """Conservative by design: 4 words with one changed word (similarity 0.67) gets no automatic fix."""
    res = run_audit("قالوا: ﴿إنا لله وإليه راجعون﴾ [البقرة: 156]")
    f = res["findings"][0]
    assert f["wording"]["level"] == "fuzzy" and f["changes"] == [] and f["correction"]["status"] == "review_only"


def test_diacritics_conflict_only_fixes_conflicting_words(use_source):
    article = "﴿إِنَّمَا يَخْشَى اللَّهُ مِنْ عِبَادِهِ الْعُلَمَاءَ﴾ [فاطر: 28]"
    res = run_audit(article)
    (ch,) = changes_of(res, include_optional=False)
    assert ch["kind"] == "diacritics"
    before_words, after_words = ch["quote_before"].split(), ch["quote_after"].split()
    changed = [(b, a) for b, a in zip(before_words, after_words) if b != a]
    assert changed == [("اللَّهُ", "اللَّهَ"), ("الْعُلَمَاءَ", "الْعُلَمَاءُ")]
    assert len(before_words) == len(after_words)


def test_hamza_seat_error_is_fixed_in_article_style(use_source):
    article = "﴿وآخر دعواهم إن الحمد لله رب العالمين﴾ [يونس: 10]"
    res = run_audit(article)
    (ch,) = changes_of(res, include_optional=False)
    assert ch["kind"] == "wording" and (ch["original"], ch["replacement"]) == ("إن", "أن")  # no diacritics added


def test_correct_unvocalized_quote_is_not_an_error(use_source):
    res = run_audit("﴿اقرأ باسم ربك الذي خلق﴾ [العلق: 1]")
    f = res["findings"][0]
    assert f["wording"]["status"] == "matched" and not f["needs_review"]
    assert all(c["optional"] for c in f["changes"])


def test_short_phrase_without_reference_is_review_only(use_source):
    res = run_audit("كما قال: ﴿الله الصمد﴾ في الحديث.")
    f = res["findings"][0]
    assert f["wording"]["status"] == "uncertain" and f["changes"] == []


def test_missing_reference_add_is_optional_and_after_bracket(use_source):
    article = "﴿اقرأ باسم ربك الذي خلق﴾ ثم تابع."
    res = run_audit(article)
    (add,) = changes_of(res, {"reference_add"})
    assert add["optional"] and add["start"] == add["end"] == article.index("﴾") + 1
    assert apply(article, [add]) == "﴿اقرأ باسم ربك الذي خلق﴾ [العلق: 1] ثم تابع."


def test_source_outage_offers_no_changes(monkeypatch):
    from tests.conftest import FakeSource

    monkeypatch.setattr(audit, "source", FakeSource(error=True))
    monkeypatch.setattr(audit, "get_provider", lambda: None)
    res = run_audit("{فإن مع العسر يسرا} [الشرح: 6]")
    assert res["stats"]["proposed_changes"] == 0
    assert res["findings"][0]["correction"]["status"] == "review_only"


class Failing(ExtractionProvider):
    name = label = "failing"

    def available(self):
        return True

    def extract(self, article):
        raise ExtractionError("503")


class Inventing(ExtractionProvider):
    """Proposes a 'corrected' quote that is not in the article, plus a real one."""

    name = label = "inventing"

    def available(self):
        return True

    def extract(self, article):
        return [RawSuggestion("إن الله مع الصابرين"), RawSuggestion("إن الله مع الصابرون")]


def test_ai_failure_still_gives_deterministic_changes(use_source, monkeypatch):
    monkeypatch.setattr(audit, "get_provider", lambda: Failing())
    res = run_audit("{فإن مع العسر يسرا} [الشرح: 6]")
    assert res["mode"] == "ai_failed" and res["ai"]["responded"] is False
    assert [c["replacement"] for c in changes_of(res, {"reference"})] == ["الشرح: 5"]


def test_ai_text_never_used_as_replacement(use_source, monkeypatch):
    monkeypatch.setattr(audit, "get_provider", lambda: Inventing())
    article = "قيل: إن الله مع الصابرون [البقرة: 153] هكذا."
    res = run_audit(article)
    assert res["ai"]["discarded"] == 1  # the invented 'correct' version is not in the article
    for c in changes_of(res):
        assert article[c["start"]:c["end"]] == c["original"]
    wording = changes_of(res, {"wording"})
    assert [c["replacement"] for c in wording] == ["الصابرين"]  # built from the source words


def test_markup_article_changes_are_plain_text(use_source):
    article = '<script>alert(1)</script> {فإن مع العسر يسرا} [الشرح: 6] <img src=x onerror=alert(2)>'
    res = run_audit(article)
    chs = changes_of(res)
    assert chs and all("<" not in c["replacement"] for c in chs)
    after = apply(article, [c for c in chs if c["kind"] == "reference"])
    assert after.startswith("<script>alert(1)</script> ") and after.endswith("<img src=x onerror=alert(2)>")


def test_emoji_and_newlines_keep_offsets(use_source):
    article = "😀😀 عنوان\r\n\r\nقال: {فإن مع العسر يسرا} [الشرح: 6] 👍\nنهاية"
    res = run_audit(article)
    normalized = article.replace("\r\n", "\n")
    (ch,) = changes_of(res, {"reference"})
    assert normalized[ch["start"]:ch["end"]] == "الشرح: 6"


def test_changes_never_overlap_and_preserve_everything_else(use_source):
    article = (
        "عنوان المقال\n\n"
        "قال تعالى: ﴿إِنَّمَا يَخْشَى اللَّهُ مِنْ عِبَادِهِ الْعُلَمَاءَ﴾ [فاطر: 27]، وهذا مهم.\n"
        "و{فإن مع العسر يسرا إن مع العسر يسرا} [الشرح: 5]؛ ثم «قل هو الله أحد» (الإخلاص: 1).\n"
        "ومن هنا قيل وقضى ربك ألا تعبدوا إلا إياه وبالوالدين إحسانا (الإسراء: 32) — انتهى."
    )
    res = run_audit(article)
    chs = changes_of(res)
    spans = sorted((c["start"], c["end"]) for c in chs)
    for (s1, e1), (s2, e2) in zip(spans, spans[1:]):
        assert e1 <= s2 and not (s1 == e1 == s2 == e2)
    after = apply(article, chs)
    assert outside_spans_identical(article, after, chs)
    assert after.count("\n") == article.count("\n")
    assert "الإسراء: 23" in after and "فاطر: 28" in after and "الشرح: 5-6" in after


@pytest.mark.parametrize(
    "written,surah,a0,a1,expected",
    [
        ("الشرح: 6", 94, 5, 5, "الشرح: 5"),
        ("الشرح ٦", 94, 5, 5, "الشرح ٥"),
        ("سورة البقرة، الآية 156", 2, 155, 156, "سورة البقرة، الآية 155-156"),
        ("94:6", 94, 5, 5, "94:5"),
        ("البقرة: 5", 94, 5, 5, "الشرح: 5"),
        ("الآية 32 من سورة الإسراء", 17, 23, 23, "الآية 23 من سورة الإسراء"),
    ],
)
def test_format_reference_keeps_writer_style(written, surah, a0, a1, expected):
    ref = parse_reference(written)
    assert ref is not None and ref.text == written
    assert format_reference(ref, surah, a0, a1) == expected


# --- one word changed in a three-word quotation (eval/articles_frozen.json, L1: «واستعينوا بالصبر الصلاة» [البقرة: 45]) ---
# Word-level similarity of such a quotation is 2/3 at best, under the 0.75 floor, so it never got replacement text even
# though its boundaries were stated and the reference named the verse. The floor is waived only when everything else is
# settled; each test below removes one of those conditions.

THREE_WORDS = "استعينوا بالصبر الصلاة"  # 2:153 reads «استعينوا بالصبر والصلاة»


def test_three_word_marked_quote_with_ayah_reference_gets_the_one_word_fix(use_source):
    article = f"وقد ورد قوله ﴿{THREE_WORDS}﴾ [البقرة: 153]، فالاستعانة بالله لا تلغي الأخذ بالأسباب."
    res = run_audit(article)
    f = res["findings"][0]
    assert f["wording"]["level"] == "fuzzy" and f["wording"]["similarity"] < 0.75
    (ch,) = changes_of(res, {"wording"})
    assert (ch["original"], ch["replacement"]) == ("الصلاة", "والصلاة")
    after = apply(article, [ch])
    assert after == article.replace("بالصبر الصلاة", "بالصبر والصلاة")
    assert outside_spans_identical(article, after, [ch])
    assert ch["optional"] is False and ch["surah"] == 2 and ch["ayah_start"] == 153 and ch["source_urls"]


def test_three_word_fix_needs_stated_boundaries(use_source):
    """The same words without a marker: the phrase search or the model chose the span, so only the verse is shown."""
    res = run_audit(f"وقد ورد قوله {THREE_WORDS} [البقرة: 153] في الكتاب.")
    assert not changes_of(res, {"wording"})


def test_three_word_fix_needs_an_ayah_number(use_source):
    for ref in ("", " [سورة البقرة]"):
        res = run_audit(f"وقد ورد قوله ﴿{THREE_WORDS}﴾{ref} في الكتاب.")
        assert not changes_of(res, {"wording"}), ref
        assert res["findings"][0]["correction"]["status"] == "review_only"


def test_three_word_fix_blocked_when_reference_points_elsewhere(use_source):
    res = run_audit(f"﴿{THREE_WORDS}﴾ [الإخلاص: 2]")
    f = res["findings"][0]
    assert f["changes"] == [] and f["correction"]["status"] == "review_only"


def test_three_word_fix_blocked_when_two_words_differ(use_source):
    """One word changed and a second one missing: more than one swap is still left to the writer."""
    res = run_audit("﴿استعينوا بالصلاة الصبر﴾ [البقرة: 153]")
    assert not changes_of(res, {"wording"})


def test_three_word_fix_in_a_manual_selection_with_a_chosen_verse(use_source):
    from app.audit import run_phrase

    article = f"وقال: {THREE_WORDS} في كتابه."
    start = article.index("استعينوا")
    out = run_phrase(article, start, start + len(THREE_WORDS), surah=2, ayah_start=153, ayah_end=153)
    (ch,) = [c for c in out["finding"]["changes"] if c["kind"] == "wording"]
    assert (ch["original"], ch["replacement"]) == ("الصلاة", "والصلاة")
    # without the chosen verse nothing is proposed
    out = run_phrase(article, start, start + len(THREE_WORDS))
    assert not [c for c in out["finding"]["changes"] if c["kind"] == "wording"]

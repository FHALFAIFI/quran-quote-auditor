"""Uthmani-script input (a quotation copied from a mushaf site or app): the documented equivalences, and what must NOT happen.

Offline: Quranpedia's text comes from the small fixture, the Uthmani text from ``fixtures/uthmani_verses.json``
(Tanzil Quran text, Uthmani v1.1; the fixture carries Tanzil's notice, see SOURCES.md §1b). The held-out evaluation set is ``eval/uthmani_heldout.json``; these are the unit and
integration tests of the rules and of the result they feed.
"""

import json
from pathlib import Path

import pytest

import app.audit as audit
from app import arabic, uthmani
from app.audit import run_audit
from app.references import parse_reference
from app.verifier import verify

V = json.loads((Path(__file__).parent / "fixtures" / "uthmani_verses.json").read_text(encoding="utf-8"))["verses"]


def words(key, a=0, b=None):
    w = V[key].split()
    return " ".join(w[a:b])


def audit_one(article):
    res = run_audit(article)
    assert len(res["findings"]) == 1, [f["quote"] for f in res["findings"]]
    return res["findings"][0]


def required(f):
    """The changes that correct something (everything optional is formatting, never a correction)."""
    return [c for c in f["changes"] if not c["optional"]]


# ---------------------------------------------------------------------------------------------------- the rules

SAME_WORD = [
    ("ٱلصَّلَوٰةَ", "الصَّلَاةَ"), ("ٱلزَّكَوٰةَ", "الزَّكَاةَ"), ("ٱلْحَيَوٰةِ", "الْحَيَاةِ"),  # waw with dagger alef
    ("ءَامَنُوا۟", "آمَنُوا"), ("ءَايَٰتِنَا", "آيَاتِنَا"), ("ٱلْقُرْءَانَ", "الْقُرْآنَ"),  # separate hamza + alef
    ("ٱلصَّـٰلِحَـٰتِ", "الصَّالِحَاتِ"), ("ٱلْكِتَـٰبَ", "الْكِتَابَ"), ("ٱلسَّمَـٰوَٰتِ", "السَّمَاوَاتِ"),  # dagger alef, tatweel
    ("ٱلَّيْلِ", "اللَّيْلِ"), ("وَٱلَّـٰتِى", "وَاللَّاتِي"),  # one lam for two
    ("ٱشْتَرَىٰهُ", "اشْتَرَاهُ"), ("إِسْرَٰٓءِيلَ", "إِسْرَائِيلَ"), ("شَيْـًٔا", "شَيْئًا"), ("ٱلسَّيِّـَٔاتِ", "السَّيِّئَاتِ"),  # alef maqsura, hamza seats
    ("لَآ", "لَا"), ("إِنَّمَآ", "إِنَّمَا"), ("جَآءَهُمْ", "جَاءَهُمْ"),  # madd sign
    ("لِّلْمُتَّقِينَ", "لِلْمُتَّقِينَ"), ("أَرَدتُّمْ", "أَرَدْتُمْ"),  # idgham shadda
    ("يَدْعُوا۟", "يَدْعُو"), ("يَدْعُوا۟", "يَدْعُوا"), ("أُو۟لُوا۟", "أُولُو"),  # silent alef the imla'i text may omit
    ("هَـٰذَا", "هَٰذَا"), ("ذَٰلِكَ", "ذَٰلِكَ"), ("إِلَـٰهَ", "إِلَٰهَ"), ("هَـٰٓؤُلَآءِ", "هَؤُلَاءِ"),  # dagger alef the imla'i text keeps
    ("أَلِيمُۢ", "أَلِيمٌ"), ("دَاوُۥدُ", "دَاوُودُ"), ("ٱلنَّبِيِّـۧنَ", "النَّبِيِّينَ"),  # small letters / iqlab
]


@pytest.mark.parametrize("quote,source", SAME_WORD)
def test_recognised_uthmani_spellings_are_the_same_word(quote, source):
    assert uthmani.explain(quote, source) is not None
    assert uthmani.vowel_conflicts(quote, source) == []


DIFFERENT_WORD = [
    ("ٱلصَّلَوٰةَ", "الزَّكَاةَ"), ("ءَامَنُوا۟", "آمَنَ"), ("ٱلرَّسُولَ", "النَّبِيَّ"), ("ٱلْكِتَـٰبَ", "الْكُتُبَ"),
    ("ٱلصَّـٰلِحَـٰتِ", "الصَّالِحِينَ"), ("ٱلَّيْلِ", "النَّهَارِ"), ("ءَامَنُوا۟", "أَمَنُوا"), ("يَـٰٓأَيُّهَا", "أَيُّهَا"),
    ("ٱلْقَيُّومُ", "الْحَيُّ"), ("سَدِيدًا", "شَدِيدًا"),
]


@pytest.mark.parametrize("quote,source", DIFFERENT_WORD)
def test_a_different_word_is_never_equivalent(quote, source):
    assert not uthmani.equivalent(quote, source)


def test_a_wrong_vowel_is_a_conflict_not_a_spelling():
    assert uthmani.vowel_conflicts("ٱلصَّلَوٰةُ", "الصَّلَاةَ")  # damma for fatha
    assert uthmani.vowel_conflicts("ٱلصَّلَوٰةِ", "الصَّلَاةَ")  # kasra for fatha
    assert uthmani.vowel_conflicts("ٱلصَّلَوٰةَ", "الصَّلَاةَ") == []


IMLAI_WORDS = ["هَٰذَا", "ذَٰلِكَ", "أُولَٰئِكَ", "لَٰكِنْ", "إِلَٰهَ", "الرَّحْمَٰنِ", "جُزْءًا", "سُوءٌ", "شَيْءٍ", "بَدَءُوكُمْ", "الْمَوْءُودَةُ", "رَءُوفٌ",
               "مَلَأَهُ", "جَاءُوا", "السَّمَاءِ", "الْقُرْآنَ", "وَآتُوا", "لَآيَاتٍ", "مَآبٍ", "تَبَوَّءُوا", "لِيَسُوءُوا", "فَكَذَٰلِكَ", "أَفَبِهَٰذَا",
               "الصَّلَاةَ", "آمَنُوا", "قَالُوا", "الَّذِينَ", "اللَّيْلِ", "مُسْتَهْزِئُونَ", "شَيْئًا", "يَسْأَلُونَكَ", "عَلَىٰ", "إِلَىٰ"]


@pytest.mark.parametrize("word", IMLAI_WORDS)
def test_text_in_the_imlai_spelling_is_folded_exactly_as_before(word):
    assert uthmani.search_fold(word) == arabic.folded(word)


def test_plain_text_without_marks_is_untouched():
    for w in ["الصلاة", "آمنوا", "يا", "أيها", "الليل", "ذلك", "إله"]:
        assert uthmani.search_fold(w) == arabic.folded(w) and uthmani.features(w) == []


def test_a_joined_vocative_is_two_words_with_offsets_intact():
    text = "قال تعالى: يَـٰٓأَيُّهَا ٱلنَّاسُ"
    toks = arabic.tokenize(text)
    assert [t.fold for t in toks] == ["قال", "تعالي", "يا", "ايها", "الناس"]
    a, b = toks[2], toks[3]
    assert text[a.start:a.end] == a.raw == "يَـٰٓ" and text[b.start:b.end] == b.raw == "أَيُّهَا" and a.end == b.start
    word = "وَيَـٰقَوْمِ"
    assert [word[a:b] for a, b in uthmani.split_vocative(word)] == ["وَيَـٰ", "قَوْمِ"]


def test_features_name_the_convention():
    assert {"wasla", "dagger_alef", "small_marks", "waw_alef"} <= set(uthmani.explain("ٱلصَّلَوٰةَ", "الصَّلَاةَ") + uthmani.explain("ءَامَنُوا۟", "آمَنُوا"))
    assert "madd_sign" in uthmani.explain("لَآ", "لَا") and "idgham_shadda" in uthmani.explain("لِّلْمُتَّقِينَ", "لِلْمُتَّقِينَ")


# ---------------------------------------------------------------------------- correct quotations: matched, no correction

CORRECT = [
    ("2:153", 0, None, "البقرة: 153"), ("2:183", 0, None, "البقرة: 183"), ("55:13", 0, None, "الرحمن: 13"), ("94:5", 0, None, "الشرح: 5"),
    ("17:23", 1, 9, "الإسراء: 23"), ("1:2", 0, None, "الفاتحة: 2"), ("2:255", 0, 7, "البقرة: 255"), ("49:10", 0, None, "الحجرات: 10"),
]


@pytest.mark.parametrize("key,a,b,ref", CORRECT)
def test_a_correct_uthmani_quotation_is_matched_and_gets_no_correction(use_source, key, a, b, ref):
    quote = words(key, a, b)
    f = audit_one(f"قال تعالى: ﴿{quote}﴾ [{ref}] وهذا تعليق.")
    w = f["wording"]
    assert w["status"] == "matched", (w["status"], w["message"])
    assert w["level"] == "uthmani" and w["script"]["convention"] == "uthmani" and w["script"]["features"]
    assert f["reference"]["status"] == "matched" and not f["needs_review"]
    assert required(f) == [] and f["correction"]["status"] == "none_needed"
    assert w["diacritic_conflicts"] == [] and not [d for d in w["script_diffs"] if d["kind"] == "significant"]
    for c in f["changes"]:  # whatever is offered is optional formatting that says so and is not a correction of an error
        assert c["optional"] and c["kind"] in ("script", "vocalize")


def test_the_optional_conversion_is_formatting_not_a_correction(use_source):
    quote = words("2:153", 0, 6)
    article = f"﴿{quote}﴾ [البقرة: 153]"
    f = audit_one(article)
    [ch] = [c for c in f["changes"] if c["kind"] == "script"]
    assert ch["optional"] and "تنسيق" in ch["reason"] and "ليس تصحيح" in ch["reason"]
    assert article[ch["start"]:ch["end"]] == ch["original"] and ch["original"] == quote  # offsets intact, the original text is the writer's
    assert [arabic.letters(x) for x in ch["replacement"].split()[:2]] == ["يا", "أيها"]  # the vocative becomes two words again
    res = run_audit(article)
    assert res["stats"]["proposed_changes"] == 0 and res["stats"]["optional_changes"] >= 1


def test_the_original_uthmani_text_and_offsets_are_never_altered(use_source):
    prose = "وقد تحدث كثيرون عن هذه الآية"
    quote = words("2:255", 0, 7)
    article = f"{prose}.\n\nقال سبحانه: ﴿{quote}﴾ [البقرة: 255]\n\n{prose}."
    res = run_audit(article)
    [f] = res["findings"]
    assert article[f["start"]:f["end"]] == f["quote"] == quote
    for c in f["changes"]:
        assert article[c["start"]:c["end"]] == c["original"]


def test_source_text_and_citation_are_still_quranpedias(use_source):
    f = audit_one(f"﴿{words('55:13')}﴾ [الرحمن: 13]")
    assert f["source"]["label"] == "الرحمن: 13" and f["source"]["segments"][0]["page_url"].startswith("https://api.quranpedia.net/")
    assert "فَبِأَيِّ آلَاءِ" in f["source"]["matched_text"]  # Quranpedia's imla'i wording is shown, not the Uthmani copy


# ------------------------------------------------------------------------------------------------ negative mutations

def replace_word(text, idx, new):
    w = text.split(" ")
    w[idx] = new
    return " ".join(w)


def test_one_changed_word_is_a_difference_with_a_source_backed_fix(use_source):
    quote = replace_word(words("2:153", 0, 6), 3, "ٱسْتَعِينُوا۟")  # fine: control, unchanged word
    assert audit_one(f"﴿{quote}﴾ [البقرة: 153]")["wording"]["status"] == "matched"
    bad = replace_word(words("2:153", 0, 6), 4, "بِٱلشُّكْرِ")  # بِٱلصَّبْرِ -> بِٱلشُّكْرِ
    f = audit_one(f"﴿{bad}﴾ [البقرة: 153]")
    assert f["wording"]["status"] == "difference" and f["needs_review"]
    [ch] = required(f)
    assert ch["kind"] == "wording" and ch["original"] == "بِٱلشُّكْرِ" and arabic.letters(ch["replacement"]) == "بالصبر"


def test_a_wrong_ending_is_not_matched(use_source):
    w = words("2:183", 0, None).split(" ")
    w[-1] = "تَشْكُرُونَ"  # تَتَّقُونَ -> تَشْكُرُونَ
    f = audit_one(f"﴿{' '.join(w)}﴾ (البقرة: 183)")
    assert f["wording"]["status"] == "difference"
    assert f["wording"]["status"] != "matched"
    assert required(f) and required(f)[0]["kind"] == "wording"


def test_a_missing_word_is_not_matched(use_source):
    quote = words("2:183", 0, None).split(" ")
    del quote[4]
    f = audit_one(f"﴿{' '.join(quote)}﴾ (البقرة: 183)")
    assert f["wording"]["status"] == "difference" and f["wording"]["level"] == "fuzzy"
    assert any(d["op"] == "missing" for d in f["wording"]["diff"])


def test_a_contradictory_vowel_is_reviewed_by_hand_never_replaced(use_source):
    w = words("2:153", 0, 6).split(" ")
    w[5] = w[5].replace("ِ", "َ")  # وَٱلصَّلَوٰةِ -> وَٱلصَّلَوٰةَ: a kasra written as a fatha
    quote = " ".join(w)
    assert quote != words("2:153", 0, 6)
    f = audit_one(f"﴿{quote}﴾ [البقرة: 153]")
    assert f["wording"]["status"] == "difference" and f["wording"]["script"] is not None
    assert any(d.get("uthmani") for d in f["wording"]["diacritic_conflicts"])
    assert required(f) == [] and f["correction"]["status"] == "review_only" and f["needs_review"]


def test_a_wrong_reference_is_flagged_even_when_the_words_match(use_source):
    f = audit_one(f"﴿{words('94:5')}﴾ [الشرح: 6]")
    assert f["wording"]["status"] == "matched" and f["wording"]["level"] == "uthmani"
    assert f["reference"]["status"] == "incorrect" and f["needs_review"]
    [ch] = required(f)
    assert ch["kind"] == "reference" and ch["replacement"].endswith("5")  # a reference fix, not a wording fix
    assert not [c for c in f["changes"] if c["kind"] in ("wording", "diacritics")]


def test_an_equivalence_the_rules_cannot_establish_is_uncertain_without_a_replacement(use_source):
    w = words("2:255", 0, 7).split(" ")
    w[6] = "ٱلْقَيَّٰومُ"  # an invented dagger-alef spelling of ٱلْقَيُّومُ: same consonants, no rule makes it the source word
    f = audit_one(f"﴿{' '.join(w)}﴾ [البقرة: 255]")
    assert f["wording"]["status"] == "uncertain" and f["needs_review"]
    assert f["wording"]["unresolved_words"][0]["quote"] == "ٱلْقَيَّٰومُ"
    assert required(f) == [] and f["correction"]["status"] == "review_only"
    assert f["reference"]["status"] == "matched"  # the reference is still judged on its own


def test_unresolved_spelling_with_a_real_error_elsewhere_only_corrects_the_real_error(use_source):
    w = words("2:255", 0, 15).split(" ")
    w[6] = "ٱلْقَيَّٰومُ"
    w[5] = "ٱلْعَلِىُّ"  # ٱلْحَىُّ -> ٱلْعَلِىُّ: a different word
    f = audit_one(f"﴿{' '.join(w)}﴾ [البقرة: 255]")
    assert f["wording"]["status"] == "difference"
    originals = [c["original"] for c in required(f)]
    assert "ٱلْعَلِىُّ" in originals and "ٱلْقَيَّٰومُ" not in originals


def test_mixed_imlai_and_uthmani_spelling_is_matched(use_source):
    w = words("2:183", 0, None).split(" ")
    mixed = " ".join(w[:3]) + " " + "كُتِبَ عَلَيْكُمُ الصِّيَامُ كَمَا كُتِبَ عَلَى الَّذِينَ مِنْ قَبْلِكُمْ لَعَلَّكُمْ تَتَّقُونَ"
    f = audit_one(f"﴿{mixed}﴾ [البقرة: 183]")
    assert f["wording"]["status"] == "matched" and required(f) == []


def test_mixed_spelling_with_a_changed_word_is_a_difference(use_source):
    mixed = "يَـٰٓأَيُّهَا ٱلَّذِينَ ءَامَنُوا۟ كُتِبَ عَلَيْكُمُ القيام كَمَا كُتِبَ عَلَى الَّذِينَ مِنْ قَبْلِكُمْ لَعَلَّكُمْ تَتَّقُونَ"
    f = audit_one(f"﴿{mixed}﴾ [البقرة: 183]")
    assert f["wording"]["status"] == "difference" and f["wording"]["status"] != "matched"


def test_surrounding_prose_does_not_change_the_verdict(use_source):
    prose = "وقد تحدث الكتّاب قديمًا عن الاختبار في الحياة وعن حسن العمل والصبر على البلاء"
    for text in (f"{prose}. ﴿{words('2:153', 0, 6)}﴾ [البقرة: 153]. {prose}.",
                 f"{prose}.\n\n«{words('2:153', 0, 6)}» (البقرة: 153)\n\n{prose}."):
        f = audit_one(text)
        assert f["wording"]["status"] == "matched" and required(f) == []


def test_text_that_is_not_quran_is_never_matched_because_of_uthmani_marks(use_source):
    res = run_audit("يقول المثل: ﴿ٱلْعِلْمُ فِى ٱلصِّغَرِ كَٱلنَّقْشِ فِى ٱلْحَجَرِ﴾ فلنتعلم.")
    for f in res["findings"]:
        assert f["wording"]["status"] != "matched"
        assert required(f) == [] or f["wording"]["status"] == "difference"


def test_unmarked_uthmani_phrase_is_found_and_not_corrected(use_source):
    quote = words("2:255", 0, 7)
    res = run_audit(f"قال الله تعالى: {quote}. وهذا عظيم.")
    fs = [f for f in res["findings"] if f["detection"]["kind"] == "phrase"]
    assert fs and all(required(f) == [] for f in fs)
    assert fs[0]["wording"]["status"] in ("matched", "uncertain") and fs[0]["wording"]["status"] != "difference"


def test_pause_signs_between_copied_words_do_not_split_the_phrase(use_source):
    quote = words("2:255", 0, 14)
    assert "ۚ" in quote
    res = run_audit(f"قال الله تعالى: {quote}.")
    fs = [f for f in res["findings"] if f["detection"]["kind"] == "phrase"]
    assert len(fs) == 1 and fs[0]["quote"] == quote.rstrip(" ۚ")


def test_source_outage_still_reports_uncertain_without_any_correction(monkeypatch, index):
    from tests.conftest import FakeSource

    monkeypatch.setattr(audit, "source", FakeSource(error=True))
    monkeypatch.setattr(audit, "get_provider", lambda: None)
    res = run_audit(f"﴿{words('2:153', 0, 6)}﴾ [البقرة: 153]")
    [f] = res["findings"]
    assert f["wording"]["status"] == "uncertain" and f["changes"] == [] and f["needs_review"]
    assert any("قرآنبيديا" in n["text"] for n in res["notices"])


def test_verify_accepts_raw_tokens_directly(index):
    toks = [t.raw for t in arabic.tokenize(words("94:5"))]
    res = verify(index, toks, parse_reference("الشرح: 5"))
    assert res["wording"]["status"] == "matched" and res["wording"]["level"] == "uthmani"

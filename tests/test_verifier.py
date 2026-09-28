"""Focused tests for the verifier. They use a small offline excerpt of the
Quranpedia Hafs text (tests/fixtures/hafs_subset.json)."""

from app.arabic import tokenize
from app.references import find_references
from app.verifier import verify


def words(text):
    return [t.raw for t in tokenize(text)]


def ref(text):
    (r,) = find_references(text)
    return r


def run(index, quote, reference=None):
    return verify(index, words(quote), ref(reference) if reference else None)


def test_literal_match_with_reference(index):
    r = run(index, "اقْرَأْ بِاسْمِ رَبِّكَ الَّذِي خَلَقَ", "العلق: 1")
    assert r["wording"]["status"] == "matched"
    assert r["wording"]["level"] == "literal"
    assert r["source"]["label"] == "العلق: 1" and r["source"]["coverage"] == "full"
    assert r["reference"]["status"] == "matched"
    assert r["needs_review"] is False


def test_match_ignoring_diacritics_is_not_literal(index):
    r = run(index, "يرفع الله الذين آمنوا منكم والذين أوتوا العلم درجات", "المجادلة: 11")
    assert r["wording"]["status"] == "matched"
    assert r["wording"]["level"] == "diacritics"
    assert r["source"]["coverage"] == "partial"


def test_hamza_omission_is_normalized_not_literal(index):
    r = run(index, "ان الله مع الصابرين", "البقرة: 153")
    assert r["wording"]["status"] == "matched"
    assert r["wording"]["level"] == "normalized"
    assert r["wording"]["script_diffs"][0]["kind"] == "benign"


def test_changed_hamza_seat_is_a_difference(index):
    # "إن" written for "أن" (يونس 10) changes the word
    r = run(index, "وآخر دعواهم إن الحمد لله رب العالمين")
    assert r["wording"]["status"] == "difference"
    assert any(d["kind"] == "significant" for d in r["wording"]["script_diffs"])


def test_diacritic_conflict_is_reported(index):
    r = run(index, "إنما يخشى اللهُ من عباده العلماءَ", "فاطر: 28")
    assert r["wording"]["status"] == "difference"
    conflicts = {(d["quote"], d["source"]) for d in r["wording"]["diacritic_conflicts"]}
    assert ("اللهُ", "اللَّهَ") in conflicts
    assert r["reference"]["status"] == "matched"
    assert r["needs_review"] is True


def test_fuzzy_is_never_verified(index):
    r = run(index, "إن الله مع الصابرون")
    assert r["wording"]["status"] == "difference"
    assert r["wording"]["level"] == "fuzzy"
    assert r["needs_review"] is True
    ops = [d for d in r["wording"]["diff"] if d["op"] != "equal"]
    assert ops == [{"op": "replace", "quote": "الصابرون", "source": "الصَّابِرِينَ"}]


def test_missing_word_diff(index):
    r = run(index, "واعتصموا بحبل الله ولا تفرقوا", "آل عمران: 103")
    assert r["wording"]["status"] == "difference"
    assert {"op": "missing", "quote": "", "source": "جَمِيعًا"} in r["wording"]["diff"]
    assert r["reference"]["status"] == "uncertain"  # fuzzy location: reference cannot be confirmed


def test_phrase_in_several_verses_needs_review(index):
    r = run(index, "إن الله مع الصابرين")  # البقرة 153 and الأنفال 46
    assert r["wording"]["status"] == "uncertain"
    assert r["occurrences"] == 2
    assert r["needs_review"] and len(r["alternatives"]) == 2


def test_reference_disambiguates_repeated_phrase(index):
    r = run(index, "إن الله مع الصابرين", "الأنفال: 46")
    assert r["wording"]["status"] == "matched"
    assert r["source"]["label"] == "الأنفال: 46"
    assert r["reference"]["status"] == "matched"


def test_repeated_phrase_with_wrong_reference(index):
    r = run(index, "إن الله مع الصابرين", "البقرة: 255")
    assert r["reference"]["status"] == "incorrect"
    assert r["wording"]["status"] == "uncertain"


def test_wrong_ayah_number(index):
    r = run(index, "فإن مع العسر يسرا", "الشرح: 6")
    assert r["wording"]["status"] == "matched"
    assert r["reference"]["status"] == "incorrect"
    assert r["reference"]["expected"] == "الشرح: 5"


def test_out_of_range_reference(index):
    r = run(index, "وقل رب زدني علما", "طه: 141")
    assert r["wording"]["status"] == "matched"
    assert r["reference"]["status"] == "incorrect"
    assert r["reference"]["expected"] == "طه: 114"


def test_missing_reference(index):
    r = run(index, "إنما المؤمنون إخوة فأصلحوا بين أخويكم")
    assert r["wording"]["status"] == "matched"
    assert r["reference"]["status"] == "missing"


def test_surah_only_reference(index):
    r = run(index, "إنما المؤمنون إخوة فأصلحوا بين أخويكم", "سورة الحجرات")
    assert r["reference"]["status"] == "matched"


def test_multi_verse_quotation(index):
    r = run(index, "قل هو الله أحد الله الصمد لم يلد ولم يولد ولم يكن له كفوا أحد", "الإخلاص: 1-4")
    assert r["wording"]["status"] == "matched"
    assert (r["source"]["ayah_start"], r["source"]["ayah_end"]) == (1, 4)
    assert r["source"]["coverage"] == "full"
    assert r["reference"]["status"] == "matched"


def test_reference_not_covering_all_verses(index):
    r = run(index, "وبشر الصابرين الذين إذا أصابتهم مصيبة قالوا إنا لله وإنا إليه راجعون", "البقرة: 156")
    assert r["wording"]["status"] == "matched"
    assert r["reference"]["status"] == "uncertain"


def test_short_phrase_without_reference_is_uncertain(index):
    r = run(index, "الحي القيوم")
    assert r["wording"]["status"] == "uncertain"
    assert r["needs_review"]


def test_text_not_in_quran(index):
    r = run(index, "العلم نور والجهل ظلام دامس في كل زمان")
    assert r["wording"]["status"] == "uncertain"
    assert r["source"] is None
    assert r["needs_review"]


def test_source_links_are_quranpedia(index):
    r = run(index, "اقرأ باسم ربك الذي خلق")
    seg = r["source"]["segments"][0]
    assert seg["api_url"] == "https://api.quranpedia.net/v1/mushafs/1/96/1"
    assert seg["page_url"].startswith("https://api.quranpedia.net/embed?surah=96&ayah=1")

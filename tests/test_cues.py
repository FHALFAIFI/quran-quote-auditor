"""Quotations the writer announced (app/cues.py): a lead-in, an adjacent reference or quotation marks (4 Oct 2026).

The retrieval may accept a weaker match than the phrase search because the writer said a verse is there, but what it
finds is graded like any unmarked span: an approximate match is only "possible" and offers no replacement until the
writer confirms, unless an ayah-level reference written next to it names the very verse it was matched to.
"""

import pytest

import app.audit as audit
from app import arabic, cues
from app.config import settings
from app.quran_source import QuranSource
from app.references import find_references

from .conftest import FakeSource

INDEX = QuranSource(cache_dir=settings.cache_dir)._load_disk()
full = pytest.mark.skipif(INDEX is None, reason="no local copy of the Quranpedia text (run the app once)")


@pytest.fixture
def use_full(monkeypatch):
    monkeypatch.setattr(audit, "source", FakeSource(INDEX))
    monkeypatch.setattr(audit, "get_provider", lambda: None)


def windows(article):
    toks = arabic.tokenize(article)
    return [(c.kind, " ".join(t.raw for t in toks[c.first:c.last]), c.states_start, c.states_end)
            for c in cues.find_cues(article, toks, find_references(article))]


def only(res, text):
    hits = [f for f in res["findings"] if text in f["quote"] or f["quote"] in text]
    assert len(hits) == 1, [f["quote"] for f in res["findings"]]
    return hits[0]


# ---- windows (no Quran text needed) -----------------------------------------------------------------------------------------

def test_lead_in_window_starts_after_the_words_of_praise():
    (w,) = windows("يقول الله عز وجل وأقيموا الصلاة وآتوا الزكاة. ثم نمضي.")
    assert w == ("lead_in", "وأقيموا الصلاة وآتوا الزكاة", True, False)


def test_lead_in_and_reference_around_the_same_words_make_one_window():
    (w,) = windows("قال تعالى: وقل رب زدني فهما [طه: 114] فالعلم بحر.")
    assert w == ("reference", "وقل رب زدني فهما", True, True)


def test_a_noun_naming_the_quran_announces_only_after_a_colon():
    assert windows("وقد حذّر القرآن من الذين يسعون في الأرض فسادا.") == []
    assert windows("ورد في القرآن الكريم: ولا تقربوا الزنى.")[0][:2] == ("lead_in", "ولا تقربوا الزنى")


def test_a_surah_named_in_running_prose_does_not_close_the_words_before_it():
    assert all(w[0] != "reference" for w in windows("وقد ختم الله الأمثال التي ضربها للناس في سورة العنكبوت بقوله كذا."))


def test_quotation_marks_make_a_window_and_a_bracket_opens_none():
    assert windows("ورد في الكتاب «إن الله لا يضيع أجر المصلحين» فالعمل لا يضيع.") == [
        ("quotes", "إن الله لا يضيع أجر المصلحين", True, True)]
    assert windows("قال تعالى: ﴿إن مع العسر يسرا﴾") == []  # the bracket states the quotation (marked extraction)


def test_announced_before_allows_words_of_praise_and_the_classical_citation():
    assert cues.announced_before("ثم يقول الله عز وجل")
    assert cues.announced_before("وفي ذلك قال تعالى:")
    assert cues.announced_before("كما في سورة العنكبوت بقوله")
    assert not cues.announced_before("قال المعلم لتلاميذه")


# ---- retrieval and grading on the full text ----------------------------------------------------------------------------------

@full
def test_lead_in_with_a_wrong_last_word_is_found_whole_and_stays_possible(use_full):
    f = only(audit.run_audit("قال تعالى: إن الله لا يضيع أجر المصلحين. فالعمل لا يضيع."), "إن الله")
    assert f["quote"] == "إن الله لا يضيع أجر المصلحين" and f["detection"]["kind"] == "cue"
    assert f["detection"]["unconfirmed"] and f["changes"] == [] and f["wording"]["status"] == "difference"
    assert (9, 120) in {(c["surah"], c["ayah_start"]) for c in f["choices"]}


@full
def test_wrong_last_word_before_an_ayah_reference_gets_the_verse_word_only(use_full):
    article = "والآية التي تقول: ما يلفظ من قول إلا لديه رقيب شهيد (ق: 18) تصلح عنوانًا."
    f = only(audit.run_audit(article), "ما يلفظ")
    assert f["detection"]["tier"] == "stated" and f["detection"]["basis"] == "reference"
    fixes = [(c["original"], c["replacement"]) for c in f["changes"] if not c["optional"]]
    assert fixes == [("شهيد", "عتيد")]  # never a deletion of the edge word, never a word outside the verse


@full
def test_a_short_misquotation_with_its_reference_is_found_and_corrected_from_the_named_verse(use_full):
    f = only(audit.run_audit("وقل رب زدني فهما [طه: 114] فالعلم بحر."), "وقل رب زدني")
    assert f["quote"] == "وقل رب زدني فهما" and f["source"]["label"] == "طه: 114"
    assert [(c["original"], c["replacement"]) for c in f["changes"] if not c["optional"]] == [("فهما", "علما")]


@full
def test_comma_prose_after_a_verse_is_not_absorbed_and_nothing_is_deleted(use_full):
    article = "فقالت (سورة الإنسان، الآية ١٢): وجزاهم بما صبروا جنة وحريرا، وفيها دلالة على أن الصبر يقابَل بنعيم دائم."
    f = only(audit.run_audit(article), "وجزاهم")
    assert f["quote"] == "وجزاهم بما صبروا جنة وحريرا" and f["wording"]["status"] == "matched"
    assert not [c for c in f["changes"] if not c["optional"]]


@full
def test_quotation_marks_alone_never_confirm_a_near_match(use_full):
    f = only(audit.run_audit("ورد في الكتاب «إن الله لا يضيع أجر المصلحين» فالعمل لا يضيع."), "إن الله")
    assert f["detection"]["unconfirmed"] and f["changes"] == []


@full
def test_ordinary_prose_after_a_mention_of_the_quran_is_not_a_finding(use_full):
    res = audit.run_audit("وقد حذّر القرآن من الذين يسعون في الأرض لإفسادها، فالبيئة أمانة.")
    assert all("يسعون" not in f["quote"] for f in res["findings"])


@full
def test_a_citation_verb_is_not_read_as_a_misspelt_verse_word(use_full):
    f = only(audit.run_audit("فلنتأمل قوله ربنا آتنا في الدنيا حسنة وفي الآخرة حسنة في كل دعاء."), "ربنا آتنا")
    assert f["quote"].startswith("ربنا") and f["wording"]["status"] != "difference"
    assert not [c for c in f["changes"] if not c["optional"]]


@full
def test_writer_confirming_the_verse_then_gets_the_source_correction(use_full):
    article = "قال تعالى: إن الله لا يضيع أجر المصلحين. فالعمل لا يضيع."
    f = only(audit.run_audit(article), "إن الله")
    res = audit.run_phrase(article, f["start"], f["end"], 9, 120, 120, finding_id=f["id"])
    fixes = [(c["original"], c["replacement"]) for c in res["finding"]["changes"] if not c["optional"]]
    assert fixes == [("المصلحين", "المحسنين")]


@full
def test_exact_short_phrase_after_a_lead_in_is_the_writers_quotation(use_full):
    f = only(audit.run_audit("قال تعالى: واعتصموا بحبل الله، ثم مضى."), "واعتصموا")
    assert f["detection"]["tier"] == "stated" and f["detection"]["basis"] == "lead_in" and not f["detection"]["unconfirmed"]


@full
def test_the_cue_never_steals_a_neighbouring_quotation_reference(use_full):
    article = ("وقد ختم الله الأمثال التي ضربها للناس في سورة العنكبوت بقوله وما يعقلها إلا العالمون، "
               "وفي هذا ما يدل على أن فهم المثل علم.")
    res = audit.run_audit(article)
    assert all("الأمثال" not in f["quote"] for f in res["findings"])

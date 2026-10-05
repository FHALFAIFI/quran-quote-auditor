"""Unmarked two-word quotations (``phrases.find_pairs``, docs/SHORT_PHRASE_PROTOCOL_20261005.md), against the FULL Hafs text.

Skipped without a local copy of the text, like tests/test_phrases_full.py. Regression checks of the chosen thresholds, not accuracy claims.
"""

import pytest

import app.audit as audit
from app import arabic
from app.phrases import find_phrases
from app.quran_source import QuranSource, settings
from tests.conftest import FakeSource

_source = QuranSource(cache_dir=settings.cache_dir)
INDEX = _source._load_disk()
pytestmark = pytest.mark.skipif(INDEX is None, reason="no local copy of the Quranpedia text (run the app once)")


def hits(text):
    toks = arabic.tokenize(text)
    return [(text[toks[h.first].start:toks[h.last - 1].end], h) for h in find_phrases(text, toks, INDEX).hits]


@pytest.fixture
def full_source(monkeypatch):
    monkeypatch.setattr(audit, "source", FakeSource(INDEX))
    monkeypatch.setattr(audit, "get_provider", lambda: None)


@pytest.mark.parametrize("pair", ["فاستبقوا الخيرات", "وعاشروهن بالمعروف", "وبالوالدين إحسانا"])
def test_a_pair_with_a_word_rare_in_ordinary_arabic_is_an_optional_possibility(pair):
    found = hits(f"في زحمة الحياة ننسى أحيانًا ما يهم، {pair} قبل أن يفوت الوقت.")
    assert [(t, h.tier, h.reasons) for t, h in found] == [(pair, "possible", ["pair"])]


@pytest.mark.parametrize("pair", ["جملة واحدة", "حياة طيبة", "الأموال والأولاد", "فاعلموا أن"])
def test_everyday_pairs_are_not_reported(pair):
    assert hits(f"قال المدرب للفريق إن {pair} تكفي اليوم، ثم انصرف الجميع.") == []


def test_no_pair_after_a_hadith_cue():
    assert hits("وفي الحديث الشريف: فاستبقوا الخيرات يا عباد الله.") == []


def test_a_longer_match_is_not_split_into_a_pair():
    found = hits("ولكل وجهة هو موليها فاستبقوا الخيرات أين ما تكونوا يأت بكم الله جميعا.")
    assert all("pair" not in h.reasons for _, h in found) and found


def test_the_audit_offers_the_pair_without_any_change(full_source):
    res = audit.run_audit("في زحمة الحياة ننسى ما يهم، فاستبقوا الخيرات قبل أن يفوت الوقت.")
    (f,) = res["findings"]
    assert f["detection"]["codes"] == ["pair"] and f["detection"]["unconfirmed"] is True
    assert f["changes"] == [] and {(c["surah"], c["ayah_start"]) for c in f["choices"]} >= {(2, 148), (5, 48)}


def test_a_pair_never_takes_the_reference_of_the_quotation_after_it(full_source):
    # 5 Oct: «في سورة آل عمران» belongs to the quotation it introduces, not to the pair before it
    art = ("وقد وجّهنا الله إلى المسابقة في الخيرات: فاستبقوا الخيرات. وبيّن في سورة آل عمران أن الجنة تحتاج إلى مسارعة: "
           "وسارعوا إلى مغفرة من ربكم وجنة عرضها السماوات والأرض. فلنسارع إلى مغفرة الله.")
    res = audit.run_audit(art)
    long_quote = next(f for f in res["findings"] if "وسارعوا" in art[f["start"]:f["end"]])
    pair = next(f for f in res["findings"] if "فاستبقوا" in art[f["start"]:f["end"]])
    assert long_quote["reference"]["status"] != "missing" and pair["reference"]["status"] == "missing"


def test_a_pair_does_not_take_the_reference_of_a_selected_span(full_source):
    # the writer selects the quotation after the pair and checks it by hand: the reference before it stays the selection's
    art = "فاستبقوا الخيرات يا قوم. وفي سورة آل عمران: وسارعوا إلى مغفرة من ربكم وجنة عرضها السماوات والأرض."
    s = art.index("وسارعوا")
    res = audit.run_phrase(art, s, art.index(" والأرض") + len(" والأرض"))
    assert res["finding"]["reference"]["status"] != "missing"

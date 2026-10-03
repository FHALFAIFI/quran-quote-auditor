"""Verse suggestions (app/suggest.py and POST /api/suggest) against the FULL Quranpedia Hafs text, when a local copy exists.

Like tests/test_phrases_full.py these use the cached text and are skipped when it is absent. They are regression checks of the
rules written in app/suggest.py (a continuation after a Quran cue, an ambiguity shown as choices, a probable correction never
presented as exact, silence for hadith / du'a cues and for text without a cue); they are NOT an accuracy measurement, which
lives in eval/run_suggest_eval.py on frozen sets.
"""

import dataclasses

import pytest
from fastapi.testclient import TestClient

import app.main as main
from app import arabic
from app.quran_source import QuranSource, settings
from app.suggest import CHUNK_TAIL, CHUNK_WORDS, MAX_CHOICES, suggest

_source = QuranSource(cache_dir=settings.cache_dir)
INDEX = _source._load_disk()
pytestmark = pytest.mark.skipif(INDEX is None, reason="no local copy of the Quranpedia text (run the app once)")


def ask(before, after="", **kw):
    return suggest(INDEX, before, after, **kw)


def best(r):
    assert r["status"] == "suggest", r
    return r["choices"][0]


# ---- the example in the product brief ---------------------------------------------------------------------------------------
def test_continuation_after_a_lead_in_is_exact_and_sourced():
    c = best(ask("قال تعالى: وما خلقت الجن والإنس إلا"))
    assert (c["kind"], c["certainty"], c["to_text"], c["label"]) == ("continue", "exact", "ليعبدون", "الذاريات: 56")
    assert c["insert_text"] == " ليعبدون"                      # the caret sits right after «إلا»: a space first
    assert c["verse"]["words"][-1] == "لِيَعْبُدُونِ"           # the source word, with its marks, is what the card shows


@pytest.mark.parametrize("typed", ["قال تعالى: وما خلقت الجن والإنس إلا لعبادتي", "قال تعالى: وما خلقت الجن والإنس إلا لعبادتي ", "﴿وما خلقت الجن والإنس إلا لعبادتي"])
def test_wrong_last_word_is_a_probable_correction_with_or_without_a_space(typed):
    r = ask(typed)
    c = best(r)
    assert (c["kind"], c["certainty"], c["from_text"], c["to_text"], c["label"]) == ("replace", "probable", "لعبادتي", "ليعبدون", "الذاريات: 56")
    assert typed[c["replace_start"]:c["replace_end"]] == "لعبادتي"
    assert not any(x["certainty"] == "exact" for x in r["choices"])


def test_a_word_still_being_typed_is_completed_not_corrected():
    c = best(ask("قال تعالى: وما خلقت الجن والإنس إلا ليعب"))
    assert (c["kind"], c["from_text"], c["to_text"]) == ("complete_word", "ليعب", "ليعبدون")
    assert ask("قال تعالى: وما خلقت الجن والإنس إلا لعب")["status"] == "none"   # three letters that fit no verse: not judged yet


def test_a_long_exact_beginning_beats_a_short_match_of_the_whole_run_elsewhere():
    """«…يصلون على الرسول» ends like 5:99 («على الرسول») but its eight-word beginning is 33:56: the odd word is «الرسول»."""
    r = ask("قوله تعالى: ﴿إِنَّ اللَّهَ وَمَلَائِكَتَهُ يُصَلُّونَ عَلَى الرسول ")
    c = best(r)
    assert (c["kind"], c["certainty"], c["label"]) == ("replace", "probable", "الأحزاب: 56")
    assert all(x["certainty"] != "exact" for x in r["choices"])


def test_omitted_word_is_a_probable_insertion():
    c = best(ask("قال تعالى: ﴿يا أيها الذين آمنوا استعينوا والصلاة "))
    assert (c["kind"], c["certainty"], c["to_text"], c["label"]) == ("insert", "probable", "بالصبر", "البقرة: 153")


# ---- ambiguity, chunks ----------------------------------------------------------------------------------------------------
def test_ambiguous_words_give_choices_from_different_verses_never_one_arbitrary_choice():
    r = ask("قال تعالى: يا أيها الذين آمنوا كتب")
    assert r["ambiguous"] and len(r["choices"]) >= 2
    assert len({(c["surah"], c["ayah_end"]) for c in r["choices"]}) == len(r["choices"])
    assert {c["label"] for c in r["choices"]} >= {"البقرة: 178", "البقرة: 183"}


def test_very_common_openings_are_not_guessed():
    for typed in ["قال تعالى: يا أيها الذين آمنوا", "قال تعالى: فبأي آلاء ربكما", "قال تعالى: إن الله على كل"]:
        assert ask(typed)["status"] == "none", typed


def test_a_short_excerpt_is_offered_not_a_whole_verse():
    r = ask("قال تعالى: الله لا إله إلا")
    for c in r["choices"]:
        assert c["added_words"] <= max(CHUNK_WORDS, CHUNK_TAIL)
    first = r["choices"][0]
    assert first["label"] == "البقرة: 255" and first["remaining_words"] > 20 and first["extend_text"]   # Ayat al-Kursi: the rest only on request
    assert len(r["choices"]) <= MAX_CHOICES


# ---- when it stays silent ----------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("typed", [
    "وما خلقت الجن والإنس إلا",                                           # no lead-in, no opening mark
    "قال رسول الله صلى الله عليه وسلم: وما خلقت الجن والإنس إلا",          # a hadith cue
    "قال تعالى: ﴿إن مع العسر يسرا﴾. وما خلقت الجن والإنس إلا",            # after a closed quotation and a full stop
    "قال تعالى: إن مع العسر يسرا",                                         # the verse is already complete
    "قال تعالى: وبالوالدين",                                               # one word
    "اللهم إني أسألك العفو والعافية في الدنيا",                             # a du'a
])
def test_no_suggestion_without_a_quran_cue_or_when_nothing_is_left(typed):
    assert ask(typed)["status"] == "none", typed


def test_distinct_text_without_a_cue_is_suggested_only_when_the_writer_allowed_it():
    typed = "وما خلقت الجن والإنس إلا"
    assert ask(typed)["status"] == "none"
    r = ask(typed, distinct=True)
    assert best(r)["to_text"] == "ليعبدون" and r["trigger"] == "distinct"
    r = ask(typed, explicit=True)
    assert best(r)["to_text"] == "ليعبدون" and r["trigger"] == "explicit"


def test_the_caret_inside_an_existing_word_is_left_alone():
    assert ask("قال تعالى: وما خلقت الجن والإنس إلا ل", "يعبدون")["reason"] == "inside_word"


def test_a_word_already_written_after_the_caret_is_not_suggested_again():
    r = ask("قال تعالى: وما خلقت الجن والإنس إلا ", "ليعبدون")
    assert r["status"] == "none" and r["reason"] == "already_present"


def test_explicit_request_with_too_little_text_is_a_hint_not_a_guess():
    r = ask("الذين ", explicit=True)
    assert r["status"] == "hint" and r["choices"] == []


# ---- provenance: every proposed word is a word of the proposed verse in the Quranpedia text ---------------------------------
PROBES = [
    "قال تعالى: وما خلقت الجن والإنس إلا", "قال تعالى: إن مع العسر", "قال تعالى: ربنا آتنا في الدنيا حسنة", "قال تعالى: ألا بذكر الله",
    "قال تعالى: إنما يخشى الله من عباده", "قال تعالى: يا أيها الذين آمنوا كتب", "﴿وما خلقت الجن والإنس إلا لعبادتي", "قال تعالى: الله لا إله إلا",
    "قال تعالى: ﴿يا أيها الذين آمنوا استعينوا والصلاة ", "قال تعالى: وما خلقت الجن والإنس إلا ليعب",
]


@pytest.mark.parametrize("typed", PROBES)
def test_every_proposed_word_and_reference_comes_from_the_source_text(typed):
    r = ask(typed)
    assert r["status"] == "suggest"
    for c in r["choices"]:
        a = INDEX.ayahs[(c["surah"], c["ayah_end"])]
        assert c["verse"]["text"] == a.text and c["verse"]["words"] == a.words           # the card's verse is the source verse itself
        lo, hi = c["verse"]["added"]
        source_words = [t.fold for w in a.words[lo:hi] for t in arabic.tokenize(w)]
        proposed = [t.fold for t in arabic.tokenize(c["to_text"])]
        assert proposed == source_words, (c["to_text"], a.words[lo:hi])                    # nothing generated, nothing re-spelt but the marks
        assert c["label"].startswith(c["surah_name"]) and c["verse"]["page_url"].endswith(f"surah={c['surah']}&ayah={c['ayah_end']}")
        if c["extend_text"]:
            rest = [t.fold for t in arabic.tokenize(c["extend_text"])]
            assert rest == [t.fold for w in a.words[hi:] for t in arabic.tokenize(w)]


def test_vocalized_typing_gets_vocalized_proposals_and_plain_typing_plain_ones():
    voc = best(ask("قال تعالى: وَمَا خَلَقْتُ الْجِنَّ وَالْإِنْسَ إِلَّا"))
    assert arabic.has_diacritics(voc["to_text"])
    assert not arabic.has_diacritics(best(ask("قال تعالى: وما خلقت الجن والإنس إلا"))["to_text"])


# ---- the endpoint -------------------------------------------------------------------------------------------------------------
@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(main, "source", _source_with_index())
    main._hits.clear()
    return TestClient(main.app)


def _source_with_index():
    class S:
        def get(self):
            return INDEX

        def status(self):
            return {"loaded": True}
    return S()


def test_endpoint_echoes_the_request_id_and_returns_choices(client):
    r = client.post("/api/suggest", json={"before": "قال تعالى: وما خلقت الجن والإنس إلا", "request_id": 7})
    j = r.json()
    assert r.status_code == 200 and j["request_id"] == 7 and j["status"] == "suggest" and j["choices"][0]["to_text"] == "ليعبدون"


def test_endpoint_bounds_its_input(client):
    assert client.post("/api/suggest", json={"before": "ا" * 5000}).status_code == 422
    assert client.post("/api/suggest", json={"before": "x", "after": "ا" * 1000}).status_code == 422


def test_suggestions_do_not_use_up_the_audit_allowance(client):
    for _ in range(12):
        assert client.post("/api/suggest", json={"before": "قال تعالى: إن مع العسر"}).status_code == 200
    assert main._rate_limited("testclient", "audit") is False   # the audit bucket is separate


def test_endpoint_rate_limit_answers_429(client, monkeypatch):
    monkeypatch.setattr(main, "settings", dataclasses.replace(settings, suggest_rate_limit_per_minute=3))
    codes = [client.post("/api/suggest", json={"before": "قال تعالى: إن مع العسر"}).status_code for _ in range(5)]
    assert codes[:3] == [200, 200, 200] and codes[3:] == [429, 429]


def test_endpoint_without_the_source_says_so_and_proposes_nothing(monkeypatch):
    from app.quran_source import SourceUnavailable

    class Down:
        def get(self):
            raise SourceUnavailable("offline")
    monkeypatch.setattr(main, "source", Down())
    main._hits.clear()
    j = TestClient(main.app).post("/api/suggest", json={"before": "قال تعالى: إن مع العسر"}).json()
    assert j["status"] == "none" and j["reason"] == "source_unavailable" and j["choices"] == []

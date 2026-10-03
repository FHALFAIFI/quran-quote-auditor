"""How much of a verse the first «أدرج» inserts (app/suggest.py, ``_chunk_bounds``), 4 Oct 2026.

The reported defect: after «قال تعالى: إن الله يأمركم أن تؤدوا الأمانات», «أدرج» inserted «إلى أهلها وإذا حكمتم», a fixed four words that ran into
the next clause, so the writer had to delete «وإذا حكمتم». The first piece now stops at the source's own pause sign, before a word that opens a
new clause, and never on a particle that governs the next word; the rest stays one keystroke away (the next suggestion, or «إلى نهاية الآية»).

The offline tests use the committed fixture (tests/fixtures/hafs_subset.json); the full-text tests use the local copy of the Quranpedia text and
are skipped without it, like tests/test_suggest_full.py.
"""

import pytest

from app import arabic
from app.quran_source import Ayah, QuranSource, settings
from app.suggest import _CLAUSE_OPENERS, _NEEDS_NEXT, _PAUSE_SIGNS, CHUNK_TAIL, CHUNK_WORDS, _chunk_bounds, _needs_next, _pauses_after, suggest

FULL = QuranSource(cache_dir=settings.cache_dir)._load_disk()
needs_full = pytest.mark.skipif(FULL is None, reason="no local copy of the Quranpedia text (run the app once)")


def best(r):
    assert r["status"] == "suggest", r
    return r["choices"][0]


def folds(text):
    return [t.fold for t in arabic.tokenize(text)]


def fake(text):
    """An ayah built from placeholder words (not Quran text) to test the rule alone."""
    words = [w for w in text.split() if arabic.folded(arabic.literal(w))]
    return Ayah(0, 0, text, words, [arabic.folded(w) for w in words])


# ---- the rule on placeholder words (no source needed) ----------------------------------------------------------------------------
def test_a_word_that_opens_a_new_clause_ends_the_first_piece():
    a = fake("كتب زيد درسه وإذا قرأ عمرو كتابه نام خالد طويلا")
    assert _chunk_bounds(a, 0) == (0, 3)                     # «كتب زيد درسه», not «… وإذا»


def test_the_first_piece_never_ends_on_a_particle_that_governs_the_next_word():
    a = fake("رأى زيد الذين في السوق صباحا وعاد مسرعا إلى بيته")
    assert _chunk_bounds(a, 0) == (0, 2)                     # «رأى زيد الذين في» would end on «في»: shortened to «رأى زيد»


def test_two_particles_at_the_start_lengthen_the_piece_to_the_word_they_govern():
    a = fake("أخذ عن الذين لم يكتبوا شيئا وعاد مسرعا إلى بيته صباحا")
    lo, hi = _chunk_bounds(a, 0)
    assert (lo, hi) == (0, 5) and not _needs_next(a.words[hi - 1])   # «أخذ عن الذين لم يكتبوا», never «أخذ عن»


def test_a_pause_sign_in_the_text_is_a_stop_even_after_one_word():
    a = fake("كتب زيد درسه ۚ وقرأ عمرو كتابه")
    assert _pauses_after(a) == {2}
    assert _chunk_bounds(a, 2) == (2, 3)                     # «درسه» and the pause: the writer can go on with Tab
    assert _chunk_bounds(a, 0) == (0, 3)


def test_six_words_before_a_stop_are_split_three_and_three_unless_the_last_two_begin_with_a_conjunction():
    assert _chunk_bounds(fake("كتب زيد درسه اليوم إليه راجع ۚ"), 0) == (0, 3)   # not «… اليوم» and a stranded «إليه راجع»
    assert _chunk_bounds(fake("كتب زيد درسه اليوم فهو سعيد ۚ"), 0) == (0, 4)   # «فهو سعيد» is a clause of its own


def test_the_rest_of_a_short_phrase_is_offered_whole():
    assert _chunk_bounds(fake("كتب زيد درسه كله اليوم"), 0) == (0, 5)
    assert _chunk_bounds(fake("كتب زيد درسه كله اليوم"), 3) == (3, 5)


def test_pauses_are_not_reported_when_the_text_and_the_words_disagree():
    a = fake("كتب زيد ۚ درسه")
    assert _pauses_after(Ayah(0, 0, a.text, a.words[:2], a.folded[:2])) == set()


# ---- real verses from the committed fixture (offline) ----------------------------------------------------------------------------
def test_offline_fixture_stops_at_the_source_pause_sign(index):
    c = best(suggest(index, "قال تعالى: ﴿واعتصموا بحبل الله", explicit=True))   # the fixture's 36 verses make every word look rare
    assert (c["to_text"], c["label"]) == ("جميعا ولا تفرقوا", "آل عمران: 103")   # the Hafs text has ۚ after «تفرقوا»
    assert c["remaining_words"] > 0 and c["extend_text"]
    assert not any(ch in _PAUSE_SIGNS or ch == "۞" for ch in c["insert_text"])    # the signs are reading marks, never inserted


def test_offline_fixture_six_words_to_the_verse_end_come_in_two_halves(index):
    typed = "قال تعالى: الذين إذا أصابتهم مصيبة"
    c = best(suggest(index, typed, explicit=True))
    assert c["to_text"] == "قالوا إنا لله" and c["remaining_words"] == 3
    c2 = best(suggest(index, typed + c["insert_text"], explicit=True))
    assert c2["to_text"] == "وإنا إليه راجعون" and c2["remaining_words"] == 0


# ---- the reported example and the full text --------------------------------------------------------------------------------------
@needs_full
def test_the_reported_example_stops_after_ilaa_ahliha_and_the_rest_follows_on_request():
    typed = "قال تعالى: إن الله يأمركم أن تؤدوا الأمانات"
    c = best(suggest(FULL, typed))
    assert (c["kind"], c["certainty"], c["to_text"], c["insert_text"], c["label"]) == ("continue", "exact", "إلى أهلها", " إلى أهلها", "النساء: 58")
    assert c["remaining_words"] == 17 and folds(c["extend_text"])[:2] == folds("وإذا حكمتم")
    pieces = [c["to_text"]]
    text = typed + c["insert_text"]
    for _ in range(6):                                       # accept each next piece, as Tab after Tab does in the editor
        r = suggest(FULL, text)
        if r["status"] != "suggest":
            break
        c = best(r)
        pieces.append(c["to_text"])
        text += c["insert_text"]
    assert pieces[:3] == ["إلى أهلها", "وإذا حكمتم بين الناس", "أن تحكموا بالعدل"]   # «بالعدل ۚ»: the source's pause
    a = FULL.ayahs[(4, 58)]
    assert folds(" ".join(pieces)) == a.folded[6:]           # piece after piece, exactly the rest of the verse and nothing else


@needs_full
def test_the_whole_verse_is_still_one_choice_away():
    c = best(suggest(FULL, "قال تعالى: إن الله يأمركم أن تؤدوا الأمانات"))
    assert folds(c["insert_text"] + c["extend_text"]) == FULL.ayahs[(4, 58)].folded[6:]


@needs_full
@pytest.mark.parametrize("typed,expect,label", [
    ("قال تعالى: إنا أعطيناك", "الكوثر", "الكوثر: 1"),            # a verse of three words: the last word, nothing more
    ("قال تعالى: وقل رب زدني", "علما", "طه: 114"),
    ("قال تعالى: فإن مع العسر", "يسرا", "الشرح: 5"),
])
def test_a_short_verse_ends_where_the_verse_ends(typed, expect, label):
    c = best(suggest(FULL, typed))
    assert (c["to_text"], c["label"], c["remaining_words"], c["extend_text"]) == (expect, label, 0, None)


@needs_full
def test_an_ambiguous_beginning_offers_each_verse_its_own_short_piece_and_picks_none():
    r = suggest(FULL, "قال تعالى: ﴿إن الله يأمركم")
    assert r["ambiguous"]
    got = {c["label"]: c["to_text"] for c in r["choices"]}
    assert got == {"البقرة: 67": "أن تذبحوا بقرة", "النساء: 58": "أن تؤدوا الأمانات"}   # before «قالوا»; never ending on «إلى»
    for c in r["choices"]:
        assert not _needs_next(c["to_text"].split()[-1])


@needs_full
def test_punctuation_before_the_caret_gets_a_space_and_the_piece_is_unchanged():
    for typed in ("قال تعالى: «إن الله يأمركم أن تؤدوا الأمانات", "قال تعالى: إن الله يأمركم أن تؤدوا الأمانات،"):
        c = best(suggest(FULL, typed))
        assert (c["to_text"], c["insert_text"]) == ("إلى أهلها", " إلى أهلها"), typed


@needs_full
def test_across_the_whole_text_no_first_piece_crosses_a_pause_sign_and_almost_none_ends_on_a_governing_particle():
    """Every word position of all 6,236 verses. Before this change a fixed four words ran across a pause sign 10,813 times and ended on
    a governing particle 10,572 times (of 48,578 mid-verse pieces)."""
    crossing = dangling = mid = 0
    for a in FULL.ayahs.values():
        pauses = _pauses_after(a)
        for nxt in range(len(a.words)):
            lo, hi = _chunk_bounds(a, nxt)
            assert 1 <= hi - lo <= max(CHUNK_WORDS, CHUNK_TAIL)
            crossing += any(i in pauses for i in range(lo, hi - 1))
            if hi < len(a.words):
                mid += 1
                dangling += _needs_next(a.words[hi - 1])
    assert crossing == 0
    assert dangling <= mid // 1000, (dangling, mid)          # 5 of 50,900 on 4 Oct 2026: 2 at the five-word ceiling (9:91-92), 3 at the source's saktah mark (75:27, 83:14)


@needs_full
def test_tab_after_tab_tiles_every_verse_exactly():
    for a in list(FULL.ayahs.values())[::97]:
        nxt, out = 0, []
        while nxt < len(a.words):
            lo, hi = _chunk_bounds(a, nxt)
            out.extend(a.folded[lo:hi])
            nxt = hi
        assert out == a.folded, (a.surah, a.number)


def test_the_word_lists_hold_no_duplicate_spellings():
    assert all(w == arabic.folded(w) for w in _CLAUSE_OPENERS) and all(w == arabic.letters(w) for w in _NEEDS_NEXT)


def test_a_pronoun_ending_or_a_verb_is_not_taken_for_a_particle():
    assert _needs_next("إِلَى") and _needs_next("عَلَىٰ") and _needs_next("بَيْنَ")
    assert not _needs_next("إِلَيَّ") and not _needs_next("عَلَيَّ") and not _needs_next("بَيَّنَ")

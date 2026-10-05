"""Which verse comes first when several places align equally well (hard-quotation set HD-017, 5 Oct 2026).

«كل نفس بما كسبت رهين» shares four whole words with الرعد 33, غافر 17, الجاثية 22 and المدثر 38, and differs in one word from each.
Only in المدثر 38 is the differing word spelt like the writer's («رهينة»); before this rule the three others filled the list of
choices and the verse the writer meant was not offered at all. The tie-break changes the order only: no span, tier or proposal.
"""

import time

from app import arabic
from app.quran_source import build_index
from app.verifier import fuzzy_candidates, verify

AYAHS = [  # the Quranpedia (Hafs) text of the four places
    {"surah": 13, "number": 33, "text": "أَفَمَنْ هُوَ قَائِمٌ عَلَىٰ كُلِّ نَفْسٍ بِمَا كَسَبَتْ ۗ وَجَعَلُوا لِلَّهِ شُرَكَاءَ قُلْ سَمُّوهُمْ"},
    {"surah": 40, "number": 17, "text": "الْيَوْمَ تُجْزَىٰ كُلُّ نَفْسٍ بِمَا كَسَبَتْ ۚ لَا ظُلْمَ الْيَوْمَ ۚ إِنَّ اللَّهَ سَرِيعُ الْحِسَابِ"},
    {"surah": 45, "number": 22, "text": "وَخَلَقَ اللَّهُ السَّمَاوَاتِ وَالْأَرْضَ بِالْحَقِّ وَلِتُجْزَىٰ كُلُّ نَفْسٍ بِمَا كَسَبَتْ وَهُمْ لَا يُظْلَمُونَ"},
    {"surah": 74, "number": 38, "text": "كُلُّ نَفْسٍ بِمَا كَسَبَتْ رَهِينَةٌ"},
]
INDEX = build_index(AYAHS, time.time())


def words(text):
    return [t.raw for t in arabic.tokenize(text)]


def test_the_places_tie_on_whole_words():
    qf = [arabic.search_fold(w) for w in words("كل نفس بما كسبت رهين")]
    sims = {round(a.similarity, 3) for a in fuzzy_candidates(INDEX, qf, limit=10)}
    assert sims == {0.8}  # the premise: whole words alone cannot tell the places apart


def test_the_place_with_the_near_spelt_word_comes_first():
    r = verify(INDEX, words("كل نفس بما كسبت رهين"), None)
    assert r["source"]["label"] == "المدثر: 38"
    assert r["wording"]["status"] == "difference"
    assert len(r["alternatives"]) == 2  # still a choice: the others stay listed after it


def test_a_tie_is_still_never_a_proposal():
    # the runner-up is as similar as the first place, so no replacement is offered before the writer picks the verse
    r = verify(INDEX, words("كل نفس بما كسبت رهين"), None)
    assert r["proposal"]["status"] == "review_only" and r["proposal"]["edits"] == []


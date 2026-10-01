"""Phrase search against the FULL Quranpedia Hafs text, when a local copy exists.

The app caches the text in the temporary directory after its first run (``hafs-mushaf-1.json``); these tests
use that file and are skipped when it is absent (for example on a clean CI machine), so the suite stays offline.
They check behaviour that depends on real-Quran statistics (rarity mass), which the 36-verse fixture cannot show.
Expected values describe the tiers chosen in app/phrases.py; they are regression checks, not accuracy claims.
"""

import pytest

from app import arabic
from app.phrases import find_phrases
from app.quran_source import QuranSource, settings

_source = QuranSource(cache_dir=settings.cache_dir)
INDEX = _source._load_disk()
pytestmark = pytest.mark.skipif(INDEX is None, reason="no local copy of the Quranpedia text (run the app once)")


def hits(text):
    sc = find_phrases(text, arabic.tokenize(text), INDEX)
    toks = arabic.tokenize(text)
    return [(text[toks[h.first].start:toks[h.last - 1].end], h) for h in sc.hits], sc


@pytest.mark.parametrize("quote", [
    "وافعلوا الخير لعلكم تفلحون",        # 4 words, unmarked, no reference (evaluation case c11)
    "ولا تنسوا الفضل بينكم",
    "وتعاونوا على البر والتقوى",          # held-out h02
    "ادعوا ربكم تضرعا وخفية",            # held-out h03
])
def test_short_distinctive_quotations_are_candidates(quote):
    found, _ = hits(f"العمل الصالح طريق النجاح، والله يقول {quote}. وفي الخلافات نتذكر ذلك.")
    assert [(t, h.tier) for t, h in found] == [(quote, "candidate")]


def test_common_fragments_are_not_reported_and_are_counted():
    found, sc = hits("يعيش الناس في كثير من المدن الكبيرة.")
    assert found == [] and len(sc.suppressed) == 1


def test_formulas_hadith_and_sayings_are_never_candidates():
    found, sc = hits("بسم الله الرحمن الرحيم، أما بعد.")
    assert found == [] and len(sc.suppressed) == 1                      # everyday formula with no Quran cue: hidden
    (hadith,) = hits("وجاء في الحديث: من كان يؤمن بالله واليوم الآخر فليقل خيرا أو ليصمت.")[0]
    assert hadith[1].tier == "possible" and "non_quran_cue" in hadith[1].reasons
    for text in ["إنما الأعمال بالنيات", "من جد وجد", "اللهم إني أسألك العفو والعافية", "الدين النصيحة", "لا ضرر ولا ضرار"]:
        assert hits(text)[0] == []


def test_a_misquotation_is_possible_never_matched_and_keeps_the_wrong_word_inside():
    text = "وفي مواساة المصابين وبشر المؤمنين الذين إذا أصابتهم مصيبة قالوا إنا لله وإنا إليه راجعون رسالة أمل."
    ((quoted, h),) = hits(text)[0]
    assert quoted.startswith("وبشر المؤمنين") and quoted.endswith("راجعون")
    assert h.tier == "possible" and not h.exact


def test_repeated_phrase_keeps_every_place():
    ((_, h),) = hits("وقال إن الله مع الصابرين دائما")[0]
    assert h.exact and len(h.spans) >= 2


def test_search_builds_no_phrase_dictionary():
    assert not hasattr(INDEX, "ngrams")


def test_work_budget_cuts_off_pathological_input_but_not_real_text():
    words = sorted(INDEX.doc_freq, key=lambda w: -INDEX.doc_freq[w])[:60]
    soup = " ".join(words[(k * 7) % 60] for k in range(900))[:5900]        # frequent words only: no real article looks like this
    found, sc = hits(soup)
    assert sc.truncated and sc.steps <= 80_000 + 400                        # stopped by the budget, and says so
    real = " ".join(INDEX.ayahs[k].text for k in sorted(INDEX.ayahs)[300:420])[:5900]  # 6,000 characters of real mushaf text
    found, sc = hits(real)
    assert not sc.truncated and found


# --- the two end-of-quotation misquotations of the frozen set (eval/phrases_frozen.json f23, f32) ----------------------
# Both were once reported "matched". The wrong words are at the END, so the search selects the correct opening as a
# candidate; its end is not settled, so the wording verdict must not be "matched".

@pytest.mark.parametrize("article, quoted, quran_next, article_next", [
    ("ولا يتغير حال قوم دون عمل، فإن الله لا يغير ما بقوم حتى يغيروا أنفسهم كما نقرأ.", "الله لا يغير ما بقوم حتى يغيروا", "ما", "أنفسهم"),
    ("والعبادة غاية الوجود، وما خلقت الجن والإنس إلا لعبادتي كما يقول المفسرون.", "وما خلقت الجن والإنس إلا", "ليعبدون", "لعبادتي"),
])
def test_frozen_end_misquotations_are_not_matched(monkeypatch, article, quoted, quran_next, article_next):
    import app.audit as audit
    from tests.conftest import FakeSource

    monkeypatch.setattr(audit, "source", FakeSource(INDEX))
    monkeypatch.setattr(audit, "get_provider", lambda: None)
    res = audit.run_audit(article)
    (f,) = res["findings"]
    assert f["quote"] == quoted and f["detection"]["tier"] == "candidate"        # the candidate is still reported
    assert f["wording"]["status"] == "uncertain" and f["needs_review"]
    assert f["continuation"] == {"quran": quran_next, "article": article_next}
    assert f["reference"]["status"] == "missing" and res["stats"]["matched"] == 0


# --- the start-of-quotation rule on real frozen/held-out text -------------------------------------------------------
# Correct quotations that begin in the middle of a verse and follow ordinary prose were "matched" before the start rule.
# Reported as "uncertain": prose before a correct quotation and a wrong first word look the same.

@pytest.mark.parametrize("article, quoted, quran_prev, article_prev", [
    ("القلب لا يهدأ بكثرة المال، أَلَا بِذِكْرِ اللَّهِ تَطْمَئِنُّ الْقُلُوبُ وتسكن النفوس.",           # frozen f07
     "أَلَا بِذِكْرِ اللَّهِ تَطْمَئِنُّ الْقُلُوبُ", "الله", "المال"),
    ("إذا ضاقت بك السبل فتذكر ومن يتق الله يجعل له مخرجا، واطلب المزيد.",                            # held-out h01
     "ومن يتق الله يجعل له مخرجا", "الآخر", "فتذكر"),
])
def test_correct_quotations_after_prose_are_uncertain_not_matched(monkeypatch, article, quoted, quran_prev, article_prev):
    import app.audit as audit
    from tests.conftest import FakeSource

    monkeypatch.setattr(audit, "source", FakeSource(INDEX))
    monkeypatch.setattr(audit, "get_provider", lambda: None)
    res = audit.run_audit(article)
    (f,) = res["findings"]
    assert f["quote"] == quoted                                                     # detected as before
    assert f["wording"]["status"] == "uncertain" and f["needs_review"]
    assert f["lead_in"] == {"quran": quran_prev, "article": article_prev}
    assert f["reference"]["status"] == "missing" and res["stats"]["matched"] == 0

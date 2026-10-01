"""Unmarked-phrase search: detection tiers, offsets, manual selection (all offline, on the small fixture).

The fixture has only 36 verses, so rarity statistics differ from the full Quran's; the ``lenient`` fixture
lowers the mass thresholds so the same rules can be exercised on it. A test against the real text, which
runs only when a local copy of the Quranpedia text exists, is in test_phrases_full.py.
"""

import pytest
from fastapi.testclient import TestClient

import app.audit as audit
import app.phrases as ph
from app import arabic
from app.audit import InputError, run_audit, run_phrase
from app.extraction.base import RawSuggestion
from tests.test_pipeline import FakeProvider


@pytest.fixture
def lenient(monkeypatch):
    monkeypatch.setattr(ph, "MASS_FLOOR", 3.0)
    monkeypatch.setattr(ph, "MASS_CANDIDATE", 9.0)
    monkeypatch.setattr(ph, "MASS_APPROX", 4.0)
    monkeypatch.setattr(ph, "ANCHOR_IDF", 3.0)


def scan(index, article):
    return ph.find_phrases(article, arabic.tokenize(article), index)


def apply(article, changes):
    for c in sorted(changes, key=lambda c: -c["start"]):
        assert article[c["start"]:c["end"]] == c["original"]
        article = article[:c["start"]] + c["replacement"] + article[c["end"]:]
    return article


# --- search ---------------------------------------------------------------------------------------

def test_unmarked_exact_phrase_is_found_with_article_offsets(index, lenient):
    article = "وهنا قالوا واعتصموا بحبل الله جميعا ولا تفرقوا في كل أمر."
    (hit,) = scan(index, article).hits
    toks = arabic.tokenize(article)
    assert article[toks[hit.first].start:toks[hit.last - 1].end] == "واعتصموا بحبل الله جميعا ولا تفرقوا"
    assert hit.exact and hit.tier == "candidate" and hit.reasons == []


def test_a_full_stop_ends_a_run_but_a_comma_does_not(index, lenient):
    (a,) = [h for h in scan(index, "واعتصموا بحبل الله، جميعا ولا تفرقوا").hits]
    assert a.words == 6
    hits = scan(index, "واعتصموا بحبل الله. جميعا ولا تفرقوا").hits
    assert sorted(h.words for h in hits) == [3, 3]  # two separate phrases, never one across the full stop


def test_words_of_ordinary_prose_are_not_absorbed(index, lenient):
    article = "كتب الباحث أن الأمة تحتاج واعتصموا بحبل الله جميعا ولا تفرقوا لأن الوحدة مطلب."
    (hit,) = scan(index, article).hits
    toks = arabic.tokenize(article)
    assert article[toks[hit.first].start:toks[hit.last - 1].end] == "واعتصموا بحبل الله جميعا ولا تفرقوا"


def test_a_substituted_word_stays_inside_the_span(index, lenient):
    # The old verbatim scan trimmed the wrong word off and called the correct part a clean match.
    article = "وفي مواساة المصابين وبشر المؤمنين الذين إذا أصابتهم مصيبة قالوا إنا لله وإنا إليه راجعون رسالة أمل."
    (hit,) = scan(index, article).hits
    toks = arabic.tokenize(article)
    text = article[toks[hit.first].start:toks[hit.last - 1].end]
    assert text.startswith("وبشر المؤمنين الذين") and text.endswith("راجعون")
    assert not hit.exact and hit.tier == "possible" and hit.edits == 1 and "approximate" in hit.reasons


def test_one_weak_word_cannot_stretch_a_phrase_over_prose(index, lenient):
    # "الخاص،" is followed by a comma and only a single near-match word stands beyond the edit: not absorbed
    article = "لكل إنسان حسابه الخاص، واعتصموا بحبل الله جميعا ولا تفرقوا فلا خلاف."
    (hit,) = scan(index, article).hits
    toks = arabic.tokenize(article)
    assert article[toks[hit.first].start:toks[hit.last - 1].end] == "واعتصموا بحبل الله جميعا ولا تفرقوا"
    assert hit.exact


def test_a_letter_changed_inside_a_word_is_a_near_match(index, lenient):
    # مذكر for مدكر: one letter differs in the middle of the word (no shared prefix or suffix to lean on)
    assert ph._soft("مذكر", "مدكر") and not ph._soft("كتاب", "مدكر")


def test_a_misspelt_last_word_is_kept_in_the_span(index, lenient):
    article = "ومن ذلك قولنا اقرأ باسم ربك الذي خلقك دائما."
    (hit,) = scan(index, article).hits
    toks = arabic.tokenize(article)
    assert article[toks[hit.first].start:toks[hit.last - 1].end].endswith("خلقك")
    assert hit.tier == "possible" and hit.soft == 1


def test_repeated_phrase_lists_every_place(index, lenient):
    (hit,) = scan(index, "فبأي آلاء ربكما تكذبان").hits
    assert len(hit.spans) == 2 and hit.exact


def test_work_budget_is_reported(index, lenient, monkeypatch):
    monkeypatch.setattr(ph, "MAX_SEED_STEPS", 2)
    assert scan(index, "واعتصموا بحبل الله جميعا ولا تفرقوا " * 20).truncated


def test_no_phrase_dictionary_is_built(index, lenient):
    """Memory: the index holds words and their positions only; searching must not grow it."""
    assert not hasattr(index, "ngrams")
    before = {k: len(v) for k, v in vars(index).items() if hasattr(v, "__len__")}
    scan(index, "واعتصموا بحبل الله جميعا ولا تفرقوا وقل رب زدني علما")
    assert before == {k: len(v) for k, v in vars(index).items() if hasattr(v, "__len__")}


# --- tiers --------------------------------------------------------------------------------------------

def test_formula_and_hadith_context_are_never_candidates(index, lenient):
    assert scan(index, "بسم الله الرحمن الرحيم").hits == []  # an everyday formula with no cue: hidden, counted
    assert len(scan(index, "بسم الله الرحمن الرحيم").suppressed) == 1
    (basmala,) = scan(index, "وقال تعالى في أول الكتاب بسم الله الرحمن الرحيم").hits
    assert basmala.tier == "possible" and "formula" in basmala.reasons  # with a Quran cue it is shown, never as a candidate
    (hadith,) = scan(index, "وقد جاء في الحديث الشريف: واعتصموا بحبل الله جميعا ولا تفرقوا").hits
    assert hadith.tier == "possible" and "non_quran_cue" in hadith.reasons
    (cued,) = scan(index, "قال تعالى واعتصموا بحبل الله جميعا ولا تفرقوا").hits
    assert cued.tier == "candidate"  # an explicit Quran cue keeps a distinctive phrase a candidate


def test_short_common_phrases_are_hidden_but_counted(index, monkeypatch):
    monkeypatch.setattr(ph, "MASS_FLOOR", 50.0)
    sc = scan(index, "واعتصموا بحبل الله جميعا ولا تفرقوا")
    assert sc.hits == [] and len(sc.suppressed) == 1


def test_ordinary_arabic_and_non_quran_sayings_give_nothing(index):
    for text in ["إنما الأعمال بالنيات", "من جد وجد", "اللهم إني أسألك العفو والعافية", "سافر الوفد إلى العاصمة يوم الخميس"]:
        assert scan(index, text).hits == []


# --- pipeline -----------------------------------------------------------------------------------------

def test_candidate_finding_carries_detection_and_source_backed_change(use_source, lenient):
    # إن (hamza-less spelling of the verse's 'إن' is fine); a vocalized word with the wrong mark gives a proposal
    article = "وهنا واعتصموا بحبل اللهِ جميعا ولا تفرقوا في كل أمر."
    res = run_audit(article)
    (f,) = res["findings"]
    assert f["detection"]["kind"] == "phrase" and f["detection"]["tier"] == "candidate"
    assert f["detected_by"] == ["phrase"]
    assert res["stats"]["candidates"] == 1 and res["stats"]["possible"] == 0
    assert article[f["start"]:f["end"]] == f["quote"]


def test_possible_phrase_offers_no_changes_until_confirmed(use_source, lenient):
    article = "وفي مواساة المصابين وبشر المؤمنين الذين إذا أصابتهم مصيبة قالوا إنا لله وإنا إليه راجعون رسالة أمل."
    res = run_audit(article)
    (f,) = res["findings"]
    assert f["detection"]["tier"] == "possible" and f["detection"]["unconfirmed"]
    assert f["detection"]["label"] == "قد يكون اقتباسًا قرآنيًا — يحتاج مراجعة"
    assert f["changes"] == [] and f["correction"]["status"] == "unconfirmed" and f["needs_review"]
    assert f["wording"]["status"] == "difference" and f["wording"]["level"] == "fuzzy"  # never "matched"
    assert res["stats"]["possible"] == 1 and res["stats"]["matched"] == 0
    # the editor confirms the place: now, and only now, a source-backed proposal appears, limited to the quoted span
    (choice,) = f["choices"]
    out = run_phrase(article, f["start"], f["end"], choice["surah"], choice["ayah_start"], choice["ayah_end"])["finding"]
    assert out["detection"]["kind"] == "manual" and out["changes"]
    fixed = apply(article, [c for c in out["changes"] if not c["optional"]])
    assert fixed.startswith("وفي مواساة المصابين وبشر الصابرين الذين") and fixed.endswith("راجعون رسالة أمل.")


def test_marked_quote_and_phrase_hit_become_one_finding(use_source, lenient):
    article = "قال تعالى: ﴿واعتصموا بحبل الله جميعا ولا تفرقوا﴾ وانتهى."
    res = run_audit(article)
    (f,) = res["findings"]
    assert f["detected_by"] == ["marked", "phrase"] and f["detection"]["kind"] == "marked"


def test_ai_candidate_and_phrase_hit_are_deduplicated(use_source, lenient, monkeypatch):
    article = "وهنا قالوا واعتصموا بحبل الله جميعا ولا تفرقوا في كل أمر."
    monkeypatch.setattr(audit, "get_provider", lambda: FakeProvider([RawSuggestion("واعتصموا بحبل الله جميعا ولا تفرقوا")]))
    (f,) = run_audit(article)["findings"]
    assert f["detected_by"] == ["ai", "phrase"]


def test_repeated_phrase_shows_choices_and_picks_none(use_source, lenient):
    res = run_audit("ونقول لكل متعب إن الله مع الصابرين مهما طال الطريق.")
    (f,) = res["findings"]
    assert f["source"] is None and f["changes"] == []
    assert {c["label"] for c in f["choices"]} >= {"البقرة: 153", "الأنفال: 46"}


def test_continuation_hint_shows_the_next_word_without_a_verdict(use_source, lenient):
    f = run_audit("وذلك أن إنما يخشى الله من عباده الفقهاء عند الناس.")["findings"][0]
    assert f["continuation"] == {"quran": "العلماء", "article": "الفقهاء"}
    g = run_audit("إنما يخشى الله من عباده العلماء عند الناس.")["findings"][0]
    assert g["continuation"] is None or g["continuation"]["article"] != "العلماء"


# --- end of the span: "matched" only when the whole identified span is settled -------------------------------------

def _one(article):
    res = run_audit(article)
    (f,) = res["findings"]
    return f, res


def test_wrong_last_word_after_the_matching_part_is_not_matched(use_source, lenient):
    """Release blocker: a quotation whose LAST word is wrong looks like a correct partial quotation followed by prose."""
    f, res = _one("وهنا واعتصموا بحبل الله جميعا ولا تفرقوا وكذلك نختم المقال.")
    assert f["quote"] == "واعتصموا بحبل الله جميعا ولا تفرقوا" and f["detection"]["tier"] == "candidate"   # candidate kept
    assert f["wording"]["status"] == "uncertain" and f["needs_review"]
    assert f["end_boundary"] == {"status": "uncertain", "basis": "adjacent_word", "quran": "واذكروا", "article": "وكذلك"}
    assert f["continuation"] == {"quran": "واذكروا", "article": "وكذلك"}
    assert f["reference"]["status"] == "missing"                                  # the reference verdict is its own
    assert res["stats"]["matched"] == 0 and res["stats"]["uncertain"] == 1 and res["stats"]["candidates"] == 1
    assert not [c for c in f["changes"] if c["kind"] == "reference_add"]          # a reference would go after a word that may be wrong
    assert f["correction"]["status"] == "review_only"


def test_dropped_words_misquotation_is_not_matched_either(use_source, lenient):
    f, _ = _one("وهنا واعتصموا بحبل الله جميعا ولا تفرقوا أنفسهم دائما.")
    assert f["wording"]["status"] == "uncertain" and f["end_boundary"]["status"] == "uncertain"


def test_a_correct_partial_quotation_stays_matched_when_something_closes_it(use_source, lenient):
    for article, basis in [
        ("وهنا واعتصموا بحبل الله جميعا ولا تفرقوا. وهذا كلام آخر.", "punctuation"),
        ("وهنا واعتصموا بحبل الله جميعا ولا تفرقوا\nوهذا كلام آخر.", "punctuation"),
        ("وهنا واعتصموا بحبل الله جميعا ولا تفرقوا", "article_end"),
        ("وهنا واعتصموا بحبل الله جميعا ولا تفرقوا (آل عمران: 103) وهذا كلام آخر.", "reference"),
        ("وهنا واعتصموا بحبل الله جميعا ولا تفرقوا آل عمران: 103 وهذا كلام آخر.", "reference"),
    ]:
        f, res = _one(article)
        assert f["wording"]["status"] == "matched" and not f["needs_review"], article
        assert f["end_boundary"] == {"status": "settled", "basis": basis} and f["continuation"] is None, article
        assert res["stats"]["matched"] == 1


def test_a_quotation_that_reaches_the_end_of_its_verse_is_settled(use_source, lenient):
    f, _ = _one("وهنا إنما المؤمنون إخوة فأصلحوا بين أخويكم واتقوا الله لعلكم ترحمون وكذلك نختم المقال.")
    assert f["wording"]["status"] == "matched" and f["end_boundary"] == {"status": "settled", "basis": "verse_end"}


def test_a_quotation_followed_by_ordinary_prose_is_flagged_not_matched(use_source, lenient):
    """Prose that touches the span cannot be told from a wrong last word; the candidate stays and the editor decides."""
    f, _ = _one("وهنا واعتصموا بحبل الله جميعا ولا تفرقوا كما قال المفسرون في هذه الآية.")
    assert f["detection"]["tier"] == "candidate" and f["quote"] == "واعتصموا بحبل الله جميعا ولا تفرقوا"
    assert f["wording"]["status"] == "uncertain" and f["needs_review"]
    assert f["continuation"] == {"quran": "واذكروا", "article": "كما"}
    # a comma does not settle it (the search itself reads through commas); a full stop does
    g, _ = _one("وهنا واعتصموا بحبل الله جميعا ولا تفرقوا، كما قال المفسرون.")
    assert g["wording"]["status"] == "uncertain"
    h, _ = _one("وهنا واعتصموا بحبل الله جميعا ولا تفرقوا. كما قال المفسرون.")
    assert h["wording"]["status"] == "matched"


def test_wording_and_reference_verdicts_stay_separate(use_source, lenient):
    f, res = _one("وهنا واعتصموا بحبل الله جميعا ولا تفرقوا وكذلك آل عمران: 103 وهذا كلام آخر.")
    assert f["reference"]["status"] == "matched" and f["wording"]["status"] == "uncertain"   # a right reference does not settle the end
    assert res["stats"]["ref_matched"] == 1 and res["stats"]["matched"] == 0


def test_stated_ends_are_not_questioned(use_source, lenient, monkeypatch):
    marked, _ = _one("قال تعالى ﴿واعتصموا بحبل الله جميعا ولا تفرقوا﴾ كما نرى.")
    assert marked["wording"]["status"] == "matched" and marked["end_boundary"] is None
    article = "وهنا واعتصموا بحبل الله جميعا ولا تفرقوا كما نرى."
    manual = run_phrase(article, article.index("واعتصموا"), article.index(" كما"), 3, 103, 103)["finding"]
    assert manual["wording"]["status"] == "matched" and manual["end_boundary"] is None   # the editor highlighted it
    # an end chosen by the AI is not stated by the writer, so it is held to the same rule
    monkeypatch.setattr(audit, "get_provider", lambda: FakeProvider([RawSuggestion("واعتصموا بحبل الله جميعا ولا تفرقوا")]))
    (ai,) = run_audit(article)["findings"]
    assert ai["detected_by"] == ["ai", "phrase"] and ai["wording"]["status"] == "uncertain"


# --- start of the span: the mirror of the end rule ----------------------------------------------------------------
# The fixture verse 3:103 is «واعتصموا بحبل الله جميعا ولا تفرقوا ۚ واذكروا نعمت الله عليكم إذ كنتم أعداء فألف بين قلوبكم …».
# A quotation that begins in the middle of a verse has a word before it in the verse; if the article's word there differs
# and nothing marks the start, "the writer's prose" and "a wrong first word" cannot be told apart.

MID = "نعمت الله عليكم إذ كنتم أعداء فألف بين قلوبكم"      # begins at the 2nd sentence of the verse (after «واذكروا»)
LEAD_IN_QURAN = "واذكروا"


def test_wrong_first_word_is_not_matched(use_source, lenient):
    """The search starts at the first word that matches, so a wrong first word looks like prose before the quotation."""
    f, res = _one(f"وهنا وتأملوا {MID}. وانتهى الكلام.")
    assert f["quote"] == MID and f["detection"]["tier"] == "candidate"                        # the candidate is still reported
    assert f["wording"]["status"] == "uncertain" and f["needs_review"]
    assert f["start_boundary"] == {"status": "uncertain", "basis": "adjacent_word", "quran": LEAD_IN_QURAN, "article": "وتأملوا"}
    assert f["lead_in"] == {"quran": LEAD_IN_QURAN, "article": "وتأملوا"}
    assert f["end_boundary"]["status"] == "settled" and f["continuation"] is None              # only the start is in question
    assert f["reference"]["status"] == "missing"                                              # the reference verdict is its own
    assert f["wording"]["message"] == audit.START_UNCERTAIN_MESSAGE and audit.START_UNCERTAIN_MESSAGE in f["review_reasons"]
    assert res["stats"]["matched"] == 0 and res["stats"]["uncertain"] == 1 and res["stats"]["candidates"] == 1
    assert f["correction"]["status"] == "review_only"


def test_a_correct_quotation_preceded_by_ordinary_prose_is_flagged_not_matched(use_source, lenient):
    """Prose that touches the span cannot be told from a wrong first word: the candidate stays, the editor decides."""
    f, res = _one(f"كتب الباحث أن الأمة تحتاج {MID}. وانتهى الكلام.")
    assert f["quote"] == MID and f["detection"]["tier"] == "candidate"
    assert f["wording"]["status"] == "uncertain" and f["needs_review"] and f["lead_in"] == {"quran": LEAD_IN_QURAN, "article": "تحتاج"}
    assert res["stats"]["matched"] == 0 and res["stats"]["uncertain"] == 1
    # a comma does not settle it (it is how prose and a quotation are usually joined, and the search reads through commas)
    g, _ = _one(f"كتب الباحث أن الأمة تحتاج، {MID}. وانتهى الكلام.")
    assert g["wording"]["status"] == "uncertain"


def test_a_correct_quotation_stays_matched_when_something_opens_it(use_source, lenient):
    for article, basis in [
        (f"كتب الباحث أن الأمة تحتاج. {MID}. وانتهى الكلام.", "punctuation"),
        (f"كتب الباحث أن الأمة تحتاج:\n{MID}. وانتهى الكلام.", "punctuation"),
        (f"كتب الباحث أن الأمة تحتاج: «{MID}». وانتهى الكلام.", "punctuation"),
        (f"كتب الباحث وقال تعالى {MID}. وانتهى الكلام.", "lead_in"),
        (f"كتب الباحث في القرآن الكريم {MID}. وانتهى الكلام.", "lead_in"),
        (f"كتب الباحث في سورة آل عمران: 103 {MID}. وانتهى الكلام.", "reference"),
        (f"{MID}. وانتهى الكلام.", "article_start"),
    ]:
        f, res = _one(article)
        assert f["wording"]["status"] == "matched" and not f["needs_review"], article
        assert f["start_boundary"] == {"status": "settled", "basis": basis} and f["lead_in"] is None, article
        assert res["stats"]["matched"] == 1


def test_a_quotation_that_begins_where_its_verse_begins_is_settled(use_source, lenient):
    f, _ = _one("وهنا واعتصموا بحبل الله جميعا ولا تفرقوا. وانتهى الكلام.")
    assert f["wording"]["status"] == "matched" and f["start_boundary"] == {"status": "settled", "basis": "verse_start"}


def test_a_lead_in_must_touch_the_span(use_source, lenient):
    """«قال تعالى» settles the start only when the quotation begins right after it, not when another word intervenes."""
    f, _ = _one(f"قال تعالى كما نعلم {MID}. وانتهى الكلام.")
    assert f["wording"]["status"] == "uncertain" and f["start_boundary"]["status"] == "uncertain"


def test_start_and_end_both_uncertain_say_so(use_source, lenient):
    f, res = _one(f"كتب الباحث أن الأمة تحتاج نعمت الله عليكم إذ كنتم أعداء فألف بين قلوبكم وكذلك نختم المقال")
    assert f["start_boundary"]["status"] == "uncertain" and f["end_boundary"]["status"] == "uncertain"
    assert f["lead_in"] and f["continuation"]
    assert f["wording"]["status"] == "uncertain" and f["wording"]["message"] == audit.BOTH_UNCERTAIN_MESSAGE
    assert res["stats"]["matched"] == 0


def test_wording_and_reference_verdicts_stay_separate_at_the_start(use_source, lenient):
    f, res = _one(f"كتب الباحث في سورة آل عمران: 103 كما نرى جميعا {MID}. وانتهى الكلام.")
    assert f["reference"]["status"] == "matched" and f["wording"]["status"] == "uncertain"    # a right reference does not settle the start
    assert res["stats"]["ref_matched"] == 1 and res["stats"]["matched"] == 0
    # ...and a settled start does not make a missing reference "matched" either
    g, _ = _one(f"{MID}. وانتهى الكلام.")
    assert g["wording"]["status"] == "matched" and g["reference"]["status"] == "missing"


def test_stated_starts_are_not_questioned(use_source, lenient, monkeypatch):
    marked, _ = _one(f"كتب الباحث أن الأمة تحتاج ﴿{MID}﴾ كما نرى.")
    assert marked["wording"]["status"] == "matched" and marked["start_boundary"] is None
    article = f"كتب الباحث أن الأمة تحتاج {MID} وانتهى الكلام."
    manual = run_phrase(article, article.index("نعمت"), article.index(" وانتهى"), 3, 103, 103)["finding"]
    assert manual["wording"]["status"] == "matched" and manual["start_boundary"] is None and manual["end_boundary"] is None
    # a start chosen by the AI is not stated by the writer, so it is held to the same rule
    monkeypatch.setattr(audit, "get_provider", lambda: FakeProvider([RawSuggestion(MID)]))
    (ai,) = run_audit(f"كتب الباحث أن الأمة تحتاج {MID}. وانتهى الكلام.")["findings"]
    assert ai["detected_by"] == ["ai", "phrase"] and ai["wording"]["status"] == "uncertain" and ai["start_boundary"]["status"] == "uncertain"


def test_confirming_the_highlighted_boundaries_turns_uncertain_into_matched(use_source, lenient):
    """The UI's «الحدود صحيحة» button re-sends the same span as a manual highlight with the verse already proposed."""
    article = f"كتب الباحث أن الأمة تحتاج {MID}. وانتهى الكلام."
    (f,) = run_audit(article)["findings"]
    assert f["wording"]["status"] == "uncertain"
    (choice,) = f["choices"]
    done = run_phrase(article, f["start"], f["end"], choice["surah"], choice["ayah_start"], choice["ayah_end"])["finding"]
    assert (done["start"], done["end"]) == (f["start"], f["end"])
    assert done["wording"]["status"] == "matched" and done["detection"]["kind"] == "manual" and done["start_boundary"] is None


def test_phrase_hits_do_not_steal_references_from_marked_quotes(use_source, lenient):
    article = "واعتصموا بحبل الله جميعا ولا تفرقوا ثم قال تعالى ﴿اقرأ باسم ربك الذي خلق﴾ [العلق: 1]"
    res = run_audit(article)
    marked = next(f for f in res["findings"] if f["detection"]["kind"] == "marked")
    assert marked["reference"]["status"] == "matched"


# --- manual selection ---------------------------------------------------------------------------------

def test_manual_short_phrase_needs_a_verse_then_matches(use_source):
    article = "وقال لهم كونوا مع الصابرين دائما"
    start = article.index("مع الصابرين")
    res = run_phrase(article, start, start + len("مع الصابرين"))
    f = res["finding"]
    assert f["needs_choice"] and f["source"] is None and f["changes"] == []
    assert f["detection"]["kind"] == "manual" and len(f["choices"]) >= 2
    picked = next(c for c in f["choices"] if c["label"] == "الأنفال: 46")
    g = run_phrase(article, start, start + len("مع الصابرين"), picked["surah"], picked["ayah_start"], picked["ayah_end"])["finding"]
    assert g["source"]["label"] == "الأنفال: 46" and g["wording"]["status"] == "matched"
    assert g["reference"]["status"] == "missing"  # the editor's choice is never reported as a reference the writer wrote


def test_manual_selection_snaps_to_whole_words_and_keeps_offsets(use_source):
    article = "كتب: اقرأ باسم ربك الذي خلق. وانتهى."
    start = article.index("باسم") + 2  # the editor's selection starts in the middle of a word
    f = run_phrase(article, start, article.index("خلق") + 1)["finding"]
    assert f["quote"] == "باسم ربك الذي خلق" and article[f["start"]:f["end"]] == f["quote"]


@pytest.mark.parametrize("args", [(5, 5), (-1, 3), (0, 10_000), (3, 2)])
def test_manual_selection_rejects_bad_offsets(use_source, args):
    with pytest.raises(InputError):
        run_phrase("اقرأ باسم ربك الذي خلق", *args)


def test_manual_selection_rejects_non_arabic_too_long_and_unknown_verse(use_source):
    with pytest.raises(InputError):
        run_phrase("hello world 123", 0, 5)
    long_text = "كلمة " * 70
    with pytest.raises(InputError):
        run_phrase(long_text, 0, len(long_text))
    with pytest.raises(InputError):
        run_phrase("اقرأ باسم ربك الذي خلق", 0, 10, surah=96, ayah_start=99)


def test_phrase_api(use_source):
    from app.main import app

    client = TestClient(app)
    article = "اقرأ باسم ربك الذي خلق"
    ok = client.post("/api/phrase", json={"article": article, "start": 0, "end": len(article)})
    assert ok.status_code == 200 and ok.headers["cache-control"] == "no-store"
    body = ok.json()
    assert body["finding"]["wording"]["status"] == "matched" and "article" not in body
    assert client.post("/api/phrase", json={"article": article, "start": 4, "end": 4}).status_code == 400
    assert client.post("/api/phrase", json={"article": article, "start": "a", "end": 4}).status_code == 422
    assert client.post("/api/phrase", json={"article": article, "start": 0, "end": 5, "surah": 500}).status_code == 422


def test_phrase_api_reports_unavailable_source(monkeypatch):
    import app.audit as audit_mod
    from app.main import app
    from tests.conftest import FakeSource

    monkeypatch.setattr(audit_mod, "source", FakeSource(error=True))
    res = TestClient(app).post("/api/phrase", json={"article": "اقرأ باسم ربك", "start": 0, "end": 5})
    assert res.status_code == 503


def test_offsets_hold_on_random_articles(use_source, lenient):
    """Fuzz: every finding and every proposed change points at exactly the text it claims; changes never overlap,
    never touch text outside their quotation (reference changes aside), and never attach to an unconfirmed 'maybe'."""
    import random

    rng = random.Random(7)
    prose = "العلم نور والعمل طريق النجاح في الحياة الناس يحتاجون إلى الصبر ومن يجتهد يصل قال رسول الله ﷺ اللهم اغفر لنا".split()
    quran = ["واعتصموا بحبل الله جميعا ولا تفرقوا", "إنما يخشى الله من عباده العلماء", "اقرأ باسم ربك الذي خلق", "إن الله مع الصابرين",
             "وبشر المؤمنين الذين إذا أصابتهم مصيبة قالوا إنا لله وإنا إليه راجعون", "فبأي نعم ربكما تكذبان", "قل هو الله أحد", "ولا تعاونوا على الإثم والعدوان"]
    seps = [" ", " ", "، ", ". ", "\n", " (", ") ", " «", "» ", " ﴿", "﴾ ", " 12 ", " abc ", "‏"]
    for _ in range(250):
        parts = []
        for _ in range(rng.randrange(1, 7)):
            parts.append(rng.choice(quran) if rng.random() < .5 else " ".join(rng.choice(prose) for _ in range(rng.randrange(1, 6))))
            parts.append(rng.choice(seps))
        article = "".join(parts)
        if not article.strip():
            continue
        taken = []
        for f in run_audit(article)["findings"]:
            assert article[f["start"]:f["end"]] == f["quote"]
            if f["detection"]["unconfirmed"]:
                assert f["changes"] == []
            for c in f["changes"]:
                assert article[c["start"]:c["end"]] == c["original"]
                assert not any(c["start"] < e and s < c["end"] for s, e in taken)
                taken.append((c["start"], c["end"]))
                if c["kind"] in ("wording", "diacritics", "vocalize"):
                    assert f["start"] <= c["start"] and c["end"] <= f["end"]


# --- a manual check must not take a reference that belongs to the neighbouring quotation ------------------------------

NEIGHBOUR = "قال تعالى: ﴿فإن مع العسر يسرا﴾ [الشرح: 6]\n\nوتذكّر قول الله تعالى إن الله مع الصابرين."


def test_manual_check_does_not_take_the_reference_of_a_neighbouring_marked_quote(use_source):
    """In a full audit the reference after a marked quotation belongs to it. The manual path used to see only the
    highlighted span, so the phrase two paragraphs later 'owned' «[الشرح: 6]», was reported with a wrong reference and
    got a change that overlaps the neighbour's own reference change."""
    start = NEIGHBOUR.index("إن الله مع الصابرين")
    end = start + len("إن الله مع الصابرين")
    first = run_phrase(NEIGHBOUR, start, end)["finding"]
    assert first["reference"]["status"] == "missing" and first["changes"] == []
    pick = next(c for c in first["choices"] if c["label"] == "الأنفال: 46")
    g = run_phrase(NEIGHBOUR, start, end, pick["surah"], pick["ayah_start"], pick["ayah_end"])["finding"]
    assert g["reference"]["status"] == "missing"
    assert all(c["kind"] != "reference" or c["start"] >= start for c in g["changes"])  # never the neighbour's «[الشرح: 6]»
    assert not any("الشرح" in (c.get("original") or "") for c in g["changes"])


def test_manual_check_with_the_editor_listed_neighbours_does_not_take_their_reference(use_source):
    """Spans of the other findings (for example a short phrase the editor selected earlier, or a quotation only the model
    proposed) are sent by the browser; the server cannot rebuild those, because the search does not report them."""
    article = "والصبر مع الصابرين [الأنفال: 46] وقال لهم كونوا مع الصابرين دائما"
    first = article.index("مع الصابرين")
    other = (first, first + len("مع الصابرين"))
    second = article.index("مع الصابرين", first + 1)
    span = (second, second + len("مع الصابرين"))
    without = run_phrase(article, *span)["finding"]
    with_others = run_phrase(article, *span, others=[other])["finding"]
    assert without["reference"]["status"] != "missing"  # alone, the server has no way to know the neighbour owns it
    assert with_others["reference"]["status"] == "missing"

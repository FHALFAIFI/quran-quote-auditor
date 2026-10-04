"""What the AI may and may not decide.

The model only proposes where a quotation may be. A span that nothing but the model proposed is graded with the same
deterministic rules as an unmarked span found by the phrase search; the model's say-so is never evidence that ordinary
prose is a Quran quotation, and it never raises a tier the search already assigned. Provenance says what the model really
contributed. Offline: the 36-verse fixture, plus the full text when a local copy exists (those tests are skipped otherwise).
"""

import pytest

import app.audit as audit
from app import arabic
from app.audit import run_audit, run_phrase
from app.extraction.base import ExtractionProvider, RawSuggestion
from app.phrases import PhraseScan
from app.quran_source import QuranSource, settings
from tests.conftest import FakeSource


class Proposes(ExtractionProvider):
    name = label = "fake"

    def __init__(self, *quotes):
        self.quotes = quotes

    def available(self):
        return True

    def extract(self, article):
        return [RawSuggestion(q) for q in self.quotes]


def audit_with(monkeypatch, article, *quotes):
    monkeypatch.setattr(audit, "get_provider", lambda: Proposes(*quotes) if quotes else None)
    return run_audit(article)


# ---- ordinary prose proposed by the model (fixture: البقرة 153 is «إن الله مع الصابرين») -----------------------------------

def test_prose_proposed_by_the_model_is_a_possible_quotation_not_an_established_one(use_source, monkeypatch):
    article = "وقال لهم كونوا مع الصابرين دائما."
    res = audit_with(monkeypatch, article, "كونوا مع الصابرين")
    (f,) = res["findings"]
    det = f["detection"]
    assert det["tier"] == "possible" and det["unconfirmed"] and det["ai_role"] == "only"
    assert "ai_only" in det["codes"] and det["label"]  # says why, and says "maybe", not a verdict
    assert f["changes"] == [] and f["correction"]["status"] == "unconfirmed"  # no automatic correction
    assert f["wording"]["status"] == "difference"  # the closest-verse comparison is still shown, as "if it is a quotation"
    assert f["choices"]  # the editor can still say "yes, this is البقرة: 153"
    stats = res["stats"]
    assert stats["possible"] == 1 and stats["matched"] == 0 and stats["proposed_changes"] == 0
    assert res["ai"]["added_only"] == 1 and res["ai"]["also_found"] == 0


@pytest.mark.parametrize("prose", [
    "كونوا مع الصابرين",              # the live finding
    "كونوا مع الصابرين دائما",
    "إن الله مع الصابرين دائما",      # closer to a verse, still ordinary prose around a Quran-like phrase
    "اصبروا على الأذى",               # matches nothing
])
def test_model_proposed_prose_never_gets_changes_or_a_verdict(use_source, monkeypatch, prose):
    res = audit_with(monkeypatch, f"قال المعلم: {prose} يا أبنائي.", prose)
    for f in res["findings"]:
        assert f["detection"]["unconfirmed"], f["quote"]
        assert f["changes"] == []
    assert res["stats"]["proposed_changes"] == 0 and res["stats"]["matched"] == 0


def test_the_editor_can_still_confirm_a_possible_quotation(use_source, monkeypatch):
    """Confirming the verse (the same call the interface makes) is what turns it into proposals."""
    article = "قيل إن الله مع الصابرون هكذا."
    res = audit_with(monkeypatch, article, "إن الله مع الصابرون")
    (f,) = res["findings"]
    assert f["detection"]["unconfirmed"] and f["changes"] == []
    (choice,) = [c for c in f["choices"] if c["surah"] == 2 and c["ayah_start"] == 153]
    out = run_phrase(article, f["start"], f["end"], choice["surah"], choice["ayah_start"], choice["ayah_end"], f["id"])
    changes = [c for c in out["finding"]["changes"] if c["kind"] == "wording"]
    assert out["finding"]["detection"]["kind"] == "manual" and [c["replacement"] for c in changes] == ["الصابرين"]


# ---- genuine short misquotations are still detected -------------------------------------------------------------------------

def test_misquotation_backed_by_the_writers_reference_is_still_reported_and_corrected(use_source, monkeypatch):
    article = "قيل إن الله مع الصابرون [البقرة: 153] هكذا."
    res = audit_with(monkeypatch, article, "إن الله مع الصابرون")
    (f,) = res["findings"]
    assert f["detection"]["tier"] == "stated" and f["detection"]["basis"] == "reference" and not f["detection"]["unconfirmed"]
    assert f["wording"]["status"] == "difference" and f["source"]["label"] == "البقرة: 153"
    assert [c["replacement"] for c in f["changes"] if c["kind"] == "wording"] == ["الصابرين"]
    assert f["detection"]["ai_role"] == "only"  # still the model's discovery: provenance and tier are separate questions


def test_misquotation_after_a_quran_lead_in_is_reported(use_source, monkeypatch):
    res = audit_with(monkeypatch, "قال تعالى إن الله مع الصابرون هكذا.", "إن الله مع الصابرون")
    (f,) = res["findings"]
    assert f["detection"]["tier"] == "stated" and f["detection"]["basis"] == "lead_in"
    assert f["wording"]["status"] == "difference" and f["source"]["label"] == "البقرة: 153"


def test_a_reference_to_another_verse_does_not_back_the_span(use_source, monkeypatch):
    res = audit_with(monkeypatch, "قيل إن الله مع الصابرون [الشرح: 5] هكذا.", "إن الله مع الصابرون")
    (f,) = res["findings"]
    assert f["detection"]["tier"] == "possible" and f["changes"] == []


def test_misquotation_without_support_is_listed_as_possible_with_its_closest_verse(use_source, monkeypatch):
    res = audit_with(monkeypatch, "قيل إن الله مع الصابرون هكذا.", "إن الله مع الصابرون")
    (f,) = res["findings"]
    assert f["detection"]["tier"] == "possible"
    assert f["source"]["label"] == "البقرة: 153" and f["wording"]["diff"]


# ---- marked quotations are untouched; provenance is accurate ----------------------------------------------------------------

def test_marked_quotation_stays_stated_and_the_model_only_agreed(use_source, monkeypatch):
    article = "قال تعالى: ﴿اقرأ باسم ربك الذي خلق﴾ [العلق: 1]"
    res = audit_with(monkeypatch, article, "اقرأ باسم ربك الذي خلق")
    (f,) = res["findings"]
    assert f["detected_by"] == ["marked", "ai", "phrase"]  # three methods found the same span
    assert f["detection"]["tier"] == "stated" and not f["detection"]["unconfirmed"] and f["detection"]["ai_role"] == "also"
    assert res["ai"]["added_only"] == 0 and res["ai"]["also_found"] == 1
    plain = audit_with(monkeypatch, article)
    assert plain["findings"][0]["detection"]["ai_role"] is None
    assert plain["findings"][0]["wording"] == f["wording"] and plain["findings"][0]["changes"] == f["changes"]


def test_model_agreeing_with_the_phrase_search_changes_nothing(use_source, monkeypatch):
    article = "ومن هنا قيل وتعاونوا على البر والتقوى ولا تعاونوا على الإثم والعدوان وهذا أصل."
    quote = "وتعاونوا على البر والتقوى ولا تعاونوا على الإثم والعدوان"
    without, with_ai = audit_with(monkeypatch, article), audit_with(monkeypatch, article, quote)
    a, b = without["findings"][0], with_ai["findings"][0]
    assert a["detected_by"] == ["phrase"] and b["detected_by"] == ["ai", "phrase"] and b["detection"]["ai_role"] == "also"
    for key in ("tier", "unconfirmed", "codes", "label"):
        assert a["detection"][key] == b["detection"][key], key
    assert (a["wording"], a["changes"], a["correction"]) == (b["wording"], b["changes"], b["correction"])
    assert with_ai["ai"]["added_only"] == 0 and with_ai["ai"]["also_found"] == 1


def test_source_outage_never_makes_a_model_proposal_a_quotation(monkeypatch):
    monkeypatch.setattr(audit, "source", FakeSource(error=True))
    res = audit_with(monkeypatch, "وقال لهم كونوا مع الصابرين دائما.", "كونوا مع الصابرين")
    (f,) = res["findings"]
    assert f["detection"]["unconfirmed"] and f["changes"] == [] and f["wording"]["status"] == "uncertain"


# ---- the full text (rarity statistics of the real Quran) ----------------------------------------------------------------------

INDEX = QuranSource(cache_dir=settings.cache_dir)._load_disk()
full = pytest.mark.skipif(INDEX is None, reason="no local copy of the Quranpedia text (run the app once)")


@pytest.fixture
def use_full(monkeypatch):
    monkeypatch.setattr(audit, "source", FakeSource(INDEX))


@full
def test_full_text_model_agreement_never_upgrades_an_approximate_phrase(use_full, monkeypatch):
    """The live finding: with the model on, «وبشر المؤمنين…» (a changed word) was offered two automatic changes."""
    article = "لا تجزع من الأزمات، وفي مواساة المصابين وبشر المؤمنين الذين إذا أصابتهم مصيبة قالوا إنا لله وإنا إليه راجعون رسالة أمل."
    quote = "وبشر المؤمنين الذين إذا أصابتهم مصيبة قالوا إنا لله وإنا إليه راجعون"
    a = audit_with(monkeypatch, article)["findings"][0]
    b = audit_with(monkeypatch, article, quote)["findings"][0]
    assert a["detection"]["tier"] == b["detection"]["tier"] == "possible" and b["detection"]["unconfirmed"]
    assert a["changes"] == b["changes"] == [] and b["detected_by"] == ["ai", "phrase"]


@full
@pytest.mark.parametrize("prose", ["كونوا مع الصابرين", "إن الله مع المتقين دائما", "اصبروا على الأذى"])
def test_full_text_prose_is_not_established(use_full, monkeypatch, prose):
    res = audit_with(monkeypatch, f"وقال لهم {prose} في كل حال.", prose)
    assert res["findings"] and all(f["detection"]["unconfirmed"] and f["changes"] == [] for f in res["findings"])
    assert res["stats"]["matched"] == 0


@full
def test_full_text_prose_the_search_itself_reports_is_the_searchs_finding_not_the_models(use_full, monkeypatch):
    """«لا تحزن إن الله معنا» is five literal words of التوبة: 40, so the phrase search reports it with no model at all.
    A wider model span («… دائما») used to replace that finding with a weaker «possible» one; now it can only sit beside it."""
    article = "وقال لهم لا تحزن إن الله معنا دائما في كل حال."
    (alone,) = audit_with(monkeypatch, article)["findings"]
    (f,) = audit_with(monkeypatch, article, "لا تحزن إن الله معنا دائما")["findings"]
    assert (f["start"], f["end"], f["detection"]["tier"], f["changes"], f["wording"]) == (alone["start"], alone["end"], alone["detection"]["tier"], alone["changes"], alone["wording"])
    assert f["detected_by"] == ["phrase"] and f["detection"]["ai_role"] == "overlap" and f["wording"]["status"] != "matched"


@full
def test_full_text_exact_phrase_the_search_missed_is_graded_like_the_search_grades(use_full, monkeypatch):
    """Simulate a source search that found nothing: the span only the model proposed gets the search's own tier.

    (Since 4 Oct 2026 the source search also includes the retrieval anchored on the writer's cues, which would find the
    announced quotation below by itself; it is switched off here too so that the model-only grading is what is tested.)"""
    monkeypatch.setattr(audit, "find_phrases", lambda article, tokens, index: PhraseScan([]))
    monkeypatch.setattr(audit, "find_cue_hits", lambda article, tokens, refs, index: [])
    distinct = audit_with(monkeypatch, "ثم ذكر الكاتب ادعوا ربكم تضرعا وخفية ثم أكمل.", "ادعوا ربكم تضرعا وخفية")["findings"][0]
    assert distinct["detection"]["tier"] == "candidate" and not distinct["detection"]["unconfirmed"]
    assert distinct["detected_by"] == ["ai"] and distinct["detection"]["ai_role"] == "only"
    announced = audit_with(monkeypatch, "والله يقول ادعوا ربكم تضرعا وخفية. ثم نتأمل.", "ادعوا ربكم تضرعا وخفية")["findings"][0]
    assert announced["detection"]["tier"] == "stated" and announced["detection"]["basis"] == "lead_in"  # the writer announced a verse
    common = audit_with(monkeypatch, "يعيش الناس في كثير من المدن الكبيرة.", "في كثير من المدن")
    assert all(f["detection"]["unconfirmed"] for f in common["findings"])
    formula = audit_with(monkeypatch, "ونبدأ كل عمل بقول بسم الله الرحمن الرحيم ثم نمضي.", "بسم الله الرحمن الرحيم")["findings"][0]
    assert formula["detection"]["unconfirmed"] and "common" in formula["detection"]["codes"]


@full
def test_full_text_model_proposed_misquotation_with_reference_is_still_corrected(use_full, monkeypatch):
    article = "وفي ذلك يقول ربنا وافعلوا الشر لعلكم تفلحون (الحج: 77) فلنتدبر."
    res = audit_with(monkeypatch, article, "وافعلوا الشر لعلكم تفلحون")
    (f,) = res["findings"]
    assert f["detection"]["tier"] == "stated" and f["detection"]["basis"] == "reference"
    assert [(c["original"], c["replacement"]) for c in f["changes"] if c["kind"] == "wording"] == [("الشر", "الخير")]
    assert arabic.folded(f["source"]["matched_text"]).startswith("وافعلوا الخير")

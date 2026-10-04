"""A model proposal that overlaps a finding the program made can never replace, shrink, widen, downgrade or drop it.

What a marker, the writer's own selection or a literal phrase match established stays exactly as it would be without the
model; the model's overlapping span is kept beside it as evidence (``detection.ai_spans``). Offline: the 36-verse fixture
and a fake provider, no network and no Groq call.
"""

import pytest

import app.audit as audit
from app import arabic
from app.audit import merge
from app.extraction.base import Candidate
from tests.test_ai_tiers import audit_with

GOOD = "وتعاونوا على البر والتقوى ولا تعاونوا على الإثم والعدوان"   # المائدة: 2, correct
BAD = "وتعاونوا على البر والتقوى ولا تعاونوا على الشر والعدوان"    # the same verse with one wrong word
LEAD, TAIL = "ومن هنا قيل", "وهذا أصل."

# model spans that overlap the quotation without being the same span (relative to the sentence built below)
WIDER = "ومن هنا قيل {q} وهذا"
NARROWER = "على البر والتقوى ولا"
SHIFTED = "قيل وتعاونوا على البر"
OVERLAPS = {"wider": WIDER, "narrower": NARROWER, "shifted": SHIFTED}


def words(text):
    return [t.fold for t in arabic.tokenize(text)]


def article_of(quote):
    return f"{LEAD} {quote} {TAIL}"


def verdict(f):
    """Everything the source-based audit decided about a finding (not who proposed what)."""
    d = f["detection"]
    return {
        "span": (f["start"], f["end"], f["quote"]), "source": f["source"], "wording": f["wording"], "reference": f["reference"],
        "changes": f["changes"], "correction": f["correction"], "needs_review": f["needs_review"], "review_reasons": f["review_reasons"],
        "boundaries": (f["start_boundary"], f["end_boundary"], f["lead_in"], f["continuation"]),
        "detection": (d["kind"], d["tier"], d["codes"], d["label"], d["unconfirmed"], d["reasons"]),
    }


# ---- unmarked phrase found by the search: a correct quotation and a misquotation --------------------------------------------

@pytest.mark.parametrize("quote", [GOOD, BAD], ids=["correct", "misquote"])
@pytest.mark.parametrize("relation", sorted(OVERLAPS))
def test_overlapping_model_span_leaves_the_phrase_finding_exactly_as_without_the_model(use_source, monkeypatch, quote, relation):
    article = article_of(quote)
    model_span = OVERLAPS[relation].format(q=quote)
    (alone,) = audit_with(monkeypatch, article)["findings"]
    res = audit_with(monkeypatch, article, model_span)
    (f,) = res["findings"]                                   # not replaced, not duplicated
    assert alone["detection"]["tier"] == "candidate" and alone["changes"]  # it is a real finding with something to offer
    assert verdict(f) == verdict(alone)
    assert f["detected_by"] == ["phrase"]                    # the model did not "find" this finding
    det = f["detection"]
    assert det["ai_role"] == "overlap"
    (kept,) = det["ai_spans"]                                # ... but its proposal is preserved as evidence
    assert kept["quote"] == model_span and kept["relation"] == relation
    assert article[kept["start"]:kept["end"]] == model_span
    assert res["ai"]["overlapped"] == 1 and res["ai"]["added_only"] == 0 and res["ai"]["also_found"] == 0


def test_the_models_own_proposal_never_outranks_the_search_even_when_listed_first(use_source, monkeypatch):
    """Order of the candidates must not matter: the search's finding wins whether or not the model's span is longer."""
    article = article_of(GOOD)
    (alone,) = audit_with(monkeypatch, article)["findings"]
    for model_span in (WIDER.format(q=GOOD), article.rstrip(".")):  # even a span covering almost the whole article
        (f,) = audit_with(monkeypatch, article, model_span)["findings"]
        assert verdict(f) == verdict(alone)


def test_correct_quotation_keeps_its_tier_and_changes_when_the_model_proposes_a_wider_span(use_source, monkeypatch):
    """The failure this prevents: a wider model span used to turn a candidate with an automatic change into «possible»."""
    article = article_of(GOOD)
    (f,) = audit_with(monkeypatch, article, WIDER.format(q=GOOD))["findings"]
    assert f["detection"]["tier"] == "candidate" and not f["detection"]["unconfirmed"]
    assert f["source"]["label"] == "المائدة: 2" and [c["kind"] for c in f["changes"]] == ["vocalize"]
    assert f["correction"]["status"] != "unconfirmed"


def test_misquotation_next_to_the_search_hit_is_still_surfaced_by_the_source_not_by_the_model(use_source, monkeypatch):
    """The search hit stops before the wrong word; the audit shows the verse's word beside the article's, whatever the model says."""
    article = article_of(BAD)
    (f,) = audit_with(monkeypatch, article, BAD)["findings"]  # the model proposes the whole misquotation
    assert f["detection"]["tier"] == "candidate" and f["detected_by"] == ["phrase"]
    assert f["continuation"] and f["continuation"]["article"] == "الشر" and f["continuation"]["quran"] == "الإثم"
    assert f["wording"]["status"] == "uncertain"            # the boundary is not settled; never "matched"
    assert f["detection"]["ai_spans"][0]["relation"] == "wider"
    assert f["quote"] == "وتعاونوا على البر والتقوى ولا تعاونوا على"  # the model's wider span did not replace it


def test_the_same_span_still_only_adds_agreement(use_source, monkeypatch):
    article = article_of(GOOD)
    (alone,) = audit_with(monkeypatch, article)["findings"]
    res = audit_with(monkeypatch, article, GOOD)
    (f,) = res["findings"]
    assert verdict(f) == verdict(alone) and f["detected_by"] == ["ai", "phrase"]
    assert f["detection"]["ai_role"] == "also" and "ai_spans" not in f["detection"]
    assert res["ai"]["also_found"] == 1 and res["ai"]["overlapped"] == 0


# ---- marked quotation and the writer's own selection ------------------------------------------------------------------------

@pytest.mark.parametrize("model_span", ["قال تعالى اقرأ باسم ربك الذي خلق", "اقرأ باسم ربك", "ربك الذي خلق [العلق"], ids=["wider", "narrower", "shifted"])
def test_overlapping_model_span_leaves_a_marked_quotation_alone(use_source, monkeypatch, model_span):
    article = "قال تعالى: ﴿اقرأ باسم ربك الذي خلق﴾ [العلق: 1] ثم نقول"
    (alone,) = audit_with(monkeypatch, article)["findings"]
    (f,) = audit_with(monkeypatch, article, model_span)["findings"]
    assert verdict(f) == verdict(alone) and f["detected_by"] == ["marked", "phrase"]
    assert f["detection"]["ai_role"] == "overlap" and words(f["detection"]["ai_spans"][0]["quote"]) == words(model_span)


@pytest.mark.parametrize("model_span", ["قال تعالى ﴿وتعاونوا على البر والتقوى ولا تعاونوا على الشر والعدوان", "على البر والتقوى ولا"], ids=["wider", "narrower"])
def test_marked_misquotation_keeps_its_source_based_correction(use_source, monkeypatch, model_span):
    article = f"قال تعالى: ﴿{BAD}﴾ [المائدة: 2] ثم نقول"
    (alone,) = audit_with(monkeypatch, article)["findings"]
    (f,) = audit_with(monkeypatch, article, model_span)["findings"]
    assert verdict(f) == verdict(alone)
    assert f["wording"]["status"] == "difference"
    assert [(c["original"], c["replacement"]) for c in f["changes"] if c["kind"] == "wording"] == [("الشر", "الإثم")]


# ---- the model still works where nothing deterministic is -------------------------------------------------------------------

def test_a_model_span_apart_from_the_search_hit_is_still_its_own_finding(use_source, monkeypatch):
    article = f"قال المعلم كونوا مع الصابرين دائما. {article_of(GOOD)}"
    res = audit_with(monkeypatch, article, "كونوا مع الصابرين")
    by_role = {f["detection"]["ai_role"]: f for f in res["findings"]}
    assert set(by_role) == {"only", None}                    # the search hit is untouched, the prose is the model's possible finding
    assert by_role[None]["detection"]["tier"] == "candidate" and by_role["only"]["detection"]["unconfirmed"]
    assert res["ai"]["added_only"] == 1 and res["ai"]["overlapped"] == 0


def test_a_model_span_overlapping_the_search_hit_adds_no_second_finding_for_the_rest_of_its_words(use_source, monkeypatch):
    article = f"قال المعلم كونوا مع الصابرين دائما. {article_of(GOOD)}"
    wide = f"كونوا مع الصابرين دائما. {LEAD} {GOOD}"
    res = audit_with(monkeypatch, article, wide)
    assert [f["detected_by"] for f in res["findings"]] == [["phrase"]]


# ---- merge itself -----------------------------------------------------------------------------------------------------------

def cand(start, end, src):
    return Candidate(start, end, "x" * (end - start), {src})


@pytest.mark.parametrize("order", [0, 1, 2])
def test_merge_keeps_the_deterministic_span_whatever_the_order_of_the_inputs(order):
    base = [cand(10, 40, "phrase"), cand(0, 60, "ai"), cand(5, 20, "ai")]
    base = base[order:] + base[:order]
    (k,) = merge(base)
    assert (k.start, k.end, k.sources) == (10, 40, {"phrase"})
    assert sorted((s["start"], s["end"], s["relation"]) for s in k.ai_spans) == [(0, 60, "wider"), (5, 20, "shifted")]


def test_merge_attaches_one_model_span_to_every_deterministic_span_it_overlaps():
    a, b = cand(0, 10, "phrase"), cand(12, 22, "marked")
    kept = merge([cand(5, 18, "ai"), b, a])
    assert [(k.start, k.end) for k in kept] == [(0, 10), (12, 22)]
    assert all(len(k.ai_spans) == 1 and k.ai_spans[0]["relation"] == "shifted" for k in kept)


def test_merge_still_dedups_the_same_span_and_two_model_spans_for_one_place():
    kept = merge([cand(0, 10, "ai"), cand(0, 10, "phrase")])
    assert len(kept) == 1 and kept[0].sources == {"ai", "phrase"} and kept[0].ai_spans == []
    kept = merge([cand(0, 10, "ai"), cand(2, 12, "ai"), cand(30, 40, "ai")])
    assert [(k.start, k.end) for k in kept] == [(0, 10), (30, 40)] and kept[0].ai_spans == []


def test_marked_still_outranks_the_phrase_search():
    (k,) = merge([cand(0, 10, "phrase"), cand(2, 8, "marked")])
    assert k.sources == {"marked", "phrase"} and (k.start, k.end) == (2, 8)


def test_detected_by_order_is_unchanged(use_source, monkeypatch):
    article = article_of(GOOD)
    assert audit_with(monkeypatch, article, GOOD)["findings"][0]["detected_by"] == ["ai", "phrase"]
    # the listing order of the earlier methods is unchanged; the writer-cue retrieval (4 Oct 2026) is listed last
    assert audit.PRIORITY == {"manual": 0, "marked": 0, "ai": 1, "phrase": 2, "cue": 3}

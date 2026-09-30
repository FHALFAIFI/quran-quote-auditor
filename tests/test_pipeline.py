"""Pipeline tests: extraction safety, fallbacks and the HTTP API (all offline)."""

import pytest
from fastapi.testclient import TestClient

import app.audit as audit
from app.audit import InputError, run_audit
from app.extraction.base import ExtractionError, ExtractionProvider, RawSuggestion
from app.extraction.gemini import parse_model_json
from app.extraction.marked import extract_marked
from app.references import find_references


class FakeProvider(ExtractionProvider):
    name = "fake"
    label = "fake"

    def __init__(self, suggestions=None, error=None):
        self.suggestions, self.error = suggestions or [], error

    def available(self):
        return True

    def extract(self, article):
        if self.error:
            raise self.error
        return self.suggestions


def test_ai_suggestions_must_occur_in_article(use_source, monkeypatch):
    article = "قال تعالى وتعاونوا على البر والتقوى في كتابه."
    provider = FakeProvider([
        RawSuggestion("وتعاونوا على البر والتقوى"),
        RawSuggestion("إن الله مع الصابرين"),  # hallucinated: not in the article
    ])
    monkeypatch.setattr(audit, "get_provider", lambda: provider)
    res = run_audit(article)
    assert res["mode"] == "ai"
    assert len(res["findings"]) == 1
    f = res["findings"][0]
    assert f["quote"] == "وتعاونوا على البر والتقوى"
    assert article[f["start"]:f["end"]] == f["quote"]
    assert "ai" in f["detected_by"]
    assert any("استُبعد 1" in n["text"] for n in res["notices"])


def test_ai_quote_located_despite_diacritics(use_source, monkeypatch):
    article = "وقال: وَتَعَاوَنُوا عَلَى الْبِرِّ وَالتَّقْوَى."
    monkeypatch.setattr(audit, "get_provider", lambda: FakeProvider([RawSuggestion("وتعاونوا على البر والتقوى")]))
    res = run_audit(article)
    assert res["findings"][0]["quote"] == "وَتَعَاوَنُوا عَلَى الْبِرِّ وَالتَّقْوَى"


def test_ai_failure_falls_back_to_marked(use_source, monkeypatch):
    monkeypatch.setattr(audit, "get_provider", lambda: FakeProvider(error=ExtractionError("انتهت المهلة")))
    res = run_audit("قال تعالى: ﴿اقرأ باسم ربك الذي خلق﴾ [العلق: 1]")
    assert res["mode"] == "ai_failed"
    assert res["findings"][0]["wording"]["status"] == "matched"
    assert any(n["level"] == "warning" for n in res["notices"])


def test_reduced_mode_without_provider(use_source):
    res = run_audit("قال تعالى: ﴿اقرأ باسم ربك الذي خلق﴾ [العلق: 1]")
    assert res["mode"] == "reduced" and res["provider"] is None
    f = res["findings"][0]
    assert f["detected_by"][0] == "marked"
    assert f["reference"]["status"] == "matched"


def test_source_outage_gives_no_verdicts(monkeypatch):
    from tests.conftest import FakeSource

    monkeypatch.setattr(audit, "source", FakeSource(error=True))
    monkeypatch.setattr(audit, "get_provider", lambda: None)
    res = run_audit("﴿اقرأ باسم ربك الذي خلق﴾ [العلق: 1]")
    assert res["source"]["available"] is False
    f = res["findings"][0]
    assert f["wording"]["status"] == "uncertain"
    assert f["source"] is None
    assert f["reference"]["status"] == "uncertain"
    assert f["needs_review"]
    assert res["stats"]["matched"] == 0


def test_input_limits(use_source):
    with pytest.raises(InputError):
        run_audit("   ")
    with pytest.raises(InputError):
        run_audit("ا" * 7000)


def test_ornate_brackets_pair_in_order():
    article = "﴿اقرأ باسم ربك﴾ [العلق: 1] ثم ﴿الذي خلق﴾ وأيضًا ﴾إن الله مع الصابرين﴿"
    cands = extract_marked(article, find_references(article))
    assert [c.text for c in cands] == ["اقرأ باسم ربك", "الذي خلق", "إن الله مع الصابرين"]


def test_quotes_need_cue_or_reference():
    a = "كتب المؤلف «هذا كلام عادي جدا» في مقدمته."
    assert extract_marked(a, find_references(a)) == []
    b = "قال تعالى: «إن الله مع الصابرين»"
    assert len(extract_marked(b, find_references(b))) == 1


def test_reference_attached_to_nearest_quote(use_source):
    res = run_audit("﴿فإن مع العسر يسرا﴾ [الشرح: 5] ﴿إن مع العسر يسرا﴾ [الشرح: 6]")
    refs = [f["reference"]["found"]["label"] for f in res["findings"]]
    assert refs == ["الشرح: 5", "الشرح: 6"]
    assert all(f["reference"]["status"] == "matched" for f in res["findings"])


def test_unmarked_exact_run_is_found_by_phrase_search(use_source):
    res = run_audit("ومن هنا قيل وتعاونوا على البر والتقوى ولا تعاونوا على الإثم والعدوان وهذا أصل.")
    assert res["findings"][0]["detected_by"] == ["phrase"]
    assert res["findings"][0]["source"]["label"] == "المائدة: 2"


@pytest.mark.parametrize("raw", ["not json", "{\"foo\": 1}", "[1, 2]", ""])
def test_malformed_model_output(raw):
    if raw == "[1, 2]":
        assert parse_model_json(raw, 10) == []  # list of non-objects: ignored, not trusted
        return
    with pytest.raises(ExtractionError):
        parse_model_json(raw, 10)


def test_model_output_fences_and_limits():
    raw = '```json\n{"candidates": [{"quote": "اقرأ باسم ربك", "reference_text": "العلق: 1"}, {"quote": ""}, {"quote": 5}, {"quote": "الذي خلق"}]}\n```'
    out = parse_model_json(raw, 10)
    assert [s.quote for s in out] == ["اقرأ باسم ربك", "الذي خلق"]
    assert out[0].reference_text == "العلق: 1"
    assert len(parse_model_json(raw, 1)) == 1


def test_api_escaping_and_errors(use_source):
    from app.main import app

    client = TestClient(app)
    health = client.get("/api/health").json()
    assert health["mode"] == "reduced"
    res = client.post("/api/audit", json={"article": "<script>alert(1)</script> ﴿اقرأ باسم ربك الذي خلق﴾"})
    assert res.status_code == 200
    assert res.headers["cache-control"] == "no-store"
    assert "script-src 'self'" in res.headers["content-security-policy"]
    body = res.json()
    assert "article" not in body  # the article is not echoed back
    assert body["findings"][0]["quote"] == "اقرأ باسم ربك الذي خلق"
    assert client.post("/api/audit", json={"article": ""}).status_code == 400
    assert client.post("/api/audit", json={"text": "x"}).status_code == 422
    assert client.get("/").status_code == 200

"""Audit behaviour added for the writing workspace: the model is optional per audit, a long article is audited without it and says so,
and no passage is dropped silently when there are more than the cap. Offline (36-verse fixture, fake provider)."""

import dataclasses

import app.audit as audit
from app.audit import run_audit
from app.config import settings
from tests.test_ai_tiers import Proposes

ARTICLE = "قال تعالى: ﴿وتعاونوا على البر والتقوى﴾ [المائدة: 2]."


def with_provider(monkeypatch, provider):
    monkeypatch.setattr(audit, "get_provider", lambda: provider)


def test_the_writer_can_switch_the_model_off_for_one_audit(use_source, monkeypatch):
    calls = []

    class Spy(Proposes):
        def extract(self, article):
            calls.append(article)
            return super().extract(article)

    with_provider(monkeypatch, Spy("وتعاونوا على البر والتقوى"))
    res = run_audit(ARTICLE, use_ai=False)
    assert calls == [] and res["mode"] == "reduced"
    assert res["ai"]["configured"] is True and res["ai"]["responded"] is False and res["ai"]["outcome"] == "skipped_writer"
    assert [f["quote"] for f in res["findings"]] == ["وتعاونوا على البر والتقوى"]      # the marked quotation is audited as ever
    res_on = run_audit(ARTICLE)
    assert len(calls) == 1 and res_on["mode"] == "ai"


def test_an_article_longer_than_the_model_limit_is_audited_without_the_model_and_says_so(use_source, monkeypatch):
    calls = []

    class Spy(Proposes):
        def extract(self, article):
            calls.append(article)
            return []

    with_provider(monkeypatch, Spy())
    monkeypatch.setattr(audit, "settings", dataclasses.replace(settings, ai_max_chars=60))
    res = run_audit(ARTICLE + " " + "نص عادي " * 20)
    assert calls == [] and res["ai"]["outcome"] == "skipped_length" and res["mode"] == "reduced"
    assert any("أطول من 60" in n["text"] for n in res["notices"])
    assert [f["quote"] for f in res["findings"]] == ["وتعاونوا على البر والتقوى"]


def test_the_article_limit_is_the_configured_limit(use_source):
    assert settings.max_chars >= 20000


def test_passages_beyond_the_cap_are_reported_not_dropped_silently(use_source, monkeypatch):
    monkeypatch.setattr(audit, "settings", dataclasses.replace(settings, max_candidates=3))
    article = "\n".join(f"قال تعالى: ﴿وتعاونوا على البر والتقوى﴾ [المائدة: 2] الفقرة {i}." for i in range(6))
    res = run_audit(article)
    assert len(res["findings"]) == 3 and res["candidates_capped"] == 3
    note = [n for n in res["notices"] if "لم يُفحص 3" in n["text"]]
    assert note and note[0]["level"] == "warning" and "حتى السطر 3" in note[0]["text"] and "وُجد 6" in note[0]["text"]
    assert run_audit(ARTICLE)["candidates_capped"] == 0

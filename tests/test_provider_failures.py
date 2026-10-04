"""Provider test harness (roadmap §1.4): every model failure against a recorded FAKE Groq (tests/fake_groq.py, no network).

Everything here is SIMULATED: no Groq or Gemini call is made, no real key is used, and nothing is shown about how well a real
model finds quotations. For each scenario an audit of the same realistic article (tests/fake_groq.ARTICLE: a bracketed quotation
with its reference, one with a wrong reference, an unmarked distinctive misquotation, a short common phrase) goes through the
real FastAPI app (TestClient) with the offline 36-verse fixture, and the test asserts:

(a) the source-based audit is complete and unchanged: findings (ids, spans, wording and reference verdicts, tiers, changes),
    stats, phrase counts and source block are exactly those of the same article audited with AI_PROVIDER=none;
(b) ``mode`` / ``ai.outcome`` / the notices are exactly the calm, accurate state for what happened;
(c) one HTTP request per audit; a second audit inside the cooldown makes ZERO requests and says so (``skipped_cooldown``,
    no HTTP status of the earlier call, the seconds left) instead of reporting a failure it did not have;
(d) once the cooldown has run out (the cooldown clock is moved forward), exactly one request is made again;
(e) many rapid audits during a 429 cooldown, sequential or concurrent, make no request beyond the first;
(f) /api/health never contains the article, the API key, or any text of the provider's error body;
(g) log records at DEBUG (app, httpx, httpcore, uvicorn, starlette, fastapi) contain none of them either, the unhandled
    error path included, and a real uvicorn server writes no traceback that could quote the article;
(h) the audit answer itself. Decision (4 Oct): the per-audit ``ai.error_body`` keeps only the provider's ``type``, ``code``,
    ``param`` and ``message`` (account ids such as ``org_…`` and key-shaped strings redacted). Groq's ``failed_generation``
    is NOT returned, even to the writer who sent the article: it is model-generated text, so beside passages of that article
    it can hold text that is not in it (an invented or paraphrased verse, prompt fragments), and the app never shows model
    text as Quran text. Only its length (``failed_generation_chars``) is kept, for diagnosis. The body goes back only to the
    requester; it is never logged and never in /api/health (the public call status holds no body).
"""

from __future__ import annotations

import dataclasses
import json
import logging
import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest
from fastapi.testclient import TestClient

import app.audit as audit
import app.main as main
from app.extraction import base, gemini, groq, status
from tests import fake_groq as fg

LOGGERS = ("", "auditor", "app", "httpx", "httpcore", "uvicorn", "uvicorn.error", "uvicorn.access", "starlette", "fastapi")
COOLDOWN_NOTICE = ("لم يُسأل الذكاء الاصطناعي في هذا التدقيق لأن استدعاءً سابقًا له تعذّر قبل قليل، ويُسأل من جديد بعد نحو {n} ث؛ "
                   "فُحص المقال كاملًا بالعلامات وبالبحث في نص المصحف.")
DISCARDED_2 = "استُبعد مقطعان اقترحه نموذج الذكاء الاصطناعي لأنه غير موجود حرفيًا في المقال."


@dataclasses.dataclass
class Expect:
    outcome: str                 # ai.outcome of the first audit
    http: int | None             # ai.http_status of the first audit (this call's, never an earlier one)
    detail: str | None           # what /api/health's ai_last_call.detail says
    error: str | None            # a fragment of ai.error (the calm Arabic reason shown behind «تفاصيل هذا التدقيق»)
    cooldown: float              # seconds the next audits skip the model (0: no cooldown)
    body: bool = False           # ai.error_body holds the provider's (shortened, redacted) error object
    generation_failure: bool = False
    proposed: int = 0
    discarded: int = 0


AI_COOLDOWN = groq.settings.ai_cooldown
QUOTA = max(AI_COOLDOWN, 120)
EXPECT = {
    "429_rate_limit_rpm": Expect("failed", 429, "429", "الحصة", QUOTA, body=True),
    "429_rate_limit_rpd": Expect("failed", 429, "429", "الحصة", max(QUOTA, 864), body=True),   # Groq's retry-after honoured
    "429_request_too_large": Expect("failed", 429, "429", "الحصة", QUOTA, body=True),
    "timeout": Expect("failed", None, "timeout", "انتهت مهلة", AI_COOLDOWN),
    "connect_error": Expect("failed", None, "connection", "تعذّر الاتصال", AI_COOLDOWN),
    "500": Expect("failed", 500, "500", "(500)", AI_COOLDOWN, body=True),
    "502": Expect("failed", 502, "502", "(502)", AI_COOLDOWN, body=True),
    "503": Expect("failed", 503, "503", "(503)", AI_COOLDOWN, body=True),
    "401": Expect("failed", 401, "401", "مرفوض", max(AI_COOLDOWN, 300), body=True),
    "malformed_json": Expect("failed", 200, "malformed_json", "ليست JSON صالحًا", AI_COOLDOWN),
    "truncated": Expect("failed", 200, "truncated", "مقطوعة", AI_COOLDOWN),
    "empty_choices": Expect("failed", 200, "empty_or_blocked", "غير مكتملة", AI_COOLDOWN),
    "content_null": Expect("failed", 200, "empty_or_blocked", "غير مكتملة", AI_COOLDOWN),
    "content_empty": Expect("failed", 200, "malformed_json", "ليست JSON صالحًا", AI_COOLDOWN),
    "400_json_validate_failed": Expect("failed", 400, "400", "أعادت الخطأ 400", AI_COOLDOWN, body=True, generation_failure=True),
    "unexpected_client_error": Expect("failed", None, "error", "تعذّر الاتصال", AI_COOLDOWN),
    "200_answered_nothing": Expect("ok", 200, None, None, 0),
    "200_spans_not_in_article": Expect("ok", 200, None, None, 0, proposed=2, discarded=2),
}
assert set(EXPECT) == set(fg.GROQ_ANSWERS)


class Harness:
    def __init__(self, monkeypatch, caplog, module=groq, selection="groq", key_env="GROQ_API_KEY"):
        self.monkeypatch, self.caplog, self.module = monkeypatch, caplog, module
        self.clock = fg.Clock()
        monkeypatch.setattr(status, "time", self.clock)
        monkeypatch.setattr(audit, "get_provider", base.get_provider)    # the real selection, not the conftest stub
        for k in ("GROQ_API_KEY", "GEMINI_API_KEY"):
            monkeypatch.delenv(k, raising=False)
        monkeypatch.setenv(key_env, fg.KEY)
        self.select(selection)
        self.client = TestClient(main.app, raise_server_exceptions=False)
        for name in LOGGERS:
            caplog.set_level(logging.DEBUG, logger=name)

    def select(self, name):
        self.monkeypatch.setattr(base, "settings", dataclasses.replace(base.settings, ai_provider=name))

    def fake(self, answer):
        return fg.FakeProvider(answer).install(self.monkeypatch, self.module)

    def audit(self, article=fg.ARTICLE):
        main._hits.clear()  # the per-address limiter (10/min) is not under test here
        r = self.client.post("/api/audit", json={"article": article})
        assert r.status_code == 200, r.text
        return r.json()

    def health(self):
        r = self.client.get("/api/health")
        assert r.status_code == 200
        return r.text, r.json()

    def baseline(self):
        """The same article with AI_PROVIDER=none (what the source-based audit decides on its own)."""
        self.select("none")
        try:
            res = self.audit()
        finally:
            self.select("groq" if self.module is groq else "gemini")
        assert res["mode"] == "reduced" and res["ai"]["outcome"] == "not_configured"
        return res

    def log_text(self):
        fmt = logging.Formatter()
        parts = [self.caplog.text]
        for rec in self.caplog.records:
            parts.append(rec.getMessage())
            if rec.exc_info:
                parts.append(fmt.formatException(rec.exc_info))
            if rec.stack_info:
                parts.append(rec.stack_info)
        return "\n".join(parts)


def private_strings(extra=()):
    """What must never reach /api/health or a log: the writer's text, the key, the provider's error body and account id."""
    return [fg.KEY, fg.ORG, fg.FG_MARK, fg.INVENTED, *fg.PROSE, *fg.ARTICLE.splitlines(), *extra]


def leaked(text, strings):
    return [s for s in strings if s and s in text]


def reset_trackers():
    for t in (groq._tracker, gemini._tracker):
        t.clear_cooldown()
        t.last.update(outcome="never_called", at=None, model=None, detail=None, http_status=None, elapsed_ms=None)


@pytest.fixture(autouse=True)
def _reset():
    reset_trackers()
    main._hits.clear()
    yield
    reset_trackers()


@pytest.fixture
def harness(use_source, monkeypatch, caplog):
    return Harness(monkeypatch, caplog)


def source_audit(res):
    """Everything the source-based audit decided; must not depend on what the model did."""
    return {k: res[k] for k in ("findings", "stats", "phrases", "candidates_capped", "source")}


def model_notices(res, base_res):
    base_texts = [n["text"] for n in base_res["notices"]]
    extra = [n for n in res["notices"] if n["text"] not in base_texts]
    assert [n for n in res["notices"] if n not in extra] == base_res["notices"]  # the source's own notices, unchanged and in order
    return extra


# ---------------------------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("scenario", list(EXPECT))
def test_every_provider_answer_ends_in_the_complete_source_audit(harness, scenario):
    exp = EXPECT[scenario]
    answer, body_strings = fg.GROQ_ANSWERS[scenario]
    base_res = harness.baseline()
    assert len(base_res["findings"]) == 3 and base_res["stats"]["proposed_changes"] > 0  # a real audit with work in it
    fake = harness.fake(answer)
    private = private_strings(body_strings)

    # ---- first audit: one request, the full source audit, an accurate model state
    res = harness.audit()
    assert len(fake.requests) == 1
    sent = fake.requests[0]
    assert sent["headers"]["authorization"] == f"Bearer {fg.KEY}"           # the sentinel key really was in play
    assert fg.PROSE[1] in sent["json"]["messages"][1]["content"]           # and so was the article
    assert source_audit(res) == source_audit(base_res)                      # (a)
    ai = res["ai"]
    assert ai["configured"] is True and ai["provider"] == "groq" and ai["http_status"] == exp.http
    assert ai["added_only"] == ai["also_found"] == ai["overlapped"] == 0 and ai["located"] == 0 and ai["cooldown_seconds"] is None
    assert all("ai" not in f["detected_by"] and f["detection"]["ai_role"] is None for f in res["findings"])
    extra = model_notices(res, base_res)
    if exp.outcome == "failed":                                             # (b)
        assert res["mode"] == "ai_failed" and ai["outcome"] == "failed" and ai["responded"] is False
        assert ai["proposed"] == 0 and ai["discarded"] == 0 and exp.error in ai["error"]
        assert ai["generation_failure"] is exp.generation_failure
        assert extra == [{"level": "warning", "text": audit.MODEL_FAILED_NOTICE}]
    else:
        assert res["mode"] == "ai" and ai["outcome"] == "ok" and ai["responded"] is True and ai["error"] is None
        assert ai["proposed"] == exp.proposed and ai["discarded"] == exp.discarded
        assert extra == ([{"level": "info", "text": DISCARDED_2}] if exp.discarded else [])

    # ---- (h) the audit answer: the provider's body only as type/code/message, never failed_generation, account ids or the key
    answer_text = json.dumps(res, ensure_ascii=False)
    assert leaked(answer_text, [fg.KEY, fg.ORG, fg.FG_MARK, fg.INVENTED, "unexpected failure while sending"]) == []
    if exp.body:
        eb = ai["error_body"]
        assert eb and "failed_generation" not in eb and set(eb) <= {"type", "code", "param", "message", "raw", "failed_generation_chars"}
        assert ("failed_generation_chars" in eb) is (scenario == "400_json_validate_failed")
    else:
        assert ai["error_body"] is None

    # ---- (f) health right after: the real outcome, the cooldown, nothing private
    h_text, h = harness.health()
    last = h["ai_last_call"]
    assert last["outcome"] == exp.outcome and last["http_status"] == exp.http and last["detail"] == exp.detail
    assert (exp.cooldown - 2) <= last["cooldown_seconds"] <= exp.cooldown if exp.cooldown else last["cooldown_seconds"] == 0
    assert leaked(h_text, private) == []

    # ---- (c) second audit
    res2 = harness.audit()
    assert source_audit(res2) == source_audit(base_res)
    if exp.cooldown:
        assert len(fake.requests) == 1                                       # zero requests inside the cooldown
        ai2 = res2["ai"]
        assert res2["mode"] == "reduced" and ai2["outcome"] == "skipped_cooldown" and ai2["responded"] is False
        assert ai2["http_status"] is None and ai2["error"] is None and ai2["error_body"] is None and ai2["elapsed_ms"] is None
        assert 0 < ai2["cooldown_seconds"] <= exp.cooldown and res2["provider"] is None
        assert model_notices(res2, base_res) == [{"level": "info", "text": COOLDOWN_NOTICE.format(n=ai2["cooldown_seconds"])}]
        assert not any("تعذّر الاستخراج" in n["text"] for n in res2["notices"])   # it does not claim this audit failed
        assert harness.health()[1]["ai_last_call"]["http_status"] == exp.http      # health still names the call that failed
        # ---- (d) after the cooldown, exactly one request again
        harness.clock.offset += exp.cooldown + 1
        res3 = harness.audit()
        assert len(fake.requests) == 2 and res3["ai"]["outcome"] == "failed" and source_audit(res3) == source_audit(base_res)
    else:
        assert len(fake.requests) == 2 and res2["ai"]["outcome"] == "ok"   # a success starts no cooldown: one request per audit

    # ---- (g) logs, at DEBUG, for the whole scenario
    assert leaked(harness.log_text(), private) == []


def test_no_retry_storm_during_a_429_cooldown(harness):
    """(e) After one 429, 25 rapid audits and then 12 concurrent ones make no further request, and each one says why."""
    answer, _ = fg.GROQ_ANSWERS["429_rate_limit_rpm"]
    fake = harness.fake(answer)
    assert harness.audit()["ai"]["outcome"] == "failed"
    outcomes = [harness.audit()["ai"]["outcome"] for _ in range(25)]

    def one(_):
        r = harness.client.post("/api/audit", json={"article": fg.ARTICLE}, headers={"x-forwarded-for": f"10.0.0.{_}"})
        return r.json()["ai"]["outcome"]

    with ThreadPoolExecutor(max_workers=12) as pool:
        outcomes += list(pool.map(one, range(12)))
    assert len(fake.requests) == 1
    assert set(outcomes) == {"skipped_cooldown"}


def test_a_cooldown_skip_is_not_reported_as_a_failure_with_the_earlier_status(use_source, monkeypatch, caplog):
    """The defect this harness found (4 Oct): on main, the audit after a 429 said outcome «failed», http_status 429 and the
    model-failure warning, although it made no request. It now says the model was not asked, and why."""
    h = Harness(monkeypatch, caplog)
    h.fake(fg.GROQ_ANSWERS["429_rate_limit_rpm"][0])
    h.audit()
    ai = h.audit()["ai"]
    assert (ai["outcome"], ai["http_status"], ai["error"]) == ("skipped_cooldown", None, None)


def test_error_body_keeps_no_failed_generation_and_redacts_account_ids():
    r = httpx.Response(400, json=fg.JSON_FAILED)
    body = groq.error_body(r)
    assert body["code"] == "json_validate_failed" and body["failed_generation_chars"] == len(fg.JSON_FAILED["error"]["failed_generation"])
    assert "failed_generation" not in body and fg.FG_MARK not in json.dumps(body, ensure_ascii=False)
    assert groq.is_generation_failure(400, body)
    rpm = groq.error_body(httpx.Response(429, json=fg.RPM))
    assert fg.ORG not in rpm["message"] and "org_…" in rpm["message"] and "requests per minute" in rpm["message"]
    assert groq.error_body(httpx.Response(401, json={"error": {"message": f"bad key {fg.KEY}"}}))["message"] == "bad key gsk_…"
    assert groq.error_body(httpx.Response(502, json=["not", "an", "object"])) == {"raw": '["not","an","object"]'}


@pytest.mark.parametrize("header,expected", [("2", 2.0), ("864", 864.0), ("999999", 3600.0), ("soon", 0.0), (None, 0.0)])
def test_retry_after_is_read_and_capped(header, expected):
    assert groq._retry_after(httpx.Response(429, headers={"retry-after": header} if header else {})) == expected


# ---- the unhandled-error path --------------------------------------------------------------------------------------------

def _break_the_phrase_search(monkeypatch):
    def boom(*a, **k):
        raise KeyError(f"{fg.PROSE[1]} {fg.KEY}")   # an exception whose message quotes the article (and a secret)
    monkeypatch.setattr(audit, "find_phrases", boom)


def test_unhandled_error_answers_generically_and_logs_only_its_type(harness, monkeypatch):
    harness.fake(fg.GROQ_ANSWERS["400_json_validate_failed"][0])
    _break_the_phrase_search(monkeypatch)
    main._hits.clear()
    r = harness.client.post("/api/audit", json={"article": fg.ARTICLE})
    assert r.status_code == 500 and r.json() == {"error": "حدث خطأ غير متوقع أثناء التدقيق."}
    assert r.headers["x-content-type-options"] == "nosniff"                   # answered inside the middleware
    logs = harness.log_text()
    assert "unhandled error on /api/audit: KeyError" in logs
    assert leaked(logs + r.text + harness.health()[0], private_strings(fg.GROQ_ANSWERS["400_json_validate_failed"][1])) == []


def test_a_defect_inside_the_provider_adapter_still_gives_the_source_audit(harness, monkeypatch):
    """Not an ExtractionError: a bug in the adapter itself. The audit completes, the model is cooled down, the log has the type."""
    base_res = harness.baseline()

    def broken(self, article):
        raise ValueError(f"adapter bug near «{fg.PROSE[1]}»")
    monkeypatch.setattr(groq.GroqProvider, "extract", broken)
    res = harness.audit()
    assert source_audit(res) == source_audit(base_res)
    assert res["mode"] == "ai_failed" and res["ai"]["outcome"] == "failed" and res["ai"]["error"] == "خطأ غير متوقع في خدمة الذكاء الاصطناعي"
    assert model_notices(res, base_res) == [{"level": "warning", "text": audit.MODEL_FAILED_NOTICE}]
    assert groq._tracker.cooldown_remaining() > 0 and groq._tracker.last["detail"] == "unexpected"
    assert "model provider raised ValueError" in harness.log_text()
    assert leaked(harness.log_text(), ["adapter bug", *private_strings()]) == []
    assert "adapter bug" not in json.dumps(res, ensure_ascii=False)


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_real_uvicorn_writes_no_traceback_that_quotes_the_article(harness, monkeypatch):
    """Starlette re-raises after the app's Exception handler so the server can log it, and uvicorn logs the full traceback
    (message included). On main that traceback quoted whatever the exception said. Run a real uvicorn (127.0.0.1 only) with a
    model failure and then an unhandled error, and read every log record it wrote."""
    import uvicorn

    harness.fake(fg.GROQ_ANSWERS["400_json_validate_failed"][0])
    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(main.app, host="127.0.0.1", port=port, log_config=None, lifespan="off", log_level="debug"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        for _ in range(200):
            if server.started:
                break
            time.sleep(0.02)
        assert server.started
        with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=30) as local:   # the real httpx: only the provider is faked
            main._hits.clear()
            ok = local.post("/api/audit", json={"article": fg.ARTICLE})
            assert ok.status_code == 200 and ok.json()["ai"]["outcome"] == "failed"
            _break_the_phrase_search(monkeypatch)
            main._hits.clear()
            bad = local.post("/api/audit", json={"article": fg.ARTICLE})
            assert bad.status_code == 500
            health = local.get("/api/health").text
    finally:
        server.should_exit = True
        thread.join(10)
    logs = harness.log_text()
    assert '"POST /api/audit HTTP/1.1" 500' in logs or "POST /api/audit" in logs   # uvicorn's access line was captured
    assert "Exception in ASGI application" not in logs and "Traceback" not in logs
    assert leaked(logs + health, private_strings(fg.GROQ_ANSWERS["400_json_validate_failed"][1])) == []


# ---- Gemini: the same properties where they apply ----------------------------------------------------------------------
# Gemini is not deployed (render.yaml selects Groq). Its plan retries a fast 503 once and may move to fallback models, so 503
# and timeout make more than one request by design (tests/test_gemini.py); those two are not repeated here.

GEMINI_ANSWERS = {
    "429": (lambda r: httpx.Response(429, json={"error": {"code": 429, "message": "Resource has been exhausted SENTINELG429", "status": "RESOURCE_EXHAUSTED"}}), "الحصة", "SENTINELG429"),
    "401": (lambda r: httpx.Response(401, json={"error": {"code": 401, "message": "API key not valid SENTINELG401", "status": "UNAUTHENTICATED"}}), "401", "SENTINELG401"),
    "500": (lambda r: httpx.Response(500, json={"error": {"code": 500, "message": "Internal error SENTINELG500", "status": "INTERNAL"}}), "500", "SENTINELG500"),
    "400": (lambda r: httpx.Response(400, json={"error": {"code": 400, "message": f"Invalid value near «{fg.PROSE[1]}»", "status": "INVALID_ARGUMENT"}}), "400", "Invalid value"),
    "malformed": (lambda r: httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": "{candidates: ["}]}}]}), "JSON", None),
    "blocked": (lambda r: httpx.Response(200, json={"promptFeedback": {"blockReason": "OTHER"}}), "غير مكتملة", None),
    "connect": (fg._raise(httpx.ConnectError, "refused"), "تعذّر الاتصال", None),
}


@pytest.mark.parametrize("scenario", list(GEMINI_ANSWERS))
def test_gemini_failures_end_in_the_source_audit_with_one_request_and_a_cooldown(use_source, monkeypatch, caplog, scenario):
    answer, error, sentinel = GEMINI_ANSWERS[scenario]
    h = Harness(monkeypatch, caplog, module=gemini, selection="gemini", key_env="GEMINI_API_KEY")
    base_res = h.baseline()
    fake = h.fake(answer)
    res = h.audit()
    assert len(fake.requests) == 1 and fake.requests[0]["headers"]["x-goog-api-key"] == fg.KEY and fg.KEY not in fake.requests[0]["url"]
    assert source_audit(res) == source_audit(base_res)
    assert res["mode"] == "ai_failed" and res["ai"]["outcome"] == "failed" and error in res["ai"]["error"] and res["ai"]["error_body"] is None
    res2 = h.audit()
    assert len(fake.requests) == 1, "on main, Gemini 401/500/400/malformed/blocked started no cooldown: every audit asked again"
    assert res2["ai"]["outcome"] == "skipped_cooldown" and res2["ai"]["http_status"] is None and source_audit(res2) == source_audit(base_res)
    h_text, _ = h.health()
    assert leaked(h_text + h.log_text(), private_strings([sentinel] if sentinel else [])) == []
    assert leaked(json.dumps(res, ensure_ascii=False), [fg.KEY] + ([sentinel] if sentinel else [])) == []

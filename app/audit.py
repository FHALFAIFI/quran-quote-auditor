"""Audit pipeline: extract candidates → locate in article → attach references → verify."""

from __future__ import annotations

import time

from . import arabic
from .corrections import build_changes
from .config import settings
from .extraction import Candidate, ExtractionError, get_provider
from .extraction.marked import extract_marked
from .phrases import ends_with_quran_cue, find_phrases, grade_approximate, grade_exact, quran_cue, span_mass
from .quran_source import MUSHAF_URL, QuranIndex, SourceUnavailable, source
from .references import Reference, find_references
from .verifier import MIN_WORDS, unavailable_result, verify

REF_AFTER_CHARS, REF_AFTER_WORDS = 40, 3
REF_BEFORE_CHARS, REF_BEFORE_WORDS = 60, 6
PRIORITY = {"manual": 0, "marked": 0, "ai": 1, "phrase": 2}  # order in which a finding's methods are listed
# Who keeps an overlapping span: what the program established from the text (a marker, the writer's own selection, a
# literal phrase match) always outranks the model's proposal, which is only a place to look.
MERGE_PRIORITY = {"manual": 0, "marked": 0, "phrase": 1, "ai": 2}
MANUAL_MAX_WORDS = 60

# Detection (is this a Quran quotation?) is reported separately from verification (does it match the text?).
TIER_LABEL = {
    "candidate": "مرشَّح لاقتباس قرآني",
    "possible": "قد يكون اقتباسًا قرآنيًا — يحتاج مراجعة",
}
TIER_REASON = {
    "candidate": "مطابقة حرفية لعبارة مميزة من المصحف دون علامات اقتباس؛ تأكد أنها مقصودة اقتباسًا.",
    "common": "عبارة قصيرة أو شائعة قد ترد في الكلام العادي.",
    "approximate": "مطابقة تقريبية: بعض كلمات العبارة تختلف عن المصحف، وليست تحققًا.",
    "formula": "عبارة شائعة الاستعمال (بسملة أو حمدلة أو ذكر…) وقد لا يُقصد بها اقتباس آية.",
    "non_quran_cue": "سبقتها إشارة إلى حديث أو دعاء أو مثل، فقد تكون من غير القرآن.",
    "ai_only": "اقترحه نموذج الذكاء الاصطناعي وحده ولم يجده البحث الآلي، واقتراح النموذج ليس دليلًا على أنه اقتباس قرآني؛ فقد يكون من كلام الكاتب.",
    "no_match": "لا تدعم مقارنتُه بنص المصحف أنه اقتباس قرآني.",
}
END_UNCERTAIN_MESSAGE = ("نهاية المقطع غير محسومة: ما قبل هذه الكلمة مطابق للمصحف، لكن الكلمة التالية في المقال تختلف عن كلمة الآية التالية "
                         "ولا يغلق المقطعَ علامةٌ ولا إحالة، فلا يُعرف أهي كلام الكاتب بعد الاقتباس أم خطأ في آخر الاقتباس.")
START_UNCERTAIN_MESSAGE = ("بداية المقطع غير محسومة: ما بعد هذه الكلمة مطابق للمصحف، لكن الكلمة التي قبله في المقال تختلف عن كلمة الآية التي قبله "
                           "ولا يفتتح المقطعَ علامةٌ ولا إحالة ولا عبارة تمهيد، فلا يُعرف أهي كلام الكاتب قبل الاقتباس أم خطأ في أول الاقتباس.")
BOTH_UNCERTAIN_MESSAGE = ("حدود المقطع غير محسومة: الكلمة قبل المقطع والكلمة بعده في المقال تختلفان عن كلمتي الآية المجاورتين، "
                          "ولا علامة ولا إحالة تحدّد أين يبدأ الاقتباس وأين ينتهي، فلا يُعرف أهما كلام الكاتب أم خطأ في أول الاقتباس وآخره.")
UNCONFIRMED_REASON = "لم يتأكد أن هذا المقطع اقتباس قرآني، فلا تُقترح عليه تصحيحات. إن كان اقتباسًا فأكّد ذلك واختر موضعه ليظهر التصحيح المقترح."


class InputError(ValueError):
    """Invalid user input; message is safe to show."""


def locate(tokens: list[arabic.Token], quote: str) -> list[tuple[int, int]]:
    """Token-index ranges [i, j) where ``quote`` occurs in the article (folded)."""
    qf = [t.fold for t in arabic.tokenize(quote)]
    if not qf:
        return []
    af = [t.fold for t in tokens]
    n = len(qf)
    return [(i, i + n) for i in range(len(af) - n + 1) if af[i:i + n] == qf]


def _span_candidate(article: str, tokens: list[arabic.Token], i: int, j: int, src: str) -> Candidate:
    s, e = tokens[i].start, tokens[j - 1].end
    return Candidate(s, e, article[s:e], {src})


def _relation(c: Candidate, k: Candidate) -> str:
    """How the model's span ``c`` lies against the kept span ``k``: wider, narrower, or shifted (a partial overlap)."""
    if c.start <= k.start and k.end <= c.end:
        return "wider"
    if k.start <= c.start and c.end <= k.end:
        return "narrower"
    return "shifted"


def merge(cands: list[Candidate]) -> list[Candidate]:
    """Keep non-overlapping candidates. A span found by a marker, the writer or the phrase search is never replaced,
    shrunk, widened or dropped by a model proposal that overlaps it (marked/manual > phrase > ai).

    The model's overlapping proposal is kept as evidence instead: the same span only adds "ai" to the sources
    (the model agreed), a different span is recorded in ``ai_spans`` and the kept span's tier and verdict stay its own.
    """
    kept: list[Candidate] = []
    for c in sorted(cands, key=lambda c: (min(MERGE_PRIORITY[x] for x in c.sources), c.start, -(c.end - c.start))):
        overlaps = [k for k in kept if c.start < k.end and k.start < c.end]
        if not overlaps:
            kept.append(c)
        elif c.sources == {"ai"}:
            for k in overlaps:
                k.reference_hint = k.reference_hint or c.reference_hint
                if k.sources == {"ai"}:
                    continue  # two model proposals for one place: the first stands
                if (k.start, k.end) == (c.start, c.end):
                    k.sources.add("ai")
                else:
                    k.ai_spans.append({"start": c.start, "end": c.end, "quote": c.text, "relation": _relation(c, k)})
        else:
            overlap = overlaps[0]
            overlap.sources |= c.sources
            overlap.reference_hint = overlap.reference_hint or c.reference_hint
            overlap.phrase = overlap.phrase or c.phrase
    return sorted(kept, key=lambda c: c.start)


def _words_between(article: str, a: int, b: int) -> int:
    return len(arabic.tokenize(article[a:b])) if b > a else 0


def attach_references(article: str, cands: list[Candidate], refs: list[Reference]) -> list[Reference | None]:
    """Associate each candidate with at most one nearby reference."""
    used: set[int] = set()
    out: list[Reference | None] = [None] * len(cands)
    free = [r for r in refs if not any(c.start <= r.start and r.end <= c.end for c in cands)]
    # 1) references right after the quotation
    for ci, c in enumerate(cands):
        limit = cands[ci + 1].start if ci + 1 < len(cands) else len(article)
        for ri, r in enumerate(free):
            if ri in used or r.start < c.end or r.start >= limit:
                continue
            if r.start - c.end <= REF_AFTER_CHARS and _words_between(article, c.end, r.start) <= REF_AFTER_WORDS:
                out[ci] = r
                used.add(ri)
            break
    # 2) reference text proposed by the AI, if it is really in the article near the quote
    for ci, c in enumerate(cands):
        if out[ci] is not None or not c.reference_hint:
            continue
        hint = arabic.folded(c.reference_hint)
        for ri, r in enumerate(free):
            if ri not in used and abs(r.start - c.end) <= 150 and hint and (hint in arabic.folded(r.text) or arabic.folded(r.text) in hint):
                out[ci] = r
                used.add(ri)
                break
    # 3) references just before the quotation ("في سورة البقرة: ...")
    for ci, c in enumerate(cands):
        if out[ci] is not None:
            continue
        floor = cands[ci - 1].end if ci > 0 else 0
        for ri in range(len(free) - 1, -1, -1):
            r = free[ri]
            if ri in used or r.end > c.start or r.end < floor:
                continue
            if c.start - r.end <= REF_BEFORE_CHARS and _words_between(article, r.end, c.start) <= REF_BEFORE_WORDS:
                out[ci] = r
                used.add(ri)
            break
    return out


def _line_col(article: str, pos: int) -> tuple[int, int]:
    line = article.count("\n", 0, pos) + 1
    col = pos - (article.rfind("\n", 0, pos) + 1) + 1
    return line, col


def _grade_span(article: str, index: QuranIndex | None, c: Candidate, result: dict) -> tuple[str, list[str]]:
    """Tier and reason codes of an unmarked span that the AI proposed.

    The model's proposal is never evidence that a span is a Quran quotation, so the span is graded exactly as the phrase
    search grades its own hits (``phrases.grade_exact`` / ``grade_approximate``) and the AI can neither raise nor lower
    that tier: an exact, distinctive phrase is a "candidate"; a short or common one, a formula, one that follows a
    hadith/du'a cue, one whose words differ from the text, and one that matches nothing are only "possible".
    (A span only the model proposed is "stated" instead when the writer's own reference or lead-in backs it: see
    ``_corroboration``.)
    """
    if index is None:
        return "possible", ["no_match"]
    cue = quran_cue(article, c.start)
    folded = tuple(t.fold for t in arabic.tokenize(c.text))
    if result["occurrences"] and len(folded) >= MIN_WORDS:
        graded = grade_exact(folded, span_mass(index, folded), cue)
        return graded if graded else ("possible", ["common"])
    if result["wording"].get("level") == "fuzzy":
        return grade_approximate(cue)
    return "possible", ["common"] if result["occurrences"] else ["no_match"]


def _corroboration(article: str, c: Candidate, result: dict, ref: Reference | None) -> str | None:
    """Evidence from the writer, not the model, that this span is meant as a quotation (None if there is none).

    "reference": a written reference with an ayah number points at the very verse the span was matched to.
    "lead_in": a lead-in such as «قال تعالى» comes right before the span.
    """
    src = result["source"]
    if ref is not None and ref.valid and ref.ayah_start is not None and src is not None and ref.surah == src["surah"]:
        if ref.ayah_start <= src["ayah_end"] and src["ayah_start"] <= (ref.ayah_end or ref.ayah_start):
            return "reference"
    return "lead_in" if ends_with_quran_cue(article[max(0, c.start - 80):c.start]) else None


def _detection(article: str, index: QuranIndex | None, c: Candidate, result: dict, ref: Reference | None) -> dict:
    """How the span was found, how sure we are that the writer meant a Quran quotation, and what the AI contributed.

    ``ai_role`` is "only" when the model proposed a span nothing else found (it would be absent without the model),
    "also" when it proposed the same span a marker or the phrase search had found, "overlap" when it proposed a different
    span that overlaps one the program found (that span, its tier and its verdict stay the program's; the model's span
    is listed in ``ai_spans``), and None when it took no part.
    """
    ai_role = "overlap" if c.ai_spans and "ai" not in c.sources else None if "ai" not in c.sources else "only" if c.sources == {"ai"} else "also"
    spans = {"ai_spans": [dict(s) for s in c.ai_spans]} if c.ai_spans else {}
    if "manual" in c.sources:
        return {"kind": "manual", "tier": "manual", "label": "حدّدتَ هذا المقطع بنفسك", "codes": ["manual"], "reasons": [], "unconfirmed": False, "ai_role": ai_role, **spans}
    if "marked" in c.sources:
        return {"kind": "marked", "tier": "stated", "label": None, "codes": [], "reasons": [], "unconfirmed": False, "ai_role": ai_role, **spans}
    if c.phrase is not None:
        # Found by the phrase search: its tier is the search's own, whatever the model did or did not propose.
        tier, codes = c.phrase.tier, list(c.phrase.reasons)
        info = {"exact": c.phrase.exact, "occurrences": len(c.phrase.spans) if c.phrase.exact else None}
    else:
        info = {"exact": bool(result["occurrences"]), "occurrences": result["occurrences"] or None}
        basis = _corroboration(article, c, result, ref) if ai_role == "only" else None
        if basis:
            return {"kind": "ai", "tier": "stated", "label": None, "codes": [], "reasons": [], "unconfirmed": False, "ai_role": ai_role, "basis": basis, **info}
        tier, codes = _grade_span(article, index, c, result)
        if ai_role == "only":
            codes = ["ai_only", *codes]
    codes = codes or ["candidate"]
    return {"kind": "phrase" if c.phrase is not None else "ai", "tier": tier, "label": TIER_LABEL.get(tier), "codes": codes,
            "reasons": [TIER_REASON[k] for k in codes if k in TIER_REASON], "unconfirmed": tier == "possible", "ai_role": ai_role, **info, **spans}


def _choices(index: QuranIndex, finding: dict) -> list[dict]:
    """Places the editor can pick from: the proposed place first, then the alternatives."""
    out, seen = [], set()
    blocks = ([finding["source"]] if finding.get("source") else []) + [a["source"] for a in finding.get("alternatives", []) if a.get("source")]
    for b in blocks:
        key = (b["surah"], b["ayah_start"], b["ayah_end"])
        if key not in seen:
            seen.add(key)
            out.append({"surah": b["surah"], "ayah_start": b["ayah_start"], "ayah_end": b["ayah_end"], "label": b["label"],
                        "text": b["matched_text"]})
    return out


def _finding(article: str, index: QuranIndex | None, n: int, c: Candidate, ref: Reference | None, pin: Reference | None = None) -> dict:
    """Verify one candidate and assemble the finding (with its proposed changes) the interface shows."""
    words = [t.raw for t in arabic.tokenize(c.text)]
    phrase_found = c.phrase is not None and not ({"marked", "manual"} & c.sources)
    if index is None:
        result = unavailable_result(ref)
    else:
        result = verify(index, words, ref, pin=pin, hints=list(c.phrase.spans) if phrase_found else None)
    line, col = _line_col(article, c.start)
    finding = {
        "id": n,
        "start": c.start,
        "end": c.end,
        "line": line,
        "column": col,
        "quote": c.text,
        "detected_by": sorted(c.sources, key=lambda x: PRIORITY[x]),
        "marker": c.marker,
        "detection": _detection(article, index, c, result, ref),
        **result,
    }
    start_b = _start_boundary(article, c, finding, ref) if index is not None else None
    end_b = _end_boundary(article, c, finding, ref) if index is not None else None
    finding["start_boundary"], finding["end_boundary"] = start_b, end_b
    start_unc, end_unc = bool(start_b and start_b["status"] == "uncertain"), bool(end_b and end_b["status"] == "uncertain")
    finding["lead_in"] = {"quran": start_b["quran"], "article": start_b["article"]} if start_unc else None
    finding["continuation"] = {"quran": end_b["quran"], "article": end_b["article"]} if end_unc else None
    boundary_msg = BOTH_UNCERTAIN_MESSAGE if start_unc and end_unc else START_UNCERTAIN_MESSAGE if start_unc else END_UNCERTAIN_MESSAGE
    boundary_unc = start_unc or end_unc
    if boundary_unc:
        # Keep wording and reference verdicts apart: only the wording verdict is held back, and only for "matched".
        if finding["wording"]["status"] == "matched":
            finding["wording"] = {**finding["wording"], "status": "uncertain", "message": boundary_msg}
            finding["needs_review"] = True
        finding["review_reasons"] = list(dict.fromkeys([boundary_msg, *finding["review_reasons"]]))
    det = finding["detection"]
    if det["unconfirmed"]:
        # Detection is weak: show it, but offer no replacement text until the editor says it is a Quran quotation.
        finding.pop("proposal", None)
        finding["changes"] = []
        finding["correction"] = {"status": "unconfirmed", "reason": UNCONFIRMED_REASON}
        finding["needs_review"] = True
        finding["review_reasons"] = list(dict.fromkeys([det["label"], *det["reasons"], *finding["review_reasons"]]))
    else:
        changes, summary = build_changes(article, finding, c.start, ref)
        finding.pop("proposal", None)
        finding["changes"] = changes
        finding["correction"] = summary
        if det["kind"] in ("phrase", "ai"):
            finding["review_reasons"] = list(dict.fromkeys([*det["reasons"], *finding["review_reasons"]]))
        if end_unc:
            # Nothing may be offered that depends on where the quotation ends (a reference goes after its last word).
            finding["changes"] = [ch for ch in finding["changes"] if ch["kind"] != "reference_add"]
        if boundary_unc and finding["correction"]["status"] == "none_needed":
            finding["correction"] = {"status": "review_only", "reason": boundary_msg}
    finding["choices"] = _choices(index, finding) if index is not None and (det["kind"] in ("phrase", "manual") or det["unconfirmed"]) else []
    return finding


def _start_boundary(article: str, c: Candidate, finding: dict, ref: Reference | None) -> dict | None:
    """Is the START of the identified span settled, or could the quotation really begin earlier (a wrong first word)?

    The mirror of ``_end_boundary``. Only spans whose start was chosen by the program or by the AI are in question;
    brackets, quotation marks and a highlight made by the editor state the start themselves (``None``). The start is
    settled when the span begins at the start of its verse, when punctuation / a line break / the start of the article
    precedes it, when a lead-in such as «قال تعالى» or the reference that belongs to it comes just before it. Otherwise
    the previous article word touches the span and the verse says something else there: a wrong first word and
    ordinary prose before a correct quotation look identical, so the start is "uncertain".
    """
    if {"marked", "manual"} & c.sources:
        return None
    src = finding.get("source")
    if not src or not src.get("segments"):
        return None
    first = src["segments"][0]
    if first["from"] <= 0:
        return {"status": "settled", "basis": "verse_start"}
    if ref is not None and ref.end <= c.start and not arabic.tokenize(article[ref.end:c.start]):
        return {"status": "settled", "basis": "reference"}
    window = article[max(0, c.start - 80):c.start]
    prev = arabic.tokenize(window)
    if not prev:
        return {"status": "settled", "basis": "article_start"}
    gap = window[prev[-1].end:]
    if "\n" in gap or gap.strip(" \t\u00a0،,؛;") != "":
        return {"status": "settled", "basis": "punctuation"}
    if ends_with_quran_cue(window):
        return {"status": "settled", "basis": "lead_in"}
    return {"status": "uncertain", "basis": "adjacent_word", "quran": arabic.letters(first["words"][first["from"] - 1]), "article": prev[-1].raw}


def _end_boundary(article: str, c: Candidate, finding: dict, ref: Reference | None) -> dict | None:
    """Is the END of the identified span settled, or could the quotation really run on (a wrong last word)?

    Only spans whose end was chosen by the program or by the AI are in question; brackets, quotation marks and a
    highlight made by the editor state the end themselves (``None``). The end is settled when the span reaches the
    end of its verse, when punctuation / a line break / the end of the article follows it, or when the reference
    that belongs to it follows at once. Otherwise the next article word touches the span and the verse says
    something else there: a wrong last word and ordinary prose look identical, so the end is "uncertain".
    """
    if {"marked", "manual"} & c.sources:
        return None
    src = finding.get("source")
    if not src or not src.get("segments"):
        return None
    last = src["segments"][-1]
    if last["to"] >= len(last["words"]):
        return {"status": "settled", "basis": "verse_end"}
    if ref is not None and ref.start >= c.end and not arabic.tokenize(article[c.end:ref.start]):
        return {"status": "settled", "basis": "reference"}
    nxt = arabic.tokenize(article[c.end:c.end + 80])
    if not nxt:
        return {"status": "settled", "basis": "article_end"}
    gap = article[c.end:c.end + nxt[0].start]
    if "\n" in gap or gap.strip(" \t\u00a0،,؛;") != "":
        return {"status": "settled", "basis": "punctuation"}
    return {"status": "uncertain", "basis": "adjacent_word", "quran": arabic.letters(last["words"][last["to"]]), "article": nxt[0].raw}


def _drop_overlapping_changes(findings: list[dict]) -> None:
    """Changes from different findings must never overlap; drop any that would (defensive)."""
    taken: list[tuple[int, int]] = []
    for f in findings:
        keep = []
        for ch in f["changes"]:
            s0, e0 = ch["start"], ch["end"]
            if any(s0 < e1 and s1 < e0 or (s0 == e0 == s1 == e1) for s1, e1 in taken):
                continue
            taken.append((s0, e0))
            keep.append(ch)
        f["changes"] = keep


def _stats(findings: list[dict]) -> dict:
    weak = lambda f: f["detection"]["unconfirmed"]  # noqa: E731
    return {
        "total": len(findings),
        "matched": sum(f["wording"]["status"] == "matched" and not weak(f) for f in findings),
        "difference": sum(f["wording"]["status"] == "difference" for f in findings),
        "uncertain": sum(f["wording"]["status"] == "uncertain" for f in findings),
        "needs_review": sum(f["needs_review"] for f in findings),
        "possible": sum(weak(f) for f in findings),
        "candidates": sum(f["detection"]["tier"] == "candidate" for f in findings),
        "ref_matched": sum(f["reference"]["status"] == "matched" for f in findings),
        "ref_missing": sum(f["reference"]["status"] == "missing" for f in findings),
        "ref_incorrect": sum(f["reference"]["status"] == "incorrect" for f in findings),
        "ref_uncertain": sum(f["reference"]["status"] == "uncertain" for f in findings),
        "proposed_changes": sum(len(f["changes"]) for f in findings),
    }


def _clean_article(article: str) -> str:
    if not isinstance(article, str) or not article.strip():
        raise InputError("الرجاء إدخال نص المقال.")
    article = article.replace("\r\n", "\n").replace("\r", "\n")
    if len(article) > settings.max_chars:
        raise InputError(f"النص أطول من الحد المسموح ({settings.max_chars} حرف).")
    return article


def run_audit(article: str) -> dict:
    article = _clean_article(article)
    started = time.monotonic()
    notices: list[dict] = []
    tokens = arabic.tokenize(article)
    refs = find_references(article)

    # Source first: without it nothing can be verified, but extraction still runs.
    index: QuranIndex | None
    try:
        index = source.get()
        if index.stale:
            notices.extend({"level": "warning", "text": n} for n in index.notes)
    except SourceUnavailable:
        index = None
        notices.append({"level": "error", "text": "تعذّر الوصول إلى قرآنبيديا الآن، فلن يُحكم على أي اقتباس. أعد المحاولة لاحقًا."})

    provider = get_provider()
    mode = "ai" if provider else "reduced"
    candidates: list[Candidate] = extract_marked(article, refs)
    # What really happened with AI on THIS audit (configured ≠ responded).
    ai: dict = {
        "configured": provider is not None,
        "provider": provider.name if provider else None,
        "model": getattr(provider, "model", None) if provider else None,
        "responded": False,
        "outcome": "not_configured" if provider is None else "not_called",
        "http_status": None,
        "elapsed_ms": None,
        "proposed": 0,
        "located": 0,
        "discarded": 0,
        "error": None,
        "error_body": None,
        "generation_failure": False,
        "added_only": 0,
        "also_found": 0,
        "overlapped": 0,
    }
    discarded = 0
    if provider:
        t_ai = time.monotonic()
        try:
            suggestions = provider.extract(article)
            ai.update(responded=True, outcome="ok", proposed=len(suggestions), model=provider.used_model)
            for sug in suggestions:
                spans = locate(tokens, sug.quote)
                if not spans:
                    discarded += 1
                    continue
                ai["located"] += 1
                for i, j in spans:
                    c = _span_candidate(article, tokens, i, j, "ai")
                    c.reference_hint = sug.reference_text
                    candidates.append(c)
        except ExtractionError as exc:
            mode = "ai_failed"
            ai.update(outcome="failed", error=str(exc), error_body=exc.body, generation_failure=exc.generation_failure)
            notices.append({"level": "warning", "text": f"تعذّر الاستخراج بالذكاء الاصطناعي ({exc}). عُرضت الاقتباسات المعلَّمة صراحةً والعبارات المطابقة لنص المصحف فقط؛ وقد تفوت الاقتباسات القصيرة غير المعلَّمة."})
        ai["elapsed_ms"] = int((time.monotonic() - t_ai) * 1000)
        ai["discarded"] = discarded
        last = provider.tracker.status() if getattr(provider, "tracker", None) else {}
        ai["http_status"] = last.get("http_status")
    if discarded:
        notices.append({"level": "info", "text": f"استُبعد {discarded} مقطعًا اقترحه نموذج الذكاء الاصطناعي لأنه غير موجود حرفيًا في المقال."})
    scan = None
    if index is not None:
        scan = find_phrases(article, tokens, index)
        for h in scan.hits:
            c = _span_candidate(article, tokens, h.first, h.last, "phrase")
            c.phrase = h
            candidates.append(c)

    candidates = [c for c in merge(candidates)][: settings.max_candidates]
    attached = attach_references(article, candidates, refs)

    findings = [_finding(article, index, n, c, ref) for n, (c, ref) in enumerate(zip(candidates, attached), start=1)]
    _drop_overlapping_changes(findings)
    if provider:
        # What the model added: spans only it proposed (absent without it) vs. spans something else had found too.
        ai["added_only"] = sum(f["detection"]["ai_role"] == "only" for f in findings)
        ai["also_found"] = sum(f["detection"]["ai_role"] == "also" for f in findings)
        ai["overlapped"] = sum(f["detection"]["ai_role"] == "overlap" for f in findings)

    phrase_info = None
    if scan is not None:
        # Short, common phrases that match the Quran but cannot be told from ordinary Arabic: counted, not listed.
        hidden = [h for h in scan.suppressed
                  if not any(tokens[h.first].start < c.end and c.start < tokens[h.last - 1].end for c in candidates)]
        phrase_info = {"hidden": len(hidden), "truncated": scan.truncated}
        if hidden:
            notices.append({"level": "info", "text": f"لم تُعرض {len(hidden)} عبارة قصيرة أو شائعة تطابق نص المصحف، لأنها لا تتميّز عن الكلام العادي. إن كنت تقصد اقتباسًا قرآنيًا منها فحدّده بالماوس في مربع النص واختر موضعه."})
        if scan.truncated:
            notices.append({"level": "warning", "text": "بلغ البحث عن العبارات غير المعلَّمة حدّ العمل المسموح، فلم يُفحص ما بقي من النص بهذه الطريقة."})

    return {
        "mode": mode,
        "provider": provider.label if provider else None,
        "provider_model": provider.used_model if provider else None,
        "ai": ai,
        "notices": notices,
        "source": {
            "name": "Quranpedia — مصحف حفص عن عاصم",
            "url": MUSHAF_URL,
            "available": index is not None,
            "fetched_at": index.fetched_at if index else None,
            "stale": bool(index and index.stale),
            "loaded_from": index.loaded_from if index else None,
        },
        "findings": findings,
        "stats": _stats(findings),
        "phrases": phrase_info,
        "elapsed_ms": int((time.monotonic() - started) * 1000),
    }


def _manual_reference(article: str, index: QuranIndex, cand: Candidate, others) -> Reference | None:
    """The reference that belongs to a manually checked span.

    In a full audit every reference goes to at most one quotation, so one written after another quotation is not taken
    by a phrase that merely follows it. A manual check sees only the highlighted span, so the other quotations are
    rebuilt first (marked ones and the phrase search, both deterministic, no AI) and the browser adds the spans of
    the findings it shows (``others``, for example one only the model proposed). Spans that overlap the highlighted
    one are dropped: the manual span replaces them.
    """
    refs = find_references(article)
    tokens = arabic.tokenize(article)
    neighbours = extract_marked(article, refs)
    for h in find_phrases(article, tokens, index).hits:
        neighbours.append(_span_candidate(article, tokens, h.first, h.last, "phrase"))
    for pair in others or ():
        try:
            s, e = int(pair[0]), int(pair[1])
        except (TypeError, ValueError, IndexError):
            continue
        if 0 <= s < e <= len(article):
            neighbours.append(Candidate(s, e, article[s:e], {"ai"}))  # lowest merge rank: it only reserves its reference
    neighbours = [n for n in merge(neighbours) if n.end <= cand.start or n.start >= cand.end]
    everyone = sorted(neighbours + [cand], key=lambda c: c.start)
    return attach_references(article, everyone, refs)[everyone.index(cand)]


def run_phrase(article: str, start: int, end: int, surah: int | None = None, ayah_start: int | None = None,
               ayah_end: int | None = None, finding_id: int = 1, others: list | tuple = ()) -> dict:
    """Check a span the editor highlighted by hand (code-point offsets), optionally with a verse they chose.

    No AI is involved and nothing is guessed: the span is verified like any quotation, the editor's verse (if any)
    settles the location the way a written reference would, and the result is one finding whose proposed changes
    still need the editor's approval one by one. Very short phrases may match many verses; then the choices are listed.
    """
    article = _clean_article(article)
    if not all(isinstance(v, int) and not isinstance(v, bool) for v in (start, end)) or not 0 <= start < end <= len(article):
        raise InputError("حدّد مقطعًا من المقال.")
    index = source.get()  # SourceUnavailable propagates: the API answers "source unavailable"
    chosen = [t for t in arabic.tokenize(article) if t.start < end and t.end > start]
    if not chosen:
        raise InputError("حدّد كلمات عربية من المقال.")
    if len(chosen) > MANUAL_MAX_WORDS:
        raise InputError(f"المقطع المحدَّد أطول من {MANUAL_MAX_WORDS} كلمة.")
    s0, e0 = chosen[0].start, chosen[-1].end
    cand = Candidate(s0, e0, article[s0:e0], {"manual"})
    ref = _manual_reference(article, index, cand, others)
    pin = None
    if surah is not None:
        a1 = ayah_end or ayah_start
        if ayah_start is None or (surah, ayah_start) not in index.ayah_pos or (surah, a1) not in index.ayah_pos or a1 < ayah_start:
            raise InputError("الموضع المختار غير موجود في المصحف.")
        pin = Reference(-1, -1, "", surah, ayah_start, a1)
    finding = _finding(article, index, int(finding_id), cand, ref, pin=pin)
    finding["needs_choice"] = finding["source"] is None and bool(finding["choices"])
    return {"finding": finding, "pinned": pin is not None}

"""Turn deterministic verifier proposals into precise, reviewable article changes.

Every change is ``{start, end, original, replacement}`` in code-point offsets of
the submitted article, with ``article[start:end] == original``. A change only
touches the words of one quotation, or one reference, so every other character
of the article (the writer's prose, punctuation, line breaks) is preserved.

Replacement Quran words come only from the Quranpedia source via the verifier.
Nothing here uses AI output. Changes are *proposals*: the browser applies only
the ones the editor approves.
"""

from __future__ import annotations

import re

from . import arabic
from .references import Reference
from .surahs import NAMES

_DIGITS_AR = str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩")
_NUM_RANGE = re.compile(r"[0-9٠-٩]+(?:\s*[-–—]\s*[0-9٠-٩]+)?")
_CLOSERS = "﴾﴿}»\"”)"


def _apply_edits(quote: str, edits: list[tuple[int, int, list[str]]]) -> tuple[int, int, str] | None:
    """Apply token edits to ``quote``; return (rel_start, rel_end, replacement) covering the changed region."""
    toks = arabic.tokenize(quote)
    if len({(t.start, t.end) for t in toks}) != len(toks):
        return None  # expanded ligature (e.g. ﷺ): token ↔ character mapping is not one-to-one
    n = len(toks)
    pieces: list[tuple[int, int, str]] = []
    for i0, i1, words in edits:
        if i0 < i1:  # replace or delete
            s, e = toks[i0].start, toks[i1 - 1].end
            text = " ".join(words)
            if words and i1 < n and toks[i1].start == e:  # the next word was written joined (يَٰٓأَيُّهَا): keep it a separate word
                text += " "
            if not words:  # delete: also remove one adjacent separator space
                if e < len(quote) and quote[e] == " ":
                    e += 1
                elif s > 0 and quote[s - 1] == " ":
                    s -= 1
            pieces.append((s, e, text))
        elif words:  # insert before token i0 (or after the last token)
            if i0 < n:
                pieces.append((toks[i0].start, toks[i0].start, " ".join(words) + " "))
            else:
                pieces.append((toks[-1].end, toks[-1].end, " " + " ".join(words)))
    if not pieces:
        return None
    pieces.sort()
    for a, b in zip(pieces, pieces[1:]):
        if b[0] < a[1]:
            return None  # overlapping edits: refuse rather than guess
    lo, hi = pieces[0][0], max(p[1] for p in pieces)
    out, pos = [], lo
    for s, e, text in pieces:
        out.append(quote[pos:s])
        out.append(text)
        pos = e
    out.append(quote[pos:hi])
    return lo, hi, "".join(out)


def _range_text(a0: int, a1: int, arabic_digits: bool, dash: str = "-") -> str:
    t = str(a0) if a0 == a1 else f"{a0}{dash}{a1}"
    return t.translate(_DIGITS_AR) if arabic_digits else t


def format_reference(original: Reference | None, surah: int, a0: int, a1: int) -> str:
    """Corrected reference text that keeps the writer's style where possible."""
    name = NAMES.get(surah, str(surah))
    if original is None:
        return f"{name}: {_range_text(a0, a1, False)}"
    text = original.text
    arabic_digits = bool(re.search(r"[٠-٩]", text))
    dash_m = re.search(r"[-–—]", text)
    dash = dash_m.group(0) if dash_m else "-"
    new_range = _range_text(a0, a1, arabic_digits, dash)
    numeric_form = bool(re.match(r"^\s*[0-9٠-٩]{1,3}\s*:", text))
    if numeric_form:
        sur = str(surah).translate(_DIGITS_AR) if arabic_digits else str(surah)
        return f"{sur}:{new_range}"
    if original.surah == surah:
        matches = list(_NUM_RANGE.finditer(text))
        if matches:
            m = matches[-1]
            return text[:m.start()] + new_range + text[m.end():]
        sep = "، الآية " if text.strip().startswith("سورة") else ": "
        return text + sep + new_range
    return f"{name}: {new_range}"


def _source_meta(src: dict) -> dict:
    return {
        "surah": src["surah"],
        "surah_name": src["surah_name"],
        "ayah_start": src["ayah_start"],
        "ayah_end": src["ayah_end"],
        "label": src["label"],
        "source_urls": [seg["page_url"] for seg in src["segments"]],
        "source_api_urls": [seg["api_url"] for seg in src["segments"]],
    }


def build_changes(article: str, finding: dict, cand_start: int, ref: Reference | None) -> tuple[list[dict], dict]:
    """Proposed changes for one finding, and a summary of why/why not."""
    fid = finding["id"]
    prop = finding.get("proposal") or {"status": "review_only", "edits": [], "vocalize": [], "script": [], "reason": ""}
    src = finding.get("source")
    changes: list[dict] = []
    summary = {"status": prop["status"], "reason": prop.get("reason", "")}
    quote = finding["quote"]

    def quote_change(kind: str, edits, reason: str, optional: bool) -> dict | None:
        res = _apply_edits(quote, edits)
        if res is None:
            return None
        lo, hi, repl = res
        s, e = cand_start + lo, cand_start + hi
        if article[s:e] == repl:
            return None
        full_after = quote[:lo] + repl + quote[hi:]
        return {"id": f"{fid}-{kind}", "finding_id": fid, "kind": kind, "optional": optional,
                "start": s, "end": e, "original": article[s:e], "replacement": repl,
                "quote_before": quote, "quote_after": full_after, "reason": reason, **_source_meta(src)}

    location_certain = src is not None and prop["status"] in ("proposed", "none_needed")
    if location_certain and prop["status"] == "proposed":
        ch = quote_change("wording", prop["edits"], prop.get("reason") or "تصحيح ألفاظ الاقتباس وفق نص المصحف.", False)
        if ch:
            if arabic.letters(ch["original"]) == arabic.letters(ch["replacement"]):
                # Same letters: only the vocalization differs. Printed mushafs differ in some
                # marks (e.g. idgham shadda), so this is flagged as a check, not a certain error.
                ch["id"], ch["kind"] = f"{fid}-diacritics", "diacritics"
            changes.append(ch)
        else:
            summary.update(status="review_only", reason="تعذّر بناء تصحيح آمن لهذا المقطع؛ يُراجع يدويًا.")
            location_certain = False
    if location_certain and prop.get("script"):
        ch = quote_change("script", prop["script"],
                          "اختياري: كتابة الكلمات بالرسم الإملائي المعتمد في قرآنبيديا بدل الرسم العثماني. رسمك الحالي صحيح، وهذا تنسيق وليس تصحيح خطأ.", True)
        if ch:
            changes.append(ch)
    if location_certain and prop.get("vocalize"):
        ch = quote_change("vocalize", prop["vocalize"], "اختياري: كتابة الاقتباس بضبط المصحف الكامل. النص الحالي صحيح الحروف، وهذا تنسيق وليس تصحيح خطأ.", True)
        if ch:
            changes.append(ch)

    # reference corrections, only when the quotation's location is certain
    r = finding["reference"]
    if location_certain:
        a0, a1 = src["ayah_start"], src["ayah_end"]
        if r["status"] == "incorrect" and ref is not None:
            repl = format_reference(ref, src["surah"], a0, a1)
            if repl != ref.text:
                changes.append({"id": f"{fid}-reference", "finding_id": fid, "kind": "reference", "optional": False,
                                "start": ref.start, "end": ref.end, "original": ref.text, "replacement": repl,
                                "reason": r["message"], **_source_meta(src)})
        elif r["status"] == "uncertain" and ref is not None and ref.valid and ref.surah == src["surah"] and ref.ayah_start is not None:
            repl = format_reference(ref, src["surah"], a0, a1)
            if repl != ref.text:
                changes.append({"id": f"{fid}-reference", "finding_id": fid, "kind": "reference", "optional": False,
                                "start": ref.start, "end": ref.end, "original": ref.text, "replacement": repl,
                                "reason": r["message"], **_source_meta(src)})
        elif r["status"] == "missing":
            pos = finding["end"]
            closed = 0
            while pos < len(article) and article[pos] in _CLOSERS and closed < 2:
                pos += 1
                closed += 1
            label = format_reference(None, src["surah"], a0, a1)
            repl = f" [{label}]" if closed else f" ({label})"
            changes.append({"id": f"{fid}-reference-add", "finding_id": fid, "kind": "reference_add", "optional": True,
                            "start": pos, "end": pos, "original": "", "replacement": repl,
                            "reason": "اختياري: إضافة إحالة الموضع كما في المصحف.", **_source_meta(src)})
    if not changes and summary["status"] == "none_needed" and r["status"] in ("incorrect", "uncertain"):
        summary.update(status="review_only", reason=r["message"])
    return changes, summary

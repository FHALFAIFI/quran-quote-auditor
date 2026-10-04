"""Unit tests for the OCR benchmark scorer (eval/ocr/score_ocr.py). Tiny synthetic strings only: no images, no engine."""

import importlib.util
import json
import random
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("score_ocr", ROOT / "eval" / "ocr" / "score_ocr.py")
so = importlib.util.module_from_spec(_spec)
sys.modules["score_ocr"] = so  # dataclasses look the module up by name
_spec.loader.exec_module(so)

PROSE = "قال الكاتب في مقاله"
VERSE = "فإن مع العسر يسرا"


def naive_lev(a, b):
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j - 1] + (ca != cb), prev[j] + 1, cur[j - 1] + 1))
        prev = cur
    return prev[-1]


def span_of(text, part, surah=94, ayah=5):
    s = text.index(part)
    return {"start": s, "end": s + len(part), "surah": surah, "ayah_start": ayah}


def test_levenshtein_matches_naive_dp():
    rnd = random.Random(7)
    alphabet = "ابتثجح ُ"
    for _ in range(300):
        a = "".join(rnd.choice(alphabet) for _ in range(rnd.randint(0, 70)))
        b = "".join(rnd.choice(alphabet) for _ in range(rnd.randint(0, 70)))
        assert so.levenshtein(a, b) == naive_lev(a, b), (a, b)


def test_words_ignore_punctuation_tatweel_and_unify_digits():
    w = so.words("﴿فإن مع العســر يسرا﴾ [الشرح: ٥]")
    assert [x.key for x in w] == ["فإن", "مع", "العسر", "يسرا", "الشرح", "5"]
    assert so.words("الشرح: 5")[-1].key == "5"


def test_identical_text_scores_zero():
    gt = f"{PROSE}: ﴿{VERSE}﴾"
    r = so.score_page(gt, gt, [span_of(gt, VERSE)], set())
    rates = so.rates(r["counts"])
    assert rates["cer_strict"] == 0 and rates["wer_letters"] == 0 and rates["wer_in_quran_spans"] == 0
    assert r["spans"][0]["word_perfect"] is True


def test_cer_and_wer_overall():
    gt = "كتب الطالب الدرس"
    ocr = "كتب الطالب الدرسى"  # one extra letter in one word
    r = so.rates(so.score_page(gt, ocr, [], set())["counts"])
    assert r["cer_letters"] == pytest.approx(1 / len(gt))
    assert r["wer_letters"] == pytest.approx(1 / 3)


def test_error_inside_span_is_projected_through_alignment():
    gt = f"{PROSE}: {VERSE}"
    # A word is dropped in the prose (shifts every later word) and one word of the verse is misread.
    ocr = "قال الكاتب مقاله: فإن مع العسير يسرا"
    r = so.score_page(gt, ocr, [span_of(gt, VERSE)], set())
    c, rates = r["counts"], so.rates(r["counts"])
    assert c["span_words"] == 4 and c["span_sub"] == 1 and c["span_del"] == 0
    assert rates["wer_in_quran_spans"] == pytest.approx(1 / 4)
    assert rates["wer_outside_quran_spans"] == pytest.approx(1 / 4)  # the dropped «في» out of 4 prose words
    assert r["spans"][0]["word_perfect"] is False


def test_insertion_counts_inside_span_only_between_two_span_words():
    gt = f"{PROSE} {VERSE}"
    inside = so.score_page(gt, "قال الكاتب في مقاله فإن مع و العسر يسرا", [span_of(gt, VERSE)], set())["counts"]
    assert inside["span_ins"] == 1
    at_edge = so.score_page(gt, "قال الكاتب في مقاله و فإن مع العسر يسرا", [span_of(gt, VERSE)], set())["counts"]
    assert at_edge["ins"] == 1 and at_edge["span_ins"] == 0


def test_deleted_span_word():
    gt = VERSE
    r = so.score_page(gt, "فإن العسر يسرا", [span_of(gt, VERSE)], set())
    assert r["counts"]["span_del"] == 1 and r["spans"][0]["wer"] == pytest.approx(1 / 4)


def test_diacritic_error_rate_on_aligned_letters():
    gt = "إِنَّ مَعَ"
    ocr = "إِنَ مُعَ"  # shadda lost on ن; fatha read as damma on م
    c = so.score_page(gt, ocr, [], set())["counts"]
    assert c["diacritic_letters_wrong"] == 2
    assert c["diacritic_marks_missing"] == 2  # shadda, fatha
    assert c["diacritic_marks_extra"] == 1  # damma
    # Letters-level words are equal, so the letters WER is 0 while the strict WER is not.
    r = so.rates(c)
    assert r["wer_letters"] == 0 and r["wer_strict"] == 1.0
    assert r["diacritic_error_rate"] == pytest.approx(2 / c["diacritic_letters_compared"])


def test_diacritics_compared_inside_a_substituted_word():
    c = so.diacritic_compare("العُسْرِ", "العَسِير")  # a different word: only letters aligned as matches are compared
    assert c["letters_compared"] >= 2 and c["letters_wrong"] >= 2


def test_plausible_wrong_word_uses_lexicon_and_skips_spelling_variants():
    gt = "فإن مع العسر يسرا"
    lex = {so.words("العصر")[0].fold}
    c = so.score_page(gt, "فان مع العصر يسرا", [span_of(gt, gt)], lex)["counts"]
    assert c["sub"] == 2
    assert c["plausible_wrong"] == 1 and c["span_plausible_wrong"] == 1  # العصر is in the list
    assert c["sub_spelling_variant"] == 1  # فان folds to the same form as فإن (hamza seat), so it is not "plausible wrong"
    assert so.rates(c)["plausible_wrong_share_of_substitutions"] == 0.5


def test_lexicon_from_cache_and_ground_truth(tmp_path):
    cache = tmp_path / "hafs.json"
    cache.write_text(json.dumps({"ayahs": [{"surah": 103, "number": 1, "text": "وَالْعَصْرِ"}]}), encoding="utf-8")
    lex, info = so.build_lexicon(["كلمة أخرى"], cache)
    assert so.words("والعصر")[0].fold in lex and so.words("أخرى")[0].fold in lex
    assert info["approximate"] is True and info["quran_forms"] == 1
    lex2, info2 = so.build_lexicon(["كلمة"], tmp_path / "missing.json")
    assert info2["quran_cache"].startswith("not readable") and info2["quran_forms"] == 0


def _manifest(gt_text, spans, **rights):
    r = {"source": "synthetic test string", "licence": "test only", "cleared_by": "nobody (synthetic)", "cleared_on": "2026-10-04",
         "may_commit_image": False, "may_commit_ground_truth": True}
    r.update(rights)
    return {"schema_version": 1, "set_id": "unit", "pages": [
        {"page_id": "p1", "category": "book", "script": "naskh", "diacritics": "none", "ground_truth": gt_text,
         "ground_truth_checked_by": ["typist A", "checker B"], "rights": r, "quran_spans": spans}]}


def test_validate_manifest_rejects_bad_spans_and_rights(tmp_path):
    gt = f"{PROSE}: {VERSE}"
    assert so.validate_manifest(_manifest(gt, [span_of(gt, VERSE)]), tmp_path) == []
    errs = so.validate_manifest(_manifest(gt, [{"start": 0, "end": 999, "surah": 94, "ayah_start": 5}]), tmp_path)
    assert any("outside the ground truth" in e for e in errs)
    errs = so.validate_manifest(_manifest(gt, [{"start": 0, "end": 3, "surah": 94, "ayah_start": 9}]), tmp_path)
    assert any("not in surah 94" in e for e in errs)
    m = _manifest(gt, [])
    m["pages"][0]["ground_truth_checked_by"] = ["one person", "one person"]
    del m["pages"][0]["rights"]["cleared_on"]
    errs = so.validate_manifest(m, tmp_path)
    assert any("two different people" in e for e in errs) and any("cleared_on" in e for e in errs)


def test_validate_manifest_keeps_uncleared_files_out_of_the_repository(tmp_path):
    m = _manifest("نص", [], may_commit_ground_truth=False)
    m["pages"][0]["image_path"] = "eval/ocr/pages/p1.png"
    errs = so.validate_manifest(m, so.ROOT, manifest_path=so.ROOT / "eval" / "ocr" / "m.json")
    assert any("may_commit_image" in e for e in errs)
    assert any("may_commit_ground_truth" in e for e in errs)
    # The same page kept outside the repository is fine.
    assert so.validate_manifest(m, tmp_path, manifest_path=tmp_path / "m.json") == []


def test_score_whole_run_counts_missing_pages_and_reads_time_and_cost(tmp_path):
    gt = f"{PROSE}: {VERSE}"
    m = _manifest(gt, [span_of(gt, VERSE)])
    m["pages"].append(dict(m["pages"][0], page_id="p2", category="phone_photo"))
    run = {"engine": {"name": "synthetic"}, "pages": [
        {"page_id": "p1", "text": gt, "seconds": 2.0, "cost": {"amount": 0.5, "currency": "USD"}}]}
    rep = so.score(m, run, tmp_path, None)
    assert rep["pages_failed"] == [{"page_id": "p2", "reason": "missing from run"}]
    assert rep["overall"]["rates"]["wer_letters"] == pytest.approx(0.5)  # p2 counts as all words deleted
    assert rep["by_group"]["category"]["book"]["rates"]["wer_letters"] == 0
    assert rep["by_group"]["category"]["phone_photo"]["rates"]["wer_letters"] == 1
    tc = rep["time_and_cost"]
    assert tc["pages_with_time"] == 1 and tc["seconds_total"] == 2.0
    assert tc["cost_total_by_currency"] == {"USD": 0.5} and tc["pages_with_cost"] == 1


def test_cli_refuses_invalid_manifest(tmp_path, capsys):
    mp, rp = tmp_path / "m.json", tmp_path / "r.json"
    mp.write_text(json.dumps({"schema_version": 1, "pages": []}), encoding="utf-8")
    rp.write_text(json.dumps({"pages": []}), encoding="utf-8")
    assert so.main(["--manifest", str(mp), "--run", str(rp)]) == 2


def test_cli_scores_valid_manifest(tmp_path, capsys):
    gt = f"{PROSE}: {VERSE}"
    mp, rp, out = tmp_path / "m.json", tmp_path / "r.json", tmp_path / "rep.json"
    mp.write_text(json.dumps(_manifest(gt, [span_of(gt, VERSE)]), ensure_ascii=False), encoding="utf-8")
    rp.write_text(json.dumps({"engine": {"name": "synthetic"}, "pages": [{"page_id": "p1", "text": gt}]}, ensure_ascii=False), encoding="utf-8")
    assert so.main(["--manifest", str(mp), "--run", str(rp), "--no-quran-lexicon", "--out", str(out)]) == 0
    assert json.loads(out.read_text(encoding="utf-8"))["overall"]["rates"]["wer_in_quran_spans"] == 0


def test_manifest_schema_is_valid_json_and_names_the_rights_fields():
    schema = json.loads((ROOT / "eval" / "ocr" / "manifest.schema.json").read_text(encoding="utf-8"))
    rights = schema["$defs"]["rights"]["required"]
    for f in ("source", "licence", "cleared_by", "cleared_on", "may_commit_image", "may_commit_ground_truth"):
        assert f in rights


def test_run_tesseract_exits_clearly_when_tesseract_is_missing(tmp_path, monkeypatch, capsys):
    spec = importlib.util.spec_from_file_location("run_tesseract", ROOT / "eval" / "ocr" / "run_tesseract.py")
    rt = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rt)
    monkeypatch.setattr(rt.shutil, "which", lambda name: None)
    mp = tmp_path / "m.json"
    mp.write_text(json.dumps(_manifest("نص", [])), encoding="utf-8")
    assert rt.main(["--manifest", str(mp), "--pages-dir", str(tmp_path), "--out", str(tmp_path / "run.json")]) == 3
    assert "tesseract is not installed" in capsys.readouterr().err
    assert not (tmp_path / "run.json").exists()

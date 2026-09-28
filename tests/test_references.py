import pytest

from app.references import find_references


@pytest.mark.parametrize(
    "text,surah,a1,a2",
    [
        ("[البقرة: 255]", 2, 255, None),
        ("(البقرة: ٢٥٥)", 2, 255, None),
        ("البقرة/255", 2, 255, None),
        ("سورة آل عمران، الآية 103", 3, 103, None),
        ("سورة البقرة آية 255-257", 2, 255, 257),
        ("الآية 5 من سورة المائدة", 5, 5, None),
        ("2:255", 2, 255, None),
        ("[2:255–257]", 2, 255, 257),
        ("(الانعام: 12)", 6, 12, None),
        ("سورة براءة: 40", 9, 40, None),
        ("في سورة الكهف", 18, None, None),
    ],
)
def test_reference_forms(text, surah, a1, a2):
    refs = find_references(text)
    assert len(refs) == 1, refs
    r = refs[0]
    assert (r.surah, r.ayah_start, r.ayah_end) == (surah, a1, a2)
    assert r.valid
    assert text[r.start:r.end] == r.text


def test_out_of_range_is_flagged():
    (r,) = find_references("[طه: 141]")
    assert not r.valid and "135" in r.problems[0]
    (r,) = find_references("115:1")
    assert not r.valid


def test_bare_common_word_is_not_a_reference():
    # "النور" and "محمد" are ordinary words; without a number they are not references
    assert find_references("اهتدى بالنور وجاء محمد إلى البيت") == []

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


def test_ayah_number_written_as_an_ordinal_word():
    """Found in the internal walkthrough of 4 Oct 2026: «وهي الآية الخامسة عشرة من سورة النور» was not read as a reference."""
    from app.references import find_references

    cases = {"وهي الآية الخامسة عشرة من سورة النور.": (24, 15), "في الآية الأولى من سورة الفاتحة": (1, 1),
             "الآية الحادية والعشرون من سورة الأحزاب": (33, 21), "كما في الآية الثانية عشرة من سورة لقمان": (31, 12)}
    for text, (s, a) in cases.items():
        (r,) = find_references(text)
        assert (r.surah, r.ayah_start, r.valid) == (s, a, True), text
    # an ordinal outside the named surah is a reference with a problem, not silently accepted
    (r,) = find_references("الآية التاسعة والتسعون من سورة الفاتحة")
    assert not r.valid
    # ordinary prose with an ordinal is not a reference
    assert find_references("وهذه هي الحالة الخامسة عشرة من سورة حياته") == []
    assert find_references("في الآية الخامسة من كتاب الأدب") == []

from app import arabic


def test_levels_are_distinct():
    src = "﻿اللَّهُ لَا إِلَٰهَ إِلَّا هُوَ ۚ"
    assert arabic.literal(src) == "اللَّهُ لَا إِلَٰهَ إِلَّا هُوَ"  # BOM and waqf mark removed
    assert arabic.letters(src) == "الله لا إله إلا هو"  # dagger alef removed with diacritics
    assert arabic.folded(src) == "الله لا اله الا هو"


def test_folding_variants():
    assert arabic.folded("مُوسَىٰ") == arabic.folded("موسي")
    assert arabic.folded("رحمة") == arabic.folded("رحمه")
    assert arabic.folded("ٱلْحَمْدُ") == "الحمد"
    assert arabic.folded("الـــحمد") == "الحمد"  # tatweel


def test_tokenize_keeps_offsets():
    text = "قال: ﴿إِنَّ اللَّهَ مَعَ الصَّابِرِينَ﴾ (البقرة 153)"
    toks = arabic.tokenize(text)
    assert [t.fold for t in toks] == ["قال", "ان", "الله", "مع", "الصابرين", "البقره"]
    for t in toks:
        assert text[t.start:t.end] == t.raw


def test_fold_with_map_maps_back():
    text = "سُورَةُ البَقَرَةِ ٢٥٥"
    f, idx = arabic.fold_with_map(text)
    assert f == "سوره البقره 255"
    assert text[idx[0]] == "س" and text[idx[-1]] == "٥"

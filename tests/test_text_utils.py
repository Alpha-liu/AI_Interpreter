"""字幕文本切分与整句对齐。"""
from ai_interpreter.text_utils import split_aligned, split_lines


def test_split_lines_respects_bounds_and_keeps_text():
    text = "第一句内容。第二句内容。"
    parts = split_lines(text, 8)
    assert parts
    assert all(len(p) <= 8 for p in parts)
    assert "".join(parts) == text


def test_split_aligned_one_sentence_each():
    pairs = split_aligned("第一句。第二句。第三句。", "First. Second. Third.")
    assert len(pairs) == 3
    assert [t for _, t in pairs] == ["First.", "Second.", "Third."]


def test_split_aligned_keeps_order():
    src = "A one. A two. A three. A four."
    tgt = "甲一。甲二。"
    pairs = split_aligned(src, tgt)
    assert len(pairs) == 2
    assert "".join(s for s, _ in pairs).replace(" ", "") == src.replace(" ", "")
    assert "".join(t for _, t in pairs) == tgt


def test_single_sentence_pair_is_not_fragmented():
    src = "a single english sentence that is fairly long but has only one sentence."
    tgt = "只有一句中文，但是长度也不算短。"
    assert len(split_aligned(src, tgt)) == 1

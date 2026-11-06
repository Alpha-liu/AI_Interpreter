# -*- coding: utf-8 -*-
"""字幕文本切分工具：按“整句”切分并让原文/译文整句对齐。

为什么不再按字数硬切
--------------------
旧实现把原文、译文各自按字符比例切片再配对，结果一行中文可能对上不相干的
半句英文（词量/语义对不上），而且切得非常碎。现在改为：

1. 两边各自按句末标点切成“整句”（单句过长时才按子句再分，且不切碎正常句子）。
2. 句数不同时，把句中单位按**整句分组**到相同条数（`_group_units`），
   分组只合并相邻整句、绝不在句子中间下刀，顺序严格保持。
3. 最终一一配对，每条字幕都是一段语义完整的原文 + 对应译文。

对外接口：
    split_lines(text, max_chars)        -> [短句, ...]（无配对需求时使用）
    split_aligned(src, tgt, max_chars)  -> [(src句, tgt句), ...]（条数对齐）
"""

import re

# 句末标点：中文标点直接切；英文 . ! ? 仅在后面跟空格或结尾时切（避免切开 3.5、U.S 等）
_SENT_RE = re.compile(r'(?<=[。！？!?；;…])|(?<=[.!?])(?=\s|$)')
# 次级标点
_CLAUSE_RE = re.compile(r'(?<=[，,、：:—])')

# 单句超过该长度才按子句再分；正常句子不会被切碎
UNIT_MAX_CHARS = 80


def _hard_split(text, max_chars):
    out = []
    s = (text or "").strip()
    while len(s) > max_chars:
        window = s[:max_chars]
        sp = window.rfind(" ")
        cut = sp + 1 if sp >= max_chars // 2 else max_chars
        piece = s[:cut].strip()
        if piece:
            out.append(piece)
        s = s[cut:].strip()
    if s:
        out.append(s)
    return out


def _pack_clauses(sentence, max_chars):
    """把一个过长句子按子句贪心打包成若干 <= max_chars 的片段。"""
    clauses = [c for c in _CLAUSE_RE.split(sentence) if c]
    out = []
    buf = ""
    for clause in clauses:
        if len(buf) + len(clause) <= max_chars:
            buf += clause
            continue
        if buf.strip():
            out.append(buf.strip())
            buf = ""
        if len(clause) <= max_chars:
            buf = clause
        else:
            out.extend(_hard_split(clause, max_chars))
    if buf.strip():
        out.append(buf.strip())
    return out


def _units(text, max_chars):
    """把文本切成“整句”单位；单句过长才按子句再分。"""
    text = (text or "").strip()
    if not text:
        return []
    units = []
    for sent in _SENT_RE.split(text):
        sent = sent.strip()
        if not sent:
            continue
        if len(sent) <= max_chars:
            units.append(sent)
        else:
            units.extend(_pack_clauses(sent, max_chars))
    return units or [text]


def _join(parts):
    """拼接若干片段；中英混排时在英文之间补空格。"""
    out = ""
    for p in parts:
        p = (p or "").strip()
        if not p:
            continue
        if not out:
            out = p
        elif out[-1].isascii() and p[0].isascii():
            out += " " + p
        else:
            out += p
    return out


def _group_units(units, n):
    """把有序的整句单位合并成 n 组（只合并相邻整句，顺序不变）。"""
    m = len(units)
    if n <= 1:
        return [_join(units)]
    if n >= m:
        return list(units)

    lengths = [max(len(u), 1) for u in units]
    total = float(sum(lengths))
    avg = total / n

    groups = []
    i = 0
    while i < m:
        groups_left = n - len(groups)
        if groups_left <= 1:
            groups.append(_join(units[i:]))
            break
        remaining = m - i
        # 给后面每组至少留 1 个整句
        max_take = remaining - (groups_left - 1)
        take = []
        take_len = 0
        while i < m and len(take) < max_take:
            take.append(units[i])
            take_len += lengths[i]
            i += 1
            if take_len >= avg:
                break
        groups.append(_join(take))
    return groups


def split_lines(text, max_chars=80):
    """把一段文本切成不超过 max_chars 的短句列表（无配对需求时使用）。"""
    text = (text or "").strip()
    if not text:
        return []
    max_chars = max(4, int(max_chars))
    if len(text) <= max_chars:
        return [text]
    return _units(text, max_chars)


def split_aligned(src, tgt, max_chars=UNIT_MAX_CHARS):
    """把原文/译文切成一一对应的整句组。

    返回 [(src_piece, tgt_piece), ...]；任一侧为空时对应位置为空串。
    每条都是一段语义完整的原文 + 对应译文，不会出现句中错配。
    """
    src = (src or "").strip()
    tgt = (tgt or "").strip()
    if not src and not tgt:
        return []
    if not tgt:
        return [(s, "") for s in _units(src, max_chars)]
    if not src:
        return [("", t) for t in _units(tgt, max_chars)]

    a = _units(src, max_chars)
    b = _units(tgt, max_chars)
    n = min(len(a), len(b))
    ga = _group_units(a, n)
    gb = _group_units(b, n)
    # 防御：两侧长度对齐
    if len(ga) != len(gb):
        n = min(len(ga), len(gb))
        ga, gb = ga[:n], gb[:n]
    return list(zip(ga, gb))

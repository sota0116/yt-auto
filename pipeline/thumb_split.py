# サムネの字を「語の切れ目」で2行に割る部品（2026-11-04 新設）
# ・本人「サムネのテキストが日本語的に意味わからなかったり、文脈が繋がってないことが多いから変える」（2026-11-04）
# ・前の割り方（最後の2〜3字で割る）は「最／下位」「なぜ辞／める?」のように語の途中で切れていた
# ・割ってよい所：助詞・助動詞・副詞・接続詞・連体詞の後ろ、動詞・形容詞のすぐ後ろに名詞が来る所（次が助詞・助動詞・接尾辞・記号なら割らない）
#   その中で、2行の字数が一番そろう所。同じなら後ろ（下の行が短い方）。数字があれば数字の前で割る（語の切れ目の時だけ）
# ・sudachi が無い環境では None を返す（呼ぶ側が前の割り方を使う）
import threading

try:
    from sudachipy import dictionary, tokenizer as _tk
    _TOK = dictionary.Dictionary(dict="full").tokenizer()
    _MODE = _tk.Tokenizer.SplitMode.C
except Exception:
    _TOK = None
_LOCK = threading.Lock()  # tokenizer は同時に使えない

_AFTER_OK = ("助詞", "助動詞", "副詞", "接続詞", "連体詞", "感動詞")
_NEXT_NG = ("助詞", "助動詞", "接尾辞", "補助記号")


def tokens(text):
    """(語, 始まり, 終わり, 品詞) の並び。sudachi が無ければ None"""
    if _TOK is None:
        return None
    with _LOCK:
        ms = list(_TOK.tokenize(text, _MODE))
    res, pos = [], 0
    for m in ms:
        w = m.surface()
        res.append((w, pos, pos + len(w), m.part_of_speech()[0]))
        pos += len(w)
    return res


def cuts(text):
    """(文節の切れ目, 語の切れ目＝次が助詞・助動詞・接尾辞・記号でない所) の2つの集合。sudachi が無ければ None"""
    tk = tokens(text)
    if tk is None:
        return None
    phrase, word = set(), set()
    for a, b in zip(tk, tk[1:]):
        if b[3] in _NEXT_NG:
            continue
        word.add(b[1])
        if a[3] in _AFTER_OK or (a[3] in ("動詞", "形容詞") and b[3] in ("名詞", "代名詞")):
            phrase.add(b[1])
    return phrase, word


def split2(t):
    """t を2行に割る。割らない方がよい時は [t]。sudachi が無い時は None"""
    c = cuts(t)
    if c is None:
        return None
    phrase, word = c
    n = len(t)
    if n <= 4:
        return [t]
    d = next((i for i, ch in enumerate(t) if ch.isdigit()), -1)
    if d > 0 and d in phrase:
        return [t[:d], t[d:]]
    for pool in (phrase, word):
        pool = [p for p in pool if 2 <= p <= n - 2]
        if pool:
            p = min(pool, key=lambda p: (abs(p - (n - p)), -p))
            return [t[:p], t[p:]]
    return [t]


def word_cut(text, start, end):
    """text[start:end] が語の切れ目にそろっているか（sudachi が無ければ True）"""
    c = cuts(text)
    if c is None:
        return True
    tk = tokens(text)
    ok = {t[1] for t in tk} | {len(text)}
    return start in ok and end in ok

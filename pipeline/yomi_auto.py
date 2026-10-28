# 読みの自動点検（2026-10-27 から）：VOICEVOX の読みと、辞書（Sudachi full）の読みを全カットで照らし、食い違う語だけを出す
#   python -X utf8 pipeline\yomi_auto.py <作業フォルダ> --ch spi [--json 出力.json]
# ・目で171カットのカナを読む点検（make_voice_vv.py kana）の代わりに、怪しい語だけに絞る。最後の判定は Claude か本人がする
#   （辞書の方が間違える語もある。例：一粒万倍日をヒトツブマンバイヒ。チャンネルの yomi.json に入れた語は合格にする）
# ・同じ字で読みが変わる語（家・米・上・方・日 など）は、食い違いがなくても「念のため」に出す
# ・見つけた読み違いは、channels\<ch>\yomi.json の dict（言葉の区切りとアクセントも直る）か replace に1行足す。カットだけの直しは tts_text
# ・終了コード：食い違いがあれば1（念のための語だけなら0）
import argparse, difflib, json, os, re, sys, urllib.parse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import make_voice_vv as vv

try:
    from sudachipy import dictionary, tokenizer
except ImportError:
    sys.exit("【止まりました】sudachipy がありません：python -m pip install sudachipy sudachidict_full")

KANJI = re.compile(r"[一-龥々〆ヵヶ]")
# 同じ字で読みが変わり、VOICEVOX が文脈で取り違えた実績か、取り違えやすい語（見つけたら足す）
RISKY = ["家", "米", "上", "下", "方", "生", "今日", "明日", "一日", "大人", "人気", "最中", "市場", "寒気", "上手", "下手",
         "色紙", "目下", "大家", "風車", "帰す", "返す", "重なり", "重なる", "吉", "盛り", "開く", "空く", "辛い", "初日", "十分",
         "一行", "見物", "仕業", "末", "頭", "本日", "封筒", "札"]
# 辞書（Sudachi）の方が間違えるか、どちらでも正しい組み合わせ（表記：声の読み）。見つけたら足す
OK_PAIR = {"数": ["カズ"], "月": ["ツキ"], "言う": ["イウ", "イオ"], "吉日": ["キチジツ"], "何": ["ナニ"], "その後": ["ソノゴ"],
           "一粒万倍日": ["イチリュウマンバイビ"], "七五三": ["シチゴサン"], "日": ["ニチ", "ビ", "ヒ", "カ"]}
LONG = {"オ": "オウ", "エ": "エイ"}  # 長い音の書き方の違いはそろえる
VOWEL = {}
for row, v in [("アカサタナハマヤラワガザダバパァャ", "ア"), ("イキシチニヒミリギジヂビピィ", "イ"), ("ウクスツヌフムユルグズヅブプゥュ", "ウ"),
               ("エケセテネヘメレゲゼデベペェ", "エ"), ("オコソトノホモヨロヲゴゾドボポォョ", "オ")]:
    for ch in row:
        VOWEL[ch] = v


def norm(s, prev="", keep=None):
    """カナをそろえる：ー→前の母音／オウ・オオ→オオ、エイ→エエ／ヲ→オ・ヅ→ズ・ヂ→ジ。カナ以外は落とす。
    keep に配列を渡すと、そろえた字ごとに元の字の位置を入れる（声の読みを元のカナで見せるため）"""
    out = []
    last = prev
    for k, ch in enumerate(s):
        if ch == "ー":
            ch = VOWEL.get(last, "")
        ch = {"ヲ": "オ", "ヅ": "ズ", "ヂ": "ジ"}.get(ch, ch)
        if not re.match(r"[ァ-ヴ]", ch or ""):
            continue
        v = VOWEL.get(last)
        if ch == "ウ" and v == "オ":
            ch = "オ"
        elif ch == "イ" and v == "エ":
            ch = "エ"
        out.append(ch)
        if keep is not None:
            keep.append(k)
        last = ch
    return "".join(out)


def expected(tok, text):
    """辞書の読みを、語ごとに（表記・読み・始まりの位置）で返す。助詞のハ・ヘは声の音（ワ・エ）にする"""
    rows, buf = [], ""
    for m in tok.tokenize(text, tokenizer.Tokenizer.SplitMode.C):
        surf, r, pos = m.surface(), m.reading_form(), m.part_of_speech()
        if pos[0] == "補助記号" or pos[0] == "空白":
            continue
        particle = pos[0] == "助詞" and surf in ("は", "へ")
        if pos[0] == "助詞" and surf == "は":
            r = "ワ"
        elif pos[0] == "助詞" and surf == "へ":
            r = "エ"
        if not re.search(r"[ァ-ヴー]", r):  # 読みが取れない（英字・記号）は声の読みをそのまま使う
            r = ""
        n = norm(r, buf[-1:] if buf else "")
        rows.append((surf, r, len(buf), n, particle))
        buf += n
    return rows, buf


def vv_kana(q):
    return "".join(m["text"] for ap in q["accent_phrases"] for m in ap["moras"] + ([ap["pause_mora"]] if ap.get("pause_mora") else []))


def check_cut(tok, sid, text, rep, ok_words):
    q = json.loads(vv.call("/audio_query?" + urllib.parse.urlencode({"text": vv.say(text, rep), "speaker": sid})))
    raw = vv_kana(q)
    idx = []
    got = norm(raw, keep=idx)
    rows, exp = expected(tok, text)
    sm = difflib.SequenceMatcher(None, exp, got, autojunk=False)
    ops = sm.get_opcodes()

    def to_got(i):  # 辞書の読みの位置 → 声の読みの位置
        for tag, i1, i2, j1, j2 in ops:
            if i1 <= i < i2 or (i == i2 and tag == ops[-1][0] and i2 == len(exp)):
                return j1 + (i - i1) if tag == "equal" else j1 + round((i - i1) * (j2 - j1) / max(1, i2 - i1))
        return len(got)

    bad, risky = [], []
    # 助詞の は・へ も見る（2026-10-27 金運おきぬで「レシートはね」をハネ、「財布はね」をハネと読んだ。漢字だけ見ていて見逃した）
    for surf, r, st, n, particle in rows:
        if not (KANJI.search(surf) or particle) or not n:
            continue
        en = st + len(n)
        diff = any(tag != "equal" and i1 < en and i2 > st for tag, i1, i2, j1, j2 in ops)
        g1, g2 = to_got(st), to_got(en)
        heard = got[g1:g2] if en <= len(exp) else ""
        shown = raw[idx[g1]:idx[g2 - 1] + 1] if heard and g2 - 1 < len(idx) else heard
        if diff and heard in [norm(k) for k in OK_PAIR.get(surf, [])]:
            diff = False
        if diff and not any(w in surf or surf in w for w in ok_words):
            bad.append({"語": surf, "辞書の読み": r, "声の読み": shown})
        elif surf in RISKY:
            risky.append({"語": surf, "声の読み": shown})
    return bad, risky, raw


def main():
    a = argparse.ArgumentParser()
    a.add_argument("work")
    a.add_argument("--ch", default="job")
    a.add_argument("--json", default="")
    a.add_argument("--speaker", type=int, default=None, help="話者の番号（yt-auto の外のチャンネル。無ければ台本の voice.speaker）")
    a.add_argument("--yomi", default="", help="読みの表（yomi.json）の場所。yt-auto の外のチャンネル用")
    a = a.parse_args()
    s = json.load(open(os.path.join(a.work, "script.json"), encoding="utf-8"))
    yf = a.yomi or os.path.join(vv.ROOT, "channels", a.ch, "yomi.json")
    if a.speaker is not None or (s.get("voice") or {}).get("speaker") is not None:
        sid = a.speaker if a.speaker is not None else s["voice"]["speaker"]
        rep = {}
        if os.path.exists(yf):  # 表の dict もエンジンに入れる（make_voice_vv.yomi と同じ）
            rep = json.load(open(yf, encoding="utf-8")).get("replace", {})
    else:
        p = vv.profile(a.ch)["voicevox"]
        sid = vv.speaker_id(p["narrator"]["name"], p["narrator"]["style"])
        rep = vv.yomi(a.ch)
    y = json.load(open(yf, encoding="utf-8")) if os.path.exists(yf) else {}
    ok_words = [w["surface"] for w in y.get("dict", [])] + [k for k in y.get("replace", {}) if KANJI.search(k)]
    tok = dictionary.Dictionary(dict="full").tokenizer()
    out, nb = [], 0
    for c in s["cuts"]:
        if not c.get("narration"):
            continue
        text = c.get("tts_text") or c["narration"]
        bad, risky, got = check_cut(tok, sid, text, rep, ok_words)
        if bad or risky:
            out.append({"id": c["id"], "文": text, "声の読み": got, "食い違い": bad, "念のため": risky})
        nb += len(bad)
        for b in bad:
            print(f"{c['id']}  {b['語']}：辞書 {b['辞書の読み']} ／ 声 {b['声の読み']}    {text[:40]}", flush=True)
    seen = {}
    for r in out:
        for k in r["念のため"]:
            seen.setdefault(k["語"], {}).setdefault(k["声の読み"], []).append(r["id"])
    for w, d in seen.items():  # 同じ字で読みが変わる語は、どう読んだかを語ごとに1行で出す（読みが2通り以上ある語は要確認）
        mark = "【2通り】" if len(d) > 1 else ""
        print(f"（念のため）{mark}{w}：" + "／".join(f"{k}×{len(v)}（{','.join(v[:4])}）" for k, v in d.items()))
    dst = a.json or os.path.join(a.work, "voice", "_yomi_auto.json")
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    json.dump({"食い違いの数": nb, "カット": out}, open(dst, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"食い違い {nb} 語（{dst}）。辞書の方が間違っている語もあるので、1語ずつ見て決める")
    sys.exit(1 if nb else 0)


if __name__ == "__main__":
    main()

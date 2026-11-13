# サムネの字が「意味の通る日本語か・文脈がつながっているか」を見る点検（2026-11-04 新設）
#   python -X utf8 pipeline/check_thumb_text.py <作業フォルダ> [--ch job] [--no-llm]
#   python -X utf8 pipeline/check_thumb_text.py --samples <試験材料.json> [--out 結果.json]
# ・本人「サムネのテキストが日本語的に意味わからなかったり、文脈が繋がってないことが多いから変える」（2026-11-04）
# ・形の点検（sudachi）：行の境目・色を変えた語（hl）が語の途中で切れていないか／行の頭が助詞・助動詞でないか（頭の助詞は注意だけ。競合にも「黒幕は／すぐ隣／にいた」がある）
# ・意味の点検（claude -p sonnet）：①字だけで何の話か分かる（主語・対象がある）②上の段と下の段が1文の自然な日本語でつながる
#   ③タイトルと矛盾せず、役が分かれている（タイトル＝何の話か、サムネ＝命令・結果・数の落差・伏せた答え）④フックの型がある
#   決まりの出どころは 調査/サムネ文字調査_2026-11-03/サムネ改善レポート_v1_2026-11-04.md の §2・§5
# ・作業フォルダの時：結果を check_thumb_text.json に書き、NG があれば終了コード1。sudachi が無い環境では形の点検を飛ばす（意味の点検だけ）
# ・--samples：[{"name":..,"ch":..,"script":{script.json と同じ形の項目}}] をまとめて試す（4本ずつ並べて回す）
# ・チャンネル別の項目の形（make_thumb_*.py の読み方に合わせた）
#   job：トップの階層の thumb_top（上の段）・thumb_text（下の段。割り方は thumb_lines、無ければ make_thumb_job.parts と同じ割り方）・thumb_band
#   psy：thumb.lines（[[["語","#色"],..],..]。黄 #FFE234 が色を変えた語）と thumb.lines_b（B案。あれば両方を見る）
#   spi：thumb.top・big・hl　　nihongi：thumb.top・big・hl_top・hl_big
#   okinu：thumb.line1・line2・judge・hl・left_label・right_label（layout の無い前の形は thumb.top・big・hl）
#   kakure・shimei（agent）：作業フォルダの thumb.json の texts（[{"t","y","hl"},..]。y の小さい順に上の段・下の段）。--samples では script の "thumb_json" に入れる（2026-11-04 追加）
import argparse, concurrent.futures, json, os, re, shutil, subprocess, sys, threading, unicodedata

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
YELLOW = "#FFE234"
from thumb_split import split2

try:
    from sudachipy import dictionary, tokenizer as _tk
    _TOK = dictionary.Dictionary(dict="full").tokenizer()
    _MODE = _tk.Tokenizer.SplitMode.C
except Exception:  # クラウドに sudachi が無い時は形の点検を飛ばす
    _TOK = None
_LOCK = threading.Lock()  # sudachi の tokenizer は同時に使えない（--samples は並べて回すため）


def N(t):
    return unicodedata.normalize("NFKC", t or "").strip()


def title_of(s):
    t = s.get("title") or (s.get("titles") or [""])[0]
    return t if isinstance(t, str) else str(t)


def job_parts(t, given, most):
    """make_thumb_job.parts と同じ割り方（語の切れ目。sudachi が無い時だけ数字の所か、最後の2〜3字）。強調の行の番号も返す"""
    if given:
        lines = [N(x) for x in given]
    elif split2(t) is not None:
        lines = split2(t)
    else:
        m = re.search(r"\d", t)
        if m and m.start() > 0:
            lines = [t[:m.start()], t[m.start():]]
        elif len(t) <= 4:
            lines = [t]
        else:
            k = 3 if t.endswith("?") else 2
            lines = [t[:-k], t[-k:]]
    hi = next((i for i, x in enumerate(lines) if re.search(r"\d", x)), len(lines) - 1)
    if len(lines) == 3 and not re.search(r"\d", "".join(lines)):
        hi = 1
    return lines, hi


def extract(s, ch):
    """サムネの字を、案ごとに {name, blocks:[{role, lines, hl}], band} にする。blocks は上から読む順"""
    th = s.get("thumb") if isinstance(s.get("thumb"), dict) else {}
    out = []
    tj = s.get("thumb_json") if isinstance(s.get("thumb_json"), dict) else {}
    if tj.get("texts"):  # kakure・shimei（agent）：作業フォルダの thumb.json の texts を、上（y が小さい順）から読む
        ts = sorted([x for x in tj["texts"] if isinstance(x, dict) and N(x.get("t"))], key=lambda x: x.get("y", 0))
        roles = ["上の段", "下の段（特大）"] if len(ts) == 2 else [f"{i + 1}段目" for i in range(len(ts))]
        blocks = [{"role": r, "lines": N(x["t"]).split("\n"), "hl": [N(w) for w in (x.get("hl") or []) if isinstance(w, str)]}
                  for r, x in zip(roles, ts)]
        out.append({"name": "a", "blocks": blocks, "band": ""})
        return out
    if ch == "job" or (not th and s.get("thumb_text")):
        top, t = N(s.get("thumb_top")), N(s.get("thumb_text"))
        if t:
            lines, hi = job_parts(t, s.get("thumb_lines"), 3)
            blocks = ([{"role": "上の段", "lines": [top], "hl": []}] if top else []) + \
                     [{"role": "下の段（特大）", "lines": lines, "hl": [lines[hi]]}]
            out.append({"name": "a", "blocks": blocks, "band": N(s.get("thumb_band"))})
        return out
    if ch == "psy" or th.get("lines"):
        for k, name in (("lines", "a"), ("lines_b", "b")):
            if th.get(k):
                lines = ["".join(N(w) for w, _ in l) for l in th[k]]
                hl = [N(w) for l in th[k] for w, c in l if str(c).upper() == YELLOW]
                out.append({"name": name, "blocks": [{"role": "全体", "lines": lines, "hl": hl}], "band": ""})
        return out
    if th.get("line1") or th.get("line2") or th.get("judge"):  # okinu
        blocks = [{"role": "上の2行", "lines": [N(th.get("line1")), N(th.get("line2"))], "hl": [N(w) for w in th.get("hl") or []]}]
        if th.get("judge"):
            blocks.append({"role": "判定", "lines": [N(th["judge"])], "hl": []})
        for k, r in (("left_label", "左の札"), ("right_label", "右の札")):
            if th.get(k):
                blocks.append({"role": r, "lines": [N(th[k])], "hl": []})
        blocks[0]["lines"] = [l for l in blocks[0]["lines"] if l]
        out.append({"name": "a", "blocks": blocks, "band": ""})
        return out
    if th.get("big") or th.get("top"):  # spi・nihongi・okinu の前の形
        hl_all = [N(w) for w in (th.get("hl") or [])]
        hl_top = [N(th["hl_top"])] if th.get("hl_top") else [w for w in hl_all if w in N(th.get("top"))]
        hl_big = [N(th["hl_big"])] if th.get("hl_big") else [w for w in hl_all if w in N(th.get("big"))]
        blocks = []
        if th.get("top"):
            blocks.append({"role": "上の段", "lines": N(th["top"]).split("\n"), "hl": hl_top})
        if th.get("big"):
            blocks.append({"role": "下の段（特大）", "lines": N(th["big"]).split("\n"), "hl": hl_big})
        out.append({"name": "a", "blocks": blocks, "band": N(th.get("tag"))})
        return out
    if s.get("thumb_text"):  # 古い形（thumb_text が配列か文字）
        t = s["thumb_text"]
        lines = [N(x) for x in (t if isinstance(t, list) else [t])]
        out.append({"name": "a", "blocks": [{"role": "全体", "lines": lines, "hl": []}], "band": ""})
    return out


def tokens(text):
    """(語, 始まり, 終わり, 品詞) の並び"""
    res, pos = [], 0
    with _LOCK:
        ms = list(_TOK.tokenize(text, _MODE))
    for m in ms:
        w = m.surface()
        res.append((w, pos, pos + len(w), m.part_of_speech()[0]))
        pos += len(w)
    return res


def shape(v):
    """形の点検。NG（語の途中で切れる）と注意（行の頭が助詞・助動詞）を返す"""
    if _TOK is None:
        return [], ["sudachi が無いので形の点検を飛ばした"]
    ng, warn = [], []
    for b in v["blocks"]:
        lines = [l for l in b["lines"] if l]
        if not lines:
            continue
        text = "".join(lines)
        tk = tokens(text)
        cuts = {t[1] for t in tk} | {len(text)}
        pos = 0
        for i, l in enumerate(lines):
            if i and pos not in cuts:
                w = next(t[0] for t in tk if t[1] < pos < t[2])
                ng.append(f"{b['role']}：行の境目で「{w}」が切れている（{'／'.join(lines)}）")
            head = next((t for t in tk if t[1] == pos), None)
            if i and head and head[3] in ("助詞", "助動詞"):
                warn.append(f"{b['role']}：{i + 1}行目が{head[3]}「{head[0]}」から始まる（{'／'.join(lines)}）")
            pos += len(l)
        if tk and tk[-1][3] == "助詞" and tk[-1][0] in ("が", "を", "に", "で", "と", "は", "の", "へ") and b is v["blocks"][-1]:
            warn.append(f"{b['role']}：最後が助詞「{tk[-1][0]}」で終わる（{text}）")
        for w in b["hl"]:
            if not w or w == "●●":
                continue
            i = text.find(w)
            if i < 0:
                continue  # 色を変える語が本文に無い（形の問題。make_thumb 側の点検が見る）
            if i not in cuts or i + len(w) not in cuts:
                ng.append(f"{b['role']}：色を変えた語「{w}」が語の途中で切れている（{text}）")
    return ng, warn


PROMPT = """あなたは日本語の YouTube サムネイルの字を点検する編集者です。チャンネル：{ch}
動画のタイトル：{title}
サムネの字（上から読む順。／は行の境目、［］は色を変えた語）：
{text}

次の4点を1つずつ判定してください。NG にするのは、下に書いた NG の形に明らかに当てはまる時だけ。好みの問題・もっと良くできる、は OK にして fix_hint に書く。
1. 字だけで話が分かる：サムネの字だけを読んで、何の話か・誰（何）のことか分かる。主語や対象が無い問い（「損するのは誰？」「割に合う？」だけ）、何の物差しか・誰の数か分からない数（「時給は107位」「時給は平均以下」だけで、どの職・どんな人の数か字に無い）、意味が取れない切れ端（「選んだかがかぎ」「刀だけ家に帰る」）は NG。
2. 1文としてつながる：上の段と下の段（行どうし）を続けて読むと、自然な日本語の1文（か、自然に続く2文）になる。助詞が抜けて意味が変わる・文法が崩れる・行どうしの関係が分からないものは NG。体言止め・倒置・伏せ字（●●）は、意味が通れば OK。
3. タイトルと役が分かれている：NG は3つだけ。①タイトルと矛盾する・別の話をしている（タイトルは「辞める人が多い」のにサムネは「時給は平均以下」だけ）②サムネの字がタイトルの一部をほぼそのまま写しただけ（言い換え・要点の抜き出し・数の切り出しは OK）③タイトルとサムネで、出てくる物・場所・人が食い違う（タイトルは「財布」なのにサムネは「カバン」）。タイトル＝何の話か、サムネ＝命令・結果・数の落差・伏せた答え・問い、の役分けは理想として fix_hint に書く。
4. フックがある：見た人がクリックしたくなる引っかかり（伏せた答え・「実は」・数の落差・意外な組み合わせ・有名な名前＋ひねり・命令・問い・見た人の得か損）が1つでもあれば OK。NG は、由来・正体・事実の説明だけで終わっていて引っかかりが1つも無い時。

OK の例：「光秀だけ99%」（有名な名前＋数の落差）、「笑う福の神は／元・捨て子」（有名な存在＋意外な過去）、「家から出ない人の脳は／実は休んでない」（身近なクセ＋実は）、「小銭を●●に置いてる家」（物＋伏せ字）。
NG の例：「ひとりが好きな人は／選んだかがかぎ」（意味が取れない）、「刀に「心」があったら／刀だけ家に帰る」（何の話か分からない）、「損するのは誰？」（主語・対象が無い）、「年収は建築／でも逆転」（何と何の逆転か分からない）。

答えは JSON だけを1つ。前置き・説明は書かない。
{{"ok": true か false（4つ全部 OK の時だけ true）, "items": [{{"k": "話が分かる", "ok": true/false, "why": "30字以内"}}, {{"k": "つながる", ...}}, {{"k": "役分け", ...}}, {{"k": "フック", ...}}], "fix_hint": "NG の時、どう直すか60字以内（OK なら空）", "example": "NG の時、同じ行数・同じ役で書き直した例。行の境目は／。数字や事実はタイトルにある物だけ使う（OK なら空）"}}"""


def claude_env():
    try:
        from nihongi_common import claude_env as ce
        return ce()
    except Exception:
        return dict(os.environ)


def render(v):
    rows = []
    for b in v["blocks"]:
        ls = []
        for l in b["lines"]:
            for w in sorted(b["hl"], key=len, reverse=True):
                if w and w in l and "［" not in l:
                    l = l.replace(w, f"［{w}］", 1)
            ls.append(l)
        rows.append(f"・{b['role']}：{'／'.join(ls)}")
    if v.get("band"):
        rows.append(f"・帯（小さい字）：{v['band']}")
    return "\n".join(rows)


def ask(ch, title, v):
    p = PROMPT.format(ch=ch, title=title or "（無し）", text=render(v))
    r = subprocess.run([shutil.which("claude") or "claude", "-p", "--model", os.environ.get("CLAUDE_PICK_MODEL", "sonnet"),
                        "--output-format", "json"], cwd=ROOT, env=claude_env(), input=p, capture_output=True, text=True,
                       encoding="utf-8", timeout=600)
    if r.returncode:
        raise RuntimeError(f"claude が止まった：{(r.stderr or r.stdout)[-300:]}")
    res = json.loads(r.stdout)["result"]
    m = re.search(r"\{.*\}", res, re.S)
    if not m:
        raise RuntimeError(f"JSON が返らなかった：{res[:200]}")
    return json.loads(m.group(0))


def check(s, ch, llm=True):
    """1本の台本を見る。{ok, variants:[{name, text, ng, warn, llm}]} を返す"""
    title = title_of(s)
    vs = extract(s, ch)
    if not vs:
        return {"ok": False, "title": title, "variants": [], "ng": ["サムネの字が台本に無い"]}
    res = []
    for v in vs:
        ng, warn = shape(v)
        r = {"name": v["name"], "text": render(v), "ng": ng, "warn": warn}
        if llm:
            try:
                j = ask(ch, title, v)
                r["llm"] = j
                if not j.get("ok"):
                    r["ng"] = r["ng"] + [f"{i['k']}：{i.get('why', '')}" for i in j.get("items", []) if not i.get("ok")]
            except Exception as e:  # 意味の点検が回らない時は止めずに注意にする（制作を止めない）
                r["warn"].append(f"意味の点検が回らなかった：{e}")
        res.append(r)
    return {"ok": not any(r["ng"] for r in res), "title": title, "variants": res}


def guess_ch(work):
    p = os.path.abspath(work)
    for name, ch in (("かくれ神語り", "kakure"), ("指名手配ボード", "shimei"), ("カラダイブ", "karada")):
        if name in p:
            return ch
    m = re.search(r"channels[\\/](\w+)[\\/]", p)
    return m.group(1) if m else ""


def show(name, r):
    print(f"■ {name}：{'OK' if r['ok'] else 'NG'}｜{r.get('title', '')}")
    for v in r["variants"]:
        print(f"  [{v['name']}案] {v['text'].replace(chr(10), ' ')}")
        for x in v["ng"]:
            print("    NG", x)
        for x in v["warn"]:
            print("    注意", x)
        j = v.get("llm") or {}
        if j.get("example"):
            print("    書き直し例：", j["example"])
    for x in r.get("ng", []):
        print("  NG", x)


def main():
    a = argparse.ArgumentParser()
    a.add_argument("work", nargs="?")
    a.add_argument("--ch", default="")
    a.add_argument("--samples")
    a.add_argument("--out")
    a.add_argument("--no-llm", action="store_true")
    a = a.parse_args()
    if a.samples:
        items = json.load(open(a.samples, encoding="utf-8"))
        with concurrent.futures.ThreadPoolExecutor(4) as ex:
            rs = list(ex.map(lambda it: check(it["script"], it["ch"], not a.no_llm), items))
        out = []
        for it, r in zip(items, rs):
            show(f"{it['ch']}/{it['name']}", r)
            out.append({"name": it["name"], "ch": it["ch"], "expect": it.get("expect"), **r})
        hit = [o for o in out if o.get("expect") in ("OK", "NG")]
        if hit:
            good = sum((o["ok"] and o["expect"] == "OK") or (not o["ok"] and o["expect"] == "NG") for o in hit)
            print(f"\n期待との一致：{good}/{len(hit)}")
            for o in hit:
                if o["ok"] != (o["expect"] == "OK"):
                    print(f"  外れ：{o['ch']}/{o['name']}（期待 {o['expect']}）")
        if a.out:
            json.dump(out, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        return
    if not a.work:
        sys.exit("作業フォルダか --samples を渡してください")
    s = json.load(open(os.path.join(a.work, "script.json"), encoding="utf-8"))
    tp = os.path.join(a.work, "thumb.json")
    if os.path.exists(tp):  # agent の2チャンネルは字を thumb.json に書く
        s["thumb_json"] = json.load(open(tp, encoding="utf-8"))
    r = check(s, a.ch or guess_ch(a.work), not a.no_llm)
    json.dump(r, open(os.path.join(a.work, "check_thumb_text.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    show(os.path.basename(os.path.abspath(a.work)), r)
    sys.exit(0 if r["ok"] else 1)


if __name__ == "__main__":
    main()

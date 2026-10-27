# 台本の機械点検（心理学ch・2026-10-27 新設。手順書 §9）：script.json と facts.json を決まりと照らす
#   python -X utf8 pipeline\check_psy_script.py <作業フォルダ> [--no-net]
# ・NG：字数（4,900〜6,000）・章（6〜8）・つかみの決まった文・登録の呼びかけの位置（40〜50%）・締めの文・クイズ・
#   研究カード（5〜8枚と形）・動かす絵（20〜40）・使い回し（12%まで）・サムネの背景（THUMB）・記号と禁止表現・
#   タイトル（【心理学】・100字まで・3案）・サムネの文字（3行・11〜17字・黄は1か所）・概要欄（置き換えの印・研究・断り）・
#   研究（5〜9個・study の参照先・DOI を Crossref で引いて著者と年が合うか）
# ・注意：1カットの字数・label の数など、直した方がよいが止めない物
# ・--no-net：Crossref を引かない（手元で形だけ見る時）。ネットにつながらない時は注意にとどめる
# ・NG があれば終了コード1
import argparse, json, os, re, sys, urllib.error, urllib.parse, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MARKS = ("──", "—", "…", "※", "★", "→")


def count(t):
    return len(re.sub(r"[\s、。！？「」『』（）]", "", t))


def crossref(doi):
    url = "https://api.crossref.org/works/" + urllib.parse.quote(doi.strip())
    req = urllib.request.Request(url, headers={"User-Agent": "yt-auto-psy-check/1.0 (mailto:yt-auto@users.noreply.github.com)"})
    return json.load(urllib.request.urlopen(req, timeout=30))["message"]


def main():
    a = argparse.ArgumentParser()
    a.add_argument("work")
    a.add_argument("--no-net", action="store_true")
    a = a.parse_args()
    ng, warn = [], []
    s = json.load(open(os.path.join(a.work, "script.json"), encoding="utf-8"))
    fp = os.path.join(a.work, "facts.json")
    f = json.load(open(fp, encoding="utf-8")) if os.path.exists(fp) else {}
    cuts = s.get("cuts", [])
    ids = [c.get("id") for c in cuts]
    if len(ids) != len(set(ids)):
        ng.append("カットの id が重なっている：" + ", ".join(sorted({i for i in ids if ids.count(i) > 1})))
    talk = [c for c in cuts if c.get("narration")]
    total = sum(count(c["narration"]) for c in talk)
    if not 4900 <= total <= 6000:
        ng.append(f"語りの字数 {total}字（4,900〜6,000字。§2）")
    if not 150 <= len(talk) <= 240:
        ng.append(f"語りのカット {len(talk)}（170〜220 のめやす。§2）")
    for c in talk:
        if count(c["narration"]) > 60:
            warn.append(f"{c['id']}：1カット {count(c['narration'])}字（45字までのめやす）")
    pos, acc = {}, 0
    for c in talk:
        acc += count(c["narration"])
        pos[c["id"]] = acc / max(1, total)
    chaps = [c for c in cuts if c.get("chapter")]
    if not 7 <= len(chaps) <= 9:
        ng.append(f"章 {len(chaps)}（本編6〜7章＋まとめ。§2）")
    if chaps and chaps[-1]["chapter"] != "まとめ":
        ng.append("最後の章が「まとめ」ではない（§2）")
    if talk and talk[0].get("chapter"):
        ng.append("最初のカットに chapter がある（つかみの後から章。§2）")
    for c in chaps:
        if len(c["chapter"]) > 20:
            ng.append(f"{c['id']}：章の名前が20字を超える")
    nar = {c["id"]: c["narration"] for c in talk}
    hook = [c for c in talk[:8]]
    if not any(re.match(r"今回は、.+心理学の研究から見ていきます。", c["narration"]) for c in hook):
        ng.append("つかみに「今回は、〇〇を、心理学の研究から見ていきます。」が無い（§3-1）")
    if not any(c["narration"].startswith("最後に、") and "お話しします" in c["narration"] for c in hook):
        ng.append("つかみに「最後に、〇〇も、お話しします。」が無い（§3-1）")
    sub = [i for i, t in nar.items() if "チャンネル登録" in t]
    if not sub:
        ng.append("登録の呼びかけが無い（§3-4）")
    elif not 0.38 <= pos[sub[0]] <= 0.52:
        ng.append(f"登録の呼びかけの位置 {pos[sub[0]]:.0%}（40〜50%。§3-4）")
    if not any("ここで問題です" in t for t in nar.values()):
        ng.append("クイズ（「ここで問題です。」）が無い（§3-3）")
    tail = " ".join(c["narration"] for c in talk[-6:])
    for need in ("コメントで教えてください", "最後まで見てくださって、ありがとうございました", "また次の動画で、お会いしましょう"):
        if need not in tail:
            ng.append(f"締めに「{need}」が無い（§3-7）")
    if "LINE" in " ".join(nar.values()):
        ng.append("語りに LINE が出ている（LINE は概要欄と固定コメントだけ）")
    # 記号・禁止表現
    bad_words = [w.strip() for w in open(os.path.join(ROOT, "channels", "psy", "禁止表現.txt"), encoding="utf-8")
                 if w.strip() and not w.startswith("#")]
    for c in talk:
        t = c["narration"]
        for m in MARKS:
            if m in t:
                ng.append(f"{c['id']}：記号「{m}」（§4）")
        for w in bad_words:
            if w in t and w not in MARKS:
                warn.append(f"{c['id']}：禁止表現「{w}」の可能性（台本ゲートが文脈で見る）：{t}")
    # 絵
    img = [c for c in cuts if c.get("image") and not c.get("same_as")]
    same = [c for c in talk if c.get("same_as")]
    if len(same) / max(1, len(talk)) > 0.12:
        ng.append(f"使い回し {len(same)}カット（{len(same) / max(1, len(talk)):.0%}。12%まで。§5）")
    for c in same:
        if c["same_as"] not in ids:
            ng.append(f"{c['id']}：same_as の先 {c['same_as']} が無い")
    for c in talk:
        if not c.get("image") and not c.get("same_as"):
            ng.append(f"{c['id']}：image も same_as も無い")
    for c in img:
        hero_txt = "主役" in c["image"]
        if hero_txt != ("hero" in (c.get("chars") or [])):
            ng.append(f"{c['id']}：image の「主役」と chars の hero が合わない（§5）")
        if c.get("nobody") != ("人物は描かない" in c["image"]) and (c.get("nobody") or "人物は描かない" in c["image"]):
            ng.append(f"{c['id']}：nobody と「（人物は描かない）」が合わない（§5）")
        if c.get("nobody") and c.get("chars"):
            ng.append(f"{c['id']}：nobody なのに chars がある")
    nob = sum(1 for c in img if c.get("nobody"))
    if nob / max(1, len(img)) > 0.3:
        warn.append(f"物だけの絵 {nob}/{len(img)}（3割までのめやす）")
    mo = [c for c in cuts if c.get("motion")]
    if not 20 <= len(mo) <= 40:
        ng.append(f"動かす絵 {len(mo)}カット（25〜35 のめやす。§5）")
    for c in mo:
        if not c.get("image") or c.get("same_as") or c.get("card"):
            ng.append(f"{c['id']}：motion は、自分の絵があるカットだけ（same_as・card には付けない）")
    cards = [c for c in cuts if c.get("card")]
    if not 5 <= len(cards) <= 8:
        ng.append(f"研究カード {len(cards)}枚（5〜8枚。§5）")
    for c in cards:
        k = c["card"]
        if not k.get("source"):
            ng.append(f"{c['id']}：card に source が無い")
        if k.get("rows"):
            if len(k["rows"]) > 3 or any(len(r) != 2 for r in k["rows"]):
                ng.append(f"{c['id']}：card の rows は [条件, 結果] を3行まで")
        elif k.get("text"):
            lines = k["text"].split("\n")
            if len(lines) > 3 or max(len(x) for x in lines) > 14:
                ng.append(f"{c['id']}：card の text は1行14字・3行まで（{lines}）")
        else:
            ng.append(f"{c['id']}：card に text も rows も無い")
        if not c.get("narration"):
            ng.append(f"{c['id']}：card のカットに語りが無い")
    labels = [c for c in talk if c.get("label")]
    for c in labels:
        if len(c["label"]) > 18:
            ng.append(f"{c['id']}：label が18字を超える（{c['label']}）")
    if not 12 <= len(labels) <= 40:
        warn.append(f"label {len(labels)}個（1章に3〜4個のめやす）")
    th = next((c for c in cuts if c.get("id") == s.get("thumb_bg")), None)
    if s.get("thumb_bg") != "THUMB" or not th or th.get("narration") or "hero" not in (th.get("chars") or []):
        ng.append("サムネの背景：語りの無い THUMB カット（主役つき）を置き、thumb_bg を THUMB にする（§5）")
    if not s.get("style") or "しずく形" not in s.get("style", ""):
        ng.append("style が手順書 §5 の画風ではない")
    if not s.get("avoid"):
        ng.append("avoid が無い（§5）")
    # タイトル・サムネ
    t = s.get("title", "")
    if not t.startswith("【心理学】") or len(t) > 100:
        ng.append(f"タイトルは「【心理学】」で始め100字まで：{t}")
    elif not 40 <= len(t) <= 85:
        warn.append(f"タイトル {len(t)}字（60〜80字のめやす）")
    if len(s.get("titles", [])) != 3 or s["titles"][0] != t:
        ng.append("titles は3案で、1番目が title と同じ（§6）")
    lines = (s.get("thumb") or {}).get("lines") or []
    flat = ["".join(r[0] for r in ln) for ln in lines]
    yellow = sum(1 for ln in lines for r in ln if r[1].upper() == "#FFE234")
    if len(lines) != 3 or not 11 <= sum(len(x) for x in flat) <= 17 or yellow != 1 or \
            any(r[1].upper() not in ("#FFFFFF", "#FFE234") for ln in lines for r in ln):
        ng.append(f"サムネの文字は3行・11〜17字・白と黄（黄は1か所）：{flat}（§6）")
    # 概要欄
    d = s.get("desc", "")
    for need in ("{LINE_URL}", "{CHAPTERS}", "📚参考にした研究", "医療・診断・治療を目的としたものではありません",
                 "音声：VOICEVOX:No.7", "AIを使って作っています", "#心理学", "sub_confirmation=1"):
        if need not in d:
            ng.append(f"概要欄に「{need}」が無い（§7）")
    if "PR" in d:
        ng.append("概要欄に PR の文字（§7）")
    if not 7 <= len(s.get("tags", [])) <= 12:
        warn.append(f"tags {len(s.get('tags', []))}個（7〜10個）")
    # 研究
    st = {x.get("key"): x for x in f.get("studies", [])}
    if not 5 <= len(st) <= 9:
        ng.append(f"facts.json の研究 {len(st)}個（5〜9個。§8）")
    for k, x in st.items():
        for need in ("cite", "finding", "may_say", "first_author", "year"):
            if not x.get(need):
                ng.append(f"facts.json {k}：{need} が無い")
        if not x.get("doi") and not x.get("url"):
            ng.append(f"facts.json {k}：doi も url も無い")
        if x.get("cite") and x["cite"].split("(")[0].strip()[:12] not in d:
            warn.append(f"facts.json {k} の cite が概要欄の研究の並びに無い：{x['cite']}")
    for c in talk:
        if c.get("study") and c["study"] not in st:
            ng.append(f"{c['id']}：study {c['study']} が facts.json に無い")
    if not any(c.get("study") for c in talk):
        ng.append("研究を言うカットに study が1つも無い（§8）")
    if not a.no_net:
        for k, x in st.items():
            if not x.get("doi"):
                continue
            try:
                m = crossref(x["doi"])
            except urllib.error.HTTPError as e:
                ng.append(f"facts.json {k}：DOI {x['doi']} が Crossref に無い（{e.code}）")
                continue
            except Exception as e:
                warn.append(f"facts.json {k}：Crossref につながらない（{type(e).__name__}）")
                continue
            fams = [au.get("family", "") for au in m.get("author", [])]
            yr = ((m.get("issued") or {}).get("date-parts") or [[None]])[0][0]
            if not any(str(x.get("first_author", "")).lower() in fa.lower() or fa.lower() in str(x.get("first_author", "")).lower()
                       for fa in fams if fa):
                ng.append(f"facts.json {k}：DOI の著者 {fams[:3]} と first_author {x.get('first_author')} が合わない")
            if yr and x.get("year") and abs(int(yr) - int(x["year"])) > 1:
                ng.append(f"facts.json {k}：DOI の年 {yr} と year {x['year']} が合わない")
    print(f"語り {total}字・{len(talk)}カット・章 {len(chaps)}・絵 {len(img)}（物だけ {nob}）・使い回し {len(same)}・"
          f"動かす {len(mo)}・カード {len(cards)}・研究 {len(st)}")
    for w in warn:
        print("注意：", w)
    for x in ng:
        print("NG：", x)
    print(f"NG {len(ng)}件・注意 {len(warn)}件")
    sys.exit(1 if ng else 0)


if __name__ == "__main__":
    main()

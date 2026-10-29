# 千年こよみ（spi）の台本の点検（2026-10-29 新設）：手順書 §4・§6・§11 の項目を、暦の固定ファイルと照らして機械で見る
#   python -X utf8 pipeline/check_spi_script.py <作業フォルダ>
# ・元は手元の check_koyomi_v2.py（001 v3 で使った点検）。毎日の自動制作のために、次を変えた・足した
#   ・暦の固定ファイルは repo の data/koyomi_2026_2027.json（koyomi_spi.py が読む物と同じ）
#   ・章の印は "chapter"（自動の回）と "yt_chapter"（001）のどちらでもよい
#   ・場面の絵は card の無いカット（"image" に日本語で絵の頼み方。make_images_lovart.py が絵を作る）でもよい（写真の札として数える）
#   ・年の書いていない日付は、公開日（pub_date）の45日前より後で、いちばん近い年として照らす（2026・2027 の決め打ちをやめた）
#   ・§11 の足りなかった項目：facts.json の暦の欄が作り直した値と同じか（暦の鍵）／次の重なりの表と、その日付を曜日つきで声で言うカット／
#     章ごとの動くカード／見どころ（peak）／つかみの型（hook_type）／タイトル3案の数字・【】・「AI」「PR」「ランキング」「人気」／
#     概要欄の AI の行・LINE の受け取り口・{LINE_URL}・{CHAPTERS}・声のクレジット／LINE の案内と登録の呼びかけの文が決まった文か／
#     サムネの字数／「最強開運日」は天赦日と一粒万倍日が重なる日だけ／答えを先に延ばすだけの文
# ・NG が1つでもあれば終了コード 1。結果は <作業フォルダ>/check/check_spi.txt にも書く
import argparse, datetime as dt, json, os, re, sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import koyomi_spi as KS  # noqa: E402

WD = "月火水木金土日"
AI_LINE = ["千年以上続く暦の、人の手では数えきれない日付の重なりをプログラムで計算し、AIで映像と声にしています。日付は全部、暦と照らしています。",
           "千年以上続く暦の、人の手では数えきれない日付の重なりをプログラムで計算し、AIで映像と声にしています。日付は暦と、数字は統計と照らしています。"]
# 手順書 §4 の決まった文（読点の有無は見ない。〇〇はこの回の吉日・言い伝えの名前）
SUB_COPY = {1: "暦としきたりを、日付と由来つきで届けています。よければチャンネル登録をお願いします。",
            2: "このチャンネルでは、次に来る吉日を、日付と由来つきで紹介しています。チャンネル登録をおすすめします。",
            3: "次の回も、暦の話を1つ届けます。よければチャンネル登録をお願いします。"}
LINE_COPY = {
    "A": {1: "今月と来月の吉日と行事を、カレンダーにまとめました。概要欄のLINEから受け取れます。",
          2: "次の〇〇も、カレンダーに印をつけてあります。概要欄のLINEからどうぞ。",
          3: "天赦日と一粒万倍日が重なる日を、全部書き出した今月と来月のカレンダーです。概要欄のLINEから受け取れます。"},
    # 型B：作法の早見表ができるまで、特典は型A と同じカレンダー（手順書 v3.9 §4。無い早見表を約束しない）
    "B": {1: "今月と来月の吉日と行事を、カレンダーにまとめました。神社へ行く日を選ぶ時に使えます。概要欄のLINEから受け取れます。",
          2: "天赦日や一粒万倍日など、今月と来月の吉日を1枚のカレンダーにしました。概要欄のLINEからどうぞ。",
          3: "次に神社へ行く日を選ぶのに使える、今月と来月の吉日カレンダーです。概要欄のLINEから受け取れます。"},
    "C": {1: "2027年の吉日を、1年分のカレンダーにまとめました。概要欄のLINEから受け取れます。",
          2: "〇〇年生まれの方の干支の日にも、印をつけてあります。概要欄のLINEからどうぞ。",
          3: "天赦日と一粒万倍日が重なる日を、全部書き出した年間カレンダーです。概要欄のLINEから受け取れます。"},
}
LINE_COPY["C2"] = LINE_COPY["A"]
TOKUTEN = {"A": "今月と来月の吉日と行事のカレンダー", "C2": "今月と来月の吉日と行事のカレンダー", "B": "今月と来月の吉日と行事のカレンダー",
           "C": "2027年 年間の吉日カレンダー", "D": "言い伝え早見表"}
CARD_TYPES = {"photo", "big_text", "quote", "chapter_title", "rules", "calendar", "next_table", "tally", "timeline", "kgrid", "two_cards"}
META = ["この動画", "この回", "今回", "このチャンネル", "ここからは", "ここまで", "この後", "このあと", "次の章", "見ていきます", "紹介します",
        "おさらい", "採点結果です", "ありがとうございました", "ご覧いただき", "今日", "今夜", "今宵", "舞台裏", "概要欄に残して", "ひより",
        "最後に言います", "発表します", "最後の章で", "後半で", "最後まで見て", "お見せします"]
BAN = ["ランキング", "人気", "必ず当たる", "必ず叶う", "万円入る", "治る", "体がよくなる", "見れた人だけ", "見れたら強運"]
FREQ = ["毎日", "明日も"]  # 呼びかけ・案内・締めで公開の頻度を言わない（§4）
HEALTH = ["風邪をひかない", "無病息災", "邪気を払う", "厄が落ちる", "夏バテ", "滋養", "疲労回復", "病気にならない"]
DRE = re.compile(r"(?:(\d{4})年)?(?:(\d{1,2})月)?(\d{1,2})日(?:[、の]?\s*[（(]?([月火水木金土日])(?:曜)?)?")
SRE = re.compile(r"(?<![\d/])(\d{1,2})/(\d{1,2})(?![\d/])(?:\s*[（(]([月火水木金土日])[）)])?")  # サムネの「12/16（水）」
SPAN_SKIP = re.compile(r"\d+日(?:に1度|ごと|後|分|続|間|目)")
NUM = re.compile(r"(?:\d{4}年)?\d{1,2}月\d{1,2}日|\d+(?:日|つ|通り|回|か月|週間|年|分|か所)|[一二三四五六七八九十百千]+(?:つ|通り|日ごと)|半年|半分")
LAB = {"万倍": ("senjitsu", "一粒万倍日"), "天赦": ("senjitsu", "天赦日"), "巳": ("senjitsu", "巳の日"), "寅": ("senjitsu", "寅の日"),
       "己巳": ("senjitsu", "己巳の日"), "大安": ("rokuyo", "大安")}
NAME = {"一粒万倍日": "一粒万倍日", "天赦日": "天赦日", "巳の日": "巳の日", "寅の日": "寅の日", "己巳の日": "己巳の日", "大安": "大安"}
norm = lambda t: re.sub(r"[、\s]", "", t or "")


def main():
    a = argparse.ArgumentParser()
    a.add_argument("work")
    a = a.parse_args()
    work = os.path.abspath(a.work)
    s = json.load(open(os.path.join(work, "script.json"), encoding="utf-8"))
    fp = os.path.join(work, "facts.json")
    f = json.load(open(fp, encoding="utf-8")) if os.path.exists(fp) else {}
    np_ = os.path.join(work, "neta.json")
    neta = json.load(open(np_, encoding="utf-8")) if os.path.exists(np_) else None
    K = KS.K()
    DAY = K["_day"]
    meta = K["meta"]
    cuts = [c for c in s["cuts"] if c.get("narration")]
    ng, warn, ok = [], [], []
    T = sum(len(c["narration"]) for c in cuts) or 1
    at = lambda i: sum(len(c["narration"]) for c in cuts[:i]) / T
    pub = s.get("pub_date") or (neta or {}).get("pub_date")
    pub_d = dt.date.fromisoformat(pub) if pub else dt.date.fromisoformat(meta["valid_from"])
    chap = lambda c: c.get("chapter") or c.get("yt_chapter")
    typ = s.get("type")

    def ymd(y, m, d):
        try:
            return dt.date(y, m, d).isoformat()
        except ValueError:
            return None

    def year_of(m, d, y=None, w=None, after=None):
        """年の無い日付の年：after（無ければ公開日の45日前）より後の年。曜日が書いてある時は、曜日が合う年を先に取る"""
        if y:
            return int(y)
        base = after or (pub_d - dt.timedelta(days=45))
        cand = [yy for yy in (pub_d.year - 1, pub_d.year, pub_d.year + 1, pub_d.year + 2)
                if ymd(yy, m, d) and dt.date.fromisoformat(ymd(yy, m, d)) >= base]
        if w:
            hit = [yy for yy in cand if WD[dt.date(yy, m, d).weekday()] == w]
            if hit:
                return hit[0]
        return cand[0] if cand else pub_d.year

    def dates_in(t, need_m=False, after=None):
        out, m = [], None
        for y, mm, d, w in DRE.findall(t):
            if mm:
                m = int(mm)
            if not m or (need_m and not mm and not w):
                continue
            out.append((ymd(year_of(m, int(d), y, w, after), m, int(d)), w, f"{y + '年' if y else ''}{m}月{d}日"))
        for mm, d, w in SRE.findall(t):
            m = int(mm)
            if 1 <= m <= 12:
                out.append((ymd(year_of(m, int(d), None, w, after), m, int(d)), w, f"{m}/{d}"))
        return out

    def check_dates(cid, t, where):
        for iso, w, lab in dates_in(SPAN_SKIP.sub("", t or "")):
            if not iso or iso not in DAY:
                if iso and meta["valid_from"] <= iso <= meta["valid_to"]:
                    ng.append(f"{cid} {where}の {lab} が暦の固定ファイルに無い")
                continue
            if w and DAY[iso]["weekday"] != w:
                ng.append(f"{cid} {where}の {lab} の曜日が「{w}」（暦は {DAY[iso]['weekday']}）")

    # 1. 台本に持たせる項目（§11）
    for k in ("type", "frame", "target", "pub_date", "hook_type", "sub_copy", "line_copy", "card_theme", "title", "desc", "style", "avoid"):
        if k not in s:
            ng.append(f"台本の項目 {k} が無い")
    if typ in ("A", "C2"):
        if not s.get("window"):
            ng.append("型A・C2 なのに window が無い")
        elif pub and not (s["window"][0] <= pub <= s["window"][1]):
            ng.append(f"pub_date {pub} が window {s['window']} の外")
    if typ == "C2" and not s.get("target_month"):
        ng.append("型C2 なのに target_month が無い")
    if typ == "C" and pub and pub > "2027-01-31":
        ng.append(f"型C の公開日 {pub} が 2027-01-31 より後（§3。2月からは C2）")
    bad_sp = [c["id"] for c in cuts if c.get("speaker", "narrator") not in ("narrator", "listener")]
    if bad_sp:
        ng.append(f"speaker が narrator／listener でないカット：{bad_sp}")
    ids = [c["id"] for c in s["cuts"]]
    dup = [k for k, v in Counter(ids).items() if v > 1]
    if dup:
        ng.append(f"カットの id が重なっている：{dup}")

    # 2. 長さ・聞き手・つかみ〜前置き（§4）
    # 下限は 2026-10-29 に 3,000 から 3,200 へ。001 の実測は1分374字（速さ1.25）で、3,000字だと約8分01秒になり、
    # gate_video.py の8分（MIN_SEC 480）にぎりぎり届かない回が出るため（門は下げずに字数を上げた）
    # 同じ日にもう一度 3,650 へ。クラウドで作った 003 は 3,350字で7.7分（1秒7.25字。クラウドの VOICEVOX は 001 より速い）で、8分の門で止まった
    (ok if 3650 <= T <= 4200 else ng).append(f"字数 {T}（3,650〜4,200）")
    (ok if 95 <= len(cuts) <= 110 else ng).append(f"カット {len(cuts)}（95〜110）")
    (ok if T / 7.25 >= 500 else ng).append(f"見込み {T / 7.25 / 60:.1f}分（字数÷1秒7.25字＝003 のクラウドの実測。8分20秒以上）")
    li = [c for c in cuts if c.get("speaker") == "listener"]
    if li:
        r = len(li) / len(cuts)
        (ok if r <= 0.3 else ng).append(f"聞き手 {len(li)}カット（{r:.0%}。3割まで）")
        for c in li:
            n = len([x for x in re.split(r"(?<=[。？！])", c["narration"]) if x.strip()])
            if n > 1:
                ng.append(f"{c['id']} 聞き手が{n}文（1回1文）：{c['narration']}")
            if len(c["narration"]) > 26:
                warn.append(f"{c['id']} 聞き手のセリフが {len(c['narration'])}字（20字前後まで）")
        if "もち子さん" not in s.get("desc", ""):
            ng.append("聞き手を入れた回なのに、概要欄に聞き手の声のクレジット（VOICEVOX:もち子さん）が無い")
    else:
        ok.append("1人語り（聞き手 0カット）")
    first = next((i for i, c in enumerate(cuts) if chap(c)), None)
    if first is None:
        ng.append("章（chapter）が1つも無い")
        first = len(cuts)
    op = sum(len(c["narration"]) for c in cuts[:first])
    (ok if 240 <= op <= 420 else ng).append(f"つかみ〜前置き {op}字＝約{op / 6:.0f}秒（240〜420字・40〜70秒）")

    # 3. LINE の案内・登録の呼びかけ・コメント（§4）。文は決まった文（line_copy・sub_copy の番号の文）
    for word, lo, hi, name, key, table in (("LINE", .35, .50, "LINE の案内", "line_copy", LINE_COPY.get(typ, {})),
                                          ("チャンネル登録", .60, .70, "登録の呼びかけ", "sub_copy", SUB_COPY)):
        idx = [i for i, c in enumerate(cuts) if word in c["narration"]]
        if len(idx) != 1:
            ng.append(f"{name}が {len(idx)} 回（1回）")
            continue
        p = at(idx[0])
        c = cuts[idx[0]]
        (ok if lo <= p <= hi else ng).append(f"{name} {c['id']} の位置 {p:.1%}（{lo:.0%}〜{hi:.0%}）")
        want = table.get(s.get(key))
        if want:
            pat = "^" + re.escape(norm(want)).replace("〇〇", ".{1,24}?") + "$"
            if not re.match(pat, norm(c["narration"])):
                ng.append(f"{c['id']} {name}の文が {key}={s.get(key)} の決まった文と違う：{c['narration']}（決まった文：{want}）")
            elif key == "line_copy" and typ in ("A", "C2") and s.get(key) == 2:
                m = re.match(r"次の(.+?)も", norm(c["narration"]))
                if m and not any(m.group(1) in norm(x["narration"]) for x in cuts if x is not c):
                    ng.append(f"{c['id']} 案内文②の「{m.group(1)}」が、この回のほかのカットに出てこない（§11）")
        elif typ in LINE_COPY or key == "sub_copy":
            ng.append(f"{key} が 1〜3 でない：{s.get(key)}")
    if not any("コメント" in c["narration"] for c in cuts[-3:]):
        ng.append("締め（最後の3カット）にコメントへの問いかけが無い")

    # 4. メタの言葉・禁止の言葉（決まった文＝LINE・登録・コメントのカットは除く）
    fixed = {c["id"] for c in cuts if "LINE" in c["narration"] or "チャンネル登録" in c["narration"] or "コメント" in c["narration"]}
    tail = {c["id"] for c in cuts[-3:]}
    for c in cuts:
        for w in META:
            if w in c["narration"] and c["id"] not in fixed:
                ng.append(f"{c['id']} メタの言葉・先送りの言い方「{w}」：{c['narration']}")
        for w in BAN:
            if w in c["narration"]:
                ng.append(f"{c['id']} 禁止の言葉「{w}」")
        for w in FREQ:
            if w in c["narration"]:
                (ng if c["id"] in fixed | tail else warn).append(f"{c['id']} 「{w}」（呼びかけ・案内・締めでは公開の頻度を言わない。場面の中なら可）")
        for w in HEALTH:
            if w in c["narration"]:
                warn.append(f"{c['id']} 健康の言い伝えの言葉「{w}」（由来の言い方か、台本ゲートが文脈で見る）")
        if c["narration"].startswith(("私は", "わたしは")):
            ng.append(f"{c['id']} 名乗りに見える文：{c['narration']}")

    # 5. タイトル・サムネ・概要欄（§4・§7・§11）
    titles = s.get("titles") or [s.get("title")] + list(s.get("title_alts") or [])
    titles = [t for t in titles if t]
    if len(titles) != 3:
        ng.append(f"タイトルが {len(titles)} 案（3案）")
    if s.get("titles") and s.get("title") != s["titles"][0]:
        ng.append("title が titles の1案目と違う")
    th = s.get("thumb") or {}
    thumb_txt = [th.get("top", ""), th.get("big", ""), th.get("tag", "")] if th else list(s.get("thumb_text") or [])
    for t in titles:
        if not re.search(r"[0-9０-９一二三四五六七八九十]", t):
            ng.append(f"タイトルに日付・年・数が無い：{t}")
        if t.count("【") > 1:
            ng.append(f"タイトルの【】が2つ以上：{t}")
        if len(t) > 100:
            ng.append(f"タイトルが100字を超える：{t}")
        for w in ("ランキング", "人気", "PR") + (("AI",) if typ != "D" else ()):
            if w in t:
                ng.append(f"タイトルに「{w}」：{t}")
        if "最強開運日" in t:
            for iso, w, lab in dates_in(SPAN_SKIP.sub("", t)):
                if iso and iso not in meta["saikyo_kaiun"]:
                    ng.append(f"タイトルの「最強開運日」と一緒の {lab} は、天赦日と一粒万倍日が重なる日ではない：{t}")
        check_dates("title", t, "タイトル")
    for t in thumb_txt:
        for w in ("ランキング", "人気", "PR", "AI"):
            if w in (t or ""):
                ng.append(f"サムネの文字に「{w}」：{t}")
        check_dates("thumb", t, "サムネ")
    if th:
        if not th.get("big"):
            ng.append("thumb に big（下の段の答え）が無い")
        if len(th.get("top", "")) > 12:
            ng.append(f"サムネの上の段が {len(th['top'])}字（12字まで）")
        if len(th.get("big", "")) > 8:
            ng.append(f"サムネの下の段が {len(th['big'])}字（8字まで）")
        if not 1 <= len(th.get("hl") or []) <= 2:
            ng.append("サムネの色を変える語（hl）は1〜2語")
        for w in th.get("hl") or []:
            if w not in th.get("top", "") + th.get("big", ""):
                ng.append(f"サムネの hl「{w}」が上の段にも下の段にも無い")
        for full, short in (("天赦日", "天赦"), ("一粒万倍日", "万倍")):
            if short in th.get("tag", "") and full in th.get("tag", ""):
                warn.append("サムネの札は略称（天赦・万倍）にする（§7）")
        bg = s.get("thumb_bg") or "THUMB"
        if not any(c["id"] == bg and c.get("image") for c in s["cuts"]):
            ng.append(f"サムネの背景のカット {bg}（image のあるカット）が無い")
    elif s.get("titles"):
        ng.append("thumb（サムネの文字。top・big・hl）が無い")
    desc = s.get("desc", "")
    first_line = desc.split("\n")[0]
    if "LINEで無料で受け取れます" not in first_line or (typ in TOKUTEN and TOKUTEN[typ] not in first_line):
        ng.append(f"概要欄の1行目が「{TOKUTEN.get(typ, '特典の名前')}…LINEで無料で受け取れます」の形でない：{first_line}")
    for k in ("{LINE_URL}", "{CHAPTERS}"):
        if k not in desc:
            ng.append(f"概要欄に {k} が無い（アップの時にリンクと目次に置き換える）")
    stats = typ == "D" and any(x.get("kind") == "統計" for x in f.get("sources") or [] if isinstance(x, dict))
    if AI_LINE[1 if stats else 0] not in desc.split("\n"):
        ng.append(f"概要欄の AI の行が §4 の文と完全一致していない（{'2' if stats else '1'}つ目の文）")
    for w in ("PR",):
        if w in desc:
            ng.append("概要欄に「PR」（PR は LINE の中のアフィのリンクだけ）")
    cr = ((s.get("voice") or {}).get("credit")) or "音声：VOICEVOX:玄野武宏"
    if cr not in desc:
        warn.append(f"概要欄に声のクレジット「{cr}」が無い（§2。規約で必須）")

    # 6. 日付と曜日（声・画面）を暦の固定ファイルと照らす（§11）
    for c in cuts:
        check_dates(c["id"], c["narration"], "声")
        cd = c.get("card") or c.get("photo") or {}
        for k in ("text", "text2", "kicker", "title", "note", "tag", "tag_sub"):
            if isinstance(cd.get(k), str):
                check_dates(c["id"], cd[k], f"画面（{k}）")
        for k, sub in (("pop", "small"), ("pop", "big"), ("tate", "text")):
            v = (cd.get(k) or {}).get(sub)
            if isinstance(v, str):
                check_dates(c["id"], v, f"画面（{k}.{sub}）")
        if c.get("label"):
            check_dates(c["id"], c["label"], "画面（label）")

    def has(day, part):
        fld, v = LAB.get(part, (None, None))
        if fld is None:
            return None
        x = day.get(fld)
        return x == v if fld == "rokuyo" else v in (x or [])

    def has_name(day, nm):
        return day["rokuyo"] == nm if nm == "大安" else nm in day["senjitsu"]

    def month_days(y, m):
        return [d for k, d in DAY.items() if k.startswith(f"{y}-{m:02d}-")]

    # 7. 画面（カード・場面の絵）と、カードの中身を暦と照らす（§6・§11）
    cards = Counter()
    nt_rows = []
    for c in cuts:
        cd = c.get("card")
        if not cd:
            if c.get("image") or c.get("same_as"):
                cards["photo"] += 1
            else:
                ng.append(f"{c['id']} に card も image（場面の絵）も same_as も無い")
            if c.get("motion") and not c.get("image"):
                ng.append(f"{c['id']} motion なのに image が無い")
            continue
        if cd.get("type") not in CARD_TYPES:
            ng.append(f"{c['id']} card の type「{cd.get('type')}」は千年こよみのカードに無い（{sorted(CARD_TYPES)}）")
            continue
        if c.get("motion"):
            ng.append(f"{c['id']} card のあるカットに motion（動く絵は card の無い場面の絵だけ）")
        cards["photo" if cd["type"] == "photo" else "図解"] += 1
        try:
            if cd["type"] == "calendar":
                y, m = cd["year"], cd["month"]
                for mk in cd["marks"]:
                    iso = ymd(y, m, mk["d"])
                    day = DAY.get(iso or "")
                    if not day:
                        ng.append(f"{c['id']} カレンダーの {m}/{mk['d']} が暦に無い")
                        continue
                    for part in mk["lab"].split("・"):
                        h = has(day, part)
                        if h is None:
                            warn.append(f"{c['id']} カレンダーの印の名前「{part}」を照らせない")
                        elif not h:
                            ng.append(f"{c['id']} カレンダー {m}/{mk['d']} は「{part}」ではない")
                marked = {mk["d"] for mk in cd["marks"]}
                if set(cd.get("hl", [])) - marked:
                    ng.append(f"{c['id']} hl の日 {sorted(set(cd['hl']) - marked)} に印が無い")
                if not cd.get("nums") and len(cd["marks"]) > 6:
                    warn.append(f"{c['id']} カレンダーの印が {len(cd['marks'])} 個（1画面の数字は6個まで）")
            elif cd["type"] == "tally":
                mt = re.match(r"(\d{4})年(?:(\d{1,2})月)?", cd.get("title", ""))
                if not mt:
                    ng.append(f"{c['id']} 数の札の title に「〇〇〇〇年（〇月）」が無い（照らせない）")
                    continue
                y, m = int(mt.group(1)), (int(mt.group(2)) if mt.group(2) else None)
                days = month_days(y, m) if m else [d for k, d in DAY.items() if k.startswith(f"{y}-")]
                for it in cd["items"]:
                    if it["name"] in NAME:
                        n = sum(has_name(d, NAME[it["name"]]) for d in days)
                    elif "重なる" in it["name"]:
                        n = sum("天赦日" in d["senjitsu"] and "一粒万倍日" in d["senjitsu"] for d in days)
                    else:
                        warn.append(f"{c['id']} 数の札「{it['name']}」を照らせない")
                        continue
                    if n != it["n"]:
                        ng.append(f"{c['id']} {cd['title']} の {it['name']} が {it['n']}日（暦では {n}日）")
                if len(cd["items"]) > 6:
                    warn.append(f"{c['id']} 数の札が {len(cd['items'])} 行（1画面6個まで）")
            elif cd["type"] == "next_table":
                prev = None
                for r in cd["rows"]:
                    got = dates_in(f"{r['date']}（{r['wd']}）", after=dt.date.fromisoformat(prev) if prev else pub_d)
                    if not got or not got[0][0]:
                        ng.append(f"{c['id']} 次の重なりの日付「{r['date']}」が読めない")
                        continue
                    iso, w, lab = got[0]
                    day = DAY.get(iso)
                    if not day:
                        ng.append(f"{c['id']} 次の重なり {lab} が暦に無い")
                        continue
                    if day["weekday"] != r["wd"]:
                        ng.append(f"{c['id']} 次の重なり {lab} の曜日が {r['wd']}（暦は {day['weekday']}）")
                    for nm in r["names"].split(" × "):
                        if not has_name(day, nm):
                            ng.append(f"{c['id']} 次の重なり {lab} は「{nm}」ではない")
                    if prev and iso < prev:
                        ng.append(f"{c['id']} 次の重なりの表が近い順でない（{lab}）")
                    prev = iso
                    nt_rows.append((c["id"], iso, r))
                if len(cd["rows"]) > 3:
                    warn.append(f"{c['id']} 次の重なりの表が {len(cd['rows'])} 行（3つまで）")
            elif cd["type"] == "timeline":
                ds = [(dates_in(p["label"]) or [(None,)])[0][0] for p in cd["points"]]
                if cd.get("span") and all(ds):
                    i, j, lab = cd["span"]
                    n = (dt.date.fromisoformat(ds[j]) - dt.date.fromisoformat(ds[i])).days
                    if lab != f"{n}日":
                        ng.append(f"{c['id']} 年表の間が「{lab}」（計算では {n}日）")
                for p, iso in zip(cd["points"], ds):
                    if "最強開運日" in p.get("text", "") and iso not in meta["saikyo_kaiun"]:
                        ng.append(f"{c['id']} {p['label']} は最強開運日ではない")
            elif cd["type"] == "kgrid":
                for key, md in (cd.get("dates") or {}).items():
                    mm, dd = map(int, md.split("/"))
                    cand = [x for x in (ymd(pub_d.year - 1, mm, dd), ymd(pub_d.year, mm, dd), ymd(pub_d.year + 1, mm, dd))
                            if x in DAY and "天赦日" in DAY[x]["senjitsu"]]
                    if not cand:
                        ng.append(f"{c['id']} 表の {md} が天赦日ではない")
                        continue
                    ri, ci = map(int, key.split("-"))
                    if not any(DAY[x]["setsugetsu"] == ri * 3 + ci + 1 for x in cand):
                        ng.append(f"{c['id']} 表の {md} の置き場所 {key} が節月と合わない")
                for ri, r_ in enumerate(cd.get("rows", [])):
                    for ci in range(3):
                        want = int(r_["b"] in meta["rules"]["manbai"][str(ri * 3 + ci + 1)])
                        if r_["ok"][ci] != want:
                            ng.append(f"{c['id']} 表の {r_['s']} {r_['m'][ci][0]} の○×が暦の決まりと違う")
        except (KeyError, TypeError, ValueError, IndexError) as e:
            ng.append(f"{c['id']} {cd.get('type')} のカードの形が読めない（{type(e).__name__}: {e}）。見本の形にする")
        if c.get("era") and cd["type"] != "photo" and not cd.get("era"):
            ng.append(f"{c['id']} 昔の場面（era）なのに、画面に「再現イメージ」が出ない（図のカードには era を付けない）")
    era = [c["id"] for c in cuts if c.get("era")]
    if era and not f.get("sources"):
        ng.append(f"昔の場面のカット {era} があるのに、facts.json の sources（道具・服・建物の出典）が空（§6）")

    # 8. 次の重なりの表（どの回にも1回）と、その日付を曜日つきで声で言うカット（§3・§11）
    if not nt_rows:
        ng.append("「次の重なり」の表（card の type が next_table）のカットが無い（§3。どの回にも1回）")
    else:
        cid, iso, r = nt_rows[0]
        if pub and iso < pub:
            ng.append(f"{cid} 次の重なりの1行目 {r['date']} が公開日 {pub} より前")
        names = r["names"].split(" × ")
        want = KS.overlaps(pub or meta["valid_from"], 1, names=names)
        if want and want[0]["iso"] != iso:
            ng.append(f"{cid} 次の重なりの1行目が {r['date']}（公開日から近い順では {want[0]['date']}（{want[0]['wd']}）が先）")
        lab = KS.label(iso)
        say = re.compile(re.escape(lab) + r"[、の]?\s*[（(]?" + DAY[iso]["weekday"] + "曜")
        if not any(say.search(c["narration"]) for c in cuts):
            ng.append(f"次の重なりの1行目 {lab}（{DAY[iso]['weekday']}）を、曜日つきで声で言うカットが無い（例「{lab}、{DAY[iso]['weekday']}曜日」）")

    # 9. 「最強開運日」と一緒に言う日付（§3・§11）
    for c in cuts:
        if "最強開運日" in c["narration"]:
            for iso, w, lab in dates_in(SPAN_SKIP.sub("", c["narration"])):
                if iso and iso not in meta["saikyo_kaiun"] and "次" not in c["narration"] and "前の日" not in c["narration"]:
                    warn.append(f"{c['id']} 「最強開運日」と同じ文に {lab}（重なる日か目で見る）")

    # 10. 1章で声に出る日付と数（§11 の警告）
    ch_, seen = "（前置き）", {}
    for c in cuts:
        ch_ = chap(c) or ch_
        if c.get("speaker", "narrator") == "narrator" and c["id"] not in fixed:
            seen.setdefault(ch_, [])
            seen[ch_] += [m for m in NUM.findall(c["narration"]) if not re.fullmatch(r"\d{1,2}月", m)]
    for k, v in seen.items():
        if k == "（前置き）":
            continue
        u = sorted(set(v), key=v.index)
        if len(u) > 2:
            warn.append(f"章「{k}」で声に出る日付・数が {len(u)} 個：{u}（言い切りは1つ。ほかは画面に任せる）")

    # 11. 章ごとの動く絵・見どころ（§6）
    per, cur = {}, None
    for c in cuts:
        cur = chap(c) or cur
        if cur is None:
            continue
        cd = c.get("card") or {}
        per.setdefault(cur, 0)
        per[cur] += bool((cd and cd.get("type") != "photo") or c.get("motion"))
    still = [k for k, v in per.items() if not v]
    (ng if still else ok).append(f"動くカード（図のカードか motion の場面）の無い章：{still}" if still else f"章 {len(per)} 個の全部に動くカードか motion の場面がある")
    peaks = [c for c in cuts if c.get("peak")]
    if not peaks:
        ng.append("見どころ（\"peak\": true）のカットが無い（§6。1本に1つ以上）")
    for c in peaks:
        if c["id"] in tail:
            ng.append(f"{c['id']} 締めのカットに peak（締めには付けない）")
        cd = c.get("card") or {}
        n = sum([bool(cd and cd.get("type") != "photo") or bool(c.get("motion")), bool(c.get("strong") or c.get("emo") == "strong"),
                 bool((cd.get("pop") or (c.get("photo") or {}).get("pop")) or cd.get("type") in ("big_text", "quote", "next_table"))])
        if n < 2:
            warn.append(f"{c['id']} 見どころなのに、動き・強調（strong）・言葉の札のうち {n} つ（2つ以上で目立たせる）")
    mot = [c["id"] for c in cuts if c.get("motion")]
    if not mot:
        warn.append("motion（Kling で動かす場面の絵）のカットが無い（場面の絵も1〜2割は動かすと紙芝居に見えにくい）")

    # 12. つかみの型（hook_type。§4・§11）
    sents = [x for c in cuts[:3] for x in re.split(r"(?<=[。？！])", c["narration"]) if x.strip()]
    hk = s.get("hook_type")
    lim = 1 if hk == "日付" else 2
    head = "".join(sents[:lim])
    if not re.search(r"\d|[一二三四五六七八九十百千]+(?:日|つ|回|年|か月)", head):
        ng.append(f"hook_type「{hk}」なのに、{lim}文目までに日付か数字が無い：{head}")

    # 13. 画面の配分・人のいない場面（§6）
    p = cards["photo"] / max(1, sum(cards.values()))
    (ok if 0.45 <= p <= 0.65 else warn).append(f"場面の絵 {cards['photo']}・図のカード {cards['図解']}（場面 {p:.0%}。5〜6割）")
    scene = [c for c in cuts if (c.get("image") or c.get("image_en")) and (not c.get("card") or c["card"].get("type") == "photo")]
    nob = [c["id"] for c in scene if not c.get("chars")]
    q = len(nob) / max(1, len(scene))
    (ok if q <= 0.3 else warn).append(f"登場人物のいない場面 {len(nob)}枚（場面の絵の {q:.0%}。3割まで）")
    bad_chars = sorted({x for c in s["cuts"] for x in c.get("chars") or []} - set(
        json.load(open(os.path.join(KS.ROOT, "channels", "spi", "characters", "characters.json"), encoding="utf-8"))["chars"]))
    if bad_chars:
        ng.append(f"chars に、characters.json に無い人：{bad_chars}")
    many = [c["id"] for c in s["cuts"] if len(c.get("chars") or []) > 2]
    if many:
        ng.append(f"1カット3人以上の chars：{many}（2人まで）")

    # 14. 暦の鍵：facts.json の "koyomi" の欄が、neta.json から作り直した値と同じか（書き手が暦の値を書き換えていないか。§8）
    if neta is None:
        warn.append("neta.json が無いので、facts.json の暦の欄を作り直して照らせない（手で作った回）")
    elif not f.get("koyomi"):
        ng.append("facts.json に koyomi の欄が無い（pick_neta_spi.py が置く。消さない）")
    else:
        want = json.loads(json.dumps(KS.facts(neta), ensure_ascii=False))
        if json.dumps(f["koyomi"], ensure_ascii=False, sort_keys=True) != json.dumps(want, ensure_ascii=False, sort_keys=True):
            diff = [k for k in set(want) | set(f["koyomi"]) if json.dumps(want.get(k), sort_keys=True) != json.dumps(f["koyomi"].get(k), sort_keys=True)]
            ng.append(f"facts.json の koyomi の欄が、暦の固定ファイルから作り直した値と違う（書き換えない）：{diff}")
        else:
            ok.append("facts.json の暦の欄＝暦の固定ファイルから作り直した値")
        for k in ("type", "frame", "pub_date", "hook_type", "line_copy", "sub_copy"):
            if neta.get(k) is not None and s.get(k) != neta.get(k):
                ng.append(f"台本の {k}={s.get(k)} が neta.json の {neta.get(k)} と違う（ネタ選びが決めた値のまま）")

    rep = ["OK: " + x for x in ok] + ["注意: " + x for x in warn] + ["NG: " + x for x in ng]
    print("\n".join(rep))
    print("→ NG 0件" if not ng else f"→ NG {len(ng)}件。直してから進める")
    os.makedirs(os.path.join(work, "check"), exist_ok=True)
    open(os.path.join(work, "check", "check_spi.txt"), "w", encoding="utf-8").write("\n".join(rep) + "\n")
    sys.exit(1 if ng else 0)


if __name__ == "__main__":
    main()

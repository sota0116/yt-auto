# ⑥グラフ（設計書 §5⑥・手順書 §3）：script.json の chart カットを、facts.json の値から短い動画にして images\<id>.mp4 に置く
#   python -X utf8 pipeline\make_charts_job.py <作業フォルダ> [--only C01,C02] [--still]
# ・数字はすべて facts.json から取る（台本の文から数字を拾わない）。台本で言う丸めた値（約25万円など）は facts.json の「声」の値
# ・紺の背景に、生成りの文字と黄色の強調。グラフは画面の上 3/4 に収め、下は字幕のためにあける
# ・最初の約1秒で棒が伸びる・カードが出る。そのあとは止めた画面（組み立ての時に声の長さまで最後の画面をのばす）
# ・数字のグラフには出典（facts.json の「加工」）を左下に小さく出す
# ・確かめ用に、最後の画面を images\_charts\<id>.png にも置く（--still なら動画を作らず、これだけ作る）
# ・型D（AI検証）の図：score_bars（採点結果の棒）・source_card（出典カード）・test_compare（確かめ1つの2本の棒）・trend_lines（年ごとの線）・big_text（大きな字の1枚）
#   値は facts.json（d_facts.py が書いた物）だけから取る。出典の字は高さの3%以上（34px）で左下、図は画面の上 3/4 に収める
import argparse, json, math, os, re, subprocess, sys
from PIL import Image, ImageDraw, ImageFont

W, H, FPS, SEC = 1920, 1080, 30, 2.4
NAVY, PANEL, LINE = (20, 31, 52), (31, 46, 74), (58, 76, 108)
KINARI, MUTED, DIM = (243, 235, 221), (139, 157, 186), (86, 102, 132)
YELLOW, CORAL = (242, 193, 78), (226, 132, 112)
FONTS = [r"C:\Windows\Fonts\NotoSansJP-VF.ttf", "/usr/share/fonts/opentype/noto/NotoSansCJK-Black.ttc",
         "/usr/share/fonts/noto-cjk/NotoSansCJK-Black.ttc", r"C:\Windows\Fonts\YuGothB.ttc"]
FONT = next((f for f in FONTS if os.path.exists(f)), None)
SERIFS = [r"C:\Windows\Fonts\NotoSerifJP-VF.ttf", "/usr/share/fonts/opentype/noto/NotoSerifCJK-Bold.ttc",
          "/usr/share/fonts/noto-cjk/NotoSerifCJK-Bold.ttc"]
SERIF = next((f for f in SERIFS if os.path.exists(f)), None)  # 出典カード・山場の大きな字（手順書 §5）。無ければ Noto Sans JP
GREY = (112, 122, 140)  # 型D の2位以下の棒。1位の黄より暗く、紺の地との対比は約3.8:1
SRC = 34  # 型D の出典の字の大きさ（画面の高さの3%以上）
D_KINDS = ("score_bars", "source_card", "test_compare", "trend_lines", "big_text")
TOKUTEN_D ="主な職業の年収・労働時間の一覧と、年齢別 転職で年収が上がった人・下がった人の割合の一覧"
TOKUTEN_B = "年齢別 転職で年収が上がった人・下がった人の割合の一覧"  # 手順書 §4 の型B の特典
ABC_KINDS = ("reasons", "job_vs_all", "compare_table", "bars", "vs_national", "age_line")  # 型A-1・A-3・B・C の図
_cache = {}

UNIT = {"年収": ("年収_万円", lambda v: f"{v:.1f}万円"), "月の労働時間": ("月の労働時間", lambda v: f"{v:g}時間"),
        "時給に直した額": ("時給に直した額_円", lambda v: f"{v:,.0f}円"), "年齢": ("年齢", lambda v: f"{v:.1f}歳")}
TITLE = {"年収": "年収", "月の労働時間": "1か月に働いた時間", "時給に直した額": "時給に直した額", "年齢": "平均の年齢"}
ORDER = {"年収": "高い順", "月の労働時間": "長い順", "時給に直した額": "高い順", "年齢": "高い順"}
QUIZ_Q = {"年収": "年収の1位は？", "月の労働時間": "1か月にいちばん長く働いているのは？", "時給に直した額": "時給に直した額の1位は？"}


def font(size, weight=900, serif=False):
    k = (size, weight, serif)
    if k not in _cache:
        if not FONT:
            sys.exit("【止まりました】日本語のフォント（Noto Sans JP）が見つかりません")
        f = ImageFont.truetype(SERIF if serif and SERIF else FONT, size)
        try:
            f.set_variation_by_axes([weight])
        except Exception:
            pass
        _cache[k] = f
    return _cache[k]


def ease(t):
    t = max(0.0, min(1.0, t))
    return 1 - (1 - t) ** 3


def text(d, xy, s, size, fill=KINARI, weight=900, anchor="la", serif=False):
    d.text(xy, s, font=font(size, weight, serif), fill=fill, anchor=anchor)


def tw(s, size, weight=900, serif=False):
    return font(size, weight, serif).getlength(s)


def fit(s, size, maxw, weight=900, serif=False):
    while size > 20 and tw(s, size, weight, serif) > maxw:
        size -= 2
    return size


def mix(c, a):
    return tuple(int(NAVY[i] + (c[i] - NAVY[i]) * a) for i in range(3))


class Facts:
    def __init__(self, f):
        self.f = f
        jobs = f.get("職業", [])  # 型D・B の facts.json には職業が無い。A-1・C は職業名の文字1つ
        self.jobs = {j["表示名"]: j for j in jobs if isinstance(j, dict)} if isinstance(jobs, list) else {}
        self.source = f.get("加工", "")

    def val(self, job, measure):
        return self.jobs[job][UNIT[measure][0]]

    def fmt(self, measure, v):
        return UNIT[measure][1](v)

    def order(self, measure):
        if measure in self.f["順位"]:
            return self.f["順位"][measure]
        return sorted(self.jobs, key=lambda j: -self.val(j, measure))

    def rank(self, job, measure):
        return self.order(measure).index(job) + 1


def base(title=None, sub=None, source=None):
    im = Image.new("RGB", (W, H), NAVY)
    d = ImageDraw.Draw(im)
    if title:
        d.rectangle((70, 66, 82, 132), fill=YELLOW)
        text(d, (106, 62), title, 64)
        if sub:
            text(d, (106 + tw(title, 64) + 28, 86), sub, 36, MUTED, 700)
    if source:
        text(d, (70, 812), "出典：" + source, 24, DIM, 500)
    return im, d


def bar_rows(d, fx, measure, rows, t, new, highlight=None, hidden=(), names=True, y0=190, y1=780, extra=None):
    """横の棒グラフ。rows は上から順の職業名。new は今回出す行（伸びる）。hidden は「？」で隠す行"""
    n = len(rows)
    rh = (y1 - y0) / n
    vmax = max(fx.val(j, measure) for j in fx.jobs)
    x_bar, bar_max = 790, 780
    for i, job in enumerate(rows):
        yc = y0 + rh * i + rh / 2
        bh = min(64, rh * 0.62)
        rank = i + 1
        if job in hidden or job is None:
            text(d, (80, yc), f"{rank}位", 40, DIM, 700, "lm")
            text(d, (180, yc), "？", 46, DIM, 900, "lm")
            d.rounded_rectangle((x_bar, yc - bh / 2, x_bar + 160, yc + bh / 2), 8, outline=DIM, width=3)
            continue
        k = ease((t - 0.1 - 0.25 * new.index(job)) / 0.9) if job in new else 1.0
        col = YELLOW if job == highlight else (KINARI if job in new else MUTED)
        a = 1.0 if job not in new else min(1.0, 0.3 + k)
        text(d, (80, yc), f"{rank}位", 40, mix(YELLOW if job == highlight else MUTED, a), 700, "lm")
        if names:
            s = fit(job, 46, x_bar - 200)
            text(d, (180, yc), job, s, mix(KINARI, a), 900, "lm")
        v = fx.val(job, measure)
        L = bar_max * v / vmax * k
        if L > 2:
            d.rounded_rectangle((x_bar, yc - bh / 2, x_bar + L, yc + bh / 2), 8, fill=col)
        if k > 0.6:  # 数字は途中の値を出さず、伸びきる直前に正しい値のまま浮かび上がらせる
            text(d, (x_bar + L + 22, yc), fx.fmt(measure, v), 46, mix(col, (k - 0.6) / 0.4), 900, "lm")
    return x_bar, bar_max, vmax, y0, rh


def prev_chart(cuts, i, kind, key, val):
    for c in reversed(cuts[:i]):
        ch = c.get("chart")
        if ch and ch.get("kind") == kind and ch.get(key) == val:
            return ch
    return None


# ここから型D（AI検証）の図の部品
def need(f, key):
    if key not in f:
        sys.exit(f"【止まりました】facts.json に「{key}」がありません（d_facts.py make を回し直す）")
    return f[key]


def d_test(fx, tid):
    """確かめの id（K1 など）から、容疑者の名前と確かめの中身"""
    for r in need(fx.f, "結果"):
        for t in r["確かめ"]:
            if t["id"] == tid:
                return r["名前"], t
    sys.exit(f"【止まりました】facts.json に確かめ {tid} がありません")


def d_source(fx, stats):
    """統計の名前（法人企業統計調査 など）から、出典の1行（府省「統計名」を加工して作成）"""
    names = []
    for st in stats:
        for x in fx.f.get("出典", []):
            n = x["名前"].split("」")[0] + "」"
            if st in n and n not in names:
                names.append(n)
    return "出典：" + "、".join(names) + "を加工して作成" if names else ""


def wrap(s, size, maxw, weight=900, serif=False):
    lines, cur = [], ""
    for ch in s:
        if cur and tw(cur + ch, size, weight, serif) > maxw:
            lines.append(cur)
            cur = ""
        cur += ch
    return lines + ([cur] if cur else [])


def wrap_even(s, size, maxw, weight=900, serif=False):
    """行の長さをそろえて折り返す（最後の行に1字だけ残らないように）"""
    n = len(wrap(s, size, maxw, weight, serif))
    if n <= 1:
        return [s]
    goal = tw(s, size, weight, serif) / n
    lines, cur = [], ""
    for ch in s:
        if cur and len(lines) < n - 1 and tw(cur + ch, size, weight, serif) > goal * 1.08:
            lines.append(cur)
            cur = ""
        cur += ch
    return lines + [cur] if all(tw(x, size, weight, serif) <= maxw for x in lines + [cur]) else wrap(s, size, maxw, weight, serif)


def choice_lines(c, maxw):
    """3択の1つを3行までに。「（…）」の補足は前で折り、44px で次の行に置く"""
    i = c.find("（")
    if i > 0:
        main, note = c[:i], c[i:]
        ls = [(x, 52) for x in wrap_even(main, 52, maxw)]
        ls += [(x, 44) for x in wrap_even(note, 44, maxw)]
        if len(ls) <= 3:
            return ls
    return [(x, 52) for x in wrap_even(c, 52, maxw)[:3]]


def d_base(title, sub, src):
    """型D の図の地。出典は左下に2行まで（字の高さは画面の3%以上）。図は y=700 までに収める"""
    im, d = base(title, sub)
    if src:
        ls = wrap(src, SRC, W - 140, 500)[:2]
        y = 806 - len(ls) * 44
        for line in ls:
            text(d, (70, y), line, SRC, MUTED, 500)
            y += 44
    return im, d


def d_num(v):
    """表の値は桁を変えずに出す（整数の値だけ3桁ごとに区切る）"""
    return f"{int(v):,}" if float(v).is_integer() else f"{v}"


def d_key(key):
    """前後の値の名前（例：利益剰余金_兆円）から、見出しと単位"""
    if key.endswith("_指数用") or "÷" in key:
        sys.exit(f"【止まりました】「{key}」は計算の途中の値なので図に出せません（mode を 値 か 伸び率 にする）")
    for suf, u in (("_兆円", "兆円"), ("_万円", "万円"), ("_千円", "千円"), ("_%", "%")):
        if key.endswith(suf):
            return key[:-len(suf)], u
    return key, ""


def d_years(s):
    """「1995年2月→2026年1～3月」などから、前と後の年の言い方"""
    ys = re.findall(r"\d{4}年(?:度|1～3月|\d+月)?", s)
    return (ys[0], ys[1]) if len(ys) >= 2 else ("前", "後")


def hbars(d, rows, t, unit_fmt, y0=330, gap=200, x0=80, width=1460):
    """横の棒を2～3本。rows は (見出し, 値, 強調か)。0の線から伸ばす（負の値は左へ）"""
    vals = [v for _, v, _ in rows]
    lo, hi = min(0.0, *vals), max(0.0, *vals)
    span = (hi - lo) or 1.0
    xz = x0 + width * (-lo) / span
    if lo < 0:
        d.line((xz, y0 - 90, xz, y0 + gap * (len(rows) - 1) + 60), fill=LINE, width=4)
    for i, (lab, v, hl) in enumerate(rows):
        y = y0 + gap * i
        kk = ease((t - 0.1 - 0.25 * i) / 0.9)
        col = YELLOW if hl else GREY
        text(d, (x0, y - 66), lab, fit(lab, 46, 1700), KINARI, 900, "lm")
        L = width * v / span * kk
        x_a, x_b = (xz, xz + L) if L >= 0 else (xz + L, xz)
        if abs(L) > 2:
            d.rounded_rectangle((x_a, y - 30, x_b, y + 40), 10, fill=col)
        else:
            d.rectangle((xz, y - 30, xz + 6, y + 40), fill=col)
        if kk > 0.6:
            a = (kk - 0.6) / 0.4
            s = unit_fmt(v)
            if v >= 0:
                text(d, (x_b + 22, y + 5), s, 50, mix(YELLOW if hl else KINARI, a), 900, "lm")
            else:
                text(d, (x_a - 22, y + 5), s, 50, mix(YELLOW if hl else KINARI, a), 900, "rm")


def draw_d(k, ch, cuts, idx, fx, t):
    """型D の図。値はすべて facts.json から取る"""
    if k == "score_bars":  # 採点結果の棒（1位は黄、ほかは1位より暗い灰）。shown は下から出した本数
        bars = need(fx.f, "点のグラフ")["棒"]
        full = need(fx.f, "満点")
        if len(bars) > 6:
            sys.exit("【止まりました】採点の棒が6本を超えています（手順書 §3 型D）")
        rank = {r["名前"]: r["順位"] for r in need(fx.f, "順位")}
        n = len(bars)
        shown = ch.get("shown", n)
        pv = prev_chart(cuts, idx, "score_bars", "kind", "score_bars")
        before = min(pv.get("shown", n), shown) if pv else 0
        im, d = d_base("AIの採点結果", f"（{full}点満点）",
                       f"出典：この回で使った政府の統計（一覧は概要欄）を加工して作成。点数は決まった物差し（版{fx.f.get('物差しの版', '')}）で計算")
        y0, y1 = 200, 690
        rh = (y1 - y0) / max(n, 4)
        y0 += (y1 - y0 - rh * n) / 2
        xb, bm = 800, 840
        new = [i for i in range(n) if n - shown <= i < n - before]
        for i, b in enumerate(bars):
            yc = y0 + rh * i + rh / 2
            bh = min(66, rh * 0.62)
            r = rank[b["名前"]]
            top = b["色"] == "黄"
            if i < n - shown:  # まだ伏せている行
                text(d, (80, yc), f"{r}位", 44, DIM, 900, "lm")
                text(d, (200, yc), "？", 50, DIM, 900, "lm")
                d.rounded_rectangle((xb, yc - bh / 2, xb + 160, yc + bh / 2), 8, outline=DIM, width=3)
                continue
            kk = ease((t - 0.1 - 0.3 * (len(new) - 1 - new.index(i))) / 0.9) if i in new else 1.0
            a = min(1.0, 0.3 + kk) if i in new else 1.0
            col = YELLOW if top else GREY
            text(d, (80, yc), f"{r}位", 44, mix(YELLOW if top else KINARI, a), 900, "lm")
            text(d, (200, yc), b["名前"], fit(b["名前"], 46, xb - 240), mix(KINARI, a), 900, "lm")
            L = bm * b["点数"] / full * kk
            if L > 2:
                d.rounded_rectangle((xb, yc - bh / 2, xb + L, yc + bh / 2), 8, fill=mix(col, a))
            else:  # 0点の棒は細い線だけ
                d.rectangle((xb, yc - bh / 2, xb + 6, yc + bh / 2), fill=mix(col, a))
            if kk > 0.6:
                text(d, (xb + max(L, 6) + 24, yc), f"{b['点数']}点", 50, mix(YELLOW if top else KINARI, (kk - 0.6) / 0.4), 900, "lm")
        return im

    if k == "source_card":  # 出典カード：表の値をそのまま、表の名前・年・表の中の位置を添えて
        rows = need(fx.f, "出典カード").get(ch["test"])
        if rows is None:
            sys.exit(f"【止まりました】facts.json の出典カードに {ch['test']} がありません")
        if ch.get("items"):
            rows = [r for r in rows if r["項目"] in ch["items"]]
        items = list(dict.fromkeys(r["項目"] for r in rows))[:3]  # 1画面の数字は6個まで（3項目×2年）
        a = ease(t / 0.6)
        im, d = base(None)
        d.rounded_rectangle((70, 60, 350, 126), 33, fill=mix(YELLOW, a))
        text(d, (210, 93), "出典カード", 40, NAVY, 900, "mm")
        text(d, (380, 93), "統計の表の値（計算する前）", 34, mix(MUTED, a), 700, "lm")
        y = 160
        for tb in list(dict.fromkeys(r["表"] for r in rows if r["項目"] in items))[:2]:
            for line in wrap(tb, SRC, W - 160, 700, True)[:2]:
                text(d, (80, y), line, SRC, mix(KINARI, a), 700, "la", True)
                y += 46
            y += 6
        y = max(y + 24, 320)
        for it in items:
            rs = [r for r in rows if r["項目"] == it][:2]
            text(d, (80, y), it, fit(it, 44, 760, 900, True), mix(KINARI, a), 900, "lm", True)
            pos = "／".join(r["表の中の位置"] for r in rs)
            text(d, (W - 80, y), pos, fit(pos, 30, 960, 700), mix(MUTED, a), 700, "rm")
            x = 110
            for j, r in enumerate(rs):
                if j:
                    text(d, (x + 20, y + 66), "→", 48, mix(MUTED, a), 900, "lm")
                    x += 110
                text(d, (x, y + 66), r["年"], 36, mix(MUTED, a), 700, "lm")
                x += tw(r["年"], 36, 700) + 24
                v = d_num(r["値"])
                text(d, (x, y + 66), v, 54, mix(YELLOW, a), 900, "lm", True)
                x += tw(v, 54, 900, True) + 12
                text(d, (x, y + 72), r["単位"], 32, mix(KINARI, a), 700, "lm")
                x += tw(r["単位"], 32, 700)
            y += 140
        return im

    if k == "test_compare":  # 確かめ1つの値を、2本の棒か、線との比べで見せる
        sus, tt = d_test(fx, ch["test"])
        mode = ch.get("mode") or ("伸び率" if "伸び率" in tt else next((x for x in tt.get("前後", {}) if not (x.endswith("_指数用") or "÷" in x)), "値"))
        src = d_source(fx, tt["統計"])
        y_a, y_b = d_years(tt["年"])
        im, d = d_base(sus, f"（{tt['年']}）", src)
        for i, line in enumerate(wrap(tt["物差し"], SRC, W - 160, 700)[:2]):
            text(d, (106, 160 + i * 44), line, SRC, MUTED, 700)
        if mode == "伸び率":
            g = tt["伸び率"]
            hi = max(g, key=lambda x: g[x])
            hbars(d, [(f"{x}の伸び率", v, x == hi) for x, v in g.items()], t, lambda v: f"{v:+.1f}%")
            foot = f"差 {tt['値']:+.1f}{tt['単位']}"
        elif mode == "値":  # 物差しの値と、支えるの線
            op, line_v = tt["支える"]
            word = {">=": "以上なら支える", "<=": "以下なら支える", "<": "より下なら支える", ">": "より上なら支える"}[op]
            hbars(d, [("物差しの値", tt["値"], "支える" in tt["判定"]), (f"線（この値{word}）", float(line_v), False)], t, lambda v: f"{v:+.1f}{tt['単位']}")  # 黄は支える時だけ
            foot = f"判定：{tt['判定']}"
        else:
            name, unit = d_key(mode)
            v0, v1 = tt["前後"][mode]
            hbars(d, [(f"{name}（{y_a}）", v0, False), (f"{name}（{y_b}）", v1, True)], t, lambda v: f"{v:,.1f}{unit}")
            foot = f"変化 {tt['値']:+.1f}{tt['単位']}" if tt["単位"] == "ポイント" and unit == "%" else ""
        b = ease((t - 1.1) / 0.5)
        if foot and b > 0:
            text(d, (W - 90, 660), foot, 56, mix(YELLOW, b), 900, "rm")
        return im

    if k == "trend_lines":  # 年ごとの線（1～2本）。facts.json のグラフの値だけを使う
        grp = need(fx.f, "グラフ").get(ch["group"])
        if grp is None:
            sys.exit(f"【止まりました】facts.json のグラフに「{ch['group']}」がありません")
        names = ch["series"][:2]
        for nm in names:
            if not isinstance(grp.get(nm), dict):
                sys.exit(f"【止まりました】グラフ「{ch['group']}」に系列「{nm}」がありません")
        pct = [nm.endswith("_%") for nm in names]
        if len(set(pct)) > 1:
            sys.exit("【止まりました】割合（_%）と指数の線は1つの図に混ぜられません")
        firsts = [grp[nm][min(grp[nm], key=int)] for nm in names]
        idx_chart = not pct[0] and ("100" in grp.get("単位", "") or all(v == 100 for v in firsts))  # 始めの年を100にした指数
        unit = "%" if pct[0] or grp.get("単位", "").startswith("%") else ""
        sub = "（%）" if unit else f"（{grp.get('単位', '')}）"
        stats = []
        for nm in names:
            stats += fx.f.get("系列の統計", {}).get(nm, [])
        title = ch.get("title") or (names[0].replace("_%", "") if len(names) == 1 else ch["group"])
        im, d = d_base(title, sub, d_source(fx, stats))
        ys = sorted({int(y) for nm in names for y in grp[nm]})
        vals = [v for nm in names for v in grp[nm].values()]
        lo, hi = min(vals), max(vals)
        pad = (hi - lo) * 0.12 or 1
        lo, hi = lo - pad, hi + pad
        px0, px1, py0, py1 = 200, 1500, 210, 640
        dg = 1 if any(float(v) != int(v) for v in vals) else 0  # 線の端の値は、小数の桁をそろえて出す
        X = lambda y: px0 + (px1 - px0) * (y - ys[0]) / max(1, ys[-1] - ys[0])
        Y = lambda v: py1 - (py1 - py0) * (v - lo) / (hi - lo)
        d.line((px0, py1 + 10, px1, py1 + 10), fill=LINE, width=3)
        text(d, (px0, py1 + 34), f"{ys[0]}", 40, MUTED, 700, "mm")
        text(d, (px1, py1 + 34), f"{ys[-1]}", 40, MUTED, 700, "mm")
        if idx_chart and lo < 100 < hi:  # 始めの年＝100 の線
            for x in range(px0, px1, 28):
                d.line((x, Y(100), x + 14, Y(100)), fill=LINE, width=3)
        hl = ch.get("highlight") or names[0]
        prog = ease((t - 0.1) / 1.3)
        y_cut = ys[0] + (ys[-1] - ys[0]) * prog
        for nm in sorted(names, key=lambda x: x == hl):  # 強調の線を上に重ねる
            col = YELLOW if nm == hl else GREY
            pts = sorted((int(y), v) for y, v in grp[nm].items())
            for (ya, va), (yb, vb) in zip(pts, pts[1:]):
                if yb - ya > 1 or ya > y_cut:  # 年が抜けている所は線を切る
                    continue
                f = min(1.0, (y_cut - ya) / (yb - ya))
                d.line((X(ya), Y(va), X(ya) + (X(yb) - X(ya)) * f, Y(va) + (Y(vb) - Y(va)) * f), fill=col, width=9 if nm == hl else 7)
            if prog > 0.95:
                (y_e, v_e), (y_s, v_s) = pts[-1], pts[0]
                lab = nm.replace("_%", "")
                text(d, (X(y_e) + 24, Y(v_e) - 26), f"{v_e:.{dg}f}{unit}", 46, col, 900, "lm")
                text(d, (X(y_e) + 24, Y(v_e) + 22), lab, fit(lab, 30, W - X(y_e) - 40, 700), col, 700, "lm")
                if not idx_chart:
                    text(d, (X(y_s) - 16, Y(v_s)), f"{v_s:.{dg}f}{unit}", 40, col, 900, "rm")
        return im

    if k == "big_text":  # 暗い地に大きな字の1枚（言い切らない所の見せ方。手順書 §3 型D）
        a = ease(t / 0.8)
        im, d = base(None)
        ls = wrap_even(ch["text"], 84, 1600, 900, True)[:4]
        y = 420 - (len(ls) - 1) * 60
        for line in ls:
            text(d, (W / 2, y), line, 84, mix(KINARI, a), 900, "mm", True)
            y += 120
        return im
    return None


def draw(cut, cuts, idx, fx, s, t, tokuten_png):
    ch = cut["chart"]
    k = ch["kind"]
    src = fx.source

    if k == "bar_reveal":
        m = ch["measure"]
        order = fx.order(m)
        shown, hid = ch.get("shown", 0), ch.get("hidden", 0)
        pv = prev_chart(cuts, idx, "bar_reveal", "measure", m)
        before = pv.get("shown", 0) if pv and pv is not cut["chart"] else 0
        revealed = order[len(order) - shown:] if shown else []
        new = [j for j in reversed(order[len(order) - shown:len(order) - before])] if shown > before else []
        hidden = [j for j in order if j not in revealed]
        im, d = base(TITLE[m], f"（{ORDER[m]}・6つの仕事）", src)
        bar_rows(d, fx, m, order, t, new, ch.get("highlight"), hidden)
        if hid:  # 残りの行が何の仕事かだけ明かす（順位はまだ）
            names = [j for j in order if j not in revealed][:hid]
            ys = 190 + (780 - 190) / 6 * 0, 190 + (780 - 190) / 6 * hid
            a = ease(t / 0.6)
            d.rounded_rectangle((1000, ys[0] + 14, 1820, ys[1] - 14), 18, outline=mix(YELLOW, a), width=4, fill=mix(PANEL, a))
            text(d, (1410, (ys[0] + ys[1]) / 2), " ／ ".join(names), fit(" ／ ".join(names), 50, 760), mix(KINARI, a), 900, "mm")
        return im

    if k == "range":  # 名前はまだ伏せて、いちばん上と下だけ数字を出す
        m = ch["measure"]
        order = fx.order(m)
        im, d = base(TITLE[m], "（6つの仕事・高い順）", src)
        gap = fx.f["言い直し"]["年収の差（いちばん上と下）"]
        vmax = fx.val(order[0], m)
        y0, rh, xb, bm = 190, (780 - 190) / 6, 420, 900
        kk = ease((t - 0.1) / 0.9)
        for i, job in enumerate(order):
            yc = y0 + rh * i + rh / 2
            ends = i in (0, len(order) - 1)
            col = YELLOW if ends else MUTED
            L = bm * fx.val(job, m) / vmax * kk
            text(d, (80, yc), "いちばん上" if i == 0 else ("いちばん下" if ends else ""), 46, YELLOW, 900, "lm")
            if L > 2:
                d.rounded_rectangle((xb, yc - 32, xb + L, yc + 32), 8, fill=col)
            if ends and kk > 0.05:
                text(d, (xb + L + 22, yc), fx.fmt(m, fx.val(job, m)), 46, YELLOW, 900, "lm")
        a = ease((t - 1.0) / 0.5)
        if a > 0:
            x = 1640
            ya, yb = y0 + rh / 2, y0 + rh * (len(order) - 0.5)
            for yy in (ya, yb):
                d.line((x - 24, yy, x, yy), fill=mix(YELLOW, a), width=6)
            d.line((x, ya, x, yb), fill=mix(YELLOW, a), width=6)
            ym = (ya + yb) / 2
            d.rounded_rectangle((x + 30, ym - 80, x + 290, ym + 80), 16, fill=mix(PANEL, a), outline=mix(YELLOW, a), width=4)
            text(d, (x + 160, ym - 28), "差は", 36, mix(MUTED, a), 700, "mm")
            text(d, (x + 160, ym + 28), gap["声"], 54, mix(YELLOW, a), 900, "mm")
        return im

    if k == "quiz":
        m = ch.get("measure")  # 型D は measure が無く、question を使う
        im, d = base(None)
        d.rounded_rectangle((W / 2 - 150, 90, W / 2 + 150, 170), 40, fill=YELLOW)
        text(d, (W / 2, 130), "クイズ", 52, NAVY, 900, "mm")
        q = ch.get("question") or (QUIZ_Q[m] if m in QUIZ_Q else fx.f.get("クイズ", {}).get("問い", ""))  # 型D は台本の問い・A-1 は facts.json のクイズ
        text(d, (W / 2, 260), q, fit(q, 76, 1700), KINARI, 900, "mm")
        choices = ch.get("choices") or fx.f.get("クイズ", {}).get("選択肢", [])
        if not 2 <= len(choices) <= 3:
            sys.exit(f"【止まりました】クイズの選択肢は2つか3つ：{cut['id']}")
        if len(choices) == 3:  # A-1 の3択（長い理由は2〜3行に折り返す）
            for i, c in enumerate(choices):
                a = ease((t - 0.2 - 0.25 * i) / 0.6)
                x0 = 80 + i * 600
                yo = (1 - a) * 60
                d.rounded_rectangle((x0, 380 + yo, x0 + 560, 700 + yo), 28, fill=mix(PANEL, a), outline=mix(MUTED, a), width=4)
                d.ellipse((x0 + 30, 405 + yo, x0 + 120, 495 + yo), fill=mix(YELLOW, a))
                text(d, (x0 + 75, 450 + yo), "ABC"[i], 56, NAVY, 900, "mm")
                ls = choice_lines(c, 490)
                y = 590 - (len(ls) - 1) * 33 + yo
                for line, size in ls:
                    text(d, (x0 + 280, y), line, size, mix(KINARI if size == 52 else MUTED, a), 900, "mm")
                    y += 66
            return im
        for i, c in enumerate(choices):
            a = ease((t - 0.2 - 0.25 * i) / 0.6)
            x0 = 160 + i * 820
            yo = (1 - a) * 60
            d.rounded_rectangle((x0, 380 + yo, x0 + 780, 700 + yo), 28, fill=mix(PANEL, a), outline=mix(MUTED, a), width=4)
            d.ellipse((x0 + 40, 420 + yo, x0 + 140, 520 + yo), fill=mix(YELLOW, a))
            text(d, (x0 + 90, 470 + yo), "AB"[i], 60, NAVY, 900, "mm")
            text(d, (x0 + 390, 590 + yo), c, fit(c, 72, 680), mix(KINARI, a), 900, "mm")
        return im

    if k == "bar_gap":
        m = ch["measure"]
        a_, b_ = ch["pair"]
        im, d = base(TITLE[m], "（いちばん上と下）", src)
        va, vb = fx.val(a_, m), fx.val(b_, m)
        vmax = max(va, vb)
        x0, bm = 600, 1000
        ys = (330, 560)
        for (job, v, y) in ((a_, va, ys[0]), (b_, vb, ys[1])):
            kk = ease((t - 0.1) / 0.9)
            text(d, (80, y - 70), job, fit(job, 46, 1500), KINARI, 900, "lm")
            col = YELLOW if v == vmax else MUTED
            d.rounded_rectangle((80, y - 30, 80 + (x0 + bm - 80) * v / vmax * kk, y + 50), 10, fill=col)
            text(d, (100 + (x0 + bm - 80) * v / vmax * kk, y + 10), fx.fmt(m, v), 48, col, 900, "lm")
        diff = abs(va - vb)
        lab = f"{diff:g}時間" if m == "月の労働時間" else (f"約{int(diff / 10 + 0.5) * 10:,}円" if m == "時給に直した額" else fx.fmt(m, diff))
        a = ease((t - 1.0) / 0.5)
        if a > 0:
            xs = 80 + (x0 + bm - 80) * min(va, vb) / vmax
            xe = 80 + (x0 + bm - 80)
            y = 690
            d.line((xs, ys[0] + 50, xs, y), fill=mix(YELLOW, a), width=4)
            d.line((xe, ys[0] + 50, xe, y), fill=mix(YELLOW, a), width=4)
            d.line((xs, y, xe, y), fill=mix(YELLOW, a), width=6)
            text(d, ((xs + xe) / 2, y + 50), "差は " + lab, 56, mix(YELLOW, a), 900, "mm")
        return im

    if k == "breakdown":
        m = ch["measure"]
        p0, p1 = ch["parts"]
        im, d = base(TITLE[m], "（うち、残業など）", src)
        vmax = max(fx.jobs[j]["月の労働時間"] for j in ch["jobs"])
        L = 1250
        for i, job in enumerate(ch["jobs"]):
            y = 300 + i * 230
            j = fx.jobs[job]
            text(d, (80, y - 70), job, fit(job, 46, 1500), KINARI, 900, "lm")
            w0 = L * j[p0] / vmax
            w1 = L * j[p1] / vmax * ease((t - 0.3) / 0.9)
            d.rectangle((80, y - 30, 80 + w0, y + 50), fill=MUTED)
            if w1 > 1:
                d.rectangle((80 + w0, y - 30, 80 + w0 + w1, y + 50), fill=YELLOW)
            text(d, (80 + w0 / 2, y + 10), f"決まった時間 {j[p0]}時間", 38, NAVY, 900, "mm")
            if w1 > 1:
                text(d, (80 + w0 + w1 + 24, y + 10), f"残業など {j[p1]}時間", 46, YELLOW, 900, "lm")
        return im

    if k == "formula":
        im, d = base(None)
        a = ease(t / 0.6)
        b = ease((t - 0.8) / 0.6)
        text(d, (W / 2, 330), ch["text"], fit(ch["text"], 96, 1700), mix(KINARI, a), 900, "mm")
        d.line((W / 2 - 600, 440, W / 2 + 600, 440), fill=mix(LINE, a), width=4)
        text(d, (W / 2, 560), "＝ 時給に直した額", 96, mix(YELLOW, b), 900, "mm")
        text(d, (W / 2, 700), "（ボーナスも含めた1年分の収入を、残業も含めた1年分の時間で割る）", 34, mix(MUTED, b), 700, "mm")
        return im

    if k == "title_cards":
        im, d = base(None)
        text(d, (W / 2, 150), "3つの物差しで並べる", 68, KINARI, 900, "mm")
        for i, it in enumerate(ch["items"]):
            a = ease((t - 0.15 - 0.3 * i) / 0.5)
            x0 = 110 + i * 580
            yo = (1 - a) * 50
            d.rounded_rectangle((x0, 280 + yo, x0 + 540, 700 + yo), 28, fill=mix(PANEL, a), outline=mix(YELLOW if i == 2 else MUTED, a), width=4)
            text(d, (x0 + 270, 360 + yo), f"物差し {i + 1}", 40, mix(YELLOW, a), 700, "mm")
            text(d, (x0 + 270, 520 + yo), it, fit(it, 64, 480), mix(KINARI, a), 900, "mm")
        return im

    if k == "rank_table":
        ms = ch["measures"]
        rows = fx.order(ms[0])
        im, d = base("順位を並べると", "（6つの仕事）", src)
        cx = [820 + i * (1000 / len(ms)) for i in range(len(ms))]
        cw = 1000 / len(ms)
        for i, m in enumerate(ms):
            text(d, (cx[i] + cw / 2, 200), TITLE[m], fit(TITLE[m], 40, cw - 30), MUTED, 900, "mm")
        oldest = sorted(fx.jobs, key=lambda j: -fx.jobs[j]["年齢"])[:2] if "年齢" in ms else []
        for r, job in enumerate(rows):
            a = ease((t - 0.1 - 0.12 * r) / 0.5)
            y = 290 + r * 88
            d.rounded_rectangle((70, y - 38, 1830, y + 38), 12, fill=mix(PANEL, a * (1 if r % 2 == 0 else 0.6)))
            text(d, (100, y), job, fit(job, 42, 680), mix(KINARI, a), 900, "lm")
            for i, m in enumerate(ms):
                if m == "年齢":
                    v = fx.jobs[job]["年齢"]
                    col = YELLOW if job in oldest else KINARI
                    text(d, (cx[i] + cw / 2, y), f"{v:.1f}歳", 44, mix(col, a), 900, "mm")
                    continue
                rk = fx.rank(job, m)
                col = KINARI
                if m == "時給に直した額" and "年収" in ms:  # 矢印は「年収の順位 → 時給の順位」の動きだけ
                    mv = fx.rank(job, "年収") - rk
                    col = YELLOW if mv > 0 else (CORAL if mv < 0 else KINARI)
                    if mv:
                        text(d, (cx[i] + cw / 2 + 80, y), ("↑" if mv > 0 else "↓") + str(abs(mv)), 34, mix(col, a), 900, "lm")
                text(d, (cx[i] + cw / 2, y), f"{rk}位", 48, mix(col, a), 900, "mm")
        return im

    if k == "rank_swap":
        jobs = ch["jobs"]
        shown = ch.get("shown", 0)
        pv = prev_chart(cuts, idx, "rank_swap", "jobs", jobs)
        before = pv.get("shown", 0) if pv else 0
        im, d = base("順位が大きく動いた3つ", "（年収の順位 → 時給の順位）", src)
        for i, job in enumerate(jobs):
            y = 300 + i * 165
            if i >= shown:
                d.rounded_rectangle((70, y - 60, 1830, y + 60), 16, outline=LINE, width=3)
                text(d, (110, y), "？", 50, DIM, 900, "lm")
                continue
            a = ease((t - 0.1) / 0.6) if i >= before else 1.0
            hl = ch.get("highlight") == job
            d.rounded_rectangle((70, y - 60, 1830, y + 60), 16, fill=mix(PANEL, a), outline=mix(YELLOW if hl else LINE, a), width=4)
            text(d, (110, y), job, fit(job, 48, 700), mix(KINARI, a), 900, "lm")
            r0, r1 = fx.rank(job, "年収"), fx.rank(job, "時給に直した額")
            text(d, (900, y), "年収", 34, mix(MUTED, a), 700, "rm")
            text(d, (920, y), f"{r0}位", 60, mix(KINARI, a), 900, "lm")
            b = ease((t - 0.5) / 0.6) if i >= before else 1.0
            col = YELLOW if r1 < r0 else CORAL
            d.line((1100, y, 1100 + 220 * b, y), fill=mix(col, b), width=8)
            if b > 0.9:
                d.polygon([(1320, y - 22), (1350, y), (1320, y + 22)], fill=col)
            text(d, (1530, y), "時給", 34, mix(MUTED, b), 700, "rm")
            text(d, (1550, y), f"{r1}位", 60, mix(col, b), 900, "lm")
        return im

    if k == "calendar_days":
        node = fx.f
        for key in ch["ref"].split("."):
            node = node[key]
        days = int(round(float(node)))
        g = fx.f["言い直し"]["月の労働時間の差（いちばん長いと短い）"]
        im, d = base("働く時間の差を、日に直すと", "（1日8時間で数えた場合）", src)
        cols, size, gap_ = 37, 36, 8
        x0, y0 = (W - cols * (size + gap_)) / 2, 200
        lit = int(days * ease((t - 0.1) / 1.4))
        for i in range(365):
            r, c = divmod(i, cols)
            x, y = x0 + c * (size + gap_), y0 + r * (size + gap_)
            d.rounded_rectangle((x, y, x + size, y + size), 6, fill=YELLOW if i < lit else PANEL)
        text(d, (W / 2, 690), f"1年 365日のうち 約{days}日分", 64, KINARI, 900, "mm")
        text(d, (W / 2, 770), f"（{g['長い']}と{g['短い']}の、1年の差 {g['年_時間']}時間 ÷ 8時間。出勤した日数ではありません）", 30, MUTED, 700, "mm")
        return im

    if k == "tokuten":
        im, d = base(None)
        if tokuten_png and os.path.exists(tokuten_png):
            p = Image.open(tokuten_png).convert("RGB")
            p.thumbnail((620, 640))
            a = ease(t / 0.6)
            im.paste(p, (int(150 + (1 - a) * -60), int(110 + (640 - p.size[1]) / 2)))
            d = ImageDraw.Draw(im)
            d.rectangle((150 + (1 - a) * -60 - 4, 106 + (640 - p.size[1]) / 2, 150 + (1 - a) * -60 + p.size[0] + 4,
                         114 + (640 - p.size[1]) / 2 + p.size[1]), outline=YELLOW, width=4)
        d.rounded_rectangle((900, 150, 1260, 220), 35, fill=YELLOW)
        text(d, (1080, 185), "LINEで受け取れます", 36, NAVY, 900, "mm")
        title = s.get("tokuten_title") or (TOKUTEN_D if s.get("type") == "D" else TOKUTEN_B if s.get("type") == "B" else "主な職業の年収と労働時間の一覧")
        y = 300
        line = ""
        for chh in title:  # 2行までに折り返す
            if tw(line + chh, 58) > 880 and chh not in "・、。":  # 「・」「、」は行の頭に置かず、前の行の終わりにぶら下げる
                text(d, (900, y), line, 58); y += 80; line = ""
            line += chh
        text(d, (900, y), line, 58)
        text(d, (900, y + 130), "概要欄のLINEから", 46, MUTED, 700)
        return im

    if k in D_KINDS:
        return draw_d(k, ch, cuts, idx, fx, t)
    if k in ABC_KINDS:
        return draw_abc(k, ch, cuts, idx, fx, t)
    raise SystemExit(f"【止まりました】知らないグラフの種類：{k}（{cut['id']}）")


def render(work, cut, cuts, idx, fx, s, still_only, tokuten_png):
    os.makedirs(os.path.join(work, "images", "_charts"), exist_ok=True)
    last = draw(cut, cuts, idx, fx, s, 99.0, tokuten_png)
    last.save(os.path.join(work, "images", "_charts", cut["id"] + ".png"))
    if still_only:
        return
    out = os.path.join(work, "images", cut["id"] + ".mp4")
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
                          "-i", "-", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "16", "-preset", "fast", out],
                         stdin=subprocess.PIPE)
    n = int(SEC * FPS)
    for f in range(n):
        p.stdin.write(draw(cut, cuts, idx, fx, s, f / FPS, tokuten_png).tobytes())
    p.stdin.close()
    if p.wait():
        sys.exit(f"【止まりました】ffmpeg でグラフの動画を作れません：{cut['id']}")


def main():
    a = argparse.ArgumentParser()
    a.add_argument("work")
    a.add_argument("--only", default="")
    a.add_argument("--still", action="store_true")
    a.add_argument("--tokuten", default="", help="特典の見本の絵（無ければ、文字だけのカード）")
    a = a.parse_args()
    s = json.load(open(os.path.join(a.work, "script.json"), encoding="utf-8"))
    fx = Facts(json.load(open(os.path.join(a.work, "facts.json"), encoding="utf-8")))
    only = set(filter(None, a.only.split(",")))
    cuts = s["cuts"]
    done = 0
    for i, c in enumerate(cuts):
        if c.get("chart") and (not only or c["id"] in only):
            render(a.work, c, cuts, i, fx, s, a.still, a.tokuten)
            done += 1
            print(c["id"], c["chart"]["kind"], flush=True)
    print(f"グラフ {done} 個{'（止めた絵だけ）' if a.still else ''}：images\\_charts に確かめ用の絵")


# ここから型A-1・A-3・B・C の図（手順書 §3・§5）。値は facts.json だけから取る。
# 出典は左下に字の高さ3%以上（d_base）、項目名と数字は4%以上（44px 以上）、1画面の数字は6個まで、山場の値だけ黄
A_UNIT = {"年収": lambda v: f"{v:.1f}万円", "月の労働時間": lambda v: f"{v:g}時間", "時給に直した額": lambda v: f"{v:,.0f}円",
          "平均年齢": lambda v: f"{v:.1f}歳", "勤続年数": lambda v: f"{v:.1f}年"}
M_NAME = {"年収_万円": ("年収", lambda v: f"{v:.1f}万円"), "月の労働時間": ("1か月に働いた時間", lambda v: f"{v:g}時間"),
          "平均年齢": ("平均の年齢", lambda v: f"{v:.1f}歳"), "勤続年数": ("勤続年数", lambda v: f"{v:.1f}年"),
          "時給に直した額_円": ("時給に直した額", lambda v: f"{v:,.0f}円")}


def src_of(fx, keys):
    """出典の key から、出典の1行（〇〇を加工して作成）。key が無ければ facts.json の「加工」"""
    names = [x["名前"] for x in fx.f.get("出典", []) if isinstance(x, dict) and x.get("key") in keys]
    if names:
        return "出典：" + "、".join(names) + "を加工して作成"
    return "出典：" + fx.source if fx.source else ""


def head(title, sub, src):
    """見出し（長い時は字を小さく、副題は下の行へ）と、左下の出典（d_base と同じ3%以上）"""
    im, d = d_base(None, None, src)
    d.rectangle((70, 66, 82, 132), fill=YELLOW)
    s = fit(title, 64, W - 200)
    text(d, (106, 99), title, s, KINARI, 900, "lm")
    if sub:
        x = 106 + tw(title, s) + 28
        if x + tw(sub, 36, 700) < W - 70:
            text(d, (x, 104), sub, 36, MUTED, 700, "lm")
        else:
            text(d, (106, 152), sub, fit(sub, 36, W - 200, 700), MUTED, 700, "lm")
    return im, d


def label(d, x, yc, s, maxw, col, size=46):
    """項目名を1行で（入らない時は44pxで2行に折る。4%より小さくしない）"""
    if tw(s, size) <= maxw:
        text(d, (x, yc), s, size, col, 900, "lm")
        return
    if tw(s, 44) <= maxw:
        text(d, (x, yc), s, 44, col, 900, "lm")
        return
    i = s.find("（")
    if i > 0 and tw(s[:i], 44) <= maxw and tw(s[i:], 44) <= maxw:  # 「（…）」の補足は前で折る
        ls = [s[:i], s[i:]]
    else:
        ls = wrap_even(s, 44, maxw)[:2]
    for k, line in enumerate(ls):
        text(d, (x, yc + (k - (len(ls) - 1) / 2) * 50), line, 44, col, 900, "lm")


def draw_abc(k, ch, cuts, idx, fx, t):
    f = fx.f
    if k == "reasons":  # A-1：辞める理由5つ。上が1位。shown は下（5位）から出した数。1位の棒だけ黄
        five = need(f, "辞める理由_5つ")
        if len(five) != 5:
            sys.exit("【止まりました】facts.json の辞める理由が5つではありません（a1_facts.py make を回し直す）")
        shown = ch.get("shown", 0)
        pv = prev_chart(cuts, idx, "reasons", "kind", "reasons")
        before = min(pv.get("shown", 0), shown) if pv else 0
        ind = f.get("業界", {}).get("声の名前", "")
        im, d = head("前の職場を辞めた理由", f"（{ind}に転職した人・割合の大きい順）", src_of(fx, ["koyodoko_r7_t12"]))
        y0, y1 = 200, 700
        rh = (y1 - y0) / 5
        vmax = max(r["割合_%"] for r in five)
        xb, bm = 1080, 560
        for i, r in enumerate(reversed(five)):
            yc = y0 + rh * i + rh / 2
            bh = min(60, rh * 0.6)
            nth = 5 - i  # 何番目に出す行か（5位が1番目）
            if nth > shown:
                text(d, (80, yc), f"{r['順位']}位", 44, DIM, 900, "lm")
                text(d, (210, yc), "？", 50, DIM, 900, "lm")
                d.rounded_rectangle((xb, yc - bh / 2, xb + 160, yc + bh / 2), 8, outline=DIM, width=3)
                continue
            new = nth > before
            kk = ease((t - 0.1) / 0.9) if new else 1.0
            a = min(1.0, 0.3 + kk) if new else 1.0
            top = r["順位"] == 1
            text(d, (80, yc), f"{r['順位']}位", 44, mix(YELLOW if top else KINARI, a), 900, "lm")
            label(d, 210, yc, r["理由"], xb - 250, mix(KINARI if new or top else MUTED, a))
            L = bm * r["割合_%"] / vmax * kk
            if L > 2:
                d.rounded_rectangle((xb, yc - bh / 2, xb + L, yc + bh / 2), 8, fill=mix(YELLOW if top else GREY, a))
            if kk > 0.6:
                text(d, (xb + L + 22, yc), f"{r['割合_%']:.1f}%", 48, mix(YELLOW if top else KINARI, (kk - 0.6) / 0.4), 900, "lm")
        return im

    if k == "job_vs_all":  # A-1：この職業と全産業の平均を、物差しごとに2本ずつ（3つまで＝数字6個まで）
        g = need(f, "棒グラフ")
        rows = {b["物差し"]: b for b in g["棒"]}
        ms = ch.get("measures") or [g["棒"][0]["物差し"]]
        if len(ms) > 3 or any(m not in rows for m in ms):
            sys.exit(f"【止まりました】job_vs_all の measures は facts.json の棒グラフの物差しから3つまで：{ms}")
        hl = ch.get("highlight")
        ind = f.get("業界", {}).get("声の名前", "業界")
        im, d = head(g["題"], "", src_of(fx, []))
        gh = (705 - 180) / len(ms)
        for gi, m in enumerate(ms):
            b = rows[m]
            if m.endswith("_%"):
                name, fmt = m[:-2], (lambda v: f"{v:.1f}%")
            else:
                name, fmt = M_NAME.get(m, (m, lambda v: f"{v:g}"))
            series = [(ind if kk == "業界" else kk, v) for kk, v in b.items() if kk != "物差し" and isinstance(v, (int, float))]
            vmax = max(v for _, v in series) or 1
            ytop = 180 + gh * gi
            kk_ = ease((t - 0.1 - 0.25 * gi) / 0.9)
            text(d, (80, ytop + 26), name, fit(name, 46, 1700), MUTED, 900, "lm")
            for si, (sn, v) in enumerate(series):
                yc = ytop + 78 + si * 58
                main_bar = si == 0
                col = YELLOW if (main_bar and m == hl) else (GREY if main_bar else DIM)
                label(d, 120, yc, sn, 520, KINARI if main_bar else MUTED, 44)
                L = 900 * v / vmax * kk_  # 右に値（260px くらい）が入るように、棒は900まで
                if L > 2:
                    d.rounded_rectangle((660, yc - 22, 660 + L, yc + 22), 8, fill=col)
                if kk_ > 0.6:
                    text(d, (660 + L + 20, yc), fmt(v), 46, mix(YELLOW if (main_bar and m == hl) else KINARI, (kk_ - 0.6) / 0.4), 900, "lm")
        return im

    if k == "compare_table":  # A-3：2つの職業を項目ごとに。○がよい方。数字は values と highlight の行だけ（3行まで＝6個まで）
        js = [j["表示名"] for j in need(f, "職業")][:2]
        rows = {r["項目"]: r for r in need(f, "項目ごと")}
        items = ch.get("items") or need(f, "比べる項目")
        if any("離職率" in x or x not in rows for x in items):
            sys.exit(f"【止まりました】比べの表の項目が facts.json の比べる項目に無い（離職率は比べない）：{items}")
        hl = ch.get("highlight")
        vals = set(ch.get("values", [])) | ({hl} if hl else set())
        if len(vals) > 3:
            sys.exit("【止まりました】比べの表で数字を出す行は3つまで（1画面の数字は6個まで）")
        shown = ch.get("shown", len(items))
        pv = prev_chart(cuts, idx, "compare_table", "kind", "compare_table")
        before = min(pv.get("shown", len(items)), shown) if pv and (pv.get("items") or f["比べる項目"]) == items else 0
        im, d = head(f"{js[0]}と{js[1]}", "（○がよい方）", src_of(fx, []))
        cx = (1000, 1530)
        for j, nm in enumerate(js):
            text(d, (cx[j], 230), nm, fit(nm, 46, 500), KINARI, 900, "mm")
        y0 = 280
        rh = min(90, (700 - y0) / len(items))
        for i, it in enumerate(items):
            r = rows[it]
            y = y0 + rh * i + rh / 2
            on = i < shown
            new = on and i >= before
            a = ease((t - 0.1) / 0.6) if new else 1.0
            is_hl = it == hl
            d.rounded_rectangle((70, y - rh / 2 + 6, 1830, y + rh / 2 - 6), 12, fill=mix(PANEL, a * (1 if on else 0.5)),
                                outline=mix(YELLOW, a) if (is_hl and on) else None, width=4)
            text(d, (100, y), it, fit(it, 46, 620), mix(KINARI if on else DIM, a if on else 1), 900, "lm")
            if not on:
                continue
            if r.get("勝った方") is None:
                if it not in vals:
                    text(d, ((cx[0] + cx[1]) / 2, y), "判定しない", 44, mix(MUTED, a), 700, "mm")
            for j, nm in enumerate(js):
                win = r.get("勝った方") == nm
                col = YELLOW if (is_hl and win) else KINARI
                s = ("○ " if win else "") + (A_UNIT[it](r[nm]) if it in vals else "")
                if s:
                    text(d, (cx[j], y), s.strip(), 50 if it in vals else 58, mix(col, a), 900, "mm")
        return im

    if k == "bars":  # 型B：facts.json のグラフ（6本まで）。強調の棒だけ黄。注に「（300千円）の線を引く」があれば線を引く
        gs = need(f, "グラフ")
        gi = ch.get("graph", 0)
        if not isinstance(gi, int) or not 0 <= gi < len(gs):
            sys.exit(f"【止まりました】facts.json のグラフに {gi} 番がありません")
        g = gs[gi]
        bars = g["棒"]
        if len(bars) > 6 or any(b["値"] < 0 for b in bars):
            sys.exit("【止まりました】型B のグラフは0以上の棒6本まで")
        note = g.get("注") or ""
        m = re.search(r"([^、。]*?)（([\d,.]+)(\S+?)）の線を引く", note)
        line = None
        if m:
            if m.group(3) != g["単位"]:
                sys.exit(f"【止まりました】グラフの注の線の単位が、グラフの単位（{g['単位']}）と違う：{note}")
            line = (m.group(1).replace("題の前提の", "題の前提 "), float(m.group(2).replace(",", "")))
        every = len(bars) + (1 if line else 0) <= 6  # 数字が6個を超える時は、強調の棒の値（と線）だけ出す
        im, d = head(g["題"], "" if line else (f"（{note}）" if note else ""), src_of(fx, [g.get("出典key")]))
        vmax = max([b["値"] for b in bars] + ([line[1]] if line else []))
        nw = max(tw(b["名前"], 46) for b in bars)
        y0 = 250 if line else 200
        y1 = 690
        rh = (y1 - y0) / max(len(bars), 3)
        side = nw <= 560
        xb = 80 + (nw + 50 if side else 0)
        bm = 1500 - xb
        if line:  # 線は棒より先に引く（値の字が線の上に乗るように）
            a = ease((t - 0.9) / 0.5)
            x = xb + bm * line[1] / vmax
            for yy in range(int(y0 - 10), int(y1), 26):
                d.line((x, yy, x, yy + 14), fill=mix(KINARI, a), width=4)
            text(d, (x, y0 - 22), line[0], 44, mix(KINARI, a), 900, "mb" if x > 500 else "lb")
        for i, b in enumerate(bars):
            yc = y0 + rh * i + rh / 2
            hi = b["名前"] == g.get("強調")
            kk = ease((t - 0.1 - 0.12 * i) / 0.9)
            col = YELLOW if hi else GREY
            if side:
                text(d, (80, yc), b["名前"], 46, YELLOW if hi else KINARI, 900, "lm")
                by, bh = yc, min(60, rh * 0.6)
            else:
                text(d, (80, yc - rh * 0.22), b["名前"], fit(b["名前"], 46, 1700), YELLOW if hi else KINARI, 900, "lm")
                by, bh = yc + rh * 0.22, min(48, rh * 0.36)
            L = bm * b["値"] / vmax * kk
            if L > 2:
                d.rounded_rectangle((xb, by - bh / 2, xb + L, by + bh / 2), 8, fill=col)
            else:
                d.rectangle((xb, by - bh / 2, xb + 6, by + bh / 2), fill=col)
            if kk > 0.6 and (every or hi):
                vx = xb + max(L, 6) + 20
                if line:  # 値の後ろを地の色で塗り、点線と重ねない
                    d.rectangle((vx - 10, by - 30, vx + tw(b["表示"], 46) + 10, by + 30), fill=NAVY)
                text(d, (vx, by), b["表示"], 46, mix(YELLOW if hi else KINARI, (kk - 0.6) / 0.4), 900, "lm")
        return im

    if k == "vs_national":  # 型C：この職業と全産業の平均（3行まで＝数字6個まで。差は2行以下の時だけ）
        rows = {r["物差し"]: r for r in need(f, "全国平均と並べる表")}
        its = ch.get("items") or list(rows)[:3]
        if len(its) > 3 or any(x not in rows for x in its):
            sys.exit(f"【止まりました】vs_national の items は facts.json の全国平均と並べる表から3つまで：{its}")
        job = f["職業"]
        hl = ch.get("highlight")
        show_gap = len(its) <= 2
        im, d = head(f"{job}と全国の平均", "（全産業の平均）", src_of(fx, []))
        cols = [1000, 1500] if not show_gap else [820, 1220, 1620]
        heads = [job, "全産業の平均"] + (["差"] if show_gap else [])
        for j, h in enumerate(heads):
            text(d, (cols[j], 240), h, fit(h, 44, 380), MUTED, 900, "mm")
        rh = min(140, (700 - 290) / len(its))
        for i, it in enumerate(its):
            r = rows[it]
            y = 290 + rh * i + rh / 2
            a = ease((t - 0.1 - 0.15 * i) / 0.6)
            is_hl = it == hl
            d.rounded_rectangle((70, y - rh / 2 + 8, 1830, y + rh / 2 - 8), 14, fill=mix(PANEL, a), outline=mix(YELLOW, a) if is_hl else None, width=4)
            text(d, (100, y), it, fit(it, 48, 560), mix(KINARI, a), 900, "lm")
            cells = [r[job], r["全産業の平均"]] + ([r.get("差", "")] if show_gap else [])
            for j, s in enumerate(cells):
                col = YELLOW if (is_hl and j == 0) or (is_hl and j == 2) else (KINARI if j == 0 else MUTED)
                if s:
                    text(d, (cols[j], y), s, fit(s, 54, 400), mix(col, a), 900, "mm")
        return im

    if k == "age_line":  # 型C：年齢別の線。いちばん高い年齢階級を黄、marks の年齢階級に値を出す（5つまで）
        data = need(f, "年齢別")
        m = ch.get("measure", "年収_万円")
        name, fmt = M_NAME[m]
        pts = [(i, r[m]) for i, r in enumerate(data) if r.get(m) is not None]
        if len(pts) < 2:
            sys.exit("【止まりました】年齢別の値が2つより少ない")
        peak_age = f.get("年収がいちばん高い年齢階級", {}).get("年齢階級") if m == "年収_万円" else None
        peak = next((i for i, r in enumerate(data) if r["年齢階級"] == peak_age), max(pts, key=lambda p: p[1])[0])
        marks = [i for i, r in enumerate(data) if r["年齢階級"] in ch.get("marks", []) and r.get(m) is not None and i != peak][:5]
        im, d = head(f"年齢別の{name}", f"（{f['職業']}）", src_of(fx, []))
        vals = [v for _, v in pts]
        lo, hi = min(vals), max(vals)
        pad = (hi - lo) * 0.15 or 1
        lo, hi = lo - pad, hi + pad * 1.6  # 上は値の字が入るように広めに
        px0, px1, py0, py1 = 170, 1700, 230, 640
        n = len(data)
        X = lambda i: px0 + (px1 - px0) * i / max(1, n - 1)
        Y = lambda v: py1 - (py1 - py0) * (v - lo) / (hi - lo)
        d.line((px0 - 30, py1 + 20, px1 + 30, py1 + 20), fill=LINE, width=3)
        for i, r in enumerate(data):  # 年齢の目盛り（「20～24歳」→「20」）
            lab = re.sub(r"歳", "", r["年齢階級"])
            lab = lab if lab.startswith("～") or lab.endswith("～") else lab.split("～")[0]
            text(d, (X(i), py1 + 58), lab, 44, MUTED, 700, "mm")
        text(d, (px1 + 70, py1 + 58), "歳", 44, MUTED, 700, "mm")
        prog = ease((t - 0.1) / 1.2)
        cut = (n - 1) * prog
        for (ia, va), (ib, vb) in zip(pts, pts[1:]):
            if ib - ia > 1 or ia > cut:  # 値が無い年齢階級は線を切る
                continue
            fr = min(1.0, (cut - ia) / (ib - ia))
            d.line((X(ia), Y(va), X(ia) + (X(ib) - X(ia)) * fr, Y(va) + (Y(vb) - Y(va)) * fr), fill=GREY, width=8)
        for i, v in pts:
            if i <= cut:
                rr = 16 if i == peak else 9
                d.ellipse((X(i) - rr, Y(v) - rr, X(i) + rr, Y(v) + rr), fill=YELLOW if i == peak else GREY)
        if prog > 0.95:
            # 線の上の点（値の字が線と重ならない場所を、上・下・右上・左上・右下・左下の順に探す）
            dots = [(X(ia) + (X(ib) - X(ia)) * u / 20, Y(va) + (Y(vb) - Y(va)) * u / 20)
                    for (ia, va), (ib, vb) in zip(pts, pts[1:]) if ib - ia == 1 for u in range(21)]
            for i in marks + [peak]:
                v = data[i][m]
                s = fmt(v)
                sz = 48 if i == peak else 44
                w2, x, y = tw(s, sz) / 2 + 6, X(i), Y(v)
                best = None
                for dx, dy in ((0, -1), (0, 1), (1, -1), (-1, -1), (1, 1), (-1, 1)):
                    cx = min(max(x + dx * (w2 + 10), px0 - 60 + w2), W - 60 - w2)
                    cy = y + dy * (sz / 2 + 30)
                    if cy - sz / 2 < py0 - 40 or cy + sz / 2 > py1 + 10:
                        continue
                    hit = sum(1 for px, py in dots if abs(px - cx) < w2 and abs(py - cy) < sz / 2 + 6)
                    if best is None or hit < best[0]:
                        best = (hit, cx, cy)
                    if hit == 0:
                        break
                cx, cy = best[1:] if best else (x, y - sz / 2 - 30)
                text(d, (cx, cy), s, sz, YELLOW if i == peak else KINARI, 900, "mm")
        return im
    return None


if __name__ == "__main__":
    main()

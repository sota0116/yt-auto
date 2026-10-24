# 仕事チャンネル 型D（AI検証）の点数と facts.json を出す（手順書 §3 型D・§4）
#   python -X utf8 pipeline\d_facts.py make <作業フォルダ> wage30   … 容疑者ごとの点数・順位・言い直し・グラフの値を facts.json に書く
#   python -X utf8 pipeline\d_facts.py ties <作業フォルダ> wage30   … 比べる年を少しずつずらして同点がどれだけ出るかを数え、記録を作業フォルダの log_d_wage30.md に書く
# ・値は data\job\d_wage30.json（fetch_d_wage30.py が保存した表の値）だけを読む。物差しと点は data\scoring_rank.json
# ・割合・伸び率・点数・順位・声の値はここで計算し、Claude は計算しない
# ・『意外な』を題に使えるのは、1位が expected_top と違い、しかも1位が1つに決まった時だけ（facts.json の 意外なを使える）
# ・グラフと出典カードの値（満点・系列の統計・出典カード）もここで書く。make_charts_job.py はこの値をそのまま出す
import json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data", "job")
BASE = 1995
AGE5 = ["20～24歳", "25～29歳", "30～34歳", "35～39歳", "40～44歳", "45～49歳", "50～54歳", "55～59歳", "60～64歳"]
OPS = {">=": lambda a, b: a >= b, "<=": lambda a, b: a <= b, "<": lambda a, b: a < b, ">": lambda a, b: a > b}


def half_up(v, step=1.0):
    """四捨五入（銀行丸めにしない）。負の数は絶対値で丸めて符号を戻す"""
    s = -1 if v < 0 else 1
    r = (abs(v) + step / 2) // step * step
    return s * (int(r) if step >= 1 else round(r, 10))


class D:
    """d_wage30.json の系列から、年ごとの物差しを作る"""

    def __init__(self, topic):
        self.j = json.load(open(os.path.join(DATA, f"d_{topic}.json"), encoding="utf-8"))
        self.s = self.j["series"]

    def v(self, name, y):
        x = self.s[name]["値"].get(str(y))
        if x is None:
            raise KeyError(f"{name} の {y} の値がありません")
        return x

    def last(self, name):
        return max(int(y) for y in self.s[name]["値"])

    # 法人企業統計（年度・百万円）
    def hojin(self, item, y):
        return self.v(f"法人企業統計_{item}", y)

    def bonus(self, y):  # 従業員賞与は2007年度から別の項目。それより前は従業員給与に入っている（値の段差から推測）
        return self.s["法人企業統計_従業員賞与"]["値"].get(str(y)) or 0.0

    def pay(self, y):  # 従業員1人当たり給与（賞与込み）万円
        return (self.hojin("従業員給与", y) + self.bonus(y)) / self.hojin("期中平均従業員数", y) * 100

    def labor_share(self, y):  # 労働分配率 %
        jinken = sum(self.hojin(k, y) for k in ("役員給与", "役員賞与", "従業員給与", "福利厚生費")) + self.bonus(y)
        return jinken / self.hojin("付加価値", y) * 100

    def cho(self, item, y):  # 兆円
        return self.hojin(item, y) / 1e6

    # 労働力調査（2001年までは2月、2002年からは1～3月平均）
    @staticmethod
    def lfs_key(y):
        return f"{y}年2月" if y <= 2001 else f"{y}年1～3月"

    def lfs(self, y):
        r = self.s["労働力調査_表9-1"]["値"].get(self.lfs_key(y))
        if r is None:
            raise KeyError(f"労働力調査の {self.lfs_key(y)} がありません")
        return r

    def lfs_last(self):
        return max(int(k[:4]) for k in self.s["労働力調査_表9-1"]["値"] if k.endswith("1～3月"))

    def hiseiki(self, y):
        return self.lfs(y)["非正規の割合"]

    def hiseiki_prime(self, y):
        r = self.lfs(y)
        ages = ("25～34歳", "35～44歳", "45～54歳")
        return sum(r[f"{a}_非正規"] for a in ages) / sum(r[f"{a}_役員を除く雇用者"] for a in ages) * 100

    def old55(self, y):
        r = self.lfs(y)
        return (r["55～64歳_役員を除く雇用者"] + r["65歳以上_役員を除く雇用者"]) / r["役員を除く雇用者"] * 100

    # 家計調査（2000年からの『勤労者世帯』を優先し、1999年までは『農林漁家世帯を除く』でつなぐ）
    def kakei(self, item, y):
        for s in ("勤労者世帯（2000年～）", "勤労者世帯（農林漁家世帯を除く）"):
            x = self.s[f"家計調査_{s}_{item}"]["値"].get(str(y))
            if x is not None:
                return x
        raise KeyError(f"家計調査の {item} の {y} がありません")

    def nonconsump(self, y):
        return self.kakei("非消費支出", y) / self.kakei("実収入", y) * 100

    # 国民経済計算（暦年）
    def sna(self, item, y):
        return self.v(f"国民経済計算_{item}", y)

    def prod_hour(self, y):  # 10億円÷（万人×時間）なので、指数としてだけ使う
        return self.sna("実質GDP", y) / (self.sna("就業者数", y) * self.sna("雇用者1人当たり労働時間", y))

    def prod_person(self, y):
        return self.sna("実質GDP", y) / self.sna("就業者数", y)

    def comp_hour_real(self, y):
        deflator = self.sna("名目GDP", y) / self.sna("実質GDP", y)
        return self.sna("雇用者報酬", y) / (self.sna("雇用者数", y) * self.sna("雇用者1人当たり労働時間", y)) / deflator

    def employer_ratio(self, y):
        return self.sna("雇主の社会負担", y) / self.sna("雇用者報酬", y) * 100

    # 賃金構造基本統計調査（20～64歳の一般労働者）
    def ck(self, kind, y):
        x = self.s[f"賃金構造_{kind}"]["値"].get(str(y))
        if x is None:
            raise KeyError(f"賃金構造の {y} がありません")
        return x

    def ck_avg(self, wage_y, weight_y):
        w, p = self.ck("労働者数", weight_y), self.ck("所定内給与額", wage_y)
        return sum(w[a] * p[a] for a in AGE5) / sum(w[a] for a in AGE5)

    def ck_old(self, y):
        w = self.ck("労働者数", y)
        return (w["55～59歳"] + w["60～64歳"]) / sum(w[a] for a in AGE5) * 100


def g(a, b):
    return (b / a - 1) * 100


def periods(d, base=BASE, shift=0):
    """統計ごとの始めと終わりの年"""
    return {"法人企業統計調査": (base, d.last("法人企業統計_利益剰余金") - shift),
            "労働力調査": (base, d.lfs_last() - shift),
            "毎月勤労統計調査": (base, d.last("毎月勤労統計_名目賃金指数_就業形態計") - shift),
            "消費者物価指数": (base, d.last("消費者物価指数_持家の帰属家賃を除く総合") - shift),
            "家計調査": (base, min(d.last("家計調査_勤労者世帯（2000年～）_実収入"), d.last("家計調査_勤労者世帯（2000年～）_非消費支出")) - shift),
            "国民経済計算": (base, d.last("国民経済計算_実質GDP") - shift),
            "賃金構造基本統計調査": (max(base, 1999), 2019 - shift)}


def measure(d, pr):
    """確かめごとの値（向きは scoring_rank.json の条件で読む）と、前・後の値"""
    a, b = pr["法人企業統計調査"]
    la, lb = pr["労働力調査"]
    ma, mb = pr["毎月勤労統計調査"]
    ka, kb = pr["家計調査"]
    sa, sb = pr["国民経済計算"]
    ca, cb = pr["賃金構造基本統計調査"]
    mk = lambda k, y: d.v(f"毎月勤労統計_{k}", y)
    out = {}
    pay = (d.pay(a), d.pay(b))
    for tid, item in (("K1", "利益剰余金"), ("K2", "現金・預金")):
        x = (d.cho(item, a), d.cho(item, b))
        out[tid] = {"値": g(*x) - g(*pay), "年": f"{a}年度→{b}年度",
                    "前後": {f"{item}_兆円": x, "従業員1人当たり給与_万円": pay},
                    "伸び率": {item: g(*x), "従業員1人当たり給与": g(*pay)}}
    x = (d.labor_share(a), d.labor_share(b))
    out["K3"] = {"値": x[1] - x[0], "年": f"{a}年度→{b}年度", "前後": {"労働分配率_%": x}}
    x = (d.hiseiki(la), d.hiseiki(lb))
    out["H1"] = {"値": x[1] - x[0], "年": f"{d.lfs_key(la)}→{d.lfs_key(lb)}", "前後": {"非正規の割合_%": x}}
    x1, x2 = (mk("名目賃金指数_一般労働者", ma), mk("名目賃金指数_一般労働者", mb)), (mk("名目賃金指数_就業形態計", ma), mk("名目賃金指数_就業形態計", mb))
    out["H2"] = {"値": g(*x1) - g(*x2), "年": f"{ma}年→{mb}年", "前後": {"一般労働者の賃金指数": x1, "就業形態計の賃金指数": x2},
                 "伸び率": {"一般労働者": g(*x1), "就業形態計": g(*x2)}}
    x = (d.hiseiki_prime(la), d.hiseiki_prime(lb))
    out["H3"] = {"値": x[1] - x[0], "年": f"{d.lfs_key(la)}→{d.lfs_key(lb)}", "前後": {"25～54歳の非正規の割合_%": x}}
    x = (d.prod_hour(sa), d.prod_hour(sb))
    out["P1"] = {"値": g(*x), "年": f"{sa}年→{sb}年", "前後": {"1時間当たり実質GDP_指数用": x}}
    x = (d.prod_person(sa), d.prod_person(sb))
    out["P2"] = {"値": g(*x), "年": f"{sa}年→{sb}年", "前後": {"就業者1人当たり実質GDP_10億円÷万人": x}}
    y = (d.comp_hour_real(sa), d.comp_hour_real(sb))
    ph = (d.prod_hour(sa), d.prod_hour(sb))
    out["P3"] = {"値": g(*ph) - g(*y), "年": f"{sa}年→{sb}年",
                 "伸び率": {"1時間当たり実質GDP": g(*ph), "1時間当たり実質雇用者報酬": g(*y)}}
    x = (d.old55(la), d.old55(lb))
    out["A1"] = {"値": x[1] - x[0], "年": f"{d.lfs_key(la)}→{d.lfs_key(lb)}", "前後": {"55歳以上の割合_%": x}}
    x = (d.ck_old(ca), d.ck_old(cb))
    out["A2"] = {"値": x[1] - x[0], "年": f"{ca}年→{cb}年", "前後": {"20～64歳のうち55～64歳の割合_%": x}}
    base_avg, real_avg, fixed_avg = d.ck_avg(ca, ca), d.ck_avg(cb, cb), d.ck_avg(cb, ca)
    out["A3"] = {"値": g(base_avg, fixed_avg) - g(base_avg, real_avg), "年": f"{ca}年→{cb}年",
                 "前後": {"実際の平均所定内給与_千円": (base_avg, real_avg), "年齢構成を始めの年のままにした平均_千円": (base_avg, fixed_avg)},
                 "伸び率": {"実際": g(base_avg, real_avg), "年齢構成をそのままにした時": g(base_avg, fixed_avg)}}
    p = pr["消費者物価指数"]
    x1 = (d.v("消費者物価指数_持家の帰属家賃を除く総合", p[0]), d.v("消費者物価指数_持家の帰属家賃を除く総合", p[1]))
    x2 = (mk("名目賃金指数_就業形態計", ma), mk("名目賃金指数_就業形態計", mb))
    out["B1"] = {"値": g(*x1) - g(*x2), "年": f"物価 {p[0]}年→{p[1]}年・賃金 {ma}年→{mb}年",
                 "前後": {"消費者物価指数": x1, "名目賃金指数": x2}, "伸び率": {"物価": g(*x1), "名目賃金": g(*x2)}}
    x = (d.nonconsump(ka), d.nonconsump(kb))
    out["B2"] = {"値": x[1] - x[0], "年": f"{ka}年→{kb}年", "前後": {"非消費支出の割合_%": x}}
    x = (d.employer_ratio(sa), d.employer_ratio(sb))
    out["B3"] = {"値": x[1] - x[0], "年": f"{sa}年→{sb}年", "前後": {"雇主の社会負担の割合_%": x}}
    return out


def judge(rank, topic, ms, variant_b=False):
    """点数と順位。variant_b は『線の2倍以上なら支えるに+1点』の試し（使うかはメインが決める）"""
    cfg = rank["題"][topic]
    pt = rank["点"]
    res = []
    for sus in cfg["容疑者"]:
        tests, raw, ns, no = [], 0, 0, 0
        for t in sus["確かめ"]:
            v = ms[t["id"]]["値"]
            if OPS[t["支える"][0]](v, t["支える"][1]):
                kind, p = "支える", pt["支える_大きい統計"] if t["大きさ"] == "大きい" else pt["支える_小さい統計"]
                big = pt.get("大きく支える_加点", 0) or (1 if variant_b else 0)  # 版1.1 から物差しに入れた（三択で線の2倍以上）
                if big and abs(v) >= 2 * abs(t["支える"][1]) and t["型"] == "三択":
                    p += big
                ns += 1
            elif OPS[t["反対"][0]](v, t["反対"][1]):
                kind, p = "反対", pt["反対"]
                no += 1
            else:
                kind, p = "どちらでもない", pt["どちらでもない"]
            raw += p
            tests.append({**t, "値": v, "判定": kind, "点": p, **{k: ms[t["id"]][k] for k in ms[t["id"]] if k != "値"}})
        res.append({"名前": sus["名前"], "確かめ": tests, "点数_丸める前": raw,
                    "点数": max(pt["下限"], min(pt["上限"], raw)), "支える数": ns, "反対数": no, "同点の決め手": ns - no})
    for r in res:
        r["順位"] = 1 + sum(1 for x in res if (x["点数"], x["同点の決め手"]) > (r["点数"], r["同点の決め手"]))
    return sorted(res, key=lambda r: (r["順位"], [x["名前"] for x in cfg["容疑者"]].index(r["名前"])))


def ties_of(res):
    by_pt = {}
    for r in res:
        by_pt.setdefault(r["点数"], []).append(r["名前"])
    same_pt = [v for v in by_pt.values() if len(v) > 1]
    same_rank = {}
    for r in res:
        same_rank.setdefault(r["順位"], []).append(r["名前"])
    return same_pt, [v for v in same_rank.values() if len(v) > 1], same_rank.get(1, [])


def fmt(v, unit):
    return f"{v:+.1f}{unit}"


def voice_pt(x):
    n = half_up(abs(x))
    return f"約{n}ポイント{'上がった' if x > 0 else '下がった'}" if n else "ほぼ変わらない"


def voice_growth(a, b):
    r = b / a
    if r >= 2:
        return f"約{half_up(r, 0.1):.1f}倍"
    n = half_up(abs(g(a, b)))
    return f"約{n}%{'増えた' if b > a else '減った'}" if n else "ほぼ変わらない"


def voice_share(p):
    return f"約{half_up(100 / p)}人に1人"


def voices(ms):
    """声で読む値（言い直しはこの値だけを使う。手順書 §3 型D）"""
    K1, K2 = ms["K1"]["前後"], ms["K2"]["前後"]
    pay = K1["従業員1人当たり給与_万円"]
    v = {
        "K1": {"利益剰余金": f"約{half_up(K1['利益剰余金_兆円'][0])}兆円 → 約{half_up(K1['利益剰余金_兆円'][1])}兆円（{voice_growth(*K1['利益剰余金_兆円'])}）",
               "従業員1人当たり給与": f"約{half_up(pay[0])}万円 → 約{half_up(pay[1])}万円（{voice_growth(*pay)}）"},
        "K2": {"現金・預金": f"約{half_up(K2['現金・預金_兆円'][0])}兆円 → 約{half_up(K2['現金・預金_兆円'][1])}兆円（{voice_growth(*K2['現金・預金_兆円'])}）"},
        "K3": {"労働分配率": f"約{half_up(ms['K3']['前後']['労働分配率_%'][0])}% → 約{half_up(ms['K3']['前後']['労働分配率_%'][1])}%（{voice_pt(ms['K3']['値'])}）"},
        "H1": {"非正規の割合": f"約{half_up(ms['H1']['前後']['非正規の割合_%'][0])}% → 約{half_up(ms['H1']['前後']['非正規の割合_%'][1])}%",
               "言い直し": f"{voice_share(ms['H1']['前後']['非正規の割合_%'][0])} → {voice_share(ms['H1']['前後']['非正規の割合_%'][1])}"},
        "H2": {"一般労働者の賃金": voice_growth(*ms["H2"]["前後"]["一般労働者の賃金指数"]),
               "パート込みの平均の賃金": voice_growth(*ms["H2"]["前後"]["就業形態計の賃金指数"])},
        "H3": {"25～54歳の非正規の割合": f"約{half_up(ms['H3']['前後']['25～54歳の非正規の割合_%'][0])}% → 約{half_up(ms['H3']['前後']['25～54歳の非正規の割合_%'][1])}%"},
        "P1": {"1時間当たり実質GDP": voice_growth(*ms["P1"]["前後"]["1時間当たり実質GDP_指数用"])},
        "P2": {"就業者1人当たり実質GDP": voice_growth(*ms["P2"]["前後"]["就業者1人当たり実質GDP_10億円÷万人"])},
        "P3": {"差": f"約{half_up(ms['P3']['値'])}ポイント"},
        "A1": {"55歳以上の割合": f"約{half_up(ms['A1']['前後']['55歳以上の割合_%'][0])}% → 約{half_up(ms['A1']['前後']['55歳以上の割合_%'][1])}%",
               "言い直し": f"{voice_share(ms['A1']['前後']['55歳以上の割合_%'][0])} → {voice_share(ms['A1']['前後']['55歳以上の割合_%'][1])}"},
        "A2": {"55～64歳の割合": f"約{half_up(ms['A2']['前後']['20～64歳のうち55～64歳の割合_%'][0])}% → 約{half_up(ms['A2']['前後']['20～64歳のうち55～64歳の割合_%'][1])}%"},
        "A3": {"実際の伸び": f"約{half_up(ms['A3']['伸び率']['実際'])}%", "年齢構成をそのままにした時の伸び": f"約{half_up(ms['A3']['伸び率']['年齢構成をそのままにした時'])}%"},
        "B1": {"物価": voice_growth(*ms["B1"]["前後"]["消費者物価指数"]), "名目賃金": voice_growth(*ms["B1"]["前後"]["名目賃金指数"])},
        "B2": {"非消費支出の割合": f"約{half_up(ms['B2']['前後']['非消費支出の割合_%'][0])}% → 約{half_up(ms['B2']['前後']['非消費支出の割合_%'][1])}%（{voice_pt(ms['B2']['値'])}）"},
        "B3": {"雇主の社会負担の割合": f"約{half_up(ms['B3']['前後']['雇主の社会負担の割合_%'][0])}% → 約{half_up(ms['B3']['前後']['雇主の社会負担の割合_%'][1])}%（{voice_pt(ms['B3']['値'])}）"},
    }
    return v


def series(fn, ys, digits=1):
    out = {}
    for y in ys:
        try:
            out[str(y)] = round(fn(y), digits)
        except KeyError:
            pass
    return out


def index(fn, ys, base):
    b = fn(base)
    return series(lambda y: fn(y) / b * 100, ys)


def charts(d, pr):
    """容疑者ごとのグラフの値（年ごと）と、現象のグラフ"""
    r = lambda k: range(pr[k][0], pr[k][1] + 1)
    mk = lambda k: (lambda y: d.v(f"毎月勤労統計_{k}", y))
    cpi = lambda y: d.v("消費者物価指数_持家の帰属家賃を除く総合", y)
    h, s, c = r("法人企業統計調査"), r("国民経済計算"), pr["賃金構造基本統計調査"]
    return {
        "現象": {"説明": "名目と実質の賃金指数（毎月勤労統計・就業形態計・5人以上）。始めの年＝100に直した値", "単位": "指数",
               "名目賃金": index(mk("名目賃金指数_就業形態計"), r("毎月勤労統計調査"), BASE),
               "実質賃金": index(mk("実質賃金指数_就業形態計"), r("毎月勤労統計調査"), BASE)},
        "お金をため込んだ企業": {"単位": "始めの年度＝100", "年の区切り": "年度",
                         "利益剰余金": index(lambda y: d.cho("利益剰余金", y), h, BASE),
                         "現金・預金": index(lambda y: d.cho("現金・預金", y), h, BASE),
                         "従業員1人当たり給与": index(d.pay, h, BASE),
                         "労働分配率_%": series(d.labor_share, h)},
        "非正規の割合の変化": {"単位": "%（2001年までは2月、2002年からは1～3月平均）",
                       "非正規の割合": series(d.hiseiki, r("労働力調査")),
                       "25～54歳の非正規の割合": series(d.hiseiki_prime, r("労働力調査"))},
        "上がらない生産性": {"単位": "始めの年＝100",
                     "1時間当たり実質GDP": index(d.prod_hour, s, BASE),
                     "1時間当たり実質雇用者報酬": index(d.comp_hour_real, s, BASE)},
        "働き手の年齢構成の変化": {"単位": "%",
                         "55歳以上の割合": series(d.old55, r("労働力調査")),
                         "20～64歳の一般労働者のうち55～64歳の割合": series(d.ck_old, range(c[0], c[1] + 1))},
        "物価と税・保険料": {"単位": "始めの年＝100（割合は%）",
                     "物価": index(cpi, r("消費者物価指数"), BASE),
                     "名目賃金": index(mk("名目賃金指数_就業形態計"), r("毎月勤労統計調査"), BASE),
                     "非消費支出の割合_%": series(d.nonconsump, r("家計調査")),
                     "雇主の社会負担の割合_%": series(d.employer_ratio, s)},
    }


# グラフの系列ごとに、どの統計の値か（グラフの左下の出典に使う）
SERIES_STAT = {"名目賃金": ["毎月勤労統計調査"], "実質賃金": ["毎月勤労統計調査", "消費者物価指数"],
               "利益剰余金": ["法人企業統計調査"], "現金・預金": ["法人企業統計調査"], "従業員1人当たり給与": ["法人企業統計調査"],
               "労働分配率_%": ["法人企業統計調査"], "非正規の割合": ["労働力調査"], "25～54歳の非正規の割合": ["労働力調査"],
               "1時間当たり実質GDP": ["国民経済計算"], "1時間当たり実質雇用者報酬": ["国民経済計算"], "55歳以上の割合": ["労働力調査"],
               "20～64歳の一般労働者のうち55～64歳の割合": ["賃金構造基本統計調査"], "物価": ["消費者物価指数"],
               "非消費支出の割合_%": ["家計調査"], "雇主の社会負担の割合_%": ["国民経済計算"]}

# 出典カード（手順書 §3 型D：表の値をそのまま、表の名前・年・表の中の位置を添えて出す）。確かめごとに、表から読んだ値（計算前）を2～3項目
# （系列の名前, 列（行の中の項目。無ければ None）, カードに出す項目名, 単位）
CARD = {
    "K1": [("法人企業統計_利益剰余金", None, "利益剰余金", "百万円"), ("法人企業統計_従業員給与", None, "従業員給与", "百万円")],
    "K2": [("法人企業統計_現金・預金", None, "現金・預金", "百万円"), ("法人企業統計_従業員給与", None, "従業員給与", "百万円")],
    "K3": [("法人企業統計_付加価値", None, "付加価値", "百万円"), ("法人企業統計_従業員給与", None, "従業員給与", "百万円")],
    "H1": [("労働力調査_表9-1", "非正規の割合", "非正規の割合", "%"), ("労働力調査_表9-1", "非正規", "非正規の職員・従業員", "万人"),
           ("労働力調査_表9-1", "役員を除く雇用者", "役員を除く雇用者", "万人")],
    "H2": [("毎月勤労統計_名目賃金指数_一般労働者", None, "一般労働者の現金給与総額指数", "2020年＝100"),
           ("毎月勤労統計_名目賃金指数_就業形態計", None, "就業形態計の現金給与総額指数", "2020年＝100")],
    "H3": [("労働力調査_表9-1", f"{a}_非正規", f"{a}の非正規", "万人") for a in ("25～34歳", "35～44歳", "45～54歳")],
    "P1": [("国民経済計算_実質GDP", None, "実質GDP", "10億円"), ("国民経済計算_就業者数", None, "就業者数", "万人"),
           ("国民経済計算_雇用者1人当たり労働時間", None, "雇用者1人当たり労働時間", "時間（年）")],
    "P2": [("国民経済計算_実質GDP", None, "実質GDP", "10億円"), ("国民経済計算_就業者数", None, "就業者数", "万人")],
    "P3": [("国民経済計算_実質GDP", None, "実質GDP", "10億円"), ("国民経済計算_雇用者報酬", None, "雇用者報酬", "10億円")],
    "A1": [("労働力調査_表9-1", "55～64歳_役員を除く雇用者", "55～64歳の雇用者", "万人"),
           ("労働力調査_表9-1", "65歳以上_役員を除く雇用者", "65歳以上の雇用者", "万人"), ("労働力調査_表9-1", "役員を除く雇用者", "役員を除く雇用者", "万人")],
    "A2": [("賃金構造_労働者数", "55～59歳", "55～59歳の労働者数", "十人"), ("賃金構造_労働者数", "60～64歳", "60～64歳の労働者数", "十人")],
    "A3": [("賃金構造_所定内給与額", a, f"{a}の所定内給与額", "千円") for a in ("20～24歳", "40～44歳", "60～64歳")],
    "B1": [("消費者物価指数_持家の帰属家賃を除く総合", None, "持家の帰属家賃を除く総合", "2020年＝100"),
           ("毎月勤労統計_名目賃金指数_就業形態計", None, "就業形態計の現金給与総額指数", "2020年＝100")],
    "B2": [("家計調査_実収入", None, "実収入（勤労者世帯）", "円（1世帯1か月）"), ("家計調査_非消費支出", None, "非消費支出（勤労者世帯）", "円（1世帯1か月）")],
    "B3": [("国民経済計算_雇用者報酬", None, "雇用者報酬", "10億円"), ("国民経済計算_雇主の社会負担", None, "雇主の社会負担", "10億円")],
}
CARD_STAT = {"法人企業統計": "法人企業統計調査", "労働力調査": "労働力調査", "毎月勤労統計": "毎月勤労統計調査", "消費者物価指数": "消費者物価指数",
             "家計調査": "家計調査", "国民経済計算": "国民経済計算", "賃金構造": "賃金構造基本統計調査"}


def card_value(d, name, col, y):
    """表の値（計算前）と、使った系列の名前・行の名前"""
    fam = name.split("_")[0]
    if fam == "労働力調査":
        return d.lfs(y)[col], name, d.lfs_key(y)
    if fam == "家計調査":
        item = name.split("_", 1)[1]
        for s in ("勤労者世帯（2000年～）", "勤労者世帯（農林漁家世帯を除く）"):
            k = f"家計調査_{s}_{item}"
            x = d.s[k]["値"].get(str(y))
            if x is not None:
                return x, k, f"{y}年"
        raise KeyError(f"家計調査の {item} の {y} がありません")
    if fam == "賃金構造":
        return d.ck(name.split("_", 1)[1], y)[col], name, f"{y}年"
    return d.v(name, y), name, (f"{y}年度" if fam == "法人企業統計" else f"{y}年")


def cards(d, pr, srcs):
    names = {s["key"]: s["名前"] for s in srcs}
    out = {}
    for tid, items in CARD.items():
        rows = []
        for name, col, label, unit in items:
            st = CARD_STAT[name.split("_")[0]]
            for y in pr[st]:
                v, key, row = card_value(d, name, col, y)
                keys = d.s[key]["source"].split(" / ")
                sk = keys[0] if len(keys) == 1 or y <= 2003 else keys[1]  # 賃金構造は 1999～2003年と 2010年からで表が別
                lab, at = label, col or label
                if key.startswith("家計調査_"):  # 家計調査は年で世帯の区分の名前が違うので、区分は表の中の位置に出す
                    lab = label.split("（")[0]
                    at = f"{key.split('_')[1]}・{lab}"
                rows.append({"項目": lab, "年": row, "値": v, "単位": unit, "表": names[sk],
                             "表の中の位置": f"{row}の行・{at}の列" + ("（6月分）" if st == "賃金構造基本統計調査" else "")})
        out[tid] = rows
    return out


def sources(d):
    src = json.load(open(os.path.join(ROOT, "data", "sources.json"), encoding="utf-8"))
    keys = sorted({s["source"].split(" / ")[i] for s in d.s.values() for i in range(len(s["source"].split(" / ")))})
    out = []
    for k in keys:
        x = src[k]
        out.append({"key": k, "名前": f"{x['府省']}「{x['統計名']}」{x['表名']}", "公表日": x.get("公表日") or x.get("サーバーの更新日時"),
                    "URL": x["url"], "ダウンロード": x.get("download"), "statInfId": x.get("statInfId") or x.get("statsDataId"),
                    "取得日": x["fetched"], "e-Statにある": x["e_stat"], "取り方": x["取り方"],
                    "確かさ": "公的統計の表の値をプログラムで計算"})
    return out


def run(topic):
    d = D(topic)
    rank = json.load(open(os.path.join(ROOT, "data", "scoring_rank.json"), encoding="utf-8"))
    pr = periods(d)
    ms = measure(d, pr)
    return d, rank, pr, ms, judge(rank, topic, ms)


def make(work, topic):
    d, rank, pr, ms, res = run(topic)
    cfg = rank["題"][topic]
    same_pt, same_rank, top = ties_of(res)
    exp = cfg["expected_top"]
    srcs = sources(d)
    on = sorted({s["名前"].split("」")[0] + "」" for s in srcs if s["e-Statにある"]})
    off = sorted({s["名前"].split("」")[0] + "」" for s in srcs if not s["e-Statにある"]})
    bars = [{"名前": r["名前"], "点数": r["点数"], "色": "黄" if r["順位"] == 1 else "灰"} for r in res][:6]
    low = [r["名前"] for r in res if r["順位"] == max(x["順位"] for x in res)]
    facts = {
        "type": "D", "題": cfg["題"], "物差しの版": rank["版"], "物差しの状態": rank["状態"],
        "比べた時期": {k: {"始め": v[0], "終わり": v[1]} for k, v in pr.items()},
        "容疑者": [{"名前": s["名前"]} for s in cfg["容疑者"]],
        "結果": res,
        "順位": [{"順位": r["順位"], "名前": r["名前"], "点数": r["点数"], "支える数−反対数": r["同点の決め手"]} for r in res],
        "1位": top, "1位が同点": len(top) > 1, "同じ点数の組": same_pt, "同じ順位の組": same_rank,
        "expected_top": exp, "1位がexpected_topと同じ": exp in top,
        "意外なを使える": (exp not in top) and len(top) == 1,
        "題の言い方の決まり": ("1位は" + "と".join(top) + "（『意外な』『差はたった1点』は使わない）") if len(top) > 1 else None,
        "満点": rank["点"]["上限"],
        "点のグラフ": {"棒": bars, "注": "1位は黄、ほかは灰。声で読む点数は1位と最下位だけ",
                   "声で読む点数": {"1位": [{"名前": r["名前"], "点数": r["点数"]} for r in res if r["順位"] == 1],
                              "最下位": [{"名前": r["名前"], "点数": r["点数"]} for r in res if r["名前"] in low]}},
        "声の値": voices(ms),
        "グラフ": charts(d, pr),
        "系列の統計": SERIES_STAT,
        "出典カード": cards(d, pr, srcs),
        "出典": srcs,
        "e-Statにある統計": on, "e-Statにない統計": off,
        "題の言い方": "政府統計だけで" if not off else "政府の統計だけで",
        "e_stat_note": d.j["meta"]["e_stat_note"],
        "加工": "、".join(sorted({s["名前"].split("」")[0] + "」" for s in srcs})) + "を加工して作成",
        "言い方の決まり": "年齢や雇用形態の『人』は犯人ではなく『要因』として言う（手順書 §3 型D）",
    }
    os.makedirs(work, exist_ok=True)
    p = os.path.join(work, "facts.json")
    json.dump(facts, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"書きました：{p}")
    for r in res:
        marks = " ".join(f"{t['id']}{'○' if t['判定'] == '支える' else '×' if t['判定'] == '反対' else '－'}({t['値']:+.1f})" for t in r["確かめ"])
        print(f"  {r['順位']}位 {r['名前']}：{r['点数']}点（丸める前 {r['点数_丸める前']}・支える−反対 {r['同点の決め手']}） {marks}")
    print(f"  1位 {top}／expected_top と同じ：{exp in top}／意外なを使える：{facts['意外なを使える']}／題の言い方：{facts['題の言い方']}")


def ties(work, topic):
    d = D(topic)
    rank = json.load(open(os.path.join(ROOT, "data", "scoring_rank.json"), encoding="utf-8"))
    rows, n_tie, n_top, n_pt, n_top_b, n_tie_b = [], 0, 0, 0, 0, 0
    for base in range(1995, 2001):
        for shift in (0, 1, 2):
            pr = periods(d, base, shift)
            ms = measure(d, pr)
            res, resb = judge(rank, topic, ms), judge(rank, topic, ms, variant_b=True)
            sp, sr, top = ties_of(res)
            _, srb, topb = ties_of(resb)
            n_pt += bool(sp)
            n_tie += bool(sr)
            n_top += len(top) > 1
            n_tie_b += bool(srb)
            n_top_b += len(topb) > 1
            rows.append(f"| {base} | -{shift} | " + " / ".join(f"{r['名前']} {r['点数']}({r['同点の決め手']:+d})" for r in res)
                        + f" | {'・'.join(top)} | {'あり' if sr else 'なし'} | {'・'.join(topb)} |")
    n = len(rows)
    # データの確かめ（値の段差・つなぎ目）
    bon = [(y, d.hojin("従業員給与", y), d.bonus(y)) for y in (2005, 2006, 2007, 2008)]
    ov = []
    for y in range(2000, 2008):
        a = d.s["家計調査_勤労者世帯（2000年～）_非消費支出"]["値"].get(str(y)) / d.s["家計調査_勤労者世帯（2000年～）_実収入"]["値"].get(str(y)) * 100
        b = d.s["家計調査_勤労者世帯（農林漁家世帯を除く）_非消費支出"]["値"].get(str(y)) / d.s["家計調査_勤労者世帯（農林漁家世帯を除く）_実収入"]["値"].get(str(y)) * 100
        ov.append(f"{y}: {a:.2f}% / {b:.2f}%（差 {a - b:+.2f}）")
    ck = d.s["賃金構造_所定内給与額"]["値"]
    lines = [
        "# 型D wage30 の記録（d_facts.py ties が書いた。値はプログラムの計算）", "",
        "## 1. 同点の確かめ（手順書 §3 型D：同点の頻度を記録する）", "",
        f"比べる始めの年を1995～2000年、終わりの年を各統計の最新から0～2年前にずらした {n} 通りで、物差し（data\\scoring_rank.json 版{rank['版']}）の順位を出した。",
        "（賃金構造基本統計調査の始めは1999年より前がないので1999年、終わりは2019年から0～2年前。労働力調査の始めは各年2月、終わりは各年1～3月平均）", "",
        f"- 同じ点数の容疑者がいた：{n_pt}/{n}",
        f"- 支える数−反対数でも分かれず同じ順位が出た：{n_tie}/{n}",
        f"- 1位が同じ順位で並んだ：{n_top}/{n}",
        f"- 試し案B（三択で線の2倍以上なら支えるに+1点）にした時：同じ順位 {n_tie_b}/{n}、1位が並ぶ {n_top_b}/{n}（案Bは値を見た後の案なので、採るかはメインが決める）", "",
        "| 始めの年 | 終わり | 点数（支える−反対） | 1位 | 同じ順位 | 案Bの1位 |", "|---|---|---|---|---|---|", *rows, "",
        "## 2. データの確かめ", "",
        "### 法人企業統計：従業員賞与は2007年度から別の項目（それより前は従業員給与に入っていると推測）",
        *[f"- {y}年度：従業員給与 {a / 1e6:.1f}兆円・従業員賞与 {b / 1e6:.1f}兆円" for y, a, b in bon],
        "→ 2006年度の給与が2007年度の給与＋賞与とほぼ同じ大きさなので、1人当たり給与は『従業員給与＋従業員賞与（ない年は0）』で計算した", "",
        "### 家計調査：世帯区分のつなぎ目（非消費支出÷実収入。勤労者世帯 / 農林漁家世帯を除く勤労者世帯）", *[f"- {x}" for x in ov],
        "→ 重なる年の差が小さいので、2000年からは『勤労者世帯』、1999年までは『農林漁家世帯を除く』を使った", "",
        "### 賃金構造基本統計調査：年齢計の値（表の値）",
        f"- 1999年 年齢計 {ck['1999']['年齢計']}千円・2019年 年齢計 {ck['2019']['年齢計']}千円（1999～2003年と2010～2019年は別の表。2004～2009年は取っていない）", "",
        "### 国民経済計算", "- 1時間当たりの計算は『就業者数×雇用者1人当たり年間労働時間』で割った（自営業などの労働時間は雇用者の平均で代用）", "",
    ]
    os.makedirs(work, exist_ok=True)
    p = os.path.join(work, "log_d_wage30.md")
    open(p, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print(f"書きました：{p}（同じ順位 {n_tie}/{n}・1位が並ぶ {n_top}/{n}・案B {n_tie_b}/{n}・{n_top_b}/{n}）")


if __name__ == "__main__":
    a = sys.argv[1:]
    if len(a) == 3 and a[0] == "make":
        make(a[1], a[2])
    elif len(a) == 3 and a[0] == "ties":
        ties(a[1], a[2])
    else:
        print("使い方は先頭のコメントを見てください")

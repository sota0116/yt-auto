# 仕事チャンネル 型B（会社の決断の結末）の facts.json を書く（手順書 §3 型B・§4 特典・§10 型B の点検）
#   python -X utf8 pipeline\b_facts.py make <作業フォルダ> <題のキー>   … 題のキー：soki45 zangyo0 shonin30 nenko shukyu3
#   python -X utf8 pipeline\b_facts.py list                             … 作れる題と、使える骨組みを並べる
# ・値は data\job\b_data.json（fetch_b_data.py が e-Stat から取った表）を読むだけ。言い直し・差・合計はここで計算し、Claude は計算しない
# ・台本で声に出してよい数字は、facts.json の「声」「言い直し」「表の値」の文字だけ（点検は文字の形で照らすため、全部を文字で書く）
# ・A社は統計から作った架空の会社。A社の物語に数字は入れない。数字は「全国で同じ立場にいる人の数字」として、つなぎの文の後に出す
import json, os, sys
from decimal import Decimal, ROUND_HALF_UP

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data", "job", "b_data.json")
BOARD = os.path.join(ROOT, "channels", "job", "ネタ帳.json")

A_NAME = "統計の平均から作った、平均的な会社、A社"
TSUNAGI = ["A社ではなく、全国で同じ立場にいる人の数字です。", "同じ年齢の人の、全国の統計です。"]  # 進み方を言わない形（手順書 v3.2 §4 メタの禁止）
RULES = [
    "A社の物語の文には数字を入れない（何人辞めた・売上が何%などは書かない）。数字は 統計 の「声」か「言い直し」をそのまま使う",
    "統計の数字を出す章では、その章で最初の数字の直前に、つなぎ の文のどちらかを入れる（A社の数字に見せないため）",
    "各章で声で言い切る数字は1つ。ほかの数字は画面のグラフに任せる",
    "骨組みの時点（1か月後・半年後など）の数字は、A社のその時点の数字ではない。その時点の立場に当たる、全国の人の数字として言う",
    "年齢は表の区切りのまま言う（45～49歳）。「45歳以上の人は」のように区切りを広げて言わない",
    "賃金の変わり方は、会社を移った人が、前の会社と比べて答えた物。上がった人の割合も、下がった人の割合と一緒に1回は出す（片方だけで言い切らない）",
    "所定内給与は、残業代や賞与を入れない毎月の給与。「年収」とは言わない",
]


def half_up(v, step="1"):
    """四捨五入（銀行丸めにしない）。小数の誤差が出ないよう Decimal で丸める"""
    q = Decimal(str(v)).quantize(Decimal(step), rounding=ROUND_HALF_UP)
    return int(q) if step == "1" else float(q)


def fmt(v):
    """表の値の書き方（30.0→30、30.1→30.1）"""
    return f"{v:g}"


# ---- 言い直し（声の形）----
PAIRS = [(1, 2), (1, 3), (2, 3), (1, 4), (3, 4), (1, 5), (2, 5), (3, 5), (4, 5), (1, 6), (1, 7), (1, 8), (1, 9), (1, 10),
         (3, 10), (7, 10), (9, 10)]


def per_n(v, unit="人"):
    """割合（%）を「〇人に〇人」にする。差が2ポイント以内かつ1割以内の、分母の小さい形だけ。合わなければ None"""
    if v is None or v <= 0:
        return None
    if v < 1:
        return f"100{unit}に1{unit}もいない" if unit == "人" else f"100{unit}に1{unit}もない"
    best = None
    for n, d in PAIRS:
        diff = abs(100 * n / d - v)
        if diff <= 2.0 and diff / v <= 0.1 and (best is None or (diff, d) < (best[0], best[2])):
            best = (diff, n, d)
    if best:
        return f"{best[2]}{unit}に{best[1]}{unit}"
    if v < 15:  # 小さい割合は「〇人に1人」。きりのよい数（10・5の倍数）を先に試す
        x = 100 / v
        for c in (half_up(x, "1") // 10 * 10, -(-half_up(x, "1") // 10) * 10, half_up(x / 5) * 5, half_up(x)):
            if c and abs(100 / c - v) / v <= 0.1:
                return f"{int(c)}{unit}に1{unit}"
    return None


def pct_voice(v):
    if v is None:
        return None
    return f"{fmt(v)}%" if v < 1 else f"約{half_up(v)}%"


def wari(v):
    """「約〇割」。丸めた割と2ポイント以内の時だけ（16%を「約2割」とは言わない）"""
    if v is None or v < 10:
        return None
    w = half_up(v / 10)
    return f"約{w}割" if abs(w * 10 - v) <= 2.0 else None


def man_yen(sen):
    """千円 → 声の「約〇万円」（10万円未満は小数1けた）"""
    m = sen / 10
    return f"約{half_up(m)}万円" if m >= 10 else f"約{fmt(half_up(m, '0.1'))}万円"


class Facts:
    def __init__(self):
        self.b = json.load(open(DATA, encoding="utf-8"))
        self.t = self.b["tables"]
        self.stats, self.used = {}, []

    def src(self, table):
        k = self.t[table]["source"]
        if k not in self.used:
            self.used.append(k)
        return k

    def add(self, sid, what, v, unit, table, where, voice=None, again=(), calc=None, who=None):
        """統計の数字を1つ登録する。声の形と言い直しを付ける"""
        if v is None:
            sys.exit(f"【止まりました】{table} の {where} に値がありません")
        what = what.replace("年齢計の", "全年齢の").replace("年齢計で", "全年齢で")
        s = {"id": sid, "何の数字": what, "値": v, "単位": unit, "表の値": f"{fmt(v)}{unit}" if unit in ("%", "時間", "日") else None,
             "声": voice, "言い直し": [x for x in again if x], "立場": who, "出典key": self.src(table),
             "表": self.t[table]["表名"], "表の中の位置": where}
        if calc:
            s["計算"] = calc
        self.stats[sid] = s
        return sid

    def pct(self, sid, what, v, table, where, unit_word="人", who=None):
        return self.add(sid, what, v, "%", table, where, pct_voice(v), (per_n(v, unit_word), wari(v)), who=who)

    def yen(self, sid, what, sen, table, where, who=None, calc=None, prefix=""):
        s = self.add(sid, what, sen, "千円", table, where, prefix + man_yen(sen), (), calc=calc, who=who)
        self.stats[sid]["表の値"] = f"{fmt(sen)}千円"
        return s

    # ---- 表から引く ----
    def hendo(self, age, k="減少", sex="男女計"):
        return self.t["賃金変動"]["値"][sex][age][k]

    def ido(self, age, k):
        return self.t["労働移動率"]["値"][age][k]

    def nen(self, age, k, kibo="規模計"):
        return self.t["年齢別の賃金"]["値"][kibo][age][k]

    def bunpu(self, age, kibo="規模計"):
        return self.t["所定内給与の分布"]["値"][kibo][age]

    # ---- よく使う統計 ----
    def s_hendo(self, age, k="減少"):
        word = {"減少": "下がった", "増加": "上がった", "1割以上減少": "1割以上下がった", "1割以上増加": "1割以上上がった", "変わらない": "変わらなかった"}[k]
        return self.pct(f"賃金{word}_{age}", f"{age}で会社を移った人のうち、前の会社より賃金が{word}人の割合", self.hendo(age, k), "賃金変動",
                        f"第13-2表 転職入職者（経験1年未満）・男女計・{age}・{k}の構成比", who=f"{age}で会社を移った人")

    def s_rishoku(self, age):
        return self.pct(f"離職率_{age}", f"{age}で、1年間に会社を辞めた人の割合（離職率）", self.ido(age, "離職率"), "労働移動率",
                        f"参考表2 計・男女計・{age}・離職率", who=f"{age}の働く人")

    def s_tenshoku(self, age):
        return self.pct(f"転職入職率_{age}", f"{age}で、1年間に別の会社から移ってきた人の割合（転職入職率）", self.ido(age, "転職入職率"), "労働移動率",
                        f"参考表2 計・男女計・{age}・転職入職率", who=f"{age}の働く人")

    def s_keiei(self, age):
        v = self.t["離職理由"]["値"][age]["経営上の都合"]
        return self.pct(f"経営上の都合_{age}", f"{age}で会社を辞めた人のうち、会社の経営上の都合（人員整理・希望退職の募集など）で辞めた人の割合", v,
                        "離職理由", f"第34-3表 構成比・計・{age}・事業所側の理由のうち経営上の都合", who=f"{age}で会社を辞めた人")

    def s_shoteinai(self, age, kibo="規模計"):
        return self.yen(f"所定内給与_{age}_{kibo}", f"{age}の会社員（一般労働者{kibo_word(kibo)}）の、毎月の所定内給与の平均（残業代・賞与は入らない）",
                        self.nen(age, "所定内給与額", kibo), "年齢別の賃金", f"第1表 産業計・男女計学歴計・{kibo}・{age}・所定内給与額",
                        who=f"{age}の会社員", prefix="月に")

    def s_median(self, age, kibo="規模計"):
        return self.yen(f"中位数_{age}_{kibo}", f"{age}の会社員を所定内給与の順に並べた時の、真ん中の人の額（中位数）", self.bunpu(age, kibo)["中位数_千円"],
                        "所定内給与の分布", f"第3表 産業計({kibo})・男女計学歴計・{age}・中位数", who=f"{age}の会社員", prefix="月に")


def kibo_word(kibo):
    return "" if kibo in ("規模計", "調査計") else f"・企業規模{kibo}"


def chart(title, rows, hi, unit, src, note=None):
    """画面のグラフの材料（1画面の棒は6本まで・手順書 §5）"""
    if len(rows) > 6:
        sys.exit(f"【止まりました】グラフ「{title}」の棒が6本を超えています")
    return {"kind": "bars", "題": title, "棒": [{"名前": n, "値": v, "表示": f"{fmt(v)}{unit}"} for n, v in rows], "強調": hi,
            "単位": unit, "出典key": src, "注": note}


# ---- 題ごとの組み立て ----
def soki45(F):
    t = F.t
    hook = F.s_hendo("45～49歳")
    F.s_hendo("45～49歳", "増加")
    F.s_hendo("50～54歳")
    F.s_hendo("45～49歳", "1割以上減少")
    k0, k20 = (t["年齢と勤続年数別の賃金"]["値"]["45～49歳"][k]["所定内給与額"] for k in ("0年", "20～24年"))
    F.yen("勤続0年_45～49歳", "45～49歳で、今の会社に勤めて1年未満の人の毎月の所定内給与の平均", k0, "年齢と勤続年数別の賃金",
          "第2表 規模計・男女計学歴計・45～49歳・勤続0年・所定内給与額", who="45～49歳で勤めて1年未満の人", prefix="月に")
    F.yen("勤続20～24年_45～49歳", "45～49歳で、今の会社に20～24年勤めている人の毎月の所定内給与の平均", k20, "年齢と勤続年数別の賃金",
          "第2表 規模計・男女計学歴計・45～49歳・勤続20～24年・所定内給与額", who="45～49歳で長く勤めている人", prefix="月に")
    diff = F.yen("勤続の差_45～49歳", "45～49歳の、勤続20～24年の人と勤続1年未満の人の、毎月の所定内給与の差", round(k20 - k0, 1), "年齢と勤続年数別の賃金",
                 "第2表 45～49歳の勤続20～24年−勤続0年", calc=f"{fmt(k20)}千円−{fmt(k0)}千円", who="45～49歳", prefix="月に")
    frames = {
        "B-1": {"発表": F.s_rishoku("45～49歳"), "1か月後": F.s_keiei("45～49歳"), "半年後": hook, "1年後": diff, "山場": "半年後"},
        "B-2": {"経営": F.s_keiei("年齢計"), "40代の中堅": F.s_shoteinai("45～49歳"), "20代の若手": F.s_shoteinai("25～29歳"),
                "辞めた人": hook, "山場": "辞めた人"},
    }
    F.s_tenshoku("45～49歳")
    v = t["賃金変動"]["値"]["男女計"]
    ages = ["35～39歳", "40～44歳", "45～49歳", "50～54歳", "55～59歳", "60～64歳"]
    charts = [chart("会社を移って、前の会社より賃金が下がった人の割合（年齢別）", [(a, v[a]["減少"]) for a in ages], "45～49歳", "%", F.src("賃金変動")),
              chart("45～49歳の毎月の所定内給与（勤続年数別）", [(k, t["年齢と勤続年数別の賃金"]["値"]["45～49歳"][k]["所定内給与額"]) for k in
                                                ("0年", "1～2年", "5～9年", "10～14年", "20～24年", "30年以上")], "0年", "千円", F.src("年齢と勤続年数別の賃金"))]
    no = {"B-3": "早期退職の制度（早期退職優遇制度がある会社の割合など）の表を、まだ取っていない（就労条件総合調査 退職給付制度の回の表を足せば使える）"}
    return hook, frames, charts, no


def zangyo0(F):
    over = lambda a, kibo="規模計": round(F.nen(a, "きまって支給する現金給与額", kibo) - F.nen(a, "所定内給与額", kibo), 1)
    hrs = lambda a, kibo="規模計": F.add(f"超過実労働時間_{a}_{kibo}", f"{a}の会社員{kibo_word(kibo).replace('・', '（', 1) + '）' if kibo_word(kibo) else ''}の、1か月の残業など（超過実労働時間）の平均",
                                       F.nen(a, "超過実労働時間数", kibo), "時間", "年齢別の賃金", f"第1表 産業計・男女計学歴計・{kibo}・{a}・超過実労働時間数",
                                       f"月に約{half_up(F.nen(a, '超過実労働時間数', kibo))}時間", who=f"{a}の会社員")
    def pay(a, kibo="規模計"):
        m = over(a, kibo)
        k = F.nen(a, "きまって支給する現金給与額", kibo), F.nen(a, "所定内給与額", kibo)
        return F.yen(f"超過労働給与_{a}_{kibo}", f"{a}の会社員{kibo_word(kibo).replace('・', '（', 1) + '）' if kibo_word(kibo) else ''}の、毎月の残業代など（超過労働給与額＝きまって支給する現金給与額−所定内給与額）",
                     m, "年齢別の賃金", f"第1表 産業計・男女計学歴計・{kibo}・{a}", calc=f"{fmt(k[0])}千円−{fmt(k[1])}千円", who=f"{a}の会社員", prefix="月に")
    h25 = hrs("25～29歳")
    p25 = pay("25～29歳")
    m25 = over("25～29歳")
    F.yen("超過労働給与の1年分_25～29歳", "25～29歳の会社員の、残業代など（超過労働給与額）を12か月分に直した額", round(m25 * 12, 1), "年齢別の賃金",
                "第1表 25～29歳の超過労働給与額×12", calc=f"{fmt(m25)}千円×12（6月分の額を12倍しただけ。月ごとの違いは見ていない）", who="25～29歳の会社員", prefix="年に")
    F.yen("超過労働給与の半年分_25～29歳", "25～29歳の会社員の、残業代など（超過労働給与額）を6か月分に直した額", round(m25 * 6, 1), "年齢別の賃金",
          "第1表 25～29歳の超過労働給与額×6", calc=f"{fmt(m25)}千円×6（6月分の額を6倍しただけ）", who="25～29歳の会社員", prefix="半年で")
    hrs("年齢計")
    pay("45～49歳")
    hrs("45～49歳")
    pay("25～29歳", "1,000人以上")
    hrs("25～29歳", "1,000人以上")
    frames = {
        "B-1": {"発表": h25, "1か月後": p25, "半年後": "超過労働給与の半年分_25～29歳", "1年後": F.s_rishoku("25～29歳"), "山場": "半年後",
                "注": "半年後の山場は、残業代を6か月分に直した額（題の前提の0時間なら、この分の給与が出ない、という読み方。A社の数字ではない）。1年分は 超過労働給与の1年分 にある"},
        "B-2": {"経営": pay("年齢計"), "40代の中堅": "超過労働給与_45～49歳_規模計", "20代の若手": p25, "辞めた人": F.s_hendo("25～29歳"), "山場": "辞めた人"},
    }
    F.s_hendo("25～29歳", "増加")
    ages = ["20～24歳", "25～29歳", "30～34歳", "35～39歳", "40～44歳", "45～49歳"]
    charts = [chart("毎月の残業代など（超過労働給与額・年齢別）", [(a, over(a)) for a in ages], "25～29歳", "千円", F.src("年齢別の賃金"),
                    "きまって支給する現金給与額−所定内給与額"),
              chart("1か月の残業など（超過実労働時間・年齢別）", [(a, F.nen(a, "超過実労働時間数")) for a in ages], "25～29歳", "時間", F.src("年齢別の賃金"))]
    no = {"B-3": "残業の制度（割増賃金率など）の表は、残業ゼロの宣言の分かれ目と結びつけにくいので使わない"}
    return p25, frames, charts, no


def shonin30(F):
    t = F.t
    sk = t["初任給"]["値"]
    univ = F.yen("初任給_大学", "大学を出て働き始めた人の初任給（所定内給与額）の平均", sk["大学"]["規模計"]["所定内給与額"], "初任給",
                 "新規学卒者第1表 大学・男女計・企業規模計", who="大学を出たばかりの新人", prefix="月に")
    F.yen("初任給_学歴計", "学校を出て働き始めた人（学歴計）の初任給（所定内給与額）の平均", sk["学歴計"]["規模計"]["所定内給与額"], "初任給",
          "新規学卒者第1表 学歴計・男女計・企業規模計", who="学校を出たばかりの新人", prefix="月に")
    big = F.yen("初任給_大学_1,000人以上", "1,000人以上の会社に入った大学卒の初任給（所定内給与額）の平均", sk["大学"]["1,000人以上"]["所定内給与額"], "初任給",
                "新規学卒者第1表 大学・男女計・1,000人以上", who="大きな会社に入った大学卒の新人", prefix="月に")
    gap = round(300 - sk["大学"]["規模計"]["所定内給与額"], 1)
    F.yen("前提との差_大学", "題の前提の初任給30万円と、大学卒の初任給の平均の差", gap, "初任給", "新規学卒者第1表 大学・企業規模計",
          calc=f"300千円（題の前提）−{fmt(sk['大学']['規模計']['所定内給与額'])}千円", who="大学を出たばかりの新人", prefix="月に")
    for a in ("25～29歳", "30～34歳", "35～39歳", "40～44歳"):
        F.s_median(a)
    # 所定内給与が30万円以上の人の割合（第3表の階級の人数を足す）
    def share300(a):
        d = F.bunpu(a)
        up = sum(x["労働者数_十人"] for x in d["階級"] if x["下限_千円"] >= 300)
        v = round(up / d["労働者数_十人"] * 100, 1)
        return F.add(f"30万円以上の割合_{a}", f"{a}の会社員のうち、毎月の所定内給与が30万円以上の人の割合", v, "%", "所定内給与の分布",
                     f"第3表 産業計(規模計)・男女計学歴計・{a}・300.0千円以上の階級の合計÷計", pct_voice(v), (per_n(v), wari(v)),
                     calc=f"300.0千円以上の階級の労働者数の合計{fmt(up)}十人÷{fmt(d['労働者数_十人'])}十人", who=f"{a}の会社員")
    s25 = share300("25～29歳")
    share300("20～24歳")
    first = next(a for a in ("20～24歳", "25～29歳", "30～34歳", "35～39歳", "40～44歳", "45～49歳") if F.bunpu(a)["中位数_千円"] >= 300)
    F.stats["中位数_" + first + "_規模計"]["メモ"] = f"真ん中の人の所定内給与が30万円を超えるのは、{first}からです（年齢の区切りの中で最初）"
    frames = {
        "B-1": {"発表": univ, "1か月後": "中位数_25～29歳_規模計", "半年後": "中位数_30～34歳_規模計", "1年後": F.s_rishoku("20～24歳"), "山場": "半年後",
                "注": "半年後の山場は「30～34歳の真ん中の人の所定内給与」。題の前提の30万円より少ない（新人が先輩を追い越す形）"},
        "B-2": {"経営": big, "40代の中堅": "中位数_40～44歳_規模計", "20代の若手": s25, "辞めた人": F.s_hendo("25～29歳", "増加"), "山場": "辞めた人"},
    }
    F.s_hendo("25～29歳")
    ages = ["20～24歳", "25～29歳", "30～34歳", "35～39歳", "40～44歳", "45～49歳"]
    charts = [chart("毎月の所定内給与の真ん中の人の額（中位数・年齢別）", [(a, F.bunpu(a)["中位数_千円"]) for a in ages], "30～34歳", "千円", F.src("所定内給与の分布"),
                    "題の前提の30万円（300千円）の線を引く")]
    no = {"B-3": "初任給の決め方の制度の割合の表を、まだ取っていない"}
    return univ, frames, charts, no


def nenko(F):
    t = F.t
    y = t["基本給の決定要素"]["値"]
    where = "第29-2表（令和4年）管理職以外・{}・{}"
    def yoso(k, kibo="調査計"):
        return F.pct(f"基本給の決定要素_{k}_{kibo}", f"管理職以外の基本給を決める物に「{k}」が入っている会社の割合（2022年の調査・複数回答）",
                     y[kibo][k], "基本給の決定要素", where.format(kibo, k), unit_word="社", who="会社（常用労働者30人以上）")
    age = yoso("年齢・勤続年数など")
    job = yoso("職務・職種など仕事の内容")
    abl = yoso("職務遂行能力")
    perf = yoso("業績・成果")
    big = yoso("年齢・勤続年数など", "1,000人以上")
    yoso("年齢・勤続年数など", "30～99人")
    k = t["年齢と勤続年数別の賃金"]["値"]["45～49歳"]
    diff = F.yen("勤続の差_45～49歳", "45～49歳の、勤続20～24年の人と勤続1年未満の人の、毎月の所定内給与の差",
                 round(k["20～24年"]["所定内給与額"] - k["0年"]["所定内給与額"], 1), "年齢と勤続年数別の賃金", "第2表 45～49歳の勤続20～24年−勤続0年",
                 calc=f"{fmt(k['20～24年']['所定内給与額'])}千円−{fmt(k['0年']['所定内給与額'])}千円", who="45～49歳", prefix="月に")
    frames = {
        "B-1": {"発表": age, "1か月後": perf, "半年後": diff, "1年後": F.s_tenshoku("45～49歳"), "山場": "半年後"},
        "B-2": {"経営": big, "40代の中堅": F.s_shoteinai("45～49歳"), "20代の若手": F.s_shoteinai("25～29歳"), "辞めた人": F.s_hendo("45～49歳"), "山場": "辞めた人"},
        "B-3": {"制度": [job, abl, perf], "分かれ目": perf, "山場": "分かれ目",
                "注": "基本給を何で決めるか（複数回答）の3つ。分かれ目は「業績・成果」。2022年の調査（この項目の最新）と言う"},
    }
    F.s_hendo("45～49歳", "増加")
    charts = [chart("45～49歳の毎月の所定内給与（勤続年数別）", [(n, k[n]["所定内給与額"]) for n in ("0年", "1～2年", "5～9年", "10～14年", "20～24年", "30年以上")],
                    "20～24年", "千円", F.src("年齢と勤続年数別の賃金")),
              chart("基本給を決める物（管理職以外・会社の割合・2022年）", [(n, y["調査計"][n]) for n in ("職務・職種など仕事の内容", "職務遂行能力", "年齢・勤続年数など", "業績・成果")],
                    "業績・成果", "%", F.src("基本給の決定要素"), "複数回答")]
    return age, frames, charts, {}


def shukyu3(F):
    t = F.t
    kg, rd, ky = (t[n]["値"] for n in ("週休制_企業割合", "週休制_労働者割合", "年間休日"))
    def sk(k, kibo="調査計"):
        return F.pct(f"週休制_{k}_{kibo}", f"週休制が「{k}」の会社の割合{kibo_word(kibo).replace('・', '（', 1) + '）' if kibo_word(kibo) else ''}", kg[kibo][k], "週休制_企業割合",
                     f"就労条件 第2表 {kibo}・{k}", unit_word="社", who="会社（常用労働者30人以上）")
    three = sk("何らかの週休3日制")
    two = sk("完全週休2日制")
    one = sk("週休1日制又は週休1日半制")
    big = sk("何らかの週休3日制", "1,000人以上")
    sk("何らかの週休3日制", "30～99人")
    wk = F.pct("週休3日制の労働者_調査計", "週休制が「何らかの週休3日制」の会社で働く人の割合（労働者割合）", rd["調査計"]["何らかの週休3日制"], "週休制_労働者割合",
               "就労条件 第3表 調査計・何らかの週休3日制", who="働く人（常用労働者30人以上の会社）")
    avg = F.add("年間休日の平均", "1つの会社の、1年間の休日の数の平均（1企業平均年間休日総数）", ky["調査計"]["1企業平均年間休日総数_日"], "日", "年間休日",
                "就労条件 第4表 調査計・1企業平均年間休日総数", f"約{half_up(ky['調査計']['1企業平均年間休日総数_日'])}日", who="会社（常用労働者30人以上）")
    k130 = F.pct("年間休日130日以上", "1年間の休日が130日以上の会社の割合", ky["調査計"]["130日以上"], "年間休日", "就労条件 第4表 調査計・130日以上",
                 unit_word="社", who="会社（常用労働者30人以上）")
    F.pct("年間休日120～129日", "1年間の休日が120～129日の会社の割合", ky["調査計"]["120～129日"], "年間休日", "就労条件 第4表 調査計・120～129日",
          unit_word="社", who="会社（常用労働者30人以上）")
    frames = {
        "B-1": {"発表": three, "1か月後": avg, "半年後": k130, "1年後": wk, "山場": "半年後",
                "注": "時点の数字は、どれも制度の割合（会社か働く人）。人の動き（転職・賃金）の統計は、週休3日と結びつく表が無いので使わない"},
        "B-3": {"制度": [one, two, three], "分かれ目": three, "山場": "分かれ目", "注": "週休制の3つの形の、会社の割合。分かれ目は週休3日"},
    }
    charts = [chart("週休制の形の会社の割合", [("週休1日制又は週休1日半制", kg["調査計"]["週休1日制又は週休1日半制"]), ("完全週休2日制", kg["調査計"]["完全週休2日制"]),
                                         ("何らかの週休3日制", kg["調査計"]["何らかの週休3日制"])], "何らかの週休3日制", "%", F.src("週休制_企業割合")),
              chart("週休3日制の会社の割合（企業規模別）", [(n, kg[n]["何らかの週休3日制"]) for n in ("1,000人以上", "300～999人", "100～299人", "30～99人")],
                    "1,000人以上", "%", F.src("週休制_企業割合"))]
    no = {"B-2": "年齢別の賃金・離職率と、週休3日の制度を結びつける表が無い（立場別の4人の数字が題と離れる）"}
    return three, frames, charts, no


TOPICS = {"soki45": ("b_soki45", soki45), "zangyo0": ("b_zangyo0", zangyo0), "shonin30": ("b_shonin30", shonin30),
          "nenko": ("b_nenko", nenko), "shukyu3": ("b_shukyu3", shukyu3)}


def hook_line(s):
    """つかみの1文の例（声の形をそのまま使う）"""
    say = s["言い直し"][0] if s["言い直し"] else s["声"]
    return {"統計": s["id"], "例": f"{s['何の数字']}は、{say}です。",
            "決まり": "つかみの1文目にこの数字を入れる（hook_type が統計の回）。文は台本で言いやすく直してよいが、数字の形（声・言い直し）は変えない。A社の話はその後"}


def tokuten(F):
    """特典の表：年齢別・男女別の、転職で賃金が上がった人・下がった人の割合（手順書 §4 の B の行）"""
    v = F.t["賃金変動"]["値"]
    ages = ["19歳以下", "20～24歳", "25～29歳", "30～34歳", "35～39歳", "40～44歳", "45～49歳", "50～54歳", "55～59歳", "60～64歳", "65歳以上"]
    keys = ["増加", "1割以上増加", "変わらない", "減少", "1割以上減少", "不詳"]
    rows = [{"性": s, "年齢": a, **{k: v[s][a][k] for k in keys}} for s in ("男女計", "男", "女") for a in ["年齢計"] + ages]
    tb = F.t["賃金変動"]
    return {"名前": "年齢別 転職で年収が上がった人・下がった人の割合の一覧", "列": keys, "単位": "%（転職入職者を100とした構成比）", "行": rows,
            "出典key": F.src("賃金変動"),
            "表の下に書く": [f"出典：厚生労働省「雇用動向調査」令和7年 {tb['表名']}（{tb['URL']}）", "厚生労働省「雇用動向調査」を加工して作成",
                         F.b["meta"]["e_stat_note"]],
            "注": "転職入職者（入職前1年間に仕事をしていた人）が、前の会社の賃金と比べて答えた物。「年収」は案内文の言い方で、表は賃金の変わり方"}


def make(work, key):
    if key not in TOPICS:
        sys.exit(f"【止まりました】題のキーがありません：{key}（{list(TOPICS)}）")
    nid, fn = TOPICS[key]
    row = next((r for r in json.load(open(BOARD, encoding="utf-8")) if r["id"] == nid), None)
    if not row:
        sys.exit(f"【止まりました】ネタ帳に {nid} の行がありません")
    F = Facts()
    hook, frames, charts, no = fn(F)
    F.src("賃金変動")  # 特典の表の出典
    for f in frames.values():  # 骨組みが指す統計が全部あるか
        for k, x in f.items():
            for sid in (x if isinstance(x, list) else [x]):
                if k not in ("山場", "注") and sid not in F.stats:
                    sys.exit(f"【止まりました】骨組みの {k} の統計 {sid} がありません")
    srcs = []
    for k in F.used:
        tb = next(x for x in F.t.values() if x["source"] == k)
        srcs.append({"key": k, "名前": f"厚生労働省「{tb['統計名']}」{tb['表名']}", "公表日": tb.get("公表日"), "URL": tb["URL"],
                     "ダウンロード": tb["ダウンロード"], "statInfId": tb["statInfId"], "取得日": tb["取得日"], "e-Statにある": tb["e_stat"],
                     "取り方": "e-Stat のファイル", "確かさ": "公的統計の表の値をプログラムで計算"})
    names = sorted({f"厚生労働省「{x['統計名']}」" for x in F.t.values() if x["source"] in F.used})
    facts = {
        "type": "B", "題": row["title"], "neta_id": nid, "key": key, "premise_numbers": row.get("premise_numbers", []),
        "A社": {"呼び名": A_NAME, "名札": A_NAME, "題の呼び名": ["平均的な会社", "統計から作った会社"],
               "決まり": "前置きで語り手が1回「統計の平均から作った、平均的な会社、A社」と紹介する。A社の場面のカットは reenact の印を付け、右上に「イメージ」"},
        "つなぎ": TSUNAGI,
        "使える骨組み": list(frames), "使えない骨組み": no,
        "骨組み": frames,
        "つかみ": hook_line(F.stats[hook]),
        "統計": F.stats,
        "グラフ": charts,
        "特典": tokuten(F),
        "出典": srcs,
        "題の言い方": "厚生労働省の統計",
        "e_stat_note": F.b["meta"]["e_stat_note"],
        "加工": "、".join(names) + "を加工して作成",
        "言い方の決まり": RULES,
    }
    os.makedirs(work, exist_ok=True)
    p = os.path.join(work, "facts.json")
    json.dump(facts, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"書きました：{p}（{row['title']}／骨組み {list(frames)}／統計 {len(F.stats)}／出典 {len(srcs)}）")


def list_topics():
    for key, (nid, fn) in TOPICS.items():
        F = Facts()
        _, frames, _, no = fn(F)
        print(f"{key}（{nid}）：骨組み {list(frames)}／使えない {list(no)}")


if __name__ == "__main__":
    a = sys.argv[1:]
    if len(a) == 3 and a[0] == "make":
        make(a[1], a[2])
    elif a and a[0] == "list":
        list_topics()
    else:
        print("使い方は先頭のコメントを見てください")

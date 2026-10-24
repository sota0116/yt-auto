# 仕事チャンネル 型A-1・A-3・C の facts.json を作る共通の部品（a1_facts.py・a3_facts.py・c_facts.py から読む）
# ・値は data\job\ の保存済みの JSON を読むだけ（e-Stat には取りに行かない。取るのは fetch_job_data.py・fetch_a1c_data.py）
# ・順位・差・言い直しは、ここの関数で計算する。Claude は計算しない（手順書 §2・§4）
import json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data", "job")

# ネタ帳のキー → 職種（賃金構造基本統計調査の職種（小分類）の名前）・表示名・その職業を含む産業（雇用動向調査の産業の記号）
#  産業は「その職業の人が多く働く産業」をこのチャンネルが当てはめた物。表の上で職業と産業が結びついているわけではない（facts.json に書く）
JOBS = {
    "kaigo": {"職種": ["介護職員（医療・福祉施設等）"], "表示名": "介護職員", "産業": "Ｐ"},
    "hoiku": {"職種": ["保育士"], "表示名": "保育士", "産業": "Ｐ"},
    "yakuzai": {"職種": ["薬剤師"], "表示名": "薬剤師", "産業": "Ｐ",
                "産業の注意": "薬剤師は病院・診療所（医療，福祉）のほか、調剤薬局・ドラッグストア（卸売業，小売業）でも働く。ここでは医療，福祉に当てはめた"},
    "sekokan": {"職種": ["建築技術者", "土木技術者"], "表示名": "建築・土木の技術者（施工管理）", "産業": "Ｄ"},
    "chori": {"職種": ["飲食物調理従事者"], "表示名": "調理人", "産業": "Ｍ"},
    "taxi": {"職種": ["タクシー運転者"], "表示名": "タクシー運転手", "産業": "Ｈ"},
    "se": {"職種": ["システムコンサルタント・設計者"], "表示名": "システムエンジニア", "産業": "Ｇ"},
    "truck": {"職種": ["営業用大型貨物自動車運転者"], "表示名": "大型トラック運転手", "産業": "Ｈ"},
    "kango": {"職種": ["看護師"], "表示名": "看護師", "産業": "Ｐ"},
    "keibi": {"職種": ["警備員"], "表示名": "警備員", "産業": "Ｒ"},
    "denki": {"職種": ["電気工事従事者"], "表示名": "電気工事士", "産業": "Ｄ"},
    "seibi": {"職種": ["自動車整備・修理従事者"], "表示名": "自動車整備士", "産業": None,
              "産業の注意": "自動車整備は整備工場（サービス業）と販売店（卸売業，小売業）に分かれるので、産業を当てはめない"},
    "daiku": {"職種": ["大工"], "表示名": "大工", "産業": "Ｄ"},
}


def load(name):
    p = os.path.join(DATA, name)
    if not os.path.exists(p):
        sys.exit(f"【止まりました】{os.path.relpath(p, ROOT)} がありません（先に fetch_job_data.py・fetch_a1c_data.py を走らせる）")
    return json.load(open(p, encoding="utf-8"))


def sources():
    return json.load(open(os.path.join(ROOT, "data", "sources.json"), encoding="utf-8"))


def job(key):
    if key not in JOBS:
        sys.exit(f"【止まりました】知らないキー：{key}（job_facts_common.JOBS にあるキー：{', '.join(JOBS)}）")
    return JOBS[key]


def rnd(v, step=1):
    """四捨五入（銀行丸めにしない）。a4_facts.yen_round と同じ"""
    return int((v + step / 2) // step * step) if v >= 0 else -int((-v + step / 2) // step * step)


def man(sen):
    """千円 → 万円（小数1桁）"""
    return round(sen / 10, 1)


def voice_man(sen):
    return f"約{rnd(sen / 10)}万円"


def voice_yen(yen, step=10):
    return f"約{rnd(yen, step):,}円"


def voice_pct(p):
    return f"約{rnd(p)}%"


def per_n(p):
    """割合（%）→「約〇人に1人」。10%なら約10人に1人"""
    if not p:
        return None
    n = 100 / p
    return f"約{rnd(n)}人に1人" if n >= 1.5 else None


def industry_voice(name):
    """表の産業名（医療，福祉）を声と画面の言い方（医療・福祉）にする"""
    return name.replace("，", "・").replace("(", "（").replace(")", "）")


def job_row(sh, m40, official, display):
    """職種1つの値（賃金構造 職種 第1表）と、主な職業40・全職種の中の順位"""
    v = sh[official]
    allv = [x for n, x in sh.items() if n != "不詳" and x.get("年収_千円") is not None]
    rank_n = 1 + sum(1 for x in allv if x["年収_千円"] > v["年収_千円"])
    rank_h = 1 + sum(1 for x in allv if x["時給に直した額_円"] > v["時給に直した額_円"])
    rank_t = 1 + sum(1 for x in allv if x["月の労働時間"] > v["月の労働時間"])
    m = {x["職種"]: x for x in m40}
    row = {
        "表示名": display, "職種（調査の名前）": official,
        "年収_千円": v["年収_千円"], "年収_万円": man(v["年収_千円"]), "声の年収": voice_man(v["年収_千円"]),
        "月の給与（きまって支給）_千円": v["きまって支給する現金給与額"], "声の月の給与": f"月に{voice_man(v['きまって支給する現金給与額'])}",
        "年間の賞与など_千円": v["年間賞与その他特別給与額"], "声の賞与": f"年に{voice_man(v['年間賞与その他特別給与額'])}",
        "月の労働時間": v["月の労働時間"], "うち所定内": v["所定内実労働時間数"], "うち残業など（超過）": v["超過実労働時間数"],
        "時給に直した額_円": v["時給に直した額_円"], "声の時給": voice_yen(v["時給に直した額_円"]),
        "年齢": v["年齢"], "勤続年数": v["勤続年数"], "労働者数_十人": v["労働者数"],
        f"全{len(allv)}職種の中の年収の順位": rank_n, f"全{len(allv)}職種の中の時給の順位": rank_h,
        f"全{len(allv)}職種の中の月の労働時間の順位（長い順）": rank_t,
    }
    if official in m:
        row["主な職業40の中の年収の順位"] = m[official]["年収の順位"]
        row["主な職業40の中の時給の順位"] = m[official]["時給の順位"]
    return row


def avg_row(rec, name):
    """産業計・産業ごとの平均（賃金構造 産業大分類 第1表の年齢計）"""
    v = rec["年齢計"]
    return {"名前": name, "年収_千円": v["年収_千円"], "年収_万円": man(v["年収_千円"]), "声の年収": voice_man(v["年収_千円"]),
            "月の労働時間": v["月の労働時間"], "うち所定内": v["所定内実労働時間数"], "うち残業など（超過）": v["超過実労働時間数"],
            "時給に直した額_円": v["時給に直した額_円"], "声の時給": voice_yen(v["時給に直した額_円"]),
            "年齢": v["年齢"], "勤続年数": v["勤続年数"]}


def compare(a, b, a_name, b_name):
    """a と b の差（年収・月の労働時間・残業・時給・年齢・勤続）と暮らしの言葉への言い直し"""
    dn = a["年収_千円"] - b["年収_千円"]
    dt = a["月の労働時間"] - b["月の労働時間"]
    do = a["うち残業など（超過）"] - b["うち残業など（超過）"]
    dh = a["時給に直した額_円"] - b["時給に直した額_円"]
    word = lambda d, hi, lo: hi if d > 0 else (lo if d < 0 else "同じ")
    return {
        "比べた相手": f"{a_name} と {b_name}（{a_name} − {b_name}）",
        "年収の差_万円": round(dn / 10, 1), "年収": word(dn, "高い", "低い"), "声_年収": f"{voice_man(abs(dn))}{word(dn, '高い', '低い')}" if dn else "同じ",
        "年収の差を月に直すと_万円": round(dn / 120, 1), "声_年収の差を月に": f"月にすると{voice_man(abs(dn) / 12)}" if dn else None,
        "月の労働時間の差": dt, "月の労働時間": word(dt, "長い", "短い"),
        "年の労働時間の差": dt * 12, "週に直すと_時間": round(dt * 12 / 52, 1),
        "声_週": f"週に約{rnd(abs(dt) * 12 / 52)}時間{word(dt, '長い', '短い')}" if dt else "同じ",
        "1日8時間の日に直すと_日": round(dt * 12 / 8, 1),
        "声_日": f"1日8時間で数えると、年に約{rnd(abs(dt) * 12 / 8)}日分{word(dt, '多く働く', '少なく働く')}" if dt else None,
        "月の残業など（超過）の差": do, "年の残業などの差": do * 12,
        "時給の差_円": dh, "時給": word(dh, "高い", "低い"), "声_時給": f"{voice_yen(abs(dh))}{word(dh, '高い', '低い')}" if dh else "同じ",
        "年齢の差": round(a["年齢"] - b["年齢"], 1), "勤続年数の差": round(a["勤続年数"] - b["勤続年数"], 1),
        "計算": "週＝月の差×12÷52。日＝月の差×12÷8（1日8時間で割っただけ。実際の出勤日数ではない）。月に直した年収の差＝年の差÷12。"
                "差は丸める前の値どうしで計算する（丸めた年収どうしを引いた数と1万円ずれることがある。声ではこの差を使う）",
    }


def src_entry(key, name, src):
    s = src.get(key)
    if not s:
        sys.exit(f"【止まりました】data/sources.json に {key} がありません（fetch_a1c_data.py の出典を足していない）")
    return {"key": key, "名前": name, "表": s.get("table"), "公表日": s.get("release_date"), "URL": s.get("landing_page"),
            "ダウンロード": s.get("url"), "statInfId": s.get("statInfId"), "取得日": s.get("fetched"),
            "e_stat": True, "確かさ": "公的統計の表の値をプログラムで計算"}


SRC_NAMES = {
    "chinkin_r7_shokushu": "厚生労働省「令和7年賃金構造基本統計調査」一般労働者 職種 第1表",
    "chinkin_r7_shokushu_t5": "厚生労働省「令和7年賃金構造基本統計調査」一般労働者 職種 第5表（職種・年齢階級別）",
    "chinkin_r7_sangyo_t1": "厚生労働省「令和7年賃金構造基本統計調査」一般労働者 産業大分類 第1表",
    "koyodoko_r7_sanko1": "厚生労働省「令和7年雇用動向調査」参考表1（産業別の労働移動率）",
    "koyodoko_r7_t12": "厚生労働省「令和7年雇用動向調査」年計 第12表（前の勤め先を辞めた理由別 転職入職者）",
}


def sources_block(keys):
    src = sources()
    stats = sorted({SRC_NAMES[k].split("」")[0] + "」" for k in keys})
    return {"出典": [src_entry(k, SRC_NAMES[k], src) for k in keys],
            "e_stat_note": load("shokushu_r7.json")["meta"]["e_stat_note"],
            "加工": "、".join(stats) + "を加工して作成",
            "使った統計": stats, "使った統計がすべてe-Statにあるか": True}


def write(work, facts):
    os.makedirs(work, exist_ok=True)
    p = os.path.join(work, "facts.json")
    json.dump(facts, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return p

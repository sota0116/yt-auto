# 仕事チャンネル 型A-4（職業くらべ）の組を探し、選んだ組の facts.json を書く（手順書 §3 A-4・§4）
#   python -X utf8 pipeline\a4_facts.py search [--top 20]                 … 年収が近い6職業で、時給にすると順位がよく入れ替わる組を並べる
#   python -X utf8 pipeline\a4_facts.py make <作業フォルダ> <表示名> ×5〜6  … その組の facts.json を作業フォルダに書く
# ・値は data\job\main40_r7.json と shokushu_r7.json を読むだけ。順位・差・言い直しはここで計算し、Claude は計算しない
# ・「逆転」をタイトルに入れてよいのは、入れ替わりが2つ以上ある時だけ（facts.json の 逆転を使える）
import itertools, json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data", "job")
NEAR = 800  # 年収の近さ：いちばん上と下の差が 80万円（800千円）以内


def load():
    m40 = json.load(open(os.path.join(DATA, "main40_r7.json"), encoding="utf-8"))
    sh = json.load(open(os.path.join(DATA, "shokushu_r7.json"), encoding="utf-8"))
    return m40, sh


def ranks(rows, key):
    """大きい順の順位（同じ値は同じ順位）"""
    out = {}
    for r in rows:
        out[r["表示名"]] = 1 + sum(1 for x in rows if x[key] > r[key])
    return out


def search(top):
    m = load()[0]["data"]
    res = []
    for g in itertools.combinations(m, 6):
        ns = [x["年収_千円"] for x in g]
        if max(ns) - min(ns) > NEAR:
            continue
        rn, rh = ranks(g, "年収_千円"), ranks(g, "時給に直した額_円")
        moved = [x["表示名"] for x in g if rn[x["表示名"]] != rh[x["表示名"]]]
        mx = max(abs(rn[k] - rh[k]) for k in rn)
        disp = sum(abs(rn[k] - rh[k]) for k in rn)
        res.append((mx, disp, (max(ns) - min(ns)) / 10, len(moved), sorted(rn, key=rn.get), sorted(rh, key=rh.get)))
    res.sort(key=lambda r: (-r[0], -r[1], r[2]))
    print(f"年収の差が{NEAR // 10}万円以内の6職業の組：{len(res)}")
    for r in res[:top]:
        print(f"最大の動き {r[0]}／動きの合計 {r[1]}／年収の差 {r[2]:.1f}万円／入れ替わり {r[3]}")
        print("  年収順", r[4])
        print("  時給順", r[5])


def yen_round(v, step):
    return int((v + step / 2) // step * step)  # 四捨五入（銀行丸めにしない）


def make(work, names):
    m40, sh = load()
    by = {x["表示名"]: x for x in m40["data"]}
    miss = [n for n in names if n not in by]
    if miss:
        sys.exit(f"【止まりました】主な職業40にない名前：{miss}")
    if not 5 <= len(names) <= 6:
        sys.exit("【止まりました】A-4 は5〜6職業（手順書 §3）")
    src = json.load(open(os.path.join(ROOT, "data", "sources.json"), encoding="utf-8"))
    ci = src["chinkin_r7_shokushu"]
    g = [by[n] for n in names]
    full = sh["data"]["男女計"]
    rows = []
    for x in g:
        f = full[x["職種"]]
        man = x["年収_千円"] / 10
        rows.append({
            "表示名": x["表示名"], "職種（調査の名前）": x["職種"],
            "年収_千円": x["年収_千円"], "年収_万円": round(man, 1), "声の年収": f"約{yen_round(man, 1)}万円",
            "月の労働時間": x["月の労働時間"], "うち所定内": f["所定内実労働時間数"], "うち残業など（超過）": f["超過実労働時間数"],
            "時給に直した額_円": x["時給に直した額_円"], "声の時給": f"約{yen_round(x['時給に直した額_円'], 10):,}円",
            "年齢": x["年齢"], "勤続年数": x["勤続年数"],
            "主な職業40の中の年収の順位": x["年収の順位"], "主な職業40の中の時給の順位": x["時給の順位"],
        })
    rn, rt, rh = ranks(rows, "年収_千円"), ranks(rows, "月の労働時間"), ranks(rows, "時給に直した額_円")
    for r in rows:
        r["この回の年収の順位"], r["この回の労働時間の順位（長い順）"], r["この回の時給の順位"] = rn[r["表示名"]], rt[r["表示名"]], rh[r["表示名"]]
    swaps = [{"表示名": k, "年収の順位": rn[k], "時給の順位": rh[k], "動き": rn[k] - rh[k]} for k in rn if rn[k] != rh[k]]

    # 山場に出す職業（3つまで）：いちばん下がった職業 → 時給で1位になった職業 → いちばん上がった職業
    peak = []
    if swaps:
        down = min(swaps, key=lambda s: (s["動き"], -s["年収の順位"]))
        if down["動き"] < 0:
            peak.append(down["表示名"])
        top = [s for s in swaps if s["時給の順位"] == 1]
        if top and top[0]["表示名"] not in peak:
            peak.append(top[0]["表示名"])
        for s in sorted(swaps, key=lambda s: -s["動き"]):
            if len(peak) >= 3:
                break
            if s["動き"] > 0 and s["表示名"] not in peak:
                peak.append(s["表示名"])

    by_r = {r["表示名"]: r for r in rows}
    hi_n, lo_n = max(rows, key=lambda r: r["年収_千円"]), min(rows, key=lambda r: r["年収_千円"])
    hi_t, lo_t = max(rows, key=lambda r: r["月の労働時間"]), min(rows, key=lambda r: r["月の労働時間"])
    hi_h, lo_h = max(rows, key=lambda r: r["時給に直した額_円"]), min(rows, key=lambda r: r["時給に直した額_円"])
    dn = (hi_n["年収_千円"] - lo_n["年収_千円"]) / 10
    dt = hi_t["月の労働時間"] - lo_t["月の労働時間"]
    dh = hi_h["時給に直した額_円"] - lo_h["時給に直した額_円"]
    talk = {
        "年収の差（いちばん上と下）": {"上": hi_n["表示名"], "下": lo_n["表示名"], "万円": round(dn, 1), "声": f"約{yen_round(dn, 1)}万円"},
        "月の労働時間の差（いちばん長いと短い）": {
            "長い": hi_t["表示名"], "短い": lo_t["表示名"], "月_時間": dt, "年_時間": dt * 12,
            "週_時間": round(dt * 12 / 52, 1), "声_週": f"週に約{yen_round(dt * 12 / 52, 1)}時間",
            "8時間の日に直すと_日": round(dt * 12 / 8, 1), "声_日": f"1日8時間で数えると、年に約{yen_round(dt * 12 / 8, 1)}日分",
            "計算": "週＝月の差×12÷52。日＝月の差×12÷8（1日8時間で割っただけ。実際の出勤日数ではない）"},
        "時給の差（いちばん高いと低い）": {"高い": hi_h["表示名"], "低い": lo_h["表示名"], "円": dh, "声": f"約{yen_round(dh, 10):,}円"},
    }
    for k in peak:  # 山場の職業ごとの、時給1位との差・労働時間の差
        r = by_r[k]
        talk[f"山場：{k}"] = {"年収の順位": r["この回の年収の順位"], "時給の順位": r["この回の時給の順位"],
                            "月の労働時間": r["月の労働時間"], "うち残業など（超過）": r["うち残業など（超過）"]}

    facts = {
        "type": "A", "frame": "A-4",
        "比べた物差し": {"年収": "高い順", "月の労働時間": "長い順", "時給に直した額": "高い順"},
        "定義": {"年収": m40["meta"]["年収の定義"], "時給に直した額": m40["meta"]["時給の定義"],
               "月の労働時間": "所定内実労働時間数＋超過実労働時間数（1か月）", "対象": m40["meta"]["対象"],
               "順位": "この回の職業の中での順位。同じ値は同じ順位"},
        "職業": sorted(rows, key=lambda r: r["この回の年収の順位"]),
        "順位": {"年収": sorted(rn, key=rn.get), "月の労働時間": sorted(rt, key=rt.get), "時給に直した額": sorted(rh, key=rh.get)},
        "入れ替わり": swaps, "入れ替わりの数": len(swaps), "逆転を使える": len(swaps) >= 2,
        "山場の職業": peak, "言い直し": talk,
        "出典": [{"key": "chinkin_r7_shokushu", "名前": "厚生労働省「令和7年賃金構造基本統計調査」一般労働者 職種 第1表",
                "公表日": ci.get("release_date"), "URL": ci.get("landing_page"), "ダウンロード": ci.get("url"), "statInfId": ci.get("statInfId"),
                "取得日": ci.get("fetched"), "確かさ": "公的統計の表の値をプログラムで計算"}],
        "e_stat_note": m40["meta"]["e_stat_note"], "加工": "厚生労働省「令和7年賃金構造基本統計調査」を加工して作成",
    }
    os.makedirs(work, exist_ok=True)
    p = os.path.join(work, "facts.json")
    json.dump(facts, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"書きました：{p}（入れ替わり {len(swaps)}／山場 {peak}）")


if __name__ == "__main__":
    a = sys.argv[1:]
    if a and a[0] == "search":
        search(int(a[a.index("--top") + 1]) if "--top" in a else 20)
    elif len(a) >= 3 and a[0] == "make":
        make(a[1], a[2:])
    else:
        print("使い方は先頭のコメントを見てください")

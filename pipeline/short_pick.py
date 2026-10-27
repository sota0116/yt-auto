# ショート①題選び（2026-10-27 から。本人「横動画は毎日じゃなくてもいい。その代わりショートを毎日1〜3本」）
#   python -X utf8 pipeline\short_pick.py [--out <作業フォルダ>] [--kind rank|duel] [--list]
# ・data\job\ の保存済みの統計（賃金構造基本統計調査 令和7年 職種別）だけから、ショート1本分の題と facts.json を作る。e-Stat には取りに行かない
# ・題は2種類：rank（ある仲間の職業を1つの物差しで並べた上位5つ）／duel（年収がほぼ同じ2つの職業が、別の物差しで大きく分かれる）
# ・順位・差・声で言う丸めた値は、ここで計算して facts.json に書く。Claude は計算しない（手順書 §4・§12）
# ・使った題は history\job\shorts.json に残し、同じ題を2回出さない。rank と duel を交互に、同じ物差しが続かないように選ぶ
# ・数字が集まったら（short_learn.py の history\job\shorts_learn.json）、3本に2本は点の高い種類と物差しを先に、1本は試す枠で選ぶ
# ・先生（小・中学校・高校）は使わない（公務＝公立の学校は調査の対象外で、私立だけの値になるため。手順書 §8）
import argparse, datetime, hashlib, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from job_facts_common import ROOT, load, rnd, sources_block, write

HIST = os.path.join(ROOT, "history", "job", "shorts.json")
SKIP = ("小・中学校の先生", "高校の先生")

# 物差し：表の項目・画面の単位・声の言い方・高い方と低い方の言葉
MEASURES = {
    "年収": {"key": "年収_千円", "screen": lambda v: f"{v / 10:,.1f}万円", "voice": lambda v: f"約{rnd(v / 10):,}万円", "hi": "高い", "lo": "低い"},
    "時給": {"key": "時給に直した額_円", "screen": lambda v: f"{v:,.0f}円", "voice": lambda v: f"約{rnd(v, 10):,}円", "hi": "高い", "lo": "低い",
             "名前": "時給に直した額"},
    "労働時間": {"key": "月の労働時間", "screen": lambda v: f"{v:g}時間", "voice": lambda v: f"月に{v:g}時間", "hi": "長い", "lo": "短い",
                 "名前": "1か月に働いた時間"},
    "残業": {"key": "超過実労働時間数", "screen": lambda v: f"{v:g}時間", "voice": lambda v: f"月に{v:g}時間", "hi": "多い", "lo": "少ない",
             "名前": "1か月の残業など（所定外の労働時間）"},
    "ボーナス": {"key": "年間賞与その他特別給与額", "screen": lambda v: f"{v / 10:,.1f}万円", "voice": lambda v: f"年に約{rnd(v / 10):,}万円",
                 "hi": "多い", "lo": "少ない", "名前": "年間の賞与など（ボーナス）"},
    "年齢": {"key": "年齢", "screen": lambda v: f"{v:.1f}歳", "voice": lambda v: f"約{rnd(v)}歳", "hi": "高い", "lo": "若い", "名前": "平均の年齢"},
    "勤続": {"key": "勤続年数", "screen": lambda v: f"{v:.1f}年", "voice": lambda v: f"約{rnd(v)}年", "hi": "長い", "lo": "短い", "名前": "平均の勤続年数"},
}
# 仲間（表示名で決める。賃金構造の職種の分け方ではなく、このチャンネルの分け方。facts.json に書く）
GROUPS = {
    "全体": None,
    "医療・福祉": ["医師", "歯科医師", "薬剤師", "看護師", "臨床検査技師", "理学療法士など（リハビリ職）", "ケアマネージャー", "保育士",
                 "歯科衛生士", "介護職員（施設）", "訪問介護員（ヘルパー）", "幼稚園の先生・保育教諭"],
    "乗り物": ["パイロット", "電車の運転士", "客室乗務員（CA）", "大型トラック運転手", "バス運転手", "タクシー運転手", "自動車整備士"],
    "現場": ["電気工事士", "大工", "建築技術者（設計・施工管理）", "土木技術者（設計・施工管理）", "自動車整備士", "警備員", "調理人",
             "大型トラック運転手"],
    "会社員": ["管理職", "システムエンジニア（設計者）", "プログラマー（ソフトウェア作成者）", "一般事務（総合事務員）", "銀行・証券の営業",
               "機械・通信・システムの営業", "保険の営業", "デザイナー", "販売店員", "公認会計士・税理士"],
}
GROUP_WORD = {"全体": "主な職業", "医療・福祉": "医療・福祉の仕事", "乗り物": "乗り物の仕事", "現場": "現場の仕事", "会社員": "会社員の仕事"}
TOP = 5


def rows():
    """主な職業40（先生を除く）に、職種第1表の残業・ボーナスを足した物"""
    m40 = load("main40_r7.json")["data"]
    sh = load("shokushu_r7.json")["data"]["男女計"]
    out = []
    for r in m40:
        if r["表示名"] in SKIP:
            continue
        v = sh[r["職種"]]
        out.append({**r, "超過実労働時間数": v["超過実労働時間数"], "年間賞与その他特別給与額": v["年間賞与その他特別給与額"],
                    "きまって支給する現金給与額": v["きまって支給する現金給与額"]})
    return out


def ranks(rs, key):
    """大きい順の順位（同じ値は同じ順位）"""
    return {r["表示名"]: 1 + sum(1 for x in rs if x[key] > r[key]) for r in rs}


def topics(rs):
    out = []
    for g, names in GROUPS.items():
        pool = [r for r in rs if names is None or r["表示名"] in names]
        if len(pool) < 6:
            continue
        for m in MEASURES:
            for hi in (True, False):
                if not hi and m in ("年齢", "勤続", "ボーナス") and g != "全体":
                    continue  # 仲間の中の「低い順」は差が小さく驚きが少ない
                k = MEASURES[m]["key"]
                vs = sorted((r[k] for r in pool), reverse=hi)
                if vs[0] == vs[1] or vs[TOP - 1] == vs[TOP] or len(set(vs[:TOP])) < 4:
                    continue  # 1位か5位が同じ値で並ぶ・同じ値ばかりの題は、順位で見せられない
                out.append({"id": f"rank_{g}_{m}_{'hi' if hi else 'lo'}", "kind": "rank", "group": g, "measure": m, "hi": hi})
    # duel：年収の差が5%以内で、時給か労働時間か残業かボーナスの差が大きい2つ
    for i, a in enumerate(rs):
        for b in rs[i + 1:]:
            if abs(a["年収_千円"] - b["年収_千円"]) > 0.05 * max(a["年収_千円"], b["年収_千円"]):
                continue
            best = None
            for m in ("時給", "労働時間", "残業", "ボーナス"):
                k = MEASURES[m]["key"]
                lo, hi_ = sorted([a[k], b[k]])
                ratio = hi_ / lo if lo else 99
                need = {"時給": 1.15, "労働時間": 1.10, "残業": 2.0, "ボーナス": 1.5}[m]
                if ratio >= need and (not best or ratio / need > best[1]):
                    best = (m, ratio / need)
            if best:
                x, y = sorted([a, b], key=lambda r: r["表示名"])
                out.append({"id": f"duel_{x['表示名']}_{y['表示名']}_{best[0]}", "kind": "duel", "a": x["表示名"], "b": y["表示名"], "measure": best[0]})
    # 同じ順にならないように、題の名前から決まる順で並べる（毎回同じ結果になる）
    return sorted(out, key=lambda t: hashlib.sha1(t["id"].encode()).hexdigest())


def history():
    return json.load(open(HIST, encoding="utf-8")) if os.path.exists(HIST) else []


def choose(ts, kind=None):
    h = history()
    used = {x["topic_id"] for x in h}
    last = h[-1] if h else {}
    recent_m = [x.get("measure") for x in h[-3:]]
    want = kind or ("duel" if last.get("kind") == "rank" else "rank")
    # PDCA（short_learn.py の学び）：3本に2本は点の高い種類・物差しから、1本は試していない・点の低い物から（試す枠）
    lp = os.path.join(ROOT, "history", "job", "shorts_learn.json")
    learn = json.load(open(lp, encoding="utf-8")) if os.path.exists(lp) else {}
    kp, mp = learn.get("種類の点") or {}, learn.get("物差しの点") or {}
    explore = len(h) % 3 == 2
    if not kind and len(kp) == 2 and not explore:
        want = max(kp, key=kp.get)
    if mp:
        mid = sorted(mp.values())[len(mp) // 2]
        ts = sorted(ts, key=lambda t: mp.get(t["measure"], -1) if explore else -mp.get(t["measure"], mid))
    for strict in (True, False):
        for t in ts:
            if t["id"] in used or t["kind"] != want:
                continue
            if strict and t["measure"] in recent_m:
                continue
            return t
    if not kind:
        return choose(ts, "rank" if want == "duel" else "duel")
    sys.exit("【止まりました】ショートの題が残っていません（short_pick.py の題の作り方を足す）")


def item(r, m, all_ranks):
    M = MEASURES[m]
    v = r[M["key"]]
    return {"表示名": r["表示名"], "職種（調査の名前）": r["職種"], "値": v, "画面の値": M["screen"](v), "声の値": M["voice"](v),
            "年収_万円": round(r["年収_千円"] / 10, 1), "声の年収": MEASURES["年収"]["voice"](r["年収_千円"]),
            "時給に直した額_円": r["時給に直した額_円"], "声の時給": MEASURES["時給"]["voice"](r["時給に直した額_円"]),
            "月の労働時間": r["月の労働時間"], "月の残業など": r["超過実労働時間数"],
            "月の給与（きまって支給する額）_万円": round(r["きまって支給する現金給与額"] / 10, 1),
            "声の月の給与": f"月に約{rnd(r['きまって支給する現金給与額'] / 10):,}万円",
            "年間の賞与など_万円": round(r["年間賞与その他特別給与額"] / 10, 1), "年齢": r["年齢"], "勤続年数": r["勤続年数"],
            f"主な職業{len(all_ranks['年収'])}の中の年収の順位": all_ranks["年収"][r["表示名"]],
            f"主な職業{len(all_ranks['年収'])}の中の時給の順位": all_ranks["時給"][r["表示名"]]}


def facts(t, rs):
    allr = {m: ranks(rs, MEASURES[m]["key"]) for m in ("年収", "時給")}
    n_all = len(rs)
    M = MEASURES[t["measure"]]
    name = M.get("名前", t["measure"])
    base = {"kind": t["kind"], "topic_id": t["id"], "measure": t["measure"], "物差し": name,
            "定義": {"年収": "きまって支給する現金給与額×12＋年間賞与その他特別給与額（賞与は前の年1年分）",
                   "時給に直した額": "年収÷（所定内実労働時間数＋超過実労働時間数）÷12",
                   "1か月に働いた時間": "所定内実労働時間数＋超過実労働時間数（6月分）",
                   "1か月の残業など（所定外の労働時間）": "超過実労働時間数（6月分）。早出・残業・休日出勤など",
                   "年間の賞与など（ボーナス）": "年間賞与その他特別給与額（前の年1年分）"}.get(name, name),
            "対象": f"一般労働者（短時間労働者を除く）・企業規模10人以上・男女計。主な職業{n_all}（main40 から先生2つを除いた物）",
            **sources_block(["chinkin_r7_shokushu"])}
    if t["kind"] == "rank":
        names = GROUPS[t["group"]]
        pool = [r for r in rs if names is None or r["表示名"] in names]
        k = M["key"]
        pool.sort(key=lambda r: r[k], reverse=t["hi"])
        top = pool[:TOP]
        word = M["hi"] if t["hi"] else M["lo"]
        grp = GROUP_WORD[t["group"]]
        rk = {r["表示名"]: 1 + sum(1 for x in pool if (x[k] > r[k] if t["hi"] else x[k] < r[k])) for r in top}
        return {**base, "group": t["group"], "仲間": grp, "仲間の数": len(pool), "仲間の職業": [r["表示名"] for r in pool],
                "並べ方": f"{name}が{word}順", "題": f"{grp}{len(pool)}の中で、{name}が{word}5つ",
                "順位": [{"順位": rk[r["表示名"]], **item(r, t["measure"], allr)} for r in top],
                "1位と5位の差": {"画面": M["screen"](abs(top[0][k] - top[-1][k])), "声": M["voice"](abs(top[0][k] - top[-1][k]))},
                "charts": [{"title": f"{name}（{word}順）", "unit": name, "bars": [
                    {"name": r["表示名"], "rank": rk[r["表示名"]], "value": r[k], "label": M["screen"](r[k])} for r in top], "reveal": "bottom_up"}]}
    a = next(r for r in rs if r["表示名"] == t["a"])
    b = next(r for r in rs if r["表示名"] == t["b"])
    k = M["key"]
    big, small = (a, b) if a[k] >= b[k] else (b, a)
    dv = big[k] - small[k]
    ratio = big[k] / small[k] if small[k] else None
    dn = abs(a["年収_千円"] - b["年収_千円"])
    return {**base, "2つの職業": [a["表示名"], b["表示名"]],
            "題": f"年収がほぼ同じ{a['表示名']}と{b['表示名']}、{name}で比べると",
            "年収の差": {"画面": MEASURES["年収"]["screen"](dn), "声": f"約{rnd(dn / 10):,}万円" if rnd(dn / 10) else "1万円もない"},
            "職業": [item(r, t["measure"], allr) for r in (a, b)],
            f"{name}が{M['hi']}方": big["表示名"],
            f"{name}の差": {"画面": M["screen"](dv), "声": M["voice"](dv).replace("約約", "約")},
            f"{name}の倍率": {"値": round(ratio, 2), "声": f"約{ratio:.1f}倍"} if ratio and ratio >= 1.4 else None,
            "charts": [
                {"title": "年収", "unit": "年収", "bars": [{"name": r["表示名"], "value": r["年収_千円"], "label": MEASURES["年収"]["screen"](r["年収_千円"])}
                                                       for r in (a, b)], "reveal": "together"},
                {"title": name, "unit": name, "bars": [{"name": r["表示名"], "value": r[k], "label": M["screen"](r[k]),
                                                        "hl": r is big} for r in (a, b)], "reveal": "together"}]}


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--out")
    a.add_argument("--kind", choices=["rank", "duel"])
    a.add_argument("--list", action="store_true")
    a = a.parse_args()
    rs = rows()
    ts = topics(rs)
    if a.list:
        used = {x["topic_id"] for x in history()}
        print(f"題：{len(ts)}（rank {sum(t['kind'] == 'rank' for t in ts)}・duel {sum(t['kind'] == 'duel' for t in ts)}）・使った題 {len(used)}")
        for t in ts[:40]:
            print(("済 " if t["id"] in used else "   ") + t["id"])
        return
    t = choose(ts, a.kind)
    f = facts(t, rs)
    stamp = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).strftime("%Y%m%d_%H%M")
    work = a.out or os.path.join(ROOT, "channels", "job", "shorts", f"{stamp}_{t['kind']}")
    write(work, f)
    print(json.dumps({"work": work, "topic_id": t["id"], "題": f["題"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()

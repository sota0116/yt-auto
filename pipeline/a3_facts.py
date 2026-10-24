# 仕事チャンネル 型A-3（似た職業との比べ）の facts.json を書く（手順書 §3 型A A-3・§4）
#   python -X utf8 pipeline\a3_facts.py list                         … 用意した組と、逆転が起きる項目を並べる
#   python -X utf8 pipeline\a3_facts.py make <作業フォルダ> <組のキー>  … その組の facts.json を作業フォルダに書く
# ・同じ業界の2つの職業を5項目（年収・月の労働時間・時給に直した額・平均年齢・勤続年数）で並べ、項目ごとに判定する
# ・離職率は産業の数字で2つが同じ値になるので、比べる項目に入れない（手順書 §3）
# ・値は data\job\shokushu_r7.json（賃金構造 職種 第1表）を読むだけ。時給・差・判定はここで計算し、Claude は計算しない
import sys
import job_facts_common as c

# 組：同じ業界で働くことが多い2職業（業界の当てはめは、このチャンネルの判断。表の上で結びついているわけではない）
PAIRS = {
    "kenchiku_doboku": {"業界": "建設業", "職業": [("建築技術者", "建築の技術者（施工管理）"), ("土木技術者", "土木の技術者（施工管理）")]},
    "se_pg": {"業界": "情報通信業", "職業": [("システムコンサルタント・設計者", "システムエンジニア"), ("ソフトウェア作成者", "プログラマー")]},
    "taxi_bus": {"業界": "運輸業", "職業": [("タクシー運転者", "タクシー運転手"), ("バス運転者", "バス運転手")]},
    "truck_daisho": {"業界": "運輸業", "職業": [("営業用大型貨物自動車運転者", "大型トラック運転手"), ("営業用貨物自動車運転者（大型車を除く）", "中小型トラック運転手")]},
    "kaigo_houmon": {"業界": "医療・福祉", "職業": [("介護職員（医療・福祉施設等）", "施設の介護職員"), ("訪問介護従事者", "訪問介護員（ホームヘルパー）")]},
    "kango_junkango": {"業界": "医療・福祉", "職業": [("看護師", "看護師"), ("准看護師", "准看護師")]},
}
# 項目：(facts の名前, 職業の値のキー, よい方の向き)。向き None は判定しない
ITEMS = [("年収", "年収_千円", "高い"), ("月の労働時間", "月の労働時間", "短い"), ("時給に直した額", "時給に直した額_円", "高い"),
         ("平均年齢", "年齢", None), ("勤続年数", "勤続年数", "長い")]


def build(key):
    if key not in PAIRS:
        sys.exit(f"【止まりました】知らない組：{key}（{', '.join(PAIRS)}）")
    pr = PAIRS[key]
    sh = c.load("shokushu_r7.json")["data"]["男女計"]
    m40 = c.load("main40_r7.json")["data"]
    for off, _ in pr["職業"]:
        if off not in sh:
            sys.exit(f"【止まりました】職種の表に無い名前：{off}")
    a, b = (c.job_row(sh, m40, off, disp) for off, disp in pr["職業"])
    na, nb = a["表示名"], b["表示名"]
    rich = na if a["年収_千円"] >= b["年収_千円"] else nb  # 年収が高い方
    unit = {"年収": "万円", "月の労働時間": "時間", "時給に直した額": "円", "平均年齢": "歳", "勤続年数": "年"}
    rows = []
    for name, k, good in ITEMS:
        va, vb = a[k], b[k]
        if name == "年収":
            va, vb = a["年収_万円"], b["年収_万円"]
        d = round(va - vb, 1) if isinstance(va, float) or isinstance(vb, float) else va - vb
        if good is None or va == vb:
            win = None
        elif good in ("高い", "長い"):
            win = na if va > vb else nb
        else:
            win = na if va < vb else nb
        say = {"年収": lambda x: c.voice_man(x * 10), "時給に直した額": c.voice_yen}.get(name, lambda x: f"{x}{unit[name]}")
        rows.append({"項目": name, "よい方の向き": good, na: va, nb: vb, f"声_{na}": say(va), f"声_{nb}": say(vb),
                     f"差（{na}−{nb}）": d, "声_差": (say(abs(d)) if name not in ("年収",) else c.voice_man(abs(a["年収_千円"] - b["年収_千円"]))) if d else "同じ",
                     "判定": (f"{win}の方がよい" if win else ("判定しない" if good is None else "同じ")), "勝った方": win,
                     "逆転": bool(win) and name != "年収" and win != rich})
    flips = [r["項目"] for r in rows if r["逆転"]]
    order = ["時給に直した額", "月の労働時間", "勤続年数"]
    peak = next((x for x in order if x in flips), None)
    return pr, a, b, rows, flips, peak, rich


def list_pairs():
    for k in PAIRS:
        pr, a, b, rows, flips, peak, rich = build(k)
        print(f"{k}｜{a['表示名']} {a['声の年収']}・{b['表示名']} {b['声の年収']}｜逆転：{flips or 'なし'}｜山場：{peak}")


def make(work, key):
    pr, a, b, rows, flips, peak, rich = build(key)
    na, nb = a["表示名"], b["表示名"]
    poor = nb if rich == na else na
    vs = c.compare(a, b, na, nb)
    nums = []
    for r in rows:
        nums += [r[f"声_{na}"], r[f"声_{nb}"], r["声_差"]]
    nums += [vs["声_週"], vs["声_日"], vs["声_年収の差を月に"]]
    facts = {
        "type": "A", "frame": "A-3", "組": key, "業界": pr["業界"], "職業": [a, b],
        "比べる項目": [x[0] for x in ITEMS],
        "定義": {"年収": "きまって支給する現金給与額×12＋年間賞与その他特別給与額", "時給に直した額": "年収÷（月の労働時間×12）",
               "月の労働時間": "所定内実労働時間数＋超過実労働時間数（1か月）",
               "対象": "一般労働者（短時間労働者を除く）・民営事業所・企業規模10人以上・男女計",
               "判定": "年収・時給は高い方、月の労働時間は短い方、勤続年数は長い方を「よい方」にする。平均年齢は判定しない",
               "逆転": f"年収が低い方（{poor}）が、年収以外の項目で上になること",
               "業界": "2職業を同じ業界に置いたのはこのチャンネルの当てはめ。離職率は産業の数字で2つが同じ値になるので比べない（手順書 §3）"},
        "項目ごと": rows, "年収が高い方": rich, "逆転した項目": flips, "逆転を使える": bool(flips), "山場の項目": peak,
        "山場の注意": None if peak else "逆転が起きる項目が無い。A-3 の山場（意外な逆転）が作れないので、この組は使わない",
        "言い直し": {"2職業の差": vs},
        "声の決まり": "1章で声で言い切る数字は1つ。ほかは画面の表で見せる（手順書 §4）",
        "声で言える数字": [n for n in nums if n],
    }
    facts.update(c.sources_block(["chinkin_r7_shokushu"]))
    p = c.write(work, facts)
    print(f"書きました：{p}（{na}・{nb}／逆転 {flips}／山場 {peak}）")


if __name__ == "__main__":
    args = sys.argv[1:]
    if args[:1] == ["list"]:
        list_pairs()
    elif len(args) == 3 and args[0] == "make":
        make(args[1], args[2])
    else:
        print("使い方は先頭のコメントを見てください")

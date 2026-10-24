# 仕事チャンネル 型A-1（理由の数え上げ「なぜ〇〇を辞める人が多いのか」）の facts.json を書く（手順書 §3 型A・§4）
#   python -X utf8 pipeline\a1_facts.py make <作業フォルダ> <キー>      … キーは job_facts_common.JOBS のキー（kaigo・hoiku など）
#   python -X utf8 pipeline\a1_facts.py check                          … 全部のキーで、A-1 にできるか（産業の離職率が全産業より高いか）を並べる
# ・値は data\job\ の保存済みの JSON を読むだけ（shokushu_r7・main40_r7・rishoku_sangyo_r7・a1c_r7）
# ・辞める理由は雇用動向調査 第12表「前の勤め先を辞めた理由」（転職入職者）。産業は「入った先」の産業。職業の数字ではない
# ・その職業を含む産業の離職率が全産業より高くない時は止まる（手順書 §3：A-1 の題はその職業だけ）
import os, sys
import job_facts_common as c

# 自分から辞めた理由（個人的理由）のうち、中身の分かる9項目だけを順位にする
#  ・「その他の個人的理由」「その他の理由（出向等を含む）」は中身が分からないので外す
#  ・「定年、契約期間の満了」「会社都合」は本人が選んだ辞め方ではないので順位に入れず、参考に置く
RANKED = ["仕事の内容に興味を持てず", "能力・個性・資格を生かせず", "職場の人間関係", "会社の将来が不安", "収入が少ない",
          "労働条件が悪い", "結婚", "出産・育児", "介護・看護"]
REFERENCE = ["定年、契約期間の満了", "会社都合", "その他の個人的理由", "その他の理由（出向等を含む）"]
# 声と画面の言い方（調査の項目名は「出典の項目名」に残す）
SAY = {"仕事の内容に興味を持てず": "仕事の内容に興味を持てない", "能力・個性・資格を生かせず": "能力や資格を生かせない",
       "職場の人間関係": "職場の人間関係", "会社の将来が不安": "会社の将来が不安", "収入が少ない": "収入が少ない",
       "労働条件が悪い": "労働条件が悪い（労働時間・休日など）", "結婚": "結婚", "出産・育児": "出産・育児", "介護・看護": "家族の介護・看護"}


def industry(key):
    j = c.job(key)
    if not j["産業"]:
        sys.exit(f"【止まりました】{j['表示名']} は産業を1つに当てはめていません（{j.get('産業の注意')}）。A-1 にできません")
    rs = c.load("rishoku_sangyo_r7.json")
    rows = rs["data"]["男女計"]
    name = next((n for n, v in rows.items() if v.get("記号") == j["産業"]), None)
    if not name:
        sys.exit(f"【止まりました】rishoku_sangyo_r7.json に記号 {j['産業']} の産業がありません")
    return j, rs, name, rows[name]["離職率"], rows["産業計"]["離職率"]


def say_industry(name):
    """声の業界名（医療，福祉 → 医療・福祉業）。手順書 §3 の「△△業」に合わせ、業で終わらない名前には業を付ける"""
    v = c.industry_voice(name)
    return v if v.endswith("業") else v + "業"


def check():
    print("キー｜職業｜産業｜離職率｜全産業｜A-1 にできるか")
    for k, j in c.JOBS.items():
        if not j["産業"]:
            print(f"{k}｜{j['表示名']}｜（当てはめない）｜-｜-｜できない")
            continue
        _, _, name, r, all_r = industry(k)
        print(f"{k}｜{j['表示名']}｜{name}｜{r}｜{all_r}｜{'できる' if r > all_r else 'できない'}")


def make(work, key):
    j, rs, name, rate, all_rate = industry(key)
    if not rate > all_rate:
        sys.exit(f"【止まりました】{j['表示名']} を含む{name}の離職率 {rate}% は、全産業 {all_rate}% より高くありません。"
                 "A-1（なぜ辞める人が多いのか）の題にできません（手順書 §3）")
    a = c.load("a1c_r7.json")
    sh = c.load("shokushu_r7.json")["data"]["男女計"]
    m40 = c.load("main40_r7.json")["data"]
    t12 = a["data"]["離職理由_産業別"]["男女計"]
    ind, tot = t12[j["産業"]], t12["産業計"]
    if ind["表の名前"][:4] != name[:4]:
        sys.exit(f"【止まりました】第12表の産業（{ind['表の名前']}）と離職率の産業（{name}）が合いません")
    iv, sv = c.industry_voice(name), say_industry(name)
    disp = j["表示名"]

    # 辞める理由：9項目を割合の大きい順に。同じ割合は同じ順位
    pct, cnt, all_pct = ind["辞めた理由_構成比"], ind["辞めた理由_千人"], tot["辞めた理由_構成比"]
    items = sorted(RANKED, key=lambda x: (-pct[x], RANKED.index(x)))
    rank = {x: 1 + sum(1 for y in RANKED if pct[y] > pct[x]) for x in RANKED}
    top = [x for x in items if rank[x] <= 5]
    if len(top) < 5:
        sys.exit("【止まりました】出典のある理由が5つ取れません（手順書 §3：ネタ帳に入れない）")
    tie = len(top) > 5 or any(list(rank.values()).count(rank[x]) > 1 for x in top)
    reasons = []
    for x in top:
        d = round(pct[x] - all_pct[x], 1)
        reasons.append({
            "順位": rank[x], "理由": SAY[x], "出典の項目名": x,
            "割合_%": pct[x], "声の割合": f"{pct[x]}%", "声の割合_丸め": c.voice_pct(pct[x]), "人に1人": c.per_n(pct[x]),
            "人数_千人": cnt[x], "全産業の割合_%": all_pct[x], "全産業との差_ポイント": d,
            "声_全産業との差": (f"全産業の{all_pct[x]}%より{abs(d)}ポイント{'高い' if d > 0 else '低い'}" if d else f"全産業と同じ{all_pct[x]}%"),
        })
    by_rank = {r["順位"]: r for r in reasons}
    order = sorted(reasons, key=lambda r: (-r["順位"], -RANKED.index(r["出典の項目名"])))  # 5位 → 1位
    first = [r for r in reasons if r["順位"] == 1]

    # 2位の前のクイズ：2位の答えと、まだ出していない（5位まで外の）理由2つ。1位は選択肢に入れない（山場を先に明かさないため）
    second = by_rank.get(2)
    quiz = None
    if second:
        others = [x for x in items if rank[x] > 5][:2]
        if len(others) < 2:
            others = [x for x in items if x not in top][:2]
        ch = sorted([second["出典の項目名"]] + others, key=RANKED.index)
        quiz = {"いつ": "2位を出す前", "問い": f"{sv}で転職した人が、前の職場を辞めた理由の2位は？",
                "選択肢": [SAY[x] for x in ch], "答え": second["理由"], "答えの割合": second["声の割合"],
                "外れの選択肢の割合": {SAY[x]: f"{pct[x]}%" for x in others},
                "決まり": "1位は選択肢に入れない。選択肢の並びは調査の項目の順（順位を当てさせない）"}

    # 職業の数字（賃金構造 職種 第1表）と、全国平均（産業計）・その産業の平均
    sg = a["data"]["産業別_平均"]
    me = c.job_row(sh, m40, j["職種"][0], disp)
    avg_all = c.avg_row(sg["産業計"], "全産業の平均（一般労働者）")
    avg_ind = c.avg_row(sg[j["産業"]], f"{iv}の平均（一般労働者）") if j["産業"] in sg else None
    vs_all = c.compare(me, avg_all, disp, "全産業の平均")
    vs_ind = c.compare(me, avg_ind, disp, f"{iv}の平均") if avg_ind else None

    # 山場：1位の理由を自前データで裏付ける。理由に合う物差しを選ぶ
    peak = []
    for r in first:
        x = r["出典の項目名"]
        p = {"理由": r["理由"], "業界の割合": r["声の割合"], "全産業の割合": f"{r['全産業の割合_%']}%", "声_全産業との差": r["声_全産業との差"]}
        if x == "収入が少ない":
            p["裏付けの物差し"] = "年収・時給（その職業と全産業の平均）"
            p["その職業"] = {"年収": me["声の年収"], "時給": me["声の時給"]}
            p["全産業の平均"] = {"年収": avg_all["声の年収"], "時給": avg_all["声の時給"]}
            p["差"] = {k: vs_all[k] for k in ("声_年収", "声_年収の差を月に", "声_時給")}
        elif x == "労働条件が悪い":
            p["裏付けの物差し"] = "月の労働時間・残業など（その職業と全産業の平均）"
            p["その職業"] = {"月の労働時間": f"{me['月の労働時間']}時間", "うち残業など": f"{me['うち残業など（超過）']}時間"}
            p["全産業の平均"] = {"月の労働時間": f"{avg_all['月の労働時間']}時間", "うち残業など": f"{avg_all['うち残業など（超過）']}時間"}
            p["差"] = {k: vs_all[k] for k in ("声_週", "声_日")}
        else:
            p["裏付けの物差し"] = "業界の割合と全産業の割合のくらべ（賃金の表にこの理由に当たる値はない）"
            p["業界の人数_千人"] = r["人数_千人"]
            p["人に1人"] = r["人に1人"]
        peak.append(p)

    # 選んだ理由は「続ける理由」ではない（今の勤め先を選んだ理由）。参考だけ
    pick = ind["選んだ理由_構成比"]
    pick_top = sorted([k for k in pick if not k.startswith("その他")], key=lambda k: -pick[k])[:3]

    rate_d = round(rate - all_rate, 1)
    say_rate = f"{disp}を含む{sv}の離職率"
    nums = [f"{rate}%", f"{all_rate}%", f"{rate_d}ポイント", me["声の年収"], me["声の時給"], avg_all["声の年収"], avg_all["声の時給"],
            f"{me['月の労働時間']}時間", f"{avg_all['月の労働時間']}時間"]
    nums += [r["声の割合"] for r in reasons] + [r["声の割合_丸め"] for r in reasons] + [r["人に1人"] for r in reasons if r["人に1人"]]
    facts = {
        "type": "A", "frame": "A-1", "キー": key, "職業": disp,
        "定義": {
            "辞める理由": "雇用動向調査「転職入職者の前職の離職理由」（第12表。前の勤め先を辞めた理由別の転職入職者の構成比）",
            "割合の母数": f"1年の間に{iv}の事業所へ転職して入った人（転職入職者）{ind['転職入職者数_千人']}千人。割合は、その全員を100%にした値",
            "産業の向き": "産業は「入った先（今の勤め先）」の産業。前の職場は別の産業のこともある。職業ごとの値ではない",
            "順位に入れた項目": "自分から辞めた理由（個人的理由）のうち、中身の分かる9項目。その他の個人的理由・定年や契約期間の満了・会社都合・その他の理由は順位に入れない（参考に置く）",
            "順位": "割合の大きい順。同じ割合は同じ順位",
            "離職率": "雇用動向調査 参考表1。1年の離職者数÷1月1日現在の常用労働者数（%）。産業の数字",
            "年収": "きまって支給する現金給与額×12＋年間賞与その他特別給与額", "時給に直した額": "年収÷（月の労働時間×12）",
            "月の労働時間": "所定内実労働時間数＋超過実労働時間数（1か月）", "賃金の対象": a["meta"]["賃金構造の範囲"],
        },
        "声の前置き": f"{sv}で転職した人が、前の職場を辞めた理由です。",
        "声の前置き_より正確な言い方": f"{sv}に転職してきた人が、前の職場を辞めた理由です。",
        "声の前置きの注意": "手順書 §10 の決まりの文は「声の前置き」。ただし値は「入った先」の産業なので、前の職場が別の業界の人も入る。「〇〇を辞めた理由」とは言わない",
        "業界": {"表の名前": name, "声の名前": sv, "記号": j["産業"], "当てはめの注意": j.get("産業の注意", "職業と産業の結びつきは、このチャンネルの当てはめ（表の上で結びついていない）"),
               "離職率_%": rate, "全産業の離職率_%": all_rate, "差_ポイント": rate_d,
               "声_離職率": f"{say_rate}は{rate}%", "声_全産業との差": f"全産業の{all_rate}%より{rate_d}ポイント高い",
               "A-1にできる": True, "転職入職者数_千人": ind["転職入職者数_千人"]},
        "辞める理由_5つ": order, "辞める理由_順位": [{"順位": rank[x], "理由": SAY[x], "割合_%": pct[x]} for x in items],
        "同じ順位がある": tie, "1位": [r["理由"] for r in first],
        "クイズ": quiz,
        "参考_順位に入れない項目": [{"項目": x, "割合_%": pct[x], "全産業の割合_%": all_pct[x]} for x in REFERENCE],
        "山場": peak,
        "続ける理由": {"使える": False, "理由": "続けたい人の割合・仕事の満足度の統計を、この回の出典に持っていない（手順書 §3：なければ入れない）",
                    "参考_今の勤め先を選んだ理由": {"注意": f"{iv}に転職してきた人が、今の勤め先を選んだ理由。続ける理由ではないので、続ける理由として言わない",
                                          "上位3つ": [{"理由": k, "割合_%": pick[k]} for k in pick_top]}},
        "この職業の数字": me, "全産業の平均": avg_all, "業界の平均": avg_ind,
        "比べ_全産業の平均": vs_all, "比べ_業界の平均": vs_ind,
        "棒グラフ": {"題": f"{disp}と全産業の平均", "棒": [
            {"物差し": "年収_万円", disp: me["年収_万円"], "全産業の平均": avg_all["年収_万円"]},
            {"物差し": "月の労働時間", disp: me["月の労働時間"], "全産業の平均": avg_all["月の労働時間"]},
            {"物差し": "平均年齢", disp: me["年齢"], "全産業の平均": avg_all["年齢"]},
            {"物差し": "勤続年数", disp: me["勤続年数"], "全産業の平均": avg_all["勤続年数"]},
            {"物差し": f"{sv}の離職率_%", "業界": rate, "全産業": all_rate}]},
        "タイトル用": {"職業名": disp, "年収": me["声の年収"], "離職率": f"{sv}の離職率{rate}%",
                    "例": f"{disp}を辞める人が多いのはなぜ｜年収{me['声の年収'].lstrip('約')}・{sv}の離職率{rate}%"},
        "声で言える数字": [n for n in nums if n],
    }
    facts.update(c.sources_block(["chinkin_r7_shokushu", "chinkin_r7_sangyo_t1", "koyodoko_r7_sanko1", "koyodoko_r7_t12"]))
    p = c.write(work, facts)
    print(f"書きました：{p}（{disp}・{sv} 離職率 {rate}%・1位 {facts['1位']}・同じ順位 {'あり' if tie else 'なし'}）")


if __name__ == "__main__":
    args = sys.argv[1:]
    if args[:1] == ["check"]:
        check()
    elif len(args) == 3 and args[0] == "make":
        make(args[1], args[2])
    else:
        print("使い方は先頭のコメントを見てください")

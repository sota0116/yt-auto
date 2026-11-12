# 仕事チャンネル 型C の骨組み C-4「〇〇の一生」（20歳から64歳まで、40年あまりの年収・労働時間）の facts.json を書く（手順書 §3 型C C-4）
#   python -X utf8 pipeline\isshou_facts.py make <作業フォルダ> <キー>      … キーは job_facts_common.JOBS のキー
# ・まず c_facts.py と同じ facts.json を作り（主役・全国平均と並べる表・年齢別・業界・出典）、そこへ「一生」の値を足す
# ・一生の値は、賃金構造 職種 第5表の年齢階級（20～24歳〜60～64歳の9つ。各5年）を足した物：
#     一生の年収＝各年齢階級の年収×5年の合計／一生の労働時間＝各年齢階級の月の労働時間×12か月×5年の合計／一生の時給＝一生の年収÷一生の労働時間
#   全産業の平均（賃金構造 産業大分類 第1表の産業計）も同じ計算で並べる。順位は 9つの年齢階級に値がそろう職業（〇〇の40年の職業）の中で数える
# ・これは「今年の、年齢ごとに別の人たちの平均」を足した数。同じ人が40年働いた記録ではない（声の断り書きは1本で2回まで。手順書 §0）
# ・値の計算はここだけ。Claude は計算しない（手順書 §2・§4）
import json, os, sys
import job_facts_common as c
import c_facts

AGES = ["20～24歳", "25～29歳", "30～34歳", "35～39歳", "40～44歳", "45～49歳", "50～54歳", "55～59歳", "60～64歳"]
SPAN = 5  # 年齢階級1つの年数
CAVEAT = "今年の、年齢ごとに別の人たちの平均を足した数。同じ人が20歳から64歳まで働いた記録ではない（物価・賃上げ・転職も入っていない）"


def voice_big(man_value):
    """万円の値 → 声。1億円以上は100万円の位で丸めて「約1億6000万円」、1億円より下は10万円の位で丸めて「約8350万円」（点検が数字を切り出せるよう、万の前にカンマを入れない）"""
    step = 100 if abs(man_value) >= 10000 else 10
    v = c.rnd(abs(man_value), step)
    oku, rest = divmod(v, 10000)
    if oku:
        return f"約{oku}億{rest}万円" if rest else f"約{oku}億円"
    return f"約{rest}万円"


def voice_hours(h):
    return f"約{c.rnd(h, 100):,}時間"


def lifetime(age_rows, name):
    """年齢階級の行（第5表・第1表の 年齢階級）から一生の値。9つの年齢階級のどれかに値が無い時は None"""
    rows = [age_rows.get(a, {}) for a in AGES]
    if any(r.get("年収_千円") is None or r.get("月の労働時間") is None for r in rows):
        return None
    sen = sum(r["年収_千円"] for r in rows) * SPAN
    hours = sum(r["月の労働時間"] for r in rows) * 12 * SPAN
    yen_h = sen * 1000 / hours
    peak_i = max(range(len(rows)), key=lambda i: rows[i]["年収_千円"])
    first, peak, last = rows[0]["年収_千円"], rows[peak_i]["年収_千円"], rows[-1]["年収_千円"]
    return {"名前": name, "一生の年収_千円": round(sen, 1), "一生の年収_万円": round(sen / 10, 1), "声_一生の年収": voice_big(sen / 10),
            "一生の労働時間": hours, "声_一生の労働時間": voice_hours(hours),
            "一生の時給_円": round(yen_h), "声_一生の時給": c.voice_yen(yen_h),
            "年収がいちばん高い年齢階級": AGES[peak_i], "声_いちばん高い年収": c.voice_man(peak),
            "20～24歳の年収_万円": c.man(first), "声_20～24歳の年収": c.voice_man(first),
            "60～64歳の年収_万円": c.man(last), "声_60～64歳の年収": c.voice_man(last),
            "山までの伸び_倍": round(peak / first, 2), "声_山までの伸び": f"約{round(peak / first, 1)}倍",
            "山から60～64歳への下がり_%": round((peak - last) / peak * 100, 1), "声_山から60～64歳への下がり": c.voice_pct((peak - last) / peak * 100) + "下がる",
            "計算": f"年収＝{AGES[0]}〜{AGES[-1]}の9つの年齢階級の年収×{SPAN}年の合計。労働時間＝月の労働時間×12×{SPAN}の合計。時給＝年収÷労働時間"}


def make(work, key):
    j = c.job(key)
    official, disp = j["職種"][0], j["表示名"]
    a = c.load("a1c_r7.json")
    d = a["data"]
    if official not in d["〇〇の40年の職業"]:
        sys.exit(f"【止まりました】{disp}（{official}）は20～24歳〜60～64歳の年収がそろわないので「一生」の回は作れない（a1c_r7.json の 〇〇の40年の職業）")
    c_facts.make(work, key)  # 主役・全国平均と並べる表・年齢別・業界・出典は型C と同じ物を使う
    p = os.path.join(work, "facts.json")
    facts = json.load(open(p, encoding="utf-8"))

    me = lifetime(d["職種_年齢階級"][official]["年齢階級"], disp)
    avg = lifetime(d["産業別_平均"]["産業計"]["年齢階級"], "全産業の平均（一般労働者）")
    if not me or not avg:
        sys.exit("【止まりました】一生の値を計算できない年齢階級がある")

    # 順位：9つの年齢階級がそろう職業（〇〇の40年の職業）の中で、一生の年収・一生の時給・一生の労働時間（長い順）
    pool = {n: lifetime(d["職種_年齢階級"][n]["年齢階級"], n) for n in d["〇〇の40年の職業"] if n in d["職種_年齢階級"]}
    pool = {n: v for n, v in pool.items() if v}
    rank = lambda f: 1 + sum(1 for v in pool.values() if v[f] > me[f])
    n_pool = len(pool)

    dn = me["一生の年収_千円"] - avg["一生の年収_千円"]
    dh = me["一生の労働時間"] - avg["一生の労働時間"]
    dy = me["一生の時給_円"] - avg["一生の時給_円"]
    w = lambda x, hi, lo: hi if x > 0 else (lo if x < 0 else "同じ")
    diff = {"年収の差_万円": round(dn / 10, 1), "声_年収の差": f"{voice_big(abs(dn) / 10)}{w(dn, '多い', '少ない')}" if dn else "同じ",
            "労働時間の差": dh, "声_労働時間の差": f"{voice_hours(abs(dh))}{w(dh, '長い', '短い')}" if dh else "同じ",
            "声_労働時間の差を日に": f"1日8時間で数えると約{c.rnd(abs(dh) / 8):,}日分{w(dh, '多く働く', '少なく働く')}" if dh else None,
            "時給の差_円": dy, "声_時給の差": f"{c.voice_yen(abs(dy))}{w(dy, '高い', '低い')}" if dy else "同じ",
            "計算": "差は丸める前の値どうしで計算する（声の合計どうしを引いた数とずれることがある。声ではこの差を使う）。日＝時間の差÷8（実際の出勤日数ではない）"}

    old65 = d["職種_年齢階級"][official]["年齢階級"].get("65～69歳", {})
    isshou = {
        "この職業": me, "全産業の平均": avg, "比べ_全産業の平均": diff,
        f"{n_pool}の職業の中の順位": {"一生の年収": rank("一生の年収_千円"), "一生の時給": rank("一生の時給_円"),
                                "一生の労働時間（長い順）": rank("一生の労働時間"),
                                "順位の範囲の言い方": f"20歳から64歳まで年収の値がそろう{n_pool}の職業の中で（タイトル・サムネでは「全職業で」と言わない。範囲の数も書かない）"},
        "参考_65～69歳": {"声の年収": c.voice_man(old65["年収_千円"]), "注意": "一生の合計には入れていない（足すのは20～24歳〜60～64歳）"} if old65.get("年収_千円") is not None else None,
        "注意": CAVEAT,
        "言い方": "「〇〇として40年あまり働くと、今の数字ではこのくらい」と言う。「あなたは一生で〇〇円稼ぐ」「この人は」と、同じ人の記録のように言わない",
    }
    facts["frame"] = "C-4"
    facts["一生"] = isshou
    facts["年齢別_全産業の平均"] = [{"年齢階級": k, "年収_万円": c.man(v["年収_千円"]), "声の年収": c.voice_man(v["年収_千円"]),
                              "月の労働時間": v.get("月の労働時間"), "時給に直した額_円": v.get("時給に直した額_円")}
                             for k, v in d["産業別_平均"]["産業計"]["年齢階級"].items() if v.get("年収_千円") is not None]
    facts["全国平均と並べる表"] += [
        {"物差し": "20〜64歳の年収の合計", disp: me["声_一生の年収"], "全産業の平均": avg["声_一生の年収"], "差": diff["声_年収の差"]},
        {"物差し": "20〜64歳の労働時間の合計", disp: me["声_一生の労働時間"], "全産業の平均": avg["声_一生の労働時間"], "差": diff["声_労働時間の差"]},
        {"物差し": "40年あまりを時給に直すと", disp: me["声_一生の時給"], "全産業の平均": avg["声_一生の時給"], "差": diff["声_時給の差"]}]
    for k in ("C-1", "C-3"):
        facts["骨組み"][k]["使える"] = False
        facts["骨組み"][k]["理由"] = "この回は「一生」（C-4）の題。値は参考に残す"
    facts["骨組み"]["C-4"] = {
        "使える": True,
        "山場": f"一生の年収（{me['声_一生の年収']}）を全産業の平均（{avg['声_一生の年収']}）と並べ、一生の時給（{me['声_一生の時給']}）で言い直す",
        "章の流れ": "20代前半→山（年収がいちばん高い年齢階級）→60代前半の順に年齢を追う。age_line で年収の線を見せ、山場は vs_national の「20〜64歳の年収の合計」",
        "注意": CAVEAT + "。断り書きは前置きか山場で1回言えば足りる（1本で2回まで）"}
    facts["題と統計のずれ"] = "「一生」は統計の言葉ではない。20～24歳〜60～64歳の年齢階級の年収×5年を足した物（" + CAVEAT + "）" + \
        (f"。{facts['題と統計のずれ']}" if facts.get("題と統計のずれ") else "")
    # 「40年」も数字に数えられるので、タイトルの例には入れない（「1億7400万円」は点検で2つに数える。1案に2つまで §6）
    facts["タイトル用"]["例"] = f"{disp}の一生｜20歳から64歳までの年収を足すと{me['声_一生の年収']}"
    facts["タイトル用"]["一生の年収"] = me["声_一生の年収"]
    facts["タイトル用"]["一生の注意"] = "「生涯年収」「一生で稼ぐ」と書く時も、同じ人の記録とは書かない。順位は「全職業で」と言わない（範囲は上の順位の言い方）"
    facts["定義"]["一生の年収"] = me["計算"]
    hours_words = [f"{x}時間" for x in (me["一生の労働時間"], avg["一生の労働時間"], abs(dh))]
    facts["声で言える数字"] += [v for v in (
        me["声_一生の年収"], avg["声_一生の年収"], diff["声_年収の差"], me["声_一生の労働時間"], avg["声_一生の労働時間"],
        diff["声_労働時間の差"], diff["声_労働時間の差を日に"], me["声_一生の時給"], avg["声_一生の時給"], diff["声_時給の差"],
        me["声_いちばん高い年収"], me["声_20～24歳の年収"], me["声_60～64歳の年収"], me["声_山までの伸び"], me["声_山から60～64歳への下がり"],
        "40年", "45年", *hours_words) if v]
    c.write(work, facts)
    print(f"一生を足しました：{disp}・一生の年収 {me['声_一生の年収']}（全産業 {avg['声_一生の年収']}）・一生の時給 {me['声_一生の時給']}"
          f"・{n_pool}職業で年収 {isshou[f'{n_pool}の職業の中の順位']['一生の年収']}位")


if __name__ == "__main__":
    args = sys.argv[1:]
    if len(args) == 3 and args[0] == "make":
        make(args[1], args[2])
    else:
        print("使い方は先頭のコメントを見てください")

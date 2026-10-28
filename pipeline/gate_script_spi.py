# ④台本ゲート（千年こよみ spi・2026-10-29 新設）：形・直近の回との回し方・似すぎ・暦と出典・禁止表現・広告に向くか・続きを見たくなるか
#   python -X utf8 pipeline/gate_script_spi.py <作業フォルダ> [--ch spi]
# ・結果は 作業フォルダ/gate_script.json。不合格の項目があれば終了コード1（write_script_spi.py --fix がこれを読んで直す）
# ・形：スキルの check_script.py --long（注意だけ。記録に残す）と check_spi_script.py（手順書 §4・§7・§11 の機械の点検。NG 0件で合格）
# ・直近の回（手順書 §11）：呼びかけの番号が直近5本で3回以上／数え上げの骨組み（A-2・B-2・C2-2）が直近9本で4本以上 なら不合格。元は history/spi/produced.json
# ・似すぎ：1本目（golden/script_001.json）と history/spi/scripts/ の過去回と比べる（3文字の重なり 0.35 未満・同じ1文目なし）
# ・文脈の判定（暦と出典・禁止表現・広告・続き）は gemini.ask（2026-10-24 から、ふだんは Claude（claude -p・契約の範囲内）。JUDGE=gemini で Gemini）
# ・「続きを見たくなるか」の名前は run_daily.py の record() が点を拾う名前にそろえた（仕事chと同じ）
import argparse, json, os, re, subprocess, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gemini  # noqa: E402
from gate_script import ROOT, ask_json, items, S, trigram, cost  # noqa: E402

CPS = 6.0  # 読む速さ（字/秒）。check_script.py・check_spi_script.py と同じ
SKILL_CHECK = os.path.join(ROOT, "vendor", "youtube-video-maker", "scripts", "check_script.py")
COUNTING = ("A-2", "B-2", "C2-2")  # 数え上げの骨組み（手順書 §3）


def load(work):
    s = json.load(open(os.path.join(work, "script.json"), encoding="utf-8"))
    f = json.load(open(os.path.join(work, "facts.json"), encoding="utf-8"))
    s["all_cuts"] = s["cuts"]
    s["cuts"] = [c for c in s["cuts"] if c.get("narration")]
    return s, f


def chapters(s):
    out, cur = [], None
    for c in s["all_cuts"]:
        if c.get("chapter"):
            cur = {"name": c["chapter"], "cuts": []}
            out.append(cur)
        if cur is None:
            cur = {"name": "つかみ", "cuts": []}
            out.append(cur)
        if c.get("narration"):
            cur["cuts"].append(c)
    return [x for x in out if x["cuts"]]


def screen(c):
    """画面に出る字（カード・写真の札）を短く。点検の材料にする"""
    out = []
    card = c.get("card") or {}
    for k, v in card.items():
        if k in ("type", "src", "video", "seed", "frame"):
            continue
        out.append(f"{k}={json.dumps(v, ensure_ascii=False)}")
    ph = c.get("photo") or {}
    for k in ("pop", "tag", "tag_sub", "tate"):
        if ph.get(k):
            out.append(f"{k}={json.dumps(ph[k], ensure_ascii=False)}")
    t = "；".join(out)
    return f"［画面：{card.get('type', '絵')}{'・' + t[:220] if t else ''}］" if (card or ph) else ""


def lines(cuts, scr=False):
    def one(c):
        who = "聞き手" if c.get("speaker") == "listener" else "語り手"
        era = f"［昔の場面：{c['era']}］" if c.get("era") else ""
        return f"{c['id']}［{who}］{era}{c['narration']}{screen(c) if scr else ''}"
    return "\n".join(one(c) for c in cuts)


def gate_form(work):
    """スキルの点検（注意だけ）と、千年こよみの点検（NG で不合格）"""
    tmp = os.path.join(work, "check", "_skill_tmp")
    os.makedirs(tmp, exist_ok=True)
    s = json.load(open(os.path.join(work, "script.json"), encoding="utf-8"))
    for c in s["cuts"]:  # カードのカットは絵の指示があるものとして渡す（仕事chの check_job_script.py と同じ）
        if c.get("card") and not c.get("image"):
            c["image"] = "（カード）"
    json.dump(s, open(os.path.join(tmp, "script.json"), "w", encoding="utf-8"), ensure_ascii=False)
    k = subprocess.run([sys.executable, "-X", "utf8", SKILL_CHECK, tmp, "--long"], capture_output=True, text=True, encoding="utf-8")
    r = subprocess.run([sys.executable, "-X", "utf8", os.path.join(ROOT, "pipeline", "check_spi_script.py"), work],
                       capture_output=True, text=True, encoding="utf-8")
    ngs = [l for l in r.stdout.splitlines() if l.startswith("NG")]
    return {"合格": r.returncode == 0, "NG": ngs[:20], "出力の最後": r.stdout.strip().splitlines()[-4:],
            "スキルの点検の注意": [l[3:].strip() for l in k.stdout.splitlines() if l.startswith("注意:")]}


def gate_recent(s, ch, work):
    """手順書 §11：直近n本は、ゲートに合格して在庫に入った回を作った順に数える（produced.json）"""
    p = os.path.join(ROOT, "history", ch, "produced.json")
    h = [x for x in (json.load(open(p, encoding="utf-8")) if os.path.exists(p) else []) if x.get("work") != os.path.basename(work)]
    last4, last8 = h[-4:], h[-8:]
    sub_n = sum(1 for x in last4 if x.get("sub_copy") == s.get("sub_copy")) + 1
    cnt_n = sum(1 for x in last8 if x.get("frame") in COUNTING) + (1 if s.get("frame") in COUNTING else 0)
    bad = []
    if sub_n >= 3:
        bad.append(f"登録の呼びかけの番号 {s.get('sub_copy')} が、この回を入れて直近5本で{sub_n}回（3回以上はだめ。§11）")
    if cnt_n > 3:
        bad.append(f"数え上げの骨組み（A-2・B-2・C2-2）が、この回を入れて直近9本で{cnt_n}本（3本まで。§3）")
    return {"合格": not bad, "理由": bad, "数えた回": len(h)}


def gate_fact(s, f, use):
    k = f.get("koyomi") or {}
    p = f"""あなたは暦と神社のしきたりの解説番組（千年こよみ）の事実確認の担当です。下の台本の各文と画面の字を、下の facts.json と照らしてください。
facts.json の "koyomi" は、暦の固定ファイルからプログラムが作った、この回で使ってよい日付・曜日・六曜・選日・重なり・回数の全部です。
"sources" と "quotes" は、書き手が調べた由来・言い伝え・行事の出典です（"kind" が 一次／二次）。

見ること
1. 暦と違う：日付・曜日・六曜・干支・選日の名前・重なり・回数が、"koyomi" と合わない／"koyomi" に無い日付や回数を言い切っている。「最強開運日」を、天赦日と一粒万倍日が重なる日以外に使っている。
2. 出典なしの由来：由来・言い伝え・行事の始まり・時代の話（平安・江戸など）・数・人名・文献名を、sources に無いのに言い切っている。
   二次資料しか無い話を、言い伝えの形（「〜と言い伝えられてきました」「〜とされています」）でなく事実として言い切っている。
   毎日の暮らしの場面の描写・気持ち・問いかけ・誰でも知っている事（お正月に初詣へ行く など）は対象外。
3. 結果の保証と健康の効果：「必ず叶う」「〇万円入る」のような具体的な結果の保証／病気・健康への効果を、語り手が効果として言い切っている
   （「昔から、柚子湯に入ると風邪をひかないと言われてきました」のような由来の言い方は当たらない）。
   「金運を呼ぶと言われてきました」「最強開運日」「やってはいけないこと」のような強い言葉は、このチャンネルでは使ってよい（当たらない）。
4. 章の言い切り：1つの章で、声で言い切る別々の日付か数が2つ以上ある章（画面の表やカレンダーに任せるべき所）。
   曜日・六曜・旧暦の日付は、その日付と合わせて1つに数える。同じ日付・同じ数を言い直すのは1つ。
   題そのものの名前（「三歳・五歳・七歳」の七五三、「一粒万倍日」の万倍 など、行事や吉日の名前に入っている数）と、年の名前（2026年）は数えない。
   決まった文（登録の呼びかけ・LINE の案内）の中の数は数えない。
タイトル・サムネの文字・概要欄も 1〜3 と同じように見る。問題がなければ空の配列を返す。

1〜2 には「重さ」を付ける。
- 重い：暦の値と違う／sources に無い日付・数・人名・文献名を言い切る／二次資料しか無い説を、事実として断定する（「〜が理由です」「〜になりました」）
- 軽い：言い伝えの形（「〜とされています」「〜と言われてきました」）にはなっているが、sources の used_for にそのカットが無い／タイトル・サムネの言い方が少し強い
（台本ゲートは、重いが1つでもあるか、軽いが3つ以上か、3 が1つでもあるか、4 が章の数の半分を超えると不合格。軽いと 4 を無理に探さない）

facts.json の koyomi：
{json.dumps(k, ensure_ascii=False)}
sources：
{json.dumps(f.get('sources', {}), ensure_ascii=False)}
quotes：
{json.dumps(f.get('quotes', []), ensure_ascii=False)}

タイトル3案：{json.dumps(s.get('titles'), ensure_ascii=False)}
サムネの文字：{json.dumps(s.get('thumb'), ensure_ascii=False)}
概要欄：{s.get('desc')}
台本（章ごと。［画面：…］は画面に出る字）：
""" + "\n\n".join(f"【章：{c['name']}】\n" + lines(c["cuts"], True) for c in chapters(s))
    w = {"type": "string", "enum": ["重い", "軽い"]}
    sch = {"type": "object", "properties": {"暦と違う": items(id=S, 文=S, 理由=S, 重さ=w), "出典なしの由来": items(id=S, 文=S, 理由=S, 重さ=w),
                                            "結果の保証と健康の効果": items(id=S, 文=S, 理由=S), "章の言い切り": items(章=S, 言い切った物=S)},
           "required": ["暦と違う", "出典なしの由来", "結果の保証と健康の効果", "章の言い切り"]}
    r = ask_json(p, sch, use)
    # 2026-10-29 の試し（003 七五三）：重さを分けない形だと、直すたびに別の軽い所（言い伝えの形の文の出典の付け方）が出て、
    # 章の言い切りも題の名前の数（三歳・五歳・七歳）まで数えて6章になった。心理chの「軽い言いすぎは3つまで通す」と同じ考えで線を引いた
    xs = r["暦と違う"] + r["出典なしの由来"]
    heavy = [x for x in xs if x.get("重さ") != "軽い"]
    light = [x for x in xs if x.get("重さ") == "軽い"]
    nch = len(chapters(s))
    ok = not heavy and len(light) < 3 and not r["結果の保証と健康の効果"] and len(r["章の言い切り"]) <= nch // 2
    return {"合格": ok, "章の数": nch, **r}


def gate_ng(s, ch, use):
    words = [w.strip() for w in open(os.path.join(ROOT, "channels", ch, "禁止表現.txt"), encoding="utf-8")
             if w.strip() and not w.startswith("#")]
    th = s.get("thumb") or {}
    texts = [(c["id"], c["narration"]) for c in s["cuts"]] + [(f"title{i + 1}", t) for i, t in enumerate(s.get("titles", []))] + \
            [("thumb", "／".join(str(th.get(x) or "") for x in ("top", "big", "tag"))), ("desc", s.get("desc", ""))]
    hits = [{"id": i, "語": w, "文": t} for i, t in texts for w in words if w in t]
    p = f"""YouTube の暦・吉日・しきたりのチャンネル「千年こよみ」（50〜60代の女性が家事の合間に耳で聞く）の台本の点検です。
下の「当たった所」は、禁止表現の一覧と単純に一致した所です。それぞれ、文脈で本当に禁止に当たるかを判定してください。
カギかっこの引用・行事や神社の正式名・資料の名前の中は「当たらない」。

禁止の中身（手順書 §4）
- 具体的な結果の保証（必ず当たる・必ず叶う・〇万円入る・誰でも〜になる）。
- 病気・健康への効果を、語り手が効果として言い切る。健康に関わる言い伝え（風邪をひかない・無病息災・邪気を払う・厄が落ちる・夏バテ・滋養・疲労回復・病気にならない）は、
  「昔から〜と言われてきました」のような由来の言い方なら当たらない。「〜します」「〜になります」と効果を言い切ったら当たる。
- メタ：名乗り／動画や回のこと（この動画・この回・今回・このチャンネル）／進み方の予告と区切り（ここからは・ここまで・この後すぐ・次の章では・見ていきます・紹介します・おさらいです）／お礼。
  ただし、登録の呼びかけ・LINE の案内・締めのコメントへの問いかけの決まった文の中は当たらない。
- 答えを先に延ばすだけの文（最後に言います・このあと発表します・答えは最後の章で・後半でお見せします・最後まで見てください）。
- 時を決める言い方（今日・今夜・今宵）。ただし「今日まで続く」「今日の暦」のような「今の時代」の意味は当たらない。
- 公開の頻度（毎日・明日も）。暮らしの場面の「毎日」（例：毎日神棚に手を合わせる）は当たらない。
- 「ランキング」「人気」（数え上げの順位を人気や効果の順に見せる言い方）。
- 霊感・霊視があると語り手が言う。
- 記号（──・…・※・★・→）。
- 丙午の回：その年に生まれた人の性格・運勢の評価を、語り手が言い伝えの形でなく言っている。
あわせて、一覧に無くても台本の全文を読んで、上の禁止の中身に当たる文があれば足してください。無ければ空の配列。

当たった所：{json.dumps(hits, ensure_ascii=False)}
台本：
{lines(s['cuts'])}
タイトル3案：{json.dumps(s.get('titles'), ensure_ascii=False)}
サムネの文字：{json.dumps(th, ensure_ascii=False)}
概要欄：{s.get('desc')}
"""
    r = ask_json(p, {"type": "object", "properties": {"禁止に当たる": items(id=S, 文=S, 理由=S)}, "required": ["禁止に当たる"]}, use)
    return {"合格": not r["禁止に当たる"], "一致した所": hits, **r}


def gate_ads(s, use):
    p = f"""YouTube の「広告掲載に適したコンテンツのガイドライン」の項目（不適切な言葉・暴力・アダルトなコンテンツ・ショッキングなコンテンツ・有害な行為や危険な行為・憎悪を煽るコンテンツや軽蔑的なコンテンツ・薬物・物議を醸す問題・センシティブな事件・扇情的な表現（あおるタイトルやサムネ））で、下の台本・タイトル・サムネの文字を見てください。
特に、医療・健康の効果を言う所（病気が治る・体がよくなる）と、不幸・災いを強くあおって不安にさせる言い方が無いかを重点的に見てください。
暦・吉日・言い伝え・神社の作法の紹介、「最強開運日」「金運」「やってはいけないこと」のような開運チャンネルでよくある言い方は、それだけでは当てはまりません。広告が限られる見込みが高い所だけを挙げてください。無ければ空の配列。

タイトル3案：{json.dumps(s.get('titles'), ensure_ascii=False)}
サムネの文字：{json.dumps(s.get('thumb'), ensure_ascii=False)}
台本：
{lines(s['cuts'])}
"""
    r = ask_json(p, {"type": "object", "properties": {"当てはまる所": items(id=S, 文=S, 項目=S, 理由=S)}, "required": ["当てはまる所"]}, use)
    return {"合格": not r["当てはまる所"], **r}


def gate_hook(s, use):
    acc, first30 = 0, []
    for c in s["cuts"]:
        if acc / CPS < 30:
            first30.append(c)
        acc += len(re.sub(r"[、。！？「」]", "", c["narration"]))
    body = "\n\n".join(f"【章：{c['name']}】\n" + lines(c["cuts"]) for c in chapters(s))
    p = f"""あなたは YouTube の長尺動画の編集者です。家で家事の合間に、耳だけで聞いている50〜60代の女性（カレンダーに印をつけ、神社にはときどき行く人）として、下の台本を採点してください。
採点（10点満点・整数）
1. 最初の30秒（下の「最初の30秒」）：ここで離脱せず、続きを聞きたくなるか。いちばん驚く日付か由来を言い切っているか。「みんなが思っていること」と暦の計算の結果の食い違いがあるか
2. 各章（台本の【章】ごと。全部の章を採点する）：耳だけで日付と話が分かるか・家で起きそうな「あるある」の場面があるか・章の終わりの1文で、次の章も聞きたくなるか（進み方を言うのではなく、中身で引いているか）
3. 山場（"peak" の付いたカットのあたり。無ければいちばん盛り上がる所）：持ち帰れる事実（日付・由来・やり方）として残るか
このチャンネルの決まりとして、40〜45%あたりに LINE の案内、65%あたりに登録の呼びかけ、締めにコメントへの問いかけの決まった文が入ります。入っていること自体は減点しないでください。
語り口はやわらかい です・ます で、名乗りやお礼のあいさつはしない決まりです。
点が低い所は、どこをどう直すと上がるかを1文で書いてください。具体的な結果の保証・病気や健康の効果・答えを先に延ばすだけの文・動画や回のことを話す言い方を足す案は出さないでください。甘く付けないでください。

最初の30秒：
{lines(first30)}

台本（章ごと）：
{body}
"""
    pt = {"type": "object", "properties": {"点": {"type": "integer"}, "直すなら": S}, "required": ["点", "直すなら"]}
    sch = {"type": "object", "properties": {"最初の30秒": pt, "章": items(章=S, 点={"type": "integer"}, 直すなら=S), "山場": pt},
           "required": ["最初の30秒", "章", "山場"]}
    r = ask_json(p, sch, use)
    ok = r["最初の30秒"]["点"] >= 7 and all(c["点"] >= 5 for c in r["章"]) and r["山場"]["点"] >= 6
    return {"合格": ok, **r}


def gate_similar(s, ch, work):
    me = trigram("".join(c["narration"] for c in s["cuts"]))
    past = [os.path.join(ROOT, "channels", ch, "golden", "script_001.json")]
    sd = os.path.join(ROOT, "history", ch, "scripts")
    past += [os.path.join(sd, n) for n in sorted(os.listdir(sd)) if n.endswith(".json")] if os.path.isdir(sd) else []
    worst, res = 0, []
    for sp in past:
        if os.path.basename(sp)[:-5] == os.path.basename(work) or not os.path.exists(sp):
            continue
        o = [c for c in json.load(open(sp, encoding="utf-8"))["cuts"] if c.get("narration")]
        if not o:
            continue
        rate = len(me & trigram("".join(c["narration"] for c in o))) / max(1, len(me))
        worst = max(worst, rate)
        res.append({"回": os.path.basename(sp), "一致率": round(rate, 3), "同じつかみ": o[0]["narration"] == s["cuts"][0]["narration"]})
    # 決まった文（LINE の案内・登録の呼びかけ・AI の行）は毎回同じなので、0.35 は仕事ch・心理chと同じ線
    return {"合格": worst < 0.35 and not any(r["同じつかみ"] for r in res), "比べた回": res}


def main():
    a = argparse.ArgumentParser()
    a.add_argument("work")
    a.add_argument("--ch", default="spi")
    a = a.parse_args()
    work = os.path.abspath(a.work)
    s, f = load(work)
    use = []
    judge = gemini.TEXT_MODEL if os.environ.get("JUDGE", "claude") == "gemini" else f"claude -p（{os.environ.get('CLAUDE_JUDGE_MODEL', 'sonnet')}）"
    res = {"モデル": judge, "形": gate_form(work), "直近の回との回し方": gate_recent(s, a.ch, work), "似すぎ": gate_similar(s, a.ch, work)}
    if not res["形"]["合格"]:  # 形が落ちた回は、文脈の判定（時間がかかる）を回さずに直しへ回す
        print("（形が不合格なので、文脈の判定は直したあとに回します）")
    else:
        res.update({"暦と出典": gate_fact(s, f, use), "禁止表現": gate_ng(s, a.ch, use), "広告に向くか": gate_ads(s, use),
                    "続きを見たくなるか": gate_hook(s, use)})
    res["お金"] = cost(use)
    res["合格"] = all(v["合格"] for v in res.values() if isinstance(v, dict) and "合格" in v)
    json.dump(res, open(os.path.join(work, "gate_script.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    for k, v in res.items():
        if isinstance(v, dict) and "合格" in v:
            print(f"{k}：{'合格' if v['合格'] else '不合格'}")
            if not v["合格"]:  # クラウドでは作業フォルダが見えないので、落ちた理由をログに残す
                print("  理由：", json.dumps({x: y for x, y in v.items() if x != "合格"}, ensure_ascii=False)[:800])
    print("お金：", res["お金"])
    print("台本ゲート：", "合格" if res["合格"] else "不合格（gate_script.json を見て直す）")
    sys.exit(0 if res["合格"] else 1)


if __name__ == "__main__":
    main()

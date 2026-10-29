# ④台本ゲート（設計書 §5④）：形・事実・似すぎ・文体の偏り・骨組みの偏り・禁止表現・広告に向くか・続きを見たくなるか・押したくなるか
#   python -X utf8 pipeline\gate_script.py <作業フォルダ> [--ch job]
# ・結果は 作業フォルダ\gate_script.json。不合格の項目があれば終了コード1
# ・判定のAI（gemini.py の ask。2026-10-24 からふだんは Claude Sonnet が claude -p で答える）に、事実・禁止表現の文脈・広告・続き・押したくなるかの5つを見せる
# ・押したくなるかは点を記録に残すだけで、合否には使わない（2026-10-29 に競合33組で確かめ、伸びた回を当てられなかった。手順書 v5.2）
# ・似すぎ・偏りは history\<ch>\produced.json の過去回と比べる（1本目は比べる相手がないので合格）
import argparse, json, os, re, subprocess, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gemini

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CPS = 6.0  # 読む速さ（字/秒）。1本目の台本 3,224字・約9.0分から


def speed(ch):
    """声の速さ（profile.json の voicevox.narrator.speed。2026-10-29 から 1.05）。最初の30秒を切る時に掛ける"""
    p = os.path.join(ROOT, "channels", ch, "profile.json")
    return json.load(open(p, encoding="utf-8")).get("voicevox", {}).get("narrator", {}).get("speed", 1.0) if os.path.exists(p) else 1.0


def load(work):
    s = json.load(open(os.path.join(work, "script.json"), encoding="utf-8"))
    f = json.load(open(os.path.join(work, "facts.json"), encoding="utf-8"))
    return s, f


def chapters(s):
    out, cur = [], None
    for c in s["cuts"]:
        if c.get("chapter"):
            cur = {"name": c["chapter"], "cuts": []}
            out.append(cur)
        if cur is None:
            cur = {"name": "つかみ・前置き", "cuts": []}
            out.append(cur)
        cur["cuts"].append(c)
    return out


def lines(cuts, name):
    return "\n".join(f"{c['id']}［{name if c.get('speaker') == 'listener' else 'ミナト'}］{c['narration']}" for c in cuts)


def gate_form(work):
    r = subprocess.run([sys.executable, "-X", "utf8", os.path.join(ROOT, "pipeline", "check_job_script.py"), work],
                       capture_output=True, text=True, encoding="utf-8")
    return {"合格": r.returncode == 0, "出力の最後": r.stdout.strip().splitlines()[-3:]}


def ask_json(prompt, schema, use):
    t, u = gemini.ask(prompt, schema=schema)
    use.append(u)
    return json.loads(t)


def items(**props):
    return {"type": "array", "items": {"type": "object", "properties": props, "required": list(props)}}


S = {"type": "string"}


def thumb_words(s):
    """サムネの字（上の見出し／大きい字／下の帯。手順書 §6 の2026-10-27 からの形）"""
    return "／".join(x for x in (s.get("thumb_top"), s.get("thumb_text"), s.get("thumb_band")) if x)


def gate_fact(s, f, use):
    p = f"""あなたは統計番組の事実確認の担当です。下の台本の各文を、下の facts.json（厚生労働省の統計からプログラムで計算した値。「豆知識」は書き手が公的なページで確かめた決まり・仕組みで、url と原文つき）と照らしてください。

見ること
1. 食い違い：台本の数字・順位・比べ方（上・下・長い・短い・1位・最下位・入れ替わり）が facts.json と合わない文。丸めた言い方（約453万円・約1,910円・約25万円など）は facts.json の「声の〜」「言い直し」の値なら合っているとみなす。
2. 出典なしの断定：facts.json にない数字・年・決まり・統計上の事実を言い切っている文。仕事の中身の一般的な説明（バス運転手は決まった道を走る、など誰でも知っている事）や、数字のない職場の場面描写は対象外。ただし統計の定義（どの職種をどうまとめて数えているか等）は対象で、正しいかを一般知識で判定して「一般に正しいか」に書く（正しい／誤り／不明）。
タイトル・サムネの文字・概要欄も同じように見る。問題がなければ空の配列を返す。

facts.json
{json.dumps(f, ensure_ascii=False)}

タイトル3案：{json.dumps(s['titles'], ensure_ascii=False)}
サムネの文字：{thumb_words(s)}
概要欄：{s['desc']}
台本：
{lines(s['cuts'], s.get('listener_name', '聞き手'))}
"""
    sch = {"type": "object", "properties": {"食い違い": items(id=S, 文=S, 理由=S),
                                            "出典なしの断定": items(id=S, 文=S, 理由=S, 一般に正しいか=S)},
           "required": ["食い違い", "出典なしの断定"]}
    r = ask_json(p, sch, use)
    bad = r["食い違い"] + [x for x in r["出典なしの断定"] if x["一般に正しいか"] != "正しい"]
    return {"合格": not bad, **r}


def gate_ng(s, ch, use):
    words = [w.strip() for w in open(os.path.join(ROOT, "channels", ch, "禁止表現.txt"), encoding="utf-8")
             if w.strip() and not w.startswith("#")]
    texts = [(c["id"], c["narration"]) for c in s["cuts"]] + [(f"title{i+1}", t) for i, t in enumerate(s["titles"])] + \
            [("thumb", thumb_words(s)), ("desc", s["desc"])]
    hits = [{"id": i, "語": w, "文": t} for i, t in texts for w in words if w in t]
    p = f"""YouTube の仕事チャンネルの台本の点検です。下の「当たった所」は、禁止表現の一覧と単純に一致した所です。
それぞれ、文脈で本当に禁止に当たるかを判定してください。カギかっこの引用・統計や制度の正式名の中は「当たらない」。
禁止の中身：特定の人・会社・職業をけなす言い方／男女や世代の対立をあおる言い方／年齢・雇用の形・男女などの人の集団を問題の犯人として名指す言い方／呼びかけ・案内・締めで公開の頻度（毎日・明日も）を言うこと／結果の保証／見る人に見える所の守りの断り書き（架空・フィクション・個別の相談には応じられない、など）／台本のセリフの中のメタな言い方（名乗り・動画や回やチャンネルのこと・「ここからは」「次の章では」「見ていきます」「〇〇の結果です」のような進み方の言葉・聞き手に役を振る言い方・見てくれたお礼。登録の呼びかけ・LINE の案内・コメントへの問いかけの文は当たらない。タイトルと概要欄は対象外）。
職場の場面の描写の中の「毎日」（例：毎日同じ停留所で待つ）は、公開の頻度ではないので当たらない。
あわせて、一覧に無くても台本の全文を読んで、上の禁止の中身に当たる文があれば足してください。無ければ空の配列。

当たった所：{json.dumps(hits, ensure_ascii=False)}
台本：
{lines(s['cuts'], s.get('listener_name', '聞き手'))}
タイトル3案：{json.dumps(s['titles'], ensure_ascii=False)}
"""
    r = ask_json(p, {"type": "object", "properties": {"禁止に当たる": items(id=S, 文=S, 理由=S)}, "required": ["禁止に当たる"]}, use)
    # 登録の呼びかけ・LINE の案内・コメントへの問いかけは、手順書 §4 の決まった文（メタの禁止の例外）。
    # 判定するAIが決まった文の前半をメタと取って3回とも落とした（2026-10-25）ので、そのカットのメタの指摘はここで外す
    fixed = {c["id"] for c in s["cuts"] if re.search("チャンネル登録|LINE|コメント", c["narration"])}
    out = [x for x in r["禁止に当たる"] if not (x["id"] in fixed and "メタ" in x["理由"])]
    if len(out) < len(r["禁止に当たる"]):
        r["外した指摘"] = [x for x in r["禁止に当たる"] if x not in out]
    r["禁止に当たる"] = out
    return {"合格": not out, "一致した所": hits, **r}


def gate_ads(s, use):
    p = f"""YouTube の「広告掲載に適したコンテンツのガイドライン」の項目（不適切な言葉・暴力・アダルトなコンテンツ・ショッキングなコンテンツ・有害な行為や危険な行為・憎悪を煽るコンテンツや軽蔑的なコンテンツ・薬物・銃器・物議を醸す問題・センシティブな事件・扇情的な表現（あおるタイトルやサムネ））で、下の台本・タイトル・サムネの文字を見てください。
特に、ある職業そのものを下げる言い方（その仕事を選んだ人を見下す・やめるべきだと決めつける等）が無いかを重点的に見てください。
数字に基づく比べ（年収・時給の順位）や問いかけの形は、それだけでは当てはまりません。広告が限られる見込みが高い所だけを挙げてください。無ければ空の配列。

タイトル3案：{json.dumps(s['titles'], ensure_ascii=False)}
サムネの文字：{thumb_words(s)}
台本：
{lines(s['cuts'], s.get('listener_name', '聞き手'))}
"""
    r = ask_json(p, {"type": "object", "properties": {"当てはまる所": items(id=S, 文=S, 項目=S, 理由=S)}, "required": ["当てはまる所"]}, use)
    return {"合格": not r["当てはまる所"], **r}


def gate_hook(s, use, ch="job"):
    acc, first30, cps = 0, [], CPS * speed(ch)
    for c in s["cuts"]:
        if acc / cps < 30:
            first30.append(c)
        acc += len(c["narration"])
    name = s.get("listener_name", "聞き手")
    body = "\n\n".join(f"【章：{c['name']}】\n" + lines(c["cuts"], name) for c in chapters(s))
    # 山場は型ごとに違う（A-4 は時給の逆転、D は決め手の統計と採点結果など）。台本で山場の印（strong）を付けたカットを見せる
    peak = [c["id"] for c in s["cuts"] if c.get("strong") and c["id"] != s["cuts"][0]["id"]]
    peak_txt = f"台本で山場の印を付けたカット（{'・'.join(peak)}）" if peak else "この回でいちばん驚く所"
    p = f"""あなたは YouTube の長尺動画の編集者です。見る人は、スマホでショート動画に慣れていて、退屈したら10秒で次の動画に行く20〜50代です。勉強しに来たのではなく、面白いから見て、見終わった時に「へえ、知らなかった」が残れば満足します。その前提で、下の台本を採点してください。
採点（10点満点・整数）
1. 最初の30秒（下の「最初の30秒」）：ここで離脱せず、続きを見たくなるか
2. 各章（台本の【章】ごと。全部の章を採点する）：章の中身の面白さと、章の終わりの1〜2文で次の章も見たくなるか
3. 山場（{peak_txt}）：驚きがあるか。この回の型にない山場（別の回の仕掛け）を求めないでください
減点する所：統計の数字を並べて読むだけの所／数字が続いて覚えきれない所（胃もたれ。1章で金額・割合・順位が3つ以上続くなど）／数字のあとに定義・断り書きが続く所／「へえ」「えっ」と思う所（知らなかった決まりや仕組み・予想が外れる・食い違い）が1つも無い章／聞き手が相づち・同意しかしない所／しんみりした情緒だけの場面が続く所／最初に立てた謎や問いが、最後まで答えられずに終わる回（山場で減点）。
加点する所：最初に立てた1つの謎が章をまたいで追われ、山場で答えが出る所／見る人が自分の場合（自分の時給・自分の会社）に置き換えられる問いと、その答えの出し方がある所／聞き手が予想を言って外れる・本音でツッコむ所／外の人が知らない決まりや仕組み（豆知識）が、話の流れの中で出てくる所。
このチャンネルの決まりとして、台本は名乗り・動画の説明・進み方の予告（「この回は」「ここからは」「次の章では」「見ていきます」など）をせず、中身（数字・場面・問い）だけで進めます。直す案にも、名乗りや進み方の予告を足す案は出さないでください。
LINE の案内と登録の呼びかけも決まった位置に入ります。入っていること自体は減点しないでください。
点が低い所は、どこをどう直すと上がるかを1文で書いてください。甘く付けないでください。

最初の30秒：
{lines(first30, name)}

台本（章ごと）：
{body}
"""
    pt = {"type": "object", "properties": {"点": {"type": "integer"}, "直すなら": S}, "required": ["点", "直すなら"]}
    sch = {"type": "object", "properties": {"最初の30秒": pt, "章": items(章=S, 点={"type": "integer"}, 直すなら=S), "山場": pt},
           "required": ["最初の30秒", "章", "山場"]}
    r = ask_json(p, sch, use)
    ok = r["最初の30秒"]["点"] >= 7 and all(c["点"] >= 5 for c in r["章"])
    return {"合格": ok, **r}


def gate_click(s, use):
    """押したくなるか（手順書 §6）：1案目のタイトルとサムネの字を、一覧で見た人の目で採点する。点は記録だけで、合否には使わない
    2026-10-29 に競合の伸びた回と伸びなかった回の33組で確かめ、伸びた回に高い点が付いたのはタイトル47%・サムネ39%（当てずっぽうで50%）だった"""
    # 型D の「AIに〈出典名〉だけで採点させたら」は競合で伸びた型で、わざと入れている。2026-10-29 の試しで作り方の説明として減点されたので、ここで伝える
    d = "このタイトルの「AIに〈出典名〉だけで採点（検証）させたら」は、このチャンネルが決めて入れている見どころの方法なので、作り方の説明として減点しないでください。\n" if s.get("type") == "D" else ""
    p = f"""あなたは YouTube のサムネとタイトルの担当です。見る人はスマホのおすすめ欄を親指で流している20〜50代で、仕事やお金の話に興味はあるが、勉強したいわけではありません。
下のタイトルとサムネの字（サムネには、その回の人物の驚いた顔の絵が大きく入ります）を1秒見た時に、押したくなるかを10点満点（整数）で採点してください。
減点する所：統計の報告に見える（数字と順位を並べただけ・何の中の何位か考えないと驚けない数字）／数字が多い／出典や作り方の説明（「厚生労働省の統計で」「〜を並べた」）が目立つ／職業名を並べただけ／タイトルとサムネが同じ言葉をくり返している／押した先で何が分かるかが見えない。
加点する所：答えを知りたくなる謎・食い違い／見る人が自分のこと（自分の時給・自分の会社）として気になる問い／「割に合う？」「やめとけ？」のような判定を問う気持ちの言葉／タイトルとサムネで、片方が謎を出し、もう片方が手がかりを出している。
その仕事の人をけなす言い方は、押したくなっても減点してください。甘く付けないでください。点が7点より低い方は、どう直すと上がるかを1文で書いてください（数字を足す案は出さない）。
このチャンネルの決まり：順位（1位・〇位）を言う時は何の中の順位か（「6職種で」など）を付ける。型A・C のタイトルは前の15字に職業名を入れる。型B のタイトルには「平均的な会社」か「統計から作った会社」を入れる。数字は統計にある値だけ。直す案は、この決まりの中で出してください。
{d}
タイトル（1案目）：{s['titles'][0] if s.get('titles') else ''}
サムネの字（上の見出し／大きい字／下の帯）：{thumb_words(s)}
"""
    pt = {"type": "object", "properties": {"点": {"type": "integer"}, "直すなら": S}, "required": ["点", "直すなら"]}
    r = ask_json(p, {"type": "object", "properties": {"タイトル": pt, "サムネ": pt}, "required": ["タイトル", "サムネ"]}, use)
    return {"合格": True, "使い方": "記録だけ（合否と書き直しには使わない。手順書 v5.2）", **r}


def trigram(t):
    t = re.sub(r"\s", "", t)
    return {t[i:i + 3] for i in range(len(t) - 2)}


def gate_similar(s, ch):
    p = os.path.join(ROOT, "history", ch, "produced.json")
    past = json.load(open(p, encoding="utf-8")) if os.path.exists(p) else []
    if not past:
        return {"合格": True, "メモ": "過去の回がまだ無い（1本目）。似すぎ・文体の偏り・骨組みの偏りは比べる相手なし"}
    me = trigram("".join(c["narration"] for c in s["cuts"]))
    worst, res = 0, []
    for x in past:  # 過去の台本は history\<ch>\scripts\<回>.json（セリフだけ。git に入るのでクラウドにもある）、無ければ手元の作業フォルダ
        sp = next((q for q in (os.path.join(ROOT, "history", ch, "scripts", x["work"] + ".json"),
                               os.path.join(ROOT, "channels", ch, "videos", x["work"], "script.json")) if os.path.exists(q)), None)
        if not sp:
            continue
        o = json.load(open(sp, encoding="utf-8"))
        rate = len(me & trigram("".join(c["narration"] for c in o["cuts"]))) / max(1, len(me))
        worst = max(worst, rate)
        res.append({"回": x["work"], "一致率": round(rate, 3), "同じつかみ": o["cuts"][0]["narration"] == s["cuts"][0]["narration"]})
    return {"合格": worst < 0.35 and not any(r["同じつかみ"] for r in res), "比べた回": res}


def cost(use):
    i = sum(u.get("promptTokenCount", 0) for u in use)
    o = sum(u.get("candidatesTokenCount", 0) + u.get("thoughtsTokenCount", 0) for u in use)
    usd = i / 1e6 * 0.50 + o / 1e6 * 3.00  # 推測の単価（Gemini 3.x Flash 相当。月1回の請求確認で直す）
    return {"入力トークン": i, "出力トークン": o, "見積もり_ドル": round(usd, 4), "見積もり_円": round(usd * 155, 1)}


def main():
    a = argparse.ArgumentParser()
    a.add_argument("work")
    a.add_argument("--ch", default="job")
    a = a.parse_args()
    s, f = load(a.work)
    use = []
    res = {"モデル": gemini.TEXT_MODEL, "形": gate_form(a.work), "似すぎ・偏り": gate_similar(s, a.ch),
           "事実": gate_fact(s, f, use), "禁止表現": gate_ng(s, a.ch, use), "広告に向くか": gate_ads(s, use),
           "続きを見たくなるか": gate_hook(s, use, a.ch), "押したくなるか": gate_click(s, use)}
    res["お金"] = cost(use)
    res["合格"] = all(v["合格"] for v in res.values() if isinstance(v, dict) and "合格" in v)
    json.dump(res, open(os.path.join(a.work, "gate_script.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    for k, v in res.items():
        if isinstance(v, dict) and "合格" in v:
            print(f"{k}：{'合格' if v['合格'] else '不合格'}")
            if not v["合格"]:  # クラウドでは作業フォルダが見えないので、落ちた理由をログに残す
                print("  理由：", json.dumps({x: y for x, y in v.items() if x != "合格"}, ensure_ascii=False)[:600])
    print("お金：", res["お金"])
    print("台本ゲート：", "合格" if res["合格"] else "不合格（gate_script.json を見て直す）")
    sys.exit(0 if res["合格"] else 1)


if __name__ == "__main__":
    main()

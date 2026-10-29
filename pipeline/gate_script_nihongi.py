# ④台本ゲート（アナザー日本紀・2026-10-29 新設。千年こよみ gate_script_spi.py と同じ形）
#   python -X utf8 pipeline/gate_script_nihongi.py <作業フォルダ> [--ch nihongi]
# ・結果は 作業フォルダ/gate_script.json。不合格の項目があれば終了コード1（write_script_nihongi.py --fix がこれを読んで直す）
# ・形：動画スキルの check_script.py（--short／--long。NG 0件）＋手順書の数値（ショートは250〜330字・1文27字まで・hook 1行5字2行まで・帯の小さい字10字まで・
#   最後の一言・動く絵2つ以上と見どころ・fiction なら world_rules・概要欄の作り話とAIの行・出どころ付きの facts。横動画は約3100字・95〜110カット前後・章ごとに動く絵）
# ・直近の回：前のショートと同じずらし方でない／『へえ』の主役の史実が過去の回と同じでない／hook・帯の小さい字・題が過去の回と同じでない（手順書 §2・§10）
# ・似すぎ：見本と history/nihongi/scripts/ の過去回と比べる（3文字の重なり 0.35 未満・同じ1文目なし）。横動画は元のショートとは比べない（企画が同じため）
# ・文脈の判定（史実と出どころ・決まりの食い違い・禁止表現・広告に向くか・続きを見たくなるか・電子ゴミ）は gemini.ask（ふだんは Claude（claude -p）。JUDGE=gemini で Gemini）
# ・『続きを見たくなるか』の名前は run_daily.py の record() が点を拾う名前にそろえた
import argparse, json, os, re, subprocess, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gemini  # noqa: E402
from gate_script import ask_json, items, S, trigram, cost  # noqa: E402
from nihongi_common import ROOT, CH, CDIR, HIST, VENDOR, jload, kind_of_work, past_works, FIXED_END, AI_LINE, vendor_ok  # noqa: E402
from pick_neta_nihongi import same_fact  # noqa: E402

CPS = 7.5  # ショートの読む速さ（字/秒。check_script.py と同じ）


def load(work):
    s = json.load(open(os.path.join(work, "script.json"), encoding="utf-8"))
    n = jload(os.path.join(work, "neta.json"), {})
    s["all_cuts"] = s["cuts"]
    s["cuts"] = [c for c in s["cuts"] if c.get("narration")]
    return s, n


def lines(cuts, with_voice=True):
    return "\n".join(f"{c['id']}［{'語り手' if not c.get('voice') else c['voice'] + 'のセリフ'}］{c['narration']}" for c in cuts)


def groups(s, kind):
    """ショートは場面（3〜4カットずつ）、横動画は章"""
    if kind == "long":
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
        return [g for g in out if g["cuts"]]
    cs = s["cuts"]
    k = 4 if len(cs) >= 12 else 3
    return [{"name": f"場面{i // k + 1}", "cuts": cs[i:i + k]} for i in range(0, len(cs), k)]


def gate_form(work, s, n, kind):
    ng, note = [], []
    cuts = s["cuts"]
    bad = vendor_ok()
    if bad:
        return {"合格": False, "NG": [bad]}
    r = subprocess.run([sys.executable, "-X", "utf8", os.path.join(VENDOR, "check_script.py"), work, f"--{kind}"], capture_output=True, text=True, encoding="utf-8")
    ng += [l for l in r.stdout.splitlines() if l.startswith("NG")]
    note += [l[3:].strip() for l in r.stdout.splitlines() if l.startswith("注意:")]
    chars = sum(len(c["narration"]) for c in cuts)
    allc = s["all_cuts"]
    anim = [c["id"] for c in allc if c.get("anim")]
    end = [c["narration"] for c in cuts[-3:]]
    if not any(FIXED_END in x for x in end):
        ng.append(f"NG: 最後の一言「{FIXED_END}コメントで教えて{'ください' if kind == 'long' else ''}。」が最後の3カットに無い")
    d = s.get("desc", "")
    if "AIを使って作っています" not in d:
        ng.append(f"NG: 概要欄に「{AI_LINE}」が無い")
    if "作り話" not in d:
        ng.append("NG: 概要欄に「※〇〇は作り話です」の行が無い（手順書 §4）")
    if not s.get("facts") or not any(re.search(r"https?://|www\.|出どころ|『|資料|報告書", str(f)) for f in s["facts"]):
        ng.append("NG: facts に出どころ（URL か資料名）が付いた史実が無い（手順書 §4）")
    if re.search(r"\{LONG_URL\}|\{CHAPTERS\}", d) and kind == "long":
        note.append("概要欄の {LONG_URL}／{CHAPTERS} が残っている（アップの時に置き換える）")
    for c in allc:
        if c.get("voice") and c["voice"] not in (s.get("voices") or {}):
            ng.append(f"NG: {c['id']} の voice「{c['voice']}」が voices に無い（characters.json の id と voice の番号）")
        if not c.get("image_en") and not c.get("same_as") and not c.get("card"):
            ng.append(f"NG: {c['id']} に image_en（英語の場面）も same_as も無い")
        if c.get("chars"):
            known = (jload(os.path.join(CDIR, "characters", "characters.json"), {}).get("chars") or {})
            if any(k not in known for k in c["chars"]):
                ng.append(f"NG: {c['id']} の chars に characters.json に無い id がある：{c['chars']}")
    if kind == "short":
        if not 240 <= chars <= 345:
            ng.append(f"NG: 字数 {chars} 字（250〜330字・30〜45秒。手順書 §3）")
        long_s = [x for c in cuts for x in re.split(r"(?<=[。！？])", c["narration"]) if len(x.strip()) > 30]
        if long_s:
            ng.append(f"NG: 1文が30字を超える文がある（27字まで）：{long_s[0][:34]}")
        h = (cuts[0].get("hook") or "") if cuts else ""
        if not h or len(h.split("\n")) > 2 or max(len(x) for x in h.split("\n")) > 5:
            ng.append(f"NG: 1カット目の hook「{h}」は1行5字・2行まで")
        bn = s.get("banner") or []
        if len(bn) < 2 or len(bn[1]) > 10:
            ng.append(f"NG: 帯の小さい字「{bn[1:] }」は10字まで（意外な結果）")
        if not allc or not allc[0].get("anim") or len(anim) < 2:
            ng.append("NG: 動く絵（anim: kling）は1カット目と見どころのカットの2つ以上")
        if not any(c.get("peak") and c.get("anim") for c in allc):
            note.append("見どころ（peak）のカットが動く絵（anim）ではない")
    else:
        if not 2700 <= chars <= 4300:
            ng.append(f"NG: 字数 {chars} 字（約3100字・8〜15分）")
        if not 85 <= len(allc) <= 125:
            ng.append(f"NG: カット数 {len(allc)}（95〜110カット前後）")
        chs = [c for c in allc if c.get("chapter")]
        if not 7 <= len(chs) <= 11:
            ng.append(f"NG: 章の数 {len(chs)}（8〜10）")
        t = s.get("thumb") or {}
        if not all(t.get(k) for k in ("top", "big", "bg")) or t["bg"] not in {c["id"] for c in allc}:
            ng.append("NG: thumb に top・big・bg（絵のカットの id）が揃っていない")
        subs = sum("チャンネル登録" in c["narration"] for c in cuts)
        if subs != 1:
            ng.append(f"NG: 登録の呼びかけが {subs} 回（真ん中あたりで軽く1回）")
        if sum(1 for c in allc if c.get("same_as")) > 0.12 * len(allc):
            note.append("絵の使い回しが1割を超えている")
    return {"合格": not ng, "NG": ng[:20], "字数": chars, "カット数": len(allc), "動く絵": anim, "注意": note[:12]}


def gate_recent(s, n, kind, work):
    past = [x for x in past_works() if x["work"] != os.path.basename(work) and x["no"] != n.get("no")]
    shorts = [x for x in past if x["kind"] == "short"]
    bad = []
    if kind == "short":
        last = shorts[-1] if shorts else {}
        if last and n.get("distort") == last.get("distort"):
            bad.append(f"前のショート（{last.get('no')}）と同じずらし方「{n.get('distort')}」（2本続けない。手順書 §2）")
        for x in past:
            if x.get("fact_main") and same_fact(n.get("fact_main"), x.get("fact_main")):
                bad.append(f"『へえ』の主役の史実が過去の回（{x.get('no')}）と同じ（手順書 §2・§10）")
                break
    hd = os.path.join(HIST, "scripts")
    hist = [jload(os.path.join(hd, f), {}) for f in sorted(os.listdir(hd))] if os.path.isdir(hd) else []
    mine_hook = (s["cuts"][0].get("hook") or "").replace("\n", "") if s["cuts"] else ""
    mine_ban = ((s.get("banner") or [None, None]) + [None])[1]
    for h in hist:
        if h.get("kind") != kind or not kind == "short":
            continue
        if mine_hook and (h.get("hook") or "").replace("\n", "") == mine_hook:
            bad.append(f"hook「{mine_hook}」が過去の回と同じ")
        if mine_ban and (h.get("banner") or [None, None])[1:2] == [mine_ban]:
            bad.append(f"帯の小さい字「{mine_ban}」が過去の回と同じ")
        if s.get("title") and h.get("title") == s["title"]:
            bad.append("題が過去の回と同じ")
    return {"合格": not bad, "理由": bad[:6], "数えた回": len(past)}


def gate_similar(s, n, kind, work):
    me = trigram("".join(c["narration"] for c in s["cuts"]))
    past = [os.path.join(CDIR, "golden", "script_short_S010.json" if kind == "short" else "script_long_L002.json")]
    sd = os.path.join(HIST, "scripts")
    src = os.path.basename(n.get("short_script", "")) if kind == "long" else ""
    past += [os.path.join(sd, f) for f in sorted(os.listdir(sd)) if f.endswith(".json") and f != src] if os.path.isdir(sd) else []
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
    return {"合格": worst < 0.35 and not any(r["同じつかみ"] for r in res), "最大": round(worst, 3), "高い回": sorted(res, key=lambda r: -r["一致率"])[:3]}


def gate_fact(s, n, kind, use):
    p = f"""あなたは歴史解説番組の事実確認の担当です。下の台本は『ありえないルールを1つだけ足した、もしも歴史』です。足したルール（作り話）と、本当にあった出来事（史実）を分けて、史実の側だけを点検します。
台本の facts は、書き手が調べた史実と出どころです。

見ること
1. 史実と違う：年・人・場所・出来事・数が、facts の内容や一般に確かな史実と合わない文（ずらしたルールのせいで変わる『作り話の部分』は対象外）。
2. 出どころなし：facts に無い年・数・人名・文献名・出来事を、史実として言い切っている文。誰でも知っている事（織田信長は戦国の武将、など）や、場面の描写・気持ちは対象外。
3. 説・逸話の言い切り：諸説ある話・逸話（「〜と伝わる」「〜といわれる」にすべき物）を、事実として言い切っている文。
4. 作り話と史実の混同：概要欄の「作り話です」の線と、台本で作り話として語っている範囲が合っていない（作り話の部分が史実のように語られている／概要欄に書いてない作り話がある）。
5. 近現代の事件・実在の人の性・病気・民族を笑いの種にしている、昭和の戦争の死者・被害を笑いにしている（手順書 §4）。
重さ：重い＝1・2 で年・人・数が違う／出来事そのものを作っている／5 に当たる。軽い＝3 の言い切りや、言い方が少し強い。
（台本ゲートは、重いが1つでもあるか、軽いが3つ以上あれば不合格）

ずらしたルール：{n.get('企画')}（ずらし方：{n.get('distort')}／時代：{n.get('era')}／史実の主役：{n.get('fact_main')}）
facts：
{json.dumps(s.get('facts'), ensure_ascii=False, indent=1)}
概要欄：{s.get('desc')}
題：{s.get('title')}
台本：
{lines(s['cuts'])}
"""
    w = {"type": "string", "enum": ["重い", "軽い"]}
    sch = {"type": "object", "properties": {"史実と違う": items(id=S, 文=S, 理由=S, 重さ=w), "出どころなし": items(id=S, 文=S, 理由=S, 重さ=w),
                                            "説の言い切り": items(id=S, 文=S, 理由=S), "作り話と史実の混同": items(id=S, 文=S, 理由=S),
                                            "笑いにしてはいけない題材": items(id=S, 文=S, 理由=S)},
           "required": ["史実と違う", "出どころなし", "説の言い切り", "作り話と史実の混同", "笑いにしてはいけない題材"]}
    r = ask_json(p, sch, use)
    xs = r["史実と違う"] + r["出どころなし"]
    heavy = [x for x in xs if x.get("重さ") != "軽い"]
    light = [x for x in xs if x.get("重さ") == "軽い"] + [{"説": x} for x in r["説の言い切り"]]
    ok = not heavy and len(light) < 3 and not r["作り話と史実の混同"] and not r["笑いにしてはいけない題材"]
    return {"合格": ok, **r}


def gate_rules(s, kind, use):
    rules = s.get("world_rules") or []
    terms = s.get("world_terms") or []
    hit = [c for c in s["cuts"] if any(t in c["narration"] for t in terms)] if terms else []
    if not rules:
        return {"合格": False, "理由": ["world_rules が無い"]}
    if not hit:
        return {"合格": True, "照らしたカット": 0}
    p = f"""下の『決まり』は、この動画で足した作り話のルールです（誰に何が見えるか・誰が何を知っているか）。
決まりに関わる言葉が出てくるカットを、1つずつ決まりと照らしてください。見ること
- その文を言う人（語り手か、人物のセリフか）が、決まりの上でそれを見られる／知っているか。見られない人・知らない人が、それを前提に話している文は食い違い。
  （例：数字が見えるのは信長だけ、の決まりで、秀吉が自分の頭の上の数字を知っている前提で答える。信長が自分の頭の上の数字を見る。）
- 語り手の文は、見えない物を『見る人（視聴者）への説明』として言うのはよい。人物の文は、その人が知り得る範囲だけ。
- 決まりが途中で変わっている（見えない人に見えている、知らない人が知っている）文は食い違い。
食い違いが無ければ空の配列を返す。

決まり：
{json.dumps(rules, ensure_ascii=False, indent=1)}
決まりに関わる言葉：{json.dumps(terms, ensure_ascii=False)}
照らすカット（［語り手］か［<人物>のセリフ］）：
{lines(hit)}
"""
    r = ask_json(p, {"type": "object", "properties": {"食い違い": items(id=S, 文=S, 理由=S)}, "required": ["食い違い"]}, use)
    return {"合格": not r["食い違い"], "照らしたカット": len(hit), **r}


def gate_ng(s, use):
    words = [w.strip() for w in open(os.path.join(CDIR, "禁止表現.txt"), encoding="utf-8") if w.strip() and not w.startswith("#")]
    texts = [(c["id"], c["narration"]) for c in s["cuts"]] + [("title", s.get("title", "")), ("desc", s.get("desc", "")),
             ("thumb", "／".join(str(v) for v in (s.get("thumb") or {}).values() if isinstance(v, str))), ("banner", "／".join(s.get("banner") or []))]
    hits = [{"id": i, "語": w, "文": t} for i, t in texts for w in words if w in t]
    p = f"""YouTube の歴史チャンネル「アナザー日本紀」（雑学が好きな人向けの『もしも歴史』のショート・横動画）の台本の点検です。
下の『当たった所』は、禁止表現の一覧と単純に一致した所です。それぞれ、文脈で本当に禁止に当たるかを判定してください。人物のセリフの中・史料や固有名詞（人名・地名・書名）の中は『当たらない』。

禁止の中身（手順書 §3・§4・§10）
- 中身の無い引っ張り（答えは最後に・このあと発表・最後まで見て）。問いだけを出すのはよい。横動画へつなぐ導線の文（続きは〇月〇日のロング動画で）は残してよい。
- 名乗り・メタ（この動画では・今回は・ここからは・次の章では・見ていきます・紹介します・おさらいです・あいさつ）。
- 時を決める言い方（今夜・今日・今宵・この夜・明日）。ただし『今日まで続く』のような『今の時代』の意味は当たらない。
- 史実のように言い切れない説・逸話を言い切る（間違いなく・真実は・教科書は隠した）。
- 具体的な結果の保証や、効果の約束。
- 昭和の戦争の死者・被害を笑いにする、実在の人の性・病気・民族を笑いの種にする、今も遺族や関係者がいる近現代の事件。
一覧に無くても、台本の全文を読んで当たる文があれば足してください。無ければ空の配列。

当たった所：{json.dumps(hits, ensure_ascii=False)}
台本：
{lines(s['cuts'])}
題：{s.get('title')}／帯：{s.get('banner')}／サムネ：{s.get('thumb')}
概要欄：{s.get('desc')}
"""
    r = ask_json(p, {"type": "object", "properties": {"禁止に当たる": items(id=S, 文=S, 理由=S)}, "required": ["禁止に当たる"]}, use)
    return {"合格": not r["禁止に当たる"], "一致した所": hits[:20], **r}


def gate_ads(s, use):
    p = f"""YouTube の『広告掲載に適したコンテンツのガイドライン』の項目（不適切な言葉・暴力・ショッキングなコンテンツ・有害な行為や危険な行為・憎悪を煽るコンテンツや軽蔑的なコンテンツ・物議を醸す問題・センシティブな事件・扇情的なタイトルやサムネ）で、下の台本・題・帯・サムネの文字を見てください。
歴史の戦い・政変・病気の歴史を事実として扱うこと、『もしも』の作り話は、それだけでは当てはまりません。血・遺体・拷問・差別・戦争の死者を笑いにする描き方や言葉、広告が限られる見込みが高い所だけを挙げてください。無ければ空の配列。
題：{s.get('title')}／帯：{s.get('banner')}／サムネ：{s.get('thumb')}
台本：
{lines(s['cuts'])}
"""
    r = ask_json(p, {"type": "object", "properties": {"当てはまる所": items(id=S, 文=S, 項目=S, 理由=S)}, "required": ["当てはまる所"]}, use)
    return {"合格": not r["当てはまる所"], **r}


def gate_hook(s, kind, use):
    acc, first = 0, []
    for c in s["cuts"]:
        if acc / (7.5 if kind == "short" else 6.0) < (3 if kind == "short" else 30):
            first.append(c)
        acc += len(re.sub(r"[、。！？「」]", "", c["narration"]))
    first = first or s["cuts"][:2]
    gs = groups(s, kind)
    body = "\n\n".join(f"【{g['name']}】\n" + lines(g["cuts"]) for g in gs)
    unit = "場面" if kind == "short" else "章"
    p = f"""あなたは YouTube の{'ショート（30〜45秒）' if kind == 'short' else '横動画（約8〜10分）'}の編集者です。雑学が好きで、見終わったあと『へえ』と言いたい人として、下の台本を採点してください。教科書の名前を少し覚えている程度の知識の人です。
採点（10点満点・整数。甘く付けない）
1. 最初の{'3秒（hook と最初の1文）' if kind == 'short' else '30秒'}：ここで離脱せず、続きを見たくなるか。何をずらしたかが1文で分かるか。説明が要る設定になっていないか
2. 各{unit}（台本の【{unit}】ごと。全部を採点する）：本当にあった出来事（年・人・場所）が『へえ』として残るか・画面が変わる{'テンポ' if kind == 'short' else '場面'}があるか・{unit}の終わりで次も見たくなるか（『答えは最後に』のような先送りではなく、中身で引いているか）
3. 山場（"peak" の付いたカットのあたり）：いちばん面白い場面として、ずらしたルールのせいで史実が少しだけひっくり返るのが伝わるか。持ち帰れる『へえ』が残るか
このチャンネルの決まりとして、最後は『あなたなら、どこで歴史を変える？コメントで教えて。』の決まった一言で終わります。入っていること自体は減点しないでください。名乗り・あいさつはしない決まりです。
点が低い所は、どこをどう直すと上がるかを1文で書いてください。中身の無い引っ張り・メタな言い方・評価の植え付け（『あなたも〇〇ですよね』）を足す案は出さないでください。

最初の{'3秒' if kind == 'short' else '30秒'}：
{lines(first)}

台本（{unit}ごと）：
{body}
"""
    pt = {"type": "object", "properties": {"点": {"type": "integer"}, "直すなら": S}, "required": ["点", "直すなら"]}
    sch = {"type": "object", "properties": {"最初の30秒": pt, "章": items(章=S, 点={"type": "integer"}, 直すなら=S), "山場": pt}, "required": ["最初の30秒", "章", "山場"]}
    r = ask_json(p, sch, use)
    ok = r["最初の30秒"]["点"] >= 7 and all(c["点"] >= 5 for c in r["章"]) and r["山場"]["点"] >= 6
    return {"合格": ok, **r}


def gate_trash(s, n, kind, use, work):
    # 作り途中のこの回（videos/ の neta.json）も past_works に入るので外す。外さないと自分と比べて「前の回と同じ」で落ちる（L101。2026-10-29）
    past = [x for x in past_works() if x["kind"] == kind and x["work"] != os.path.basename(work) and x["no"] != n.get("no")][-6:]
    p = f"""下の台本が『電子ゴミ』（手順書 §10）の線に当たらないかを判定します。当たる物は出さずに直します。
1. 持ち帰れる『へえ』が無い：どの{'場面' if kind == 'short' else '章'}にも、本当にあった出来事（年・人・場所）が1つ入っているか。入っていない{'場面' if kind == 'short' else '章'}を挙げる。
2. 道具を置くだけ：足したルールを置いたあと、史実の何が変わった／何が見えたかまで言えているか。置いただけで終わっているなら挙げる。
3. 前の回との重なり：下の直近の回と、ずらし方・『へえ』の主役の史実・オチの形が言い換えただけで同じなら挙げる。
4. 中身の無い引っ張り：『答えは最後に』『最後まで見て』のような、中身の無い先送りの文。
当たる物が無ければ空の配列。

この回：{n.get('企画')}（{n.get('distort')}／{n.get('era')}／{n.get('fact_main')}）
直近の回：{json.dumps([{k: x.get(k) for k in ('no', '企画', 'distort', 'fact_main')} for x in past], ensure_ascii=False)}
台本：
{lines(s['cuts'])}
"""
    r = ask_json(p, {"type": "object", "properties": {"当たる": items(線=S, 場所=S, 理由=S)}, "required": ["当たる"]}, use)
    return {"合格": not r["当たる"], **r}


def main():
    a = argparse.ArgumentParser()
    a.add_argument("work")
    a.add_argument("--ch", default=CH)
    a = a.parse_args()
    work = os.path.abspath(a.work)
    kind = kind_of_work(work)
    s, n = load(work)
    use = []
    judge = gemini.TEXT_MODEL if os.environ.get("JUDGE", "claude") == "gemini" else f"claude -p（{os.environ.get('CLAUDE_JUDGE_MODEL', 'sonnet')}）"
    res = {"モデル": judge, "種類": kind, "形": gate_form(work, s, n, kind), "直近の回との回し方": gate_recent(s, n, kind, work),
           "似すぎ": gate_similar(s, n, kind, work)}
    if not res["形"]["合格"]:  # 形が落ちた回は、文脈の判定（時間がかかる）を回さずに直しへ回す
        print("（形が不合格なので、文脈の判定は直したあとに回します）")
    else:
        res.update({"史実と出どころ": gate_fact(s, n, kind, use), "決まりの食い違い": gate_rules(s, kind, use), "禁止表現": gate_ng(s, use),
                    "広告に向くか": gate_ads(s, use), "続きを見たくなるか": gate_hook(s, kind, use), "電子ゴミの線": gate_trash(s, n, kind, use, work)})
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

# ④台本ゲート（心理学ch・2026-10-27 新設）：形・研究と合っているか・似すぎ・禁止表現・広告に向くか・続きを見たくなるか
#   python -X utf8 pipeline\gate_script_psy.py <作業フォルダ> [--ch psy]
# ・結果は 作業フォルダ\gate_script.json。不合格の項目があれば終了コード1（write_script_psy.py --fix がこれを読んで直す）
# ・Gemini（書いた Claude と別の会社のAI）に、研究・禁止表現の文脈・広告・続きの4つを見せる。部品は gate_script.py のものを使う
# ・似すぎは、1本目（golden\script_001.json）と history\psy\scripts\ の過去回と比べる
# ・THUMB（サムネの背景のカット）は語りが無いので、語りを見る所では外す
# ・『続きを見たくなるか』の名前は run_daily.py の record() が点を拾う名前にそろえた（2026-10-29 まで「続きを聞きたくなるか」で拾われていなかった）
import argparse, json, os, re, subprocess, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gemini  # noqa: E402
from gate_script import ROOT, ask_json, items, S, trigram, cost  # noqa: E402

CPS = 5.15  # 読む速さ（字/秒）。1本目 5,254字（句読点を除く）・17分01秒から


def load(work):
    s = json.load(open(os.path.join(work, "script.json"), encoding="utf-8"))
    f = json.load(open(os.path.join(work, "facts.json"), encoding="utf-8"))
    s["cuts"] = [c for c in s["cuts"] if c.get("narration")]
    return s, f


def chapters(s):
    out, cur = [], None
    for c in s["cuts"]:
        if c.get("chapter"):
            cur = {"name": c["chapter"], "cuts": []}
            out.append(cur)
        if cur is None:
            cur = {"name": "つかみ", "cuts": []}
            out.append(cur)
        cur["cuts"].append(c)
    return out


def lines(cuts):
    return "\n".join(f"{c['id']}{'［' + c['study'] + '］' if c.get('study') else ''} {c['narration']}" for c in cuts)


def gate_form(work):
    r = subprocess.run([sys.executable, "-X", "utf8", os.path.join(ROOT, "pipeline", "check_psy_script.py"), work],
                       capture_output=True, text=True, encoding="utf-8")
    return {"合格": r.returncode == 0, "出力の最後": r.stdout.strip().splitlines()[-4:]}


def gate_fact(s, f, use):
    p = f"""あなたは心理学の解説番組の事実確認の担当です。下の台本の各文を、下の facts.json（書き手が調べた研究と「台本で言ってよい範囲 may_say」）と照らしてください。
台本の行の頭の［S1］は、その文が facts.json のどの研究の話かの印です。

見ること
1. 言いすぎ：研究の話の文が、その研究の may_say より強く言っている（観察研究を「〇〇すると△△になる」と因果で言う・対象の人を広げる・数字を変える・not_say に当たる）。
2. 出典なしの断定：facts.json に無い研究・数字・「研究で分かっている」「〜という報告があります」を言い切っている文。毎日の場面の描写・気持ちの言い換え・誰でも知っている事は対象外。
3. 医療・効果の約束：病気の名前・治る・予防・薬・受診をすすめる・効果を約束する文。研究の結果を「やれば必ず〜」と言う文。
タイトル・サムネの文字・概要欄も同じように見る。問題がなければ空の配列を返す。
このチャンネルの型（手順書 §3・§6）：「〇〇な人の意外な特徴」「〇〇な人に共通するN個の特徴」「〇〇な人、実は〇〇です」は、〇〇の場面にいる人について研究で分かった傾向を並べる番組の型。題・予告の文・「〇つ目の特徴は」の文がこの型で言うこと自体は、言いすぎに当たらない（2026-10-29 005 で、型そのものを重いと付けて3回落ちた）。見るのは中身：特徴の章の研究の文と締めの文が、その研究の may_say・調べた人の範囲を超えている時（数字を変える・因果にする・調べていない年代や条件に広げる・傾向を「必ず」「みんな」と言い切る）だけを言いすぎにする。

言いすぎには「重さ」を付ける。
- 重い：研究の結果とちがう／観察研究を因果で言う／調べていない人（年代・国・条件）に広げる／facts.json に無い数字・変えた数字／not_say に当たる
- 軽い：結果は合っているが、言い方が少し強い（「はっきり」「〜が分かった」の強さ・「かもしれない」が無い程度）
（台本ゲートは、重いが1つでもあるか、軽いが4つ以上で不合格。軽いを無理に探さない）

facts.json
{json.dumps(f, ensure_ascii=False)}

タイトル3案：{json.dumps(s.get('titles'), ensure_ascii=False)}
サムネの文字：{json.dumps(s.get('thumb'), ensure_ascii=False)}
概要欄：{s.get('desc')}
台本：
{lines(s['cuts'])}
"""
    sch = {"type": "object", "properties": {"言いすぎ": items(id=S, 文=S, 理由=S, 重さ={"type": "string", "enum": ["重い", "軽い"]}),
                                            "出典なしの断定": items(id=S, 文=S, 理由=S), "医療・効果の約束": items(id=S, 文=S, 理由=S)},
           "required": ["言いすぎ", "出典なしの断定", "医療・効果の約束"]}
    r = ask_json(p, sch, use)
    # 軽い言いすぎ（結果は合っていて言い方が少し強いだけ）は3つまで通す。直すたびに別の軽い所が出て、3回で飛ばされるのを防ぐ（2026-10-27 の試しで起きた）
    heavy = [x for x in r["言いすぎ"] if x.get("重さ") != "軽い"]
    light = [x for x in r["言いすぎ"] if x.get("重さ") == "軽い"]
    return {"合格": not (heavy or len(light) > 3 or r["出典なしの断定"] or r["医療・効果の約束"]), **r}


DISCLAIMER = "この動画は、心理学の研究をもとにした一般的なお話です。医療・診断・治療を目的としたものではありません。"


def gate_ng(s, ch, use):
    words = [w.strip() for w in open(os.path.join(ROOT, "channels", ch, "禁止表現.txt"), encoding="utf-8")
             if w.strip() and not w.startswith("#")]
    th = lambda k: "".join(t for line in (s.get("thumb") or {}).get(k) or [] for t, _ in line)
    shs = [s.get("short") or {}] + list(s.get("extra_shorts") or [])  # 2本目からのショート（extra_shorts。2026-10-29）も見る
    texts = [(c["id"], c["narration"]) for c in s["cuts"]] + [(f"title{i+1}", t) for i, t in enumerate(s.get("titles", []))] + \
            [("thumb", th("lines")), ("thumb_b", th("lines_b")), ("desc", s.get("desc", "").replace(DISCLAIMER, ""))] + \
            [x for j, sh in enumerate(shs) for x in [(f"short{j + 1}_title", sh.get("title", ""))] +
             [(f"short{j + 1}_{c.get('id', 'S')}", c.get("narration", "")) for c in sh.get("cuts", [])]]
    # 手順書 §7 の決まった断り書きの「治療」は当たらない。サムネB案・ショートも見る（2026-10-28 002 で題とサムネに「怠けではない」が残った）
    hits =[{"id": i, "語": w, "文": t} for i, t in texts for w in words if w in t]
    p = f"""YouTube の心理学チャンネル（50〜70代の女性向け・夜にひとりで聞く）の台本の点検です。下の「当たった所」は、禁止表現の一覧と単純に一致した所です。
それぞれ、文脈で本当に禁止に当たるかを判定してください。カギかっこの引用・研究や制度の正式名の中は「当たらない」。
禁止の中身：病気の診断・治し方・薬・受診のすすめ／効果の約束（必ず・誰でも・人生が変わる）／見る人の内面に点をつける言い方（あなたは悪くない・そのままでいい・頑張ってきた証・自分を責めなくていい など、見る人の心を評価する言い方。「怠けではない」「甘えじゃない」のように見る人の行いを打ち消して許す言い方も当たる）／中身の無い抽象語（道のり・輪郭・光が差す・心を整える・本当の自分）／占い・スピの言葉（波動・運気・魂など）／時を決める言い方（今夜・今日は）／公開の頻度（毎日・明日も）／人や世代・男女をけなす・対立をあおる言い方／記号（──・…・※・★・→）。
毎日の場面の描写の中の「毎日」（例：毎日同じ道を散歩する）は、公開の頻度ではないので当たらない。研究の説明の中の「必ずしも〜ない」も当たらない。
特徴を「やさしすぎる人」「頑張り屋」「繊細な人」のような人柄の点数で言い切る文も、見る人の内面に点をつける言い方に当たる。行い・頭の中で起きていること・研究の結果で言う特徴（例：眠っている間に昼の出来事を片づけ直している）は当たらない。
あわせて、一覧に無くても台本の全文を読んで、上の禁止の中身に当たる文があれば足してください。無ければ空の配列。

当たった所：{json.dumps(hits, ensure_ascii=False)}
台本：
{lines(s['cuts'])}
タイトル3案：{json.dumps(s.get('titles'), ensure_ascii=False)}
サムネの文字（A案・B案）：{th("lines")}／{th("lines_b")}
ショート：{json.dumps([{"title": x.get("title"), "語り": [c.get("narration") for c in x.get("cuts", [])]} for x in shs], ensure_ascii=False)}
"""
    r = ask_json(p, {"type": "object", "properties": {"禁止に当たる": items(id=S, 文=S, 理由=S)}, "required": ["禁止に当たる"]}, use)
    return {"合格": not r["禁止に当たる"], "一致した所": hits, **r}


def gate_ads(s, use):
    p = f"""YouTube の「広告掲載に適したコンテンツのガイドライン」の項目（不適切な言葉・暴力・アダルトなコンテンツ・ショッキングなコンテンツ・有害な行為や危険な行為・憎悪を煽るコンテンツや軽蔑的なコンテンツ・薬物・物議を醸す問題・センシティブな事件・扇情的な表現（あおるタイトルやサムネ））で、下の台本・タイトル・サムネの文字を見てください。
特に、AIの語り手による医療・健康の助言（病気・薬・治療・心の病の話）と、死・孤独を強くあおる言い方が無いかを重点的に見てください。
研究の結果の紹介や問いかけの形は、それだけでは当てはまりません。
「〇〇な人の意外な特徴」「〇〇な人の正体」「実は〇〇です」「恐ろしい特徴」のような、このジャンルで普通の題の言い方は、本編でそれに見合う研究の話をしていれば扇情には当たりません（本編と関係のない、怖がらせるだけの言い方は当たる）。
広告が限られる見込みが高い所だけを挙げてください。無ければ空の配列。

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
    p = f"""あなたは YouTube の長尺動画の編集者です。家事をしながら耳で聞いている60代の女性として、下の台本を採点してください。
この人は勉強をしに来たのではありません。「へぇ」「これ、私のことだ」「人に話したい」が無いと、退屈してすぐ次の動画へ行きます。研究の結果を順に並べるだけの講義になっている所は、正しくても低く付けてください。
採点（10点満点・整数）
1. 最初の30秒（下の「最初の30秒」）：ここで離脱せず、続きを見たくなるか。自分の毎日の場面か。思い込みがひっくり返りそうで、答えが気になるか
2. 各章（台本の【章】ごと。全部の章を採点する）：自分のことだと思える場面があるか・研究の話が人の出てくる物語になっていて、驚く数字か意外な結果があるか・たとえで耳だけで分かるか・次の章も見たくなるか
3. 全体：最後まで楽しく見られるか。後ろの特徴ほど意外になっているか。見終わったあとに人に話したい事が1つ以上残るか
このチャンネルの決まりとして、つかみに「そんな経験は、ありませんか？」の問いと「今回は、〇〇な人に共通する、N個の特徴を〜」の予告、特徴の章の頭に「〇つ目の特徴は、〇〇です。」、
まとめに登録の呼びかけと決まった挨拶が入ります。入っていること自体は減点しないでください。語り口はゆっくりで、やさしく話しかける形です。
点が低い所は、どこをどう直すと上がるかを1文で書いてください。病気・治し方・効果の約束を足す案、facts.json に無い数字や研究を足す案は出さないでください。甘く付けないでください。

最初の30秒：
{lines(first30)}

台本（章ごと）：
{body}
"""
    pt = {"type": "object", "properties": {"点": {"type": "integer"}, "直すなら": S}, "required": ["点", "直すなら"]}
    sch = {"type": "object", "properties": {"最初の30秒": pt, "章": items(章=S, 点={"type": "integer"}, 直すなら=S), "全体": pt},
           "required": ["最初の30秒", "章", "全体"]}
    r = ask_json(p, sch, use)
    # 2026-10-29：各章 5→6・全体 7 を足した（「最後まで楽しく見られる」を線にする。本人の指摘）
    ok = r["最初の30秒"]["点"] >= 7 and all(c["点"] >= 6 for c in r["章"]) and r["全体"]["点"] >= 7
    return {"合格": ok, **r}


def gate_similar(s, ch, work):
    me_txt = "".join(c["narration"] for c in s["cuts"])
    me = trigram(me_txt)
    past = [os.path.join(ROOT, "channels", ch, "golden", "script_001.json")]
    sd = os.path.join(ROOT, "history", ch, "scripts")
    past += [os.path.join(sd, n) for n in sorted(os.listdir(sd))] if os.path.isdir(sd) else []
    worst, res = 0, []
    for sp in past:
        if os.path.basename(sp)[:-5] == os.path.basename(work):
            continue
        o = [c for c in json.load(open(sp, encoding="utf-8"))["cuts"] if c.get("narration")]
        rate = len(me & trigram("".join(c["narration"] for c in o))) / max(1, len(me))
        worst = max(worst, rate)
        res.append({"回": os.path.basename(sp), "一致率": round(rate, 3), "同じつかみ": o[0]["narration"] == s["cuts"][0]["narration"]})
    # 決まった文（つかみの問いと予告・「〇つ目の特徴は」・登録の呼びかけ・締め）は毎回同じなので、0.35 は仕事chと同じ線のまま様子を見る
    return {"合格": worst < 0.35 and not any(r["同じつかみ"] for r in res), "比べた回": res}


def main():
    a = argparse.ArgumentParser()
    a.add_argument("work")
    a.add_argument("--ch", default="psy")
    a = a.parse_args()
    s, f = load(a.work)
    use = []
    res = {"モデル": gemini.TEXT_MODEL, "形": gate_form(a.work), "似すぎ": gate_similar(s, a.ch, a.work),
           "研究と合っているか": gate_fact(s, f, use), "禁止表現": gate_ng(s, a.ch, use), "広告に向くか": gate_ads(s, use),
           "続きを見たくなるか": gate_hook(s, use)}
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

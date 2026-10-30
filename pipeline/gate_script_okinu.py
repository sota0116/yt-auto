# ④台本ゲート（金運おきぬ・2026-10-29 新設／2026-10-30 制作ルール v1.7 に合わせて更新）：形・直近の回との重なり・言い伝えの確かさ・禁止表現・広告に向くか・続きを見たくなるか
#   python -X utf8 pipeline/gate_script_okinu.py <作業フォルダ> [--ch okinu]
# ・結果は 作業フォルダ/gate_script.json。不合格の項目があれば終了コード1（write_script_okinu.py --fix がこれを読んで直す）
# ・形：check_okinu_script.py（ショートの型の表・手順書の機械の点検・スキルの check_script.py）。NG 0件で合格
# ・似すぎ（手順書 §12 の2）：見本（golden）・手で作った回（OneDrive）・history/okinu/scripts/ の過去回と比べる。3文字の重なり 0.35 未満・
#   同じ1文目なし・同じ最初の文字（hook）なし・同じ題なし。切り出しは元の長尺の文と重なるのが前提なので、長尺は相手から外す
#   長尺（順位の型）は線を 0.45 に上げる：手で作った 003〜006 の組ごとの 3文字の重なりを測ると 0.308〜0.369（最大 004→006 の 0.368／006→004 の 0.363／005→004 の 0.369）。
#   同じ型（第5位〜第1位・直し方・まとめ）の決まり文句が重なる分で、0.35 のままだと手で作った回同士が不合格になる。0.45 は最大値に 0.08 の余裕を足した線
#   （001v6・002 との重なりは 0.18〜0.33。作業中の 007 捨てる物 と 006 は 0.384）。同じ1文目・同じ題・同じ最初の文字は長尺でも不合格のまま。作業フォルダ自身と同じ番号の回（006 と long_006 と history の 006）は相手から外す
# ・v1.7：題・サムネ・番号カードの判定語（破産・貧乏神・お金が逃げる 等）は本人の方針で使う＝それだけでは不合格にしない（gate_fact・gate_ads・gate_ng）。本文の効果の言い切りと保証は従来どおり見る
# ・文脈の判定（言い伝え・禁止表現・広告・続きを見たくなるか・電子ゴミの線）は gemini.ask（ふだんは Claude の claude -p。JUDGE=gemini で Gemini）
# ・「続きを見たくなるか」の名前と中身（最初の30秒・章・山場の点）は run_daily.py の record() が点を拾う名前にそろえた
import argparse, glob, json, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gemini  # noqa: E402,F401
from gate_script import ROOT, ask_json, items, S, trigram, cost  # noqa: E402
import check_okinu_script as CK  # noqa: E402

CPS = 6.0
SIM_LINE = {"long": 0.45, "short": 0.35, "cut": 0.35}  # 3文字の重なりの線（長尺は上の測定値から 0.45）
HAND_DIR = os.environ.get("OKINU_HAND_DIR", r"C:\Users\koneb\OneDrive\YouTube自動チャンネル\金運おきぬ\videos")


def load(work):
    s = json.load(open(os.path.join(work, "script.json"), encoding="utf-8"))
    f = json.load(open(os.path.join(work, "facts.json"), encoding="utf-8")) if os.path.exists(os.path.join(work, "facts.json")) else {}
    n = json.load(open(os.path.join(work, "neta.json"), encoding="utf-8")) if os.path.exists(os.path.join(work, "neta.json")) else {}
    return s, f, n


def lines(s):
    return "\n".join(f"{c['id']}［{'おきぬ' if not c.get('voice') else c['voice']}］{c['narration']}" for c in s["cuts"] if c.get("narration"))


def gate_form(work):
    kind, ng, warn, info = CK.check(work)
    return {"合格": not ng, "種類": kind, "NG": ng[:25], "注意": warn[:10], **info}


def prior_scripts(ch, work, kind):
    out = []
    for p in sorted(glob.glob(os.path.join(ROOT, "channels", ch, "golden", "*.json"))):
        out.append((os.path.basename(p), p))
    for base in (HAND_DIR, os.path.join(ROOT, "history", ch, "scripts")):
        if os.path.isdir(base):
            for p in sorted(glob.glob(os.path.join(base, "*", "script.json")) + glob.glob(os.path.join(base, "*.json"))):
                out.append((os.path.basename(os.path.dirname(p)) if p.endswith("script.json") else os.path.basename(p)[:-5], p))
    me = CK.num_of(work)
    return [(n, p) for n, p in out if n != os.path.basename(work) and CK.num_of(n) != me]  # 同じ番号の回（見本 long_006・history の写し）は外す


def gate_similar(s, n, ch, work):
    me_cuts = [c for c in s["cuts"] if c.get("narration")]
    me = trigram("".join(c["narration"] for c in me_cuts))
    hook = next((c["hook"] for c in s["cuts"] if c.get("hook")), "")
    res, worst = [], 0
    for name, p in prior_scripts(ch, work, n.get("kind")):
        try:
            o = json.load(open(p, encoding="utf-8"))
        except Exception:
            continue
        oc = [c for c in o.get("cuts", []) if c.get("narration")]
        if not oc:
            continue
        if n.get("kind") == "cut" and (name == n.get("long") or name.startswith("long_") or o.get("format") == "long"):
            continue  # 切り出しは元の長尺と文が重なるのが前提
        rate = len(me & trigram("".join(c["narration"] for c in oc))) / max(1, len(me))
        same_first = oc[0]["narration"] == me_cuts[0]["narration"]
        same_hook = bool(hook) and hook == next((c["hook"] for c in o.get("cuts", []) if c.get("hook")), None)
        same_title = bool(s.get("title")) and s.get("title") == o.get("title")
        worst = max(worst, rate)
        res.append({"回": name, "一致率": round(rate, 3), "同じ1文目": same_first, "同じ最初の文字": same_hook, "同じ題": same_title})
    line = SIM_LINE.get(n.get("kind") or s.get("format") or "short", 0.35)
    bad = [r for r in res if r["一致率"] >= line or r["同じ1文目"] or r["同じ最初の文字"] or r["同じ題"]]
    return {"合格": not bad, "最大の一致率": round(worst, 3), "線": line, "重なった回": bad, "比べた回数": len(res)}


def gate_fact(s, f, n, use):
    p = f"""あなたは「金運おきぬ」（財布と暮らしの小物の金運の言い伝えを、60代前後の女性に伝えるチャンネル）の事実確認の担当です。
書き手が調べた言い伝えの控え（facts.json）と、台本・題・概要欄を照らしてください。

見ること
1. 出典なしの言い伝え：「昔から〜と言われています」などの言い伝えが、控えの「言い伝え」に無い、または確かさが「確かめられず」。誰でも知っている生活の事実（財布は薄い方が出し入れしやすい 等）は対象外。
2. 事実として言い切った言い伝え：言い伝えを「〜です」「〜になります」と効果・事実として言い切っている（「昔から言われている」「やってみてね」の距離感を超えている）。
3. 結果の保証とお金の助言：「必ず貯まる」「〇万円増える」のような保証。貯金・投資のすすめ。脅し（放置すると悲惨な老後 など）。
4. 研究・統計・出典を並べている（このチャンネルでは置かない）。数字を言うなら、控えに一次情報で確かめた根拠があるものだけ。
   ただし題・サムネ・番号カード・見出しの判定語（破産・貧乏神・お金が逃げる・大損 など）は本人の方針で使う。これだけで不合格にしない（本文の効果の言い切りと保証は従来どおり見る）。
5. 作り話の決まり：world_rules（誰が何を知っているか）と食い違うセリフ・地の文（人物が知らないはずのことを話している）。
6. 当たり前の前提：「使ったらなくなる」のような、言われなくても分かる話を謎にしている。
問題がなければ空の配列。

控え（facts.json）：{json.dumps(f.get('言い伝え', f), ensure_ascii=False)[:3000]}
world_rules：{json.dumps(s.get('world_rules'), ensure_ascii=False)}
題：{s.get('title')}／概要欄：{s.get('desc')}
台本：
{lines(s)}
"""
    sch = {"type": "object", "properties": {"出典なしの言い伝え": items(id=S, 文=S, 理由=S), "言い切り": items(id=S, 文=S, 理由=S),
                                            "保証・助言・脅し": items(id=S, 文=S, 理由=S), "研究や統計": items(id=S, 文=S, 理由=S),
                                            "作り話の食い違い": items(id=S, 文=S, 理由=S), "当たり前の前提": items(id=S, 文=S, 理由=S)},
           "required": ["出典なしの言い伝え", "言い切り", "保証・助言・脅し", "研究や統計", "作り話の食い違い", "当たり前の前提"]}
    r = ask_json(p, sch, use)
    own = [x for x in (f.get("言い伝え") or []) if x.get("確かさ") == "確かめられず"]
    return {"合格": not any(r.values()) and not own, "確かめられずの控え": own, **r}


def gate_ng(s, ch, use):
    hard, soft = CK.words(soft=False), CK.words(soft=True)
    texts = [(c["id"], c["narration"]) for c in s["cuts"] if c.get("narration")] + [("title", s.get("title", ""))]
    hits = [{"id": i, "語": w, "文": t} for i, t in texts for w in hard + soft if w in t]
    p = f"""YouTube の金運チャンネル「金運おきぬ」（60代前後の女性向け・財布と暮らしの小物の言い伝え）の台本の点検です。
下の「当たった所」は、禁止表現の一覧と単純に一致した所です。それぞれ、文脈で本当に禁止に当たるかを判定してください。カギかっこの引用の中は「当たらない」。
「最後に残ったのは」「今日では」のように、メタや時の指定でない使い方は当たらない。
題・サムネ・番号カード・見出しの判定語（破産・貧乏神・お金が逃げる・大損・入れてはいけない・絶対〜しないで など）は本人の方針で使ってよい（制作ルール v1.6／v1.7）。これだけでは当たらない。

禁止の中身
- メタ文：名乗り／動画や回やチャンネルのこと（今回は・この動画では）／進み方の予告（最後に〜を言います・〜を3つ書いています）／お礼。予告は入れても1文だけ（その1文は当たらない）。
- 中身の無い引っ張り：答えは最後に・このあとお伝えします・後半でお話しします・最後まで見てね。問いだけを出すのは良い。長尺へつなぐ1文（日付と時刻、または「続きは、チャンネルの長い動画で。」）は導線なので当たらない。
- 時を決める言い方（今夜・今日・今宵）。ただし「今日では」のような今の時代の意味は当たらない。
- 脅し（暮らしへの脅し：放置すると悲惨な老後 など）、結果の保証、霊感・霊視があると語り手が言う。
- 名前の読みが1通りでない人名、「ひとつめ」（VOICEVOX で誤読）。
あわせて、一覧に無くても台本の全文を読んで、上の禁止に当たる文があれば足してください。無ければ空の配列。

当たった所：{json.dumps(hits, ensure_ascii=False)}
台本：
{lines(s)}
題：{s.get('title')}
"""
    r = ask_json(p, {"type": "object", "properties": {"禁止に当たる": items(id=S, 文=S, 理由=S)}, "required": ["禁止に当たる"]}, use)
    return {"合格": not r["禁止に当たる"], "一致した所": hits, **r}


def gate_ads(s, use):
    p = f"""YouTube の「広告掲載に適したコンテンツのガイドライン」の項目（不適切な言葉・暴力・ショッキングなコンテンツ・有害な行為・扇情的な表現（あおる題やサムネ）・センシティブな事件など）で、
下の台本・題を見てください。特に、お金に関する不安を強くあおる言い方（借金・生活苦・老後破綻をちらつかせる）と、医療・健康の効果を言う所を重点的に。
財布・お札・言い伝えの紹介、「金運」のような開運チャンネルでよくある言い方は、それだけでは当てはまりません。
題・サムネ・番号カードの判定語（破産・貧乏神・お金が逃げる 等）は本人の方針で使う。これだけで当てはまりとしない（本文の効果の言い切りと保証は従来どおり見る）。広告が限られる見込みが高い所だけを挙げてください。無ければ空の配列。
題：{s.get('title')}
台本：
{lines(s)}
"""
    r = ask_json(p, {"type": "object", "properties": {"当てはまる所": items(id=S, 文=S, 項目=S, 理由=S)}, "required": ["当てはまる所"]}, use)
    return {"合格": not r["当てはまる所"], **r}


def gate_hook(s, n, use):
    kind = n.get("kind", "short")
    cuts = [c for c in s["cuts"] if c.get("narration")]
    acc, first = 0, []
    for c in cuts:
        if kind == "long" and acc / CPS >= 30:
            break
        first.append(c)
        acc += len(re.sub(r"[、。！？「」]", "", c["narration"]))
        if kind != "long" and len(first) >= 3:
            break
    body = lines(s)
    if kind == "long":
        # v1.7 の場所の順位の型（第5位〜第1位）。最初の30秒＝NGの場面→判定→「5つあります」→主人公の対比→先見せ、章＝順位ごと、山場＝第1位
        p = f"""あなたは YouTube の編集者です。家で耳と目で長い動画を見ている60代前後の女性（その場所の片づけが気になり、神社のお守りやおみくじは持っている）として、下の「場所のNG5つを第5位から第1位まで数える動画」の台本を採点してください。
採点（10点満点・整数）
1. 最初の30秒（ここで離脱せず、続きを聞きたくなるか）：自分のその場所を思い浮かべて「うちはいくつ当てはまるか」と気になるか。判定の語（お金が逃げる・貧乏神 など）は題・見出しでは使ってよい。2文目までに具体的な場面（物・暗い絵）が浮かぶか
2. 各章（第5位・第4位・第3位・第2位・第1位・上がる側。全部採点する）：物の名前→判定→「と言われています」のわけ→主人公の場面→手元でできる直し方、が残るか。順位が下がっても「次が気になる」引きがあるか
3. 山場（第1位。"peak" が付いたカットのあたり）：「ほとんどの人がついやってしまう」場面として強く残るか。ここで声と間が変わるか
4. 電子ゴミの線：見た人が持ち帰れる物（直し方）が無い／生活の常識を金運として言い直しただけ／5つが他の場所の話と入れ替えられる、のどれかに当たる時は「電子ゴミ」を true
語り口はやわらかい話し言葉で、名乗りやお礼はしない決まり。点が低い所は、どこをどう直すと上がるかを1文で書く。具体的な結果の保証・お金の助言・答えを先に延ばすだけの文を足す案は出さない。甘く付けないでください。

最初の部分：
{lines({'cuts': first})}

台本：
{body}
"""
    else:
        p = f"""あなたは YouTube の編集者です。スマホでショートを流し見している60代前後の女性（財布の中身が気になり、神社のお守りやおみくじは持っている）として、下の台本を採点してください。
採点（10点満点・整数）
1. 最初の3文（スワイプせずに見続けるか）：自分の財布や玄関を確かめたくなる問いか（型1は「〜に入れていると、お金が逃げる物、3つ。」の言い切りでもよい）。判定の語（お金が逃げる 等）は題・1文目で使ってよい
2. 各章（ショートは前半・中盤・後半の3つに分けて見る）：場面が目に浮かぶか・言い伝えと「やっていいか」の答えが手元でできる形で残るか
3. 山場（"peak" が付いたカットのあたり＝第1位）：持ち帰れる物（手元の物でできる習慣・言い伝え）として残るか
4. 電子ゴミの線：見た人が持ち帰れる物が無い／生活の常識を金運として言い直しただけ／ショートなのに問いと答えが無い、のどれかに当たる時は「電子ゴミ」を true
語り口はやわらかい話し言葉で、名乗りやお礼はしない決まり。点が低い所は、どこをどう直すと上がるかを1文で書く。具体的な結果の保証・お金の助言・答えを先に延ばすだけの文を足す案は出さない。甘く付けないでください。

最初の部分：
{lines({'cuts': first})}

台本：
{body}
"""
    pt = {"type": "object", "properties": {"点": {"type": "integer"}, "直すなら": S}, "required": ["点", "直すなら"]}
    sch = {"type": "object", "properties": {"最初の30秒": pt, "章": items(章=S, 点={"type": "integer"}, 直すなら=S), "山場": pt, "電子ゴミ": {"type": "boolean"}, "電子ゴミの理由": S},
           "required": ["最初の30秒", "章", "山場", "電子ゴミ", "電子ゴミの理由"]}
    r = ask_json(p, sch, use)
    ok = r["最初の30秒"]["点"] >= 7 and all(c["点"] >= 5 for c in r["章"]) and r["山場"]["点"] >= 6 and not r["電子ゴミ"]
    return {"合格": ok, **r}


def main():
    a = argparse.ArgumentParser()
    a.add_argument("work")
    a.add_argument("--ch", default="okinu")
    a = a.parse_args()
    work = os.path.abspath(a.work)
    s, f, n = load(work)
    use = []
    judge = "Gemini" if os.environ.get("JUDGE", "claude") == "gemini" else f"claude -p（{os.environ.get('CLAUDE_JUDGE_MODEL', 'sonnet')}）"
    res = {"モデル": judge, "形": gate_form(work), "似すぎ": gate_similar(s, n, a.ch, work)}
    if not res["形"]["合格"]:  # 形が落ちた回は、文脈の判定（時間がかかる）を回さずに直しへ回す
        print("（形が不合格なので、文脈の判定は直したあとに回します）")
    else:
        res.update({"言い伝え": gate_fact(s, f, n, use), "禁止表現": gate_ng(s, a.ch, use), "広告に向くか": gate_ads(s, use),
                    "続きを見たくなるか": gate_hook(s, n, use)})
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

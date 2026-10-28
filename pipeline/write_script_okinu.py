# ③台本（金運おきぬ・2026-10-29 新設）：Claude（claude -p）に、手順書（制作ルール v1.4）と見本から script.json を書かせる
#   python -X utf8 pipeline/write_script_okinu.py <作業フォルダ> --ch okinu [--fix]
# ・作業フォルダには neta.json（pick_neta_okinu.py が置く）が先にあること。種類（kind）は short／cut／long
# ・見本（channels/okinu/golden）は形だけを借りる（項目名・カットの長さ・subs の切り方）。中身の場面・言い回し・小物は写さない（§12 の2）
# ・書く前に読ませる物：手順書（全部）・ショートの型（全部）・改善ログ2つのいちばん下の「次に上げること」・直近の回の題と1文目・競合メモ（あれば）
# ・言い伝えは Claude が WebSearch／WebFetch で確かめ、確かめた範囲だけを「昔から〜と言われています」の形で書く。確かめた結果は facts.json に残す
# ・書く作業には鍵を渡さない（write_script.py と同じ。子のプロセスから鍵の場所と鍵の環境変数を消して動かす）
# ・Claude は書いたあと check_okinu_script.py を自分で回し、NG が0件になるまで直す。最後にここでもう一度回して確かめる
# ・決まった値（format・画風・描かない物・声・速さ・BGM・概要欄の決まった行・タグ）は、書いたあとにプログラムが入れる（finish）
# ・--fix：gate_script.json（台本ゲートの不合格）を読ませて、不合格の所だけ直させる
# ・書いたあと、改善ログに1行足す（levelup_add。自動の回は history/okinu/改善ログ.md）
import argparse, glob, json, os, re, shutil, subprocess, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from write_script import ROOT, SECRET_ENV, levelup, levelup_add, LEVELUP_ASK  # noqa: E402

CH_DIR = os.path.join(ROOT, "channels", "okinu")
GOLD = os.path.join(CH_DIR, "golden")
LEVELUP_CH = os.path.join(CH_DIR, "改善ログ.md")  # 手で作った回の改善ログ（2026-10-28 まで）。自動の回は history/okinu/改善ログ.md に足す
HAND_DIR = os.environ.get("OKINU_HAND_DIR", r"C:\Users\koneb\OneDrive\YouTube自動チャンネル\金運おきぬ\videos")
AI_LINES = "※映像とナレーションはAIを使って作っています。\n※お話は創作です。"


def rel(p):
    return os.path.relpath(p, ROOT).replace("\\", "/")


def recent(ch="okinu"):
    """直近の回の題・1文目・最初の文字（同じ小物・1文目・問い・題を避ける材料。§12 の2）。手元は OneDrive の手で作った回も見る"""
    out = []
    for base in (HAND_DIR, os.path.join(CH_DIR, "videos")):
        for p in sorted(glob.glob(os.path.join(base, "*", "script.json"))):
            try:
                s = json.load(open(p, encoding="utf-8"))
            except Exception:
                continue
            v = [c for c in s.get("cuts", []) if c.get("narration")]
            if v:
                out.append({"回": os.path.basename(os.path.dirname(p)), "題": s.get("title"), "1文目": v[0]["narration"],
                            "最初の文字": next((c["hook"] for c in s["cuts"] if c.get("hook")), None), "最後の問い": v[-1]["narration"]})
    seen, rows = set(), []
    for x in out:
        if x["回"] not in seen:
            seen.add(x["回"]); rows.append(x)
    return rows[-14:]


def extra_docs():
    out = []
    for p, what in ((os.path.join(ROOT, "history", "okinu", "学び.md"), "学び（週報が書いた物。手順書とぶつかる時は手順書が勝つ）"),
                    (os.path.join(ROOT, "history", "okinu", "competitors", "競合メモ.md"), "競合メモ（型と『次の回で試すこと』を手順書の決まりの中で1つ取り入れてよい。題・文は写さない）"),
                    (LEVELUP_CH, "改善ログ（手で作った回の分）"), (levelup("okinu"), "改善ログ（自動で作った回の分）")):
        if os.path.exists(p):
            out.append((p, what))
    return out


SHORT_FORM = """## script.json の形（ショート・単独）
一番上：title（20字前後・【60代】のように年代を頭に・言い切らない）・fiction: true・world_rules（誰が何を知っているか。1〜3行の配列）・cuts。
format・desc・tags・style・avoid・bgm・voice・voices・tempo・comment は書かない（書いたあとにプログラムが入れる）。
cuts は13〜17個（1カット＝1文。1文は27字まで・平均18〜19字）。1つのカット：
- id："C01"〜"C15"
- narration：声に出す文（字幕もこの字）。1文目は「〇〇を、〜していませんか。」、最後は「あなたの〇〇には、〜ですか。」。この2文以外に問いかけを重ねない
- subs：字幕の分け方（配列。\\n で改行。1行8字まで。つなぐと narration と同じ字になること。語の途中で切らない）。全カットに書く
- image_en：絵の頼み方（英語。1枚で2文ほど。物の寄りを中心に、おきぬ（chars: ["okinu"]）は最初と最後だけ）。新しい絵のカットだけに書く。全体で7〜8枚
- same_as＋shots：前の絵を使い回すカット（"same_as": "C01", "shots": ["C01@close"]。@close／@full／@face／@left／@right）。絵が7〜8枚になるよう、残りのカットはこれで
- chars：絵に出る人（characters.json の id。主人公は neta.json の「主人公」＝さわこ(sawako)か澄江(sumie)。1カット2人まで）。手元だけの絵は []
- hook：1カット目だけ。画面いっぱいの最初の文字。5字×2行まで（"レシート\\n入れてる?"）
- motion: true と "anim": "kling"：1カット目と、見どころ（peak）のカットの2つに付ける（後で5秒の動く絵になる）。絵は動かしやすい物（手元・物の寄り）にする
- peak: true：1本に1つ。「やっていいか」の答えの場面。strong: true も付ける
- highlight：字幕の中で色を変える1語（配列。1〜2か所だけ）
- tts_text：読みを直す時だけ（channels/okinu/yomi.json の replace を見る。「米」「帰す」「角」「母」「札」の前後は特に）
- voice："sawako" のように人物の id：その人が口にするセリフだけのカットに付ける（おきぬの声のまま読ませない。手順書 §3）。セリフはカギかっこで囲まず、そのカットを丸ごとセリフにする
中身の流れ（ショートの型の表）：1文目＝自分の財布を確かめる問い／2〜5文目＝主人公（年・金額は出すなら1つずつ）の場面と「〜のに〜」／6〜8文目＝言い伝えとそのわけ（「昔から〜と言われています」）／
9〜12文目＝「やっていいか」への答えと、手元の物でできるやり方1つ／13〜14文目＝主人公のその後（効いたと言い切らない。暮らしで見えた変化）／最後＝問い。
"""

CUT_FORM = """## script.json の形（ショート・長尺の切り出し）
neta.json の long_dir にある長尺の script.json（と images/）から、小物「{item}」の1場面を切り出す。長尺の絵だけを使う（新しい絵は作らない）。
一番上：title・funnel（{{"long": "<長尺の作業フォルダ名>", "long_publish": "<長尺の公開日時。neta.json の long_publish。無ければ空>", "kind": "切り出し"}}）・fiction: true・world_rules・cuts。
cuts は13〜17個。1つのカット：id・narration・subs・shots（長尺の絵の id の配列。"B21@close" のように@で寄りを付けてよい）・highlight・tts_text・voice・peak・hook（1カット目だけ）。image_en は書かない。
- 1文目は「〇〇を、〜していませんか。」で、長尺の場面をそのまま写さず、ショートとしての問いと答えを持つ（手順書 §12 の3）
- 答えの一歩手前まで話し、最後の問いの直前のカットに「続きは、チャンネルの長い動画で。」（長尺が公開前なら、長尺の日付と時刻を声で言う。neta.json の long_publish から）。最後は「あなたの〇〇には、〜ですか。」
- 1カット目と peak のカットは、長尺で動く絵（images/<id>.mp4）がある絵を選ぶ（無ければ静止画でもよい）。"anim": "kling" を付ける
"""

LONG_FORM = """## script.json の形（長尺）
一番上：title（【年金11万円】のように、年代かお金の数字を頭に。結果の約束は言い切りにしない）・thumb（{"top": "場面か悩み（例 毎晩家計簿をつけてるのに）", "big": "答え・ひっかかりの語（1行・8字まで）", "hl": ["要の1語"]}）・
titles（3案）・fiction: true・world_rules（誰が何を知っているか）・world_terms・desc_lead（概要欄の1段落目：コメントを呼ぶ最後の問いと同じ文＋「コメントで教えてくださいね。」）・tags・cuts。
カットは見本 long_001v6.json の形（id・narration・tts_text・image_en・chars・card・same_as・yt_chapter）に合わせる。違い：
- 章の頭のカットに "chapter": "章の名前"（見本の yt_chapter と同じ役。両方書いてよい）。章は6〜8個（つかみ／小物の章×neta.json の items の数／その後／まとめ）
- 字数 3,000〜4,200字（句読点を含む）・見込み10分前後
- 伏線：全体の40%より前のカットに "tease": true（後半で答える問いを1つ。「最後まで見て」とは言わない）。答えのカットに "payoff": true（50%より後）
- 見どころ：「やっていいか」の答えの場面に "peak": true と "strong": true（動く絵か真ん中のキーワードカードで目立たせる）
- 動く絵：章ごとに1つ以上と見どころに "anim": "kling"（"motion": true も付ける）か "anim": "card"（見本の card が動くカード）。motion は全体の1〜2割まで
- 絵：新しい絵（image_en）は25〜60枚。同じ絵の続きは same_as。物（財布・お札・レシート）の寄りを中心にする。人物のカットは chars を書く
- 人物のセリフ：その人だけが口にするカットに "voice": "take" のように書く（おきぬの声のまま読ませない）。セリフのカットは短く
- 各章の終わりの1文で、次の章で分かることを中身で引く（進み方の予告はしない）
- カードのカット（見本の card：wallet・photo・big_text・quote・rules など）は、見本で使っている型と項目だけ
- 聞き手・掛け合いは入れない（手順書 §3）
- サムネの背景：cuts の最後に narration の無いカット "THUMB" を1つ置き、一番上に "thumb_bg": "THUMB" を書く。THUMB の image_en は、暗めの背景で主役に光、主役を真ん中の高さに置き上下の2割をあけた絵（その回の小物を画面の半分近くまで大きく、または人物のはっきりした表情。人物は chars）。絵の中に文字は入れない
"""


def prompt(work, fix):
    neta = json.load(open(os.path.join(work, "neta.json"), encoding="utf-8"))
    kind = neta.get("kind", "short")
    more = "".join(f"\n{i}. {rel(x)}（{what}）" for i, (x, what) in enumerate(extra_docs(), 8))
    gold = {"short": ["short_S001.json", "kiridashi_S008.json"], "cut": ["kiridashi_S008.json", "short_S001.json"], "long": ["long_001v6.json"]}[kind]
    form = {"short": SHORT_FORM, "cut": CUT_FORM.format(item=neta.get("item", "")), "long": LONG_FORM}[kind]
    p = f"""あなたは YouTube チャンネル「金運おきぬ」（財布と暮らしの小物の金運の言い伝え。60代前後の女性が耳と目で見る。語り手はおきぬ）の台本の書き手です。
作業フォルダ {rel(work)} に script.json を書いてください（facts.json も下の決まりで書く）。今回は「{ {'short': '単独のショート', 'cut': '長尺から切り出すショート', 'long': '長尺'}[kind] }」です。

## 先に全部読むファイル（部分読み禁止。手順書は最後の行まで）
1. {rel(os.path.join(CH_DIR, '手順書.md'))}（制作ルール v1.4。§0〜§14 の全部。このチャンネルの決まりの正本）
2. {rel(os.path.join(CH_DIR, 'ショートの型.md'))}（ショートの型の表と台本案 S1〜S3。ショートの時は特に）
3. {rel(os.path.join(work, 'neta.json'))}（この回の小物・悩み・年・「やっていいか」の問い・主人公。ネタ選びが決めた値。書き換えない）
4. {' と '.join(rel(os.path.join(GOLD, g)) for g in gold)}（形と密度の見本。項目名・カットの長さ・subs の切り方を借りる。中身の小物・場面・言い回し・つかみは写さない）
5. {rel(os.path.join(CH_DIR, 'characters', 'characters.json'))}（絵に出る人。chars に書けるのはこの id だけ。voice は人物ごとの声）
6. {rel(os.path.join(CH_DIR, '禁止表現.txt'))}（使わない言葉）と {rel(os.path.join(CH_DIR, 'yomi.json'))}（読みの表）{more}

## この回（neta.json の要点）
種類：{kind}／小物：{neta.get('小物')}／悩み：{neta.get('悩み')}／主人公の年：{neta.get('年')}／主人公：{neta.get('主人公')}／「やっていいか」の問い：{neta.get('ok_q')}
{('小物の章：' + '・'.join(neta.get('items', []))) if neta.get('items') else ''}{('切り出し元：' + str(neta.get('long')) + '（' + str(neta.get('long_dir')) + '）／小物：' + str(neta.get('item'))) if kind == 'cut' else ''}

## 直近の回（同じ小物・1文目・最初の文字・問い・題を使わない材料。言い換えただけも同じ。§12 の2）
{json.dumps(recent(), ensure_ascii=False, indent=1)}

## 中身の決まり（手順書の要点。全文は手順書）
- 1本につき小物か行為を1つ。「これはやっていいか」に先回りして1文で答える。お金のかからない、手元にある物でできる習慣・言い伝えだけ。
- 効果は言い切らない（「必ず貯まる」は使わない）。距離感は「昔から言われている」「やってみてね」。効かなかった人を置き去りにしない一言を入れる。「お金を呼ぶ力はわかりません」と自分で否定もしない。
- お金の助言（貯金・投資のすすめ）にしない。研究・統計・出典を並べない。使わない語：宝くじ・億・借金・一発逆転・今夜・今日。脅さない。
- 主人公は視聴者と同年代の女性（さわこ・すみえ）。名乗らない。メタ文（今回は・この動画では・最後に）と中身の無い引っ張り（答えは最後に・このあとお伝えします）を書かない。
- 数え方は「最初は／次に／そして」か「1番／2番／3番」。「ひとつめ」は使わない。禁止記号（── — → … ※ ★ 水平線）を台本に入れない。
- 言い伝えは、WebSearch／WebFetch で確かめられた範囲だけを「昔から〜と言われています」の形で書く。確かめられない物は言い伝えとして言わない（別の習慣に差し替える）。
  確かめた結果を facts.json に {{"言い伝え": [{{"文": "台本の文", "確かめた所": "URL か 名前", "確かさ": "広く言われている／出典あり／確かめられず"}}]}} の形で書く。
- 締めはしんみりまとめない。問いかけで終える。

{form}
## やること
1. 上のファイルを全部読む。改善ログ2つの「いちばん下の行」の日付を比べ、新しい方の「次に上げること」をこの回に必ず1つ入れる。
2. 言い伝えを調べて facts.json に書く。
3. script.json を書く。
4. 終わる前に必ず `python -X utf8 pipeline/check_okinu_script.py {rel(work)}` を回し、NG が0件になるまで直す（注意は直せる物は直す）。概要欄は書いたあとにプログラムが入れるので、「概要欄に〜が無い」の NG は気にしなくてよい（finish で入る）。
5. 最後に、字数・カット数・絵の数（新しい絵）・使った言い伝えの確かめ方を1行ずつ書いて終える。

{LEVELUP_ASK}
## 台本ゲートの採点（書いたあと、別のAIがこの線で見る）
- 60代前後の女性として10点満点。最初の文（ショートは1文目、長尺は最初の30秒）で続きを見たくなるか。持ち帰れる物（手元でできる習慣・言い伝え）が1つ言えているか。
- 事実の点検：言い伝えを事実として言い切っていないか。結果の保証・お金の助言・脅しが無いか。前の回と同じ小物・問い・1文目でないか。
"""
    if fix:
        g = json.load(open(os.path.join(work, "gate_script.json"), encoding="utf-8"))
        bad = {k: v for k, v in g.items() if isinstance(v, dict) and v.get("合格") is False}
        p += f"""
## 今回は書き直し
台本ゲートで、次の項目が不合格でした。不合格の所だけを直し、ほかは変えないでください。点検の「直すなら」は案です。手順書の決まりとぶつかる案は採らず、決まりの中で同じ狙いを達する直し方にしてください。
直したら check_okinu_script.py をもう一度回し、NG 0件にしてから終えてください。
{json.dumps(bad, ensure_ascii=False, indent=1)}
"""
    return p


def finish(work):
    """決まった値を入れる：format・画風・描かない物・声・速さ・BGM・概要欄・タグ・image（image_en の写し）・anim"""
    sp = os.path.join(work, "script.json")
    neta = json.load(open(os.path.join(work, "neta.json"), encoding="utf-8"))
    prof = json.load(open(os.path.join(CH_DIR, "profile.json"), encoding="utf-8"))
    chars = json.load(open(os.path.join(CH_DIR, "characters", "characters.json"), encoding="utf-8")).get("chars", {})
    s = json.load(open(sp, encoding="utf-8"))
    kind, b = neta.get("kind", "short"), prof.get("build") or {}
    s.update({"format": "long" if kind == "long" else "short", "channel": "okinu", "style": prof["style"], "avoid": prof["avoid"],
              "characters_dir": "../../characters", "bgm": "../../assets/bgm/okinu_bgm_01_seed1.m4a"})
    if kind == "long":
        s.update({"card_theme": "kinun", "tempo": 1.0, "gap": b.get("gap", 0.35), "voice": {"engine": "voicevox", "speaker": 9, "speedScale": 0.85}})
    else:
        s.update({"tempo": (b.get("short") or {}).get("tempo", 1.3), "voice": {"engine": "voicevox", "speaker": 9}})
    # 人物の声（セリフのカットの voice）
    used = sorted({c["voice"] for c in s["cuts"] if c.get("voice")})
    s["voices"] = {k: chars[k]["voice"] for k in used if k in chars}  # スキルの make_voice.py の形（人物の id → VOICEVOX の声の番号）
    voice_names = ["波音リツ"] + sorted({(chars[k].get("voice_name") or "").split("（")[0] for k in used if k in chars} - {""})
    for c in s["cuts"]:
        if c.get("image_en"):
            c["image"] = c["image_en"]  # make_images_lovart.py は image を読む（英語のまま渡す）
        if c.get("motion") and not c.get("anim"):
            c["anim"] = "kling"
    narr = [c for c in s["cuts"] if c.get("narration")]
    last_q = narr[-1]["narration"] if narr else ""
    if kind == "long":
        lead = s.get("desc_lead") or f"{last_q}コメントで教えてくださいね。"
        s["desc"] = lead + "\n\n{CHAPTERS}\n\n" + AI_LINES + "\nVOICEVOX:" + "、VOICEVOX:".join(voice_names)
        s.setdefault("tags", ["金運", "財布", neta.get("小物", "")[:10], "60代"])
        s["titles"] = s.get("titles") or [s["title"]]
    else:
        long_line = ""
        if kind == "cut":
            f = s.get("funnel") or {}
            url = f"https://youtu.be/{neta['long_video_id']}" if neta.get("long_video_id") else "{LONG_URL}"
            long_line = f"本編（長い動画）：{url}\n\n"
            s["funnel"] = {"long": neta.get("long"), "long_publish": f.get("long_publish") or neta.get("long_publish") or "", "kind": "切り出し"}
            s["subs_bottom"] = True
        tag = re.sub(r"[#\s　、。]", "", neta.get("小物", ""))[:10]
        s["desc"] = f"{last_q}コメントで教えてくださいね。\n\n{long_line}{AI_LINES}\nVOICEVOX:" + "、VOICEVOX:".join(voice_names) + f"\n\n#shorts #金運 #{tag}"
        s["tags"] = ["金運", "財布", tag, "60代"]
    s["comment"] = f"{last_q}"  # 公開後の固定コメント＝最後の問いをそのままもう一度（ショートの型「固定コメント」）
    json.dump(s, open(sp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def main():
    a = argparse.ArgumentParser()
    a.add_argument("work")
    a.add_argument("--ch", default="okinu")
    a.add_argument("--fix", action="store_true")
    a = a.parse_args()
    work = os.path.abspath(a.work)
    if not os.path.exists(os.path.join(work, "neta.json")):
        sys.exit("【止まりました】neta.json がありません（pick_neta_okinu.py で作業フォルダを作る）")
    tools = ["Read", "Write", "Edit", "Glob", "Grep", "WebSearch", "WebFetch", "Bash(python -X utf8 pipeline/check_okinu_script.py:*)"]
    env = {k: v for k, v in os.environ.items() if k not in SECRET_ENV + ("YT_TOKEN_PSY", "YT_TOKEN")}
    env["YT_SECRETS_DIR"] = os.path.join(ROOT, "_no_secrets_here")  # 書く作業から鍵の場所を見えなくする
    cmd = [shutil.which("claude") or "claude", "-p", "--model", os.environ.get("CLAUDE_WRITER_MODEL", "opus"),
           "--allowedTools", *tools, "--permission-mode", "acceptEdits", "--output-format", "json"]
    r = subprocess.run(cmd, cwd=ROOT, env=env, input=prompt(work, a.fix), capture_output=True, text=True, encoding="utf-8", timeout=5400)
    open(os.path.join(work, "_write.log"), "a", encoding="utf-8").write(r.stdout + "\n" + r.stderr + "\n")
    out = {}
    try:
        out = json.loads(r.stdout)
        print(out.get("result", "")[-1500:])
        print(f"（Claude：{out.get('num_turns')}手・{out.get('duration_ms', 0) / 60000:.1f}分）")
    except json.JSONDecodeError:
        print(r.stdout[-1500:], r.stderr[-800:])
    sp = os.path.join(work, "script.json")
    if r.returncode != 0 or not os.path.exists(sp):
        sys.exit("【止まりました】台本を書けませんでした（_write.log を見る）")
    finish(work)
    if not a.fix:
        levelup_add(a.ch, work, out.get("result", ""))
    chk = subprocess.run([sys.executable, "-X", "utf8", os.path.join(ROOT, "pipeline", "check_okinu_script.py"), work],
                         capture_output=True, text=True, encoding="utf-8")
    print("\n".join(chk.stdout.strip().splitlines()[-12:]))
    sys.exit(0 if chk.returncode == 0 else 1)


if __name__ == "__main__":
    main()

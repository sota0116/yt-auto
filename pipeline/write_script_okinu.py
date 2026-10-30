# ③台本（金運おきぬ・2026-10-29 新設／2026-10-30 制作ルール v1.7 の順位の型に更新）：Claude（claude -p）に、手順書（制作ルール v1.7）と見本から script.json を書かせる
#   python -X utf8 pipeline/write_script_okinu.py <作業フォルダ> --ch okinu [--fix]
# ・作業フォルダには neta.json（pick_neta_okinu.py が置く）が先にあること。種類（kind）は short／cut／long
# ・見本（channels/okinu/golden）は形だけを借りる（項目名・カットの長さ・subs の切り方）。中身の場面・言い回し・小物は写さない（§12 の2）
#   長尺の見本は long_006.json（手で作った 006 台所のNG5＝§15 の順位の型）。long_001v6.json は物語の型（v1.4）なので使わない
# ・長尺（v1.7）：neta.json の「小物」は場所・テーマ（カバン・洗面所…）。書き手が競合の言う NG5 を WebSearch で選び、facts.json の「順位」に残す
# ・共有ポーズ絵：cuts に "img_from": "pose:A17" と書くと、finish が channels/okinu/assets/poses/A17.jpg を images/<id>.png に写す（絵は作らない。image は消す）
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
import check_okinu_script as CK  # noqa: E402

CH_DIR = os.path.join(ROOT, "channels", "okinu")
GOLD = os.path.join(CH_DIR, "golden")
POSES = os.path.join(CH_DIR, "assets", "poses")  # 共有ポーズ絵（手で作った 001v6／002 の絵。1920x1080 の jpg）
LEVELUP_CH = os.path.join(CH_DIR, "改善ログ.md")  # 手で作った回の改善ログ（2026-10-28 まで）。自動の回は history/okinu/改善ログ.md に足す
HAND_DIR = os.environ.get("OKINU_HAND_DIR", r"C:\Users\koneb\OneDrive\YouTube自動チャンネル\金運おきぬ\videos")
AI_LINES = "※映像とナレーションはAIを使って作っています。\n※お話は創作です。"


def rel(p):
    return os.path.relpath(p, ROOT).replace("\\", "/")


def recent(ch="okinu"):
    """直近の回の題・1文目・最初の文字（同じ小物・1文目・問い・題を避ける材料。§12 の2）。手元は OneDrive の手で作った回も見る。
    クラウドには OneDrive が無いので、手で作った 003〜006 は history/okinu/scripts/ に写した物（題・サムネの型・各カットの文）から読む"""
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
                            "最初の文字": next((c["hook"] for c in s["cuts"] if c.get("hook")), None), "最後の問い": v[-1]["narration"],
                            "サムネの型": (s.get("thumb") or {}).get("layout")})
    for p in sorted(glob.glob(os.path.join(ROOT, "history", ch, "scripts", "*.json"))):
        try:
            s = json.load(open(p, encoding="utf-8"))
        except Exception:
            continue
        v = [c for c in s.get("cuts", []) if c.get("narration")]
        if v:
            out.append({"回": os.path.basename(p)[:-5], "題": s.get("title"), "1文目": v[0]["narration"],
                        "最初の文字": next((c["hook"] for c in s["cuts"] if c.get("hook")), None), "最後の問い": v[-1]["narration"],
                        "サムネの型": (s.get("thumb") or {}).get("layout") or s.get("thumb_kind")})
    seen, rows = {}, []
    for x in out:  # 同じ回は OneDrive（手元の正本）を先に取り、history の写しは重ねない（番号が同じ回＝003_ のような頭の数字で見る）
        k = x["回"].split("_")[0]
        if k not in seen:
            seen[k] = 1; rows.append(x)
    for x in rows:
        x["サムネの型"] = x.get("サムネの型") or CK.HAND_LAYOUT.get(x["回"].split("_")[0])
    rows.sort(key=lambda x: x["回"])
    return rows[-14:]


def extra_docs():
    out = []
    for p, what in ((os.path.join(ROOT, "history", "okinu", "学び.md"), "学び（週報が書いた物。手順書とぶつかる時は手順書が勝つ）"),
                    (os.path.join(ROOT, "history", "okinu", "competitors", "競合メモ.md"), "競合メモ（型と『次の回で試すこと』を手順書の決まりの中で1つ取り入れてよい。題・文は写さない）"),
                    (LEVELUP_CH, "改善ログ（手で作った回の分）"), (levelup("okinu"), "改善ログ（自動で作った回の分）")):
        if os.path.exists(p):
            out.append((p, what))
    return out


SHORT_FORM = """## script.json の形（ショート・単独）ショートの型 v2
neta.json の「型」が 1 なら 型1（NG 3つの数え下げ）、2 なら 型2（1つだけ禁止）。型の表はショートの型.md が正本。
一番上：title（20〜28字・伸びた題の形を写して場所と物だけ変える。型1「〇〇に入れてはいけない物3選」「実は貧乏な人に多い〇〇の特徴3選」「〇〇に置くとお金が逃げる物3選」／型2「〇〇に「これ」絶対置かないで」。頭の【60代】は付けても付けなくてもよい。説明するだけの題・言い切るだけの題にしない）・fiction: true・world_rules（1〜3行の配列）・cuts。
format・desc・tags・style・avoid・bgm・voice・voices・tempo・comment は書かない（書いたあとにプログラムが入れる）。
cuts（1カット＝1文。1文は27字まで）。1つのカット：
- id："C01"〜
- narration：声に出す文（字幕もこの字）
- subs：字幕の分け方（配列。\n で改行。1行8字まで。つなぐと narration と同じ字になること。語の途中で切らない）。全カットに書く
- image_en：絵の頼み方（英語。縦長 1080x1920 で物が画面の半分以上の寄り。人物は第1位の場面だけ・はっとした顔で）。新しい絵のカットだけ。全体で7〜9枚
- same_as＋shots：前の絵を使い回すカット（"same_as": "C01", "shots": ["C01@close"]。@close／@full／@face／@left／@right）
- chars：絵に出る人（characters.json の id）。物だけの絵は書かない
- hook：1カット目だけ。画面いっぱいの最初の文字。5字×2行まで（"財布に\n入れたらNG"）
- band：帯（型1のみ。7字まで「お金が逃げる物」）。1カット目に付ける
- motion: true と "anim": "kling"：1カット目と、第1位（型2は物を見せるカット）の2つ以上。動かしやすい絵（手元・物の寄り）にする
- peak: true：1本に1つ（型1＝第1位の場面／型2＝「やっていいか」の答え）。strong: true も付ける
- highlight：字幕の中で色を変える1語（配列。1〜2か所）
- tts_text：読みを直す時だけ（channels/okinu/yomi.json の replace を見る）
- voice：人物のセリフだけのカットに（ショートは物が主役なので原則使わない）
型1（290〜360字・35〜45秒。15〜20カット）：1文目「〇〇に入れていると、お金が逃げる物、3つ。」→ 第3位（70〜90字：物の名前→判定1文→意味づけ1文「昔から〜と言われています」→直し方1文）→ 第2位（70〜90字・同じ並び）→
  第1位（90〜110字：「ほとんどの人が入れている」物。「これはやっていいか」に1文で答える）→ 最後「あなたの〇〇には、いくつ入っていましたか。」。「第3位」「第2位」「第1位」はそれぞれのカットの文頭に言う（画面の真ん中に大きく出る）。
型2（250〜300字・30〜35秒。14〜18カット）：1文目「玄関に、これを置いていませんか。」→ 物を見せる（大写し）→ 判定1文 → 意味づけ（気・五行・風水・仏教・縁起のどれか1つ。「昔から〜と言われています」）→
  「これはやっていいか」への答えと手元の物でできる直し方1つ → 最後「あなたの玄関には、置いてありませんか。」。
どちらも：金額・年齢は2文目以降。長尺へのつなぎ文は入れない（概要欄だけでつなぐ）。効果音なし。
"""


CUT_FORM = """## script.json の形（ショート・長尺の切り出し）
neta.json の long_dir にある長尺の script.json（と images/）から、小物「{item}」の1場面を切り出す。長尺の絵だけを使う（新しい絵は作らない）。
一番上：title・funnel（{{"long": "<長尺の作業フォルダ名>", "long_publish": "<長尺の公開日時。neta.json の long_publish。無ければ空>", "kind": "切り出し"}}）・fiction: true・world_rules・cuts。
cuts は13〜17個。1つのカット：id・narration・subs・shots（長尺の絵の id の配列。"B21@close" のように@で寄りを付けてよい）・highlight・tts_text・voice・peak・hook（1カット目だけ）。image_en は書かない。
- 1文目は「〇〇を、〜していませんか。」で、長尺の場面をそのまま写さず、ショートとしての問いと答えを持つ（手順書 §12 の3）
- 答えの一歩手前まで話し、最後の問いの直前のカットに「続きは、チャンネルの長い動画で。」（長尺が公開前なら、長尺の日付と時刻を声で言う。neta.json の long_publish から）。最後は「あなたの〇〇には、〜ですか。」
- 1カット目と peak のカットは、長尺で動く絵（images/<id>.mp4）がある絵を選ぶ（無ければ静止画でもよい）。"anim": "kling" を付ける
"""

LONG_FORM = """## script.json の形（長尺・制作ルール v1.7 §15 の順位の型）
お手本：channels/okinu/golden/long_006.json（手で作った 006 台所のNG5。形・カードの使い方・カットの長さを借りる。場面・言い回し・小物は写さない）。
この回は「場所（neta.json の小物）で、お金が残らない人がやっていること NG 5つ」を第5位から第1位まで数える。長さ 4,000〜4,800字・150〜170カット・約13分（声は速さ 1.0・1分320〜340字）。
一番上：title・titles（3案）・thumb・fiction: true・world_rules（誰が何を知っているか）・world_terms・desc_lead・tags・cuts。
## 5つの選び方（書く前に）
競合が同じ場所で言っているNGを WebSearch／WebFetch で調べ、お金のかからない・手元でできる直し方がある物を5つ選ぶ。順位はひっかかりの強さ（第1位は「疲れた夜に、ほとんどの人がついやってしまう」物）。
5つとその確かめた所を facts.json の「順位」（[{"位":5,"項目":..,"確かめた所":..,"直し方":..}]）に、言い伝えを「言い伝え」に書く。確かめられない物は入れない。
## 時間配分（約13分）
つかみ 40〜70秒（A）／第5位〜第2位 各2〜3分（B・C・D・E）／クイズの伏線と答え 30秒／第1位 3分（ピーク）／上がる側 1分（G）／まとめ 30〜40秒（K）。
## 必ず入れる物
1. つかみ（§2）：1カット目＝その場所の NG の絵（暗め・動く絵）→ 金運の世界の判定の1文（「〜と言われています」）→ 「お金が残る人が〇〇で絶対にしないことが5つあります」（big_text）→ 主人公（佐和子さん）と同じ団地の澄江さんの対比（two_cards・年金はほとんど同じ）→ 5つの先見せ（モンタージュ）→ 第1位の予告（伏せ字で）。
2. モンタージュ（先見せ）：つかみの終わりに "montage": [出てくる絵のカット id を4つ]・"montage_blur": 14・"montage_labels": ["第5位　欠けた●●を使い続ける", …]（伏せ字の●で。第5位〜第2位）。narration は「お金が残らない人は、〇〇で、この5つをやっています。」の1文。このカット自体には image_en を書かない。
3. 順位の番号カード：各順位の頭に {"type": "rank", "num": "第5位", "title": "…", "sub": "…"}（第1位は伏せ字の title・"mark": "？" で予告しておき、第1位の頭で出す）。"yt_chapter": "第5位 …" も付ける。
4. 判定の語＋意味づけ：順位ごとに「それは〇〇のしるしだと言われています」（判定→わけ）。「昔から〜」の距離感は本文で守る。
5. 主人公の短い場面：順位ごとに佐和子さんの1〜3カット（人物の絵は共有ポーズ絵 "img_from": "pose:A17" で足りる。下の一覧）。セリフは本人の声（"voice": "sawako"）で、そのカットを丸ごとセリフにする。
6. 直し方は rules カード：{"type": "rules", "title": "第5位の直し方", "items": [3つ], "show": 1, "fresh": true}→ 次のカットで show 2 → 最後に show 3, "all": true（1つずつ増やす）。まとめは "nums": ["5","4","3","2","1"] を付けた rules。
7. 「やっていいか」の問い：2つ以上（「母の形見のお皿が欠けたら？」「食洗機ならいいか？」のような。答えは big_text の kicker「答え」で1文）。
8. クイズ：全体の40%より前のカットに "tease": true（big_text の kicker「ここで」・text2「問題」。問いは「西に置くといい色は？」のような答えが1語で言える物）。50%より後に "payoff": true（kicker「答え」）。
9. 第1位の山場：第1位の場面のカットに "peak": true と "strong": true（動く絵）。"highlight" で核の1語。ほとんどの人がついやってしまうことで、ここで声と間を作る。
10. 上がる側（1分）："番外"の rank カード（"good": true・"mark": "開運"）で、金運が上がると言われる行いを1つ。
11. まとめ：rules（"all": true・"nums" 付き）で5つを読み上げ → 最後に「あなたの〇〇は、5つのうちいくつ当てはまりましたか？ コメントで数を教えてくださいね」（コメントを呼ぶ数の問い。desc_lead はこの文）。
## カードの型（これ以外は使わない）
rank／rules／big_text（text・text2・accent・kicker）／two_cards（items[{head, sub, x?}]・sep）／photo（pop{small, big, size}・name・role）。写真だけのカット（絵のみ）は card を書かない。
## 絵と動き
- 新しく作る絵（image_en）は14〜20枚（006 は14枚。多くても25枚まで）。絵のあるカットは新規＋ポーズ絵で合わせて40以上（006 は45）。同じ絵の続きは same_as。物の寄りと、その場所の暗い絵（NGの場面）を中心に。人物は chars を書く（sawako・sumie・okinu）。
- 共有ポーズ絵（新しく作らない）："img_from": "pose:A17"（image_en は書かない）。使える id：A17・A16・C02・C16・D10・F03・F06・E11（おきぬの上半身のポーズ）／A10（澄江さんが玄関で笑う）／s02_A05（佐和子さんの場面）／s02_A07（佐和子さんの驚き顔）／M03・M04・K07・C09。好きな場面に使い回してよい（同じ id を1本で3〜4回まで）。
- 動く絵：約7カットに "anim": "kling" と "motion": true（1カット目・各順位に1つ・山場）。動かすカットに card は付けない（card があると動かない）。
## サムネ（制作ルール v1.7 §9）
thumb の layout を次の4つから選ぶ。直近2本と同じ layout にしない（直近6本で同じ型は2回まで。下の「直近の回」のサムネの型を見る）。
- "object"：物の寄りが背景。{"layout":"object","bg":"<物の絵のカットid>","line1":"枕元の","line2":"コレ","judge":"今すぐどけて"}（line2 は大きく黄色）
- "person"：人物（左）＋右上に2行＋下に大きな赤の判定。{"layout":"person","bg":"<人物のカットid>","line1":"疲れた夜に","line2":"●●する人","judge":"大損してます","hl":["●●"]}
- "split"：左右半分。左＝暗い悪い絵／右＝明るい良い絵。{"layout":"split","left":"<カットid>","right":"<カットid>","line1":"トイレの●●で","line2":"差がつく","left_label":"残らない家","right_label":"残る家"}
- "shock"：左上に2行＋右に驚いた顔＋下に赤の判定。{"layout":"shock","bg":"<物の絵のカットid>","face":"<驚いた顔のカットid（s02_A07 を使った cut でもよい）>","line1":"玄関に●●を","line2":"出してる家","judge":"破産します"}
文字は3段（上2行＝場面か悩み／下＝判定）。判定の語（破産します・大損・貧乏神）は題・サムネ・番号カード・見出しに使ってよい（本人の方針）。判定は画面の幅の6割以上・伏せ字は●。背景の絵は暗め。
## 題（§8）
型 A〜F（手順書 §8）のどれか1つ。直近の回と同じ型を続けない。必ず【金運】で終える（頭の【】は型による）。26〜40字。titles に3案。
## 中身の決まり（v1.7）
- 判定の語は題・サムネ・見出しに使ってよい。本文は「〜と言われています」の距離を保ち、効果の言い切りと保証はしない。1本で場所は1つ。
- 聞き手・掛け合いは入れない。人物のセリフは本人の声で。各順位の終わりの1文で次に分かることを中身で引く（進み方の予告はしない）。
- 章は yt_chapter（順位の rank カードのカットと、番外・まとめ）。"chapter" も同じ名前で付けてよい。
"""


SHORT_RULES = """## 中身の決まり（手順書の要点。全文は手順書）
- 題・サムネ・番号の判定の語（逃げる・貧乏・破産 など）は本人の方針で使ってよい。本文は「〜と言われています」の距離を保つ。
- 型1は物3つ・型2は物1つ。第1位（型2は答えの文）で「これはやっていいか」に先回りして1文で答える。お金のかからない、手元にある物でできる習慣・言い伝えだけ。
- 効果は言い切らない（「必ず貯まる」は使わない）。距離感は「昔から言われている」「やってみてね」。効かなかった人を置き去りにしない一言を入れる。「お金を呼ぶ力はわかりません」と自分で否定もしない。
- お金の助言（貯金・投資のすすめ）にしない。研究・統計・出典を並べない。使わない語：宝くじ・億・借金・一発逆転・今夜・今日。暮らしへの脅し（悲惨な老後 など）は書かない。
- ショートは物が主役。人物は出すなら第1位の場面だけ（名乗らない）。物語の場面は入れない。メタ文（今回は・この動画では・最後に）と中身の無い引っ張り（答えは最後に・このあとお伝えします）を書かない。
- 数え方は「第3位／第2位／第1位」（型1）。「ひとつめ」は使わない。禁止記号（── — → … ※ ★ 水平線）を台本に入れない。
- 言い伝えは、WebSearch／WebFetch で確かめられた範囲だけを「昔から〜と言われています」の形で書く。確かめられない物は言い伝えとして言わない（別の習慣に差し替える）。
  確かめた結果を facts.json に {"言い伝え": [{"文": "台本の文", "確かめた所": "URL か 名前", "確かさ": "広く言われている／出典あり／確かめられず"}]} の形で書く。
- 締めはしんみりまとめない。問いかけで終える。

"""
LONG_RULES = """## 中身の決まり（制作ルール v1.7 の要点。全文は手順書）
- お金のかからない、手元にある物でできる直し方だけ。効果の言い切りと保証（「必ず貯まる」）はしない。お金の助言（貯金・投資のすすめ）にしない。研究・統計・出典を並べない。
- 題・サムネ・番号カード・見出しの判定語（破産・貧乏神・お金が逃げる・大損 など）は本人の方針で使ってよい。本文は「昔から〜と言われています」の距離を保つ。使わない語：宝くじ・億・借金・一発逆転・今夜・今日。
- 主人公は視聴者と同年代の女性（さわこ・すみえ）。メタ文（今回は・この動画では・最後に）と中身の無い引っ張り（答えは最後に）を書かない。数え方は「第5位…第1位」。禁止記号（── — → … ※ ★ 水平線）を台本に入れない。
- 言い伝えは、WebSearch／WebFetch で確かめられた範囲だけを「昔から〜と言われています」の形で書く。確かめた結果を facts.json に {"言い伝え": [{"文": "台本の文", "確かめた所": "URL か 名前", "確かさ": "広く言われている／出典あり／確かめられず"}], "順位": [...]} の形で書く。
- 締めは問いかけ（5つのうちいくつ当てはまったか）で終える。
"""


def prompt(work, fix):
    neta = json.load(open(os.path.join(work, "neta.json"), encoding="utf-8"))
    kind = neta.get("kind", "short")
    more = "".join(f"\n{i}. {rel(x)}（{what}）" for i, (x, what) in enumerate(extra_docs(), 8))
    gold = {"short": ["short_S001.json", "kiridashi_S008.json"], "cut": ["kiridashi_S008.json", "short_S001.json"], "long": ["long_006.json"]}[kind]
    form = {"short": SHORT_FORM, "cut": CUT_FORM.format(item=neta.get("item", "")), "long": LONG_FORM}[kind]
    rules = LONG_RULES if kind == 'long' else SHORT_RULES
    p = f"""あなたは YouTube チャンネル「金運おきぬ」（財布と暮らしの小物の金運の言い伝え。60代前後の女性が耳と目で見る。語り手はおきぬ）の台本の書き手です。
作業フォルダ {rel(work)} に script.json を書いてください（facts.json も下の決まりで書く）。今回は「{ {'short': '単独のショート', 'cut': '長尺から切り出すショート', 'long': '長尺'}[kind] }」です。

## 先に全部読むファイル（部分読み禁止。手順書は最後の行まで）
1. {rel(os.path.join(CH_DIR, '手順書.md'))}（制作ルール v1.7。§0〜§15 の全部。このチャンネルの決まりの正本。題の型 §8・サムネ §9・長尺の型 §15 を特に）
2. {rel(os.path.join(CH_DIR, 'ショートの型.md'))}（ショートの型 v2：型1・型2 の表と、これから作る案。ショートの時は特に）
3. {rel(os.path.join(work, 'neta.json'))}（この回の小物・悩み・年・「やっていいか」の問い・主人公。ネタ選びが決めた値。書き換えない）
4. {' と '.join(rel(os.path.join(GOLD, g)) for g in gold)}（形と密度の見本。項目名・カットの長さ・subs の切り方を借りる。中身の小物・場面・言い回し・つかみは写さない。ショートの見本は v1 の物語型：項目の形だけ借り、中身の流れはショートの型 v2 に従う）
5. {rel(os.path.join(CH_DIR, 'characters', 'characters.json'))}（絵に出る人。chars に書けるのはこの id だけ。voice は人物ごとの声）
6. {rel(os.path.join(CH_DIR, '禁止表現.txt'))}（使わない言葉）と {rel(os.path.join(CH_DIR, 'yomi.json'))}（読みの表）{more}

## この回（neta.json の要点）
種類：{kind}{('（型' + str(neta.get('型')) + '）') if kind == 'short' and neta.get('型') else ''}／{'場所' if kind == 'long' else '小物'}：{neta.get('小物')}／悩み：{neta.get('悩み')}／主人公の年：{neta.get('年')}／主人公：{neta.get('主人公')}／「やっていいか」の問い：{neta.get('ok_q')}
{('小物の章：' + '・'.join(neta.get('items', []))) if neta.get('items') else ''}{('切り出し元：' + str(neta.get('long')) + '（' + str(neta.get('long_dir')) + '）／小物：' + str(neta.get('item'))) if kind == 'cut' else ''}

## 直近の回（同じ小物・1文目・最初の文字・問い・題を使わない材料。言い換えただけも同じ。§12 の2）
{json.dumps(recent(), ensure_ascii=False, indent=1)}

{rules}{form}
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


def place_pose(work, c):
    """"img_from": "pose:A17" → channels/okinu/assets/poses/A17.jpg を images/<id>.png（1920x1080）に写す。
    image・image_en は消す（残すと make_images_lovart.py が同じ絵を作り直し、run_daily の missing() も絵を頼む）"""
    from PIL import Image
    pid = c["img_from"].split(":", 1)[1]
    src = os.path.join(POSES, pid + ".jpg")
    if not os.path.exists(src):
        sys.exit(f"【止まりました】共有ポーズ絵 {pid} がありません：{rel(src)}")
    os.makedirs(os.path.join(work, "images"), exist_ok=True)
    dst = os.path.join(work, "images", c["id"] + ".png")
    if not os.path.exists(dst):
        Image.open(src).convert("RGB").resize((1920, 1080), Image.LANCZOS).save(dst)
    c.pop("image", None)
    c.pop("image_en", None)


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
        # v1.7：速さ 1.0（声 speedScale 1.0・組み立て tempo 1.0）・間 0.3。1分 320〜340字（001v6 の 0.85／1.1 は物語の型の速さ）
        s.update({"card_theme": "kinun", "tempo": 1.0, "gap": b.get("gap", 0.3), "voice": {"engine": "voicevox", "speaker": 9, "speedScale": 1.0}})
    else:
        s.update({"tempo": (b.get("short") or {}).get("tempo", 1.3), "voice": {"engine": "voicevox", "speaker": 9}})
    # 人物の声（セリフのカットの voice）
    used = sorted({c["voice"] for c in s["cuts"] if c.get("voice")})
    s["voices"] = {k: chars[k]["voice"] for k in used if k in chars}  # スキルの make_voice.py の形（人物の id → VOICEVOX の声の番号）
    voice_names = ["波音リツ"] + sorted({(chars[k].get("voice_name") or "").split("（")[0] for k in used if k in chars} - {""})
    for c in s["cuts"]:
        if str(c.get("img_from", "")).startswith("pose:"):
            place_pose(work, c)  # 共有ポーズ絵：images/<id>.png に写し、image を消す（絵の生成・gate_images・run_daily の missing が見ない）
        elif c.get("image_en"):
            c["image"] = c["image_en"]  # make_images_lovart.py は image を読む（英語のまま渡す）
        if c.get("anim") == "kling" and not c.get("motion"):
            c["motion"] = True  # make_motion_psy.py は motion を見る
        if c.get("motion") and not c.get("anim"):
            c["anim"] = "kling"
        if c.get("motion") and c.get("card") == {"type": "photo"}:
            c.pop("card")  # card が付くと make_motion_psy.py が動かさない。何も載せない photo は不要
    th = s.get("thumb") or {}
    if th.get("layout"):
        s["thumb_kind"] = th["layout"]  # run_daily の record() が produced.json に残す＝サムネの型の履歴（同じ型を続けない）
    narr = [c for c in s["cuts"] if c.get("narration")]
    last_q = narr[-1]["narration"] if narr else ""
    if kind == "long":
        lead = s.get("desc_lead") or f"{last_q}コメントで教えてくださいね。"
        s["desc"] = lead + "\n\n{CHAPTERS}\n\n" + AI_LINES + "\nVOICEVOX:" + "、VOICEVOX:".join(voice_names)
        s.setdefault("tags", ["金運", "金運アップ", neta.get("小物", "")[:10], "風水", "開運", "お金の習慣", "60代", "50代"])
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
        if neta.get("型"):
            s["short_type"] = neta["型"]  # ショートの型 v2（1＝NG3つの数え下げ／2＝1つだけ禁止）
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

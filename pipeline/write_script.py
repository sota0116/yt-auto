# ③台本（設計書 §5③）：Claude（claude -p）に、手順書と facts.json から script.json を書かせる
#   python -X utf8 pipeline\write_script.py <作業フォルダ> --ch job [--fix]
# ・作業フォルダには neta.json（ネタ帳の1行）と facts.json（プログラムが計算した値）が先にあること
# ・書く作業には鍵を渡さない（設計書 §4「作業を2つに分ける」）：子のプロセスから鍵の場所と鍵の環境変数を消して動かす
# ・Claude は書いたあと check_job_script.py を自分で回し、注意が0件になるまで直す。最後にここでもう一度回して確かめる
# ・--fix：gate_script.json（台本ゲートの不合格）を読ませて、不合格の所だけ直させる（設計書 §5④ 書き直しは2回まで）
# ・競合メモ（research.py が毎日書く）も読ませ、試すことを1つ以上取り入れさせる（何を取り入れたかは competitor_note）
# ・学び（learn_job.py が毎日書く。うちの回の数字から）も読ませ、「次の回で試すこと」を1つやらせる（何をやったかは learn_note）
# ・モデルは環境変数 CLAUDE_WRITER_MODEL（無ければ opus）。豆知識を確かめるので、どの型もネット検索を許す（2026-10-29 から）
import argparse, datetime, json, os, shutil, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = os.environ.get("YT_DOCS_DIR", r"C:\Users\koneb\OneDrive\YouTube自動チャンネル")
SECRET_ENV = ("YT_SECRETS_DIR", "GEMINI_API_KEY", "ESTAT_APP_ID", "OPENAI_API_KEY", "UTAGE_API_KEY", "LOVART_ACCESS_KEY",
              "LOVART_SECRET_KEY", "YT_CLIENT_SECRET", "YT_TOKEN_JOB", "YT_TOKEN_SPI", "YT_TOKEN_NIHONGI", "YT_TOKEN_OKINU", "YT_TOKEN_PSY")
MEMO = lambda ch: os.path.join(ROOT, "history", ch, "competitors", "競合メモ.md")  # research.py が毎日書く
LEARN = lambda ch: os.path.join(ROOT, "history", ch, "学び.md")  # learn_job.py が毎日書く（うちの回の数字から）
GOLDEN = {"job": os.path.join(ROOT, "channels", "job", "videos", "001_a4_untenshu_fukushi", "script.json")}
STYLE = {"job": os.path.join(ROOT, "channels", "job", "文体見本_v2.md")}  # 手順書 §0（2026-10-29 の2回目）の書き方の見本。v1 は数字が多すぎたので使わない


def doc(ch, name):
    """手順書の正本は OneDrive。手元では正本を repo の channels/<ch>/ に写してから使う（クラウドは repo の写しを読む）"""
    src, dst = os.path.join(DOCS, "channels", ch, name), os.path.join(ROOT, "channels", ch, name)
    if os.path.exists(src):
        if not os.path.exists(dst) or open(src, "rb").read() != open(dst, "rb").read():
            shutil.copyfile(src, dst)
            print(f"（{name} の正本が新しくなっていたので、repo の写しを更新しました。commit を忘れずに）")
        return dst
    if os.path.exists(dst):
        return dst
    sys.exit(f"【止まりました】{name} が見つかりません（channels/{ch}/）")


def levelup(ch):
    """改善ログ（毎日1つ上げる。2026-10-28）：書く前に最後の「次に上げること」を読ませ、書き終えたら書き手の最後の行を1行足す"""
    return os.path.join(ROOT, "history", ch, "改善ログ.md")


LEVELUP_ASK = """## 改善ログ（毎日1つ上げる・電子ゴミにしない）
- 改善ログがある時は、いちばん下の行の「次に上げること」を、この回に必ず1つ入れる（手順書の決まりの中で）。
- この回が手順書の「電子ゴミの線」に1つでも当たる時は、当たらなくなるまで直してから終える。
- 最後の行に、次の形で1行だけ書く（プログラムが日付と回の名前を付けて改善ログに足す）：
  改善ログ：前の回より良くした所（確かめられる形で）｜次の回で上げること1つ
"""


def levelup_add(ch, work, result):
    """書き手の最後の「改善ログ：」の行を、日付と回の名前を付けて改善ログに足す（書き直しの時は足さない）"""
    line = next((x.strip()[len("改善ログ："):] for x in reversed(result.splitlines()) if x.strip().startswith("改善ログ：")), "")
    if not line:
        print("【メモ】書き手が改善ログの行を書きませんでした")
        return
    p = levelup(ch)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    head = "" if os.path.exists(p) else "# 改善ログ（作るたびに1行。日付｜作った物｜前より良くした所｜次に上げること）\n\n"
    with open(p, "a", encoding="utf-8") as f:
        f.write(f"{head}- {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))):%Y-%m-%d}｜{os.path.basename(work)}｜{line}\n")


def recent(ch, n=9):
    p = os.path.join(ROOT, "history", ch, "produced.json")
    h = json.load(open(p, encoding="utf-8")) if os.path.exists(p) else []
    keep = ("work", "type", "frame", "hook_type", "sub_copy", "line_copy", "title", "titles", "thumb_text", "thumb_kind", "chapters")  # thumb_kind：直近3本と同じ字の型を続けない（手順書 §6）
    return [{k: x.get(k) for k in keep} for x in h[-n:]]


def prompt(work, ch, fix):
    neta = json.load(open(os.path.join(work, "neta.json"), encoding="utf-8"))
    rel = lambda p: os.path.relpath(p, ROOT)
    p = f"""あなたは YouTube チャンネルの台本の書き手です。作業フォルダ {rel(work)} に script.json を書いてください。

## 先に全部読むファイル（部分読み禁止）
1. {doc(ch, '手順書.md')}（このチャンネルの決まりの正本。全部読む）
2. {rel(os.path.join(work, 'neta.json'))}（この回の題・型・骨組み・向ける人）
3. {rel(os.path.join(work, 'facts.json'))}（この回の数字。プログラムが計算した値。ここにない数字・順位・差は書かない。あなたは計算しない）
4. {rel(GOLDEN[ch]) if ch in GOLDEN else '（見本なし）'}（script.json の形の見本。項目名と形だけを借りる。つかみ・言い回し・章立ては写さない。見本には名乗り・「ここまで」・お礼などのメタな文が残っているが、手順書 v3.2 で禁止になったので絶対に写さない）
5. {rel(os.path.join(ROOT, 'channels', ch, 'profile.json'))}（語り手と聞き手の名前）
6. {rel(os.path.join(ROOT, 'channels', ch, '禁止表現.txt'))}（使わない言葉。台本ゲートでも照らす）
7. {rel(MEMO(ch)) if os.path.exists(MEMO(ch)) else '（競合メモはまだ無い）'}（毎日の競合リサーチのまとめ。手順書より下の扱い。借りるのは題材の傾向と型だけ）
8. {rel(os.path.join(ROOT, 'channels', ch, 'characters', 'characters.json'))}（場面の絵に出す決まった登場人物。手順書 §5）
9. {rel(LEARN(ch)) if os.path.exists(LEARN(ch)) else '（学びはまだ無い）'}（うちの回の数字から毎日書く学び。手順書より下、競合メモより上の扱い）
10. {rel(levelup(ch)) if os.path.exists(levelup(ch)) else '（改善ログはまだ無い）'}（作るたびに1行ずつ足す記録。いちばん下の「次に上げること」をこの回に入れる）
11. {rel(STYLE[ch]) if ch in STYLE and os.path.exists(STYLE[ch]) else '（文体見本なし）'}（手順書 §0・§6 の見本。謎の立て方と回収・自分ごとの問いの往復・主役の数字の4拍・聞き手の使いどころ・タイトルとサムネの組み方を借りる。言い回し・例え・ツッコミの文は写さない）

## 直近の回（同じ番号の文・同じつかみの型・同じ骨組みが続かないようにする材料）
{json.dumps(recent(ch), ensure_ascii=False, indent=1)}

## いちばん大事なこと（手順書 §0。2026-10-29 本人「統計を淡々と話してるだけで価値がない」「ドパガキに刺さらない」「最後まで楽しんで見れないと意味がない」、2回目「サムネタイトルも特につまらない」「掛け合いがあることが面白いなの？安直ではないか？」「数字がありすぎても胃もたれしそう」）
- 面白さは掛け合いでも数字の量でもない。次の5つから来る。1と2は毎回入れ、3〜5から1つ以上を足す。
  1. 自分ごと：つかみで見る人に「あなたの〜は？」と問い、締めで答えを出せる形（式・物差し）にして返す。
  2. 1本を貫く謎と回収：つかみで食い違いの謎を1つ立て、章の名前はその手がかりにし、見どころの章で回収する。
  3. 物語（1日・1年・一生を追う）、4. 裏側（外の人が知らない決まり＝豆知識）、5. 判定（締めの前に、割に合うかを1文で言い切る）。
- fun_core を最初に決めて script.json に書く（形は「謎：〜｜自分ごと：〜｜判定：〜」）。
- 数字は胃もたれさせない。主役の数字を3つまで決めて key_numbers に書き（facts.json の値）、どれも 予想→出す→言い直す（物差しを付ける）→反応 の4拍で出す。声に出る統計の数字は1本で8種類まで（型D は12）、豆知識の数字を足して10種類まで（型D は14）。驚きの粒の半分以上は数字の無い物（豆知識・予想が外れる・場面の具体）にする。
- 豆知識を3つ以上、公的なページで確かめて facts.json の 豆知識 に足す（文・出典・url・取得日・原文）。
- 掛け合いは器。聞き手（全カットの2割5分〜4割）は、謎を口にする・予想して外す・条件や仕組みに本音でツッコむ・自分ごとをやって見せる時だけ出す。相づちだけのカットは書かない。ツッコミはその仕事の人には向けない。
- 数字を言ったら、次のカットで定義を続けない。声の断り書きは1本で2回まで。語り手のカットを4つ続けない。しんみりした情緒だけの場面は1本2つまで。
- 驚きの粒のカットには "wow": true、絵のカットなら label（12字まで）も付ける（効果音と大きな字が出る）。各章に2つ以上。
- タイトルとサムネ（手順書 §6）：統計の報告・出典・作り方を売らず、謎・判定・自分ごとを気持ちの言葉で売る。タイトル3案は別々の型、数字は1案に1つまで、出典の尾（「（厚生労働省の統計）」）は付けない。謎は一息で読める形で言い切り、タイトルでは順位より「高い・安い・同じ」で言う。答え（結論）はサムネにもタイトルにも書かない。サムネは thumb_kind（判定・落差・自分ごと・謎・裏側）を直近3本と変え、3つの字で同じ結論を言い直さず、問いか手がかりを1つずつ持たせる。数字は3つの字で1つまで。thumb_bg は漫画くらいに誇張した表情と、謎を語る小道具1つ。
- 正確さの決まり（facts.json にない数字を書かない・離職率は産業の数字・「逆転」は記録がある時だけ・書かないこと）・メタの禁止・答えの先送りの禁止は、これまでどおり守る。

## 書き方
- 手順書 §3 のこの回の型・骨組み、§4 の全回共通の決まり、§5 の絵、§6 のタイトル3案とサムネの文字、§7 の概要欄、§10 の点検の項目を全部守る。
- 手順書 §4 の「メタの禁止」を守る。名乗り・動画や回のこと・「ここからは」「次の章では」「見ていきます」のような進み方の言葉・聞き手の名前を呼ぶこと・お礼を書かず、中身（数字・場面・問い）だけで進める。例外は登録の呼びかけ・LINE の案内・コメントへの問いかけの決まった文だけ。
- 絵のカットの image は、日本語で場面を1〜2文。読める文字・ロゴ・実在の会社は書かない。
- 場面の絵は、人が何かをしている場面を主にする（手順書 §5 の登場人物）。人のいない部屋・物だけの絵は、場面の絵の3割まで。
  人を出すカットには characters.json の人物から合う人を選び、カットに "chars": ["kenji"] と書く（1カット2人まで）。image にもその人の名前（例「健二が」）を書き、年齢・髪・服は書かない（設定画でそろえる）。
  登場人物の名前は声では言わない（絵だけに出る人。聞き手・語り手とは別）。同じ回で同じ人を何度も出してよい。
  characters.json に合う人がいない時は、script.json の "characters" にその回だけの人物を足す（{{"id": {{"name": "日本語の呼び方", "desc_en": "英語1文で年齢・体格・髪・服"}}}}）。2カット以上に出る人は必ずこうする。
- サムネ（手順書 §6）。どの型も次の項目を script.json に書く（型D は判定の形、ほかは場面の形がa案。もう1つの形がb案）。
  - thumb_bg：登場人物（chars）の顔が大きく、気持ちが分かる表情で写る絵のカットの id。そのカットの image に次を書く（手順書 §6 の絵）。サムネを外から見て「この人に何が起きた？」と思える場面にする。
    ・表情：漫画のリアクションくらいに誇張した1つ（目を見開く・口を大きく開ける・冷や汗・頭を抱える・給与明細を握って青ざめる）。無表情・穏やかな顔・遠くを見る顔にしない。
    ・話を1枚で語る物：その回の謎が分かる小道具か状況を1つ（深夜を指す時計・薄い給与明細・満車の駐車場など）。人が立っているだけにしない。顔は画面の高さの4割以上。
    ・背景は暗めで色は濃く、主役の顔と体にだけ光が当たる。明るいベージュや白っぽい背景にしない。
    ・主役は画面の真ん中の高さ、上と下の2割ずつをあける（上の帯と下の大きい字が顔にかからないため）。顔は真ん中か右寄り、左と下に字を置く空き。
    ・比べる回（複数の仕事を並べる型A など）は、比べる人を2〜3人横に並べ、それぞれ違う表情（得意げ・青ざめる）にした絵のカット1枚を thumb_bg にする（並べる人数・それぞれの仕事の服装と道具・全員の表情を image に書く）。各人の札に使う順位・数字は facts.json にある物だけ（札の描画は未実装。入るまでは並べた絵だけを使う）。
  - thumb_top：上の見出し（場面の形は横幅の6割以上に大きく出る）・左上の札。16字以内（例「30年 給料が上がらない」「同じ会社員でも」）。頭に数字を置くと札の赤い箱に入る。
  - thumb_text：いちばん大きい字。10字以内で、答えを伏せた問いか言い切り（例「上がらない本当の理由」「時給は何位？」）。thumb_lines で割り方を指定できる（場面の形は2つまで・判定の形は3つまで。数字の所か最後の部分が強調の色になる）。
  - thumb_band：判定の形の下の帯。28字以内。謎を一段深くする一言（例「年収は144職種の真ん中なのに」）。作り方の説明（「統計で〜」「〜を並べた」）にしない。
  - thumb_kind：字の型（判定・落差・自分ごと・謎・裏側のどれか。手順書 §6）。
  - サムネの字に「AI」「PR」は入れない。数字は facts.json にある物だけ。「逆転」「意外」はタイトルと同じ決まり。
- 型A・B・C のタイトル（｜の前）とサムネ（thumb_top・thumb_text）で「1位」「最下位」「〇位」と言う時は、何の中の順位かを同じ所に書く（例「バス運転手は6職種で年収1位」「144職種で一番長く働く」）。
  比べた仕事が数個だけなのに「年収1位」とだけ書くと、全部の仕事の中の1位に読める（2026-10-28 本人「バス運転手と大型トラック運転手、どちらも年収1位なの？」）。
- 図のカットは chart に、facts.json の値を指す形で書く（見本の chart の kind と項目名を使う）。
- 2026-10-28 本人の指摘（スキル references/16。見本・前の回に無くても守る）：
  - 図のカット（chart。組み立てで動くグラフ・カードになる）を、まとめの章も含めて章ごとに1つ以上置く（止まった絵だけの章を作らない）。
  - 見どころ：この回でいちばん驚く数字が出るカット1つに "peak": true を書き、chart・label・strong のうち2つ以上を付ける。締めの6カット・LINE の案内・登録の呼びかけには付けない。
  - 「答えは最後に」「このあと発表します」「後半でお見せします」「最後まで見てください」のような、答えを先に延ばすだけの文は書かない。章の終わりの引きは、次の章で分かることを中身で言う。
- 競合メモがある時は「うちの次の回で試すこと」から、この回の型に合う物を1つ以上、手順書の決まりの中で取り入れる（タイトル3案・サムネの文字・概要欄・台本の構成のどれか）。
  手順書とぶつかる案は採らない。競合の文・言い回しは写さない。取り入れた物を script.json の competitor_note に1行で書く（無ければ「なし（理由）」）。
- 学びがある時は「分かったこと」を全部守り、「次の回で試すこと」を、この回で手順書の決まりの中でやる（競合メモと同じ所を変える時は、学びを先にする）。
  やった事を script.json の learn_note に1行で書く（「試す_10-29：」のように学びの印から始める。この回の型でできない時は「なし（理由）」）。
- 概要欄 desc の LINE のリンクは {{LINE_URL}}、チャプターは {{CHAPTERS}} と書く（あとでプログラムが置き換える）。
- 出典が要る事実は WebSearch・WebFetch で公的な一次資料を確かめ、facts.json の「出典」に URL と取得日を足してよい。統計の数字は facts.json の値だけを使う。豆知識（手順書 §0）は、公的機関か業界団体のページで確かめた物だけを facts.json の 豆知識 に足し、その「文」にある数字だけを声で言ってよい。個人のブログ・噂・実在の会社の話は使わない。

## 台本ゲートの採点（書いたあと、判定のAI（Claude Sonnet）がこの線で見る）
- スマホで見ていて、退屈したら10秒で次の動画に行く人の前提で、10点満点。最初の30秒が7点以上、全部の章が5点以上で合格。山場は驚きがあるかを見る。説明・断り書き・相づちが続いて驚きが無い所は減点される。
- 最初の30秒は、聞く人自身の損得に結びつく問いや数字で始める。山場の答え（どの職業が何位に動くか）は、手順書の決まりの範囲で山場まで取っておく。
- 各章の終わりの1〜2文で、次の章を聞きたくなる引きを作る。画面を見ないと分からない言い方（「この棒」「濃い色の所」など）はしない。
- 数字が続いて覚えきれない所（胃もたれ）と、つかみで立てた謎が回収されないまま終わる回は減点される。
- 1案目のタイトルとサムネの字は「押したくなるか」でも採点されるが、点は記録に残すだけで合否には使わない（競合で確かめたら、伸びた回を当てられなかった）。タイトルとサムネの良し悪しは公開後の数字で決める。決まり（§6）は守る。

## 終わる前に必ずやること
- `python -X utf8 pipeline/check_job_script.py {rel(work)}` を回し、NG が0件・注意も0件になるまで script.json を直す（pub_date が空という注意だけは残す。公開日は在庫に入れる時にプログラムが入れる）。
- 最後に、字数・カット数・聞き手の割合・LINE の案内と登録の呼びかけの位置（%）を1行ずつ書いて終える。

""" + LEVELUP_ASK
    if neta["type"] == "D":  # 見本（001）は型A-4 なので、型D の図と項目の形はここで渡す
        p += """
## 型D の script.json（見本に無い所）
- 図の kind は次だけ。値は全部プログラムが facts.json から取るので、chart には数字を書かない。
  - score_bars {"shown": 下から出す本数}：採点結果の章だけ。棒は facts.json の点のグラフ
  - source_card {"test": "K1" など, "items": ["利益剰余金", ...]（省略可）}：facts.json の出典カードの表の値。6秒以上映す（same_as で続ける）
  - test_compare {"test": "K1" など, "mode": "伸び率" か "値" か 前後の名前（例 "利益剰余金_兆円"）}：確かめ1つの比べ
  - trend_lines {"group": facts.json のグラフの名前, "series": [系列を1〜2本], "highlight": 強調の系列, "title": 見出し（省略可）}
  - big_text {"text": 言い切らない所の大きな字}
  - quiz {"question": 問い, "choices": [A, B]}（説2と説4の章の頭）・tokuten {}（LINE の案内の所）
- 章：つかみ・前置きのカットには chapter を付けない。以降は「AIが最初にやったこと」→「AIで検証① 〈facts.json の説の名前そのまま〉」〜 →「決め手の統計」2〜3章 →「ここまでのおさらい」→「採点結果」→「結論」→「まとめ」。
- line_copy は2つの番号の並び（例 [1, 3]）。1回目と2回目で別の文にする。おさらいでは説の名前を facts.json のとおりに言う。
"""
    kind = neta["type"] if neta["type"] in ("B", "C") else neta.get("frame")
    if kind in ("A-1", "A-3", "B", "C"):  # 見本（001）は型A-4 なので、この型の図と項目の形はここで渡す
        p += f"""
## 型{kind} の script.json（見本に無い所）
- 図の kind は次だけ。値は全部プログラムが facts.json から取るので、chart には数字を書かない。どの回も tokuten {{}}（LINE の案内の所）を入れる。
"""
        p += {
            "A-1": """  - reasons {"shown": 下（5位）から出した数 0〜5}：辞める理由5つ。shown は1つずつ増やし、減らさない。5位から順に声で言う
  - quiz {}（問いと3つの選択肢は facts.json のクイズ。shown が4になる前に置く）
  - job_vs_all {"measures": [facts.json の棒グラフの物差しから1〜3つ], "highlight": 強調の物差し}
- 最初の理由を出す前に、facts.json の「声の前置き」か「声の前置き_より正確な言い方」を言う。定義と出典（koyodoko_r7_t12）も声で言う。
""",
            "A-3": """  - compare_table {"items": [facts.json の比べる項目], "shown": 出した行の数, "values": [数字を出す項目（highlight と合わせて3つまで）], "highlight": facts.json の山場の項目}
  - quiz {"question": 問い, "choices": [A, B]}
- 「〇〇の方が高い（低い・長い・短い）」と言う所は、facts.json の項目ごとの勝った方と合わせる。離職率は比べない。タイトルに「逆転」を使うのは facts.json の逆転を使えるが true の時だけ。
""",
            "B": """  - bars {"graph": facts.json のグラフの番号（0から）}
  - quiz {"question": 問い, "choices": [A, B]}
- frame は facts.json の使える骨組みから1つ（B-1・B-2・B-3）。章の名前に、その骨組みの時点（例「半年後」）を入れ、山場の章では山場の統計の声か言い直しを言う。
- A社の場面の絵のカットには "reenact": true と "badge": "イメージ" を付ける（図は付けない）。A社の物語の中で使う数字は、facts.json の統計とグラフと premise_numbers の値だけ。
- 統計の数字を言う章では、その章の最初の数字の前に facts.json の「つなぎ」の文のどちらかを言う。「下がった人」を言う時は「上がった人」も言う。
- 前置きで A社の呼び名を1回だけ言い、そのカットの label に呼び名を書く（名札）。タイトル3案とも題の呼び名のどちらかを入れる（頭の職業名の決まりは型B には無い）。
""",
            "C": """  - vs_national {"items": [facts.json の全国平均と並べる表の物差しから1〜3つ], "highlight": 強調の物差し}
  - age_line {"measure": "年収_万円" か "月の労働時間" か "時給に直した額_円", "marks": [値を出す年齢階級を5つまで]}
  - quiz {"question": 問い, "choices": [A, B]}
- frame は facts.json の骨組みで使えるの物（C-1 か C-3）。C-3 は声_年収の差を声で言う。
- 前置きで主役の呼び方を1回だけ言い、そのカットの label に呼び方を書く（名札）。
""",
        }[kind]
        if kind in ("B", "C"):
            p += "- script.json に cast（主役の見た目を1文）を書き、主役は \"characters\" に \"hero\" として足して、主役が出るカットに \"chars\": [\"hero\"] を付ける。thumb_bg は主役の表情が大きく写る絵のカットにする。\n"
    if fix:
        g = json.load(open(os.path.join(work, "gate_script.json"), encoding="utf-8"))
        bad = {k: v for k, v in g.items() if isinstance(v, dict) and v.get("合格") is False}
        p += f"""
## 今回は書き直し
台本ゲート（別の会社のAIの点検）で、次の項目が不合格でした。不合格の所だけを直し、ほかは変えないでください。
点検の「直すなら」は案です。手順書の決まり（数字の数・LINE の案内の位置・禁止表現・facts.json にない数字を書かない など）とぶつかる案は採らず、決まりの中で同じ狙いを達する直し方にしてください。
{json.dumps(bad, ensure_ascii=False, indent=1)}
"""
    return p


def main():
    a = argparse.ArgumentParser()
    a.add_argument("work")
    a.add_argument("--ch", default="job")
    a.add_argument("--fix", action="store_true")
    a = a.parse_args()
    work = os.path.abspath(a.work)
    # 2026-10-29 から全部の型で豆知識（手順書 §0）を公的なページで確かめるので、どの型もネット検索を許す
    tools = ["Read", "Write", "Edit", "Glob", "Grep", "Bash(python -X utf8 pipeline/check_job_script.py:*)", "WebSearch", "WebFetch"]
    env = {k: v for k, v in os.environ.items() if k not in SECRET_ENV}
    env["YT_SECRETS_DIR"] = os.path.join(ROOT, "_no_secrets_here")  # 書く作業から鍵の場所を見えなくする
    cmd = [shutil.which("claude") or "claude", "-p", "--model", os.environ.get("CLAUDE_WRITER_MODEL", "opus"),
           "--allowedTools", *tools, "--permission-mode", "acceptEdits", "--output-format", "json"]
    if os.path.isdir(DOCS):  # 手元だけ（クラウドには OneDrive が無いので、repo の channels\<ch>\手順書.md を読む）
        cmd += ["--add-dir", DOCS]
    r = subprocess.run(cmd, cwd=ROOT, env=env, input=prompt(work, a.ch, a.fix), capture_output=True, text=True, encoding="utf-8", timeout=3600)
    log = os.path.join(work, "_write.log")
    open(log, "a", encoding="utf-8").write(r.stdout + "\n" + r.stderr + "\n")
    out = {}
    try:
        out = json.loads(r.stdout)
        print(out.get("result", "")[-1500:])
        print(f"（Claude：{out.get('num_turns')}手・{out.get('duration_ms', 0) / 60000:.1f}分）")
    except json.JSONDecodeError:
        print(r.stdout[-1500:], r.stderr[-800:])
    if r.returncode != 0 or not os.path.exists(os.path.join(work, "script.json")):
        sys.exit("【止まりました】台本を書けませんでした（_write.log を見る）")
    if not a.fix:
        levelup_add(a.ch, work, out.get("result", ""))
    chk = subprocess.run([sys.executable, "-X", "utf8", os.path.join(ROOT, "pipeline", "check_job_script.py"), work],
                         capture_output=True, text=True, encoding="utf-8")
    print("\n".join(chk.stdout.strip().splitlines()[-3:]))
    sys.exit(0 if chk.returncode == 0 else 1)


if __name__ == "__main__":
    main()

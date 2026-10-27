# ③台本（設計書 §5③）：Claude（claude -p）に、手順書と facts.json から script.json を書かせる
#   python -X utf8 pipeline\write_script.py <作業フォルダ> --ch job [--fix]
# ・作業フォルダには neta.json（ネタ帳の1行）と facts.json（プログラムが計算した値）が先にあること
# ・書く作業には鍵を渡さない（設計書 §4「作業を2つに分ける」）：子のプロセスから鍵の場所と鍵の環境変数を消して動かす
# ・Claude は書いたあと check_job_script.py を自分で回し、注意が0件になるまで直す。最後にここでもう一度回して確かめる
# ・--fix：gate_script.json（台本ゲートの不合格）を読ませて、不合格の所だけ直させる（設計書 §5④ 書き直しは2回まで）
# ・競合メモ（research.py が毎日書く）も読ませ、試すことを1つ以上取り入れさせる（何を取り入れたかは competitor_note）
# ・モデルは環境変数 CLAUDE_WRITER_MODEL（無ければ opus）。調べものが要る型（B・C・D）はネット検索も許す
import argparse, json, os, shutil, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = os.environ.get("YT_DOCS_DIR", r"C:\Users\koneb\OneDrive\YouTube自動チャンネル")
SECRET_ENV = ("YT_SECRETS_DIR", "GEMINI_API_KEY", "ESTAT_APP_ID", "OPENAI_API_KEY", "UTAGE_API_KEY", "LOVART_ACCESS_KEY",
              "LOVART_SECRET_KEY", "YT_CLIENT_SECRET", "YT_TOKEN_JOB", "YT_TOKEN_SPI")
MEMO = lambda ch: os.path.join(ROOT, "history", ch, "competitors", "競合メモ.md")  # research.py が毎日書く
GOLDEN = {"job": os.path.join(ROOT, "channels", "job", "videos", "001_a4_untenshu_fukushi", "script.json")}


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


def recent(ch, n=9):
    p = os.path.join(ROOT, "history", ch, "produced.json")
    h = json.load(open(p, encoding="utf-8")) if os.path.exists(p) else []
    keep = ("work", "type", "frame", "hook_type", "sub_copy", "line_copy", "title", "chapters")
    return [{k: x.get(k) for k in keep} for x in h[-n:]]


def prompt(work, ch, fix):
    neta = json.load(open(os.path.join(work, "neta.json"), encoding="utf-8"))
    rel = lambda p: os.path.relpath(p, ROOT)
    research = neta["type"] in ("B", "C", "D")
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

## 直近の回（同じ番号の文・同じつかみの型・同じ骨組みが続かないようにする材料）
{json.dumps(recent(ch), ensure_ascii=False, indent=1)}

## 書き方
- 手順書 §3 のこの回の型・骨組み、§4 の全回共通の決まり、§5 の絵、§6 のタイトル3案とサムネの文字、§7 の概要欄、§10 の点検の項目を全部守る。
- 手順書 §4 の「メタの禁止」を守る。名乗り・動画や回のこと・「ここからは」「次の章では」「見ていきます」のような進み方の言葉・聞き手の名前を呼ぶこと・お礼を書かず、中身（数字・場面・問い）だけで進める。例外は登録の呼びかけ・LINE の案内・コメントへの問いかけの決まった文だけ。
- 絵のカットの image は、日本語で場面を1〜2文。読める文字・ロゴ・実在の会社は書かない。
- 場面の絵は、人が何かをしている場面を主にする（手順書 §5 の登場人物）。人のいない部屋・物だけの絵は、場面の絵の3割まで。
  人を出すカットには characters.json の人物から合う人を選び、カットに "chars": ["kenji"] と書く（1カット2人まで）。image にもその人の名前（例「健二が」）を書き、年齢・髪・服は書かない（設定画でそろえる）。
  登場人物の名前は声では言わない（絵だけに出る人。聞き手・語り手とは別）。同じ回で同じ人を何度も出してよい。
  characters.json に合う人がいない時は、script.json の "characters" にその回だけの人物を足す（{{"id": {{"name": "日本語の呼び方", "desc_en": "英語1文で年齢・体格・髪・服"}}}}）。2カット以上に出る人は必ずこうする。
- サムネ（手順書 §6）。どの型も次の項目を script.json に書く（型D は判定の形、ほかは場面の形がa案。もう1つの形がb案）。
  - thumb_bg：登場人物（chars）の顔が大きく、気持ちが分かる表情で写る絵のカットの id。顔は真ん中か右寄り、左と下に字を置く空きがある構図で、そのカットの image を書く（サムネを外から見て「この人に何が起きた？」と思える場面）。
  - thumb_top：上の見出し・左上の札。16字以内（例「30年 給料が上がらない」「同じ会社員でも」）。頭に数字を置くと札の赤い箱に入る。
  - thumb_text：いちばん大きい字。10字以内で、答えを伏せた問いか言い切り（例「上がらない本当の理由」「時給は何位？」）。thumb_lines で割り方を指定できる（場面の形は2つまで・判定の形は3つまで。数字の所か最後の部分が強調の色になる）。
  - thumb_band：判定の形の下の帯。28字以内。何を確かめたか＋答えが気になる一言（例「政府の統計で5人の容疑者を採点 → 意外な1位」）。
  - thumb_q：答えを伏せる回は true（どちらの形にも右上に「？」の箱が出る。型D は1位の扱いで決まるので書かなくてよい）。答えをタイトルで言っている回は書かない。
  - サムネの字に「AI」「PR」は入れない。数字は facts.json にある物だけ。「逆転」「意外」はタイトルと同じ決まり。
- 図のカットは chart に、facts.json の値を指す形で書く（見本の chart の kind と項目名を使う）。
- 競合メモがある時は「うちの次の回で試すこと」から、この回の型に合う物を1つ以上、手順書の決まりの中で取り入れる（タイトル3案・サムネの文字・概要欄・台本の構成のどれか）。
  手順書とぶつかる案は採らない。競合の文・言い回しは写さない。取り入れた物を script.json の competitor_note に1行で書く（無ければ「なし（理由）」）。
- 概要欄 desc の LINE のリンクは {{LINE_URL}}、チャプターは {{CHAPTERS}} と書く（あとでプログラムが置き換える）。
- {'出典が要る事実は WebSearch・WebFetch で公的な一次資料を確かめ、facts.json の「出典」に URL と取得日を足してよい。数字そのものは facts.json の値だけを使う。' if research else 'ネットは使わない（この型は facts.json の値だけで書く）。'}

## 台本ゲートの採点（書いたあと、別の会社のAIがこの線で見る）
- 30〜40代の会社員が通勤中に耳だけで聞く前提で、10点満点。最初の30秒が7点以上、全部の章が5点以上で合格。山場は驚きがあるかを見る。
- 最初の30秒は、聞く人自身の損得に結びつく問いや数字で始める。山場の答え（どの職業が何位に動くか）は、手順書の決まりの範囲で山場まで取っておく。
- 各章の終わりの1〜2文で、次の章を聞きたくなる引きを作る。画面を見ないと分からない言い方（「この棒」「濃い色の所」など）はしない。

## 終わる前に必ずやること
- `python -X utf8 pipeline/check_job_script.py {rel(work)}` を回し、NG が0件・注意も0件になるまで script.json を直す（pub_date が空という注意だけは残す。公開日は在庫に入れる時にプログラムが入れる）。
- 最後に、字数・カット数・聞き手の割合・LINE の案内と登録の呼びかけの位置（%）を1行ずつ書いて終える。
"""
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
    neta = json.load(open(os.path.join(work, "neta.json"), encoding="utf-8"))
    tools = ["Read", "Write", "Edit", "Glob", "Grep", "Bash(python -X utf8 pipeline/check_job_script.py:*)"]
    if neta["type"] in ("B", "C", "D"):
        tools += ["WebSearch", "WebFetch"]
    env = {k: v for k, v in os.environ.items() if k not in SECRET_ENV}
    env["YT_SECRETS_DIR"] = os.path.join(ROOT, "_no_secrets_here")  # 書く作業から鍵の場所を見えなくする
    cmd = [shutil.which("claude") or "claude", "-p", "--model", os.environ.get("CLAUDE_WRITER_MODEL", "opus"),
           "--allowedTools", *tools, "--permission-mode", "acceptEdits", "--output-format", "json"]
    if os.path.isdir(DOCS):  # 手元だけ（クラウドには OneDrive が無いので、repo の channels\<ch>\手順書.md を読む）
        cmd += ["--add-dir", DOCS]
    r = subprocess.run(cmd, cwd=ROOT, env=env, input=prompt(work, a.ch, a.fix), capture_output=True, text=True, encoding="utf-8", timeout=3600)
    log = os.path.join(work, "_write.log")
    open(log, "a", encoding="utf-8").write(r.stdout + "\n" + r.stderr + "\n")
    try:
        out = json.loads(r.stdout)
        print(out.get("result", "")[-1500:])
        print(f"（Claude：{out.get('num_turns')}手・{out.get('duration_ms', 0) / 60000:.1f}分）")
    except json.JSONDecodeError:
        print(r.stdout[-1500:], r.stderr[-800:])
    if r.returncode != 0 or not os.path.exists(os.path.join(work, "script.json")):
        sys.exit("【止まりました】台本を書けませんでした（_write.log を見る）")
    chk = subprocess.run([sys.executable, "-X", "utf8", os.path.join(ROOT, "pipeline", "check_job_script.py"), work],
                         capture_output=True, text=True, encoding="utf-8")
    print("\n".join(chk.stdout.strip().splitlines()[-3:]))
    sys.exit(0 if chk.returncode == 0 else 1)


if __name__ == "__main__":
    main()

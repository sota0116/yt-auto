# ショート②台本（手順書 §12）：Claude（claude -p）に、手順書と facts.json からショートの script.json を書かせる
#   python -X utf8 pipeline\write_short.py <作業フォルダ>
# ・作業フォルダには short_pick.py が書いた facts.json が先にあること
# ・書く作業には鍵を渡さない（write_script.py と同じ。子のプロセスから鍵の場所と鍵の環境変数を消す）
# ・Claude は書いたあと check_short.py を自分で回し、NG が0件になるまで直す。最後にここでもう一度回して確かめる
# ・これまでのショートの数字（short_learn.py の shorts_learn.json）の、点の高い3本と低い3本を渡す（PDCA）
# ・モデルは環境変数 CLAUDE_SHORT_MODEL（無ければ sonnet。ショートは短く、型が決まっているため）
import json, os, shutil, subprocess, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from write_script import ROOT, DOCS, SECRET_ENV, doc

HIST = os.path.join(ROOT, "history", "job", "shorts.json")


def recent(n=6):
    h = json.load(open(HIST, encoding="utf-8")) if os.path.exists(HIST) else []
    return [{k: x.get(k) for k in ("title", "hook", "banner")} for x in h[-n:]]


def learned():
    p = os.path.join(ROOT, "history", "job", "shorts_learn.json")
    L = json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {}
    if not L.get("点の高い3本"):
        return "（まだ数字が少ないので、手順書 §12 のとおりに書く）"
    return ("点の高い3本の hook・帯・タイトルの作り方（問いか言い切りか・数字の出し方・字数）を借り、点の低い3本の作り方は避ける。文はそのまま写さない。"
            "平均視聴率が低い回が多い時は、hook と2カット目をより短く、1位までの間を詰める。\n"
            + json.dumps({k: L[k] for k in ("全体", "点の高い3本", "点の低い3本")}, ensure_ascii=False, indent=1))


def prompt(work):
    rel = lambda p: os.path.relpath(p, ROOT).replace("\\", "/")
    return f"""あなたは YouTube ショートの台本の書き手です。作業フォルダ {rel(work)} に script.json を書いてください。

## 先に全部読むファイル（部分読み禁止）
1. {rel(doc('job', '手順書.md'))}（チャンネルの決まりの正本。§2 の語り手と聞き手、§4 の書かないこととメタの禁止、§12 ショートを必ず守る）
2. {rel(os.path.join(work, 'facts.json'))}（この回の数字。プログラムが計算した値。ここにない数字・順位・差は書かない。あなたは計算しない）
3. {rel(os.path.join(ROOT, 'channels', 'job', '禁止表現.txt'))}（使わない言葉）

## 直近のショート（同じ hook・同じ言い回し・同じ帯が続かないようにする材料）
{json.dumps(recent(), ensure_ascii=False, indent=1)}

## これまでのショートの数字（PDCA。short_learn.py が毎日まとめる。点＝再生×平均視聴率＋登録者の増加×200）
{learned()}

## script.json の形
{{
 "format": "short",
 "title": "タイトル（§12。最後にハッシュタグ2〜3）",
 "tags": ["年収", "仕事", ...],
 "desc_lead": "説明文の1段落目。コメントへの問いかけ1文",
 "banner": ["大きい字7字まで", "小さい字10字まで"],
 "hook_type": "数字 か 問い",
 "cuts": [
  {{"id": "s01", "speaker": "narrator", "narration": "声の文", "hook": "5字まで\\n5字まで", "screen": {{"hook": true}}}},
  {{"id": "s02", "speaker": "narrator", "narration": "...", "screen": {{"chart": 0, "show": 0}}}},
  {{"id": "s03", "speaker": "narrator", "narration": "5位は、〇〇。", "screen": {{"chart": 0, "show": 1}}}},
  ...
 ]
}}
- id は s01 から順に。speaker は narrator（語り手）か listener（聞き手）。
- screen.chart は facts.json の charts の番号（0から）。show は出す棒の本数（rank は5位から下から順に出るので、1にすると5位だけ）。本数は減らさず、最後のカットまでに全部出す。
- 声の文の数字は facts.json の「声の値」「声_」「声」の言い方をそのまま使う。画面の値（小数）を声で言わない。
- 1位の名前は、1位の棒を出すカット（show が最後の本数になるカット）まで言わない（hook・帯・タイトルにも書かない）。
- 声は合成音声で読むので、読み間違えやすい職業名には、カットに "tts_text"（読みやすいひらがな混じりの文）を書いてよい。

## 終わる前に必ずやること
- `python -X utf8 pipeline/check_short.py {rel(work)}` を回し、NG が0件になるまで script.json を直す。注意もできるだけ0件にする。
- 最後に、字数・カット数・聞き手の割合を1行で書いて終える。
"""


def main():
    work = os.path.abspath(sys.argv[1])
    tools = ["Read", "Write", "Edit", "Glob", "Grep", "Bash(python -X utf8 pipeline/check_short.py:*)"]
    env = {k: v for k, v in os.environ.items() if k not in SECRET_ENV}
    env["YT_SECRETS_DIR"] = os.path.join(ROOT, "_no_secrets_here")
    cmd = [shutil.which("claude") or "claude", "-p", "--model", os.environ.get("CLAUDE_SHORT_MODEL", "sonnet"),
           "--allowedTools", *tools, "--permission-mode", "acceptEdits", "--output-format", "json"]
    r = subprocess.run(cmd, cwd=ROOT, env=env, input=prompt(work), capture_output=True, text=True, encoding="utf-8", timeout=1800)
    open(os.path.join(work, "_write.log"), "a", encoding="utf-8").write(r.stdout + "\n" + r.stderr + "\n")
    try:
        out = json.loads(r.stdout)
        print(out.get("result", "")[-800:])
        print(f"（Claude：{out.get('num_turns')}手・{out.get('duration_ms', 0) / 60000:.1f}分）")
    except json.JSONDecodeError:
        print(r.stdout[-800:], r.stderr[-800:])
    if r.returncode != 0 or not os.path.exists(os.path.join(work, "script.json")):
        sys.exit("【止まりました】ショートの台本を書けませんでした（_write.log を見る）")
    chk = subprocess.run([sys.executable, "-X", "utf8", os.path.join(ROOT, "pipeline", "check_short.py"), work],
                         capture_output=True, text=True, encoding="utf-8")
    print(chk.stdout.strip())
    sys.exit(0 if chk.returncode == 0 else 1)


if __name__ == "__main__":
    main()

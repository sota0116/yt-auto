# ③台本（心理学ch・2026-10-27 新設）：Claude（claude -p）に、研究を調べて facts.json を、手順書と見本（001）から script.json を書かせる
#   python -X utf8 pipeline\write_script_psy.py <作業フォルダ> --ch psy [--fix]
# ・作業フォルダには neta.json（ネタ帳の1行。pick_neta_psy.py が置く）が先にあること
# ・研究は WebSearch・WebFetch で調べさせ、facts.json に DOI か URL と「言ってよい範囲」を書かせる（手順書 §8）
# ・書く作業には鍵を渡さない（write_script.py と同じ。子のプロセスから鍵の場所と鍵の環境変数を消して動かす）
# ・Claude は書いたあと check_psy_script.py を自分で回し、NG が0件になるまで直す。最後にここでもう一度回して確かめる
# ・--fix：gate_script.json（台本ゲートの不合格）を読ませて、不合格の所だけ直させる（書き直しは2回まで。run_daily.py が数える）
# ・モデルは環境変数 CLAUDE_WRITER_MODEL（無ければ opus）
import argparse, json, os, shutil, subprocess, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from write_script import ROOT, DOCS, SECRET_ENV, doc  # noqa: E402

GOLDEN = os.path.join(ROOT, "channels", "psy", "golden", "script_001.json")
GOLDEN_FACTS = os.path.join(ROOT, "channels", "psy", "golden", "facts_001.md")


def recent(ch, n=9):
    """直近の回の題・章・使った研究（同じ研究・同じつかみが続かないように）と、出ていれば公開後の数字（見張り watch.py の metrics.json。
    7日後が無ければ72時間後。直す所＝見る人が離れた所。毎日の PDCA：前の回の数字を次の回の書き手が読む。2026-10-27）"""
    p = os.path.join(ROOT, "history", ch, "metrics.json")
    metrics = json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {}
    p = os.path.join(ROOT, "history", ch, "shorts_metrics.json")
    shorts = json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {}
    out = []
    for name in ("uploaded.json", "produced.json"):
        p = os.path.join(ROOT, "history", ch, name)
        for x in json.load(open(p, encoding="utf-8")) if os.path.exists(p) else []:
            if not x.get("work"):
                continue
            o = next((o for o in out if o["work"] == x["work"]), None)
            if o is None:
                out.append({"work": x["work"], "area": x.get("type"), "title": x.get("title"), "chapters": x.get("chapters"), "studies": x.get("studies")})
            else:  # uploaded.json には章と研究が無い。produced.json の分で埋める（2026-10-28 まで研究が書き手に届いていなかった）
                for k, v in (("chapters", x.get("chapters")), ("studies", x.get("studies"))):
                    o[k] = o.get(k) or v
    for o in out:
        m = metrics.get(o["work"], {})
        row = m.get("d7") if (m.get("d7") or {}).get("views") is not None else m.get("h72")
        if row and row.get("views") is not None:
            o["数字"] = {"いつ": "7日後" if row is m.get("d7") else "72時間後",
                        **{k: row.get(k) for k in ("views", "impressions", "ctr", "averageViewPercentage", "subscribersGained", "直す所") if row.get(k) is not None}}
        # ショートの数字（shorts_watch.py の shorts_metrics.json）。つかみの文と上の帯の字ごとに、どれが見られたかを次のショートで比べる（2026-10-28）
        sm = shorts.get(o["work"], {})
        srow = sm.get("d7") if (sm.get("d7") or {}).get("views") is not None else sm.get("h72")
        if srow and srow.get("views") is not None:
            o["ショートの数字"] = {"いつ": "7日後" if srow is sm.get("d7") else "72時間後", "つかみ": sm.get("hook"), "帯": sm.get("band"),
                               **{k: srow.get(k) for k in ("views", "averageViewPercentage", "averageViewDuration", "subscribersGained") if srow.get(k) is not None}}
    return out[-n:]


def extra_docs(ch):
    """あれば読む物：競合メモ（research.py が毎日書く）と、学び（weekly.py が毎週書く。数字から分かったこと）"""
    out = []
    for p, what in ((os.path.join(ROOT, "history", ch, "competitors", "競合メモ.md"),
                     "競合メモ（毎日の競合リサーチ。§3〜7 の型と「次の回で試すこと」を、手順書の決まりの中で1つ取り入れてよい。文・題は写さない）"),
                    (os.path.join(ROOT, "history", ch, "学び.md"),
                     "学び（うちの回の数字から週報が書いた物。手順書の決まりの中で守る。手順書とぶつかる時は手順書が勝つ）")):
        if os.path.exists(p):
            out.append((p, what))
    return out


def prompt(work, ch, fix):
    rel = lambda p: os.path.relpath(p, ROOT).replace("\\", "/")
    more = "".join(f"\n{i}. {rel(x)}（{what}）" for i, (x, what) in enumerate(extra_docs(ch), 8))
    p = f"""あなたは YouTube チャンネル「しずくの心理学」の台本の書き手です。作業フォルダ {rel(work)} に facts.json と script.json を書いてください。

## 先に全部読むファイル（部分読み禁止）
1. {rel(doc(ch, '手順書.md'))}（このチャンネルの決まりの正本。全部読む）
2. {rel(os.path.join(work, 'neta.json'))}（この回の題・場面・切り口・研究の手がかり・参考にした競合の題）
3. {rel(GOLDEN)}（1本目の台本。形と密度の見本。項目名・カットの長さ・つかみと締めの決まった文・研究の話し方・カード・動かす絵の付け方を借りる。中身の場面・言い回しは写さない）
4. {rel(GOLDEN_FACTS)}（1本目で使った研究と「言ってよい範囲」の書き方の見本）
5. {rel(os.path.join(ROOT, 'channels', ch, 'profile.json'))}（チャンネルの設定）
6. {rel(os.path.join(ROOT, 'channels', ch, '禁止表現.txt'))}（使わない言葉。台本ゲートでも照らす）
7. {rel(os.path.join(ROOT, 'channels', ch, 'characters', 'characters.json'))}（主役 hero）{more}

## 直近の回（同じ研究を中心にしない・同じつかみの場面を使わない材料）
数字がある回は、平均視聴率（averageViewPercentage）とクリック率（ctr）の高い回の、つかみの形・章の引き・タイトルとサムネの言葉の型を参考にする。
「直す所」（見る人が離れた所）と同じ作りは避ける。数字が2本に満たない時は、数字で決めつけない。
{json.dumps(recent(ch), ensure_ascii=False, indent=1)}

## やること
1. 研究を調べる：neta.json の angle と hint を手がかりに、WebSearch・WebFetch で、この回の場面のわけを説明できる研究を5〜9個選ぶ。
   査読のある論文か、大学・学会の公式の解説だけ。論文は DOI を確かめて書く（DOI の無い物は url）。読めた範囲（抄録・公式の解説）から外れることは書かない。
   手順書 §8 の形で facts.json を書く。may_say には「台本で言ってよい範囲」、kind には実験・観察・総説のどれかを書く。
   手がかりの研究が見つからない・合わない時は、同じ切り口の別の研究にしてよい。研究で説明できない題なら、題を研究に合わせて少し変えてよい（neta.json は書き換えない）。
2. 台本を書く：手順書 §2〜§7 の決まりを全部守って script.json を書く。研究の結果を言うカットには "study": "S1" のように facts.json の key を付ける。
   研究の結果は may_say の範囲だけで言う。観察研究を「〇〇すると△△になる」と言わない。効果の約束・医療の話はしない。
   サムネの背景（THUMB カット）は手順書 §5・§6 の通り：主役のしずくの顔に、その回の気持ち（驚き・不安・困惑・ほっとした顔のどれか1つ）をはっきり出し、
   画面の真ん中の高さに（上と下の2割をあける）、暗めの背景に主役だけ光を当てて描く絵を image に書く。人間は描かない。比べる回は色ちがいのしずくを並べて札を付ける絵にする。thumb の文字は2段（上＝何の話か・下＝答え）。
   2026-10-28 本人の指摘（スキル references/16。見本 001 に無くても守る。見本の B20・C35・I11c の言い方は写さない）：
   ・章ごとに motion のカット（動く絵）を1つ以上置く。
   ・見どころ：この回でいちばん面白い場面（この回だけの研究の結果か場面）のカット1つに "peak": true を書き、motion・label・strong のうち2つ以上を付ける。締めの6カットには付けない。
   ・「その答えは後半で」「答えは次の章で」「最後まで見て」のような、答えを先に延ばすだけの文は書かない。締めのお礼は「見てくださって、ありがとうございました。」（「最後まで」を付けない）。
3. ショートを書く：手順書 §10 の決まりで、script.json に "short" を書く。サムネの B案（thumb の "lines_b"。§6）も忘れずに。
4. 終わる前に必ず `python -X utf8 pipeline/check_psy_script.py {rel(work)}` と `python -X utf8 pipeline/make_short_psy.py {rel(work)} --check` を回し、
   どちらも NG が0件になるまで直す（注意は、直せる物は直す）。
5. 最後に、語りの字数・カット数・章の名前・使った研究（key と cite）・登録の呼びかけの位置（%）・ショートの字数とカット数を1行ずつ書いて終える。

## 台本ゲートの採点（書いたあと、別のAIがこの線で見る）
- 夜ひとりの時間に、お茶を飲みながら耳で聞く60代の女性として10点満点。最初の30秒が7点以上、全部の章が5点以上で合格。
- 最初の30秒は、見る人の毎日の1場面の小さな謎で始める。各章の終わりの1文で、次を聞きたくなる引きを作る。
- 画面を見ないと分からない言い方（「この表」「ここに書いてある」）はしない。
"""
    if fix:
        g = json.load(open(os.path.join(work, "gate_script.json"), encoding="utf-8"))
        bad = {k: v for k, v in g.items() if isinstance(v, dict) and v.get("合格") is False}
        p += f"""
## 今回は書き直し
台本ゲート（別のAIの点検）で、次の項目が不合格でした。不合格の所だけを直し、ほかは変えないでください。facts.json の研究を直してよいのは、
「研究と合っていない」と言われた所だけです。点検の「直すなら」は案です。手順書の決まりとぶつかる案は採らず、決まりの中で同じ狙いを達する直し方にしてください。
「言いすぎ」を言われた時は、言われた文を直したあと、同じ研究の話をしている文（同じ "study" のカットと、まとめ・タイトル・サムネ・概要欄）を全部読み直し、
同じ種類の強い言い方（「はっきり」「〜が変わる」「年を重ねると〜になる」・観察研究の因果の言い方）があれば、同じように may_say の範囲へ弱める（点検は毎回全文を見るため）。
{json.dumps(bad, ensure_ascii=False, indent=1)}
"""
    return p


def main():
    a = argparse.ArgumentParser()
    a.add_argument("work")
    a.add_argument("--ch", default="psy")
    a.add_argument("--fix", action="store_true")
    a = a.parse_args()
    work = os.path.abspath(a.work)
    tools = ["Read", "Write", "Edit", "Glob", "Grep", "WebSearch", "WebFetch", "Bash(python -X utf8 pipeline/check_psy_script.py:*)",
             "Bash(python -X utf8 pipeline/make_short_psy.py:*)"]
    env = {k: v for k, v in os.environ.items() if k not in SECRET_ENV + ("YT_TOKEN_PSY",)}
    env["YT_SECRETS_DIR"] = os.path.join(ROOT, "_no_secrets_here")  # 書く作業から鍵の場所を見えなくする
    cmd = [shutil.which("claude") or "claude", "-p", "--model", os.environ.get("CLAUDE_WRITER_MODEL", "opus"),
           "--allowedTools", *tools, "--permission-mode", "acceptEdits", "--output-format", "json"]
    if os.path.isdir(DOCS):  # 手元だけ（クラウドには OneDrive が無いので、repo の channels\psy\手順書.md を読む）
        cmd += ["--add-dir", DOCS]
    r = subprocess.run(cmd, cwd=ROOT, env=env, input=prompt(work, a.ch, a.fix), capture_output=True, text=True, encoding="utf-8", timeout=5400)
    log = os.path.join(work, "_write.log")
    open(log, "a", encoding="utf-8").write(r.stdout + "\n" + r.stderr + "\n")
    try:
        out = json.loads(r.stdout)
        print(out.get("result", "")[-1500:])
        print(f"（Claude：{out.get('num_turns')}手・{out.get('duration_ms', 0) / 60000:.1f}分）")
    except json.JSONDecodeError:
        print(r.stdout[-1500:], r.stderr[-800:])
    sp = os.path.join(work, "script.json")
    if r.returncode != 0 or not os.path.exists(sp):
        sys.exit("【止まりました】台本を書けませんでした（_write.log を見る）")
    # type は area（アップの記録 uploaded.json の type になり、見張りと週報が area ごとに数字を比べる）
    s = json.load(open(sp, encoding="utf-8"))
    area = json.load(open(os.path.join(work, "neta.json"), encoding="utf-8")).get("area")
    if area and s.get("type") != area:
        s["type"] = area
        json.dump(s, open(sp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    if not s.get("short"):
        print("【メモ】ショートの台本（short）がありません。この回はショートを作りません")
    chk = subprocess.run([sys.executable, "-X", "utf8", os.path.join(ROOT, "pipeline", "check_psy_script.py"), work],
                         capture_output=True, text=True, encoding="utf-8")
    print("\n".join(chk.stdout.strip().splitlines()[-6:]))
    sys.exit(0 if chk.returncode == 0 else 1)


if __name__ == "__main__":
    main()

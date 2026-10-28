# 毎日の学び（毎日 01:17 の競合リサーチのあと。research.yml）：うちの回の数字から、次の回で試すことを1つ決める
#   python -X utf8 pipeline\learn_job.py job [--no-claude]
# ・2026-10-28 本人「毎日レベル上げてね」。週報の改善案は本人の返事待ちで止まるので、手順書の決まりの中で済む改善は毎日ここで回す
# ・材料はプログラムが集める（history\<ch>\学び\<日付>.json）：回ごとの台本ゲートの点・公開ページの再生・72時間後と7日後の数字・
#   試したこと（learn_note）・競合メモから取り入れた物（competitor_note）。YouTube には触らない（読むのも見張り watch.py が取った記録だけ）
# ・まとめは Claude（claude -p）。鍵は渡さない（write_script.py と同じ分け方）。書くのは history\<ch>\学び.md（30行まで）と日付の写し
#   中身：分かったこと（2本以上の根拠つき）／次の回で試すこと（1つだけ）／試したことの結果（続ける・やめる・まだ数字待ち）
# ・台本の書き手（write_script.py）が毎回読み、試すことを1つやって learn_note に残す。次の日にここで結果を見る
# ・手順書は変えない（手順書を変える案は週報へ）
# ・--no-claude：集めるだけ
import argparse, datetime, json, os, shutil, subprocess, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from notify import jload, now, issue
from run_daily import jsave
from write_script import SECRET_ENV, LEARN, MEMO, doc

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KEEP = ("work", "made", "type", "frame", "hook_type", "title", "thumb_text", "competitor_note", "learn_note", "台本ゲートの点")
NUM = ("views", "impressions", "ctr", "averageViewPercentage", "averageViewDuration", "subscribersGained", "直す所")


def gather(ch):
    """回ごとに、作った時の記録と、公開後の数字を1行にまとめる（Claude が割り算をしなくて済むように、1日あたりの再生はここで出す）"""
    up = {e["work"]: e for e in jload(os.path.join(ROOT, "history", ch, "uploaded.json"), []) if e.get("work") and not e.get("retired")}
    metrics = jload(os.path.join(ROOT, "history", ch, "metrics.json"), {})
    rows = []
    for p in jload(os.path.join(ROOT, "history", ch, "produced.json"), []):
        r = {k: p.get(k) for k in KEEP if p.get(k) is not None}
        e = up.get(p["work"], {})
        if e.get("published_at"):
            days = (now() - datetime.datetime.fromisoformat(e["published_at"])).total_seconds() / 86400
            r["公開"] = e["published_at"][:16]
            r["公開からの日数"] = round(days, 1)
            r["公開ページの再生"] = e.get("views_now")
            r["1日あたりの再生（計算）"] = round((e.get("views_now") or 0) / max(days, 0.5), 1)
            r["今のタイトル"] = e.get("title_now")
        elif e:
            r["公開"] = f"まだ（予約 {(e.get('publish_at') or '')[:16]}）"
        m = metrics.get(p["work"], {})
        for k in ("h72", "d7"):
            if m.get(k):
                r[{"h72": "72時間後", "d7": "7日後"}[k]] = {x: m[k].get(x) for x in NUM if m[k].get(x) is not None}
        rows.append(r)
    n = lambda key: sum(1 for r in rows if key in r)
    return {"日付": now().isoformat(timespec="minutes"),
            "母数": {"作った回": len(rows), "公開した回": n("公開からの日数"), "72時間後の数字がある回": n("72時間後"),
                    "7日後の数字がある回": n("7日後"), "台本ゲートの点がある回": n("台本ゲートの点")},
            "回ごと": rows}


def prompt(ch, path, learn):
    rel = lambda p: os.path.relpath(p, ROOT).replace("\\", "/")
    today = now().date().isoformat()
    sm = os.path.join(ROOT, "history", ch, "shorts_learn.json")
    return f"""あなたは YouTube チャンネルの改善の担当です。毎日1回、うちの回の数字を見て「学び」を書き直します。
読むのは、このチャンネルの台本の書き手（AI）です。書き手は毎回これを読み、「次の回で試すこと」を1つだけやって、何をやったかを learn_note に残します。
日本語で、短い文で書きます。

## 先に全部読むファイル（部分読み禁止）
1. {doc(ch, '手順書.md')}（このチャンネルの決まりの正本。学びは全部この決まりの中に収める）
2. {rel(path)}（今日プログラムが集めた物。回ごとの台本ゲートの点・公開ページの再生・72時間後と7日後の数字・試したこと。ここにない数字は書かない）
3. {rel(learn) if os.path.exists(learn) else '（前の学びは無い。今日が初回）'}（前の日までの学び。続いている事は残す）
4. {rel(MEMO(ch)) if os.path.exists(MEMO(ch)) else '（競合メモは無い）'}（毎日の競合リサーチのまとめ。うちの数字が足りない時の、試すことの材料）
5. {rel(sm) if os.path.exists(sm) else '（ショートの学びは無い）'}（ショートの数字から分かった事。プログラムが書く。長尺のタイトルとサムネの言葉の参考だけ）

## 数字の見方
- 台本ゲートの点：別の会社のAIが、通勤中に耳で聞く人の気持ちで付けた10点満点（最初の30秒・章ごと・山場）。台本を書いた日に出る、いちばん早い数字。
- 公開ページの再生と1日あたりの再生：公開から2〜3日の早い数字。公開の時刻と曜日で揺れるので、これだけで良し悪しを決めない。
- 72時間後・7日後：見張りが YouTube の分析から取った数字。クリック率（ctr）はタイトルとサムネ、平均視聴率（averageViewPercentage）と直す所は台本の良し悪し。
- 型（A〜D）が違う回どうしは、同じ型どうしより差が出やすい。比べる時は型を添える。

## 書く物：{rel(learn)}（全部を書き直す。30行まで。見出しは ## で、この順）
1. 分かったこと：うちの回の数字から言えることだけ。1行に1つ、根拠（回の名前と数字・何本中何本か）をつける。2本以上で同じ向きの事だけ。1本だけの傾向は書かない。
   前の学びで「続ける」になった試しは、ここに移す（書き手は毎回これを守る）。数字が足りない時は「まだ数字が足りない（{today}）」の1行。
2. 次の回で試すこと（1つだけ）：見出しの次の行に「試す_{today[5:]}：」で始めて、何をどう変えるかを1〜2文で。次に、どの数字で良し悪しを見るか（例「台本ゲートの最初の30秒の点」「72時間後のクリック率」）を1行。
   ・材料の順：うちの数字で低い所（台本ゲートの点の低い章・直す所・クリック率）＞前の試しの続き＞競合メモの「うちの次の回で試すこと」でまだ試していない物。
   ・前の学びの「次の回で試すこと」が、まだどの回の learn_note にも出ていない時は、同じ物をそのまま残す（作る日が1日おきなので、毎日替えない）。
   ・手順書の決まりの中でできる事だけ（字数・数字の数・LINE の案内の位置・禁止表現・facts.json にない数字を書かない、は変えない）。手順書とぶつかる案は書かない。
   ・どの型でもできる事にする。型を選ぶ時は「型Aの回なら」のように書く。
3. 試したことの結果：learn_note に「試す_」がある回ごとに1行。何を試し、どの数字がどうだったか、判定（続ける／やめる／まだ数字待ち）。
   続けるは、試した回が2本以上あり、同じ型の試していない回より良い時だけ。悪かった時はやめる。どちらでもない時はまだ数字待ち（7日後の数字が出たら決める）。

## 決まり
- 数字は {rel(path)} の値だけ。割り算をした時は「計算」と書く。母数（何本中何本）を必ず添える。
- 結果を約束しない。「伸びる」と言い切らない。
- 水平線（--- など）は使わない。「—」「→」の多用もしない。
- 書き手は AI なので、「〇〇を意識する」のような中身の無い言い方はしない。何をどう書くかを具体的に書く。
- 最後に、書いた物と同じ全文を {rel(os.path.join(os.path.dirname(path), today + '.md'))} にも保存して終える。
"""


def main():
    a = argparse.ArgumentParser()
    a.add_argument("ch", choices=["job"])
    a.add_argument("--no-claude", action="store_true")
    a = a.parse_args()
    os.environ["TZ"] = "Asia/Tokyo"
    d = os.path.join(ROOT, "history", a.ch, "学び")
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, now().date().isoformat() + ".json")
    data = gather(a.ch)
    jsave(path, data)
    print(f"{a.ch}：{data['母数']}")
    if a.no_claude:
        return
    learn = LEARN(a.ch)
    before = os.path.getmtime(learn) if os.path.exists(learn) else 0
    env = {k: v for k, v in os.environ.items() if k not in SECRET_ENV}
    env["YT_SECRETS_DIR"] = os.path.join(ROOT, "_no_secrets_here")
    cmd = [shutil.which("claude") or "claude", "-p", "--model", os.environ.get("CLAUDE_RESEARCH_MODEL", "opus"),
           "--allowedTools", "Read", "Write", "Glob", "Grep", "--permission-mode", "acceptEdits", "--output-format", "json"]
    r = subprocess.run(cmd, cwd=ROOT, env=env, input=prompt(a.ch, path, learn), capture_output=True, text=True,
                       encoding="utf-8", timeout=1200)
    logd = os.path.join(ROOT, "_research", a.ch)  # commit しない所
    os.makedirs(logd, exist_ok=True)
    open(os.path.join(logd, "_learn.log"), "a", encoding="utf-8").write(r.stdout[-4000:] + "\n" + r.stderr[-2000:] + "\n")
    if r.returncode != 0 or not os.path.exists(learn) or os.path.getmtime(learn) <= before:
        issue(f"【止まりました】{a.ch}：毎日の学びを書けませんでした", f"{now():%m/%d %H:%M} 台本は前の学びで書きます。集めた物は {os.path.relpath(path, ROOT)}")
        sys.exit(1)
    lines = open(learn, encoding="utf-8").read().splitlines()
    print(f"学びを書きました（{len(lines)}行）")
    print("\n".join(lines[:40]))


if __name__ == "__main__":
    main()

# 通知の段（設計書 §4「最後に必ず通知の段を動かす」・§3 外の見張り）：成功でも失敗でも最後に動かす
#   python -X utf8 pipeline\notify.py daily <ch> --slot first|retry
# ・止まった時は Issue を立てる。件名は「【止まりました】<ch>：<理由>」。同じ件名の開いた Issue があれば、そこに1行足すだけ
# ・Healthchecks.io：成功したら合図。02:07（first）の失敗では合図を送らず、08:07（retry）か 17:37（late）も失敗した時だけ /fail を送る
#   Gemini の1日の回数の上限で止まった（last_run の「待ち」）時は、17:37（late）でも止まった時だけ Issue にする
#   受け口の URL は環境変数 HC_DAILY_JOB・HC_DAILY_SPI・HC_WATCH（無ければ送らない）。PAUSED の間も成功の合図は送る
# ・見張り役どうしの見張り：毎日の実行は「見張り（watch）が48時間ない」、見張りは「毎日の実行が26時間ない」、どちらも「週報が8日ない」で Issue
# ・Issue は gh コマンド（GitHub Actions の GH_TOKEN）で立てる。手元で gh が無い時は画面に出すだけ
import argparse, datetime, json, os, shutil, subprocess, sys, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JST = datetime.timezone(datetime.timedelta(hours=9))
# 止まった理由ごとの「やること」（設計書 §9 の表。Issue の本文の最初の行）
TODO = [("台本ゲート", "何もしなくてよい。同じ理由が3日続いたら、Claude に見せる"),
        ("絵", "何もしなくてよい。同じ理由が3日続いたら、Claude に見せる"),
        ("完成", "何もしなくてよい。同じ理由が3日続いたら、Claude に見せる"),
        ("ハッシュ", "PC で Claude Code にこの Issue を貼って「このIssueを直して」と言う"),
        ("MONTHLY_CAP_YEN", "上限額を確かめる。上げてよければ Variables の MONTHLY_CAP_YEN を書き換える"),
        ("上限", "上限額を確かめる。上げてよければ Variables の MONTHLY_CAP_YEN を書き換える"),
        ("ログイン", "PC で Claude に「YouTube のログインをやり直して」と言う（約5分）"),
        ("予約", "週報の「今週やること」にある予約をする（道1なら約25分、道2なら約45分）"),
        ("72時間", "何もしなくてよい（次のネタで作り続けている）。同じことが3日続いたら、Claude に見せる"),
        ("在庫が少ない", "何もしなくてよい（詰まった回は速いモードで作る）。3日続いたら、Claude に見せる"),
        ("Lovart", "何もしなくてよい（無料モードに戻してある）")]


def now():
    return datetime.datetime.now(JST)


def jload(p, d):
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else d


def issue(title, line):
    title = title[:120]
    body_first = next((t for k, t in TODO if k in title), "PC で Claude Code にこの Issue を貼って「このIssueを直して」と言う")
    if not shutil.which("gh") or not os.environ.get("GH_TOKEN"):
        print("【Issue（手元なので出すだけ）】", title, "\n", line)
        return
    r = subprocess.run(["gh", "issue", "list", "--state", "open", "--search", f'"{title}" in:title', "--json", "number,title"],
                       capture_output=True, text=True, encoding="utf-8")
    same = [x for x in json.loads(r.stdout or "[]") if x["title"] == title]
    if same:
        subprocess.run(["gh", "issue", "comment", str(same[0]["number"]), "--body", line])
    else:
        subprocess.run(["gh", "issue", "create", "--title", title, "--body", f"やること：{body_first}\n\n{line}"])


def ping(env, suffix=""):
    url = os.environ.get(env)
    if not url:
        return
    try:
        urllib.request.urlopen(url.rstrip("/") + suffix, timeout=20)
    except Exception as e:
        print("Healthchecks に合図を送れませんでした：", type(e).__name__)


def stale(hb, key, hours):
    t = hb.get(key)
    return t is None or now() - datetime.datetime.fromisoformat(t) > datetime.timedelta(hours=hours)


def daily(ch, slot):
    r = jload(os.path.join(ROOT, "history", ch, "last_run.json"), {})
    stopped = r.get("stopped")
    paused = bool(stopped) and stopped.startswith("PAUSED")
    when = now().strftime("%m/%d %H:%M")
    if not r:
        stopped = "毎日の実行が記録を残さずに終わりました（司令塔より前で落ちた）"
    if stopped and r.get("途中"):  # 時間の枠で区切っただけ（絵の順番待ちなど）。失敗ではないので、見張りには「動いている」と伝える
        print(f"途中で区切りました。次の実行で続きから作る（Issue にしない）：{stopped}")
        ping(f"HC_DAILY_{ch.upper()}")
    elif stopped and r.get("待ち") and slot != "late":
        print(f"Gemini の回数の上限で待ち。17:37 の実行で続きから作る（Issue にしない）：{stopped}")
    elif stopped and not paused:
        reason = stopped.split("：")[0].split("（")[0]
        issue(f"【止まりました】{ch}：{reason}", f"{when}（{slot}）{stopped}\n在庫 {r.get('在庫', '?')}本・今月の制作費 {r.get('今月の制作費_円', '?')}円")
        if slot in ("retry", "late"):
            ping(f"HC_DAILY_{ch.upper()}", "/fail")
    else:
        ping(f"HC_DAILY_{ch.upper()}")
    # 詰まった時の決まり（run_daily.py の説明の4・5。2026-10-29）
    for w in r.get("長く止まって飛ばした回", []):
        issue(f"【止まりました】{ch}：72時間終わらない回を飛ばした", f"{when}（{slot}）{w}。次のネタで作り続けています")
    if slot == "first" and isinstance(r.get("在庫"), int) and r["在庫"] <= 2:  # 1日1回だけ（02:07）
        issue(f"【在庫が少ない】{ch}", f"{when} 在庫 {r['在庫']}本（今回作った {len(r.get('made', []))}本）。止まった理由：{stopped or 'なし'}")
    hb = jload(os.path.join(ROOT, "history", "heartbeat.json"), {})
    if hb.get("watch") and stale(hb, "watch", 48):
        issue("【止まりました】見張り：48時間動いていません", f"{when} 毎日の実行（{ch}）が見つけました。最後の見張り：{hb.get('watch')}")
    if stale(hb, "weekly", 24 * 8) and hb.get("weekly"):
        issue("【止まりました】週報：8日動いていません", f"{when} 最後の週報：{hb.get('weekly')}")


def main():
    a = argparse.ArgumentParser()
    a.add_argument("kind", choices=["daily"])  # 見張り（watch.py）は自分で Issue と合図を出す。週報（weekly）の通知は、その段を作る時に足す
    a.add_argument("ch")
    a.add_argument("--slot", default="first", choices=["first", "retry", "late"])
    a = a.parse_args()
    if a.kind == "daily":
        daily(a.ch, a.slot)


if __name__ == "__main__":
    main()

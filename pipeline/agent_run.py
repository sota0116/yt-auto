# 「Claude が1本作る」チャンネルをクラウドで動かす（.github/workflows/agent.yml。2026-10-31 本人「kakure・shimei も github の無料にして」）
#   python -X utf8 pipeline/agent_run.py pick <ch>        … 続きを作るか、新しく作るか、何もしないかを決める（GITHUB_OUTPUT に書く）
#   python -X utf8 pipeline/agent_run.py prompt <ch>      … 指示書を channels/<ch>/_prompt.md に作る
#   python -X utf8 pipeline/agent_run.py title <ch> "題"   … 題が過去の回の言い換えでないかを、記録の題で確かめる（作る段には YouTube の鍵を渡さないため）
#   python -X utf8 pipeline/agent_run.py finish <ch>      … upload.json を置いた回を上げて、公開の予約を入れる
# ・PC の auto_long_v5.ps1 ＋ auto_long_pick_v4.py のクラウド版。決め方は同じ（途中の回があれば続き・在庫が目標より少なければ新しく）
# ・作る段（Claude）と上げる段を分ける：作る段はネットの調べ物をするので、YouTube の鍵・Release の鍵には触れないようにする
import datetime, glob, json, os, re, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import long_day_guard as g
from title_guard import check as title_check, similar

JST = datetime.timezone(datetime.timedelta(hours=9))
TARGET = int(os.environ.get("AGENT_STOCK_TARGET") or 6)
BUDGET_MIN = int(os.environ.get("AGENT_MINUTES") or 270)
CHS = {"kakure": {"upload": "upload_kakure.py", "is_long": lambda n: bool(re.match(r"\d", n))},
       "shimei": {"upload": "upload_shimei.py", "is_long": lambda n: n.startswith("L")}}


def now():
    return datetime.datetime.now(JST)


def videos(ch):
    return os.path.join(ROOT, "channels", ch, "videos")


def records(ch):
    for p in glob.glob(os.path.join(ROOT, "history", ch, "*uploaded.json")):
        for h in json.load(open(p, encoding="utf-8")):
            if isinstance(h, dict) and not h.get("missing") and not h.get("retired"):
                yield p, h


def stock(ch):
    """(在庫の本数, 予約が入っている日)。これから公開される横動画だけを数える"""
    days = set()
    for p, h in records(ch):
        at = h.get("published_at") or h.get("publish_at")
        if at and g.is_long(p, h):
            d = datetime.datetime.fromisoformat(at.replace("Z", "+00:00"))
            d = d if d.tzinfo else d.replace(tzinfo=JST)
            if d > now():
                days.add(d.astimezone(JST).date().isoformat())
    return len(days), sorted(days)


def unfinished(ch):
    for name in sorted(os.listdir(videos(ch))):
        f = os.path.join(videos(ch), name, "_auto_run.md")
        if CHS[ch]["is_long"](name) and os.path.exists(f):
            if not re.search(r"^## (完了|中止)", open(f, encoding="utf-8").read(), re.M):
                return os.path.join(videos(ch), name)
    return None


def waiting_upload(ch):
    """upload.json があって、まだ上げていない回。横動画を先に"""
    w = [os.path.dirname(p) for p in glob.glob(os.path.join(videos(ch), "*", "upload.json"))
         if not os.path.exists(os.path.join(os.path.dirname(p), "uploaded.json"))]
    return sorted(w, key=lambda d: (not CHS[ch]["is_long"](os.path.basename(d)), d))


def output(**kw):
    print(kw, flush=True)
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as f:
            f.writelines(f"{k}={v}\n" for k, v in kw.items())


def pick(ch):
    r = unfinished(ch)
    n, _ = stock(ch)
    if r:
        cnt = os.path.join(r, "_cloud_runs.txt")
        runs = int(open(cnt).read() or 0) + 1 if os.path.exists(cnt) else 1
        open(cnt, "w").write(str(runs))
        if runs >= 6:  # 止めない。4回で1本ぐらいの見込みなので、6回を超える時は見てもらう
            from notify import issue
            issue(f"【止まりました】{ch}：1本が {runs} 回の実行でも終わらない", f"{now():%m/%d %H:%M} {os.path.basename(r)}。_auto_run.md は暗号の保存の中にあります")
        output(run="true", resume=r, why=f"途中の回の続き（{runs}回目）")
    elif n < TARGET:
        output(run="true", resume="", why=f"在庫 {n} 本（目標 {TARGET} 本）")
    else:
        output(run="false", resume="", why=f"在庫 {n} 本で目標に届いている")


def prompt(ch):
    resume = os.environ.get("AGENT_RESUME") or "なし（新しく作る）"
    if resume.startswith(ROOT):
        resume = os.path.relpath(resume, ROOT).replace("\\", "/")
    t = open(os.path.join(ROOT, "agent", "prompt_common.md"), encoding="utf-8").read() + "\n" + \
        open(os.path.join(ROOT, "agent", f"prompt_{ch}.md"), encoding="utf-8").read()
    _, taken = stock(ch)
    end = now() + datetime.timedelta(minutes=BUDGET_MIN - 20)
    rep = f"channels/{ch}/_reports/{now():%Y%m%d_%H%M}.md"
    os.makedirs(os.path.join(ROOT, os.path.dirname(rep)), exist_ok=True)
    for k, v in {"CH": ch, "RESUME": resume, "NOW": now().strftime("%Y-%m-%d %H:%M"), "DEADLINE": end.strftime("%H:%M"),
                 "REPORT": rep, "TAKEN": "、".join(taken) or "なし"}.items():
        t = t.replace("{{" + k + "}}", v)
    p = os.path.join(ROOT, "channels", ch, "_prompt.md")
    open(p, "w", encoding="utf-8").write(t)
    output(report=rep)


def title(ch, t):
    others = [h.get("title") for _, h in records(ch) if h.get("title")]
    for r, o in similar(t, others)[:3]:
        print(f"{r:.2f}  {o}")
    title_check(t, others)
    print("OK（言い換えになっている題はありません）")


def finish(ch):
    from notify import issue
    made, bad = [], []
    for w in waiting_upload(ch):
        name = os.path.basename(w)
        r = subprocess.run([sys.executable, "-X", "utf8", os.path.join(ROOT, "pipeline", CHS[ch]["upload"]), w, "--go"], cwd=ROOT,
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        print(r.stdout[-1500:], r.stderr[-500:], flush=True)
        with open(os.path.join(w, "_upload.log"), "a", encoding="utf-8") as f:
            f.write(f"\n### {now().isoformat(timespec='seconds')}\n{r.stdout}\n{r.stderr}\n")
        (made if r.returncode == 0 else bad).append(name)
        if r.returncode:
            issue(f"【止まりました】{ch}：上げられなかった回があります", f"{now():%m/%d %H:%M} {name}：{(r.stdout + r.stderr).strip()[-300:]}")
    p = os.path.join(ROOT, "history", ch, "last_run.json")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    json.dump({"ch": ch, "ended": now().isoformat(timespec="seconds"), "made": made, "上げられなかった": bad, "在庫": stock(ch)[0]},
              open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"上げた {len(made)} 本・上げられなかった {len(bad)} 本・在庫 {stock(ch)[0]} 本", flush=True)


def main():
    cmd, ch = sys.argv[1], sys.argv[2]
    if ch not in CHS:
        sys.exit(f"【止まりました】知らないチャンネル：{ch}")
    if cmd == "title":
        title(ch, sys.argv[3])
    else:
        {"pick": pick, "prompt": prompt, "finish": finish}[cmd](ch)


if __name__ == "__main__":
    main()

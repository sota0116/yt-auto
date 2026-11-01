# ショートの1日分（手順書 §12）：題選び → 台本 → 点検 → 声 → 画面 → 組み立て →（自動公開がオンの時だけ）明日の予約
#   python -X utf8 pipeline\run_shorts.py [--n 2] [--no-upload] [--routine-only --at 2026-11-03T18:10]
# ・統計ショートを先に作り、後ろの枠を1日の流れに回す（本数は shorts_learn.json の判定か profile.json の routine_per_day）。1日の流れが作れない時は、その枠を統計ショートに戻す
# ・本数と予約の時刻は profile.json の shorts（per_day・times・auto_publish）。auto_publish が false の間は作るだけ（本人のOKの後に true にする）
# ・作業フォルダは channels\job\shorts\<日時>_<種類>\（git に入れない）。使った題は history\job\shorts.json
# ・台本の点検で NG が残った時は1回だけ書き直させ、それでも NG ならその本は捨てて次の題へ（題は使ったことにする）
import argparse, datetime, json, os, subprocess, sys, time
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = [sys.executable, "-X", "utf8"]
JST = datetime.timezone(datetime.timedelta(hours=9))
HIST = os.path.join(ROOT, "history", "job", "shorts.json")


def step(*args, env=None):
    r = subprocess.run([*PY, *args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", env={**os.environ, **(env or {})})
    print((r.stdout + r.stderr).strip()[-1200:], flush=True)
    return r


def record(work, fx, sc, ok, why=""):
    h = json.load(open(HIST, encoding="utf-8")) if os.path.exists(HIST) else []
    h.append({"work": os.path.basename(work), "topic_id": fx["topic_id"], "kind": fx["kind"], "measure": fx["measure"],
              "title": (sc or {}).get("title"), "hook": ((sc or {}).get("cuts") or [{}])[0].get("hook"), "banner": (sc or {}).get("banner"),
              "ok": ok, "why": why, "made_at": datetime.datetime.now(JST).isoformat(timespec="seconds")})
    json.dump(h, open(HIST, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def one(i, slot, upload):
    stamp = datetime.datetime.now(JST).strftime("%Y%m%d_%H%M")
    r = step("pipeline/short_pick.py", "--out", os.path.join("channels", "job", "shorts", f"{stamp}_{i}"))
    work = os.path.join(ROOT, json.loads(r.stdout.strip().splitlines()[-1])["work"])
    fx = json.load(open(os.path.join(work, "facts.json"), encoding="utf-8"))
    load = lambda: json.load(open(os.path.join(work, "script.json"), encoding="utf-8")) if os.path.exists(os.path.join(work, "script.json")) else None
    if step("pipeline/write_short.py", work).returncode and step("pipeline/write_short.py", work).returncode:
        record(work, fx, load(), False, "台本の点検で NG が残った")
        return f"×{fx['topic_id']}（台本）"
    for args in (("pipeline/make_voice_vv.py", "make", work, "--ch", "job"), ("pipeline/short_charts.py", work), ("pipeline/build_short_job.py", work)):
        if step(*args).returncode:
            record(work, fx, load(), False, f"{args[0]} で止まった")
            return f"×{fx['topic_id']}（{os.path.basename(args[0])}）"
    record(work, fx, load(), True)
    if upload and slot:
        if step("pipeline/short_upload.py", work, "--at", slot, "--go").returncode:
            return f"△{load()['title']}（作ったがアップで止まった）"
        return f"○{load()['title']}（予約 {slot}）"
    return f"○{load()['title']}（作っただけ：{os.path.relpath(work, ROOT)}）"


def routine(i, slot, upload):
    """1日の流れ（手順書 §12）。どの段で止まっても公開せず、× を返す（呼ぶ側が統計ショートに戻す）"""
    stamp = datetime.datetime.now(JST).strftime("%Y%m%d_%H%M")
    rel = os.path.join("channels", "job", "shorts", f"{stamp}_r{i}")
    r = step("pipeline/routine_pick.py", "--out", rel)
    if r.returncode:
        return "×1日の流れ（題が選べない）"
    work = os.path.join(ROOT, rel)
    fx = json.load(open(os.path.join(work, "facts.json"), encoding="utf-8"))
    load = lambda: json.load(open(os.path.join(work, "script.json"), encoding="utf-8")) if os.path.exists(os.path.join(work, "script.json")) else None
    if step("pipeline/write_routine.py", work).returncode and step("pipeline/write_routine.py", work).returncode:
        record(work, fx, load(), False, "台本の点検で NG が残った")
        return f"×{fx['topic_id']}（台本）"
    gets = (("pipeline/make_voice_vv.py", "make", work, "--ch", "job"), ("pipeline/make_images_lovart.py", work, "--par", "5"),
            ("pipeline/gate_images.py", work, "--fix"))
    for args in gets:
        if step(*args, env={"LOVART_WAIT_MAX": "5400"}).returncode:
            record(work, fx, load(), False, f"{args[0]} で止まった")
            return f"×{fx['topic_id']}（{os.path.basename(args[0])}）"
    step("pipeline/make_motion_psy.py", work, "--par", "3", env={"MOTION_DEADLINE": str(time.time() + 1800)})  # 間に合わない絵は、静止画の寄りのまま
    if step("pipeline/build_short_routine.py", work).returncode:
        record(work, fx, load(), False, "組み立てで止まった")
        return f"×{fx['topic_id']}（組み立て）"
    record(work, fx, load(), True)
    if upload and slot:
        if step("pipeline/short_upload.py", work, "--at", slot, "--go").returncode:
            return f"△{load()['title']}（作ったがアップで止まった）"
        return f"○{load()['title']}（予約 {slot}）"
    return f"○{load()['title']}（作っただけ：{rel}）"


def routine_broken(k=3):
    h = [x for x in (json.load(open(HIST, encoding="utf-8")) if os.path.exists(HIST) else []) if x.get("kind") == "routine"][-k:]
    return len(h) == k and not any(x.get("ok") for x in h)


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--n", type=int)
    a.add_argument("--no-upload", action="store_true")
    a.add_argument("--routine-only", action="store_true", help="1日の流れを1本だけ作る（失敗しても統計ショートに戻さない）")
    a.add_argument("--at", help="--routine-only の公開の予約（日本時間）例 2026-11-03T18:10")
    a = a.parse_args()
    cfg = json.load(open(os.path.join(ROOT, "channels", "job", "profile.json"), encoding="utf-8")).get("shorts", {})
    upload = cfg.get("auto_publish", False) and not a.no_upload
    if a.routine_only:
        res = [routine(0, a.at, upload)]
        print("\n".join(["ショート：", *res]))
        sys.exit(0 if res[0].startswith("○") else 1)
    n = a.n or cfg.get("per_day", 2)
    tom = (datetime.datetime.now(JST) + datetime.timedelta(days=1)).date()
    slots = [f"{tom.isoformat()}T{t}" for t in cfg.get("times", ["12:10", "20:10"])]
    # 1日の流れの本数は、数字の判定（short_learn.py）があればそれ、無ければ profile.json。統計を先に作り、1日の流れを後ろの枠に回す
    lp = os.path.join(ROOT, "history", "job", "shorts_learn.json")
    judged = (json.load(open(lp, encoding="utf-8")) if os.path.exists(lp) else {}).get("1日の流れ", {}).get("1日の本数")
    rp = min(n, cfg.get("routine_per_day", 0) if judged is None else judged)
    res = []
    for i in range(n):
        slot = slots[i] if i < len(slots) else None
        got = routine(i, slot, upload) if i >= n - rp else None
        if got and got.startswith("×"):
            print(f"1日の流れは今回作れなかったので、統計ショートに戻します：{got}", flush=True)
            got = None
        res.append(got or one(i, slot, upload))
    print("\n".join(["ショート：", *res]))
    sys.exit(0 if all(x.startswith("○") for x in res) and not routine_broken() else 1)


if __name__ == "__main__":
    main()

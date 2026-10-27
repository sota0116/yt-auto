# ショートの1日分（手順書 §12）：題選び → 台本 → 点検 → 声 → 画面 → 組み立て →（自動公開がオンの時だけ）明日の予約
#   python -X utf8 pipeline\run_shorts.py [--n 2] [--no-upload]
# ・本数と予約の時刻は profile.json の shorts（per_day・times・auto_publish）。auto_publish が false の間は作るだけ（本人のOKの後に true にする）
# ・作業フォルダは channels\job\shorts\<日時>_<種類>\（git に入れない）。使った題は history\job\shorts.json
# ・台本の点検で NG が残った時は1回だけ書き直させ、それでも NG ならその本は捨てて次の題へ（題は使ったことにする）
import argparse, datetime, json, os, subprocess, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = [sys.executable, "-X", "utf8"]
JST = datetime.timezone(datetime.timedelta(hours=9))
HIST = os.path.join(ROOT, "history", "job", "shorts.json")


def step(*args):
    r = subprocess.run([*PY, *args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
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


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--n", type=int)
    a.add_argument("--no-upload", action="store_true")
    a = a.parse_args()
    cfg = json.load(open(os.path.join(ROOT, "channels", "job", "profile.json"), encoding="utf-8")).get("shorts", {})
    n = a.n or cfg.get("per_day", 2)
    tom = (datetime.datetime.now(JST) + datetime.timedelta(days=1)).date()
    slots = [f"{tom.isoformat()}T{t}" for t in cfg.get("times", ["12:10", "20:10"])]
    upload = cfg.get("auto_publish", False) and not a.no_upload
    res = [one(i, slots[i] if i < len(slots) else None, upload) for i in range(n)]
    print("\n".join(["ショート：", *res]))
    sys.exit(0 if all(x.startswith("○") for x in res) else 1)


if __name__ == "__main__":
    main()

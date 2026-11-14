# ショートの1日分（手順書 §12）：題選び → 台本 → 点検 → 声 → 画面 → 組み立て →（自動公開がオンの時だけ）明日の予約
#   python -X utf8 pipeline\run_shorts.py [--n 2] [--no-upload] [--routine-only --at 2026-11-03T18:10]
# ・統計ショートを先に作り、後ろの枠を1日の流れに回す（本数は shorts_learn.json の判定か profile.json の routine_per_day）。1日の流れが作れない時は、その枠を統計ショートに戻す
#   1日の流れが絵（Lovart）で2回続けて止まったら、3日間は試さずに統計ショートを作る（images_down。3日たったら1回試す）
# ・企業もしも（手順書 §15。2026-11-14〜）：前の枠（今は 07:10）の統計ショートを、作れた本数が KIGYO_N 本になるまで企業もしもに回す。
#   作れない時（題が無い・絵が無い・点検で NG）は、その枠を統計ショートに戻す
# ・本数は profile.json の shorts（per_day・auto_publish）。予約の時刻は 2026-11-04〜 day_slots.py の PLAN["job"]（times は記録として残す）。auto_publish が false の間は作るだけ（本人のOKの後に true にする）
# ・作業フォルダは channels\job\shorts\<日時>_<種類>\（git に入れない）。使った題は history\job\shorts.json
# ・台本の点検で NG が残った時は1回だけ書き直させ、それでも NG ならその本は捨てて次の題へ（題は使ったことにする）
import argparse, datetime, json, os, subprocess, sys, time
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = [sys.executable, "-X", "utf8"]
JST = datetime.timezone(datetime.timedelta(hours=9))
HIST = os.path.join(ROOT, "history", "job", "shorts.json")
KIGYO_N = 10  # §15「前の枠の統計ショートを10本だけ回す」。profile.json の shorts.kigyo_total があればそちら
DRAWN = ("routine", "kigyo")  # 絵を Lovart で描く種類（絵が止まった時の見送りを一緒に数える）


def step(*args, env=None):
    r = subprocess.run([*PY, *args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", env={**os.environ, **(env or {})})
    print((r.stdout + r.stderr).strip()[-1200:], flush=True)
    return r


def record(work, fx, sc, ok, why=""):
    h = json.load(open(HIST, encoding="utf-8")) if os.path.exists(HIST) else []
    h.append({"work": os.path.basename(work), "topic_id": fx["topic_id"], "kind": fx["kind"], "measure": fx["measure"],
              "title": (sc or {}).get("title"), "hook": ((sc or {}).get("cuts") or [{}])[0].get("hook"), "banner": (sc or {}).get("banner"),
              "編集の版": (sc or {}).get("編集の版", 1), "bgm": (sc or {}).get("bgm"),
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


def kigyo(i, slot, upload):
    """企業もしも（手順書 §15）。どの段で止まっても公開せず、× を返す（呼ぶ側が統計ショートに戻す）"""
    stamp = datetime.datetime.now(JST).strftime("%Y%m%d_%H%M")
    rel = os.path.join("channels", "job", "shorts", f"{stamp}_k{i}")
    if step("pipeline/kigyo_pick.py", "--out", rel).returncode:
        return "×企業もしも（題が選べない）"
    work = os.path.join(ROOT, rel)
    fx = json.load(open(os.path.join(work, "facts.json"), encoding="utf-8"))
    load = lambda: json.load(open(os.path.join(work, "script.json"), encoding="utf-8")) if os.path.exists(os.path.join(work, "script.json")) else None
    ready = fx.get("台本") and os.path.exists(os.path.join(ROOT, fx["台本"]))  # 手で書いた台本がある題（1本目の証券）
    if ready:
        import shutil
        shutil.copyfile(os.path.join(ROOT, fx["台本"]), os.path.join(work, "script.json"))
        ready = not step("pipeline/check_kigyo.py", work).returncode
    if not ready and step("pipeline/write_kigyo.py", work).returncode and step("pipeline/write_kigyo.py", work).returncode:
        record(work, fx, load(), False, "台本の点検で NG が残った")
        return f"×{fx['topic_id']}（台本）"
    gets = (("pipeline/make_voice_vv.py", "make", work, "--ch", "job"), ("pipeline/make_images_lovart.py", work, "--par", "5"),
            ("pipeline/gate_images.py", work, "--fix"))
    for args in gets:
        if step(*args, env={"LOVART_WAIT_MAX": "5400"}).returncode:
            record(work, fx, load(), False, f"{args[0]} で止まった")
            return f"×{fx['topic_id']}（{os.path.basename(args[0])}）"
    step("pipeline/make_motion_psy.py", work, "--par", "3", env={"MOTION_DEADLINE": str(time.time() + 1800)})
    if step("pipeline/build_short_kigyo.py", work).returncode:
        record(work, fx, load(), False, "組み立てで止まった")
        return f"×{fx['topic_id']}（組み立て）"
    record(work, fx, load(), True)
    if upload and slot:
        if step("pipeline/short_upload.py", work, "--at", slot, "--go").returncode:
            return f"△{load()['title']}（作ったがアップで止まった）"
        return f"○{load()['title']}（予約 {slot}）"
    return f"○{load()['title']}（作っただけ：{rel}）"


def kigyo_left(cfg):
    """企業もしもを、あと何本作るか（作れた本数で数える。取り下げた回は数えない）"""
    h = json.load(open(HIST, encoding="utf-8")) if os.path.exists(HIST) else []
    up = os.path.join(ROOT, "history", "job", "shorts_uploaded.json")
    retired = {x["work"] for x in (json.load(open(up, encoding="utf-8")) if os.path.exists(up) else []) if x.get("retired")}
    return cfg.get("kigyo_total", KIGYO_N) - sum(x.get("kind") == "kigyo" and x.get("ok") and x["work"] not in retired for x in h)


def routine_broken(k=3):
    h = [x for x in (json.load(open(HIST, encoding="utf-8")) if os.path.exists(HIST) else []) if x.get("kind") == "routine"][-k:]
    return len(h) == k and not any(x.get("ok") for x in h)


def images_down(days=3):
    """1日の流れが直近2回とも絵（make_images_lovart）で止まっていて、最後の失敗から days 日たっていない。
    この間は1日の流れを試さない（台本と声を作っては捨てるのをやめる。days 日たったら1回試す）"""
    h = [x for x in (json.load(open(HIST, encoding="utf-8")) if os.path.exists(HIST) else []) if x.get("kind") in DRAWN][-2:]
    return (len(h) == 2 and all(not x.get("ok") and "make_images_lovart" in (x.get("why") or "") and x.get("made_at") for x in h)
            and datetime.datetime.now(JST) - datetime.datetime.fromisoformat(h[-1]["made_at"]) < datetime.timedelta(days=days))


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--n", type=int)
    a.add_argument("--no-upload", action="store_true")
    a.add_argument("--routine-only", action="store_true", help="1日の流れを1本だけ作る（失敗しても統計ショートに戻さない）")
    a.add_argument("--kigyo-only", action="store_true", help="企業もしもを1本だけ作る（失敗しても統計ショートに戻さない）")
    a.add_argument("--at", help="--routine-only・--kigyo-only の公開の予約（日本時間）例 2026-11-03T18:10")
    a = a.parse_args()
    cfg = json.load(open(os.path.join(ROOT, "channels", "job", "profile.json"), encoding="utf-8")).get("shorts", {})
    upload = cfg.get("auto_publish", False) and not a.no_upload
    if a.routine_only or a.kigyo_only:
        res = [(kigyo if a.kigyo_only else routine)(0, a.at, upload)]
        print("\n".join(["ショート：", *res]))
        sys.exit(0 if res[0].startswith("○") else 1)
    n = a.n or cfg.get("per_day", 2)
    tom = (datetime.datetime.now(JST) + datetime.timedelta(days=1)).date()
    # 2026-11-04〜 枠は day_slots.py の PLAN["job"]（07:10・12:10。横 19:00・予告 22:10 と3時間以上あける）。
    #   翌日から順に、空いていて前後3時間に何も無い枠を取る（埋まっていれば次の日へ）
    import day_slots
    picked = []
    for _ in range(n):
        t = day_slots.next_short("job", used=picked, after=datetime.datetime.combine(tom, datetime.time(0, 0), JST))
        if t:
            picked.append(t)
    slots = [t.strftime("%Y-%m-%dT%H:%M") for t in picked]
    # 1日の流れの本数は、数字の判定（short_learn.py）があればそれ、無ければ profile.json。統計を先に作り、1日の流れを後ろの枠に回す
    lp = os.path.join(ROOT, "history", "job", "shorts_learn.json")
    judged = (json.load(open(lp, encoding="utf-8")) if os.path.exists(lp) else {}).get("1日の流れ", {}).get("1日の本数")
    rp = min(n, cfg.get("routine_per_day", 0) if judged is None else judged)
    down = rp > 0 and images_down()  # 絵（Lovart）で2回続けて止まった後の3日間は、最初から統計ショートを作る（2026-11-13：9日続けて台本と声を捨てていた）
    if down:
        print("::warning::1日の流れは絵（Lovart）が作れないので見送り中です。3日おきに1回試します", flush=True)
    kg = n - rp > 0 and kigyo_left(cfg) > 0 and not down  # 前の枠（統計ショートの枠の先頭）を企業もしもに回す
    res = []
    for i in range(n):
        slot = slots[i] if i < len(slots) else None
        got = routine(i, slot, upload) if i >= n - rp and not down else None
        if got and got.startswith("×"):
            print(f"1日の流れは今回作れなかったので、統計ショートに戻します：{got}", flush=True)
            got = None
        if i == 0 and kg and not got:
            got = kigyo(i, slot, upload)
            if got.startswith("×"):
                print(f"企業もしもは今回作れなかったので、統計ショートに戻します：{got}", flush=True)
                got = None
        res.append(got or one(i, slot, upload))
    print("\n".join(["ショート：", *res]))
    sys.exit(0 if all(x.startswith("○") for x in res) and (down or not routine_broken()) else 1)


if __name__ == "__main__":
    main()

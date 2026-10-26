# 司令塔（設計書 §2・§4）：1チャンネル分の毎日の制作を、①ネタ〜⑫記録まで順に動かす
#   python -X utf8 pipeline\run_daily.py <ch> [--count auto|1|2] [--no-upload] [--resume]
# ・段ごとに history\<ch>\status.json を書く。失敗した回は、次の実行（08:07 のやり直し）でその段から続ける
# ・止める決まり：PAUSED=true／固定データのハッシュが合わない／MONTHLY_CAP_YEN が無い（クラウドの時）か今月の累計が届いた
#   止めた日も在庫で公開はつながる。止めた理由は history\<ch>\last_run.json に書き、通知の段（notify.py）が Issue にする
# ・何本作るか：在庫（非公開で上げて、まだ公開していない本数）が目標より少なければ2本、そうでなければ1本（設計書 §2 の表）
#   審査の前と後は、設定値 STOCK_PHASE（pre／post。無ければ pre）で切り替える
# ・台本ゲートで落ちたら書き直しは2回まで。絵ゲートで使い回しが15%を超えた（終了コード2）・完成品ゲートで落ちた回は、その回を止める
# ・お金：各段が表示した見積もりの円を拾い、補正係数（COST_FACTOR。無ければ1.5）を掛けて history\<ch>\cost.json に月ごとに足す
# ・Gemini の1日の回数の上限（各段の終了コード 75）で止まった時は、失敗に数えず「待ち」にする。上限が戻った後の 17:37 の枠（retry）で続きから作る
# ・時間の枠：GitHub Actions は1回5時間まで。RUN_BUDGET_MIN（無ければ260分）を超えそうな段は区切って「途中」にし、次の実行で続きから作る。
#   Lovart の無料モードは1枚十数分かかり、絵だけで数時間になるため（2026-10-24）。「途中」は失敗に数えず、Issue にもしない
# ・3回続けて失敗した回は飛ばす。ただし最後の失敗の後に道具（pipeline の .py）が変わっていれば、直したとみなして0から数え直す（2026-10-27）
# ・--no-upload：手元で試す時。アップの段の手前で止める（status は upload の前で止まったまま残る）
import argparse, datetime, hashlib, json, os, re, subprocess, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = [sys.executable, "-X", "utf8"]
JST = datetime.timezone(datetime.timedelta(hours=9))
T0 = time.time()
BUDGET = float(os.environ.get("RUN_BUDGET_MIN") or 260) * 60
STOCK_GOAL = {"pre": (9, 8), "post": (2, 1)}  # (在庫の目標, この本数以下なら2本作る)


def now():
    return datetime.datetime.now(JST)


def hpath(ch, name):
    os.makedirs(os.path.join(ROOT, "history", ch), exist_ok=True)
    return os.path.join(ROOT, "history", ch, name)


def jload(p, default):
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else default


def jsave(p, d):
    tmp = p + ".tmp"
    json.dump(d, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    os.replace(tmp, p)


def heartbeat(ch):
    p = os.path.join(ROOT, "history", "heartbeat.json")
    hb = jload(p, {})
    hb[f"daily_{ch}"] = now().isoformat(timespec="seconds")
    jsave(p, hb)


def verify_checksums():
    """ハッシュは Windows の手元（改行 CRLF）で取った物。クラウド（Linux）は git が改行を LF にして取り出すので、
    改行だけの違いは同じ中身とみなす。.gitignore で git に入れていないファイル（スピの元資料など）はクラウドに無いので数えない（2026-10-25）"""
    sha = lambda b: hashlib.sha256(b).hexdigest()
    bad = []
    for rel, h in jload(os.path.join(ROOT, "data", "checksums.json"), {}).items():
        p = os.path.join(ROOT, rel)
        if not os.path.exists(p):
            if subprocess.run(["git", "check-ignore", "-q", rel], cwd=ROOT).returncode != 0:
                bad.append(f"{rel}（無い）")
            continue
        b = open(p, "rb").read()
        lf = b.replace(b"\r\n", b"\n")
        if h not in (sha(b), sha(lf), sha(lf.replace(b"\n", b"\r\n"))):
            bad.append(f"{rel}（中身が違う）")
    return bad


def code_ver():
    """道具（pipeline の .py）の中身の版。失敗の後に直して push されたかを見分ける（改行の違いは同じとみなす）"""
    h = hashlib.sha256()
    d = os.path.join(ROOT, "pipeline")
    for name in sorted(os.listdir(d)):
        if name.endswith(".py"):
            h.update(name.encode() + open(os.path.join(d, name), "rb").read().replace(b"\r\n", b"\n"))
    return h.hexdigest()[:12]


def month_cost(ch):
    return jload(hpath(ch, "cost.json"), {}).get(now().strftime("%Y-%m"), 0.0)


def add_cost(ch, work, stage, yen):
    if not yen:
        return
    f = float(os.environ.get("COST_FACTOR") or 1.5)
    p = hpath(ch, "cost.json")
    c = jload(p, {})
    m = now().strftime("%Y-%m")
    c[m] = round(c.get(m, 0.0) + yen * f, 1)
    c.setdefault("_明細", []).append({"日時": now().isoformat(timespec="seconds"), "回": os.path.basename(work), "段": stage,
                                     "見積もり円": round(yen, 1), "補正係数": f})
    jsave(p, c)


def yen_in(text):
    """各段が表示した見積もりの円だけを拾う（台本の中の金額は拾わない）"""
    n = 0.0
    for line in text.splitlines():
        m = re.search(r"(?:Gemini[^\n]*?約|見積もり約|'見積もり_円': )([\d.]+)", line)
        if m:
            n += float(m.group(1))
    return n


def stock(ch):
    up = jload(hpath(ch, "uploaded.json"), [])
    return sum(1 for x in up if not x.get("published") and not x.get("missing"))  # published・missing は見張り（watch.py）が書く


class Stop(Exception):
    pass


class Wait(Stop):
    """Gemini の1日の回数の上限（終了コード 75）。失敗ではないので、3回で飛ばす数に入れない。17:37 の枠で続きから作る"""


class Busy(Wait):
    """時間の枠の中で終わらなかった（絵の順番待ちなど）。失敗ではない。次の実行で続きから作る"""


def left():
    return T0 + BUDGET - time.time()


def run(work, stage, args, ch, ok=(0,), timeout=4 * 3600, env=None):
    log = os.path.join(work, "_run.log")
    t0 = time.time()
    with open(log, "a", encoding="utf-8") as f:
        f.write(f"\n### {now().isoformat(timespec='seconds')} {stage}: {' '.join(args)}\n")
    try:
        r = subprocess.run(PY + [os.path.join(ROOT, "pipeline", args[0])] + args[1:], cwd=ROOT, capture_output=True,
                           text=True, encoding="utf-8", errors="replace", timeout=max(60, min(timeout, left())),
                           env={**os.environ, **(env or {})})
    except subprocess.TimeoutExpired:
        with open(log, "a", encoding="utf-8") as f:
            f.write(f"\n（時間の枠で区切った・{(time.time() - t0) / 60:.1f}分）\n")
        raise Busy(f"{stage} が時間の枠の中で終わりませんでした。次の実行で続きから作ります")
    out = r.stdout + "\n" + r.stderr
    with open(log, "a", encoding="utf-8") as f:
        f.write(out + f"\n（終了コード {r.returncode}・{(time.time() - t0) / 60:.1f}分）\n")
    if stage != "write":
        add_cost(ch, work, stage, yen_in(r.stdout))
    tail = "\n".join(x for x in out.strip().splitlines()[-20:])  # クラウドのログで落ちた理由まで読めるように（2026-10-25 に4行から増やした）
    print(f"[{stage}] 終了コード {r.returncode}・{(time.time() - t0) / 60:.1f}分\n{tail}", flush=True)
    if r.returncode == 75:
        raise Wait(f"{stage} で Gemini の1日の回数の上限に届きました。上限が戻る 17:37 の実行で続きから作ります")
    if r.returncode not in ok:
        raise Stop(f"{stage} で止まりました（終了コード {r.returncode}）：{tail[-300:]}")
    return r


def record(ch, work):
    s = jload(os.path.join(work, "script.json"), {})
    n = jload(os.path.join(work, "neta.json"), {})
    f = jload(os.path.join(work, "facts.json"), {})
    up = jload(os.path.join(work, "uploaded.json"), {})
    chp = os.path.join(work, "chapters.txt")
    keep = ("hook_type", "sub_copy", "line_copy", "name_copy", "title", "titles", "thumb_text", "competitor_note")
    rec = {"work": os.path.basename(work), "type": n.get("type") or s.get("type"), "frame": n.get("frame") or s.get("frame"),
           "neta_id": n.get("id"), "jobs": n.get("jobs") or (f.get("順位") if isinstance(f.get("順位"), dict) else {}).get("年収", []),  # 型D の順位は説の並び（list）
           "made": now().date().isoformat(), **{k: s.get(k) for k in keep}, "chapters": open(chp, encoding="utf-8").read().splitlines() if os.path.exists(chp) else [],
           "video_id": up.get("video_id"), "回した理由": n.get("回した理由")}
    p = hpath(ch, "produced.json")
    h = jload(p, [])
    if not any(x["work"] == rec["work"] for x in h):
        jsave(p, h + [rec])
    # 台本ゲートの「似すぎ」が次の回から比べられるように、セリフだけを git に入る所へ残す（videos\ は git に入れない）
    os.makedirs(os.path.join(ROOT, "history", ch, "scripts"), exist_ok=True)
    jsave(os.path.join(ROOT, "history", ch, "scripts", rec["work"] + ".json"),
          {"cuts": [{"id": c.get("id"), "narration": c.get("narration", "")} for c in s.get("cuts", [])]})


def make_one(ch, st, upload):
    """1本作る。st は status.json の中身（続きから始める時は work と done が入っている）"""
    sp = hpath(ch, "status.json")
    if not st.get("work"):
        r = run(ROOT, "pick", ["pick_neta.py", ch], ch)
        work = r.stdout.strip().splitlines()[-1].strip()
        if not os.path.isdir(work):
            raise Stop(f"ネタの段で作業フォルダが分かりません：{work}")
        st = {"work": work, "done": ["pick"], "started": now().isoformat(timespec="seconds"), "tries": 0}
        jsave(sp, st)
    work = st["work"]
    st["tries"] = st.get("tries", 0) + 1
    st["code"] = code_ver()
    print(f"■ {ch}：{os.path.basename(work)}（{st['tries']}回目・済み {st['done']}）", flush=True)

    def step(name, fn):
        if name in st["done"]:
            return
        if left() < 20 * 60:
            raise Busy(f"時間の枠の残りが20分を切ったので、{name} の前で区切りました。次の実行で続きから作ります")
        st["stage"] = name
        jsave(sp, st)
        fn()
        st["done"].append(name)
        st["updated"] = now().isoformat(timespec="seconds")
        jsave(sp, st)

    def write_and_gate():
        for i in range(3):  # 1回目＋書き直し2回
            if i == 0 and "write" not in st["done"]:
                run(work, "write", ["write_script.py", work, "--ch", ch], ch, ok=(0, 1))
                st["done"].append("write")
                jsave(sp, st)
            elif i > 0:
                run(work, "write", ["write_script.py", work, "--ch", ch, "--fix"], ch, ok=(0, 1))
            r = run(work, "gate_script", ["gate_script.py", work, "--ch", ch], ch, ok=(0, 1))
            if r.returncode == 0:
                return
        raise Stop("台本ゲートで3回不合格（書き直し2回でも直らない）。その回は止め、在庫で公開をつなぐ")

    step("gate_script", write_and_gate)
    # 声は profile.json の tts_engine で選ぶ（2026-10-24 から仕事チャンネルは VOICEVOX）
    voice_py = "make_voice_vv.py" if jload(os.path.join(ROOT, "channels", ch, "profile.json"), {}).get("tts_engine") == "voicevox" else "make_voice_job.py"
    step("voice", lambda: run(work, "voice", [voice_py, "make", work, "--ch", ch], ch))
    if voice_py == "make_voice_vv.py":  # 読み違い（数字・単位・職業名など）を読みの文字で探し、見つかったカットは読みを書いて作り直す
        step("reading", lambda: run(work, "reading", ["check_reading_vv.py", work, "--ch", ch, "--fix"], ch))
    def images():
        # 待つ上限を時間の枠に合わせる（区切っても、頼んだ絵は次の実行で受け取る）
        run(work, "images", ["make_images_lovart.py", work, "--par", "6"], ch, ok=(0, 1),
            env={"LOVART_WAIT_MAX": str(int(max(300, left() - 15 * 60)))})
        s = jload(os.path.join(work, "script.json"), {})
        lg = jload(os.path.join(work, "images", "_lovart.json"), {})
        rest = [c["id"] for c in s.get("cuts", []) if c.get("image") and not c.get("same_as") and not c.get("chart")
                and not os.path.exists(os.path.join(work, "images", c["id"] + ".png"))
                and (lg.get(c["id"], {}).get("状態") == "待ち" or lg.get(c["id"], {}).get("回", 0) < 2)]
        if rest:
            raise Busy(f"絵がまだ途中（残り{len(rest)}枚。Lovart の無料モードは1枚十数分）。次の実行で続きから作ります")
    step("images", images)
    step("charts", lambda: run(work, "charts", ["make_charts_job.py", work], ch))

    def gate_images():
        r = run(work, "gate_images", ["gate_images.py", work, "--fix"], ch, ok=(0, 1, 2))
        if r.returncode == 2:
            raise Stop("絵の使い回しが15%を超えました（絵ゲート）。その回は止め、在庫で公開をつなぐ")
        if r.returncode == 1:
            raise Stop("絵ゲートの不合格が残りました（images\\_gate.json）")
    step("gate_images", gate_images)
    step("build", lambda: run(work, "build", ["build_long_job.py", work], ch))
    step("gate_video", lambda: run(work, "gate_video", ["gate_video.py", work], ch))

    def thumb():
        s = jload(os.path.join(work, "script.json"), {})
        args = ["make_thumb_job.py", work, "--check"]
        if s.get("thumb_bg"):
            args[2:2] = ["--bg", s["thumb_bg"]]
        run(work, "thumb", args, ch)
    step("thumb", thumb)
    if not upload:
        print("（--no-upload なので、アップの手前で止めました）")
        return st
    step("upload", lambda: run(work, "upload", ["upload_job.py", work, "--channel", ch, "--privacy", "private"], ch))
    step("record", lambda: record(ch, work))
    if os.environ.get("GITHUB_ACTIONS") == "true":  # 上げ終えた回の大きいファイルは、次の実行に引き継がない（動画は YouTube にある）
        import shutil
        for d in ("images", "voice", "_build"):
            shutil.rmtree(os.path.join(work, d), ignore_errors=True)
        for x in ("long.mp4",):
            if os.path.exists(os.path.join(work, x)):
                os.remove(os.path.join(work, x))
    return st


def main():
    a = argparse.ArgumentParser()
    a.add_argument("ch", choices=["job", "spi"])
    a.add_argument("--count", default="auto")
    a.add_argument("--no-upload", action="store_true")
    a.add_argument("--slot", default="first", choices=["first", "retry", "late"], help="retry＝08:07・late＝17:37 のやり直し。今日の 02:07 が成功していれば何もしない")
    a = a.parse_args()
    os.environ["TZ"] = "Asia/Tokyo"
    ch = a.ch
    cloud = os.environ.get("GITHUB_ACTIONS") == "true"
    res = {"ch": ch, "started": now().isoformat(timespec="seconds"), "made": [], "stopped": None}
    lp = hpath(ch, "last_run.json")
    last = jload(lp, {})
    if a.slot != "first" and last.get("started", "")[:10] == now().date().isoformat() and not last.get("stopped"):
        print("今日の分はもう作れています（やり直しは不要）")
        return
    try:
        if (os.environ.get("PAUSED") or "").lower() == "true":
            res["stopped"] = "PAUSED が true なので作りませんでした（公開は在庫で続く）"
            return
        bad = verify_checksums()
        if bad:
            raise Stop("固定データのハッシュが合いません：" + "、".join(bad[:5]))
        cap = os.environ.get("MONTHLY_CAP_YEN")
        if cloud and not cap:
            raise Stop("MONTHLY_CAP_YEN（制作費の月の上限）が入っていないので、新しく作りませんでした")
        if cap and month_cost(ch) >= float(cap):
            raise Stop(f"今月の制作費の累計 {month_cost(ch):.0f}円 が上限 {cap}円 に届いたので、新しく作りませんでした")
        goal, two_at = STOCK_GOAL.get(os.environ.get("STOCK_PHASE") or "pre", STOCK_GOAL["pre"])
        n_stock = stock(ch)
        res["在庫"] = n_stock
        n = int(a.count) if a.count.isdigit() else (2 if n_stock <= two_at else 1)
        sp = hpath(ch, "status.json")
        for i in range(n):
            st = jload(sp, {})
            if st.get("work") and "record" in st.get("done", []):
                st = {}
            if st.get("tries") and st.get("code") != code_ver():
                print(f"前の失敗の後に道具が直っているので、{os.path.basename(st['work'])} の失敗の数を0から数え直します", flush=True)
                st["tries"] = 0  # 直した後も前の3回で飛ばすと、出来上がり寸前の回を捨てる（006 がそうなった。2026-10-26）
            if st.get("tries", 0) >= 3:
                res.setdefault("飛ばした回", []).append(st["work"])
                st = {}  # 3回続けて失敗した回は飛ばして次のネタへ（週報に出す）
            if cap and month_cost(ch) >= float(cap):
                raise Stop(f"今月の制作費の累計が上限 {cap}円 に届いたので、{i}本で止めました")
            st = make_one(ch, st, not a.no_upload)
            if not a.no_upload:
                res["made"].append(os.path.basename(st["work"]))
                jsave(sp, {})
            else:
                break
    except Stop as e:
        res["stopped"] = str(e)
        if isinstance(e, Wait):
            res["待ち"] = True
            if isinstance(e, Busy):
                res["途中"] = True
            sp = hpath(ch, "status.json")
            st = jload(sp, {})
            if st.get("tries"):
                st["tries"] -= 1  # 回数の上限で止まったのは、その回の失敗ではない
                jsave(sp, st)
        print("【止まりました】", e, flush=True)
    except subprocess.TimeoutExpired as e:
        res["stopped"] = f"時間切れ：{e.cmd[2] if len(e.cmd) > 2 else e.cmd}"
    finally:
        res["ended"] = now().isoformat(timespec="seconds")
        res["今月の制作費_円"] = month_cost(ch)
        jsave(lp, res)
        heartbeat(ch)
        print(json.dumps(res, ensure_ascii=False))
    sys.exit(1 if res["stopped"] and not res["stopped"].startswith("PAUSED") else 0)


if __name__ == "__main__":
    main()

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
# ・詰まった時の決まり（2026-10-29 本人「エラーが起きた場合の対処もあらかじめ決めておく」「詰まりを取ろう」）：
#   1. 絵・動く絵が時間の枠で終わらない →「途中」にして次の実行で続ける（前と同じ）
#   2. 同じ段が2回続けて「途中」になり、在庫が目標より少ない → 残りを Lovart の速いモードで作る（lovart_boost.py。その日の上限の分だけ・
#      絵は半額の 23:00〜04:00 だけ・速いモードは1回45分まで・終わったら必ず無料モードに戻す）。上限で足りない分は無料で続ける
#   3. 動く絵は、無料の実行3回でも終わらなければ残りを静止画のまま進める（make_motion_psy.py。前と同じ）
#   4. 作り始めて72時間たっても上がらない回は飛ばして次のネタへ（Issue。作業フォルダは残すので、あとで続きから作れる）
#   5. 在庫が2本以下になったら、02:07 の実行の通知で Issue にする（notify.py）
#   6. 完成動画ゲートで落ちたのが画面（絵の中の読める文字・崩れた絵）だけなら、そのカットの絵を作り直して組み立て直す（2回まで。bad_frame_cuts）。
#      心理学ch 004 が、組み立てまで済んだ18分の回を、看板の英語1枚で止めた（2026-10-29）。前の絵は images/_video_gate_old/ に残す
#   7. 完成動画ゲートで落ちたのが「8分未満」だけで、足りないのが5%以内なら、カットの間（gap。0.6秒まで）を広げて1回だけ組み直す
#      （千年こよみ 003 が7.7分で止まった。2026-10-29。声の速さは変えない。組み立ての道具が --gap を受ける時だけ）
# ・--no-upload：手元で試す時。アップの段の手前で止める（status は upload の前で止まったまま残る）
# ・種類ごとに作るチャンネル（2026-10-29 アナザー日本紀から。profile.json の "kinds"：{"short": {...}, "long": {...}}）：
#   ショート中心のチャンネルは、1日に何本ものショートと、2日に1本の横動画を作る。そこで run_daily に「種類ごとの繰り返し」を足した
#   （別の入口を作らなかった理由：台本→声→絵→動く絵→ゲート→組み立て→アップ→記録の段・途中から続ける仕組み・時間の枠・お金・詰まりの決まりを
#   そのまま使いたいため。入口を分けると全部を写すことになり、直した時に片方だけ古くなる）。
#   ・種類ごとに kinds.<種類>.tools（段の道具。書いた段が profile.json の tools より先）・stock_goal（[目標, この本数以下なら make_max 本]）・make_max
#   ・作り途中の回は種類ごとに history/<ch>/status_<種類>.json（ショートが詰まっても横動画の続きは止まらず、横動画が詰まってもショートは作れる）
#   ・在庫は種類ごとに数える（ustore.kind_of）。pick には --kind <種類> を渡す。kinds の無いチャンネル（job・psy・spi）は今までと同じ動き
import argparse, datetime, hashlib, json, os, re, subprocess, sys, time, wave

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


def profile(ch):
    return jload(os.path.join(ROOT, "channels", ch, "profile.json"), {})


def kinds(ch):
    """種類ごとに作るチャンネルの設定（profile.json の kinds）。無ければ None（今までの動き）"""
    return profile(ch).get("kinds") or None


def status_path(ch, kind=None):
    return hpath(ch, f"status_{kind}.json" if kind else "status.json")


def tool(ch, stage, default, kind=None):
    """段の道具。profile.json の tools に書いた段はその道具（null はその段を飛ばす＝None）。書いていない段は仕事チャンネルと同じ道具
    （2026-10-27 心理学chを毎日の制作に入れた時に足した）。kind を渡すと、kinds.<kind>.tools に書いた段が先"""
    pf = profile(ch)
    kt = ((pf.get("kinds") or {}).get(kind) or {}).get("tools") or {} if kind else {}
    if stage in kt:
        return kt[stage]
    t = pf.get("tools") or {}
    return t[stage] if stage in t else default


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


def stock(ch, kind=None):
    """在庫＝上げて、まだ公開していない本数。kind を渡すと、その種類（short／long）だけ数える
    公開の予約の時刻（publish_at）を過ぎた回も公開済みとして数えない。読むだけの記録（ustore.py の uploaded_files_ro）は
    見張りが published を書き戻さないので、10/28 に公開した日本紀・おきぬの横動画が在庫に残り、おきぬの横動画を作っていなかった（2026-10-29）"""
    import ustore
    up = ustore.load(ch)
    t = now()

    def gone(x):
        try:
            return datetime.datetime.fromisoformat(x["publish_at"].replace("Z", "+00:00")) <= t
        except (KeyError, AttributeError, TypeError, ValueError):
            return False
    return sum(1 for x in up if not x.get("published") and not x.get("missing") and not x.get("retired") and not gone(x)
               and (not kind or ustore.kind_of(x) == kind))  # published・missing は見張り（watch.py）が書く


def stock_goal(ch, kind=None):
    """(在庫の目標, この本数以下なら多く作る)。profile.json の stock_goal が先、無ければ stock_phase か設定値 STOCK_PHASE（pre／post）。
    kind を渡すと kinds.<kind>.stock_goal が先"""
    prof = profile(ch)
    kg = ((prof.get("kinds") or {}).get(kind) or {}).get("stock_goal") if kind else None
    if kg:
        return tuple(kg)
    phase = prof.get("stock_phase") or os.environ.get("STOCK_PHASE") or "pre"
    return tuple(prof.get("stock_goal") or STOCK_GOAL.get(phase, STOCK_GOAL["pre"]))


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
    keep = ("hook_type", "sub_copy", "line_copy", "name_copy", "title", "titles", "thumb_text", "thumb_kind", "competitor_note", "learn_note")
    rec = {"work": os.path.basename(work), "type": n.get("type") or s.get("type"), "frame": n.get("frame") or s.get("frame"),
           "neta_id": n.get("id"), "jobs": n.get("jobs") or (f.get("順位") if isinstance(f.get("順位"), dict) else {}).get("年収", []),  # 型D の順位は説の並び（list）
           "made": now().date().isoformat(), **{k: s.get(k) for k in keep}, "chapters": open(chp, encoding="utf-8").read().splitlines() if os.path.exists(chp) else [],
           "video_id": up.get("video_id"), "回した理由": n.get("回した理由")}
    rec.update({k: n.get(k) for k in ("kind", "no", "企画", "distort", "era", "fact_main", "from_short") if n.get(k) is not None})  # アナザー日本紀：種類・番号・企画・ずらし方・時代・「へえ」の主役の史実
    if isinstance(f.get("studies"), list):  # 心理学ch：使った研究（次の回の書き手が同じ研究を中心にしないように）
        rec["studies"] = [x.get("cite") for x in f["studies"]]
    g = jload(os.path.join(work, "gate_script.json"), {}).get("続きを見たくなるか") or {}
    if isinstance(g.get("最初の30秒"), dict):  # 台本ゲートの点（いちばん早い数字。learn_job.py が毎日の学びに使う。作業フォルダは git に入らないのでここに残す）
        ch_pts = sorted(g.get("章") or [], key=lambda c: c.get("点", 10))
        rec["台本ゲートの点"] = {"最初の30秒": g["最初の30秒"].get("点"), "章": [c.get("点") for c in g.get("章") or []],
                            "山場": (g.get("山場") or {}).get("点"),
                            "低い所の直すなら": [str(x.get("直すなら", ""))[:120] for x in [g["最初の30秒"]] + ch_pts[:2] if x.get("点", 10) < 8]}
    if s.get("short"):  # 心理学ch：ショートを上げられたか（週報が数える）
        rec["short_video_id"] = jload(os.path.join(work, "short", "uploaded.json"), {}).get("video_id") or "上げられなかった"
    p = hpath(ch, "produced.json")
    h = jload(p, [])
    if not any(x["work"] == rec["work"] for x in h):
        jsave(p, h + [rec])
    # 台本ゲートの「似すぎ」が次の回から比べられるように、セリフだけを git に入る所へ残す（videos\ は git に入れない）
    os.makedirs(os.path.join(ROOT, "history", ch, "scripts"), exist_ok=True)
    hs = {"cuts": [{"id": c.get("id"), "narration": c.get("narration", "")} for c in s.get("cuts", [])]}
    if s.get("banner"):  # アナザー日本紀：題・帯・hook も残す（次の回が同じ言葉を使わないため）
        hs.update({"kind": s.get("format"), "title": s.get("title"), "banner": s.get("banner"), "hook": (s.get("cuts") or [{}])[0].get("hook")})
    jsave(os.path.join(ROOT, "history", ch, "scripts", rec["work"] + ".json"), hs)


def apply_fixes(ch, work, st):
    """台本ゲートを通った後に人が見つけた直し（channels\\<ch>\\fixes\\<作業フォルダ名>.json）を、アップの前に script.json へ入れる（2026-10-28）
    titles（3案）・thumb・short_title を置き換え、drop_lines_with の言葉がある行を概要欄（本編・ショート）から除く"""
    fp = os.path.join(ROOT, "channels", ch, "fixes", os.path.basename(work) + ".json")
    sp = os.path.join(work, "script.json")
    if not os.path.exists(fp) or not os.path.exists(sp) or "upload" in st.get("done", []) or st.get("fixed"):
        return
    fx, s = jload(fp, {}), jload(sp, {})
    if fx.get("titles"):
        s["titles"], s["title"] = fx["titles"], fx["titles"][0]
    if fx.get("thumb"):
        s["thumb"] = fx["thumb"]
    if fx.get("short_title") and s.get("short"):
        s["short"]["title"] = fx["short_title"]
    drop = lambda t: "\n".join(x for x in t.split("\n") if not any(w in x for w in fx.get("drop_lines_with", [])))
    s["desc"] = drop(s.get("desc", ""))
    if s.get("short"):
        s["short"]["desc"] = drop(s["short"].get("desc", ""))
    jsave(sp, s)
    st["done"] = [d for d in st.get("done", []) if d not in ("thumb", "short")]  # 字が変わったのでサムネとショートは作り直す
    st["fixed"] = True
    print(f"直し（{os.path.relpath(fp, ROOT)}）を script.json に入れました", flush=True)


def redo(ch, work, st):
    """作り途中の回を台本からやり直す（status.json に "redo": "<ネタの id>" を手で入れた時。2026-10-29 手順書 v4.0 の型に替えた psy 005 のため）
    neta.json と _run.log だけ残し、題はネタ帳.json の今の行に合わせる。台本・声・絵などは消す（声の段は同じカット番号の音声があると使い回すため）"""
    import shutil
    np_ = os.path.join(work, "neta.json")
    neta = jload(np_, {})
    nid = neta.get("id") or st["redo"]
    row = next((r for r in jload(os.path.join(ROOT, "channels", ch, "ネタ帳.json"), []) if r.get("id") == nid), None)
    if row:
        neta = {**neta, **row} if neta else {**row, "type": row.get("area"), "frame": row.get("area"), "made": now().date().isoformat()}
    if not neta:
        raise Stop(f"やり直しの回のネタが分かりません（neta.json もネタ帳の行 {nid} も無い）")
    os.makedirs(work, exist_ok=True)
    for x in os.listdir(work):
        if x not in ("neta.json", "_run.log"):
            p = os.path.join(work, x)
            shutil.rmtree(p, ignore_errors=True) if os.path.isdir(p) else os.remove(p)
    jsave(np_, neta)
    print(f"■ {os.path.basename(work)} を台本からやり直します（題：{neta.get('title')}）", flush=True)
    return {"work": work, "done": ["pick"], "started": now().isoformat(timespec="seconds"), "tries": 0,
            "redone": {"日時": now().isoformat(timespec="seconds"), "前の済み": st.get("done", [])}}


def bad_frame_cuts(work):
    """完成動画ゲート（_gate_video.json）で落ちたのが画面だけの時、落ちた画面の秒からカットを引き、{絵のカットの id: 作り直しの英語の指示} を返す。
    秒は組み立てが残した _build/<id>_v.wav（1カットの声＋間）の長さを足して決める（build_long_psy.py と同じ並び）。
    長さ・声の大きさ・無音・動く絵の不合格が混じる時、カットが引けない時、図やカードのカットの時は {}（絵の作り直しでは直らない）"""
    g = jload(os.path.join(work, "_gate_video.json"), {})
    bad = g.get("不合格") or []
    if not bad or not all(b.startswith("画面") for b in bad):
        return {}
    cuts = jload(os.path.join(work, "script.json"), {}).get("cuts", [])
    by_id, spans, t = {c.get("id"): c for c in cuts}, [], 0.0
    for c in (c for c in cuts if c.get("narration")):
        p = os.path.join(work, "_build", c["id"] + "_v.wav")
        if not os.path.exists(p):
            return {}
        with wave.open(p) as w:
            d = w.getnframes() / w.getframerate()
        spans.append((t, t + d, c))
        t += d
    out = {}
    for x in g.get("画面", []):
        if x.get("合格"):
            continue
        c = next((c for a, b, c in spans if a <= x.get("秒", -1) < b), None)
        while c and c.get("same_as") and c["same_as"] in by_id and c["same_as"] != c["id"]:
            c = by_id[c["same_as"]]
        if not c or c.get("card") or c.get("chart") or not os.path.exists(os.path.join(work, "images", c["id"] + ".png")):
            return {}
        q = x.get("問題", "") + (x.get("見直し") or {}).get("問題", "")
        out[c["id"]] = ("Absolutely no readable text anywhere: no signs, shop names, letters, numbers or logos (leave signboards blank)."
                        if re.search(r"文字|ロゴ|看板|英語|ブランド|店名", q) else
                        "Redraw the scene cleanly: natural hands, faces, bodies and objects, nothing deformed, no readable text.")
    return out


def make_one(ch, st, upload, kind=None):
    """1本作る。st は status.json の中身（続きから始める時は work と done が入っている）。kind＝種類（kinds のあるチャンネルだけ）"""
    sp = status_path(ch, kind)
    KIND = kind  # boost() の引数 kind（images／motion）と区別するため
    T = lambda stage, default: tool(ch, stage, default, KIND)  # 種類ごとの道具（kind が None なら今までと同じ）
    if not st.get("work"):
        r = run(ROOT, "pick", [T("pick", "pick_neta.py"), ch] + (["--kind", kind] if kind else []), ch)
        work = r.stdout.strip().splitlines()[-1].strip()
        if not os.path.isdir(work):
            raise Stop(f"ネタの段で作業フォルダが分かりません：{work}")
        st = {"work": work, "done": ["pick"], "started": now().isoformat(timespec="seconds"), "tries": 0}
        jsave(sp, st)
    work = st["work"]
    if st.get("redo") and "upload" not in st.get("done", []):
        st = redo(ch, work, st)
        jsave(sp, st)
    apply_fixes(ch, work, st)
    st["tries"] = st.get("tries", 0) + 1
    st["code"] = code_ver()
    print(f"■ {ch}{'/' + kind if kind else ''}：{os.path.basename(work)}（{st['tries']}回目・済み {st['done']}）", flush=True)

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
        w_py, g_py = T("write", "write_script.py"), T("gate_script", "gate_script.py")
        for i in range(3):  # 1回目＋書き直し2回
            if i == 0 and "write" not in st["done"]:
                run(work, "write", [w_py, work, "--ch", ch], ch, ok=(0, 1))
                st["done"].append("write")
                jsave(sp, st)
            elif i > 0:
                run(work, "write", [w_py, work, "--ch", ch, "--fix"], ch, ok=(0, 1))
            r = run(work, "gate_script", [g_py, work, "--ch", ch], ch, ok=(0, 1))
            if r.returncode == 0:
                return
        raise Stop("台本ゲートで3回不合格（書き直し2回でも直らない）。その回は止め、在庫で公開をつなぐ")

    step("gate_script", write_and_gate)
    # 声は profile.json の tts_engine で選ぶ（2026-10-24 から仕事チャンネルは VOICEVOX）
    voice_py = T("voice", None) or ("make_voice_vv.py" if profile(ch).get("tts_engine") == "voicevox" else "make_voice_job.py")
    # profile の tools.voice に書いた道具（アナザー日本紀：人物ごとの声）は <作業フォルダ> --ch の形。ふだんの2つは make の引数が先
    step("voice", lambda: run(work, "voice", [voice_py, work, "--ch", ch] if T("voice", None) else [voice_py, "make", work, "--ch", ch], ch))
    import importlib.util
    if voice_py == "make_voice_vv.py" and os.path.exists(os.path.join(ROOT, "pipeline", "yomi_auto.py")) and importlib.util.find_spec("sudachipy"):
        # 読みの機械点検（2026-10-28 本人の指摘。スキル references/16 の7）：辞書（Sudachi）と声の読みの食い違いを voice/_yomi_auto.json に残す。
        # 食い違いがあっても止めない（終了コード1も通す）。次の reading の段が、食い違いを目印にして Gemini に確かめさせる
        step("yomi", lambda: run(work, "yomi", ["yomi_auto.py", work, "--ch", ch], ch, ok=(0, 1)))
    if voice_py == "make_voice_vv.py":  # 読み違い（数字・単位・職業名など）を読みの文字で探し、見つかったカットは読みを書いて作り直す
        step("reading", lambda: run(work, "reading", ["check_reading_vv.py", work, "--ch", ch, "--fix"], ch))

    def busy(kind, msg):
        """「途中」の回数を数えてから区切る（2回続いたら、次の実行で速いモードを使う）"""
        st.setdefault("busy", {})[kind] = st.get("busy", {}).get(kind, 0) + 1
        jsave(sp, st)
        raise Busy(f"{msg}（{st['busy'][kind]}回目）")

    def boost(kind, ids, script, extra):
        """詰まった時の決まり2：同じ段が2回続けて「途中」で、在庫が目標より少なければ、残りを速いモードで作る（上の説明）。
        extra は環境変数を返す関数（23:00 まで待った後の残り時間で決めるため）"""
        import lovart_boost as lb
        if not ids or st.get("busy", {}).get(kind, 0) < 2 or stock(ch, KIND) >= stock_goal(ch, KIND)[0]:
            return
        if kind == "images" and not lb.night():
            t = now()
            if not (t.hour == 22 and t.minute >= 30 and left() > 120 * 60):
                print(f"絵の速いモードは半額の 23:00〜04:00 だけ使う（今は {t:%H:%M}）", flush=True)
                return
            time.sleep((60 - t.minute) * 60 - t.second + 5)  # 22:47 の実行は 23:00 まで待つ
        n = int(lb.left_today(ch) // lb.unit("image" if kind == "images" else "video"))
        if n < 1 or left() < 60 * 60:
            print(f"速いモードは使わない（今日の残り {lb.left_today(ch)} クレジット・時間の枠の残り {left() / 60:.0f}分）", flush=True)
            return
        pick = ids[:n]
        print(f"■ 詰まりを取る：{kind} の残り {len(ids)} のうち {len(pick)} を速いモードで作る（今日の残り {lb.left_today(ch)} クレジット）", flush=True)
        with lb.fast_mode():
            run(work, kind + "_boost", [script, work, "--boost", "--only", ",".join(pick)], ch, ok=(0, 1), env=extra())

    def images():
        s = jload(os.path.join(work, "script.json"), {})
        missing = lambda: [c["id"] for c in s.get("cuts", []) if c.get("image") and not c.get("same_as") and not c.get("chart")
                           and not os.path.exists(os.path.join(work, "images", c["id"] + ".png"))]
        boost("images", missing(), T("images", "make_images_lovart.py"), lambda: {"LOVART_WAIT_MAX": str(int(min(45 * 60, left() - 50 * 60)))})
        # 待つ上限を時間の枠に合わせる（区切っても、頼んだ絵は次の実行で受け取る）
        run(work, "images", [T("images", "make_images_lovart.py"), work, "--par", "6"], ch, ok=(0, 1),
            env={"LOVART_WAIT_MAX": str(int(max(300, left() - 15 * 60)))})
        lg = jload(os.path.join(work, "images", "_lovart.json"), {})
        rest = [i for i in missing() if lg.get(i, {}).get("状態") == "待ち" or lg.get(i, {}).get("回", 0) < 2]
        if rest:
            busy("images", f"絵がまだ途中（残り{len(rest)}枚。Lovart の無料モードは1枚十数分）。次の実行で続きから作ります")
    step("images", images)
    def motion():  # 絵の一部を数秒の動画にする（心理学ch。無料の時だけ。終わらない分は3回の実行まで続きを待つ。できなくても止めない）
        s = jload(os.path.join(work, "script.json"), {})
        ids = [c["id"] for c in s.get("cuts", []) if c.get("motion") and not c.get("same_as") and not c.get("card")
               and os.path.exists(os.path.join(work, "images", c["id"] + ".png"))
               and not os.path.exists(os.path.join(work, "images", c["id"] + ".mp4"))]
        boost("motion", ids, T("motion", None), lambda: {"MOTION_DEADLINE": str(int(time.time() + 30 * 60))})
        r = run(work, "motion", [T("motion", None), work], ch, ok=(0, 3),
                env={"MOTION_DEADLINE": str(int(time.time() + max(0, left() - 75 * 60)))})
        if r.returncode == 3:
            busy("motion", "動く絵がまだ途中（Lovart の無料モードの順番待ち）。次の実行で続きから作ります")
    if T("motion", None):
        step("motion", motion)
    if T("charts", "make_charts_job.py"):
        step("charts", lambda: run(work, "charts", [T("charts", "make_charts_job.py"), work], ch))

    def gate_images():
        r = run(work, "gate_images", ["gate_images.py", work, "--fix"], ch, ok=(0, 1, 2))
        if r.returncode == 2:
            raise Stop("絵の使い回しが15%を超えました（絵ゲート）。その回は止め、在庫で公開をつなぐ")
        if r.returncode == 1:
            raise Stop("絵ゲートの不合格が残りました（images\\_gate.json）")
    step("gate_images", gate_images)
    def build_args():  # 長さの足りない回は、カットの間を広げて組み直す（決まり7。build_gap は status に残す）
        return [T("build", "build_long_job.py"), work] + (["--gap", str(st["build_gap"])] if st.get("build_gap") else [])
    step("build", lambda: run(work, "build", build_args(), ch))

    def stretch_gap():
        """完成動画ゲートの不合格が「8分未満」だけで、足りないのが5%以内なら、カットの間（gap）を広げた値を返す（声の速さは変えない）。
        組み立ての道具が --gap を受けない・広げても 0.6秒を超える時は None"""
        g = jload(os.path.join(work, "_gate_video.json"), {})
        bad, sec = g.get("不合格") or [], g.get("長さ秒") or 0
        src = open(os.path.join(ROOT, "pipeline", T("build", "build_long_job.py")), encoding="utf-8").read()
        if not bad or not all(b.startswith("長さが") for b in bad) or "--gap" not in src or not sec or sec < 480 * 0.95:
            return None
        n = sum(1 for c in jload(os.path.join(work, "script.json"), {}).get("cuts", []) if c.get("narration"))
        base = st.get("build_gap") or (profile(ch).get("build") or {}).get("gap", 0.25)
        gap = round(base + (495 - sec) / max(1, n), 2)  # 8分15秒を目指す
        return gap if gap <= 0.6 else None

    def redo_cuts(fixes):
        """完成動画ゲートで落ちた画面のカットの絵を作り直し、絵ゲート→動く絵→組み立てをやり直す（詰まった時の決まり6）。
        前の絵は images/_video_gate_old/ に残す。絵が時間の枠で終わらなければ「途中」にして、次の実行で続きから受け取る"""
        img, old = os.path.join(work, "images"), os.path.join(work, "images", "_video_gate_old")
        first = not st.get("video_redo_sent")  # 続きから受け取る2回目以降は、動かさず・頼み直さない（作り直した絵を古い方へ動かさないため）
        if first:
            os.makedirs(old, exist_ok=True)
            for i in fixes:
                for ext in (".png", ".mp4"):
                    if os.path.exists(os.path.join(img, i + ext)):
                        os.replace(os.path.join(img, i + ext), os.path.join(old, i + ext))
            st["video_redo_sent"] = True
            jsave(sp, st)
        run(work, "images", [T("images", "make_images_lovart.py"), work, "--only", ",".join(fixes)]
            + (sum((["--fix", f"{i}={x}"] for i, x in fixes.items()), []) if first else []), ch, ok=(0, 1),
            env={"LOVART_WAIT_MAX": str(int(max(300, left() - 30 * 60)))})
        if [i for i in fixes if not os.path.exists(os.path.join(img, i + ".png"))]:
            busy("images", "完成動画ゲートで落ちた絵の作り直しがまだ途中。次の実行で続きから受け取ります")
        r = run(work, "gate_images", ["gate_images.py", work, "--fix", "--only", ",".join(fixes)], ch, ok=(0, 1, 2))
        if r.returncode:
            raise Stop("完成動画ゲートで落ちた絵を作り直したが、絵ゲートで不合格のまま（images\\_gate.json）")
        moved = [i for i in fixes if os.path.exists(os.path.join(old, i + ".mp4"))]
        if moved and T("motion", None):  # 動く絵だったカットは動く絵も作り直す。終わらなければ静止画のまま進める（決まり3と同じ）
            run(work, "motion", [T("motion", None), work, "--only", ",".join(moved)], ch, ok=(0, 3),
                env={"MOTION_DEADLINE": str(int(time.time() + max(0, min(40 * 60, left() - 60 * 60))))})
        run(work, "build", build_args(), ch)

    def gate_video():
        g_py = T("gate_video", "gate_video.py")
        while True:
            if st.get("video_redo_ids"):
                redo_cuts(st["video_redo_ids"])
                st.pop("video_redo_ids"), st.pop("video_redo_sent", None)
                jsave(sp, st)
            r = run(work, "gate_video", [g_py, work], ch, ok=(0, 1))
            if r.returncode == 0:
                return
            gap = None if st.get("build_gap") else stretch_gap()
            if gap:
                st["build_gap"] = gap
                jsave(sp, st)
                print(f"■ 完成動画ゲート：8分にわずかに足りないので、カットの間を {gap} 秒にして組み直す（1回だけ）", flush=True)
                run(work, "build", build_args(), ch)
                continue
            fixes = bad_frame_cuts(work)
            if not fixes or st.get("video_redo", 0) >= 2:
                raise Stop(f"gate_video で止まりました（終了コード 1）：{r.stdout.strip()[-300:]}")
            st["video_redo"] = st.get("video_redo", 0) + 1
            st["video_redo_ids"] = fixes
            print(f"■ 完成動画ゲートで落ちた画面のカット {list(fixes)} の絵を作り直す（{st['video_redo']}回目・2回まで）", flush=True)
            jsave(sp, st)
    step("gate_video", gate_video)

    def thumb():
        s = jload(os.path.join(work, "script.json"), {})
        args = [T("thumb", "make_thumb_job.py"), work, "--check"]
        if s.get("thumb_bg"):
            args[2:2] = ["--bg", s["thumb_bg"]]
        run(work, "thumb", args, ch)
    if T("thumb", "make_thumb_job.py"):  # null＝この種類はサムネを作らない（アナザー日本紀のショート。ショートは動画の中の1コマが表紙）
        step("thumb", thumb)
    # 長尺の予告ショート（profile.json の tools の teaser。仕事ch 2026-10-28）。long.mp4 と _build はアップの後に消すので、ここで作る
    if T("teaser", None):
        step("teaser", lambda: short("teaser", [T("teaser", None), "make", work]))

    def short(name, args):  # ショート（心理学ch。2026-10-27）。作れなくても本編は止めない（その回はショート無しで先へ進む。理由は _run.log）
        try:
            run(work, name, args, ch)
        except Wait:
            raise
        except Stop as e:
            print(f"【メモ】{name} で止まりました（本編は続けます）：{str(e)[:300]}", flush=True)
    if T("short", None):
        step("short", lambda: short("short", [T("short", None), work]))
    if not upload:
        print("（--no-upload なので、アップの手前で止めました）")
        return st
    step("upload", lambda: run(work, "upload", [T("upload", "upload_job.py"), work, "--channel", ch, "--privacy", "private"], ch))
    if T("short_upload", None) and os.path.exists(os.path.join(work, "short", "short.mp4")):
        step("short_upload", lambda: short("short_upload", [T("short_upload", None), work]))
    if T("teaser", None) and os.path.exists(os.path.join(work, "teaser", "teaser.mp4")):  # 非公開で上げる。公開の予約は見張り
        step("teaser_upload", lambda: short("teaser_upload", [T("teaser", None), "upload", work, "--ch", ch, "--go"]))
    step("record", lambda: record(ch, work))
    if os.environ.get("GITHUB_ACTIONS") == "true":  # 上げ終えた回の大きいファイルは、次の実行に引き継がない（動画は YouTube にある）
        import shutil
        for d in ("images", "voice", "_build", "short", "teaser"):
            shutil.rmtree(os.path.join(work, d), ignore_errors=True)
        for x in os.listdir(work):  # 作業フォルダの直下の動画（long.mp4・アナザー日本紀の short.mp4 と _1440p の写し）
            if x.endswith(".mp4") and os.path.isfile(os.path.join(work, x)):
                os.remove(os.path.join(work, x))
    return st


def main():
    a = argparse.ArgumentParser()
    a.add_argument("ch", choices=["job", "spi", "psy", "nihongi", "okinu"])
    a.add_argument("--count", default="auto")
    a.add_argument("--no-upload", action="store_true")
    a.add_argument("--kind", default="", help="kinds のあるチャンネルで、この種類だけ作る（short／long）")
    a.add_argument("--slot", default="first", choices=["first", "retry", "late"], help="retry＝08:07・late＝17:37 のやり直し。今日の 02:07 が成功していれば何もしない")
    a = a.parse_args()
    os.environ["TZ"] = "Asia/Tokyo"
    ch = a.ch
    cloud = os.environ.get("GITHUB_ACTIONS") == "true"
    res = {"ch": ch, "started": now().isoformat(timespec="seconds"), "made": [], "stopped": None}
    cur = {"sp": hpath(ch, "status.json")}  # いま作っている回の status ファイル（種類ごとに別。止まった時にその回の失敗の数を戻す）
    lp = hpath(ch, "last_run.json")
    last = jload(lp, {})
    # 作り途中の回（時間切れで落ちた回。status.json に work が残る）がある時は、やり直しの枠でも続きを作る（2026-10-28）
    KS = kinds(ch)  # 種類ごとに作るチャンネル（アナザー日本紀）。無ければ None＝今までの動き
    kinds_run = [k for k in (KS or {}) if not a.kind or k == a.kind]
    if a.kind and KS and a.kind not in KS:
        sys.exit(f"【止まりました】{ch} の profile.json の kinds に {a.kind} がありません")
    in_progress = any(jload(status_path(ch, k), {}).get("work") for k in (kinds_run if KS else [None]))
    if a.slot != "first" and last.get("started", "")[:10] == now().date().isoformat() and not last.get("stopped") \
            and not in_progress:
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
        # 在庫の目標（profile.json の stock_goal：[目標, この本数以下なら2本]。無ければ stock_phase か STOCK_PHASE。stock_goal() の説明）
        goal, two_at = stock_goal(ch)
        n_stock = stock(ch)
        res["在庫"] = n_stock
        n = int(a.count) if a.count.isdigit() else (2 if n_stock <= two_at else 1)
        # 種類ごとのチャンネル：種類ごとの在庫で、作る本数を決める（make_max 本まで。在庫が目標に届いていて作り途中の回も無ければ作らない）
        jobs = [(None, n)]
        if KS:
            jobs = []
            res["在庫"] = {}
            for k in kinds_run:
                g, t2 = stock_goal(ch, k)
                ns = stock(ch, k)
                res["在庫"][k] = ns
                mx = int((KS[k].get("make_max")) or 2)
                nk = int(a.count) if a.count.isdigit() else (0 if ns >= g else (mx if ns <= t2 else 1))
                if nk == 0 and jload(status_path(ch, k), {}).get("work"):
                    nk = 1  # 作り途中の回は、在庫が目標に届いていても最後まで作る
                jobs.append((k, nk))
            res["作る本数"] = {k or "-": nk for k, nk in jobs}
        # 長尺を毎日は出さないチャンネル（profile.json の publish_every_days＝仕事chは 2026-10-27 から1日おき・publish_weekdays＝心理学chは 2026-10-29 から週5本）は、
        # 在庫が目標に届いていて作り途中の回も無ければ作らない（毎日作ると在庫がたまり続けるため。空いた時間はショートに回す）
        pf = jload(os.path.join(ROOT, "channels", ch, "profile.json"), {})
        if not KS and not a.count.isdigit() and (int(pf.get("publish_every_days") or 1) > 1 or len(pf.get("publish_weekdays") or range(7)) < 7) \
                and n_stock >= goal and not jload(hpath(ch, "status.json"), {}).get("work"):
            n = 0
            res["作らなかった理由"] = f"在庫が{n_stock}本で目標の{goal}本に届いている（長尺は毎日ではない）"
        for kind, n in jobs:
          sp = status_path(ch, kind)
          for i in range(n):
            cur["sp"] = sp
            st = jload(sp, {})
            if st.get("work") and "record" in st.get("done", []):
                st = {}
            if st.get("tries") and st.get("code") != code_ver():
                print(f"前の失敗の後に道具が直っているので、{os.path.basename(st['work'])} の失敗の数を0から数え直します", flush=True)
                st["tries"] = 0  # 直した後も前の3回で飛ばすと、出来上がり寸前の回を捨てる（006 がそうなった。2026-10-26）
            if st.get("tries", 0) >= 3:
                res.setdefault("飛ばした回", []).append(st["work"])
                st = {}  # 3回続けて失敗した回は飛ばして次のネタへ（週報に出す）
            if st.get("work") and st.get("started") and "upload" not in st.get("done", []) \
                    and now() - datetime.datetime.fromisoformat(st["started"]) > datetime.timedelta(hours=72):
                # 詰まった時の決まり4：72時間たっても上がらない回は飛ばす（通知の段が Issue にする。作業フォルダは消さない）
                res.setdefault("長く止まって飛ばした回", []).append(f"{os.path.basename(st['work'])}（{st.get('stage')} の段・{st['started'][:16]} から）")
                res.setdefault("飛ばした回", []).append(st["work"])
                st = {}
            if cap and month_cost(ch) >= float(cap):
                raise Stop(f"今月の制作費の累計が上限 {cap}円 に届いたので、{i}本で止めました")
            st = make_one(ch, st, not a.no_upload, kind)
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
            sp = cur["sp"]
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

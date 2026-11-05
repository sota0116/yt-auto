# Lovart の速いモード（クレジットを使う）を、詰まった回の残りにだけ短く使う（2026-10-29 本人「詰まりを取ろう」「エラーの対処を先に決めておく」）
#   python -X utf8 pipeline\lovart_boost.py restore   … この実行が速いモードにしていたら、無料モードに戻す（daily.yml の always の段）
#   python -X utf8 pipeline\lovart_boost.py check     … 速いモードのままなら無料モードに戻し、2回続けて見つけたら Issue（見張り）
#   python -X utf8 pipeline\lovart_boost.py status <ch> … 今日の上限・使った量・残り
#   python -X utf8 pipeline\lovart_boost.py balance <数> … Lovart の画面で見た残高を記録する（data\lovart_balance.json）。翌日からの上限がこれで決まる
# ・速いモードはアカウント全体に効き、戻すまで続く（Lovart 公式 SKILL の set-mode）。だから「切り替える→残りを頼む→必ず戻す」を1か所にまとめる
# ・1日の上限は data\lovart_budget.json（日付ごとの上限×チャンネルの割合）。失効が近いほど上限を上げる（本人 2026-10-29）
# ・使った量は history\<ch>\lovart_credits.json（チャンネルごとに分ける。並んで動く2つの実行が同じファイルを書き合わないため）
# ・クレジットの数は Lovart から取れないので、確認（pending_confirmation）に出た見積もりがあればそれを、無ければ data の目安で数える
import contextlib, datetime, json, os, sys, tempfile, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JST = datetime.timezone(datetime.timedelta(hours=9))
MARK = os.path.join(os.environ.get("RUNNER_TEMP") or tempfile.gettempdir(), "lovart_boost_on")


def now():
    return datetime.datetime.now(JST)


def jload(p, d):
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else d


def jsave(p, d):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".tmp"
    json.dump(d, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    os.replace(tmp, p)


def budget():
    return jload(os.path.join(ROOT, "data", "lovart_budget.json"), {})


def night(t=None):
    """Nano Banana 2／Pro が半分のクレジットになる時間（日本時間 23:00〜04:00。Lovart の画面の表示）"""
    return (t or now()).hour in (23, 0, 1, 2, 3)


def unit(kind):
    u = budget().get("unit", {})
    if kind == "image":
        return u.get("image_night", 10) if night() else u.get("image", 20)
    return u.get("video", 60)


BAL = os.path.join(ROOT, "data", "lovart_balance.json")


def period(d=None):
    d = d or now().date().isoformat()
    return next((x for x in budget().get("schedule", []) if x["from"] <= d <= x["to"]), None)


def at(s):
    t = datetime.datetime.fromisoformat(s)
    return t if t.tzinfo else t.replace(tzinfo=JST)


def readings(x):
    """期間に入ってからの、画面の残高の読み（古い順）。途中で大きく増えた時（戻った・買い足した）は、増えた後の読みだけを使う"""
    r = sorted((y for y in jload(BAL, {}).get("読み", []) if y.get("日時", "")[:10] >= x["from"]), key=lambda y: y["日時"])
    jump = [n for n in range(1, len(r)) if r[n]["残高"] > r[n - 1]["残高"] + 500]
    return r[jump[-1]:] if jump else r


def spent_log(t0, t1):
    """全チャンネルが数えた量のうち、t0 より後で t1 までの分（明細の日付と時刻で比べる）"""
    import glob
    n = 0
    for p in glob.glob(os.path.join(ROOT, "history", "*", "lovart_credits.json")):
        for day, v in jload(p, {}).items():
            for m in v.get("明細", []):
                try:
                    t = at(f"{day}T{m['時刻']}")
                except (KeyError, ValueError):
                    continue
                if t0 < t <= t1:
                    n += m.get("クレジット", 0)
    return n


def ratio(x):
    """画面の残高が実際に減った量 ÷ 仕組みが数えた量（前回は約1.6）。期間の最初と最後の読みの間で測る。
    YouTube 以外で使った分と、毎日のログインで増える分（login_per_day）も入るので、多めに出る（安全側）"""
    b = budget().get("balance", {})
    r = readings(x)
    if len(r) >= 2:
        t0, t1 = at(r[0]["日時"]), at(r[-1]["日時"])
        rec = spent_log(t0, t1)
        if rec >= b.get("min_recorded", 200):
            used = r[0]["残高"] - r[-1]["残高"] + b.get("login_per_day", 0) * (t1 - t0).total_seconds() / 86400
            return min(max(used / rec, b.get("ratio_min", 1.0)), b.get("ratio_max", 3.0))
    return b.get("ratio", 1.6)


def balance_now(x):
    """(今日の0時の残高の見込み, 今の残高の見込み, 最後の読みの日時)。読みが無ければ None"""
    r = readings(x)
    if not r:
        return None
    q, last, tl = ratio(x), r[-1]["残高"], at(r[-1]["日時"])
    ds = datetime.datetime.combine(now().date(), datetime.time(0), JST)
    start = last - q * spent_log(tl, ds) if tl <= ds else last + q * spent_log(ds, tl)
    return start, last - q * spent_log(tl, now()), tl


def total_cap(x):
    """全チャンネルを合わせた今日の上限（記録の単位）。今日の0時の残高の見込みから、残す分（floor）を引いて、
    今日を含む残りの日数と比率で割る（2026-11-05 本人「毎日実際の残りクレジットを見て翌日以降の使用クレジットを調節する」）。
    使い残しは残高に残るので自然に足され、使いすぎは自然に引かれる。読みが無い間は None（元の carry の計算に戻る）"""
    got = balance_now(x)
    if not got:
        return None
    b = budget().get("balance", {})
    left_days = (datetime.date.fromisoformat(x["to"]) - now().date()).days + 1
    t = max(0, (got[0] - b.get("floor", 4100)) / left_days / ratio(x))
    t = min(t, b.get("max_mult", 2) * x["cap"])  # 1日に使いすぎない頭打ち
    if (now() - got[2]).days >= b.get("stale_days", 3):  # 読みが古い間は、元の1日の上限より増やさない
        t = min(t, x["cap"])
    return t


def add_reading(n, src):
    if not 0 <= n <= 30000:
        sys.exit(f"【止まりました】残高 {n} は受け付けません（0〜30,000 の間だけ）")
    d = jload(BAL, {})
    d.setdefault("読み", []).append({"日時": now().isoformat(timespec="minutes"), "残高": n, "どこから": src})
    jsave(BAL, d)


def cap_today(ch):
    b = budget()
    d = now().date().isoformat()
    if d < b.get("cap_from", ""):  # 2026-11-05 本人：使い切ったので 11/17 まではクレジットを使わない
        return 0
    share = b.get("share", {}).get(ch, 0)
    x = period(d)
    if not x:
        return int(b.get("cap_after", 0) * share)
    base = x["cap"] * share
    if not x.get("carry"):
        return int(base)
    t = total_cap(x)
    if t is not None:
        return int(t * share)
    # 2026-11-05 本人「予想より使ってなかったら徐々に使用料を切り替わりのタイミングまでに増やすのはOK。ただし切り替わりよりずっと前になくなるのはなし」
    # 昨日までに使わなかった分（使いすぎた分はマイナス）を、今日を含む残りの日数で割って足す。期間の合計（cap×日数×割合）は超えない
    day = datetime.date.fromisoformat
    passed = (day(d) - day(x["from"])).days
    left_days = (day(x["to"]) - day(d)).days + 1
    unused = base * passed - spent_between(ch, x["from"], d)
    return int(max(0, base + unused / left_days))


def expiring():
    """失効するクレジットが残る間か（budget の schedule の期間）"""
    d = now().date().isoformat()
    return any(x["from"] <= d <= x["to"] for x in budget().get("schedule", []))


def boost_after():
    """同じ段が何回「途中」になったら速いモードを使うか。失効前は0回（詰まるのを待たず、在庫が足りない回は最初から使う）、その後は2回
    （2026-10-31 本人「クレジット消費をして早めたほうがいい」。18,615 のうち3日で524しか使えず、待つ決まりのままでは 11/17 に大半が失効する）"""
    return 0 if expiring() else 2


def can_join(ch):
    """別の回が速いモードにしている間、一緒に頼んでよいか。失効前で、その日の上限が残っている時だけ（上限が無いと1回で数千クレジット使える）"""
    return expiring() and left_today(ch) >= unit("image")


def spent_today(ch):
    return jload(os.path.join(ROOT, "history", ch, "lovart_credits.json"), {}).get(now().date().isoformat(), {}).get("計", 0)


def spent_between(ch, start, end):
    """start の日から end の前の日までに使った量"""
    c = jload(os.path.join(ROOT, "history", ch, "lovart_credits.json"), {})
    return sum(v.get("計", 0) for k, v in c.items() if start <= k < end)


def add_spent(ch, n, what):
    p = os.path.join(ROOT, "history", ch, "lovart_credits.json")
    c = jload(p, {})
    d = c.setdefault(now().date().isoformat(), {"計": 0, "明細": []})
    d["計"] = round(d["計"] + n, 1)
    d["明細"].append({"時刻": now().strftime("%H:%M"), "クレジット": n, "中身": what})
    jsave(p, c)


def left_today(ch):
    """その日に使える残り＝自分の割り当ての残り＋ほかのチャンネルの割り当ての使っていない分の半分（2026-10-29 本人「うまくやって」）。
    割り当てを使い切るほど詰まるチャンネルは限られ、使わない分は 11/17 に失効するので、詰まった回が借りる。半分にするのは、同じ夜に
    詰まったほかのチャンネルの分を残すため（並んで動く実行が同じ時に数えると、合計で1日の上限を少し超えることがある）"""
    # 2026-11-05 借りるのをやめた：並んで動く回が同じ空き枠を同時に数え、1日の上限の2.5〜4.4倍を使って 11/4 に使い切った（ルール違反）。
    # 自分の割り当てだけなら、全チャンネルの合計は1日の上限を超えない
    return int(max(0, cap_today(ch) - spent_today(ch)))


def client():
    """make_images_lovart.client と同じ。見張り（watch.yml）には Pillow が無いので、絵の道具を読み込まずに作る"""
    import importlib.util
    spec = importlib.util.spec_from_file_location("lovart_agent_skill", os.environ.get(
        "LOVART_SKILL", r"C:\Users\koneb\OneDrive\ClaudeBackup\tools\lovart\agent_skill.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    ak, sk = os.environ.get("LOVART_ACCESS_KEY"), os.environ.get("LOVART_SECRET_KEY")
    if not ak or not sk:
        sys.exit("【止まりました】LOVART_ACCESS_KEY / LOVART_SECRET_KEY が環境変数にありません（中身は人に見せない）")
    return m.AgentSkill(base_url=os.environ.get("LOVART_BASE_URL", "https://lgw.lovart.ai"), access_key=ak, secret_key=sk, timeout=180)


@contextlib.contextmanager
def fast_mode():
    """速いモードにして中を動かし、最後に必ず無料モードに戻す。落ちても戻せるように印のファイルを置く（restore が見る）"""
    sk = client()
    open(MARK, "w").write(now().isoformat())
    sk.set_mode(unlimited=False)
    print("Lovart を速いモード（クレジットを使う）にしました", flush=True)
    try:
        yield sk
    finally:
        try:
            sk.set_mode(unlimited=True)
            os.remove(MARK)
            print("Lovart を無料モードに戻しました", flush=True)
        except Exception as e:
            print("【注意】無料モードに戻せませんでした（後片づけの段と見張りがもう一度戻す）：", type(e).__name__, flush=True)


def restore():
    if not os.path.exists(MARK):
        return
    client().set_mode(unlimited=True)
    os.remove(MARK)
    print("落ちた実行が残した速いモードを、無料モードに戻しました", flush=True)


def check():
    sk = client()
    p = os.path.join(ROOT, "history", "lovart_mode.json")
    h = jload(p, {})
    # Lovart が「回数が多すぎる（429）」と返した時は、少し待って2回まで聞き直し、それでもだめなら今回は見ない
    # （見張りは1日2回あるので次で見る。この段が落ちると見張り全体が失敗に見えて Issue が立っていた。2026-10-29）
    for wait in (30, 90, None):
        try:
            mode = sk.query_mode()
            break
        except Exception as e:
            if getattr(e, "code", None) != 429 and "Rate limit" not in str(e):
                raise
            if wait is None:
                print(f"::warning::Lovart の回数の上限（429）で、今回はモードを確かめられませんでした。次の見張りで見ます", flush=True)
                return
            time.sleep(wait)
    if mode.get("unlimited") is True:
        jsave(p, {"fast_seen": 0, "checked": now().isoformat(timespec="seconds")})
        return
    sk.set_mode(unlimited=True)
    n = h.get("fast_seen", 0) + 1
    jsave(p, {"fast_seen": n, "checked": now().isoformat(timespec="seconds")})
    print(f"Lovart が速いモードのままだったので、無料モードに戻しました（{n}回目）", flush=True)
    if n >= 2 and not expiring():  # 失効前は速いモードの回が多いので、見つけても異常ではない
        from notify import issue
        issue("【止まりました】Lovart：速いモードのままになっていた",
              f"{now():%m/%d %H:%M} 見張りが2回続けて見つけ、無料モードに戻しました。手で速いモードを使った後なら、何もしなくてよい")


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "restore":
        restore()
    elif cmd == "check":
        check()
    elif cmd == "balance" and len(sys.argv) > 2:
        add_reading(int(sys.argv[2].replace(",", "")), sys.argv[3] if len(sys.argv) > 3 else "本人が画面で見た")
        print(f"残高 {sys.argv[2]} を記録しました（{BAL}）")
        x = period()
        if x and x.get("carry") and total_cap(x) is not None:
            print(f"全チャンネルの今日の上限：{int(total_cap(x))}（記録の単位）")
    elif cmd == "status" and len(sys.argv) > 2:
        ch = sys.argv[2]
        print(f"{ch}：今日の上限 {cap_today(ch)}・使った {spent_today(ch)}・残り {left_today(ch)}（絵1枚 {unit('image')}・動く絵1本 {unit('video')}）")
        x = period()
        got = x and balance_now(x)
        if got:
            print(f"残高の見込み：今 約{int(got[1])}（最後の読み {got[2]:%m/%d %H:%M}）・比率 {ratio(x):.2f}・全チャンネルの今日の上限 {int(total_cap(x))}")
        elif x:
            print("この期間の残高の読みがまだ無いので、元の上限（cap と使い残しの足し算）で動いています")
    else:
        sys.exit("restore / check / status <ch> / balance <画面の残高> [どこから]")


if __name__ == "__main__":
    main()

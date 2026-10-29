# Lovart の速いモード（クレジットを使う）を、詰まった回の残りにだけ短く使う（2026-10-29 本人「詰まりを取ろう」「エラーの対処を先に決めておく」）
#   python -X utf8 pipeline\lovart_boost.py restore   … この実行が速いモードにしていたら、無料モードに戻す（daily.yml の always の段）
#   python -X utf8 pipeline\lovart_boost.py check     … 速いモードのままなら無料モードに戻し、2回続けて見つけたら Issue（見張り）
#   python -X utf8 pipeline\lovart_boost.py status <ch> … 今日の上限・使った量・残り
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


def cap_today(ch):
    b = budget()
    d = now().date().isoformat()
    cap = next((x["cap"] for x in b.get("schedule", []) if x["from"] <= d <= x["to"]), b.get("cap_after", 0))
    return int(cap * b.get("share", {}).get(ch, 0))


def spent_today(ch):
    return jload(os.path.join(ROOT, "history", ch, "lovart_credits.json"), {}).get(now().date().isoformat(), {}).get("計", 0)


def add_spent(ch, n, what):
    p = os.path.join(ROOT, "history", ch, "lovart_credits.json")
    c = jload(p, {})
    d = c.setdefault(now().date().isoformat(), {"計": 0, "明細": []})
    d["計"] = round(d["計"] + n, 1)
    d["明細"].append({"時刻": now().strftime("%H:%M"), "クレジット": n, "中身": what})
    jsave(p, c)


def left_today(ch):
    return max(0, cap_today(ch) - spent_today(ch))


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
    if n >= 2:
        from notify import issue
        issue("【止まりました】Lovart：速いモードのままになっていた",
              f"{now():%m/%d %H:%M} 見張りが2回続けて見つけ、無料モードに戻しました。手で速いモードを使った後なら、何もしなくてよい")


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "restore":
        restore()
    elif cmd == "check":
        check()
    elif cmd == "status" and len(sys.argv) > 2:
        ch = sys.argv[2]
        print(f"{ch}：今日の上限 {cap_today(ch)}・使った {spent_today(ch)}・残り {left_today(ch)}（絵1枚 {unit('image')}・動く絵1本 {unit('video')}）")
    else:
        sys.exit(__doc__ or "restore / check / status <ch>")


if __name__ == "__main__":
    main()

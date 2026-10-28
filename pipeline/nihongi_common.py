# アナザー日本紀（nihongi）の道具が共通で使う物（2026-10-29 新設）。ネタ選び・台本・ゲート・声・組み立て・サムネ・アップが読む
#   ・場所：channels/nihongi（設定・ネタ帳・手順書・人物・読み・禁止表現・見本）／history/nihongi（記録）／vendor/youtube-video-maker（動画スキルの配布物）
#   ・過去の回の一覧（past_works）：手で作った分（ネタ帳.json の used）＋毎日の制作が作った分（history/nihongi/produced.json）＋作り途中の回（videos の neta.json）
import json, os, re, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CH = "nihongi"
CDIR = os.path.join(ROOT, "channels", CH)
HIST = os.path.join(ROOT, "history", CH)
VDIR = os.path.join(CDIR, "videos")
VENDOR = os.path.join(ROOT, "vendor", "youtube-video-maker", "scripts")
FIXED_END = "あなたなら、どこで歴史を変える？"  # 手順書 §3 の締めの一言の頭（ショートは「コメントで教えて。」、横動画は「コメントで教えてください。」）
SHORT_STYLE = ("劇画寄りの歴史漫画。太く力強い主線、陰の濃い塗り、行灯と夕日の暖かい色。縦長で1枚の絵に1つの場面（コマ割り・上下2分割にしない・枠を付けない）。"
               "大事な物は画面の縦30〜65%・真ん中。絵の中に文字を入れない")
LONG_STYLE = ("劇画寄りの歴史漫画。太く力強い主線、陰の濃い塗り、行灯や夕日の暖かい色。表情は大げさに。横長の画面で1枚の絵に1つの場面（コマ割り・枠を付けない）。"
              "人物は真ん中より少し右。有名なアニメ・漫画・ゲームの絵柄に似せない。絵の中に文字を入れない")
AVOID = "絵の中の文字・数字・ロゴ・看板の字、コマ割り、枠、吹き出し、血・けが"
AI_LINE = "※映像とナレーションはAIを使って作っています。"


def jload(p, default=None):
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else default


def jsave(p, obj):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    json.dump(obj, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def profile():
    return jload(os.path.join(CDIR, "profile.json"), {})


def characters():
    """{id: {name, desc_en, voice, voice_name, sheet}} と、画風の英語（style_en）"""
    d = jload(os.path.join(CDIR, "characters", "characters.json"), {})
    return d.get("chars", {}), d.get("style_en", "")


def kind_of_work(work):
    n = jload(os.path.join(work, "neta.json"), {})
    if n.get("kind") in ("short", "long"):
        return n["kind"]
    return "long" if os.path.basename(work.rstrip("/\\")).startswith("L") else "short"


def book():
    return jload(os.path.join(CDIR, "ネタ帳.json"), {})


def refill_rows():
    return jload(os.path.join(HIST, "ネタ補充.json"), [])


def past_works():
    """作った順の過去の回。{no, kind, distort, era, fact_main, 企画, work}。手で作った分 → 毎日の制作が上げた分 → 作り途中の回"""
    out = []
    for u in book().get("used", []):
        out.append({"no": u["no"], "kind": u.get("kind", "short"), "distort": u.get("distort"), "era": u.get("era"),
                    "fact_main": u.get("fact_main"), "企画": u.get("企画"), "work": u["no"], "from_short": u.get("from_short")})
    seen = {x["work"] for x in out}
    for p in jload(os.path.join(HIST, "produced.json"), []):
        if p.get("work") in seen:
            continue
        out.append({"no": p.get("no") or p.get("work", "").split("_")[0], "kind": p.get("kind") or ("long" if p.get("work", "").startswith("L") else "short"),
                    "distort": p.get("distort"), "era": p.get("era"), "fact_main": p.get("fact_main"), "企画": p.get("企画") or p.get("title"),
                    "work": p.get("work"), "from_short": p.get("from_short")})
        seen.add(p.get("work"))
    if os.path.isdir(VDIR):
        for d in sorted(os.listdir(VDIR)):
            n = jload(os.path.join(VDIR, d, "neta.json"), None)
            if n and d not in seen:
                out.append({"no": n.get("no") or d.split("_")[0], "kind": n.get("kind", "short"), "distort": n.get("distort"), "era": n.get("era"),
                            "fact_main": n.get("fact_main"), "企画": n.get("企画"), "work": d, "from_short": n.get("from_short")})
                seen.add(d)
    return out


def number_key(no):
    m = re.match(r"([SL])(\d+)", str(no or ""))
    return (int(m.group(2)) if m else 0)


def vendor_ok():
    """動画スキルの配布物（クラウドは Secrets の VENDOR_SKILL_B64 から戻す）が、アナザー日本紀の決まり（制作ルール v2.1）を点検できる版か。
    check_script.py に v2.0 で足した NG（引っ張り・動く絵・見どころ）が入っていない古い版なら、点検が甘くなるので止める"""
    p = os.path.join(VENDOR, "check_script.py")
    if not os.path.exists(p):
        return f"動画スキルがありません（{p}）"
    t = open(p, encoding="utf-8").read()
    for need in ("PULL", "\"anim\"", "\"peak\"", "world_rules"):
        if need not in t:
            return f"動画スキルが古い版です（check_script.py に {need} が無い）。Secrets の VENDOR_SKILL_B64 を新しい版に入れ替える"
    for f in ("build_short.py", "build_long.py", "make_voice.py", "make_thumb.py", "common.py"):
        if not os.path.exists(os.path.join(VENDOR, f)):
            return f"動画スキルに {f} がありません"
    return None


def vendor_run(script, *args, cwd=None, timeout=3 * 3600, capture=True):
    return subprocess.run([sys.executable, "-X", "utf8", os.path.join(VENDOR, script), *args], cwd=cwd or ROOT,
                          capture_output=capture, text=True, encoding="utf-8", errors="replace", timeout=timeout)


def claude_env():
    """claude -p に渡す環境。鍵は消す（書く作業・選ぶ作業に鍵を渡さない）"""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from write_script import SECRET_ENV
    env = {k: v for k, v in os.environ.items() if k not in SECRET_ENV + ("YT_TOKEN_PSY", "YT_TOKEN")}
    env["YT_SECRETS_DIR"] = os.path.join(ROOT, "_no_secrets_here")
    return env

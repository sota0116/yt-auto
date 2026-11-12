# 「Claude が1本作る」チャンネル（agent.yml：shimei・kakure）の絵を、PC の Codex に回すための受け渡し（2026-11-07 本人「ショート間空きすぎるのダメだからcodexでよろしく」）
#   python -X utf8 pipeline/codex_todo.py export <ch>       … 絵がまだ無いカットの注文書を history/<ch>/codex_todo/<回>.json に書く（agent.yml の終わりで commit される）
#   python -X utf8 pipeline/codex_todo.py fetch <作業フォルダ> … PC の Codex が release「codex-images」に置いた絵を images/<id>.png に受け取る
#   python -X utf8 pipeline/codex_todo.py fetch-all <ch>    … そのチャンネルの作業フォルダ全部で fetch（agent.yml の「作る」の前）
# ・作りかけの台本は暗号の保存（agent-state）にあり、PC からは読めない。そこで絵の注文に要る物（英語の場面・画風・人物の見た目・チャンネルの絵の決まり）だけを書き出す。
#   ナレーション・題・説明文は書き出さない。リポジトリは公開なので、絵の場面だけは公開前に見える（絵そのものも公開の release に置くのと同じ扱い）
# ・PC 側は make_images_codex.py --auto が注文書を読み、Codex で作って release に置く。名前は make_images_lovart.codex_name で決まる（場面の文が変われば別の名前）
# ・絵が全部そろった回・消えた回の注文書は、次の export で消える
import glob, json, os, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))


def jload(p, d=None):
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return d


def image_cuts(s):
    return [c for c in s.get("cuts", []) if c.get("image") and not c.get("same_as") and not c.get("chart")]


def is_short(work, s):
    return s.get("format") == "short" or os.path.basename(os.path.normpath(work)).startswith("S")


def active(work):
    """作っている途中の回だけ。upload.json がある回（上げ待ち・上げ済み。上げ済みは images を消してある）と中止の回は外す"""
    if any(os.path.exists(os.path.join(work, n)) for n in ("upload.json", "uploaded.json")):
        return False
    ar = os.path.join(work, "_auto_run.md")
    return not (os.path.exists(ar) and "\n## 中止" in "\n" + open(ar, encoding="utf-8", errors="replace").read())


def missing(work, s):
    return [c for c in image_cuts(s) if not os.path.exists(os.path.join(work, "images", c["id"] + ".png"))]


def export(ch):
    cdir = os.path.join(ROOT, "channels", ch)
    out = os.path.join(ROOT, "history", ch, "codex_todo")
    chan_chars = (jload(os.path.join(cdir, "characters", "characters.json"), {}) or {}).get("chars", {})
    rules = (jload(os.path.join(cdir, "profile.json"), {}) or {}).get("image_rules_en") or {}
    keep = set()
    for sp in sorted(glob.glob(os.path.join(cdir, "videos", "*", "script.json"))):
        work = os.path.dirname(sp)
        wk = os.path.basename(work)
        s = jload(sp)
        if not s or not active(work):
            continue
        todo = missing(work, s)
        if not todo:
            continue
        en = jload(os.path.join(work, "images", "_scene_en.json"), {}) or {}
        need = {k for c in todo for k in c.get("chars", [])}
        chars = {k: {"desc_en": v["desc_en"], "channel": True} for k, v in chan_chars.items() if k in need and v.get("desc_en")}
        chars.update({k: {"desc_en": v["desc_en"]} for k, v in (s.get("characters") or {}).items() if k in need and v.get("desc_en")})
        doc = {"ch": ch, "work": wk, "portrait": is_short(work, s), "made": time.strftime("%Y-%m-%d %H:%M"),
               "style_en": s.get("style_en") or en.get("_style") or s.get("style", ""),
               "avoid_en": s.get("avoid_en") or en.get("_avoid") or s.get("avoid", ""),
               "rules": rules, "characters": chars,
               # image・image_en は名前（codex_name）を決めるのでそのまま。en は Codex に渡す英語の場面
               "cuts": [{k: c[k] for k in ("id", "image", "image_en", "chars", "nobody") if k in c}
                        | {"en": c.get("image_en") or en.get(c["id"]) or ""} for c in todo]}
        os.makedirs(out, exist_ok=True)
        p = os.path.join(out, wk + ".json")
        old = jload(p, {}) or {}
        if {k: v for k, v in old.items() if k != "made"} != {k: v for k, v in doc.items() if k != "made"}:
            json.dump(doc, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        keep.add(wk + ".json")
        print(f"{ch}/{wk}：絵の無いカット {len(todo)} 枚を Codex の注文書に書きました", flush=True)
    for p in glob.glob(os.path.join(out, "*.json")):
        if os.path.basename(p) not in keep:
            os.remove(p)
            print(f"{os.path.basename(p)}：絵がそろった（または回が無い）ので注文書を消しました", flush=True)


def fetch(work):
    import make_images_lovart as ML
    s = jload(os.path.join(work, "script.json"))
    if not s or not active(work):
        return 0
    ch = os.path.basename(os.path.dirname(os.path.dirname(os.path.abspath(work))))
    cuts = {c["id"]: c for c in image_cuts(s)}
    need = [c["id"] for c in missing(work, s)]
    if not need:
        return 0
    img = os.path.join(work, "images")
    os.makedirs(img, exist_ok=True)
    lp = os.path.join(img, "_lovart.json")
    log = jload(lp, {}) or {}
    got = ML.codex_fill(work, ch, cuts, need, log, is_short(work, s))
    if got:
        json.dump(log, open(lp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"{os.path.basename(work)}：Codex の絵 {len(got)} 枚を受け取り、まだ無い絵 {len(need) - len(got)} 枚", flush=True)
    return len(got)


def main():
    if len(sys.argv) < 3 or sys.argv[1] not in ("export", "fetch", "fetch-all"):
        sys.exit(__doc__ or "使い方：codex_todo.py export|fetch|fetch-all <ch か 作業フォルダ>")
    cmd, arg = sys.argv[1], sys.argv[2]
    if cmd == "export":
        export(arg)
    elif cmd == "fetch":
        fetch(arg)
    else:
        for sp in sorted(glob.glob(os.path.join(ROOT, "channels", arg, "videos", "*", "script.json"))):
            fetch(os.path.dirname(sp))


if __name__ == "__main__":
    main()

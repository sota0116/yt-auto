# Lovart の代わりに、PC の Codex（ChatGPT の画像生成）で絵を作り、GitHub の release「codex-images」に置く（2026-11-07）
#   python -X utf8 pipeline\make_images_codex.py [job/019_c_denki okinu/S111_期限切れのクーポン券 ...] [--par 3] [--limit 0] [--dry]
# ・PC 専用。Codex の ChatGPT ログインで動く（Actions では動かない。~/.codex/auth.json は読まない・どこにも写さない）
# ・対象は history\<ch>\wip\<回>\script.json の絵のカット（same_as・chart を除く）のうち、_lovart.json で「できた」になっていない物
# ・Actions の make_images_lovart.py が、Lovart に頼む前に同じ名前（codex_name）の絵を release から受け取る。無い絵は今までどおり Lovart
# ・プロンプトは make_images_lovart.prompt をそのまま使う（画風・チャンネルの絵の決まり・文字なし・人物の設定画の添付）。
#   英語の場面（image_en）が無いカットは、日本語の場面をそのまま渡す
# ・その回だけの人物（script.json の characters）の設定画は Actions のキャッシュにしか無いので、PC で Codex に設定画を作らせて添付する
# ・回数の上限らしい失敗が3回続いたら止める（ChatGPT の枠は不明）
# ・release は公開（リポジトリが公開のため）。動画で公開する絵なので、そのまま置く
import argparse, glob, json, os, shutil, subprocess, sys, tempfile, threading, time
from concurrent.futures import ThreadPoolExecutor
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))
import make_images_lovart as ML

REPO, TAG = "sota0116/yt-auto", "codex-images"
OUT = os.environ.get("CODEX_IMAGES_OUT", r"C:\tmp\codex_images")
GEN = os.path.join(os.path.expanduser("~"), ".codex", "generated_images")
MODEL = os.environ.get("CODEX_IMAGE_MODEL", "gpt-5.6-luna")
# 在庫が切れる順（2026-11-07 時点）
ORDER = ["job/019_c_denki", "job/021_c_seibi", "okinu/101_通帳まわりの3つ", "okinu/S111_期限切れのクーポン券", "okinu/S112_五円玉",
         "okinu/S113_新札", "nihongi/S112_n017", "nihongi/S113_n012", "nihongi/S114_n018", "psy/013_jiman_hito", "psy/014_ikigai_yakuwari",
         "nihongi/L106_long_s105", "psy/015_kanojo_iya", "nihongi/L105_long_s102", "nihongi/L107_long_s110", "spi/017_b_ujigami_2026"]
lock = threading.Lock()
fails = [0]


def logline(**k):
    with lock:
        with open(os.path.join(OUT, "_log.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps({"t": time.strftime("%m-%d %H:%M:%S"), **k}, ensure_ascii=False) + "\n")


def have_assets():
    r = subprocess.run(["gh", "api", "--paginate", f"repos/{REPO}/releases/tags/{TAG}", "--jq", ".assets[].name"],
                       capture_output=True, text=True, encoding="utf-8")
    names = set(r.stdout.split())
    rid = subprocess.run(["gh", "api", f"repos/{REPO}/releases/tags/{TAG}", "--jq", ".id"], capture_output=True, text=True).stdout.strip()
    if rid:  # 30件を超える分（tags の答えは assets を全部は返さない）
        r = subprocess.run(["gh", "api", "--paginate", f"repos/{REPO}/releases/{rid}/assets?per_page=100", "--jq", ".[].name"],
                           capture_output=True, text=True, encoding="utf-8")
        names |= set(r.stdout.split())
    return names


def codex(prompt, images=()):
    """Codex に1回頼み、できた絵のパスを返す（できなければ None と理由）"""
    exe = shutil.which("codex") or shutil.which("codex.cmd")
    with tempfile.TemporaryDirectory() as d:
        cmd = [exe, "exec", "--json", "--skip-git-repo-check", "-m", MODEL, "-c", "model_reasoning_effort=low", "-s", "read-only"]
        for p in images:
            cmd += ["-i", p]
        cmd += ["-"]
        try:
            r = subprocess.run(cmd, input=prompt, capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=d, timeout=900)
        except subprocess.TimeoutExpired:
            return None, "15分で終わらない"
    tid = None
    for ln in r.stdout.splitlines():
        try:
            ev = json.loads(ln)
        except Exception:
            continue
        tid = tid or ev.get("thread_id") or (ev.get("msg") or {}).get("thread_id")
    got = sorted(glob.glob(os.path.join(GEN, tid, "*.png")), key=os.path.getmtime) if tid else []
    if got:
        return got[-1], ""
    tail = (r.stdout[-400:] + r.stderr[-400:]).replace("\n", " ")
    return None, tail


def to_jpg(src, dst):
    Image.open(src).convert("RGB").save(dst, "JPEG", quality=93)


def upload(path):
    r = subprocess.run(["gh", "release", "upload", TAG, path, "--clobber", "--repo", REPO], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return r.returncode == 0, r.stderr[-300:]


def plan(ch, wk):
    d = os.path.join(ROOT, "history", ch, "wip", wk)
    s = json.load(open(os.path.join(d, "script.json"), encoding="utf-8"))
    lp = os.path.join(d, "images", "_lovart.json")
    lg = json.load(open(lp, encoding="utf-8")) if os.path.exists(lp) else {}
    cuts = [c for c in s["cuts"] if c.get("image") and not c.get("same_as") and not c.get("chart") and lg.get(c["id"], {}).get("状態") != "できた"]
    return s, cuts


def sheets(ch, wk, s, need):
    """人物の設定画のパス。チャンネルの人は git の characters\\、その回だけの人は PC で Codex に作らせる"""
    cdir = os.path.join(ROOT, "channels", ch, "characters")
    cp = os.path.join(cdir, "characters.json")
    chars = {}
    if os.path.exists(cp):
        for k, v in json.load(open(cp, encoding="utf-8")).get("chars", {}).items():
            chars[k] = {"desc_en": v["desc_en"], "sheet": os.path.join(cdir, v.get("sheet", k + ".png"))}
    style = s.get("style_en") or s.get("style", "")
    for k, v in (s.get("characters") or {}).items():
        p = os.path.join(OUT, "_chars", f"{ch}__{wk}__{k}.png")
        chars[k] = {"desc_en": v["desc_en"], "sheet": p}
        if k in need and not os.path.exists(p):
            os.makedirs(os.path.dirname(p), exist_ok=True)
            src, why = codex("Use your image generation tool.\n" + ML.sheet_prompt(style, chars[k]))
            if not src:
                print(f"{ch}/{wk} {k} の設定画ができない：{why[:200]}", flush=True)
                continue
            ML.to_png(src, p)
            print(f"{ch}/{wk} {k} の設定画を作りました", flush=True)
    return chars


def main():
    a = argparse.ArgumentParser()
    a.add_argument("works", nargs="*")
    a.add_argument("--par", type=int, default=3)
    a.add_argument("--limit", type=int, default=0, help="作る枚数の上限（0＝全部）")
    a.add_argument("--dry", action="store_true")
    a = a.parse_args()
    os.makedirs(OUT, exist_ok=True)
    have = set() if a.dry else have_assets()
    jobs = []
    for w in a.works or ORDER:
        ch, wk = w.replace("\\", "/").split("/", 1)
        s, cuts = plan(ch, wk)
        rules = (json.load(open(os.path.join(ROOT, "channels", ch, "profile.json"), encoding="utf-8")).get("image_rules_en") or {}) \
            if os.path.exists(os.path.join(ROOT, "channels", ch, "profile.json")) else {}
        work_like = os.path.join("channels", ch, "videos", wk)  # 名前は回の名前とチャンネルだけで決まる
        todo = [c for c in cuts if ML.codex_name(ch, work_like, c) not in have]
        print(f"{ch}/{wk}：絵 {len(cuts)} 枚のうち、まだ release に無い {len(todo)} 枚", flush=True)
        if a.dry or not todo:
            continue
        need = sorted({k for c in todo for k in c.get("chars", [])})
        chars = sheets(ch, wk, s, need)
        en = {"_style": s.get("style_en") or s.get("style", "")}
        if s.get("avoid_en") or s.get("avoid"):
            en["_avoid"] = s.get("avoid_en") or s.get("avoid")
        portrait = s.get("format") == "short"
        for c in todo:
            ok_chars = [chars[k] for k in c.get("chars", []) if k in chars and os.path.exists(chars[k]["sheet"])]
            en[c["id"]] = c.get("image_en") or ("(The scene is written in Japanese; draw it, but write no Japanese or any text in the picture) "
                                                + c["image"])
            p = ("Use your image generation tool to create the picture below. Do not write any files yourself.\n"
                 + ML.prompt(en, c, False, "", ok_chars, rules, portrait))
            jobs.append((ch, wk, c["id"], ML.codex_name(ch, work_like, c), p, [x["sheet"] for x in ok_chars]))
    if a.limit:
        jobs = jobs[:a.limit]
    print(f"Codex で作る：{len(jobs)} 枚（同時に{a.par}本）", flush=True)
    stop = threading.Event()

    def one(j):
        ch, wk, cid, name, p, imgs = j
        if stop.is_set():
            return
        dst = os.path.join(OUT, name)
        t0 = time.time()
        if not os.path.exists(dst):
            src, why = codex(p, imgs)
            if not src:
                with lock:
                    fails[0] += 1
                    if fails[0] >= 3:
                        stop.set()
                print(f"× {ch}/{wk} {cid}：{why[:300]}", flush=True)
                logline(ch=ch, work=wk, id=cid, ok=False, why=why[:500])
                return
            with lock:
                fails[0] = 0
            to_jpg(src, dst)
        ok, err = upload(dst)
        print(f"{'○' if ok else '△'} {ch}/{wk} {cid} {round(time.time() - t0)}秒 {'' if ok else err}", flush=True)
        logline(ch=ch, work=wk, id=cid, ok=ok, sec=round(time.time() - t0), name=name, err="" if ok else err)

    with ThreadPoolExecutor(a.par) as ex:
        list(ex.map(one, jobs))
    if stop.is_set():
        print("【止まりました】Codex の失敗が3回続いた（ChatGPT の回数の上限の可能性）。時間をあけてもう一度動かすと続きから作ります", flush=True)
        sys.exit(2)


if __name__ == "__main__":
    main()

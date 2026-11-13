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
# ・--auto（2026-11-07 追加。PC のタスクスケジューラが30分ごとに動かす）：回を指定せず、
#   history\<ch>\codex_todo\*.json（agent.yml のチャンネル＝shimei・kakure の注文書。codex_todo.py export が書く）と
#   history\<ch>\wip\*\script.json を全部見て、ショート → 注文書 → その他 の順に作る。3回続けて失敗したら90分休む（_pause_until）
# ・--auto は動き始めに、今いない回（status*.json・parked*.json・注文書のどれにも無い回）の絵を release から消し、
#   作るのも今いる回だけにする（2026-11-13。release は1000件までで、満杯になって新しい絵を置けなくなった）
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
    """release にある絵の「名前 → asset の番号」（番号は消す時に使う）"""
    rid = subprocess.run(["gh", "api", f"repos/{REPO}/releases/tags/{TAG}", "--jq", ".id"], capture_output=True, text=True).stdout.strip()
    if not rid:
        return {}
    r = subprocess.run(["gh", "api", "--paginate", f"repos/{REPO}/releases/{rid}/assets?per_page=100", "--jq", '.[] | "\\(.id) \\(.name)"'],
                       capture_output=True, text=True, encoding="utf-8")
    return {n: i for i, n in (ln.split(" ", 1) for ln in r.stdout.splitlines() if " " in ln)}


def wanted():
    """今いる回（作っている途中・後回し・注文書）の「(チャンネル, 回) → 作り始めた時刻」。
    1つでも読めないファイルがあれば None（その時は消さない・絞らない）"""
    out = {}
    H = os.path.join(ROOT, "history")
    try:
        for p in glob.glob(os.path.join(H, "*", "status*.json")) + glob.glob(os.path.join(H, "*", "parked*.json")):
            d = json.load(open(p, encoding="utf-8"))
            for st in d if isinstance(d, list) else [d]:
                if st.get("work"):
                    out[(os.path.basename(os.path.dirname(p)), os.path.basename(st["work"].replace("\\", "/")))] = st.get("started") or ""
        for p in glob.glob(os.path.join(H, "*", "codex_todo", "*.json")):
            d = json.load(open(p, encoding="utf-8"))
            out[(d["ch"], d["work"])] = ""
    except Exception as e:
        print(f"今いる回を読めない（{type(e).__name__} {e}）", flush=True)
        return None
    return out


def clean(have, dry=False):
    """今いない回（上げ終わった回・飛ばされた回）の絵を release から消す（2026-11-13）。
    release は1つに1000件までで、満杯になると新しい絵を置けず、全チャンネルが絵の段で止まった。
    絵は OUT にも残っているので、要る時は作り直さずに置き直せる"""
    keep = wanted()
    if not keep:
        print("今いる回が分からないので、release の掃除はしない", flush=True)
        return
    pre = lambda n: "__".join(n.split("__")[:2])
    ok = {pre(ML.codex_name(ch, os.path.join("channels", ch, "videos", wk), {"id": "", "image": ""})) for ch, wk in keep}
    old = sorted(n for n in have if n.count("__") == 3 and n.endswith(".jpg") and pre(n) not in ok)
    print(f"release の絵 {len(have)} 枚のうち、今いない回の絵 {len(old)} 枚を{'消す対象にする（--dry なので消さない）' if dry else '消します'}", flush=True)
    if dry:
        return
    for n in old:  # 1枚ずつ、間をあけて（GitHub の書き込みの回数の制限に当たらないように）
        r = subprocess.run(["gh", "api", "-X", "DELETE", f"repos/{REPO}/releases/assets/{have[n]}"], capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        if r.returncode:
            print(f"消せない（残りは次の回で消す）：{n} {r.stderr[-200:]}", flush=True)
            break
        del have[n]
        time.sleep(1)
    print(f"掃除のあとの release の絵：{len(have)} 枚", flush=True)


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


def sheets(ch, wk, s, need, chan=None):
    """人物の設定画のパス。チャンネルの人は git の characters\\、その回だけの人は PC で Codex に作らせる。
    chan（注文書の "channel": true の人）は、git に設定画が無ければ PC で作り、チャンネル単位で使い回す"""
    cdir = os.path.join(ROOT, "channels", ch, "characters")
    cp = os.path.join(cdir, "characters.json")
    chars = {}
    if os.path.exists(cp):
        for k, v in json.load(open(cp, encoding="utf-8")).get("chars", {}).items():
            chars[k] = {"desc_en": v["desc_en"], "sheet": os.path.join(cdir, v.get("sheet", k + ".png"))}
    style = s.get("style_en") or s.get("style", "")
    todo = [(k, v, os.path.join(OUT, "_chars", f"{ch}__{wk}__{k}.png")) for k, v in (s.get("characters") or {}).items()]
    todo += [(k, v, os.path.join(OUT, "_chars", f"{ch}__{k}.png")) for k, v in (chan or {}).items()
             if not (k in chars and os.path.exists(chars[k]["sheet"]))]
    for k, v, p in todo:
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


def rules_of(ch):
    p = os.path.join(ROOT, "channels", ch, "profile.json")
    return (json.load(open(p, encoding="utf-8")).get("image_rules_en") or {}) if os.path.exists(p) else {}


def wip_spec(ch, wk):
    s, cuts = plan(ch, wk)
    return {"ch": ch, "wk": wk, "s": s, "cuts": cuts, "rules": rules_of(ch), "chan": None,
            "portrait": s.get("format") == "short", "todo": False}


def todo_spec(p):
    """codex_todo.py export の注文書（agent.yml のチャンネル。台本は暗号の保存にあり、PC には絵の注文だけが来る）"""
    d = json.load(open(p, encoding="utf-8"))
    chars = d.get("characters") or {}
    s = {"style_en": d.get("style_en", ""), "avoid_en": d.get("avoid_en", ""),
         "characters": {k: v for k, v in chars.items() if not v.get("channel")}}
    return {"ch": d["ch"], "wk": d["work"], "s": s, "cuts": d["cuts"], "rules": d.get("rules") or {},
            "chan": {k: v for k, v in chars.items() if v.get("channel")}, "portrait": bool(d.get("portrait")), "todo": True}


def auto_specs():
    out = []
    keep = wanted()
    for p in glob.glob(os.path.join(ROOT, "history", "*", "codex_todo", "*.json")):
        try:
            out.append(todo_spec(p))
        except Exception as e:
            print(f"{p}：注文書を読めない（{type(e).__name__}）", flush=True)
    for sp in glob.glob(os.path.join(ROOT, "history", "*", "wip", "*", "script.json")):
        wk = os.path.basename(os.path.dirname(sp))
        ch = os.path.basename(os.path.dirname(os.path.dirname(os.path.dirname(sp))))
        if keep and (ch, wk) not in keep:
            continue  # 飛ばされた回の控え（wip）は残り続ける。その絵は使われないので作らない（2026-11-13）
        try:
            out.append(wip_spec(ch, wk))
        except Exception as e:
            print(f"{ch}/{wk}：台本を読めない（{type(e).__name__}）", flush=True)
    # 待ち始めが古い回を先に（72時間で飛ばされる前に届ける）
    return sorted(out, key=lambda x: (not x["portrait"], not x["todo"], (keep or {}).get((x["ch"], x["wk"]), ""), x["ch"], x["wk"]))


PAUSE = os.path.join(OUT, "_pause_until")


def main():
    a = argparse.ArgumentParser()
    a.add_argument("works", nargs="*")
    a.add_argument("--auto", action="store_true", help="注文書と wip を全部見て作る（タスクスケジューラ用）")
    a.add_argument("--par", type=int, default=3)
    a.add_argument("--limit", type=int, default=0, help="作る枚数の上限（0＝全部）")
    a.add_argument("--dry", action="store_true")
    a = a.parse_args()
    os.makedirs(OUT, exist_ok=True)
    if a.auto and not a.dry and os.path.exists(PAUSE):
        try:
            until = float(open(PAUSE).read().strip())
        except Exception:
            until = 0
        if time.time() < until:
            print(f"休み中（Codex の失敗が続いたため）：{time.strftime('%m-%d %H:%M', time.localtime(until))} まで", flush=True)
            return
        os.remove(PAUSE)
    have = have_assets()  # 読むだけなので --dry でも取る
    if a.auto:
        clean(have, a.dry)
        specs = auto_specs()
    else:
        specs = [wip_spec(*w.replace("\\", "/").split("/", 1)) for w in (a.works or ORDER)]
    jobs = []
    for sp in specs:
        ch, wk, s, cuts, rules, portrait = sp["ch"], sp["wk"], sp["s"], sp["cuts"], sp["rules"], sp["portrait"]
        work_like = os.path.join("channels", ch, "videos", wk)  # 名前は回の名前とチャンネルだけで決まる
        todo = [c for c in cuts if ML.codex_name(ch, work_like, c) not in have]
        print(f"{ch}/{wk}{'（注文書）' if sp['todo'] else ''}{'（縦）' if portrait else ''}：絵 {len(cuts)} 枚のうち、まだ release に無い {len(todo)} 枚", flush=True)
        if a.dry or not todo:
            continue
        need = sorted({k for c in todo for k in c.get("chars", [])})
        chars = sheets(ch, wk, s, need, sp["chan"])
        en = {"_style": s.get("style_en") or s.get("style", "")}
        if s.get("avoid_en") or s.get("avoid"):
            en["_avoid"] = s.get("avoid_en") or s.get("avoid")
        for c in todo:
            ok_chars = [chars[k] for k in c.get("chars", []) if k in chars and os.path.exists(chars[k]["sheet"])]
            en[c["id"]] = c.get("en") or c.get("image_en") or ("(The scene is written in Japanese; draw it, but write no Japanese or any text in the picture) "
                                                               + c["image"])
            p = ("Use your image generation tool to create the picture below. Do not write any files yourself.\n"
                 + ML.prompt(en, c, False, "", ok_chars, rules, portrait))
            jobs.append((ch, wk, c["id"], ML.codex_name(ch, work_like, c), p, [x["sheet"] for x in ok_chars]))
    if a.limit:
        jobs = jobs[:a.limit]
    print(f"Codex で作る：{len(jobs)} 枚（同時に{a.par}本）", flush=True)
    stop = threading.Event()
    full = threading.Event()

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
        if not ok and "limited to 1000" in err:  # 満杯の間は何枚作っても置けないので、残りを試さない
            full.set()
            stop.set()

    with ThreadPoolExecutor(a.par) as ex:
        list(ex.map(one, jobs))
    if full.is_set():
        print("【止まりました】release「codex-images」が上限の1000件で、絵を置けない。--auto は動き始めに今いない回の絵を消すので、"
              "それでも満杯なら、今いる回だけで1000枚を超えている", flush=True)
        sys.exit(3)
    if stop.is_set():
        if a.auto:
            open(PAUSE, "w").write(str(time.time() + 90 * 60))
        print("【止まりました】Codex の失敗が3回続いた（ChatGPT の回数の上限の可能性）。時間をあけてもう一度動かすと続きから作ります", flush=True)
        sys.exit(2)


if __name__ == "__main__":
    main()

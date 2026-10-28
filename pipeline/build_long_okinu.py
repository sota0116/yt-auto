# ⑧組み立て・長尺（金運おきぬ・2026-10-29 新設）：build_long_spi.py（千年こよみ）を okinu 用に写したもの。カードは motion_cards_spi.py の kinun 配色（001 v6 の作り）
#   python -X utf8 pipeline/build_long_okinu.py <作業フォルダ> [--out long.mp4] [--par 3] [--tempo 1.1 --gap 0.35] [--only-cards] [--height 1080]
# ・設定は channels/okinu/profile.json の build（声は 0.85 で作って組み立てで 1.1 倍・間 0.35・−14 LUFS・1440p・字幕 72px／22字・BGM 0.02・カード kinun）。
#   コマンドの引数が優先。script.json の tempo・gap は使わない（手で作った 001 の値が残っているため）
# ・流れ・カードの中身・絵の探し方・BGM の探し方は build_long_spi.py と同じ（BGM は環境変数 OKINU_BGM → profile の build.bgm（m4a）→ script.json の bgm）
#   2026-10-29 試験：金運おきぬの黄金サンプル 001v6 から6カット（章の題・図解カード・2枚並べ・絵）を抜いて声 → カード → 組み立て。19秒・−14.2 LUFS・字幕の切り替えは声の間に一致
# ・字幕の字：Windows は Noto Sans JP Bold、Linux は Noto Sans CJK JP Bold（fonts-noto-cjk）
import argparse, hashlib, json, os, re, shutil, subprocess, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "vendor", "youtube-video-maker", "scripts"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import dur, run, voice_path, chunks, ass_time, prep_voice  # noqa: E402
from build_long_psy import onsets, sub_starts  # noqa: E402
import motion_cards_spi as MC  # noqa: E402

W, H, FPS = 1920, 1080, 30
INK, WASHI = "22262B", "E3F1F7"  # &HBBGGRR（墨 #2B2622・和紙 #F7F1E3）
CLOUD = os.environ.get("GITHUB_ACTIONS") == "true"
SUB_FONTS = [(r"C:\Windows\Fonts\NotoSansJP-Bold.ttf", "Noto Sans JP"),
             (os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Windows\Fonts\NotoSansJP-Bold.ttf"), "Noto Sans JP"),
             ("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc", "Noto Sans CJK JP"),
             ("/usr/share/fonts/noto-cjk/NotoSansCJK-Bold.ttc", "Noto Sans CJK JP")]


def mt(p):
    return f"{os.path.getmtime(p):.0f}:{os.path.getsize(p)}" if p and os.path.exists(p) else "-"


def find_bgm(work, sc, prof):
    for p in (os.environ.get("OKINU_BGM"), os.path.join(ROOT, prof["bgm"]) if prof.get("bgm") else None,
              os.path.join(work, sc["bgm"]) if sc.get("bgm") else None):
        if p and os.path.exists(p):
            return os.path.abspath(p)
    raise SystemExit("【止まりました】BGM が見つかりません（環境変数 OKINU_BGM か、profile.json の build.bgm の場所に wav を置く）")


def pic(work, cuts, c):
    """そのカットの絵（png）と動く絵（mp4）。same_as は先をたどる"""
    seen, cur = set(), c
    while True:
        im = os.path.join(work, "images")
        for name in (cur["id"], cur.get("img_src")):
            if name and os.path.exists(os.path.join(im, name + ".png")):
                src = os.path.join(im, name + ".png")
                vid = None
                if cur.get("motion") and os.path.exists(os.path.join(im, cur["id"] + ".mp4")):
                    vid = os.path.join(im, cur["id"] + ".mp4")
                else:
                    for n2 in (cur["id"], cur.get("img_src")):
                        if n2 and os.path.exists(os.path.join(im, "_kling", n2 + ".mp4")):
                            vid = os.path.join(im, "_kling", n2 + ".mp4")
                            break
                return src, vid
        if not cur.get("same_as") or cur["id"] in seen:
            return None, None
        seen.add(cur["id"])
        cur = next((x for x in cuts if x["id"] == cur["same_as"]), {"id": ""})


def webm(src, b):
    """Playwright の chromium は H.264 を読めないことがあるので、動く絵を VP9 に直す（作り直しは元が変わった時だけ）"""
    out = os.path.join(b, "webm", hashlib.md5(f"{src}|{mt(src)}".encode()).hexdigest()[:16] + ".webm")
    if not os.path.exists(out):
        os.makedirs(os.path.dirname(out), exist_ok=True)
        run("ffmpeg", "-v", "error", "-y", "-i", src, "-an", "-c:v", "libvpx-vp9", "-b:v", "0", "-crf", "30", "-row-mt", "1",
            "-deadline", "realtime", "-cpu-used", "8", out + ".part.webm")
        os.replace(out + ".part.webm", out)
    return out


def card_spec(work, cuts, c, n, b):
    from pathlib import Path
    if c.get("card"):
        spec = dict(c["card"], seed=n)
        if c.get("era") and spec.get("type") == "photo":
            spec.setdefault("era", c["era"])
    else:
        spec = {"type": "photo", "seed": n, **(c.get("photo") or {})}
        if c.get("era"):
            spec["era"] = c["era"]
    if spec["type"] != "photo":
        return spec, []
    src, vid = pic(work, cuts, c)
    if not src:
        return None, []
    spec["src"] = Path(src).resolve().as_uri()
    deps = [src]
    if vid:
        deps.append(vid)
        spec["video"] = Path(webm(vid, b) if MC.uses_bundled() else vid).resolve().as_uri()
    return spec, deps


def make_cards(work, b, cuts, durs, theme, data, clips, par, stamps, stamp_p):
    html = os.path.join(os.path.dirname(os.path.abspath(__file__)), "motion_cards_spi.html")
    todo, miss = [], []
    for n, c in enumerate(cuts):
        spec, deps = card_spec(work, cuts, c, n, b)
        if spec is None:
            miss.append(c["id"]); continue
        d = durs[c["id"]] + 0.3
        out = os.path.join(work, clips, c["id"] + ".mp4")
        key = hashlib.md5(json.dumps([spec, round(d, 2), theme, data, [mt(x) for x in deps], mt(html), mt(MC.__file__)],
                                     ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        if stamps.get(c["id"] + ":card") == key and os.path.exists(out):
            continue
        todo.append({"id": c["id"], "spec": spec, "dur": d, "out": out, "key": key})
    if miss:
        raise SystemExit(f"【止まりました】絵（images/<id>.png）が無いカット：{miss[:12]}（{len(miss)}カット）")
    print(f"動く図解カード：作る {len(todo)}／前のまま {len(cuts) - len(todo)}（同時に {par}）", flush=True)
    t0 = time.time()
    for tri in range(2):
        if not todo:
            break
        groups = [todo[i::par] for i in range(par) if todo[i::par]]
        procs = []
        for k, g in enumerate(groups):
            jp = os.path.join(b, f"cards_{k}.json")
            json.dump({"theme": theme, "data": data, "items": g}, open(jp, "w", encoding="utf-8"), ensure_ascii=False)
            log = open(os.path.join(b, f"cards_{k}.log"), "a", encoding="utf-8")
            procs.append((subprocess.Popen([sys.executable, "-X", "utf8", MC.__file__, "--jobs", jp], stdout=log, stderr=subprocess.STDOUT), log))
        for p, log in procs:
            p.wait()
            log.close()
        for it in todo:
            if os.path.exists(it["out"]) and os.path.getmtime(it["out"]) >= t0:
                stamps[it["id"] + ":card"] = it["key"]
        json.dump(stamps, open(stamp_p, "w", encoding="utf-8"), ensure_ascii=False)
        todo = [it for it in todo if stamps.get(it["id"] + ":card") != it["key"]]
        if todo:
            print(f"（できなかったカード {[x['id'] for x in todo]} を、もう一度描きます）", flush=True)
            par = 1
    if todo:
        raise SystemExit(f"【止まりました】カードを描けませんでした：{[x['id'] for x in todo]}（{b}/cards_*.log）")
    print(f"動く図解カード：{(time.time() - t0) / 60:.1f}分", flush=True)


def loud(path, cwd):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", path, "-af", "ebur128=peak=true", "-f", "null", "-"],
                       capture_output=True, text=True, cwd=cwd)
    m = re.findall(r"I:\s+(-?[\d.]+) LUFS", r.stderr)
    return float(m[-1]) if m else None


def main():
    prof = (json.load(open(os.path.join(ROOT, "channels", "okinu", "profile.json"), encoding="utf-8")).get("build") or {})
    ap = argparse.ArgumentParser()
    ap.add_argument("work")
    ap.add_argument("--out", default="long.mp4")
    ap.add_argument("--clips", default=prof.get("clips", "images/_v3"))
    ap.add_argument("--tempo", type=float, default=prof.get("tempo", 1.25))
    ap.add_argument("--gap", type=float, default=prof.get("gap", 0.25))
    ap.add_argument("--bgm-volume", type=float, default=prof.get("bgm_volume", 0.03))
    ap.add_argument("--lufs", type=float, default=prof.get("lufs", -14))
    ap.add_argument("--height", type=int, default=prof.get("height", 1440))
    ap.add_argument("--font-size", type=int, default=prof.get("font_size", 72))
    ap.add_argument("--maxlen", type=int, default=prof.get("maxlen", 22))
    ap.add_argument("--par", type=int, default=prof.get("par", 3))
    ap.add_argument("--build", default="_build")
    ap.add_argument("--only-cards", action="store_true", help="カードを描くところまで（見た目の確認用）")
    a = ap.parse_args()
    for cmd in ("ffmpeg", "ffprobe"):
        if not shutil.which(cmd):
            raise SystemExit(f"【止まりました】{cmd} が見つかりません")
    work = os.path.abspath(a.work.rstrip("/\\"))
    b = os.path.join(work, a.build)
    os.makedirs(b, exist_ok=True)
    out = os.path.abspath(os.path.join(work, a.out))
    sc = json.load(open(os.path.join(work, "script.json"), encoding="utf-8"))
    cuts = [c for c in sc["cuts"] if c.get("narration")]
    nov = [c["id"] for c in cuts if not os.path.exists(voice_path(work, c["id"]))]
    if nov:
        raise SystemExit(f"【止まりました】声（voice/<id>.wav）が無いカット：{nov[:12]}")
    bgm = find_bgm(work, sc, prof)
    stamp_p = os.path.join(b, "stamps.json")
    stamps = json.load(open(stamp_p, encoding="utf-8")) if os.path.exists(stamp_p) else {}

    # ① 声
    durs, vcs = {}, []
    for c in cuts:
        v = os.path.join(b, c["id"] + "_v.wav")
        vkey = f"{a.tempo}|{a.gap}|{mt(voice_path(work, c['id']))}"
        if stamps.get(c["id"] + ":v") != vkey or not os.path.exists(v):
            prep_voice(voice_path(work, c["id"]), v, a.tempo, a.gap)
            stamps[c["id"] + ":v"] = vkey
        durs[c["id"]] = dur(v)
        vcs.append(v)
    json.dump(stamps, open(stamp_p, "w", encoding="utf-8"), ensure_ascii=False)
    print(f"声：{len(cuts)}カット・{sum(durs.values()) / 60:.1f}分（速さ {a.tempo}・間 {a.gap}）", flush=True)

    # ② カード
    make_cards(work, b, cuts, durs, sc.get("card_theme", "kinun"), sc.get("card_data", {}), a.clips, max(1, a.par), stamps, stamp_p)
    if a.only_cards:
        return

    # ③ 絵を声の長さに合わせて切る ＋ ④ 字幕
    t, chaps, clips, events = 0.0, [], [], []
    n_anchor = n_split = n_exact = 0
    for c in cuts:
        cid, d = c["id"], durs[c["id"]]
        n = c.get("chapter") or c.get("yt_chapter")
        if n:
            chaps.append((t, n))
        src = os.path.join(work, a.clips, cid + ".mp4")
        clip = os.path.join(b, cid + ".mp4")
        key = f"{mt(src)}|{d:.3f}"
        if stamps.get(cid) != key or not os.path.exists(clip):
            # カードは声より少し長く作ってあるので切る。足りない時は最後のコマで延ばす
            run("ffmpeg", "-v", "error", "-y", "-i", src, "-vf", f"scale={W}:{H},fps={FPS},tpad=stop_mode=clone:stop_duration=10",
                "-t", f"{d:.3f}", "-an", "-pix_fmt", "yuv420p", "-c:v", "libx264", "-crf", "14", "-preset", "veryfast" if CLOUD else "fast", clip)
            stamps[cid] = key
            json.dump(stamps, open(stamp_p, "w", encoding="utf-8"), ensure_ascii=False)
        clips.append(clip)
        ps = chunks(c["narration"], a.maxlen)
        starts, na, ns, exact = sub_starts(c["narration"], ps, d, onsets(os.path.join(b, cid + "_v.wav")))
        n_anchor += na; n_split += ns; n_exact += exact
        ends = starts[1:] + [d - a.gap * 0.5]
        style = "L" if c.get("speaker") == "listener" else "N"
        for p, st, en in zip(ps, starts, ends):
            events.append(f"Dialogue: 0,{ass_time(t + st)},{ass_time(t + en)},{style},,0,0,0,,{p.replace(chr(10), chr(92) + 'N')}")
        t += d
    print(f"字幕：カットの中の切り替え {n_split} か所のうち {n_anchor} か所を声の「間」に合わせた（一致したカット {n_exact}/{len(cuts)}）", flush=True)

    font, fname = next(((p, n) for p, n in SUB_FONTS if os.path.exists(p)), (None, None))
    if not font:
        raise SystemExit("【止まりました】字幕の字（NotoSansJP-Bold.ttf か NotoSansCJK-Bold.ttc）が見つかりません（Linux は fonts-noto-cjk を入れる）")
    fd = os.path.join(b, "fonts")
    shutil.rmtree(fd, ignore_errors=True)
    os.makedirs(fd)
    shutil.copyfile(font, os.path.join(fd, os.path.basename(font)))
    fs, mv = a.font_size, 110  # 下 8%（86px）より上に帯を置く（手順書 §6）
    open(os.path.join(b, "subs.ass"), "w", encoding="utf-8").write(f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: N,{fname},{fs},&H00{INK},&H00{INK},&H10{WASHI},&H00000000,1,0,0,0,100,100,2,0,3,16,0,2,120,120,{mv},1
Style: L,{fname},{fs},&H00{WASHI},&H00{WASHI},&H10{INK},&H00000000,1,0,0,0,100,100,2,0,3,16,0,2,120,120,{mv},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
""" + "\n".join(events) + "\n")
    open(os.path.join(b, "clips.txt"), "w", encoding="utf-8").write("".join(f"file '{os.path.basename(p)}'\n" for p in clips))
    run("ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", os.path.join(b, "clips.txt"), "-c", "copy", os.path.join(b, "video.mp4"))
    open(os.path.join(b, "voice.txt"), "w", encoding="utf-8").write("".join(f"file '{os.path.basename(p)}'\n" for p in vcs))
    run("ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", os.path.join(b, "voice.txt"), os.path.join(b, "voice.wav"))

    # ⑤ 音：声＋BGM を混ぜてから、全体を −14 LUFS にそろえる（2回測る方式。最後にもう一度測って、ずれたら音量だけ足す）
    mix = (f"[1:a]volume={a.bgm_volume},afade=t=in:d=1.5,afade=t=out:st={max(0, t - 2.5):.2f}:d=2.5[m];"
           "[0:a][m]amix=inputs=2:duration=first:normalize=0[a]")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", "voice.wav", "-stream_loop", "-1", "-i", bgm, "-filter_complex", mix,
                    "-map", "[a]", "-t", f"{t:.3f}", "-ar", "48000", "mix.wav"], check=True, cwd=b)
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", "mix.wav", "-af", f"loudnorm=I={a.lufs}:TP=-1.5:LRA=11:print_format=json",
                        "-f", "null", "-"], capture_output=True, text=True, cwd=b)
    js = r.stderr[r.stderr.rfind("{"):]
    m = json.loads(js[: js.find("}") + 1])
    ln = (f"loudnorm=I={a.lufs}:TP=-1.5:LRA=11:measured_I={m['input_i']}:measured_TP={m['input_tp']}:"
          f"measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", "mix.wav", "-af", f"{ln},aresample=48000", "-ar", "48000", "mix_n.wav"], check=True, cwd=b)
    li = loud("mix_n.wav", b)
    # 声の山が大きい時、linear の loudnorm が届かないことがある。音量を足して頭を抑える。
    # 頭を抑えると上がり方が足した量の 3〜4 割に減るので、実際の上がり方を見て足す量を直し、最大 4 回くり返す
    # （001 の試験：足す量そのままでは −15.5 止まり。4dB 足して −14.2）
    if li is not None and abs(li - a.lufs) > 0.7:
        li0, g, best = li, a.lufs - li, None
        for _ in range(4):
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", "mix_n.wav", "-af",
                            f"volume={g:.2f}dB,alimiter=limit=0.84:level=false:attack=5:release=50",
                            "-ar", "48000", "mix_g.wav"], check=True, cwd=b)
            lg = loud("mix_g.wav", b)
            if lg is None:
                break
            if best is None or abs(lg - a.lufs) < abs(best - a.lufs):
                best = lg
                os.replace(os.path.join(b, "mix_g.wav"), os.path.join(b, "mix_best.wav"))
            if abs(lg - a.lufs) <= 0.5:
                break
            if lg - li0 > 0.05:
                g = min(12.0, g * (a.lufs - li0) / (lg - li0))
            else:
                g = min(12.0, g * 2)
        if best is not None and abs(best - a.lufs) < abs(li - a.lufs):
            os.replace(os.path.join(b, "mix_best.wav"), os.path.join(b, "mix_n.wav"))
            li = best
    print(f"音：{m['input_i']} LUFS → {li} LUFS（目標 {a.lufs}）", flush=True)

    # ⑥ 書き出し（subtitles には相対パスで渡す。Windows の「C:」で壊れるため）
    up = "" if a.height == H else f"scale={W * a.height // H}:{a.height}:flags=lanczos,"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", "video.mp4", "-i", "mix_n.wav", "-filter_complex",
                    f"[0:v]{up}subtitles=subs.ass:fontsdir=fonts[v]", "-map", "[v]", "-map", "1:a",
                    "-t", f"{t:.3f}", "-c:v", "libx264", "-preset", "medium" if CLOUD else "slow", "-crf", "17",
                    "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", out], check=True, cwd=b)

    lines = ["0:00 はじめに"] if not chaps or chaps[0][0] > 0 else []
    lines += [f"{int(st // 60)}:{int(st % 60):02d} {name}" for st, name in chaps]
    open(os.path.join(work, "chapters.txt"), "w", encoding="utf-8").write("\n".join(lines) + "\n")
    chars = sum(len(re.sub(r"[\s、。！？「」]", "", c["narration"])) for c in cuts)
    fl = loud(out, b)
    print(f"できました：{out}（{int(t // 60)}分{int(t % 60)}秒・語りの速さ {chars / t * 60:.0f}字/分・{fl} LUFS）")
    print("\n".join(lines))


if __name__ == "__main__":
    main()

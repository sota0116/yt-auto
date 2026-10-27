# ⑧組み立て（心理学ch・2026-10-27 新設）：001 v3 と同じ作り（手元の long_full_v3.py＋long_extras.py）を、クラウドでも動く形にしたもの
#   python -X utf8 pipeline\build_long_psy.py <作業フォルダ> [--out long.mp4]
# ・設定は channels\psy\profile.json の build（声の速さ 1.28・間 0.25・−14 LUFS・1440p・字幕 76px／22字・BGM 0.035・章の見出し・章の鐘・主役の絵）
# ・001 からの変更：
#   ・scipy を使わない（クラウドの requirements に無い。wav の読み書きは wave＋numpy）
#   ・研究カードは extras.json ではなく、カットの "card"（{"head", "text"} か {"head", "rows"}、と "source"）から作る
#   ・吹き出し・手書きの文字（bubbles・notes）は使わない（絵ごとに座標が要るため。自動の回では作らない）
#   ・フォントは手元（Windows）とクラウド（Linux）の両方で見つかる物を順に探す。カードは BIZ UDゴシック、無ければ Noto Sans CJK
#   ・静止画を動かす時の拡大を2倍から1.5倍に、つなぎの動画を veryfast に（クラウドで時間の枠に収めるため。仕事chと同じ）。
#     仕上げは手元は slow、クラウドは medium（crf 17 は同じ）
#   ・THUMB（サムネの背景のカット）は語りが無いので動画に入れない
# ・字幕は声の「間」に合わせて切り替える（long_full_v3.py と同じ）。目次は chapters.txt に書く
import argparse, json, os, re, subprocess, sys, time, wave
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "vendor", "youtube-video-maker", "scripts"))
from common import load_config, need, dur, resolve_image, run, voice_path, chunks, ass_time, font_file, font_name, prep_voice  # noqa: E402
from build_long import chapter_png, label_png, W, H, FPS  # noqa: E402

PUNCT = "、。！？"
ZOOM = 1.5
CLOUD = os.environ.get("GITHUB_ACTIONS") == "true"
GOTHIC_BOLD = ["C:/Windows/Fonts/meiryob.ttc", "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"]  # 001 の札・大きな言葉は Meiryo Bold だった
HEAVY = ["C:/Windows/Fonts/meiryob.ttc", "/usr/share/fonts/opentype/noto/NotoSansCJK-Black.ttc"]
CARD_FONT = ["C:/Windows/Fonts/BIZ-UDGothicB.ttc", "BIZ UDGothic:style=Bold", "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"]
SUB_FONT = ["Meiryo", "Noto Sans CJK JP"]
INK, GREEN, RED, GRAY = (74, 52, 38), (110, 143, 62), (194, 87, 74), (122, 106, 90)
TX0, TX1 = 690, 1700  # カードの文字を置く範囲（ゆっくり寄る・横に流れる動きで端が切れないよう内側に）


def wav_read(p):
    with wave.open(p) as w:
        sr, ch = w.getframerate(), w.getnchannels()
        x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32)
    return sr, (x.reshape(-1, ch).mean(1) if ch > 1 else x)


def wav_write(p, sr, x):
    with wave.open(p, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype(np.int16).tobytes())


def onsets(wav, min_pause=0.2):
    """声の「間」が終わって声が戻る時刻の一覧"""
    sr, x = wav_read(wav)
    hop = int(sr * 0.01); n = len(x) // hop
    r = np.sqrt((x[: n * hop].reshape(n, hop) ** 2).mean(1)) + 1e-9
    quiet = 20 * np.log10(r / r.max()) < -35
    out, k = [], 0
    for i, q in enumerate(quiet):
        if q:
            k += 1
            continue
        if k * 0.01 >= min_pause and i - k > 0:
            out.append(i * 0.01)
        k = 0
    return out


def sub_starts(narr, ps, d, ons):
    """各字幕の出る時刻。句読点で切れる所は「間」に合わせ、てにをはで切れる所は前後の合わせた時刻の間を文字数で分ける"""
    total = len(re.sub(r"\s", "", narr))
    npunct = sum(narr[:-1].count(p) for p in PUNCT)
    exact = len(ons) == npunct
    starts, pos, k = [0.0], 0, 0
    anchored = [True]
    for p in ps[:-1]:
        flat = p.replace("\n", "")
        pos += len(re.sub(r"\s", "", flat))
        k += sum(flat.count(q) for q in PUNCT)
        guess = d * pos / max(1, total)
        if flat and flat[-1] in PUNCT and ons:
            if exact:
                st = ons[k - 1]
            else:
                st = min(ons, key=lambda o: abs(o - guess))
                if abs(st - guess) > 1.5:
                    st = None
        else:
            st = None
        starts.append(st if st is None else max(0.0, st - 0.08)); anchored.append(st is not None)
    lens = [len(re.sub(r"\s", "", p)) for p in ps]
    cum = np.cumsum([0] + lens)
    for i in range(1, len(ps)):
        if starts[i] is None:
            j = max(a for a in range(i) if starts[a] is not None)
            nxt = [a for a in range(i + 1, len(ps)) if starts[a] is not None]
            e, ce = (starts[nxt[0]], cum[nxt[0]]) if nxt else (d, cum[-1])
            starts[i] = starts[j] + (e - starts[j]) * (cum[i] - cum[j]) / max(1, ce - cum[j])
    for i in range(1, len(starts)):
        starts[i] = max(starts[i], starts[i - 1] + 0.3)
    return starts, sum(anchored[1:]), len(ps) - 1, exact


def F(size):
    return ImageFont.truetype(font_file(CARD_FONT), size)


def fit(d, lines, size, width, low=40):
    while size > low and max(d.textlength(l, font=F(size)) for l in lines) > width:
        size -= 4
    return F(size)


def paper_with_hero(hero):
    """主役の見本（紙の色の背景）から、主役を左へ寄せた紙を作る。背景と同じ紙なので継ぎ目が出ない（座標は hero.png＝主役見本_v1.png の物）"""
    im = Image.open(hero).convert("RGB").resize((W, H))
    patch = im.crop((1350, 0, 1850, H))
    m = Image.new("L", patch.size, 0); ImageDraw.Draw(m).rectangle((40, 0, 460, H), fill=255)
    base = im.copy(); base.paste(patch, (690, 0), m.filter(ImageFilter.GaussianBlur(30)))
    h = im.crop((700, 130, 1170, 900))
    h = h.resize((int(h.width * 0.82), int(h.height * 0.82)))
    hm = Image.new("L", h.size, 0); ImageDraw.Draw(hm).rounded_rectangle((25, 25, h.width - 25, h.height - 25), 60, fill=255)
    base.paste(h, (170, 230), hm.filter(ImageFilter.GaussianBlur(20)))
    return base


def card(spec, out, hero):
    im = paper_with_hero(hero); d = ImageDraw.Draw(im)
    y = 220
    head = spec.get("head", "研究でわかったこと")
    d.text((TX0, y), head, font=fit(d, [head], 54, TX1 - TX0), fill=GREEN)
    d.line((TX0, y + 82, TX1, y + 82), fill=GREEN, width=3)
    y += 130
    if spec.get("rows"):
        ft = F(50)
        tagw = max(d.textlength(t, font=ft) for t, _ in spec["rows"]) + 44
        for tag, txt in spec["rows"]:
            d.rounded_rectangle((TX0, y, TX0 + tagw, y + 84), 14, fill=GREEN)
            d.text((TX0 + 22, y + 15), tag, font=ft, fill=(255, 255, 255))
            d.text((TX0 + tagw + 36, y + 6), txt, font=fit(d, [txt], 66, TX1 - TX0 - tagw - 36), fill=INK)
            y += 125
    else:
        lines = spec["text"].split("\n")
        f = fit(d, lines, 86, TX1 - TX0)
        d.multiline_text((TX0, y), spec["text"], font=f, fill=INK, spacing=int(f.size * 0.4))
    if spec.get("source"):
        d.ellipse((TX0, 812, TX0 + 20, 832), fill=RED)
        d.text((TX0 + 36, 800), spec["source"], font=fit(d, [spec["source"]], 38, TX1 - TX0 - 36, low=20), fill=GRAY)
    im.save(out)


def chapter_title(title, num, out):
    im = Image.new("RGBA", (W, H), (30, 22, 15, 110)); d = ImageDraw.Draw(im)
    d.rectangle((0, 380, W, 720), fill=(30, 22, 15, 150))
    d.text((W / 2, 450), f"第{num}章", font=F(62), fill=(255, 210, 63), anchor="mm")
    d.text((W / 2, 590), title, font=fit(d, [title], 116, W - 240), fill=(255, 255, 255), anchor="mm", stroke_width=5, stroke_fill=(30, 22, 15))
    im.save(out)


def chime(sr=48000):
    t = np.arange(int(2.6 * sr)) / sr
    s = sum(a * np.sin(2 * np.pi * 1046.5 * r * t) * np.exp(-t / dk) for r, a, dk in ((1, 1.0, 0.9), (2.76, 0.35, 0.35), (5.4, 0.12, 0.15)))
    s[: int(0.004 * sr)] *= np.linspace(0, 1, int(0.004 * sr))
    return s / np.max(np.abs(s))


def render(src_img, n, d, overlays, out):
    if src_img.endswith(".mp4"):  # 動く絵（Kling の5秒）。短い時は最後のコマのまま伸ばす
        src = ["-i", src_img]
        vf = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps={FPS},tpad=stop_mode=clone:stop_duration=30"
    else:  # 静止画は、ゆっくり寄る／ゆっくり横に流す を交互に
        nfr = int(d * FPS) + 2
        sw, sh = int(W * ZOOM), int(H * ZOOM)
        src = ["-loop", "1", "-i", src_img]
        move = (f"z='1+0.08*on/{nfr}':x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2'" if n % 2 == 0
                else f"z='1.08':x='(iw-iw/zoom)*on/{nfr}':y='ih/2-ih/zoom/2'")
        vf = f"scale={sw}:{sh}:force_original_aspect_ratio=increase,crop={sw}:{sh},zoompan={move}:d={nfr}:s={W}x{H}:fps={FPS}"
    enc = ["-t", f"{d:.3f}", "-an", "-pix_fmt", "yuv420p", "-c:v", "libx264", "-crf", "15", "-preset", "veryfast", out]
    if not overlays:
        return run("ffmpeg", "-v", "error", "-y", *src, "-vf", vf, *enc)
    ins = sum([["-loop", "1", "-i", p] for p, _, _, _ in overlays], [])
    fc = f"[0:v]{vf}[v0];"
    for k, (_, st, en, fout) in enumerate(overlays):
        fo = f",fade=t=out:st={en - 0.3:.2f}:d=0.3:alpha=1" if fout else ""
        fc += f"[{k + 1}:v]fade=t=in:st={st}:d=0.3:alpha=1{fo}[o{k}];[v{k}][o{k}]overlay=0:0:enable='between(t,{st},{en})':shortest=1[v{k + 1}];"
    run("ffmpeg", "-v", "error", "-y", *src, *ins, "-filter_complex", fc.rstrip(";"), "-map", f"[v{len(overlays)}]", *enc)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("work"); ap.add_argument("--out", default="long.mp4")
    a = ap.parse_args()
    need("ffmpeg", "ffmpeg を入れてください")
    work = os.path.abspath(a.work.rstrip("/\\"))
    prof = json.load(open(os.path.normpath(os.path.join(work, "..", "..", "profile.json")), encoding="utf-8"))
    bc = prof["build"]
    tempo, gap, lufs, height = bc["tempo"], bc["gap"], bc["lufs"], bc["height"]
    hero = os.path.join(ROOT, bc["hero"])
    b = os.path.join(work, "_build"); os.makedirs(b, exist_ok=True)
    out = os.path.abspath(os.path.join(work, a.out))
    cfg = load_config(work)
    cfg.update({"font_gothic": GOTHIC_BOLD, "font_heavy": HEAVY})
    sc = json.load(open(os.path.join(work, "script.json"), encoding="utf-8"))
    cuts = [c for c in sc["cuts"] if c.get("narration")]
    missing = [c["id"] for c in cuts if not os.path.exists(voice_path(work, c["id"]))]
    if missing:
        raise SystemExit(f"【止まりました】声がないカット：{missing[:10]}（{len(missing)}カット）")
    noimg = [c["id"] for c in cuts if not c.get("card") and not resolve_image(work, sc["cuts"], c)]
    if noimg:
        raise SystemExit(f"【止まりました】絵がないカット：{noimg[:10]}（{len(noimg)}カット）")
    stamp_p = os.path.join(b, "stamps.json")
    stamps = json.load(open(stamp_p, encoding="utf-8")) if os.path.exists(stamp_p) else {}

    t, chap_t, chaps, nchap, clips, vcs, events = 0.0, [], [], 0, [], [], []
    n_anchor = n_split = n_exact = n_motion = 0
    for n, c in enumerate(cuts):
        cid = c["id"]
        v = os.path.join(b, cid + "_v.wav")
        vkey = f"{tempo}|{gap}|{os.path.getmtime(voice_path(work, cid))}"
        if stamps.get(cid + ":v") != vkey or not os.path.exists(v):
            prep_voice(voice_path(work, cid), v, tempo, gap); stamps[cid + ":v"] = vkey
        vcs.append(v); d = dur(v)
        is_chap = bool(c.get("chapter"))
        if is_chap:
            nchap += 1; chap_t.append(t); chaps.append((t, c["chapter"]))
        src = resolve_image(work, sc["cuts"], c) or hero
        n_motion += src.endswith(".mp4")
        spec = {"src": src, "mtime": os.path.getmtime(src), "d": round(d, 3), "n": n % 2,
                "x": json.dumps([c.get("card"), c.get("label"), c.get("strong"), c.get("chapter"), bc.get("chapter_title")], ensure_ascii=False)}
        clip = os.path.join(b, cid + ".mp4")
        if stamps.get(cid) != spec or not os.path.exists(clip):
            if c.get("card"):
                src = os.path.join(b, cid + "_card.png"); card(c["card"], src, hero)
            overlays = []
            if is_chap:
                p2 = os.path.join(b, cid + "_chap.png"); chapter_png(c["chapter"], nchap, p2, cfg)
                if bc.get("chapter_title"):
                    p = os.path.join(b, cid + "_title.png"); chapter_title(c["chapter"], nchap, p)
                    overlays += [(p, 0.1, min(d, 2.9), True), (p2, min(d, 2.9), min(d, 7.4), False)]
                else:
                    overlays.append((p2, 0.0, min(d, 4.5), False))
            if c.get("label") and not c.get("card"):  # カードには要点を書いたので、大きな言葉は重ねない
                p = os.path.join(b, cid + "_label.png"); label_png(c["label"], p, cfg, c.get("strong", False), 90)
                overlays.append((p, 3.0 if is_chap and bc.get("chapter_title") else 0.3, d, False))
            for k in range(3):  # ffmpeg がたまにメモリ不足で落ちる（やり直せば通る。2026-10-26）
                try:
                    render(src, n, d, overlays, clip); break
                except subprocess.CalledProcessError:
                    if k == 2:
                        raise
                    print(cid, "失敗したのでやり直す", flush=True); time.sleep(20)
            stamps[cid] = spec
            json.dump(stamps, open(stamp_p, "w", encoding="utf-8"), ensure_ascii=False)
            print(cid, f"{d:.1f}秒", os.path.basename(src), flush=True)
        clips.append(clip)
        ps = chunks(c["narration"], bc["maxlen"])
        starts, na, ns, exact = sub_starts(c["narration"], ps, d, onsets(v))
        n_anchor += na; n_split += ns; n_exact += exact
        ends = starts[1:] + [d - gap * 0.5]
        for p, st, en in zip(ps, starts, ends):
            events.append(f"Dialogue: 0,{ass_time(t + st)},{ass_time(t + en)},Cap,,0,0,0,,{p.replace(chr(10), chr(92) + 'N')}")
        t += d
    json.dump(stamps, open(stamp_p, "w", encoding="utf-8"), ensure_ascii=False)
    print(f"字幕：カットの中の切り替え {n_split} か所のうち {n_anchor} か所を声の「間」に合わせた"
          f"（句読点と「間」の数が一致したカット {n_exact}/{len(cuts)}）／動く絵 {n_motion} カット", flush=True)

    open(os.path.join(b, "subs.ass"), "w", encoding="utf-8").write(f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,{font_name(SUB_FONT)},{bc['font_size']},&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,1,0,0,0,100,100,0,0,1,5,2,2,80,80,50,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
""" + "\n".join(events) + "\n")
    open(os.path.join(b, "clips.txt"), "w").write("".join(f"file '{p}'\n" for p in clips))
    run("ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", os.path.join(b, "clips.txt"), "-c", "copy", os.path.join(b, "video.mp4"))
    open(os.path.join(b, "voice.txt"), "w").write("".join(f"file '{p}'\n" for p in vcs))
    run("ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", os.path.join(b, "voice.txt"), os.path.join(b, "voice.wav"))

    # 音：声＋章の鐘＋BGM を混ぜてから、全体を −14 LUFS にそろえる（2回測る方式）
    sr = 48000; fx = np.zeros(int((t + 3) * sr))
    if bc.get("chime"):
        ch = chime(sr) * 0.22
        for st in chap_t:
            i = int((st + 0.1) * sr); fx[i:i + len(ch)] += ch[: len(fx) - i]
    wav_write(os.path.join(b, "fx.wav"), sr, fx)
    ins = ["-i", "voice.wav", "-i", "fx.wav"]
    mix = "[0:a][1:a]amix=inputs=2:duration=first:normalize=0[a]"
    if bc.get("bgm"):
        ins += ["-stream_loop", "-1", "-i", os.path.join(ROOT, bc["bgm"])]
        mix = (f"[2:a]volume={bc['bgm_volume']},afade=t=in:d=1.5,afade=t=out:st={max(0, t - 3):.2f}:d=3[m];"
               "[0:a][1:a][m]amix=inputs=3:duration=first:normalize=0[a]")
    subprocess.run(["ffmpeg", "-v", "error", "-y", *ins, "-filter_complex", mix, "-map", "[a]", "-t", f"{t:.3f}",
                    "-ar", "48000", "mix.wav"], check=True, cwd=b)
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", "mix.wav", "-af", f"loudnorm=I={lufs}:TP=-1.5:LRA=11:print_format=json",
                        "-f", "null", "-"], capture_output=True, text=True, cwd=b)
    js = r.stderr[r.stderr.rfind("{"):]
    m = json.loads(js[: js.find("}") + 1])
    ln = (f"loudnorm=I={lufs}:TP=-1.5:LRA=11:measured_I={m['input_i']}:measured_TP={m['input_tp']}:"
          f"measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true")
    print(f"仕上げ（字幕・音）{t:.1f}秒／音の大きさ {m['input_i']} LUFS → {lufs} LUFS", flush=True)
    # Windows では subtitles に C:/... を渡すと「C:」で壊れるので、作業場所に移って相対パスで渡す
    up = "" if height == H else f"scale={W * height // H}:{height}:flags=lanczos,"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", "video.mp4", "-i", "mix.wav", "-filter_complex",
                    f"[0:v]{up}subtitles=subs.ass[v];[1:a]{ln},aresample=48000[a]", "-map", "[v]", "-map", "[a]",
                    "-t", f"{t:.3f}", "-c:v", "libx264", "-preset", "medium" if CLOUD else "slow", "-crf", "17", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", out], check=True, cwd=b)

    lines = ["0:00 はじめに"] if chaps and chaps[0][0] > 0 else []
    lines += [f"{int(st // 60)}:{int(st % 60):02d} {name}" for st, name in chaps]
    open(os.path.join(work, "chapters.txt"), "w", encoding="utf-8").write("\n".join(lines) + "\n")
    chars = sum(len(re.sub(r"[\s、。！？「」]", "", c["narration"])) for c in cuts)
    print(f"できました：{out}（{int(t // 60)}分{int(t % 60)}秒・語りの速さ {chars / t * 60:.0f}字/分）")
    print("\n".join(lines))


if __name__ == "__main__":
    main()

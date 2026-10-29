# ⑨ショート（心理学ch・2026-10-27 新設）：その回の長尺の絵（動く絵）を借りて、縦のショート（1080x1920・60秒未満）を作る
#   python -X utf8 pipeline\make_short_psy.py <作業フォルダ> [--check] [--name short_2]
# ・台本は script.json の "short"（台本の書き手 write_script_psy.py が手順書 §10 の決まりで書く）
# ・2026-10-29 から、特徴の章ごとのショートを "extra_shorts"（同じ形の並び）に足せる。作業フォルダ\short_2\・short_3\ … に作る。
#   --name が無い時は全部作る。"short"（1本目）が作れなければ止める（今までと同じ）。2本目からは作れなかった物だけ飛ばす
#   形はどれも {"title", "lines": サムネと同じ形の上の帯の文字（1〜2行）, "desc", "cuts": [{"id": "S01", "narration", "from": "本編のカットの id", "study"?}]}
# ・声は長尺と同じ VOICEVOX（make_voice_vv.py を 作業フォルダ\short\ に向けて回す）。速さ・間・BGM・音の大きさも長尺と同じ（profile.json の build）
# ・画面：上に濃い帯と白い大きな字（大事な言葉1つは黄）、真ん中に本編の絵を正方形で（静止画はゆっくり寄る。動く絵はそのまま）、下に大きな字幕
# ・--check：作る前の点検だけ（字数・カット数・借りる絵・決まった締めの文・禁止表現・帯の字）。台本の書き手も書いたあとに回す
# ・出力：作業フォルダ\short\short.mp4。59.5秒を超えたら不合格（ショートは60秒まで）
import argparse, json, os, re, subprocess, sys
from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "vendor", "youtube-video-maker", "scripts"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import need, dur, resolve_image, run, chunks, ass_time, font_name, prep_voice  # noqa: E402
from build_long_psy import onsets, sub_starts, HEAVY  # noqa: E402

W, H, FPS = 1080, 1920, 30
BAND, IMG_Y = 400, 400  # 上の帯の高さ・正方形の絵を置く高さ（絵は 400〜1480）
PAPER, DARK, YELLOW = (246, 238, 220), (48, 36, 26), "#FFE234"
CHARS = (180, 290)  # 語りの字数（句読点を除く）。速さ 1.28 で約35〜57秒
NCUT = (5, 11)
CLOSE = "続きは、本編の動画でお話ししています。"
SUB_MAX = 12  # 字幕の1行の字数
EXTRA_MAX = 3  # 2本目からのショートは3本まで（1回で4本。予約の枠は1日3つ・長尺は週5本なので週20本。shorts_watch.py の TIMES）


def plain(t):
    return re.sub(r"[\s、。！？「」]", "", t)


def shorts_of(s):
    """[(フォルダの名前, ショートの台本)]。1本目は short、2本目からは short_2 …（upload_short_psy.py も使う）"""
    if not s.get("short"):
        return []
    extra = (s.get("extra_shorts") or [])[:EXTRA_MAX]
    return [("short", s["short"])] + [(f"short_{i + 2}", x) for i, x in enumerate(extra)]


def check(work, name="short"):
    s = json.load(open(os.path.join(work, "script.json"), encoding="utf-8"))
    sh = dict(shorts_of(s)).get(name) or {}
    ng = []
    cuts = sh.get("cuts") or []
    long_ids = {c["id"]: c for c in s.get("cuts", [])}
    n = sum(len(plain(c.get("narration", ""))) for c in cuts)
    if not CHARS[0] <= n <= CHARS[1]:
        ng.append(f"語りの字数 {n}字（{CHARS[0]}〜{CHARS[1]}字）")
    if not NCUT[0] <= len(cuts) <= NCUT[1]:
        ng.append(f"カット数 {len(cuts)}（{NCUT[0]}〜{NCUT[1]}）")
    for i, c in enumerate(cuts):
        if c.get("id") != f"S{i + 1:02d}":
            ng.append(f"{i + 1}番目のカットの id が S{i + 1:02d} ではない：{c.get('id')}")
        if len(plain(c.get("narration", ""))) > 40:
            ng.append(f"{c.get('id')}：1カット40字まで（{len(plain(c.get('narration', '')))}字）")
        src = long_ids.get(c.get("from"))
        if not src or not src.get("narration") or src.get("card") or src["id"] == "THUMB":
            ng.append(f"{c.get('id')}：from「{c.get('from')}」は、本編の語りのある絵のカット（card と THUMB 以外）にする")
        elif os.path.isdir(os.path.join(work, "images")) and not resolve_image(work, s["cuts"], src):
            ng.append(f"{c.get('id')}：from「{c.get('from')}」の絵のファイルが images にない")
        for mark in ("──", "…", "※", "★", "→"):
            if mark in c.get("narration", ""):
                ng.append(f"{c.get('id')}：記号「{mark}」は使わない")
    if cuts and cuts[-1].get("narration") != CLOSE:
        ng.append(f"最後のカットは決まった文「{CLOSE}」にする")
    # 2026-10-28 本人の指摘（スキル references/16）：答えを先送りするだけの文（6）・動く絵（2）・見どころ（4）
    from check_psy_script import tease
    for c in cuts[:-1]:  # 最後の決まった文（本編への案内）は除く
        w = tease(c.get("narration", ""))
        if w:
            ng.append(f"{c.get('id')}：答えを先送りするだけの文「{w}」（問いで引き、答えの手前で止める。§10）")
    if cuts and not (long_ids.get(cuts[0].get("from")) or {}).get("motion"):
        ng.append("S01 の from は、本編で motion（動く絵）を付けたカットにする（ショートの1カット目は動く絵。§10）")
    pk = [c for c in cuts[1:-1] if c.get("peak")]
    if not pk:
        ng.append("見どころのカットが無い：いちばん面白い所（答えの一歩手前）のカットに \"peak\": true を書き、"
                  "from を本編で motion を付けたカットにする（§10）")
    for c in pk:
        if not (long_ids.get(c.get("from")) or {}).get("motion"):
            ng.append(f"{c.get('id')}：見どころ（peak）の from は、本編で motion（動く絵）を付けたカットにする（§10）")
    if cuts and not cuts[0].get("narration", "").rstrip().endswith(("？", "か。")):
        ng.append("S01 は見る人の毎日の場面の小さな謎を、問いの形（？で終わる）で言う")
    words = [w.strip() for w in open(os.path.join(ROOT, "channels", "psy", "禁止表現.txt"), encoding="utf-8") if w.strip() and not w.startswith("#")]
    texts = [c.get("narration", "") for c in cuts] + [sh.get("title", ""), sh.get("desc", "")]
    ng += [f"禁止表現「{w}」：{t[:30]}" for t in texts for w in words if w in t]
    lines = sh.get("lines") or []
    band = ["".join(t for t, _ in ln) for ln in lines]
    yellow = sum(1 for ln in lines for _, col in ln if col.upper() == YELLOW)
    if not 1 <= len(lines) <= 2 or any(len(b) > 12 for b in band) or yellow != 1:
        ng.append(f"上の帯の字は1〜2行・1行12字まで・黄の言葉が1つ（今：{band}・黄 {yellow}）")
    t = sh.get("title", "")
    if not 10 <= len(t) <= 60 or not t.startswith("【心理学】"):
        ng.append(f"ショートの題は「【心理学】」で始めて60字まで（今 {len(t)}字）")
    others = [x.get("title") for k, x in shorts_of(s) if k != name]
    if t and t in others:
        ng.append("ほかのショートと同じ題（1本ずつ別の題にする）")
    print(f"{name}：語り {n}字・{len(cuts)}カット・題 {len(t)}字・帯 {band}")
    for x in ng:
        print("  NG", x)
    print(f"NG {len(ng)}件")
    return not ng


def band_png(lines, out):
    im = Image.new("RGB", (W, H), PAPER)
    d = ImageDraw.Draw(im)
    d.rectangle((0, 0, W, BAND), fill=DARK)
    ys = [(150, 120)] if len(lines) == 1 else [(70, 120), (220, 120)]
    for (y, size), runs in zip(ys, lines):
        text = "".join(t for t, _ in runs)
        while size > 60:
            f = ImageFont.truetype(_font(), size)
            if d.textlength(text, font=f) <= W - 100:
                break
            size -= 6
        f = ImageFont.truetype(_font(), size)
        x = (W - d.textlength(text, font=f)) / 2
        for t, col in runs:
            d.text((x, y), t, font=f, fill=col, stroke_width=max(4, size // 16), stroke_fill=(20, 14, 8))
            x += d.textlength(t, font=f)
    d.text((W / 2, 1860), "しずくの心理学", font=ImageFont.truetype(_font(), 40), fill=(140, 120, 96), anchor="mm")
    im.save(out)


def _font():
    return next(p for p in HEAVY if os.path.exists(p))


def clip(bg, src, n, d, out):
    size = W
    if src.endswith(".mp4"):
        ins = ["-loop", "1", "-i", bg, "-i", src]
        img = f"[1:v]scale=-2:{size},crop={size}:{size},fps={FPS},tpad=stop_mode=clone:stop_duration=30[img]"
    else:
        nfr = int(d * FPS) + 2
        z = int(size * 1.5)
        move = (f"z='1+0.10*on/{nfr}':x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2'" if n % 2 == 0
                else f"z='1.10':x='(iw-iw/zoom)*on/{nfr}':y='ih/2-ih/zoom/2'")
        ins = ["-loop", "1", "-i", bg, "-loop", "1", "-i", src]
        img = f"[1:v]scale=-2:{z},crop={z}:{z},zoompan={move}:d={nfr}:s={size}x{size}:fps={FPS}[img]"
    fc = f"{img};[0:v]fps={FPS}[bg];[bg][img]overlay=0:{IMG_Y}:shortest=1[v]"
    run("ffmpeg", "-v", "error", "-y", *ins, "-filter_complex", fc, "-map", "[v]", "-t", f"{d:.3f}", "-an",
        "-pix_fmt", "yuv420p", "-c:v", "libx264", "-crf", "17", "-preset", "veryfast", out)


def build(work, name="short"):
    need("ffmpeg", "ffmpeg を入れてください")
    s = json.load(open(os.path.join(work, "script.json"), encoding="utf-8"))
    sh = dict(shorts_of(s))[name]
    prof = json.load(open(os.path.join(ROOT, "channels", "psy", "profile.json"), encoding="utf-8"))
    bc = prof["build"]
    sw = os.path.join(work, name); b = os.path.join(sw, "_build")
    os.makedirs(b, exist_ok=True)
    # 声：作業フォルダ\short\script.json に語りだけを置いて、長尺と同じ道具で作る
    json.dump({"cuts": [{k: c[k] for k in ("id", "narration", "tts_text") if k in c} for c in sh["cuts"]]},
              open(os.path.join(sw, "script.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    r = subprocess.run([sys.executable, "-X", "utf8", os.path.join(ROOT, "pipeline", "make_voice_vv.py"), "make", sw, "--ch", "psy"],
                       capture_output=True, text=True, encoding="utf-8")
    print(r.stdout[-400:], r.stderr[-400:])
    if r.returncode:
        sys.exit("【止まりました】ショートの声を作れませんでした")
    bg = os.path.join(b, "band.png"); band_png(sh["lines"], bg)
    long_cuts = {c["id"]: c for c in s["cuts"]}
    t, clips, vcs, events = 0.0, [], [], []
    for n, c in enumerate(sh["cuts"]):
        v = os.path.join(b, c["id"] + "_v.wav")
        prep_voice(os.path.join(sw, "voice", c["id"] + ".wav"), v, bc["tempo"], bc["gap"])
        d = dur(v); vcs.append(v)
        src = resolve_image(work, s["cuts"], long_cuts[c["from"]])
        out = os.path.join(b, c["id"] + ".mp4")
        clip(bg, src, n, d, out); clips.append(out)
        ps = chunks(c["narration"], SUB_MAX)
        starts = sub_starts(c["narration"], ps, d, onsets(v))[0]
        for p, st, en in zip(ps, starts, starts[1:] + [d - bc["gap"] * 0.5]):
            events.append(f"Dialogue: 0,{ass_time(t + st)},{ass_time(t + en)},Cap,,0,0,0,,{p.replace(chr(10), chr(92) + 'N')}")
        t += d
    if t > 59.5:
        sys.exit(f"【止まりました】ショートが {t:.1f}秒（60秒を超える）。short の語りを減らす")
    # 動く絵が本当に入ったか（Kling は無料の時だけなので、作れなかった絵は止まった絵になる。references/16 の2）
    srcs = [resolve_image(work, s["cuts"], long_cuts[c["from"]]) for c in sh["cuts"]]
    n_mv = sum(str(x).endswith(".mp4") for x in srcs)
    print(f"動く絵 {n_mv} カット（1カット目 {'動く' if str(srcs[0]).endswith('.mp4') else '止まった絵'}）")
    if n_mv == 0:
        sys.exit("【止まりました】ショートに動く絵が1つも無い（止まった絵だけの紙芝居は出さない）。本編の motion の絵ができてから作る")
    open(os.path.join(b, "subs.ass"), "w", encoding="utf-8").write(f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,{font_name(["Meiryo", "Noto Sans CJK JP"])},82,&H00263448,&H00263448,&H00FFFFFF,&H00000000,1,0,0,0,100,100,0,0,1,6,0,8,40,40,1515,1
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
""" + "\n".join(events) + "\n")
    open(os.path.join(b, "clips.txt"), "w").write("".join(f"file '{p}'\n" for p in clips))
    run("ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", os.path.join(b, "clips.txt"), "-c", "copy", os.path.join(b, "video.mp4"))
    open(os.path.join(b, "voice.txt"), "w").write("".join(f"file '{p}'\n" for p in vcs))
    run("ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", os.path.join(b, "voice.txt"), os.path.join(b, "voice.wav"))
    # 声＋BGM を混ぜて −14 LUFS に（短いので1回で測って合わせる）。Windows では subtitles に C:/... を渡すと壊れるので、作業場所に移って相対パスで渡す
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", "video.mp4", "-i", "voice.wav", "-stream_loop", "-1", "-i", os.path.join(ROOT, bc["bgm"]),
                    "-filter_complex", f"[0:v]subtitles=subs.ass[v];[2:a]volume={bc['bgm_volume']},afade=t=in:d=1,afade=t=out:st={max(0, t - 2):.2f}:d=2[m];"
                    f"[1:a][m]amix=inputs=2:duration=first:normalize=0,loudnorm=I={bc['lufs']}:TP=-1.5:LRA=11,aresample=48000[a]",
                    "-map", "[v]", "-map", "[a]", "-t", f"{t:.3f}", "-c:v", "libx264", "-preset", "medium", "-crf", "18",
                    "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", os.path.join(sw, "short.mp4")],
                   check=True, cwd=b)
    print(f"できました：{os.path.join(sw, 'short.mp4')}（{t:.1f}秒・{len(clips)}カット）")


def main():
    a = argparse.ArgumentParser()
    a.add_argument("work")
    a.add_argument("--check", action="store_true")
    a.add_argument("--name", default="", help="1本だけ作る時（short・short_2 …）")
    a = a.parse_args()
    work = os.path.abspath(a.work)
    s = json.load(open(os.path.join(work, "script.json"), encoding="utf-8"))
    names = [a.name] if a.name else [k for k, _ in shorts_of(s)] or ["short"]
    oks = {k: check(work, k) for k in names}
    if a.check or not oks[names[0]]:
        sys.exit(0 if all(oks.values()) else 1)
    for k in names:
        if not oks[k]:
            print(f"{k}：点検で NG があるので作りません")
            continue
        try:
            build(work, k)
        except (SystemExit, subprocess.CalledProcessError) as e:
            if k == names[0]:
                raise
            print(f"{k}：作れませんでした（{e}）。ほかのショートは続けます")


if __name__ == "__main__":
    main()

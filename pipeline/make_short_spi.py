# ⑨ショート（千年こよみ・2026-10-27 新設。心理学ch の make_short_psy.py をもとにした。元は残している）
#   python -X utf8 pipeline\make_short_spi.py <作業フォルダ> [--check] [--clips images/_v3]
# ・台本は 作業フォルダ\short.json（script.json は 台本_生成元 で作り直すと消えるので、別のファイルにした）
#   {"title", "lines": 上の帯の文字（1〜2行）, "desc", "cuts": [{"id": "S01", "narration", "from": "本編のカットの id", "emo"?, "tts_text"?, "pan"?}]}
# ・絵は本編のカードの動画（--clips。既定 images/_v3）を借りる。千年こよみの本編は全部が横長のカード（1920x1080）なので、
#   photo は真ん中を正方形に切る（"pan" 0〜1 で左右の位置）。図や表のカードは、中身のある所だけを切り出して幅いっぱいに置く
# ・声は本編と同じ make_voice_vv2.py（感情づけ・玄野武宏・yomi.json）。間 0.25秒・BGM（script.json の bgm）0.03・−14 LUFS
# ・画面：上に墨の帯と和紙の字（大事な言葉1つは金）、真ん中に本編の絵、下に大きな字幕、いちばん下にチャンネル名
# ・--check：作る前の点検（字数・カット数・借りる絵・決まった締めの文・メタの言葉・書かないこと・帯の字・題）
# ・出力：作業フォルダ\short\short.mp4。59.5秒を超えたら不合格
# ・本編へつなぐ（2026-10-28 本人の指示「本編はいついつのロング動画で、と誘導をかけよう」）：
#   本編を上げて公開の日（予約）が決まってから作る。本編の公開の日と長さは YouTube から読む（作業フォルダの uploaded.json の video_id）
#   最後のカットの語りは "{CLOSE}" と書く → 「続きは、10月27日、火曜日に出した、本編の長い動画でお話ししています。」にする
#   最後のカットの from は "END"：本編のサムネ（uploaded.json の thumb）と「10月27日（火）公開・約9分」の案内の画面にする
import argparse, json, os, re, subprocess, sys
from PIL import Image, ImageChops, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "vendor", "youtube-video-maker", "scripts"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import need, dur, run, chunks, ass_time, prep_voice  # noqa: E402
from build_long_psy import onsets, sub_starts  # noqa: E402

W, H, FPS = 1080, 1920, 30
BAND, IMG_Y = 400, 400  # 上の帯の高さ・絵を置く所（400〜1480）
WASHI, INK, GOLD = (241, 235, 221), (43, 38, 34), "#F2C14E"  # 和紙はカードの地の色に合わせた
CHARS = (170, 260)  # 語りの字数（句読点を除く）。本編の速さ（約303字/分）で約35〜55秒
NCUT = (5, 11)
CLOSE = "続きは、{m}月{d}日、{w}曜日に出した、本編の長い動画でお話ししています。"
WEEK = "月火水木金土日"
SUB_MAX = 12
TEMPO, GAP, BGM_VOL, LUFS = 1.0, 0.25, 0.03, -14
FONT = r"C:\Windows\Fonts\NotoSansJP-Bold.ttf"
# 手順書 §4 のメタの禁止と、書かないこと（決まった締めの文 CLOSE は除く）
META = ["この動画", "この回", "今回", "このチャンネル", "ここからは", "ここまで", "この後すぐ", "次の章", "見ていきます", "紹介します",
        "おさらい", "ありがとうございました", "今日", "今夜"]
NG_WORDS = ["必ず当たる", "必ず叶う", "万円入る", "治る", "体がよくなる", "病気にならない"]


def plain(t):
    return re.sub(r"[\s、。！？「」]", "", t)


def long_info(work):
    """本編の公開の日（予約の日）・長さ・サムネ。日が決まっていなければ止める"""
    from upload_job import api, API
    up = json.load(open(os.path.join(work, "uploaded.json"), encoding="utf-8"))
    it = json.load(api("spi", "GET", f"{API}/videos?part=status,snippet,contentDetails&id={up['video_id']}", timeout=60))["items"][0]
    st = it["status"]
    when = it["snippet"]["publishedAt"] if st["privacyStatus"] == "public" else st.get("publishAt")
    if not when:
        sys.exit("【止まりました】本編の公開の日（予約）がまだ決まっていません。本編の予約を入れてから、ショートを作ります")
    import datetime
    day = datetime.datetime.fromisoformat(when.replace("Z", "+00:00")).astimezone(datetime.timezone(datetime.timedelta(hours=9))).date()
    m = re.fullmatch(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", it["contentDetails"]["duration"])
    h, mi, s = (int(x or 0) for x in m.groups())
    return {"day": day, "minutes": round((h * 3600 + mi * 60 + s) / 60), "video_id": up["video_id"],
            "thumb": os.path.join(work, up.get("thumb") or "thumb.jpg"),
            "close": CLOSE.format(m=day.month, d=day.day, w=WEEK[day.weekday()])}


def load(work):
    s = json.load(open(os.path.join(work, "script.json"), encoding="utf-8"))
    sh = json.load(open(os.path.join(work, "short.json"), encoding="utf-8"))
    return s, sh


def check(work, clips, li):
    s, sh = load(work)
    close = li["close"]
    for c in sh.get("cuts") or []:
        if c.get("narration") == "{CLOSE}":
            c["narration"] = close
    ng = []
    cuts = sh.get("cuts") or []
    long_ids = {c["id"]: c for c in s.get("cuts", [])}
    n = sum(len(plain(c.get("narration", ""))) for c in cuts)
    if not CHARS[0] <= n <= CHARS[1]:
        ng.append(f"語りの字数 {n}字（{CHARS[0]}〜{CHARS[1]}字）")
    if not NCUT[0] <= len(cuts) <= NCUT[1]:
        ng.append(f"カット数 {len(cuts)}（{NCUT[0]}〜{NCUT[1]}）")
    used = {}
    for i, c in enumerate(cuts):
        t = c.get("narration", "")
        if c.get("id") != f"S{i + 1:02d}":
            ng.append(f"{i + 1}番目のカットの id が S{i + 1:02d} ではない：{c.get('id')}")
        if len(plain(t)) > 40:
            ng.append(f"{c.get('id')}：1カット40字まで（{len(plain(t))}字）")
        src = long_ids.get(c.get("from"))
        used[c.get("from")] = used.get(c.get("from"), 0) + 1
        if c.get("from") == "END":
            if i != len(cuts) - 1:
                ng.append(f"{c.get('id')}：from「END」（本編の案内の画面）は最後のカットだけ")
            elif not os.path.exists(li["thumb"]):
                ng.append(f"本編のサムネ {li['thumb']} がない")
        elif not src or not src.get("narration") or (src.get("card") or {}).get("type") == "chapter_title":
            ng.append(f"{c.get('id')}：from「{c.get('from')}」は、本編の語りのあるカット（章の題のカード以外）にする")
        elif not os.path.exists(os.path.join(work, clips, c["from"] + ".mp4")):
            ng.append(f"{c.get('id')}：from「{c.get('from')}」の動画が {clips} にない")
        for mark in ("──", "—", "…", "※", "★", "→"):
            if mark in t:
                ng.append(f"{c.get('id')}：記号「{mark}」は使わない")
        if t != close:
            ng += [f"{c.get('id')}：メタの言葉「{w}」" for w in META if w in t]
    ng += [f"from「{k}」が {v}回（2回まで）" for k, v in used.items() if v > 2]
    if cuts and cuts[-1].get("narration") != close:
        ng.append(f"最後のカットは決まった文「{close}」にする（short.json には {{CLOSE}} と書く）")
    if cuts and cuts[-1].get("from") != "END":
        ng.append("最後のカットの from は END（本編の案内の画面）にする")
    if cuts and not cuts[0].get("narration", "").rstrip().endswith(("？", "か。")):
        ng.append("S01 は問いの形（？か「か。」で終わる）にする")
    texts = [c.get("narration", "") for c in cuts] + [sh.get("title", ""), sh.get("desc", "")]
    ng += [f"書かないこと「{w}」：{t[:30]}" for t in texts for w in NG_WORDS if w in t]
    lines = sh.get("lines") or []
    band = ["".join(t for t, _ in ln) for ln in lines]
    gold = sum(1 for ln in lines for _, col in ln if col.upper() == GOLD)
    if not 1 <= len(lines) <= 2 or any(len(b) > 12 for b in band) or gold != 1:
        ng.append(f"上の帯の字は1〜2行・1行12字まで・金の言葉が1つ（今：{band}・金 {gold}）")
    t = sh.get("title", "")
    if not 10 <= len(t) <= 60:
        ng.append(f"ショートの題は10〜60字（今 {len(t)}字）")
    print(f"ショートの台本：語り {n}字・{len(cuts)}カット・題 {len(t)}字・帯 {band}")
    for x in ng:
        print("  NG", x)
    print(f"NG {len(ng)}件")
    return not ng


def band_png(lines, out):
    im = Image.new("RGB", (W, H), WASHI)
    d = ImageDraw.Draw(im)
    d.rectangle((0, 0, W, BAND), fill=INK)
    d.rectangle((0, BAND - 10, W, BAND), fill=(178, 58, 46))  # 朱の細い線
    ys = [(140, 124)] if len(lines) == 1 else [(60, 124), (215, 124)]
    for (y, size), runs in zip(ys, lines):
        text = "".join(t for t, _ in runs)
        while size > 60:
            if d.textlength(text, font=ImageFont.truetype(FONT, size)) <= W - 100:
                break
            size -= 6
        f = ImageFont.truetype(FONT, size)
        x = (W - d.textlength(text, font=f)) / 2
        for t, col in runs:
            d.text((x, y), t, font=f, fill=col if col.upper() == GOLD else "#F7F1E3", stroke_width=max(4, size // 18), stroke_fill=(20, 16, 12))
            x += d.textlength(t, font=f)
    d.text((W / 2, 1862), "千年こよみ", font=ImageFont.truetype(FONT, 42), fill=(150, 120, 90), anchor="mm")
    im.save(out)


def end_png(bg, li, out):
    """最後のカットの画面：本編のサムネと、公開の日・長さ・見つけ方"""
    im = Image.open(bg).convert("RGB")
    d = ImageDraw.Draw(im)
    f1, f2, f3 = (ImageFont.truetype(FONT, z) for z in (76, 58, 44))
    d.text((W / 2, IMG_Y + 95), "続きは、本編で", font=f1, fill=INK, anchor="mm")
    th = Image.open(li["thumb"]).convert("RGB").resize((960, 540), Image.LANCZOS)
    x, y = (W - 960) // 2, IMG_Y + 180
    d.rectangle((x - 8, y - 8, x + 968, y + 548), fill=(178, 58, 46))
    im.paste(th, (x, y))
    day = li["day"]
    d.text((W / 2, y + 625), f"{day.month}月{day.day}日（{WEEK[day.weekday()]}）公開・約{li['minutes']}分", font=f2, fill=(178, 58, 46), anchor="mm")
    d.text((W / 2, y + 705), "千年こよみの「動画」の欄にあります", font=f3, fill=INK, anchor="mm")
    im.save(out)


def content_box(src, b):
    """図や表のカードの、中身のある所（地の色と違う所）を、終わり近くの1コマから探す"""
    fr = os.path.join(b, os.path.basename(src) + ".png")
    run("ffmpeg", "-v", "error", "-y", "-sseof", "-0.5", "-i", src, "-frames:v", "1", fr)
    im = Image.open(fr).convert("RGB")
    diff = ImageChops.difference(im, Image.new("RGB", im.size, im.getpixel((960, 1040)))).convert("L").point(lambda v: 255 if v > 40 else 0)
    x0, y0, x1, y1 = diff.getbbox() or (0, 0, im.width, im.height)
    m = 40
    x0, y0, x1, y1 = max(0, x0 - m), max(0, y0 - m), min(im.width, x1 + m), min(im.height, y1 + m)
    return x0, y0, x1 - x0, y1 - y0


def clip(bg, src, kind, pan, d, out, b):
    size = W
    if kind == "END":  # 本編の案内の画面（静止画のまま）
        run("ffmpeg", "-v", "error", "-y", "-loop", "1", "-i", src, "-vf", f"fps={FPS}", "-t", f"{d:.3f}", "-an",
            "-pix_fmt", "yuv420p", "-c:v", "libx264", "-crf", "17", "-preset", "veryfast", out)
        return
    if kind == "photo":
        x = f"(iw-{size})*{pan}"
        img = f"[1:v]scale=-2:{size},crop={size}:{size}:{x}:0,fps={FPS},tpad=stop_mode=clone:stop_duration=30[img]"
        pos = f"0:{IMG_Y}"
    else:
        x0, y0, w, h = content_box(src, b)
        k = min((size - 40) / w, (size - 40) / h, 1.3)  # 幅と高さの両方が収まる大きさ（小さい札は1.3倍まで大きくする）
        sw, sh = int(w * k) // 2 * 2, int(h * k) // 2 * 2
        # 図のカードは本編の声の長さで動くので、ショートの声のほうが短い時は速く回して、最後の形（表の○・4つ目の札など）まで見せる
        sp = min(1.0, max(0.5, d - 0.6) / dur(src))
        img = f"[1:v]setpts=PTS*{sp:.4f},crop={w}:{h}:{x0}:{y0},scale={sw}:{sh},fps={FPS},tpad=stop_mode=clone:stop_duration=30[img]"
        pos = f"{(W - sw) // 2}:{IMG_Y + (size - sh) // 2}"
    fc = f"{img};[0:v]fps={FPS}[bg];[bg][img]overlay={pos}:shortest=1[v]"
    run("ffmpeg", "-v", "error", "-y", "-loop", "1", "-i", bg, "-i", src, "-filter_complex", fc, "-map", "[v]", "-t", f"{d:.3f}", "-an",
        "-pix_fmt", "yuv420p", "-c:v", "libx264", "-crf", "17", "-preset", "veryfast", out)


def loud(b, src):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", src, "-af", f"loudnorm=I={LUFS}:TP=-1.5:LRA=11:print_format=json", "-f", "null", "-"],
                       capture_output=True, text=True, cwd=b)
    js = r.stderr[r.stderr.rfind("{"):]
    return json.loads(js[: js.find("}") + 1])


def build(work, clips, li):
    need("ffmpeg", "ffmpeg を入れてください")
    s, sh = load(work)
    for c in sh["cuts"]:
        if c.get("narration") == "{CLOSE}":
            c["narration"] = li["close"]
    sw = os.path.join(work, "short"); b = os.path.join(sw, "_build")
    os.makedirs(b, exist_ok=True)
    # 声：作業フォルダ\short\script.json に語りだけを置いて、本編と同じ道具（感情づけ）で作る
    json.dump({"cuts": [{k: c[k] for k in ("id", "narration", "tts_text", "emo") if k in c} for c in sh["cuts"]]},
              open(os.path.join(sw, "script.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    r = subprocess.run([sys.executable, "-X", "utf8", os.path.join(ROOT, "pipeline", "make_voice_vv2.py"), "make", sw, "--ch", "spi", "--force"],
                       capture_output=True, text=True, encoding="utf-8")
    print(r.stdout[-600:], r.stderr[-400:])
    if r.returncode:
        sys.exit("【止まりました】ショートの声を作れませんでした")
    bg = os.path.join(b, "band.png"); band_png(sh["lines"], bg)
    endp = os.path.join(b, "end.png"); end_png(bg, li, endp)
    long_cuts = {c["id"]: c for c in s["cuts"]}
    t, outs, vcs, events = 0.0, [], [], []
    for c in sh["cuts"]:
        v = os.path.join(b, c["id"] + "_v.wav")
        prep_voice(os.path.join(sw, "voice", c["id"] + ".wav"), v, TEMPO, GAP)
        d = dur(v); vcs.append(v)
        kind = "END" if c["from"] == "END" else (long_cuts[c["from"]].get("card") or {}).get("type", "photo")
        src = endp if kind == "END" else os.path.join(work, clips, c["from"] + ".mp4")
        out = os.path.join(b, c["id"] + ".mp4")
        clip(bg, src, kind, c.get("pan", 0.5), d, out, b); outs.append(out)
        ps = chunks(c["narration"], SUB_MAX)
        starts = sub_starts(c["narration"], ps, d, onsets(v))[0]
        for p, st, en in zip(ps, starts, starts[1:] + [d - GAP * 0.5]):
            events.append(f"Dialogue: 0,{ass_time(t + st)},{ass_time(t + en)},Cap,,0,0,0,,{p.replace(chr(10), chr(92) + 'N')}")
        t += d
    if t > 59.5:
        sys.exit(f"【止まりました】ショートが {t:.1f}秒（60秒を超える）。short.json の語りを減らす")
    # 字幕：墨の字に和紙のふち（本編の字幕と同じ Noto Sans JP Bold）
    open(os.path.join(b, "subs.ass"), "w", encoding="utf-8").write(f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,Noto Sans JP,84,&H0022262B,&H0022262B,&H00F7FBFF,&H00000000,1,0,0,0,100,100,2,0,1,7,0,8,40,40,1530,1
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
""" + "\n".join(events) + "\n")
    fd = os.path.join(b, "fonts"); os.makedirs(fd, exist_ok=True)
    import shutil
    shutil.copyfile(FONT, os.path.join(fd, "NotoSansJP-Bold.ttf"))
    open(os.path.join(b, "clips.txt"), "w").write("".join(f"file '{p}'\n" for p in outs))
    run("ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", os.path.join(b, "clips.txt"), "-c", "copy", os.path.join(b, "video.mp4"))
    open(os.path.join(b, "voice.txt"), "w").write("".join(f"file '{p}'\n" for p in vcs))
    run("ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", os.path.join(b, "voice.txt"), os.path.join(b, "voice.wav"))
    # 音：声＋BGM → 足りない分だけ音量を上げて、リミッター（最大 −1.5 dB）で山をおさえる。
    # loudnorm だけでは、感情づけの強調で山が上がっているため −16.3 LUFS にしかならなかった（本編も −16.5 → 同じ方式で −14.8）
    bgm = os.path.abspath(os.path.join(work, s["bgm"]))
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", "voice.wav", "-stream_loop", "-1", "-i", bgm, "-filter_complex",
                    f"[1:a]volume={BGM_VOL},afade=t=in:d=1,afade=t=out:st={max(0, t - 2):.2f}:d=2[m];"
                    "[0:a][m]amix=inputs=2:duration=first:normalize=0[a]",
                    "-map", "[a]", "-t", f"{t:.3f}", "-ar", "48000", "mix.wav"], check=True, cwd=b)
    gain = LUFS - float(loud(b, "mix.wav")["input_i"])
    for _ in range(3):  # リミッターで少し下がるので、測って足す（3回まで）
        run("ffmpeg", "-v", "error", "-y", "-i", os.path.join(b, "mix.wav"), "-af", f"volume={gain:.2f}dB,alimiter=limit=0.84:level=false",
            os.path.join(b, "mix2.wav"))
        now_i = float(loud(b, "mix2.wav")["input_i"])
        if now_i >= LUFS - 0.6:
            break
        gain += LUFS - now_i
    out = os.path.join(sw, "short.mp4")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", "video.mp4", "-i", "mix2.wav", "-filter_complex",
                    "[0:v]subtitles=subs.ass:fontsdir=fonts[v];[1:a]aresample=48000[a]", "-map", "[v]", "-map", "[a]",
                    "-t", f"{t:.3f}", "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", out], check=True, cwd=b)
    f = loud(b, out)
    print(f"できました：{out}（{t:.1f}秒・{len(outs)}カット・音の大きさ {f['input_i']} LUFS・最大 {f['input_tp']} dB）")


def main():
    a = argparse.ArgumentParser()
    a.add_argument("work")
    a.add_argument("--check", action="store_true")
    a.add_argument("--clips", default=os.path.join("images", "_v3"))
    a = a.parse_args()
    work = os.path.abspath(a.work)
    li = long_info(work)
    ok = check(work, a.clips, li)
    if a.check or not ok:
        sys.exit(0 if ok else 1)
    build(work, a.clips, li)


if __name__ == "__main__":
    main()

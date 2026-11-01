# 1日の流れショート④組み立て（手順書 §12）：縦全面の絵、語りの声、字幕、時刻の大きな字を short.mp4 にする
#   python -X utf8 pipeline\build_short_routine.py <作業フォルダ> [--out 出力.mp4]
# ・絵は 1080x1920 に切り抜き、ゆっくり寄る／引く動きを交互に付ける。動く絵（images\<id>.mp4）はそのまま使い、足りない分は最後のコマでのばす
# ・"chart": "pay" のカットは、facts.json の年収・時給・労働時間を紺の地のカードにする（数字はプログラムが書く）
# ・字幕は統計ショートと同じセーフゾーンの下の段。clock は上の段に黄の大きな字。上の端に職業名の札
# ・BGM は入れない（job に音源が無い。他のチャンネルの音源は流用しない）
import argparse, json, os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "vendor", "youtube-video-maker", "scripts"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PIL import Image, ImageDraw
from common import run, need, dur, ass_time, voice_path, image_path, starts_of, chunks, prep_voice
from short_charts import W, H, FPS, SAFE_T, SAFE_B, TXT_L, TXT_R, TXT_W, BAR_T, BAR_B, CX
from make_charts_job import NAVY, PANEL, KINARI, MUTED, YELLOW, text, fit
from build_short_job import (ass_c, hook_size, safezone_sheet, KINARI as K_H, YELLOW as Y_H, NAVY as N_H, PANEL as P_H,
                             FONT, TEMPO, GAP, CAP_FS, CAP_LEN, LUFS)

MAX_SEC, MIN_SEC = 90, 45
ZOOM = 0.11  # 1カットで11%寄る／引く


def pay_card(fx, out):
    j = fx["職業"]
    im = Image.new("RGB", (W, H), NAVY)
    d = ImageDraw.Draw(im)
    x = TXT_L
    text(d, (CX, SAFE_T + 60), fx["呼び名"], fit(fx["呼び名"], 72, TXT_W), KINARI, anchor="ma")
    rows = [("平均の年収", f"{j['年収_万円']:,.1f}万円", YELLOW, 118), ("時給に直すと", f"{j['時給に直した額_円']:,.0f}円", KINARI, 96),
            ("1か月に働いた時間", f"{j['月の労働時間']:g}時間", KINARI, 96)]
    y = SAFE_T + 150
    for name, val, color, size in rows:
        d.rounded_rectangle((x - 24, y, TXT_R + 24, y + 176), 18, fill=PANEL)
        text(d, (x + 8, y + 12), name, 38, MUTED, weight=700)
        text(d, (TXT_R - 8, y + 162), val, fit(val, size, TXT_W - 16), color, anchor="rs")
        y += 190
    src = fx["使った統計"][0] + "を加工して作成"
    text(d, (CX, y + 12), src, fit(src, 34, TXT_W + 40, weight=500), MUTED, weight=500, anchor="ma")
    im.save(out)


def clip_of(src, d, zoom_in, out):
    frames = max(1, int(d * FPS) + 1)
    if src.lower().endswith(".mp4"):
        vf = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps={FPS},tpad=stop_mode=clone:stop_duration=30"
    else:
        z = f"1+{ZOOM}*on/{frames}" if zoom_in else f"{1 + ZOOM}-{ZOOM}*on/{frames}"
        vf = (f"scale={W * 2}:{H * 2}:force_original_aspect_ratio=increase,crop={W * 2}:{H * 2},"
              f"zoompan=z='{z}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s={W}x{H}:fps={FPS}")
    run("ffmpeg", "-v", "error", "-y", "-i", src, "-vf", vf, "-t", f"{d:.3f}", "-an", "-c:v", "libx264", "-crf", "17", "-preset", "fast",
        "-pix_fmt", "yuv420p", out)


def build(work, out):
    need("ffmpeg", "ffmpeg を入れてください")
    sc = json.load(open(os.path.join(work, "script.json"), encoding="utf-8"))
    fx = json.load(open(os.path.join(work, "facts.json"), encoding="utf-8"))
    b = os.path.join(work, "_build")
    os.makedirs(b, exist_ok=True)
    os.makedirs(os.path.join(work, "images"), exist_ok=True)
    cuts = sc["cuts"]
    t, clips, vs, events, moved = 0.0, [], [], [], 0
    for n, c in enumerate(cuts):
        if c.get("chart"):
            pay_card(fx, os.path.join(work, "images", c["id"] + ".png"))
        src, img = voice_path(work, c["id"]), image_path(work, c["id"])
        if not os.path.exists(src) or not img:
            sys.exit(f"【止まりました】{c['id']} の声か絵がありません")
        v = os.path.join(b, c["id"] + "_v.wav")
        prep_voice(src, v, sc.get("tempo", TEMPO), GAP)
        vs.append(v)
        d = dur(v)
        clip = os.path.join(b, c["id"] + ".mp4")
        clip_of(img, d, n % 2 == 0, clip)
        clips.append(clip)
        moved += img.lower().endswith(".mp4")
        if not c.get("chart"):
            if c.get("clock"):
                events.append(f"Dialogue: 2,{ass_time(t)},{ass_time(t + d)},Clock,,0,0,0,,{{\\an5\\pos({CX},{SAFE_T + 130})}}{c['clock']}")
            events.append(f"Dialogue: 2,{ass_time(t)},{ass_time(t + d)},Tag,,0,0,0,,{{\\an5\\pos({CX},{SAFE_T + 26})}}{fx['呼び名']}の1日")
        if c.get("hook"):
            cy = (BAR_T + BAR_B) // 2
            events.append(f"Dialogue: 3,{ass_time(t)},{ass_time(t + d)},Hook,,0,0,0,,{{\\an5\\pos({CX},{cy})\\fs{hook_size(c['hook'])}"
                          f"\\fscx40\\fscy40\\t(0,140,\\fscx112\\fscy112)\\t(140,240,\\fscx100\\fscy100)}}{c['hook'].replace(chr(10), chr(92) + 'N')}")
        ps = chunks(c["narration"], CAP_LEN)
        starts = starts_of(ps, [], d - GAP)
        for p, st, en in zip(ps, starts, starts[1:] + [d]):
            events.append(f"Dialogue: 0,{ass_time(t + st)},{ass_time(t + en)},Nar,,0,0,0,,{p.replace(chr(10), chr(92) + 'N')}")
        t += d
    box = f"1,0,0,0,100,100,0,0,3,12,0,2,{TXT_L},{W - TXT_R},{H - SAFE_B},1"
    ass = os.path.join(b, "subs.ass")
    open(ass, "w", encoding="utf-8").write(f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Nar,{FONT},{CAP_FS},{ass_c(K_H)},{ass_c(K_H)},{ass_c(P_H)},{ass_c(P_H)},{box}
Style: Clock,{FONT},132,{ass_c(Y_H)},{ass_c(Y_H)},{ass_c(N_H)},{ass_c(N_H, 0x40)},1,0,0,0,100,100,0,0,1,9,4,5,0,0,0,1
Style: Tag,{FONT},44,{ass_c(K_H)},{ass_c(K_H)},{ass_c(P_H)},{ass_c(P_H)},1,0,0,0,100,100,0,0,3,10,0,5,0,0,0,1
Style: Hook,{FONT},190,{ass_c(Y_H)},{ass_c(Y_H)},{ass_c(N_H)},{ass_c(N_H, 0x60)},1,0,0,0,100,100,0,0,1,10,4,5,0,0,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
""" + "\n".join(events) + "\n")
    lst = os.path.join(b, "clips.txt")
    open(lst, "w").write("".join(f"file '{os.path.abspath(p)}'\n" for p in clips))
    run("ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", os.path.join(b, "video.mp4"))
    vl = os.path.join(b, "voice.txt")
    open(vl, "w").write("".join(f"file '{os.path.abspath(p)}'\n" for p in vs))
    run("ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", vl, os.path.join(b, "voice.wav"))
    sub = ass.replace("\\", "/").replace(":", "\\:")
    run("ffmpeg", "-v", "error", "-y", "-i", os.path.join(b, "video.mp4"), "-i", os.path.join(b, "voice.wav"),
        "-filter_complex", f"[0:v]subtitles='{sub}'[v];[1:a]loudnorm=I={LUFS}:LRA=11:TP=-1.5,aresample=48000[a]",
        "-map", "[v]", "-map", "[a]", "-t", f"{t:.3f}", "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", out)
    safezone_sheet(out, t, os.path.join(work, "safezone_check.png"))
    print(f"できました：{out}（{t:.1f}秒・{len(cuts)}カット・動く絵 {moved}）")
    if not MIN_SEC <= t <= MAX_SEC:
        sys.exit(f"【止まりました】長さが {t:.1f}秒（1日の流れは {MIN_SEC}〜{MAX_SEC}秒）")
    return t


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("work")
    p.add_argument("--out")
    a = p.parse_args()
    build(os.path.abspath(a.work), a.out or os.path.join(os.path.abspath(a.work), "short.mp4"))

# ショート④組み立て（2026-10-27）：short_charts.py の画面と VOICEVOX の声と字幕を、縦 1080x1920 の short.mp4 にする
#   python -X utf8 pipeline\build_short_job.py <作業フォルダ> [--out 出力.mp4]
# ・スキルの build_short.py を土台に、仕事チャンネル用に変えた物（スキル側は書き換えない。クラウドのスキルは古い版のため、ここで全部持つ）
#   ・画面は images\<id>.mp4（帯とグラフ入り）。最後の画面のまま声の長さまでのばす
#   ・字幕は話し手で色を分ける（長尺と同じ。語り手は生成りの字、聞き手は紺の字に生成りの下地）。黄は字幕に使わない
#   ・字幕はセーフゾーンの下の段（1085〜1248）。1行11字まで・2行まで。タイミングは文字数の割合（Whisper は使わない）
#   ・1カット目の hook は、グラフの段の真ん中に黄の大きな字で出す（1行5字・2行まで）
#   ・声の大きさを約 −14 LUFS にそろえる
# ・できあがると safezone_check.png（赤い枠＝セーフゾーン。はじめ・真ん中・終わりの3コマ）も作る
import argparse, json, os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "vendor", "youtube-video-maker", "scripts"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import run, need, dur, ass_time, voice_path, image_path, starts_of, chunks, prep_voice, vlen
from short_charts import W, H, FPS, SAFE_L, SAFE_T, SAFE_R, SAFE_B, SAFE_W, BAR_T, BAR_B

NAVY, KINARI, YELLOW, PANEL = "#141F34", "#F3EBDD", "#F2C14E", "#1F2E4A"
FONT = "Noto Sans JP"
TEMPO, GAP = 1.15, 0.12
CAP_FS, CAP_LEN = 68, 11
LUFS = -14


def ass_c(h, alpha=0):
    h = h.lstrip("#")
    return f"&H{alpha:02X}{h[4:6]}{h[2:4]}{h[0:2]}"


def hook_size(s):
    longest = max(vlen(x) for x in s.split("\n")) or 1
    return min(190, int(SAFE_W * 0.92 / longest))


def safezone_sheet(video, t, out):
    ts = [min(0.6, t / 4), t / 2, max(0.0, t - 1.0)]
    ins = []
    for x in ts:
        ins += ["-ss", f"{x:.2f}", "-i", video]
    fc = ";".join(f"[{i}:v]trim=end_frame=1,drawbox=x={SAFE_L}:y={SAFE_T}:w={SAFE_W}:h={SAFE_B - SAFE_T}:color=red@0.9:t=6,scale=360:640[f{i}]"
                  for i in range(3)) + ";[f0][f1][f2]hstack=inputs=3"
    run("ffmpeg", "-v", "error", "-y", *ins, "-filter_complex", fc, "-frames:v", "1", out)


def build(work, out):
    need("ffmpeg", "ffmpeg を入れてください")
    sc = json.load(open(os.path.join(work, "script.json"), encoding="utf-8"))
    b = os.path.join(work, "_build"); os.makedirs(b, exist_ok=True)
    cuts = sc["cuts"]
    t, clips, vs, events = 0.0, [], [], []
    for c in cuts:
        src = voice_path(work, c["id"])
        img = image_path(work, c["id"])
        if not os.path.exists(src) or not img:
            sys.exit(f"【止まりました】{c['id']} の声か画面がありません（make_voice_vv.py・short_charts.py）")
        v = os.path.join(b, c["id"] + "_v.wav"); prep_voice(src, v, sc.get("tempo", TEMPO), GAP); vs.append(v)
        d = dur(v)
        clip = os.path.join(b, c["id"] + ".mp4")
        run("ffmpeg", "-v", "error", "-y", "-i", img, "-vf", f"fps={FPS},tpad=stop_mode=clone:stop_duration=30",
            "-t", f"{d:.3f}", "-an", "-c:v", "libx264", "-crf", "16", "-preset", "fast", "-pix_fmt", "yuv420p", clip)
        clips.append(clip)
        if c.get("hook"):
            cy = (BAR_T + BAR_B) // 2
            events.append(f"Dialogue: 1,{ass_time(t)},{ass_time(t + d)},Hook,,0,0,0,,{{\\an5\\pos({(SAFE_L + SAFE_R) // 2},{cy})\\fs{hook_size(c['hook'])}"
                          f"\\fscx40\\fscy40\\t(0,140,\\fscx112\\fscy112)\\t(140,240,\\fscx100\\fscy100)}}{c['hook'].replace(chr(10), chr(92) + 'N')}")
        ps = chunks(c["narration"], CAP_LEN)
        speak = d - GAP
        starts = starts_of(ps, [], speak)
        ends = starts[1:] + [d]
        style = "Lis" if c.get("speaker") == "listener" else "Nar"
        for p, st, en in zip(ps, starts, ends):
            events.append(f"Dialogue: 0,{ass_time(t + st)},{ass_time(t + en)},{style},,0,0,0,,{p.replace(chr(10), chr(92) + 'N')}")
        t += d
    box = f"1,0,0,0,100,100,0,0,3,12,0,2,{SAFE_L},{W - SAFE_R},{H - SAFE_B},1"  # 地の箱つき・下そろえ。下の端がセーフゾーンの下（1248）
    ass = os.path.join(b, "subs.ass")
    open(ass, "w", encoding="utf-8").write(f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Nar,{FONT},{CAP_FS},{ass_c(KINARI)},{ass_c(KINARI)},{ass_c(PANEL)},{ass_c(PANEL)},{box}
Style: Lis,{FONT},{CAP_FS},{ass_c(NAVY)},{ass_c(NAVY)},{ass_c(KINARI)},{ass_c(KINARI)},{box}
Style: Hook,{FONT},190,{ass_c(YELLOW)},{ass_c(YELLOW)},{ass_c(NAVY)},{ass_c(NAVY, 0x60)},1,0,0,0,100,100,0,0,1,10,4,5,0,0,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
""" + "\n".join(events) + "\n")
    lst = os.path.join(b, "clips.txt"); open(lst, "w").write("".join(f"file '{os.path.abspath(p)}'\n" for p in clips))
    run("ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", os.path.join(b, "video.mp4"))
    vl = os.path.join(b, "voice.txt"); open(vl, "w").write("".join(f"file '{os.path.abspath(p)}'\n" for p in vs))
    run("ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", vl, os.path.join(b, "voice.wav"))
    sub = ass.replace("\\", "/").replace(":", "\\:")
    run("ffmpeg", "-v", "error", "-y", "-i", os.path.join(b, "video.mp4"), "-i", os.path.join(b, "voice.wav"),
        "-filter_complex", f"[0:v]subtitles='{sub}'[v];[1:a]loudnorm=I={LUFS}:LRA=11:TP=-1.5,aresample=48000[a]",
        "-map", "[v]", "-map", "[a]", "-t", f"{t:.3f}", "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", out)
    safezone_sheet(out, t, os.path.join(work, "safezone_check.png"))
    print(f"できました：{out}（{t:.1f}秒・{len(cuts)}カット）")
    if not 15 <= t <= 59:
        sys.exit(f"【止まりました】長さが {t:.1f}秒（ショートは15〜59秒にする）")
    return t


if __name__ == "__main__":
    p = argparse.ArgumentParser(); p.add_argument("work"); p.add_argument("--out")
    a = p.parse_args()
    build(os.path.abspath(a.work), a.out or os.path.join(os.path.abspath(a.work), "short.mp4"))

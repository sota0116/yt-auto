# ⑧組み立て（設計書 §5⑧・仕事の手順書 §3）：スキルの build_long.py を土台にした、仕事チャンネル用の組み立て
#   python -X utf8 pipeline\build_long_job.py <作業フォルダ> [--out 出力.mp4]
# スキルの build_long.py からの変更（スキル側は書き換えない）：
#   ・絵を動かす時の拡大を2倍から1.5倍に（処理を軽く）。つなぎの動画は速い設定で作る
#   ・声の大きさを約 −15 LUFS にそろえる（loudnorm）
#   ・字幕のタイミングは、カットごとの声の長さを文字数の割合で分けて決める（Whisper は使わない）
#   ・字幕の色を話し手で分ける：語り手は紺の地に生成りの文字、聞き手は生成りの地に紺の文字。黄色は使わない。画面の下8%はあける
#   ・クイズのカット（"quiz": true）のあとは2秒の間をあける（答えを考える時間）
#   ・章の頭の札（第○章）は、図のカットには重ねない（図の左上の見出しとぶつかるため。章の名前は YouTube のチャプターに残る）
#   ・"badge": "イメージ" のカットは、右上の隅に小さく札を出す（読み上げない）
#   ・書き出しは約4Mbps（10分で約300MB）
#   ・グラフ（images\<id>.mp4）は、短い時は最後の画面のままのばし、カットの間ずっと3%だけゆっくり寄る（2026-10-25。止まった画面が続かないように。
#     図は画面の上75%の内側にあるので、3%寄っても端の文字は切れない）
#   ・声の頭か終わりに大きな雑音（5ミリ秒で振れが0.3超）があるカットは、組み立てずに止まる
#   ・効果音（2026-10-29。手順書 §5）：驚きの粒（"wow": true）のカットの頭に短く上がる音、見どころ（"peak": true）の頭に「ジャン」と鳴る和音。
#     ffmpeg で計算して作る音なので、素材の権利もお金もかからない。声より小さく（SFX_VOL）、声の大きさをそろえる前に混ぜる
import argparse, json, os, sys
from PIL import Image, ImageDraw, ImageFont
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "vendor", "youtube-video-maker", "scripts"))
from common import (load_config, run, need, dur, font_file, ass_time, voice_path, resolve_image, starts_of, chunks,
                    prep_voice, find_bgm)
from build_long import label_png, chapter_png

W, H, FPS = 1920, 1080, 30
ZOOM = 1.5
NAVY, KINARI = "#141F34", "#F3EBDD"
FONT_SUB = "Noto Sans JP"
QUIZ_GAP, GAP = 2.0, 0.3
LUFS = -15
VBIT = "4M"
SFX_VOL = 0.35
SFX = {"wow": ("0.6*sin(2*PI*(880+1800*t)*t)*exp(-14*t)", 0.3),
       "peak": ("0.45*sin(2*PI*523*t)*exp(-4*t)+0.35*sin(2*PI*784*t)*exp(-4*t)+0.4*sin(2*PI*130*t)*exp(-10*t)", 0.9)}
# 見どころの音はスマホのスピーカーで聞こえる高さ（523Hz・784Hz の和音）を主にする。低い音（130Hz）は補助。100Hz 以下はスマホでほぼ鳴らない


def ass_c(h, alpha=0):
    h = h.lstrip("#")
    return f"&H{alpha:02X}{h[4:6]}{h[2:4]}{h[0:2]}"


def badge_png(text, path, cfg):
    f = ImageFont.truetype(font_file(cfg["font_gothic"]), 34)
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    w = d.textlength(text, font=f)
    d.rounded_rectangle((W - 60 - w - 36, 44, W - 60, 44 + 58), 10, fill=(20, 31, 52, 190))
    d.text((W - 60 - w - 18, 50), text, font=f, fill=(243, 235, 221))
    im.save(path)


def edge_peak(path):
    """声の頭と終わり（無音の前）の5ミリ秒の、いちばん大きい振れ（0〜1）"""
    import wave
    import numpy as np
    with wave.open(path) as w:
        sr = w.getframerate()
        x = np.abs(np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768)
    nz = np.flatnonzero(x > 1e-3)
    if not len(nz):
        return 0.0
    k = sr // 200
    return float(max(x[:k].max(), x[max(0, nz[-1] - k):nz[-1] + 1].max()))


def sfx_wav(kind, path):
    expr, d = SFX[kind]
    run("ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"aevalsrc='{expr}':s=48000:d={d}", "-ac", "1", path)


def sfx_mix(times, first):
    """効果音を鳴らす時刻 {種類: [秒]} から、入力に足す種類（first 番目から）と、混ぜた音 [sx] を作る式を返す"""
    kinds, fc, outs = [], "", []
    for kind, ts in times.items():
        if not ts:
            continue
        k = first + len(kinds)
        kinds.append(kind)
        fc += f"[{k}:a]asplit={len(ts)}" + "".join(f"[{kind}{j}]" for j in range(len(ts))) + ";"
        for j, st in enumerate(ts):
            fc += f"[{kind}{j}]adelay={int(st * 1000)}:all=1[{kind}d{j}];"
            outs.append(f"[{kind}d{j}]")
    if outs:
        fc += "".join(outs) + f"amix=inputs={len(outs)}:duration=longest:normalize=0,volume={SFX_VOL}[sx];"
    return kinds, fc


def build(work, out, gap_base=GAP):
    need("ffmpeg", "ffmpeg を入れてください")
    cfg = load_config(work)
    cfg.update({"label_color": KINARI, "label_color2": "#F2C14E", "chapter_bg": NAVY, "chapter_accent": "#F2C14E"})
    sc = json.load(open(os.path.join(work, "script.json"), encoding="utf-8"))
    tempo = sc.get("tempo", cfg["tempo_long"])
    b = os.path.join(work, "_build"); os.makedirs(b, exist_ok=True)
    cuts = [c for c in sc["cuts"] if c.get("narration")]
    missing = [c["id"] for c in cuts if not os.path.exists(voice_path(work, c["id"]))]
    if missing:
        raise SystemExit(f"【止まりました】声がないカット：{missing[:10]}（{len(missing)}カット）")
    noimg = [c["id"] for c in cuts if not resolve_image(work, sc["cuts"], c)]
    if noimg:
        raise SystemExit(f"【止まりました】絵がないカット：{noimg[:10]}（{len(noimg)}カット）")
    t, clips, vcs, events, chaps, nchap = 0.0, [], [], [], [], 0
    sfx = {"wow": [], "peak": []}
    for n, c in enumerate(cuts):
        gap = QUIZ_GAP if c.get("quiz") else gap_base
        v = os.path.join(b, c["id"] + "_v.wav"); prep_voice(voice_path(work, c["id"]), v, tempo, gap); vcs.append(v)
        pop = edge_peak(v)
        if pop > 0.3:  # 声の頭か終わりの5ミリ秒が大きい＝切り替わりで「バチッ」と鳴る（1本目は wav の頭が音として入っていた）
            raise SystemExit(f"【止まりました】声の頭か終わりに大きな雑音：{c['id']}（大きさ {pop:.2f}。voice の {c['id']}.wav を作り直す）")
        d = dur(v)
        if c.get("peak") or c.get("wow"):
            sfx["peak" if c.get("peak") else "wow"].append(t + 0.05)
        src_img = resolve_image(work, sc["cuts"], c)
        clip = os.path.join(b, c["id"] + ".mp4")
        if src_img.endswith(".mp4"):
            nfr = int(d * FPS) + 2
            src = ["-i", src_img]
            vf = (f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps={FPS},tpad=stop_mode=clone:stop_duration=60,"
                  f"scale={int(W * ZOOM)}:{int(H * ZOOM)},zoompan=z='1+0.03*on/{nfr}':x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2':d=1:s={W}x{H}:fps={FPS}")
        else:  # 静止画は、ゆっくり寄る／ゆっくり横に流す を交互に
            nfr = int(d * FPS) + 2
            sw, sh = int(W * ZOOM), int(H * ZOOM)
            src = ["-loop", "1", "-i", src_img]
            move = (f"z='1+0.08*on/{nfr}':x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2'" if n % 2 == 0
                    else f"z='1.08':x='(iw-iw/zoom)*on/{nfr}':y='ih/2-ih/zoom/2'")
            vf = f"scale={sw}:{sh}:force_original_aspect_ratio=increase,crop={sw}:{sh},zoompan={move}:d={nfr}:s={W}x{H}:fps={FPS}"
        overlays = []
        if c.get("chapter"):
            nchap += 1; chaps.append((t, c["chapter"]))
            if not (c.get("chart") or src_img.endswith(".mp4")):  # 図は左上に自分の見出しがあるので、章の札を重ねない（2026-10-24 完成品ゲートで重なりを検出）
                p = os.path.join(b, c["id"] + "_chap.png"); chapter_png(c["chapter"], nchap, p, cfg)
                overlays.append((p, 0.0, min(d, 4.5)))
        if c.get("label") and not src_img.endswith(".mp4"):  # グラフの上には重ねない
            p = os.path.join(b, c["id"] + "_label.png"); label_png(c["label"], p, cfg, c.get("strong", False), 90)
            overlays.append((p, 0.3, d))
        if c.get("badge"):
            p = os.path.join(b, c["id"] + "_badge.png"); badge_png(c["badge"], p, cfg)
            overlays.append((p, 0.0, d))
        enc = ["-t", f"{d:.3f}", "-an", "-pix_fmt", "yuv420p", "-c:v", "libx264", "-crf", "18", "-preset", "veryfast", clip]
        if overlays:
            ins = sum([["-loop", "1", "-i", p] for p, _, _ in overlays], [])
            fc = f"[0:v]{vf}[v0];"
            for k, (_, st, en) in enumerate(overlays):
                fc += f"[{k + 1}:v]fade=t=in:st={st}:d=0.25:alpha=1[o{k}];[v{k}][o{k}]overlay=0:0:enable='between(t,{st},{en})':shortest=1[v{k + 1}];"
            run("ffmpeg", "-v", "error", "-y", *src, *ins, "-filter_complex", fc.rstrip(";"), "-map", f"[v{len(overlays)}]", *enc)
        else:
            run("ffmpeg", "-v", "error", "-y", *src, "-vf", vf, *enc)
        clips.append(clip)
        ps = chunks(c["narration"], 22)
        speak = d - gap
        starts = starts_of(ps, [], speak)  # 文字数の割合で決める
        ends = starts[1:] + [speak + min(gap, 0.3) * 0.5]
        style = "Lis" if c.get("speaker") == "listener" else "Nar"
        for p, st, en in zip(ps, starts, ends):
            events.append(f"Dialogue: 0,{ass_time(t + st)},{ass_time(t + en)},{style},,0,0,0,,{p.replace(chr(10), chr(92) + 'N')}")
        t += d
        print(c["id"], f"{d:.1f}秒", flush=True)
    ass = os.path.join(b, "subs.ass")
    box = "1,0,0,0,100,100,0,0,3,14,0,2,80,80,90,1"  # BorderStyle 3＝地の箱。下の余白90px（画面の8%強）
    open(ass, "w", encoding="utf-8").write(f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Nar,{FONT_SUB},74,{ass_c(KINARI)},{ass_c(KINARI)},{ass_c(NAVY, 0x20)},{ass_c(NAVY, 0x20)},{box}
Style: Lis,{FONT_SUB},74,{ass_c(NAVY)},{ass_c(NAVY)},{ass_c(KINARI, 0x10)},{ass_c(KINARI, 0x10)},{box}

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
""" + "\n".join(events) + "\n")
    lst = os.path.join(b, "clips.txt"); open(lst, "w").write("".join(f"file '{os.path.abspath(p)}'\n" for p in clips))
    run("ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", os.path.join(b, "video.mp4"))
    vl = os.path.join(b, "voice.txt"); open(vl, "w").write("".join(f"file '{os.path.abspath(p)}'\n" for p in vcs))
    run("ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", vl, os.path.join(b, "voice.wav"))
    bgm = find_bgm(work, sc.get("bgm"))
    ins = ["-i", os.path.join(b, "video.mp4"), "-i", os.path.join(b, "voice.wav")]
    if bgm:
        ins += ["-stream_loop", "-1", "-i", bgm]
        mix = (f"[2:a]volume={cfg['bgm_volume']},afade=t=in:d=1.5,afade=t=out:st={max(0, t - 2.5):.2f}:d=2.5[m];"
               "[1:a]volume=1.0[n];[n][m]amix=inputs=2:duration=first:normalize=0[am];")
    else:
        mix = "[1:a]anull[am];"
    kinds, s_fc = sfx_mix(sfx, 3 if bgm else 2)
    if s_fc:
        for kind in kinds:
            sfx_wav(kind, os.path.join(b, f"sfx_{kind}.wav"))
            ins += ["-i", os.path.join(b, f"sfx_{kind}.wav")]
        mix += s_fc + "[am][sx]amix=inputs=2:duration=first:normalize=0[amx];"
    else:
        mix += "[am]anull[amx];"
    mix += f"[amx]loudnorm=I={LUFS}:LRA=11:TP=-1.5,aresample=48000[a]"
    sub = ass.replace("\\", "/").replace(":", "\\:")
    run("ffmpeg", "-v", "error", "-y", *ins, "-filter_complex", f"[0:v]subtitles='{sub}'[v];{mix}",
        "-map", "[v]", "-map", "[a]", "-t", f"{t:.3f}", "-c:v", "libx264", "-preset", "medium",
        "-b:v", VBIT, "-maxrate", "5M", "-bufsize", "8M", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", out)
    lines = []
    if chaps and chaps[0][0] > 0:
        lines.append("0:00 はじめに")
    for st, name in chaps:
        lines.append(f"{int(st // 60)}:{int(st % 60):02d} {name}")
    open(os.path.join(work, "chapters.txt"), "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print(f"できました：{out}（{int(t // 60)}分{int(t % 60)}秒）")


if __name__ == "__main__":
    p = argparse.ArgumentParser(); p.add_argument("work"); p.add_argument("--out")
    p.add_argument("--gap", type=float, default=GAP, help="カットの間の秒（8分にわずかに足りない時に run_daily.py が広げる。0.6まで）")
    a = p.parse_args()
    build(a.work, a.out or os.path.join(a.work, "long.mp4"), a.gap)

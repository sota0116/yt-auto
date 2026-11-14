# 企業もしもショート④組み立て（手順書 §15）：縦全面の絵、語りの声、字幕に、固定の題・年齢の札・本物のロゴを重ねて short.mp4 にする
#   python -X utf8 pipeline\build_short_kigyo.py <作業フォルダ> [--out 出力.mp4]
# ・絵の切り方・字幕・音は 1日の流れ（build_short_routine.py）と同じ（§15「絵：1日の流れと同じ組み立て」）
# ・カットごとに透明の板（1080x1920 の PNG）を作って絵に重ねる。板に載せる物：
#     全カット：上の端に固定の題「もし〇〇に就職したら」、その下の右に「人物・出来事はイメージです」（決まり3。読み上げない）
#     1カット目：hook（「どこに入る？」）と、候補の会社のロゴを白い札に並べる。札の下にロゴの断りの1文（決まり4）
#     "logo" のカット：主役の会社のロゴを白い札に1つ
#     "tag" のカット：年齢と年収の札（facts.json の値。Claude は計算しない）と「業界の平均」・出典
# ・ロゴは facts.json の logos の PNG を、形・色・縦横の比を変えずに縮めるだけ（決まり4）。白い札の上に置き、絵とは混ぜない
import argparse, json, os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "vendor", "youtube-video-maker", "scripts"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PIL import Image, ImageDraw
from common import run, need, dur, ass_time, voice_path, image_path, starts_of, chunks, prep_voice
from short_charts import W, H, FPS, SAFE_T, TXT_L, TXT_R, TXT_W, CX
from make_charts_job import NAVY, KINARI, MUTED, YELLOW, text, fit, tw
from build_short_job import ass_c, KINARI as K_H, PANEL as P_H, FONT, TEMPO, GAP, CAP_FS, CAP_LEN, LUFS
from build_short_routine import clip_of, safezone_sheet
import short_audio

MAX_SEC, MIN_SEC = 90, 55  # §15 は60〜80秒。声の速さの揺れで外れても、55〜90秒なら出す（ショートの上限は3分）
WHITE, INK = (255, 255, 255), (20, 31, 52)
SHADE = (20, 31, 52, 200)  # 字の下に敷く紺（絵の上でも読めるように）


def band(d, box, r=16):
    d.rounded_rectangle(box, r, fill=SHADE)


def put_logo(im, path, box):
    """ロゴを box（左, 上, 右, 下）の中に、縦横の比を変えずに真ん中へ置く"""
    lg = Image.open(path).convert("RGBA")
    bw, bh = box[2] - box[0], box[3] - box[1]
    s = min(bw / lg.width, bh / lg.height)
    lg = lg.resize((max(1, round(lg.width * s)), max(1, round(lg.height * s))), Image.LANCZOS)
    im.alpha_composite(lg, (box[0] + (bw - lg.width) // 2, box[1] + (bh - lg.height) // 2))


def board(work, sc, fx, c, n, out):
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    title = fx["題"]
    fs = fit(title, 64, TXT_W - 40)
    band(d, (TXT_L - 20, SAFE_T, TXT_R + 20, SAFE_T + fs + 36))
    text(d, (CX, SAFE_T + 16), title, fs, KINARI, anchor="ma")
    note = fx["イメージの断り"]
    y = SAFE_T + fs + 48
    nw = fit(note, 34, TXT_W, weight=700)
    band(d, (TXT_R - 16 - round(tw(note, nw, 700)), y - 6, TXT_R + 16, y + nw + 10), 10)
    text(d, (TXT_R, y), note, nw, KINARI, weight=700, anchor="ra")
    top = y + nw + 40  # ここから下に札を置く
    logos = {l["会社"]: os.path.join(work, l["png"]) for l in fx["logos"]}
    if n == 0:
        hook = c.get("hook", "").replace("\n", "")
        hs = fit(hook, 120, TXT_W)
        text(d, (CX, top), hook, hs, YELLOW, anchor="ma")
        names = [x for x in c.get("logos", []) if x in logos]
        rows = (len(names) + 1) // 2
        py, cw, ch = top + hs + 30, (TXT_W + 40 - 30) // 2, 120
        ph = rows * (ch + 14) + 14
        d.rounded_rectangle((TXT_L - 20, py, TXT_R + 20, py + ph), 18, fill=WHITE)
        for i, name in enumerate(names):
            r, k = divmod(i, 2)
            left = TXT_L - 10 + k * (cw + 10)
            if i == len(names) - 1 and len(names) % 2:  # 最後の1つは真ん中
                left = CX - cw // 2
            put_logo(im, logos[name], (left + 14, py + 14 + r * (ch + 14) + 10, left + cw - 14, py + 14 + r * (ch + 14) + ch - 10))
        ny = py + ph + 14
        for line in split_note(fx["ロゴの断り"]):
            s = fit(line, 32, TXT_W, weight=700)
            band(d, (TXT_L - 20, ny - 4, TXT_R + 20, ny + s + 8), 8)
            text(d, (CX, ny), line, s, KINARI, weight=700, anchor="ma")
            ny += s + 14
    elif c.get("logo") in logos:
        d.rounded_rectangle((TXT_L + 40, top, TXT_R - 40, top + 220), 20, fill=WHITE)
        put_logo(im, logos[c["logo"]], (TXT_L + 80, top + 30, TXT_R - 80, top + 190))
    if c.get("tag"):
        t = next(x for x in fx["年齢の札"] if x["年齢"].replace("～", "〜") == c["tag"].replace("～", "〜"))
        age, val = t["年齢"].replace("～", "〜"), t["声の年収"].lstrip("約")
        lab = "業界の平均（1,000人以上の企業）"
        src = fx["使った統計"][0] + "を加工して作成"
        a_s, v_s, l_s, s_s = fit(age, 92, TXT_W), fit(val, 160, TXT_W), fit(lab, 40, TXT_W, weight=700), fit(src, 30, TXT_W, weight=500)
        band(d, (TXT_L - 20, top - 10, TXT_R + 20, top + a_s + v_s + l_s + s_s + 70), 20)
        text(d, (CX, top), age, a_s, KINARI, anchor="ma")
        text(d, (CX, top + a_s + 10), val, v_s, YELLOW, anchor="ma")
        text(d, (CX, top + a_s + v_s + 30), lab, l_s, KINARI, weight=700, anchor="ma")
        text(d, (CX, top + a_s + v_s + l_s + 46), src, s_s, MUTED, weight=500, anchor="ma")
    im.save(out)


def split_note(s):
    """ロゴの断り（「ロゴは各社の商標です。この動画は各社と関係ありません」）を文の切れ目で2行に"""
    i = s.find("。")
    return [s[:i + 1], s[i + 1:]] if 0 < i < len(s) - 1 else [s]


def overlay(clip, png, out):
    run("ffmpeg", "-v", "error", "-y", "-i", clip, "-i", png, "-filter_complex", "[0:v][1:v]overlay=0:0:format=auto,format=yuv420p",
        "-an", "-c:v", "libx264", "-crf", "17", "-preset", "fast", out)


def build(work, out):
    need("ffmpeg", "ffmpeg を入れてください")
    sc = json.load(open(os.path.join(work, "script.json"), encoding="utf-8"))
    fx = json.load(open(os.path.join(work, "facts.json"), encoding="utf-8"))
    b = os.path.join(work, "_build")
    os.makedirs(b, exist_ok=True)
    cuts = sc["cuts"]
    t, clips, vs, events, moved, changes = 0.0, [], [], [], 0, 0
    hits = {"hit": [0.0], "tick": [], "coin": [], "peak": []}
    for n, c in enumerate(cuts):
        src, img = voice_path(work, c["id"]), image_path(work, c["id"])
        if not os.path.exists(src) or not img:
            sys.exit(f"【止まりました】{c['id']} の声か絵がありません")
        v = os.path.join(b, c["id"] + "_v.wav")
        prep_voice(src, v, sc.get("tempo", TEMPO), GAP)
        vs.append(v)
        d = dur(v)
        raw = os.path.join(b, c["id"] + "_raw.mp4")
        changes += clip_of(img, d, n, raw)
        png = os.path.join(b, c["id"] + "_board.png")
        board(work, sc, fx, c, n, png)
        clip = os.path.join(b, c["id"] + ".mp4")
        overlay(raw, png, clip)
        clips.append(clip)
        moved += img.lower().endswith(".mp4")
        if c.get("peak"):
            hits["peak"].append(t)
        elif c.get("tag"):
            hits["coin"].append(t)
        elif c.get("logo"):
            hits["tick"].append(t)
        ps = chunks(c["narration"], CAP_LEN)
        starts = starts_of(ps, [], d - GAP)
        for p, st, en in zip(ps, starts, starts[1:] + [d]):
            events.append(f"Dialogue: 0,{ass_time(t + st)},{ass_time(t + en)},Nar,,0,0,0,,{p.replace(chr(10), chr(92) + 'N')}")
        t += d
    from short_charts import SAFE_B
    box = f"1,0,0,0,100,100,0,0,3,12,0,2,{TXT_L},{W - TXT_R},{H - SAFE_B},1"
    ass = os.path.join(b, "subs.ass")
    open(ass, "w", encoding="utf-8").write(f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Nar,{FONT},{CAP_FS},{ass_c(K_H)},{ass_c(K_H)},{ass_c(P_H)},{ass_c(P_H)},{box}

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
    audio = os.path.join(b, "audio.wav")
    short_audio.note(work, sc, short_audio.mix(work, os.path.join(b, "voice.wav"), t, hits, audio, short_audio.pick_bgm(work, ("tense", "lofi"))))
    run("ffmpeg", "-v", "error", "-y", "-i", os.path.join(b, "video.mp4"), "-i", audio,
        "-filter_complex", f"[0:v]subtitles='{sub}'[v];[1:a]loudnorm=I={LUFS}:LRA=11:TP=-1.5,aresample=48000[a]",
        "-map", "[v]", "-map", "[a]", "-t", f"{t:.3f}", "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", out)
    safezone_sheet(out, t, os.path.join(work, "safezone_check.png"))
    print(f"できました：{out}（{t:.1f}秒・{len(cuts)}カット・動く絵 {moved}・画面の変化 {changes}回・BGM {sc['bgm']}）")
    if not MIN_SEC <= t <= MAX_SEC:
        sys.exit(f"【止まりました】長さが {t:.1f}秒（企業もしもは {MIN_SEC}〜{MAX_SEC}秒）")
    return t


def preview(work):
    """声と絵が無くても、板だけを紺の地に重ねて見る（手元の確かめ用）。work\\_build\\preview_<id>.png"""
    sc = json.load(open(os.path.join(work, "script.json"), encoding="utf-8"))
    fx = json.load(open(os.path.join(work, "facts.json"), encoding="utf-8"))
    b = os.path.join(work, "_build")
    os.makedirs(b, exist_ok=True)
    for n, c in enumerate(sc["cuts"]):
        if n and not (c.get("logo") or c.get("tag")):
            continue
        p = os.path.join(b, f"preview_{c['id']}.png")
        board(work, sc, fx, c, n, p)
        bg = Image.new("RGBA", (W, H), NAVY + (255,))
        bg.alpha_composite(Image.open(p))
        bg.convert("RGB").save(p)
        print(p)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("work")
    p.add_argument("--out")
    p.add_argument("--preview", action="store_true")
    a = p.parse_args()
    if a.preview:
        preview(os.path.abspath(a.work))
    else:
        build(os.path.abspath(a.work), a.out or os.path.join(os.path.abspath(a.work), "short.mp4"))

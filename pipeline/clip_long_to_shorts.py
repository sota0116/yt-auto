# -*- coding: utf-8 -*-
"""完成した横動画（長尺）から、画像生成ゼロ・音声再生成ゼロで縦9:16ショート（1080x1920）を2〜3本切り出す共通ツール。

使い方:
  python -X utf8 pipeline/clip_long_to_shorts.py <横動画の作業フォルダ> [--ch shimei] [--count 2] [--out-root <出力先>] [--prefix S_clip] [--video <mp4>]

特徴:
- 既存の完成横動画（16:9）の映像・音声のみを再利用（AI画像生成・Lovart課金・TTS再生成なし）。
- 1080x1920 のぼかし背景＋中央16:9本編クリップ（1080x608 @ y=585）＋Pillow製透過RGBAオーバーレイ（上部見出し＋下部CTA）。
- subtitles=/drawtext= のパスエスケープ不具合を避けるため、文字はすべて Pillow で透過PNG描画して overlay=0:0 で合成。
- 音量はフェードイン/アウト＋2-pass loudnorm で -14.5 LUFS (TP -1.5) に統一。
- 各出力フォルダに short.mp4 / safezone_check.png / voice/_credits.txt / script.json / upload.json を出力。
"""
import argparse
import glob
import json
import os
import re
import subprocess
import sys
import wave

from PIL import Image, ImageDraw, ImageFont

W, H = 1080, 1920
SAFE = (48, 288, 888, 1248)  # (x1, y1, x2, y2)
CLIP_W, CLIP_H, CLIP_Y = 1080, 608, 585
TEXT_X1, TEXT_X2 = 192, 888
MIN_DUR, MAX_DUR = 25.0, 59.0
TARGET_MIN, TARGET_MAX = 35.0, 54.0

CHANNEL_META = {
    "shimei": {
        "display": "指名手配ボード",
        "accent": (255, 208, 64, 255),
        "pill_bg": (20, 24, 34, 215),
        "border": (220, 64, 64, 235),
        "default_credit": "VOICEVOX:雀松朱司",
        "hashtags": "#shorts #未解決 #事件 #指名手配ボード",
        "disclosure": "※本動画の映像・音声の一部にはAIツールを使用しています。",
        "tags": ["shorts", "事件", "指名手配ボード", "海外事件", "実話"],
    },
    "nihongi": {
        "display": "アナザー日本紀",
        "accent": (255, 212, 71, 255),
        "pill_bg": (32, 22, 16, 215),
        "border": (214, 164, 66, 235),
        "default_credit": "VOICEVOX:青山龍星",
        "hashtags": "#shorts #もしも #日本史",
        "disclosure": "※本動画の映像・音声の一部にはAIツールを使用しています。",
        "tags": ["shorts", "もしも", "日本史", "歴史", "アナザー日本紀"],
    },
    "okinu": {
        "display": "金運おきぬ",
        "accent": (255, 220, 88, 255),
        "pill_bg": (38, 28, 16, 215),
        "border": (218, 178, 72, 235),
        "default_credit": "VOICEVOX:波音リツ",
        "hashtags": "#shorts #金運",
        "disclosure": "※本動画の映像・音声の一部にはAIツールを使用しています。\n※お話は創作です。",
        "tags": ["shorts", "金運", "金運おきぬ", "開運", "暮らし"],
    },
    "spi": {
        "display": "白蛇弁財天・翠仙",
        "accent": (255, 222, 96, 255),
        "pill_bg": (20, 32, 36, 215),
        "border": (224, 188, 84, 235),
        "default_credit": "",
        "hashtags": "#shorts #金運 #翠仙",
        "disclosure": "※本動画の映像・音声の一部にはAIツールを使用しています。\n※運気やご利益には個人差があり、結果を保証するものではありません。",
        "tags": ["shorts", "金運", "翠仙", "白蛇", "開運"],
    },
    "shinshiten": {
        "display": "シン視点事件簿",
        "accent": (245, 200, 72, 255),
        "pill_bg": (18, 22, 30, 220),
        "border": (196, 154, 64, 235),
        "default_credit": "VOICEVOX:青山龍星",
        "hashtags": "#shorts",
        "disclosure": "※本動画の映像・音声の一部にはAIツールを使用しています。",
        "tags": ["shorts", "事件解説", "シン視点事件簿"],
    },
}


def find_jp_font():
    cands = []
    windir = os.environ.get("WINDIR")
    if windir:
        fdir = os.path.join(windir, "Fonts")
        for name in ("NotoSansJP-Bold.ttf", "BIZ-UDGothicB.ttc", "meiryob.ttc", "YuGothB.ttc", "NotoSansJP-VF.ttf", "msgothic.ttc"):
            cands.append(os.path.join(fdir, name))
    cands += [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/noto-cjk/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansJP-Bold.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/truetype/fonts-japanese-gothic.ttf",
        "/usr/share/fonts/truetype/takao-gothic/TakaoPGothic.ttf",
        "/usr/share/fonts/truetype/vlgothic/VL-PGothic-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ]
    for p in cands:
        if os.path.exists(p):
            return p
    for root in ("/usr/share/fonts", "/usr/local/share/fonts"):
        if os.path.isdir(root):
            for dp, _, files in os.walk(root):
                for f in files:
                    if re.search(r"(NotoSans.*CJK|NotoSansJP|Gothic|IPA.*g).*\.tt[cf]$", f, re.I):
                        return os.path.join(dp, f)
    return None


def load_font(path, size):
    if path:
        try:
            f = ImageFont.truetype(path, size)
            if path.lower().endswith("-vf.ttf") and hasattr(f, "set_variation_by_name"):
                try:
                    f.set_variation_by_name("Bold")
                except Exception:
                    pass
            return f
        except Exception:
            pass
    return ImageFont.load_default()


def probe_video(path):
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type,width,height", "-of", "json", path],
        capture_output=True, text=True, encoding="utf-8", errors="replace", check=True,
    )
    j = json.loads(r.stdout or "{}")
    dur = float(j.get("format", {}).get("duration") or 0)
    w = h = 0
    has_audio = False
    for st in j.get("streams", []):
        if st.get("codec_type") == "video" and not w:
            w, h = int(st.get("width") or 0), int(st.get("height") or 0)
        elif st.get("codec_type") == "audio":
            has_audio = True
    return dur, w, h, has_audio


def detect_silences(video_path):
    r = subprocess.run(
        ["ffmpeg", "-v", "info", "-i", video_path, "-af", "silencedetect=noise=-35dB:d=0.4", "-f", "null", "-"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    cuts = []
    cur_start = None
    for line in (r.stderr or "").splitlines():
        m1 = re.search(r"silence_start:\s*([0-9.]+)", line)
        if m1:
            cur_start = float(m1.group(1))
        m2 = re.search(r"silence_end:\s*([0-9.]+)", line)
        if m2:
            end = float(m2.group(1))
            mid = (cur_start + end) / 2.0 if cur_start is not None else end
            cuts.append((cur_start if cur_start is not None else end, end, mid))
            cur_start = None
    return cuts


def snap_to_silence(t, silences, max_delta=1.4):
    best_t, best_d = t, max_delta + 1.0
    for s0, s1, mid in silences:
        for cand in (mid, s0, s1):
            d = abs(cand - t)
            if d <= max_delta and d < best_d:
                best_t, best_d = cand, d
    return best_t


def find_source_video(work_dir, explicit_video=None):
    if explicit_video:
        p = explicit_video if os.path.isabs(explicit_video) else os.path.join(work_dir, explicit_video)
        if os.path.exists(p):
            return p
    up_path = os.path.join(work_dir, "upload.json")
    if os.path.exists(up_path):
        try:
            u = json.load(open(up_path, encoding="utf-8"))
            vp = os.path.join(work_dir, u.get("video", ""))
            if os.path.isfile(vp):
                return vp
        except Exception:
            pass
    for name in ("完成.mp4", "long_final.mp4", "long.mp4"):
        p = os.path.join(work_dir, name)
        if os.path.isfile(p):
            return p
    cands = [
        p for p in glob.glob(os.path.join(work_dir, "*.mp4"))
        if "_1440p" not in os.path.basename(p) and not os.path.basename(p).startswith(("_raw", "raw."))
    ]
    if not cands:
        cands = glob.glob(os.path.join(work_dir, "*.mp4"))
    return max(cands, key=os.path.getsize) if cands else None


def cut_timeline(work_dir, script, total_dur):
    cuts = [c for c in (script.get("cuts") or []) if c.get("narration")]
    if not cuts:
        return []
    raw_durs = []
    for c in cuts:
        cid = c.get("id", "")
        d = None
        for rel in (os.path.join("_build", f"{cid}_v.wav"), os.path.join("_build_v3", f"{cid}_v.wav"), os.path.join("voice", f"{cid}.wav")):
            wp = os.path.join(work_dir, rel)
            if os.path.isfile(wp):
                try:
                    with wave.open(wp) as wf:
                        d = wf.getnframes() / float(wf.getframerate())
                    break
                except Exception:
                    pass
        if d is None:
            d = max(1.8, len(c.get("narration", "")) / 5.5)
        raw_durs.append(d)
    s_raw = sum(raw_durs) or 1.0
    scale = total_dur / s_raw
    out, t = [], 0.0
    for c, d in zip(cuts, raw_durs):
        dd = d * scale
        out.append({"id": c.get("id", ""), "start": t, "end": t + dd, "text": c.get("narration", ""), "cut": c})
        t += dd
    return out


def clean_headline(text, fallback):
    raw = re.sub(r"[【】\[\]『』「」<>＜＞\n\r]", " ", text or "").strip()
    raw = re.sub(r"\s+", " ", raw)
    # Prefer a complete clause/sentence within 8..22 chars instead of mid-word truncation
    clauses = [c.strip() for c in re.split(r"(?<=[。！？!?])", raw) if c.strip()]
    chosen = ""
    for cl in clauses:
        cl_c = re.sub(r"[。、！？!?]+$", "", cl)
        if not chosen:
            chosen = cl_c
        elif len(chosen) + len(cl_c) + 1 <= 22:
            chosen = chosen + " " + cl_c
        else:
            break
    if len(chosen) > 22:
        parts = [p.strip() for p in re.split(r"[、，,｜|・\s]+", chosen) if p.strip()]
        acc = ""
        for p in parts:
            if not acc:
                acc = p
            elif len(acc) + len(p) + 1 <= 22:
                acc = acc + " " + p
            else:
                break
        chosen = acc if 6 <= len(acc) <= 22 else (re.sub(r"[【】\[\]『』「」<>＜＞]", "", fallback or "").strip()[:22])
    chosen = re.sub(r"[。、！？!?]+$", "", chosen).strip()
    if len(chosen) < 5:
        chosen = re.sub(r"[【】\[\]『』「」<>＜＞]", "", fallback or "").strip()[:22]
    return chosen[:22]


def _bad_split(s, pos):
    if pos <= 0 or pos >= len(s):
        return True
    a, b = s[pos - 1], s[pos]
    # Avoid splitting inside ASCII alphanumerics or Katakana words
    if re.match(r"[A-Za-z0-9]", a) and re.match(r"[A-Za-z0-9]", b):
        return True
    if "\u30A0" <= a <= "\u30FF" and "\u30A0" <= b <= "\u30FF":
        return True
    return False


def split_two_lines(text, max_chars=12):
    s = re.sub(r"\s+", " ", (text or "")).strip()
    compact = s.replace(" ", "")
    if len(compact) <= max_chars:
        return [compact]
    # Try splitting at explicit space first
    if " " in s:
        best = None
        for m in re.finditer(r" ", s):
            l1 = s[: m.start()].replace(" ", "")
            l2 = s[m.end() :].replace(" ", "")
            if 2 <= len(l1) <= max_chars and 2 <= len(l2) <= max_chars:
                score = abs(len(l1) - len(l2))
                if best is None or score < best[0]:
                    best = (score, [l1, l2])
        if best:
            return best[1]
    s = compact[: max_chars * 2]
    mid = len(s) // 2
    for delta in range(0, 6):
        for pos in (mid + delta, mid - delta):
            if 3 <= pos <= max_chars and (len(s) - pos) <= max_chars and not _bad_split(s, pos):
                if s[pos - 1] in "。、！？!?のはがをにでとへもや":
                    return [s[:pos], s[pos:]]
    for delta in range(0, 6):
        for pos in (mid + delta, mid - delta):
            if 3 <= pos <= max_chars and (len(s) - pos) <= max_chars and not _bad_split(s, pos):
                return [s[:pos], s[pos:]]
    return [s[:max_chars], s[max_chars : max_chars * 2]]


def pick_segments(work_dir, video_path, script, total_dur, count, silences):
    tl = cut_timeline(work_dir, script, total_dur)
    segs = []
    if tl and total_dur >= 90:
        anchors = [0.0, total_dur * 0.34, total_dur * 0.64]
        used = []
        for idx, anchor in enumerate(anchors):
            if len(segs) >= count:
                break
            si = min(range(len(tl)), key=lambda i: abs(tl[i]["start"] - anchor))
            while si < len(tl) and any(a - 5 <= tl[si]["start"] <= b + 5 for a, b in used):
                si += 1
            if si >= len(tl):
                continue
            start_t = tl[si]["start"]
            end_i = si
            while end_i + 1 < len(tl) and (tl[end_i + 1]["end"] - start_t) <= TARGET_MAX:
                end_i += 1
                if (tl[end_i]["end"] - start_t) >= TARGET_MIN and tl[end_i]["text"].rstrip().endswith(("。", "！", "？")):
                    if (tl[end_i]["end"] - start_t) >= 40.0:
                        break
            end_t = min(total_dur - 0.5, tl[end_i]["end"])
            s_snapped = max(0.0, snap_to_silence(start_t, silences, 1.2))
            e_snapped = min(total_dur - 0.2, snap_to_silence(end_t, silences, 1.2))
            dur = e_snapped - s_snapped
            if dur < MIN_DUR:
                e_snapped = min(total_dur - 0.2, s_snapped + 42.0)
                dur = e_snapped - s_snapped
            if dur > MAX_DUR:
                e_snapped = s_snapped + 54.0
                dur = e_snapped - s_snapped
            if dur < MIN_DUR or any(not (e_snapped <= a or s_snapped >= b) for a, b in used):
                continue
            used.append((s_snapped, e_snapped))
            snippet = "".join(x["text"] for x in tl[si : end_i + 1])
            first_line = tl[si]["text"]
            label = tl[si]["cut"].get("label") or ""
            segs.append({"start": round(s_snapped, 2), "end": round(e_snapped, 2), "headline": clean_headline(first_line, script.get("title") or label), "snippet": snippet[:160]})
    if len(segs) < count:
        step = max(55.0, (total_dur - 50.0) / max(1, count))
        used = [(x["start"], x["end"]) for x in segs]
        for i in range(count * 2):
            if len(segs) >= count:
                break
            s0 = min(max(1.0, i * step + 1.0), max(1.0, total_dur - 46.0))
            s0 = max(0.0, snap_to_silence(s0, silences, 1.4))
            e0 = min(total_dur - 0.3, s0 + 44.0)
            e0 = min(total_dur - 0.2, snap_to_silence(e0, silences, 1.4))
            if e0 - s0 > MAX_DUR:
                e0 = s0 + 52.0
            if e0 - s0 < MIN_DUR or any(not (e0 <= a or s0 >= b) for a, b in used):
                continue
            used.append((s0, e0))
            segs.append({"start": round(s0, 2), "end": round(e0, 2), "headline": clean_headline(script.get("title") or os.path.basename(work_dir), os.path.basename(work_dir)), "snippet": ""})
    return segs[:count]


def draw_centered_text(draw, y, text, font, fill, stroke_fill=(0, 0, 0, 245), stroke_w=6, cx=540):
    bbox = draw.textbbox((0, 0), text, font=font, stroke_width=stroke_w)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    x = int(cx - tw / 2)
    x = max(TEXT_X1 + 6, min(x, TEXT_X2 - tw - 6))
    draw.text((x, y), text, font=font, fill=fill, stroke_width=stroke_w, stroke_fill=stroke_fill)
    return th


def make_overlay_png(out_png, headline, ch_cfg, font_path):
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Top & bottom accent bars framing the centered 16:9 clip
    border = ch_cfg["border"]
    draw.rectangle([0, CLIP_Y - 4, W, CLIP_Y], fill=border)
    draw.rectangle([0, CLIP_Y + CLIP_H, W, CLIP_Y + CLIP_H + 4], fill=border)

    # Channel badge inside top safe zone (y=298..342, x within 192..888)
    badge_font = load_font(font_path, 28)
    badge_txt = f" {ch_cfg['display']} "
    bb = draw.textbbox((0, 0), badge_txt, font=badge_font)
    bw, bh = bb[2] - bb[0] + 32, bb[3] - bb[1] + 14
    bx1 = max(TEXT_X1, int(540 - bw / 2))
    bx2 = min(TEXT_X2, bx1 + bw)
    draw.rounded_rectangle([bx1, 296, bx2, 296 + bh], radius=18, fill=ch_cfg["pill_bg"], outline=border, width=2)
    draw.text((bx1 + 16, 296 + 5), badge_txt, font=badge_font, fill=ch_cfg["accent"])

    # Headline (1-2 bold lines, <=12 chars/line, strictly inside x=192..888 and y=354..562)
    lines = split_two_lines(headline, max_chars=12)
    fsize = 54
    while fsize >= 34:
        hfont = load_font(font_path, fsize)
        max_w = max(draw.textbbox((0, 0), ln, font=hfont, stroke_width=6)[2] for ln in lines)
        if max_w <= (TEXT_X2 - TEXT_X1 - 16):
            break
        fsize -= 4
    hfont = load_font(font_path, fsize)
    line_heights = [draw.textbbox((0, 0), ln, font=hfont, stroke_width=6)[3] for ln in lines]
    total_h = sum(line_heights) + max(0, len(lines) - 1) * 14
    cur_y = 356 + max(0, (200 - total_h) // 2)
    for idx, ln in enumerate(lines):
        fill = ch_cfg["accent"] if idx == len(lines) - 1 else (255, 255, 255, 255)
        th = draw_centered_text(draw, cur_y, ln, hfont, fill=fill, stroke_w=6)
        cur_y += th + 14

    # Bottom CTA pill inside y=1205..1246, x within 192..888
    cta_txt = f"▼ 本編は概要欄リンクから｜{ch_cfg['display']}"
    csize = 24
    while csize >= 16:
        cfont = load_font(font_path, csize)
        cb = draw.textbbox((0, 0), cta_txt, font=cfont)
        if (cb[2] - cb[0] + 36) <= (TEXT_X2 - TEXT_X1):
            break
        csize -= 2
    cfont = load_font(font_path, csize)
    cb = draw.textbbox((0, 0), cta_txt, font=cfont)
    cw, ch_h = cb[2] - cb[0] + 36, min(40, cb[3] - cb[1] + 14)
    cx1 = max(TEXT_X1, int(540 - cw / 2))
    cx2 = min(TEXT_X2, cx1 + cw)
    cy1, cy2 = 1205, min(1246, 1205 + ch_h)
    draw.rounded_rectangle([cx1, cy1, cx2, cy2], radius=18, fill=ch_cfg["pill_bg"], outline=border, width=2)
    tx = cx1 + max(10, (cx2 - cx1 - (cb[2] - cb[0])) // 2)
    ty = cy1 + max(4, (cy2 - cy1 - (cb[3] - cb[1])) // 2 - 2)
    draw.text((tx, ty), cta_txt, font=cfont, fill=(255, 255, 255, 255))

    img.save(out_png)


def measure_loudnorm(video_path, start, dur):
    af = f"afade=t=in:st=0:d=0.15,afade=t=out:st={max(0.2, dur - 0.35):.2f}:d=0.35,loudnorm=I=-14.5:TP=-1.5:LRA=11:print_format=json"
    r = subprocess.run(
        ["ffmpeg", "-v", "info", "-ss", f"{start:.3f}", "-t", f"{dur:.3f}", "-i", video_path, "-vn", "-af", af, "-f", "null", "-"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    m = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", r.stderr or "", re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


def render_clip(video_path, start, end, overlay_png, out_mp4):
    dur = end - start
    ln = measure_loudnorm(video_path, start, dur)
    fade = f"afade=t=in:st=0:d=0.15,afade=t=out:st={max(0.2, dur - 0.35):.2f}:d=0.35"
    if ln and ln.get("input_i") not in (None, "-inf"):
        af = (
            f"{fade},loudnorm=I=-14.5:TP=-1.5:LRA=11:linear=true:"
            f"measured_I={ln['input_i']}:measured_TP={ln['input_tp']}:"
            f"measured_LRA={ln['input_lra']}:measured_thresh={ln['input_thresh']}:offset={ln['target_offset']}"
        )
    else:
        af = f"{fade},loudnorm=I=-14.5:TP=-1.5:LRA=11"

    vf = (
        f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
        f"boxblur=20:5,eq=brightness=-0.22:saturation=0.85,setsar=1[bg];"
        f"[0:v]scale={CLIP_W}:{CLIP_H}:force_original_aspect_ratio=decrease,"
        f"pad={CLIP_W}:{CLIP_H}:(ow-iw)/2:(oh-ih)/2:black,setsar=1[fg];"
        f"[bg][fg]overlay=0:{CLIP_Y}[v1];"
        f"[v1][1:v]overlay=0:0,fps=30,format=yuv420p[vout]"
    )
    cmd = [
        "ffmpeg", "-y", "-v", "error",
        "-ss", f"{start:.3f}", "-t", f"{dur:.3f}", "-i", video_path,
        "-loop", "1", "-t", f"{dur:.3f}", "-i", overlay_png,
        "-filter_complex", vf,
        "-map", "[vout]", "-map", "0:a:0",
        "-af", af,
        "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-threads", "4", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
        "-movflags", "+faststart", "-shortest",
        out_mp4,
    ]
    subprocess.run(cmd, check=True)


def make_safezone_check(mp4_path, out_png):
    tmp = out_png + ".frame.png"
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-ss", "2.0", "-i", mp4_path, "-frames:v", "1", tmp],
        check=True,
    )
    img = Image.open(tmp).convert("RGBA")
    draw = ImageDraw.Draw(img)
    draw.rectangle(SAFE, outline=(255, 48, 48, 255), width=4)
    draw.rectangle([TEXT_X1, SAFE[1], TEXT_X2, SAFE[3]], outline=(64, 220, 255, 220), width=2)
    img.convert("RGB").save(out_png)
    os.remove(tmp)


def read_credits(work_dir, default_credit):
    for rel in (os.path.join("voice", "_credits.txt"), "voice_credits.txt", os.path.join("voice", "_credit.txt")):
        p = os.path.join(work_dir, rel)
        if os.path.isfile(p):
            lines = [x.strip() for x in open(p, encoding="utf-8", errors="replace").read().splitlines() if x.strip()]
            if lines:
                return lines
    return [default_credit] if default_credit else []


def sanitize_yt_text(s):
    return (s or "").replace("<", "＜").replace(">", "＞").strip()


def clip_long(work_dir, ch="shimei", count=2, out_root=None, prefix="S_clip", explicit_video=None):
    work_dir = os.path.abspath(work_dir)
    long_name = os.path.basename(work_dir)
    out_root = os.path.abspath(out_root or os.path.dirname(work_dir))
    ch_cfg = CHANNEL_META.get(ch, CHANNEL_META["shimei"])

    video_path = find_source_video(work_dir, explicit_video)
    if not video_path:
        raise FileNotFoundError(f"横動画のmp4が見つかりません: {work_dir}")
    total_dur, vw, vh, has_audio = probe_video(video_path)
    if total_dur < MIN_DUR or not has_audio:
        raise RuntimeError(f"切り出し不可の動画です: dur={total_dur:.1f}s audio={has_audio} ({video_path})")

    script_path = os.path.join(work_dir, "script.json")
    script = json.load(open(script_path, encoding="utf-8")) if os.path.isfile(script_path) else {}
    uploaded_path = os.path.join(work_dir, "uploaded.json")
    long_vid = json.load(open(uploaded_path, encoding="utf-8")).get("video_id") if os.path.isfile(uploaded_path) else None

    silences = detect_silences(video_path)
    segs = pick_segments(work_dir, video_path, script, total_dur, count, silences)
    font_path = find_jp_font()
    credits = read_credits(work_dir, ch_cfg["default_credit"])

    created = []
    for idx, seg in enumerate(segs, 1):
        clip_name = f"{prefix}_{long_name}_{idx:02d}"
        clip_dir = os.path.join(out_root, clip_name)
        os.makedirs(clip_dir, exist_ok=True)
        overlay_png = os.path.join(clip_dir, "_overlay.png")
        out_mp4 = os.path.join(clip_dir, "short.mp4")
        safe_png = os.path.join(clip_dir, "safezone_check.png")

        make_overlay_png(overlay_png, seg["headline"], ch_cfg, font_path)
        render_clip(video_path, seg["start"], seg["end"], overlay_png, out_mp4)
        make_safezone_check(out_mp4, safe_png)
        if os.path.exists(overlay_png):
            os.remove(overlay_png)

        if credits:
            vdir = os.path.join(clip_dir, "voice")
            os.makedirs(vdir, exist_ok=True)
            with open(os.path.join(vdir, "_credits.txt"), "w", encoding="utf-8") as f:
                f.write("\n".join(credits) + "\n")

        base_title = sanitize_yt_text(seg["headline"])
        long_title = sanitize_yt_text(script.get("title") or long_name)
        title = f"{base_title}｜{ch_cfg['display']} #shorts"
        if len(title) > 98:
            title = f"{base_title[:70]} #shorts"

        desc_parts = []
        if long_vid:
            desc_parts.append(f"▼ 本編はこちら\nhttps://youtu.be/{long_vid}")
        if seg.get("snippet"):
            desc_parts.append(sanitize_yt_text(seg["snippet"]))
        else:
            desc_parts.append(long_title)
        desc_parts.append(ch_cfg["disclosure"])
        if credits:
            desc_parts.append("音声：" + " / ".join(credits))
        desc_parts.append(ch_cfg["hashtags"])
        desc = sanitize_yt_text("\n\n".join(p for p in desc_parts if p))[:4950]

        clip_script = {
            "format": "short",
            "title": title,
            "desc": desc,
            "tags": list(ch_cfg["tags"]),
            "source_work": long_name,
            "source_video_id": long_vid,
            "clip_index": idx,
            "clip_start": seg["start"],
            "clip_end": seg["end"],
        }
        with open(os.path.join(clip_dir, "script.json"), "w", encoding="utf-8") as f:
            json.dump(clip_script, f, ensure_ascii=False, indent=1)
        with open(os.path.join(clip_dir, "upload.json"), "w", encoding="utf-8") as f:
            json.dump({"video": "short.mp4", "format": "short"}, f, ensure_ascii=False, indent=1)

        cdur, cw, ch_px, caudio = probe_video(out_mp4)
        if not (cw == W and ch_px == H and MIN_DUR <= cdur <= 59.5 and caudio):
            raise RuntimeError(f"生成品質ゲート不合格: {clip_dir} ({cw}x{ch_px}, {cdur:.1f}s, audio={caudio})")
        print(f"[clip_long_to_shorts] OK {clip_name}: {cw}x{ch_px} {cdur:.1f}s ({seg['start']:.1f}-{seg['end']:.1f}s) -> {clip_dir}", flush=True)
        created.append(clip_dir)
    return created


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("work", help="完成した横動画の作業フォルダ")
    ap.add_argument("--ch", default="shimei", choices=list(CHANNEL_META.keys()))
    ap.add_argument("--count", type=int, default=2)
    ap.add_argument("--out-root", default=None)
    ap.add_argument("--prefix", default="S_clip")
    ap.add_argument("--video", default=None)
    args = ap.parse_args()
    created = clip_long(args.work, ch=args.ch, count=args.count, out_root=args.out_root, prefix=args.prefix, explicit_video=args.video)
    for d in created:
        print(d)


if __name__ == "__main__":
    main()

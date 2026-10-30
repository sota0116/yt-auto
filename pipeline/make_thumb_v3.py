# 金運おきぬ用の写し（2026-10-30）：スキル youtube-video-maker/scripts/make_thumb.py v3 をそのまま写し、common の探し先だけ vendor にした。make_thumb_okinu.py が import して使う
# サムネイルに文字を入れる → 1280x720 の JPG（長尺）／1080x1920（ショート）
#   python3 scripts/make_thumb.py <作業フォルダ>/thumb.json
# thumb.json の見本は templates/thumb.json。決まり（型・点検）は references/15_サムネの型.md
#   "bg": 背景の絵（作業フォルダからの場所）  "size": "long" か "short"
#   "shade": 文字を読みやすくする暗いグラデーション（"left" "right" "top" "bottom" "both"（上と下） か null）
#   "texts": [{"t": "文字", "x": 40, "y": 400, "size": 160, "color": "#FFFFFF" か ["#上の色","#真ん中","#下の色"], "box": "#帯の色" か null,
#              "hl": ["色を変える語"], "hl_color": "#FF2A2A" か [3色],  "glow": "#光の色" か null,  "center": true（横の真ん中にそろえる）,
#              "edge": "#縁の色" か null（字のすぐ外に色の縁、その外に黒い縁。赤い字に白い縁を付ける時）}]
#   "marks": [{"type": "circle", "box": [x0, y0, x1, y1]} か {"type": "arrow", "from": [x, y], "to": [x, y]}]（赤に白い縁。絵の中のモノを指す）
# ・文字は少なく大きく。スマホの小さい画面で一瞬で読めるか、縮小して確かめる（--preview で小さい版も作る）
# ・作ったあとに点検を出す（いちばん大きい字の横幅・字の面積・行数・色を変えた語）。NG があっても絵は保存する
# v2（2026-10-28）：hl・glow・center・shade "both"・点検を足した。前の版は make_thumb_v1_文字入れのみ.py
# v3（2026-10-29）：edge・marks を足した（金運の競合の「破産します」型。references/15 の参考5）。前の版は make_thumb_v2_2026-10-28.py
import json, os, sys
from PIL import Image, ImageDraw, ImageFilter, ImageFont
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "vendor", "youtube-video-maker", "scripts"))  # common（vendor の写し）
from common import load_config, font_file, hex_rgb


def shade(im, side):
    if side == "both":
        shade(im, "top"); shade(im, "bottom"); return
    w, h = im.size; g = Image.new("L", (w, h), 0); d = ImageDraw.Draw(g)
    n = w if side in ("left", "right") else h
    reach = 0.62 if side in ("left", "right") else 0.45
    for i in range(n):
        a = int(210 * max(0, 1 - i / (n * reach)))
        if side == "left": d.line((i, 0, i, h), fill=a)
        elif side == "right": d.line((w - 1 - i, 0, w - 1 - i, h), fill=a)
        elif side == "top": d.line((0, i, w, i), fill=a)
        else: d.line((0, h - 1 - i, w, h - 1 - i), fill=a)
    im.paste((0, 0, 0), (0, 0, w, h), g)


def gradient(size, cols):
    w, h = size; g = Image.new("RGB", (1, h))
    for y in range(h):
        t = y / max(1, h - 1); a, b, u = (cols[0], cols[1], t * 2) if t < 0.5 else (cols[1], cols[2], (t - 0.5) * 2)
        g.putpixel((0, y), tuple(int(a[k] + (b[k] - a[k]) * u) for k in range(3)))
    return g.resize((w, h))


def colors(col):
    return [hex_rgb(c) for c in col] if isinstance(col, list) else [hex_rgb(col)] * 3


def draw_text(im, t, cfg):
    s = t["size"]
    ff = font_file(t.get("font") or cfg["font_heavy"])
    font = ImageFont.truetype(ff, s)
    W, H = im.size
    lines = t["t"].split("\n")
    meas = ImageDraw.Draw(Image.new("L", (1, 1)))
    widest = lambda f: max(meas.textlength(l, font=f) for l in lines)
    # はみ出すときは小さくする（どの行も）
    while (t["x"] if not t.get("center") else 20) + widest(font) > W - 20 and s > 40:
        s -= 6; font = ImageFont.truetype(ff, s)
    gap = s // 6
    line_h = meas.textbbox((0, 0), "A", font=font)[3] + gap
    xs = [(W - meas.textlength(l, font=font)) / 2 if t.get("center") else t["x"] for l in lines]
    ys = [t["y"] + i * line_h for i in range(len(lines))]
    mask = Image.new("L", (W, H), 0); md = ImageDraw.Draw(mask)
    hl_mask = Image.new("L", (W, H), 0); hd = ImageDraw.Draw(hl_mask)
    for l, x, y in zip(lines, xs, ys):
        md.text((x, y), l, font=font, fill=255)
        for w in t.get("hl") or []:
            i = l.find(w)
            while i >= 0:  # 同じ語が2回あれば両方
                hd.text((x + meas.textlength(l[:i], font=font), y), w, font=font, fill=255)
                i = l.find(w, i + len(w))
    if t.get("box"):
        bb = mask.getbbox(); ImageDraw.Draw(im).rounded_rectangle((bb[0] - 22, bb[1] - 16, bb[2] + 22, bb[3] + 16), 10, fill=t["box"])
    ow = max(6, s // 11)
    inner = mask.filter(ImageFilter.MaxFilter(ow * 2 + 1)) if t.get("edge") else None
    outline = mask.filter(ImageFilter.MaxFilter(ow * (4 if inner else 2) + 1))
    if t.get("glow"):  # 黒い縁の外側に色の光（暗い絵の上で字が浮いて見える）
        glow = outline.filter(ImageFilter.MaxFilter(ow * 2 + 1)).filter(ImageFilter.GaussianBlur(s // 7))
        im.paste(hex_rgb(t["glow"]), (0, 0, W, H), glow.point(lambda v: min(255, int(v * 1.6))))
    im.paste((0, 0, 0), (s // 22, s // 18, W + s // 22, H + s // 18), outline.filter(ImageFilter.GaussianBlur(s // 14)).point(lambda v: int(v * 0.8)))
    im.paste((0, 0, 0), (0, 0, W, H), outline)
    if inner: im.paste(hex_rgb(t["edge"]), (0, 0, W, H), inner)
    im.paste(gradient((W, H), colors(t.get("color", "#FFFFFF"))), (0, 0), mask)
    if hl_mask.getbbox():
        im.paste(gradient((W, H), colors(t.get("hl_color", "#FF2A2A"))), (0, 0), hl_mask)
    return {"size": s, "lines": len(lines), "width": widest(font), "bbox": mask.getbbox(), "hl": bool(hl_mask.getbbox()) or bool(t.get("hl"))}


def draw_marks(im, marks):
    """赤丸・赤い矢印（白い縁つき）。絵の中のモノを指す"""
    d = ImageDraw.Draw(im)
    for m in marks or []:
        for col, w in (("#FFFFFF", 22), ("#E60012", 12)):
            if m["type"] == "circle":
                d.ellipse(m["box"], outline=col, width=w)
            else:
                (x0, y0), (x1, y1) = m["from"], m["to"]
                dx, dy = x1 - x0, y1 - y0; n = max(1, (dx * dx + dy * dy) ** 0.5); ux, uy = dx / n, dy / n
                hl, hw = 44 + w, 30 + w // 2  # 矢じりの長さと幅
                bx, by = x1 - ux * hl, y1 - uy * hl
                d.line((x0, y0, bx, by), fill=col, width=w + 8)
                d.polygon([(x1 + ux * w / 3, y1 + uy * w / 3), (bx - uy * hw, by + ux * hw), (bx + uy * hw, by - ux * hw)], fill=col)


def check(results, size):
    """15_サムネの型.md の点検。数字のめやすは参考チャンネル36枚を見て決めた（推測を含む）"""
    W, H = size; ng = []
    big = max(results, key=lambda r: r["size"])
    ratio = big["width"] / W
    lines = sum(r["lines"] for r in results)
    area = 0
    for r in results:
        if r["bbox"]: area += (r["bbox"][2] - r["bbox"][0]) * (r["bbox"][3] - r["bbox"][1])
    area /= W * H
    print(f"点検：いちばん大きい字の横幅 {ratio:.0%}（めやす70%以上）／字の面積 約{area:.0%}（めやす30〜60%）／行数 {lines}（めやす4行まで）")
    if ratio < 0.70: ng.append("いちばん大きい字が細い。答えの語を横幅いっぱい（70%以上）にする")
    if area < 0.30: ng.append("字が少なすぎて目に入らない（面積30%未満）")
    if area > 0.60: ng.append("字が絵をつぶしている（面積60%超）")
    if lines > 4: ng.append("行が多い。上の段（何の話か）と下の段（答え・ひっかかり）の2段にまとめる")
    if not any(r["hl"] for r in results): ng.append("色を変えた語が無い。いちばん強い1語に hl を付ける")
    for m in ng: print("  NG", m)
    if not ng: print("  点検 NG 0件")
    return ng


def main(spec_path, preview=False):
    s = json.load(open(spec_path, encoding="utf-8")); base = os.path.dirname(os.path.abspath(spec_path))
    cfg = load_config(base)
    size = (1080, 1920) if s.get("size") == "short" else (1280, 720)
    bg = Image.open(os.path.join(base, s["bg"])).convert("RGB")
    r = max(size[0] / bg.width, size[1] / bg.height)  # はみ出す分は切って、画面いっぱいにする
    bg = bg.resize((int(bg.width * r + .5), int(bg.height * r + .5)))
    im = bg.crop(((bg.width - size[0]) // 2, (bg.height - size[1]) // 2, (bg.width - size[0]) // 2 + size[0], (bg.height - size[1]) // 2 + size[1]))
    if s.get("shade"): shade(im, s["shade"])
    draw_marks(im, s.get("marks"))
    results = [draw_text(im, t, cfg) for t in s["texts"]]
    out = os.path.join(base, s.get("out", "thumb.jpg")); im.save(out, quality=92); print("保存", out)
    check(results, size)
    if preview:  # スマホで見たときの大きさ（横幅 320px）
        p = out.replace(".jpg", "_small.jpg"); im.resize((320, int(320 * size[1] / size[0]))).save(p, quality=90); print("小さい版", p)


if __name__ == "__main__":
    main(sys.argv[1], "--preview" in sys.argv)

# サムネの字の一部にモザイクをかける（2026-11-09 シン視点事件簿）
#   python -X utf8 pipeline/make_thumb_mosaic_v1.py <thumb.json> [--preview]
# make_thumb_v3 の絵の作り方はそのまま使い、字を描いたあと、JPGに保存する前にモザイクをかける。
# thumb.json の texts に足す項目:
#   "mosaic": ["殺"]（モザイクをかける語。同じ語が2回あれば両方）
#   "mosaic_block": 24（モザイクの1マスの大きさ。省略時は字の大きさの1/7）
import json, os, sys
from PIL import Image, ImageDraw, ImageFont
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.expanduser("~/.claude/skills/youtube-video-maker/scripts"))  # common の本体（vendor に写しが無いため）
import make_thumb_v3 as m


def word_boxes(t, r, W, cfg):
    """字の実際の位置を、make_thumb_v3.draw_text と同じ計算で出す"""
    s = r["size"]; font = ImageFont.truetype(m.font_file(t.get("font") or cfg["font_heavy"]), s)
    meas = ImageDraw.Draw(Image.new("L", (1, 1))); lines = t["t"].split("\n")
    line_h = meas.textbbox((0, 0), "A", font=font)[3] + s // 6
    pad_y = max(6, s // 11); out = []  # 字の縁1本分だけ広げる（広げすぎると四角が字からはみ出す）
    for k, l in enumerate(lines):
        x = (W - meas.textlength(l, font=font)) / 2 if t.get("center") else t["x"]
        y = t["y"] + k * line_h
        for w in t.get("mosaic") or []:
            i = l.find(w)
            while i >= 0:
                x0 = x + meas.textlength(l[:i], font=font); x1 = x + meas.textlength(l[:i + len(w)], font=font)
                bb = font.getbbox(w)
                out.append((int(x0), int(y + bb[1] - pad_y), int(x1 + .5), int(y + bb[3] + pad_y)))
                i = l.find(w, i + len(w))
    return out


def pixelate(im, box, block):
    x0, y0, x1, y1 = box; c = im.crop(box); w, h = c.size
    small = c.resize((max(1, w // block), max(1, h // block)), Image.BOX)
    im.paste(small.resize((w, h), Image.NEAREST), (x0, y0))


def main(spec_path, preview=False):
    s = json.load(open(spec_path, encoding="utf-8")); base = os.path.dirname(os.path.abspath(spec_path))
    cfg = m.load_config(base); size = (1080, 1920) if s.get("size") == "short" else (1280, 720)
    bg = Image.open(os.path.join(base, s["bg"])).convert("RGB")
    r = max(size[0] / bg.width, size[1] / bg.height)
    bg = bg.resize((int(bg.width * r + .5), int(bg.height * r + .5)))
    im = bg.crop(((bg.width - size[0]) // 2, (bg.height - size[1]) // 2, (bg.width - size[0]) // 2 + size[0], (bg.height - size[1]) // 2 + size[1]))
    if s.get("shade"): m.shade(im, s["shade"])
    m.draw_marks(im, s.get("marks"))
    results = [m.draw_text(im, t, cfg) for t in s["texts"]]
    n = 0
    for t, res in zip(s["texts"], results):  # 字を全部描いてからかける（後の字の縁に隠れない）
        for box in word_boxes(t, res, size[0], cfg):
            pixelate(im, box, t.get("mosaic_block") or max(8, res["size"] // 7)); n += 1; print("モザイク", t["mosaic"], box)
    if n != sum(t["t"].count(w) for t in s["texts"] for w in t.get("mosaic") or []):
        print("  NG モザイクの数が語の数と合わない")
    out = os.path.join(base, s.get("out", "thumb.jpg")); im.save(out, quality=92); print("保存", out)
    m.check(results, size)
    if preview:
        p = out.replace(".jpg", "_small.jpg"); im.resize((320, int(320 * size[1] / size[0]))).save(p, quality=90); print("小さい版", p)


if __name__ == "__main__":
    main(sys.argv[1], "--preview" in sys.argv)

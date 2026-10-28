# 千年こよみ サムネA（日付が主役。手順書 §7）→ 1280x720 の JPG と、横320pxの小さい版
#   python -X utf8 make_thumb_koyomi.py <作業フォルダ>/thumb.json
# thumb.json：{"bg": "images/F05.png", "lines": ["12/16", "天赦×万倍"], "out": "thumb_a.jpg"}
# ・左は朱色の地に白い文字（Noto Sans JP の900・墨の縁取り）、右に暦か神社の絵。文字は合わせて12字以内
# ・右下の再生時間の表示（右下 200x80px）には文字を置かない（文字は左の朱の地だけ）
import json, os, sys
from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H, SPLIT = 1280, 720, 640
SHU, WHITE, INK = (196, 62, 44), (255, 248, 236), (43, 38, 34)
VF = next(p for p in (r"C:\Windows\Fonts\NotoSansJP-VF.ttf",
                      os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Windows\Fonts\NotoSansJP-VF.ttf")) if os.path.exists(p))


def font(size):
    f = ImageFont.truetype(VF, size); f.set_variation_by_axes([900]); return f


def fit(text, maxw, start):
    s = start
    while font(s).getlength(text) > maxw and s > 60:
        s -= 4
    return s


def main(spec, preview=True):
    sp = json.load(open(spec, encoding="utf-8")); base = os.path.dirname(os.path.abspath(spec))
    n = sum(len(l.replace(" ", "")) for l in sp["lines"])
    if n > 12:
        raise SystemExit(f"【止まりました】文字が {n} 字です（12字以内。手順書 §7）")
    im = Image.new("RGB", (W, H), SHU)
    bg = Image.open(os.path.join(base, sp["bg"])).convert("RGB")
    rw = W - SPLIT + 120; r = max(rw / bg.width, H / bg.height)
    bg = bg.resize((int(bg.width * r + .5), int(bg.height * r + .5)))
    cx = int(bg.width * sp.get("focus_x", .5)) - rw // 2; cx = max(0, min(bg.width - rw, cx))
    bg = bg.crop((cx, (bg.height - H) // 2, cx + rw, (bg.height - H) // 2 + H))
    m = Image.new("L", (rw, H), 255); d = ImageDraw.Draw(m)
    for i in range(120):  # 朱の地へ、なめらかにつなぐ
        d.line((i, 0, i, H), fill=int(255 * i / 120))
    im.paste(bg, (SPLIT - 120, 0), m)
    d = ImageDraw.Draw(im)
    ys, gap = [], 18
    sizes = [fit(l, SPLIT - 90, 250 if i == 0 else 170) for i, l in enumerate(sp["lines"])]
    total = sum(sizes) + gap * (len(sizes) - 1); y = (H - total) // 2 - 10
    for l, s in zip(sp["lines"], sizes):
        f = font(s); x = 48
        sh = Image.new("L", (W, H), 0); ImageDraw.Draw(sh).text((x + 6, y + 8), l, font=f, fill=150, stroke_width=s // 12)
        im.paste(INK, (0, 0), sh.filter(ImageFilter.GaussianBlur(8)))
        d.text((x, y), l, font=f, fill=WHITE, stroke_width=max(6, s // 16), stroke_fill=INK, anchor="la")
        y += s + gap
    out = os.path.join(base, sp.get("out", "thumb_a.jpg")); im.save(out, quality=92); print("保存", out)
    if preview:
        p = out.replace(".jpg", "_small.jpg"); im.resize((320, 180), Image.LANCZOS).save(p, quality=90); print("小さい版", p)


if __name__ == "__main__":
    main(sys.argv[1])

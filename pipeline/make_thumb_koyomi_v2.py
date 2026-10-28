# 千年こよみ サムネ（競合の暦チャンネルの伸びた回の型）→ 1280x720 の JPG と、横320pxの小さい版
#   python -X utf8 make_thumb_koyomi_v2.py <作業フォルダ>/thumb_b.json
# 2026-10-27 新設。元の make_thumb_koyomi.py（サムネA：朱の地・12字以内）は残している。
# 理由：競合773本の実測（_research/spi_bench_2026-10-27）で、伸びた回は 明るい地・3行・約20字・赤い特大の字・人物あり。
#   いちばん近い競合（神秘の雑学書の伸びた49本）は、白地に金の枠／上に黒い1行（12〜15字）／特大の赤い動作の言葉／
#   左に日付のカレンダー札／人物が下。手順書 §7 のサムネA（12字以内・朱の地）とは違うので、A と並べて比べる案として作る。
# thumb_b.json：{"top": "次は210日後！最強開運日に", "big": "やること3つ", "cal": ["12月16日", "天赦×万倍"],
#               "tag": "借金はNG", "person": {"src": "images/C12.png", "box": [0, 120, 980, 1080]}, "out": "thumb_b.jpg"}
# ・右下の再生時間の表示（右下 200x80px）には文字を置かない（人物の絵だけ）
# ・文字は Noto Sans JP の900（手順書 §7）。特大の字は白い縁取り＋影
import json, os, sys
from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H = 1280, 720
WASHI, GOLD, GOLD2, INK, RED = (253, 250, 243), (196, 154, 60), (240, 226, 186), (34, 30, 28), (212, 36, 30)
VF = next(p for p in (r"C:\Windows\Fonts\NotoSansJP-VF.ttf",
                      os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Windows\Fonts\NotoSansJP-VF.ttf")) if os.path.exists(p))


def font(size):
    f = ImageFont.truetype(VF, size); f.set_variation_by_axes([900]); return f


def fit(text, maxw, start, low=40):
    s = start
    while font(s).getlength(text) > maxw and s > low:
        s -= 2
    return s


def shadow_text(im, xy, text, f, fill, stroke, stroke_fill, blur=6, off=(4, 6), anchor="la"):
    sh = Image.new("L", im.size, 0)
    ImageDraw.Draw(sh).text((xy[0] + off[0], xy[1] + off[1]), text, font=f, fill=120, stroke_width=stroke, anchor=anchor)
    im.paste((0, 0, 0), (0, 0), sh.filter(ImageFilter.GaussianBlur(blur)))
    ImageDraw.Draw(im).text(xy, text, font=f, fill=fill, stroke_width=stroke, stroke_fill=stroke_fill, anchor=anchor)


def calendar(im, x, y, w, lines):
    """日付のカレンダー札：赤い上帯に輪が2つ、白い紙に日付（墨）と吉日の名前（赤）"""
    h = int(w * 0.92); d = ImageDraw.Draw(im)
    sh = Image.new("L", im.size, 0); ImageDraw.Draw(sh).rounded_rectangle((x + 6, y + 8, x + w + 6, y + h + 8), 18, fill=110)
    im.paste((0, 0, 0), (0, 0), sh.filter(ImageFilter.GaussianBlur(7)))
    d.rounded_rectangle((x, y, x + w, y + h), 18, fill=(255, 255, 255), outline=(200, 200, 200), width=3)
    d.rounded_rectangle((x, y, x + w, y + int(h * 0.22)), 18, fill=RED)
    d.rectangle((x, y + int(h * 0.12), x + w, y + int(h * 0.22)), fill=RED)
    for cx in (x + w * 0.28, x + w * 0.72):
        d.rounded_rectangle((cx - 9, y - 16, cx + 9, y + 26), 9, fill=(90, 90, 90))
    s1 = fit(lines[0], w - 30, 88); f1 = font(s1)
    d.text((x + w / 2, y + h * 0.50), lines[0], font=f1, fill=INK, anchor="mm")
    if len(lines) > 1:
        s2 = fit(lines[1], w - 30, 52); d.text((x + w / 2, y + h * 0.78), lines[1], font=font(s2), fill=RED, anchor="mm")
    return h


def tag(im, x, y, text, maxw):
    s = fit(text, maxw - 40, 46); f = font(s); d = ImageDraw.Draw(im)
    tw = f.getlength(text)
    d.rounded_rectangle((x, y, x + tw + 40, y + s + 26), 12, fill=RED, outline=(255, 255, 255), width=4)
    d.text((x + 20, y + 10), text, font=f, fill=(255, 255, 255))


def person(im, base, p, area):
    """場面の絵から人物の所を切り出して、上と左を和紙の地へなめらかにつなぐ"""
    src = Image.open(os.path.join(base, p["src"])).convert("RGB")
    x0, y0, x1, y1 = p["box"]; crop = src.crop((x0, y0, x1, y1))
    ax0, ay0, ax1, ay1 = area; aw, ah = ax1 - ax0, ay1 - ay0
    r = max(aw / crop.width, ah / crop.height)
    crop = crop.resize((int(crop.width * r + .5), int(crop.height * r + .5)), Image.LANCZOS)
    cx = (crop.width - aw) // 2; crop = crop.crop((cx, 0, cx + aw, ah))
    m = Image.new("L", (aw, ah), 255); d = ImageDraw.Draw(m)
    fx, fy = int(aw * 0.18), int(ah * 0.10)
    for i in range(fx):
        d.line((i, 0, i, ah), fill=int(255 * (i / fx) ** 1.4))
    m2 = Image.new("L", (aw, ah), 255); d2 = ImageDraw.Draw(m2)
    for j in range(fy):
        d2.line((0, j, aw, j), fill=int(255 * (j / fy) ** 1.4))
    from PIL import ImageChops
    im.paste(crop, (ax0, ay0), ImageChops.multiply(m, m2))


def main(spec, preview=True):
    sp = json.load(open(spec, encoding="utf-8")); base = os.path.dirname(os.path.abspath(spec))
    im = Image.new("RGB", (W, H), WASHI); d = ImageDraw.Draw(im)
    # 下の段：人物（右）
    person(im, base, sp["person"], (400, 330, W - 14, H - 14))
    # 上の段：淡い金の帯に黒い1行
    d.rectangle((0, 0, W, 104), fill=GOLD2)
    s = fit(sp["top"], W - 80, 72); d.text((W / 2, 56), sp["top"], font=font(s), fill=INK, anchor="mm")
    # 特大の赤い字
    s = fit(sp["big"], W - 70, 200, 120); f = font(s)
    shadow_text(im, (W / 2, 112 + s * 0.56), sp["big"], f, RED, max(8, s // 14), (255, 255, 255), anchor="mm")
    # 左：カレンダー札と赤い札
    by = 112 + int(s * 1.12) + 10
    ch = calendar(im, 46, by + 18, 270, sp["cal"])
    if sp.get("tag"):
        tag(im, 40, by + 20 + ch + 22, sp["tag"], 380)
    # 金の枠
    d = ImageDraw.Draw(im)
    d.rectangle((0, 0, W - 1, H - 1), outline=GOLD, width=12)
    d.line((0, 104, W, 104), fill=GOLD, width=4)
    out = os.path.join(base, sp.get("out", "thumb_b.jpg")); im.save(out, quality=92); print("保存", out)
    if preview:
        p = out.replace(".jpg", "_small.jpg"); im.resize((320, 180), Image.LANCZOS).save(p, quality=90); print("小さい版", p)


if __name__ == "__main__":
    main(sys.argv[1])

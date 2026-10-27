# ⑩サムネ（心理学ch・2026-10-27 新設）：001 の v4a と同じ作り（手元の thumb_runs_v2.py＋thumb_work_v4\spec_v4a.json）
#   python -X utf8 pipeline\make_thumb_psy.py <作業フォルダ> [--bg THUMB] [--check]
# ・背景：images\<--bg>.png（script.json の thumb_bg。主役が右3分の1・左半分があいた絵）。色を濃くして（color 1.45・contrast 1.12・brightness 0.97）、左を少し暗くする
# ・文字：script.json の thumb.lines（[[["言葉", "#色"], ...], ...] の2〜3行）を、左に一番太い字（Noto Sans JP Black）・太い黒フチで置く。
#   3行の時は 001 と同じ位置と大きさ（1行目は小さく、2・3行目を大きく）。2行の時は2行とも大きく
# ・thumb.lines_b があれば、同じ背景で B案（thumb_b.jpg。公開の後に見張り watch.py が差し替える）も作る
# ・出力：thumb_a.jpg（1280x720）と、スマホで見る大きさの thumb_a_320.jpg
# ・--check：字数（11〜17字）・黄色の言葉が1つ・文字のある所の明るさ、と、横320pxに縮めた版を Gemini に読ませて文字が一致するかを見る
import argparse, json, os, sys, unicodedata
import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
W, H = 1280, 720
BLACK_VF = "C:/Windows/Fonts/NotoSansJP-VF.ttf"
BLACK_TTC = "/usr/share/fonts/opentype/noto/NotoSansCJK-Black.ttc"
YELLOW = "#FFE234"
GRADE = {"color": 1.45, "contrast": 1.12, "brightness": 0.97}
X, MAXW = 36, 810
LAYOUT = {3: [(28, 96), (165, 195), (395, 195)], 2: [(90, 195), (330, 195)], 1: [(240, 195)]}


def font(size):
    if os.path.exists(BLACK_VF):
        f = ImageFont.truetype(BLACK_VF, size)
        f.set_variation_by_axes([900])
        return f
    return ImageFont.truetype(BLACK_TTC, size)


def hexc(h):
    h = h.lstrip("#"); return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def shade(im, strength=60, reach=0.7):
    g = Image.new("L", (W, H), 0); d = ImageDraw.Draw(g)
    for i in range(W):
        d.line((i, 0, i, H), fill=int(strength * max(0, 1 - i / (W * reach))))
    im.paste((0, 0, 0), (0, 0, W, H), g)


def line(im, x, y, size, runs):
    while True:
        f = font(size)
        tw = sum(ImageDraw.Draw(im).textlength(t, font=f) for t, _ in runs)
        if x + tw <= MAXW or size <= 40:
            break
        size -= 4
    ow = max(6, size // 9)
    mask = Image.new("L", (W, H), 0); md = ImageDraw.Draw(mask)
    cx = x
    for t, _ in runs:
        md.text((cx, y), t, font=f, fill=255); cx += md.textlength(t, font=f)
    out = mask.filter(ImageFilter.MaxFilter(ow * 2 + 1))
    im.paste((0, 0, 0), (size // 24, size // 20, W + size // 24, H + size // 20), out.filter(ImageFilter.GaussianBlur(size // 12)).point(lambda v: int(v * 0.7)))
    im.paste((0, 0, 0), (0, 0, W, H), out)
    cx = x
    for t, col in runs:
        m = Image.new("L", (W, H), 0); ImageDraw.Draw(m).text((cx, y), t, font=f, fill=255)
        im.paste(hexc(col), (0, 0, W, H), m); cx += md.textlength(t, font=f)


def make(work, bg_id, lines, name):
    bg = Image.open(os.path.join(work, "images", bg_id + ".png")).convert("RGB")
    r = max(W / bg.width, H / bg.height)
    bg = bg.resize((int(bg.width * r + .5), int(bg.height * r + .5)))
    im = bg.crop(((bg.width - W) // 2, (bg.height - H) // 2, (bg.width - W) // 2 + W, (bg.height - H) // 2 + H))
    for k, fn in (("color", ImageEnhance.Color), ("contrast", ImageEnhance.Contrast), ("brightness", ImageEnhance.Brightness)):
        im = fn(im).enhance(GRADE[k])
    shade(im)
    for (y, size), runs in zip(LAYOUT[len(lines)], lines):
        line(im, X, y, size, runs)
    out = os.path.join(work, f"thumb_{name}.jpg")
    im.save(out, quality=92)
    im.resize((320, 180), Image.LANCZOS).save(out.replace(".jpg", "_320.jpg"), quality=90)
    print("保存", out)
    return out


def text_of(lines):
    return "".join(t for ln in lines for t, _ in ln)


def check(work, outs, texts):
    ok = True
    for o, (t, lines) in zip(outs, texts):
        n = len(t)
        yellow = sum(1 for ln in lines for _, c in ln if c.upper() == YELLOW)
        light = float(np.asarray(Image.open(o).convert("L").crop((0, 0, MAXW, H))).mean()) / 255
        print(os.path.basename(o), f"字数 {n}（11〜17）・黄色の言葉 {yellow}（1つ）・左の明るさ {light:.2f}")
        if not 11 <= n <= 17 or yellow != 1 or not 2 <= len(lines) <= 3:
            print("  【不合格】手順書 §6 のサムネの文字の決まり（2〜3行・11〜17字・黄色は1語）")
            ok = False
    import gemini
    sch = {"type": "object", "properties": {"読めた文字": {"type": "array", "items": {"type": "string"}}}, "required": ["読めた文字"]}
    r, _ = gemini.ask(f"添付の{len(outs)}枚は YouTube のサムネを横320pxに縮めた物です。それぞれ、大きい文字を、改行を詰めて上から1つの文字列で書いてください。読めない字は？にしてください。",
                      schema=sch, images=[o.replace(".jpg", "_320.jpg") for o in outs])
    norm = lambda s: unicodedata.normalize("NFKC", s).replace(" ", "")
    for o, g, (t, _) in zip(outs, json.loads(r)["読めた文字"], texts):
        same = norm(g) == norm(t)
        print(os.path.basename(o), "320pxで読めた：", g, "一致" if same else "【不一致】")
        ok = ok and same
    return ok


def main():
    a = argparse.ArgumentParser()
    a.add_argument("work")
    a.add_argument("--bg", default="")
    a.add_argument("--check", action="store_true")
    a = a.parse_args()
    s = json.load(open(os.path.join(a.work, "script.json"), encoding="utf-8"))
    th = s.get("thumb") or {}
    bg = a.bg or s.get("thumb_bg") or "THUMB"
    if not os.path.exists(os.path.join(a.work, "images", bg + ".png")):
        sys.exit(f"【止まりました】サムネの背景の絵がありません：images\\{bg}.png")
    if not th.get("lines") or len(th["lines"]) not in LAYOUT:
        sys.exit("【止まりました】script.json の thumb.lines が無いか、1〜3行ではありません")
    outs, texts = [make(a.work, bg, th["lines"], "a")], [(text_of(th["lines"]), th["lines"])]
    if th.get("lines_b") and len(th["lines_b"]) in LAYOUT:
        outs.append(make(a.work, bg, th["lines_b"], "b")); texts.append((text_of(th["lines_b"]), th["lines_b"]))
    if a.check:
        sys.exit(0 if check(a.work, outs, texts) else 1)


if __name__ == "__main__":
    main()

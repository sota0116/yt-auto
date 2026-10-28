# ⑩サムネ（心理学ch・2026-10-27 新設。2026-10-28 v2：2段・横幅いっぱい・光・点検。型の正本は skills\youtube-video-maker\references\15_サムネの型.md）
#   python -X utf8 pipeline\make_thumb_psy.py <作業フォルダ> [--bg THUMB] [--check]
# ・背景：images\<--bg>.png（script.json の thumb_bg）。主役（気持ちのはっきりした人）を真ん中の高さに置き、上と下をあけた絵（手順書 §5）。
#   色を濃くして、まわりを暗くし（主役のまわりだけ明るく残る）、上と下に暗い帯を足す
# ・文字：script.json の thumb.lines を2段に置く。上の段＝何の話か（横幅の6割以上）、下の段＝答え・ひっかかり（横幅の7割以上・いちばん大きい）。
#   1行＝下の段だけ、2行＝上・下、3行（前の版の形）＝2・3行目をつないで下の段にする。どの段も横幅に合わせて大きさを決める
#   [["言葉","#色"], ...] の色が黄 #FFE234 の語が「1語だけ色を変えた語」。下の段の外側に光。太い黒フチ（Noto Sans JP Black）
# ・thumb.lines_b があれば、同じ背景で B案（thumb_b.jpg。公開の後に見張り watch.py が差し替える）も作る
# ・出力：thumb_a.jpg（1280x720）と、スマホで見る大きさの thumb_a_320.jpg
# ・作ったあとに点検を出す（いちばん大きい字の横幅・上の段の横幅・字の面積・行数・色を変えた語・字のない中段）。--check は、さらに
#   字数（11〜17字）・黄色の言葉が1つ と、横320pxに縮めた版を Gemini に読ませて文字が一致するかを見る
import argparse, json, os, sys, unicodedata
import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
W, H = 1280, 720
BLACK_VF = "C:/Windows/Fonts/NotoSansJP-VF.ttf"
BLACK_TTC = "/usr/share/fonts/opentype/noto/NotoSansCJK-Black.ttc"
YELLOW = "#FFE234"
GLOW_LOWER = "#FFB02E"  # 下の段の外側の光（字が白と黄なので、温かい金色。赤にはしない）
GRADE = {"color": 1.45, "contrast": 1.12, "brightness": 0.97}
MARGIN = 40
MAXW = W - 2 * MARGIN
LOWER_CAP, UPPER_CAP = 230, 175
TOP, BOTTOM = 14, 18  # 字の上端・下端から画面のふちまで


def font(size):
    if os.path.exists(BLACK_VF):
        f = ImageFont.truetype(BLACK_VF, size)
        f.set_variation_by_axes([900])
        return f
    return ImageFont.truetype(BLACK_TTC, size)


def hexc(h):
    h = h.lstrip("#"); return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


_meas = ImageDraw.Draw(Image.new("L", (1, 1)))


def width(runs, size):
    f = font(size)
    return sum(_meas.textlength(t, font=f) for t, _ in runs)


def fit(runs, cap, limit=MAXW):
    """横幅 limit に収まる、cap 以下でいちばん大きい字の大きさ"""
    s = cap
    while s > 40 and width(runs, s) > limit:
        s -= 2
    return s


def stages(lines):
    """[[行]...] → (上の段, 下の段)。3行（前の版の形）は2・3行目をつなぐ"""
    if len(lines) == 1:
        return None, lines[0]
    if len(lines) == 2:
        return lines[0], lines[1]
    return lines[0], lines[1] + lines[2]


def vignette(im):
    """まわり（とくに上と下）を暗くして、まん中の主役を明るく残す"""
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    d = np.sqrt(((xx - W / 2) / (W * 0.62)) ** 2 + ((yy - H / 2) / (H * 0.62)) ** 2)
    a = np.clip((d - 0.45) / 0.75, 0, 1) ** 1.2 * 0.55  # まわりの暗さ（最大55%）
    band = np.clip(1 - yy / (H * 0.30), 0, 1) ** 1.3 * 0.50 + np.clip((yy - H * 0.68) / (H * 0.32), 0, 1) ** 1.3 * 0.55  # 字の下に敷く暗い帯
    k = 1 - np.clip(1 - (1 - a) * (1 - band), 0, 1)
    arr = np.asarray(im).astype(np.float32) * k[..., None]
    return Image.fromarray(arr.clip(0, 255).astype(np.uint8))


def draw_stage(im, runs, size, anchor, glow=None):
    """1段を横の真ん中にそろえて置く。anchor=("top", y) か ("bottom", y)（字の見えている上端／下端の位置）。点検用の数字を返す"""
    f = font(size)
    tw = width(runs, size)
    x0 = (W - tw) / 2
    dm = ImageDraw.Draw(Image.new("L", (1, 1)))
    bb = dm.textbbox((0, 0), "".join(t for t, _ in runs), font=f)
    y = anchor[1] - bb[1] if anchor[0] == "top" else anchor[1] - bb[3]
    mask = Image.new("L", (W, H), 0); md = ImageDraw.Draw(mask)
    cx = x0
    for t, _ in runs:
        md.text((cx, y), t, font=f, fill=255); cx += md.textlength(t, font=f)
    ow = max(6, size // 9)
    out = mask.filter(ImageFilter.MaxFilter(ow * 2 + 1))
    if glow:
        g = out.filter(ImageFilter.MaxFilter(9)).filter(ImageFilter.GaussianBlur(size // 6)).point(lambda v: min(255, int(v * 1.5)))
        im.paste(hexc(glow), (0, 0, W, H), g)
    im.paste((0, 0, 0), (size // 24, size // 20, W + size // 24, H + size // 20), out.filter(ImageFilter.GaussianBlur(size // 12)).point(lambda v: int(v * 0.7)))
    im.paste((0, 0, 0), (0, 0, W, H), out)
    cx = x0
    for t, col in runs:
        m = Image.new("L", (W, H), 0); ImageDraw.Draw(m).text((cx, y), t, font=f, fill=255)
        im.paste(hexc(col), (0, 0, W, H), m); cx += md.textlength(t, font=f)
    return {"size": size, "width": tw, "bbox": mask.getbbox(), "hl": [t for t, c in runs if c.upper() == YELLOW]}


def inspect(res):
    """15_サムネの型.md の点検（めやすは参考36枚を見て決めた推測を含む数字）。NG の一覧を返す。作った絵は NG があっても残す"""
    big = max(r["width"] for r in res) / W
    up = next((r["width"] / W for r in res if r["name"] == "上"), None)
    area = sum((r["bbox"][2] - r["bbox"][0]) * (r["bbox"][3] - r["bbox"][1]) for r in res) / (W * H)
    hl = [w for r in res for w in r["hl"]]
    up_bottom = next((r["bbox"][3] for r in res if r["name"] == "上"), 0)
    lo_top = next(r["bbox"][1] for r in res if r["name"] == "下")
    print(f"  点検：いちばん大きい字の横幅 {big:.0%}（70%以上）／上の段の横幅 " + (f"{up:.0%}" if up is not None else "なし") +
          f"（60%以上）／字の面積 約{area:.0%}（30〜60%）／行数 {len(res)}（4行まで）／色を変えた語 {hl}／字のない中段 y={up_bottom}〜{lo_top}（主役はここ）")
    ng = []
    if big < 0.70:
        ng.append("いちばん大きい字の横幅が70%未満")
    if up is not None and up < 0.60:
        ng.append("上の段の横幅が60%未満")
    if len(res) > 4:
        ng.append("行が4行を超えた")
    if not hl:
        ng.append("色を変えた語（黄）が無い")
    if not 0.30 <= area <= 0.60:
        print(f"  注意：字の面積 {area:.0%} がめやす（30〜60%）の外")
    for m in ng:
        print("  点検NG", m)
    return ng


def make(work, bg_id, lines, name):
    bg = Image.open(os.path.join(work, "images", bg_id + ".png")).convert("RGB")
    r = max(W / bg.width, H / bg.height)
    bg = bg.resize((int(bg.width * r + .5), int(bg.height * r + .5)))
    im = bg.crop(((bg.width - W) // 2, (bg.height - H) // 2, (bg.width - W) // 2 + W, (bg.height - H) // 2 + H))
    for k, fn in (("color", ImageEnhance.Color), ("contrast", ImageEnhance.Contrast), ("brightness", ImageEnhance.Brightness)):
        im = fn(im).enhance(GRADE[k])
    im = vignette(im)
    up, lo = stages(lines)
    ls = fit(lo, LOWER_CAP)
    res = []
    if up:
        s60 = fit(up, 400, limit=W * 0.62)  # 横幅6割になる大きさ（それより小さくしない）
        us = fit(up, max(min(UPPER_CAP, round(ls * 0.9)), s60))
        res.append({"name": "上", **draw_stage(im, up, us, ("top", TOP))})
    res.append({"name": "下", **draw_stage(im, lo, ls, ("bottom", H - BOTTOM), glow=GLOW_LOWER)})
    print(f"保存 thumb_{name}.jpg")
    ng = inspect(res)
    out = os.path.join(work, f"thumb_{name}.jpg")
    im.save(out, quality=92)
    im.resize((320, 180), Image.LANCZOS).save(out.replace(".jpg", "_320.jpg"), quality=90)
    return out, ng


def text_of(lines):
    return "".join(t for ln in lines for t, _ in ln)


def check(outs, texts, ngs):
    ok = not any(ngs)
    for o, (t, lines), ng in zip(outs, texts, ngs):
        n = len(t)
        yellow = sum(1 for ln in lines for _, c in ln if c.upper() == YELLOW)
        print(os.path.basename(o), f"字数 {n}（11〜17）・黄色の言葉 {yellow}（1つ）・点検NG {len(ng)}件")
        if not 11 <= n <= 17 or yellow != 1 or not 1 <= len(lines) <= 3:
            print("  【不合格】手順書 §6 のサムネの文字の決まり（2段・11〜17字・黄色は1語）")
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
    if not th.get("lines") or not 1 <= len(th["lines"]) <= 3:
        sys.exit("【止まりました】script.json の thumb.lines が無いか、1〜3行ではありません")
    outs, ngs = [], []
    texts = [(text_of(th["lines"]), th["lines"])]
    o, ng = make(a.work, bg, th["lines"], "a"); outs.append(o); ngs.append(ng)
    if th.get("lines_b") and 1 <= len(th["lines_b"]) <= 3:
        o, ng = make(a.work, bg, th["lines_b"], "b"); outs.append(o); ngs.append(ng)
        texts.append((text_of(th["lines_b"]), th["lines_b"]))
    if a.check:
        sys.exit(0 if check(outs, texts, ngs) else 1)


if __name__ == "__main__":
    main()

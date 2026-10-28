# 千年こよみ サムネ v3（暗い地に金と赤の光・字は2段・1語だけ色を変える）→ 1280x720 の JPG と、横320pxの小さい版
#   python -X utf8 make_thumb_koyomi_v3.py <作業フォルダ>/thumb_b.json [--out <出力の場所>]
# 2026-10-28 新設。v2（make_thumb_koyomi_v2.py：明るい和紙の地・上に帯・特大の赤い字・カレンダー札）は残している。
# 理由：本人の指摘「今のサムネは、よく言えばシンプル、悪く言うとインパクトやわかりやすさがない」。
#   参考チャンネル36枚の共通の型（skills/youtube-video-maker/references/15_サムネの型.md）の spi の行に合わせた。
#   1. 地を暗く沈め、主役にだけ光（金）。縁に赤い光。開運で明るい気持ちになる内容なので、黒一色にはせず「特別な日」の金の光にする
#   2. 字は2段：上＝何の話か（横幅6割以上）・下＝答え／ひっかかり（横幅7割以上）。1語だけ色を変える。字の外側に光
#   3. 人物の表情は絵の側で決める（絵を頼む時に入れる。手順書 §7）。この道具では表情は変えられない
#   4. 作ったあとに点検を出す（いちばん大きい字の横幅・字の面積・行数・色を変えた語・右下の再生時間の所）
# thumb.json：{"bg": "images/C12.png", "box": [230, 170, 1620, 788]（任意。絵の使う範囲）, "focus": [0.35, 0.45]（任意。光を当てる所・画面の割合）,
#              "top": "天赦日と一粒万倍日", "big": "年に数回だけ", "hl": ["数回"], "hl_color": "#FFC83D"（任意。朱にするなら "#FF3A2A"）,
#              "tag": "次は12/16（水）"（任意。左下の小さい札）, "cal": ["12/16", "天赦×万倍"]（任意。左の小さい札。基本は付けない）,
#              "dark": 0.34（任意。地の暗さ。小さいほど暗い）, "out": "thumb_b.jpg"}
#   v2 の thumb_b.json（"person": {"src", "box"}, "cal", "tag"）もそのまま読める（person は bg と box として読む）。
# ・右下の再生時間の表示（右下 200x80px）には文字を置かない（道具が重なりを点検する）
# ・文字は Noto Sans JP の900（手順書 §7）に黒い縁取り。字数のめやす：上の段12字まで・下の段8字まで（サムネA・型D は §7 の12字以内のまま）
import json, os, random, sys
from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageFont

W, H = 1280, 720
GOLD, GOLD_T, CREAM, INK = (196, 154, 60), (242, 193, 78), (255, 246, 226), (22, 17, 26)
RED_GLOW, GOLD_GLOW = (226, 48, 30), (222, 162, 48)
HL_GOLD = "#FFC83D"
VF = next(p for p in (r"C:\Windows\Fonts\NotoSansJP-VF.ttf",
                      os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Windows\Fonts\NotoSansJP-VF.ttf")) if os.path.exists(p))
PLAY_BOX = (W - 200, H - 80, W, H)  # 右下の再生時間の表示


def font(size):
    f = ImageFont.truetype(VF, size); f.set_variation_by_axes([900]); return f


def hexrgb(c):
    c = c.lstrip("#"); return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def fit_size(text, target_w, cap, low=44):
    s = cap
    while font(s).getlength(text) > target_w and s > low:
        s -= 2
    return s


def cover(src, box, focus_x):
    """絵を 1280x720 いっぱいに（はみ出す分は切る）"""
    if box: src = src.crop(tuple(box))
    r = max(W / src.width, H / src.height)
    src = src.resize((int(src.width * r + .5), int(src.height * r + .5)), Image.LANCZOS)
    cx = int(src.width * focus_x) - W // 2; cx = max(0, min(src.width - W, cx))
    cy = (src.height - H) // 2
    return src.crop((cx, cy, cx + W, cy + H))


def radial(cx, cy, rx, ry, power=1.0):
    """中心が255・外が0 のなめらかな楕円の光"""
    g = ImageChops.invert(Image.radial_gradient("L")).resize((int(rx * 2), int(ry * 2)), Image.BICUBIC)
    g = g.point(lambda v: int(255 * (v / 255) ** power))
    m = Image.new("L", (W, H), 0); m.paste(g, (int(cx - rx), int(cy - ry))); return m


def grade(im, bright, sat, tint=None, amt=0.0):
    o = ImageEnhance.Color(ImageEnhance.Brightness(im).enhance(bright)).enhance(sat)
    return Image.blend(o, Image.new("RGB", im.size, tint), amt) if tint else o


def background(im, focus, dark):
    """暗く沈め、主役にだけ光。金の光を主役の後ろに、赤い光を縁に"""
    fx, fy = focus[0] * W, focus[1] * H
    dim = grade(im, dark, 0.72, (30, 20, 44), 0.30)          # 暗い地（夜の藍がかった墨）
    lit = ImageEnhance.Contrast(grade(im, 0.80, 1.15, (255, 170, 90), 0.12)).enhance(1.3)       # 主役のあたり（暖かい光）
    spot = radial(fx, fy, W * 0.36, H * 0.62, 1.15)
    out = Image.composite(lit, dim, spot)
    gold = radial(fx, fy - H * 0.04, W * 0.30, H * 0.50, 1.6).point(lambda v: int(v * 0.42))
    out = ImageChops.screen(out, Image.composite(Image.new("RGB", (W, H), (236, 176, 64)), Image.new("RGB", (W, H), 0), gold))
    edge = ImageChops.invert(radial(W / 2, H / 2, W * 0.62, H * 0.78, 1.0)).point(lambda v: int(v * 0.40))
    out = ImageChops.screen(out, Image.composite(Image.new("RGB", (W, H), (176, 22, 18)), Image.new("RGB", (W, H), 0), edge))
    # 金の粒（上の半分に。字の読みやすさのため小さく控えめに）
    rnd = random.Random(7); sp = Image.new("L", (W, H), 0); d = ImageDraw.Draw(sp)
    for _ in range(46):
        x, y, r = rnd.randint(30, W - 30), rnd.randint(30, int(H * 0.62)), rnd.choice((2, 2, 3, 4, 6))
        d.ellipse((x - r, y - r, x + r, y + r), fill=rnd.randint(110, 230))
    sp = sp.filter(ImageFilter.GaussianBlur(1.6)).point(lambda v: int(v * 0.55))
    out = ImageChops.screen(out, Image.composite(Image.new("RGB", (W, H), (255, 214, 120)), Image.new("RGB", (W, H), 0), sp))
    return out


def shade(im):
    """上と下を暗くして、2段の字を浮かせる（顔にかからない上下をあける）"""
    g = Image.new("L", (W, H), 0); d = ImageDraw.Draw(g)
    for i in range(H):
        a = max(int(200 * max(0, 1 - i / (H * 0.26))), int(235 * max(0, 1 - (H - 1 - i) / (H * 0.52))) if i > H * 0.40 else 0)
        d.line((0, i, W, i), fill=a)
    im.paste((0, 0, 0), (0, 0, W, H), g)


def gradient(cols):
    g = Image.new("RGB", (1, H))
    for y in range(H):
        t = y / (H - 1); a, b, u = (cols[0], cols[1], t * 2) if t < 0.5 else (cols[1], cols[2], (t - 0.5) * 2)
        g.putpixel((0, y), tuple(int(a[k] + (b[k] - a[k]) * u) for k in range(3)))
    return g.resize((W, H))


def draw_row(im, text, f, s, ink_top=None, ink_bottom=None, color=CREAM, hl=(), hl_color=HL_GOLD, glow=RED_GLOW, glow_k=1.5):
    """1行を横の真ん中に。ink_top か ink_bottom で縦の位置（字の見える端）を決める。点検用の結果を返す"""
    meas = ImageDraw.Draw(Image.new("L", (1, 1)))
    l, t, r, b = meas.textbbox((0, 0), text, font=f, anchor="la")
    x = (W - meas.textlength(text, font=f)) / 2
    y = ink_top - t if ink_top is not None else ink_bottom - b
    mask = Image.new("L", (W, H), 0); ImageDraw.Draw(mask).text((x, y), text, font=f, fill=255)
    hmask = Image.new("L", (W, H), 0); hd = ImageDraw.Draw(hmask); nhl = 0
    for w in hl:
        i = text.find(w)
        while i >= 0:
            hd.text((x + meas.textlength(text[:i], font=f), y), w, font=f, fill=255); nhl += 1
            i = text.find(w, i + len(w))
    ow = max(6, s // 11)
    outline = Image.new("L", (W, H), 0); ImageDraw.Draw(outline).text((x, y), text, font=f, fill=255, stroke_width=ow)
    if glow:  # 黒い縁の外側に色の光
        gl = outline.filter(ImageFilter.MaxFilter(5)).filter(ImageFilter.GaussianBlur(max(8, s // 6)))
        im.paste(glow, (0, 0, W, H), gl.point(lambda v: min(255, int(v * glow_k))))
    im.paste((0, 0, 0), (s // 22, s // 18, W + s // 22, H + s // 18), outline.filter(ImageFilter.GaussianBlur(s // 14)).point(lambda v: int(v * 0.8)))
    im.paste((0, 0, 0), (0, 0, W, H), outline)
    im.paste(gradient([CREAM, CREAM, (238, 226, 196)]) if color == CREAM else Image.new("RGB", (W, H), color), (0, 0), mask)
    if nhl:
        im.paste(gradient([(255, 226, 120), hexrgb(hl_color), tuple(int(c * 0.86) for c in hexrgb(hl_color))]), (0, 0), hmask)
    return {"size": s, "width": meas.textlength(text, font=f), "bbox": mask.getbbox(), "hl": nhl, "mask": mask, "text": text}


def plate(im, x, y, lines, sizes, colors):
    """暗い地に金の縁の小さい札（日付など）"""
    d = ImageDraw.Draw(im); fs = [font(s) for s in sizes]
    wd = max(f.getlength(t) for f, t in zip(fs, lines)); h = sum(sizes) + 14 * (len(lines) - 1) + 28
    box = (x, y, x + int(wd) + 44, y + h)
    sh = Image.new("L", (W, H), 0); ImageDraw.Draw(sh).rounded_rectangle((box[0] + 5, box[1] + 7, box[2] + 5, box[3] + 7), 14, fill=130)
    im.paste((0, 0, 0), (0, 0), sh.filter(ImageFilter.GaussianBlur(6)))
    d.rounded_rectangle(box, 14, fill=(20, 14, 22), outline=GOLD_T, width=3)
    yy = y + 14
    for t, f, s, c in zip(lines, fs, sizes, colors):
        d.text((box[0] + 22, yy - f.getbbox(t, anchor="la")[1] + 2), t, font=f, fill=c); yy += s + 14
    return box


def check(rows, nchars):
    """15_サムネの型.md の点検（めやすは参考36枚を見て決めた推測を含む数字）。NG があっても絵は保存する"""
    ng = []; top, big = rows[0], rows[-1]
    ratio_big = big["width"] / W; ratio_top = top["width"] / W if len(rows) > 1 else None
    biggest = max(r["width"] for r in rows) / W
    area = sum((r["bbox"][2] - r["bbox"][0]) * (r["bbox"][3] - r["bbox"][1]) for r in rows if r["bbox"]) / (W * H)
    nhl = sum(r["hl"] for r in rows)
    print(f"点検：いちばん大きい字の横幅 {biggest:.0%}（めやす70%以上）／下の段 {ratio_big:.0%}（70%以上）"
          + (f"／上の段 {ratio_top:.0%}（60%以上）" if ratio_top is not None else "")
          + f"／字の面積 約{area:.0%}（30〜60%）／行数 {len(rows)}（4行まで）／色を変えた語 {nhl}（1〜2）／字数 {nchars}")
    if biggest < 0.70: ng.append("いちばん大きい字が細い。答えの語を横幅いっぱい（70%以上）にする（字数が少なすぎる時は語を足す）")
    if ratio_big < 0.70: ng.append(f"下の段の横幅が {ratio_big:.0%}。70%以上にする")
    if ratio_top is not None and ratio_top < 0.60: ng.append(f"上の段の横幅が {ratio_top:.0%}。60%以上にする（字数を増やすか短い見出しをやめる）")
    if area < 0.30: ng.append("字が少なすぎて目に入らない（面積30%未満）")
    if area > 0.60: ng.append("字が絵をつぶしている（面積60%超）")
    if len(rows) > 4: ng.append("行が多い。2段にまとめる")
    if nhl < 1: ng.append("色を変えた語が無い。いちばん強い1語に hl を付ける")
    if nhl > 2: ng.append("色を変えた語が3つ以上。1〜2語にする")
    for r in rows:
        if r["mask"].crop(PLAY_BOX).getbbox(): ng.append(f"「{r['text']}」が右下の再生時間の表示（200x80）に重なる")
    for m in ng: print("  NG", m)
    if not ng: print("  点検 NG 0件")
    return ng


def main(spec, out_dir=None, preview=True):
    sp = json.load(open(spec, encoding="utf-8")); base = os.path.dirname(os.path.abspath(spec))
    p = sp.get("person") or {}
    src = Image.open(os.path.join(base, sp.get("bg") or p["src"])).convert("RGB")
    focus = sp.get("focus") or [0.5, 0.46]
    im = cover(src, sp.get("box") or p.get("box"), focus[0])
    im = background(im, focus, sp.get("dark", 0.34))
    shade(im)
    hl, hlc = sp.get("hl") or [], sp.get("hl_color", HL_GOLD)
    rows = []
    # 上の段（何の話か）：横幅6割以上を目指し、できるだけ大きく
    top = sp.get("top")
    if top:
        s = fit_size(top, (W - 60) * 0.90, 112)
        rows.append(draw_row(im, top, font(s), s, ink_top=26, hl=hl, glow=GOLD_GLOW, glow_k=1.1, hl_color=hlc))
    # 下の段（答え・ひっかかり）：横幅7割以上。再生時間の表示（右下）に掛からない高さ
    big = sp["big"]
    s = fit_size(big, (W - 50) * 0.94, 250, 120)
    rows.append(draw_row(im, big, font(s), s, ink_bottom=sp.get("big_bottom", 598), hl=hl, glow=RED_GLOW, glow_k=1.7, hl_color=hlc))
    if sp.get("cal"):
        t = sp["cal"]; plate(im, 34, 150, t, [64, 36][:len(t)], [GOLD_T, CREAM][:len(t)])
    if sp.get("tag"):
        s = fit_size(sp["tag"], 520, 38, 28); plate(im, 34, H - 26 - s - 28 - 14, [sp["tag"]], [s], [GOLD_T])
    d = ImageDraw.Draw(im); d.rectangle((0, 0, W - 1, H - 1), outline=GOLD, width=8)
    out = sp.get("out", "thumb_b.jpg")
    out = os.path.join(out_dir, os.path.basename(out)) if out_dir else os.path.join(base, out)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    im.save(out, quality=92); print("保存", out)
    nchars = sum(len(r["text"]) for r in rows)
    ng = check(rows, nchars)
    if preview:
        pth = out.replace(".jpg", "_small.jpg"); im.resize((320, 180), Image.LANCZOS).save(pth, quality=90); print("小さい版", pth)
    return out, ng


if __name__ == "__main__":
    od = sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv else None
    main(sys.argv[1], od)

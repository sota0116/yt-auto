# ⑩サムネ（手順書 §6。2026-10-27 から：本人「横動画のサムネ全然だめ」→ 競合の伸びている回のサムネの型に寄せた）
#   python -X utf8 pipeline\make_thumb_job.py <作業フォルダ> [--bg D20] [--check]
# ・2つの形を作る。a案＝その回の主な形、b案＝もう1つの形（公開72時間の再生がほかの回より少ない時に watch.py が差し替える）
#   場面（型A・B・C の a案）：人物が写る場面の絵を全面に。上に白い帯と赤い見出し（thumb_top）、下に特大の字（thumb_text。強調の部分を黄で特大）
#   判定（型D の a案）：左の黒地に答えを伏せた1文（thumb_text。強調の行を赤）、右に人物の絵（型D は1位の箱）、左上に札（thumb_top）、下の帯（thumb_band）
# ・絵は台本の thumb_bg（人物が大きく写るカット）。--bg で替えられる。絵が無ければ止める
# ・字：thumb_top 16字以内・thumb_text 10字以内（割り方は thumb_lines）・thumb_band 28字以内。「AI」「PR」は入れない。数字は facts.json にある物だけ（check_job_script と同じ照らし方）
# ・1位の箱：型D だけ（タイトルで1位を言う回はその名前、伏せる回は「1位は？」。check_job_script.d_top_label）
#   ほかの型には箱を出さない（2026-10-28 本人「謎の？マークは何？必要？」。thumb_text がもう問いの形で、中身の無い「？」だけの箱は意味が伝わらない。
#   台本の thumb_q は読まない）
# ・右下の再生時間の表示の所（x>1090, y>630）には字を置かない
# ・--check：横320pxに縮めた版を Gemini に読ませ、いちばん大きい字が thumb_text と一致するかを見る（手順書 §10 サムネの点検）
# ・前の形（紺の地の棒グラフ・黄の地のサムネA）は git の 3745ed1 までの版
import argparse, json, os, re, sys, unicodedata
from PIL import Image, ImageDraw, ImageEnhance
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from make_charts_job import font, tw

W, H = 1280, 720
BLACK, WHITE = (10, 10, 16), (255, 255, 255)
RED, YEL = (226, 32, 40), (255, 214, 0)
SAFE = (1090, 630)  # 右下の再生時間の表示の所
N = lambda s: unicodedata.normalize("NFKC", s or "")


def say(d, xy, s, size, fill, stroke=BLACK, sw=None, anchor="la"):
    d.text(xy, s, font=font(size), fill=fill, stroke_width=sw if sw is not None else max(6, size // 9), stroke_fill=stroke, anchor=anchor)


def fit(s, size, maxw, low=40):
    while tw(s, size) > maxw and size > low:
        size -= 4
    return size


def cover(p, w, h, fx=0.5):
    """絵を w×h に切り抜く（fx は横の切り出し位置。0.5＝真ん中）"""
    im = Image.open(p).convert("RGB")
    r = max(w / im.width, h / im.height)
    im = im.resize((int(im.width * r + .5), int(im.height * r + .5)), Image.LANCZOS)
    x0 = int((im.width - w) * fx)
    y0 = (im.height - h) // 2
    return im.crop((x0, y0, x0 + w, y0 + h))


def shade(im, box, top_a, bottom_a):
    """box の中を上から下へ黒く（字を読みやすく）"""
    x0, y0, x1, y1 = box
    g = Image.new("RGBA", (x1 - x0, y1 - y0))
    gd = ImageDraw.Draw(g)
    for i in range(y1 - y0):
        gd.line([(0, i), (x1 - x0, i)], fill=(0, 0, 0, int(top_a + (bottom_a - top_a) * i / (y1 - y0))))
    im.paste(g, (x0, y0), g)


def qbox(d, box, label="1位は？"):
    x0, y0, x1, y1 = box
    d.rectangle(box, fill=BLACK, outline=RED, width=8)
    if label == "1位は？":  # 伏せた1位（何が伏せてあるかを箱の上の字で言う）
        say(d, ((x0 + x1) // 2, y0 + 38), "1位は", fit("1位は", 48, x1 - x0 - 24, 24), WHITE, BLACK, 3, "mm")
        say(d, ((x0 + x1) // 2, (y0 + y1) // 2 + 24), "？", int((y1 - y0) * .5), RED, BLACK, 2, "mm")
    else:  # 型D でタイトルが1位を言う回は、その名前を出す
        say(d, ((x0 + x1) // 2, (y0 + y1) // 2), label, fit(label, 56, x1 - x0 - 24, 24), YEL, BLACK, 4, "mm")


def parts(t, given, most=2):
    """thumb_text の割り方。given（thumb_lines）があればそれ。無ければ数字の所か最後の2〜3字を強調の部分にする。強調する番号も返す"""
    if given:
        given = [N(x) for x in given]  # thumb_text と同じく全角・半角をそろえて照らす（「？」と「?」で止まった。2026-10-26）
        if "".join(given) != t or len(given) > most:
            sys.exit(f"【止まりました】thumb_lines は{most}つまでで、つなぐと thumb_text になる並び：{given}／{t}")
        lines = list(given)
    else:
        m = re.search(r"\d", t)
        if m and m.start() > 0:
            lines = [t[:m.start()], t[m.start():]]
        elif len(t) <= 4:
            lines = [t]
        else:
            k = 3 if t.endswith("?") else 2
            lines = [t[:-k], t[-k:]]
    hi = next((i for i, x in enumerate(lines) if re.search(r"\d", x)), len(lines) - 1)
    if len(lines) == 3 and not re.search(r"\d", "".join(lines)):
        hi = 1  # 3行で数字が無い時は真ん中（競合の「黒幕は／すぐ隣／にいた」）
    return lines, hi


def scene(s, bgp, box_label):
    """場面：絵を全面＋上の帯（赤い見出し）＋下の特大の字"""
    im = ImageEnhance.Brightness(cover(bgp, W, H)).enhance(0.92)
    d = ImageDraw.Draw(im)
    top = N(s.get("thumb_top"))
    if top:
        d.rectangle((0, 0, W, 122), fill=WHITE)
        say(d, (W // 2, 63), top, fit(top, 92, W - 60), RED, WHITE, 4, "mm")
    shade(im, (0, H - 300, W, H), 0, 215)
    d = ImageDraw.Draw(im)
    lines, hi = parts(N(s["thumb_text"]), s.get("thumb_lines"), 2)
    size = [190 if i == hi else 120 for i in range(len(lines))]
    maxw = SAFE[0] - 50  # 下の段は再生時間の表示の所に掛けない
    if sum(tw(x, z) for x, z in zip(lines, size)) + 30 * (len(lines) - 1) <= maxw:  # 1行に並べる
        x = 40
        for i, (t, z) in enumerate(zip(lines, size)):
            say(d, (x, H - 30), t, z, YEL if i == hi else WHITE, anchor="ls")
            x += int(tw(t, z)) + 30
    else:  # 2行：普通の部分の下に強調の部分
        y = H - 30
        for i in reversed(range(len(lines))):
            z = fit(lines[i], size[i] if i == hi else 110, maxw)
            say(d, (40, y), lines[i], z, YEL if i == hi else WHITE, anchor="ls")
            y -= int(z * 1.08)
    if box_label:
        qbox(d, (1030, 170, 1240, 380), box_label)
    return im


def verdict(s, bgp, box_label):
    """判定：左の黒地に答えを伏せた1文、右に人物の絵と「？」の箱、左上の札、下の帯"""
    im = Image.new("RGB", (W, H), BLACK)
    im.paste(cover(bgp, 660, 620, 0.62), (620, 0))
    fade = Image.new("L", (220, 620))
    fd = ImageDraw.Draw(fade)
    for i in range(220):
        fd.line([(i, 0), (i, 620)], fill=int(255 * (1 - i / 220)))
    im.paste(Image.new("RGB", (220, 620), BLACK), (620, 0), fade)
    d = ImageDraw.Draw(im)
    top = N(s.get("thumb_top"))
    if top:  # 札：頭の数字（30年 など）を赤い箱に、残りを白い箱に
        m = re.match(r"([\d,.]+(?:万円|円|%|時間|年|歳|位|倍|割|人|日|分)?)\s*(.+)", top)
        num, rest = (m.group(1), m.group(2)) if m else ("", top)
        x = 40
        if num:
            w = int(tw(num, 42)) + 28
            d.rectangle((x, 36, x + w, 100), fill=RED)
            say(d, (x + w // 2, 68), num, 42, WHITE, sw=0, anchor="mm")
            x += w
        z = fit(rest, 38, 580 - x, 24)
        w = int(tw(rest, z)) + 28
        d.rectangle((x, 36, x + w, 100), fill=WHITE)
        d.text((x + w // 2, 68), rest, font=font(z), fill=BLACK, anchor="mm")
    lines, hi = parts(N(s["thumb_text"]), s.get("thumb_lines"), 3)
    zs = [fit(t, 160 if i == hi else 128, 570) for i, t in enumerate(lines)]
    y = 130 + max(0, (480 - sum(int(z * 1.12) for z in zs)) // 2)
    for i, (t, z) in enumerate(zip(lines, zs)):
        y += z
        if i == hi:
            say(d, (40, y), t, z, RED, WHITE, max(5, z // 22), "ls")
        else:
            say(d, (40, y), t, z, WHITE, anchor="ls")
        y += int(z * 0.12)
    if box_label:
        qbox(d, (1060, 390, 1250, 600), box_label)  # 顔は絵の上半分に来るので帯の上の右下（右上だと 2026-10-27 陽子の頬・004 の介護職員の顔にかかった）
    d.rectangle((0, 620, W, H), fill=(30, 30, 36))
    band = N(s.get("thumb_band"))
    if band:
        say(d, (40, 670), band, fit(band, 52, SAFE[0] - 60, 30), YEL, BLACK, 3, "lm")
    return im


def rules(s, f):
    """字の決まり（手順書 §6）。破ったら止める（check_job_script.py でも同じ所を見る）"""
    top, t, band = N(s.get("thumb_top")), N(s.get("thumb_text")), N(s.get("thumb_band"))
    ng = []
    if not t or len(t) > 10:
        ng.append(f"thumb_text は1〜10字：{t}")
    if len(top) > 16:
        ng.append(f"thumb_top は16字以内：{top}")
    if not band or len(band) > 28:
        ng.append(f"thumb_band は1〜28字：{band}")
    allt = top + t + band
    if re.search(r"AI|PR", allt.upper()):
        ng.append(f"サムネの字に「AI」か「PR」：{allt}")
    if "離職率" in allt and not re.search(r"(含む|業)の?離職率", allt):
        ng.append(f"サムネの離職率に業界名（〇〇業の）が無い：{allt}")
    if "逆転" in allt and not f.get("逆転を使える"):
        ng.append("サムネに「逆転」があるのに、facts.json に入れ替わりの記録（逆転を使える）が無い")
    if s.get("type") == "D" and "意外" in allt and not f.get("意外なを使える"):
        ng.append("サムネに「意外」があるのに、この回は使えない（1位が予想どおりか同点。facts.json の 意外なを使える）")
    from check_job_script import tokens, allowed_from
    ok = allowed_from(f)
    for x in (top, t, band):
        ng += [f"サムネに facts.json にない数字：{x} {k}" for k in tokens(x) if k not in ok]
    if ng:
        sys.exit("【止まりました】" + "／".join(ng))


def box_of(s, f, layout):
    if s.get("type") == "D":
        from check_job_script import d_top_label
        labels = d_top_label(s.get("titles", []), f)
        if labels is None:
            sys.exit("【止まりました】タイトル3案で1位の名前を出す案と伏せる案が混ざっている（サムネの「？」の箱を決められない）")
        return "1位は？" if labels[0] == "？" else "・".join(labels)
    return None


def make(work, variant, bg_id=None):
    s = json.load(open(os.path.join(work, "script.json"), encoding="utf-8"))
    f = json.load(open(os.path.join(work, "facts.json"), encoding="utf-8"))
    rules(s, f)
    bg_id = bg_id or s.get("thumb_bg")
    bgp = os.path.join(work, "images", f"{bg_id}.png")
    if not bg_id or not os.path.exists(bgp):
        sys.exit(f"【止まりました】サムネの絵（thumb_bg：{bg_id}）が images に無い")
    main_layout = "verdict" if s.get("type") == "D" else "scene"
    layout = main_layout if variant == "a" else {"scene": "verdict", "verdict": "scene"}[main_layout]
    im = (scene if layout == "scene" else verdict)(s, bgp, box_of(s, f, layout))
    out = os.path.join(work, f"thumb_{variant}.jpg")
    im.save(out, quality=92)
    im.resize((320, 180), Image.LANCZOS).save(out.replace(".jpg", "_320.jpg"), quality=90)
    return out


def check(work, outs, t):
    import gemini
    sch = {"type": "object", "properties": {"読めた文字": {"type": "array", "items": {"type": "string"}}}, "required": ["読めた文字"]}
    r, u = gemini.ask("添付の2枚は YouTube のサムネを横320pxに縮めた物です。それぞれ、いちばん大きい字の見出し（上の白い帯・左上の札・下の帯・箱の中の字は除く）を、改行を詰めて1つの文字列で書いてください。読めない字は？にしてください。",
                      schema=sch, images=[o.replace(".jpg", "_320.jpg") for o in outs])
    got = json.loads(r)["読めた文字"]
    t = N(t)  # 読めた文字も thumb_text も全角・半角をそろえて照らす（「？」と「?」で006が3回目も止まった。2026-10-26）
    same = lambda g: N(g).replace(" ", "") == t
    for o, g in zip(outs, got):
        print(os.path.basename(o), "320pxで読めた：", g, "一致" if same(g) else "【不一致】")
    return all(same(g) for g in got)


def main():
    a = argparse.ArgumentParser()
    a.add_argument("work")
    a.add_argument("--bg", default="")
    a.add_argument("--check", action="store_true")
    a = a.parse_args()
    outs = [make(a.work, v, a.bg or None) for v in ("a", "b")]
    for o in outs:
        print("保存", o)
    if a.check:
        t = json.load(open(os.path.join(a.work, "script.json"), encoding="utf-8"))["thumb_text"]
        sys.exit(0 if check(a.work, outs, t) else 1)


if __name__ == "__main__":
    main()

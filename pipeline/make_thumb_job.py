# ⑩サムネ（手順書 §6 サムネA-4）：facts.json の順位から、サムネを2案（a＝図だけ／b＝場面の絵＋図）作る
#   python -X utf8 pipeline\make_thumb_job.py <作業フォルダ> [--bg D20] [--check]
# ・人は描かない。年収の順の棒3本（サムネの文字が指す職業を黄）と、時給の順位への矢印をプログラムが描く。文字の順位は facts.json と照らす
# ・文字は script.json の thumb_text（12字以内・数字を1つ）。Noto Sans JP の900に黒い縁取り。強調の1行だけ黄で特大
# ・競合のフルAIチャンネルの型（左に3行の大きな文字・真ん中か最後の行だけ色を変えて特大・右に題材）に合わせた（設計\競合分析 の「サムネ」の節）
# ・右下の再生時間の表示の所（x>1090, y>630）には何も置かない
# ・--check：横320pxに縮めた版を Gemini に読ませ、文字が元と一致するかを見る（手順書 §10 サムネの点検）
# ・型D（script.json の type が D）はサムネD：facts.json の点のグラフから説の棒を3〜5本。1位は黄、ほかは灰。
#   1位の棒の名前は、タイトルで1位を言う回はその名前、伏せる回は「？」（check_job_script.d_top_label）。点数の数字は出さない
#   文字は数字のある行を黄で特大。行の割り方を変えたい時は script.json に thumb_lines（つなぐと thumb_text になる並び）
# ・A-1・A-3 はサムネA：黄の地に黒い文字（12字以内・2行まで・数字の行を大きい黒の太字。赤は使わない）。左は a案＝棒2本の図、b案＝thumb_bg の絵
# ・型B・C はサムネB：thumb_bg（主役の表情が大きい絵）を背景に、文字は8字以内。a案＝絵を全面、b案＝紺の地の右に絵
import argparse, json, os, re, sys, unicodedata
from PIL import Image, ImageDraw, ImageFilter
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from make_charts_job import font, tw, NAVY, PANEL, KINARI, MUTED, DIM, YELLOW, GREY

W, H = 1280, 720
BLACK = (8, 12, 22)
SAFE = (1090, 630)  # 右下の再生時間の表示の所


def short(name):
    m = re.search(r"（(.+?)）", name)
    return m.group(1) if m else name


def lines_of(t):
    """「年収1位が時給最下位」→ ["年収1位が", "時給", "最下位"]（最後の行を強調）"""
    m = re.match(r"(.+?[がは])(.+)", t)
    head, rest = (m.group(1), m.group(2)) if m else ("", t)
    e = re.search(r"(\d+位|最下位|最上位)$", rest)  # 強調は順位の言葉（「時給1位」を「時」「給1位」に割らない）
    if e and e.start() > 0:
        return [x for x in (head, rest[:e.start()], rest[e.start():]) if x]
    if len(rest) > 3:
        return [x for x in (head, rest[:-3], rest[-3:]) if x]
    return [x for x in (head, rest) if x]


def outlined(d, xy, s, size, fill, sw=None):
    d.text(xy, s, font=font(size), fill=fill, stroke_width=sw or max(6, size // 14), stroke_fill=BLACK)


def headline(im, lines, x, y, maxw, hi=None):
    d = ImageDraw.Draw(im)
    hi = len(lines) - 1 if hi is None else hi  # 強調する行（A-4 は最後の行）
    for i, s in enumerate(lines):
        last = i == hi
        size = 200 if last else 112
        while tw(s, size) > maxw and size > 60:
            size -= 4
        outlined(d, (x, y), s, size, YELLOW if last else KINARI)
        y += int(size * 1.12)
    return y


def focus(f, t):
    """サムネの文字（例：年収1位が時給最下位／年収3位が時給1位）が指す職業の年収の順位。文字の順位が facts.json と合わなければ止める"""
    order = f["順位"]["年収"]
    m = re.search(r"年収(\d+)位が時給(\d+|最下)位", t)
    if not m:
        print("【メモ】サムネの文字から職業を決められないので、年収1位を強調します")
        return 1
    n = int(m.group(1))
    if not 1 <= n <= len(order):
        sys.exit(f"【止まりました】サムネの文字の年収{n}位が、この回の職業の数を超えています")
    job = next(j for j in f["職業"] if j["表示名"] == order[n - 1])
    want = len(order) if m.group(2) == "最下" else int(m.group(2))
    if job["この回の時給の順位"] != want:
        sys.exit(f"【止まりました】サムネの文字と facts.json が合いません：{job['表示名']} の時給の順位は {job['この回の時給の順位']}位")
    return n


def bars(im, f, box, t=""):
    """年収の順に3本。サムネの文字が指す職業だけ黄。その棒の右端から下へ矢印を引き、時給の順位の札を出す"""
    x0, y0, x1, y1 = box
    d = ImageDraw.Draw(im)
    jobs = {j["表示名"]: j for j in f["職業"]}
    n = focus(f, t)
    first = max(0, min(n - 2, len(f["順位"]["年収"]) - 3)) if n > 3 else 0
    top = f["順位"]["年収"][first:first + 3]
    vmax = max(jobs[x]["年収_万円"] for x in top)
    bh, gap = 74, 30
    label_w = 150
    outlined(d, (x0, y0 - 6), "年収", 44, MUTED, 4)
    y = y0 + 56
    ends = []
    for k, nm in enumerate(top):
        j = jobs[nm]
        L = int((x1 - x0 - label_w) * (0.55 + 0.45 * j["年収_万円"] / vmax))
        hi = first + k + 1 == n
        outlined(d, (x0, y + 12), f"{first + k + 1}位", 46, YELLOW if hi else KINARI, 4)
        d.rounded_rectangle((x0 + label_w - 40, y, x0 + label_w - 40 + L, y + bh), 12, fill=YELLOW if hi else DIM)
        name = short(nm)
        s = 40
        while tw(name, s) > L - 40 and s > 24:
            s -= 2
        d.text((x0 + label_w - 20, y + bh // 2), name, font=font(s), fill=BLACK if hi else KINARI, anchor="lm")
        ends.append((x0 + label_w - 40 + L, y + bh // 2, j))
        y += bh + gap
    # 矢印：強調した棒の右端 → 下の札
    ex, ey, j = ends[n - 1 - first]
    rank = j["この回の時給の順位"]
    tag = f"時給は{rank}位"  # 見出しと同じ言葉をくり返さず、順位の数字で見せる
    if f"時給{rank}位" in t:  # 見出しに同じ順位がある時は、何職業の中の順位かを見せる
        tag = f"{len(f['順位']['年収'])}職業中 時給{rank}位"
    ts = 64
    tx1 = min(x1, SAFE[0] - 10)
    while tx1 - int(tw(tag, ts)) - 48 < x0 and ts > 40:  # 札がパネルの左へはみ出さない大きさに
        ts -= 4
    tx0 = tx1 - int(tw(tag, ts)) - 48
    ty0 = y + 18
    ty1 = ty0 + ts + 34
    if ty1 > SAFE[1] - 10 and tx1 > SAFE[0]:
        ty0, ty1 = SAFE[1] - 10 - (ts + 34), SAFE[1] - 10
    ax = min(ex + 40, x1 - 20)
    pts = [(ex + 6, ey), (ax, ey), (ax, ty0 - 34)]
    d.line(pts, fill=YELLOW, width=18, joint="curve")
    d.polygon([(ax - 34, ty0 - 40), (ax + 34, ty0 - 40), (ax, ty0 - 2)], fill=YELLOW)
    d.rounded_rectangle((tx0, ty0, tx1, ty1), 14, fill=YELLOW, outline=BLACK, width=5)
    d.text(((tx0 + tx1) // 2, (ty0 + ty1) // 2), tag, font=font(ts), fill=BLACK, anchor="mm")


def scan_frame(d, box, label):
    """競合の「AIが見ている」枠（水色の角の線）"""
    x0, y0, x1, y1 = box
    c, L = (90, 200, 230), 34
    for (px, py, dx, dy) in ((x0, y0, 1, 1), (x1, y0, -1, 1), (x0, y1, 1, -1), (x1, y1, -1, -1)):
        d.line([(px, py + dy * L), (px, py), (px + dx * L, py)], fill=c, width=5)
    if label:
        d.rectangle((x0, y0 - 34, x0 + tw(label, 24) + 16, y0), fill=c)
        d.text((x0 + 8, y0 - 17), label, font=font(24), fill=BLACK, anchor="lm")


def d_lines(t, given=None):
    """「給料30年の謎」→ ["給料", "30年", "の謎"]。数字のある行を返す番号も（その行を黄で特大）"""
    if given:
        given = [unicodedata.normalize("NFKC", x) for x in given]  # thumb_text と同じく全角・半角をそろえて照らす（「？」と「?」で止まった。2026-10-26）
        if "".join(given) != t:
            sys.exit(f"【止まりました】thumb_lines をつなぐと thumb_text と違う：{given}／{t}")
        lines = list(given)
    else:
        m = re.search(r"\d[\d,.]*[^\dのがはもでにを]?", t)
        lines = [x for x in (t[:m.start()], m.group(0), t[m.end():]) if x]
    return lines, next(i for i, x in enumerate(lines) if re.search(r"\d", x))


def d_bars(im, f, labels, box):
    """サムネD の棒：点の順に3本（手順書は3〜5本。横320pxで2位以下の名前が読めるのは3本まで）。1位は黄（名前か「？」）、ほかは1位より暗い灰。点数の数字は出さない"""
    x0, y0, x1, y1 = box
    d = ImageDraw.Draw(im)
    bs = f["点のグラフ"]["棒"][:3]
    if len(bs) < 3:
        sys.exit("【止まりました】facts.json の点のグラフの棒が3本より少ない（サムネD は3〜5本）")
    top = f.get("1位", [])
    vmax = max(b["点数"] for b in bs) or 1
    slot = (y1 - y0) // len(bs)
    bh = int(slot * 0.5)
    k = 0
    for i, b in enumerate(bs):
        y = y0 + i * slot
        hi = b["名前"] in top
        L = max(24, int((x1 - x0) * b["点数"] / vmax))
        name = labels[k] if hi else b["名前"]
        k += hi
        s = (56 if name == "？" else 40) if hi else 32  # 伏せる回の「？」も、名前と同じ所に黄で出す
        while tw(name, s) > x1 - x0 and s > 22:
            s -= 2
        outlined(d, (x0, y + slot - bh - 14 - int(s * 1.25)), name, s, YELLOW if hi else KINARI, 4)
        d.rounded_rectangle((x0, y + slot - bh - 10, x0 + L, y + slot - 10), 12, fill=YELLOW if hi else GREY)


def make_d(work, variant, bg_id, s, f):
    t = unicodedata.normalize("NFKC", s["thumb_text"])
    if len(t) > 12 or not re.search(r"\d", t) or "AI" in t.upper():
        sys.exit(f"【止まりました】サムネD の文字は12字以内で数字を1つ、「AI」は入れない：{t}")
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from check_job_script import d_top_label
    labels = d_top_label(s.get("titles", []), f)
    if labels is None:
        sys.exit("【止まりました】タイトル3案で1位の名前を出す案と伏せる案が混ざっている（サムネD の1位の棒を決められない）")
    lines, hi = d_lines(t, s.get("thumb_lines"))
    im = Image.new("RGB", (W, H), NAVY)
    if variant == "b" and bg_id:
        bg_on(im, work, bg_id)
    d = ImageDraw.Draw(im)
    if variant == "a":
        headline(im, lines, 48, 100, 560, hi)
        d.rounded_rectangle((640, 70, 1240, 610), 22, fill=PANEL)
        d_bars(im, f, labels, (676, 96, 1200, 590))
    else:
        headline(im, lines, 48, 100, 600, hi)
        panel = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(panel).rounded_rectangle((690, 100, 1240, 610), 20, fill=(20, 31, 52, 215))
        im.paste(panel, (0, 0), panel)
        d_bars(im, f, labels, (720, 120, 1200, 590))
    return im


def bg_on(im, work, bg_id):
    """場面の絵を全面に敷き、左（文字の側）を紺で暗くする"""
    p = os.path.join(work, "images", bg_id + ".png")
    bg = Image.open(p).convert("RGB")
    r = max(W / bg.width, H / bg.height)
    bg = bg.resize((int(bg.width * r + .5), int(bg.height * r + .5)))
    bg = bg.crop(((bg.width - W) // 2, (bg.height - H) // 2, (bg.width - W) // 2 + W, (bg.height - H) // 2 + H))
    im.paste(bg)
    g = Image.new("L", (W, H), 0)
    gd = ImageDraw.Draw(g)
    for x in range(W):  # 左を暗く（文字の側）
        gd.line((x, 0, x, H), fill=int(235 * max(0.25, 1 - x / (W * 0.62))))
    im.paste(NAVY, (0, 0, W, H), g)


def two_lines(t, given=None):
    """サムネA・B の文字を2行までに割る。数字のある行を返す番号も（その行を大きく）。数字が無ければ最後の行"""
    if given:
        given = [unicodedata.normalize("NFKC", x) for x in given]  # thumb_text と同じく全角・半角をそろえて照らす（「？」と「?」で止まった。2026-10-26）
        if "".join(given) != t or len(given) > 2:
            sys.exit(f"【止まりました】thumb_lines は2行までで、つなぐと thumb_text になる並び：{given}／{t}")
        lines = list(given)
    else:
        m = re.search(r"\d", t)
        if m and m.start() > 0:
            lines = [t[:m.start()], t[m.start():]]
        elif m:
            n = re.match(r"[\d,.]+(万円|万|円|%|時間|年|歳|位|倍|割|人|日)?", t)
            lines = [x for x in (t[:n.end()], t[n.end():]) if x]
        elif len(t) <= 4:
            lines = [t]
        else:  # 数字が無い時は、真ん中に近い助詞の後ろで割る
            cut = min((i + 1 for i, c in enumerate(t[:-1]) if c in "のがはもでにをとへ"), key=lambda i: abs(i - len(t) / 2), default=len(t) // 2)
            lines = [t[:cut], t[cut:]]
    hi = next((i for i, x in enumerate(lines) if re.search(r"\d", x)), len(lines) - 1)
    return lines, hi


def save(im, work, variant):
    out = os.path.join(work, f"thumb_{variant}.jpg")
    im.save(out, quality=92)
    im.resize((320, 180), Image.LANCZOS).save(out.replace(".jpg", "_320.jpg"), quality=90)
    return out


def a_bars(im, s, f, box):
    """サムネA の a案の左の図：2本の棒（数字は出さない）。A-1＝この職業と全産業の平均の年収、A-3＝2つの職業の山場の項目。よい方を黄"""
    x0, y0, x1, y1 = box
    d = ImageDraw.Draw(im)
    d.rounded_rectangle(box, 26, fill=NAVY)
    if s.get("frame") == "A-1":
        b = next((x for x in f["棒グラフ"]["棒"] if x["物差し"] == "年収_万円"), None)
        if not b:
            sys.exit("【止まりました】facts.json の棒グラフに年収_万円が無い（サムネA の図を描けない）")
        cap = "年収"
        rows = [(f["職業"], b[f["職業"]], True), ("全産業の平均", b["全産業の平均"], False)]
    else:
        it = f["山場の項目"]
        r = next(x for x in f["項目ごと"] if x["項目"] == it)
        cap = it
        rows = [(j["表示名"], r[j["表示名"]], r.get("勝った方") == j["表示名"]) for j in f["職業"][:2]]
    outlined(d, (x0 + 34, y0 + 26), cap, 52, MUTED, 4)
    vmax = max(v for _, v, _ in rows) or 1
    y = y0 + 130
    for nm, v, hi in rows:
        nm = short(nm)
        sz = 50
        while tw(nm, sz) > x1 - x0 - 68 and sz > 36:
            sz -= 2
        outlined(d, (x0 + 34, y), nm, sz, YELLOW if hi else KINARI, 4)
        L = int((x1 - x0 - 68) * v / vmax)  # 0から伸ばす（差を大きく見せない）
        d.rounded_rectangle((x0 + 34, y + sz + 22, x0 + 34 + L, y + sz + 22 + 84), 12, fill=YELLOW if hi else GREY)
        y += sz + 22 + 84 + 46


def make_a(work, variant, bg_id, s, f):
    """サムネA（A-1・A-3）：黄の地に黒い文字を右半分に2行まで。強調の1語（数字の行）は大きい黒の太字（赤は使わない）。
    左は a案＝2本の棒の図（プログラムが描く）、b案＝その職業の道具か場面の絵（thumb_bg）"""
    t = unicodedata.normalize("NFKC", s["thumb_text"])
    if len(t) > 12 or not re.search(r"\d", t):
        sys.exit(f"【止まりました】サムネA の文字は12字以内で数字を1つ：{t}")
    if "離職率" in t and not re.search(r"業の離職率|含む", t):
        sys.exit(f"【止まりました】サムネに離職率を出す時は「〇〇業の」を付ける：{t}")
    lines, hi = two_lines(t, s.get("thumb_lines"))
    im = Image.new("RGB", (W, H), YELLOW)
    if variant == "b" and bg_id:
        p = os.path.join(work, "images", bg_id + ".png")
        bg = Image.open(p).convert("RGB")
        bw, bh = 580, 580
        r = max(bw / bg.width, bh / bg.height)
        bg = bg.resize((int(bg.width * r + .5), int(bg.height * r + .5)))
        bg = bg.crop(((bg.width - bw) // 2, (bg.height - bh) // 2, (bg.width - bw) // 2 + bw, (bg.height - bh) // 2 + bh))
        m = Image.new("L", (bw, bh), 0)
        ImageDraw.Draw(m).rounded_rectangle((0, 0, bw - 1, bh - 1), 26, fill=255)
        im.paste(bg, (40, 70), m)
        ImageDraw.Draw(im).rounded_rectangle((40, 70, 40 + bw, 70 + bh), 26, outline=BLACK, width=6)
    else:
        a_bars(im, s, f, (40, 70, 620, 650))
    d = ImageDraw.Draw(im)
    sizes = []
    for i, x in enumerate(lines):
        size = 210 if i == hi else 120
        while tw(x, size) > 590 and size > 60:
            size -= 4
        sizes.append(size)
    y = 70 + (580 - sum(int(z * 1.18) for z in sizes)) // 2  # 左の図（y 70〜650）と上下の真ん中をそろえる
    for x, size in zip(lines, sizes):
        d.text((660, y), x, font=font(size), fill=BLACK, stroke_width=max(5, size // 16), stroke_fill=KINARI)
        y += int(size * 1.18)
    if y > SAFE[1] + 40:
        sys.exit(f"【止まりました】サムネA の文字が右下の再生時間の所に掛かる：{lines}")
    return im


def make_b(work, variant, bg_id, s, f):
    """サムネB（型B・C）：主役の表情を大きく出した絵（thumb_bg）を背景に、文字は8字以内。数字の行（無ければ最後の行）を黄で特大。
    a案＝絵を全面に敷き左を暗く、b案＝紺の地の右に絵を枠で出す"""
    t = unicodedata.normalize("NFKC", s["thumb_text"])
    if not 0 < len(t) <= 8:
        sys.exit(f"【止まりました】サムネB の文字は8字以内：{t}")
    lines, hi = two_lines(t, s.get("thumb_lines"))
    im = Image.new("RGB", (W, H), NAVY)
    has = bool(bg_id) and os.path.exists(os.path.join(work, "images", bg_id + ".png"))
    if not has:
        print("【メモ】サムネB の主役の絵（thumb_bg）がまだ無いので、文字だけの仮の絵です")
    elif variant == "a":
        bg_on(im, work, bg_id)
    else:
        p = os.path.join(work, "images", bg_id + ".png")
        bg = Image.open(p).convert("RGB")
        bw, bh = 640, 600
        r = max(bw / bg.width, bh / bg.height)
        bg = bg.resize((int(bg.width * r + .5), int(bg.height * r + .5)))
        x0 = int((bg.width - bw) * 0.7)  # 主役は絵の右寄り（a案で左を暗くするため）なので、切り出しも右へ寄せる
        bg = bg.crop((x0, (bg.height - bh) // 2, x0 + bw, (bg.height - bh) // 2 + bh))
        im.paste(bg, (600, 20))
        ImageDraw.Draw(im).rectangle((600, 20, 600 + bw - 1, 20 + bh - 1), outline=YELLOW, width=8)
    y = 110 if len(lines) == 2 else 210
    for i, x in enumerate(lines):
        size = 230 if i == hi else 150
        while tw(x, size) > 530 and size > 70:  # b案の絵の枠（x=600）に掛けない
            size -= 4
        outlined(ImageDraw.Draw(im), (48, y), x, size, YELLOW if i == hi else KINARI)
        y += int(size * 1.15)
    return im


def make(work, variant, bg_id=None):
    s = json.load(open(os.path.join(work, "script.json"), encoding="utf-8"))
    f = json.load(open(os.path.join(work, "facts.json"), encoding="utf-8"))
    if s.get("type") in ("B", "C"):  # サムネB（人物が主役）
        return save(make_b(work, variant, bg_id, s, f), work, variant)
    if s.get("type") == "A" and s.get("frame") in ("A-1", "A-3"):  # サムネA（数字が主役）
        return save(make_a(work, variant, bg_id, s, f), work, variant)
    if s.get("type") == "D":
        im = make_d(work, variant, bg_id, s, f)
        out = os.path.join(work, f"thumb_{variant}.jpg")
        im.save(out, quality=92)
        im.resize((320, 180), Image.LANCZOS).save(out.replace(".jpg", "_320.jpg"), quality=90)
        return out
    t = unicodedata.normalize("NFKC", s["thumb_text"])  # 全角の数字も半角にそろえて照らす
    if len(t) > 12 or not re.search(r"\d", t):
        sys.exit(f"【止まりました】サムネの文字は12字以内で数字を1つ：{t}")
    im = Image.new("RGB", (W, H), NAVY)
    if variant == "b" and bg_id:
        p = os.path.join(work, "images", bg_id + ".png")
        bg = Image.open(p).convert("RGB")
        r = max(W / bg.width, H / bg.height)
        bg = bg.resize((int(bg.width * r + .5), int(bg.height * r + .5)))
        bg = bg.crop(((bg.width - W) // 2, (bg.height - H) // 2, (bg.width - W) // 2 + W, (bg.height - H) // 2 + H))
        im.paste(bg)
        g = Image.new("L", (W, H), 0)
        gd = ImageDraw.Draw(g)
        for x in range(W):  # 左を暗く（文字の側）
            gd.line((x, 0, x, H), fill=int(235 * max(0.25, 1 - x / (W * 0.62))))
        im.paste(NAVY, (0, 0, W, H), g)
    d = ImageDraw.Draw(im)
    lines = lines_of(t)
    if variant == "a":
        headline(im, lines, 48, 100, 560)
        d.rounded_rectangle((640, 70, 1240, 610), 22, fill=PANEL)
        bars(im, f, (676, 106, 1210, 610), t)
    else:
        headline(im, lines, 48, 100, 600)
        panel = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(panel).rounded_rectangle((700, 120, 1240, 520), 20, fill=(20, 31, 52, 215))
        im.paste(panel, (0, 0), panel)
        d = ImageDraw.Draw(im)
        scan_frame(d, (700, 120, 1240, 520), "年収と時給をくらべた")
        bars(im, f, (724, 140, 1220, 640), t)
    out = os.path.join(work, f"thumb_{variant}.jpg")
    im.save(out, quality=92)
    im.resize((320, 180), Image.LANCZOS).save(out.replace(".jpg", "_320.jpg"), quality=90)
    return out


def check(work, outs, t):
    import gemini
    sch = {"type": "object", "properties": {"読めた文字": {"type": "array", "items": {"type": "string"}}}, "required": ["読めた文字"]}
    r, u = gemini.ask("添付の2枚は YouTube のサムネを横320pxに縮めた物です。それぞれ、いちばん大きい見出しの文字を、改行を詰めて1つの文字列で書いてください（棒グラフの中の文字は除く）。読めない字は？にしてください。",
                      schema=sch, images=[o.replace(".jpg", "_320.jpg") for o in outs])
    got = json.loads(r)["読めた文字"]
    t = unicodedata.normalize("NFKC", t)  # 読めた文字も thumb_text も全角・半角をそろえて照らす（「？」と「?」で006が3回目も止まった。2026-10-26）
    same = lambda g: unicodedata.normalize("NFKC", g).replace(" ", "") == t
    for o, g in zip(outs, got):
        print(os.path.basename(o), "320pxで読めた：", g, "一致" if same(g) else "【不一致】")
    return all(same(g) for g in got)


def main():
    a = argparse.ArgumentParser()
    a.add_argument("work")
    a.add_argument("--bg", default="")
    a.add_argument("--check", action="store_true")
    a = a.parse_args()
    outs = [make(a.work, "a", a.bg or None)]  # A-4・D の a案は絵を使わない。B・C の a案は主役の絵を全面に敷く
    if a.bg and os.path.exists(os.path.join(a.work, "images", a.bg + ".png")):
        outs.append(make(a.work, "b", a.bg))
    else:
        print("【メモ】b案の背景の絵がまだ無いので、a案だけ作りました")
    for o in outs:
        print("保存", o)
    if a.check:
        t = json.load(open(os.path.join(a.work, "script.json"), encoding="utf-8"))["thumb_text"]
        sys.exit(0 if check(a.work, outs, t) else 1)


if __name__ == "__main__":
    main()

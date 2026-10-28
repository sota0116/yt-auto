# 千年こよみの特典（型A・C2）「今月と来月の吉日と行事のカレンダー」を画像と PDF にする（手順書 §4 の表・line_scenario.md の0日目）
#   python -X utf8 pipeline\make_tokuten_spi.py 2026-11
# ・値は data\koyomi_2026_2027.json を読むだけ（計算は build_koyomi.py）。日付・曜日・六曜・選日・行事・節気は全部この固定ファイルから
# ・天赦日と一粒万倍日が重なる日に金の印をつける（あいさつ文「重なる日には、印をつけてあります」）
# ・出力：tokuten\spi\tokuten_spi_AC2_<年-月>.png（A4・300dpi相当）／_phone.png（スマホ用に縮めた物）／.pdf／.json（有効月）
import calendar, datetime, hashlib, json, os, sys
from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "tokuten", "spi")
F = "C:/Windows/Fonts/"
UD_B, UD_R, MIN = F + "BIZ-UDGothicB.ttc", F + "BIZ-UDGothicR.ttc", F + "BIZ-UDMinchoM.ttc"

# 千年こよみの色（手順書 §6：朱と金と生成り。サムネの朱は make_thumb_koyomi.py と同じ）
SHU = (196, 62, 44)
GOLD = (217, 180, 90)
ECRU = (248, 242, 230)
INK = (43, 38, 34)
GRAY = (120, 110, 100)
CELL = (255, 251, 243)
LINE = (214, 200, 178)
SUN = (196, 62, 44)
SAT = (52, 84, 140)

W, H = 2480, 3508  # A4 縦・300dpi
M = 100
KEY = ["天赦日", "一粒万倍日", "己巳の日", "巳の日", "寅の日"]
SHORT = {"天赦日": "天赦日", "一粒万倍日": "一粒万倍日", "己巳の日": "己巳の日", "巳の日": "巳の日", "寅の日": "寅の日"}


def f(path, size):
    return ImageFont.truetype(path, size)


def tw(d, s, ft):
    return d.textlength(s, font=ft)


def center(d, cx, y, s, ft, fill):
    d.text((cx - tw(d, s, ft) / 2, y), s, font=ft, fill=fill)


def wrap(d, s, ft, max_w):
    out, line = [], ""
    for ch in s:
        if tw(d, line + ch, ft) > max_w and line:
            out.append(line)
            line = ch
        else:
            line += ch
    return out + [line]


def marks(x):
    s = [k for k in KEY if k in x["senjitsu"]]
    if "己巳の日" in s and "巳の日" in s:
        s.remove("巳の日")  # 己巳の日は巳の日の1つ。札は1つにする
    return s


def is_top(x):
    return "天赦日" in x["senjitsu"] and "一粒万倍日" in x["senjitsu"]


def month_grid(d, y, yr, mo, days):
    d.text((M, y), f"{yr}年{mo}月", font=f(MIN, 92), fill=INK)
    y += 128
    cw = (W - 2 * M) / 7
    hh = 64
    for i, wd in enumerate("日月火水木金土"):
        x0 = M + i * cw
        d.rectangle((x0, y, x0 + cw, y + hh), fill=INK)
        center(d, x0 + cw / 2, y + 12, wd, f(UD_B, 38), SHU if i == 0 else ((150, 180, 230) if i == 6 else ECRU))
    y += hh
    weeks = calendar.Calendar(firstweekday=6).monthdayscalendar(yr, mo)
    ch = 216
    for wi, wk in enumerate(weeks):
        for i, dn in enumerate(wk):
            x0, y0 = M + i * cw, y + wi * ch
            d.rectangle((x0, y0, x0 + cw, y0 + ch), fill=CELL if dn else ECRU, outline=LINE, width=2)
            if not dn:
                continue
            x = days[f"{yr}-{mo:02d}-{dn:02d}"]
            top = is_top(x)
            if top:
                d.rectangle((x0 + 4, y0 + 4, x0 + cw - 4, y0 + ch - 4), outline=GOLD, width=12)
                d.rectangle((x0 + 16, y0 + 16, x0 + cw - 16, y0 + ch - 16), fill=(253, 241, 205))
            red = i == 0 or x["holiday"]
            d.text((x0 + 22, y0 + 14), str(dn), font=f(UD_B, 60), fill=SUN if red else (SAT if i == 6 else INK))
            rk = x["rokuyo"]
            rf = f(UD_B if rk == "大安" else UD_R, 30)
            d.text((x0 + cw - 22 - tw(d, rk, rf), y0 + 22), rk, font=rf, fill=SHU if rk == "大安" else GRAY)
            ly = y0 + 88
            labels = []
            if top:
                labels.append(("最強開運日", GOLD, INK))
            for k in marks(x):
                if top and k in ("天赦日", "一粒万倍日"):
                    continue
                labels.append((SHORT[k], SHU, ECRU))
            for name, bg, fg in labels:
                lf = f(UD_B, 29)
                lw = tw(d, name, lf) + 20
                d.rounded_rectangle((x0 + 14, ly, x0 + 14 + lw, ly + 40), 8, fill=bg)
                d.text((x0 + 24, ly + 5), name, font=lf, fill=fg)
                ly += 46
            if top:
                d.text((x0 + 18, ly), "天赦日×一粒万倍日", font=f(UD_R, 23), fill=INK)
                ly += 32
            for t in ([x["holiday"]] if x["holiday"] else []) + x["gyoji"] + ([x["sekki"]["name"]] if x["sekki"] else []) + x["zassetsu"]:
                tf = f(UD_R, 25)
                for line in wrap(d, t, tf, cw - 30)[:2]:
                    if ly + 30 > y0 + ch - 6:
                        break
                    d.text((x0 + 16, ly), line, font=tf, fill=SHU if t == x["holiday"] else INK)
                    ly += 30
    return y + len(weeks) * ch


def overlaps(seq):
    out = []
    for x in seq:
        s = marks(x) + (["大安"] if x["rokuyo"] == "大安" else [])
        if len(s) >= 2:
            out.append((x, s))
    return out


def main(month):
    k = json.load(open(os.path.join(ROOT, "data", "koyomi_2026_2027.json"), encoding="utf-8"))
    days = {x["date"]: x for x in k["days"]}
    y1, m1 = map(int, month.split("-"))
    y2, m2 = (y1 + 1, 1) if m1 == 12 else (y1, m1 + 1)
    for yr, mo in ((y1, m1), (y2, m2)):
        last = calendar.monthrange(yr, mo)[1]
        if f"{yr}-{mo:02d}-01" not in days or f"{yr}-{mo:02d}-{last:02d}" not in days:
            sys.exit(f"【止まりました】暦の固定ファイルに {yr}年{mo}月 がありません（有効 {k['meta']['valid_from']}〜{k['meta']['valid_to']}）")
    seq = [x for x in k["days"] if x["date"][:7] in (f"{y1}-{m1:02d}", f"{y2}-{m2:02d}")]

    img = Image.new("RGB", (W, H), ECRU)
    d = ImageDraw.Draw(img)
    d.rectangle((0, 0, W, 300), fill=SHU)
    d.text((M, 44), "千年こよみ", font=f(UD_B, 46), fill=ECRU)
    s = f"{y1}年{m1}月・{m2}月版"
    d.text((W - M - tw(d, s, f(UD_B, 46)), 44), s, font=f(UD_B, 46), fill=ECRU)
    d.text((M, 120), f"{m1}月と{m2}月の吉日と行事のカレンダー", font=f(MIN, 104), fill=ECRU)

    y = month_grid(d, 330, y1, m1, days)
    y = month_grid(d, y + 36, y2, m2, days)

    # 2か月の重なり
    y += 34
    d.text((M, y), "この2か月の重なり", font=f(MIN, 60), fill=INK)
    y += 84
    ov = overlaps(seq)
    col = (W - 2 * M) / 2
    of = f(UD_R, 34)
    for i, (x, s) in enumerate(ov):
        c, r = divmod(i, (len(ov) + 1) // 2)
        mo, dn = int(x["date"][5:7]), int(x["date"][8:10])
        ft, fc = (f(UD_B, 34), SHU) if is_top(x) else (of, INK)
        d.text((M + c * col, y + r * 50), f"{mo}月{dn}日（{x['weekday']}）", font=ft, fill=fc)
        d.text((M + c * col + 300, y + r * 50), "×".join(s), font=ft, fill=fc)  # 日付の幅がそろわないので、重なりの頭をそろえる
    y += ((len(ov) + 1) // 2) * 50 + 20

    # 注と出典
    d.line((M, y, W - M, y), fill=LINE, width=3)
    y += 20
    notes = [
        "金の枠は、天赦日と一粒万倍日が重なる日です。右上は六曜（大安は朱）。赤い日付は日曜と祝日です。",
        "天赦日：「万事にわたって吉とする」日。一粒万倍日：万事を始めるによい日とされ、仕事始め・開店・種まき・出金などは吉、借金・借り物は凶とされています。大安：「万事大吉」。（国立国会図書館「日本の暦」）",
        "巳の日・己巳の日は弁財天、寅の日は金運にゆかりのある日と伝えられています。己巳の日は60日に1度です。",
        "日付・曜日・六曜・干支・選日・節気・祝日は、国立天文台の暦要項と国立国会図書館「日本の暦」をもとにプログラムで計算し、照らし合わせています。行事の日付は、公的機関と神社の公式サイトの記述で確かめています。",
    ]
    nf = f(UD_R, 29)
    for n in notes:
        for line in wrap(d, n, nf, W - 2 * M):
            d.text((M, y), line, font=nf, fill=GRAY)
            y += 40
        y += 4
    if y > H - 30:
        sys.exit(f"【止まりました】A4 に収まりません（{y}px／{H}px）")

    os.makedirs(OUT, exist_ok=True)
    base = os.path.join(OUT, f"tokuten_spi_AC2_{month}")
    img.save(base + ".png", optimize=True)
    img.save(base + ".pdf", resolution=300.0)
    ph = img.resize((1240, round(H * 1240 / W)), Image.LANCZOS)
    ph.save(base + "_phone.png", optimize=True)
    meta = {"特典": "今月と来月の吉日と行事のカレンダー", "型": ["A", "C2"], "有効月": month, "月": [f"{y1}-{m1:02d}", f"{y2}-{m2:02d}"],
            "作った日": datetime.date.today().isoformat(), "使った値": ["data/koyomi_2026_2027.json"],
            "重なり": [{"date": x["date"], "重なり": s} for x, s in ov], "ファイル": {}}
    for ext in (".png", "_phone.png", ".pdf"):
        p = base + ext
        meta["ファイル"][os.path.basename(p)] = hashlib.sha256(open(p, "rb").read()).hexdigest()
    json.dump(meta, open(base + ".json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"作りました：{base}.png / _phone.png / .pdf（下端 {y}px／{H}px・重なり {len(ov)} 日）")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else datetime.date.today().strftime("%Y-%m"))

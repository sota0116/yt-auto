# 仕事チャンネルの特典（型A・C）「主な職業の年収・労働時間と、産業別の離職率の一覧」を画像と PDF にする
#   python -X utf8 pipeline\make_tokuten_job.py 2026-11
# ・値は data\job\ の JSON を読むだけ（計算は fetch_job_data.py）。表の下に出典・加工の旨・e-Stat の決まりの1文を書く（手順書 §4）
# ・出力：tokuten\job\tokuten_job_AC_<年-月>.png（A4・300dpi相当）／_phone.png（スマホ用に縮めた物）／.pdf／.json（有効月）
import datetime, hashlib, json, os, sys
from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data", "job")
OUT = os.path.join(ROOT, "tokuten", "job")
F = "C:/Windows/Fonts/"
UD_B, UD_R = F + "BIZ-UDGothicB.ttc", F + "BIZ-UDGothicR.ttc"

# チャンネルの看板と同じ色（設計/branding_tools/make_branding_v11.py）
NAVY = (31, 42, 68)
ECRU = (243, 235, 221)
YELLOW = (245, 197, 24)
RED = (217, 58, 43)
INK = (33, 33, 33)
GRAY = (110, 110, 110)
ROWBG = (250, 246, 238)
LINE = (214, 205, 190)

W, H = 2480, 3508  # A4 縦・300dpi
M = 110  # 左右の余白


def f(path, size):
    return ImageFont.truetype(path, size)


def tw(d, s, ft):
    return d.textlength(s, font=ft)


def right(d, x, y, s, ft, fill):
    d.text((x - tw(d, s, ft), y), s, font=ft, fill=fill)


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


def main(month):
    m40 = json.load(open(os.path.join(DATA, "main40_r7.json"), encoding="utf-8"))
    rs = json.load(open(os.path.join(DATA, "rishoku_sangyo_r7.json"), encoding="utf-8"))
    src = json.load(open(os.path.join(ROOT, "data", "sources.json"), encoding="utf-8"))
    rows = m40["data"]
    if len(rows) != 40:
        sys.exit("【止まりました】主な職業が40ではありません")
    y_, mo_ = map(int, month.split("-"))

    img = Image.new("RGB", (W, H), ECRU)
    d = ImageDraw.Draw(img)

    # 見出しの帯
    d.rectangle((0, 0, W, 330), fill=NAVY)
    d.text((M, 52), "あの仕事の年収と一生", font=f(UD_B, 46), fill=YELLOW)
    right(d, W - M, 52, f"{y_}年{mo_}月版", f(UD_B, 46), ECRU)
    d.text((M, 120), "主な職業40の年収・労働時間と、", font=f(UD_B, 84), fill=ECRU)
    d.text((M, 218), "産業別の離職率", font=f(UD_B, 84), fill=ECRU)
    sub = "厚生労働省の統計（2025年の調査）から計算"
    right(d, W - M, 248, sub, f(UD_R, 44), ECRU)

    # 表1：職業
    y = 350
    d.text((M, y), "1. 職業ごとの年収と働く時間（年収の高い順）", font=f(UD_B, 60), fill=NAVY)
    y += 92
    cols = {"rank": M + 78, "name": M + 108, "bar": M + 900, "nen": M + 1335, "hrs": M + 1610,
            "jik": M + 1905, "age": M + 2100, "kin": W - M}
    hf = f(UD_B, 36)
    d.rectangle((M, y, W - M, y + 96), fill=NAVY)
    right(d, cols["rank"], y + 30, "順位", hf, ECRU)
    d.text((cols["name"], y + 30), "職業", font=hf, fill=ECRU)
    right(d, cols["nen"], y + 8, "年収", hf, YELLOW)
    right(d, cols["nen"], y + 52, "（万円）", f(UD_R, 30), ECRU)
    right(d, cols["hrs"], y + 8, "月の労働", hf, ECRU)
    right(d, cols["hrs"], y + 52, "時間（残業込）", f(UD_R, 28), ECRU)
    right(d, cols["jik"], y + 8, "時給に", hf, ECRU)
    right(d, cols["jik"], y + 52, "直すと（円）", f(UD_R, 28), ECRU)
    right(d, cols["age"], y + 8, "平均", hf, ECRU)
    right(d, cols["age"], y + 52, "年齢", hf, ECRU)
    right(d, cols["kin"], y + 8, "勤続", hf, ECRU)
    right(d, cols["kin"], y + 52, "年数", hf, ECRU)
    y += 96
    rh = 48
    maxn = max(r["年収_千円"] for r in rows)
    nf, vf, bf = f(UD_R, 35), f(UD_R, 35), f(UD_B, 37)
    for i, r in enumerate(rows):
        top = y + i * rh
        if i % 2 == 0:
            d.rectangle((M, top, W - M, top + rh), fill=ROWBG)
        ty = top + 6
        right(d, cols["rank"], ty, str(r["年収の順位"]), vf, GRAY)
        name = r["表示名"]
        nfit = nf
        while tw(d, name, nfit) > cols["bar"] - cols["name"] - 20:
            nfit = f(UD_R, nfit.size - 2)
        d.text((cols["name"], ty + (35 - nfit.size) // 2), name, font=nfit, fill=INK)
        bw = (cols["nen"] - 175 - cols["bar"]) * r["年収_千円"] / maxn
        d.rectangle((cols["bar"], top + 12, cols["bar"] + bw, top + rh - 12), fill=YELLOW)
        right(d, cols["nen"], ty - 1, f"{round(r['年収_千円'] / 10):,}", bf, INK)
        right(d, cols["hrs"], ty, f"{r['月の労働時間']}", vf, INK)
        right(d, cols["jik"], ty, f"{r['時給に直した額_円']:,}", vf, INK)
        right(d, cols["age"], ty, f"{r['年齢']:.1f}", vf, INK)
        right(d, cols["kin"], ty, f"{r['勤続年数']:.1f}", vf, INK)
    y += rh * 40
    d.line((M, y, W - M, y), fill=LINE, width=3)

    # 表2：産業の離職率（2列）
    y += 40
    d.text((M, y), "2. 産業ごとの離職率（1年に辞めた人の割合・高い順）", font=f(UD_B, 60), fill=NAVY)
    y += 90
    ind = {k: v for k, v in rs["data"]["男女計"].items() if k != "産業計"}
    allr = rs["data"]["男女計"]["産業計"]["離職率"]
    items = sorted(ind.items(), key=lambda kv: -kv[1]["離職率"])
    short = {"サービス業（他に分類されないもの）": "サービス業（派遣・警備・清掃など）",
             "学術研究，専門・技術サービス業": "学術研究・専門・技術サービス業",
             "電気・ガス・熱供給・水道業": "電気・ガス・水道業",
             "鉱業，採石業，砂利採取業": "鉱業・採石業"}
    colw = (W - 2 * M - 60) / 2
    irh = 50
    maxr = items[0][1]["離職率"]
    lf, rf = f(UD_R, 34), f(UD_B, 37)
    for i, (k, v) in enumerate(items):
        c, rr = divmod(i, 8)
        x0 = M + c * (colw + 60)
        top = y + rr * irh
        name = short.get(k, k).replace("，", "・")
        d.text((x0, top + 8), name, font=lf, fill=INK)
        bx0, bx1 = x0 + 640, x0 + colw - 120
        bw = (bx1 - bx0) * v["離職率"] / maxr
        d.rectangle((bx0, top + 12, bx0 + bw, top + irh - 12), fill=RED if v["離職率"] > allr else NAVY)
        right(d, x0 + colw, top + 5, f"{v['離職率']:.1f}%", rf, INK)
    y += irh * 8 + 18
    d.text((M, y), f"全産業の平均は {allr:.1f}%。赤い棒は平均より高い産業、紺の棒は平均以下の産業。",
           font=f(UD_R, 36), fill=INK)
    y += 56
    d.text((M, y), "離職率は産業ごとの数字です。職業ごとの離職率は、国の統計にはありません。",
           font=f(UD_B, 36), fill=RED)

    # 注と出典
    y += 64
    d.line((M, y, W - M, y), fill=LINE, width=3)
    y += 22
    ci, ko = src["chinkin_r7_shokushu"], src["koyodoko_r7_sanko1"]
    notes = [
        "年収＝毎月の給与（残業代を含む）×12＋1年分のボーナス。時給に直すと＝年収÷（月の労働時間×12）。",
        "対象は、フルタイムで働く人（短時間で働く人を除く）・従業員10人以上の会社・男女合わせた平均。役所で働く公務員は入っていません。",
        "職業名は、調査の職種名を短くした呼び名です（例：パイロット＝航空機操縦士、管理職＝管理的職業従事者、調理人＝飲食物調理従事者）。",
        f"出典：厚生労働省「令和7年賃金構造基本統計調査」一般労働者 職種 第1表（{ci['release_date']} 公表）、"
        f"厚生労働省「令和7年雇用動向調査」参考表1（{ko['release_date']} 公表）。いずれも e-Stat（https://www.e-stat.go.jp/）。",
        "上の出典の表をもとに、「あの仕事の年収と一生」が加工して作成しました。",
        "このサービスは、政府統計総合窓口(e-Stat)のAPI機能を使用していますが、サービスの内容は国によって保証されたものではありません。",
    ]
    nf2 = f(UD_R, 29)
    for n in notes:
        for line in wrap(d, n, nf2, W - 2 * M):
            d.text((M, y), line, font=nf2, fill=GRAY if "API機能" not in n else INK)
            y += 40
        y += 4
    if y > H - 40:
        sys.exit(f"【止まりました】A4 に収まりません（{y}px／{H}px）")

    os.makedirs(OUT, exist_ok=True)
    base = os.path.join(OUT, f"tokuten_job_AC_{month}")
    img.save(base + ".png", optimize=True)
    img.save(base + ".pdf", resolution=300.0)
    ph = img.resize((1240, round(H * 1240 / W)), Image.LANCZOS)
    ph.save(base + "_phone.png", optimize=True)
    meta = {"特典": "主な職業の年収・労働時間と、産業別の離職率の一覧", "型": ["A", "C"], "有効月": month,
            "作った日": datetime.date.today().isoformat(), "使った値": ["data/job/main40_r7.json", "data/job/rishoku_sangyo_r7.json"],
            "ファイル": {}}
    for ext in (".png", "_phone.png", ".pdf"):
        p = base + ext
        meta["ファイル"][os.path.basename(p)] = hashlib.sha256(open(p, "rb").read()).hexdigest()
    json.dump(meta, open(base + ".json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"作りました：{base}.png / _phone.png / .pdf（下端 {y}px／{H}px）")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else datetime.date.today().strftime("%Y-%m"))

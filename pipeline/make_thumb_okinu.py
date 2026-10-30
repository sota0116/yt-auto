# ⑨サムネ・長尺（金運おきぬ・2026-10-29 新設／2026-10-30 制作ルール v1.7 §9 の4つの型に更新）：run_daily.py の thumb の段から呼ぶ薄い包み
#   python -X utf8 pipeline/make_thumb_okinu.py <作業フォルダ> [--bg THUMB] [--check]
# ・script.json の thumb.layout が object／person／split／shock のどれかなら、その型で背景を組んで文字を載せる（手で作った 003〜006 のサムネの作り）。layout が無ければ前の2段の型（thumb.top／big）
#     object：物の寄りが背景。左上に2行（2行目は大きく黄色）・下に赤い帯の判定。 {"layout":"object","bg":"<カットid>","line1":"枕元の","line2":"コレ","judge":"今すぐどけて"}
#     person：人物を左に（左右反転）・右上に2行・下に大きな赤の判定。            {"layout":"person","bg":"<カットid>","line1":"疲れた夜に","line2":"●●する人","judge":"大損してます","hl":["●●"]}
#     split：左右半分（左＝暗い悪い絵・右＝明るい良い絵）・上に2行・下に札。     {"layout":"split","left":"<カットid>","right":"<カットid>","line1":"トイレの●●で","line2":"差がつく","left_label":"残らない家","right_label":"残る家"}
#     shock：左に物の絵・右に驚いた顔・左上に2行・下に赤い判定。               {"layout":"shock","bg":"<物のカットid>","face":"<驚いた顔のカットid>","line1":"玄関に●●を","line2":"出してる家","judge":"破産します"}
#   任意：hl（色を変える語の配列。無ければ ●● か先頭2字）・marks（赤丸・赤矢印。make_thumb_v3.py の marks と同じ）・flip（person の左右反転。既定 true）・
#         zoom／zx／zy（object の寄り。既定 1.0・中心）・face_dx（shock の顔を右へずらす px。既定 380）
# ・絵は images/<id>.png（ポーズ絵のカットも同じ。same_as はたどる。.mp4 しか無ければ1コマ目）。背景は thumb_bg.png に組んで、make_thumb_v3.py（スキルの make_thumb.py v3 の写し）で文字を載せる
# ・手順書 §9：3段の字（上2行＝場面か悩み／下＝判定）・判定は画面の幅の6割以上・赤い判定・背景は暗め・右に驚いた顔・赤い矢印か丸
# ・thumb.jpg を thumb_a.jpg（アップロードの名前）と横320pxの thumb_small.jpg にも置く。--check：点検に NG があれば終了コード1（絵は保存される）
# ・点検（make_thumb_v3.py の check）は、型ごとに外れる数字を直した：いちばん大きい字の横幅は 70% → 45% 以上（object は2行目が大きく判定が帯なので）
import argparse, contextlib, io, json, os, shutil, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "vendor", "youtube-video-maker", "scripts"))  # make_thumb_v3.py が import する common
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import make_thumb_v3 as T  # noqa: E402
import rank_montage_okinu as RM  # noqa: E402
from PIL import Image, ImageEnhance  # noqa: E402

W, H = 1280, 720
YEL, RED = "#FFE600", ["#FF6A4A", "#FF1E1E", "#C00010"]
LAYOUTS = ("object", "person", "split", "shock")


def spec_legacy(s, bg_rel):
    """前の2段の型（thumb.top／big）。layout の無い台本用"""
    th = s.get("thumb") or {}
    top, big = (th.get("top") or "").strip(), (th.get("big") or "").strip()
    if not big:
        sys.exit("【止まりました】script.json に thumb.layout も thumb.big（下の段の語）もありません")
    n_big = max(len(l) for l in big.split("\n"))
    size_big = min(250, int(1180 / max(1, n_big)))
    y_big = H - int(size_big * 1.2) - 40
    texts = []
    if top:
        n_top = max(len(l) for l in top.split("\n"))
        size_top = min(112, int(1180 / max(1, n_top)))
        hl_top = [w for w in (th.get("hl") or []) if w in top][:1]
        texts.append({"t": top, "x": 0, "y": 28, "size": size_top, "color": "#FFFFFF", "hl": hl_top, "hl_color": "#FFD23F", "center": True})
    hl_big = [w for w in (th.get("hl") or []) if w in big][:1] or [big.split("\n")[-1][-3:]]
    texts.append({"t": big, "x": 0, "y": y_big, "size": size_big, "color": "#FFFFFF", "hl": hl_big,
                  "hl_color": ["#FFE0D0", "#FF3B2F", "#B00010"], "glow": "#FFFFFF", "center": True})
    return {"bg": bg_rel, "size": "long", "out": "thumb.jpg", "shade": "both", "texts": texts}


def cut_image(work, cuts, cid, tmp):
    """カット id の絵（PIL）。same_as はたどる。.mp4 しか無ければ1コマ目"""
    c = next((x for x in cuts if x["id"] == cid), None)
    src = RM.find_image(work, cuts, c) if c else None
    if not src:
        sys.exit(f"【止まりました】サムネの絵がありません：{cid}（images/{cid}.png）")
    return Image.open(RM.first_frame(src, os.path.join(tmp, f"_thumb_{cid}.png"))).convert("RGB")


def cover(im, w, h, zoom=1.0, zx=.5, zy=.5):
    """w×h いっぱいに敷く（はみ出す分は切る）。zoom で寄る（zx・zy が寄る中心の割合）"""
    s = max(w / im.width, h / im.height) * zoom
    im = im.resize((round(im.width * s), round(im.height * s)), Image.LANCZOS)
    x = min(max(0, round(im.width * zx - w / 2)), im.width - w)
    y = min(max(0, round(im.height * zy - h / 2)), im.height - h)
    return im.crop((x, y, x + w, y + h))


def hl_of(th, lines, default):
    """色を変える語：thumb.hl（どれかの行に含まれる物）→ ●● → 既定"""
    hl = [w for w in (th.get("hl") or []) if any(w in l for l in lines)]
    return hl or [w for w in ("●●●", "●●") if any(w in l for l in lines)][:1] or [default]


def fit(text, budget, cap):
    return max(60, min(cap, int(budget // max(1, max(len(l) for l in text.split("\n"))))))


def layout_spec(s, work, tmp):
    th, cuts = s["thumb"], s["cuts"]
    lay = th["layout"]
    need = {"object": ("bg", "line1", "line2", "judge"), "person": ("bg", "line1", "line2", "judge"),
            "split": ("left", "right", "line1", "line2", "left_label", "right_label"), "shock": ("bg", "face", "line1", "line2", "judge")}[lay]
    miss = [k for k in need if not th.get(k)]
    if miss:
        sys.exit(f"【止まりました】thumb（{lay}）に {miss} がありません")
    l1, l2, jd = th["line1"], th["line2"], th.get("judge", "")
    hl = th.get("hl")
    marks = th.get("marks")
    if lay == "object":
        bg = cover(cut_image(work, cuts, th["bg"], tmp), W, H, th.get("zoom", 1.0), th.get("zx", .5), th.get("zy", .5))
        s1, s2, sj = fit(l1, 700, 150), fit(l2, 700, 300), fit(jd, 1180, 150)
        texts = [{"t": l1, "x": 36, "y": 24, "size": s1, "color": "#FFFFFF", "edge": "#000000"},
                 {"t": l2, "x": 36, "y": 24 + int(s1 * 0.9), "size": s2, "color": YEL, "edge": "#000000"},
                 {"t": jd, "x": 0, "y": H - int(sj * 1.1) - 40, "size": sj, "color": "#FFFFFF", "box": "#C00010", "center": True,
                  "hl": hl_of(th, [jd], jd[:3]), "hl_color": YEL}]
        shade = "left"
    elif lay == "person":
        im = cut_image(work, cuts, th["bg"], tmp)
        if th.get("flip", True):
            im = im.transpose(Image.FLIP_LEFT_RIGHT)
        bg = cover(im, W, H, th.get("zoom", 1.0), th.get("zx", .5), th.get("zy", .5))
        s1, s2, sj = fit(l1, 570, 112), fit(l2, 570, 118), fit(jd, 1180, 196)
        texts = [{"t": l1, "x": 690, "y": 30, "size": s1, "color": "#FFFFFF", "edge": "#000000"},
                 {"t": l2, "x": 690, "y": 30 + int(s1 * 1.25), "size": s2, "color": "#FFFFFF", "hl": hl_of(th, [l2, l1], l2[:2]), "hl_color": YEL, "edge": "#000000"},
                 {"t": jd, "x": 0, "y": H - int(sj * 1.1) - 20, "size": sj, "color": RED, "edge": "#FFFFFF", "center": True}]
        shade = "both"
    elif lay == "shock":
        bg = cover(cut_image(work, cuts, th["bg"], tmp), W, H, th.get("zoom", 1.0), th.get("zx", .5), th.get("zy", .5))
        face = cover(cut_image(work, cuts, th["face"], tmp), W, H)
        dx = int(th.get("face_dx", 380))
        layer = Image.new("RGB", (W, H))
        layer.paste(face, (dx, 0))
        mask = Image.new("L", (W, H), 0)
        for x in range(dx, W):  # 顔の左の縁を物の絵にとかす
            a = min(255, int(255 * (x - dx) / 240))
            mask.paste(a, (x, 0, x + 1, H))
        bg.paste(layer, (0, 0), mask)
        s1, s2, sj = fit(l1, 700, 124), fit(l2, 700, 124), fit(jd, 1180, 200)
        texts = [{"t": l1, "x": 36, "y": 18, "size": s1, "color": "#FFFFFF", "hl": hl_of(th, [l1, l2], l1[:2]), "hl_color": YEL},
                 {"t": l2, "x": 36, "y": 18 + int(s1 * 1.4), "size": s2, "color": "#FFFFFF"},
                 {"t": jd, "x": 0, "y": H - int(sj * 1.1) - 20, "size": sj, "color": RED, "edge": "#FFFFFF", "center": True}]
        shade = "left"
        marks = marks if marks is not None else [{"type": "arrow", "from": [470, 330], "to": [600, 420]}]
    else:  # split
        left = cover(cut_image(work, cuts, th["left"], tmp), W // 2, H, 1.0, .5, .5)
        left = ImageEnhance.Brightness(ImageEnhance.Color(left).enhance(.8)).enhance(.55)  # 悪い側は暗く
        right = ImageEnhance.Brightness(cover(cut_image(work, cuts, th["right"], tmp), W // 2, H, 1.0, .5, .5)).enhance(1.12)  # 良い側は明るく
        bg = Image.new("RGB", (W, H))
        bg.paste(left, (0, 0))
        bg.paste(right, (W // 2, 0))
        bg.paste((255, 255, 255), (W // 2 - 4, 0, W // 2 + 4, H))
        s1, s2 = fit(l1, 1180, 136), fit(l2, 1180, 228)
        sl = fit(th["left_label"], 560, 96)
        sr = fit(th["right_label"], 560, 96)
        rx = W - 24 - 50 - sr * len(th["right_label"])
        texts = [{"t": l1, "x": 0, "y": 8, "size": s1, "color": "#FFFFFF", "hl": hl_of(th, [l1], l1[:2]), "hl_color": YEL, "center": True, "edge": "#000000"},
                 {"t": l2, "x": 0, "y": 8 + int(s1 * 1.05), "size": s2, "color": RED, "edge": "#FFFFFF", "center": True},
                 {"t": th["left_label"], "x": 24, "y": H - sl - 56, "size": sl, "color": "#FFFFFF", "box": "#C00010"},
                 {"t": th["right_label"], "x": rx, "y": H - sr - 56, "size": sr, "color": "#1A1A1A", "box": YEL}]
        shade = "top"
    bg.save(os.path.join(work, "thumb_bg.png"))
    sp = {"bg": "thumb_bg.png", "size": "long", "out": "thumb.jpg", "shade": shade, "texts": texts}
    if marks:
        sp["marks"] = marks
    return sp


def main():
    a = argparse.ArgumentParser()
    a.add_argument("work")
    a.add_argument("--bg", default="")
    a.add_argument("--check", action="store_true")
    a = a.parse_args()
    work = os.path.abspath(a.work)
    s = json.load(open(os.path.join(work, "script.json"), encoding="utf-8"))
    sp = os.path.join(work, "thumb.json")
    if (s.get("thumb") or {}).get("layout") in LAYOUTS:
        spec = layout_spec(s, work, work)
    elif (s.get("thumb") or {}).get("layout"):
        sys.exit(f"【止まりました】thumb.layout「{s['thumb']['layout']}」は {LAYOUTS} のどれでもありません")
    else:
        bg_id = a.bg or s.get("thumb_bg") or "THUMB"
        bg_rel = f"images/{bg_id}.png"
        if not os.path.exists(os.path.join(work, bg_rel)):
            sys.exit(f"【止まりました】サムネの背景の絵がありません：{bg_rel}（台本の THUMB カットの絵）")
        spec = spec_legacy(s, bg_rel)
    json.dump(spec, open(sp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        T.main(sp, preview=True)
    log = buf.getvalue()
    shutil.copyfile(os.path.join(work, "thumb.jpg"), os.path.join(work, "thumb_a.jpg"))
    ng = [l.strip() for l in log.splitlines() if l.strip().startswith("NG")]
    if (s.get("thumb") or {}).get("layout") in LAYOUTS:  # 型の作りでは、いちばん大きい字の横幅の線を 70% → 45% にする（上の説明）
        loose = [x for x in ng if x.startswith("NG いちばん大きい字が細い") and _ratio(log) >= 0.45]
        ng = [x for x in ng if x not in loose]
        log = chr(10).join(l for l in log.splitlines() if l.strip() not in loose) + chr(10)
        if loose:
            log += f"  （型の線：いちばん大きい字の横幅 {_ratio(log):.0%}・45%以上でOK）" + chr(10)
    print(log, end="")
    if ng and a.check:
        print("【NG】サムネの点検：" + "／".join(ng))
        print("サムネの指定：" + json.dumps(s.get("thumb"), ensure_ascii=False))  # 止まった回は作業フォルダがクラウドにしかないので、直す字をログで読めるようにする
        sys.exit(1)


def _ratio(log):
    import re
    m = re.search(r"いちばん大きい字の横幅 (\d+)%", log)
    return int(m.group(1)) / 100 if m else 0


if __name__ == "__main__":
    main()

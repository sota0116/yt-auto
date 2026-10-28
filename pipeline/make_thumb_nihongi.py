# ⑨サムネ（アナザー日本紀の横動画・2026-10-29 新設。ショートはサムネを作らない）
#   python -X utf8 pipeline/make_thumb_nihongi.py <作業フォルダ> [--check]
# ・script.json の thumb {top, big, hl_top, hl_big, bg} から thumb.json を書き、動画スキルの make_thumb.py で thumb_a.jpg（1280x720）を作る（手順書 §7）
#   top＝上の段（ずらしたルール。2行まで。\n で改行）、big＝下の段（意外な結果を1行で横幅いっぱい）、hl_*＝色を変える語、bg＝背景のカットの id（山場の絵）
# ・字の大きさは、下の段が横幅の96%、上の段が最大の行で横幅の80%になるように測って決める。make_thumb.py の点検が NG なら終了コード1（--check の時。絵は保存される）
import argparse, json, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from nihongi_common import VENDOR, vendor_ok, vendor_run  # noqa: E402

W, H = 1280, 720


def fit(text, font_path, target):
    from PIL import ImageFont, Image, ImageDraw
    m = ImageDraw.Draw(Image.new("L", (1, 1)))
    lo, hi = 30, 400
    while hi - lo > 2:
        mid = (lo + hi) // 2
        f = ImageFont.truetype(font_path, mid)
        w = max(m.textlength(l, font=f) for l in text.split("\n"))
        lo, hi = (mid, hi) if w <= target else (lo, mid)
    return lo


def main():
    a = argparse.ArgumentParser()
    a.add_argument("work")
    a.add_argument("--check", action="store_true")
    a = a.parse_args()
    work = os.path.abspath(a.work)
    bad = vendor_ok()
    if bad:
        sys.exit(f"【止まりました】{bad}")
    s = json.load(open(os.path.join(work, "script.json"), encoding="utf-8"))
    t = s.get("thumb") or {}
    if not all(t.get(k) for k in ("top", "big", "bg")):
        sys.exit("【止まりました】script.json の thumb に top・big・bg がありません")
    bg = next((p for p in (f"images/{t['bg']}.png", f"images/{t['bg']}.jpg") if os.path.exists(os.path.join(work, p))), None)
    if not bg:
        sys.exit(f"【止まりました】サムネの背景の絵がありません：images/{t['bg']}.png")
    sys.path.insert(0, VENDOR)
    from common import load_config, font_file
    ff = font_file(load_config(work)["font_heavy"])
    big = min(fit(t["big"], ff, W * 0.96), 260)
    top = min(fit(t["top"], ff, W * 0.80), int(big * 0.75))
    n_top = len(t["top"].split("\n"))
    by = H - int(big * 1.25) - 28
    if 36 + n_top * (top + top // 6) > by:  # 上の段が下の段にかかる時は小さくする
        top = max(30, int(top * 0.8))
    spec = {"bg": bg, "size": "long", "out": "thumb_a.jpg", "shade": "both", "texts": [
        {"t": t["top"], "y": 36, "size": top, "center": True, "color": "#FFFFFF", "hl": [t["hl_top"]] if t.get("hl_top") else [],
         "hl_color": "#FFD83B", "glow": "#FFFFFF"},
        {"t": t["big"], "y": by, "size": big, "center": True, "color": "#FFFFFF", "hl": [t["hl_big"]] if t.get("hl_big") else [],
         "hl_color": ["#FFE0D0", "#FF3B2F", "#B00010"], "glow": "#FFFFFF"}]}
    json.dump(spec, open(os.path.join(work, "thumb.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    r = vendor_run("make_thumb.py", os.path.join(work, "thumb.json"), "--preview")
    print(r.stdout, r.stderr[-500:])
    if r.returncode or not os.path.exists(os.path.join(work, "thumb_a.jpg")):
        sys.exit("【止まりました】サムネが作れませんでした")
    if a.check and re.search(r"^\s+NG ", r.stdout, re.M):
        sys.exit(1)


if __name__ == "__main__":
    main()

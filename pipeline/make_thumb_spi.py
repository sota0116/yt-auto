# ⑨サムネ（千年こよみ spi・2026-10-29 新設）：run_daily.py の thumb の段から呼ぶ薄い包み。中身は make_thumb_koyomi_v3.py（手順書 §7 のサムネ v3）
#   python -X utf8 pipeline/make_thumb_spi.py <作業フォルダ> [--bg THUMB] [--check]
# ・script.json の thumb {top, big, hl, tag} と、背景のカット（--bg か script.json の thumb_bg。既定 THUMB）の絵 images/<id>.png から
#   作業フォルダ/thumb_b.json を書き、make_thumb_koyomi_v3.py で thumb_a.jpg（upload_job.py が上げる名前）と横320pxの小さい版を作る
# ・--check：点検（いちばん大きい字の横幅・字の面積・行数・色を変えた語・右下の再生時間の所）に NG があれば終了コード1（絵は保存される）
# ・make_thumb_koyomi_v3.py は読み込んだ時に Windows の字（NotoSansJP-VF.ttf）を探して、無いと止まる。
#   ここでは読み込む間だけ「ある」と答えさせ、字を選ぶ関数を、Windows は同じ VF の900、Linux は Noto Sans CJK JP Black（無ければ Bold）に差し替える
#   （make_thumb_koyomi_v3.py は書き換えない）
import argparse, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
WIN_VF = [r"C:\Windows\Fonts\NotoSansJP-VF.ttf", os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Windows\Fonts\NotoSansJP-VF.ttf")]
LINUX = ["/usr/share/fonts/opentype/noto/NotoSansCJK-Black.ttc", "/usr/share/fonts/noto-cjk/NotoSansCJK-Black.ttc",
         "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc", "/usr/share/fonts/noto-cjk/NotoSansCJK-Bold.ttc"]


def load_v3():
    real = os.path.exists
    os.path.exists = lambda p: True if str(p).endswith("NotoSansJP-VF.ttf") else real(p)
    try:
        import make_thumb_koyomi_v3 as T
    finally:
        os.path.exists = real
    from PIL import ImageFont
    vf = next((p for p in WIN_VF if os.path.exists(p)), None)
    if vf:
        def font(size):
            f = ImageFont.truetype(vf, size); f.set_variation_by_axes([900]); return f
    else:
        ttc = next((p for p in LINUX if os.path.exists(p)), None)
        if not ttc:
            sys.exit("【止まりました】サムネの字（NotoSansJP-VF.ttf か NotoSansCJK-Black/Bold.ttc）が見つかりません（Linux は fonts-noto-cjk を入れる）")
        def font(size):
            return ImageFont.truetype(ttc, size, index=0)  # ttc の0番目が JP
    T.font = font
    return T


def main():
    a = argparse.ArgumentParser()
    a.add_argument("work")
    a.add_argument("--bg", default=None)
    a.add_argument("--check", action="store_true")
    a = a.parse_args()
    work = os.path.abspath(a.work)
    s = json.load(open(os.path.join(work, "script.json"), encoding="utf-8"))
    th = s.get("thumb") or {}
    if not th.get("big"):
        sys.exit("【止まりました】script.json の thumb に big（下の段の字）がありません")
    bg = a.bg or s.get("thumb_bg") or "THUMB"
    bgp = next((os.path.join("images", bg + e) for e in (".png", ".jpg") if os.path.exists(os.path.join(work, "images", bg + e))), None)
    if not bgp:
        sys.exit(f"【止まりました】サムネの背景の絵 images/{bg}.png がありません（絵の段で THUMB のカットを作る）")
    spec = {"bg": bgp.replace("\\", "/"), "top": th.get("top"), "big": th["big"], "hl": th.get("hl") or [], "out": "thumb_a.jpg"}
    for k in ("tag", "focus", "box", "dark", "hl_color", "big_bottom"):
        if th.get(k) is not None:
            spec[k] = th[k]
    sp = os.path.join(work, "thumb_b.json")
    json.dump(spec, open(sp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    T = load_v3()
    out, ng = T.main(sp)
    print(f"サムネ：{out}（NG {len(ng)}件）")
    sys.exit(1 if (a.check and ng) else 0)


if __name__ == "__main__":
    main()

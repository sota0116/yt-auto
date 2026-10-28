# ⑨サムネ・長尺（金運おきぬ・2026-10-29 新設）：run_daily.py の thumb の段から呼ぶ薄い包み。中身はスキルの make_thumb.py（references/15 の2段の型）
#   python -X utf8 pipeline/make_thumb_okinu.py <作業フォルダ> [--bg THUMB] [--check]
# ・script.json の thumb {top（上の段）, big（下の段・1行・8字まで）, hl（色を変える語）} と、背景のカット（--bg か script.json の thumb_bg。既定 THUMB）の絵
#   images/<id>.png から thumb.json を書き、make_thumb.py で thumb.jpg を作る。thumb_a.jpg（アップロードの名前）と横320pxの thumb_small.jpg も置く
# ・手順書 §9：2段・合わせて4行まで・下の段は横幅7割以上（字の大きさは字数から決める）・要の1語だけ色を変える・下の段に光
# ・--check：make_thumb.py の点検に NG があれば終了コード1（絵は保存される）
import argparse, contextlib, io, json, os, shutil, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "vendor", "youtube-video-maker", "scripts"))
import make_thumb as T  # noqa: E402

W, H = 1280, 720


def spec(s, bg_rel):
    th = s.get("thumb") or {}
    top, big = (th.get("top") or "").strip(), (th.get("big") or "").strip()
    if not big:
        sys.exit("【止まりました】script.json に thumb.big（下の段の語）がありません")
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


def main():
    a = argparse.ArgumentParser()
    a.add_argument("work")
    a.add_argument("--bg", default="")
    a.add_argument("--check", action="store_true")
    a = a.parse_args()
    work = os.path.abspath(a.work)
    s = json.load(open(os.path.join(work, "script.json"), encoding="utf-8"))
    bg_id = a.bg or s.get("thumb_bg") or "THUMB"
    bg_rel = f"images/{bg_id}.png"
    if not os.path.exists(os.path.join(work, bg_rel)):
        sys.exit(f"【止まりました】サムネの背景の絵がありません：{bg_rel}（台本の THUMB カットの絵）")
    sp = os.path.join(work, "thumb.json")
    json.dump(spec(s, bg_rel), open(sp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        T.main(sp, preview=True)
    log = buf.getvalue()
    print(log, end="")
    shutil.copyfile(os.path.join(work, "thumb.jpg"), os.path.join(work, "thumb_a.jpg"))
    ng = [l.strip() for l in log.splitlines() if l.strip().startswith("NG")]
    if ng and a.check:
        print("【NG】サムネの点検：" + "／".join(ng))
        sys.exit(1)


if __name__ == "__main__":
    main()

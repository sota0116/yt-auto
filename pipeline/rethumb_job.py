# 上げ済みの長尺のサムネを、手順書 v4.0 §6 の新しい形に差し替える（2026-10-27 本人「差し替える（おすすめ）」）
#   python -X utf8 pipeline\rethumb_job.py export <出力フォルダ>
#   python -X utf8 pipeline\rethumb_job.py apply [--dry]
# ・作業フォルダはクラウドの actions/cache にしか無い回があるので、.github/workflows/rethumb.yml から動かす
# ・export：作業フォルダごとに script.json・facts.json と、登場人物（chars）がいるカットの絵を横640pxに縮めた jpg を出す（サムネの字と絵を選ぶ材料）
# ・apply：history/job/rethumb.json の works の項目（thumb_top・thumb_text・thumb_lines・thumb_band・thumb_q・thumb_bg）を script.json に足し、
#   make_thumb_job.py で a案・b案を作って（横320pxの読み取りの点検も）、video_id があれば a案を YouTube に送る。
#   b案は作業フォルダに残るので、見張り（watch.py）の72時間の差し替えで使われる。済んだ回は done に書き、2回目は飛ばす
import argparse, datetime, json, os, subprocess, sys
from PIL import Image
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VIDEOS = os.path.join(ROOT, "channels", "job", "videos")
REC = os.path.join(ROOT, "history", "job", "rethumb.json")
KEYS = ("thumb_top", "thumb_text", "thumb_lines", "thumb_band", "thumb_q", "thumb_bg")


def export(out):
    os.makedirs(out, exist_ok=True)
    listing = []
    for w in sorted(os.listdir(VIDEOS)):
        sp = os.path.join(VIDEOS, w, "script.json")
        if not os.path.exists(sp):
            continue
        s = json.load(open(sp, encoding="utf-8"))
        o = os.path.join(out, w)
        os.makedirs(o, exist_ok=True)
        for n in ("script.json", "facts.json"):
            if os.path.exists(os.path.join(VIDEOS, w, n)):
                open(os.path.join(o, n), "wb").write(open(os.path.join(VIDEOS, w, n), "rb").read())
        n = 0
        pics = [c for c in s.get("cuts", []) if c.get("image") and not c.get("chart") and not c.get("same_as")]
        has_chars = any(c.get("chars") for c in pics)  # chars の印が無い古い回（2026-10-25 より前）は場面の絵を全部出す
        for c in pics:
            p = os.path.join(VIDEOS, w, "images", f"{c['id']}.png")
            if (c.get("chars") or not has_chars) and os.path.exists(p):
                im = Image.open(p).convert("RGB")
                im.resize((640, int(640 * im.height / im.width))).save(os.path.join(o, f"{c['id']}.jpg"), quality=80)
                n += 1
        listing.append({"work": w, "type": s.get("type"), "frame": s.get("frame"), "人の絵": n,
                        "thumb_b": os.path.exists(os.path.join(VIDEOS, w, "thumb_b.jpg"))})
    json.dump(listing, open(os.path.join(out, "_一覧.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps(listing, ensure_ascii=False, indent=1))


def apply(dry):
    rec = json.load(open(REC, encoding="utf-8"))
    done = rec.setdefault("done", {})
    bad = []
    for e in rec["works"]:
        w = e["work"]
        if w in done:
            print(w, "済み（", done[w]["日時"], "）")
            continue
        work = os.path.join(VIDEOS, w)
        sp = os.path.join(work, "script.json")
        if not os.path.exists(sp):
            bad.append(f"{w}：作業フォルダがキャッシュに無い")
            continue
        s = json.load(open(sp, encoding="utf-8"))
        s.update({k: e[k] for k in KEYS if k in e})
        if "thumb_lines" not in e:  # 前の形の割り方が残っていると、新しい thumb_text とつながらずに止まる
            s.pop("thumb_lines", None)
        json.dump(s, open(sp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        r = subprocess.run([sys.executable, "-X", "utf8", os.path.join(ROOT, "pipeline", "make_thumb_job.py"), work, "--check"],
                           capture_output=True, text=True, encoding="utf-8")
        print(w, r.stdout.strip(), r.stderr.strip()[-600:])
        if r.returncode != 0:
            bad.append(f"{w}：サムネを作れなかったか、320pxで読めなかった")
            continue
        note = "作った"
        if e.get("video_id") and not dry:
            from upload_job import api
            api("job", "POST", f"https://www.googleapis.com/upload/youtube/v3/thumbnails/set?videoId={e['video_id']}",
                open(os.path.join(work, "thumb_a.jpg"), "rb").read(), {"Content-Type": "image/jpeg"}, timeout=120)
            note = "a案を YouTube に送った"
        print(w, note)
        if not dry:
            done[w] = {"日時": datetime.datetime.now().isoformat(timespec="seconds"), "内容": note}
    if not dry:
        json.dump(rec, open(REC, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    if bad:
        sys.exit("【止まりました】" + "／".join(bad))


def main():
    a = argparse.ArgumentParser()
    a.add_argument("mode", choices=["export", "apply"])
    a.add_argument("out", nargs="?", default="_rethumb")
    a.add_argument("--dry", action="store_true")
    a = a.parse_args()
    export(a.out) if a.mode == "export" else apply(a.dry)


if __name__ == "__main__":
    main()

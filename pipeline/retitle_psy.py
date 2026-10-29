# 上げ済みの長尺の題とサムネを、手順書 v4.0 §6 の型（競合の伸びた「〇〇な人」型）に差し替える（心理学ch・2026-10-29 本人「全部OK」）
#   python -X utf8 pipeline\retitle_psy.py [--dry]
# ・history/psy/retitle.json の works ごとに、題を titles[0] にし、サムネを history/psy/rethumb/<回>/thumb_a.jpg にする
# ・説明・タグ・カテゴリ・言語は今の値をそのまま送り返す（送らなかった項目は消えるため。watch.py の swap と同じ）
# ・uploaded.json の title・titles・thumb も新しくする（見張りが差し替えに titles[1] を使い、B案は rethumb/<回>/thumb_b.jpg を読む）
# ・済んだ回は done に書き、2回目は飛ばす
import argparse, datetime, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from upload_job import api, API  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REC = os.path.join(ROOT, "history", "psy", "retitle.json")
UP = os.path.join(ROOT, "history", "psy", "uploaded.json")
THUMBS = os.path.join(ROOT, "history", "psy", "rethumb")


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--dry", action="store_true")
    a = a.parse_args()
    rec = json.load(open(REC, encoding="utf-8"))
    up = json.load(open(UP, encoding="utf-8"))
    for w in rec["works"]:
        if w["work"] in rec["done"]:
            print(f"{w['work']}：済み")
            continue
        tb = os.path.join(THUMBS, w["work"], "thumb_a.jpg")
        if not os.path.exists(tb):
            sys.exit(f"【止まりました】サムネがありません：{tb}")
        it = json.load(api("psy", "GET", f"{API}/videos?part=snippet&id={w['video_id']}", timeout=60))["items"][0]
        sn = {k: it["snippet"][k] for k in ("title", "description", "categoryId", "defaultLanguage", "defaultAudioLanguage")
              if k in it["snippet"]}
        print(f"{w['work']}：「{sn['title']}」→「{w['titles'][0]}」")
        if a.dry:
            continue
        sn.update(title=w["titles"][0], tags=it["snippet"].get("tags", []))
        api("psy", "PUT", f"{API}/videos?part=snippet", {"id": w["video_id"], "snippet": sn}, timeout=60)
        api("psy", "POST", f"https://www.googleapis.com/upload/youtube/v3/thumbnails/set?videoId={w['video_id']}",
            open(tb, "rb").read(), {"Content-Type": "image/jpeg"}, timeout=120)
        e = next((e for e in up if e.get("video_id") == w["video_id"]), None)
        if e is not None:
            e.update(title=w["titles"][0], titles=w["titles"], title_now=w["titles"][0], thumb_lines=w["thumb"],
                     thumb=os.path.relpath(tb, ROOT).replace("\\", "/"))
            # swaps には足さない（見張りは swaps の数で次の差し替えの番号を決める。titles[1] から使わせる）
            e["retitled"] = {"日時": datetime.datetime.now().isoformat(timespec="seconds"), "内容": "手順書 v4.0 の型へ題とサムネを差し替え"}
        rec["done"].append(w["work"])
        json.dump(rec, open(REC, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        json.dump(up, open(UP, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("  題とサムネを送りました")


if __name__ == "__main__":
    main()

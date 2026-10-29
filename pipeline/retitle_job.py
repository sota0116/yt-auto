# 上げ済みの長尺のタイトルを、手順書 v5.3 §6 の形（1文の謎・判定・自分ごと。出典・作り方を書かない）に差し替える（仕事ch・2026-10-30 本人「タイトルがへたくそすぎる」「（厚生労働省の統計）こういうのいらない」）
#   python -X utf8 pipeline\retitle_job.py [--dry]
# ・history/job/retitle.json の works ごとに、タイトルを titles[0] にする。サムネは変えない
# ・説明・タグ・カテゴリ・言語は今の値をそのまま送り返す（送らなかった項目は消えるため。watch.py の swap と同じ）
# ・uploaded.json の title・titles・title_now も新しくする（見張りの72時間後の差し替えは titles[1]、2回目は titles[2] を使う）
# ・済んだ回は done に書き、2回目は飛ばす
import argparse, datetime, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from upload_job import api, API  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REC = os.path.join(ROOT, "history", "job", "retitle.json")
UP = os.path.join(ROOT, "history", "job", "uploaded.json")


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--dry", action="store_true")
    a = a.parse_args()
    rec = json.load(open(REC, encoding="utf-8"))
    up = json.load(open(UP, encoding="utf-8"))
    for w in rec["works"]:
        if w["video_id"] in rec["done"]:
            print(f"{w['work']}：済み")
            continue
        items = json.load(api("job", "GET", f"{API}/videos?part=snippet,status&id={w['video_id']}", timeout=60))["items"]
        if not items:
            print(f"{w['work']}：YouTube に見つからないので飛ばした（{w['video_id']}）")
            continue
        it = items[0]
        sn = {k: it["snippet"][k] for k in ("title", "description", "categoryId", "defaultLanguage", "defaultAudioLanguage")
              if k in it["snippet"]}
        print(f"{w['work']}（{it['status'].get('privacyStatus')}・{it['status'].get('publishAt', '公開日なし')}）：\n  「{sn['title']}」\n→「{w['titles'][0]}」")
        if a.dry:
            continue
        sn.update(title=w["titles"][0], tags=it["snippet"].get("tags", []))
        api("job", "PUT", f"{API}/videos?part=snippet", {"id": w["video_id"], "snippet": sn}, timeout=60)
        for e in up:
            if e.get("video_id") == w["video_id"]:
                # swaps には足さない（見張りは swaps の数で次の差し替えの番号を決める。titles[1] から使わせる）
                e.update(title=w["titles"][0], titles=w["titles"], title_now=w["titles"][0])
                e["retitled"] = {"日時": datetime.datetime.now().isoformat(timespec="seconds"), "内容": "手順書 v5.3 の形へタイトルを差し替え"}
        rec["done"].append(w["video_id"])
        json.dump(rec, open(REC, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        json.dump(up, open(UP, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("  タイトルを送りました")


if __name__ == "__main__":
    main()

# 予約済みのショートを取り下げる（手順書 §12）：予約を外して非公開のままにする。動画は消さない（戻せる。消すのは本人）
#   python -X utf8 pipeline/short_unschedule.py <video_id> --why "取り下げる理由"
# ・Actions の shorts で動かす（入力 pull_video。手元で鍵を読まない）
# ・もう公開された動画には触らない。予約が外れたことを読み直して確かめてから記録を直す
# ・記録：shorts_uploaded.json の回に "retired": true（short_learn.py が数字を取らない）、
#   shorts.json の回を ok: false（routine_pick.py がその職業をまた選べる。失敗2回で飛ばす）
import argparse, datetime, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from upload_job import API, ROOT, api

JST = datetime.timezone(datetime.timedelta(hours=9))
H = lambda n: os.path.join(ROOT, "history", "job", n)


def status_of(vid):
    items = json.load(api("job", "GET", f"{API}/videos?part=status&id={vid}", timeout=60)).get("items", [])
    if not items:
        sys.exit(f"【止まりました】{vid} がチャンネルにありません")
    return items[0]["status"]


def save(path, data):
    json.dump(data, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("video_id")
    p.add_argument("--why", required=True)
    a = p.parse_args()
    up, made = json.load(open(H("shorts_uploaded.json"), encoding="utf-8")), json.load(open(H("shorts.json"), encoding="utf-8"))
    rec = next((e for e in up if e["video_id"] == a.video_id), None)
    if not rec:
        sys.exit(f"【止まりました】{a.video_id} はショートの記録にありません")
    if rec.get("retired"):
        print(f"{a.video_id} はもう取り下げてあります")
        return
    st = status_of(a.video_id)
    if st.get("privacyStatus") != "private":
        sys.exit(f"【止まりました】{a.video_id} はもう {st.get('privacyStatus')} です。公開済みは触りません")
    body = {"privacyStatus": "private", "selfDeclaredMadeForKids": False, "containsSyntheticMedia": True, "embeddable": True,
            "publicStatsViewable": True, "license": st.get("license", "youtube")}
    api("job", "PUT", f"{API}/videos?part=status", {"id": a.video_id, "status": body}, timeout=60)
    st = status_of(a.video_id)
    if st.get("publishAt") or st.get("privacyStatus") != "private":
        sys.exit(f"【止まりました】予約が外れていません：{st.get('privacyStatus')} {st.get('publishAt')}")
    rec.update({"retired": True, "retired_why": a.why, "retired_at": datetime.datetime.now(JST).isoformat(timespec="seconds")})
    for m in made:
        if m["work"] == rec["work"]:
            m.update({"ok": False, "why": a.why})
    save(H("shorts_uploaded.json"), up)
    save(H("shorts.json"), made)
    print(f"取り下げました：{a.video_id}（{rec['work']}）は非公開のまま、予約なし")


if __name__ == "__main__":
    main()

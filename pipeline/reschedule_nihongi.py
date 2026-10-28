# アナザー日本紀（nihongi）の予約の時刻を変える／予約を外して旧版にする（2026-10-28 本人「今日載せてよ」で L001 を前倒しした時に作った）
#   python -X utf8 pipeline\reschedule_nihongi.py <動画ID> --at 2026-10-28T20:00 [--go]
#   python -X utf8 pipeline\reschedule_nihongi.py <動画ID> --retire "理由" [--prefix 【旧版】] [--go]
# ・--go を付けた時だけ変える（付けない時は、今の状態と変えた後を出すだけ）
# ・触るのは「非公開で予約中」か「非公開・予約なし」の動画だけ。公開済みの動画は止まる
# ・--at：publishAt を変える。記録（shorts_uploaded.json / long_uploaded.json）の publish_at も直す
#   横動画を、横動画がもう入っている日へ動かそうとしたら止まる（long_day_guard.py。2026-10-29）
# ・--retire：予約を外して非公開のまま、題の頭に --prefix を付け、記録に "retired": true。消すのは本人
# ・status を書き直す時は、上げた時と同じ項目（AI の申告オン・子ども向けでない）を全部入れる（入れないと既定に戻るため）
import argparse, datetime, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from upload_job import api, API
import long_day_guard

CH = "nihongi"
JST = datetime.timezone(datetime.timedelta(hours=9))
HIST = [r"C:\yt-auto\history\nihongi\shorts_uploaded.json", r"C:\yt-auto\history\nihongi\long_uploaded.json"]


def get(vid):
    items = json.load(api(CH, "GET", f"{API}/videos?part=snippet,status&id={vid}", timeout=60)).get("items", [])
    if not items:
        sys.exit(f"【止まりました】{vid} が見つかりません")
    return items[0]


def status_body(publish_at):
    st = {"privacyStatus": "private", "selfDeclaredMadeForKids": False, "containsSyntheticMedia": True,
          "embeddable": True, "license": "youtube"}
    if publish_at:
        st["publishAt"] = publish_at
    return st


def fix_hist(vid, **kw):
    for p in HIST:
        if not os.path.exists(p):
            continue
        hist = json.load(open(p, encoding="utf-8"))
        hit = [h for h in hist if h.get("video_id") == vid]
        for h in hit:
            h.update(kw)
        if hit:
            json.dump(hist, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
            print("記録を直しました：", os.path.basename(p))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("vid"); ap.add_argument("--at"); ap.add_argument("--retire"); ap.add_argument("--prefix", default="【旧版】")
    ap.add_argument("--go", action="store_true")
    a = ap.parse_args()
    if bool(a.at) == bool(a.retire):
        sys.exit("--at か --retire のどちらか1つを付けてください")
    it = get(a.vid)
    sn, st = it["snippet"], it["status"]
    print("今：", st["privacyStatus"], st.get("publishAt"), sn["title"])
    if st["privacyStatus"] != "private":
        sys.exit("【止まりました】公開済み・限定公開の動画は触りません")
    now = datetime.datetime.now(JST)
    if a.at:
        at = datetime.datetime.fromisoformat(a.at).replace(tzinfo=JST)
        if at < now + datetime.timedelta(minutes=30):
            sys.exit("【止まりました】30分より先の時刻にしてください")
        long_day_guard.check_vid(CH, a.vid, at)  # 横動画は同じ日に2本以上出さない（2026-10-29）
        utc = at.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        print("変えた後：公開予定", at.isoformat())
        if not a.go:
            return print("（--go が無いので変えません）")
        api(CH, "PUT", f"{API}/videos?part=status", {"id": a.vid, "status": status_body(utc)}, timeout=60)
        fix_hist(a.vid, publish_at=at.isoformat())
    else:
        title = sn["title"] if sn["title"].startswith(a.prefix) else (a.prefix + sn["title"])[:100]
        print("変えた後：予約なし・非公開／題", title)
        if not a.go:
            return print("（--go が無いので変えません）")
        api(CH, "PUT", f"{API}/videos?part=status", {"id": a.vid, "status": status_body(None)}, timeout=60)
        if title != sn["title"]:
            body = {"id": a.vid, "snippet": {"title": title, "description": sn.get("description", ""), "tags": sn.get("tags", []),
                                             "categoryId": sn["categoryId"], "defaultLanguage": sn.get("defaultLanguage", "ja"),
                                             "defaultAudioLanguage": sn.get("defaultAudioLanguage", "ja")}}
            api(CH, "PUT", f"{API}/videos?part=snippet", body, timeout=60)
        fix_hist(a.vid, retired=True, publish_at=None, retired_at=now.isoformat(timespec="seconds"), retired_reason=a.retire)
    it = get(a.vid)
    print("読み直し：", it["status"]["privacyStatus"], it["status"].get("publishAt"), it["snippet"]["title"])


if __name__ == "__main__":
    main()

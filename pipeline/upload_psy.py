# しずくの心理学（psy）の1本を上げる（手で作った動画を Claude が上げる。毎日の制作には入っていない）
#   python -X utf8 pipeline\upload_psy.py <作業フォルダ> --up upload_v7 --video long_v3.mp4 --thumb thumb_v2.jpg [--publish-at 2026-10-27T19:00:00+09:00] [--dry]
# ・タイトル・説明・タグは <作業フォルダ>\<--up>\script.json、公開後のコメントは <--up>\comment.txt（見張り watch.py が公開後に入れる）
# ・15分を超える動画は、チャンネルの「長い動画」が allowed の時だけ上げる（電話番号の確認前に上げた1本目が消えた。2026-10-26）
# ・上げた後、動画が残っていて断られていないかを数分見張る。消えた・断られた時は理由を出して止まる
# ・非公開で上げる。--publish-at を付けるとその日時に公開の予約。AI の申告はオン、子ども向けではない
# ・記録：<作業フォルダ>\<--up>\uploaded.json と history\psy\uploaded.json（watch.py が読む）
import argparse, datetime, json, os, subprocess, sys, time, urllib.error
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from upload_job import api, API, channel_titles

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CH = "psy"
JST = datetime.timezone(datetime.timedelta(hours=9))


def get(url):
    return json.load(api(CH, "GET", url, timeout=60))


def seconds(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                         capture_output=True, text=True).stdout.strip()
    return float(out or 0)


def check_after(vid, tries=10, wait=30):
    """上げた動画が残っているか。処理が終わるか、消えた・断られたと分かるまで見る"""
    for _ in range(tries):
        items = get(f"{API}/videos?part=status,processingDetails&id={vid}").get("items", [])
        if not items:
            return "消えました（チャンネルに見当たらない）"
        st = items[0]["status"]
        if st.get("uploadStatus") in ("rejected", "failed", "deleted"):
            return f"{st['uploadStatus']}：{st.get('rejectionReason') or st.get('failureReason')}"
        if items[0].get("processingDetails", {}).get("processingStatus") == "succeeded":
            return None
        time.sleep(wait)
    return None  # 処理中のまま。消えてはいない


def main():
    a = argparse.ArgumentParser()
    a.add_argument("work")
    a.add_argument("--up", required=True)
    a.add_argument("--video", required=True)
    a.add_argument("--thumb", required=True)
    a.add_argument("--publish-at")
    a.add_argument("--dry", action="store_true")
    a = a.parse_args()
    work = os.path.abspath(a.work)
    upd = os.path.join(work, a.up)
    s = json.load(open(os.path.join(upd, "script.json"), encoding="utf-8"))
    comment = open(os.path.join(upd, "comment.txt"), encoding="utf-8").read().strip()
    video, thumb = os.path.join(work, a.video), os.path.join(work, a.thumb)
    for p in (video, thumb):
        if not os.path.exists(p):
            sys.exit(f"【止まりました】ファイルがありません：{p}")
    title, desc = s["title"], s["desc"]
    if len(title) > 100 or len(desc) > 5000 or any(c in title + desc for c in "<>"):
        sys.exit("【止まりました】タイトルか説明が長すぎるか、< > が入っています")
    hp = os.path.join(ROOT, "history", CH, "uploaded.json")
    hist = json.load(open(hp, encoding="utf-8")) if os.path.exists(hp) else []
    name = os.path.basename(work)
    if any(h["work"] == name and not h.get("retired") and not h.get("missing") for h in hist):
        sys.exit(f"【止めました】{name} はもう上げてあります（history\\psy\\uploaded.json）")
    sec = seconds(video)
    long_ok = get(f"{API}/channels?part=status&mine=true")["items"][0]["status"].get("longUploadsStatus")
    print(f"動画 {sec / 60:.1f}分・{os.path.getsize(video) / 1e6:.0f}MB｜長い動画の許可：{long_ok}")
    if sec > 15 * 60 and long_ok != "allowed":
        sys.exit("【止まりました】15分を超える動画は、チャンネルの電話番号の確認が済むまで上げられません（https://www.youtube.com/verify）")
    if a.dry:
        print("（--dry なので上げません）", title)
        return
    if title in channel_titles(CH):
        sys.exit("【止めました】チャンネルに同じタイトルの動画があります（二重アップの防止）")
    status = {"privacyStatus": "private", "selfDeclaredMadeForKids": False, "containsSyntheticMedia": True,
              "embeddable": True, "publicStatsViewable": True, "license": "youtube"}
    if a.publish_at:
        status["publishAt"] = a.publish_at
    meta = {"snippet": {"title": title, "description": desc, "tags": s.get("tags", []), "categoryId": s.get("category", "27"),
                        "defaultLanguage": "ja", "defaultAudioLanguage": "ja"}, "status": status}
    r = api(CH, "POST", "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status", meta,
            {"X-Upload-Content-Type": "video/mp4", "X-Upload-Content-Length": str(os.path.getsize(video))}, timeout=120)
    with open(video, "rb") as f:
        d = json.load(api(CH, "PUT", r.headers["Location"], f.read(), {"Content-Type": "video/mp4"}))
    vid = d["id"]
    print("上げました：", f"https://youtu.be/{vid}", "｜状態", d["status"].get("privacyStatus"), "｜公開予定", d["status"].get("publishAt"))
    thumb_ok = True
    try:
        api(CH, "POST", f"https://www.googleapis.com/upload/youtube/v3/thumbnails/set?videoId={vid}", open(thumb, "rb").read(),
            {"Content-Type": "image/jpeg"}, timeout=120)
        print("サムネを付けました")
    except urllib.error.HTTPError as e:
        thumb_ok = False
        print("【メモ】サムネを付けられませんでした：", e.code)
    rec = {"work": name, "video_id": vid, "title": title, "video": a.video, "privacy": "private", "thumb": a.thumb,
           "thumb_set": thumb_ok, "publish_at": a.publish_at,
           "uploaded_at": datetime.datetime.now(JST).isoformat(timespec="seconds"),
           "type": "psy", "titles": [title], "comment": comment}
    json.dump(rec, open(os.path.join(upd, "uploaded.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    os.makedirs(os.path.dirname(hp), exist_ok=True)
    json.dump(hist + [rec], open(hp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    bad = check_after(vid)
    if bad:
        sys.exit(f"【止まりました】上げた動画が {bad}。history\\psy\\uploaded.json の {vid} は見張りが missing にします")
    print("上げた動画が残っていることを確かめました")


if __name__ == "__main__":
    main()

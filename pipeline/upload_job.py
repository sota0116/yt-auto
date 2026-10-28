# ⑪アップ（設計書 §5⑪・手順書 §7）：完成した動画を YouTube に上げて在庫に入れる
#   python -X utf8 pipeline\upload_job.py <作業フォルダ> --channel job [--privacy private|unlisted] [--thumb thumb_a.jpg] [--dry]
# ・説明文は script.json の desc。{LINE_URL} は profile.json の line_url、{CHAPTERS} は chapters.txt に置き換える
# ・声が VOICEVOX の回は、voice\_credit.txt のクレジット（例：音声：VOICEVOX:雀松朱司）を説明文の最後に足す
# ・「AIで作った映像・声」の申告（containsSyntheticMedia）はいつもオン
# ・二重に上げない：history\<ch>\uploaded.json に同じ作業フォルダがある時と、チャンネルに同じタイトルの動画がある時は上げない
# ・上げた結果は 作業フォルダ\uploaded.json と history\<ch>\uploaded.json
# ・公開後のコメント：profile.json に comment_text があればそれ（{LINE_URL} を置き換え。心理学ch 2026-10-27）、無ければ説明文の1段落目
# ・--dry：上げずに、説明文とタイトルと確かめの結果だけ出す
import argparse, datetime, json, os, sys, urllib.error, urllib.parse, urllib.request
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from yt_auth import access_token

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
API = "https://www.googleapis.com/youtube/v3"


def api(ch, method, url, body=None, headers=None, timeout=900):
    h = {"Authorization": "Bearer " + access_token(ch), **(headers or {})}
    data = json.dumps(body).encode() if isinstance(body, dict) else body
    if isinstance(body, dict):
        h["Content-Type"] = "application/json; charset=UTF-8"
    return urllib.request.urlopen(urllib.request.Request(url, data, h, method=method), timeout=timeout)


def description(work, ch):
    s = json.load(open(os.path.join(work, "script.json"), encoding="utf-8"))
    prof = json.load(open(os.path.join(ROOT, "channels", ch, "profile.json"), encoding="utf-8"))
    chp = os.path.join(work, "chapters.txt")
    chapters = open(chp, encoding="utf-8").read().strip() if os.path.exists(chp) else ""
    d = s["desc"].replace("{LINE_URL}", prof["line_url"]).replace("{CHAPTERS}", chapters)
    left = [k for k in ("{LINE_URL}", "{CHAPTERS}") if k in d]
    if left or not chapters:
        sys.exit(f"【止まりました】説明文の置き換えが残っています：{left or 'chapters.txt が無い'}")
    cr = os.path.join(work, "voice", "_credit.txt")  # VOICEVOX の声はクレジットが必須（キャラの規約）。make_voice_vv.py が書く
    if os.path.exists(cr):
        credit = open(cr, encoding="utf-8").read().strip()
        if credit and credit not in d:
            d = d.rstrip() + "\n\n" + credit
    if "PR" in d:
        sys.exit("【止まりました】説明文に PR の文字があります（PR は LINE の中のアフィのリンクだけ。手順書 §10）")
    return s, d.strip()


def channel_titles(ch):
    d = json.load(api(ch, "GET", f"{API}/channels?part=contentDetails&mine=true", timeout=60))
    pl = d["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
    titles, tok = [], ""
    while True:
        r = json.load(api(ch, "GET", f"{API}/playlistItems?part=snippet&maxResults=50&playlistId={pl}{tok}", timeout=60))
        titles += [it["snippet"]["title"] for it in r.get("items", [])]
        if not r.get("nextPageToken"):
            return titles
        tok = "&pageToken=" + r["nextPageToken"]


def main():
    a = argparse.ArgumentParser()
    a.add_argument("work")
    a.add_argument("--channel", required=True, choices=["job", "spi", "psy", "nihongi", "okinu"])
    a.add_argument("--privacy", default="private", choices=["private", "unlisted"])
    a.add_argument("--video", default="long.mp4")
    a.add_argument("--thumb", default="thumb_a.jpg")
    a.add_argument("--dry", action="store_true")
    a = a.parse_args()
    ch, work = a.channel, os.path.abspath(a.work)
    s, desc = description(work, ch)
    title = s["title"]
    video, thumb = os.path.join(work, a.video), os.path.join(work, a.thumb)
    for p in (video, thumb):
        if not os.path.exists(p):
            sys.exit(f"【止まりました】ファイルがありません：{p}")
    if len(title) > 100:
        sys.exit(f"【止まりました】タイトルが100字を超えています（{len(title)}字）")
    hp = os.path.join(ROOT, "history", ch, "uploaded.json")
    hist = json.load(open(hp, encoding="utf-8")) if os.path.exists(hp) else []
    name = os.path.basename(work)
    if any(h["work"] == name and not h.get("retired") for h in hist):  # retired＝差し替えた古い版
        sys.exit(f"【止めました】{name} はもう上げてあります（history の uploaded.json）")
    print("タイトル：", title)
    print("説明文：\n" + desc)
    if a.dry:
        print(f"（--dry なので上げません。動画 {os.path.getsize(video) / 1e6:.0f}MB・{a.privacy}）")
        return
    if title in channel_titles(ch):
        sys.exit("【止めました】チャンネルに同じタイトルの動画があります（二重アップの防止）")
    status = {"privacyStatus": a.privacy, "selfDeclaredMadeForKids": False, "containsSyntheticMedia": True}
    meta = {"snippet": {"title": title, "description": desc, "tags": s.get("tags", []), "categoryId": "27",
                        "defaultLanguage": "ja", "defaultAudioLanguage": "ja"}, "status": status}
    size = os.path.getsize(video)
    r = api(ch, "POST", "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status", meta,
            {"X-Upload-Content-Type": "video/mp4", "X-Upload-Content-Length": str(size)}, timeout=120)
    with open(video, "rb") as f:
        d = json.load(api(ch, "PUT", r.headers["Location"], f.read(), {"Content-Type": "video/mp4"}))
    vid = d["id"]
    print("上げました：", f"https://youtu.be/{vid}", "｜状態", d["status"].get("privacyStatus"))
    thumb_ok = True
    try:
        api(ch, "POST", f"https://www.googleapis.com/upload/youtube/v3/thumbnails/set?videoId={vid}", open(thumb, "rb").read(),
            {"Content-Type": "image/jpeg"}, timeout=120)
        print("サムネを付けました")
    except urllib.error.HTTPError as e:
        thumb_ok = False
        print("【メモ】サムネを付けられませんでした（電話番号の確認が済んでいないと付けられない）：", e.code)
    prof = json.load(open(os.path.join(ROOT, "channels", ch, "profile.json"), encoding="utf-8"))
    comment = (prof.get("comment_text") or "").replace("{LINE_URL}", prof.get("line_url", "")) or desc.split("\n\n")[0].strip()
    rec = {"work": name, "video_id": vid, "title": title, "privacy": a.privacy, "thumb": a.thumb, "thumb_set": thumb_ok,
           "uploaded_at": datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).isoformat(timespec="seconds"),
           "requested_privacy": a.privacy, "privacy_after_upload": d["status"].get("privacyStatus"),
           # 見張り（watch.py）が使う：公開後のコメント（説明文の1段落目＝LINE の案内とリンク）と、差し替え用のタイトル案
           "type": s.get("type"), "titles": s.get("titles", [title]), "comment": comment}
    json.dump(rec, open(os.path.join(work, "uploaded.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    os.makedirs(os.path.dirname(hp), exist_ok=True)
    json.dump(hist + [rec], open(hp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()

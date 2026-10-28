# アナザー日本紀（nihongi）のショートを上げて、公開の予約を入れる（upload_okinu.py・short_upload.py を写した物。2026-10-27）
#   python -X utf8 pipeline\upload_nihongi.py <作業フォルダ> --video S001_裏切り確率_v3_文字を真ん中.mp4 [--at 2026-10-28T19:00] [--go]
# ・--go を付けた時だけ上げる（付けない時は、タイトル・説明文・予約の時刻・確かめの結果だけ出す）
# ・--at が無い時は、毎日の枠（SLOTS：18:00・21:00）のうち、まだ予約が入っていない一番近い枠に入れる（今から1時間より後）
#   1日3本の日は --three で昼の 12:10 も使う
# ・横動画（長尺）は --long --thumb thumb.jpg --at 2026-10-29T20:00（2026-10-28 足した）。1920x1080・8分以上を確かめ、
#   作業フォルダの chapters.txt を説明文の最後に足し、サムネを付ける。記録は history\nihongi\long_uploaded.json（ショートの枠には数えない）
#   同じ日に横動画がもう入っていれば止まる（long_day_guard.py。2026-10-29 本人「横動画は同じ日に2本以上は載せない」）
# ・作り直して上げ直す時は、古い記録に "retired": true を付ける（付けた記録は二重アップの確かめと枠から外す）
# ・タイトル・説明・タグは <作業フォルダ>\script.json。説明文に VOICEVOX のクレジットと AI の1文が無ければ止まる
# ・上げる前に、ログインしているチャンネルが アナザー日本紀（CH_ID）かを確かめる（同じアカウントに別のチャンネルがあるため）
# ・非公開で上げて publishAt で公開の予約。AI の申告（containsSyntheticMedia）はオン、子ども向けではない
# ・二重に上げない：history\nihongi\shorts_uploaded.json に同じ作業フォルダがある時と、チャンネルに同じタイトルがある時
# ・上げた後、動画が残っていて断られていないかを数分見張る
import argparse, datetime, json, os, subprocess, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from upload_job import ROOT, api, API, channel_titles
import long_day_guard

CH = "nihongi"
CH_ID = "UCPUDU140U5U8xXWYFLPHZKg"
JST = datetime.timezone(datetime.timedelta(hours=9))
# 毎日の公開の枠（日本時間）。競合の歴史ショートは 18〜21時の更新が多い（設計\チャンネル看板_アナザー日本紀_v1）
# 2026-10-28：夜を主にする。ふだんは 18:00・21:00 の1日2本。昼の 12:10 は 1日3本にする日だけ（--three）
SLOTS = ["18:00", "21:00"]
EXTRA = "12:10"
CREDIT = "VOICEVOX:青山龍星"


def get(url):
    return json.load(api(CH, "GET", url, timeout=60))


def probe(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height:format=duration",
                          "-of", "json", path], capture_output=True, text=True).stdout
    j = json.loads(out or "{}")
    st = (j.get("streams") or [{}])[0]
    return float(j.get("format", {}).get("duration", 0)), st.get("width"), st.get("height")


def up1440(video, w, h):
    """1080p の動画を 1440p に引き上げた写しを作って返す（2026-10-28 本人「画質が粗い」）。
    YouTube は 1080p の動画を約1〜3Mbps に圧縮し直していた（手元は4〜6Mbps）。1440p 以上で上げると高い画質の形式で配信される（推測。上げた後に yt-dlp -F で確かめる）"""
    big = (2560, 1440) if w > h else (1440, 2560)
    out = os.path.splitext(video)[0] + f"_{min(big)}p.mp4"
    if not os.path.exists(out):
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", video, "-vf", f"scale={big[0]}:{big[1]}:flags=lanczos",
                        "-c:v", "libx264", "-crf", "16", "-preset", "medium", "-pix_fmt", "yuv420p", "-c:a", "copy", out], check=True)
    return out


def live(h):
    """まだ生きている記録か（消えた・差し替えた動画は数えない）"""
    return not h.get("missing") and not h.get("retired")


def next_slot(hist, three=False):
    taken = {h["publish_at"][:16] for h in hist if h.get("publish_at") and live(h)}
    now = datetime.datetime.now(JST)
    day = now.date()
    for _ in range(60):
        for s in ([EXTRA] if three else []) + SLOTS:
            hh, mm = map(int, s.split(":"))
            t = datetime.datetime(day.year, day.month, day.day, hh, mm, tzinfo=JST)
            if t > now + datetime.timedelta(hours=1) and t.isoformat()[:16] not in taken:
                return t
        day += datetime.timedelta(days=1)
    sys.exit("【止まりました】60日先まで枠が埋まっています")


def check_after(vid, tries=10, wait=30):
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
    return None


def main():
    a = argparse.ArgumentParser()
    a.add_argument("work")
    a.add_argument("--video", required=True)
    a.add_argument("--at", help="公開の予約（日本時間）例 2026-10-28T19:00。無ければ次の空き枠")
    a.add_argument("--three", action="store_true", help="1日3本の日：昼の 12:10 の枠も使う")
    a.add_argument("--long", action="store_true", help="横動画（長尺）として上げる。--thumb と --at が要る")
    a.add_argument("--thumb", help="横動画のサムネ（作業フォルダの中の .jpg）")
    a.add_argument("--go", action="store_true")
    a.add_argument("--keep1080", action="store_true", help="1440p に引き上げず、そのまま上げる")
    a = a.parse_args()
    if a.long and not (a.thumb and a.at):
        sys.exit("【止まりました】横動画は --thumb と --at が要ります")
    work = os.path.abspath(a.work)
    name = os.path.basename(work)
    s = json.load(open(os.path.join(work, "script.json"), encoding="utf-8"))
    video = os.path.join(work, a.video)
    if not os.path.exists(video):
        sys.exit(f"【止まりました】ファイルがありません：{video}")
    title, desc = s["title"], s["desc"].strip()
    if a.long:
        chp = os.path.join(work, "chapters.txt")
        if not os.path.exists(chp):
            sys.exit("【止まりました】chapters.txt がありません（build_long.py が作る）")
        desc += "\n\n" + open(chp, encoding="utf-8").read().strip()
    if len(title) > 100 or len(desc) > 5000 or any(c in title + desc for c in "<>"):
        sys.exit("【止まりました】タイトルか説明が長すぎるか、< > が入っています")
    if CREDIT not in desc or "AI" not in desc:
        sys.exit(f"【止まりました】説明文に「{CREDIT}」か AI の1文がありません（制作ルール §5・§6）")
    # 人物のセリフを別の声で読んだ時は、その声のクレジットも要る（2026-10-28。make_voice.py が voice\_credits.txt に書く）
    cp = os.path.join(work, "voice", "_credits.txt")
    miss = [c for c in (open(cp, encoding="utf-8").read().splitlines() if os.path.exists(cp) else []) if c.strip() and c.strip() not in desc]
    if miss:
        sys.exit(f"【止まりました】説明文に声のクレジットが足りません：{'／'.join(miss)}（voice\\_credits.txt）")
    sec, w, h = probe(video)
    thumb = os.path.join(work, a.thumb) if a.long else None
    if a.long:
        if not (w == 1920 and h == 1080) or sec < 480:
            sys.exit(f"【止まりました】横動画の形ではありません（{w}x{h}・{sec:.1f}秒。1920x1080・8分以上）")
        if not os.path.exists(thumb):
            sys.exit(f"【止まりました】サムネがありません：{thumb}")
    elif not (w == 1080 and h == 1920) or sec > 60:
        sys.exit(f"【止まりました】ショートの形ではありません（{w}x{h}・{sec:.1f}秒。1080x1920・60秒以内）")
    if a.go and not a.keep1080:  # 上げる物だけ 1440p にする（形の確かめは元の 1080p で済ませた）
        video = up1440(video, w, h)
        print("1440p の写しを上げます：", os.path.basename(video))
    hp = os.path.join(ROOT, "history", CH, "long_uploaded.json" if a.long else "shorts_uploaded.json")
    hist = json.load(open(hp, encoding="utf-8")) if os.path.exists(hp) else []
    if any(x["work"] == name and live(x) for x in hist):
        sys.exit(f"【止めました】{name} はもう上げてあります（history\\nihongi\\shorts_uploaded.json）")
    at = datetime.datetime.fromisoformat(a.at).replace(tzinfo=JST) if a.at else next_slot(hist, a.three)
    if at < datetime.datetime.now(JST) + datetime.timedelta(minutes=30):
        sys.exit(f"【止まりました】予約の時刻 {at:%m/%d %H:%M} が近すぎるか過ぎています")
    if a.long:
        long_day_guard.check(CH, at)  # 横動画は同じ日に2本以上出さない（2026-10-29）
    print(f"動画 {sec:.1f}秒・{w}x{h}・{os.path.getsize(video) / 1e6:.1f}MB")
    print("タイトル：", title)
    print("予約：", at.isoformat())
    print("説明文：\n" + desc)
    if not a.go:
        print("（--go が無いので上げません）")
        return
    me = get(f"{API}/channels?part=id,snippet&mine=true")["items"][0]
    if me["id"] != CH_ID:
        sys.exit(f"【止まりました】ログイン中のチャンネルが違います：{me['snippet']['title']}（{me['id']}）")
    if title in channel_titles(CH):
        sys.exit("【止めました】チャンネルに同じタイトルの動画があります（二重アップの防止）")
    status = {"privacyStatus": "private", "publishAt": at.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
              "selfDeclaredMadeForKids": False, "containsSyntheticMedia": True, "embeddable": True, "license": "youtube"}
    meta = {"snippet": {"title": title, "description": desc, "tags": s.get("tags", []), "categoryId": "27",
                        "defaultLanguage": "ja", "defaultAudioLanguage": "ja"}, "status": status}
    r = api(CH, "POST", "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status", meta,
            {"X-Upload-Content-Type": "video/mp4", "X-Upload-Content-Length": str(os.path.getsize(video))}, timeout=120)
    with open(video, "rb") as f:
        d = json.load(api(CH, "PUT", r.headers["Location"], f.read(), {"Content-Type": "video/mp4"}))
    vid = d["id"]
    url = f"https://youtu.be/{vid}" if a.long else f"https://youtube.com/shorts/{vid}"
    print("上げました：", url, "｜状態", d["status"].get("privacyStatus"), "｜公開予定", d["status"].get("publishAt"))
    rec = {"work": name, "video_id": vid, "title": title, "video": a.video, "format": "long" if a.long else "short", "privacy": "private",
           "publish_at": at.isoformat(), "uploaded_at": datetime.datetime.now(JST).isoformat(timespec="seconds"), "missing": False}
    if a.long:
        try:
            api(CH, "POST", f"https://www.googleapis.com/upload/youtube/v3/thumbnails/set?videoId={vid}", open(thumb, "rb").read(),
                {"Content-Type": "image/jpeg"}, timeout=120)
            rec["thumb_set"] = True
            print("サムネを付けました")
        except Exception as e:
            rec["thumb_set"] = False
            print("【メモ】サムネを付けられませんでした（チャンネルの電話番号の確認が要るかもしれません）：", str(e)[:120])
        rec["thumb"] = a.thumb
    json.dump(rec, open(os.path.join(work, "uploaded.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    os.makedirs(os.path.dirname(hp), exist_ok=True)
    json.dump(hist + [rec], open(hp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    bad = check_after(vid)
    if bad:
        sys.exit(f"【止まりました】上げた動画が {bad}")
    print("上げた動画が残っていることを確かめました")


if __name__ == "__main__":
    main()

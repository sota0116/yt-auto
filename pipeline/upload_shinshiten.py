# シン視点事件簿（shinshiten）の横動画を上げて、公開の予約を入れる（upload_nihongi.py の横動画の道を写した物。2026-11-11）
#   python -X utf8 pipeline\upload_shinshiten.py <作業フォルダ> --video full.mp4 --thumb thumb.jpg --at 2026-11-15T21:00 [--post 投稿案_v3.md] [--go]
# ・--go を付けた時だけ上げる（付けない時は、タイトル・説明文・タグ・予約の時刻・確かめの結果だけ出す）
# ・非公開で上げて publishAt で公開の予約を入れる。【決まり】公開の時刻が来る前に、司令室の確認カードで持ち主のOKを取る。
#   1本目と、型を変えた最初の回は、OKが出てから --go を打つ（手順書 §0）。OKが出なければ、予約を外すか時刻を先へ動かす
# ・タイトル・説明文・タグは、作業フォルダの 投稿案 md（--post。省けば 投稿案_v*.md のうち版番号が一番大きい物）から取る。
#   「## タイトル」「## 概要欄」「## タグ」の見出しの、すぐ後のコードブロックの中身を使う（script.json と chapters ファイルは使わない）
# ・上げる前の確かめ（手順書 §6 の門のうち、機械で見られる物）：
#   タイトル100字・説明文5000字・タグ合計500字・< > 無し／説明文に「再現」の断りと AI の1文／voice\_credits.txt の声が全部書いてある／
#   目次が 0:00 から始まり、3つ以上、時刻が順に進み、動画の長さに収まる／1920x1080・profile.json の min_sec 以上／サムネがある
# ・横動画は同じ日に2本出さない（long_day_guard.py）。同じチャンネルの公開・予約と3時間あいていなければ注意を出す（day_slots.py）
# ・二重に上げない：history\shinshiten\uploaded.json に同じ作業フォルダがある時と、チャンネルに同じタイトルがある時
# ・作り直して上げ直す時は、古い記録に "retired": true を付ける
# ・上げる前に、ログインしているチャンネルが シン視点事件簿（CH_ID）かを確かめる。CH_ID が空の間は --go で止まる
# ・ショートはまだ扱わない（型は手順書 §8。決まったら道を足す）
import argparse, datetime, glob, json, os, re, subprocess, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from upload_job import ROOT, api, API, channel_titles
import long_day_guard
import day_slots

CH = "shinshiten"
CH_ID = "UCqjsFHU9ACKQFassZJJwAcA"  # 2026-11-11 公開済みの1本目の動画ページから読んだ ID。上げる時にログイン中のチャンネルと突き合わせる
JST = datetime.timezone(datetime.timedelta(hours=9))
CATEGORY = "27"  # 教育（nihongi と同じ）
MUST = ["セリフは記録をもとにした再現です", "AI"]  # 手順書 §6-10


def get(url):
    return json.load(api(CH, "GET", url, timeout=60))


def min_long_sec(work):
    """横動画で止める長さ（秒）。チャンネルの profile.json の min_sec（無ければ8分）"""
    p = os.path.normpath(os.path.join(work, "..", "..", "profile.json"))
    return (json.load(open(p, encoding="utf-8")).get("min_sec") if os.path.exists(p) else None) or 480


def probe(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height:format=duration",
                          "-of", "json", path], capture_output=True, text=True).stdout
    j = json.loads(out or "{}")
    st = (j.get("streams") or [{}])[0]
    return float(j.get("format", {}).get("duration", 0)), st.get("width"), st.get("height")


def up1440(video, w, h):
    """1080p の動画を 1440p に引き上げた写しを作って返す（upload_nihongi.py と同じ）"""
    big = (2560, 1440) if w > h else (1440, 2560)
    out = os.path.splitext(video)[0] + f"_{min(big)}p.mp4"
    if not os.path.exists(out):
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", video, "-vf", f"scale={big[0]}:{big[1]}:flags=lanczos",
                        "-c:v", "libx264", "-crf", "16", "-preset", "medium", "-pix_fmt", "yuv420p", "-c:a", "copy", out], check=True)
    return out


def live(h):
    """まだ生きている記録か（消えた・差し替えた動画は数えない）"""
    return not h.get("missing") and not h.get("retired")


def latest_post(work):
    """作業フォルダの 投稿案_v<数字>*.md のうち、版番号が一番大きい物（同じ番号なら名前が後ろの物）"""
    rows = []
    for p in glob.glob(os.path.join(work, "投稿案_v*.md")):
        m = re.match(r"投稿案_v(\d+)", os.path.basename(p))
        if m:
            rows.append((int(m.group(1)), os.path.basename(p), p))
    if not rows:
        sys.exit("【止まりました】作業フォルダに 投稿案_v*.md がありません（--post で名前を渡す）")
    return max(rows)[2]


def block(md, head):
    """「## <head>…」の見出しのすぐ後のコードブロックの中身"""
    m = re.search(r"^##\s*" + re.escape(head) + r"[^\n]*\n(?:(?!^##\s)[^\n]*\n)*?```[^\n]*\n(.*?)\n```", md, re.M | re.S)
    if not m:
        sys.exit(f"【止まりました】投稿案に「## {head}」とコードブロックがありません")
    return m.group(1).strip()


def chapters(desc):
    """説明文の ▼目次 の後に並ぶ時刻（秒）"""
    out, on = [], False
    for line in desc.splitlines():
        if "目次" in line:
            on = True
            continue
        if on:
            m = re.match(r"\s*(?:(\d+):)?(\d{1,2}):(\d{2})\b", line)
            if m:
                out.append(int(m.group(1) or 0) * 3600 + int(m.group(2)) * 60 + int(m.group(3)))
            elif out:
                break
    return out


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
    a.add_argument("--thumb", required=True, help="サムネ（作業フォルダの中の .jpg）")
    a.add_argument("--at", required=True, help="公開の予約（日本時間）例 2026-11-15T21:00")
    a.add_argument("--post", help="投稿案の md（作業フォルダの中の名前）。省けば版番号が一番大きい 投稿案_v*.md")
    a.add_argument("--go", action="store_true")
    a.add_argument("--keep1080", action="store_true", help="1440p に引き上げず、そのまま上げる")
    a = a.parse_args()
    work = os.path.abspath(a.work)
    name = os.path.basename(work)
    video, thumb = os.path.join(work, a.video), os.path.join(work, a.thumb)
    for p in (video, thumb):
        if not os.path.exists(p):
            sys.exit(f"【止まりました】ファイルがありません：{p}")
    post = os.path.join(work, a.post) if a.post else latest_post(work)
    if not os.path.exists(post):
        sys.exit(f"【止まりました】投稿案がありません：{post}")
    md = open(post, encoding="utf-8").read()
    title, desc = block(md, "タイトル"), block(md, "概要欄")
    tags = [t.strip() for t in re.split(r"[,、\n]", block(md, "タグ")) if t.strip()]
    if "\n" in title:
        sys.exit("【止まりました】投稿案のタイトルが2行以上あります（採用の1本だけにする）")
    if len(title) > 100 or len(desc) > 5000 or any(c in title + desc for c in "<>"):
        sys.exit(f"【止まりました】タイトル（{len(title)}字）か説明文（{len(desc)}字）が長すぎるか、< > が入っています")
    if sum(len(t) + (2 if " " in t else 0) for t in tags) + max(len(tags) - 1, 0) > 500:
        sys.exit("【止まりました】タグの合計が500字を超えています")
    miss = [m for m in MUST if m not in desc]
    if miss:
        sys.exit(f"【止まりました】説明文に決まりの文がありません：{'／'.join(miss)}（手順書 §6）")
    cp = os.path.join(work, "voice", "_credits.txt")
    if not os.path.exists(cp):
        sys.exit("【止まりました】voice\\_credits.txt がありません（声のクレジットを確かめられない）")
    miss = [c.strip() for c in open(cp, encoding="utf-8").read().splitlines() if c.strip() and c.strip() not in desc]
    if miss:
        sys.exit(f"【止まりました】説明文に声のクレジットが足りません：{'／'.join(miss)}（voice\\_credits.txt）")
    sec, w, h = probe(video)
    if not (w == 1920 and h == 1080) or sec < min_long_sec(work):
        sys.exit(f"【止まりました】横動画の形ではありません（{w}x{h}・{sec:.1f}秒。1920x1080・{min_long_sec(work)}秒以上）")
    ch = chapters(desc)
    if len(ch) < 3 or ch[0] != 0 or any(y - x < 10 for x, y in zip(ch, ch[1:])) or ch[-1] >= sec:
        sys.exit(f"【止まりました】目次の形が違います（0:00 から・3つ以上・10秒以上ずつ進む・動画 {sec:.0f}秒に収まる）：{ch}")
    hp = os.path.join(ROOT, "history", CH, "uploaded.json")
    hist = json.load(open(hp, encoding="utf-8")) if os.path.exists(hp) else []
    if any(x.get("work") == name and live(x) for x in hist):
        sys.exit(f"【止めました】{name} はもう上げてあります（history\\{CH}\\uploaded.json）")
    at = datetime.datetime.fromisoformat(a.at).replace(tzinfo=JST)
    if at < datetime.datetime.now(JST) + datetime.timedelta(minutes=30):
        sys.exit(f"【止まりました】予約の時刻 {at:%m/%d %H:%M} が近すぎるか過ぎています")
    long_day_guard.check(CH, at)  # 横動画は同じ日に2本以上出さない
    for t, wk in day_slots.near(CH, at)[:1]:
        print(f"（注意）{wk}（{t:%m/%d %H:%M}）と3時間あいていません")
    print("投稿案：", os.path.basename(post))
    print(f"動画 {sec:.1f}秒・{w}x{h}・{os.path.getsize(video) / 1e6:.1f}MB｜目次 {len(ch)}個（最後 {ch[-1]}秒）")
    print("タイトル：", title, f"（{len(title)}字）")
    print("予約：", at.isoformat())
    print(f"タグ（{len(tags)}個）：", "、".join(tags))
    print(f"説明文（{len(desc)}字）：\n" + desc)
    if not a.go:
        print("（--go が無いので上げません。確かめは全部通りました）")
        return
    if not CH_ID:
        sys.exit("【止まりました】CH_ID が空です。yt_auth.py login --channel shinshiten で出た ID を、この道具の CH_ID に入れてから上げます")
    me = get(f"{API}/channels?part=id,snippet&mine=true")["items"][0]
    if me["id"] != CH_ID:
        sys.exit(f"【止まりました】ログイン中のチャンネルが違います：{me['snippet']['title']}（{me['id']}）")
    if title in channel_titles(CH):
        sys.exit("【止めました】チャンネルに同じタイトルの動画があります（二重アップの防止）")
    if not a.keep1080:  # 上げる物だけ 1440p にする（形の確かめは元の 1080p で済ませた）
        video = up1440(video, w, h)
        print("1440p の写しを上げます：", os.path.basename(video))
    status = {"privacyStatus": "private", "publishAt": at.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
              "selfDeclaredMadeForKids": False, "containsSyntheticMedia": True, "embeddable": True, "license": "youtube"}
    meta = {"snippet": {"title": title, "description": desc, "tags": tags, "categoryId": CATEGORY,
                        "defaultLanguage": "ja", "defaultAudioLanguage": "ja"}, "status": status}
    r = api(CH, "POST", "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status", meta,
            {"X-Upload-Content-Type": "video/mp4", "X-Upload-Content-Length": str(os.path.getsize(video))}, timeout=120)
    with open(video, "rb") as f:
        d = json.load(api(CH, "PUT", r.headers["Location"], f.read(), {"Content-Type": "video/mp4"}))
    vid = d["id"]
    print("上げました：", f"https://youtu.be/{vid}", "｜状態", d["status"].get("privacyStatus"), "｜公開予定", d["status"].get("publishAt"))
    rec = {"work": name, "video_id": vid, "title": title, "video": a.video, "post": os.path.basename(post), "format": "long", "privacy": "private",
           "publish_at": at.isoformat(), "uploaded_at": datetime.datetime.now(JST).isoformat(timespec="seconds"), "missing": False}
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
    print("上げた動画が残っていることを確かめました。公開の前に、司令室の確認カードで持ち主のOKを取ります")


if __name__ == "__main__":
    main()

# 指名手配ボード（shimei）の動画を上げて、公開の予約を入れる（かくれ神語り用の物を写した。2026-10-30）
#   python -X utf8 pipeline\upload_shimei.py <作業フォルダ> [--at 2026-11-01T20:00] [--go]   … 1本
#   python -X utf8 pipeline\upload_shimei.py --all <指名手配ボードフォルダ> [--go]               … 在庫を全部
# ・作業フォルダに upload.json {"video": "完成.mp4", "format": "long" か "short", "thumb": "thumb.jpg"（横だけ）} がある物を在庫とみなす
#   （品質の門を通ったら upload.json を置く。置いていない作業フォルダは上げない）
# ・--all は videos\ の作業フォルダを名前の順に、横動画は横の枠、ショートはショートの枠へ、空いている一番近い枠に予約する
#   一気に上げても公開は枠どおりに散らす（ショート毎日 12:00・19:00 の2本・横動画 2日に1本 20:00。設計\チャンネル看板_指名手配ボード_v2 §8）
# ・--go を付けた時だけ上げる（付けない時は、上げる物・タイトル・予約の時刻・確かめの結果だけ出す）
# ・横動画は 1920x1080。長さは決まりにしない（看板 v2 §3「足す中身が無ければ短く出す」）が、1分未満は止める。
#   15分をこえる物は、チャンネルの電話番号の確認が済んでいないと上がらない
#   作業フォルダの chapters.txt を説明文の最後に足し、サムネを付ける。同じ日に横動画がもう入っていれば止まる（long_day_guard.py）
# ・説明文に、voice\_credits.txt の声のクレジット全部と AI の1文が無ければ止まる
# ・チャンネルIDはまだ控えていないので、ログイン中のチャンネル名に「指名手配ボード」が入っているかで確かめる
# ・非公開で上げて publishAt で公開の予約。AI の申告（containsSyntheticMedia）はオン、子ども向けではない
# ・script.json に "playlist" があれば、その再生リストに足す（ID は history\shimei\playlists.json。まだ作っていない）
# ・二重に上げない：history\shimei\*_uploaded.json に同じ作業フォルダがある時と、チャンネルに同じタイトルがある時
import argparse, datetime, glob, json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from upload_job import ROOT, api, API, channel_titles
from upload_nihongi import probe, up1440, live  # check_after は nihongi のログインで動くので借りない
import long_day_guard

CH = "shimei"
TITLE = "指名手配ボード"
JST = datetime.timezone(datetime.timedelta(hours=9))
SHORT_AT = ["12:00", "19:00"]  # ショートは1日2本
LONG_AT = "20:00"
LONG_GAP = 2  # 横動画は2日に1本


def get(url):
    return json.load(api(CH, "GET", url, timeout=60))


def check_after(vid, tries=10, wait=30):
    """上げた後、動画が残っていて断られていないかを数分見張る（upload_nihongi.py と同じ中身を shimei のログインで）"""
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


def hist_path(long_):
    return os.path.join(ROOT, "history", CH, "long_uploaded.json" if long_ else "shorts_uploaded.json")


def load(p):
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else []


def next_slot(hist, long_):
    """空いている一番近い枠（今から1時間より後）。横動画は、前の横動画から LONG_GAP 日あける。ショートは1日2つの時刻を順に埋める"""
    now = datetime.datetime.now(JST)
    times = [LONG_AT] if long_ else SHORT_AT
    live_at = [h["publish_at"] for h in hist if h.get("publish_at") and live(h)]
    taken = {p[:10] for p in live_at} if long_ else {p[:16] for p in live_at}
    day = now.date()
    if long_ and taken:
        day = max(day, datetime.date.fromisoformat(max(taken)) + datetime.timedelta(days=LONG_GAP))
    for _ in range(120):
        for hm in times:
            hh, mm = map(int, hm.split(":"))
            t = datetime.datetime(day.year, day.month, day.day, hh, mm, tzinfo=JST)
            key = day.isoformat() if long_ else t.isoformat()[:16]
            if t > now + datetime.timedelta(hours=1) and key not in taken:
                return t
        day += datetime.timedelta(days=1)
    sys.exit("【止まりました】120日先まで枠が埋まっています")


def prepare(work, at_s, plan):
    """上げる前の確かめ。plan は --all の時に、まだ上げていない予約の予定（枠の取り合いを防ぐ）"""
    name = os.path.basename(work)
    up = json.load(open(os.path.join(work, "upload.json"), encoding="utf-8"))
    long_ = up["format"] == "long"
    s = json.load(open(os.path.join(work, "script.json"), encoding="utf-8"))
    video = os.path.join(work, up["video"])
    if not os.path.exists(video):
        sys.exit(f"【止まりました】ファイルがありません：{video}")
    title, desc = s["title"], s["desc"].strip()
    if long_:
        chp = os.path.join(work, "chapters.txt")
        if not os.path.exists(chp):
            sys.exit(f"【止まりました】{name}：chapters.txt がありません（build_long.py が作る）")
        desc += "\n\n" + open(chp, encoding="utf-8").read().strip()
    if len(title) > 100 or len(desc) > 5000 or any(c in title + desc for c in "<>"):
        sys.exit(f"【止まりました】{name}：タイトルか説明が長すぎるか、< > が入っています")
    cp = os.path.join(work, "voice", "_credits.txt")
    credits = [c.strip() for c in open(cp, encoding="utf-8").read().splitlines() if c.strip()] if os.path.exists(cp) else []
    if not credits:
        sys.exit(f"【止まりました】{name}：voice\\_credits.txt が無いか空です（make_voice.py が書く）")
    miss = [c for c in credits if c not in desc]
    if miss or "AI" not in desc:
        sys.exit(f"【止まりました】{name}：説明文に声のクレジット（{'／'.join(miss) or 'OK'}）か AI の1文がありません")
    sec, w, h = probe(video)
    thumb = os.path.join(work, up.get("thumb") or "thumb.jpg") if long_ else None
    if long_:
        if not (w == 1920 and h == 1080) or sec < 60:
            sys.exit(f"【止まりました】{name}：横動画の形ではありません（{w}x{h}・{sec:.1f}秒。1920x1080・1分以上）")
        if not os.path.exists(thumb):
            sys.exit(f"【止まりました】{name}：サムネがありません：{thumb}")
        if sec > 900:
            print(f"【注意】{name} は {sec / 60:.1f} 分。15分をこえるので、チャンネルの電話番号の確認が済んでいないと上がりません")
    elif not (w == 1080 and h == 1920) or sec > 60:
        sys.exit(f"【止まりました】{name}：ショートの形ではありません（{w}x{h}・{sec:.1f}秒。1080x1920・60秒以内）")
    hist = load(hist_path(long_))
    if any(x["work"] == name and live(x) for x in hist):
        return None  # もう上げてある
    at = (datetime.datetime.fromisoformat(at_s).replace(tzinfo=JST) if at_s
          else next_slot(hist + [p for p in plan if (p["format"] == "long") == long_], long_))
    if at < datetime.datetime.now(JST) + datetime.timedelta(minutes=30):
        sys.exit(f"【止まりました】{name}：予約の時刻 {at:%m/%d %H:%M} が近すぎるか過ぎています")
    if long_:
        long_day_guard.check(CH, at)  # 横動画は同じ日に2本以上出さない
        if any(p["format"] == "long" and p["publish_at"][:10] == at.date().isoformat() for p in plan):
            sys.exit(f"【止めました】{name}：{at:%m/%d} には、この実行で予約する横動画がもう入っています")
    return dict(work=work, name=name, video=video, video_file=up["video"], long=long_, title=title, desc=desc,
                tags=s.get("tags", []), thumb=thumb, thumb_file=up.get("thumb"), at=at, sec=sec, w=w, h=h, playlist=s.get("playlist"),
                format="long" if long_ else "short", publish_at=at.isoformat(), live=True)


def upload(j, keep1080):
    video = j["video"] if keep1080 else up1440(j["video"], j["w"], j["h"])
    if title_taken(j["title"]):
        sys.exit(f"【止めました】{j['name']}：チャンネルに同じタイトルの動画があります（二重アップの防止）")
    status = {"privacyStatus": "private", "publishAt": j["at"].astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
              "selfDeclaredMadeForKids": False, "containsSyntheticMedia": True, "embeddable": True, "license": "youtube"}
    meta = {"snippet": {"title": j["title"], "description": j["desc"], "tags": j["tags"], "categoryId": "27",
                        "defaultLanguage": "ja", "defaultAudioLanguage": "ja"}, "status": status}
    r = api(CH, "POST", "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status", meta,
            {"X-Upload-Content-Type": "video/mp4", "X-Upload-Content-Length": str(os.path.getsize(video))}, timeout=120)
    with open(video, "rb") as f:
        d = json.load(api(CH, "PUT", r.headers["Location"], f.read(), {"Content-Type": "video/mp4"}))
    vid = d["id"]
    url = f"https://youtu.be/{vid}" if j["long"] else f"https://youtube.com/shorts/{vid}"
    print("上げました：", url, "｜状態", d["status"].get("privacyStatus"), "｜公開予定", d["status"].get("publishAt"))
    rec = {"work": j["name"], "video_id": vid, "title": j["title"], "video": j["video_file"], "format": j["format"], "privacy": "private",
           "publish_at": j["publish_at"], "uploaded_at": datetime.datetime.now(JST).isoformat(timespec="seconds"), "missing": False}
    if j["long"]:
        try:
            api(CH, "POST", f"https://www.googleapis.com/upload/youtube/v3/thumbnails/set?videoId={vid}", open(j["thumb"], "rb").read(),
                {"Content-Type": "image/jpeg"}, timeout=120)
            rec["thumb_set"] = True
            print("サムネを付けました")
        except Exception as e:
            rec["thumb_set"] = False
            print("【メモ】サムネを付けられませんでした（チャンネルの電話番号の確認が要るかもしれません）：", str(e)[:120])
        rec["thumb"] = j["thumb_file"]
    # 再生リスト：script.json の "playlist" を history\shimei\playlists.json の ID に足す
    if j.get("playlist"):
        pls = json.load(open(os.path.join(ROOT, "history", CH, "playlists.json"), encoding="utf-8"))
        try:
            api(CH, "POST", f"{API}/playlistItems?part=snippet",
                {"snippet": {"playlistId": pls[j["playlist"]], "resourceId": {"kind": "youtube#video", "videoId": vid}}}, timeout=60)
            rec["playlist"] = j["playlist"]
            print("再生リストに足しました：", j["playlist"])
        except Exception as e:
            print("【メモ】再生リストに足せませんでした：", str(e)[:120])
    json.dump(rec, open(os.path.join(j["work"], "uploaded.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    hp = hist_path(j["long"])
    os.makedirs(os.path.dirname(hp), exist_ok=True)
    json.dump(load(hp) + [rec], open(hp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    bad = check_after(vid)
    if bad:
        sys.exit(f"【止まりました】上げた動画が {bad}")
    print("上げた動画が残っていることを確かめました")


_titles = None


def title_taken(t):
    global _titles
    if _titles is None:
        _titles = set(channel_titles(CH))
    return t in _titles


def main():
    a = argparse.ArgumentParser()
    a.add_argument("work", help="作業フォルダ（--all の時は 指名手配ボードフォルダ）")
    a.add_argument("--all", action="store_true", help="videos\\ の中の upload.json がある作業フォルダを全部")
    a.add_argument("--at", help="公開の予約（日本時間）例 2026-11-01T20:00。無ければ次の空き枠。--all では使えない")
    a.add_argument("--go", action="store_true")
    a.add_argument("--keep1080", action="store_true", help="1440p に引き上げず、そのまま上げる")
    a = a.parse_args()
    if a.all and a.at:
        sys.exit("【止まりました】--all と --at は一緒に使えません")
    root = os.path.abspath(a.work)
    works = (sorted(os.path.dirname(p) for p in glob.glob(os.path.join(root, "videos", "*", "upload.json"))) if a.all else [root])
    if not works:
        sys.exit("【止まりました】上げられる在庫がありません（作業フォルダに upload.json を置いた物が在庫です）")
    plan = []
    for w in works:
        j = prepare(w, a.at, plan)
        if j is None:
            print(f"（{os.path.basename(w)} はもう上げてあるので飛ばします）")
            continue
        plan.append(j)
        print(f"{'横' if j['long'] else 'ショート'}｜{j['at']:%m/%d(%a) %H:%M}｜{j['name']}｜{j['sec']:.0f}秒・{j['w']}x{j['h']}｜{j['title']}")
    if not plan:
        return
    if len(plan) == 1:
        print("説明文：\n" + plan[0]["desc"])
    print(f"全部で {len(plan)} 本（横 {sum(j['long'] for j in plan)}・ショート {sum(not j['long'] for j in plan)}）")
    if not a.go:
        print("（--go が無いので上げません）")
        return
    me = get(f"{API}/channels?part=id,snippet&mine=true")["items"][0]
    if TITLE not in me["snippet"]["title"]:
        sys.exit(f"【止まりました】ログイン中のチャンネルが違います：{me['snippet']['title']}（{me['id']}）")
    for j in plan:
        print(f"上げます：{j['name']}（{j['at']:%m/%d %H:%M} に公開）", flush=True)
        upload(j, a.keep1080)


if __name__ == "__main__":
    main()

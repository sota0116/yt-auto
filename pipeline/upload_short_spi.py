# ⑪b ショートのアップ（千年こよみ・2026-10-27 新設。心理学ch の upload_short_psy.py をもとにした。元は残している）
#   python -X utf8 pipeline\upload_short_spi.py <作業フォルダ> [--dry]
# ・作業フォルダ\short\short.mp4 を上げる。題・説明は 作業フォルダ\short.json。説明文に本編のリンクを入れる
# ・予約：本編（uploaded.json の video_id）の今の状態を YouTube に聞き、公開か予約が入っていれば「本編の公開の次の日の 19:15」に予約する
#   19:15 の理由：暦の競合「招福こよみ」（ショートの再生の中央値 約11万回）が毎日 11:15 と 19:15 に出していて、中央値は同じくらい
#   （10.6万・10.3万）だが、上位6本のうち4本が夕方（18:30〜19:15）。_research\spi_shorts_time_2026-10-27.json（2026-10-27）
#   （近すぎる・過ぎている時は次の 19:15）。本編がまだ非公開で日が決まっていなければ、非公開のまま置く
#   千年こよみは、クラウドの見張り（shorts_watch.py）にまだ入れていないので、予約はここで入れる
# ・記録は history\spi\shorts_uploaded.json（長尺の uploaded.json に入れない）
# ・本編へつなぐ（2026-10-28）：記録に「comment」（本編の公開日・長さ・リンク）を入れる。見張り（shorts_watch_v2.py）が、
#   ショートが公開されたらチャンネルからこのコメントを入れる。ショートの「関連動画」は API で設定できないので、Studio で手で選ぶ
# ・--replace：同じ回のショートを作り直した時。前のショートを非公開・予約なしにして題の頭に「（差し替え前）」を付け、記録に retired を付ける
#   （消さない。消すのは本人が Studio で）。そのあと新しいほうを上げる
# ・「AIで作った映像・声」の申告（containsSyntheticMedia）はいつもオン。二重に上げない（記録と、チャンネルの同じタイトル）
import argparse, datetime, json, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from upload_job import ROOT, API, api, channel_titles

JST = datetime.timezone(datetime.timedelta(hours=9))
CH = "spi"
TIME = (19, 15)
AI_LINE = "千年以上続く暦の、人の手では数えきれない日付の重なりをプログラムで計算し、AIで映像と声にしています。日付は全部、暦と照らしています。"


def description(work):
    s = json.load(open(os.path.join(work, "script.json"), encoding="utf-8"))
    sh = json.load(open(os.path.join(work, "short.json"), encoding="utf-8"))
    long_up = json.load(open(os.path.join(work, "uploaded.json"), encoding="utf-8"))
    prof = json.load(open(os.path.join(ROOT, "channels", CH, "profile.json"), encoding="utf-8"))
    d = (f"{sh.get('desc', '').strip()}\n\n▼本編（くわしいお話）はこちら\nhttps://youtu.be/{long_up['video_id']}\n\n"
         f"今月と来月の吉日と行事のカレンダーを、LINEで無料で受け取れます。\n{prof['line_url']}\n\n"
         f"{AI_LINE}\n{prof['voicevox']['credit']}\nBGM：甘茶の音楽工房 https://amachamusic.chagasi.com/\n\n#暦 #開運 #shorts")
    if "PR" in d:
        sys.exit("【止まりました】説明文に PR の文字があります")
    return s, sh, long_up, d


def slot(long_id):
    """本編の公開（か予約）の次の日の 19:15。本編の日が決まっていなければ None"""
    it = json.load(api(CH, "GET", f"{API}/videos?part=status,snippet,contentDetails&id={long_id}", timeout=60))["items"][0]
    st = it["status"]
    when = st.get("publishAt") if st["privacyStatus"] == "private" else it["snippet"]["publishedAt"]
    if st["privacyStatus"] == "private" and not when:
        return None, st["privacyStatus"], None
    pub = datetime.datetime.fromisoformat(when.replace("Z", "+00:00")).astimezone(JST).date()
    at = datetime.datetime.combine(pub + datetime.timedelta(days=1), datetime.time(*TIME), JST)
    while at < datetime.datetime.now(JST) + datetime.timedelta(minutes=30):
        at += datetime.timedelta(days=1)
    m = re.fullmatch(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", it["contentDetails"]["duration"])
    h, mi, s = (int(x or 0) for x in m.groups())
    w = "月火水木金土日"[pub.weekday()]
    comment = f"本編（{pub.month}月{pub.day}日（{w}）公開・約{round((h * 3600 + mi * 60 + s) / 60)}分）はこちらです。\nhttps://youtu.be/{long_id}"
    return at, st["privacyStatus"], comment


def retire(hist, name):
    """作り直す前のショートを、非公開・予約なし・題に「（差し替え前）」にする（消さない）"""
    for h in hist:
        if h["work"] != name or h.get("retired"):
            continue
        it = json.load(api(CH, "GET", f"{API}/videos?part=snippet,status&id={h['video_id']}", timeout=60))["items"]
        if it and it[0]["status"]["privacyStatus"] != "public":
            sn = {k: it[0]["snippet"][k] for k in ("title", "description", "categoryId", "defaultLanguage", "defaultAudioLanguage")
                  if k in it[0]["snippet"]}
            sn.update(title="（差し替え前）" + sn["title"], tags=it[0]["snippet"].get("tags", []))
            api(CH, "PUT", f"{API}/videos?part=snippet,status", {"id": h["video_id"], "snippet": sn, "status": {
                "privacyStatus": "private", "selfDeclaredMadeForKids": False, "containsSyntheticMedia": True}}, timeout=60)
        elif it:
            sys.exit(f"【止めました】前のショート {h['video_id']} はもう公開されています。差し替えずに止めました")
        h["retired"] = datetime.datetime.now(JST).isoformat(timespec="seconds")
        print("前のショートを非公開・予約なしにしました：", f"https://youtube.com/shorts/{h['video_id']}")


def main():
    a = argparse.ArgumentParser()
    a.add_argument("work")
    a.add_argument("--dry", action="store_true")
    a.add_argument("--replace", action="store_true")
    a = a.parse_args()
    work = os.path.abspath(a.work)
    video = os.path.join(work, "short", "short.mp4")
    if not os.path.exists(video):
        sys.exit(f"【止まりました】{video} がありません")
    s, sh, long_up, desc = description(work)
    title = sh["title"] if len(sh["title"]) + 8 > 100 else sh["title"] + " #shorts"
    at, long_state, comment = slot(long_up["video_id"])
    print("タイトル：", title)
    print("説明文：\n" + desc)
    print(f"本編の今の状態：{long_state} → ショートの予約：" + (f"{at:%Y-%m-%d %H:%M}" if at else "入れない（非公開のまま）"))
    print("公開後のコメント：", comment)
    if a.dry:
        print("（--dry なので上げません）")
        return
    hp = os.path.join(ROOT, "history", CH, "shorts_uploaded.json")
    hist = json.load(open(hp, encoding="utf-8")) if os.path.exists(hp) else []
    name = os.path.basename(work)
    if a.replace:
        retire(hist, name)
        json.dump(hist, open(hp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    if any(h["work"] == name and not h.get("retired") for h in hist) or title in channel_titles(CH):
        sys.exit("【止めました】このショートはもう上げてあります（二重アップの防止。作り直した時は --replace）")
    status = {"privacyStatus": "private", "selfDeclaredMadeForKids": False, "containsSyntheticMedia": True}
    if at:
        status["publishAt"] = at.isoformat()
    meta = {"snippet": {"title": title, "description": desc, "tags": (s.get("tags") or [])[:8] + ["shorts"], "categoryId": "27",
                        "defaultLanguage": "ja", "defaultAudioLanguage": "ja"}, "status": status}
    size = os.path.getsize(video)
    r = api(CH, "POST", "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status", meta,
            {"X-Upload-Content-Type": "video/mp4", "X-Upload-Content-Length": str(size)}, timeout=120)
    with open(video, "rb") as f:
        d = json.load(api(CH, "PUT", r.headers["Location"], f.read(), {"Content-Type": "video/mp4"}))
    print("上げました：", f"https://youtube.com/shorts/{d['id']}", "（予約 " + (f"{at:%m/%d %H:%M}" if at else "なし・非公開") + "）")
    rec = {"work": name, "video_id": d["id"], "title": title, "type": s.get("type"), "long_video_id": long_up["video_id"],
           "hook": sh["cuts"][0]["narration"], "band": ["".join(t for t, _ in ln) for ln in sh.get("lines", [])],
           "privacy_now": "private", "publish_at": at.isoformat() if at else None, "comment": comment,
           "uploaded_at": datetime.datetime.now(JST).isoformat(timespec="seconds")}
    json.dump(rec, open(os.path.join(work, "short", "uploaded.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    os.makedirs(os.path.dirname(hp), exist_ok=True)
    json.dump(hist + [rec], open(hp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()

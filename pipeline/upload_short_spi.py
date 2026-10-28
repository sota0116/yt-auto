# ⑪b ショートのアップ（千年こよみ・2026-10-27 新設。心理学ch の upload_short_psy.py をもとにした。元は残している）
#   python -X utf8 pipeline\upload_short_spi.py <作業フォルダ> [--name short] [--dry]
# ・2026-10-28 改（本人「横動画は週に3〜4本」「ショートは毎日1〜3本」「全部が横動画に関係していなくてもいい」）：
#   1つの回からショートを何本でも作れるようにした（--name。short.json → short\、short_2.json → short_2\）。
#   short.json の kind（teaser 予告 / after 切り出し / solo 単独）で、予約の枠を pipeline\short_slot_spi.py が決める（毎日 11:15・19:15 の空き枠）。
#   下の「本編の公開の次の日の 19:15」は 2026-10-28 までの決まり（記録として残す）
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
from short_slot_spi import KINDS, slot

JST = datetime.timezone(datetime.timedelta(hours=9))
CH = "spi"
AI_LINE = "千年以上続く暦の、人の手では数えきれない日付の重なりをプログラムで計算し、AIで映像と声にしています。日付は全部、暦と照らしています。"


def long_state(long_id):
    """本編の公開（か予約）の日時・今の状態・長さ（分）。日が決まっていなければ日時は None"""
    it = json.load(api(CH, "GET", f"{API}/videos?part=status,snippet,contentDetails&id={long_id}", timeout=60))["items"][0]
    st = it["status"]
    when = st.get("publishAt") if st["privacyStatus"] == "private" else it["snippet"]["publishedAt"]
    m = re.fullmatch(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", it["contentDetails"]["duration"])
    h, mi, s = (int(x or 0) for x in m.groups())
    at = datetime.datetime.fromisoformat(when.replace("Z", "+00:00")).astimezone(JST) if when else None
    return at, st["privacyStatus"], round((h * 3600 + mi * 60 + s) / 60)


def description(work, sh, long_id, kind, long_at):
    s = json.load(open(os.path.join(work, "script.json"), encoding="utf-8"))
    prof = json.load(open(os.path.join(ROOT, "channels", CH, "profile.json"), encoding="utf-8"))
    if kind == "teaser":
        w = "月火水木金土日"[long_at.weekday()]
        head = f"▼本編は {long_at.month}月{long_at.day}日（{w}）{long_at:%H:%M} 公開です（公開の時刻から見られます）"
    else:
        head = "▼本編（くわしいお話）はこちら" if kind == "after" else "▼関連する本編（くわしいお話）はこちら"
    d = (f"{sh.get('desc', '').strip()}\n\n{head}\nhttps://youtu.be/{long_id}\n\n"
         f"今月と来月の吉日と行事のカレンダーを、LINEで無料で受け取れます。\n{prof['line_url']}\n\n"
         f"{AI_LINE}\n{prof['voicevox']['credit']}\nBGM：甘茶の音楽工房 https://amachamusic.chagasi.com/\n\n#暦 #開運 #shorts")
    if "PR" in d:
        sys.exit("【止まりました】説明文に PR の文字があります")
    return s, d


def comment_text(kind, long_id, long_at, minutes):
    """公開後に見張りが入れるコメント。予告（teaser）は本編が公開されてから入れる（comment_after）"""
    if not long_at:
        return None
    w = "月火水木金土日"[long_at.weekday()]
    if kind == "solo":
        return f"もっとくわしいお話は、本編（約{minutes}分）でしています。\nhttps://youtu.be/{long_id}"
    return f"本編（{long_at.month}月{long_at.day}日（{w}）公開・約{minutes}分）はこちらです。\nhttps://youtu.be/{long_id}"


def used_slots(hist):
    out = set()
    for h in hist:
        w = h.get("publish_at") or h.get("published_at")
        if w and not h.get("missing") and not h.get("retired"):
            out.add(datetime.datetime.fromisoformat(w.replace("Z", "+00:00")))
    return out


def same(h, work, name):
    return h["work"] == work and (h.get("name") or "short") == name


def retire(hist, work, name):
    """作り直す前のショートを、非公開・予約なし・題に「（差し替え前）」にする（消さない）"""
    for h in hist:
        if not same(h, work, name) or h.get("retired"):
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
    a.add_argument("--name", default="short", help="short.json なら short（既定）、short_2.json なら short_2")
    a.add_argument("--dry", action="store_true")
    a.add_argument("--replace", action="store_true")
    a = a.parse_args()
    work = os.path.abspath(a.work)
    video = os.path.join(work, a.name, "short.mp4")
    if not os.path.exists(video):
        sys.exit(f"【止まりました】{video} がありません")
    sh = json.load(open(os.path.join(work, a.name + ".json"), encoding="utf-8"))
    kind = sh.get("kind", "after")
    if kind not in KINDS:
        sys.exit(f"【止まりました】kind「{kind}」は {KINDS} のどれか")
    long_id = json.load(open(os.path.join(work, "uploaded.json"), encoding="utf-8"))["video_id"]
    long_at, long_privacy, minutes = long_state(long_id)
    if kind == "teaser" and (not long_at or long_privacy != "private"):
        sys.exit("【止まりました】予告（teaser）は、本編に公開の予約が入っていて、まだ公開前の時だけ")
    s, desc = description(work, sh, long_id, kind, long_at)
    title = sh["title"] if len(sh["title"]) + 8 > 100 else sh["title"] + " #shorts"
    hp = os.path.join(ROOT, "history", CH, "shorts_uploaded.json")
    hist = json.load(open(hp, encoding="utf-8")) if os.path.exists(hp) else []
    name = os.path.basename(work)
    now = datetime.datetime.now(JST)
    at = slot(kind, long_at, used_slots([h for h in hist if not same(h, name, a.name)] if a.replace else hist), now)
    comment = comment_text(kind, long_id, long_at, minutes)
    print("種類：", kind, "／タイトル：", title)
    print("説明文：\n" + desc)
    print(f"本編の今の状態：{long_privacy}（{long_at:%m/%d %H:%M} 公開）" if long_at else f"本編の今の状態：{long_privacy}（日が未定）",
          "→ ショートの予約：" + (f"{at:%Y-%m-%d %H:%M}" if at else "入れない（非公開のまま。見張りが後で入れる）"))
    print("公開後のコメント：", comment, "（本編の公開の後に入れる）" if kind == "teaser" else "")
    if a.dry:
        print("（--dry なので上げません）")
        return
    if a.replace:
        retire(hist, name, a.name)
        json.dump(hist, open(hp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    if any(same(h, name, a.name) and not h.get("retired") for h in hist) or title in channel_titles(CH):
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
    rec = {"work": name, "name": a.name, "kind": kind, "video_id": d["id"], "title": title, "type": s.get("type"), "long_video_id": long_id,
           "hook": sh["cuts"][0]["narration"], "band": ["".join(t for t, _ in ln) for ln in sh.get("lines", [])],
           "privacy_now": "private", "publish_at": at.isoformat() if at else None, "comment": comment,
           "uploaded_at": now.isoformat(timespec="seconds")}
    if kind == "teaser":
        rec["comment_after"] = long_at.isoformat()  # 本編がまだ見られない間はリンクのコメントを入れない（shorts_watch_v2.py）
    json.dump(rec, open(os.path.join(work, a.name, "uploaded.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    os.makedirs(os.path.dirname(hp), exist_ok=True)
    json.dump(hist + [rec], open(hp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()

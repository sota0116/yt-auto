# ⑪b ショートのアップ（心理学ch・2026-10-27 新設）：作業フォルダ\short\short.mp4 を非公開で上げる。公開の予約は見張り（shorts_watch.py）が入れる
#   python -X utf8 pipeline\upload_short_psy.py <作業フォルダ> [--name short_2] [--dry]
# ・2026-10-29 から1つの回に何本も（make_short_psy.py の shorts_of：short・short_2 …）。--name が無い時は、作れていて未アップの物を全部上げる
# ・本編（同じ作業フォルダの uploaded.json）を先に上げてあること。説明文に本編のリンクを入れる
# ・本編の公開の日がまだ決まっていない（在庫）ので、ここでは予約しない。本編の予約が入ったら、見張りが「本編の次の日の 12:10」に予約する
# ・記録は history\psy\shorts_uploaded.json（長尺の uploaded.json に入れない。見張りが長尺の在庫と公開の間隔に使っているため）
# ・「AIで作った映像・声」の申告（containsSyntheticMedia）はいつもオン。二重に上げない（記録と、チャンネルの同じタイトル）
import argparse, datetime, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from upload_job import ROOT, api, channel_titles
from make_short_psy import shorts_of

JST = datetime.timezone(datetime.timedelta(hours=9))
CH = "psy"
NOTE = "この動画は、心理学の研究をもとにした一般的なお話です。医療・診断・治療を目的としたものではありません。"


def description(work, name="short"):
    s = json.load(open(os.path.join(work, "script.json"), encoding="utf-8"))
    sh = dict(shorts_of(s))[name]
    long_up = json.load(open(os.path.join(work, "uploaded.json"), encoding="utf-8"))
    prof = json.load(open(os.path.join(ROOT, "channels", CH, "profile.json"), encoding="utf-8"))
    fx = json.load(open(os.path.join(work, "facts.json"), encoding="utf-8"))
    used = {c.get("study") for c in sh["cuts"] if c.get("study")}
    refs = "\n".join(x["cite"] for x in fx.get("studies", []) if x.get("key") in used)
    d = (f"{sh.get('desc', '').strip()}\n\n▼本編（くわしいお話）はこちら\nhttps://youtu.be/{long_up['video_id']}\n\n"
         f"🎁 LINE登録で無料プレゼント「心のクセ診断」\n{prof['line_url']}\n\n"
         + (f"📚参考にした研究\n{refs}\n\n" if refs else "")
         + f"{NOTE}\n{prof['voicevox']['credit']}\n映像とナレーションは、AIを使って作っています。\n\n#心理学 #shorts #60代")
    if "PR" in d:
        sys.exit("【止まりました】説明文に PR の文字があります")
    return s, sh, long_up, d


def main():
    a = argparse.ArgumentParser()
    a.add_argument("work")
    a.add_argument("--name", default="")
    a.add_argument("--dry", action="store_true")
    a = a.parse_args()
    work = os.path.abspath(a.work)
    s = json.load(open(os.path.join(work, "script.json"), encoding="utf-8"))
    names = [a.name] if a.name else [k for k, _ in shorts_of(s) if os.path.exists(os.path.join(work, k, "short.mp4"))]
    if not names:
        sys.exit(f"【止まりました】{os.path.join(work, 'short', 'short.mp4')} がありません")
    for k in names:
        try:
            one(work, k, a.dry)
        except SystemExit as e:
            if k == names[0]:
                raise
            print(f"{k}：{e}")


def one(work, sname, dry):
    video = os.path.join(work, sname, "short.mp4")
    if not os.path.exists(video):
        sys.exit(f"【止まりました】{video} がありません")
    s, sh, long_up, desc = description(work, sname)
    title = sh["title"] if len(sh["title"]) + 8 > 100 else sh["title"] + " #shorts"
    print("タイトル：", title)
    print("説明文：\n" + desc)
    if dry:
        print("（--dry なので上げません）")
        return
    hp = os.path.join(ROOT, "history", CH, "shorts_uploaded.json")
    hist = json.load(open(hp, encoding="utf-8")) if os.path.exists(hp) else []
    name = os.path.basename(work)
    if any(h["work"] == name and (h.get("name") or "short") == sname for h in hist) or title in channel_titles(CH):
        print(f"{sname}：もう上げてあるので飛ばします（二重アップの防止）")
        return
    status = {"privacyStatus": "private", "selfDeclaredMadeForKids": False, "containsSyntheticMedia": True}
    meta = {"snippet": {"title": title, "description": desc, "tags": (s.get("tags") or [])[:8] + ["shorts"], "categoryId": "27",
                        "defaultLanguage": "ja", "defaultAudioLanguage": "ja"}, "status": status}
    size = os.path.getsize(video)
    r = api(CH, "POST", "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status", meta,
            {"X-Upload-Content-Type": "video/mp4", "X-Upload-Content-Length": str(size)}, timeout=120)
    with open(video, "rb") as f:
        d = json.load(api(CH, "PUT", r.headers["Location"], f.read(), {"Content-Type": "video/mp4"}))
    print("上げました（非公開。予約は見張りが入れる）：", f"https://youtube.com/shorts/{d['id']}")
    rec = {"work": name, "name": sname, "video_id": d["id"], "title": title, "type": s.get("type"), "long_video_id": long_up["video_id"],
           "hook": sh["cuts"][0]["narration"], "band": ["".join(t for t, _ in ln) for ln in sh.get("lines", [])],
           "uploaded_at": datetime.datetime.now(JST).isoformat(timespec="seconds")}
    json.dump(rec, open(os.path.join(work, sname, "uploaded.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    os.makedirs(os.path.dirname(hp), exist_ok=True)
    json.dump(hist + [rec], open(hp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()

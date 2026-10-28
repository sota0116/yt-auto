# ⑩アップ（金運おきぬの毎日の自動制作・2026-10-29 新設）：非公開で上げるだけ。公開の予約は見張り（watch.py）が非公開の在庫から枠に入れる
#   python -X utf8 pipeline/upload_okinu_auto.py <作業フォルダ> --channel okinu [--privacy private] [--video short.mp4] [--dry]
# ・upload_nihongi_auto.py を okinu 用に写した物。手で作った分の upload_okinu.py（予約つき）とは別の道具。
#   記録は ustore.files("okinu") の書き込める先頭（profile.json の uploaded_files。history/okinu/uploaded_auto.json）。手で上げた分の uploaded.json は読むだけ
# ・種類（short／long）：作業フォルダの名前が S… か script.json の format が short ならショート。ショートは 1080x1920・60秒以内、
#   長尺は 1920x1080・8分以上・サムネ thumb_a.jpg つき・説明文の {CHAPTERS} を chapters.txt に
# ・説明文：AI の1行・「創作」の行・VOICEVOX のクレジット（voice/_credits.txt の全員）が無ければ止まる。{LONG_URL} が残るショートは、その行を消す（長尺の URL が決まらない間）
# ・二重アップ：記録に同じ作業フォルダ・チャンネルに同じタイトルがあれば止まる。アップの後、動画が残っているかを数分見る（upload_okinu.check_after）
# ・YouTube の API を呼ぶ道具なので、試験では --dry（上げずに説明文と形だけ点検）までしか回していない
import argparse, datetime, json, os, re, sys, urllib.error

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from upload_job import ROOT, api, API, channel_titles  # noqa: E402
from upload_okinu import up1440, check_after, get  # noqa: E402
from gate_video_okinu import probe  # noqa: E402
import ustore  # noqa: E402

JST = datetime.timezone(datetime.timedelta(hours=9))
AI_LINE = "※映像とナレーションはAIを使って作っています。"


def kind_of_work(work, s):
    return "short" if re.match(r"S\d", os.path.basename(work)) or s.get("format") == "short" else "long"


def description(work, kind, s):
    d = s["desc"].strip()
    if kind == "short":
        d = "\n".join(l for l in d.split("\n") if "{LONG_URL}" not in l)
    else:
        chp = os.path.join(work, "chapters.txt")
        if not os.path.exists(chp):
            sys.exit("【止まりました】chapters.txt がありません（build_long_okinu.py が作る）")
        d = d.replace("{CHAPTERS}", "").rstrip() + "\n\n" + open(chp, encoding="utf-8").read().strip()
    if re.search(r"\{[A-Z_]+\}", d):
        sys.exit(f"【止まりました】説明文の置き換えが残っています：{re.findall(r'{[A-Z_]+}', d)}")
    if "AIを使って作っています" not in d:
        sys.exit(f"【止まりました】説明文に「{AI_LINE}」がありません（手順書 §10）")
    if "創作" not in d:
        sys.exit("【止まりました】説明文に「※お話は創作です」の行がありません（手順書 §10）")
    cp = os.path.join(work, "voice", "_credits.txt")
    names = [x.strip() for x in open(cp, encoding="utf-8").read().splitlines() if x.strip()] if os.path.exists(cp) else []
    if not names:
        sys.exit("【止まりました】voice/_credits.txt がありません（声のクレジットが決まらない）")
    miss = [x for x in names if x not in d]
    if miss:
        sys.exit(f"【止まりました】説明文に声のクレジットが足りません：{miss}（台本の desc に入れる）")
    if "PR" in d:
        sys.exit("【止まりました】説明文に PR の文字があります（手順書 §10）")
    if len(s["title"]) > 100 or len(d) > 5000 or any(c in s["title"] + d for c in "<>"):
        sys.exit("【止まりました】タイトルか説明が長すぎるか、< > が入っています")
    return d


def main():
    a = argparse.ArgumentParser()
    a.add_argument("work")
    a.add_argument("--channel", required=True, choices=["okinu"])
    a.add_argument("--privacy", default="private", choices=["private", "unlisted"])
    a.add_argument("--video")
    a.add_argument("--thumb", default="thumb_a.jpg")
    a.add_argument("--dry", action="store_true")
    a = a.parse_args()
    ch, work = a.channel, os.path.abspath(a.work)
    s = json.load(open(os.path.join(work, "script.json"), encoding="utf-8"))
    kind = kind_of_work(work, s)
    name = os.path.basename(work)
    desc = description(work, kind, s)
    title = s["title"]
    video = os.path.join(work, a.video or ("long.mp4" if kind == "long" else "short.mp4"))
    if not os.path.exists(video):
        sys.exit(f"【止まりました】ファイルがありません：{video}")
    w, h, sec = probe(video)
    if kind == "long":
        thumb = os.path.join(work, a.thumb)
        if not os.path.exists(thumb):
            sys.exit(f"【止まりました】サムネがありません：{thumb}")
        if (w, h) != (1920, 1080) or sec < 480:
            sys.exit(f"【止まりました】長尺の形ではありません（{w}x{h}・{sec:.1f}秒）")
    elif (w, h) != (1080, 1920) or sec > 60:
        sys.exit(f"【止まりました】ショートの形ではありません（{w}x{h}・{sec:.1f}秒）")
    if any(x.get("work") == name and not x.get("missing") and not x.get("retired") for x in ustore.load(ch)):
        sys.exit(f"【止めました】{name} はもう上げてあります（history の記録）")
    print(f"動画 {sec:.1f}秒・{w}x{h}・{os.path.getsize(video) / 1e6:.1f}MB・{kind}")
    print("タイトル：", title)
    print("説明文：\n" + desc)
    if a.dry:
        print("（--dry なので上げません）")
        return
    if title in channel_titles(ch):
        sys.exit("【止めました】チャンネルに同じタイトルの動画があります（二重アップの防止）")
    up = up1440(video)
    status = {"privacyStatus": a.privacy, "selfDeclaredMadeForKids": False, "containsSyntheticMedia": True, "embeddable": True, "license": "youtube"}
    meta = {"snippet": {"title": title, "description": desc, "tags": s.get("tags", []), "categoryId": "22",
                        "defaultLanguage": "ja", "defaultAudioLanguage": "ja"}, "status": status}
    r = api(ch, "POST", "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status", meta,
            {"X-Upload-Content-Type": "video/mp4", "X-Upload-Content-Length": str(os.path.getsize(up))}, timeout=120)
    with open(up, "rb") as f:
        d = json.load(api(ch, "PUT", r.headers["Location"], f.read(), {"Content-Type": "video/mp4"}))
    vid = d["id"]
    print("上げました：", f"https://youtu.be/{vid}" if kind == "long" else f"https://youtube.com/shorts/{vid}", "｜状態", d["status"].get("privacyStatus"))
    rec = {"work": name, "video_id": vid, "title": title, "kind": kind, "format": kind, "video": os.path.basename(video), "privacy": a.privacy,
           "uploaded_at": datetime.datetime.now(JST).isoformat(timespec="seconds"), "missing": False,
           "type": s.get("type"), "titles": s.get("titles", [title]), "comment": s.get("comment", "")}
    if kind == "long":
        try:
            api(ch, "POST", f"https://www.googleapis.com/upload/youtube/v3/thumbnails/set?videoId={vid}", open(thumb, "rb").read(),
                {"Content-Type": "image/jpeg"}, timeout=120)
            rec["thumb_set"] = True
            print("サムネを付けました")
        except urllib.error.HTTPError as e:
            rec["thumb_set"] = False
            print("【メモ】サムネを付けられませんでした：", e.code)
        rec["thumb"] = a.thumb
    json.dump(rec, open(os.path.join(work, "uploaded.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    rw, _ = ustore.files(ch)
    hp = os.path.join(ROOT, "history", ch, rw[0])
    hist = json.load(open(hp, encoding="utf-8")) if os.path.exists(hp) else []
    os.makedirs(os.path.dirname(hp), exist_ok=True)
    json.dump(hist + [rec], open(hp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    bad = check_after(vid)
    if bad:
        sys.exit(f"【止まりました】上げた動画が {bad}")
    print("上げた動画が残っていることを確かめました")


if __name__ == "__main__":
    main()

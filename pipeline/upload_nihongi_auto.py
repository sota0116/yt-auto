# ⑩アップ（アナザー日本紀の毎日の自動制作・2026-10-29 新設）：非公開で上げるだけ。公開の予約は見張り（watch.py）が非公開の在庫から枠に入れる
#   python -X utf8 pipeline/upload_nihongi_auto.py <作業フォルダ> --channel nihongi [--privacy private] [--video short.mp4] [--dry]
# ・手で作った分の upload_nihongi.py（予約つき）とは別の道具。記録は history/nihongi/uploaded.json（手で作った分の shorts_uploaded.json・long_uploaded.json は読むだけ。git で衝突させない）
# ・種類（short／long）と format は台本から。ショートは 1080x1920・60秒以内、横動画は 1920x1080・8分以上・サムネ thumb_a.jpg つき・説明文の最後に chapters.txt
# ・説明文：AI の1行・「作り話です」の行・VOICEVOX のクレジット（voice/_credits.txt の全員。「音声：VOICEVOX:青山龍星、VOICEVOX:…」の形）が無ければ止まる
#   ショートの {LONG_URL} の行は消す（横動画はまだ無い。上がった後に見張りが差し替えない）
# ・上げる前に、ログイン中のチャンネルが アナザー日本紀（CH_ID）かを確かめる。二重アップ：記録に同じ作業フォルダ・チャンネルに同じタイトルがあれば止まる
# ・横動画は 1440p の写しで上げる（手順書 §7）。ショートも同じ
import argparse, datetime, json, os, re, subprocess, sys, time, urllib.error

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from upload_job import ROOT, api, API, channel_titles  # noqa: E402
from upload_nihongi import CH_ID, probe, up1440, check_after, get, live  # noqa: E402
import ustore  # noqa: E402
from nihongi_common import kind_of_work, AI_LINE  # noqa: E402

JST = datetime.timezone(datetime.timedelta(hours=9))


def description(work, kind):
    s = json.load(open(os.path.join(work, "script.json"), encoding="utf-8"))
    d = s["desc"].strip()
    if kind == "short":
        d = "\n".join(l for l in d.split("\n") if "{LONG_URL}" not in l)
    else:
        chp = os.path.join(work, "chapters.txt")
        if not os.path.exists(chp):
            sys.exit("【止まりました】chapters.txt がありません（build_long.py が作る）")
        d = d.replace("{CHAPTERS}", "").rstrip() + "\n\n" + open(chp, encoding="utf-8").read().strip()
    if re.search(r"\{[A-Z_]+\}", d):
        sys.exit(f"【止まりました】説明文の置き換えが残っています：{re.findall(r'{[A-Z_]+}', d)}")
    if "AIを使って作っています" not in d:
        sys.exit(f"【止まりました】説明文に「{AI_LINE}」がありません（手順書 §4）")
    if "作り話" not in d:
        sys.exit("【止まりました】説明文に「※〇〇は作り話です」の行がありません（手順書 §4）")
    cp = os.path.join(work, "voice", "_credits.txt")
    names = [x.strip() for x in open(cp, encoding="utf-8").read().splitlines() if x.strip()] if os.path.exists(cp) else []
    if not names:
        sys.exit("【止まりました】voice/_credits.txt がありません（声のクレジットが決まらない）")
    miss = [x for x in names if x not in d]
    if miss:  # 足りない分は「音声：」の行にまとめて足す（無い時は新しく作る）
        m = re.search(r"^音声：.*$", d, re.M)
        if m:
            d = d.replace(m.group(0), m.group(0).rstrip("。") + "、" + "、".join(miss))
        else:
            d = d.rstrip() + "\n\n音声：" + "、".join(names)
    if "PR" in d:
        sys.exit("【止まりました】説明文に PR の文字があります（手順書 §10）")
    if len(s["title"]) > 100 or len(d) > 5000 or any(c in s["title"] + d for c in "<>"):
        sys.exit("【止まりました】タイトルか説明が長すぎるか、< > が入っています")
    return s, d


def main():
    a = argparse.ArgumentParser()
    a.add_argument("work")
    a.add_argument("--channel", required=True, choices=["nihongi"])
    a.add_argument("--privacy", default="private", choices=["private", "unlisted"])
    a.add_argument("--video")
    a.add_argument("--thumb", default="thumb_a.jpg")
    a.add_argument("--dry", action="store_true")
    a = a.parse_args()
    ch, work = a.channel, os.path.abspath(a.work)
    kind = kind_of_work(work)
    name = os.path.basename(work)
    s, desc = description(work, kind)
    title = s["title"]
    video = os.path.join(work, a.video or ("long.mp4" if kind == "long" else "short.mp4"))
    if not os.path.exists(video):
        sys.exit(f"【止まりました】ファイルがありません：{video}")
    sec, w, h = probe(video)
    if kind == "long":
        thumb = os.path.join(work, a.thumb)
        if not os.path.exists(thumb):
            sys.exit(f"【止まりました】サムネがありません：{thumb}")
        if (w, h) != (1920, 1080) or sec < 480:
            sys.exit(f"【止まりました】横動画の形ではありません（{w}x{h}・{sec:.1f}秒）")
    elif (w, h) != (1080, 1920) or sec > 60:
        sys.exit(f"【止まりました】ショートの形ではありません（{w}x{h}・{sec:.1f}秒）")
    hp = os.path.join(ROOT, "history", ch, "uploaded.json")
    hist = json.load(open(hp, encoding="utf-8")) if os.path.exists(hp) else []
    if any(x.get("work") == name and live(x) for x in ustore.load(ch)):
        sys.exit(f"【止めました】{name} はもう上げてあります（history の記録）")
    print(f"動画 {sec:.1f}秒・{w}x{h}・{os.path.getsize(video) / 1e6:.1f}MB・{kind}")
    print("タイトル：", title)
    print("説明文：\n" + desc)
    if a.dry:
        print("（--dry なので上げません）")
        return
    me = get(f"{API}/channels?part=id,snippet&mine=true")["items"][0]
    if me["id"] != CH_ID:
        sys.exit(f"【止まりました】ログイン中のチャンネルが違います：{me['snippet']['title']}（{me['id']}）")
    if title in channel_titles(ch):
        sys.exit("【止めました】チャンネルに同じタイトルの動画があります（二重アップの防止）")
    up = up1440(video, w, h)
    status = {"privacyStatus": a.privacy, "selfDeclaredMadeForKids": False, "containsSyntheticMedia": True, "embeddable": True, "license": "youtube"}
    meta = {"snippet": {"title": title, "description": desc, "tags": s.get("tags", []), "categoryId": "27",
                        "defaultLanguage": "ja", "defaultAudioLanguage": "ja"}, "status": status}
    r = api(ch, "POST", "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status", meta,
            {"X-Upload-Content-Type": "video/mp4", "X-Upload-Content-Length": str(os.path.getsize(up))}, timeout=120)
    with open(up, "rb") as f:
        d = json.load(api(ch, "PUT", r.headers["Location"], f.read(), {"Content-Type": "video/mp4"}))
    vid = d["id"]
    print("上げました：", f"https://youtu.be/{vid}" if kind == "long" else f"https://youtube.com/shorts/{vid}", "｜状態", d["status"].get("privacyStatus"))
    rec = {"work": name, "video_id": vid, "title": title, "kind": kind, "format": kind, "video": os.path.basename(video), "privacy": a.privacy,
           "uploaded_at": datetime.datetime.now(JST).isoformat(timespec="seconds"), "missing": False,
           "type": s.get("type"), "titles": s.get("titles", [title]), "comment": ""}
    if kind == "long":
        try:
            api(ch, "POST", f"https://www.googleapis.com/upload/youtube/v3/thumbnails/set?videoId={vid}", open(thumb, "rb").read(),
                {"Content-Type": "image/jpeg"}, timeout=120)
            rec["thumb_set"] = True
            print("サムネを付けました")
        except urllib.error.HTTPError as e:
            rec["thumb_set"] = False
            print("【メモ】サムネを付けられませんでした（電話番号の確認が済んでいないと付けられない）：", e.code)
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

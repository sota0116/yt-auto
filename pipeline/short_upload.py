# ショート⑤アップ（手順書 §12）：short.mp4 を YouTube に上げ、公開の予約（publishAt）を入れる
#   python -X utf8 pipeline\short_upload.py <作業フォルダ> --at 2026-10-28T12:10 [--go]
# ・--go を付けた時だけ上げる（付けない時は、タイトルと説明文と予約の時刻だけ出す）
# ・説明文はプログラムが作る：desc_lead → LINE の特典 → 出典（e-Stat の決まりの1文・加工して作成）→ 作り方の1文 → VOICEVOX のクレジット
# ・「AIで作った映像・声」の申告（containsSyntheticMedia）はいつもオン。二重に上げない（history\job\shorts_uploaded.json と、チャンネルの同じタイトル）
# ・記録は長尺の uploaded.json に入れない（見張り watch.py が、長尺の公開の間隔と「止まりました」の警報に使っているため）
import argparse, datetime, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from upload_job import ROOT, api, channel_titles

JST = datetime.timezone(datetime.timedelta(hours=9))
TOKUTEN = "主な職業の年収・労働時間と、産業別の離職率の一覧"  # 手順書 §4 の型A・C の特典
# ショートの説明欄のリンクは押せないので、押せるプロフィールのリンクへ案内する。URL は登録経路の計測のために残す（2026-11-02）
PROFILE_NOTE = "チャンネル名を押すと、プロフィールにLINEのリンクがあります"
HOW = "人の手では数えきれない統計をプログラムで計算し、グラフと合成音声で動画にしています。数字は全部、出典と照らしています。"
# 企業もしも（手順書 §15 の説明文）。統計ショートの「数字は全部、出典と照らしています」は使わない
HOW_KIGYO = "人物・出来事はイメージです。会社の数字は公開資料、年齢ごとの年収は業界の平均です。"
HOW_ROUTINE = "1日の流れは、公開されている資料をもとに組み立てた、ある1日の例です。時間や中身は職場によって違います。統計とネットの情報をもとに、AIで映像と声にしています。"


def description(work, ch="job"):
    sc = json.load(open(os.path.join(work, "script.json"), encoding="utf-8"))
    fx = json.load(open(os.path.join(work, "facts.json"), encoding="utf-8"))
    prof = json.load(open(os.path.join(ROOT, "channels", ch, "profile.json"), encoding="utf-8"))
    src = "\n".join(f"出典：{s['名前']}（{s['公表日']} 公表）\n{s['URL']}" for s in fx["出典"])
    credit = prof["voicevox"]["credit"]
    tags = " ".join("#" + t for t in sc.get("tags", [])[:3])
    how = HOW
    if fx.get("kind") == "routine":  # 1日の流れ（手順書 §7・§12）：例であることと、調べた資料を書く。声は語り手だけ
        how = HOW_ROUTINE
        credit = credit.split("、")[0]
        urls = list(dict.fromkeys(x["url"] for x in sc.get("day_facts", []) if "PR" not in x["url"]))
        src = "▼1日の流れの資料\n" + "\n".join(urls) + "\n\n" + src
    if fx.get("kind") == "kigyo":  # 企業もしも（§15）：会社の数字と記事の URL → 統計の出典 → イメージの断り → ロゴの断りと出どころ。声は語り手だけ
        credit = credit.split("、")[0]
        urls = list(dict.fromkeys(x["url"] for x in sc.get("day_facts", [])))
        src = "▼会社の数字と記事\n" + "\n".join(urls) + "\n\n▼年齢ごとの年収（業界の平均）\n" + src
        # CC BY のロゴは作者とライセンスの表示が要る（Commons の各ページの条件）
        logos = "\n".join(f"{l['会社']}：Wikimedia Commons（{l['license']}{'・' + l['作者'] if l.get('作者') and 'BY' in l['license'] else ''}）{l['page']}"
                          for l in fx["logos"])
        how = f"{HOW_KIGYO}\n{fx['ロゴの断り']}。\n▼ロゴの出どころ\n{logos}"
    d = (f"{sc['desc_lead']}\n\n▼{TOKUTEN}を、LINEで無料で受け取れます\n{PROFILE_NOTE}\n{prof.get('line_url_short') or prof['line_url']}\n\n{src}\n{fx['e_stat_note']}\n{fx['加工']}\n\n"
         f"{how}\n{credit}\n\n{tags}")
    if "PR" in d:
        sys.exit("【止まりました】説明文に PR の文字があります（手順書 §10）")
    return sc, d


def main():
    a = argparse.ArgumentParser()
    a.add_argument("work")
    a.add_argument("--at", required=True, help="公開の予約（日本時間）例 2026-10-28T12:10")
    a.add_argument("--go", action="store_true")
    a = a.parse_args()
    work, ch = os.path.abspath(a.work), "job"
    sc, desc = description(work, ch)
    at = datetime.datetime.fromisoformat(a.at).replace(tzinfo=JST)
    if at < datetime.datetime.now(JST) + datetime.timedelta(minutes=30):
        sys.exit(f"【止まりました】予約の時刻 {at:%m/%d %H:%M} が近すぎるか過ぎています")
    import day_slots
    day_slots.check("job", at)  # 2026-11-04〜 同じチャンネルの公開・予約と3時間以上あける（本人「動画と動画の間は時間を空けて」）
    video = os.path.join(work, "short.mp4")
    if not os.path.exists(video):
        sys.exit(f"【止まりました】{video} がありません")
    print("タイトル：", sc["title"])
    print("予約：", at.isoformat())
    print("説明文：\n" + desc)
    if not a.go:
        print("（--go が無いので上げません）")
        return
    hp = os.path.join(ROOT, "history", ch, "shorts_uploaded.json")
    hist = json.load(open(hp, encoding="utf-8")) if os.path.exists(hp) else []
    name = os.path.basename(work)
    if any(h["work"] == name for h in hist) or sc["title"] in channel_titles(ch):
        sys.exit("【止めました】もう上げてあります（二重アップの防止）")
    status = {"privacyStatus": "private", "publishAt": at.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
              "selfDeclaredMadeForKids": False, "containsSyntheticMedia": True}
    meta = {"snippet": {"title": sc["title"], "description": desc, "tags": sc.get("tags", []), "categoryId": "27",
                        "defaultLanguage": "ja", "defaultAudioLanguage": "ja"}, "status": status}
    size = os.path.getsize(video)
    r = api(ch, "POST", "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status", meta,
            {"X-Upload-Content-Type": "video/mp4", "X-Upload-Content-Length": str(size)}, timeout=120)
    with open(video, "rb") as f:
        d = json.load(api(ch, "PUT", r.headers["Location"], f.read(), {"Content-Type": "video/mp4"}))
    print("上げました：", f"https://youtube.com/shorts/{d['id']}", "｜予約", d["status"].get("publishAt"))
    rec = {"work": name, "video_id": d["id"], "title": sc["title"], "format": "short", "privacy": "private",
           "publish_at": at.isoformat(), "uploaded_at": datetime.datetime.now(JST).isoformat(timespec="seconds"), "missing": False}
    json.dump(rec, open(os.path.join(work, "uploaded.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump(hist + [rec], open(hp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()

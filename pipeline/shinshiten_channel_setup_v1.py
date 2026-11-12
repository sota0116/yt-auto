# シン視点事件簿（shinshiten）のチャンネルの説明とキーワードを API で入れる（v1・2026-11-12）
#   python -X utf8 pipeline\shinshiten_channel_setup_v1.py <チャンネル設定フォルダ> --ver v2_2026-11-12 [--go]
# ・入れる物：説明・キーワードだけ（国・言語は日本／日本語にそろえる）。ヘッダー・透かし・名前・アイコンには触らない
# ・説明は チャンネル説明欄_<ver>.txt、キーワードは チャンネルキーワード_<ver>.txt（カンマ区切り）をそのまま使う
# ・--go の前に、今の本番の説明とキーワードを チャンネル設定\_本番の控え_<日時>.json に残す（戻す時に使う）
# ・--go が無い時は、入れる中身と今の状態だけ出す
# 元：nihongi_channel_setup.py（看板一式を入れる版）から、説明とキーワードだけに絞った
import argparse, datetime, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from upload_job import api, API

CH = "shinshiten"
CH_ID = "UCqjsFHU9ACKQFassZJJwAcA"


def get(url):
    return json.load(api(CH, "GET", url, timeout=60))


def kw_line(words):
    # YouTube のキーワードは空白区切り。空白を含む語は "" で囲む
    return " ".join(f'"{w}"' if " " in w else w for w in words)


def main():
    a = argparse.ArgumentParser()
    a.add_argument("root")
    a.add_argument("--ver", required=True)
    a.add_argument("--go", action="store_true")
    a = a.parse_args()
    root = os.path.abspath(a.root)
    pd = os.path.join(root, f"チャンネル説明欄_{a.ver}.txt")
    pk = os.path.join(root, f"チャンネルキーワード_{a.ver}.txt")
    for p in (pd, pk):
        if not os.path.exists(p):
            sys.exit(f"【止まりました】ファイルがありません：{p}")
    desc = open(pd, encoding="utf-8").read().strip()
    words = [w.strip() for w in open(pk, encoding="utf-8").read().replace("、", ",").split(",") if w.strip()]
    kw = kw_line(words)
    if len(desc) > 1000 or "<" in desc or ">" in desc:
        sys.exit(f"【止まりました】説明が1000字をこえるか < > が入っています（{len(desc)}字）")
    if len(kw) > 500:
        sys.exit(f"【止まりました】キーワードが500字をこえています（{len(kw)}字）")
    ch = get(f"{API}/channels?part=id,snippet,brandingSettings&mine=true")["items"][0]
    if ch["id"] != CH_ID:
        sys.exit(f"【止まりました】ログイン中のチャンネルが違います：{ch['snippet']['title']}（{ch['id']}）")
    bs = ch.get("brandingSettings", {})
    chan = bs.get("channel", {})
    print("今の名前：", ch["snippet"]["title"])
    print("今の説明（", len(chan.get("description", "")), "字）／今のキーワード：", chan.get("keywords"))
    print("入れる説明（", len(desc), "字）：\n" + desc)
    print("入れるキーワード（", len(words), "語）：", kw)
    if not a.go:
        print("（--go が無いので入れません）")
        return
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    bk = os.path.join(root, f"_本番の控え_{stamp}.json")
    with open(bk, "w", encoding="utf-8") as f:
        json.dump({"channel_id": CH_ID, "title": ch["snippet"]["title"], "brandingSettings_channel": chan}, f, ensure_ascii=False, indent=2)
    print("今の本番を控えました：", bk)
    # PUT は送らなかった項目を消すので、今の brandingSettings（ヘッダー画像など）を丸ごと引き継ぎ、channel の2項目だけ替える
    chan = dict(chan)
    chan.update({"description": desc, "keywords": kw, "country": "JP", "defaultLanguage": "ja"})
    nbs = dict(bs)
    nbs["channel"] = chan
    api(CH, "PUT", f"{API}/channels?part=brandingSettings", {"id": CH_ID, "brandingSettings": nbs}, timeout=60)
    print("説明・キーワードを入れました")
    after = get(f"{API}/channels?part=brandingSettings&id={CH_ID}")["items"][0]["brandingSettings"]
    c = after.get("channel", {})
    ok_d = c.get("description", "").strip() == desc
    ok_k = c.get("keywords", "").split() == kw.split()
    print("確かめ：説明", "OK" if ok_d else "違う", "｜キーワード", "OK" if ok_k else "違う", "｜", c.get("keywords"),
          "｜国", c.get("country"), "｜ヘッダー", "あり" if after.get("image", {}).get("bannerExternalUrl") else "なし（元から無いなら問題なし）")
    if not (ok_d and ok_k):
        sys.exit("【確かめで違いがあります】上の表示を見て、控えの json から戻すか判断してください")


if __name__ == "__main__":
    main()

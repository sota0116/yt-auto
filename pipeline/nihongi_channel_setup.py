# アナザー日本紀（nihongi）のチャンネルの看板を API で入れる（2026-10-27）
#   python -X utf8 pipeline\nihongi_channel_setup.py <アナザー日本紀フォルダ> --ver v1 [--go]
# ・入れる物：説明・キーワード・国（日本）・ヘッダー（branding\banner_<ver>.png）・動画の透かし（branding\watermark_<ver>.png）
# ・説明とキーワードは 設計\チャンネル看板_アナザー日本紀_<ver>_*.md の「説明文」「キーワード」のコードの中をそのまま使う
# ・名前・ハンドル・アイコンは API で変えられないので、Studio（ブラウザ）で入れる
# ・--go が無い時は、入れる中身と今の状態だけ出す
import argparse, glob, json, os, re, sys, uuid
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from upload_job import api, API

CH = "nihongi"
CH_ID = "UCPUDU140U5U8xXWYFLPHZKg"
UP = "https://www.googleapis.com/upload/youtube/v3"


def get(url):
    return json.load(api(CH, "GET", url, timeout=60))


def block(md, head):
    m = re.search(r"## " + head + r"[^\n]*\n```\n(.*?)\n```", md, re.S)
    if not m:
        sys.exit(f"【止まりました】看板の md に「{head}」のコードの欄がありません")
    return m.group(1).strip()


def main():
    a = argparse.ArgumentParser()
    a.add_argument("root")
    a.add_argument("--ver", required=True)
    a.add_argument("--go", action="store_true")
    a = a.parse_args()
    root = os.path.abspath(a.root)
    mds = glob.glob(os.path.join(os.path.dirname(root), "設計", f"チャンネル看板_アナザー日本紀_{a.ver}_*.md"))
    if len(mds) != 1:
        sys.exit(f"【止まりました】看板の md が1つに決まりません：{mds}")
    md = open(mds[0], encoding="utf-8").read()
    desc, kw = block(md, "説明文"), " ".join(block(md, "キーワード").split())
    banner = os.path.join(root, "branding", f"banner_{a.ver}.png")
    wm = os.path.join(root, "branding", f"watermark_{a.ver}.png")
    for p in (banner, wm):
        if not os.path.exists(p):
            sys.exit(f"【止まりました】ファイルがありません：{p}")
    if len(desc) > 1000 or "<" in desc or ">" in desc:
        sys.exit("【止まりました】説明が1000字をこえるか < > が入っています")
    ch = get(f"{API}/channels?part=id,snippet,brandingSettings&mine=true")["items"][0]
    if ch["id"] != CH_ID:
        sys.exit(f"【止まりました】ログイン中のチャンネルが違います：{ch['snippet']['title']}（{ch['id']}）")
    print("今の名前：", ch["snippet"]["title"])
    print("入れる説明（", len(desc), "字）：\n" + desc)
    print("入れるキーワード：", kw)
    print("ヘッダー：", banner, "｜透かし：", wm)
    if not a.go:
        print("（--go が無いので入れません）")
        return
    # ヘッダー：画像を上げて URL をもらい、brandingSettings に入れる
    r = json.load(api(CH, "POST", f"{UP}/channelBanners/insert", open(banner, "rb").read(), {"Content-Type": "image/png"}, timeout=120))
    bs = ch.get("brandingSettings", {})
    chan = bs.get("channel", {})
    chan.update({"description": desc, "keywords": kw, "country": "JP", "defaultLanguage": "ja"})
    body = {"id": CH_ID, "brandingSettings": {"channel": chan, "image": {"bannerExternalUrl": r["url"]}}}
    api(CH, "PUT", f"{API}/channels?part=brandingSettings", body, timeout=60)
    print("説明・キーワード・国・ヘッダーを入れました")
    # 透かし：動画のはじめから終わりまで。角は API の決まりの topRight（画面のどこに出るかは YouTube が決める）
    bd = uuid.uuid4().hex
    meta = {"timing": {"type": "offsetFromStart", "offsetMs": 0}, "position": {"type": "corner", "cornerPosition": "topRight"}}
    data = (f"--{bd}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n{json.dumps(meta)}\r\n"
            f"--{bd}\r\nContent-Type: image/png\r\n\r\n").encode() + open(wm, "rb").read() + f"\r\n--{bd}--\r\n".encode()
    api(CH, "POST", f"{UP}/watermarks/set?channelId={CH_ID}&uploadType=multipart", data,
        {"Content-Type": f"multipart/related; boundary={bd}"}, timeout=120)
    print("透かしを入れました")
    after = get(f"{API}/channels?part=brandingSettings&id={CH_ID}")["items"][0]["brandingSettings"]
    c = after.get("channel", {})
    print("確かめ：説明", "OK" if c.get("description", "").strip() == desc else "違う", "｜キーワード", c.get("keywords"),
          "｜国", c.get("country"), "｜ヘッダー", "あり" if after.get("image", {}).get("bannerExternalUrl") else "なし")


if __name__ == "__main__":
    main()

# 企業もしもショート①題選び（手順書 §15。2026-11-14 本人「OK」）
#   python -X utf8 pipeline\kigyo_pick.py --out <作業フォルダ> [--id kigyo_shoken] [--list]
# ・channels\job\kigyo_topics.json の上から、まだ作れていない題を1つ選び、facts.json を作る
# ・年齢の札は data\job\kigyo_r7.json（その産業・1,000人以上・年齢階級）。値と声の言い方はここで計算する（Claude は計算しない）
# ・ロゴは Wikimedia Commons から取り、作業フォルダの logos\ に置く。出どころ（ページ・ライセンス・作者・取った日）を facts.json の logos に残す（決まり4）
import argparse, datetime, json, os, re, sys, time
import requests
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from job_facts_common import ROOT, load, man, voice_man, sources_block, write
from short_pick import history

TOPICS = os.path.join(ROOT, "channels", "job", "kigyo_topics.json")
AGES = ["20～24歳", "25～29歳", "30～34歳", "35～39歳", "40～44歳", "45～49歳", "50～54歳", "55～59歳", "60～64歳"]
COMMONS = "https://commons.wikimedia.org/w/api.php"
UA = {"User-Agent": "yt-auto-kigyo/1.0 (https://github.com/sota0116/yt-auto)"}
JST = datetime.timezone(datetime.timedelta(hours=9))
LOGO_NOTE = "ロゴは各社の商標です。この動画は各社と関係ありません"
IMAGE_NOTE = "人物・出来事はイメージです"


def topics():
    return json.load(open(TOPICS, encoding="utf-8"))["題"]


def choose(ts, want=None):
    if want:
        t = next((x for x in ts if x["id"] == want), None)
        if not t:
            sys.exit(f"【止まりました】kigyo_topics.json に {want} がありません")
        return t
    h = [x for x in history() if x.get("kind") == "kigyo"]
    done = {x["topic_id"] for x in h if x.get("ok")}
    bad = {t for t in {x["topic_id"] for x in h} if sum(x["topic_id"] == t and not x.get("ok") and "make_images_lovart" not in (x.get("why") or "") for x in h) >= 2}
    q = [x for x in ts if x.get("準備") and x["id"] not in done | bad]
    if not q:
        sys.exit("【止まりました】企業もしもの題が残っていません（kigyo_topics.json の 準備 を確かめる）")
    return q[0]


def age_voice(a):
    lo = int(re.match(r"\d+", a).group())
    return f"{lo // 10 * 10}代{'前半' if lo % 10 == 0 else '後半'}"


def age_tags(code):
    d = load("kigyo_r7.json")
    rec = d["data"][code]
    out = []
    for a in AGES:
        v = rec["年齢階級"].get(a) or {}
        if v.get("年収_千円") is None:
            sys.exit(f"【止まりました】kigyo_r7.json の {code} {a} に年収がありません")
        out.append({"年齢": a, "声の年齢": age_voice(a), "年収_千円": v["年収_千円"], "年収_万円": man(v["年収_千円"]),
                    "声の年収": voice_man(v["年収_千円"]), "札": f"{a.replace('～', '〜')} {voice_man(v['年収_千円']).lstrip('約')}"})
    top = max(out, key=lambda x: x["年収_千円"])
    return rec["表の名前"], out, top, d["meta"]


def logo(title, folder):
    """Commons のファイル1つを PNG（横960）で取る。SVG も Commons が PNG にした物を使う（形・色・比は変えない）"""
    r = requests.get(COMMONS, params={"action": "query", "prop": "imageinfo", "iiprop": "url|extmetadata", "iiurlwidth": 960,
                                      "format": "json", "titles": title}, headers=UA, timeout=30)
    r.raise_for_status()
    p = next(iter(r.json()["query"]["pages"].values()))
    if "imageinfo" not in p:
        sys.exit(f"【止まりました】Wikimedia Commons に {title} がありません")
    ii = p["imageinfo"][0]
    m = ii.get("extmetadata", {})
    g = lambda k: re.sub(r"<[^>]+>", "", (m.get(k) or {}).get("value", "")).strip()
    url = ii.get("thumburl") or ii["url"]
    img = requests.get(url, headers=UA, timeout=60)
    img.raise_for_status()
    name = re.sub(r"[^\w.-]", "_", title.split(":", 1)[1]).rsplit(".", 1)[0] + ".png"
    os.makedirs(folder, exist_ok=True)
    open(os.path.join(folder, name), "wb").write(img.content)
    time.sleep(1)  # Commons に続けて聞きすぎない
    return {"file": title, "page": ii["descriptionurl"], "png": "logos/" + name, "license": g("LicenseShortName"),
            "作者": g("Artist"), "取った日": datetime.datetime.now(JST).date().isoformat()}


def facts(t, work):
    ind, tags, top, meta = age_tags(t["産業"])
    logos = []
    for c in t["並べる会社"]:
        if not c.get("logo"):
            sys.exit(f"【止まりました】{c['名前']} のロゴの出どころが kigyo_topics.json にありません")
        logos.append({"会社": c["名前"], **logo(c["logo"], os.path.join(work, "logos"))})
    call = t["会社"]
    return {"kind": "kigyo", "topic_id": t["id"], "measure": "企業_" + t["業界"], "業界": t["業界"], "会社": call, "正式名": t["正式名"],
            "読み": t["読み"], "呼び名": call, "題": f"もし{call}に就職したら",
            "産業": {"記号": t["産業"], "名前": ind, "声": ind.replace("，", "・")},
            "年齢の札": tags, "年収が一番高い年齢": {"年齢": top["年齢"], "声の年齢": top["声の年齢"], "声の年収": top["声の年収"]},
            "年齢の札の注意": f"会社の数字ではない。{ind.replace('，', '・')}で働く人の、企業規模1,000人以上・男女計・学歴計の平均（{meta['表']}）。"
                         "画面の札には「業界の平均」と出す。同じ人の記録のように言わない（手順書 §15 決まり1）",
            "資料": t.get("資料", []), "台本": t.get("台本"), "logos": logos, "ロゴの断り": LOGO_NOTE, "イメージの断り": IMAGE_NOTE,
            "定義": {"年収": "きまって支給する現金給与額×12＋年間賞与その他特別給与額（賞与は前の年1年分）"},
            "対象": "一般労働者（短時間労働者を除く）・民営事業所・企業規模1,000人以上・男女計・学歴計",
            "charts": [], **sources_block(["chinkin_r7_sangyo_t1"])}


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--out")
    a.add_argument("--id")
    a.add_argument("--list", action="store_true")
    a = a.parse_args()
    ts = topics()
    if a.list:
        print(json.dumps([{"id": x["id"], "業界": x["業界"], "会社": x.get("会社"), "準備": x.get("準備")} for x in ts], ensure_ascii=False))
        return
    t = choose(ts, a.id)
    work = os.path.join(ROOT, a.out)
    f = facts(t, work)
    write(work, f)
    print(json.dumps({"work": a.out, "topic_id": f["topic_id"], "題": f["題"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()

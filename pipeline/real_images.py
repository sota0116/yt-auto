# 実際の画像を置く（2026-11-04 新設。本人の決定「ネットで拾った実際の画像は条件なしで使ってよい」・memory feedback_youtube_real_images_ok）
#   台本の書き手がカットに "real": "<検索語（英語）>" か "real": "https://...（画像の URL）" を書くと、
#   画像を取ってきて images/<id>.png（横動画 1920x1080／ショート 1080x1920）に置き、そのカットの "image" を外す。
#   → make_images_lovart.py は作らず（png があり image も無い）、gate_images.py も見ない（image のあるカットだけ見る）。
#     image_en は残す（台本ゲートが必須にしている・取れなかった時の予備）。
# ・探す所：検索語なら Wikimedia Commons（鍵なし）。URL ならそのまま取る
# ・はめ方：画像の全体を見せる（古地図・屏風・古書の端を切らない）。余白は同じ画像を広げてぼかし、少し暗くして敷く
# ・付けないカット：chars（人物の絵）・anim / motion（動く絵）・peak（見どころ）・voice（セリフ）・hook・same_as・サムネの背景（thumb_bg / THUMB）。付いていても AI の絵のまま
# ・取れない時はそのカットは AI の絵のまま（回は止めない）
# ・出どころは script.json の各カット "real_src" と history/<ch>/real_images.json に残す（images は上げたあと消えるので。申し立てが来た時に差し替える相手を探すため）
#   単体で試す：python -X utf8 pipeline/real_images.py <作業フォルダ> --ch nihongi
import argparse, datetime, io, json, os, sys, urllib.parse, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UA = {"User-Agent": "yt-auto-real-images/1.0 (YouTube video assets)"}
API = "https://commons.wikimedia.org/w/api.php"
MIN_W = 800  # これより小さい元画像は使わない（画面でぼやける）
SKIP_KEYS = ("chars", "anim", "motion", "peak", "voice", "hook", "same_as", "chart", "card")


def _get(url, timeout=40):
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout).read()


def commons(term, n=12):
    """[(題, 画像の URL, 説明ページ, 元の幅, 元の高さ)]。並びは Commons の検索順"""
    q = {"action": "query", "format": "json", "generator": "search", "gsrsearch": f"{term} filetype:bitmap", "gsrnamespace": "6",
         "gsrlimit": str(n), "prop": "imageinfo", "iiprop": "url|size|mime", "iiurlwidth": "1920"}
    r = json.loads(_get(API + "?" + urllib.parse.urlencode(q)))
    out = []
    for p in sorted((r.get("query") or {}).get("pages", {}).values(), key=lambda x: x.get("index", 0)):
        ii = (p.get("imageinfo") or [{}])[0]
        if ii.get("width", 0) < MIN_W or ii.get("mime") not in ("image/jpeg", "image/png", "image/tiff", "image/webp"):
            continue
        out.append((p["title"], ii.get("thumburl") or ii.get("url"), ii.get("descriptionurl"), ii["width"], ii["height"]))
    return out


def fit(img, W, H):
    """全体を見せて、余白はぼかした同じ画像で埋める"""
    from PIL import Image, ImageEnhance, ImageFilter
    img = img.convert("RGB")
    s = max(W / img.width, H / img.height)
    bg = img.resize((max(W, int(img.width * s) + 1), max(H, int(img.height * s) + 1)), Image.LANCZOS)
    bg = bg.crop(((bg.width - W) // 2, (bg.height - H) // 2, (bg.width - W) // 2 + W, (bg.height - H) // 2 + H))
    bg = ImageEnhance.Brightness(bg.filter(ImageFilter.GaussianBlur(36))).enhance(0.55)
    s = min(W / img.width, H / img.height)
    fg = img.resize((int(img.width * s), int(img.height * s)), Image.LANCZOS)
    bg.paste(fg, ((W - fg.width) // 2, (H - fg.height) // 2))
    return bg


def _open(data):
    from PIL import Image
    im = Image.open(io.BytesIO(data))
    im.load()
    return im


def used_before(ch, keep=60):
    p = os.path.join(ROOT, "history", ch, "real_images.json")
    rows = json.load(open(p, encoding="utf-8")) if os.path.exists(p) else []
    return {r.get("題") for r in rows[-keep:]}


def place(work, c, size, avoid):
    """1カット分。置けたら出どころの記録を返す。置けなければ None"""
    want = str(c.get("real") or "").strip()
    if not want:
        return None
    dst = os.path.join(work, "images", c["id"] + ".png")
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    tries = [(want, want, want)] if want.startswith("http") else [(t, u, d) for t, u, d, _w, _h in commons(want) if t not in avoid][:5]
    for title, url, page in tries:
        try:
            im = _open(_get(url))
            if im.width < MIN_W * 0.8:
                continue
            fit(im, *size).save(dst)
            return {"題": title, "url": url, "説明ページ": page, "検索語": want}
        except Exception as e:  # 1枚だめでも次を試す
            print(f"  （実画像 {c['id']}：{title} が取れない {type(e).__name__}）")
    return None


def apply(work, s, ch, kind):
    """script.json（読み込み済みの dict）の "real" のあるカットに実画像を置く。置いた枚数を返す。s は書き換えるだけで保存はしない"""
    size = (1080, 1920) if kind == "short" else (1920, 1080)
    avoid = used_before(ch)
    log, n = [], 0
    th = s.get("thumb") if isinstance(s.get("thumb"), dict) else {}
    thumb = {s.get("thumb_bg") or "THUMB", "THUMB"} | {th.get(k) for k in ("bg", "face", "left", "right") if isinstance(th.get(k), str)}
    # ↑ サムネの背景のカットは AI の絵のまま（サムネの型と点検が image を前提にしている。okinu は thumb の bg・face・left・right。2026-11-05）
    for c in s.get("cuts", []):
        if not c.get("real"):
            continue
        if c.get("id") in thumb:
            print(f"  （実画像 {c['id']}：サムネの背景なので AI の絵のまま）")
            continue
        if any(c.get(k) for k in SKIP_KEYS):
            print(f"  （実画像 {c['id']}：人物・動く絵・見どころ・セリフのカットなので AI の絵のまま）")
            continue
        dst = os.path.join(work, "images", c["id"] + ".png")
        if c.get("real_src") and os.path.exists(dst):  # 書き直し（--fix）で2回目に来た時
            c.pop("image", None)
            n += 1
            continue
        try:
            src = place(work, c, size, avoid)
        except Exception as e:
            src = None
            print(f"  （実画像 {c['id']}：探せない {type(e).__name__}: {e}）")
        if not src:
            print(f"  （実画像 {c['id']}：見つからないので AI の絵のまま。検索語「{c['real']}」）")
            continue
        avoid.add(src["題"])
        c["real_src"] = src
        c.pop("image", None)
        n += 1
        log.append({"日": datetime.date.today().isoformat(), "回": os.path.basename(work.rstrip("/\\")), "カット": c["id"], **src})
    if log:
        p = os.path.join(ROOT, "history", ch, "real_images.json")
        rows = json.load(open(p, encoding="utf-8")) if os.path.exists(p) else []
        os.makedirs(os.path.dirname(p), exist_ok=True)
        json.dump(rows + log, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"実画像：{n} カット（指定 {sum(1 for c in s.get('cuts', []) if c.get('real'))}）")
    return n


def main():
    a = argparse.ArgumentParser()
    a.add_argument("work")
    a.add_argument("--ch", required=True)
    a.add_argument("--kind", choices=("short", "long"))
    a = a.parse_args()
    work = os.path.abspath(a.work)
    sp = os.path.join(work, "script.json")
    s = json.load(open(sp, encoding="utf-8"))
    kind = a.kind or ("short" if s.get("format") == "short" else "long")
    apply(work, s, a.ch, kind)
    json.dump(s, open(sp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()

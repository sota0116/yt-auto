# 実際の画像を置く（2026-11-04 新設。本人の決定「ネットで拾った実際の画像は条件なしで使ってよい」／2026-11-24 追加「SNSの画像も使っていい」）
#   台本の書き手がカットに "real": "<検索語（英語または日本語）>" か "real": "https://...（画像またはSNSポストの URL）" を書くと、
#   画像を取ってきて images/<id>.png（横動画 1920x1080／ショート 1080x1920）に置き、そのカットの "image" を外す。
#   → make_images_lovart.py は作らず（png があり image も無い）、gate_images.py も見ない（image のあるカットだけ見る）。
#     image_en は残す（台本ゲートが必須にしている・取れなかった時の予備）。
# ・探す所（2026-11-24 拡張。鍵不要・応答確認済みの公開ソースのみ）：
#   1. Wikimedia Commons（先頭。見つからない時だけ次へ回す）
#   2. Openverse
#   3. ジャパンサーチ（国立国会図書館デジタルコレクション IIIF 1920px 引き上げ・ColBase 等横断）
#   4. NASA Images
#   5. Bing 画像検索（一般 Web＋SNS 上の公開画像。透かし系ストック素材は除外）
#   URL 直接指定時：
#   - X / Twitter ポスト URL（https://x.com/<user>/status/<id> 等）→ api.fxtwitter.com で写真本体を解決
#   - Bluesky ポスト URL（https://bsky.app/profile/<handle>/post/<rkey>）→ public.api.bsky.app（resolveHandle＋getPostThread）で写真本体を解決
#   - Wikimedia Commons File: ページ URL → imageinfo API で画像本体を解決
#   - 画像直 URL（pbs.twimg.com・cdn.bsky.app・その他 http(s)）→ そのまま取得
# ・適合確認（2026-11-24 追加）：候補を最大3枚まとめて Gemini（gemini.py の無料キー ask_media）に見せ、
#   検索語と narration に合う1枚を選ぶ（どれも合わなければ「なし」＝AI の絵のまま）。
#   Gemini が使えない時（鍵なし・429・上限）は従来どおり先頭を置き、回は止めない。1カットにつき Gemini は1回まで。
# ・はめ方：画像の全体を見せる（古地図・屏風・古書の端を切らない）。余白は同じ画像を広げてぼかし、少し暗くして敷く
# ・付けないカット：chars・anim / motion・peak・voice・hook・same_as・chart・card・reenact・サムネの背景（thumb_bg / THUMB）
# ・取れない時はそのカットは AI の絵のまま（回は止めない）
# ・出どころ（どの源から取ったか "源" と元 URL を含む）は script.json の各カット "real_src" と history/<ch>/real_images.json に残す
#   単体で試す：python -X utf8 pipeline/real_images.py <作業フォルダ> --ch nihongi [--no-gemini]
import argparse, datetime, html as html_mod, io, json, os, re, sys, tempfile, urllib.parse, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UA = {"User-Agent": "yt-auto-real-images/1.0 (YouTube video assets)"}
BROWSER_UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"}
API = "https://commons.wikimedia.org/w/api.php"
OPENVERSE_API = "https://api.openverse.org/v1/images/"
JPS_API = "https://jpsearch.go.jp/api/item/search/jps-cross"
NASA_API = "https://images-api.nasa.gov/search"
BING_API = "https://www.bing.com/images/async"
BSKY_PUBLIC_API = "https://public.api.bsky.app/xrpc"
FXTWITTER_API = "https://api.fxtwitter.com"
MIN_W = 800  # これより小さい元画像は使わない（画面でぼやける）
MAX_CANDS = 3  # Gemini にまとめて見せる候補の上限（1カット1回まで）
SKIP_KEYS = ("chars", "anim", "motion", "peak", "voice", "hook", "same_as", "chart", "card", "reenact")
STOCK_WATERMARK_HOSTS = (
    "gettyimages.", "shutterstock.", "istockphoto.", "alamy.", "depositphotos.",
    "dreamstime.", "123rf.", "vecteezy.", "freepik.", "pixta.", "amanaimages.",
    "stock.adobe.", "bigstockphoto.", "canstockphoto.",
)
SNS_HOSTS = ("pbs.twimg.com", "cdn.bsky.app", "x.com", "twitter.com", "bsky.app", "i.redd.it")

_gemini_disabled = False
_gemini_reason = ""


def _get(url, timeout=40, headers=None):
    h = dict(UA)
    if headers:
        h.update(headers)
    return urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=timeout).read()


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


def _commons_file_page(url):
    """https://commons.wikimedia.org/wiki/File:... のページ URL を実際の画像 URL へ解決する"""
    m = re.search(r"commons\.wikimedia\.org/wiki/(File:[^#?]+)", url)
    if not m:
        return []
    title = urllib.parse.unquote(m.group(1)).replace("_", " ")
    q = {"action": "query", "format": "json", "titles": title, "prop": "imageinfo", "iiprop": "url|size|mime", "iiurlwidth": "1920"}
    r = json.loads(_get(API + "?" + urllib.parse.urlencode(q)))
    out = []
    for p in (r.get("query") or {}).get("pages", {}).values():
        ii = (p.get("imageinfo") or [{}])[0]
        if ii.get("width", 0) < MIN_W or ii.get("mime") not in ("image/jpeg", "image/png", "image/tiff", "image/webp"):
            continue
        out.append((p.get("title", title), ii.get("thumburl") or ii.get("url"), ii.get("descriptionurl") or url,
                    ii["width"], ii["height"], "wikimedia_commons"))
    return out


def _x_post_images(url):
    """https://x.com/<user>/status/<id>（twitter.com 含む）から api.fxtwitter.com 経由で写真本体 URL を解決する"""
    m = re.search(r"https?://(?:www\.|mobile\.)?(?:x|twitter)\.com/([^/?#]+)/status/(\d+)", url)
    if not m:
        return []
    user, tid = m.group(1), m.group(2)
    r = json.loads(_get(f"{FXTWITTER_API}/{user}/status/{tid}", timeout=25, headers={"Accept": "application/json"}))
    tw = r.get("tweet") or {}
    photos = (tw.get("media") or {}).get("photos") or []
    author = (tw.get("author") or {}).get("screen_name") or user
    text = re.sub(r"\s+", " ", str(tw.get("text") or "")).strip()[:60]
    out = []
    for i, ph in enumerate(photos, 1):
        img_url = ph.get("url")
        if not img_url:
            continue
        title = f"X @{author} ({tid}#{i}) {text}".strip()
        out.append((title, img_url, url, int(ph.get("width") or 0), int(ph.get("height") or 0), "x_post"))
    return out


def _bsky_post_images(url):
    """https://bsky.app/profile/<actor>/post/<rkey> から Bluesky 公開 API で写真本体 URL を解決する"""
    m = re.search(r"https?://bsky\.app/profile/([^/?#]+)/post/([^/?#]+)", url)
    if not m:
        return []
    actor, rkey = m.group(1), m.group(2)
    did = actor
    if not actor.startswith("did:"):
        r_did = json.loads(_get(f"{BSKY_PUBLIC_API}/com.atproto.identity.resolveHandle?" + urllib.parse.urlencode({"handle": actor}),
                                timeout=20, headers={"Accept": "application/json"}))
        did = r_did.get("did") or actor
    at_uri = f"at://{did}/app.bsky.feed.post/{rkey}"
    r = json.loads(_get(f"{BSKY_PUBLIC_API}/app.bsky.feed.getPostThread?" + urllib.parse.urlencode({"uri": at_uri, "depth": "0"}),
                        timeout=25, headers={"Accept": "application/json"}))
    post = (r.get("thread") or {}).get("post") or {}
    emb = post.get("embed") or {}
    imgs = emb.get("images") or (emb.get("media") or {}).get("images") or []
    handle = (post.get("author") or {}).get("handle") or actor
    rec_text = re.sub(r"\s+", " ", str((post.get("record") or {}).get("text") or "")).strip()[:60]
    out = []
    for i, im in enumerate(imgs, 1):
        img_url = im.get("fullsize") or im.get("thumb")
        if not img_url:
            continue
        alt = re.sub(r"\s+", " ", str(im.get("alt") or "")).strip()[:50]
        title = f"Bluesky @{handle} ({rkey}#{i}) {alt or rec_text}".strip()
        ar = im.get("aspectRatio") or {}
        out.append((title, img_url, url, int(ar.get("width") or 0), int(ar.get("height") or 0), "bluesky_post"))
    return out


def _search_commons(term, n=12):
    return [(t, u, d, w, h, "wikimedia_commons") for t, u, d, w, h in commons(term, n=n)]


def openverse(term, n=12):
    """Openverse 公開 API（鍵不要）。[(題, 画像の URL, 説明ページ, 幅, 高さ, 源)]"""
    q = {"q": term, "page_size": str(n)}
    r = json.loads(_get(OPENVERSE_API + "?" + urllib.parse.urlencode(q), timeout=30))
    out = []
    for it in r.get("results") or []:
        url = it.get("url")
        if not url:
            continue
        w, h = int(it.get("width") or 0), int(it.get("height") or 0)
        if w and w < MIN_W:
            continue
        title = str(it.get("title") or os.path.basename(urllib.parse.urlparse(url).path) or term).strip()
        page = it.get("foreign_landing_url") or url
        out.append((title, url, page, w, h, "openverse"))
    return out


def _upgrade_jps_url(url):
    """国立国会図書館デジタルコレクション等の IIIF サムネ（/full/256,/）を 1920px へ引き上げる"""
    if "/api/iiif/" in url:
        return re.sub(r"/full/\d+,/", "/full/1920,/", url)
    return url


def japan_search(term, n=12):
    """ジャパンサーチ横断検索 API（鍵不要・NDL デジタルコレクション等を含む）"""
    q = {"keyword": term, "size": str(n), "f-contents": "thumb"}
    r = json.loads(_get(JPS_API + "?" + urllib.parse.urlencode(q), timeout=30))
    out = []
    for it in r.get("list") or []:
        c = it.get("common") or {}
        thumbs = c.get("thumbnailUrl") or []
        if not thumbs:
            continue
        img_url = _upgrade_jps_url(thumbs[0])
        title = str(c.get("title") or it.get("id") or term).strip()
        page = c.get("linkUrl") or f"https://jpsearch.go.jp/item/{it.get('id', '')}"
        out.append((title, img_url, page, 0, 0, "japan_search"))
    return out


def nasa(term, n=10):
    """NASA Image and Video Library API（鍵不要）"""
    q = {"q": term, "media_type": "image", "page_size": str(n)}
    r = json.loads(_get(NASA_API + "?" + urllib.parse.urlencode(q), timeout=30))
    out = []
    for it in ((r.get("collection") or {}).get("items") or []):
        meta = (it.get("data") or [{}])[0]
        links = [x for x in (it.get("links") or []) if x.get("render") == "image" or str(x.get("href", "")).lower().endswith((".jpg", ".jpeg", ".png"))]
        if not links:
            continue
        href = links[0].get("href", "")
        if not href:
            continue
        if href.endswith("~thumb.jpg"):
            href = href[:-10] + "~medium.jpg"
        nasa_id = meta.get("nasa_id") or ""
        title = str(meta.get("title") or nasa_id or term).strip()
        page = f"https://images.nasa.gov/details/{urllib.parse.quote(nasa_id)}" if nasa_id else href
        out.append((title, href, page, 0, 0, "nasa"))
    return out


def bing_images(term, n=14):
    """Bing 画像検索（鍵不要・一般 Web および SNS 上の公開画像を拾うフォールバック。透かし系ストックサイトは除外）"""
    q = {"q": term, "first": "1", "count": str(n), "mmasync": "1"}
    body = _get(BING_API + "?" + urllib.parse.urlencode(q), timeout=25, headers=BROWSER_UA).decode("utf-8", "replace")
    out = []
    for m in re.findall(r'class="iusc"[^>]*\bm="([^"]+)"', body):
        try:
            obj = json.loads(html_mod.unescape(m))
        except Exception:
            continue
        url = str(obj.get("murl") or "").strip()
        if not url.startswith("http"):
            continue
        low = url.lower()
        purl = str(obj.get("purl") or url).strip()
        if any(h in low or h in purl.lower() for h in STOCK_WATERMARK_HOSTS):
            continue
        title = re.sub(r"\s+", " ", str(obj.get("t") or term)).strip()[:100]
        src_name = "bing_sns" if any(h in low or h in purl.lower() for h in SNS_HOSTS) else "bing_web"
        out.append((title, url, purl, 0, 0, src_name))
    return out


SOURCES = (
    ("wikimedia_commons", _search_commons),
    ("openverse", openverse),
    ("japan_search", japan_search),
    ("nasa", nasa),
    ("bing_web", bing_images),
)


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


def _download_image(url, src_name):
    hdr = BROWSER_UA if src_name in ("bing_web", "bing_sns", "url", "sns_url") else None
    return _open(_get(url, timeout=30, headers=hdr))


def _collect_candidates(want, avoid, cid):
    """候補を最大 MAX_CANDS 枚ダウンロードして返す。
    検索語の場合は Wikimedia Commons を先頭にし、1枚も取れない時だけ次の源へ回す。
    URL 直接指定時は X ポスト・Bluesky ポスト・Commons File ページを画像本体へ解決する。
    戻り値：[(題, url, 説明ページ, 源, PIL.Image)]"""
    if want.startswith("http"):
        raw = []
        if re.search(r"https?://(?:www\.|mobile\.)?(?:x|twitter)\.com/[^/?#]+/status/\d+", want):
            try:
                raw = _x_post_images(want)
            except Exception as e:
                print(f"  （実画像 {cid}：X ポスト解決に失敗 {type(e).__name__}: {e}）")
        elif re.search(r"https?://bsky\.app/profile/[^/?#]+/post/[^/?#]+", want):
            try:
                raw = _bsky_post_images(want)
            except Exception as e:
                print(f"  （実画像 {cid}：Bluesky ポスト解決に失敗 {type(e).__name__}: {e}）")
        elif "commons.wikimedia.org/wiki/File:" in want:
            try:
                raw = _commons_file_page(want)
            except Exception as e:
                print(f"  （実画像 {cid}：Commons File ページ解決に失敗 {type(e).__name__}）")
        if not raw:
            sname = "sns_url" if any(h in want.lower() for h in SNS_HOSTS) else "url"
            raw = [(want, want, want, 0, 0, sname)]
        valid = []
        for title, url, page, _w, _h, src_name in raw[:MAX_CANDS]:
            try:
                im = _download_image(url, src_name)
                if im.width < MIN_W * 0.8:
                    continue
                valid.append((title, url, page, src_name, im))
            except Exception as e:
                print(f"  （実画像 {cid}：{title} が取れない {type(e).__name__}）")
        return valid

    seen_urls = set()
    for src_name, fn in SOURCES:
        try:
            items = fn(want)
        except Exception as e:
            print(f"  （実画像 {cid}：{src_name} 検索失敗 {type(e).__name__}: {e}）")
            continue
        valid = []
        tried = 0
        for title, url, page, _w, _h, sname in items:
            if not url or title in avoid or url in seen_urls:
                continue
            seen_urls.add(url)
            tried += 1
            if tried > 6:
                break
            try:
                im = _download_image(url, sname)
                if im.width < MIN_W * 0.8:
                    continue
                valid.append((title, url, page, sname, im))
                if len(valid) >= MAX_CANDS:
                    break
            except Exception as e:
                print(f"  （実画像 {cid}：{sname}/{title} が取れない {type(e).__name__}）")
        if valid:
            return valid
    return []


def pick_with_gemini(want, narration, cands, cid):
    """候補（最大3枚）をまとめて Gemini（pipeline/gemini.py の無料キー ask_media）に見せ、合う1枚を選ぶ。
    どれも合わなければ None（AI の絵のまま）。Gemini が使えない時は先頭を返す（回は止めない）。1カットにつき1回まで。"""
    global _gemini_disabled, _gemini_reason
    if _gemini_disabled:
        return cands[0], "fallback", _gemini_reason
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import gemini
    except Exception as e:
        _gemini_disabled, _gemini_reason = True, f"gemini import失敗: {type(e).__name__}"
        return cands[0], "fallback", _gemini_reason

    sch = {
        "type": "object",
        "properties": {
            "pick": {"type": "integer"},
            "reason": {"type": "string"},
        },
        "required": ["pick", "reason"],
    }
    listing = "\n".join(f"{i + 1}枚目：題「{t}」（源：{sname}）" for i, (t, _u, _p, sname, _im) in enumerate(cands))
    nar = (narration or "").strip() or "（語りなし）"
    prompt = (
        f"YouTube動画の1カットに使う実写・実資料の画像候補を{len(cands)}枚（添付の1枚目〜{len(cands)}枚目）見せます。\n"
        f"検索語：{want}\n"
        f"このカットの語り：{nar}\n"
        f"候補一覧：\n{listing}\n\n"
        "検索語と語りの内容に最も合う画像を1枚選び、その番号（1〜"
        f"{len(cands)}）を pick に返してください。\n"
        "次のどれかに当たる候補は選ばないでください：\n"
        "- 検索語や語りと無関係な被写体（例：古文書を探したのに無関係な風景や別物）\n"
        "- 時代や文脈が大きく食い違う写真\n"
        "- SNSの文章だらけのスクリーンショット・UI切り抜き・コラ画像・読めない文字だけのページ\n"
        "- 極端にぼやけた画像・大きな透かし（ストック写真のウォーターマーク）入り\n"
        "どの候補も合わない場合は pick に 0 を返してください。reason には選んだ／却下した理由を日本語で簡潔に（40字以内）書いてください。"
    )
    try:
        with tempfile.TemporaryDirectory(prefix="yt_real_g_") as td:
            paths = []
            for i, (_t, _u, _p, _s, im) in enumerate(cands):
                p = os.path.join(td, f"c{i + 1}.jpg")
                th = im.convert("RGB").copy()
                th.thumbnail((768, 768))
                th.save(p, format="JPEG", quality=82)
                paths.append(p)
            text, _usage = gemini.ask_media(prompt, files=paths, schema=sch, temperature=0.1)
        d = json.loads(text)
        idx = int(d.get("pick", 0))
        reason = str(d.get("reason") or "").strip()[:120]
        if idx == 0:
            return None, "gemini_reject", reason
        if 1 <= idx <= len(cands):
            return cands[idx - 1], "gemini", reason
        print(f"  （実画像 {cid}：Gemini の返答番号が範囲外 {idx} → 先頭を採用）")
        return cands[0], "fallback", f"範囲外:{idx}"
    except (SystemExit, Exception) as e:
        msg = str(e) or type(e).__name__
        low = msg.lower()
        if (isinstance(e, SystemExit) and e.code == 75) or any(
            k in low for k in ("見つかりません", "上限", "spending cap", "402", "401", "403", "429", "quota")
        ):
            _gemini_disabled = True
            _gemini_reason = msg[:80]
        print(f"  （実画像 {cid}：Gemini が使えないため先頭を採用：{msg[:100]}）")
        return cands[0], "fallback", msg[:80]


def place(work, c, size, avoid, use_gemini=True):
    """1カット分。置けたら出どころの記録を返す。置けなければ None"""
    want = str(c.get("real") or "").strip()
    if not want:
        return None
    dst = os.path.join(work, "images", c["id"] + ".png")
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    cands = _collect_candidates(want, avoid, c["id"])
    if not cands:
        return None
    if use_gemini:
        chosen, verdict, reason = pick_with_gemini(want, c.get("narration") or "", cands, c["id"])
        if chosen is None:
            print(f"  （実画像 {c['id']}：Gemini が全候補を不適合と判定「{reason}」→ AI の絵のまま）")
            return None
    else:
        chosen, verdict, reason = cands[0], "skip", ""
    title, url, page, src_name, im = chosen
    fit(im, *size).save(dst)
    rec = {"題": title, "url": url, "説明ページ": page, "検索語": want, "源": src_name, "判定": verdict}
    if reason:
        rec["判定理由"] = reason
    return rec


def apply(work, s, ch, kind, use_gemini=True):
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
            print(f"  （実画像 {c['id']}：人物・動く絵・見どころ・セリフ等のカットなので AI の絵のまま）")
            continue
        dst = os.path.join(work, "images", c["id"] + ".png")
        if c.get("real_src") and os.path.exists(dst):  # 書き直し（--fix）で2回目に来た時
            c.pop("image", None)
            n += 1
            continue
        try:
            src = place(work, c, size, avoid, use_gemini=use_gemini)
        except Exception as e:
            src = None
            print(f"  （実画像 {c['id']}：探せない {type(e).__name__}: {e}）")
        if not src:
            print(f"  （実画像 {c['id']}：見つからないか不適合なので AI の絵のまま。検索語「{c['real']}」）")
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
    a.add_argument("--no-gemini", action="store_true", help="Gemini の適合確認を飛ばして先頭候補を使う")
    a = a.parse_args()
    work = os.path.abspath(a.work)
    sp = os.path.join(work, "script.json")
    s = json.load(open(sp, encoding="utf-8"))
    kind = a.kind or ("short" if s.get("format") == "short" else "long")
    apply(work, s, a.ch, kind, use_gemini=not a.no_gemini)
    json.dump(s, open(sp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()

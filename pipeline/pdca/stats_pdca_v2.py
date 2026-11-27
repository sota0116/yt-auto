# チャンネル共通の PDCA 用の数字取り・見比べ・台帳の点検（v2・2026-11-27）
#   v1 からの違い：CHS に shinshiten（シン視点事件簿）と shimei（指名手配ボード）を足し、既定の対象に shinshiten を入れた。中の仕組みは v1 と同じ
#   shimei は手元にトークンが無い（yt_auth の選択肢にも無い）ので既定に入れない。report・check-plan はトークン無しで動く
#   shinshiten はトークンが切れている間、collect で「止めた」と出て exit 1 になる（ほかのチャンネルは取れる）
#   stats_konseki_v2.py（宇宙の痕跡ファイル）の仕組みを、ほかのチャンネルでも使えるように1本にした物。konseki の道具は変えていない
#   python -X utf8 pipeline\pdca\stats_pdca_v2.py collect [--ch spi okinu ...] [--dry]  … 数字（api）と表示回数・CTR（reporting）を足す
#   python -X utf8 pipeline\pdca\stats_pdca_v2.py reach --ch okinu [--dry]               … 表示回数・CTR だけ
#   python -X utf8 pipeline\pdca\stats_pdca_v2.py report --ch okinu                      … 区切り（48h/7d）ごとに、軸の値と数字を並べる
#   python -X utf8 pipeline\pdca\stats_pdca_v2.py check-plan --ch okinu <work>           … 次の回が台帳に載っていて、探索／当たり／ずらしの決まりに合うか
# ・置き場所：channels\<フォルダ>\pdca\（検証の決まり_v*.md・検証台帳_v*.json・metrics_v1.json・reach_raw\）
# ・動画はチャンネルのアップロード一覧（API）から取る。手元の history は古いことがあるので使わない。台帳に無い動画も数字は取る（軸は空）
# ・台帳の軸は、その台帳の vocab のキーの順。チャンネルごとに軸が違ってよい（競合から決めた物だけを入れる）
# ・最初に、トークンのチャンネル ID が下の表と合うかを確かめ、違えば そのチャンネルだけ止めて次へ進む
# ・表示回数・CTR は Reporting API の reach 日報（channel_reach_basic_a1。2026-11-27 予約）。48h＝公開日から2日分、7d＝7日分がそろってから足す
# ・ana_* と keep_30s は区切りの日数で切った値。views・likes・comments は取った時点の通算（後から回すと大きく出る。見比べは ana_views で）
#   CTR の列の単位は最初のレポートで確かめる（まだ実物を見ていない）。値が全部1以下なら割合とみて100倍する
# ・書き込みは途中で切れても壊れない書き方（ustore._dump）。上書きせず足すだけ。同じ動画・同じ区切り・同じ出どころは二重に足さない
import argparse, csv, datetime, glob, gzip, io, json, os, re, sys, urllib.error, urllib.parse
PIPE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PIPE)
from upload_job import api, API, ROOT
from ustore import _dump

# ch（トークンの名前）→ チャンネル ID・フォルダ名。kakure は stats_konseki_v2.py が受け持つので、既定では回さない
CHS = {
    "spi": ("UCO30nV7L9lp4g4Cvz38n40A", "spi"),
    "okinu": ("UCRachsKL_U8-eO0BBETE0-w", "okinu"),
    "nihongi": ("UCPUDU140U5U8xXWYFLPHZKg", "nihongi"),
    "psy": ("UCLfr5Is2XZQHwDnbGjwTQ9w", "urashiten"),  # psy のトークンは今「名作の裏視点」（urashiten）
    "kakure": ("UCFfKxlfMSA8ZtR8JJ1loXbg", "uchu"),
    "shinshiten": ("UCqjsFHU9ACKQFassZJJwAcA", "shinshiten"),  # 2026-11-27 に公開5本の snippet.channelId で確認
    "shimei": ("UClPeRu9FNOUyzJSGZfTjRUQ", "shimei"),  # 2026-11-27 に ZaBMhnz1KEc の snippet.channelId で確認。手元トークン無し
}
DEFAULT = ["spi", "okinu", "nihongi", "psy", "shinshiten"]
JST = datetime.timezone(datetime.timedelta(hours=9))
PT = datetime.timezone(datetime.timedelta(hours=-8))  # 日報の1日は太平洋時間（冬時間で固定。日単位なので夏の1時間は扱わない）
ANA = "https://youtubeanalytics.googleapis.com/v2/reports"
REPORTING = "https://youtubereporting.googleapis.com/v1"
REACH_TYPE = "channel_reach_basic_a1"
REACH_DAYS = {"48h": 2, "7d": 7}
LOOKBACK_DAYS = 21   # 7d の区切りに間に合う範囲だけ見る（アナリティクスと日報の遅れを足しても足りる長さ）


def pdca_dir(ch):
    return os.path.join(ROOT, "channels", CHS[ch][1], "pdca")


def metrics_path(ch):
    return os.path.join(pdca_dir(ch), "metrics_v1.json")


def load_metrics(ch):
    p = metrics_path(ch)
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else []


def save_metrics(ch, rows):
    os.makedirs(pdca_dir(ch), exist_ok=True)
    _dump(metrics_path(ch), load_metrics(ch) + rows)


def ledger(ch, need=False):
    fs = sorted(glob.glob(os.path.join(pdca_dir(ch), "検証台帳_v*.json")), key=lambda p: int(re.search(r"_v(\d+)", p).group(1)))
    if not fs:
        if need:
            sys.exit(f"{ch}：検証台帳が無い（{pdca_dir(ch)}）")
        return None, {"entries": [], "vocab": {}}
    d = json.load(open(fs[-1], encoding="utf-8"))
    if d.get("channel_id") != CHS[ch][0]:
        sys.exit(f"{ch}：台帳のチャンネルが違う（{d.get('channel_id')}）")
    return fs[-1], d


def axes_of(d):
    return list((d.get("vocab") or {}).keys())


def whoami(ch):
    r = json.load(api(ch, "GET", f"{API}/channels?part=id,snippet,contentDetails&mine=true", timeout=60))
    items = r.get("items", [])
    if [it["id"] for it in items] != [CHS[ch][0]]:
        raise RuntimeError(f"トークンのチャンネルが違う（{[it['id'] for it in items]}）")
    return items[0]["snippet"]["title"], items[0]["contentDetails"]["relatedPlaylists"]["uploads"]


def seconds(iso):
    m = re.fullmatch(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso or "")
    d, h, mi, s = (int(x or 0) for x in m.groups()) if m else (0, 0, 0, 0)
    return d * 86400 + h * 3600 + mi * 60 + s


def recent_videos(ch, uploads):
    """アップロード一覧の新しい方から、公開済みで LOOKBACK_DAYS 以内の動画"""
    ids, tok = [], ""
    for _ in range(4):  # 200本まで
        r = json.load(api(ch, "GET", f"{API}/playlistItems?part=contentDetails&maxResults=50&playlistId={uploads}" + (f"&pageToken={tok}" if tok else ""), timeout=60))
        ids += [it["contentDetails"]["videoId"] for it in r.get("items", [])]
        tok = r.get("nextPageToken")
        if not tok:
            break
    ids = list(dict.fromkeys(ids))  # 一覧に同じ動画が2回出ることがある（2026-11-27 実測）
    now = datetime.datetime.now(JST)
    out = []
    for i in range(0, len(ids), 50):
        r = json.load(api(ch, "GET", f"{API}/videos?part=statistics,status,contentDetails,snippet&id={','.join(ids[i:i + 50])}", timeout=60))
        for it in r.get("items", []):
            if it["status"].get("privacyStatus") != "public":
                continue
            pub = datetime.datetime.fromisoformat(it["snippet"]["publishedAt"].replace("Z", "+00:00")).astimezone(JST)
            if (now - pub).days > LOOKBACK_DAYS:
                continue
            it["_pub"] = pub
            it["_sec"] = seconds(it["contentDetails"].get("duration"))
            it["_format"] = "short" if it["_sec"] <= 180 else "long"
            out.append(it)
    return out


def ana(ch, q):
    try:
        return json.load(api(ch, "GET", ANA + "?" + urllib.parse.urlencode(q), timeout=60))
    except urllib.error.HTTPError as e:
        print(f"  【メモ】アナリティクスを取れなかった（{q.get('filters')}・{e.code}）")
        return {}


def analytics(ch, vid, start, end):
    r = ana(ch, {"ids": "channel==MINE", "startDate": start, "endDate": end,
                 "metrics": "views,engagedViews,averageViewPercentage,averageViewDuration,subscribersGained", "filters": f"video=={vid}"})
    cols = [c["name"] for c in r.get("columnHeaders", [])]
    if not cols or not r.get("rows"):
        return {}
    row = dict(zip(cols, r["rows"][0]))
    return {"ana_views": row.get("views"), "engaged_views": row.get("engagedViews"), "avg_view_pct": row.get("averageViewPercentage"),
            "avg_view_sec": row.get("averageViewDuration"), "subs_gained": row.get("subscribersGained")}


def keep30(ch, vid, start, end, sec):
    if sec <= 30:
        return None
    r = ana(ch, {"ids": "channel==MINE", "startDate": start, "endDate": end,
                 "metrics": "audienceWatchRatio", "dimensions": "elapsedVideoTimeRatio", "filters": f"video=={vid}"})
    pts = r.get("rows") or []
    return round(min(pts, key=lambda p: abs(p[0] - 30 / sec))[1], 3) if pts else None


def ledger_row(d, vid):
    return next((e for e in d.get("entries", []) if e.get("video_id") == vid), {})


def collect_api(ch, vids, d, dry):
    metrics = load_metrics(ch)
    done = {(m["video_id"], m.get("checkpoint")) for m in metrics if m.get("checkpoint") and m.get("source") == "api"}
    now = datetime.datetime.now(JST)
    rows = []
    for it in vids:
        hours = (now - it["_pub"]).total_seconds() / 3600
        # 窓を区切りの日数で切るので、後から回しても 48h と 7d の両方を付けられる
        for cp in [c for c, h in (("48h", 48), ("7d", 168)) if hours >= h and (it["id"], c) not in done]:
            # アナリティクスは区切りの日数で切る（48h＝公開日から2日分、7d＝7日分）。後から回しても同じ物差しになる
            start = it["_pub"].date()
            end = min(start + datetime.timedelta(days=REACH_DAYS[cp] - 1), now.date())
            an = analytics(ch, it["id"], start.isoformat(), end.isoformat())
            if not an.get("ana_views"):
                print(f"  ・{it['snippet']['title'][:30]}：アナリティクスがまだ空。{cp} は次の回に付ける")
                continue
            e = ledger_row(d, it["id"])
            st = it["statistics"]
            rec = {"at": now.isoformat(timespec="seconds"), "source": "api", "checkpoint": cp, "work": e.get("work"), "video_id": it["id"],
                   "title": it["snippet"]["title"], "format": it["_format"], "publish_at": it["_pub"].isoformat(timespec="seconds"),
                   "hours": round(hours, 1), "ana_window": [start.isoformat(), end.isoformat()], "views": int(st.get("viewCount", 0)), "likes": int(st.get("likeCount", 0)),
                   "comments": int(st.get("commentCount", 0)), "duration_sec": it["_sec"], **an}
            if it["_format"] == "long":
                rec["keep_30s"] = keep30(ch, it["id"], start.isoformat(), end.isoformat(), it["_sec"])
            rows.append(rec)
    if rows and not dry:
        save_metrics(ch, rows)
    print(f"  api：{len(rows)} 行" + ("（--dry）" if dry else ""))
    return rows


def reach_job(ch):
    jobs = json.load(api(ch, "GET", f"{REPORTING}/jobs", timeout=60)).get("jobs", [])
    j = next((x for x in jobs if x.get("reportTypeId") == REACH_TYPE), None)
    return j["id"] if j else None


def reach_download(ch):
    job = reach_job(ch)
    if not job:
        print(f"  【メモ】{REACH_TYPE} の予約が無い")
        return {}
    raw_dir = os.path.join(pdca_dir(ch), "reach_raw")
    os.makedirs(raw_dir, exist_ok=True)
    reports, tok = [], ""
    while True:
        r = json.load(api(ch, "GET", f"{REPORTING}/jobs/{job}/reports" + (f"?pageToken={tok}" if tok else ""), timeout=60))
        reports += r.get("reports", [])
        tok = r.get("nextPageToken")
        if not tok:
            break
    latest = {}
    for rp in reports:
        day = rp["startTime"][:10]
        if day not in latest or rp["createTime"] > latest[day]["createTime"]:
            latest[day] = rp
    got = 0
    for day, rp in latest.items():
        path = os.path.join(raw_dir, f"{day}.csv")
        meta = path + ".json"
        if os.path.exists(path) and os.path.exists(meta) and json.load(open(meta, encoding="utf-8")).get("id") == rp["id"]:
            continue
        raw = api(ch, "GET", rp["downloadUrl"], timeout=300).read()
        if raw[:2] == b"\x1f\x8b":
            raw = gzip.decompress(raw)
        open(path + ".tmp", "wb").write(raw)
        os.replace(path + ".tmp", path)
        _dump(meta, {"id": rp["id"], "startTime": rp["startTime"], "createTime": rp["createTime"]})
        got += 1
    print(f"  reach：日報 {len(latest)} 日分（今回落とした {got}）")
    return {day: os.path.join(raw_dir, f"{day}.csv") for day in latest}


def collect_reach(ch, vids, d, dry):
    files = reach_download(ch)
    if not files:
        return []
    metrics = load_metrics(ch)
    done = {(m["video_id"], m.get("checkpoint")) for m in metrics if m.get("source") == "reporting"}
    cache = {}
    now = datetime.datetime.now(JST)
    rows = []
    for it in vids:
        first = it["_pub"].astimezone(PT).date()
        for cp, n in REACH_DAYS.items():
            if (it["id"], cp) in done:
                continue
            days = [(first + datetime.timedelta(days=i)).isoformat() for i in range(n)]
            if any(x not in files for x in days):
                continue
            imp = clicks = 0.0
            ctr_max = 0.0
            for day in days:
                if day not in cache:
                    cache[day] = list(csv.DictReader(io.StringIO(open(files[day], encoding="utf-8-sig").read())))
                for row in cache[day]:
                    if row.get("video_id") != it["id"]:
                        continue
                    i = float(row.get("video_thumbnail_impressions") or 0)
                    c = float(row.get("video_thumbnail_impressions_ctr") or 0)
                    imp += i
                    clicks += i * c
                    ctr_max = max(ctr_max, c)
            ctr = clicks / imp if imp else None
            if ctr is not None and ctr_max <= 1:
                ctr *= 100
            e = ledger_row(d, it["id"])
            rows.append({"at": now.isoformat(timespec="seconds"), "source": "reporting", "checkpoint": cp, "work": e.get("work"),
                         "video_id": it["id"], "title": it["snippet"]["title"], "format": it["_format"],
                         "impressions": int(round(imp)), "ctr_pct": round(ctr, 2) if ctr is not None else None, "reach_days": days})
    if rows and not dry:
        save_metrics(ch, rows)
    print(f"  reporting：{len(rows)} 行" + ("（--dry）" if dry else ""))
    return rows


def run(ch, what, dry):
    print(f"■ {ch}（{CHS[ch][1]}）")
    try:
        name, uploads = whoami(ch)
        print(f"  チャンネル：{name}")
        _, d = ledger(ch)
        vids = recent_videos(ch, uploads)
        print(f"  公開済み・{LOOKBACK_DAYS}日以内：{len(vids)} 本")
        if what in ("collect",):
            collect_api(ch, vids, d, dry)
        try:
            collect_reach(ch, vids, d, dry)
        except urllib.error.HTTPError as e:
            print(f"  【メモ】reach を取れなかった（{e.code}）")
        return True
    except SystemExit as e:  # トークン切れなど（yt_auth が止める）。そのチャンネルだけ飛ばす
        print(f"  【止めた】{e}")
    except Exception as e:
        print(f"  【止めた】{type(e).__name__}: {e}")
    return False


def report(ch):
    _, d = ledger(ch)
    m = load_metrics(ch)
    axes = axes_of(d)
    vids = {}
    for x in m:
        vids.setdefault(x["video_id"], x)
    for cp in ("48h", "7d"):
        print(f"\n■ {ch} {cp}")
        for vid, base in sorted(vids.items(), key=lambda kv: kv[1].get("publish_at") or kv[1].get("at")):
            a = ([x for x in m if x["video_id"] == vid and x.get("checkpoint") == cp and x.get("source") == "api"] or [{}])[-1]
            s = ([x for x in m if x["video_id"] == vid and x.get("checkpoint") == cp and x.get("source") == "studio"]
                 + [x for x in m if x["video_id"] == vid and x.get("checkpoint") == cp and x.get("source") == "reporting"] or [{}])[-1]
            if not a and not s:
                continue
            def f(v, fmt):
                return fmt.format(v) if v is not None else "-"
            e = ledger_row(d, vid)
            print(f"{(e.get('work') or vid):<14} {base.get('format', ''):<5} 再生={f(a.get('ana_views'), '{}')} 表示={f(s.get('impressions'), '{}')} "
                  f"CTR={f(s.get('ctr_pct'), '{}%')} 30秒={f(a.get('keep_30s') and a['keep_30s'] * 100, '{:.0f}%')} "
                  f"視聴率={f(a.get('avg_view_pct'), '{:.0f}%')} engaged={f(a.get('engaged_views'), '{}')}  {base.get('title', '')[:40]}")
            ax = e.get("axes", {})
            if ax:
                print(f"{'':<14} 題材={e.get('topic')} " + "／".join(f"{k}={ax[k]}" for k in axes if k in ax))


def check_plan(ch, work):
    _, d = ledger(ch, need=True)
    axes = axes_of(d)
    ents = d["entries"]
    e = next((x for x in ents if x["work"] == work), None)
    if not e:
        sys.exit(f"【NG】{work} が台帳に無い。作る前に台帳の新しい版へ仮説と軸を書く")
    ng = []
    if not e.get("hypothesis"):
        ng.append("仮説が空")
    ax = e.get("axes", {})
    same_fmt = [x for x in ents[:ents.index(e)] if x.get("format") == e.get("format")]
    miss = [k for k in axes if k not in ax]
    if miss:
        ng.append("軸の値が無い: " + ",".join(miss))
    vocab = d.get("vocab") or {}
    bad = [f"{k}={ax[k]}" for k in axes if k in ax and ax[k] not in vocab[k]]
    if bad:
        ng.append("決まった言葉に無い値: " + ",".join(bad))
    combo = tuple(ax.get(k) for k in axes)
    if e.get("confirm_of"):
        src = next((x for x in ents if x["work"] == e["confirm_of"]), None)
        if not src:
            ng.append(f"confirm_of の {e['confirm_of']} が台帳に無い")
        elif tuple(src.get("axes", {}).get(k) for k in axes) != combo:
            ng.append(f"確かめ回なのに {src['work']} と軸が違う")
        elif src.get("topic") == e.get("topic"):
            ng.append("確かめ回は題材を変える")
    elif d.get("phase") == "探索":
        if same_fmt:
            diff = [k for k in axes if same_fmt[-1].get("axes", {}).get(k) != ax.get(k)]
            if not diff:
                ng.append(f"前の回（{same_fmt[-1]['work']}）と軸が全部同じ。探索中は毎回どこかを変える")
            else:
                print("前の回から変えた軸:", ",".join(diff))
        for p in same_fmt:
            if tuple(p.get("axes", {}).get(k) for k in axes) == combo:
                ng.append(f"{p['work']} と組み合わせが同じ")
    else:
        main = d.get("main_type") or {}
        diff = [k for k in axes if main.get(k) != ax.get(k)]
        if len(diff) > 1:
            ng.append(f"当たりの型から {len(diff)} 軸ずれている（{','.join(diff)}）。ずらしは1軸だけ")
    if ng:
        print("【NG】" + "／".join(ng))
        sys.exit(1)
    print(f"OK：{work} は決まりに合う")


if __name__ == "__main__":
    a = argparse.ArgumentParser()
    a.add_argument("cmd", choices=["collect", "reach", "report", "check-plan"])
    a.add_argument("work", nargs="?")
    a.add_argument("--ch", nargs="+", default=DEFAULT, choices=list(CHS))
    a.add_argument("--dry", action="store_true")
    x = a.parse_args()
    if x.cmd in ("collect", "reach"):
        ok = [run(ch, x.cmd, x.dry) for ch in x.ch]
        sys.exit(0 if all(ok) else 1)
    elif x.cmd == "report":
        for ch in x.ch:
            report(ch)
    else:
        if len(x.ch) != 1 or not x.work:
            sys.exit("check-plan は --ch を1つと work を指定する")
        check_plan(x.ch[0], x.work)

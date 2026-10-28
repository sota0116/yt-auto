# 金運おきぬ（okinu）の数字を取って残す（PDCA 用。stats_nihongi.py を写した物に、平均視聴率と登録者の増加を足した。2026-10-28）
#   python -X utf8 pipeline\stats_okinu.py
# ・history\okinu\uploaded.json の生きている動画（retired・missing でない物）の再生・高評価・コメントを videos.list で取り、
#   平均視聴率・平均視聴時間・登録者の増加をアナリティクスで取って、history\okinu\metrics.json に1行ずつ足す（上書きしない）
# ・公開から48時間・7日を過ぎて最初に取った数字には checkpoint "48h" / "7d" を付ける（見比べるのはこの2つ）
# ・アナリティクスの数字は2〜3日遅れて出る。48h の平均視聴率は少なめに出ることがあるので、決めるのは 7d の数字で
# ・見比べ用に、その回の題・つかみの文字・1文目・主人公を作業フォルダの script.json から一緒に残す（1回に変えるのは1つだけ。制作ルール 0節）
# ・長尺は区切りの時に、30秒の時点で残っている割合（keep_30s）も残す。推される線を自分の数字から出すため（スキルの 09 の6。2026-10-28）
import datetime, json, os, re, sys, urllib.error, urllib.parse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from upload_job import ROOT, api, API

CH = "okinu"
JST = datetime.timezone(datetime.timedelta(hours=9))
CHECKPOINTS = [("48h", 48), ("7d", 168)]
ANA = "https://youtubeanalytics.googleapis.com/v2/reports"
VIDEOS = r"C:\Users\koneb\OneDrive\YouTube自動チャンネル\金運おきぬ\videos"


def load(name):
    p = os.path.join(ROOT, "history", CH, name)
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else []


def analytics(vid, start):
    q = {"ids": "channel==MINE", "startDate": start, "endDate": datetime.datetime.now(JST).date().isoformat(),
         "metrics": "views,averageViewPercentage,averageViewDuration,subscribersGained", "filters": f"video=={vid}"}
    try:
        r = json.load(api(CH, "GET", ANA + "?" + urllib.parse.urlencode(q), timeout=60))
    except urllib.error.HTTPError as e:
        print(f"【メモ】アナリティクスを取れませんでした（{vid}・{e.code}）")
        return {}
    cols = [c["name"] for c in r.get("columnHeaders", [])]
    row = (r.get("rows") or [[None] * len(cols)])[0]
    return {"ana_views": row[0], "avg_view_pct": row[1], "avg_view_sec": row[2], "subs_gained": row[3]} if cols else {}


def seconds(iso):
    m = re.fullmatch(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso or "")
    d, h, mi, s = (int(x or 0) for x in m.groups()) if m else (0, 0, 0, 0)
    return d * 86400 + h * 3600 + mi * 60 + s


def keep30(vid, start, sec):
    """30秒の時点で残っている割合（視聴維持のグラフ＝経過の割合ごとの、見ている人の割合。watch.py の fixes と同じ取り方）"""
    if sec <= 30:
        return None
    q = {"ids": "channel==MINE", "startDate": start, "endDate": datetime.datetime.now(JST).date().isoformat(),
         "metrics": "audienceWatchRatio", "dimensions": "elapsedVideoTimeRatio", "filters": f"video=={vid}"}
    try:
        r = json.load(api(CH, "GET", ANA + "?" + urllib.parse.urlencode(q), timeout=60))
    except urllib.error.HTTPError as e:
        print(f"【メモ】視聴維持のグラフを取れませんでした（{vid}・{e.code}）")
        return None
    pts = r.get("rows") or []
    return round(min(pts, key=lambda p: abs(p[0] - 30 / sec))[1], 3) if pts else None


def design(work):
    """見比べ用：題・つかみの文字・1文目・主人公"""
    p = os.path.join(VIDEOS, work, "script.json")
    if not os.path.exists(p):
        return {}
    s = json.load(open(p, encoding="utf-8"))
    cuts = s.get("cuts", [])
    chars = sorted({c for x in cuts for c in (x.get("chars") or []) if c != "okinu"})
    return {"title": s.get("title"), "hook": (cuts[0].get("hook") if cuts else None), "first": (cuts[0]["narration"] if cuts else None),
            "chars": chars, "n_chars": sum(len(x["narration"]) for x in cuts)}


def main():
    vids = [h for h in load("uploaded.json") if not h.get("missing") and not h.get("retired")]
    if not vids:
        sys.exit("動画の記録がありません")
    mp = os.path.join(ROOT, "history", CH, "metrics.json")
    metrics = load("metrics.json")
    done = {(m["video_id"], m.get("checkpoint")) for m in metrics if m.get("checkpoint")}
    now = datetime.datetime.now(JST)
    stats = {}
    ids = [h["video_id"] for h in vids]
    for i in range(0, len(ids), 50):
        r = json.load(api(CH, "GET", f"{API}/videos?part=statistics,status,contentDetails&id={','.join(ids[i:i + 50])}", timeout=60))
        stats.update({it["id"]: it for it in r.get("items", [])})
    rows = []
    for h in vids:
        it = stats.get(h["video_id"])
        if not it:
            print(f"【メモ】{h['work']} がチャンネルに見当たりません（{h['video_id']}）")
            continue
        pub = datetime.datetime.fromisoformat(h["publish_at"]) if h.get("publish_at") else None
        if it["status"].get("privacyStatus") != "public" or not pub or pub > now:
            continue
        hours = (now - pub).total_seconds() / 3600
        st = it["statistics"]
        v, l, c = int(st.get("viewCount", 0)), int(st.get("likeCount", 0)), int(st.get("commentCount", 0))
        cp = None
        for name, hh in CHECKPOINTS:
            if hours >= hh and (h["video_id"], name) not in done:
                cp = name
        rec = {"at": now.isoformat(timespec="seconds"), "work": h["work"], "video_id": h["video_id"],
               "format": "short" if h["work"].startswith("S") else "long", "hours": round(hours, 1), "views": v, "likes": l, "comments": c}
        rec.update(analytics(h["video_id"], pub.date().isoformat()))
        if cp:
            rec["checkpoint"] = cp
            rec.update(design(h["work"]))
            if rec["format"] == "long":
                rec["keep_30s"] = keep30(h["video_id"], pub.date().isoformat(), seconds(it["contentDetails"].get("duration")))
        metrics.append(rec)
        rows.append(rec)
    os.makedirs(os.path.dirname(mp), exist_ok=True)
    json.dump(metrics, open(mp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"{'作業フォルダ':<20}{'経過':>7}{'再生':>7}{'高評価率':>8}{'コメ':>5}{'視聴率':>7}{'登録':>5}{'30秒':>6}  区切り")
    for r in sorted(rows, key=lambda r: -r["hours"]):
        rate = f"{r['likes'] / r['views'] * 100:.1f}%" if r["views"] else "-"
        pct = f"{r['avg_view_pct']:.0f}%" if r.get("avg_view_pct") is not None else "-"
        subs = r.get("subs_gained") if r.get("subs_gained") is not None else "-"
        k30 = f"{r['keep_30s'] * 100:.0f}%" if r.get("keep_30s") is not None else "-"
        print(f"{r['work']:<20}{r['hours']:>6.0f}h{r['views']:>7}{rate:>8}{r['comments']:>5}{pct:>7}{subs:>5}{k30:>6}  {r.get('checkpoint', '')}")
    if not rows:
        print("（まだ公開された動画がありません）")


if __name__ == "__main__":
    main()

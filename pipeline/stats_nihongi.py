# アナザー日本紀（nihongi）の数字を取って残す（PDCA 用。2026-10-28）
#   python -X utf8 pipeline\stats_nihongi.py
# ・history\nihongi\shorts_uploaded.json と long_uploaded.json の生きている動画（retired・missing でない物）の
#   再生・高評価・コメントを videos.list で取り、history\nihongi\metrics.json に1行ずつ足す（上書きしない）
# ・公開から48時間・7日を過ぎて最初に取った数字には checkpoint "48h" / "7d" を付ける（見比べるのはこの2つ）
# ・画面には、公開済みの動画を「公開からの時間・再生・高評価率・コメント」で出す
import datetime, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from upload_job import ROOT, api, API

CH = "nihongi"
JST = datetime.timezone(datetime.timedelta(hours=9))
CHECKPOINTS = [("48h", 48), ("7d", 168)]


def load(name):
    p = os.path.join(ROOT, "history", CH, name)
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else []


def main():
    vids = [h for h in load("shorts_uploaded.json") + load("long_uploaded.json") if not h.get("missing") and not h.get("retired")]
    if not vids:
        sys.exit("動画の記録がありません")
    mp = os.path.join(ROOT, "history", CH, "metrics.json")
    metrics = load("metrics.json")
    done = {(m["video_id"], m.get("checkpoint")) for m in metrics if m.get("checkpoint")}
    now = datetime.datetime.now(JST)
    stats = {}
    ids = [h["video_id"] for h in vids]
    for i in range(0, len(ids), 50):
        r = json.load(api(CH, "GET", f"{API}/videos?part=statistics,status&id={','.join(ids[i:i + 50])}", timeout=60))
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
        rec = {"at": now.isoformat(timespec="seconds"), "work": h["work"], "video_id": h["video_id"], "format": h.get("format", "short"),
               "hours": round(hours, 1), "views": v, "likes": l, "comments": c}
        if cp:
            rec["checkpoint"] = cp
        metrics.append(rec)
        rows.append(rec)
    json.dump(metrics, open(mp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"{'作業フォルダ':<24}{'経過':>7}{'再生':>8}{'高評価率':>8}{'コメ':>5}  区切り")
    for r in sorted(rows, key=lambda r: -r["hours"]):
        rate = f"{r['likes'] / r['views'] * 100:.1f}%" if r["views"] else "-"
        print(f"{r['work']:<24}{r['hours']:>6.0f}h{r['views']:>8}{rate:>8}{r['comments']:>5}  {r.get('checkpoint', '')}")
    if not rows:
        print("（まだ公開された動画がありません）")


if __name__ == "__main__":
    main()

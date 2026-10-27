# ショートの PDCA（手順書 §12。2026-10-27 本人「PDCAで日々いい感じに改善してくれれば見ないから自動でいい」）
#   python -X utf8 pipeline\short_learn.py [--dry]
# ・毎日、ショートを作る前に回す。公開から48時間たったショートの数字を取り、7日目にもう一度取る（history\job\shorts_metrics.json）
# ・数字：再生回数・平均視聴率（%）・登録者の増加・高く評価。点数＝再生回数×平均視聴率÷100＋登録者の増加×200（登録者が一番の目的）
# ・学び（history\job\shorts_learn.json）：
#   ①題の選び方：種類（rank・duel）と物差しごとの点数の平均。short_pick.py が、3本に2本は点の高い物差し・種類から選び、1本は試していない・点の低い物から選ぶ（試す枠）
#   ②書き方：点の高い3本と低い3本の hook・帯・タイトル・平均視聴率。write_short.py が台本の書き手に渡す（型を借りる。文は写さない）
# ・数字が6本そろうまでは学びを出さない（少ない数で決めない）。改善は数字だけで機械的に回し、手順書の決まり（§4・§12）は変えない
import argparse, datetime, json, os, statistics, sys, urllib.error, urllib.parse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from upload_job import ROOT, api

ANA = "https://youtubeanalytics.googleapis.com/v2/reports"
JST = datetime.timezone(datetime.timedelta(hours=9))
H = lambda n: os.path.join(ROOT, "history", "job", n)
MIN_N = 6


def jl(p, d):
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else d


def stats(vid, start):
    q = {"ids": "channel==MINE", "startDate": start, "endDate": datetime.datetime.now(JST).date().isoformat(),
         "metrics": "views,averageViewPercentage,averageViewDuration,subscribersGained,likes", "filters": f"video=={vid}"}
    r = json.load(api("job", "GET", ANA + "?" + urllib.parse.urlencode(q), timeout=60))
    cols = [c["name"] for c in r.get("columnHeaders", [])]
    return dict(zip(cols, (r.get("rows") or [[0] * len(cols)])[0]))


def score(m):
    return round((m.get("views") or 0) * (m.get("averageViewPercentage") or 0) / 100 + (m.get("subscribersGained") or 0) * 200, 1)


def measure(dry):
    up = jl(H("shorts_uploaded.json"), [])
    made = {x["work"]: x for x in jl(H("shorts.json"), [])}
    met = jl(H("shorts_metrics.json"), {})
    now = datetime.datetime.now(JST)
    n = 0
    for e in up:
        at = datetime.datetime.fromisoformat(e["publish_at"])
        age = (now - at).total_seconds() / 3600
        m = met.get(e["work"], {})
        due = ("48h" not in m and age >= 48) or ("7d" not in m and age >= 24 * 7)
        if not due or dry:
            continue
        try:
            s = stats(e["video_id"], at.date().isoformat())
        except urllib.error.HTTPError as err:
            print(f"（{e['work']} の数字が取れない：{err.code}）")
            continue
        s["score"] = score(s)
        mk = made.get(e["work"], {})
        m.update({"video_id": e["video_id"], "title": e["title"], "topic_id": mk.get("topic_id"), "kind": mk.get("kind"),
                  "measure": mk.get("measure"), "hook": mk.get("hook"), "banner": mk.get("banner"),
                  "7d" if age >= 24 * 7 else "48h": s, "取った日": now.isoformat(timespec="seconds")})
        met[e["work"]] = m
        n += 1
    if not dry:
        json.dump(met, open(H("shorts_metrics.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"ショートの数字：{n}本を新しく取った・合わせて {len(met)}本")
    return met


def learn(met, dry=False):
    rows = []
    for w, m in met.items():
        s = m.get("7d") or m.get("48h")
        if s:
            rows.append({**m, "work": w, "score": s["score"], "views": s.get("views"), "avp": s.get("averageViewPercentage"),
                         "subs": s.get("subscribersGained")})
    out = {"本数": len(rows), "更新": datetime.datetime.now(JST).isoformat(timespec="seconds")}
    if len(rows) < MIN_N:
        out["メモ"] = f"数字のあるショートが {len(rows)}本（{MIN_N}本そろうまで学びは出さない）"
    else:
        avg = lambda key: {k: round(statistics.mean(r["score"] for r in rows if r.get(key) == k), 1)
                           for k in {r.get(key) for r in rows if r.get(key)}}
        out["種類の点"] = avg("kind")
        out["物差しの点"] = avg("measure")
        rows.sort(key=lambda r: r["score"], reverse=True)
        keep = ("title", "hook", "banner", "kind", "measure", "views", "avp", "subs", "score")
        out["点の高い3本"] = [{k: r.get(k) for k in keep} for r in rows[:3]]
        out["点の低い3本"] = [{k: r.get(k) for k in keep} for r in rows[-3:]]
        out["全体"] = {"再生の真ん中": statistics.median(r["views"] or 0 for r in rows),
                     "平均視聴率の真ん中": round(statistics.median(r["avp"] or 0 for r in rows), 1),
                     "登録者の増加の合計": sum(r["subs"] or 0 for r in rows)}
    if not dry:
        json.dump(out, open(H("shorts_learn.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps({k: v for k, v in out.items() if k not in ("点の高い3本", "点の低い3本")}, ensure_ascii=False))


if __name__ == "__main__":
    a = argparse.ArgumentParser(); a.add_argument("--dry", action="store_true")
    a = a.parse_args()
    learn(measure(a.dry), a.dry)

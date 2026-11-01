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


def retention(vid, start):
    """1日の流れの見続けられ方。動画の長さを100として、一番落ちた位置（%）と、半分の位置に残った割合を返す。取れない時は空"""
    q = {"ids": "channel==MINE", "startDate": start, "endDate": datetime.datetime.now(JST).date().isoformat(),
         "metrics": "audienceWatchRatio", "dimensions": "elapsedVideoTimeRatio", "filters": f"video=={vid};audienceType==ORGANIC"}
    try:
        rows = json.load(api("job", "GET", ANA + "?" + urllib.parse.urlencode(q), timeout=60)).get("rows") or []
    except urllib.error.HTTPError:
        return {}
    if len(rows) < 10:
        return {}
    fall = max(range(1, len(rows)), key=lambda i: rows[i - 1][1] - rows[i][1])
    return {"一番落ちた位置": round(rows[fall][0] * 100), "半分の位置に残った割合": round(min(rows, key=lambda r: abs(r[0] - 0.5))[1], 2)}


def routine_block(rows):
    """1日の流れと統計ショートを、48時間の再生の真ん中で比べる（手順書 §12）。5本そろって1.2倍以上なら2本、10本そろって0.8倍未満なら0本、それ以外は1本"""
    v48 = lambda r: (r.get("48h") or r.get("7d") or {}).get("views") or 0
    rt = [r for r in rows if r.get("kind") == "routine"]
    if not rt:
        return None
    st = sorted((r for r in rows if r.get("kind") != "routine"), key=lambda r: r["work"])
    base = st[-max(6, len(rt)):]
    mr, mb = statistics.median(v48(r) for r in rt), statistics.median(v48(r) for r in base) if base else 0
    ratio = round(mr / mb, 2) if mb else None
    per_day = 1
    if ratio is not None and len(rt) >= 5 and ratio >= 1.2:
        per_day = 2
    elif ratio is not None and len(rt) >= 10 and ratio < 0.8:
        per_day = 0
    rt.sort(key=lambda r: r["score"], reverse=True)
    keep = ("title", "hook", "measure", "views", "avp", "subs", "score", "一番落ちた位置", "半分の位置に残った割合")
    groups = {r.get("measure", "").replace("1日_", "") for r in rt}
    pts = {g: round(statistics.mean(r["score"] for r in rt if r.get("measure") == "1日_" + g), 1) for g in groups}
    return {"本数": len(rt), "再生の真ん中": mr, "比べた統計ショートの本数": len(base), "統計の再生の真ん中": mb, "倍率": ratio, "1日の本数": per_day,
            "仲間の点": pts, "点の高い3本": [{k: r.get(k) for k in keep} for r in rt[:3]], "点の低い3本": [{k: r.get(k) for k in keep} for r in rt[-3:]]}


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
        if mk.get("kind") == "routine":
            s.update(retention(e["video_id"], at.date().isoformat()))
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
                         "subs": s.get("subscribersGained"), "一番落ちた位置": s.get("一番落ちた位置"),
                         "半分の位置に残った割合": s.get("半分の位置に残った割合")})
    block = routine_block(rows)
    rows = [r for r in rows if r.get("kind") != "routine"]  # ここから下は統計ショートの学び。1日の流れは "1日の流れ" に分ける
    out = {"本数": len(rows), "更新": datetime.datetime.now(JST).isoformat(timespec="seconds")}
    if block:
        out["1日の流れ"] = block
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

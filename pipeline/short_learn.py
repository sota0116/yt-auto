# ショートの PDCA（手順書 §12。2026-10-27 本人「PDCAで日々いい感じに改善してくれれば見ないから自動でいい」）
#   python -X utf8 pipeline\short_learn.py [--dry]
# ・毎日、ショートを作る前に回す。公開から48時間たったショートの数字を取り、7日目にもう一度取る（history\job\shorts_metrics.json）
# ・数字：再生回数・平均視聴率（%）・登録者の増加・高く評価。点数＝再生回数×平均視聴率÷100＋登録者の増加×200（登録者が一番の目的）
# ・学び（history\job\shorts_learn.json）：
#   ①題の選び方：種類（rank・duel）と物差しごとの点数の平均。short_pick.py が、3本に2本は点の高い物差し・種類から選び、1本は試していない・点の低い物から選ぶ（試す枠）
#   ②書き方：点の高い3本と低い3本の hook・帯・タイトル・平均視聴率。write_short.py が台本の書き手に渡す（型を借りる。文は写さない）
# ・数字が6本そろうまでは学びを出さない（少ない数で決めない）。改善は数字だけで機械的に回し、手順書の決まり（§4・§12）は変えない
# ・再生の取り方（2026-11-02。Analytics は反映が遅れ、48時間の時点では0や少ない値が返る。記録が0の3本は公開ページで 561・642・445、100 の回は 620 だった）：
#   区切りの終わりから LAG 時間たっていなければ、再生は公開の数字（videos statistics）を使い、Analytics がまだ空の回は "未確定" として次の日に取り直す。
#   LAG 時間たった回は、Analytics の範囲を公開から48時間（7日の回は7日）に区切って読む。Analytics の日付は太平洋時間なので、開始日はそれに合わせる
#   前の形の記録（"再生の出どころ" が無い回）は、この区切りで取り直す
# ・本を比べる数字は48時間にそろえる（公開7日の回と2日の回を同じ土俵に置かない）
import argparse, datetime, json, os, statistics, sys, urllib.error, urllib.parse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from upload_job import API, ROOT, api

ANA = "https://youtubeanalytics.googleapis.com/v2/reports"
JST = datetime.timezone(datetime.timedelta(hours=9))
PT = datetime.timezone(datetime.timedelta(hours=-8))
LAG = 48  # Analytics がそろうまでの余裕（時間）
BIG = (2, 1000)  # 伸びた回の線：48時間の再生が直近12本の真ん中の2倍以上で、1,000回以上
H = lambda n: os.path.join(ROOT, "history", "job", n)
MIN_N = 6
OTHER = ("routine", "kigyo")  # 統計ショートとは別に数える種類（1日の流れ・企業もしも）
KIGYO_HIT = 2100  # 企業もしもを続ける線の1つ：48時間で2,100回以上が1本でもある（手順書 §15）


def jl(p, d):
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else d


def stats(vid, start, end=None):
    q = {"ids": "channel==MINE", "startDate": start, "endDate": end or datetime.datetime.now(JST).date().isoformat(),
         "metrics": "views,averageViewPercentage,averageViewDuration,subscribersGained,likes", "filters": f"video=={vid}"}
    r = json.load(api("job", "GET", ANA + "?" + urllib.parse.urlencode(q), timeout=60))
    cols = [c["name"] for c in r.get("columnHeaders", [])]
    return dict(zip(cols, (r.get("rows") or [[0] * len(cols)])[0]))


def public_views(ids):
    """公開の再生回数（反映がほぼすぐ）。{動画ID: 再生}。50本ずつ読む"""
    out = {}
    for i in range(0, len(ids), 50):
        url = f"{API}/videos?part=statistics&id={','.join(ids[i:i + 50])}"
        for x in json.load(api("job", "GET", url, timeout=60)).get("items", []):
            out[x["id"]] = int(x["statistics"].get("viewCount") or 0)
    return out


def score(m):
    return round((m.get("views") or 0) * (m.get("averageViewPercentage") or 0) / 100 + (m.get("subscribersGained") or 0) * 200, 1)


def slot(vid, at, age, hours, pub):
    """公開から hours 時間の数字を1つ作る。age はいまの経過時間"""
    start = at.astimezone(PT)
    if age >= hours + LAG:
        s = stats(vid, start.date().isoformat(), (start + datetime.timedelta(hours=hours)).date().isoformat())
        s["再生の出どころ"] = "Analytics（区切り）"
    else:
        s = stats(vid, start.date().isoformat())
        if pub.get(vid) is not None:
            s["views"] = pub[vid]
        s["再生の出どころ"] = "公開の数字"
    if not s.get("averageViewPercentage"):
        s["未確定"] = True
    s["score"] = score(s)
    return s


def stale(s):
    return s.get("未確定") or "再生の出どころ" not in s


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
    st = sorted((r for r in rows if r.get("kind") not in OTHER), key=lambda r: r["work"])
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


def kigyo_block(rows):
    """企業もしも（手順書 §15 の判定の線）：10本そろってから、48時間の再生の真ん中を統計ショートと比べる。
    続ける＝1.5倍以上か、1本でも2,100回以上／やめる＝1.2倍未満／その間＝さらに10本。登録者は1,000回あたりで並べる"""
    v48 = lambda r: (r.get("48h") or r.get("7d") or {}).get("views") or 0
    kg = [r for r in rows if r.get("kind") == "kigyo"]
    if not kg:
        return None
    st = sorted((r for r in rows if r.get("kind") not in OTHER), key=lambda r: r["work"])[-max(10, len(kg)):]
    mk, mb = statistics.median(v48(r) for r in kg), statistics.median(v48(r) for r in st) if st else 0
    ratio = round(mk / mb, 2) if mb else None
    per1k = lambda rs: round(sum(r.get("subs") or 0 for r in rs) * 1000 / max(1, sum(v48(r) for r in rs)), 2)
    top = sum(v48(r) >= KIGYO_HIT for r in kg)
    verdict = "数字待ち（10本そろってから）"
    if len(kg) >= 10 and ratio is not None:
        verdict = "続ける" if ratio >= 1.5 or top else ("やめる（次は1コマ目の見た目だけを変える試し）" if ratio < 1.2 else "その間（さらに10本で見る）")
    kg.sort(key=lambda r: r["score"], reverse=True)
    keep = ("title", "hook", "measure", "views", "avp", "subs", "score", "一番落ちた位置", "半分の位置に残った割合")
    return {"本数": len(kg), "再生の真ん中": mk, "比べた統計ショートの本数": len(st), "統計の再生の真ん中": mb, "倍率": ratio,
            f"{KIGYO_HIT:,}回以上の本数": top, "判定": verdict,
            "1,000回あたりの登録者": {"企業もしも": per1k(kg), "統計": per1k(st)},
            "点の高い3本": [{k: r.get(k) for k in keep} for r in kg[:3]], "点の低い3本": [{k: r.get(k) for k in keep} for r in kg[-3:]]}


def measure(dry):
    up = jl(H("shorts_uploaded.json"), [])
    made = {x["work"]: x for x in jl(H("shorts.json"), [])}
    met = jl(H("shorts_metrics.json"), {})
    now = datetime.datetime.now(JST)
    n = 0
    age_of = lambda e: (now - datetime.datetime.fromisoformat(e["publish_at"])).total_seconds() / 3600
    live = [e for e in up if not e.get("retired") and age_of(e) >= 48]  # 取り下げて公開しなかった回（short_unschedule.py）は入れない
    pub = public_views([e["video_id"] for e in live]) if live and not dry else {}
    for e in live:
        at = datetime.datetime.fromisoformat(e["publish_at"])
        age = age_of(e)
        m = met.get(e["work"], {})
        todo = [k for k, h in (("48h", 48), ("7d", 24 * 7)) if age >= h and (k not in m or stale(m[k]))]
        if not todo or dry:
            continue
        mk = made.get(e["work"], {})
        try:
            for k in todo:
                s = slot(e["video_id"], at, age, 48 if k == "48h" else 24 * 7, pub)
                if mk.get("kind") in OTHER:
                    s.update(retention(e["video_id"], at.astimezone(PT).date().isoformat()))
                m[k] = s
        except urllib.error.HTTPError as err:
            print(f"（{e['work']} の数字が取れない：{err.code}）")
            continue
        m.update({"video_id": e["video_id"], "title": e["title"], "topic_id": mk.get("topic_id"), "kind": mk.get("kind"),
                  "measure": mk.get("measure"), "hook": mk.get("hook"), "banner": mk.get("banner"), "編集の版": mk.get("編集の版", 1),
                  "bgm": mk.get("bgm"), "取った日": now.isoformat(timespec="seconds")})
        met[e["work"]] = m
        n += 1
    if not dry:
        json.dump(met, open(H("shorts_metrics.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"ショートの数字：{n}本を新しく取った・合わせて {len(met)}本")
    return met


def versions(rows):
    """編集の版ごと（種類は分ける）の、48時間の再生と平均視聴率の真ん中。音と画の直しの前後を比べる"""
    out = {}
    for r in rows:
        out.setdefault({"routine": "1日の流れ", "kigyo": "企業もしも"}.get(r.get("kind"), "統計") + f"_版{r.get('編集の版', 1)}", []).append(r)
    return {k: {"本数": len(v), "再生の真ん中": statistics.median(x["views"] or 0 for x in v),
                "平均視聴率の真ん中": round(statistics.median(x["avp"] or 0 for x in v), 1)} for k, v in sorted(out.items())}


def big(rows):
    """伸びた回：同じ題の長尺と関連動画につなぐ候補（週報に載せる）"""
    last = sorted(rows, key=lambda r: r["work"])[-12:]
    if len(last) < 6:
        return []
    line = max(statistics.median(r["views"] or 0 for r in last) * BIG[0], BIG[1])
    return [{k: r.get(k) for k in ("title", "video_id", "views", "avp")} for r in last if (r["views"] or 0) >= line]


def learn(met, dry=False):
    rows = []
    for w, m in met.items():
        s = m.get("48h") or m.get("7d")
        if s:
            rows.append({**m, "work": w, "score": s["score"], "views": s.get("views"), "avp": s.get("averageViewPercentage"),
                         "subs": s.get("subscribersGained"), "一番落ちた位置": s.get("一番落ちた位置"),
                         "半分の位置に残った割合": s.get("半分の位置に残った割合")})
    block, kb = routine_block(rows), kigyo_block(rows)
    ver, hits = versions(rows), big(rows)
    rows = [r for r in rows if r.get("kind") not in OTHER]  # ここから下は統計ショートの学び。1日の流れと企業もしもは別の欄に分ける
    out = {"本数": len(rows), "更新": datetime.datetime.now(JST).isoformat(timespec="seconds"), "編集の版ごと": ver, "伸びた回": hits}
    if block:
        out["1日の流れ"] = block
    if kb:
        out["企業もしも"] = kb
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

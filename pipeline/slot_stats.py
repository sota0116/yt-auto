# 公開の時間帯・間隔・その日の本数ごとの数字（2026-11-04 新設。週次 weekly.yml が鍵を置いてから回す）
#   本人「毎週アナリティクスの数字を取って分析して仮説を立てて修正してほしい」
#   python -X utf8 pipeline\slot_stats.py [ch ...]
# ・対象：day_slots.booked の公開済みのうち、直近90日の動画（横・ショート・予告の全部）
# ・数字：アナリティクスで「公開日から6日後まで」の views・averageViewPercentage・averageViewDuration・subscribersGained
#   公開から9日たった動画を「確定」とし、取り直さない（キャッシュ。history/<ch>/slot_stats.json の videos）。まだの動画は数えない
# ・1本ごとに残す：公開の時刻（JST）・曜日・その日の本数・前後の公開との間隔（時間）・横か縦か
# ・まとめ（確定した分だけ）：横・縦ごとに、時刻／時間帯（朝・昼・夜）／間隔（前後の近い方：3時間未満・3〜6時間・6時間以上）／その日の本数（1・2・3・4以上）で
#   本数・再生の中央値・再生の平均・平均視聴率・1万回あたりの登録
# ・アナリティクスに断られたチャンネルは「アナリティクス不可」と書いて次へ進む（止めない）
import argparse, datetime, json, os, statistics, sys, urllib.error, urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import day_slots as ds

JST = ds.JST
ANA = "https://youtubeanalytics.googleapis.com/v2/reports"
DAYS_BACK = 90
SETTLE = 9          # 公開から何日たてば確定か（6日後までの数字が出そろうのに2〜3日かかる）
PER_RUN = 150       # 1回の実行で1チャンネルあたり取りにいく本数の上限（初回だけ多い。次の週に続きを取る）


def path(ch):
    return os.path.join(ds.ROOT, "history", ch, "slot_stats.json")


def load(ch):
    try:
        d = json.load(open(path(ch), encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def save(ch, d):
    p = path(ch)
    tmp = p + ".tmp"
    json.dump(d, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    os.replace(tmp, p)


def features(rows):
    """{video_id: {時刻, 曜日, その日の本数, 前との間隔, 後との間隔, 横}}（予約中の物も間隔には入れる）"""
    rows = sorted(r for r in rows if r[2])
    per_day = {}
    for t, _, _, _ in rows:
        per_day[t.date()] = per_day.get(t.date(), 0) + 1
    out = {}
    for i, (t, lg, vid, work) in enumerate(rows):
        prev = (t - rows[i - 1][0]).total_seconds() / 3600 if i else None
        nxt = (rows[i + 1][0] - t).total_seconds() / 3600 if i + 1 < len(rows) else None
        out[vid] = {"work": work, "公開": t.isoformat(), "時刻": f"{t:%H:%M}", "時間帯": ds.band(f"{t:%H:%M}"), "曜日": "月火水木金土日"[t.weekday()],
                    "その日の本数": per_day[t.date()], "前との間隔": None if prev is None else round(prev, 1),
                    "後との間隔": None if nxt is None else round(nxt, 1), "横": lg}
    return out


def fetch(ch, vid, start):
    """公開日から6日後までの数字（取れなければ None）"""
    from upload_job import api  # 鍵が要るのは取りにいく時だけ（まとめだけなら手元で回せる）
    end = start + datetime.timedelta(days=6)
    q = {"ids": "channel==MINE", "startDate": start.isoformat(), "endDate": end.isoformat(),
         "metrics": "views,averageViewPercentage,averageViewDuration,subscribersGained", "filters": f"video=={vid}"}
    r = json.load(api(ch, "GET", ANA + "?" + urllib.parse.urlencode(q), timeout=60))
    cols = [c["name"] for c in r.get("columnHeaders", [])]
    row = (r.get("rows") or [[0] * len(cols)])[0]
    return dict(zip(cols, row))


def gap_bucket(f):
    gs = [g for g in (f.get("前との間隔"), f.get("後との間隔")) if g is not None]
    if not gs:
        return "?"
    g = min(gs)
    return "3時間未満" if g < 3 else ("3〜6時間" if g < 6 else "6時間以上")


def summarize(videos):
    """確定した分だけで、横・縦ごとに 時刻／時間帯／間隔／その日の本数 のまとめ"""
    out = {}
    for fmt, lg in (("横", True), ("縦", False)):
        vs = [v for v in videos.values() if v.get("確定") and v.get("横") == lg and v.get("数字")]
        if not vs:
            continue
        keys = {"時刻": lambda v: v["時刻"], "時間帯": lambda v: v["時間帯"], "間隔": gap_bucket,
                "その日の本数": lambda v: str(min(v["その日の本数"], 4)) + ("本以上" if v["その日の本数"] >= 4 else "本")}
        o = out[fmt] = {"確定した本数": len(vs)}
        for name, key in keys.items():
            groups = {}
            for v in vs:
                groups.setdefault(key(v), []).append(v["数字"])
            o[name + "ごと"] = {k: stat(g) for k, g in sorted(groups.items())}
    return out


def stat(g):
    views = [m.get("views") or 0 for m in g]
    pct = [m["averageViewPercentage"] for m in g if m.get("averageViewPercentage") is not None]
    return {"本数": len(g), "再生の中央値": round(statistics.median(views)), "再生の平均": round(sum(views) / len(views)),
            "平均視聴率": round(sum(pct) / len(pct), 1) if pct else None,
            "登録_1万回あたり": round(sum(m.get("subscribersGained") or 0 for m in g) / max(1, sum(views)) * 1e4, 1)}


def run(ch, today, offline=False):
    d = load(ch)
    videos = d.get("videos") or {}
    feats = features(ds.booked(ch))
    now = datetime.datetime.now(JST)
    asked, err = 0, None
    for vid, f in sorted(feats.items(), key=lambda x: x[1]["公開"]):
        t = datetime.datetime.fromisoformat(f["公開"])
        if t > now or (today - t.date()).days > DAYS_BACK:
            continue
        v = videos.get(vid) or {}
        v.update(f)  # 間隔・本数は後から入った予約で変わりうるので毎回入れ直す（数字は残す）
        videos[vid] = v
        if v.get("確定") or offline or err:
            continue
        if (today - t.date()).days < SETTLE:
            continue  # まだ数字が出そろわない
        if asked >= PER_RUN:
            continue
        asked += 1
        try:
            v["数字"] = fetch(ch, vid, t.date())
            v["確定"] = True
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):  # 鍵・権限の問題はチャンネルごと止める
                err = f"アナリティクス不可（HTTP {e.code}）"
            else:  # 消えた動画など。その1本だけ飛ばす
                v["取れない"] = f"HTTP {e.code}"
        except (SystemExit, Exception) as e:  # 鍵が無い・ログイン切れ
            err = f"アナリティクス不可（{str(e)[:120]}）"
    videos = {k: v for k, v in videos.items() if (today - datetime.date.fromisoformat(v["公開"][:10])).days <= DAYS_BACK + 30}
    d.update({"更新": now.isoformat(timespec="seconds"), "videos": videos, "まとめ": summarize(videos),
              "確定待ち": sum(1 for v in videos.values() if not v.get("確定")),
              "枠": {"いま": ds.PLAN.get(ch), "書いたまま": ds.BASE.get(ch)}})
    if err:
        d["状態"] = err
    elif not offline:
        d["状態"] = "取れた"
    save(ch, d)
    return asked, err, d


def main():
    a = argparse.ArgumentParser()
    a.add_argument("chs", nargs="*", default=list(ds.PLAN))
    a.add_argument("--offline", action="store_true", help="アナリティクスを取りにいかず、記録とまとめだけ作り直す")
    a = a.parse_args()
    today = datetime.datetime.now(JST).date()
    for ch in a.chs:
        try:
            asked, err, d = run(ch, today, a.offline)
        except Exception as e:  # 1チャンネルが壊れても次へ
            print(f"{ch}: 止まりました：{e}")
            continue
        m = d.get("まとめ", {})
        n = {k: v.get("確定した本数") for k, v in m.items()}
        print(f"{ch}: 取りにいった {asked} 本／確定 {n or 0}／確定待ち {d.get('確定待ち')}" + (f"／{err}" if err else ""))


if __name__ == "__main__":
    main()

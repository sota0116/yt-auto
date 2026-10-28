# -*- coding: utf-8 -*-
"""YouTube司令室（claude.ai の管理ページ）に載せる「数字」を作る（v2・2026-10-28。6チャンネルの ID を固定し、--schedule を省けるように）。

予約とサムネは dashboard_sync_v*.py、数字はこのスクリプト。
PC を閉じていても動くよう、yt-auto の GitHub Actions（dashboard.yml）で毎時回し、stats.json を dashboard の枝に置く。
クラウドの見回り役がその枝から読んで司令室へ送る。yt-auto には pipeline/dashboard_stats.py として同じ物を置く。
  - 登録者数・再生数：YouTube の公開ページ（yt-dlp の一覧読み。ログイン・鍵は使わない）
  - 日ごとの数字：前回の board/stats（--prev）に足していき、前日比と7日の伸びを出す
  - 仕組みの具合：yt-auto の history（在庫・予約・見張り・制作中の段階・週報の制作費と期限）

使い方:
  python -X utf8 dashboard_stats_v2.py --prev stats_prev.json --out stats.json --yt-auto . --source actions
    --schedule : board/schedule の中身（省ける。KNOWN_IDS に無いチャンネルの ID を、公開済みの回から拾う時だけ使う）
    --prev     : 前回の board/stats の中身（無ければ省く。初回は前日比が空になる）
    --yt-auto  : yt-auto の場所（history を読む）。--git-ref origin/main を足すと、その枝の中身を読む（PC の手元が古い時）
出した stats.json を ArtifactData set（collection board・doc_id stats）で送る。
"""
import argparse
import json
import os
import subprocess
from datetime import datetime, timedelta, timezone

import yt_dlp

JST = timezone(timedelta(hours=9))
CHANNELS = ["job", "spi", "psy", "nihongi", "okinu", "tokujiro"]
KNOWN_IDS = {
    "job": "UCBjRmvLkUHlt0MHgwm-nBGw",
    "spi": "UCO30nV7L9lp4g4Cvz38n40A",
    "psy": "UCLfr5Is2XZQHwDnbGjwTQ9w",
    "nihongi": "UCPUDU140U5U8xXWYFLPHZKg",
    "okinu": "UCRachsKL_U8-eO0BBETE0-w",
    "tokujiro": "UCvPF6RWMlpTWtkWpj-AU5rw",
}
SERIES_DAYS = 60
VID_DAYS = 8


def load(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError, TypeError):
        return None


class Repo:
    """yt-auto の history を読む。git_ref があれば git show で、無ければファイルで"""

    def __init__(self, root, git_ref=None):
        self.root, self.ref = root, git_ref

    def read(self, rel):
        if not self.root:
            return None
        if self.ref:
            try:
                out = subprocess.run(["git", "-C", self.root, "show", f"{self.ref}:{rel}"], capture_output=True, timeout=30)
                return json.loads(out.stdout.decode("utf-8")) if out.returncode == 0 else None
            except (OSError, subprocess.SubprocessError, ValueError):
                return None
        return load(os.path.join(self.root, rel))

    def names(self, rel_dir):
        if not self.root:
            return []
        if self.ref:
            out = subprocess.run(["git", "-C", self.root, "ls-tree", "--name-only", f"{self.ref}:{rel_dir}"], capture_output=True, timeout=30)
            return out.stdout.decode("utf-8").split() if out.returncode == 0 else []
        return sorted(os.listdir(os.path.join(self.root, rel_dir))) if os.path.isdir(os.path.join(self.root, rel_dir)) else []


class _Quiet:
    def debug(self, msg): pass
    def warning(self, msg): pass
    def error(self, msg): pass


def ydl(flat=True):
    return yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True, "skip_download": True, "extract_flat": flat, "ignoreerrors": True, "logger": _Quiet()})


def channel_id_of(video_id):
    try:
        info = ydl(flat=False).extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
        return (info or {}).get("channel_id")
    except Exception:
        return None


def tab(cid, name):
    """チャンネルの一覧（videos か shorts）。無い時は (None, [])"""
    try:
        info = ydl().extract_info(f"https://www.youtube.com/channel/{cid}/{name}", download=False)
    except Exception:
        return None, []
    if not info:
        return None, []
    rows = [{"id": e.get("id"), "title": e.get("title"), "views": e.get("view_count")} for e in info.get("entries") or [] if e and e.get("id")]
    return info.get("channel_follower_count"), rows


def diff_since(hist, days, today):
    """hist={日付: 値} の中で、today から days 日以上前の一番新しい値との差"""
    if not hist or today not in hist:
        return None
    limit = (datetime.fromisoformat(today) - timedelta(days=days)).date().isoformat()
    old = [d for d in hist if d <= limit]
    if not old:
        return None
    a, b = hist[today], hist[max(old)]
    return a - b if isinstance(a, (int, float)) and isinstance(b, (int, float)) else None


def pipeline_of(repo, ch):
    base = f"history/{ch}"
    w = repo.read(f"{base}/watch.json") or {}
    st = repo.read(f"{base}/status.json") or {}
    lr = repo.read(f"{base}/last_run.json") or {}
    if not (w or st or lr):
        return None
    return {
        "stock": w.get("在庫"),
        "reserve": w.get("予約"),
        "dayAfter": w.get("明後日の予約"),
        "lastWatch": w.get("最後の見張り"),
        "aiOff": w.get("AIの申告がオフ") or [],
        "stage": st.get("stage"),
        "stageWork": os.path.basename(st["work"]) if st.get("work") else None,
        "stageDone": st.get("done") or [],
        "stageAt": st.get("updated"),
        "lastRun": lr,
    }


def weekly_of(repo):
    names = [n for n in repo.names("history/weekly") if n.endswith(".json")]
    if not names:
        return None
    w = repo.read(f"history/weekly/{names[-1]}") or {}
    per = {}
    for ch, c in (w.get("チャンネル") or {}).items():
        c = c or {}
        per[ch] = {"costYen": c.get("今月の制作費_円"), "madeWeek": len(c.get("今週作った回") or []), "netaLeft": (c.get("ネタ帳") or {}).get("残り")}
    return {
        "date": w.get("日付"),
        "capYen": w.get("MONTHLY_CAP_YEN"),
        "ch": per,
        "expiries": [{"name": k, "date": (v or {}).get("切れる日"), "soon": (v or {}).get("1か月以内")} for k, v in (w.get("期限") or {}).items()],
        "md": f"history/weekly/{names[-1][:-5]}.md",
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--schedule")
    ap.add_argument("--prev")
    ap.add_argument("--out", required=True)
    ap.add_argument("--yt-auto")
    ap.add_argument("--git-ref")
    ap.add_argument("--source", default="pc")
    args = ap.parse_args()

    sched = (load(args.schedule) if args.schedule else None) or {}
    prev = load(args.prev) if args.prev else None
    prev = prev or {}
    now = datetime.now(JST)
    today = now.date().isoformat()
    repo = Repo(args.yt_auto, args.git_ref)

    by_ch = {ch: [v for v in sched.get("videos") or [] if v.get("ch") == ch] for ch in CHANNELS}
    vid_hist = prev.get("vidHist") or {}
    channels, videos, errors = {}, {}, []

    for ch in CHANNELS:
        pc = (prev.get("channels") or {}).get(ch) or {}
        cid = pc.get("channelId") or KNOWN_IDS.get(ch)
        if not cid:
            for v in by_ch[ch]:
                if v.get("state") == "public" and v.get("id"):
                    cid = channel_id_of(v["id"])
                    if cid:
                        break
        if not cid:
            errors.append(f"{ch}: チャンネルが分からない（公開済みの回が無い）")
            channels[ch] = pc
            continue
        subs, longs = tab(cid, "videos")
        subs2, shorts = tab(cid, "shorts")
        subs = subs if subs is not None else subs2
        rows = [dict(r, fmt="long") for r in longs] + [dict(r, fmt="short") for r in shorts]
        if not rows and subs is None:
            errors.append(f"{ch}: 公開ページを読めなかった")
            channels[ch] = pc
            continue
        total = sum(r["views"] or 0 for r in rows)

        series = [p for p in pc.get("series") or [] if p.get("d") != today]
        series.append({"d": today, "subs": subs, "views": total, "n": len(rows)})
        series = series[-SERIES_DAYS:]
        subs_h = {p["d"]: p.get("subs") for p in series}
        views_h = {p["d"]: p.get("views") for p in series}

        tops = []
        for r in rows:
            h = vid_hist.get(r["id"]) or {}
            h[today] = r["views"]
            vid_hist[r["id"]] = dict(sorted(h.items())[-VID_DAYS:])
            d1, d7 = diff_since(vid_hist[r["id"]], 1, today), diff_since(vid_hist[r["id"]], 7, today)
            videos[r["id"]] = {"v": r["views"], "d1": d1, "d7": d7}
            tops.append({"id": r["id"], "title": r["title"], "fmt": r["fmt"], "views": r["views"], "d1": d1})
        tops.sort(key=lambda t: ((t["d1"] or 0), (t["views"] or 0)), reverse=True)

        channels[ch] = {
            "channelId": cid,
            "subs": subs, "subsD1": diff_since(subs_h, 1, today), "subsD7": diff_since(subs_h, 7, today),
            "views": total, "viewsD1": diff_since(views_h, 1, today), "viewsD7": diff_since(views_h, 7, today),
            "longs": len(longs), "shorts": len(shorts),
            "series": series,
            "top": tops[:5],
        }

    live = set(videos)
    vid_hist = {k: v for k, v in vid_hist.items() if k in live}

    pipeline = {}
    for ch in CHANNELS:
        p = pipeline_of(repo, ch)
        pipeline[ch] = p if p else ((prev.get("pipeline") or {}).get(ch))
    weekly = weekly_of(repo) or prev.get("weekly")
    hb = repo.read("history/heartbeat.json") or prev.get("heartbeat")

    doc = {
        "updatedAt": now.isoformat(timespec="minutes"),
        "source": args.source,
        "channels": channels,
        "videos": videos,
        "vidHist": vid_hist,
        "pipeline": pipeline,
        "weekly": weekly,
        "heartbeat": hb,
        "errors": errors,
    }
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, separators=(",", ":"))
    print(f"size={os.path.getsize(args.out)}B errors={errors}")
    for ch, c in channels.items():
        print(ch, {k: c.get(k) for k in ("subs", "subsD1", "views", "viewsD1", "longs", "shorts")})


if __name__ == "__main__":
    main()

# 予約済みのショート・予告を、同じチャンネルの公開と3時間以上あく枠へ付け替える（2026-11-04 新設。手で1回ずつ回す道具）
#   本人「同じチャンネルで動画と動画の間は少なくとも時間は空けて。1日2本なら昼と夜、3本なら朝昼夜」
#   day_slots.py の決まりを入れる前に予約した分（横 19:00 とショート 20:10 など）を直すために作った
#   python -X utf8 pipeline\respace.py [ch ...] [--dry]
# ・動かすのはショートと予告だけ。横は動かさない（公開日の決まりがあるので。近すぎる横どうしは一覧に出すだけ）
# ・新しい枠の選び方：
#   予告（job の teasers.json）…同じ日の late（22:10）。だめなら次の日以降の late
#   横の切り出し（同じ作業名の横がある）…横の公開より後で、同じ日の枠→だめなら元の時刻より後の最初の枠
#   単独のショート…同じ日の枠（早い時刻も可）→だめなら元の時刻より後の最初の枠
# ・YouTube の予約を PUT で直し（embeddable・publicStatsViewable も送る。送らないとオフに戻る）、記録の publish_at も直す
import argparse, datetime, glob, json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import day_slots as ds

JST = ds.JST
API = "https://www.googleapis.com/youtube/v3"


def files(ch):
    return glob.glob(os.path.join(ds.ROOT, "history", ch, "*uploaded*.json")) + glob.glob(os.path.join(ds.ROOT, "history", ch, "teasers.json"))


def find(ch, vid):
    """video_id の記録（ファイル, 全体, その行）"""
    for p in files(ch):
        d = json.load(open(p, encoding="utf-8"))
        rows = d.values() if isinstance(d, dict) else d
        for h in rows:
            if isinstance(h, dict) and h.get("video_id") == vid and not h.get("missing"):
                return p, d, h
    return None, None, None


def save(p, d):
    tmp = p + ".tmp"
    json.dump(d, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    os.replace(tmp, p)


def pick(ch, rows, item, teaser_ids, now):
    t0, _, vid, work = item
    others = [r for r in rows if r[2] != vid]
    soon = now + datetime.timedelta(hours=1)
    ok = lambda t: t > soon and ds.gap_ok(ch, t, rows=others)
    if vid in teaser_ids:
        late = ds.PLAN[ch].get("late")
        if not late:
            return None
        day = t0.date()
        for _ in range(30):
            t = ds.at_of(day, late)
            if ok(t) and not any(r[0].date() == day and r[2] in teaser_ids for r in others):  # 予告は1日1本
                return t
            day += datetime.timedelta(days=1)
        return None
    longs = [r[0] for r in others if r[1] and r[3] == work]
    floor = max(longs) if longs else None
    day = t0.date()
    for hm in ds.short_times(ch, day, rows=others):
        t = ds.at_of(day, hm)
        if ok(t) and (floor is None or t > floor):
            return t
    for i in range(1, 60):
        d = day + datetime.timedelta(days=i)
        for hm in ds.short_times(ch, d, rows=others):
            t = ds.at_of(d, hm)
            if ok(t) and (floor is None or t > floor):
                return t
    return None


def run(ch, dry, now):
    rows = sorted(r for r in ds.booked(ch))
    teaser_ids = set()
    tp = os.path.join(ds.ROOT, "history", ch, "teasers.json")
    if os.path.exists(tp):
        teaser_ids = {v.get("video_id") for v in json.load(open(tp, encoding="utf-8")).values() if isinstance(v, dict)}
    moved, left, skip = [], [], set()
    for _ in range(50):
        fut = sorted(r for r in rows if r[0] > now + datetime.timedelta(minutes=40))
        bad = [(a, b) for a, b in zip(fut, fut[1:]) if b[0] - a[0] < ds.MIN_GAP and (a[2], b[2]) not in skip]
        if not bad:
            break
        a, b = bad[0]
        mv = b if not b[1] else (a if not a[1] else None)  # ショート・予告を動かす（両方ショートなら後ろ）
        if mv is None:
            left.append(f"{ch}: 横どうし {a[0]:%m/%d %H:%M} {a[3]} ／ {b[0]:%m/%d %H:%M} {b[3]}（動かしていません）")
            skip.add((a[2], b[2]))
            continue
        to = pick(ch, rows, mv, teaser_ids, now)
        if not to:
            left.append(f"{ch}: {mv[0]:%m/%d %H:%M} {mv[3]} の移し先が60日先までありません")
            skip.add((a[2], b[2]))
            continue
        line = f"{ch}: {mv[3]}（{'予告' if mv[2] in teaser_ids else 'ショート'}）{mv[0]:%m/%d %H:%M} → {to:%m/%d %H:%M}"
        if not dry:
            from upload_job import api  # 鍵が要るのは本番だけ
            p, d, h = find(ch, mv[2])
            if not h or h.get("published"):
                left.append(f"{line}：記録が無いか、もう公開済み")
                skip.add((a[2], b[2]))
                continue
            st = {"privacyStatus": "private", "publishAt": to.isoformat(), "selfDeclaredMadeForKids": False, "containsSyntheticMedia": True,
                  "embeddable": True, "publicStatsViewable": True}
            api(ch, "PUT", f"{API}/videos?part=status", {"id": mv[2], "status": st}, timeout=60)
            h["publish_at"] = to.isoformat()
            h["_respaced"] = f"{mv[0].isoformat()} → {to.isoformat()}（2026-11-04 respace.py。3時間あける）"
            save(p, d)
        moved.append(line)
        rows = [r for r in rows if r is not mv] + [(to, mv[1], mv[2], mv[3])]
    return moved, left


def main():
    a = argparse.ArgumentParser()
    a.add_argument("chs", nargs="*", default=list(ds.PLAN))
    a.add_argument("--dry", action="store_true")
    a = a.parse_args()
    now = datetime.datetime.now(JST)
    fail = False
    for ch in a.chs:
        try:
            moved, left = run(ch, a.dry, now)
        except (SystemExit, Exception) as e:  # 鍵が無い・ログイン切れ・YouTube に断られた（次のチャンネルは続ける。移せた分は記録済み）
            print(f"{ch}: 止まりました：{e}")
            fail = True
            continue
        for x in moved:
            print(("（--dry）" if a.dry else "") + x)
        for x in left:
            print("（残り）" + x)
        if not moved and not left:
            print(f"{ch}: 近すぎる予約はありません")
    sys.exit(1 if fail else 0)


if __name__ == "__main__":
    main()

# 予約済みのショート・予告を、ほかのショートと6時間以上・横と3時間以上あく枠へ後ろにずらす（2026-11-04 新設。手で1回ずつ回す道具）
#   2026-11-28 本人「同じチャンネルでショートは6時間以上あけてね」で作り直した
#   python -X utf8 pipeline\respace.py [ch ...] [--dry] [--log 変更の記録.json]
# ・動かすのは予約中（非公開＋公開予定）のショートと予告だけ。公開済みと横は動かさない
# ・早い順に見て、ほかのショートと6時間あいている物は動かさない。足りない物は、元の時刻より後の最初の枠へ（前へは動かさない）
#   移し先は横とも3時間あける。前からある「横との3時間」だけが足りない予約は動かさず、一覧に出す
# ・公開まで20分を切った物は動かさない
# ・書き換える直前に YouTube を読み直し、非公開のままで公開予定が変わっていない時だけ PUT する（公開済みを非公開に戻さないため）
#   status は読んだ値をそのまま送り返す（送らない項目はオフに戻る）。AI の申告（containsSyntheticMedia）は videos.list が返さないので、いつもオンで送る
#   確かめは videos.update の返事で見る（直後の videos.list は古い値を返すことがある。2026-11-28 に確認）
# ・記録（history）に同じ video_id があれば publish_at も直す
import argparse, datetime, glob, json, os, sys
from channel_policy import RETIRED_CHANNELS

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import day_slots as ds

JST = ds.JST
API = ds.API
LOCK_BEFORE = datetime.timedelta(minutes=20)  # これより公開が近い予約は触らない
LEAD = datetime.timedelta(minutes=60)  # 移し先は今から1時間より後
KEEP = ("selfDeclaredMadeForKids", "embeddable", "publicStatsViewable", "license")


def files(ch, root=None):
    base = os.path.join(root or ds.ROOT, "history", ch)
    return [p for p in glob.glob(os.path.join(base, "*uploaded*.json")) + glob.glob(os.path.join(base, "teasers.json")) if "_前_" not in os.path.basename(p)]


def record(ch, vid, old, new, root=None):
    """記録の publish_at を直す。直したファイル名の一覧を返す"""
    done = []
    for p in files(ch, root):
        d = json.load(open(p, encoding="utf-8"))
        rows = d.values() if isinstance(d, dict) else d
        hit = False
        for h in rows:
            if isinstance(h, dict) and h.get("video_id") == vid and h.get("publish_at") and not h.get("published_at"):
                h["publish_at"] = new.isoformat()
                h["_respaced"] = f"{old.isoformat()} → {new.isoformat()}（respace.py。ショートは6時間・横とは3時間あける）"
                hit = True
        if hit:
            tmp = p + ".tmp"
            json.dump(d, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
            os.replace(tmp, p)
            done.append(os.path.basename(p))
    return done


def plan(ch, rows, scheduled, now):
    """rows：booked の全部。scheduled：YouTube で今も予約中の {video_id: 公開予定}。返り値 (移す [(行, 新しい日時)], 残る問題 [文])"""
    movable = sorted((r for r in rows if r[2] in scheduled and abs(r[0] - scheduled[r[2]]) < datetime.timedelta(minutes=2)
                      and not r[1] and r[0] > now + LOCK_BEFORE), key=lambda r: (r[0], r[2]))
    placed = [r for r in rows if r not in movable]  # 記録にだけある時刻の行も、場所をふさぐ側に残る
    moves, left, later = [], [], []
    for r in movable:  # 先に、動かさずに残せる予約を全部決める（移し先が、残せる予約の場所を取らないように）
        (placed if ds.gap_ok(ch, r[0], skip_vid=r[2], rows=[x for x in placed if not x[1]]) else later).append(r)
    for r in later:
        t0, _, vid, work = r
        floor = max(t0, now + LEAD)
        day, to = floor.date(), None
        for _ in range(90):
            for hm in ds.short_times(ch, day, rows=rows):
                t = ds.at_of(day, hm)
                if t > floor and ds.gap_ok(ch, t, skip_vid=vid, rows=placed):
                    to = t
                    break
            if to:
                break
            day += datetime.timedelta(days=1)
        if not to:
            left.append(f"{ch}: {t0:%m/%d %H:%M} {work}（{vid}）の移し先が90日先までありません")
            placed.append(r)
            continue
        moves.append((r, to))
        placed.append((to, False, vid, work))
    for (a, al, av, aw), (b, bl, bv, bw) in ds.violations(placed, now):
        left.append(f"{ch}: {a:%m/%d %H:%M} {'横' if al else '縦'} {av} ／ {b:%m/%d %H:%M} {'横' if bl else '縦'} {bv}（{'横との3時間' if (al or bl) else 'ショートどうし'}。動かしていません）")
    return moves, left


def put_status(ch, vid, st, at):
    """st（今の status）を残したまま公開予定を at にする。返事の内容を確かめる"""
    from upload_job import api  # 鍵が要るのはここだけ
    body = {"privacyStatus": "private", "publishAt": at.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    body.update({k: st[k] for k in KEEP if k in st})
    body["containsSyntheticMedia"] = True  # 自動で作った動画は申告がいつもオン
    got = json.load(api(ch, "PUT", f"{API}/videos?part=status", {"id": vid, "status": body}, timeout=60)).get("status", {})
    if got.get("privacyStatus") != "private" or not got.get("publishAt") or abs(ds._ts(got["publishAt"]) - at) > datetime.timedelta(seconds=1):
        raise RuntimeError(f"書き換えた返事が合いません（{got.get('privacyStatus')} {got.get('publishAt')}）")
    lost = [k for k in KEEP if k in st and k in got and got[k] != st[k]]
    if lost or got.get("containsSyntheticMedia") is False:
        raise RuntimeError(f"予約は直りましたが、設定が変わりました：{lost} 申告={got.get('containsSyntheticMedia')}")
    return got


def read_status(ch, vid):
    from upload_job import api
    items = json.load(api(ch, "GET", f"{API}/videos?part=status&id={vid}", timeout=60)).get("items") or []
    if not items:
        raise RuntimeError("動画が見つかりません")
    return items[0]["status"]


def move_one(ch, vid, old, new):
    """直前に読み直してから予約を直す。返り値は videos.update の返事の status"""
    st = read_status(ch, vid)
    if st.get("privacyStatus") != "private" or not st.get("publishAt"):
        raise RuntimeError("もう予約中ではありません")
    if abs(ds._ts(st["publishAt"]) - old) > datetime.timedelta(seconds=90):
        raise RuntimeError(f"公開予定が変わっています（{st['publishAt']}）")
    if ds._ts(st["publishAt"]) < datetime.datetime.now(JST) + LOCK_BEFORE or new <= ds._ts(st["publishAt"]):
        raise RuntimeError("公開が近すぎるか、前へ動かすことになります")
    return put_status(ch, vid, st, new)


def run(ch, dry, now, log):
    if ch in RETIRED_CHANNELS and not ds.live_rows(ch):
        return [], [f"{ch}: 自動運用を停止しています"]
    lv = ds.live_rows(ch)
    if not lv:
        return [], [f"{ch}: この機械では YouTube を読めません（ログイン無し）。予約は直していません"]
    rows = ds.booked(ch)
    scheduled = {v: at for v, (at, _, _) in lv.items() if at and at > now}
    moves, left = plan(ch, rows, scheduled, now)
    done = []
    for (old, _, vid, work), new in moves:
        line = f"{ch}: {vid} {work}　{old:%m/%d %H:%M} → {new:%m/%d %H:%M}"
        item = {"ch": ch, "video_id": vid, "work": work, "from": old.isoformat(), "to": new.isoformat(), "result": "dry"}
        if not dry:
            try:
                move_one(ch, vid, old, new)
            except (Exception, SystemExit) as e:
                detail = getattr(e, "read", lambda: b"")()
                item["result"] = f"失敗：{str(e)[:200]} {detail.decode('utf-8', 'replace')[:200] if detail else ''}"
                log.append(item)
                left.append(f"{line}：{item['result']}")
                if "quota" in item["result"].lower():
                    left.append(f"{ch}: API の上限なので、このチャンネルの残りは直していません")
                    break
                continue
            item["result"] = "ok"
            item["records"] = [f"{r}:{f}" for r in ds.ROOTS for f in record(ch, vid, old, new, r)]
        log.append(item)
        done.append(line)
    return done, left


def main():
    a = argparse.ArgumentParser()
    a.add_argument("chs", nargs="*", default=list(ds.PLAN))
    a.add_argument("--dry", action="store_true")
    a.add_argument("--log")
    a = a.parse_args()
    now = datetime.datetime.now(JST)
    fail = False
    log = []
    for ch in a.chs:
        try:
            moved, left = run(ch, a.dry, now, log)
        except (SystemExit, Exception) as e:  # ログイン切れ・YouTube に断られた（次のチャンネルは続ける。移せた分は記録済み）
            print(f"{ch}: 止まりました：{e}")
            fail = True
            continue
        for x in moved:
            print(("（--dry）" if a.dry else "") + x)
        for x in left:
            print("（残り）" + x)
        if not moved and not left:
            print(f"{ch}: 近すぎる予約はありません")
        if a.log:
            json.dump(log, open(a.log, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    sys.exit(1 if fail or any(i["result"] not in ("ok", "dry") for i in log) else 0)


if __name__ == "__main__":
    main()

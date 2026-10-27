# ショートの見張り（心理学ch・2026-10-27 新設）：watch.yml で watch.py のあとに動く
#   python -X utf8 pipeline\shorts_watch.py psy [--dry]
# ・history\<ch>\shorts_uploaded.json のショートの今の状態を読む（消えた・公開になった）
# ・予約：非公開でまだ予約の無いショートは、本編（long_video_id）に公開か予約が入ったら、本編の公開の次の日の 12:10 に予約する。
#   その時刻が近すぎる（30分以内）か過ぎていたら、次の 12:10 にする
# ・数字：公開から72時間と7日の時点で、再生・平均視聴率・平均視聴時間・登録を history\<ch>\shorts_metrics.json に残す
#   （週報 weekly.py と、次の回の台本の書き手が読む。つかみの文と上の帯の字ごとに、どれが見られたかを比べるため）
import argparse, datetime, json, os, sys, traceback
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from notify import jload, now, JST
from run_daily import hpath, jsave
from upload_job import api, API
from watch import refresh, report, ts

TIME = (12, 10)


def slot_after(day):
    at = datetime.datetime.combine(day, datetime.time(*TIME), JST)
    while at < now() + datetime.timedelta(minutes=30):
        at += datetime.timedelta(days=1)
    return at


def schedule(ch, shorts, longs, dry):
    by_id = {e.get("video_id"): e for e in longs}
    out = []
    for s in shorts:
        if s.get("missing") or s.get("published") or s.get("publish_at") or s.get("privacy_now") != "private":
            continue
        lg = by_id.get(s.get("long_video_id"))
        when = lg and ts(lg.get("published_at") or lg.get("publish_at"))
        if not when:
            continue  # 本編がまだ在庫（公開の日が決まっていない）
        at = slot_after(when.date() + datetime.timedelta(days=1))
        if dry:
            out.append(f"（--dry）{s['work']} のショートを {at:%m/%d %H:%M} に予約する")
            continue
        st = {"privacyStatus": "private", "publishAt": at.isoformat(), "selfDeclaredMadeForKids": False, "containsSyntheticMedia": True,
              "embeddable": True, "publicStatsViewable": True}  # 送らないと予約の時にオフに戻る（2026-10-28 002 で起きた）
        api(ch, "PUT", f"{API}/videos?part=status", {"id": s["video_id"], "status": st}, timeout=60)
        s["publish_at"] = at.isoformat()
        out.append(f"{s['work']} のショートを {at:%m/%d %H:%M} に予約しました")
    return out


def numbers(ch, shorts, metrics):
    for s in shorts:
        if not s.get("published") or s.get("missing"):
            continue
        age = now() - ts(s["published_at"])
        m = metrics.setdefault(s["work"], {"type": s.get("type"), "video_id": s["video_id"], "hook": s.get("hook"), "band": s.get("band")})
        for key, h in (("h72", 72), ("d7", 24 * 7)):
            if age >= datetime.timedelta(hours=h) and key not in m:
                row = (report(ch, s["video_id"], s["published_at"][:10], "views,averageViewPercentage,averageViewDuration,subscribersGained") or [{}])[0]
                m[key] = {**row, "取った日": now().date().isoformat()}
                print(f"  {s['work']} のショート {key}：{row}")


def main():
    a = argparse.ArgumentParser()
    a.add_argument("chs", nargs="+", choices=["psy"])
    a.add_argument("--dry", action="store_true")
    a = a.parse_args()
    os.environ["TZ"] = "Asia/Tokyo"
    bad = 0
    for ch in a.chs:
        sp, mp = hpath(ch, "shorts_uploaded.json"), hpath(ch, "shorts_metrics.json")
        shorts, metrics = jload(sp, []), jload(mp, {})
        if not shorts:
            print(f"{ch}：まだ上げたショートがありません")
            continue
        try:
            refresh(ch, shorts)
            for x in schedule(ch, shorts, jload(hpath(ch, "uploaded.json"), []), a.dry):
                print(" ", x)
            numbers(ch, shorts, metrics)
        except Exception:  # ショートの見張りが落ちても、長尺の見張りの記録は止めない
            traceback.print_exc()
            bad = 1
        finally:
            jsave(sp, shorts)
            jsave(mp, metrics)
        n_wait = sum(1 for s in shorts if not s.get("missing") and not s.get("published") and not s.get("publish_at"))
        print(f"{ch}：ショート {len(shorts)}本（公開 {sum(1 for s in shorts if s.get('published'))}・予約待ち {n_wait}）")
    sys.exit(bad)


if __name__ == "__main__":
    main()

# ショートの見張り v2（2026-10-28。千年こよみ spi を足した。元の shorts_watch.py（psy だけ）は残している）：watch.yml で watch.py のあとに動く
#   python -X utf8 pipeline\shorts_watch_v2.py psy spi [--dry]
# ・v2 で変えたこと：①予約の時刻をチャンネルごとに（psy 12:10・spi 19:15。spi は暦の競合 招福こよみ の時刻。channels\spi\記録.md）
#   ②記録に comment があるショート（spi。本編の公開日とリンク）は、公開されたらチャンネルからコメントを1件入れる（watch.py の comment と同じ。
#   消されたコメントが2本出たら、そのチャンネルのショートはコメントをやめる。history\<ch>\shorts_watch.json）
# ・history\<ch>\shorts_uploaded.json のショートの今の状態を読む（消えた・公開になった）
# ・予約：非公開でまだ予約の無いショートは、本編（long_video_id）に公開か予約が入ったら予約する。psy は本編の日の 20:10 から 12:10/20:10 の空き枠（shorts_watch.py）。
#   spi は本編の公開の次の日の 19:15（2026-10-28 まで）→ 2026-10-28 から short_slot_spi.py（毎日 11:15・19:15 の空き枠。
#   ショートの種類 kind：teaser は本編の前の枠・after は本編の後の最初の空き枠・solo は今からの最初の空き枠）。
#   1つの回に何本もショートがあるので、数字は「回の名前:ショートの名前」（short は回の名前だけ）で分けて残す。
#   予告（teaser）のコメントは、本編が公開されてから入れる（comment_after。本編の公開前はリンクを開いても見られないため）
#   その時刻が近すぎる（30分以内）か過ぎていたら、次の枠にする
# ・数字：公開から72時間と7日の時点で、再生・平均視聴率・平均視聴時間・登録を history\<ch>\shorts_metrics.json に残す
#   （週報 weekly.py と、次の回の台本の書き手が読む。つかみの文と上の帯の字ごとに、どれが見られたかを比べるため）
import argparse, datetime, json, os, sys, traceback, urllib.error
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from notify import jload, now, JST
from run_daily import hpath, jsave
from upload_job import api, API
from watch import comment, refresh, report, ts
from short_slot_spi import slot as slot_spi
from shorts_watch import slot_after as slot_psy  # psy は本編の日の 20:10 から 12:10/20:10 の空き枠（2026-10-28 本人「ショートは毎日1～3本」）

TIME = {"psy": (12, 10), "spi": (19, 15)}


def slot_after(ch, day):
    at = datetime.datetime.combine(day, datetime.time(*TIME[ch]), JST)
    while at < now() + datetime.timedelta(minutes=30):
        at += datetime.timedelta(days=1)
    return at


def schedule(ch, shorts, longs, dry):
    by_id = {e.get("video_id"): e for e in longs}
    used = {ts(s.get("publish_at") or s.get("published_at")) for s in shorts if not s.get("missing") and not s.get("retired")} - {None}
    out = []
    for s in shorts:
        if s.get("missing") or s.get("published") or s.get("publish_at") or s.get("privacy_now") != "private":
            continue
        lg = by_id.get(s.get("long_video_id"))
        when = lg and ts(lg.get("published_at") or lg.get("publish_at"))
        if not when and s.get("kind") != "solo":
            continue  # 本編がまだ在庫（公開の日が決まっていない）
        at = slot_psy(when, used) if ch == "psy" else slot_spi(s.get("kind") or "after", when, used, now())
        if not at:
            continue  # 予告の枠が残っていない（本編の48時間前より前に作れなかった）。週報で見る
        used.add(at)
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
        key = s["work"] if (s.get("name") or "short") == "short" else f"{s['work']}:{s['name']}"
        m = metrics.setdefault(key, {"type": s.get("type"), "video_id": s["video_id"], "hook": s.get("hook"), "band": s.get("band")})
        m.update(kind=s.get("kind") or "after", title=s.get("title"), publish_slot=s.get("published_at") and ts(s["published_at"]).strftime("%H:%M"))
        for key, h in (("h72", 72), ("d7", 24 * 7)):
            if age >= datetime.timedelta(hours=h) and key not in m:
                row = (report(ch, s["video_id"], s["published_at"][:10], "views,averageViewPercentage,averageViewDuration,subscribersGained") or [{}])[0]
                m[key] = {**row, "取った日": now().date().isoformat()}
                print(f"  {s['work']} のショート {key}：{row}")


def main():
    a = argparse.ArgumentParser()
    a.add_argument("chs", nargs="+", choices=["psy", "spi"])
    a.add_argument("--dry", action="store_true")
    a = a.parse_args()
    os.environ["TZ"] = "Asia/Tokyo"
    bad = 0
    for ch in a.chs:
        sp, mp, stp = hpath(ch, "shorts_uploaded.json"), hpath(ch, "shorts_metrics.json"), hpath(ch, "shorts_watch.json")
        shorts, metrics, state = jload(sp, []), jload(mp, {}), jload(stp, {})
        if not shorts:
            print(f"{ch}：まだ上げたショートがありません")
            continue
        try:
            refresh(ch, shorts)
            for x in schedule(ch, shorts, jload(hpath(ch, "uploaded.json"), []), a.dry):
                print(" ", x)
            for s in shorts:
                if s.get("missing") or (s.get("comment_after") and now() < ts(s["comment_after"])):
                    continue
                try:
                    comment(ch, s, state, a.dry)
                except urllib.error.HTTPError as err:  # コメントで断られても、予約と数字は止めない
                    s["comment_error"] = f"{err.code} {now().isoformat(timespec='seconds')}"
                    print(f"  ショートにコメントを入れられませんでした（{err.code}）：{s['work']}")
            numbers(ch, shorts, metrics)
        except Exception:  # ショートの見張りが落ちても、長尺の見張りの記録は止めない
            traceback.print_exc()
            bad = 1
        finally:
            jsave(sp, shorts)
            jsave(mp, metrics)
            jsave(stp, state)
        n_wait = sum(1 for s in shorts if not s.get("missing") and not s.get("published") and not s.get("publish_at"))
        print(f"{ch}：ショート {len(shorts)}本（公開 {sum(1 for s in shorts if s.get('published'))}・予約待ち {n_wait}）")
    sys.exit(bad)


if __name__ == "__main__":
    main()

# 本編の公開の予約（千年こよみ・2026-10-28 新設。本人の指示「公開日も含めて任せる」）
#   python -X utf8 pipeline\schedule_long_spi.py <作業フォルダ> [--dry]
# ・upload_job.py で非公開で上げた本編（作業フォルダの uploaded.json）に、次の空いている「水曜か土曜の 18:00」の予約を入れる
# ・理由（競合13チャンネル・長い動画570本。_research\spi_long_time_2026-10-28.json）：18時台が270本でいちばん多い。
#   同じチャンネルの中で時刻ごと・曜日ごとの再生を比べると差は小さい（中央比 0.95〜1.18）。水曜がいちばん高かった（1.18）。
#   本数は週1〜7本（真ん中 3.7本）で、千年こよみは手で作るので週2本にした
# ・空いている日：千年こよみのほかの本編（history\spi\uploaded.json）の公開か予約が入っていない日。今から3時間より先
# ・ショートは本編の公開の次の日の 19:15（upload_short_spi.py）。なので本編が水曜なら木曜、土曜なら日曜にショートが出る
# ・2026-10-28 改（本人「横動画は週に3〜4本目指して。品質が下がらない前提ね」）：枠を 月・水・金・日 の4つにした。
#   曜日の差は小さい（水 1.18・日 1.04・土 1.01・月 0.97・金 0.95）ので、上位の水と日を入れ、あとは間を2日ずつあけるのを優先した
#   （本編どうしが近すぎると、新しい本編の最初の2日にショートの枠を回せない）。できた本数だけ埋まるので、週3本の週は空きが出るだけ。
#   ショートは short_slot_spi.py（毎日 11:15・19:15 の空き枠）。上の「水曜か土曜」「次の日の 19:15」は 2026-10-28 までの決まり
import argparse, datetime, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from upload_job import ROOT, API, api

JST = datetime.timezone(datetime.timedelta(hours=9))
CH = "spi"
DAYS, TIME = (0, 2, 4, 6), (18, 0)  # 月・水・金・日（月曜が0）、18:00（2026-10-28 週2本 → 週4本）


def taken():
    hist = json.load(open(os.path.join(ROOT, "history", CH, "uploaded.json"), encoding="utf-8"))
    out = set()
    for e in hist:
        w = e.get("publish_at") or e.get("published_at")
        if w and not e.get("missing") and not e.get("retired"):
            out.add(datetime.datetime.fromisoformat(w.replace("Z", "+00:00")).astimezone(JST).date())
    return out


def next_slot():
    busy, now = taken(), datetime.datetime.now(JST)
    day = now.date()
    while True:
        at = datetime.datetime.combine(day, datetime.time(*TIME), JST)
        if day.weekday() in DAYS and day not in busy and at > now + datetime.timedelta(hours=3):
            return at
        day += datetime.timedelta(days=1)


def main():
    a = argparse.ArgumentParser()
    a.add_argument("work")
    a.add_argument("--dry", action="store_true")
    a = a.parse_args()
    up = json.load(open(os.path.join(os.path.abspath(a.work), "uploaded.json"), encoding="utf-8"))
    st = json.load(api(CH, "GET", f"{API}/videos?part=status&id={up['video_id']}", timeout=60))["items"][0]["status"]
    if st["privacyStatus"] != "private" or st.get("publishAt"):
        sys.exit(f"【止めました】本編はもう公開か予約が入っています（{st['privacyStatus']}・{st.get('publishAt')}）")
    at = next_slot()
    w = "月火水木金土日"[at.weekday()]
    print(f"本編 {up['video_id']} を {at:%Y-%m-%d}（{w}）{at:%H:%M} に予約" + ("します（--dry なので入れません）" if a.dry else "しました"))
    if a.dry:
        return
    api(CH, "PUT", f"{API}/videos?part=status", {"id": up["video_id"], "status": {
        "privacyStatus": "private", "publishAt": at.isoformat(), "selfDeclaredMadeForKids": False, "containsSyntheticMedia": True}}, timeout=60)
    hp = os.path.join(ROOT, "history", CH, "uploaded.json")
    hist = json.load(open(hp, encoding="utf-8"))
    for e in hist:
        if e.get("video_id") == up["video_id"]:
            e["publish_at"] = at.isoformat()
    json.dump(hist, open(hp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()

# 千年こよみのショートの予約の枠（2026-10-28 新設。本人「横動画は週に3〜4本」「ショートは毎日1〜3本」
#   「全部が全部横動画に関係していなくてもいい。横動画を出したあとに関連・小出しのショートで横動画に誘導する」）
# upload_short_spi.py（上げる時）と shorts_watch_v2.py（クラウドの見張り）の両方がここを使う
# ・枠は毎日 11:15 と 19:15（暦の競合「招福こよみ」が毎日この2つの時刻に出している。channels\spi\記録.md 2026-10-27）
# ・ショートの種類（short.json の kind）で入れる枠を変える：
#   teaser（予告）：本編の公開より前で、本編の公開の48時間前より後の空き枠のうち、本編にいちばん近い枠。無ければ入れない（None）
#   after（切り出し。最後に「続きは本編で」）：本編の公開より後の最初の空き枠
#   solo（単独で完結。説明欄とコメントで関連の本編へ）：今から先の最初の空き枠
# ・どの枠も、今から30分より先。ほかのショートの公開か予約が入っている枠は使わない
import datetime

JST = datetime.timezone(datetime.timedelta(hours=9))
TIMES = ((11, 15), (19, 15))
KINDS = ("teaser", "after", "solo")


def slots_from(day):
    while True:
        for t in TIMES:
            yield datetime.datetime.combine(day, datetime.time(*t), JST)
        day += datetime.timedelta(days=1)


def slot(kind, long_at, used, now):
    """kind：teaser / after / solo。long_at：本編の公開（予約）の日時か None。used：ほかのショートの公開・予約の日時の集まり"""
    soon = now + datetime.timedelta(minutes=30)
    if kind == "teaser":
        if not long_at:
            return None
        start = max(soon, long_at - datetime.timedelta(hours=48))
        ok = [at for at in _range(start.astimezone(JST).date(), long_at) if start <= at < long_at and at not in used]
        return ok[-1] if ok else None
    if kind == "after":
        if not long_at:
            return None
        start = max(soon, long_at + datetime.timedelta(seconds=1))
    else:
        start = soon
    for at in slots_from(start.astimezone(JST).date()):
        if at >= start and at not in used:
            return at


def _range(day, end):
    out = []
    for at in slots_from(day):
        if at >= end:
            return out
        out.append(at)

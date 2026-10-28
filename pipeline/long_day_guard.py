# 横動画（長尺）は、同じチャンネルで同じ日に2本以上出さない（2026-10-29 本人「横動画は同じ日に2本以上は載せない」）
#   予約を入れる道具（upload_nihongi.py --long・reschedule_nihongi.py・upload_okinu.py・reschedule_okinu.py）が、
#   予約の前に check(ch, at) を呼ぶ。同じ日（日本時間）に公開済みか予約中の横動画が既にあれば止まる
# ・横かショートか：記録の format → ファイル名（long_uploaded.json は横・shorts の付く物はショート）→ 作業フォルダの名前（S001_… はショート）
# ・数えない記録：消えた（missing）・差し替えた（retired）・予約も公開も無い（非公開のまま）物
# ・job・psy は見張り（watch.py）が「明日の予約が無い日だけ1本」入れるので、もともと1日1本まで
import datetime, glob, json, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JST = datetime.timezone(datetime.timedelta(hours=9))


def is_long(path, h):
    if h.get("format"):
        return h["format"] == "long"
    base = os.path.basename(path)
    if base.startswith("long_"):
        return True
    if "shorts" in base:
        return False
    return not re.match(r"S\d", h.get("work") or "")


def day_of(s):
    if not s:
        return None
    d = datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))
    return (d if d.tzinfo else d.replace(tzinfo=JST)).astimezone(JST).date()


def same_day(ch, at, skip_vid=None):
    """at（日本時間）と同じ日に公開済みか予約中の、同じチャンネルの横動画の記録"""
    hits = []
    for p in glob.glob(os.path.join(ROOT, "history", ch, "*uploaded.json")):
        for h in json.load(open(p, encoding="utf-8")):
            if not isinstance(h, dict) or h.get("missing") or h.get("retired") or h.get("video_id") == skip_vid:
                continue
            if is_long(p, h) and day_of(h.get("published_at") or h.get("publish_at")) == at.astimezone(JST).date():
                hits.append(h)
    return hits


def check_vid(ch, vid, at):
    """予約を動かす時（reschedule_*.py）：動かす動画が横動画の時だけ、行き先の日を確かめる"""
    for p in glob.glob(os.path.join(ROOT, "history", ch, "*uploaded.json")):
        for h in json.load(open(p, encoding="utf-8")):
            if isinstance(h, dict) and h.get("video_id") == vid:
                if is_long(p, h):
                    check(ch, at, skip_vid=vid)
                return
    print(f"【メモ】{vid} が記録に無いので、横動画の同じ日の確かめはしていません")


def check(ch, at, skip_vid=None):
    hits = same_day(ch, at, skip_vid)
    if hits:
        h = hits[0]
        sys.exit(f"【止めました】{at.astimezone(JST):%m/%d} には横動画がもう入っています（{h.get('work')}・{h.get('video_id')}・"
                 f"{h.get('published_at') or h.get('publish_at')}）。横動画は同じ日に2本以上出しません（long_day_guard.py）")

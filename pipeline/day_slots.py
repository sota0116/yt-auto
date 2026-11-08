# 同じチャンネルの公開どうしの間をあける共通の決まり（2026-11-04 新設）
#   本人「同じチャンネルで動画と動画の間は少なくとも時間は空けて。1日2本なら昼と夜、3本なら朝昼夜。あまりにも動画間の時間が近すぎるチャンネルがある」
#   それまでは横 19:00 とショート 20:10、横 20:00 とショート 19:00 のように、1時間しかあかない日があった
# ・PLAN：チャンネルごとの枠。横の日（on）は「朝・昼のショート＋夜の横」、横の無い日（off）は「昼と夜のショート」
#   横の日かどうかは、予約か公開済みの横があるか、曜日（wd）か何日おき（every。前の横から数える）で決める
#   late：横の後の4本目（job の予告、psy の3本目のショート）。横から3時間以上あける
#   extra_on / extra_off：在庫が多い日だけ足す枠（nihongi・okinu の 3本目）
# ・MIN_GAP：どの2本も3時間以上あける。枠そのものは4時間以上あくように並べ、ずれた時の止め役にこの値を使う
# ・数える記録：history/<ch>/ の *uploaded*.json と teasers.json の publish_at / published_at（消えた・差し替えた物は数えない）
# ・標準ライブラリだけで書く（watch.py・shorts_watch.py・upload_*.py のどれからも読むので、import がぐるぐる回らないように）
# ・時間帯ごとの数字は週次（weekly.py）が見て、枠を変える案を出す。枠を変える時はここの PLAN だけを直す
import datetime, glob, json, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JST = datetime.timezone(datetime.timedelta(hours=9))
MIN_GAP = datetime.timedelta(hours=3)

PLAN = {
    # job は 2026-11-08 から1日おきの横（週3〜4本）。横の無い日の off は「2本なら昼と夜」に合う 12:10・19:10（2026-11-04 に決めた時刻）
    "job": {"long": "19:00", "every": 2, "on": ["07:10", "12:10"], "off": ["12:10", "19:10"], "late": "22:10"},
    "psy": {"long": "19:00", "wd": [2, 4, 6], "on": ["07:10", "12:10", "22:10"], "off": ["07:10", "12:10", "20:10"]},
    "spi": {"long": "18:00", "wd": [2], "on": ["07:15", "11:15"], "off": ["11:15", "19:15"]},
    "kakure": {"long": "20:00", "every": 2, "on": ["12:00"], "off": ["19:00"]},
    # shimei は 2026-11-07 本人の指示でショート1日1本（Lovart の無料モードで横1本に約5回の実行がかかり、ショートが 11/05 で切れたため）
    "shimei": {"long": "20:00", "every": 2, "on": ["12:00"], "off": ["19:00"]},
    "nihongi": {"long": "20:00", "every": 2, "on": ["07:00", "12:10"], "off": ["12:10", "20:00"], "extra_off": "07:00"},
    "okinu": {"long": "18:00", "every": 2, "on": ["12:00"], "off": ["19:00"], "extra_on": "07:00", "extra_off": "12:00"},
}
BASE = json.loads(json.dumps(PLAN))  # 上の書いたままの枠（週次が直した分は入らない）

# 週次（weekly.py → slot_apply.py）が数字を見て直したショートの枠。ここに書いた分が上の PLAN より優先する（2026-11-04〜）
#   形：{"<ch>": {"on": [...], "off": [...], "extra_on": "HH:MM", "extra_off": "HH:MM"}, "_log": [{日付, ch, key, from, to, 根拠}]}
#   元に戻す時は、その ch の行を消す（PLAN の書いたままに戻る）
OVERRIDE_PATH = os.path.join(ROOT, "history", "slot_plan.json")
AUTO_KEYS = ("on", "off", "extra_on", "extra_off")  # 週次が直してよいのはショートの枠だけ（横の時刻・予告の late は人が決める）
try:
    _ov = json.load(open(OVERRIDE_PATH, encoding="utf-8"))
except (OSError, ValueError):
    _ov = {}
for _ch, _v in _ov.items():
    if _ch in PLAN and isinstance(_v, dict):
        PLAN[_ch].update({k: x for k, x in _v.items() if k in AUTO_KEYS})


def band(hm):
    """朝（5:00〜9:59）・昼（10:00〜15:59）・夜（16:00〜）"""
    h = int(hm[:2])
    return "朝" if h < 10 else ("昼" if h < 16 else "夜")


def plan_problems(pl):
    """枠の決まりに合わない所（[文]）。本人の決まり：どの2本も3時間以上あける。1日2本なら昼と夜、3本なら朝昼夜（4本の日は夜が2本）"""
    out = []
    days = {"横の日": [pl["long"]] + list(pl["on"]) + ([pl["late"]] if pl.get("late") else []),
            "横の日（在庫が多い日）": [pl["long"]] + list(pl["on"]) + ([pl["late"]] if pl.get("late") else []) + ([pl["extra_on"]] if pl.get("extra_on") else []),
            "横の無い日": list(pl["off"]),
            "横の無い日（在庫が多い日）": list(pl["off"]) + ([pl["extra_off"]] if pl.get("extra_off") else [])}
    if pl.get("wd") is not None and len(pl["wd"]) == 7:
        days = {k: v for k, v in days.items() if k.startswith("横の日")}
    allt = []
    for name, ts in days.items():
        if any(not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", t) for t in ts):
            out.append(f"{name}：時刻の形が違う {ts}")
            continue
        ts = sorted(set(ts))
        allt += ts
        if any(not ("06:00" <= t <= "23:30") for t in ts):
            out.append(f"{name}：6:00〜23:30 の外がある {ts}")
        mins = [int(t[:2]) * 60 + int(t[3:]) for t in ts]
        if any(b - a < MIN_GAP.total_seconds() // 60 for a, b in zip(mins, mins[1:])):
            out.append(f"{name}：3時間あいていない {ts}")
        need = {2: ["昼", "夜"], 3: ["朝", "昼", "夜"], 4: ["朝", "昼", "夜", "夜"]}.get(len(ts))
        if need and [band(t) for t in ts] != need:
            out.append(f"{name}：{len(ts)}本なら {'・'.join(need)}（いまは {'・'.join(band(t) for t in ts)} {ts}）")
    if allt:
        lo, hi = min(allt), max(allt)
        if (24 * 60 - (int(hi[:2]) * 60 + int(hi[3:]))) + int(lo[:2]) * 60 + int(lo[3:]) < MIN_GAP.total_seconds() // 60:
            out.append(f"夜の最後 {hi} と次の朝の最初 {lo} が3時間あいていない")
    return out


def _ts(s):
    if not s:
        return None
    d = datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))
    return (d if d.tzinfo else d.replace(tzinfo=JST)).astimezone(JST)


def _is_long(path, h):
    if h.get("format") in ("long", "short") or h.get("kind") in ("long", "short"):
        return (h.get("format") or h.get("kind")) == "long"
    base = os.path.basename(path)
    if base.startswith("long_"):
        return True
    if "shorts" in base or base == "teasers.json":
        return False
    return not re.match(r"S\d", h.get("work") or "")


def booked(ch):
    """[(日時, 横か, video_id, 名前)]：公開済みと予約中の全部（ショート・横・予告）"""
    out = []
    paths = glob.glob(os.path.join(ROOT, "history", ch, "*uploaded*.json")) + glob.glob(os.path.join(ROOT, "history", ch, "teasers.json"))
    for p in paths:
        try:
            rows = json.load(open(p, encoding="utf-8"))
        except (OSError, ValueError):
            continue
        rows = [{"work": k, **v} for k, v in rows.items()] if isinstance(rows, dict) else rows
        for h in rows:
            if not isinstance(h, dict) or h.get("missing") or h.get("retired"):
                continue
            t = _ts(h.get("published_at") or h.get("publish_at"))
            if t:
                out.append((t, _is_long(p, h), h.get("video_id"), h.get("work")))
    return out


def long_day(ch, day, rows=None):
    """その日（date）が横の日か：予約・公開済みの横がある日、無ければ曜日か「前の横から何日おき」で決める"""
    rows = booked(ch) if rows is None else rows
    longs = sorted({t.date() for t, lg, _, _ in rows if lg})
    if day in longs:
        return True
    pl = PLAN.get(ch) or {}
    if pl.get("wd") is not None:
        return day.weekday() in pl["wd"]
    every = int(pl.get("every") or 1)
    before = [d for d in longs if d < day]
    if any(0 < (d - day).days < every for d in longs):
        return False  # すぐ後ろに横の予約がある日は、推定で横の日にしない（okinu 11/05・11/08 の間の 11/07 など）
    if not before:
        return False
    return (day - before[-1]).days % every == 0


def short_times(ch, day, extra=False, rows=None):
    """その日のショートの枠（"HH:MM" の並び。早い順）。extra=True で在庫の多い日の枠も足す"""
    pl = PLAN[ch]
    on = long_day(ch, day, rows)
    ts = list(pl["on"] if on else pl["off"])
    x = pl.get("extra_on" if on else "extra_off")
    if extra and x and x not in ts:
        ts.append(x)
    return sorted(ts)


def at_of(day, hm):
    hh, mm = map(int, hm.split(":"))
    return datetime.datetime(day.year, day.month, day.day, hh, mm, tzinfo=JST)


def near(ch, at, skip_vid=None, extra=(), rows=None):
    """at から MIN_GAP 未満のところにある公開・予約（[(日時, 名前)]）。extra はまだ記録に書いていない予約の日時"""
    at = at.astimezone(JST)
    rows = booked(ch) if rows is None else rows
    hits = [(t, w) for t, _, v, w in rows if (not skip_vid or v != skip_vid)]
    hits += [(_ts(x) if isinstance(x, str) else x.astimezone(JST), "（この実行で入れた予約）") for x in extra]
    return [(t, w) for t, w in hits if abs(t - at) < MIN_GAP]


def gap_ok(ch, at, skip_vid=None, extra=(), rows=None):
    return not near(ch, at, skip_vid, extra, rows)


def check(ch, at, skip_vid=None, extra=()):
    """予約の前に呼ぶ。近すぎれば止める（ショートの予約を入れる道具用）"""
    hits = near(ch, at, skip_vid, extra)
    if hits:
        t, w = hits[0]
        sys.exit(f"【止めました】{at.astimezone(JST):%m/%d %H:%M} は、同じチャンネルの {w}（{t:%m/%d %H:%M}）と "
                 f"{int(MIN_GAP.total_seconds() // 3600)}時間あいていません（day_slots.py。1日2本なら昼と夜、3本なら朝昼夜）")


def next_short(ch, used=(), after=None, extra=False, skip_vid=None, days=60):
    """after（既定は今から1時間後）より後で、空いていて、前後3時間に何も無い最初のショートの枠。used はまだ記録に無い予約"""
    rows = booked(ch)
    now = datetime.datetime.now(JST)
    after = max(after or now, now + datetime.timedelta(hours=1))
    day = after.date()
    for _ in range(days):
        for hm in short_times(ch, day, extra, rows):
            t = at_of(day, hm)
            if t > after and gap_ok(ch, t, skip_vid, used, rows):
                return t
        day += datetime.timedelta(days=1)
    return None


if __name__ == "__main__":
    # python -X utf8 pipeline\day_slots.py [ch ...]：これから先の予約のうち、3時間あいていない組を出す（直す前の確かめ用）
    now = datetime.datetime.now(JST)
    bad = 0
    for ch in sys.argv[1:] or list(PLAN):
        for x in plan_problems(PLAN[ch]):
            bad += 1
            print(f"{ch}: 枠の決まり：{x}")
        rows = sorted(r for r in booked(ch) if r[0] > now)
        for (a, al, _, aw), (b, bl, _, bw) in zip(rows, rows[1:]):
            if b - a < MIN_GAP:
                bad += 1
                print(f"{ch}: {a:%m/%d %H:%M} {'横' if al else '縦'} {aw} ／ {b:%m/%d %H:%M} {'横' if bl else '縦'} {bw}（{int((b - a).total_seconds() // 60)}分）")
    print(f"3時間あいていない組：{bad}")

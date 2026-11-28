# 同じチャンネルの公開どうしの間をあける共通の決まり（2026-11-04 新設）
#   本人「同じチャンネルで動画と動画の間は少なくとも時間は空けて。1日2本なら昼と夜、3本なら朝昼夜。あまりにも動画間の時間が近すぎるチャンネルがある」
#   それまでは横 19:00 とショート 20:10、横 20:00 とショート 19:00 のように、1時間しかあかない日があった
# ・PLAN：チャンネルごとの枠。横の日（on）は「朝・昼のショート＋夜の横」、横の無い日（off）は「昼と夜のショート」
#   横の日かどうかは、予約か公開済みの横があるか、曜日（wd）か何日おき（every。前の横から数える）で決める
#   late：横の後の4本目（job の予告、psy の3本目のショート）。横から3時間以上、ほかのショートから6時間以上あける
#   extra_on / extra_off：在庫が多い日だけ足す枠（nihongi・okinu の 3本目）
# ・SHORT_GAP：同じチャンネルのショート（予告も）どうしは6時間以上あける（2026-11-28 本人「同じチャンネルでショートは6時間以上あけてね」）
# ・MIN_GAP：横とショート、横と横は3時間以上あける（上の決まりの前からある線。変えていない）
#   枠は6時間ちょうどにせず10分前後の余裕を持たせる（YouTube の公開は予約より数十秒遅れることがあり、公開済みは実際の時刻で数える）
# ・数える記録：history/<ch>/ の *uploaded*.json と teasers.json の publish_at / published_at（消えた・差し替えた物は数えない）
#   に加えて、YouTube の実際の公開・予約（live_rows）。クラウドと PC は互いの記録が見えないので、記録だけだと同じ枠に2本入る（2026-11-28 に確認）
# ・標準ライブラリだけで書く（watch.py・shorts_watch.py・upload_*.py のどれからも読むので、import がぐるぐる回らないように）
# ・時間帯ごとの数字は週次（weekly.py）が見て、枠を変える案を出す。枠を変える時はここの PLAN だけを直す
import datetime, glob, json, os, re, sys, time, urllib.error, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JST = datetime.timezone(datetime.timedelta(hours=9))
MIN_GAP = datetime.timedelta(hours=3)
SHORT_GAP = datetime.timedelta(hours=6)
API = "https://www.googleapis.com/youtube/v3"
# 記録を読む場所。クラウドと PC の記録は別々なので、両方ある機械では DAY_SLOTS_EXTRA_ROOTS（;区切り）でもう片方も読める
ROOTS = [ROOT] + [r for r in os.environ.get("DAY_SLOTS_EXTRA_ROOTS", "").split(os.pathsep) if r]


def need_gap(a_long, b_long):
    """2本の間に要る時間。両方ショートの時だけ6時間"""
    return MIN_GAP if (a_long or b_long) else SHORT_GAP

PLAN = {
    # job は 2026-11-08 から1日おきの横（週3〜4本）。横の無い日の off は「2本なら昼と夜」に合う 12:10・19:10（2026-11-04 に決めた時刻）
    "job": {"long": "19:00", "every": 2, "on": ["07:10", "13:20"], "off": ["12:10", "19:10"], "late": "22:10"},
    "psy": {"long": "19:00", "wd": [2, 4, 6], "on": ["07:10", "13:20", "22:10"], "off": ["07:10", "13:20", "20:10"]},
    "spi": {"long": "18:00", "wd": [2], "on": ["07:15", "13:25"], "off": ["07:15", "13:25", "19:35"]},
    "kakure": {"long": "20:00", "every": 2, "on": ["12:00"], "off": ["19:00"]},
    "shimei": {"long": "20:00", "every": 2, "on": ["07:00", "13:10"], "off": ["07:00", "13:10", "19:20"]},
    "nihongi": {"long": "20:00", "every": 2, "on": ["07:00", "13:10"], "off": ["07:00", "13:10", "20:00"]},
    "okinu": {"long": "18:00", "every": 2, "on": ["07:00", "13:10"], "off": ["07:00", "13:10", "19:20"]},
    "shinshiten": {"long": "21:00", "wd": [2, 6], "on": ["07:30", "13:40"], "off": ["07:30", "13:40", "19:50"]},
    # karada（カラダイブ）は横だけを毎日 19:00（仮。看板 v4 §8）。ショートは作らないので on・off は空（2026-11-13）
    "karada": {"long": "19:00", "every": 1, "on": [], "off": []},
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
_OVERRIDDEN = [c for c in _ov if c in PLAN and isinstance(_ov[c], dict)]


def band(hm):
    """朝（5:00〜9:59）・昼（10:00〜15:59）・夜（16:00〜）"""
    h = int(hm[:2])
    return "朝" if h < 10 else ("昼" if h < 16 else "夜")


def _mins(t):
    return int(t[:2]) * 60 + int(t[3:])


def plan_problems(pl):
    """枠の決まりに合わない所（[文]）。本人の決まり：ショートどうしは6時間以上、横との間は3時間以上。1日2本なら昼と夜、3本なら朝昼夜（4本の日は夜が2本）"""
    out = []
    late = [(pl["late"], False)] if pl.get("late") else []
    on = [(pl["long"], True)] + [(t, False) for t in pl["on"]] + late
    off = [(t, False) for t in pl["off"]]
    days = {"横の日": on,
            "横の日（在庫が多い日）": on + ([(pl["extra_on"], False)] if pl.get("extra_on") else []),
            "横の無い日": off,
            "横の無い日（在庫が多い日）": off + ([(pl["extra_off"], False)] if pl.get("extra_off") else [])}
    if pl.get("wd") is not None and len(pl["wd"]) == 7:
        days = {k: v for k, v in days.items() if k.startswith("横の日")}
    good = []
    for name, items in days.items():
        raw = [t for t, _ in items]
        if any(not isinstance(t, str) or not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", t) for t in raw):
            out.append(f"{name}：時刻の形が違う {raw}")
            continue
        items = sorted(set(items))
        ts = [t for t, _ in items]
        good.append(items)
        if any(not ("06:00" <= t <= "23:30") for t in ts):
            out.append(f"{name}：6:00〜23:30 の外がある {ts}")
        for k, (a, al) in enumerate(items):
            for b, bl in items[k + 1:]:
                g = int(need_gap(al, bl).total_seconds() // 60)
                if _mins(b) - _mins(a) < g:
                    out.append(f"{name}：{a} と {b} が{g // 60}時間あいていない")
        need = {2: ["昼", "夜"], 3: ["朝", "昼", "夜"], 4: ["朝", "昼", "夜", "夜"]}.get(len(ts))
        if need and [band(t) for t in ts] != need:
            out.append(f"{name}：{len(ts)}本なら {'・'.join(need)}（いまは {'・'.join(band(t) for t in ts)} {ts}）")
    seen = set()
    for a_items in good:
        for b_items in good:
            for a, al in a_items:
                for b, bl in b_items:
                    g = int(need_gap(al, bl).total_seconds() // 60)
                    if 24 * 60 - _mins(a) + _mins(b) < g and (a, b) not in seen:
                        seen.add((a, b))
                        out.append(f"前の日の {a} と次の日の {b} が{g // 60}時間あいていない")
    return out


# 週次が直した枠（slot_plan.json）が今の間隔の決まりに合わない時は使わず、上の PLAN の枠に戻す
for _ch in _OVERRIDDEN:
    if plan_problems(PLAN[_ch]):
        print(f"day_slots: slot_plan.json の {_ch} は今の決まりに合わないので使いません", file=sys.stderr)
        PLAN[_ch] = json.loads(json.dumps(BASE[_ch]))


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


_LIVE = {}  # ch -> (読んだ時刻, {video_id: (日時 or None, 横か, 題)})
LIVE_TTL = 120


def live_rows(ch):
    """YouTube の実際の公開・予約（新しい順に200本まで）。{video_id: (日時, 横か, 題)}。日時が None の物は予約も公開もしていない。
    ログインの無い機械（鍵のファイルが無い）では {}。ログインがあるのに読めない時は止める（見えないまま予約しない）"""
    if os.environ.get("DAY_SLOTS_LIVE") == "0":
        return {}
    hit = _LIVE.get(ch)
    if hit and time.time() - hit[0] < LIVE_TTL:
        return hit[1]
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.append(here)
    import yt_auth
    if not os.path.exists(yt_auth.token_path(ch)):
        return {}
    last = None
    for attempt in range(3):
        try:
            head = {"Authorization": "Bearer " + yt_auth.access_token(ch)}

            def get(url):
                return json.load(urllib.request.urlopen(urllib.request.Request(url, headers=head), timeout=60))

            pl = get(f"{API}/channels?part=contentDetails&mine=true")["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
            ids, tok = [], ""
            for _ in range(4):
                try:
                    r = get(f"{API}/playlistItems?part=contentDetails&maxResults=50&playlistId={pl}{tok}")
                except urllib.error.HTTPError as e:
                    if e.code == 404:  # まだ1本も無いチャンネル
                        break
                    raise
                ids += [i["contentDetails"]["videoId"] for i in r.get("items", [])]
                if not r.get("nextPageToken"):
                    break
                tok = "&pageToken=" + r["nextPageToken"]
            # 一覧に出てこない予約があった（2026-11-28 okinu で1本）。記録にある直近とこれからの動画は ID で読み直す
            since = datetime.datetime.now(JST) - datetime.timedelta(days=2)
            seen = set(ids)
            ids += sorted({v for t, _, v, _ in _history_rows(ch) if v and v not in seen and t > since})
            out = {}
            for k in range(0, len(ids), 50):
                for it in get(f"{API}/videos?part=snippet,status,contentDetails&id={','.join(ids[k:k + 50])}").get("items", []):
                    st, sn = it.get("status", {}), it.get("snippet", {})
                    at = None
                    if st.get("privacyStatus") == "private" and st.get("publishAt"):
                        at = _ts(st["publishAt"])
                    elif st.get("privacyStatus") == "public":
                        at = _ts(sn.get("publishedAt"))
                    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", it.get("contentDetails", {}).get("duration") or "")
                    sec = sum(int(x or 0) * w for x, w in zip(m.groups(), (3600, 60, 1))) if m else 0
                    # 横か：3分より長い時だけ。長さがまだ出ない（処理中）時は None＝記録の種類を使う
                    out[it["id"]] = (at, sec > 180 if sec else None, sn.get("title", "")[:40])
            _LIVE[ch] = (time.time(), out)
            return out
        except (Exception, SystemExit) as e:
            last = e
            time.sleep(2 * (attempt + 1))
    sys.exit(f"【止めました】{ch} の YouTube の公開・予約が読めないので、予約の間隔を確かめられません：{str(last)[:200]}")


_MINE = {}  # ch -> {video_id: (日時, 横か)}：この実行で入れた予約（記録への書き込みと YouTube の読み直しより先に数える）


def remember(ch, vid, at, long=False):
    """予約を入れた・動かした直後に呼ぶ。同じ実行の次の判定に数える（videos.list は直後に古い値を返すことがある）"""
    _MINE.setdefault(ch, {})[vid] = (at.astimezone(JST), long)


def booked(ch):
    """[(日時, 横か, video_id, 名前)]：公開済みと予約中の全部（ショート・横・予告）。YouTube を読めた動画は YouTube の時刻を数える。
    記録のこれからの予約が YouTube と違う時は両方の時刻をふさぐ（同じ video_id が2行になる）"""
    out = _history_rows(ch)
    lv = live_rows(ch)
    if lv:
        kind = {v: lg for _, lg, v, _ in out if v}
        name = {v: w for _, _, v, w in out if v}
        now = datetime.datetime.now(JST)
        # videos.list は書き換えの後も古い値を返すことがある（2026-11-28 に確認：同じ動画で新旧が15分以上まざった）。
        # 記録のこれからの予約が YouTube に無いか違う時は、記録の時刻も残して空きと数えない
        rows = [r for r in out if not r[2] or r[2] not in lv
                or (r[0] > now and (not lv[r[2]][0] or abs(r[0] - lv[r[2]][0]) >= datetime.timedelta(minutes=2)))]
        for vid, (at, is_long, title) in lv.items():
            if at:  # 記録と長さのどちらかがショートなら、ショートとして数える（きつい方）。長さがまだ出ない時は記録
                lg = kind.get(vid, is_long) if is_long is None else (is_long and kind.get(vid, True))
                rows.append((at, bool(lg), vid, name.get(vid) or title))
        out = rows
    mine = _MINE.get(ch)
    if mine:
        out = [r for r in out if r[2] not in mine] + [(at, lg, v, "（この実行で入れた予約）") for v, (at, lg) in mine.items()]
    return out


def _history_rows(ch):
    out = []
    paths = [p for root in ROOTS for pat in ("*uploaded*.json", "teasers.json") for p in glob.glob(os.path.join(root, "history", ch, pat))
             if "_前_" not in os.path.basename(p)]  # 控えのファイル（*_前_*.json）は数えない
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


def near(ch, at, skip_vid=None, extra=(), rows=None, long=False):
    """at に置くと近すぎる公開・予約（[(日時, 名前)]）。long は at に置く物が横か。
    extra はまだ記録に書いていない予約。(日時, 横か) で渡す。日時だけの時はショートと見なす（きつい方）"""
    at = at.astimezone(JST)
    rows = booked(ch) if rows is None else rows
    hits = [(t, w) for t, lg, v, w in rows if (not skip_vid or v != skip_vid) and abs(t - at) < need_gap(long, lg)]
    for x in extra:
        when, lg = x if isinstance(x, (tuple, list)) else (x, False)
        when = _ts(when) if isinstance(when, str) else when.astimezone(JST)
        if abs(when - at) < need_gap(long, lg):
            hits.append((when, "（この実行で入れた予約）"))
    return hits


def gap_ok(ch, at, skip_vid=None, extra=(), rows=None, long=False):
    return not near(ch, at, skip_vid, extra, rows, long)


def check(ch, at, skip_vid=None, extra=(), long=False):
    """予約の前に呼ぶ。近すぎれば止める"""
    hits = near(ch, at, skip_vid, extra, long=long)
    if hits:
        t, w = hits[0]
        sys.exit(f"【止めました】{at.astimezone(JST):%m/%d %H:%M} は、同じチャンネルの {w}（{t:%m/%d %H:%M}）と近すぎます"
                 "（day_slots.py：ショートどうしは6時間以上、横との間は3時間以上）")


def next_short(ch, used=(), after=None, extra=False, skip_vid=None, days=60):
    """after（既定は今から1時間後）より後で、ほかのショートと6時間・横と3時間あく最初のショートの枠。used はまだ記録に無い予約"""
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


def violations(rows, since):
    """近すぎる組 [(前, 後)]。後ろが since より後の物だけ。隣どうしでない組も見る"""
    rows = sorted(rows, key=lambda r: (r[0], str(r[2])))
    out = []
    for i, a in enumerate(rows):
        for b in rows[i + 1:]:
            if b[0] - a[0] >= SHORT_GAP:
                break
            if a[2] and a[2] == b[2]:
                continue  # 同じ動画の記録の時刻と YouTube の時刻
            if b[0] > since and b[0] - a[0] < need_gap(a[1], b[1]):
                out.append((a, b))
    return out


if __name__ == "__main__":
    # python -X utf8 pipeline\day_slots.py [ch ...]：これから先の予約のうち、近すぎる組を出す（直す前の確かめ用）
    now = datetime.datetime.now(JST)
    bad = 0
    for ch in sys.argv[1:] or list(PLAN):
        for x in plan_problems(PLAN[ch]):
            bad += 1
            print(f"{ch}: 枠の決まり：{x}")
        for (a, al, _, aw), (b, bl, _, bw) in violations(booked(ch), now):
            bad += 1
            print(f"{ch}: {a:%m/%d %H:%M} {'横' if al else '縦'} {aw} ／ {b:%m/%d %H:%M} {'横' if bl else '縦'} {bw}（{int((b - a).total_seconds() // 60)}分）")
    print(f"近すぎる組（ショートどうしは6時間・横との間は3時間）：{bad}")

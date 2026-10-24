# 暦の固定ファイルを作る（spi 手順書 §8）
#   python -X utf8 pipeline\build_koyomi.py
# ・二十四節気・雑節・朔は国立天文台の暦要項（data/raw/naoj/）、祝日は内閣府の syukujitsu.csv（data/raw/cao/）、
#   年中行事は data/gyoji.json から読む。外のサイトは見ない（保存した raw だけを使う）
# ・2028年1月の朔と大寒（2027年12月28日に始まる旧暦の月の名前を決めるためだけに使う）は、暦要項がまだ無いので ephem で計算する
# ・出力は data/koyomi_2026_2027.json。raw と出力のハッシュを data/sources.json と data/checksums.json に足す（ほかのキーは消さない）
import csv, datetime as dt, hashlib, html, json, math, re, sys
from pathlib import Path

import ephem

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
RAW = DATA / "raw"
OUT = DATA / "koyomi_2026_2027.json"
VALID_FROM = dt.date(2026, 11, 1)
VALID_TO = dt.date(2027, 12, 31)
YEARS = (2026, 2027)
JST = dt.timezone(dt.timedelta(hours=9))

NAOJ_URL = "https://eco.mtk.nao.ac.jp/koyomi/yoko/{y}/rekiyou{yy}{n}.html"
CAO_URL = "https://www8.cao.go.jp/chosei/shukujitsu/syukujitsu.csv"

# 太陽黄経（度）→ 二十四節気の名前
SEKKI = {0: "春分", 15: "清明", 30: "穀雨", 45: "立夏", 60: "小満", 75: "芒種", 90: "夏至", 105: "小暑",
         120: "大暑", 135: "立秋", 150: "処暑", 165: "白露", 180: "秋分", 195: "寒露", 210: "霜降", 225: "立冬",
         240: "小雪", 255: "大雪", 270: "冬至", 285: "小寒", 300: "大寒", 315: "立春", 330: "雨水", 345: "啓蟄"}
STEMS = "甲乙丙丁戊己庚辛壬癸"
BRANCHES = "子丑寅卯辰巳午未申酉戌亥"
WEEK = "月火水木金土日"
ROKUYO = ["大安", "赤口", "先勝", "友引", "先負", "仏滅"]  # (旧暦の月 + 日) % 6
# 天赦日：節月の季節ごとの日の干支（春=戊寅・夏=甲午・秋=戊申・冬=甲子）
TENSHA = {1: "戊寅", 2: "戊寅", 3: "戊寅", 4: "甲午", 5: "甲午", 6: "甲午",
          7: "戊申", 8: "戊申", 9: "戊申", 10: "甲子", 11: "甲子", 12: "甲子"}
# 一粒万倍日：節月ごとの日の十二支
MANBAI = {1: "丑午", 2: "酉寅", 3: "子卯", 4: "卯辰", 5: "巳午", 6: "酉午",
          7: "子未", 8: "卯申", 9: "酉午", 10: "酉戌", 11: "亥子", 12: "卯子"}
DOYO_START = {297: 315, 27: 45, 117: 135, 207: 225}  # 土用の入りの黄経 → 明けの翌日の節気（立春・立夏・立秋・立冬）


def kanshi_index(d):
    # 0 = 甲子。ユリウス日 + 49 を60で割った余り
    return (d.toordinal() + 1721425 + 49) % 60


def kanshi(d):
    i = kanshi_index(d)
    return STEMS[i % 10] + BRANCHES[i % 12]


def _text(path):
    x = path.read_bytes().decode("cp932")
    x = re.sub(r"<script.*?</script>", "", x, flags=re.S)
    x = re.sub(r"<[^>]+>", " ", x)
    return re.sub(r"\s+", " ", html.unescape(x))


def _naoj_file(y, n):
    fs = sorted((RAW / "naoj").glob(f"yoko_{y}_{n}_*.html"))
    if len(fs) != 1:
        sys.exit(f"【止まりました】暦要項の raw がありません: data/raw/naoj/yoko_{y}_{n}_*.html")
    return fs[0]


def parse_naoj(y):
    """暦要項の二十四節気・雑節・朔を読む。日時は日本時間（中央標準時）"""
    t = _text(_naoj_file(y, 2))
    names = "|".join(list(SEKKI.values()) + ["土用", "入梅", "半夏生"])
    sekki, zassetsu = [], []
    for m in re.finditer(rf"({names}) (\d+)度 (\d+)月(\d+)日 (\d+)時(\d+)分", t):
        name, deg, mo, da, hh, mi = m.group(1), *map(int, m.groups()[1:])
        when = dt.datetime(y, mo, da, hh, mi, tzinfo=JST)
        if name in SEKKI.values():
            if SEKKI[deg] != name:
                sys.exit(f"【止まりました】暦要項の節気の度数が合いません: {name} {deg}")
            sekki.append({"name": name, "deg": deg, "dt": when})
        else:
            zassetsu.append({"name": name, "deg": deg, "date": when.date(), "dt": when})
    for m in re.finditer(r"(節分|彼岸|八十八夜|二百十日) (\d+)月(\d+)日(?! \d+時)", t):
        zassetsu.append({"name": m.group(1), "deg": None, "date": dt.date(y, int(m.group(2)), int(m.group(3))), "dt": None})
    if len(sekki) != 24 or len(zassetsu) != 11:
        sys.exit(f"【止まりました】{y}年の暦要項の読み取り数が違います（節気{len(sekki)}・雑節{len(zassetsu)}）")
    t3 = _text(_naoj_file(y, 3))
    saku = [dt.datetime(y, int(a), int(b), int(c), int(d), tzinfo=JST)
            for a, b, c, d in re.findall(r"朔 (\d+)月(\d+)日 (\d+)時(\d+)分", t3)]
    if not 12 <= len(saku) <= 13:
        sys.exit(f"【止まりました】{y}年の朔の数が違います（{len(saku)}）")
    return sorted(sekki, key=lambda s: s["dt"]), zassetsu, saku


def parse_holidays():
    rows = (RAW / "cao" / "syukujitsu.csv").read_bytes().decode("cp932").splitlines()
    out = {}
    for r in csv.reader(rows[1:]):
        if len(r) >= 2 and r[0]:
            y, m, d = map(int, r[0].split("/"))
            out[dt.date(y, m, d)] = r[1]
    return out


# ephem での照らし合わせ（暦要項の値を正とし、差が大きい時だけ止める）
def _edate(t):
    return ephem.Date(t.astimezone(dt.timezone.utc).replace(tzinfo=None))


def _jst(e):
    return ephem.Date(e).datetime().replace(tzinfo=dt.timezone.utc).astimezone(JST)


def _sun_lon(e):
    s = ephem.Sun()
    s.compute(e, epoch=e)
    return math.degrees(ephem.Ecliptic(ephem.Equatorial(s.ra, s.dec, epoch=e), epoch=e).lon)


def solve_sekki(deg, near):
    lo, hi = _edate(near) - 3, _edate(near) + 3
    f = lambda e: (_sun_lon(e) - deg + 180) % 360 - 180
    for _ in range(60):
        mid = (lo + hi) / 2
        if f(mid) < 0:
            lo = mid
        else:
            hi = mid
    return _jst(lo)


def ephem_new_moon_after(t):
    return _jst(ephem.next_new_moon(_edate(t)))


def lunar_months(saku_dates, chuki, start):
    """旧暦の月：朔の日（日本時間の日付）から次の朔の前日まで。月の名前は、その月に入る中気で決める。
    start を含む月から、最後の朔の前日までを返す"""
    first = max(i for i, d in enumerate(saku_dates) if d <= start)
    months = []
    for a, b in zip(saku_dates[first:], saku_dates[first + 1:]):
        cs = [deg for d, deg in chuki if a <= d < b]
        if len(cs) != 1:
            # 中気が0（閏月）か2（2033年問題の型）の月。この範囲で出たら、決まりを決めてから作り直す
            sys.exit(f"【止まりました】{a} に始まる旧暦の月の中気が {len(cs)} 個です（閏月か2033年型の例外）")
        months.append({"start": a, "end": b - dt.timedelta(days=1), "month": (cs[0] // 30 + 1) % 12 + 1,
                       "leap": False, "chuki": SEKKI[cs[0]]})
    for i, m in enumerate(months):
        if i and m["month"] != months[i - 1]["month"] % 12 + 1:
            sys.exit(f"【止まりました】旧暦の月の並びが続いていません: {m['start']}")
    jan = next((m["start"].year for m in months if m["month"] == 1), None)
    seen_jan = False
    for m in months:
        seen_jan = seen_jan or m["month"] == 1
        m["year"] = (jan if seen_jan else jan - 1) if jan else m["start"].year - (1 if m["month"] >= 11 else 0)
    return months


def day_fields(d, setsu, months):
    """1日分の 節月・旧暦・六曜・選日。setsu は [(節入りの日, 黄経)]、months は lunar_months の戻り値"""
    ki = kanshi_index(d)
    ks = kanshi(d)
    sm_start = max(sd for sd, g in setsu if sd <= d)
    setsu_deg = next(g for sd, g in setsu if sd == sm_start)
    setsugetsu = (setsu_deg - 315) % 360 // 30 + 1
    m = next(x for x in months if x["start"] <= d <= x["end"])
    kd = (d - m["start"]).days + 1
    sen = []
    if ks == TENSHA[setsugetsu]:
        sen.append("天赦日")
    if BRANCHES[ki % 12] in MANBAI[setsugetsu]:
        sen.append("一粒万倍日")
    if BRANCHES[ki % 12] == "寅":
        sen.append("寅の日")
    if BRANCHES[ki % 12] == "巳":
        sen.append("巳の日")
    if ks == "己巳":
        sen.append("己巳の日")
    return {"kanshi": ks, "setsugetsu": setsugetsu,
            "kyureki": {"year": m["year"], "month": m["month"], "day": kd, "leap": m["leap"]},
            "rokuyo": ROKUYO[(m["month"] + kd) % 6], "senjitsu": sen}


def build():
    sekki, zassetsu, saku = [], [], []
    for y in YEARS:
        s, z, k = parse_naoj(y)
        sekki += s
        zassetsu += z
        saku += k
    # 暦要項の値と ephem の計算を照らす（分）
    sekki_diff = max(abs((solve_sekki(s["deg"], s["dt"]) - s["dt"]).total_seconds()) / 60 for s in sekki)
    saku_diff = max(abs((ephem_new_moon_after(k - dt.timedelta(days=2)) - k).total_seconds()) / 60 for k in saku)
    if sekki_diff > 3 or saku_diff > 3:
        sys.exit(f"【止まりました】暦要項と ephem の差が大きすぎます（節気{sekki_diff:.1f}分・朔{saku_diff:.1f}分）")

    # 2028年分（暦要項が未発表）：ephem で計算した値。2027年12月28日に始まる月の名前を決めるためだけに使う
    saku_2028 = ephem_new_moon_after(saku[-1] + dt.timedelta(days=1))
    daikan_2028 = solve_sekki(300, dt.datetime(2028, 1, 20, 12, tzinfo=JST))
    computed_2028 = {"saku": saku_2028.strftime("%Y-%m-%d %H:%M"), "daikan": daikan_2028.strftime("%Y-%m-%d %H:%M")}
    chuki = [(s["dt"].date(), s["deg"]) for s in sekki if s["deg"] % 30 == 0] + [(daikan_2028.date(), 300)]
    setsu = [(s["dt"].date(), s["deg"]) for s in sekki if s["deg"] % 30 == 15]

    saku_dates = sorted(k.date() for k in saku) + [saku_2028.date()]
    months = lunar_months(saku_dates, chuki, VALID_FROM)
    if months[-1]["end"] < VALID_TO:
        sys.exit("【止まりました】旧暦の月が終了日まで届いていません")

    holidays = parse_holidays()
    gyoji = json.loads((DATA / "gyoji.json").read_text(encoding="utf-8"))["events"]

    # 雑節（暦要項に載っている物＋計算で出す物）
    zas = []  # {date, name, basis}
    for z in zassetsu:
        name = z["name"]
        if name == "土用":
            name = "土用入り"
        elif name == "彼岸":
            name = "彼岸入り"
        zas.append({"date": z["date"], "name": name, "basis": "暦要項"})
    for z in zassetsu:
        if z["name"] == "土用":
            nxt = next(s["dt"].date() for s in sekki if s["deg"] == DOYO_START[z["deg"]] and s["dt"].date() > z["date"])
            zas.append({"date": nxt - dt.timedelta(days=1), "name": "土用明け", "basis": "計算（次の立春・立夏・立秋・立冬の前日）"})
        if z["name"] == "彼岸":
            mid = z["date"] + dt.timedelta(days=3)
            zas.append({"date": mid, "name": "彼岸の中日", "basis": "計算（彼岸入りの3日後＝春分・秋分）"})
            zas.append({"date": mid + dt.timedelta(days=3), "name": "彼岸明け", "basis": "計算（中日の3日後）"})
    # 社日：春分・秋分に最も近い戊の日。春分・秋分の日が癸の日（前後の戊が5日ずつ）の時は、瞬間が正午より前なら前の戊、後なら後の戊
    for deg in (0, 180):
        for t in [s["dt"] for s in sekki if s["deg"] == deg]:
            d = t.date()
            stem = kanshi_index(d) % 10
            back = (stem - 4) % 10
            if back < 5:
                sha = d - dt.timedelta(days=back)
            elif back > 5:
                sha = d + dt.timedelta(days=10 - back)
            else:
                sha = d - dt.timedelta(days=5) if t.hour < 12 else d + dt.timedelta(days=5)
            zas.append({"date": sha, "name": "社日", "basis": "計算（春分・秋分に最も近い戊の日。照らした暦サイトなし）"})
    # 土用の期間（入り〜明け）と土用の丑の日
    doyo_days = set()
    for z in [x for x in zas if x["name"] == "土用入り"]:
        end = next(x["date"] for x in zas if x["name"] == "土用明け" and x["date"] > z["date"])
        d = z["date"]
        while d <= end:
            doyo_days.add(d)
            if BRANCHES[kanshi_index(d) % 12] == "丑":
                zas.append({"date": d, "name": "土用の丑の日", "basis": "計算（土用の期間の丑の日）"})
            d += dt.timedelta(days=1)

    # 日ごとの表
    days = []
    d = VALID_FROM
    while d <= VALID_TO:
        f = day_fields(d, setsu, months)
        ki = kanshi_index(d)
        m = next(x for x in months if x["start"] <= d <= x["end"])
        kd = f["kyureki"]["day"]
        sk = [s for s in sekki if s["dt"].date() == d]
        ev = []
        for g in gyoji:
            r = g["rule"]
            if r["type"] == "fixed" and (d.month, d.day) == (r["month"], r["day"]):
                ev.append(g["name"])
            elif r["type"] == "kyureki" and (m["month"], kd) == (r["month"], r["day"]):
                ev.append(g["name"])
            elif r["type"] == "branch_in_month" and d.month == r["month"] and BRANCHES[ki % 12] == r["branch"]:
                n = sum(1 for x in range(1, d.day + 1) if BRANCHES[kanshi_index(d.replace(day=x)) % 12] == r["branch"])
                ev.append(f"{g['name']}（{r['ordinal_names'][n - 1]}）")
        days.append({
            "date": d.isoformat(),
            "weekday": WEEK[d.weekday()],
            "kanshi": f["kanshi"],
            "setsugetsu": f["setsugetsu"],
            "kyureki": f["kyureki"],
            "rokuyo": f["rokuyo"],
            "sekki": {"name": sk[0]["name"], "time": sk[0]["dt"].strftime("%H:%M")} if sk else None,
            "zassetsu": [z["name"] for z in zas if z["date"] == d],
            "doyo": d in doyo_days,
            "senjitsu": f["senjitsu"],
            "holiday": holidays.get(d),
            "gyoji": ev,
        })
        d += dt.timedelta(days=1)

    saikyo = [x["date"] for x in days if "天赦日" in x["senjitsu"] and "一粒万倍日" in x["senjitsu"]]
    in_range = lambda x: VALID_FROM <= x <= VALID_TO
    files = sorted(p for p in (RAW / "naoj").glob("yoko_*.html") if int(p.name[5:9]) in YEARS)
    meta = {
        "valid_from": VALID_FROM.isoformat(),
        "valid_to": VALID_TO.isoformat(),
        "built": dt.datetime.now(JST).strftime("%Y-%m-%d"),
        "builder": "pipeline/build_koyomi.py",
        "timezone": "日本時間（中央標準時）",
        "sources": {
            "naoj": [{"url": NAOJ_URL.format(y=p.name[5:9], yy=p.name[7:9], n=p.name[10]), "file": p.relative_to(ROOT).as_posix()}
                     for p in files],
            "cao": {"url": CAO_URL, "file": "data/raw/cao/syukujitsu.csv"},
            "gyoji": "data/gyoji.json",
            "computed_2028": {**computed_2028, "by": f"ephem {ephem.__version__}",
                              "note": "暦要項 2028 が未発表のため計算値。2027-12-28 に始まる旧暦の月の名前（12月）を決めるためだけに使用"},
        },
        "rules": {
            "setsugetsu": "節入りの日（日付）を新しい節月の1日目とする",
            "kyureki": "暦要項の朔の日（日本時間の日付）を月の1日目とし、月の中の中気で月の名前を決める。中気のない月は閏月",
            "rokuyo": "（旧暦の月＋日）を6で割った余り 0大安 1赤口 2先勝 3友引 4先負 5仏滅",
            "tensha": "節月1〜3 戊寅・4〜6 甲午・7〜9 戊申・10〜12 甲子",
            "manbai": {str(k): list(v) for k, v in MANBAI.items()},
            "shanichi": "春分・秋分に最も近い戊の日（照らした暦サイトなし。台本に出す前に確認が要る）",
        },
        "checks": {
            "ephem_max_diff_min": {"sekki": round(sekki_diff, 2), "saku": round(saku_diff, 2)},
            "kyureki_months_one_chuki_each": True,
            "leap_month_in_range": any(m["leap"] for m in months),
        },
        "saikyo_kaiun": saikyo,
    }
    out = {
        "meta": meta,
        "sekki": [{"name": s["name"], "deg": s["deg"], "datetime": s["dt"].strftime("%Y-%m-%d %H:%M")}
                  for s in sekki if in_range(s["dt"].date())],
        "zassetsu": sorted([{"date": z["date"].isoformat(), "name": z["name"], "basis": z["basis"]}
                            for z in zas if in_range(z["date"])], key=lambda z: (z["date"], z["name"])),
        "kyureki_months": [{"year": m["year"], "month": m["month"], "leap": m["leap"], "start": m["start"].isoformat(),
                            "end": m["end"].isoformat(), "chuki": m["chuki"]} for m in months],
        "days": days,
    }
    return out


def sha256(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def _write_json(p, obj):
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def record_hashes(out_files):
    """raw と出力のハッシュを sources.json / checksums.json に足す（既存のキーは残す）"""
    src = json.loads((DATA / "sources.json").read_text(encoding="utf-8"))
    chk = json.loads((DATA / "checksums.json").read_text(encoding="utf-8"))
    fetched = "2026-10-24"
    entries = {}
    for p in sorted((RAW / "naoj").glob("yoko_*.html")):
        y, n = p.name[5:9], p.name[10]
        entries[f"koyomi_naoj_{y}_{n}"] = {"dataset": f"国立天文台 暦要項 {y}年 ({n})", "url": NAOJ_URL.format(y=y, yy=y[2:], n=n),
                                           "file": p.relative_to(ROOT).as_posix()}
    entries["koyomi_cao_syukujitsu"] = {"dataset": "内閣府 国民の祝日 syukujitsu.csv", "url": CAO_URL,
                                        "file": "data/raw/cao/syukujitsu.csv"}
    g = json.loads((DATA / "gyoji.json").read_text(encoding="utf-8"))
    seen = {}
    for e in g["events"]:
        for s in e["sources"]:
            seen.setdefault(s["file"], s["url"])
    for f, u in seen.items():
        entries["koyomi_gyoji_" + Path(f).stem] = {"dataset": "年中行事の出典", "url": u, "file": f}
    for k, v in entries.items():
        v["sha256"] = sha256(ROOT / v["file"])
        v["fetched"] = fetched
        src[k] = v
        chk[v["file"]] = v["sha256"]
    for p in sorted((RAW / "xcheck").rglob("*")):
        if p.is_file():
            chk[p.relative_to(ROOT).as_posix()] = sha256(p)
    for p in out_files:
        chk[Path(p).relative_to(ROOT).as_posix()] = sha256(p)
    _write_json(DATA / "sources.json", src)
    _write_json(DATA / "checksums.json", chk)


if __name__ == "__main__":
    out = build()
    _write_json(OUT, out)
    outs = [OUT, DATA / "gyoji.json"]
    if (DATA / "koyomi_check.md").exists():
        outs.append(DATA / "koyomi_check.md")
    record_hashes(outs)
    m = out["meta"]
    print("書きました:", OUT.relative_to(ROOT).as_posix(), f"{len(out['days'])}日分")
    print("ephem との差（分）:", m["checks"]["ephem_max_diff_min"])
    print("最強開運日:", ", ".join(m["saikyo_kaiun"]))

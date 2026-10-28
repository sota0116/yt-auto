# 千年こよみ（spi）の暦の部品（2026-10-29 新設）：暦の固定ファイル data/koyomi_2026_2027.json から、
#   ネタ選び（pick_neta_spi.py）・台本の点検（check_spi_script.py）・台本ゲート（gate_script_spi.py）が使う値を作る
#   python -X utf8 pipeline/koyomi_spi.py <作業フォルダ>     … neta.json から facts.json の "koyomi" の欄を作り直して表示する（確かめ用）
# ・日付・曜日・干支・六曜・選日・重なり・回数は、全部この固定ファイルの値だけで出す（Claude に暦の計算をさせない。手順書 §8）
# ・facts.json の "koyomi" の欄はこのファイルが書く。書き手（write_script_spi.py）は書き換えない。台本ゲートが作り直して一致を確かめる
import datetime as dt, json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KOYOMI = os.path.join(ROOT, "data", "koyomi_2026_2027.json")
GYOJI = os.path.join(ROOT, "data", "gyoji.json")
JST = dt.timezone(dt.timedelta(hours=9))
SEN = ["天赦日", "一粒万倍日", "寅の日", "己巳の日", "巳の日"]  # 重なりの名前を並べる順（強い順）
SHORT = {"天赦日": "天赦", "一粒万倍日": "万倍", "寅の日": "寅", "己巳の日": "己巳", "巳の日": "巳"}  # カレンダーの印の名前（check の LAB と同じ）
WD = "月火水木金土日"
_K = None


def K():
    global _K
    if _K is None:
        _K = json.load(open(KOYOMI, encoding="utf-8"))
        _K["_day"] = {d["date"]: d for d in _K["days"]}
    return _K


def day(iso):
    return K()["_day"].get(iso)


def today():
    return dt.datetime.now(JST).date()


def d(iso):
    return dt.date.fromisoformat(iso) if isinstance(iso, str) else iso


def label(iso, year=False):
    x = d(iso)
    return f"{str(x.year) + '年' if year else ''}{x.month}月{x.day}日"


def wd(iso):
    return WD[d(iso).weekday()]


def sen(dy):
    """その日の選日（己巳の日は巳の日でもあるので、重なりを数える時は巳の日を外す）"""
    s = set(dy["senjitsu"])
    if "己巳の日" in s:
        s.discard("巳の日")
    return [x for x in SEN if x in s]


def overlap_name(dy):
    s = sen(dy)
    return " × ".join(s) if len(s) >= 2 else None


def info(iso):
    dy = day(iso)
    if not dy:
        return {"date": iso, "暦の固定ファイルの外": True}
    k = dy["kyureki"]
    return {"date": iso, "声で言う形": f"{label(iso)}、{dy['weekday']}曜日", "曜日": dy["weekday"], "干支": dy["kanshi"], "六曜": dy["rokuyo"],
            "旧暦": f"{'閏' if k['leap'] else ''}{k['month']}月{k['day']}日", "節月": dy["setsugetsu"], "選日": dy["senjitsu"],
            "重なり": overlap_name(dy), "節気": (dy["sekki"] or {}).get("name"), "雑節": dy["zassetsu"], "土用": dy["doyo"],
            "祝日": dy["holiday"], "行事": dy["gyoji"]}


def overlaps(after, n=3, names=None, until=None):
    """after より後（after の日を含む）に来る重なり（選日が2つ以上の日）を近い順に。names を渡すとその組み合わせだけ"""
    out = []
    for dy in K()["days"]:
        if dy["date"] < str(after) or (until and dy["date"] > str(until)):
            continue
        nm = overlap_name(dy)
        if not nm or (names and not all(x in sen(dy) for x in names)):
            continue
        out.append({"date": label(dy["date"]), "year": int(dy["date"][:4]), "iso": dy["date"], "wd": dy["weekday"], "names": nm})
        if n and len(out) >= n:
            break
    return out


def month_marks(y, m, names=("天赦日", "一粒万倍日", "寅の日", "己巳の日", "巳の日")):
    """1か月分のカレンダーの印（calendar カードの marks の形）。lab は「万倍」「天赦・万倍」のように略称を「・」でつなぐ"""
    out = []
    for dy in K()["days"]:
        if not dy["date"].startswith(f"{y}-{m:02d}-"):
            continue
        hit = [SHORT[x] for x in sen(dy) if x in names]
        if hit:
            out.append({"d": int(dy["date"][8:]), "lab": "・".join(hit)})
    return out


def counts(prefix):
    """prefix（"2027" か "2027-03"）の期間の選日・大安・重なりの数"""
    days = [x for x in K()["days"] if x["date"].startswith(prefix)]
    c = {nm: sum(nm in x["senjitsu"] for x in days) for nm in SEN}
    c["大安"] = sum(x["rokuyo"] == "大安" for x in days)
    c["天赦日と一粒万倍日が重なる日"] = sum("天赦日" in x["senjitsu"] and "一粒万倍日" in x["senjitsu"] for x in days)
    c["選日が2つ以上重なる日"] = sum(bool(overlap_name(x)) for x in days)
    c["_日数"] = len(days)
    return c


def gyoji_src(name):
    for e in json.load(open(GYOJI, encoding="utf-8"))["events"]:
        if e["name"].split("（")[0] in name or name in e["name"]:
            return {"name": e["name"], "sources": [{"url": s["url"], "quote": s["quote"]} for s in e["sources"]], "note": e.get("note")}
    return None


def months_between(a, b):
    a, b = d(a).replace(day=1), d(b).replace(day=1)
    out = []
    while a <= b:
        out.append((a.year, a.month))
        a = (a + dt.timedelta(days=32)).replace(day=1)
    return out


def facts(neta):
    """neta.json（pick_neta_spi.py が置く）から facts.json の "koyomi" の欄を作る。同じ neta なら何度作っても同じ中身"""
    meta = K()["meta"]
    pub = neta["pub_date"]
    focus = sorted(set(neta.get("focus_dates") or []))
    tm = neta.get("target_month")
    span_from = min([pub] + focus + ([tm + "-01"] if tm else []))
    span_to = max([pub] + focus + ([tm + "-28"] if tm else []))
    mon = months_between(span_from, (d(span_to) + dt.timedelta(days=31)).isoformat())
    mon = [(y, m) for y, m in mon if f"{y}-{m:02d}-01" >= meta["valid_from"][:8] + "01" and f"{y}-{m:02d}-01" <= meta["valid_to"]]
    f = {
        "_説明": "pipeline/koyomi_spi.py が data/koyomi_2026_2027.json だけから作った欄。書き手は書き換えない（台本ゲートが作り直して照らす）。"
                 "台本・タイトル・サムネ・カードの日付・曜日・干支・六曜・選日・重なり・回数は、この欄の値だけを使う",
        "暦の固定ファイル": {"有効": [meta["valid_from"], meta["valid_to"]], "作った日": meta["built"]},
        "公開日": info(pub),
        "公開できる期間": neta.get("window"),
        "主役の日": [info(x) for x in focus],
        "次の重なり_公開日から近い順": overlaps(pub, 3),
        "最強開運日_天赦日と一粒万倍日が重なる日": [x for x in meta["saikyo_kaiun"]],
        "月ごと": {f"{y}-{m:02d}": {"数": counts(f"{y}-{m:02d}"), "カレンダーの印": month_marks(y, m),
                                   "重なり": overlaps(f"{y}-{m:02d}-01", 0, until=f"{y}-{m:02d}-31")} for y, m in mon},
        "年ごと": {y: counts(y) for y in ("2027",)},
        "節気": [{"name": s["name"], "date": s["datetime"][:10], "time": s["datetime"][11:]} for s in K()["sekki"]
                 if span_from <= s["datetime"][:10] <= (d(span_to) + dt.timedelta(days=31)).isoformat()],
        "雑節": [z for z in K()["zassetsu"] if span_from <= z["date"] <= (d(span_to) + dt.timedelta(days=31)).isoformat()],
    }
    if neta.get("overlap"):
        f["この回の重なり"] = {"組み合わせ": " × ".join(neta["overlap"]),
                            "公開日から近い順": overlaps(pub, 5, names=neta["overlap"]),
                            "2027年の数": sum(all(x in sen(dy) for x in neta["overlap"]) for dy in K()["days"] if dy["date"].startswith("2027"))}
    if neta.get("gyoji"):
        f["行事の出典"] = [g for g in (gyoji_src(x) for x in neta["gyoji"]) if g]
    return f


def main():
    work = sys.argv[1]
    neta = json.load(open(os.path.join(work, "neta.json"), encoding="utf-8"))
    print(json.dumps(facts(neta), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()

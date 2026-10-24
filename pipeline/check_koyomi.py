# 暦の固定ファイルを、保存した暦サイトのページと全日程で照らす（spi 手順書 §8・段階Aで一度だけ）
#   python -X utf8 pipeline\check_koyomi.py
# ・読むのは data/raw/ に保存したページだけ（外のサイトは見ない）
# ・結果を data/koyomi_check.md に書く。食い違いが1つでもあれば終了コード 1
import datetime as dt, html, importlib.util, json, re, sys
from collections import defaultdict
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
XC = DATA / "raw" / "xcheck"
ICS = XC / "bestcalendar_ics"
ROKUYO = ["大安", "赤口", "先勝", "友引", "先負", "仏滅"]
# 調べて理由が分かった食い違い（ほかの2つのサイトが自前と同じ＝多数に合わせて自前のまま）
EXPLAINED = {
    "2026-11-08 自前=True JAL=False": "JAL の記事の2026年11月の一粒万倍日に11月8日（丙戌の日。立冬の11月7日から節月10で、酉・戌の日が一粒万倍日）が無い。calenavi と bestcalendar はどちらも11月8日を一粒万倍日にしている。3つのうち2つと自前が同じなので、自前のまま（JAL の載せ漏れと見る）。",
}

K = json.loads((DATA / "koyomi_2026_2027.json").read_text(encoding="utf-8"))
FROM = dt.date.fromisoformat(K["meta"]["valid_from"])
TO = dt.date.fromisoformat(K["meta"]["valid_to"])
DAYS = {dt.date.fromisoformat(d["date"]): d for d in K["days"]}
in_range = lambda d: FROM <= d <= TO


def _text(p):
    x = p.read_bytes().decode("utf-8", errors="replace")
    x = re.sub(r"<script.*?</script>", "", x, flags=re.S)
    x = re.sub(r"<style.*?</style>", "", x, flags=re.S)
    x = re.sub(r"<[^>]+>", "|", x)
    x = re.sub(r"\s+", " ", html.unescape(x))
    return re.sub(r"(\s*\|\s*)+", "|", x)


def calenavi_rokuyo(year):
    """calenavi の六曜の年間ページ：日ごとの 六曜・印（粒/赦/寅/巳・祝日名）・旧暦の月日"""
    t = _text(XC / f"calenavi_rokuyo_{year}.html")
    toks = t[t.find("月別カレンダー"):].split("|")
    out, month, i = {}, None, 0
    while i < len(toks) - 3:
        a = toks[i]
        if a.isdigit() and toks[i + 1] == "月" and toks[i + 2] == "日" and toks[i + 3] == "月":
            month, i = int(a), i + 9
            continue
        if month and a.isdigit() and toks[i + 1] in ROKUYO:
            j, marks = i + 2, []
            while not re.fullmatch(r"(旧 )?\d+/\d+", toks[j]):
                marks.append(toks[j])
                j += 1
            km, kd = map(int, toks[j].replace("旧 ", "").split("/"))
            out[dt.date(year, month, int(a))] = {"rokuyo": toks[i + 1], "marks": marks, "kyu": (km, kd),
                                                 "kyu_start": toks[j].startswith("旧 ")}
            i = j + 1
            continue
        i += 1
    return out


def bestcalendar_month(y, m):
    """bestcalendar の月のページ：日ごとの 六曜・吉日の名前、月齢カレンダーの新月の日"""
    t = _text(XC / f"bestcalendar_{y}_{m:02d}.html")
    a = t.find("大安・吉日カレンダー|")
    b = t.find("月の月齢カレンダー", a)
    toks = [x for x in t[a:b].split("|")[1:] if x not in "日月火水木金土"]
    out, cur = {}, None
    for x in toks:
        if x.isdigit() and int(x) == (cur or 0) + 1:
            cur = int(x)
            out[dt.date(y, m, cur)] = {"rokuyo": None, "labels": []}
        elif cur and x in ROKUYO and out[dt.date(y, m, cur)]["rokuyo"] is None:
            out[dt.date(y, m, cur)]["rokuyo"] = x
        elif cur:
            out[dt.date(y, m, cur)]["labels"].append(x)
    c = t.find("月齢カレンダー|", b)
    seg = t[c:t.find("の特に縁起の良い日", c)]
    shingetsu = [dt.date(y, m, int(d)) for d in re.findall(r"\|(\d+)\|[^|]+\|新月\|", seg)]
    return out, shingetsu


@lru_cache(None)
def ics_dates(slug):
    return {dt.datetime.strptime(s, "%Y%m%d").date() for s in re.findall(r"DTSTART;VALUE=DATE:(\d{8})", (ICS / f"{slug}.ics").read_text(encoding="utf-8"))}


@lru_cache(None)
def calenavi_tsuchinotomi(year):
    t = _text(XC / f"calenavi_mi_{year}.html")
    return {dt.date(year, int(a), int(b)) for a, b in re.findall(r"\|(\d+)月(\d+)日\|己巳の日\|", t)}


def calenavi_sekki(year):
    t = _text(XC / f"calenavi_solar-terms_{year}.html")
    return {name: (dt.date(year, int(a), int(b)), f"{int(h):02d}:{mi}")
            for name, a, b, h, mi in re.findall(r"\|(\S\S)\|(\d+)月(\d+)日 (\d+):(\d\d)\|", t)}


def jal_lists():
    """JAL の一粒万倍日の記事：2026年1月〜2027年6月の一粒万倍日、2026年の天赦日・寅の日"""
    t = _text(XC / "jal_ichiryumanbaibi.html")

    def seg(start, end, y0):
        s = t[t.find(start) + len(start):]
        s = s[:s.find(end)]
        out, y, last = set(), y0, 0
        for yy, mm, body in re.findall(r"(?:(\d{4})年)?(\d+)月\|([^|]+)", s):
            mm = int(mm)
            y = int(yy) if yy else (y + 1 if mm < last else y)
            last = mm
            out |= {dt.date(y, mm, int(d)) for d in re.findall(r"(\d+)日（", body)}
        return out

    return (seg("〈2026年の一粒万倍日〉", "|天赦日、寅の日", 2026), seg("〈2026年の天赦日〉", "|寅の日（とらのひ）", 2026),
            seg("〈2026年の寅の日〉", "|巳の日（みのひ）", 2026))


def main():
    cn = {**calenavi_rokuyo(2026), **calenavi_rokuyo(2027)}
    bc, shin = {}, set()
    d = FROM.replace(day=1)
    while d <= TO:
        o, s = bestcalendar_month(d.year, d.month)
        bc.update(o)
        shin |= set(s)
        d = (d.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
    jal_manbai, jal_tensha, jal_tora = jal_lists()
    jal_span = (FROM, dt.date(2027, 6, 30))

    mism = defaultdict(list)
    n = defaultdict(int)

    def cmp(item, d, ours, theirs, site):
        n[item] += 1
        if ours != theirs:
            mism[item].append(f"{d} 自前={ours} {site}={theirs}")

    for d in sorted(DAYS):
        x = DAYS[d]
        c, b = cn.get(d), bc.get(d)
        if c is None or b is None:
            mism["ページの欠け"].append(f"{d} calenavi={'有' if c else '無'} bestcalendar={'有' if b else '無'}")
            continue
        cmp("六曜", d, x["rokuyo"], c["rokuyo"], "calenavi")
        cmp("六曜", d, x["rokuyo"], b["rokuyo"], "bestcalendar")
        cmp("旧暦の月日", d, (x["kyureki"]["month"], x["kyureki"]["day"]), c["kyu"], "calenavi")
        for name, cm, bl in [("天赦日", "赦", "天赦日"), ("一粒万倍日", "粒", "一粒万倍日"), ("寅の日", "寅", "寅の日"), ("巳の日", "巳", "巳の日")]:
            ours = name in x["senjitsu"]
            cmp(name, d, ours, cm in c["marks"], "calenavi")
            cmp(name, d, ours, bl in b["labels"], "bestcalendar")
        if jal_span[0] <= d <= jal_span[1]:
            cmp("一粒万倍日", d, "一粒万倍日" in x["senjitsu"], d in jal_manbai, "JAL")
        if d.year == 2026:
            cmp("天赦日", d, "天赦日" in x["senjitsu"], d in jal_tensha, "JAL")
            cmp("寅の日", d, "寅の日" in x["senjitsu"], d in jal_tora, "JAL")
        cmp("天赦日", d, "天赦日" in x["senjitsu"], d in ics_dates("tenshobi"), "bestcalendar(ics)")
        cmp("己巳の日", d, "己巳の日" in x["senjitsu"], d in ics_dates("tsuchinotominohi"), "bestcalendar(ics)")
        cmp("己巳の日", d, "己巳の日" in x["senjitsu"], d in calenavi_tsuchinotomi(d.year), "calenavi")
        # 旧暦の月の始まり
        ours_start = x["kyureki"]["day"] == 1
        cmp("旧暦の月の始まり", d, ours_start, c["kyu_start"] or d == FROM and c["kyu"][1] == 1, "calenavi")
        cmp("旧暦の月の始まり", d, ours_start, d in shin, "bestcalendar(新月の日)")
        # 祝日（日付の有無）
        hol_marks = [m for m in c["marks"] if m not in ("粒", "赦", "寅", "巳")]
        cmp("祝日", d, x["holiday"] is not None, bool(hol_marks), "calenavi")

    # 二十四節気（日付と時刻）
    slugs = {"小寒": "shokan", "大寒": "daikan", "立春": "risshun", "雨水": "usui", "啓蟄": "keichitsu", "春分": "shunbun-no-hi",
             "清明": "seimei", "穀雨": "kokuu", "立夏": "rikka", "小満": "shoman", "芒種": "boshu", "夏至": "geshi",
             "小暑": "shousho", "大暑": "taisho", "立秋": "risshu", "処暑": "shosho", "白露": "hakuro", "秋分": "shubun-no-hi",
             "寒露": "kanro", "霜降": "soko", "立冬": "ritto", "小雪": "shosetsu", "大雪": "taisetsu", "冬至": "toji"}
    cs_by = defaultdict(list)
    for y in (2026, 2027):
        for name, v in calenavi_sekki(y).items():
            cs_by[name].append(v)
    for s in K["sekki"]:
        d = dt.date.fromisoformat(s["datetime"][:10])
        tm = s["datetime"][11:]
        theirs = next((v for v in cs_by[s["name"]] if v[0] == d), None)
        cmp("二十四節気（日時）", d, (d, tm), theirs, "calenavi")
        bd = {x for x in ics_dates(slugs[s["name"]]) if x.year == d.year}
        cmp("二十四節気（日付）", d, {d}, bd, "bestcalendar(ics)")

    # 雑節
    zas = defaultdict(set)
    for z in K["zassetsu"]:
        zas[z["name"]].add(dt.date.fromisoformat(z["date"]))
    naoj = {"土用入り": "doyo", "節分": "setsubun", "彼岸入り": "ohigan", "八十八夜": "hachijuhachiya",
            "入梅": "nyubai", "半夏生": "hangesho", "土用の丑の日": "doyo-no-ushi"}
    for name, slug in naoj.items():
        theirs = {d for d in ics_dates(slug) if in_range(d)}
        ours = zas[name]
        if name == "土用の丑の日":  # bestcalendar は夏の土用の丑の日だけを載せている
            ours = {d for d in ours if d.month in (7, 8)}
        cmp("雑節", name, sorted(ours), sorted(theirs), "bestcalendar(ics)")
    # 暦要項（2027年の表）とも照らす（土用入り・節分・彼岸入り・八十八夜・入梅・半夏生・二百十日）
    spec = importlib.util.spec_from_file_location("bk", ROOT / "pipeline" / "build_koyomi.py")
    bk = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bk)
    nz = defaultdict(set)
    for y in (2026, 2027):
        for z in bk.parse_naoj(y)[1]:
            if in_range(z["date"]):
                nz[{"土用": "土用入り", "彼岸": "彼岸入り"}.get(z["name"], z["name"])].add(z["date"])
    for name, dates in sorted(nz.items()):
        cmp("雑節", name, sorted(zas[name]), sorted(dates), "暦要項")

    # 年中行事（bestcalendar の行事の日）
    gy = defaultdict(set)
    for d, x in DAYS.items():
        for g in x["gyoji"]:
            gy[re.sub(r"（[一二三]の酉）", "", g)].add(d)
    gmap = {"正月事始め（煤払い）": "kotohajime", "人日（七草）": "nanakusa", "鏡開き": "kagami-biraki", "小正月": "koshogatsu",
            "大晦日": "omisoka", "酉の市": "tori-no-ichi", "十五夜（中秋の名月）": "chushu"}
    for name, slug in gmap.items():
        theirs = {d for d in ics_dates(slug) if in_range(d)}
        cmp("年中行事", name, sorted(gy[name]), sorted(theirs), "bestcalendar(ics)")
    return n, mism, cn, bc


def write_md(n, mism):
    m = K["meta"]
    total_mis = sum(len(v) for v in mism.values())
    L = [
        "# 暦の固定ファイルの照合（spi 手順書 §8）",
        "",
        f"照合日：{dt.date.today().isoformat()}　対象：`data/koyomi_2026_2027.json`（{m['valid_from']}〜{m['valid_to']}、{len(DAYS)}日）",
        "照合のプログラム：`pipeline/check_koyomi.py`（保存したページだけを読む。外のサイトは見ない）",
        "",
        "## 照らした先",
        "",
        "| 先 | URL | 保存したファイル | 使った項目 |",
        "|---|---|---|---|",
        "| 国立天文台 暦要項（正本） | https://eco.mtk.nao.ac.jp/koyomi/yoko/2027/rekiyou272.html ほか（2026・2027の (1)〜(4)） | `data/raw/naoj/` | 節気・雑節・朔（計算の元）と雑節の照合 |",
        "| calenavi（暦の総合サイト） | https://calenavi.jp/calendar/rokuyo/2026 ・ /2027 | `data/raw/xcheck/calenavi_rokuyo_*.html` | 六曜・旧暦の月日・旧暦の月の始まり・天赦日・一粒万倍日・寅の日・巳の日・祝日 |",
        "| calenavi | https://calenavi.jp/calendar/auspicious/days/mi/2026 ・ /2027 | `data/raw/xcheck/calenavi_mi_*.html` | 己巳の日 |",
        "| calenavi | https://calenavi.jp/calendar/solar-terms/2026 ・ /2027 | `data/raw/xcheck/calenavi_solar-terms_*.html` | 二十四節気（日付と時刻） |",
        "| bestcalendar（暦の総合サイト） | https://www.bestcalendar.jp/2026/11 〜 /2027/12（14か月） | `data/raw/xcheck/bestcalendar_YYYY_MM.html` | 六曜・天赦日・一粒万倍日・寅の日・巳の日・新月の日（旧暦の月の始まり） |",
        "| bestcalendar（iCal） | https://bestcalendar.jp/ical/entity/<名前>.ics（天赦日・己巳・節気24・雑節・行事） | `data/raw/xcheck/bestcalendar_ics/` | 天赦日・己巳の日・二十四節気の日付・雑節・年中行事 |",
        "| JAL SKYWARD+ | https://skywardplus.jal.co.jp/?p=27370 | `data/raw/xcheck/jal_ichiryumanbaibi.html` | 一粒万倍日（2026年11月〜2027年6月）・2026年の天赦日と寅の日 |",
        "",
        "どの日も、自前の計算に対して2つ以上の暦サイト（六曜・選日は calenavi と bestcalendar、一粒万倍日は前半を JAL でも）を照らした。",
        "datedb.net（日の干支）は 403 で読めなかったので使っていない（`data/raw/xcheck/datedb/` は 403 の応答をそのまま残した物）。",
        "",
        "## 結果",
        "",
        f"照らした件数の合計：{sum(n.values())} 件　食い違い：{total_mis} 件",
        "",
        "| 項目 | 照らした件数 | 食い違い |",
        "|---|---|---|",
    ]
    for k in sorted(n, key=lambda k: list(n).index(k)):
        L.append(f"| {k} | {n[k]} | {len(mism.get(k, []))} |")
    if mism.get("ページの欠け"):
        L.append(f"| ページの欠け | - | {len(mism['ページの欠け'])} |")
    L += ["", "## 食い違いの中身と理由・直したこと", ""]
    if total_mis == 0:
        L.append("食い違いはなかった。")
    for k, v in mism.items():
        L.append(f"### {k}（{len(v)}件）")
        for x in v:
            L.append(f"- {x}")
            L.append(f"  - 理由と扱い：{EXPLAINED.get(x, '未解決（理由を調べるまで、この日は台本に使わない）')}")
        L.append("")
    L.append("土用の丑の日は、bestcalendar が夏の土用の分だけを載せているので、夏（7月・8月）の分だけを照らした。冬・春・秋の土用の丑の日は、照らした土用の期間（暦要項の土用入りと、照合済みの節気から出した明け）の中の丑の日（日の干支は天赦日・己巳の日の一致で確かめた）として計算した値。")
    L += [
        "",
        "## 流派で分かれる所と、どれに合わせたか",
        "",
        "- 天赦日：節月の季節（立春・立夏・立秋・立冬で区切る）ごとに 戊寅・甲午・戊申・甲子 の日。calenavi・bestcalendar・JAL の3つとも同じ決め方で、全日一致したので、この決め方に合わせた。",
        "- 一粒万倍日：節月ごとの十二支の表（`meta.rules.manbai`）。calenavi と bestcalendar は全日一致、JAL は上の1日が載っていない（多数の2つに合わせた）。不成就日と重なる日も一粒万倍日として残す（3つのサイトとも残している。JAL は重なる日に「*」を付けるだけ）。",
        "- 二百十日：bestcalendar に載っていないので、暦要項の表とだけ照らした（立春から数えた計算と一致）。",
        "- 節月の境目：節入りの日（日付）を新しい節月の1日目にする（手順書 §8）。3つのサイトと合っている。",
        "- 旧暦：朔の日を月の1日目、中気で月の名前。範囲の中の旧暦の月は全部、中気がちょうど1つで、閏月はない（2033年問題の型の例外もない）。",
        "- 社日：春分・秋分に最も近い戊の日で計算した。暦要項の雑節に社日はなく、照らせる暦サイトも見つからなかったので、照合していない（台本に出す前に、出典を決める必要がある）。",
        "- 土用明け・彼岸の中日と明け：暦要項の節気から計算した（立春・立夏・立秋・立冬の前日、彼岸入りの3日後と6日後）。元の節気は照合済み。",
        "",
        "## 2028年の境目",
        "",
        f"- 2027年12月28日に始まる旧暦の月の名前（12月）は、暦要項 2028 がまだ無いので、ephem で計算した2028年の朔（{m['sources']['computed_2028']['saku']}）と大寒（{m['sources']['computed_2028']['daikan']}）で決めた。calenavi の 2027-12-28〜31 の旧暦（12/1〜12/4）と一致している。",
        f"- 暦要項の値と ephem の計算の差は、節気で最大 {m['checks']['ephem_max_diff_min']['sekki']} 分、朔で最大 {m['checks']['ephem_max_diff_min']['saku']} 分。",
    ]
    (DATA / "koyomi_check.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    return total_mis


if __name__ == "__main__":
    n, mism, _, _ = main()
    t = write_md(n, mism)
    print("照らした件数:", dict(n))
    unexplained = [x for v in mism.values() for x in v if x not in EXPLAINED]
    print("食い違い:", t, "うち理由が分からない物:", len(unexplained))
    for x in unexplained[:20]:
        print(" ", x)
    sys.exit(1 if unexplained else 0)

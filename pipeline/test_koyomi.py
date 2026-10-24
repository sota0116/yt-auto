# 暦の計算の単体テスト（spi 手順書 §8「過去の分かっている天赦日・一粒万倍日で試す仕組み」）
#   python -X utf8 -m pytest pipeline\test_koyomi.py
# ・答えは記憶ではなく、保存した暦サイトのページから写した値。出典は各テストのコメントに書く
# ・過去の日（2026年2月〜10月）を、2026・2027年の暦要項だけから計算して照らす
import datetime as dt
import html
import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_koyomi as bk  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
D = dt.date


@pytest.fixture(scope="module")
def ctx():
    s26, _, k26 = bk.parse_naoj(2026)
    s27, _, k27 = bk.parse_naoj(2027)
    saku = sorted(k.date() for k in k26 + k27)
    chuki = [(s["dt"].date(), s["deg"]) for s in s26 + s27 if s["deg"] % 30 == 0]
    setsu = [(s["dt"].date(), s["deg"]) for s in s26 + s27 if s["deg"] % 30 == 15]
    months = bk.lunar_months(saku, chuki, D(2026, 1, 19))
    return lambda d: bk.day_fields(d, setsu, months)


def _all_days(start, end):
    d = start
    while d <= end:
        yield d
        d += dt.timedelta(days=1)


def test_tensha_2026(ctx):
    # 出典：bestcalendar の天赦日の iCal https://bestcalendar.jp/ical/entity/tenshobi.ics（data/raw/xcheck/bestcalendar_ics/tenshobi.ics）
    #       JAL SKYWARD+ https://skywardplus.jal.co.jp/?p=27370 の〈2026年の天赦日〉（data/raw/xcheck/jal_ichiryumanbaibi.html）
    #       どちらも 2026年 3月5日・5月4日・5月20日・7月19日・10月1日
    want = {D(2026, 3, 5), D(2026, 5, 4), D(2026, 5, 20), D(2026, 7, 19), D(2026, 10, 1)}
    got = {d for d in _all_days(D(2026, 2, 1), D(2026, 10, 31)) if "天赦日" in ctx(d)["senjitsu"]}
    assert got == want


def test_manbai_2026(ctx):
    # 出典：bestcalendar の一粒万倍日の iCal https://bestcalendar.jp/ical/entity/ichiryumanbaibi.ics
    #       （data/raw/xcheck/bestcalendar_ics/ichiryumanbaibi.ics）の 2026年2月〜10月。
    #       calenavi https://calenavi.jp/calendar/rokuyo/2026 の「粒」の印（data/raw/xcheck/calenavi_rokuyo_2026.html）とも同じ
    want = {
        2: [8, 13, 20, 25],
        3: [4, 5, 12, 17, 24, 29],
        4: [8, 11, 20, 23],
        5: [2, 5, 6, 17, 18, 29, 30],
        6: [12, 13, 24, 25],
        7: [6, 7, 10, 19, 22, 31],
        8: [3, 13, 18, 25, 30],
        9: [6, 7, 14, 19, 26],
        10: [1, 11, 14, 23, 26],
    }
    want = {D(2026, m, x) for m, xs in want.items() for x in xs}
    got = {d for d in _all_days(D(2026, 2, 1), D(2026, 10, 31)) if "一粒万倍日" in ctx(d)["senjitsu"]}
    assert got == want


def test_tora_2026(ctx):
    # 出典：JAL SKYWARD+ https://skywardplus.jal.co.jp/?p=27370 の〈2026年の寅の日〉（data/raw/xcheck/jal_ichiryumanbaibi.html）の 2026年10月
    #       10月7日・19日・31日
    got = [d.day for d in _all_days(D(2026, 10, 1), D(2026, 10, 31)) if "寅の日" in ctx(d)["senjitsu"]]
    assert got == [7, 19, 31]


def test_tsuchinotomi_2026(ctx):
    # 出典：calenavi https://calenavi.jp/calendar/auspicious/days/mi/2026（data/raw/xcheck/calenavi_mi_2026.html）
    #       bestcalendar https://bestcalendar.jp/ical/entity/tsuchinotominohi.ics
    #       2026年の己巳の日 2月24日・4月25日・6月24日・8月23日・10月22日
    want = {D(2026, 2, 24), D(2026, 4, 25), D(2026, 6, 24), D(2026, 8, 23), D(2026, 10, 22)}
    got = {d for d in _all_days(D(2026, 2, 1), D(2026, 10, 31)) if "己巳の日" in ctx(d)["senjitsu"]}
    assert got == want
    assert all(bk.kanshi(d) == "己巳" for d in want)


@pytest.mark.parametrize("d,month,day,rokuyo", [
    # 出典：calenavi https://calenavi.jp/calendar/rokuyo/2026（data/raw/xcheck/calenavi_rokuyo_2026.html）の
    #       旧暦の月の切り替わり日（「旧 m/1」の印）と六曜
    (D(2026, 2, 17), 1, 1, "先勝"),
    (D(2026, 3, 19), 2, 1, "友引"),
    (D(2026, 4, 17), 3, 1, "先負"),
    (D(2026, 5, 17), 4, 1, "仏滅"),
    (D(2026, 6, 15), 5, 1, "大安"),
    (D(2026, 7, 14), 6, 1, "赤口"),
    (D(2026, 8, 13), 7, 1, "先勝"),
    (D(2026, 9, 11), 8, 1, "友引"),
    (D(2026, 10, 11), 9, 1, "先負"),
])
def test_kyureki_month_start_and_rokuyo(ctx, d, month, day, rokuyo):
    f = ctx(d)
    assert (f["kyureki"]["month"], f["kyureki"]["day"], f["kyureki"]["leap"]) == (month, day, False)
    assert f["rokuyo"] == rokuyo


def test_rokuyo_and_kyureki_every_day_feb_to_oct_2026(ctx):
    # 出典：calenavi https://calenavi.jp/calendar/rokuyo/2026（data/raw/xcheck/calenavi_rokuyo_2026.html）の
    #       2026年2月〜10月の毎日の六曜と旧暦の月日（ページの表をそのまま読んで照らす）
    import check_koyomi as ck
    cn = ck.calenavi_rokuyo(2026)
    for d in _all_days(D(2026, 2, 1), D(2026, 10, 31)):
        f = ctx(d)
        assert f["rokuyo"] == cn[d]["rokuyo"], d
        assert (f["kyureki"]["month"], f["kyureki"]["day"]) == cn[d]["kyu"], d


def test_kanshi_known_days():
    # 出典：bestcalendar https://bestcalendar.jp/koyomi/tsuchinotominohi（data/raw/xcheck/bestcalendar_koyomi_tsuchinotominohi.html）
    #       「2026年12月21日（月）の暦 … 日の干支 己巳」
    assert bk.kanshi(D(2026, 12, 21)) == "己巳"
    # 出典：bestcalendar の天赦日の iCal（上と同じ）2027年7月14日が天赦日。夏（節月4〜6）の天赦日は甲午の日
    assert bk.kanshi(D(2027, 7, 14)) == "甲午"


def test_no_leap_and_one_chuki_check():
    # 2033年問題の型（中気が0か2の月）が出たら止まることを、作った値で確かめる
    saku = [D(2030, 1, 1), D(2030, 1, 30), D(2030, 3, 1)]
    with pytest.raises(SystemExit):
        bk.lunar_months(saku, [(D(2030, 1, 5), 300), (D(2030, 1, 25), 330)], D(2030, 1, 1))
    with pytest.raises(SystemExit):
        bk.lunar_months(saku, [(D(2030, 2, 10), 330)], D(2030, 1, 1))


def test_fixed_file():
    # 固定ファイルの中身：範囲・閏月なし・最強開運日が天赦日と一粒万倍日の重なりだけか
    k = json.loads((ROOT / "data" / "koyomi_2026_2027.json").read_text(encoding="utf-8"))
    assert (k["meta"]["valid_from"], k["meta"]["valid_to"]) == ("2026-11-01", "2027-12-31")
    assert len(k["days"]) == 426
    assert not any(d["kyureki"]["leap"] for d in k["days"])
    both = [d["date"] for d in k["days"] if {"天赦日", "一粒万倍日"} <= set(d["senjitsu"])]
    assert k["meta"]["saikyo_kaiun"] == both
    # 出典：calenavi https://calenavi.jp/calendar/rokuyo/2027 の「赦」と「粒」が同じ日に付いている日
    #       （2027年7月14日・9月26日・12月11日）と、bestcalendar の月のページ 2026年12月16日（一粒万倍日・天赦日）
    assert both == ["2026-12-16", "2027-07-14", "2027-09-26", "2027-12-11"]


def _plain(path):
    if path.suffix == ".pdf":
        import subprocess
        t = subprocess.run(["pdftotext", "-enc", "UTF-8", str(path), "-"], capture_output=True).stdout.decode("utf-8")
    else:
        t = path.read_bytes().decode("utf-8")
        t = re.sub(r"<script.*?</script>", "", t, flags=re.S)
        t = html.unescape(re.sub(r"<[^>]+>", " ", t))
    return re.sub(r"\s+", "", t)


def test_gyoji_quotes_in_sources():
    # data/gyoji.json の quote が、保存した出典の本文に本当にあるか（空白は無視、「…」は省略の印）
    g = json.loads((ROOT / "data" / "gyoji.json").read_text(encoding="utf-8"))
    cache = {}
    for e in g["events"]:
        for s in e["sources"]:
            p = ROOT / s["file"]
            body = cache.setdefault(p, _plain(p))
            for part in s["quote"].split("…"):
                assert re.sub(r"\s+", "", part) in body, (e["name"], s["file"], part)

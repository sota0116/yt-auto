# 仕事チャンネルの段階Aのデータ（手順書 §3 型A・§8、編集方針の出典の決まり）
#   python -X utf8 pipeline\fetch_job_data.py           … 取って data\job\ に保存
#   python -X utf8 pipeline\fetch_job_data.py --verify  … 読み方の確かめ（令和5年の Excel と API の DB を全件照らす）
# ・取る物：賃金構造基本統計調査 令和7年 職種（小分類）第1表、雇用動向調査 令和7年 参考表1（産業別の離職率）
# ・e-Stat のカタログ API で表の場所を引き、Excel を data\raw\estat\ に保存する（API の DB は2023年分までのため）
# ・年収＝きまって支給する現金給与額×12＋年間賞与その他特別給与額。時給に直した額＝年収÷（月の労働時間×12）
#   月の労働時間＝所定内実労働時間数＋超過実労働時間数。計算はここだけでやり、台本と特典はこの値を読む
import argparse, datetime, hashlib, json, os, sys
import openpyxl, requests, xlrd

sys.path.insert(0, os.path.dirname(__file__))
import estat

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "raw", "estat")
OUT = os.path.join(ROOT, "data", "job")
DL = "https://www.e-stat.go.jp/stat-search/file-download?&statInfId={}&fileKind=4"

CHINKIN = "00450091"
KOYO = "00450073"
FIELDS = ["年齢", "勤続年数", "所定内実労働時間数", "超過実労働時間数",
          "きまって支給する現金給与額", "所定内給与額", "年間賞与その他特別給与額", "労働者数"]
UNITS = ["歳", "年", "時間", "時間", "千円", "千円", "千円", "十人"]

# 主な職業40（特典の表と A-4 の候補の母集団）。選び方：
#  ①手順書 §8 のネタ帳（型A・C）に出る職業は全部入れる（15）
#  ②残りは、よく調べられる職業と働く人の多い職業から、大分類が偏らないよう本人の設計に沿って選んだ（25）
#  「その他の〜」「他に分類されない〜」は、何の仕事か伝わらないので入れない
MAIN40 = [
    # ① ネタ帳
    ("介護職員（医療・福祉施設等）", "介護職員（施設）"),
    ("保育士", "保育士"),
    ("薬剤師", "薬剤師"),
    ("建築技術者", "建築技術者（設計・施工管理）"),
    ("土木技術者", "土木技術者（設計・施工管理）"),
    ("飲食物調理従事者", "調理人"),
    ("タクシー運転者", "タクシー運転手"),
    ("ソフトウェア作成者", "プログラマー（ソフトウェア作成者）"),
    ("システムコンサルタント・設計者", "システムエンジニア（設計者）"),
    ("営業用大型貨物自動車運転者", "大型トラック運転手"),
    ("看護師", "看護師"),
    ("警備員", "警備員"),
    ("電気工事従事者", "電気工事士"),
    ("自動車整備・修理従事者", "自動車整備士"),
    ("大工", "大工"),
    # ② よく調べられる・働く人が多い
    ("医師", "医師"),
    ("歯科医師", "歯科医師"),
    ("航空機操縦士", "パイロット"),
    ("航空機客室乗務員", "客室乗務員（CA）"),
    ("大学教授（高専含む）", "大学教授"),
    ("小・中学校教員", "小・中学校の先生"),
    ("高等学校教員", "高校の先生"),
    ("幼稚園教員，保育教諭", "幼稚園の先生・保育教諭"),
    ("理学療法士，作業療法士，言語聴覚士，視能訓練士", "理学療法士など（リハビリ職）"),
    ("歯科衛生士", "歯科衛生士"),
    ("臨床検査技師", "臨床検査技師"),
    ("介護支援専門員（ケアマネージャー）", "ケアマネージャー"),
    ("訪問介護従事者", "訪問介護員（ヘルパー）"),
    ("総合事務員", "一般事務（総合事務員）"),
    ("販売店員", "販売店員"),
    ("機械器具・通信・システム営業職業従事者（自動車を除く）", "機械・通信・システムの営業"),
    ("保険営業職業従事者", "保険の営業"),
    ("金融営業職業従事者", "銀行・証券の営業"),
    ("理容・美容師", "美容師・理容師"),
    ("飲食物給仕従事者", "ホール係（飲食物給仕）"),
    ("バス運転者", "バス運転手"),
    ("鉄道運転従事者", "電車の運転士"),
    ("公認会計士，税理士", "公認会計士・税理士"),
    ("管理的職業従事者", "管理職"),
    ("デザイナー", "デザイナー"),
]


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


def find_file(stats_code, dataset_has, table_prefix):
    """カタログ API で、データセット名に dataset_has を含み、表名が table_prefix で始まる Excel を1つ探す"""
    start = 1
    while True:
        d = estat.call("getDataCatalog", statsCode=stats_code, limit=100, startPosition=start)
        r = d["GET_DATA_CATALOG"]
        ds = r.get("DATA_CATALOG_LIST_INF", {}).get("DATA_CATALOG_INF", [])
        ds = [ds] if isinstance(ds, dict) else ds
        for x in ds:
            dname = x["DATASET"]["TITLE"].get("NAME", "")
            if not all(w in dname for w in dataset_has):
                continue
            res = x["RESOURCES"]["RESOURCE"]
            res = [res] if isinstance(res, dict) else res
            for rr in res:
                if rr["TITLE"].get("NAME", "").startswith(table_prefix) and rr.get("FORMAT", "").startswith("XLS"):
                    sid = rr["URL"].split("statInfId=")[1][:12]
                    return {"statInfId": sid, "dataset": dname, "table": rr["TITLE"]["NAME"],
                            "release_date": rr.get("RELEASE_DATE"), "landing_page": x["DATASET"].get("LANDING_PAGE"),
                            "url": DL.format(sid), "licence": rr.get("RESOURCE_LICENCE_ID")}
        nxt = r.get("DATA_CATALOG_LIST_INF", {}).get("RESULT_INF", {}).get("NEXT_KEY")
        if not nxt:
            sys.exit(f"【止まりました】e-Stat に表が見つかりません：{dataset_has} {table_prefix}")
        start = nxt


def download(info, name):
    os.makedirs(RAW, exist_ok=True)
    path = os.path.join(RAW, name)
    r = requests.get(info["url"], timeout=120)
    if r.status_code != 200 or len(r.content) < 1000:
        sys.exit(f"【止まりました】{name} を取れませんでした（{r.status_code}）")
    with open(path, "wb") as f:
        f.write(r.content)
    info.update(file=os.path.relpath(path, ROOT).replace("\\", "/"), sha256=sha256(path),
                fetched=datetime.date.today().isoformat())
    return path


def num(v):
    if isinstance(v, (int, float)):
        return v
    return None  # 「－」「…」など、値のない欄


def parse_chinkin(path):
    """第1表（企業規模計の8列）を {性: {職種名: {項目: 値}}} にする"""
    ws = openpyxl.load_workbook(path, data_only=True).worksheets[0]
    out, sec = {}, None
    for row in ws.iter_rows(min_row=1, values_only=True):
        a = row[1] if len(row) > 1 else None
        if not isinstance(a, str) or num(row[3]) is None and row[3] is None:
            continue
        name = a
        if "\n" in a:
            head = a.split("\n")[0].strip()
            if head in ("男女計", "男", "女"):
                sec = head
            name = a.split("\n")[-1]
        name = name.strip()
        if sec is None or not name:
            continue
        vals = [num(v) for v in row[3:11]]
        out.setdefault(sec, {})[name] = dict(zip(FIELDS, vals))
    return out


def derive(v):
    k, b, h1, h2 = v["きまって支給する現金給与額"], v["年間賞与その他特別給与額"], v["所定内実労働時間数"], v["超過実労働時間数"]
    if None in (k, b, h1, h2):
        return {}
    nensyu = k * 12 + b  # 千円
    hours = h1 + h2
    return {"年収_千円": round(nensyu, 1), "月の労働時間": hours,
            "時給に直した額_円": round(nensyu * 1000 / (hours * 12))}


def parse_koyo(path):
    """参考表1 の男女計・男・女の『計（ＧＴ）』と産業（大分類）の行"""
    ws = xlrd.open_workbook(path).sheets()[0]
    cols = ["1月1日現在の常用労働者数_千人", "入職者数_千人", "転職入職者数_千人", "未就業入職者数_千人", "離職者数_千人",
            "延労働移動者数_千人", "入職率", "転職入職率", "未就業入職率", "離職率", "延労働移動率", "入職超過率"]
    out, sec = {}, None
    for i in range(ws.nrows):
        r = ws.row_values(i)
        a = str(r[1]).strip() if len(r) > 1 else ""
        b = str(r[2]).strip() if len(r) > 2 else ""
        for s in ("男女計", "男", "女"):
            if a.startswith(s + "\n") or a == s:
                sec = s
        vals = [v for v in r[3:] if v != ""]
        if sec is None or len(vals) < 12:
            continue
        if b == "計" and a.startswith(sec):
            out.setdefault(sec, {})["産業計"] = dict(zip(cols, vals[:12]))
        elif len(a) == 1 and b:  # 産業の記号（Ｃ〜Ｒ）の行
            out.setdefault(sec, {})[b] = dict(zip(cols, vals[:12]), 記号=a)
        if len(out.get("女", {})) >= 17:
            break
    return out


def run():
    os.makedirs(OUT, exist_ok=True)
    src = {}
    ci = find_file(CHINKIN, ["令和７年", "一般労働者", "職種"], "1_職種（小分類）別きまって支給する現金給与額")
    cp = download(ci, "chinkin_r7_shokushu_shobunrui.xlsx")
    src["chinkin_r7_shokushu"] = ci
    ki = find_file(KOYO, ["参考表", "2025年"], "1_就業形態、性、企業規模")
    kp = download(ki, "koyodoko_r7_sanko1_sangyo_idoritsu.xls")
    src["koyodoko_r7_sanko1"] = ki

    ch = parse_chinkin(cp)
    n = {s: len(v) for s, v in ch.items()}
    if n.get("男女計") != 145:
        sys.exit(f"【止まりました】職種の数が想定（145）と違います：{n}")
    for sec in ch.values():
        for name, v in sec.items():
            v.update(derive(v))
    ko = parse_koyo(kp)
    if len(ko.get("男女計", {})) != 17:
        sys.exit(f"【止まりました】産業の数が想定（16＋計）と違います：{ {s: len(v) for s, v in ko.items()} }")

    missing = [m for m, _ in MAIN40 if m not in ch["男女計"]]
    if missing or len(MAIN40) != 40:
        sys.exit(f"【止まりました】主な職業40の名前が表にありません：{missing}")
    main = []
    for official, short in MAIN40:
        v = ch["男女計"][official]
        main.append({"職種": official, "表示名": short, **{k: v[k] for k in
                     ["年収_千円", "月の労働時間", "時給に直した額_円", "年齢", "勤続年数", "労働者数"]}})
    by_n = sorted(main, key=lambda x: -x["年収_千円"])
    for i, x in enumerate(by_n, 1):
        x["年収の順位"] = i
    by_h = sorted(main, key=lambda x: -x["時給に直した額_円"])
    for i, x in enumerate(by_h, 1):
        x["時給の順位"] = i

    common = {"e_stat_note": estat.NOTE, "加工": "e-Stat の表をもとに、このチャンネルが加工して作成",
              "年収の定義": "きまって支給する現金給与額×12＋年間賞与その他特別給与額（令和7年の調査。賞与は前の年1年分）",
              "時給の定義": "年収÷（所定内実労働時間数＋超過実労働時間数）÷12",
              "対象": "一般労働者（短時間労働者を除く）・企業規模10人以上・男女計。公務（役所）は調査の対象外"}
    json.dump({"meta": {**common, "source": "chinkin_r7_shokushu", "単位": dict(zip(FIELDS, UNITS))}, "data": ch},
              open(os.path.join(OUT, "shokushu_r7.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump({"meta": {**common, "source": "koyodoko_r7_sanko1",
                        "注意": "離職率は産業の数字。職業の離職率として言わない（手順書 §3）",
                        "単位": "率は%、人数は千人"}, "data": ko},
              open(os.path.join(OUT, "rishoku_sangyo_r7.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump({"meta": {**common, "選び方": "ネタ帳（手順書 §8 型A・C）の15職業＋よく調べられる職業・働く人の多い職業25。"
                        "「その他の〜」「他に分類されない〜」は入れない", "source": "chinkin_r7_shokushu"},
               "data": by_n}, open(os.path.join(OUT, "main40_r7.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    # 出典と照合用のハッシュ（手順書 §8・設計書 §4）
    sp = os.path.join(ROOT, "data", "sources.json")
    sources = json.load(open(sp, encoding="utf-8")) if os.path.exists(sp) else {}
    sources.update(src)
    json.dump(sources, open(sp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    cpth = os.path.join(ROOT, "data", "checksums.json")
    sums = json.load(open(cpth, encoding="utf-8")) if os.path.exists(cpth) else {}
    for k in src.values():
        sums[k["file"]] = k["sha256"]
    for f in ["shokushu_r7.json", "rishoku_sangyo_r7.json", "main40_r7.json"]:
        p = os.path.join(OUT, f)
        sums[os.path.relpath(p, ROOT).replace("\\", "/")] = sha256(p)
    json.dump(sums, open(cpth, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"職種 {n}・産業 {len(ko['男女計'])}・主な職業 {len(main)} を保存しました")


def verify():
    """令和5年の同じ表の Excel を同じ読み方で読み、API の DB（0003426315 の2023年）と全件照らす"""
    info = find_file(CHINKIN, ["令和５年", "一般労働者", "職種"], "1_職種（小分類）別きまって支給する現金給与額")
    path = download(info, "chinkin_r5_shokushu_shobunrui_verify.xlsx")
    ch = parse_chinkin(path)
    meta = estat.call("getMetaInfo", statsDataId="0003426315")["GET_META_INFO"]["METADATA_INF"]["CLASS_INF"]["CLASS_OBJ"]
    cat03 = {c["@code"]: c["@name"].strip() for c in [m for m in meta if m["@id"] == "cat03"][0]["CLASS"]}
    tabs = {"33": "年齢", "34": "勤続年数", "36": "所定内実労働時間数", "38": "超過実労働時間数",
            "40": "きまって支給する現金給与額", "42": "所定内給与額", "44": "年間賞与その他特別給与額", "45": "労働者数"}
    sexes = {"01": "男女計", "02": "男", "03": "女"}
    checked = bad = 0
    for sc, sname in sexes.items():
        d = estat.call("getStatsData", statsDataId="0003426315", cdTime="2023000000", cdCat01="01", cdCat02=sc, limit=100000)
        vals = d["GET_STATS_DATA"]["STATISTICAL_DATA"]["DATA_INF"]["VALUE"]
        for v in vals:
            if v["@tab"] not in tabs:
                continue
            name = cat03.get(v["@cat03"])
            x = ch.get(sname, {}).get(name, {}).get(tabs[v["@tab"]])
            try:
                api = float(v["$"])
            except ValueError:
                api = None
            checked += 1
            if x is None and api is None:
                continue
            if x is None or api is None or abs(float(x) - api) > 1e-6:
                bad += 1
                if bad <= 10:
                    print("違い：", sname, name, tabs[v["@tab"]], "Excel", x, "API", v["$"])
    print(f"照らした数 {checked}・違い {bad}")
    os.remove(path)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--verify", action="store_true")
    a = p.parse_args()
    verify() if a.verify else run()

# 型B「会社の決断の結末」の統計を取る（手順書 §3 型B・§4 特典・§8、編集方針の出典の決まり）
#   python -X utf8 pipeline\fetch_b_data.py   … 取って、原本を data\raw\estat\ に、読んだ値を data\job\b_data.json に保存
# ・取る物（どれも e-Stat のファイル。キーはカタログを引く時だけ estat.py が自分で読む）
#   雇用動向調査 令和7年 第13-2表 転職入職者の年齢別・男女別の賃金変動（特典の表もこれ）
#   雇用動向調査 令和7年 参考表2 年齢別の入職率・転職入職率・離職率
#   雇用動向調査 令和7年 第34-3表 年齢別の離職理由の構成比（経営上の都合など）
#   賃金構造基本統計調査 令和7年 一般労働者 第1表（年齢別の所定内給与・きまって支給・超過実労働時間）・第2表（年齢×勤続年数）
#     ・第3表（年齢別の所定内給与の分布と中位数）・新規学卒者 第1表（初任給）
#   就労条件総合調査 令和7年 労働時間制度 第2表・第3表（週休制の形態）・第4表（年間休日総数）
#   就労条件総合調査 令和4年 賃金制度 第29-2表（基本給の決定要素・管理職以外。この項目は令和4年が最新）
# ・ここでは表の値をそのまま並べるだけ。割合の言い直し・差・合計は b_facts.py で計算する（Claude は計算しない）
# ・data\sources.json と data\checksums.json は、ほかの係も同時に書くので、このプログラムは書き換えない。
#   足す分を data\job\b_sources_new.json に書き出すので、係が読み直してから自分のキーだけを足す
import datetime, json, os, re, sys, unicodedata
import openpyxl, xlrd

sys.path.insert(0, os.path.dirname(__file__))
import estat
from fetch_d_wage30 import estat_file, rel, sha256  # 取り方は型D と同じ（カタログで表の情報を引き、ファイルを落とす）

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "job", "b_data.json")
NEW = os.path.join(ROOT, "data", "job", "b_sources_new.json")
TODAY = datetime.date.today().isoformat()
KOYO, CHIN, SHURO = "00450073", "00450091", "00450099"
MHLW = "厚生労働省"

AGES = ["19歳以下", "20～24歳", "25～29歳", "30～34歳", "35～39歳", "40～44歳", "45～49歳", "50～54歳", "55～59歳",
        "60～64歳", "65歳以上"]


def norm(s):
    """全角の数字・記号をそろえ、空白を除く（「４５～４９歳」→「45～49歳」、「1，000人以上」→「1,000人以上」）"""
    s = unicodedata.normalize("NFKC", str(s if s is not None else ""))
    return re.sub(r"\s", "", s).replace("~", "～")


def fnum(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None  # 「-」「…」など、値のない欄


def zero(v):
    """就労条件総合調査の「-」は該当なし（0）"""
    return 0.0 if norm(v) == "-" else fnum(v)


def age_lab(s):
    """年齢の見出しをそろえる（「～19歳」→「19歳以下」、「70歳～」→「70歳以上」）"""
    s = norm(s)
    s = re.sub(r"^～(\d+)歳$", r"\g<1>歳以下", s)
    return re.sub(r"^(\d+)歳～$", r"\g<1>歳以上", s)


def stop(msg):
    sys.exit(f"【止まりました】{msg}")


def xls_rows(path, sheet=0):
    wb = xlrd.open_workbook(path)
    ws = wb.sheet_by_index(sheet) if isinstance(sheet, int) else wb.sheet_by_name(sheet)
    return [ws.row_values(i) for i in range(ws.nrows)]


def xlsx_rows(path, sheet=0):
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    ws = wb.worksheets[sheet] if isinstance(sheet, int) else wb[sheet]
    return [list(r) for r in ws.iter_rows(values_only=True)]


def cell(rows, i, j):
    return rows[i][j] if i < len(rows) and j < len(rows[i]) else None


def must(rows, i, j, word, name):
    if word not in norm(cell(rows, i, j)):
        stop(f"{name} の {i}行{j}列が「{word}」ではありません（表の形が想定と違います）")


# ---- 1. 雇用動向調査 第13-2表 転職入職者の賃金変動 ----
HENDO = {4: "増加", 5: "1割以上増加", 6: "1割未満増加", 7: "変わらない", 8: "減少", 9: "1割未満減少", 10: "1割以上減少",
         11: "不詳", 12: "3割以上増加", 13: "1割以上3割未満増加", 14: "1割以上3割未満減少", 15: "3割以上減少"}


def hendo(src):
    path, info = estat_file(KOYO, "賃金変動", "000040489954", "b_koyodoko_r7_13-2_chingin_hendo.xls", MHLW, "雇用動向調査")
    rows = xls_rows(path, 0)
    # 最初の塊が「経験1年未満」（入職前1年間に仕事をしていた人＝転職入職者）の（前職）計,（現職）計
    must(rows, 5, 1, "経験1年未満", "第13-2表")
    must(rows, 5, 3, "(前職)計,(現職)計", "第13-2表")
    must(rows, 5, 15, "千人", "第13-2表")
    must(rows, 5, 16, "(前職)計,(現職)計", "第13-2表")
    for c, w in ((4, "増加"), (7, "変わら"), (8, "減少"), (10, "1割以上減少"), (11, "不詳"), (17, "増加"), (21, "減少")):
        must(rows, 7, c, w, "第13-2表")
    out, sex = {}, None
    for i in range(10, 58):
        r = rows[i]
        lab = norm(r[2])
        if norm(r[1]) == "GT":  # 男女計・男・女の塊の頭の行（その性の年齢計）
            sex = {"計": "男女計", "男": "男", "女": "女"}.get(lab)
            lab = "年齢計"
        if sex is None or lab not in ["年齢計"] + AGES + ["59歳以下", "60歳以上"]:
            continue
        rec = {"人数_千人": fnum(r[3])}
        for c, k in HENDO.items():
            rec[k] = fnum(r[c + 13])  # 構成比（%）は人数の列の13列右
            rec[f"{k}_千人"] = fnum(r[c])
        if fnum(r[16]) != 100.0:
            stop(f"第13-2表の {sex} {lab} の構成比の計が100ではありません")
        out.setdefault(sex, {})[lab] = rec
    for s in ("男女計", "男", "女"):
        if s not in out or any(a not in out[s] for a in AGES[1:]):
            stop(f"第13-2表の {s} の年齢の行が足りません")
    info.update(範囲="経験1年未満（入職前1年間に仕事をしていた人＝転職入職者）・前職も現職も計・前職が雇用者・調査時に在籍している人",
                表の中の位置="シート A01302 の最初の塊（（前職）計,（現職）計）。構成比（%）は右半分",
                定義="前職の賃金と比べて、現職の賃金が増えたか減ったか（入職者本人の答え）")
    src["b_koyodoko_r7_13-2"] = info
    return {"source": "b_koyodoko_r7_13-2", "単位": "%（_千人の欄は千人）", "値": out}


# ---- 2. 雇用動向調査 参考表2 年齢別の労働移動率 ----
IDO = {3: "常用労働者数_千人", 4: "入職者数_千人", 5: "転職入職者数_千人", 7: "離職者数_千人",
       9: "入職率", 10: "転職入職率", 12: "離職率"}


def idoritsu(src):
    path, info = estat_file(KOYO, "労働移動率", "000040490249", "b_koyodoko_r7_sanko2_nenrei_idoritsu.xls", MHLW, "雇用動向調査")
    rows = xls_rows(path, 0)
    must(rows, 4, 1, "計", "参考表2")
    must(rows, 5, 10, "転職入職率", "参考表2")
    must(rows, 5, 12, "離職率", "参考表2")
    must(rows, 5, 9, "入職率", "参考表2")
    out = {}
    for i in range(9, 22):  # 計（就業形態計）の男女計
        lab = norm(rows[i][2])
        if lab in AGES or lab in ("60歳以上",):
            out[lab] = {k: fnum(rows[i][c]) for c, k in IDO.items()}
    if any(a not in out for a in AGES[:9]):
        stop("参考表2 の年齢の行が足りません")
    info.update(範囲="就業形態計・男女計・年齢階級別", 表の中の位置="シート 参考表２ の最初の塊（計・ＧＴ）",
                定義="離職率＝1年間の離職者数÷1月1日現在の常用労働者数×100。転職入職率は入職前1年間に仕事をしていた入職者で数えた入職率")
    src["b_koyodoko_r7_sanko2"] = info
    return {"source": "b_koyodoko_r7_sanko2", "単位": "%（_千人の欄は千人）", "値": out}


# ---- 3. 雇用動向調査 第34-3表 離職理由の構成比 ----
RIYU = {4: "契約期間満了", 5: "事業所側の理由", 6: "経営上の都合", 7: "出向", 8: "出向元への復帰", 9: "定年",
        10: "本人の責", 11: "個人的理由", 12: "結婚", 13: "出産・育児", 14: "介護・看護", 15: "その他の個人的理由", 16: "死亡・傷病"}


def riyu(src):
    path, info = estat_file(KOYO, "離職理由", "000040490234", "b_koyodoko_r7_34-3_rishoku_riyu.xls", MHLW, "雇用動向調査")
    rows = xls_rows(path, "A0343B構成比")
    must(rows, 4, 1, "計", "第34-3表")
    must(rows, 4, 16, "%", "第34-3表")
    must(rows, 9, 6, "経営上", "第34-3表")
    must(rows, 7, 9, "定年", "第34-3表")
    must(rows, 7, 11, "個人的理由", "第34-3表")
    out = {}
    for i in range(11, 23):
        lab = norm(rows[i][2]) or norm(rows[i][1])
        lab = "年齢計" if lab == "計" else lab
        if lab == "年齢計" or lab in AGES:
            if fnum(rows[i][3]) != 100.0:
                stop(f"第34-3表の {lab} の計が100ではありません")
            out[lab] = {k: fnum(rows[i][c]) for c, k in RIYU.items()}
    if any(a not in out for a in AGES[1:9]):
        stop("第34-3表の年齢の行が足りません")
    info.update(範囲="就業形態計・雇用形態計・企業規模計・男女計・年齢階級別。離職者の離職理由の構成比", 表の中の位置="シート A0343B構成比 の最初の塊（計）",
                定義="「経営上の都合」は事業所側の理由のうちの1つ（人員整理・希望退職の募集・事業所の閉鎖など）")
    src["b_koyodoko_r7_34-3"] = info
    return {"source": "b_koyodoko_r7_34-3", "単位": "%（離職者を100とした構成比）", "値": out}


# ---- 4. 賃金構造基本統計調査 第1表 年齢階級別 ----
NEN = {0: "年齢", 1: "勤続年数", 2: "所定内実労働時間数", 3: "超過実労働時間数", 4: "きまって支給する現金給与額",
       5: "所定内給与額", 6: "年間賞与その他特別給与額", 7: "労働者数_十人"}
KIBO = {3: "規模計", 11: "1,000人以上", 19: "100～999人", 27: "10～99人"}


def chinkin_nenrei(src):
    path, info = estat_file(CHIN, "きまって支給", "000040420843", "b_chinkin_r7_1_nenrei.xlsx", MHLW, "賃金構造基本統計調査")
    rows = xlsx_rows(path, "産業計")
    must(rows, 6, 3, "産業計", "第1表")
    for c, w in KIBO.items():
        must(rows, 8, c, "企業規模計" if w == "規模計" else w, "第1表")
        must(rows, 9, c + 3, "超過", "第1表")
        must(rows, 9, c + 4, "きまって", "第1表")
        must(rows, 10, c + 5, "所定内", "第1表")
    must(rows, 12, 2, "男女計", "第1表")
    out = {}
    for c0, kibo in KIBO.items():
        d = {}
        for i in range(12, 25):
            lab = age_lab(rows[i][2])
            lab = "年齢計" if "男女計" in lab else lab
            d[lab] = {k: fnum(rows[i][c0 + j]) for j, k in NEN.items()}
        if any(a not in d for a in AGES[1:10]):
            stop(f"第1表の {kibo} の年齢の行が足りません")
        out[kibo] = d
    info.update(範囲="民営事業所・産業計・男女計・学歴計・一般労働者・令和7年6月分（賞与は前年1年間）", 表の中の位置="シート 産業計 の最初の塊（男女計学歴計）",
                定義="きまって支給する現金給与額−所定内給与額＝超過労働給与額（残業・休日出勤・深夜の手当など）。単位は千円・時間・歳・年・十人")
    src["b_chinkin_r7_1"] = info
    return {"source": "b_chinkin_r7_1", "単位": "千円・時間・歳・年・十人", "値": out}


# ---- 5. 賃金構造基本統計調査 第2表 年齢×勤続年数 ----
KINZOKU = ["勤続年数計", "0年", "1～2年", "3～4年", "5～9年", "10～14年", "15～19年", "20～24年", "25～29年", "30年以上"]


def chinkin_kinzoku(src):
    path, info = estat_file(CHIN, "勤続年数階級別", "000040420844", "b_chinkin_r7_2_kinzoku.xlsx", MHLW, "賃金構造基本統計調査")
    rows = xlsx_rows(path, "(規模計)")
    must(rows, 7, 3, "企業規模計", "第2表")
    for n, k in enumerate(KINZOKU):
        must(rows, 9, 3 + 3 * n, k, "第2表")
        must(rows, 10, 3 + 3 * n, "所定内", "第2表")
    must(rows, 12, 2, "男女計", "第2表")
    out = {}
    for i in range(12, 25):
        lab = age_lab(rows[i][2])
        lab = "年齢計" if "男女計" in lab else lab
        out[lab] = {k: {"所定内給与額": fnum(rows[i][3 + 3 * n]), "年間賞与その他特別給与額": fnum(rows[i][4 + 3 * n]),
                        "労働者数_十人": fnum(rows[i][5 + 3 * n])} for n, k in enumerate(KINZOKU)}
    if any(a not in out for a in AGES[1:10]):
        stop("第2表の年齢の行が足りません")
    info.update(範囲="民営事業所・産業計・企業規模計（10人以上）・男女計・学歴計・一般労働者", 表の中の位置="シート (規模計) の最初の塊（男女計学歴計）",
                定義="勤続年数0年は、その会社に勤めて1年未満の人（転職して入った人も、新しく学校を出た人も入る）。単位は千円・十人")
    src["b_chinkin_r7_2"] = info
    return {"source": "b_chinkin_r7_2", "単位": "千円・十人", "値": out}


# ---- 6. 賃金構造基本統計調査 第3表 所定内給与の分布 ----
BUNPU_SHEETS = {"産業計(規模計)": "規模計", "産業計(1000人以上)": "1,000人以上", "産業計(100～999人)": "100～999人", "産業計(10～99人)": "10～99人"}
STATS = {"第1・十分位数": "第1・十分位数", "第1・四分位数": "第1・四分位数", "中位数": "中位数", "第3・四分位数": "第3・四分位数", "第9・十分位数": "第9・十分位数"}


def chinkin_bunpu(src):
    path, info = estat_file(CHIN, "所定内給与額階級別", "000040420874", "b_chinkin_r7_3_bunpu.xlsx", MHLW, "賃金構造基本統計調査")
    out = {}
    for sheet, kibo in BUNPU_SHEETS.items():
        rows = xlsx_rows(path, sheet)
        must(rows, 8, 5, "年齢計", "第3表")
        must(rows, 10, 3, "男女計", "第3表")
        ages = []
        for c in range(5, 18):
            h = norm(cell(rows, 8, c))
            if h == "年齢計":
                ages.append((c, "年齢計"))
                continue
            m = re.fullmatch(r"(\d+)?～(\d+)?歳?", h)
            if not m:
                continue
            lab = f"{m.group(1)}～{m.group(2)}歳" if m.group(1) and m.group(2) else (f"{m.group(2)}歳以下" if m.group(2) else f"{m.group(1)}歳以上")
            ages.append((c, lab))
        if [a for _, a in ages][:4] != ["年齢計", "19歳以下", "20～24歳", "25～29歳"]:
            stop(f"第3表 {sheet} の年齢の見出しが想定と違います：{[a for _, a in ages][:5]}")
        d = {a: {"労働者数_十人": fnum(rows[10][c]), "階級": []} for c, a in ages}
        i = 11
        while i < len(rows):
            lab = norm(cell(rows, i, 2))
            m = re.match(r"(\d+(?:\.\d+)?)?～", lab)
            if not m:
                break
            low = float(m.group(1)) if m.group(1) else 0.0
            for c, a in ages:
                d[a]["階級"].append({"下限_千円": low, "見出し": lab, "労働者数_十人": fnum(rows[i][c]) or 0.0})
            i += 1
        for j in range(i, i + 5):
            lab = norm(cell(rows, j, 3))
            for k in STATS:
                if lab.startswith(norm(k)):
                    for c, a in ages:
                        d[a][k + "_千円"] = fnum(rows[j][c])
        for a in d:
            if "中位数_千円" not in d[a]:
                stop(f"第3表 {sheet} の {a} に中位数がありません")
            tot = sum(x["労働者数_十人"] for x in d[a]["階級"])
            if d[a]["労働者数_十人"] and abs(tot - d[a]["労働者数_十人"]) > max(5, d[a]["労働者数_十人"] * 0.001):  # 各欄の丸めの分だけずれる
                stop(f"第3表 {sheet} の {a} の階級の合計が労働者数と合いません（{tot}／{d[a]['労働者数_十人']}）")
        out[kibo] = d
    info.update(範囲="民営事業所・産業計・男女計・学歴計・一般労働者。企業規模計と規模別の4枚", 表の中の位置="各シートの最初の塊（男女計学歴計）",
                定義="所定内給与額の階級（千円）ごとの労働者数（十人）と、中位数・四分位数・十分位数（千円）")
    src["b_chinkin_r7_3"] = info
    return {"source": "b_chinkin_r7_3", "単位": "千円・十人", "値": out}


# ---- 7. 賃金構造基本統計調査 新規学卒者 第1表 初任給 ----
GAKUREKI = ["学歴計", "高校", "専門学校", "高専・短大", "大学", "大学院"]
SKIBO = {3: "規模計", 5: "1,000人以上", 7: "100～999人", 9: "10～99人"}


def shoninkyu(src):
    path, info = estat_file(CHIN, "新規学卒者", "000040420917", "b_chinkin_r7_shinsotsu.xlsx", MHLW, "賃金構造基本統計調査")
    out = {}
    for g in GAKUREKI:
        rows = xlsx_rows(path, g)
        must(rows, 5, 3, g, "新規学卒者第1表")
        for c, k in SKIBO.items():
            must(rows, 7, c, "企業規模計" if k == "規模計" else k, "新規学卒者第1表")
            must(rows, 9, c, "所定内給与額", "新規学卒者第1表")
        must(rows, 11, 1, "男女計", "新規学卒者第1表")
        out[g] = {k: {"所定内給与額": fnum(rows[11][c]), "労働者数_十人": fnum(rows[11][c + 1])} for c, k in SKIBO.items()}
    info.update(範囲="民営事業所・産業計・男女計・令和7年に学校を出て、6月時点で働いている一般労働者", 表の中の位置="学歴ごとのシートの「男女計」の行（産業計）",
                定義="新規学卒者の所定内給与額（いわゆる初任給。残業代などは入らない）。単位は千円・十人")
    src["b_chinkin_r7_shinsotsu"] = info
    return {"source": "b_chinkin_r7_shinsotsu", "単位": "千円・十人", "値": out}


# ---- 8. 就労条件総合調査 週休制・年間休日 ----
SHUKYU = ["週休1日制又は週休1日半制", "何らかの週休2日制", "完全週休2日制より休日日数が実質的に少ない制度", "完全週休2日制",
          "何らかの週休3日制", "完全週休3日制より休日日数が実質的に少ない制度", "完全週休3日制", "完全週休3日制より休日日数が実質的に多い制度"]
SKIBO2 = {"調査計": "調査計", "1,000人以上": "1,000人以上", "100～999人": "100～999人", "300～999人": "300～999人",
          "100～299人": "100～299人", "30～99人": "30～99人"}


def shuro_rows(rows, first, last):
    """表頭の下から、調査計と企業規模の行を {名前: 行} で返す"""
    out = {}
    for i in range(first, last):
        lab = norm(cell(rows, i, 2)) or norm(cell(rows, i, 3))
        if lab in SKIBO2:
            out[SKIBO2[lab]] = rows[i]
    if set(out) != set(SKIBO2):
        stop(f"就労条件総合調査の表で、企業規模の行が足りません：{sorted(out)}")
    return out


def shukyu(src):
    res = {}
    path, info = estat_file(SHURO, "週休制", "000040425669", "b_shuro_r7_2_shukyu_kigyo.xlsx", MHLW, "就労条件総合調査")
    rows = xlsx_rows(path, 0)
    must(rows, 0, 0, "第2表", "就労条件 第2表")
    for c, w in ((5, "全企業"), (6, "週休1日制"), (7, "何らかの週休2日制"), (9, "完全週休2日制"), (10, "何らかの週休3日制"),
                 (12, "完全週休3日制"), (13, "実質的に多い"), (14, "不明")):
        must(rows, 6, c, w, "就労条件 第2表")
    must(rows, 6, 8, "少ない", "就労条件 第2表")
    out = {}
    for k, r in shuro_rows(rows, 7, 17).items():
        out[k] = {n: zero(r[6 + j]) for j, n in enumerate(SHUKYU)}
        out[k]["不明"] = zero(r[14])
    info.update(範囲="常用労働者30人以上の民営企業・令和7年1月1日現在（週休制は令和6年の状況）", 表の中の位置="第2表の調査計と企業規模の行",
                定義="主な週休制の形態別の企業割合（%）。「何らかの週休3日制」は、完全週休3日制と、それより休日が実質的に少ない制度の合計。「-」は該当なしで、0にした")
    src["b_shuro_r7_2"] = info
    res["週休制_企業割合"] = {"source": "b_shuro_r7_2", "単位": "%（企業割合）", "値": out}

    path, info = estat_file(SHURO, "週休制", "000040425670", "b_shuro_r7_3_shukyu_rodosha.xlsx", MHLW, "就労条件総合調査")
    rows = xlsx_rows(path, 0)
    must(rows, 0, 0, "第3表", "就労条件 第3表")
    for c, w in ((5, "労働者計"), (6, "週休1日制"), (7, "何らかの週休2日制"), (10, "何らかの週休3日制"), (13, "実質的に多い")):
        must(rows, 3, c, w, "就労条件 第3表")
    must(rows, 4, 9, "完全週休2日制", "就労条件 第3表")
    must(rows, 4, 12, "完全週休3日制", "就労条件 第3表")
    out = {k: {n: zero(r[6 + j]) for j, n in enumerate(SHUKYU)} for k, r in shuro_rows(rows, 5, 16).items()}
    info.update(範囲="常用労働者30人以上の民営企業の労働者・令和7年1月1日現在", 表の中の位置="第3表の調査計と企業規模の行",
                定義="週休制の形態別の適用労働者割合（%）。「-」は該当なしで、0にした")
    src["b_shuro_r7_3"] = info
    res["週休制_労働者割合"] = {"source": "b_shuro_r7_3", "単位": "%（労働者割合）", "値": out}

    path, info = estat_file(SHURO, "年間休日", "000040425671", "b_shuro_r7_4_kyujitsu.xlsx", MHLW, "就労条件総合調査")
    rows = xlsx_rows(path, 0)
    must(rows, 0, 0, "第4表", "就労条件 第4表")
    must(rows, 3, 15, "平均年間休日総数", "就労条件 第4表")
    heads = [norm(cell(rows, 4, c)) + norm(cell(rows, 5, c)) for c in range(6, 15)]
    want = ["69日以下", "70～79日", "80～89日", "90～99日", "100～109日", "110～119日", "120～129日", "130日以上", "不明"]
    if heads != want:
        stop(f"就労条件 第4表の階級の見出しが想定と違います：{heads}")
    out = {}
    for k, r in shuro_rows(rows, 7, 15).items():
        out[k] = {w: zero(r[6 + j]) for j, w in enumerate(want)}
        out[k]["1企業平均年間休日総数_日"] = fnum(r[15])
    info.update(範囲="常用労働者30人以上の民営企業・令和6年（又は令和5会計年度）の年間休日総数", 表の中の位置="第4表の調査計と企業規模の行",
                定義="年間休日総数の階級別の企業割合（%）と、1企業平均の年間休日総数（日）")
    src["b_shuro_r7_4"] = info
    res["年間休日"] = {"source": "b_shuro_r7_4", "単位": "%（企業割合）・日", "値": out}
    return res


# ---- 9. 就労条件総合調査 令和4年 基本給の決定要素（管理職以外） ----
YOSO = {2: "回答あり計", 3: "職務・職種など仕事の内容", 4: "職務遂行能力", 5: "業績・成果", 6: "学歴、年齢、勤続年数など",
        7: "学歴", 8: "年齢・勤続年数など", 9: "不明"}


def kihonkyu(src):
    path, info = estat_file(SHURO, "基本給の決定要素", "000040013116", "b_shuro_r4_29-2_kihonkyu.xlsx", MHLW, "就労条件総合調査")
    rows = xlsx_rows(path, 0)
    must(rows, 2, 1, "第29-2表", "就労条件 第29-2表")
    must(rows, 2, 1, "管理職以外", "就労条件 第29-2表")
    for c, w in ((3, "職務・職種"), (4, "職務遂行能力"), (5, "業績・成果"), (6, "学歴、年齢、勤続年数")):
        must(rows, 6, c, w, "就労条件 第29-2表")
    must(rows, 7, 8, "年齢・勤続年数", "就労条件 第29-2表")
    out = {}
    for i in range(10, 16):
        lab = norm(rows[i][0])
        lab = "調査計" if "調査産業計" in lab else lab
        if lab in SKIBO2:
            out[lab] = {k: zero(rows[i][c]) for c, k in YOSO.items()}
    if set(out) != set(SKIBO2):
        stop(f"就労条件 第29-2表の企業規模の行が足りません：{sorted(out)}")
    info.update(範囲="常用労働者30人以上の民営企業・令和4年1月1日現在・管理職以外の基本給（複数回答）", 表の中の位置="第29-2表の調査産業計と企業規模の行",
                定義="基本給の決定要素ごとの企業割合（%・複数回答）。この項目は令和4年の調査が最新（就労条件総合調査は年ごとに調べる項目が替わる）",
                注意="令和4年（2022年）の数字。声では「2022年の調査で」と言う")
    src["b_shuro_r4_29-2"] = info
    return {"source": "b_shuro_r4_29-2", "単位": "%（企業割合・複数回答）", "値": out}


def run():
    src, tables = {}, {}
    tables["賃金変動"] = hendo(src)
    tables["労働移動率"] = idoritsu(src)
    tables["離職理由"] = riyu(src)
    tables["年齢別の賃金"] = chinkin_nenrei(src)
    tables["年齢と勤続年数別の賃金"] = chinkin_kinzoku(src)
    tables["所定内給与の分布"] = chinkin_bunpu(src)
    tables["初任給"] = shoninkyu(src)
    tables.update(shukyu(src))
    tables["基本給の決定要素"] = kihonkyu(src)
    for t in tables.values():  # 表の名前・URL・取得日を各表にも付ける（facts.json の出典カードに使う）
        s = src[t["source"]]
        t.update({"表名": s["表名"], "統計名": s["統計名"], "公表日": s.get("公表日"), "URL": s["url"], "ダウンロード": s["download"],
                  "statInfId": s["statInfId"], "取得日": s["fetched"], "e_stat": s["e_stat"]})
    meta = {"題": "型B 会社の決断の結末（年齢別の賃金・転職・離職・制度の割合）", "取得日": TODAY, "e_stat_note": estat.NOTE,
            "決まり": "値はダウンロードした表の値そのまま。言い直し・差・合計は b_facts.py で計算する"}
    text = json.dumps({"meta": meta, "tables": tables}, ensure_ascii=False, indent=1)
    if estat._app_id() in text:  # キーが紛れていないか（値は出さない）
        stop("保存する値にキーが入っています。保存をやめました")
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(text)
    # 共有の sources.json・checksums.json には書かず、足す分だけを書き出す
    sums = {v["file"]: v["sha256"] for v in src.values()}
    sums[rel(OUT)] = sha256(OUT)
    with open(NEW, "w", encoding="utf-8") as f:
        json.dump({"sources": src, "checksums": sums}, f, ensure_ascii=False, indent=1)
    print(f"表 {len(tables)}・原本 {len(src)} を保存しました：{rel(OUT)}")
    print(f"sources.json・checksums.json に足す分：{rel(NEW)}（係が読み直してから足す）")


if __name__ == "__main__":
    run()

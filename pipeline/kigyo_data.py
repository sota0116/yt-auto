# 企業もしも（手順書 §15 決まり1）の年齢の札：賃金構造 産業大分類 第1表の「その産業・1,000人以上・年齢階級」の値
#   python -X utf8 pipeline\kigyo_data.py   … data\raw\estat\chinkin_r7_sangyo_t1.xlsx を読み、data\job\kigyo_r7.json に保存
# ・e-Stat には取りに行かない。表は fetch_a1c_data.py が取って保存した物（sources.json の sha256 と照らしてから読む）
# ・年収は fetch_job_data.derive と同じ式（きまって支給×12＋賞与）。会社の数字ではなく「業界の平均」として使う
import json, os, re, sys
import openpyxl
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fetch_a1c_data import clean, age_label
from fetch_job_data import FIELDS, derive, num, sha256

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KEY = "chinkin_r7_sangyo_t1"
OUT = os.path.join(ROOT, "data", "job", "kigyo_r7.json")
BLOCKS = {"企業規模計（10人以上）": 3, "1,000人以上": 11, "100～999人": 19, "10～99人": 27}
SIZE = "1,000人以上"


def parse(path):
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    out = {}
    for ws in wb.worksheets:
        name = ws.title
        if name.startswith("(民＋公)"):
            continue
        rows = list(ws.iter_rows(min_row=1, max_row=40, values_only=True))
        col = BLOCKS[SIZE]
        if clean(rows[5][3]) != "民営事業所" or clean(rows[8][col]) != SIZE:
            sys.exit(f"【止まりました】産業大分類 第1表の {name} の {col} 列目が「{SIZE}」ではありません")
        if [clean(rows[9][col + i] or rows[10][col + i] or "") for i in range(8)] != [clean(x) for x in FIELDS]:
            sys.exit(f"【止まりました】産業大分類 第1表の {name} の {SIZE} の列の見出しが想定と違います")
        key = name if name == "産業計" else name[0]
        rec = None
        for r in rows[12:]:
            lab = clean(r[2]) if len(r) > 2 and r[2] is not None else ""
            vals = dict(zip(FIELDS, [num(v) for v in r[col:col + 8]]))
            if "男女計" in lab and "学歴計" in lab:
                rec = {"表の名前": name if name == "産業計" else name[1:], "年齢計": {**vals, **derive(vals)}, "年齢階級": {}}
                continue
            if rec is None:
                continue
            if "歳" not in lab:
                break
            rec["年齢階級"][age_label(lab)] = {**vals, **derive(vals)}
        if rec is None:
            sys.exit(f"【止まりました】産業大分類 第1表の {name} に男女計・学歴計の行がありません")
        out[key] = rec
    if "産業計" not in out or len(out) != 17:
        sys.exit(f"【止まりました】産業の数が想定（16＋計）と違います：{len(out)}")
    return out


def main():
    src = json.load(open(os.path.join(ROOT, "data", "sources.json"), encoding="utf-8"))[KEY]
    path = os.path.join(ROOT, src["file"])
    if sha256(path) != src["sha256"]:
        sys.exit(f"【止まりました】{src['file']} が sources.json の記録と違います（取り直した時は fetch_a1c_data.py --register を先に）")
    data = parse(path)
    from estat import NOTE
    meta = {"出典キー": KEY, "表": src["table"], "statInfId": src["statInfId"], "企業規模": SIZE, "e_stat_note": NOTE,
            "範囲": "一般労働者・民営事業所・男女計・学歴計。企業規模1,000人以上",
            "決まり": "値は表の値そのまま。年収＝きまって支給する現金給与額×12＋年間賞与その他特別給与額（千円）。"
                    "会社ごとの値ではないので、画面と声では「業界の平均」と言う（手順書 §15 決まり1）"}
    json.dump({"meta": meta, "data": data}, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    j = data["Ｊ"]["年齢階級"]
    print(f"保存しました：{os.path.relpath(OUT, ROOT)}（産業 {len(data)}・{SIZE}）。例 Ｊ 50～54歳 {j['50～54歳']['年収_千円']}千円")


if __name__ == "__main__":
    main()

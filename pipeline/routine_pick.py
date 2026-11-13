# 1日の流れショート①題選び（手順書 §12。2026-11-02 本人「その職業の1日ルーティンとかいいんじゃない」「自動でのせてPDCAで改善して」）
#   python -X utf8 pipeline\routine_pick.py --out <作業フォルダ> [--list]
# ・主な職業40から、普通は見えない時間帯のある職業の順に1つ選び、facts.json を作る（年収・時給・労働時間はプログラムが書く。Claude は計算しない）
# ・作れた職業は2度出さない。作れなかった職業は1回だけもう一度試す（絵＝Lovart で止まった回は職業のせいではないので数えない）
# ・数字が集まったら（shorts_learn.json の「1日の流れ」）、3本に2本は点の高い仲間の職業を先に、1本は試す枠で順番どおりに選ぶ
# ・先生2つは公立が調査の対象外で値が偏る（手順書 §8）。管理職は1日の形が決まらないので使わない
import argparse, json, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from job_facts_common import ROOT, sources_block, write
from short_pick import GROUPS, MEASURES, history, item, ranks, rows

ORDER = ["大型トラック運転手", "介護職員（施設）", "看護師", "警備員", "タクシー運転手", "バス運転手", "電車の運転士", "調理人", "パイロット",
         "医師", "客室乗務員（CA）", "訪問介護員（ヘルパー）", "美容師・理容師", "保育士", "大工", "自動車整備士", "ホール係（飲食物給仕）",
         "販売店員", "電気工事士", "建築技術者（設計・施工管理）", "土木技術者（設計・施工管理）", "歯科衛生士", "薬剤師", "臨床検査技師",
         "システムエンジニア（設計者）", "プログラマー（ソフトウェア作成者）", "銀行・証券の営業", "保険の営業", "一般事務（総合事務員）"]
SKIP = ("管理職",)
SERVICE = ("美容師・理容師", "ホール係（飲食物給仕）", "販売店員", "調理人")


def group(name):
    if name in SERVICE:
        return "店"
    return next((g for g, names in GROUPS.items() if names and name in names), "その他")


def short_name(name):
    return re.sub(r"（.*?）", "", name)


def tid(name):
    return "routine_" + name


def queue(rs):
    have = {r["表示名"] for r in rs}
    tail = [r["表示名"] for r in rs if r["表示名"] not in ORDER and r["表示名"] not in SKIP]
    return [x for x in ORDER if x in have] + tail


def choose(rs):
    h = [x for x in history() if x.get("kind") == "routine"]
    done = {x["topic_id"] for x in h if x.get("ok")}
    bad = {t for t in {x["topic_id"] for x in h}
           if sum(x["topic_id"] == t and not x.get("ok") and "make_images_lovart" not in (x.get("why") or "") for x in h) >= 2}
    q = [x for x in queue(rs) if tid(x) not in done | bad]
    if not q:
        sys.exit("【止まりました】1日の流れの職業が残っていません")
    lp = os.path.join(ROOT, "history", "job", "shorts_learn.json")
    pts = ((json.load(open(lp, encoding="utf-8")) if os.path.exists(lp) else {}).get("1日の流れ") or {}).get("仲間の点") or {}
    if len(pts) >= 2 and len(h) % 3 != 2:  # 3本に2本は点の高い仲間から。1本は順番どおり（試す枠）
        return max(q, key=lambda x: pts.get(group(x), -1))
    return q[0]


def facts(name, rs):
    r = next(x for x in rs if x["表示名"] == name)
    allr = {m: ranks(rs, MEASURES[m]["key"]) for m in ("年収", "時給")}
    call = short_name(name)
    return {"kind": "routine", "topic_id": tid(name), "measure": "1日_" + group(name), "仲間": group(name), "表示名": name, "呼び名": call,
            "題": f"{call}の1日", "職業": item(r, "年収", allr),
            "定義": {"年収": "きまって支給する現金給与額×12＋年間賞与その他特別給与額（賞与は前の年1年分）",
                   "時給に直した額": "年収÷（所定内実労働時間数＋超過実労働時間数）÷12", "月の労働時間": "所定内実労働時間数＋超過実労働時間数（6月分）"},
            "対象": f"一般労働者（短時間労働者を除く）・企業規模10人以上・男女計。主な職業{len(rs)}",
            "charts": [], **sources_block(["chinkin_r7_shokushu"])}


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--out")
    a.add_argument("--list", action="store_true")
    a = a.parse_args()
    rs = rows()
    if a.list:
        print(json.dumps([{"職業": x, "仲間": group(x)} for x in queue(rs)], ensure_ascii=False))
        return
    name = choose(rs)
    f = facts(name, rs)
    write(os.path.join(ROOT, a.out), f)
    print(json.dumps({"work": a.out, "topic_id": f["topic_id"], "題": f["題"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()

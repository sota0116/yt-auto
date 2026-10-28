# ショート②の点検（手順書 §12）：script.json を facts.json と決まりに照らす。NG があれば終わりのコードが1
#   python -X utf8 pipeline\check_short.py <作業フォルダ>
import json, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from check_psy_script import tease  # 答えの先送りの見分け方（references/16 の6）

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
META = ["この動画", "この回", "今回", "このチャンネル", "ここからは", "ここまで", "この後", "次の章", "見ていきます", "紹介します",
        "ありがとうございました", "今日", "今夜", "概要欄", "チャンネル登録", "LINE", "ミナト", "ユイ", "離職率"]


def banned():
    p = os.path.join(ROOT, "channels", "job", "禁止表現.txt")
    return [x.strip() for x in open(p, encoding="utf-8") if x.strip() and not x.startswith("#")]


def nums(s):
    return [n.replace(",", "") for n in re.findall(r"\d[\d,]*(?:\.\d+)?", s)]


def check(work):
    sc = json.load(open(os.path.join(work, "script.json"), encoding="utf-8"))
    fx = json.load(open(os.path.join(work, "facts.json"), encoding="utf-8"))
    ng, warn = [], []
    cuts = sc.get("cuts", [])
    text = "".join(c.get("narration", "") for c in cuts)
    n = len(text)
    if not 180 <= n <= 280:
        ng.append(f"字数 {n}（180〜280字）")
    if not 8 <= len(cuts) <= 12:
        ng.append(f"カット数 {len(cuts)}（8〜12）")
    for c in cuts:
        if len(c.get("narration", "")) > 40:
            ng.append(f"{c['id']} が {len(c['narration'])}字（1カット40字まで）")
        if c.get("speaker") not in ("narrator", "listener"):
            ng.append(f"{c['id']} の speaker がない")
    lis = sum(len(c["narration"]) for c in cuts if c.get("speaker") == "listener")
    if n and not 0.2 <= lis / n <= 0.4:
        ng.append(f"聞き手の割合 {lis / n:.0%}（2〜4割）")
    # 数字は facts.json の中にある物だけ（順位・職業の数・倍率なども facts.json に書いてある）
    have = set(nums(json.dumps(fx, ensure_ascii=False)))
    for c in cuts:
        for x in nums(c.get("narration", "") + c.get("hook", "")):
            if x not in have:
                ng.append(f"{c['id']} の数字 {x} が facts.json にない")
    spoken = [x for c in cuts for x in re.findall(r"\d[\d,.]*(?:万円|円|時間|歳|年|倍)", c.get("narration", ""))]
    if len(set(spoken)) > 2:
        warn.append(f"声で言う数字が {len(set(spoken))}個（2つまで）：{sorted(set(spoken))}")
    allv = text + sc.get("title", "") + "".join(sc.get("banner", [])) + "".join(c.get("hook", "") for c in cuts) + sc.get("desc_lead", "")
    for w in banned() + META:
        if w in allv:
            ng.append(f"使わない言葉「{w}」")
    # 帯と hook の字数
    ban = sc.get("banner") or []
    if len(ban) != 2 or len(ban[0]) > 7 or len(ban[1]) > 10:
        ng.append(f"帯 {ban}（大きい字7字・小さい字10字の2つ）")
    hook = cuts[0].get("hook", "") if cuts else ""
    if not hook or max(len(x) for x in hook.split("\n")) > 5 or hook.count("\n") > 1:
        ng.append(f"1カット目の hook「{hook}」（1行5字・2行まで）")
    # 画面：chart の番号と、出す本数が減らないか。最後に全部出ているか
    last = {}
    for c in cuts:
        s = c.get("screen") or {}
        if "chart" in s:
            if s["chart"] >= len(fx["charts"]):
                ng.append(f"{c['id']} の screen.chart {s['chart']} がない")
                continue
            k = s.get("show", len(fx["charts"][s["chart"]]["bars"]))
            if k < last.get(s["chart"], 0):
                ng.append(f"{c['id']} で出した棒が減っている")
            last[s["chart"]] = k
        elif not s.get("hook"):
            ng.append(f"{c['id']} に screen がない")
    for i, ch in enumerate(fx["charts"]):
        if last.get(i, 0) < len(ch["bars"]):
            ng.append(f"グラフ{i} の棒が最後まで全部出ていない")
    # 見どころ（2026-10-28 本人の指摘。スキル references/16 の4）：新しい棒が伸びるカット（動き）に "peak": true。
    #   rank は1位の黄の棒が出るカット（棒が伸びる動き＋黄の強調で2つ）。答えを先送りするだけの文も NG（references/16 の6）
    seen, grow = {}, {}
    for c in cuts:
        s_ = c.get("screen") or {}
        if "chart" in s_ and s_["chart"] < len(fx["charts"]):
            k = s_.get("show", len(fx["charts"][s_["chart"]]["bars"]))
            grow[c["id"]] = (k > seen.get(s_["chart"], 0), k >= len(fx["charts"][s_["chart"]]["bars"]))
            seen[s_["chart"]] = k
    pk = [c for c in cuts if c.get("peak")]
    if not pk:
        ng.append("見どころのカットが無い：1位（強調の黄の棒）が出るカットに \"peak\": true を書く（§12）")
    for c in pk:
        g, full = grow.get(c["id"], (False, False))
        if not g:
            ng.append(f"{c['id']} の peak：新しい棒が伸びるカットに付ける（止まった画面には付けない）")
        elif fx.get("kind") == "rank" and not full:
            ng.append(f"{c['id']} の peak：rank は1位の黄の棒が出るカット（show が全部の本数）に付ける")
    for c in cuts:
        w = tease(c.get("narration", "") + c.get("hook", ""))
        if w:
            ng.append(f"{c['id']}：答えを先送りするだけの文「{w}」（問いで引き、答えはこのショートの中で出す）")
    # rank：1位の名前は、1位の棒を出すカットより前に言わない
    if fx["kind"] == "rank":
        first = fx["charts"][0]["bars"][0]["name"]
        for c in cuts:
            if (c.get("screen") or {}).get("show", 0) >= len(fx["charts"][0]["bars"]):
                break
            said = c.get("narration", "") + c.get("hook", "")
            for b in fx["charts"][0]["bars"][1:]:  # 「歯科医師」の中の「医師」は1位の名前ではない
                if first in b["name"] and first != b["name"]:
                    said = said.replace(b["name"], "")
            if first in said:
                ng.append(f"{c['id']} で1位（{first}）を先に言っている")
    t = sc.get("title", "")
    if not t or len(t) > 60:
        ng.append(f"タイトル {len(t)}字（ハッシュタグ込みで60字まで）")
    for w in ("AI", "PR"):
        if w in t:
            ng.append(f"タイトルに「{w}」")
    if "逆転" in t and not fx.get("逆転"):
        ng.append("タイトルの「逆転」（facts.json に記録がない）")
    if not sc.get("desc_lead"):
        ng.append("desc_lead（説明文の1段落目）がない")
    print(f"字数 {n}・カット {len(cuts)}・聞き手 {lis / max(n, 1):.0%}")
    for x in ng:
        print("NG", x)
    for x in warn:
        print("注意", x)
    print(f"NG {len(ng)}件・注意 {len(warn)}件")
    return not ng


if __name__ == "__main__":
    sys.exit(0 if check(os.path.abspath(sys.argv[1])) else 1)

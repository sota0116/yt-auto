# 企業もしもショート②の点検（手順書 §15）：script.json を facts.json と決まりに照らす。NG があれば終わりのコードが1
#   python -X utf8 pipeline\check_kigyo.py <作業フォルダ>
# ・作り話を防ぐ：day_facts の URL を実際に開き、抜き書きがそのページにあるかを照らす（check_routine.verify）。別の URL で2件以上
# ・声の数字は、facts.json の年齢の札か、照合が通った day_facts の「事実」にある物だけ（主人公の年齢「22歳」は作り話なので通す）
# ・決まり2：会社を評価する言葉・違法や不正の言葉は、照合が通った資料に書いてある時だけ。決まり5：社名は公式の書き方
# ・決まり3・4：1カット目に候補の会社のロゴ（logos）、入社のカットに主役の会社のロゴ（logo）。facts.json の logos に出どころがあること
import json, os, re, sys
try:  # 手元の Windows は certifi の中に中間証明書が足りず、役所のページで SSL が落ちる。OS の証明書の置き場を使う（検証は外さない）
    import truststore
    truststore.inject_into_ssl()
except ImportError:
    pass
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from check_psy_script import tease
from check_short import META, banned, nums
from check_routine import ANGLES, verify, used_titles

CHARS = (400, 520)  # 声で約60〜80秒（1日の流れの 320〜420字＝約49〜64秒から割り出した目安）
CUTS = (12, 18)
FIRST_MAX, LAST_MAX = 30, 30
CUT_MAX = 55
AGE = re.compile(r"\d{1,2}歳")
JUDGE = ["ブラック", "闇", "ヤバい", "やばい", "ヤバ", "地獄", "最悪", "クズ"]  # 会社を評価する言葉（報道された事実が出る回でも、ロゴの隣・会社の評価には使わない）
WRONG = ["違法", "不正", "パワハラ", "セクハラ", "隠蔽", "改ざん", "詐欺", "横領", "粉飾", "相場操縦", "課徴金", "処分", "逮捕", "不祥事"]


def check(work):
    sc = json.load(open(os.path.join(work, "script.json"), encoding="utf-8"))
    fx = json.load(open(os.path.join(work, "facts.json"), encoding="utf-8"))
    ng, warn = [], []
    cuts = sc.get("cuts", [])
    text = "".join(c.get("narration", "") for c in cuts)
    n = len(text)
    if not CHARS[0] <= n <= CHARS[1]:
        ng.append(f"字数 {n}（{CHARS[0]}〜{CHARS[1]}字）")
    if not CUTS[0] <= len(cuts) <= CUTS[1]:
        ng.append(f"カット数 {len(cuts)}（{CUTS[0]}〜{CUTS[1]}）")
    if sc.get("format") != "short":
        ng.append('format は "short"')
    for w in ("style", "style_en", "avoid_en", "desc_lead"):
        if not sc.get(w):
            ng.append(f"{w} がない")
    if not (sc.get("characters") or {}).get("hero", {}).get("desc_en"):
        ng.append("characters.hero.desc_en（主役の見た目）がない")
    # 事実（決まり1・2）
    dfs = sc.get("day_facts") or []
    good, bad = verify(dfs)
    if len(set(good)) < 2:
        ng.append(f"day_facts の照合が通った資料 {len(set(good))}件（別の URL で2件以上）：{bad[:4]}")
    elif bad:
        ng.append(f"照合が通らなかった資料（直すか消す）：{bad[:3]}")
    passed = [d for d in dfs if d.get("url") in good]
    said_facts = "".join(d.get("事実", "") + d.get("抜き書き", "") for d in passed)
    tags = {t["年齢"].replace("～", "〜"): t for t in fx["年齢の札"]}
    have = {"1"} | {x for t in fx["年齢の札"] for x in nums(t["声の年収"] + t["年齢"])} | {x for d in passed for x in nums(d.get("事実", ""))}
    # カットごと
    hero, angles, seq = 0, [], []
    for i, c in enumerate(cuts):
        cid = c.get("id", f"#{i}")
        said = c.get("narration", "")
        if c.get("speaker") != "narrator":
            ng.append(f"{cid} の speaker は narrator（語りは1人）")
        if len(said) > CUT_MAX:
            ng.append(f"{cid} が {len(said)}字（1カット{CUT_MAX}字まで）")
        for x in nums(AGE.sub("", said + c.get("hook", ""))):
            if x not in have:
                ng.append(f"{cid} の数字 {x} が、年齢の札でも照合が通った day_facts でもない")
        w = tease(said + c.get("hook", ""))
        if w:
            ng.append(f"{cid}：答えを先送りするだけの文「{w}」")
        if c.get("tag"):
            t = c["tag"].replace("～", "〜")
            if t not in tags:
                ng.append(f"{cid} の tag「{c['tag']}」は facts.json の年齢の札の年齢（例 25〜29歳）")
            else:
                seq.append(t)
                v = tags[t]["声の年収"].lstrip("約")
                if re.search(r"\d+万", said) and v not in said:
                    ng.append(f"{cid}：札は {t}（{v}）なのに、声で別の年収を言っている")
        if c.get("chart"):
            ng.append(f"{cid}：企業もしもに年収のカード（chart）は使わない。年齢の札（tag）で出す")
        if not c.get("image") or not c.get("image_en"):
            ng.append(f"{cid} に image と image_en がない")
        if re.search(r"[ぁ-んァ-ヶ一-龠]", c.get("image_en", "")):
            ng.append(f"{cid} の image_en に日本語がある（読める文字が絵に出る）")
        if re.search(r"(?i)\blogo|nomura|daiwa|mizuho|mufg|smbc", c.get("image_en", "")):
            ng.append(f"{cid} の image_en に社名かロゴがある（ロゴは組み立てで本物を重ねる。絵に描かせない）")
        if c.get("angle") not in ANGLES:
            ng.append(f"{cid} の angle は {ANGLES} のどれか")
        angles.append(c.get("angle"))
        hero += bool(c.get("chars"))
    # 年齢の札（決まり1・§15 の中堅の拍）
    if len(set(seq)) < 4 or len(set(seq)) > 6:
        ng.append(f"年齢の札（tag）が {len(set(seq))}種類（4〜6回変える）")
    order = [list(tags).index(t) for t in seq]
    if order != sorted(order):
        ng.append("年齢の札が若い順に並んでいない（時間を戻さない）")
    vals = [tags[t]["年収_千円"] for t in dict.fromkeys(seq)]
    if vals and not any(b < a for a, b in zip(vals, vals[1:])) and not any(b - a >= 1000 for a, b in zip(vals, vals[1:])):
        ng.append("年齢の札に、大きく跳ねる所（100万円以上）か下がる所が無い")
    # 社名とロゴ（決まり4・5）
    name = fx["会社"]
    if name not in text:
        ng.append(f"声に社名「{name}」が無い")
    wrong = name.replace("證", "証") if "證" in name else None
    if wrong and wrong in text + sc.get("title", "") + sc.get("desc_lead", ""):
        ng.append(f"社名は公式の「{name}」と書く（「{wrong}」にしない）")
    logo_names = {l["会社"] for l in fx.get("logos", [])}
    for l in fx.get("logos", []):
        if not all(l.get(k) for k in ("page", "license", "取った日", "png")) or not os.path.exists(os.path.join(work, l["png"])):
            ng.append(f"facts.json の logos の {l.get('会社')}：出どころ（page・license・取った日）か絵が無い")
    first = cuts[0] if cuts else {}
    if sorted(first.get("logos") or []) != sorted(logo_names) or not logo_names:
        ng.append(f"1カット目に候補の会社のロゴを全部並べる（\"logos\": {sorted(logo_names)}）")
    if not any(c.get("logo") == name for c in cuts[1:]):
        ng.append(f"入社のカットに主役の会社のロゴを出す（\"logo\": \"{name}\"）")
    # 決まり2：評価の言葉・不正の言葉
    allv = text + sc.get("title", "") + "".join(c.get("hook", "") for c in cuts) + sc.get("desc_lead", "")
    for w in JUDGE:
        if w in allv:
            ng.append(f"会社を評価する言葉「{w}」（手順書 §15 決まり2・4）")
    for w in WRONG:
        if w in allv and w not in said_facts:
            ng.append(f"「{w}」は、照合が通った資料（報道・行政の公表）に書いてある時だけ使える")
    # 絵
    for a in zip(angles, angles[1:], angles[2:]):
        if len(set(a)) == 1:
            ng.append(f"同じ向き（{a[0]}）が3カット続く")
            break
    if cuts and hero < len(cuts) * 0.6:
        ng.append(f"主役の出る絵が {hero}（6割以上）")
    motion = sum(bool(c.get("motion")) for c in cuts)
    if not 2 <= motion <= 3:
        ng.append(f"動く絵 {motion}（2〜3）")
    if not any(c.get("peak") for c in cuts):
        ng.append('山場（回収）のカットに "peak": true を書く')
    # 1文目・最後の1文・hook
    sents = lambda s: [x for x in re.split(r"(?<=[。？！?!])", s) if x.strip()]
    if cuts and sents(cuts[0].get("narration", "")) and len(sents(cuts[0]["narration"])[0]) > FIRST_MAX:
        ng.append(f"1文目が {len(sents(cuts[0]['narration'])[0])}字（{FIRST_MAX}字まで）")
    if cuts and sents(cuts[-1].get("narration", "")) and len(sents(cuts[-1]["narration"])[-1]) > LAST_MAX:
        ng.append(f"最後の1文が {len(sents(cuts[-1]['narration'])[-1])}字（{LAST_MAX}字まで）")
    if cuts and not re.search(r"[？?]", cuts[-1].get("narration", "")):
        ng.append("最後のカットで、次に見たい会社を聞く（？で終わる問い）")
    hook = first.get("hook", "")
    if not hook or max(len(x) for x in hook.split("\n")) > 7 or hook.count("\n") > 1:
        ng.append(f"1カット目の hook「{hook}」（1行7字・2行まで）")
    for w in banned() + META:
        if w in allv:
            ng.append(f"使わない言葉「{w}」")
    t = sc.get("title", "")
    if not t or len(t) > 60:
        ng.append(f"タイトル {len(t)}字（ハッシュタグ込みで60字まで）")
    if t in used_titles():
        ng.append("タイトルが前に作った回と同じ（二重防止で上げられない）")
    if fx["題"] not in t:
        ng.append(f"タイトルに「{fx['題']}」を入れる")
    for w in ("AI", "PR"):
        if w in t:
            ng.append(f"タイトルに「{w}」")
    print(f"字数 {n}・カット {len(cuts)}・年齢の札 {len(set(seq))}・動く絵 {motion}・照合 {len(set(good))}件")
    for x in ng:
        print("NG", x)
    for x in warn:
        print("注意", x)
    print(f"NG {len(ng)}件・注意 {len(warn)}件")
    return not ng


if __name__ == "__main__":
    sys.exit(0 if check(os.path.abspath(sys.argv[1])) else 1)

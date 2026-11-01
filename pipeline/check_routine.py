# 1日の流れショート②の点検（手順書 §12）：script.json を facts.json と決まりに照らす。NG があれば終わりのコードが1
#   python -X utf8 pipeline\check_routine.py <作業フォルダ>
# ・作り話を防ぐ：day_facts の URL を実際に開き、抜き書きがそのページにあるかを照らす。2件以上通らなければ NG
# ・声の文の数字は、時刻か、facts.json か、day_facts の「事実」にある物だけ
# ・1本は1回の勤務（2026-11-02 1本目が 21:00 から翌 17:00 までの1回の勤務になり、点検を素通りした）。
#   clock の最初から最後までが SHIFT_MAX 時間以内。それより長い勤務（24時間勤務など）は、照合が通った資料の「事実」に「24時間勤務」のように書いてある時だけ
import ipaddress, json, os, re, sys, urllib.parse
import requests
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from check_psy_script import tease
from check_short import META, banned, nums

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHARS = (320, 420)  # 2026-11-02：声で約49〜64秒。詰め込みすぎない（前は330〜520字）
CUTS = (9, 12)
FIRST_MAX, LAST_MAX = 25, 30  # 1文目と最後の1文の字数
CUT_MAX = 55
SHIFT_MAX = 16
ANGLES = ("引き", "寄り", "見下ろし", "見上げ", "目線")
TIME = re.compile(r"\d{1,2}時(?!間)(?:半|\d{1,2}分)?")
UA = {"User-Agent": "Mozilla/5.0 (compatible; yt-auto-factcheck/1.0)"}


def squeeze(s):
    return re.sub(r"[\s　、。，．,.「」『』（）()・:：]", "", s)


def public(url):
    u = urllib.parse.urlparse(url)
    host = u.hostname or ""
    if u.scheme != "https" or not host or host == "localhost" or host.endswith((".local", ".internal")):
        return False
    try:
        ipaddress.ip_address(host)
        return False  # 数字だけのアドレスは開かない
    except ValueError:
        return True


def page(url, cache):
    if url in cache:
        return cache[url]
    r = requests.get(url, headers=UA, timeout=25)
    r.raise_for_status()
    kind = r.headers.get("content-type", "")
    if "html" not in kind and "text" not in kind:
        raise ValueError("HTML ではない")
    r.encoding = r.apparent_encoding or r.encoding
    cache[url] = squeeze(re.sub(r"<(script|style)\b.*?</\1>|<[^>]+>", "", r.text, flags=re.S))
    return cache[url]


def verify(day_facts):
    good, bad, cache = [], [], {}
    for d in day_facts:
        url, quote = d.get("url", ""), squeeze(d.get("抜き書き", ""))
        if not public(url) or len(quote) < 8 or not d.get("事実"):
            bad.append(f"{url or '(URL なし)'}：https の公開ページ・8字以上の抜き書き・事実が要る")
            continue
        try:
            body = page(url, cache)
        except Exception as e:
            bad.append(f"{url}：開けない（{type(e).__name__}）")
            continue
        if quote in body:
            good.append(url)
        else:
            bad.append(f"{url}：抜き書きがページにない")
    return good, bad


def shift_hours(clocks):
    """clock を順に進めた時の、最初から最後までの時間。前より早い時刻が来たら、次の日へまたいだと見る"""
    mins, day = [], 0
    for c in clocks:
        h, m = map(int, c.split(":"))
        if mins and h * 60 + m + day < mins[-1]:
            day += 1440
        mins.append(h * 60 + m + day)
    return (mins[-1] - mins[0]) / 60 if mins else 0


def shift_limit(passed):
    """照合が通った資料に「24時間勤務」のような長い勤務が書いてあれば、そこまで認める"""
    long_ = [int(x) for d in passed for x in re.findall(r"(\d+)時間(?:勤務|拘束|当直)", d.get("事実", ""))]
    return max([SHIFT_MAX] + long_)


def used_titles():
    p = os.path.join(ROOT, "history", "job", "shorts.json")
    return {x.get("title") for x in json.load(open(p, encoding="utf-8"))} if os.path.exists(p) else set()


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
    for w in ("style", "style_en", "avoid_en"):
        if not sc.get(w):
            ng.append(f"{w} がない")
    if not (sc.get("characters") or {}).get("hero", {}).get("desc_en"):
        ng.append("characters.hero.desc_en（主役の見た目）がない")
    # 事実
    dfs = sc.get("day_facts") or []
    good, bad = verify(dfs)
    if len(set(good)) < 2:
        ng.append(f"day_facts の照合が通った資料 {len(set(good))}件（別の URL で2件以上）：{bad[:4]}")
    elif bad:
        warn.append(f"照合が通らなかった資料：{bad[:3]}")
    passed = [d for d in dfs if d.get("url") in good]
    have = {"1"} | set(nums(json.dumps(fx["職業"], ensure_ascii=False))) | {x for d in passed for x in nums(d.get("事実", ""))}  # "1" は「1日」の1
    clocks, hero, angles = [], 0, []
    for i, c in enumerate(cuts):
        cid = c.get("id", f"#{i}")
        said = c.get("narration", "")
        if c.get("speaker") != "narrator":
            ng.append(f"{cid} の speaker は narrator（語りは1人）")
        if len(said) > CUT_MAX:
            ng.append(f"{cid} が {len(said)}字（1カット{CUT_MAX}字まで）")
        for x in nums(TIME.sub("", said + c.get("hook", ""))):
            if x not in have:
                ng.append(f"{cid} の数字 {x} が、時刻でも facts.json でも day_facts でもない")
        w = tease(said + c.get("hook", ""))
        if w:
            ng.append(f"{cid}：答えを先送りするだけの文「{w}」")
        if c.get("clock"):
            if not re.fullmatch(r"\d{1,2}:\d{2}", c["clock"]):
                ng.append(f"{cid} の clock「{c['clock']}」（例 22:00）")
            clocks.append(c["clock"])
        if c.get("chart"):
            continue
        if not c.get("image") or not c.get("image_en"):
            ng.append(f"{cid} に image と image_en がない")
        if re.search(r"[ぁ-んァ-ヶ一-龠]", c.get("image_en", "")):
            ng.append(f"{cid} の image_en に日本語がある（読める文字が絵に出る）")
        if c.get("angle") not in ANGLES:
            ng.append(f"{cid} の angle は {ANGLES} のどれか")
        angles.append(c.get("angle"))
        hero += bool(c.get("chars"))
    if len(clocks) < 5:
        ng.append(f"時刻のカット {len(clocks)}（5以上）")
    span, limit = shift_hours([c for c in clocks if re.fullmatch(r"\d{1,2}:\d{2}", c)]), shift_limit(passed)
    if span > limit:
        ng.append(f"最初の時刻から最後の時刻まで {span:g}時間（{clocks[0]}〜{clocks[-1]}。1本は1回の勤務で{limit}時間まで）")
    charts = [c for c in cuts if c.get("chart")]
    if len(charts) != 1:
        ng.append('年収のカットは1つ（"chart": "pay"）')
    elif charts[0] is cuts[-1]:
        ng.append("年収のカットのあとに、ひとひねりの1カットを置く")
    elif fx["職業"]["声の年収"].lstrip("約") not in charts[0].get("narration", ""):
        ng.append(f"年収のカットの声に {fx['職業']['声の年収']} がない")
    for a in zip(angles, angles[1:], angles[2:]):
        if len(set(a)) == 1:
            ng.append(f"同じ向き（{a[0]}）が3カット続く")
            break
    if cuts and hero < (len(cuts) - 1) * 0.6:
        ng.append(f"主役の出る絵が {hero}（6割以上。人のいない絵が続かないように）")
    motion = sum(bool(c.get("motion")) for c in cuts)
    if not 2 <= motion <= 3:
        ng.append(f"動く絵 {motion}（2〜3）")
    if not any(c.get("peak") for c in cuts):
        ng.append('山場のカットに "peak": true を書く')
    sents = lambda s: [x for x in re.split(r"(?<=[。？！?!])", s) if x.strip()]
    if cuts and sents(cuts[0].get("narration", "")) and len(sents(cuts[0]["narration"])[0]) > FIRST_MAX:
        ng.append(f"1文目が {len(sents(cuts[0]['narration'])[0])}字（{FIRST_MAX}字まで）")
    if cuts and sents(cuts[-1].get("narration", "")) and len(sents(cuts[-1]["narration"])[-1]) > LAST_MAX:
        ng.append(f"最後の1文が {len(sents(cuts[-1]['narration'])[-1])}字（{LAST_MAX}字まで）")
    hook = cuts[0].get("hook", "") if cuts else ""
    if not hook or max(len(x) for x in hook.split("\n")) > 7 or hook.count("\n") > 1:
        ng.append(f"1カット目の hook「{hook}」（1行7字・2行まで）")
    allv = text + sc.get("title", "") + hook + sc.get("desc_lead", "")
    for w in banned() + META:
        if w in allv:
            ng.append(f"使わない言葉「{w}」")
    t = sc.get("title", "")
    if not t or len(t) > 60:
        ng.append(f"タイトル {len(t)}字（ハッシュタグ込みで60字まで）")
    if t in used_titles():
        ng.append("タイトルが前に作った回と同じ（二重防止で上げられない）")
    if fx["呼び名"] not in t or "1日" not in t:
        ng.append(f"タイトルに「{fx['呼び名']}」と「1日」を入れる")
    for w in ("AI", "PR"):
        if w in t:
            ng.append(f"タイトルに「{w}」")
    if not sc.get("desc_lead"):
        ng.append("desc_lead がない")
    print(f"字数 {n}・カット {len(cuts)}・時刻 {len(clocks)}・動く絵 {motion}・照合 {len(set(good))}件")
    for x in ng:
        print("NG", x)
    for x in warn:
        print("注意", x)
    print(f"NG {len(ng)}件・注意 {len(warn)}件")
    return not ng


if __name__ == "__main__":
    sys.exit(0 if check(os.path.abspath(sys.argv[1])) else 1)

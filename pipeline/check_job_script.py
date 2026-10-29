# 仕事チャンネルの台本の点検（手順書 §4・§6・§7・§10 のうち、プログラムで見られる物）
#   python -X utf8 pipeline\check_job_script.py <作業フォルダ>
# ・作業フォルダに script.json と facts.json があること
# ・スキルの check_script.py --long も一緒に回す（図のカット（chart）は絵の指示があるものとして渡す）
# ・判定のAI（Claude Sonnet）で見る項目（事実の裏取り・似すぎ・広告に向くか・続きを見たくなるか・押したくなるか）は、ここでは見ない
import json, os, re, subprocess, sys, tempfile, unicodedata
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from check_psy_script import tease  # 答えの先送りの見分け方（心理学chと同じ。references/16 の6）

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILL_CHECK = os.path.join(ROOT, "vendor", "youtube-video-maker", "scripts", "check_script.py")
CPS = 6.0  # check_script.py と同じ読む速さ（声の速さ 1.0 の時）
# 声の速さ（profile の voicevox の語り手）。2026-10-29 に 1.05 にした（手順書 §2）。見込みの長さは CPS×SPEED で割る
SPEED = json.load(open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "channels", "job", "profile.json"),
                       encoding="utf-8")).get("voicevox", {}).get("narrator", {}).get("speed", 1.0)

LINE3 = "人の手では数えきれない統計をプログラムで計算し、AIで映像と声にしています。数字は全部、出典と照らしています。"
# メタの言葉（手順書 §4「メタの禁止」）：名乗り・動画や回のこと・進み方・お礼・今日。登録の呼びかけ・LINE の案内・コメントへの問いかけのカットは除く
META = ("ミナト", "案内役", "この動画", "本動画", "この回", "今回", "前回", "次回", "次の回", "チャンネル", "視聴", "ご覧",
        "見ていただ", "聞いていただ", "ありがとうございました", "ここから", "ここまで", "この後", "このあと", "次の章", "前の章",
        "この章", "次の検証", "おさらい", "まとめると", "振り返", "見ていき", "見てみ", "紹介します", "説明します", "お伝えし",
        "お話しし", "出していき", "を始めます", "始めましょう", "クイズです", "採点結果です", "AIの結論です", "今日", "今夜", "舞台裏", "概要欄")
SUB = {1: "働き方の数字を、統計から届けています。続きが気になった方は、チャンネル登録で応援してもらえると励みになります。",
       2: "このチャンネルでは、仕事や会社を、統計の数字で見ています。次の回も見たい方は、チャンネル登録をお願いします。",
       3: "次の回も、別の職場の数字を届けます。見逃したくない方は、チャンネル登録をしておいてください。"}
LINE_AC = {1: "〇〇を含む、主な職業の年収と労働時間を、1枚の表にまとめました。概要欄のLINEから受け取れます。",
           2: "自分の仕事の年収が、ほかの職業と比べてどのあたりか。一覧表で確かめられます。概要欄のLINEからどうぞ。",
           3: "〇〇の年収と、〇〇を含む産業の離職率を、ほかの職業と並べた表を作りました。概要欄のLINEから受け取れます。"}
LINE_D = {1: "主な職業の年収と働く時間、年齢別に転職で年収が上がった人の割合を、2つの一覧表にまとめました。概要欄のLINEから受け取れます。",
          2: "自分の仕事の年収と、自分の年齢で転職した人の年収の変わり方。2つの一覧表で確かめられます。概要欄のLINEからどうぞ。",
          3: "職業ごとの年収の一覧と、年齢別の転職の一覧を、セットでお届けしています。概要欄のLINEから受け取れます。"}
LINE_B = {1: "転職して年収が上がった人と下がった人の割合を、年齢別の一覧にまとめました。概要欄のLINEから受け取れます。",
          2: "あなたの年齢で会社を移った人は、年収がどう変わったか。一覧表で確かめられます。概要欄のLINEからどうぞ。",
          3: "この回で出てきた〇〇歳の数字を含めて、年齢別の一覧表を作りました。概要欄のLINEから受け取れます。"}
E_STAT = "このサービスは、政府統計総合窓口(e-Stat)のAPI機能を使用していますが、サービスの内容は国によって保証されたものではありません。"
LISTENER_TICS = ["えっ", "それ、うち", "つまり"]

# 型A-1・A-3・B・C で使える図の種類（make_charts_job.py にある物。A-4 と型D は今までどおり別に見る）
KINDS = {"A-1": ("reasons", "job_vs_all", "quiz", "formula", "tokuten"),
         "A-3": ("compare_table", "quiz", "formula", "tokuten"),
         "B": ("bars", "quiz", "tokuten"),
         "C": ("vs_national", "age_line", "quiz", "formula", "tokuten")}
# 型B の A社の物語の数字（手順書 §10）：お金・割合・量の単位だけを探す。時の言い方は探さない
B_NUM = re.compile(r"約?(\d[\d,\.]*)(万円|億円|円|%|割|万|億|倍|件|社|人)")
KANJI_NUM = re.compile(r"(?<![\d.,])[〇一二三四五六七八九十百千]+(?=万円|億円|円|%|％|割|万|億|倍|件|社|人)")
# A-3 の項目の言い方（声で別の言い方をする時）
A3_ALIAS = {"年収": ["年収"], "月の労働時間": ["月の労働時間", "働く時間", "働いた時間", "労働時間"],
            "時給に直した額": ["時給"], "勤続年数": ["勤続"]}
OPPOSITE = {"高い": "低い", "低い": "高い", "長い": "短い", "短い": "長い"}

# 声に出る数字：数字＋お金・割合・時間・量の単位（手順書 §10）。兆円・ポイントは型D で使う
NUM = re.compile(r"約?(\d[\d,\.]*)(万円|兆円|円|%|割|億|倍|件|社|人|時間|日分|日|か月|ポイント|年(?!目))")

# 型D（AI検証）の決まり（手順書 §3 型D・§4・§10）
D_CHARTS = ("score_bars", "source_card", "test_compare", "trend_lines", "big_text", "quiz", "tokuten")
CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩"
RANK_WORD = re.compile(r"(\d+|[一二三四五六])位|最下位|\d+点(?!満点)")  # 順位の言葉と点数（「20点満点」は数えない）
GROUPS = ["若者", "若い世代", "高齢", "シニア", "中高年", "年寄り", "老人", "非正規", "正社員", "派遣", "パート", "女性", "男性",
          "氷河期", "団塊", "ゆとり", "Z世代", "外国人", "新卒", "おじさん", "おばさん"]
G_RE = "|".join(GROUPS)
# 期間の言い方・決まった言い回しの中の数字は、値として数えない
SKIP = ["1日8時間で数えると", "1か月", "1年", "1時間", "1日", "1枚", "1人ずつ", "1冊ずつ"]
# 順位の範囲（2026-10-28 本人「バス運転手は年収1位のやつと大型トラック運転手は年収1位、どちらも1位なの？」→ どちらも6つの中での1位だった）
# 「6つの中で」は何の6つかが分からないので数えない（2026-10-28 本人「意味わからなくない？メタになってない？」）
# 型A・B・C で「〇位」「最下位」と言う時は、何の中の順位か（「6職種で」「144職種で」）を同じ所に書く。型D は採点の順位なので除く
SCOPE = re.compile(r"(\d+|[一二三四五六七八九十]+)(つの仕事|つの職業|職種|業種|職業|人|社)(の中|中)?で")


def rank_unscoped(text):
    """順位の言葉があるのに、何の中の順位かが無い"""
    t = unicodedata.normalize("NFKC", text or "")
    return bool(re.search(r"\d+位|最下位", t)) and not SCOPE.search(t)


RANK_NUM = re.compile(r"\d+位")  # 順位（tokens は単位つきの値だけを拾うので、数字の合計（§0）と見出しの数字の数ではこれも数える）
THUMB_KINDS = ("判定", "落差", "自分ごと", "謎", "裏側")  # 手順書 §6 のサムネの字の型
HOW_TAIL = re.compile(r"[（(][^）)]*統計[^）)]*[）)]|統計で(並べ|追っ|比べ|計算)|を並べた")  # 出典・作り方の尾（§6。2026-10-29 から付けない）


def nums(text, small_rank=True):
    """見る人に数字として見える物（単位つきの値と順位）。small_rank=False は1桁の順位（A-4 の6職業の1〜6位など、覚えなくても追える物）を数えない"""
    t = unicodedata.normalize("NFKC", text or "")
    return tokens(t) + [r for r in RANK_NUM.findall(t) if small_rank or len(r) > 2]


def tokens(text):
    t = text
    for s in SKIP:
        t = t.replace(s, "")
    return [m.group(1).replace(",", "") + m.group(2) for m in NUM.finditer(t)]


def job_names(facts):
    """facts.json の職業名。A-4・A-3 は職業の行の並び、A-1・C は職業名の文字1つ、型B・D は無し"""
    j = facts.get("職業")
    if isinstance(j, str):
        return [j]
    if isinstance(j, list):
        return [r["表示名"] for r in j if isinstance(r, dict) and "表示名" in r]
    return []


def b_sources(facts):
    """型B で数字の照らしに使う文字：統計の 声・言い直し・表の値・計算、グラフの表示、題の前提の数"""
    out = list(facts.get("premise_numbers", []))
    for st in facts.get("統計", {}).values():
        out += [st.get("声", ""), st.get("表の値", ""), st.get("計算", "")] + list(st.get("言い直し", []))
    for g in facts.get("グラフ", []):
        out += [b.get("表示", "") for b in g.get("棒", [])]
    return [s for s in out if isinstance(s, str) and s]


def kanji_to_digits(t):
    """漢数字（三割・五十万円）を算用数字に直す（単位の前にある物だけ）"""
    def conv(m):
        if m.group(0) == "一" and m.string[m.end():m.end() + 1] in ("人", "社"):  # 「先輩の一人が」「一社だけ」は数の値として数えない
            return m.group(0)
        total, cur = 0, 0
        for ch in m.group(0):
            if ch in "十百千":
                total += (cur or 1) * {"十": 10, "百": 100, "千": 1000}[ch]
                cur = 0
            else:
                cur = "〇一二三四五六七八九".index(ch)
        return str(total + cur)
    return KANJI_NUM.sub(conv, t)


def b_tokens(text):
    """型B の A社の物語の数字（円・%・割・万・億・倍・件・社・人だけ。漢数字も直して探す）"""
    t = kanji_to_digits(unicodedata.normalize("NFKC", text))
    for s in SKIP:
        t = t.replace(s, "")
    out = []
    for m in B_NUM.finditer(t):
        u = "万円" if m.group(2) == "万" else m.group(2)
        out.append(m.group(1).replace(",", "") + u)
    return out


def trivia_tokens(facts):
    """facts.json の 豆知識（手順書 §0。書き手が公的なページで確かめて足す）の数字"""
    ok = set()
    for x in facts.get("豆知識") or []:
        if isinstance(x, dict):
            ok.update(tokens(str(x.get("文", ""))))
    return ok


def allowed_from(facts):
    """facts.json にある値を、声で言える形の集合にする"""
    ok = set()
    if facts.get("type") == "B":  # 型B は統計の値・グラフの表示・題の前提の数だけ（期間の区切りの「24年」などを拾わない）
        for s in b_sources(facts):
            ok.update(tokens(s))
        ok.update(trivia_tokens(facts))  # 豆知識（手順書 §0）
        return ok

    def walk(v):
        if isinstance(v, str):
            ok.update(tokens(v))
        elif isinstance(v, dict):
            for x in v.values():
                walk(x)
        elif isinstance(v, list):
            for x in v:
                walk(x)
    walk(facts)
    rows = [r for r in facts.get("職業", []) if isinstance(r, dict)] if isinstance(facts.get("職業"), list) else []
    rows += [facts[k] for k in ("この職業の数字", "全産業の平均", "業界の平均") if isinstance(facts.get(k), dict)]  # A-1・C
    for r in rows:
        for k in ("月の労働時間", "うち所定内", "うち残業など（超過）"):
            if k in r:
                ok.add(f"{r[k]}時間")
    for v in facts.get("言い直し", {}).values():
        if "月_時間" in v:
            ok.update({f"{v['月_時間']}時間", f"{v['年_時間']}時間"})
        for k in ("月の労働時間の差", "年の労働時間の差"):  # A-3 の2職業の差
            if isinstance(v, dict) and isinstance(v.get(k), (int, float)):
                ok.add(f"{abs(v[k]):g}時間")
    for k in ("比べ_全産業の平均", "比べ_業界の平均"):  # A-1・C の全産業との差
        for kk in ("月の労働時間の差", "年の労働時間の差"):
            if isinstance(facts.get(k, {}).get(kk), (int, float)):
                ok.add(f"{abs(facts[k][kk]):g}時間")
    if facts.get("type") == "D":  # 「容疑者は5人」の数
        ok.add(f"{len(facts.get('容疑者', []))}人")
    return ok


# ここから型D（AI検証）
def d_top_label(titles, facts):
    """サムネD の1位の棒に出す名前。タイトルで1位の名前を出す回はその名前、伏せる回は「？」（手順書 §3 型D・§6）。
    make_thumb_job.py もこれを使う。3案で出す・伏せるが混ざっている時は None"""
    top = facts.get("1位", [])
    named = [any(n in t for n in top) for t in titles]
    if titles and all(named):
        return list(top)
    if not any(named):
        return ["？"] * max(1, len(top))
    return None


def d_role(name):
    if "決め手" in name:
        return "決め手"
    if "AIで検証" in name:
        return "検証"
    for key, role in (("おさらい", "おさらい"), ("コメントから", "コメント"), ("採点結果", "採点"), ("結論", "結論"),
                      ("まとめ", "締め"), ("締め", "締め")):
        if key in name:
            return role
    return "その他"


def d_recalc(facts):
    """facts.json の点数・順位を、data\\scoring_rank.json で計算し直して比べる（台本を書く人が facts.json を書き換えていないか）"""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import d_facts
    rank = json.load(open(os.path.join(ROOT, "data", "scoring_rank.json"), encoding="utf-8"))
    topic = next((k for k, v in rank["題"].items() if v["題"] == facts.get("題")), None)
    if not topic:
        return None, "data\\scoring_rank.json に、この題の物差しが無い"
    try:
        res = d_facts.run(topic)[4]
        how = "統計の表の値から"
    except (OSError, KeyError):
        ms = {t["id"]: {"値": t["値"]} for r in facts["結果"] for t in r["確かめ"]}
        res = d_facts.judge(rank, topic, ms)
        how = "facts.json の確かめの値から"
    return [(r["名前"], r["点数"], r["順位"], r["同点の決め手"]) for r in res], how


def check_d(sc, facts, cuts, chars, ng, warn):
    """型D の点検（手順書 §10 の「型D：」の項目のうち、プログラムで見られる物）"""
    sus = [s["名前"] for s in facts.get("容疑者", [])]
    res = {r["名前"]: r for r in facts.get("結果", [])}
    ranks = {n: r["順位"] for n, r in res.items()}
    scores = {n: r["点数"] for n, r in res.items()}
    full = facts.get("満点", 20)
    top = facts.get("1位", [])
    last_rank = max(ranks.values()) if ranks else 0
    titles = sc.get("titles", [])

    # 1. facts.json：割り当て・点数・順位・棒の数
    for n in sus:
        r = res.get(n)
        if not r or not r.get("確かめ") or any(t.get("判定") not in ("支える", "反対", "どちらでもない") or not t.get("統計") for t in r["確かめ"]):
            ng.append(f"facts.json の「{n}」に、支える・反対の統計の割り当てが無い")
    got, how = d_recalc(facts)
    if got is None:
        ng.append(how)
    else:
        mine = [(r["名前"], r["点数"], r["順位"], r["同点の決め手"]) for r in facts.get("結果", [])]
        if sorted(got) != sorted(mine):
            ng.append(f"facts.json の点数・順位が、物差しで計算し直した値（{how}）と違う：{sorted(set(got) ^ set(mine))}（d_facts.py make を回し直す）")
    if sorted(top) != sorted(n for n in ranks if ranks[n] == 1):
        ng.append(f"facts.json の1位 {top} が、結果の順位と合わない")
    bars = facts.get("点のグラフ", {}).get("棒", [])
    if len(bars) > 6 or len(sus) > 6:
        ng.append(f"点数の棒が {len(bars)} 本（6本まで）")
    if [(b["名前"], b["点数"]) for b in bars] != sorted([(n, scores[n]) for n in scores], key=lambda x: (ranks[x[0]], sus.index(x[0])))[:6]:
        ng.append("facts.json の点のグラフの棒が、結果の点数・順位と合わない")

    # 2. 説の名前：人の集団を責める言い方
    for n in sus:
        if re.search("増えた|のせい|犯人", n) or (re.search(G_RE, n) and not re.search("割合|構成|変化|比率", n)):
            ng.append(f"説の名前が人の集団を責める形：{n}（「〇〇の割合の変化」「〇〇の構成の変化」のように要因として立てる）")
    for c in cuts:
        if re.search(f"増えた({G_RE})|({G_RE})(が|の)?せい|犯人は({G_RE})", c["narration"]):
            ng.append(f"人の集団を問題の犯人として名指す言い方：{c['id']}")

    # 3. 章（つかみ・前置きには chapter を付けず、2章として数える）
    if cuts[0].get("chapter"):
        ng.append("つかみのカットに chapter がある（つかみ・前置きには付けない。2章として数える）")
    spans = []
    for i, c in enumerate(cuts):
        if c.get("chapter"):
            spans.append([c["chapter"], i, len(cuts)])
    for k in range(len(spans) - 1):
        spans[k][2] = spans[k + 1][1]
    n_chap = len(spans) + 2
    if not 14 <= n_chap <= 18:
        ng.append(f"章が {n_chap}（つかみ・前置きを入れて14〜18）")
    roles = [d_role(s[0]) for s in spans]
    seq = "".join({"その他": "o", "検証": "v", "決め手": "k", "おさらい": "r", "コメント": "c", "採点": "s", "結論": "e", "締め": "z"}[r] for r in roles)
    if not re.fullmatch(r"ov{5,6}k{2,3}rc?sez", seq):
        ng.append("章の並びが骨組みと違う：" + " → ".join(f"{s[0]}（{r}）" for s, r in zip(spans, roles))
                  + "（AIが最初にやったこと → AIで検証①〜 → 決め手の統計2〜3 → おさらい →（コメントから）→ 採点結果 → 結論 → まとめ）")
    nums = [re.search("AIで検証([" + CIRCLED + "])", s[0]) for s in spans]
    nums = [m.group(1) for m in nums if m]
    if nums != list(CIRCLED[:len(nums)]):
        ng.append(f"「AIで検証①」からの番号が順に振られていない：{nums}")
    if "c" in seq:
        hp = os.path.join(ROOT, "history", "job", "produced.json")
        h = json.load(open(hp, encoding="utf-8")) if os.path.exists(hp) else []
        if not any(x.get("type") == "D" for x in h):
            warn.append("初めての型D の回に「コメントから」の章がある（手順書 §3 型D の7）")
    span = {r: s for s, r in zip(spans, roles) if r not in ("検証", "決め手", "その他")}
    vs = [s for s, r in zip(spans, roles) if r == "検証"]
    order = []
    for s in vs:
        hit = [n for n in sus if n in s[0]]
        if len(hit) != 1:
            ng.append(f"検証の章の名前に、facts.json の説の名前が1つだけ入っていない：{s[0]}")
        else:
            order.append(hit[0])
    if sorted(order) != sorted(sus):
        ng.append(f"検証の章の説が facts.json の説と合わない：章 {order}／facts {sus}")
    chap_of = {}
    for s in spans:
        for i in range(s[1], s[2]):
            chap_of[i] = s

    # 4. クイズ（説2と説4の章の頭）・説ごとの図・図の参照先
    for k in (1, 3):
        if k < len(vs):
            q = [i for i in range(vs[k][1], vs[k][2]) if cuts[i].get("quiz")]
            if not q:
                ng.append(f"説{k + 1}の章にクイズが無い：{vs[k][0]}")
            elif q[0] - vs[k][1] > 2:
                warn.append(f"説{k + 1}の章のクイズが章の頭（最初の3カット）に無い：{cuts[q[0]]['id']}")
    for s in vs:
        if not any((cuts[i].get("chart") or {}).get("kind") in ("test_compare", "trend_lines", "source_card") for i in range(s[1], s[2])):
            ng.append(f"検証の章に統計の図か出典カードが無い：{s[0]}")
    tests = {t["id"] for r in facts.get("結果", []) for t in r["確かめ"]}
    s_start = span["採点"][1] if "採点" in span else len(cuts)
    for i, c in enumerate(cuts):
        ch = c.get("chart")
        if not ch:
            continue
        k = ch.get("kind")
        if k not in D_CHARTS:
            ng.append(f"型D で使えない図の種類：{c['id']} {k}（{'・'.join(D_CHARTS)}）")
        elif k == "score_bars" and i < s_start:
            ng.append(f"採点結果の章より前に採点の棒グラフ：{c['id']}")
        elif k in ("source_card", "test_compare") and ch.get("test") not in tests:
            ng.append(f"図の確かめ {ch.get('test')} が facts.json に無い：{c['id']}")
        elif k == "source_card" and ch.get("test") not in facts.get("出典カード", {}):
            ng.append(f"facts.json の出典カードに {ch.get('test')} が無い：{c['id']}（d_facts.py make を回し直す）")
        elif k == "trend_lines":
            g = facts.get("グラフ", {}).get(ch.get("group"))
            if not g or not ch.get("series") or len(ch["series"]) > 2 or any(not isinstance(g.get(x), dict) for x in ch["series"]):
                ng.append(f"線の図の group・series が facts.json のグラフに無いか、3本以上：{c['id']}")
        elif k == "big_text" and not ch.get("text"):
            ng.append(f"big_text に text が無い：{c['id']}")
        if k == "source_card":  # 出典カードは6秒以上（後に続く same_as のカットも数える）
            n = len(c["narration"]) + sum(len(x["narration"]) for x in cuts[i + 1:i + 6] if x.get("same_as") == c["id"])
            if n / CPS < 6:
                warn.append(f"出典カードが {n / CPS:.1f} 秒しか出ない（6秒以上）：{c['id']}")
    if "採点" in span and not any((cuts[i].get("chart") or {}).get("kind") == "score_bars" for i in range(*span["採点"][1:])):
        ng.append("採点結果の章に採点の棒グラフ（score_bars）が無い")

    # 5. 採点結果の章より前に、順位の言葉と点数が無いか（おさらい・コメントからも含む）
    for i in range(min(s_start, len(cuts))):
        c = cuts[i]
        ch = c.get("chart") or {}
        txt = " ".join([c["narration"], c.get("label", ""), ch.get("text", ""), ch.get("question", ""), " ".join(ch.get("choices", []))])
        m = RANK_WORD.search(txt)
        if m:
            ng.append(f"採点結果の章より前に順位か点数：{c['id']}「{m.group(0)}」")
    allowed_txt = allowed_from(facts)
    for c in cuts:
        ch = c.get("chart") or {}
        bad = [t for t in tokens(ch.get("text", "") + ch.get("question", "")) if t not in allowed_txt]
        if bad:
            ng.append(f"図の文字に facts.json にない数字：{c['id']} {bad}")

    # 6. おさらい：説の名前を、検証の章と同じ順に一度だけ
    if "おさらい" in span:
        rs = span["おさらい"]
        txt = "".join(cuts[i]["narration"] for i in range(rs[1], rs[2]))
        lis = "".join(cuts[i]["narration"] for i in range(rs[1], rs[2]) if cuts[i].get("speaker") == "listener")
        pos = [txt.find(n) for n in order]
        if any(p < 0 for p in pos) or pos != sorted(pos):
            ng.append(f"おさらいの説の名前が、検証の章と同じ順に全部出ていない（章の順：{order}）")
        many = [n for n in order if txt.count(n) > 1]
        if many:
            warn.append(f"おさらいで2回以上出た説の名前：{many}（一度だけ言い直す）")
        if any(n not in lis for n in order):
            warn.append("おさらいの説の名前を、聞き手が言っていない所がある（聞き手が言い直す）")

    # 7. 採点結果の章から後：声の点数・順位が facts.json と合うか
    spoken = set()
    for i in range(s_start, len(cuts)):
        for snt in re.split(r"(?<=[。！？])", cuts[i]["narration"]):
            names = [n for n in sus if n in snt]
            pts = [int(x) for x in re.findall(r"(\d+)点(?!満点)", snt)]
            rk = [int(x) for x in re.findall(r"(\d+)位", snt)]
            if i < span.get("採点", [None, len(cuts), len(cuts)])[2]:
                spoken.update(pts)
            for p in pts:
                if p not in scores.values() and p != full:
                    ng.append(f"facts.json にない点数：{cuts[i]['id']} {p}点")
            if len(names) == 1:
                n = names[0]
                if any(p != scores[n] for p in pts):
                    ng.append(f"「{n}」の点数が facts.json（{scores[n]}点）と違う：{cuts[i]['id']}")
                if any(r != ranks[n] for r in rk):
                    ng.append(f"「{n}」の順位が facts.json（{ranks[n]}位）と違う：{cuts[i]['id']}")
                if "最下位" in snt and ranks[n] != last_rank:
                    ng.append(f"「{n}」は最下位ではない：{cuts[i]['id']}")
    if len(spoken) >= 3:
        warn.append(f"採点結果の章で声に出る点数が {len(spoken)} つ：{sorted(spoken)}（声は1位と最下位の点だけ）")
    ends = {scores[n] for n in scores if ranks[n] in (1, last_rank)}
    if spoken - ends:
        warn.append(f"1位と最下位のほかの点数を声で言っている：{sorted(spoken - ends)}")

    # 8. LINE の案内の2回目：採点結果 → 結論 → LINE → 締め
    li = [i for i, c in enumerate(cuts) if "概要欄のLINE" in c["narration"]]
    if len(li) == 2 and "結論" in span and "締め" in span:
        if not span["結論"][1] < li[1] < span["締め"][1]:
            ng.append(f"LINE の案内の2回目が、結論の章の後・締めの前に無い：{cuts[li[1]]['id']}")

    # 9. タイトル：AI の出し方・意外な・1位の名前・同点
    say = facts.get("題の言い方", "")
    names_ok = {say[:-3]} if say.endswith("だけで") else set()
    stats = facts.get("e-Statにある統計", []) + facts.get("e-Statにない統計", [])
    if len(stats) == 1:
        names_ok.add(re.sub(r"^.*「|」.*$", "", stats[0]))
    for t in titles:
        a = t.find("AI")
        if a < 0 or a + 2 > 32:
            ng.append(f"型D のタイトルの「AI」が前の32字に無い：{t}")
        m = re.search(r"AIに(.+?)だけで(?:採点|検証)させ", t)
        if not m and re.search(r"AIが(?:採点|検証)", t):
            m = re.search(r"([^\s、。：:？！…｜【】]+?)だけで", t)
        if not m:
            ng.append(f"タイトルに「AIに〈出典名〉だけで採点（検証）させたら」の形が無い：{t}")
        elif m.group(1) not in names_ok:
            ng.append(f"「だけで」の前の名前「{m.group(1)}」が、使った統計を全部覆う名前でない（facts.json の題の言い方：{say}）：{t}")
        if "意外な" in t and not facts.get("意外なを使える"):
            ng.append(f"「意外な」はこの回では使えない（1位が予想どおりか同点。facts.json の 意外なを使える）：{t}")
        if facts.get("1位が同点"):
            if not ("1位は" in t and all(n in t for n in top)) or "意外な" in t or "差はたった" in t:
                ng.append(f"1位が同点の回は「1位は{'と'.join(top)}」の形で、「意外な」「差はたった」を使わない：{t}")
        m1 = re.search(r"1位は(.+)", t)
        if m1 and not any(m1.group(1).startswith(n) for n in top):
            ng.append(f"タイトルの「1位は」の後が facts.json の1位（{top}）でない：{t}")
        second = max([s for n, s in scores.items() if n not in top], default=None)
        for x in re.finditer(r"(\d+)点(?!満点)", t):
            ok = set(scores.values()) | {full} | ({scores[top[0]] - second} if top and second is not None else set())
            if int(x.group(1)) not in ok:
                ng.append(f"タイトルの点数が facts.json に無い：{t} {x.group(0)}")
        d = re.search(r"差はたった(\d+)点", t)
        if d and top and second is not None and int(d.group(1)) != scores[top[0]] - second:
            ng.append(f"タイトルの「差はたった{d.group(1)}点」が facts.json（{scores[top[0]] - second}点）と違う：{t}")
    if d_top_label(titles, facts) is None:
        ng.append("タイトル3案で、1位の名前を出す案と伏せる案が混ざっている（回ごとに1つに決める。サムネD の1位の棒もそろえる）")

    # 10. 絵の数・画面の配分
    imgs = [c for c in cuts if c.get("image") and not c.get("chart")]
    if len(imgs) > 70:
        ng.append(f"AIの絵が {len(imgs)} 枚（型D は70枚まで。残りは図・出典カード）")
    sw = ["絵" if c.get("image") and not c.get("chart") else ("出典カード" if (c.get("chart") or {}).get("kind") == "source_card" else "図")
          for c in cuts if not c.get("same_as")]
    run = 1
    for k in range(1, len(sw)):
        run = run + 1 if sw[k] == sw[k - 1] else 1
        if run == 5:
            warn.append(f"同じ種類の画面（{sw[k]}）が5枚以上続く所がある（4枚まで）")
            break
    if sw and sw.count("絵") / len(sw) > 0.4:
        warn.append(f"場面の絵が画面の {sw.count('絵') / len(sw):.0%}（目安は約3割。図・グラフ・出典カードを主に）")


# ここから型A-1・A-3・B・C（手順書 §3・§10）
def spans_of(cuts):
    """章の範囲 [名前, 始め, 終わり]。最初の chapter の前は（つかみ・前置き）"""
    out = [["（つかみ・前置き）", 0, len(cuts)]]
    for i, c in enumerate(cuts):
        if c.get("chapter"):
            out[-1][2] = i
            out.append([c["chapter"], i, len(cuts)])
    return out


def check_intro_name(cuts, name, ng, warn):
    """型B・C：前置きの中で、語り手が「統計の平均から作った、平均的な〇〇さん（会社、A社）」と1回だけ紹介し、名札にも1回出す"""
    if not name:
        ng.append("facts.json に主役（A社）の呼び名が無い（*_facts.py make を回し直す）")
        return
    sp = spans_of(cuts)[0]
    n_in = sum(c["narration"].count(name) for c in cuts[sp[1]:sp[2]] if c["speaker"] == "narrator")
    n_all = sum(c["narration"].count(name) for c in cuts)
    if n_in != 1 or n_all != 1:
        ng.append(f"前置きの中に、語り手の「{name}」の紹介がちょうど1回ない（前置き {n_in} 回・全体 {n_all} 回）")
    tags = [c["id"] for c in cuts if c.get("label") == name]
    if len(tags) != 1:
        warn.append(f"名札（label が「{name}」のカット）が {len(tags)} 回（紹介のカットで1回）")


def check_charts(sc, facts, cuts, fkey, ng):
    """図の種類と、図が指す facts.json の値があるか（数字そのものは make_charts_job.py が facts.json から取る）"""
    for c in cuts:
        ch = c.get("chart")
        if not ch:
            continue
        k = ch.get("kind")
        if k not in KINDS[fkey]:
            ng.append(f"{fkey} で使えない図の種類：{c['id']} {k}（{'・'.join(KINDS[fkey])}）")
        elif k == "reasons" and not 0 <= (ch.get("shown") or 0) <= 5:
            ng.append(f"辞める理由の図の shown は0〜5：{c['id']}")
        elif k == "job_vs_all":
            have = [b["物差し"] for b in facts.get("棒グラフ", {}).get("棒", [])]
            ms = ch.get("measures") or []
            if not ms or len(ms) > 3 or any(m not in have for m in ms):
                ng.append(f"job_vs_all の measures は facts.json の棒グラフの物差しから1〜3つ：{c['id']} {ms}（{have}）")
        elif k == "bars":
            g = ch.get("graph", 0)
            if not isinstance(g, int) or not 0 <= g < len(facts.get("グラフ", [])):
                ng.append(f"bars の graph が facts.json のグラフの番号に無い：{c['id']} {g}")
        elif k == "vs_national":
            have = [r["物差し"] for r in facts.get("全国平均と並べる表", [])]
            its = ch.get("items") or []
            if not its or len(its) > 3 or any(x not in have for x in its):
                ng.append(f"vs_national の items は facts.json の全国平均と並べる表から1〜3つ：{c['id']} {its}（{have}）")
            if ch.get("highlight") and ch["highlight"] not in its:
                ng.append(f"vs_national の highlight が items に無い：{c['id']}")
        elif k == "age_line":
            ages = [r["年齢階級"] for r in facts.get("年齢別", [])]
            if ch.get("measure", "年収_万円") not in ("年収_万円", "月の労働時間", "時給に直した額_円"):
                ng.append(f"age_line の measure は 年収_万円・月の労働時間・時給に直した額_円：{c['id']}")
            if any(x not in ages for x in ch.get("marks", [])) or len(ch.get("marks", [])) > 5:
                ng.append(f"age_line の marks は facts.json の年齢別の年齢階級から5つまで：{c['id']}")


def check_a1(sc, facts, cuts, ng, warn):
    """A-1 理由の数え上げ：辞める理由は5位から1位へ・2位の前にクイズ（1位は選択肢に入れない）・前置きの文・定義と出典"""
    if not facts.get("定義", {}).get("辞める理由") or not any(x.get("key") == "koyodoko_r7_t12" for x in facts.get("出典", [])):
        ng.append("facts.json に辞める理由の定義か出典（雇用動向調査 第12表 koyodoko_r7_t12）が無い（a1_facts.py make を回し直す）")
    five = facts.get("辞める理由_5つ", [])
    if len(five) != 5:
        ng.append(f"facts.json の辞める理由が {len(five)} つ（5つ取れない題は使わない）")
    rs = [(i, c) for i, c in enumerate(cuts) if (c.get("chart") or {}).get("kind") == "reasons"]
    shown = [c["chart"].get("shown") or 0 for _, c in rs]
    if not shown or max(shown) < 5:
        ng.append("辞める理由の図（reasons）で1位まで出していない（5位から1位へ）")
    if shown != sorted(shown):
        ng.append(f"辞める理由の図の shown が、5位から1位へ出す順になっていない：{shown}")
    pre = [p for p in (facts.get("声の前置き"), facts.get("声の前置き_より正確な言い方")) if p]
    said = next((i for i, c in enumerate(cuts) if any(p in c["narration"] for p in pre)), None)
    first = next((i for i, c in rs if (c["chart"].get("shown") or 0) >= 1), None)
    if said is None:
        ng.append(f"離職理由の前置きの文（{pre[0] if pre else '声の前置き'}）を声で言っていない（手順書 §3 A-1・§10）")
    elif first is not None and said > first:
        ng.append(f"離職理由の前置きの文が、理由を出し始めた後にある：{cuts[said]['id']}（5位を出す前に言う）")
    # クイズ：2位を出す前。1位は選択肢に入れない。選択肢は facts.json のクイズのとおり
    two = next((i for i, c in rs if (c["chart"].get("shown") or 0) >= 4), None)
    qs = [i for i, c in enumerate(cuts) if c.get("quiz")]
    if two is None or not any(q < two for q in qs):
        ng.append("辞める理由の2位を出す前にクイズが無い（手順書 §3 A-1）")
    qz, top = facts.get("クイズ", {}), facts.get("1位", [])
    for i in qs:
        ch = cuts[i].get("chart") or {}
        cs = ch.get("choices") or qz.get("選択肢", [])
        if any(t in cs for t in top):
            ng.append(f"クイズの選択肢に1位の理由が入っている：{cuts[i]['id']}")
        if ch.get("choices") and sorted(ch["choices"]) != sorted(qz.get("選択肢", [])):
            ng.append(f"クイズの選択肢が facts.json のクイズの選択肢と違う：{cuts[i]['id']}")
    # 声で言う順も5位から1位へ（理由の言葉は facts.json の理由の（ ）の前まで）
    start = rs[0][0] if rs else 0
    pos = []
    for r in five:
        w = re.split(r"[（(]", r["理由"])[0]
        p = next((i for i in range(start, len(cuts)) if w in cuts[i]["narration"]), None)
        if p is None:
            warn.append(f"辞める理由「{w}」を声で言っていない（言い換える時も facts.json の理由の言葉を入れる）")
        else:
            pos.append(p)
    if pos != sorted(pos):
        ng.append("辞める理由を声で言う順が、facts.json の5位から1位の順と違う")


def check_a3(sc, facts, cuts, ng, warn):
    """A-3 似た職業との比べ：逆転がある組だけ・離職率を比べない・山場の項目・判定が facts.json と合うか"""
    if not facts.get("逆転を使える"):
        ng.append("facts.json の 逆転を使える が false（意外な逆転が無い組。A-3 には使えないので、次の題に回す）")
    items, peak = facts.get("比べる項目", []), facts.get("山場の項目")
    tables = [c for c in cuts if (c.get("chart") or {}).get("kind") == "compare_table"]
    if not tables:
        ng.append("A-3 の比べの表（compare_table）が無い")
    elif not any(c["chart"].get("highlight") for c in tables):
        ng.append(f"比べの表で、山場の項目（{peak}）を強調（highlight）していない")
    for c in tables:
        ch = c["chart"]
        its = ch.get("items") or items
        used = list(its) + list(ch.get("values", [])) + ([ch["highlight"]] if ch.get("highlight") else [])
        if any("離職率" in x for x in used):
            ng.append(f"離職率は2つの職業で同じ値になるので、比べる項目に入れない：{c['id']}")
        bad = [x for x in used if x not in items and "離職率" not in x]
        if bad:
            ng.append(f"比べの表の項目が facts.json の比べる項目に無い：{c['id']} {bad}")
        if ch.get("highlight") and ch["highlight"] != peak:
            ng.append(f"強調した項目 {ch['highlight']} が facts.json の山場の項目（{peak}）と違う：{c['id']}")
        nv = set(ch.get("values", [])) | ({ch["highlight"]} if ch.get("highlight") else set())
        if len(nv) > 3:
            ng.append(f"比べの表で数字を出す項目が {len(nv)} つ（1画面の数字は6個まで＝3項目まで）：{c['id']}")
    # 声の判定：「〇〇の方が高い（短い）」が facts.json の勝った方と逆になっていないか
    rows = {r["項目"]: r for r in facts.get("項目ごと", [])}
    js = job_names(facts)
    names = {n: j for j in js for n in (j, re.split(r"[（・]", j)[0])}
    if len(js) != 2:
        return
    pat = "(" + "|".join(map(re.escape, sorted(names, key=len, reverse=True))) + r")の方が、?(高い|低い|長い|短い)"
    for c in cuts:
        for snt in re.split(r"(?<=[。！？])", c["narration"]):
            m = re.search(pat, snt)
            hit = [it for it, al in A3_ALIAS.items() if it in rows and any(a in snt for a in al)]
            if not m or len(hit) != 1:
                continue
            r = rows[hit[0]]
            good, adj = r.get("よい方の向き"), m.group(2)
            if not good or not r.get("勝った方") or adj not in (good, OPPOSITE.get(good)):
                continue
            j = names[m.group(1)]
            winner = j if adj == good else next(x for x in js if x != j)
            if winner != r["勝った方"]:
                ng.append(f"「{hit[0]}」の言い方が facts.json の判定（{r['判定']}）と逆：{c['id']}")


def check_b(sc, facts, cuts, ng, warn):
    """型B 会社の決断の結末（手順書 §3 型B・§10）"""
    a = facts.get("A社", {})
    check_intro_name(cuts, a.get("呼び名"), ng, warn)
    frame = sc.get("frame")
    if frame not in facts.get("使える骨組み", []):
        why = facts.get("使えない骨組み", {}).get(frame, "")
        ng.append(f"骨組み {frame} は、この題では使えない（facts.json の使える骨組み：{facts.get('使える骨組み')}）{('：' + why) if why else ''}")
    # A社の場面：reenact の印と「イメージ」の札
    ids = {c["id"]: c for c in cuts}
    if not any(c.get("reenact") for c in cuts):
        ng.append("A社の場面のカットに reenact の印が無い（手順書 §3 型B・§10）")
    skip = [a.get("呼び名", "")] + facts.get("つなぎ", [])
    for c in cuts:
        src = ids.get(c.get("same_as"))
        if c.get("reenact"):
            if c.get("chart"):
                ng.append(f"図のカットに reenact の印：{c['id']}")
            if c.get("badge") != "イメージ":
                ng.append(f"A社の場面のカットに badge「イメージ」が無い：{c['id']}（右上に「イメージ」を出す）")
        elif src and src.get("reenact"):
            ng.append(f"A社の場面の絵を続けて使うカットに reenact・badge が無い：{c['id']}（{src['id']} と同じ絵）")
        elif "A社" in c["narration"] and c.get("image") and not any(s and s in c["narration"] for s in skip):
            warn.append(f"A社の話のカットに reenact の印が無い：{c['id']}（A社の場面なら reenact と badge「イメージ」）")
    # A社の物語の数字：統計の値・題の前提の数・骨組みの数（B-2 の4人）のほかは NG
    ok = set()
    for s in b_sources(facts):
        ok.update(b_tokens(s))
    if frame == "B-2":
        prof = json.load(open(os.path.join(ROOT, "channels", "job", "profile.json"), encoding="utf-8"))
        for s in prof.get("b_allow_numbers", []):
            ok.update(b_tokens(s))
    for c in cuts:
        if c.get("reenact"):
            bad = [t for t in b_tokens(c["narration"]) if t not in ok]
            if bad:
                ng.append(f"A社の物語のカットに統計にない数字：{c['id']} {bad}（A社の物語には数字を入れない）")
    # 全国の数字のつなぎ：統計の数字を含む章ごとに、最初の数字より前（つかみ・前置きは除く）
    tsunagi = facts.get("つなぎ", [])
    premise = {t for s in facts.get("premise_numbers", []) for t in b_tokens(s)}
    for name, s0, s1 in spans_of(cuts)[1:]:
        seen = None
        for i in range(s0, s1):
            c = cuts[i]
            if c.get("line") or c.get("subscribe"):
                continue
            hit = False
            for s in re.split(r"(?<=[。！？])", c["narration"]):
                found = set(tokens(s)) | set(b_tokens(s))
                if c.get("reenact"):  # A社の場面の題の前提の数（初任給30万円など）は A社の数なので、つなぎは要らない
                    found -= premise
                if any(x in s for x in tsunagi):
                    seen = i
                elif found:
                    if seen is None:
                        ng.append(f"章「{name}」の最初の統計の数字の前に、全国の数字のつなぎの文が無い：{c['id']}")
                    elif any(cuts[j].get("reenact") for j in range(seen + 1, i)):
                        warn.append(f"章「{name}」のつなぎの文と最初の数字の間に、A社の場面が入っている：{c['id']}（つなぎは数字の直前に）")
                    hit = True
                    break
            if hit:
                break
    # 山場の章の数字：facts.json の骨組みの山場の統計（声・言い直し・表の値）
    fr = facts.get("骨組み", {}).get(frame, {})
    node = fr.get("山場")
    if node:
        st = facts.get("統計", {}).get(fr.get(node), {})
        want = set()
        for s in [st.get("声", ""), st.get("表の値", "")] + list(st.get("言い直し", [])):
            want.update(tokens(s))
        sp = [x for x in spans_of(cuts)[1:] if node in x[0]]
        if not sp:
            ng.append(f"山場の章が無い（chapter の名前に「{node}」を入れる。骨組み {frame} の山場）")
        elif want and not want & {t for x in sp for i in range(x[1], x[2]) for t in tokens(cuts[i]["narration"])}:
            ng.append(f"山場の章「{sp[0][0]}」で、山場の数字（{st.get('声')}）を言っていない")
    body = "".join(c["narration"] for c in cuts if not c.get("line"))
    if "下がった" in body and "上がった" not in body:
        warn.append("「下がった」割合だけで、「上がった人」の割合を言っていない（facts.json の言い方の決まり。片方だけで言い切らない）")


def check_c(sc, facts, cuts, ng, warn):
    """型C 職業の1日（手順書 §3 型C・§10）"""
    frame = sc.get("frame")
    fr = facts.get("骨組み", {}).get(frame)
    if fr is None:
        ng.append(f"型C の frame は C-1・C-2・C-3 のどれか：{frame}")
    elif not fr.get("使える"):
        ng.append(f"骨組み {frame} は使えない：{fr.get('理由', '')}（facts.json の骨組み）")
    check_intro_name(cuts, facts.get("主役", {}).get("呼び方"), ng, warn)
    if frame == "C-3" and fr:
        want = set(tokens(fr.get("値", {}).get("声_年収の差", "")))
        if want and not want & {t for c in cuts for t in tokens(c["narration"])}:
            warn.append(f"C-3 の山場の数字（2人の年収の差 {fr['値']['声_年収の差']}）を声で言っていない")


HEDGE = re.compile(r"(この職業|この仕事)だけの(値|数字)ではありません|同じ人が年を取った数字ではありません|業界の数字なので")


def fun_check(sc, facts, cuts, warn):
    """手順書 §0 面白さの軸（2026-10-29）：豆知識・驚きの粒・label・語りの続き方・声の断り書き"""
    tv = [x for x in facts.get("豆知識") or [] if isinstance(x, dict)]
    if len(tv) < 3:
        warn.append(f"豆知識が {len(tv)} つ（1本3つ以上。facts.json の 豆知識 に出典つきで足す §0）")
    for i, x in enumerate(tv):
        if not (x.get("url") and x.get("原文") and x.get("文")):
            warn.append(f"豆知識 {i + 1} に 文・url・原文 のどれかが無い（公的なページで確かめた物だけ §0）")
    wow = [c for c in cuts if c.get("wow")]
    if len(wow) < 8:
        warn.append(f"驚きの粒（\"wow\": true）のカットが {len(wow)}（1本8つ以上。各章2つ以上 §0）")
    lab, chap = {}, None
    for c in cuts:
        chap = c.get("chapter") or chap
        if chap and not re.search("まとめ|締め", chap):
            lab[chap] = lab.get(chap, 0) + bool(c.get("label") or c.get("chart"))
    nolab = [k for k, v in lab.items() if not v]
    if nolab:
        warn.append(f"label（画面に大きく出る字）か図のカットが無い章：{nolab}（各章1つ以上 §0）")
    run, worst = 0, (0, None)
    for c in cuts:
        run = run + 1 if c.get("speaker") == "narrator" and not (c.get("line") or c.get("subscribe")) else 0
        if run > worst[0]:
            worst = (run, c["id"])
    if worst[0] >= 4:
        warn.append(f"語り手のカットが {worst[0]} 続く所がある（{worst[1]} まで。3つ続いたら聞き手のツッコミか問い §0）")
    hd = [c["id"] for c in cuts if HEDGE.search(c["narration"])]
    if len(hd) > 2:
        warn.append(f"声の断り書きが {len(hd)} 回（1本2回まで。残りは画面の出典・図の見出しに任せる §0）：{hd}")
    fc = sc.get("fun_core") or ""
    miss = [k for k in ("謎", "自分ごと", "判定") if k + "：" not in fc and k + ":" not in fc]
    if fc and miss:
        warn.append(f"fun_core に {'・'.join(miss)} が無い（「謎：〜｜自分ごと：〜｜判定：〜」の形。§0 の1と2は毎回入れる）")
    # 数字の合計（§0。2026-10-29 本人「数字がありすぎても胃もたれしそう」）：声に出る統計の数字の種類と、豆知識を足した種類
    tv_tk = trivia_tokens(facts)
    said = {x for c in cuts if not (c.get("line") or c.get("subscribe")) for x in nums(c["narration"], small_rank=False)}
    stat = said - tv_tk
    d = sc.get("type") == "D"
    if len(stat) > (12 if d else 8):
        warn.append(f"声に出る統計の数字が {len(stat)} 種類（1本{12 if d else 8}種類まで。主役の数字3つに絞り、ほかは言葉の驚きにする §0）：{sorted(stat)}")
    if len(said) > (14 if d else 10):
        warn.append(f"豆知識の数字を足して {len(said)} 種類（1本{14 if d else 10}種類まで §0）")
    print(f"面白さの軸：fun_core＝{fc or '（無し）'}／主役の数字 {sc.get('key_numbers')}／声の数字 統計{len(stat)}・全部{len(said)}種類／豆知識 {len(tv)}／驚きの粒 {len(wow)}／語りの続き 最長{worst[0]}／声の断り書き {len(hd)}")


def key_check(sc, facts, cuts, allowed, ng, warn):
    """主役の数字（§0）：1〜3つ、facts.json の値で、声で言っている"""
    kn = sc.get("key_numbers")
    if not (isinstance(kn, list) and 1 <= len(kn) <= 3 and all(isinstance(x, str) and x for x in kn)):
        ng.append(f"key_numbers（主役の数字）は1〜3つの文字の並び：{kn}（§0）")
        return
    dump = unicodedata.normalize("NFKC", json.dumps(facts, ensure_ascii=False)).replace(",", "")
    voice = unicodedata.normalize("NFKC", "".join(c["narration"] for c in cuts)).replace(",", "")
    for x in kn:
        x_tk, x_rk = tokens(unicodedata.normalize("NFKC", x)), RANK_NUM.findall(unicodedata.normalize("NFKC", x))
        if not x_tk and not x_rk:
            ng.append(f"key_numbers の {x} に数字が無い（§0）")
            continue
        if [k for k in x_tk if k not in allowed] or [r for r in x_rk if r[:-1] not in dump]:
            ng.append(f"key_numbers の {x} が facts.json の値でない（§0）")
        if not all(k.lstrip("約") in voice for k in x_tk + x_rk):
            warn.append(f"key_numbers の {x} を声で言っていない（主役の数字は 予想→出す→言い直す→反応 の4拍で §0）")


def main(work):
    sc = json.load(open(os.path.join(work, "script.json"), encoding="utf-8"))
    facts = json.load(open(os.path.join(work, "facts.json"), encoding="utf-8"))
    cuts = sc["cuts"]
    ng, warn = [], []
    allowed = allowed_from(facts) | trivia_tokens(facts)
    jobs = job_names(facts)
    short = {j: re.split(r"[（・]", j)[0] for j in jobs}  # 「理学療法士など（リハビリ職）」→「理学療法士など」
    typ = sc.get("type")
    fkey = sc.get("frame") if typ == "A" else typ  # 図の種類の表（KINDS）の行。A-4 と型D は今までどおり

    # 1. スキルの点検（図のカットは絵があるものとして渡す）
    tmp = tempfile.mkdtemp()
    sc2 = json.loads(json.dumps(sc))
    for c in sc2["cuts"]:
        if c.get("chart") and not c.get("image"):
            c["image"] = "（図）"
    json.dump(sc2, open(os.path.join(tmp, "script.json"), "w", encoding="utf-8"), ensure_ascii=False)
    r = subprocess.run([sys.executable, "-X", "utf8", SKILL_CHECK, tmp, "--long"], capture_output=True, text=True, encoding="utf-8")
    print("【スキルの点検】\n" + r.stdout.strip())
    warn += [l[3:].strip() for l in r.stdout.splitlines() if l.startswith("注意:")]

    # 2. 項目
    for k in ("type", "frame", "fun_core", "target", "hook_type", "sub_copy", "line_copy"):
        if not sc.get(k):
            ng.append(f"台本の項目 {k} が空")
    if not sc.get("pub_date"):
        warn.append("pub_date（公開日）が空。在庫に入れる時に入れる")
    nos = [c["id"] for c in cuts if c.get("speaker") not in ("narrator", "listener")]
    if nos:
        ng.append(f"speaker が無いカット：{nos[:8]}")
    if typ in ("B", "C") and not sc.get("cast"):
        ng.append("型B・C の台本の項目 cast（主役の年齢・髪・服。全カットで同じ言葉）が空")
    # 登場人物（手順書 §5）：chars はチャンネルの characters.json か、この回の characters にある人だけ。人のいない絵は3割まで
    cp = os.path.join(ROOT, "channels", "job", "characters", "characters.json")
    known = dict(json.load(open(cp, encoding="utf-8")).get("chars", {})) if os.path.exists(cp) else {}
    for k, v in (sc.get("characters") or {}).items():
        if not (isinstance(v, dict) and v.get("desc_en") and v.get("name")):
            ng.append(f"この回の登場人物 {k} に name か desc_en が無い")
        known[k] = v
    pics = [c for c in cuts if c.get("image") and not c.get("chart") and not c.get("same_as")]
    for c in pics:
        cs = c.get("chars", [])
        if [x for x in cs if x not in known] or len(cs) > 2:
            ng.append(f"chars が characters.json にも この回の characters にも無いか、3人以上：{c['id']} {cs}")
    if typ in ("B", "C") and not any("hero" in c.get("chars", []) for c in pics):
        ng.append("型B・C の主役（characters の hero）が出るカットが無い")
    empty = [c["id"] for c in pics if not c.get("chars") and re.search("人は描かない|人を描かない|人はいない|無人", c["image"])]
    if pics and len(empty) / len(pics) > 0.3:
        warn.append(f"人のいない場面の絵が {len(empty)}/{len(pics)} 枚（3割まで。登場人物が何かをしている場面に）")
    if pics and not any(c.get("chars") for c in pics):
        warn.append("登場人物（chars）が出る絵が1枚も無い（手順書 §5）")
    for c in cuts:
        for k in c.get("chars", []):  # 型B・C の主役（hero）は前置きで呼び名を1回言うので除く
            nm = known.get(k, {}).get("name", "").split("（")[0]
            if k != "hero" and nm and nm in c["narration"]:
                warn.append(f"絵だけの登場人物の名前を声で言っている：{c['id']} {known[k]['name']}")
    if fkey in KINDS:
        if not any(c.get("chart") for c in cuts) or not facts.get("出典"):
            ng.append("自前データの図のカットが無いか、facts.json に出典が無い")
        check_charts(sc, facts, cuts, fkey, ng)

    # 3. 長さ（型A・B・C は字数とカット、型D は20〜25分。字数は同じ読む速さで割って出す）
    chars = sum(len(c["narration"]) for c in cuts)
    is_d = sc.get("type") == "D"
    if not is_d:
        if not 3400 <= chars <= 4200:
            ng.append(f"字数 {chars}（3,400〜4,200）")
        if not 105 <= len(cuts) <= 135:
            ng.append(f"カット {len(cuts)}（105〜135）")
        if chars / (CPS * SPEED) < 480:
            ng.append(f"見込み {chars / (CPS * SPEED) / 60:.1f} 分（8分以上。声の速さ {SPEED}）")
        switches = sum(1 for c in cuts if not c.get("same_as"))
        if not 85 <= switches <= 90:
            warn.append(f"画面の切り替わり {switches}（設計書 §5⑥ の 85〜90）")
    else:
        if not 20 * 60 <= chars / (CPS * SPEED) <= 25 * 60:
            ng.append(f"見込み {chars / (CPS * SPEED) / 60:.1f} 分・字数 {chars}（型D は20〜25分＝{int(20 * 60 * CPS * SPEED):,}〜{int(25 * 60 * CPS * SPEED):,}字。声の速さ {SPEED}）")
        if not 200 <= len(cuts) <= 300:
            ng.append(f"カット {len(cuts)}（型D は200〜300）")
        check_d(sc, facts, cuts, chars, ng, warn)

    # 4. 聞き手
    L = [c for c in cuts if c["speaker"] == "listener"]
    rate = len(L) / len(cuts)
    if not 0.25 <= rate <= 0.40:
        ng.append(f"聞き手のカットが {rate:.0%}（2割5分〜4割。手順書 §2。掛け合いは器で、謎・予想・ツッコミ・自分ごとの時だけ出す）")
    aizuchi = [c["id"] for c in L if re.search(r"それ、?うち", c["narration"])]
    if len(aizuchi) > 3:
        warn.append(f"「それ、うちも」の形の相づちが {len(aizuchi)} 回（1本3回まで。予想・ツッコミ・置き換えにする §2）：{aizuchi}")
    for c in L:
        n_sent = len([s for s in re.split(r"(?<=[。！？])", c["narration"]) if s.strip()])
        if n_sent > 1 or len(c["narration"]) > 25:
            warn.append(f"聞き手のセリフが長い（1文・20字前後）：{c['id']} {len(c['narration'])}字")
        if c["narration"].startswith(("みなさん", "ミナト")) or "ミナトです" in c["narration"]:
            ng.append(f"名乗りは語り手だけ：{c['id']}")
    for i in range(len(L)):
        for tic in LISTENER_TICS:
            if tic in L[i]["narration"] and any(tic in x["narration"] for x in L[max(0, i - 2):i]):
                warn.append(f"聞き手の口癖「{tic}」が直近3カットで続いている：{L[i]['id']}")

    # 5. 数字（出典との照合・章ごとの数）
    chap, per, peak_ch = "（つかみ・前置き）", {}, set()
    trivia = trivia_tokens(facts) - {t for k, v in facts.items() if k != "豆知識" for t in tokens(json.dumps(v, ensure_ascii=False))}
    for c in cuts:
        if c.get("chapter"):
            chap = c["chapter"]
        tk = tokens(c["narration"])
        bad = [t for t in tk if t not in allowed]
        if bad and not (typ == "B" and c.get("reenact")):  # 型B の A社の場面は check_b で（時の言い方は探さない）
            ng.append(f"facts.json にない数字：{c['id']} {bad}")
        if c["speaker"] == "listener" and tk:
            warn.append(f"聞き手が数字を言っている（facts.json の値か確かめる）：{c['id']} {tk}")
        if c.get("line") or c.get("subscribe"):
            continue
        per.setdefault(chap, set()).update(t for t in tk if t not in trivia)
        if c.get("peak"):
            peak_ch.add(chap)
    for ch, s in per.items():  # 型D の採点結果の章は、1位と最下位の点を言うので別に見る
        lim = 3 if ch in peak_ch else 2
        if ch != "（つかみ・前置き）" and "採点結果" not in ch and len(s) > lim:
            warn.append(f"章「{ch}」で声に出る統計の数字が {len(s)} つ：{sorted(s)}（{lim}つまで。豆知識の数字は除く §4）")
    hook = re.split(r"(?<=[。！？])", cuts[0]["narration"])[0]
    if sc.get("hook_type") == "統計":
        ht = tokens(hook)
        if not ht or any(t not in allowed for t in ht):
            ng.append(f"つかみの1文目に facts.json の数字がない：{hook}")

    # 6. 位置（そのカットまでの字数の合計÷全体）
    acc, pos = 0, {}
    for c in cuts:
        acc += len(c["narration"])
        if "概要欄のLINE" in c["narration"]:
            pos.setdefault("line", []).append((c["id"], acc / chars))
        if "チャンネル登録" in c["narration"]:
            pos.setdefault("sub", []).append((c["id"], acc / chars))
    li, su = pos.get("line", []), pos.get("sub", [])
    if len(li) != (2 if is_d else 1):
        ng.append(f"LINE の案内が {len(li)} 回（型A・B・C は1回、型D は2回）")
    for k, (i, r_) in enumerate(li):
        if k == 0 and not 0.35 <= r_ <= 0.50:
            ng.append(f"LINE の案内の位置 {r_:.1%}（40〜45%の前後5%）：{i}")
        if k == 1 and not 0.92 <= r_ <= 0.98:  # 型D の2回目は結論の後・締めの前
            ng.append(f"LINE の案内の2回目の位置 {r_:.1%}（95%の前後3%）：{i}")
    if len(su) != 1:
        ng.append(f"登録の呼びかけが {len(su)} 回")
    for i, r_ in su:
        if not 0.60 <= r_ <= 0.70:
            ng.append(f"登録の呼びかけの位置 {r_:.1%}（65%の前後5%）：{i}")
    print(f"位置：LINE {[f'{i} {r_:.1%}' for i, r_ in li]}／登録 {[f'{i} {r_:.1%}' for i, r_ in su]}")

    # 7. 決まった文
    texts = [c["narration"] for c in cuts]
    if SUB.get(sc.get("sub_copy")) not in texts:
        ng.append(f"登録の呼びかけの文（sub_copy={sc.get('sub_copy')}）がカットに無い")
    if is_d:  # 型D は line_copy に2つ（1回目・2回目で別の文）
        lc = sc.get("line_copy")
        if not (isinstance(lc, list) and len(lc) == 2 and lc[0] != lc[1] and all(x in LINE_D for x in lc)):
            ng.append(f"型D の line_copy は、1〜3から違う2つの番号の並び：{lc}")
        elif [t for t in texts if t in LINE_D.values()] != [LINE_D[x] for x in lc]:
            ng.append(f"LINE の案内の文（line_copy={lc}）が、この順でカットに無い（§4 の型D の文のまま）")
    else:
        tpl = (LINE_B if typ == "B" else LINE_AC).get(sc.get("line_copy"), "")
        pat = "^" + re.escape(tpl).replace("〇〇", "(.+?)") + "$"
        hit = [re.match(pat, t) for t in texts]
        hit = [h for h in hit if h]
        if not hit:
            ng.append(f"LINE の案内の文（line_copy={sc.get('line_copy')}）がカットに無い")
        dump = json.dumps(facts, ensure_ascii=False)
        for h in hit:
            for g in h.groups():
                if typ == "B":  # 型B の③の〇〇歳は、facts.json にある年齢の区切り
                    if g + "歳" not in dump:
                        ng.append(f"LINE の案内の〇〇歳が facts.json に無い：{g}歳")
                elif not any(x in g for x in list(short.values()) + jobs):
                    ng.append(f"LINE の案内の〇〇が職業名でない：{g}")
    fixed = set(LINE_D.values()) | set(LINE_B.values()) | set(SUB.values())  # 決まった文は40字の決まりから外す
    # メタの言葉（§4）：呼びかけ・案内・コメントへの問いかけのカットと、型D の「コメントから」の章は除く
    lname = json.load(open(os.path.join(ROOT, "channels", "job", "profile.json"), encoding="utf-8")).get("listener", {}).get("name")
    chap = ""
    for c in cuts:
        chap = c.get("chapter") or chap
        t = c["narration"]
        if c.get("line") or c.get("subscribe") or re.search("概要欄のLINE|チャンネル登録|コメントで", t) or "コメントから" in chap:
            continue
        hit = [w for w in META if w in t]
        if hit:
            ng.append(f"メタの言葉（動画・回・進み方・名乗りのこと）：{c['id']} {hit}「{t[:30]}」")
        w = tease(t)
        if w:  # 2026-10-28 本人の指摘（スキル references/16 の6）。問いは出してよいが、答えを先に延ばすだけの文は書かない
            ng.append(f"答えを先送りするだけの文：{c['id']}「{w}」（中身で引く：次に分かることを具体的に言う。§4）")
        if lname and lname in t:
            ng.append(f"聞き手の名前を呼んでいる：{c['id']}（名前は呼ばない）")
    k = next((i for i, c in enumerate(cuts) if c.get("chapter")), 0)  # つかみ〜前置き（最初の章の前）の長さ（手順書 §4 の 40〜70秒）
    n = sum(len(c["narration"]) for c in cuts[:k])
    if k and not 40 <= n / CPS <= 70:
        warn.append(f"つかみ〜前置きが約{n / CPS:.0f}秒（{n}字）。手順書 §4 の目安は40〜70秒（約240〜420字）")
    for i, c in enumerate(cuts):  # 相づちの相手がいない（語り手の前のカットも語り手なのに「はい」「そうです」で始まる）
        if i and c.get("speaker") == "narrator" and cuts[i - 1].get("speaker") == "narrator" and re.match("(はい|そうです|ええ)[。、]", c["narration"]):
            ng.append(f"相づちの相手がいない：{c['id']}「{c['narration'][:20]}」（前のカットも語り手）")
    for c in cuts:
        if re.search("毎日|明日も", c["narration"]):
            ng.append(f"「毎日」「明日も」：{c['id']}")
        if "離職率" in c["narration"] and not re.search(r"(含む|業)の?離職率", c["narration"]):
            ng.append(f"離職率に業界名が無い：{c['id']}")
        for s in re.split(r"(?<=[。！？])", c["narration"]):
            if len(s) > 40 and c["narration"] not in fixed:
                ng.append(f"40字を超える文：{c['id']} {len(s)}字")

    # 7-2. 動く絵と見どころ（2026-10-28 本人の指摘「紙芝居」「見どころが無い」。スキル references/16 の2・4。手順書 §5）
    #   動く絵＝図のカット（chart。組み立てで動くグラフ・カードになる）。章ごとに1つ以上
    per_mv, chap = {}, None
    for c in cuts:
        chap = c.get("chapter") or chap
        if chap:
            per_mv[chap] = per_mv.get(chap, 0) + bool(c.get("chart"))
    for k, x in per_mv.items():
        if not x:
            ng.append(f"章「{k}」に図のカット（chart＝動くグラフ・カード）が無い（動く絵は章ごとに1つ以上。§5）")
    pk = [c for c in cuts if c.get("peak")]
    if not pk:
        ng.append("見どころのカットが無い：いちばん驚く数字が出るカットに \"peak\": true を書き、chart・label・strong のうち2つ以上を付ける（§5）")
    for c in pk:
        if sum(bool(c.get(x)) for x in ("chart", "label", "strong")) < 2:
            ng.append(f"見どころ（peak）{c['id']} に chart・label・strong のうち2つ以上が無い（§5）")
        if c in cuts[-6:] or c.get("line") or c.get("subscribe"):
            ng.append(f"見どころ（peak）{c['id']} が締め・案内・呼びかけのカットにある（本編の山に付ける）")
    print(f"見どころ（peak）：{[c['id'] for c in pk]}／図のカットの無い章 {[k for k, x in per_mv.items() if not x]}")
    fun_check(sc, facts, cuts, warn)
    key_check(sc, facts, cuts, allowed, ng, warn)

    # 8. 骨組み A-4：物差しごとに、2位を出す前にクイズ
    if sc.get("frame") == "A-4":
        for m in ("年収", "月の労働時間", "時給に直した額"):
            seq = [c for c in cuts if (c.get("chart") or {}).get("measure") == m]
            q = next((k for k, c in enumerate(seq) if c.get("quiz")), None)
            five = next((k for k, c in enumerate(seq) if (c["chart"].get("shown") or 0) >= 5), None)
            if q is None or five is None or q > five:
                ng.append(f"「{m}」の画面で、2位の前にクイズが無い")
        if not facts.get("逆転を使える") and any("逆転" in t for t in sc.get("titles", [])):
            ng.append("入れ替わりが2つ未満なのにタイトルに「逆転」")
        peak = [c for c in cuts if (c.get("chart") or {}).get("kind") == "rank_swap"]
        if peak and len(peak[0]["chart"]["jobs"]) > 3:
            ng.append("山場の職業が3つを超えている")
        if peak and any(j not in facts.get("山場の職業", []) for j in peak[0]["chart"]["jobs"]):
            warn.append("山場の職業が facts.json の 山場の職業 と違う")
    elif fkey in KINDS:  # 骨組み A-1・A-3・型B・型C
        {"A-1": check_a1, "A-3": check_a3, "B": check_b, "C": check_c}[fkey](sc, facts, cuts, ng, warn)
        if not facts.get("逆転を使える") and any("逆転" in t for t in sc.get("titles", [])):
            ng.append("タイトルに「逆転」があるのに、facts.json に入れ替わりの記録（逆転を使える）が無い")
    elif typ != "D":
        ng.append(f"type・frame の組がこの点検に無い：{typ} {sc.get('frame')}（A-1・A-3・A-4・B・C・D）")

    # 9. タイトル・サムネ・概要欄
    ts = sc.get("titles", [])
    if len(ts) != 3:
        ng.append(f"タイトルが {len(ts)} 案（3案）")
    for k, t in enumerate(ts):
        names = list(short.values()) + jobs
        if typ in ("A", "C") and not any(n in t[:15] for n in names):  # 型A・C だけ（§6。2026-10-29 から頭でなく前の15字。型B は決断の言葉、型D は「AI」の位置で見る）
            ng.append(f"タイトル{k + 1}案目の前の15字に職業名が無い：{t}")
        if len(t) > 40:
            warn.append(f"タイトル{k + 1}案目が {len(t)} 字（40字まで。前の20字で謎か判定か自分ごとの問いが分かるように §6）：{t}")
        if len(nums(t)) > 2:
            warn.append(f"タイトル{k + 1}案目の数字が {len(nums(t))} つ（1案に1つまで、落差の型でも2つまで §6）：{t}")
        if len({s for s in short.values() if s in t}) >= 3:
            warn.append(f"タイトル{k + 1}案目に職業名が3つ以上（羅列は表の見出しになる。1〜2つにする §6）：{t}")
        if HOW_TAIL.search(unicodedata.normalize("NFKC", t)):
            warn.append(f"タイトル{k + 1}案目に出典・作り方の尾（出典は概要欄と画面。§6）：{t}")
        if typ == "B" and not any(n in t for n in facts.get("A社", {}).get("題の呼び名", ["平均的な会社", "統計から作った会社"])):
            ng.append(f"型B のタイトルに「平均的な会社」か「統計から作った会社」が無い：{t}")
        if sc.get("type") != "D" and "AI" in t:
            ng.append(f"型A・B・C のタイトルに「AI」：{t}")
        if t.count("【") > 1:
            ng.append(f"【】が2つ以上：{t}")
        if "離職率" in t and not re.search(r"(含む|業)の?離職率", t):
            ng.append(f"タイトルの離職率に業界名が無い：{t}")
        head = unicodedata.normalize("NFKC", t).split("|")[0]  # 見る人がまず読む｜の前に、何の中の順位かを書く
        if typ != "D" and rank_unscoped(head):
            ng.append(f"タイトルの順位に、何の中の順位か（「6職種で」など）が｜の前に無い：{t}")
        for tk in tokens(t):
            if tk not in allowed:
                ng.append(f"タイトルに facts.json にない数字：{t} {tk}")
    # サムネ（§6。2026-10-27 から場面の形・判定の形。make_thumb_job.py の rules と同じ所を見る）
    nf = lambda k: unicodedata.normalize("NFKC", sc.get(k) or "")
    top, th, band = nf("thumb_top"), nf("thumb_text"), nf("thumb_band")
    if not th or len(th) > 10:
        ng.append(f"サムネの大きい字（thumb_text）は1〜10字：{th}（{len(th)}字）")
    if len(top) > 16:
        ng.append(f"サムネの見出し（thumb_top）は16字以内：{top}（{len(top)}字）")
    if not band or len(band) > 28:
        ng.append(f"サムネの下の帯（thumb_band）は1〜28字：{band}（{len(band)}字）")
    th_all = top + th + band
    if "離職率" in th_all and not re.search(r"(含む|業)の?離職率", th_all):
        ng.append(f"サムネの離職率に業界名（〇〇業の）が無い：{th_all}")
    if re.search(r"AI|PR", th_all.upper()):
        ng.append(f"サムネの字に AI か PR：{th_all}")
    if "逆転" in th_all and not facts.get("逆転を使える"):
        ng.append("サムネに「逆転」があるのに、facts.json に入れ替わりの記録（逆転を使える）が無い")
    if typ == "D" and "意外" in th_all and not facts.get("意外なを使える"):
        ng.append("サムネに「意外」があるのに、この回は使えない（facts.json の 意外なを使える）")
    if typ != "D" and rank_unscoped(top + th):
        ng.append(f"サムネの順位に、何の中の順位か（「6職種で」など）が見出しか大きい字に無い：{top}／{th}")
    for x in (top, th, band):
        for tk in tokens(x):
            if tk not in allowed:
                ng.append(f"サムネに facts.json にない数字：{x} {tk}")
    if ts:  # タイトルとサムネで同じ言葉をくり返さない（§6。2026-10-29 のゲートの試しで、どの回でも減点された）
        t0 = unicodedata.normalize("NFKC", ts[0])
        for n in list(short.values()) + jobs:
            t0 = t0.replace(n, "")
        dup = sorted({w for w in re.findall(r"[一-鿿゠-ヿ]{2,}", top + th) if w in t0})
        if dup:
            warn.append(f"タイトル1案目とサムネの字に同じ言葉：{dup}（片方が謎、もう片方が手がかり。§6）")
    kind = sc.get("thumb_kind")
    if kind not in THUMB_KINDS:
        warn.append(f"thumb_kind（サムネの字の型）が {'・'.join(THUMB_KINDS)} のどれでもない：{kind}（§6）")
    else:
        hp = os.path.join(ROOT, "history", "job", "produced.json")
        past = [x.get("thumb_kind") for x in (json.load(open(hp, encoding="utf-8")) if os.path.exists(hp) else [])
                if x.get("work") != os.path.basename(os.path.abspath(work))][-3:]
        if kind in past:
            warn.append(f"thumb_kind「{kind}」が直近3本と同じ型（直近：{past}。§6）")
    n_th = len(nums(top)) + len(nums(th)) + len(nums(band))
    if n_th > 2:
        warn.append(f"サムネの字の数字が {n_th} つ（3つの字で1つまで、落差の型でも2つまで §6）：{top}／{th}／{band}")
    if th and not re.sub(r"[約\d.,万億円%割倍時間日か月位年人件社点のはがもで、。！？!?\s]", "", th):
        warn.append(f"サムネの大きい字が数字と単位だけ（謎・判定・自分ごとの言葉にする §6）：{th}")
    if re.search(r"統計で|並べた|厚生労働省|政府統計", band):
        warn.append(f"サムネの下の帯が作り方・出典の説明（謎を一段深くする一言に §6）：{band}")
    bgc = next((c for c in cuts if c["id"] == sc.get("thumb_bg")), None)
    if not bgc or bgc.get("chart") or not bgc.get("image"):
        ng.append(f"thumb_bg が絵のカットの id でない：{sc.get('thumb_bg')}")
    elif not bgc.get("chars"):
        warn.append(f"サムネの絵（{bgc['id']}）に登場人物（chars）がいない。人の顔が大きく写るカットに")
    desc = sc.get("desc", "")
    paras = [p for p in desc.split("\n\n")]
    if len(paras) < 3 or paras[2].strip() != LINE3:
        ng.append("概要欄の3つ目の段落が §7 の文と一致しない")
    if "LINEで無料で受け取れます" not in paras[0]:
        ng.append("概要欄の1つ目に特典の名前と「LINEで無料で受け取れます」が無い")
    if re.search(r"\bPR\b|ＰＲ", desc + "".join(ts)):
        ng.append("概要欄かタイトルに PR")
    if E_STAT not in desc or "を加工して作成" not in desc:
        ng.append("概要欄に e-Stat の1文か「を加工して作成」が無い")

    for w in warn:
        print("注意:", w)
    for n in ng:
        print("NG:", n)
    print(f"字数 {chars}／カット {len(cuts)}／聞き手 {len(L)}（{rate:.0%}）／見込み {chars / CPS / 60:.1f} 分")
    print("合格（Gemini の項目は別）" if not ng and not warn else f"→ NG {len(ng)}・注意 {len(warn)}")
    sys.exit(1 if ng else 0)


if __name__ == "__main__":
    main(sys.argv[1].rstrip("/\\"))

# 金運おきぬの台本の機械の点検（2026-10-29 新設／2026-10-30 制作ルール v1.7 に更新。手順書 = 制作ルール v1.7 の §1〜§3・§5・§8・§9・§10・§12・§13・§15、ショートの型 v2 の「型1・型2」の表）
#   python -X utf8 pipeline\check_okinu_script.py <作業フォルダ> [--kind short|long|cut]
# ・種類は neta.json の kind（無ければ script.json の format と funnel から）。short＝単独／cut＝長尺の切り出し／long＝長尺
# ・NG が1つでもあれば終了コード1。「注意」は直せる物は直す（落とさない）
# ・スキルの check_script.py（引っ張り・動く絵・見どころ・作り話の決まり・声の名前）も回して、NG をそのまま出す
# ・ショートの型 v2 を数える（単独のショート）：型1（NG3つの数え下げ）＝290〜360字・第3位70〜90／第2位70〜90／第1位90〜110字・1文目に「3つ」・最後が「あなたの〇〇には、いくつ入っていましたか。」／
#   型2（1つだけ禁止）＝250〜300字・1文目「〇〇に、これを置いていませんか。」・最後「あなたの〇〇には、置いてありませんか。」。共通：1文最長27字・最初の文字（hook）5字×2行・
#   絵7〜9枚・動く絵2つ以上・字幕は声と同じ字（subs をつなぐと narration になる）で1行8字まで・効果音なし・題は【年代】の有無を問わない。型は neta.json の「型」（無ければ「第3位」の有無で見る）
# ・長尺（v1.7 §15 の順位の型）：字数 3,800〜5,000・カット130〜190・第5位〜第1位の rank カード・まとめの rules（nums）・モンタージュ・伏線は40%より前／答えは50%より後・山場・Kling 6つ以上・
#   使えるカードは rank／rules／big_text／two_cards／photo だけ・題は【金運】で終わる・題が履歴の題と 0.55 以上似ていない・サムネ（thumb.layout 4種）が直近2本と違う型（直近6本で2回まで）
import argparse, glob, json, os, re, shutil, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILL_CHECK = os.path.join(ROOT, "vendor", "youtube-video-maker", "scripts", "check_script.py")
CH_DIR = os.path.join(ROOT, "channels", "okinu")
CPS = 6.0
MARKS = ["──", "—", "→", "…", "※", "★"]
POSES = os.path.join(CH_DIR, "assets", "poses")
LAYOUTS = ("object", "person", "split", "shock")
# 手で作った回のサムネの型（002 から。007 は順位の絵＝4つの型の外の手作り。クラウドには OneDrive が無いので history/okinu/scripts/ の thumb.layout と produced.json の thumb_kind も見る）
HAND_LAYOUT = {"002": "shock", "003": "shock", "004": "split", "005": "object", "006": "person", "007": "rank"}
LONG_CARDS = ("rank", "rules", "big_text", "two_cards", "photo")
TITLE_LINE = 0.55  # title_guard.py と同じ線


def num_of(name):
    """作業フォルダ名・回の名前の頭の番号（006_台所のNG5→006／S101_…→S101／long_006→006）"""
    m = re.match(r"^(?:long_|short_)?(S?\d+)", os.path.basename(name))
    return m.group(1) if m else os.path.basename(name)


def history_titles(skip_num=""):
    """履歴の題（公開済み・自動で作った回・手で作った回の写し）。同じ番号の回（作業フォルダ自身）は外す"""
    out = []
    hist = os.path.join(ROOT, "history", "okinu")
    for f in ("uploaded.json", "uploaded_auto.json", "produced.json"):
        try:
            rows = json.load(open(os.path.join(hist, f), encoding="utf-8"))
        except Exception:
            continue
        for r in rows if isinstance(rows, list) else []:
            if num_of(r.get("work", "")) == skip_num:
                continue
            for k in [r.get("title")] + list(r.get("titles") or []):
                if k:
                    out.append(k)
    for p in glob.glob(os.path.join(hist, "scripts", "*.json")):
        if num_of(p[:-5]) == skip_num:
            continue
        try:
            k = json.load(open(p, encoding="utf-8")).get("title")
        except Exception:
            k = None
        if k:
            out.append(k)
    return sorted(set(out))


def recent_layouts(skip_num=""):
    """長尺のサムネの型を古い順に [(番号, 型)]。手で作った回→history の写し→produced.json の thumb_kind"""
    seen = {k: v for k, v in HAND_LAYOUT.items() if k != skip_num}
    hist = os.path.join(ROOT, "history", "okinu")
    for p in sorted(glob.glob(os.path.join(hist, "scripts", "*.json"))):
        try:
            x = json.load(open(p, encoding="utf-8"))
        except Exception:
            continue
        lay = (x.get("thumb") or {}).get("layout") or x.get("thumb_kind")
        n = num_of(p[:-5])
        if lay in LAYOUTS and n != skip_num and not n.startswith("S"):
            seen[n] = lay
    try:
        for r in json.load(open(os.path.join(hist, "produced.json"), encoding="utf-8")):
            n = num_of(r.get("work", ""))
            if r.get("thumb_kind") in LAYOUTS and n != skip_num and not n.startswith("S"):
                seen[n] = r["thumb_kind"]
    except Exception:
        pass
    return sorted(seen.items())


def words(ch_dir=CH_DIR, soft=False):
    """禁止表現.txt の語。「---文脈で判定---」の行より下が soft（単純な一致では落とさず、台本ゲートが文脈で見る）"""
    out, is_soft = [], False
    for l in open(os.path.join(ch_dir, "禁止表現.txt"), encoding="utf-8"):
        if l.startswith("# ---文脈で判定"):
            is_soft = True
        elif l.strip() and not l.startswith("#") and is_soft == soft:
            out.append(l.strip())
    return out


def n_chars(t):
    """字数。スキルの check_script.py と同じく句読点も数える（空白と改行だけ除く。S001 は273字）"""
    return len(re.sub(r"\s", "", t))


def kind_of(work, s, forced):
    if forced:
        return forced
    neta = os.path.join(work, "neta.json")
    if os.path.exists(neta):
        k = json.load(open(neta, encoding="utf-8")).get("kind")
        if k:
            return k
    if s.get("format") == "long":
        return "long"
    return "cut" if (s.get("funnel") or {}).get("kind") == "切り出し" else "short"


def check(work, kind=None):
    s = json.load(open(os.path.join(work, "script.json"), encoding="utf-8"))
    kind = kind_of(work, s, kind)
    cuts = s["cuts"]
    ng, warn = [], []
    chars_json = json.load(open(os.path.join(CH_DIR, "characters", "characters.json"), encoding="utf-8")).get("chars", {})
    ids = [c.get("id") for c in cuts]
    if len(set(ids)) != len(ids):
        ng.append("カットの id が重なっている")
    voiced = [c for c in cuts if c.get("narration")]
    text = "".join(c["narration"] for c in voiced)

    # 共通：禁止表現・禁止記号・「ひとつめ」。声に出す文・題・最初の文字・サムネの文字を見る
    shown = [(c["id"], c["narration"]) for c in voiced] + [("title", s.get("title", ""))] + \
            [(f"title{i + 1}", t) for i, t in enumerate(s.get("titles") or [])] + \
            [(f"{c['id']}.hook", c.get("hook", "")) for c in cuts if c.get("hook")] + \
            [("thumb", "／".join(str(v) for k, v in (s.get("thumb") or {}).items() if k in ("top", "big", "tag", "hl") and v))]
    for w in words():
        for i, t in shown:
            if w in t:
                ng.append(f"禁止表現「{w}」：{i}「{t[:30]}」")
    for i, t in shown:
        for m in MARKS:
            if m in t:
                ng.append(f"禁止記号「{m}」：{i}")
    for c in cuts:
        for ch in c.get("chars", []):
            if ch not in chars_json:
                ng.append(f"{c['id']}：characters.json に無い人物 {ch}")
    if s.get("fiction") and not s.get("world_rules"):
        ng.append("fiction: true なのに world_rules が無い（誰が何を知っているかを書く。手順書 §3）")
    for c in cuts:
        if c.get("narration") and ("、、" in c["narration"] or "。。" in c["narration"]):
            ng.append(f"{c['id']}：句読点が重なっている")

    # 概要欄（手順書 §10・ショートの型「説明」）
    desc = s.get("desc", "")
    for need, what in (("AI", "AI で作っていること"), ("VOICEVOX:波音リツ", "VOICEVOX:波音リツ"), ("創作", "物語は創作であること")):
        if need not in desc:
            ng.append(f"概要欄に「{what}」が無い")
    for k in (s.get("voices") or {}):  # 人物の声は characters.json の voice_name の名前で概要欄に書く（手順書 §10）
        nm = (chars_json.get(k, {}).get("voice_name") or "").split("（")[0]
        if nm and f"VOICEVOX:{nm}" not in desc:
            ng.append(f"概要欄に使った声「VOICEVOX:{nm}」が無い（手順書 §10）")
    if "{LONG_URL}" in desc and kind != "cut":
        ng.append("概要欄に {LONG_URL} が残っている")

    if kind == "short":
        check_short(work, s, cuts, voiced, text, desc, ng, warn)
    elif kind == "cut":
        n = n_chars(text)
        if not 270 <= n <= 300:
            ng.append(f"字数 {n}（270〜300字。型の表）")
        if not 13 <= len(voiced) <= 17:
            ng.append(f"文（カット）の数 {len(voiced)}（15文前後＝13〜17）")
        long_ = [(c["id"], len(c["narration"])) for c in voiced if len(c["narration"]) > 27]
        if long_:
            ng.append(f"1文が27字を超えるカット：{long_}")
        avg = n / max(1, len(voiced))
        if not 16 <= avg <= 21:
            warn.append(f"1文の平均 {avg:.1f}字（型は18〜19字）")
        if not re.search(r"ていませんか。?$", voiced[0]["narration"]):
            ng.append(f"1文目が「〜していませんか。」の形でない：{voiced[0]['narration']}")
        if not re.match(r"^あなたの.+(ですか|ますか)。?$", voiced[-1]["narration"]):
            ng.append(f"最後の文が「あなたの〇〇には、〜ですか。」の形でない：{voiced[-1]['narration']}")
        h = voiced[0].get("hook", "")
        hl = h.split("\n")
        if len(hl) != 2 or any(not 1 <= len(x) <= 5 for x in hl):
            ng.append(f"最初の文字（hook）が 5字×2行 でない：{h!r}")
        if sum(1 for c in cuts if c.get("hook")) != 1:
            ng.append("hook は1カット目だけ")
        peaks = [c["id"] for c in cuts if c.get("peak")]
        if len(peaks) != 1:
            ng.append(f"見どころ（peak）は1本に1つ：{peaks}")
        # 字幕：つなぐと声と同じ字になる・1行8字まで（手順書 §5）
        for c in voiced:
            sb = c.get("subs")
            if not sb:
                ng.append(f"{c['id']}：subs が無い（自動の字幕は語の途中で切れる。手順書 §5）")
                continue
            if re.sub(r"\s", "", "".join(sb)) != re.sub(r"\s", "", c["narration"]):
                ng.append(f"{c['id']}：subs をつなぐと narration と違う")
            for line in "\n".join(sb).split("\n"):
                if len(re.sub(r"[、。]$", "", line)) > 8:
                    ng.append(f"{c['id']}：字幕の1行が8字を超える「{line}」")
        if any(c.get("sfx") for c in cuts):
            ng.append("効果音（sfx）は入れない（手順書 §7）")
        if not s.get("tempo") == 1.3:
            warn.append(f"tempo {s.get('tempo')}（ショートは 1.3。手順書 §5）")
        t = s.get("title", "")
        if not re.match(r"^【[^】]+】", t) or len(t) > 30:
            ng.append(f"題が【年代】で始まる20字前後の形でない（{len(t)}字）：{t}")
        if kind == "short":
            imgs = [c["id"] for c in cuts if c.get("image_en") and not c.get("same_as")]
            if not 7 <= len(imgs) <= 8:
                ng.append(f"絵の数 {len(imgs)}（単独は7〜8枚。同じ絵の使い回しは same_as＋shots）")
            for c in cuts:
                if not c.get("image_en") and not c.get("same_as"):
                    ng.append(f"{c['id']}：image_en も same_as も無い")
            if len([c for c in cuts if c.get("motion")]) < 2:
                ng.append("motion: true が2カット未満（1カット目と見どころ。手順書 §6・make_motion_psy.py が動かす）")
            if not (cuts[0].get("motion") and any(c.get("peak") and c.get("motion") for c in cuts)):
                ng.append("1カット目と peak のカットの両方に motion: true を付ける")
            tail = [c for c in voiced[-3:] if "続き" in c["narration"] or "長い動画" in c["narration"]]
            if tail:
                ng.append("単独のショートに長尺へのつなぎ文がある（単独は概要欄だけでつなぐ。手順書 §13）")
            if not re.search(r"(昔から|言われて|言い伝え)", text):
                ng.append("言い伝えの言い方（昔から〜と言われています）が無い（型の表 6〜8文目）")
        else:
            f = s.get("funnel") or {}
            if not f.get("long"):
                ng.append("funnel.long（切り出し元の長尺の作業フォルダ名）が無い")
            if not any("長い動画" in c["narration"] for c in voiced[-3:-1]):
                ng.append("最後の問いの直前に、つなぐ1文（続きは、チャンネルの長い動画で。）が無い（手順書 §13）")
            if "本編（長い動画）：" not in desc:
                ng.append("概要欄に「本編（長い動画）：<URL>」が無い")
            for c in cuts:
                if not c.get("shots") and not c.get("same_as"):
                    ng.append(f"{c['id']}：切り出しは shots（長尺の絵の id）で書く")
        if "#shorts" not in desc or len(re.findall(r"#\S+", desc)) > 3:
            ng.append("概要欄のタグは #shorts と2つまで")
        if any(re.search(r"[0-9０-９]+万?円(?!玉)", c["narration"]) for c in voiced[:1]):
            warn.append("1文目に金額（金額と年齢は2文目以降に1つずつ）")
    else:
        check_long(work, s, cuts, voiced, text, desc, ng, warn)

    # スキルの点検（引っ張り・動く絵・作り話・声の名前）
    if os.path.exists(SKILL_CHECK):
        tmp = os.path.join(work, "check", "_skill_tmp")
        os.makedirs(tmp, exist_ok=True)
        json.dump({**s, "cuts": [{**c, "image": c.get("image") or c.get("image_en") or ("（切り出し）" if c.get("shots") else ("（共有ポーズ絵）" if c.get("img_from") else ("（モンタージュ）" if c.get("montage") else None)))} for c in cuts]},
                  open(os.path.join(tmp, "script.json"), "w", encoding="utf-8"), ensure_ascii=False)
        r = subprocess.run([sys.executable, "-X", "utf8", SKILL_CHECK, tmp] + (["--long"] if kind == "long" else []),
                           capture_output=True, text=True, encoding="utf-8")
        for l in r.stdout.splitlines():
            if l.startswith("NG"):
                ng.append("スキル " + l)
        shutil.rmtree(tmp, ignore_errors=True)
    else:
        warn.append("vendor/youtube-video-maker が無いのでスキルの点検は飛ばした")
    return kind, ng, warn, {"字数": n_chars(text), "カット": len(voiced), "見込み秒": round(n_chars(text) / CPS / (s.get("tempo") or 1) if kind != "long" else n_chars(text) / CPS)}


def check_short(work, s, cuts, voiced, text, desc, ng, warn):
    """単独のショート：ショートの型 v2（型1＝NG 3つの数え下げ／型2＝1つだけ禁止）"""
    neta = json.load(open(os.path.join(work, "neta.json"), encoding="utf-8")) if os.path.exists(os.path.join(work, "neta.json")) else {}
    typ = int(neta.get("型") or s.get("short_type") or (1 if "第3位" in text else 2))
    n = n_chars(text)
    lo, hi = (290, 360) if typ == 1 else (250, 300)
    if not lo <= n <= hi:
        ng.append(f"字数 {n}（型{typ}は {lo}〜{hi}字。ショートの型 v2）")
    if not 12 <= len(voiced) <= 22:
        ng.append(f"文（カット）の数 {len(voiced)}（型{typ}は15文前後＝12〜22）")
    long_ = [(c["id"], len(c["narration"])) for c in voiced if len(c["narration"]) > 27]
    if long_:
        ng.append(f"1文が27字を超えるカット：{long_}")
    first, last = voiced[0]["narration"], voiced[-1]["narration"]
    if typ == 1:
        if "3つ" not in first or not first.rstrip().endswith("。"):
            ng.append(f"型1の1文目が「〇〇に入れていると、お金が逃げる物、3つ。」の形でない（「3つ」で言い切る）：{first}")
        if not re.match(r"^あなたの.+いくつ.+か。?$", last):
            ng.append(f"型1の最後が「あなたの〇〇には、いくつ入っていましたか。」の形でない：{last}")
        # 第3位・第2位・第1位：それぞれ1回ずつ・この順。各順位の字数（70〜90／70〜90／90〜110。外れが大きい時だけ NG）
        idx = {}
        for k in ("第3位", "第2位", "第1位"):
            at = [i for i, c in enumerate(voiced) if k in c["narration"]]
            if len(at) != 1:
                ng.append(f"「{k}」を言うカットが {len(at)} つ（1つ。画面の真ん中に大きく1秒出す）")
            else:
                idx[k] = at[0]
        if len(idx) == 3 and not idx["第3位"] < idx["第2位"] < idx["第1位"]:
            ng.append("第3位→第2位→第1位の順になっていない")
        if len(idx) == 3:
            parts = {"第3位": voiced[idx["第3位"]:idx["第2位"]], "第2位": voiced[idx["第2位"]:idx["第1位"]], "第1位": voiced[idx["第1位"]:-1]}
            for k, (a, b, c) in {"第3位": (70, 90, 15), "第2位": (70, 90, 15), "第1位": (90, 110, 20)}.items():
                m = sum(n_chars(x["narration"]) for x in parts[k])
                if not a - c <= m <= b + c:
                    ng.append(f"{k}の字数 {m}（{a}〜{b}字。{a - c}〜{b + c}を外れた）")
                elif not a <= m <= b:
                    warn.append(f"{k}の字数 {m}（型は{a}〜{b}字）")
        if not any(c.get("band") for c in cuts):
            warn.append("帯（band・7字まで「お金が逃げる物」）が無い（途中から見た人にも何の動画か分かるように）")
    else:
        if not re.search(r"これ.*ていませんか。?$", first):
            ng.append(f"型2の1文目が「玄関に、これを置いていませんか。」の形でない：{first}")
        if not re.match(r"^あなたの.+(ませんか|ですか)。?$", last):
            ng.append(f"型2の最後が「あなたの玄関には、置いてありませんか。」の形でない：{last}")
    avg = n / max(1, len(voiced))
    if not 15 <= avg <= 22:
        warn.append(f"1文の平均 {avg:.1f}字")
    h = voiced[0].get("hook", "")
    hl = h.split("\n")
    if len(hl) != 2 or any(not 1 <= len(x) <= 5 for x in hl):
        ng.append(f"最初の文字（hook）が 5字×2行 でない：{h!r}")
    if sum(1 for c in cuts if c.get("hook")) != 1:
        ng.append("hook は1カット目だけ")
    peaks = [c["id"] for c in cuts if c.get("peak")]
    if len(peaks) != 1:
        ng.append(f"見どころ（peak）は1本に1つ：{peaks}")
    for c in voiced:  # 字幕：つなぐと声と同じ字になる・1行8字まで（手順書 §5）
        sb = c.get("subs")
        if not sb:
            ng.append(f"{c['id']}：subs が無い（自動の字幕は語の途中で切れる。手順書 §5）")
            continue
        if re.sub(r"\s", "", "".join(sb)) != re.sub(r"\s", "", c["narration"]):
            ng.append(f"{c['id']}：subs をつなぐと narration と違う")
        for line in "\n".join(sb).split("\n"):
            if len(re.sub(r"[、。]$", "", line)) > 8:
                ng.append(f"{c['id']}：字幕の1行が8字を超える「{line}」")
    if any(c.get("sfx") for c in cuts):
        ng.append("効果音（sfx）は入れない（手順書 §7）")
    if not s.get("tempo") == 1.3:
        warn.append(f"tempo {s.get('tempo')}（ショートは 1.3。手順書 §5）")
    t = s.get("title", "")
    if len(t) > 30 or len(t) < 12:
        ng.append(f"題が短すぎる／長すぎる（{len(t)}字。ショートの型 v2 は20〜28字）：{t}")
    elif not 20 <= len(t) <= 28:
        warn.append(f"題 {len(t)}字（20〜28字）：{t}")
    imgs = [c["id"] for c in cuts if c.get("image_en") and not c.get("same_as")]
    if not 7 <= len(imgs) <= 9:
        ng.append(f"絵の数 {len(imgs)}（単独は7〜9枚。同じ絵の使い回しは same_as＋shots）")
    for c in cuts:
        if not c.get("image_en") and not c.get("same_as"):
            ng.append(f"{c['id']}：image_en も same_as も無い")
    if len([c for c in cuts if c.get("motion")]) < 2:
        ng.append("motion: true が2カット未満（1カット目と第1位。手順書 §6・make_motion_psy.py が動かす）")
    if not (cuts[0].get("motion") and any(c.get("peak") and c.get("motion") for c in cuts)):
        ng.append("1カット目と peak のカットの両方に motion: true を付ける")
    if [c["id"] for c in voiced[-3:] if "続き" in c["narration"] or "長い動画" in c["narration"]]:
        ng.append("単独のショートに長尺へのつなぎ文がある（単独は概要欄だけでつなぐ。手順書 §13）")
    if not re.search(r"(昔から|言われて|言い伝え)", text):
        ng.append("言い伝えの言い方（昔から〜と言われています）が無い")
    if "#shorts" not in desc or len(re.findall(r"#\S+", desc)) > 3:
        ng.append("概要欄のタグは #shorts と2つまで")
    if re.search(r"[0-9０-９]+万?円(?!玉)", voiced[0]["narration"]):
        warn.append("1文目に金額（金額と年齢は2文目以降に1つずつ）")


def check_layout(th, cuts, ng, warn, num):
    """サムネ（制作ルール v1.7 §9）：型 4種・必須の項目・絵の id が台本にある・直近2本と同じ型なら NG・直近6本で2回まで"""
    lay = th.get("layout")
    if lay not in LAYOUTS:
        ng.append(f"thumb.layout が {LAYOUTS} のどれでもない：{lay!r}")
        return
    need = {"object": ("bg", "line1", "line2", "judge"), "person": ("bg", "line1", "line2", "judge"),
            "split": ("left", "right", "line1", "line2", "left_label", "right_label"), "shock": ("bg", "face", "line1", "line2", "judge")}[lay]
    for k in need:
        if not th.get(k):
            ng.append(f"thumb（{lay}）に {k} が無い")
    by_id = {c["id"]: c for c in cuts}
    for k in ("bg", "left", "right", "face"):
        v = th.get(k)
        if v and (v not in by_id or not (by_id[v].get("image_en") or by_id[v].get("image") or by_id[v].get("img_from") or by_id[v].get("same_as"))):
            ng.append(f"thumb.{k}「{v}」が、絵のあるカットの id でない")
    j = th.get("judge") or ""
    if j and not 4 <= len(j) <= 9:
        warn.append(f"判定の語 {len(j)}字「{j}」（画面の幅の6割以上に収まる4〜9字）")
    for k in ("line1", "line2"):
        if th.get(k) and len(th[k]) > 10:
            warn.append(f"thumb.{k} が長い（{len(th[k])}字・10字以内）")
    seq = [l for _, l in recent_layouts(num)]
    if lay in seq[-2:]:
        ng.append(f"サムネの型「{lay}」が直近2本のどちらかと同じ（直近の型：{seq[-6:]}）")
    elif seq[-6:].count(lay) >= 2:
        ng.append(f"サムネの型「{lay}」が直近6本で2回出ている（直近の型：{seq[-6:]}）")


def check_long(work, s, cuts, voiced, text, desc, ng, warn):
    """長尺：制作ルール v1.7 §15 の順位の型"""
    import title_guard
    num = num_of(work)
    t = s.get("title", "")
    if not t.endswith("【金運】"):
        ng.append(f"題が【金運】で終わらない：{t}")
    if not 24 <= len(t) <= 48:
        warn.append(f"題 {len(t)}字（26〜40字が目安）：{t}")
    for r, o in title_guard.similar(t, history_titles(num))[:1]:
        if r >= TITLE_LINE:
            ng.append(f"題が履歴の題と似すぎ（title_guard の線 {TITLE_LINE}・{r:.2f}）：「{o}」。型（手順書 §8 の A〜F）か言い回しを替える")
    n = n_chars(text)
    if not 3800 <= n <= 5000:
        ng.append(f"字数 {n}（3,800〜5,000字。006 は4,354字・約13分）")
    if not 130 <= len(voiced) <= 190:
        ng.append(f"文（カット）の数 {len(voiced)}（150〜170カット前後。130〜190）")
    elif not 150 <= len(voiced) <= 170:
        warn.append(f"文（カット）の数 {len(voiced)}（150〜170が目安）")
    ch_n = len([c for c in cuts if c.get("chapter") or c.get("yt_chapter")])
    if ch_n < 6:
        ng.append(f"章（chapter／yt_chapter）が {ch_n} つ（第5位〜第1位・上がる側・まとめで6つ以上）")
    # 順位のカード：第5位〜第1位が rank カードで出る・まとめに rules（nums 付き・5つ）
    ranks = [(c.get("card") or {}).get("num") for c in cuts if (c.get("card") or {}).get("type") == "rank"]
    for k in ("第5位", "第4位", "第3位", "第2位", "第1位"):
        if k not in ranks:
            ng.append(f"rank カード「{k}」が無い")
    recap = [c for c in cuts if (c.get("card") or {}).get("type") == "rules" and c["card"].get("nums")
             and len(c["card"].get("items", [])) == 5 and c["card"].get("all")]
    if not recap:
        ng.append("まとめの rules カード（5つ・all: true・nums 付き）が無い")
    mts = [c for c in cuts if c.get("montage")]
    if not mts or not mts[0].get("montage_labels"):
        ng.append("モンタージュ（montage＋montage_labels＋montage_blur）のカットが無い（つかみの結論の先見せ。§6）")
    else:
        mt = mts[0]
        if len(mt["montage"]) < 4 or len(mt["montage_labels"]) != len(mt["montage"]):
            ng.append("montage は4つ以上で、montage_labels と同じ数にする")
        if mt.get("montage_blur") != 14:
            warn.append(f"montage_blur {mt.get('montage_blur')}（§6 は 14）")
        by = {c["id"]: c for c in cuts}
        for m in mt["montage"]:
            if m not in by or not (by[m].get("image_en") or by[m].get("img_from") or by[m].get("same_as")):
                ng.append(f"montage の先「{m}」に絵が無い")
    cum, pos = 0, {}
    for c in voiced:
        cum += n_chars(c["narration"])
        for k in ("tease", "payoff", "peak"):
            if c.get(k):
                pos.setdefault(k, []).append(round(cum / n * 100))
    if not pos.get("tease") or pos["tease"][0] >= 40:
        ng.append(f"伏線（tease）が全体の40%より前に無い（位置 {pos.get('tease')}）")
    if not pos.get("payoff") or (pos.get("tease") and pos["payoff"][0] <= pos["tease"][0]) or pos["payoff"][0] < 50:
        ng.append(f"答え（payoff）が伏線より後の後半に無い（位置 {pos.get('payoff')}）")
    if not pos.get("peak"):
        ng.append("見どころ（peak）が無い")
    elif pos["peak"][0] < 55:
        warn.append(f"見どころ（peak）の位置 {pos['peak']}（第1位は後半）")
    kl = [c["id"] for c in cuts if c.get("anim") == "kling"]
    if len(kl) < 6:
        ng.append(f"動く絵（anim: kling）が {len(kl)} つ（6つ以上。1カット目・各順位・山場）")
    for c in cuts:
        if c.get("anim") == "kling":
            if not c.get("motion"):
                ng.append(f"{c['id']}：anim: kling には motion: true も付ける")
            if c.get("card"):
                ng.append(f"{c['id']}：動かすカットに card を付けない（card があると make_motion_psy.py が動かさない）")
    for c in cuts:
        if c.get("card") and c["card"].get("type") not in LONG_CARDS:
            ng.append(f"{c['id']}：カードの型「{c['card'].get('type')}」は使えない（使えるのは {'／'.join(LONG_CARDS)}）")
        im = str(c.get("img_from") or "")
        if im:
            if not im.startswith("pose:"):
                ng.append(f"{c['id']}：img_from は pose:<id> の形だけ（{im}）")
            elif not os.path.exists(os.path.join(POSES, im[5:] + ".jpg")):
                ng.append(f"{c['id']}：共有ポーズ絵 {im} が assets/poses に無い")
            if c.get("image_en") or c.get("image"):
                ng.append(f"{c['id']}：ポーズ絵のカットに image_en を書かない（絵を作り直してしまう）")
        elif not (c.get("image_en") or c.get("image") or c.get("card") or c.get("same_as") or c.get("montage")):
            ng.append(f"{c['id']}：image_en も card も same_as も無い")
    # 絵：新しく作る絵（Lovart）と共有ポーズ絵（作らない）を分けて数える。006 は新規14＋ポーズ31＝絵のあるカット45（三者は手で作った 003〜006 も新規14〜15）
    imgs = [c for c in cuts if c.get("image_en") and not c.get("same_as") and not c.get("img_from")]
    poses = [c for c in cuts if c.get("img_from")]
    if len(imgs) < 10:
        ng.append(f"新しく作る絵 {len(imgs)} 枚（12〜25枚が目安。10枚未満）")
    elif len(imgs) > 40:
        ng.append(f"新しく作る絵 {len(imgs)} 枚（40枚まで。Lovart の枚数が増えすぎる）")
    elif not 12 <= len(imgs) <= 25:
        warn.append(f"新しく作る絵 {len(imgs)} 枚（12〜25枚が目安）")
    if len(imgs) + len(poses) < 35:
        ng.append(f"絵のあるカット {len(imgs) + len(poses)}（新規 {len(imgs)}＋ポーズ絵 {len(poses)}。35以上。画面が変わらない時間が増える）")
    for k in {str(c["img_from"]) for c in poses}:
        if sum(1 for c in poses if c["img_from"] == k) > 5:
            warn.append(f"同じポーズ絵 {k} を6回以上使っている")
    if len([c for c in voiced if c["narration"].rstrip().endswith("？")]) < 2:
        ng.append("「これはやっていいか？」の問い（〜いいの？ で終わる文）が2つ以上ない（§15）")
    if not s.get("fiction"):
        warn.append("fiction: true が無い（人物の場面があるので書く。手順書 §3）")
    if [c for c in cuts if c.get("speaker") == "listener"]:
        ng.append("掛け合い・聞き役は入れない（手順書 §3）")
    if not [c for c in cuts if c.get("voice")]:
        warn.append("人物のセリフ（voice 付きのカット）が無い")
    if s.get("tempo") != 1.0 or (s.get("voice") or {}).get("speedScale", 1.0) != 1.0:
        warn.append(f"tempo {s.get('tempo')}／speedScale {(s.get('voice') or {}).get('speedScale')}（v1.7 はどちらも 1.0）")
    check_layout(s.get("thumb") or {}, cuts, ng, warn, num)


def main():
    a = argparse.ArgumentParser()
    a.add_argument("work")
    a.add_argument("--kind", choices=["short", "long", "cut"])
    a = a.parse_args()
    kind, ng, warn, info = check(os.path.abspath(a.work), a.kind)
    for x in ng:
        print("NG", x)
    for x in warn:
        print("注意", x)
    print(f"種類 {kind}／字数 {info['字数']}／文 {info['カット']}／NG {len(ng)}件・注意 {len(warn)}件")
    sys.exit(1 if ng else 0)


if __name__ == "__main__":
    main()

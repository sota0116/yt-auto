# 金運おきぬの台本の機械の点検（2026-10-29 新設。手順書 = 制作ルール v1.4 の §1〜§3・§5・§8・§10・§12・§13、ショートの型.md の「型」の表）
#   python -X utf8 pipeline\check_okinu_script.py <作業フォルダ> [--kind short|long|cut]
# ・種類は neta.json の kind（無ければ script.json の format と funnel から）。short＝単独／cut＝長尺の切り出し／long＝長尺
# ・NG が1つでもあれば終了コード1。「注意」は直せる物は直す（落とさない）
# ・スキルの check_script.py（引っ張り・動く絵・見どころ・作り話の決まり・声の名前）も回して、NG をそのまま出す
# ・ショートの型の表を数える：字数 270〜300・文（カット）13〜17・1文最長27字・最初が「〜ていませんか」・最後が「あなたの〇〇には、〜ですか」・
#   最初の文字（hook）5字×2行・絵7〜8枚（単独）・字幕は声と同じ字（subs をつなぐと narration になる）で1行8字まで・効果音なし
import argparse, json, os, re, shutil, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILL_CHECK = os.path.join(ROOT, "vendor", "youtube-video-maker", "scripts", "check_script.py")
CH_DIR = os.path.join(ROOT, "channels", "okinu")
CPS = 6.0
MARKS = ["──", "—", "→", "…", "※", "★"]


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

    if kind in ("short", "cut"):
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
        t = s.get("title", "")
        if not re.match(r"^【[^】]+】", t):
            ng.append(f"題が【年代かお金の数字】で始まらない：{t}")
        ch_n = len([c for c in cuts if c.get("chapter") or c.get("yt_chapter")])
        if ch_n < 5:
            ng.append(f"章（chapter）が {ch_n} つ（5つ以上）")
        n = n_chars(text)
        if not 3000 <= n <= 4200:
            ng.append(f"字数 {n}（3,000〜4,200字。001v6 は3,492字・10.8分）")
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
        imgs = [c for c in cuts if c.get("image_en") and not c.get("same_as")]
        if len(imgs) < 25:
            warn.append(f"新しい絵 {len(imgs)} 枚（001v6 は約58枚。画面が変わらない時間が増えないか）")
        for c in cuts:
            if not (c.get("image_en") or c.get("card") or c.get("same_as")):
                ng.append(f"{c['id']}：image_en も card も same_as も無い")
        if not s.get("fiction"):
            warn.append("fiction: true が無い（物語の回は書く。手順書 §3）")
        if len([c for c in cuts if c.get("speaker") == "listener"]):
            ng.append("掛け合い・聞き役は入れない（手順書 §3）")
        if len([c for c in cuts if c.get("voice")]) < 1:
            warn.append("人物のセリフ（voice 付きのカット）が無い")

    # スキルの点検（引っ張り・動く絵・作り話・声の名前）
    if os.path.exists(SKILL_CHECK):
        tmp = os.path.join(work, "check", "_skill_tmp")
        os.makedirs(tmp, exist_ok=True)
        json.dump({**s, "cuts": [{**c, "image": c.get("image") or c.get("image_en") or ("（切り出し）" if c.get("shots") else None)} for c in cuts]},
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

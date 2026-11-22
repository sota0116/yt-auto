# ⑦絵ゲート（設計書 §5⑦）：AIの絵を Claude（2026-10-24 までは Gemini）が1枚ずつ見る → 不合格は作り直す（1枚2回まで。絵が20枚以下の回は3回まで）→ 直らなければ近い絵を使い回す
#   python -X utf8 pipeline\gate_images.py <作業フォルダ> [--fix] [--only A01,B03]
# ・見ること：セリフと合っているか／出てこないはずの人がいないか／時代（日本の今）と時間帯／崩れ（手・顔・体）／読める文字やロゴ／
#   実在の人物や有名キャラに似ていないか／裸・血・けが
# ・Gemini は1日に頼める回数に上限があるので、6枚ずつまとめて見せる（1本約9回）。絵は小さくしてから送る
# ・--fix：不合格の絵を make_images_lovart.py --fix で作り直し、もう一度見る。2回直しても不合格なら、
#   同じ章の前の絵（無ければ後ろ）を images\<id>.png に写して使い回す。使い回しが絵の15%を超えたら、終了コード2（その回は止める）
# ・見る前に、絵の外周の枠線・余白を機械で切り落とす（trim_frame。枠だけの不合格で作り直さないため。2026-11-01）
# ・使い回しが15%を超えて止まった回は、もう一度動いた時に、使い回した絵を1回だけ作り直す（使い回しの記録が残ると、何度動かしても同じ割合で止まるため。2026-11-01 nihongi S102）
# ・結果は images\_gate.json。不合格が残れば終了コード1
# ・2026-11-22：profile.json の image_consistency が true のチャンネル（アナザー日本紀）は、設定画のある人物が2カット以上に出る時、設定画と並べて
#   別人に見える絵を不合格にする（consistency）。一覧の控えは history/<ch>/checks/<回>/、結果は改善ログに1行（kaizen）
import argparse, datetime, json, os, subprocess, sys
import numpy as np
from PIL import Image
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gemini

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BATCH, MAX_FIX, REUSE_MAX = 6, 2, 0.15
FEW_CUTS, FEW_FIX = 20, 3  # 絵が少ない回は1枚の重みが大きい（17枚なら3枚の使い回しで15%を超える）ので、作り直しを1回増やす。長尺は13回とも超えなかった


def topic(work):
    """何の動画か。チャンネルの profile.json の topic（無ければ仕事チャンネルの言い方。2026-10-27 心理学chを毎日の制作に入れた時に足した）"""
    p = os.path.normpath(os.path.join(work, "..", "..", "profile.json"))
    return (json.load(open(p, encoding="utf-8")).get("topic") if os.path.exists(p) else None) or "日本の仕事と年収の統計"


def era_rule(work):
    """3番目の不合格の条件。チャンネルの profile.json の image_gate_item3（無ければ今までの言い方。アナザー日本紀は江戸・戦国・幕末の絵なので別の文を入れる）"""
    p = os.path.normpath(os.path.join(work, "..", "..", "profile.json"))
    v = json.load(open(p, encoding="utf-8")).get("image_gate_item3") if os.path.exists(p) else None
    return v or "日本の今の時代に見えない、時間帯が違う"


def image_cuts(s):
    return [c for c in s["cuts"] if c.get("image") and not c.get("same_as") and not c.get("chart")]


def trim_frame(path):
    """絵の外周に、同じ色で太さの揃った細い帯が4辺ともあれば、枠線・余白とみて切り落とし、元の大きさに戻す。空や床だけの絵は辺の色が揃わないので切らない"""
    im = Image.open(path).convert("RGB")
    a = np.asarray(im, dtype=np.int16)
    h, w = a.shape[:2]

    def band(lines, limit):
        n = 0
        for x in lines[:limit]:
            if (np.abs(x - np.median(x, axis=0)).max(axis=1) <= 24).mean() < 0.96:
                break
            n += 1
        return n

    sides = [a, a[::-1], a.transpose(1, 0, 2), a.transpose(1, 0, 2)[::-1]]
    limits = [int(0.12 * (h if i < 2 else w)) for i in range(4)]
    t, b, l, r = widths = [band(x, n) for x, n in zip(sides, limits)]
    # 単色の背景の絵（人物の後ろが無地）は帯が線まで届くか太さが揃わないので、枠とみない（切ると人物の頭や足が切れる）
    if min(widths) < 2 or max(widths) > 3 * min(widths) or any(x >= n for x, n in zip(widths, limits)):
        return False
    edge = np.array([np.median(x[0], axis=0) for x in sides])
    if (edge.max(axis=0) - edge.min(axis=0)).max() > 40:
        return False
    pad = int(min(h, w) * 0.012)  # 手描きで揺れた枠線も残らないよう、少し内側まで切る
    inner = [(np.abs(x[n + pad] - c).max(axis=1) <= 24).mean() for x, n, c in zip(sides, widths, edge)]
    if max(inner) > 0.5:  # 帯のすぐ内側も同じ色が続くなら、枠でなく背景
        return False
    x0, y0, x1, y1 = l + pad, t + pad, w - r - pad, h - b - pad
    cw, ch = x1 - x0, y1 - y0
    if cw / ch > w / h:  # 切ったあとも元の縦横の比のまま
        cut = cw - round(ch * w / h)
        x0, x1 = x0 + cut // 2, x1 - (cut - cut // 2)
    else:
        cut = ch - round(cw * h / w)
        y0, y1 = y0 + cut // 2, y1 - (cut - cut // 2)
    im.crop((x0, y0, x1, y1)).resize((w, h), Image.LANCZOS).save(path)
    return True


def small(work, cid):
    d = os.path.join(work, "images", "_gate_tmp")
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, cid + ".jpg")
    im = Image.open(os.path.join(work, "images", cid + ".png")).convert("RGB")
    im.thumbnail((576, 1024) if im.height > im.width else (1024, 576))  # 縦長のショートの絵は縦を1024に（アナザー日本紀。2026-10-29）
    im.save(p, quality=85)
    return p


def judge(work, s, cuts, use):
    S = {"type": "string"}
    sch = {"type": "object", "properties": {"判定": {"type": "array", "items": {"type": "object", "properties": {
        "id": S, "合格": {"type": "boolean"}, "問題": {"type": "array", "items": S}, "直す指示": S},
        "required": ["id", "合格", "問題", "直す指示"]}}}, "required": ["判定"]}
    who = lambda c: ("／出る人：" + "・".join(c["chars"])) if c.get("chars") else ""  # 登場人物（手順書 §5）。場面の説明に名前で出てくる
    listing = "\n".join(f"{i + 1}枚目 id={c['id']}／場面：{c['image']}{who(c)}／この絵の間に流れるセリフ：{c.get('narration') or '（サムネの背景・語りなし）'}" for i, c in enumerate(cuts))
    q = f"""YouTube の解説動画（{topic(work)}）に使う挿絵を点検します。添付の絵は順に {len(cuts)} 枚で、下の一覧と同じ順です。
画風の決まり：{s['style']}
1枚ずつ、次のどれかに当たれば不合格にしてください。
1. 場面の説明・セリフと合っていない（場所・時間帯・人数・していること）
2. 場面に出てこないはずの人がいる（場面に人の説明が無いのに人が描かれている、など）
3. {era_rule(work)}
4. 崩れ（指の数・手・顔・体のゆがみ、物の形がおかしい）
5. 読める文字・数字・偽の文字・ロゴ・ブランド名がある（紙・本の背・画面・マグ・看板・車体）
6. 実在の人物や有名なキャラクターに似ている
7. 裸・血・けが
8. 画風の決まりから大きく外れている
不合格の絵は「問題」に当たった所を短く書き、「直す指示」に作り直しの時に画像生成AIへ足す英語の指示を1文で書いてください（合格なら空）。
細かすぎる所で落とさず、動画で数秒映った時に見る人が気づく問題だけで判定してください。

{listing}"""
    t, u = gemini.ask(q, schema=sch, images=[small(work, c["id"]) for c in cuts])
    use.append(u)
    r = {x["id"]: x for x in json.loads(t)["判定"]}
    miss = [c for c in cuts if c["id"] not in r]
    if miss and len(miss) < len(cuts):  # 答えから漏れた絵だけ聞き直す。不合格にすると、見ていない絵を作り直して使い回しの数を増やす（2026-11-01 nihongi S102）
        r.update(judge(work, s, miss, use))
    return {c["id"]: r.get(c["id"], {"合格": False, "問題": ["Gemini の答えにこの絵が無い"], "直す指示": ""}) for c in cuts}


def run_gate(work, s, ids, res, use):
    cuts = [c for c in image_cuts(s) if c["id"] in ids and os.path.exists(os.path.join(work, "images", c["id"] + ".png"))]
    for c in cuts:
        if trim_frame(os.path.join(work, "images", c["id"] + ".png")):
            print(c["id"], "の枠と余白を切り落とした", flush=True)
    for i in range(0, len(cuts), BATCH):
        for k, v in judge(work, s, cuts[i:i + BATCH], use).items():
            res[k] = {**res.get(k, {}), **v}
            print(k, "合格" if v["合格"] else "不合格 " + "・".join(v["問題"]), flush=True)


def profile(work):
    p = os.path.normpath(os.path.join(work, "..", "..", "profile.json"))
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {}


def sheets(work, s):
    """設定画のある人物：{id: (名前, 設定画のパス)}。make_images_lovart.load_chars と同じ所を見る（チャンネルの characters.json と script.json の characters）"""
    out = {}
    cdir = os.path.normpath(os.path.join(work, "..", "..", "characters"))
    cp = os.path.join(cdir, "characters.json")
    for k, v in (json.load(open(cp, encoding="utf-8")).get("chars", {}) if os.path.exists(cp) else {}).items():
        if v.get("desc_en"):
            out[k] = (v.get("name") or k, os.path.join(cdir, v.get("sheet", k + ".png")))
    for k, v in (s.get("characters") or {}).items():
        out[k] = (v.get("name") or k, os.path.join(work, "images", "_chars", k + ".png"))
    return {k: v for k, v in out.items() if os.path.exists(v[1])}


def contact(work, cid_list, sheet, path):
    """設定画と絵を1枚に並べた一覧（人が後で見るための控え。左上が設定画）"""
    from PIL import ImageDraw
    tw, th, cols = 240, 135, 6  # repo に残すので小さく（1人 60枚でも約0.3MB）
    tiles = [("sheet", sheet)] + [(i, os.path.join(work, "images", i + ".png")) for i in cid_list]
    rows = (len(tiles) + cols - 1) // cols
    g = Image.new("RGB", (tw * cols, th * rows), (32, 32, 32))
    d = ImageDraw.Draw(g)
    for n, (label, p) in enumerate(tiles):
        im = Image.open(p).convert("RGB")
        im.thumbnail((tw, th))
        x, y = (n % cols) * tw, (n // cols) * th
        g.paste(im, (x + (tw - im.width) // 2, y + (th - im.height) // 2))
        d.rectangle((x, y, x + 8 * len(label) + 8, y + 14), fill=(0, 0, 0))
        d.text((x + 4, y + 2), label, fill=(255, 255, 0))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    g.save(path, quality=70)


def consistency(work, s, ids, res, use):
    """人物のそろい方（2026-11-22 本人「それは改善して自動でいくようにしよう」。改善ログの『次』に毎回「絵ができたら一覧に並べて顔と服がそろっているか
    確かめる」が残り、次の書き手は絵を見られないので7回続けてできなかった）。profile.json の image_consistency が true のチャンネルだけ。
    設定画のある人物が2カット以上に出る時、設定画とその人物の出る絵を並べて見せ、別人に見える絵を不合格にする（作り直しは --fix が設定画を付けて頼む）。
    そろいで作り直すのは1枚1回まで。2回目も別人に見える絵は、不合格にせず注意だけ残す（使い回しが増えて回が止まるのを避ける）。
    一覧の控えは history/<ch>/checks/<回>/<人物>.jpg に置く（クラウドの記録の commit が history を足す）。見た結果を返す"""
    if not profile(work).get("image_consistency"):
        return {}
    sh = sheets(work, s)
    by = {}
    for c in image_cuts(s):
        if c["id"] in ids and os.path.exists(os.path.join(work, "images", c["id"] + ".png")) and not res.get(c["id"], {}).get("使い回し"):
            for k in c.get("chars") or []:
                if k in sh:
                    by.setdefault(k, []).append(c)
    ch = os.path.basename(os.path.dirname(os.path.dirname(os.path.abspath(work))))
    out = {}
    S = {"type": "string"}
    sch = {"type": "object", "properties": {"判定": {"type": "array", "items": {"type": "object", "properties": {
        "id": S, "同じ人": {"type": "boolean"}, "違う所": S, "直す指示": S}, "required": ["id", "同じ人", "違う所", "直す指示"]}}}, "required": ["判定"]}
    for k, cuts in by.items():
        if len(cuts) < 2 and not any(res.get(c["id"], {}).get("そろい直し") for c in cuts):
            continue
        name, sheet = sh[k]
        try:
            contact(work, [c["id"] for c in cuts], sheet, os.path.join(ROOT, "history", ch, "checks", os.path.basename(os.path.abspath(work)), k + ".jpg"))
        except Exception as e:  # noqa: BLE001  控えが作れなくても点検は続ける
            print(f"（{k} の一覧の控えは作れなかった：{type(e).__name__}）", flush=True)
        sp = os.path.join(work, "images", "_gate_tmp", "_sheet_" + k + ".jpg")
        os.makedirs(os.path.dirname(sp), exist_ok=True)
        im = Image.open(sheet).convert("RGB")
        im.thumbnail((1024, 576))
        im.save(sp, quality=85)
        for i in range(0, len(cuts), 10):
            part = cuts[i:i + 10]
            listing = "\n".join(f"{n + 2}枚目 id={c['id']}／場面：{c['image']}" for n, c in enumerate(part))
            q = f"""動画の挿絵で、同じ人物の見た目がそろっているかを点検します。
1枚目は人物「{name}」の設定画（同じ人を正面・斜め・顔の寄りで描いた物）です。2枚目からは動画の絵で、どれにもこの人物が出ているはずです（下の一覧と同じ順）。
1枚ずつ、設定画と比べて、顔・髪型・ひげ・服の色と形・紋が別人に見える時、またはこの人物が描かれていない時に「同じ人」を false にしてください。
場面の説明で年齢や服（鎧・寝間着など）が変わると書いてある時は、その違いは問題にしません。遠くに小さく描かれて見分けられない絵は true にします。
動画で数秒映った時に、見る人が『さっきと別の人だ』と気づく違いだけで判定してください。false の絵は「違う所」を短く、「直す指示」に画像生成AIへ足す英語の指示を1文で書いてください（true なら空）。

{listing}"""
            try:
                t, u = gemini.ask(q, schema=sch, images=[sp] + [small(work, c["id"]) for c in part])
                use.append(u)
                got = {x["id"]: x for x in json.loads(t)["判定"]}
            except Exception as e:  # noqa: BLE001  そろいの点検が動かなくても、絵ゲートの本体は止めない
                print(f"（{k} のそろいの点検ができなかった：{type(e).__name__} {str(e)[:120]}）", flush=True)
                continue
            for c in part:
                v = got.get(c["id"])
                if not v:
                    continue
                out.setdefault(k, {})[c["id"]] = v["同じ人"]
                if v["同じ人"]:
                    continue
                r = res.setdefault(c["id"], {"合格": True, "問題": [], "直す指示": ""})
                why = f"設定画の{name}（{k}）と別人に見える：{v['違う所']}"
                if r.get("そろい直し", 0) >= 1 or r.get("作り直し", 0) >= MAX_FIX:  # 1回作り直しても別人に見える絵（作り直しの回数が尽きた絵も）は、止めずに注意だけ残す
                    r["そろいの注意"] = why
                    print(c["id"], "注意（作り直してもそろわない）", why, flush=True)
                    continue
                r["そろい直し"] = r.get("そろい直し", 0) + 1
                r.update({"合格": False, "問題": list(r.get("問題") or []) + [why],
                          "直す指示": (f"Draw {name} exactly as in the attached character sheet: same face, hairstyle, beard, clothing colors and crest. "
                                    + (v.get("直す指示") or "") + " " + (r.get("直す指示") or "")).strip()})
                print(c["id"], "不合格 " + why, flush=True)
    return out


def kaizen(work, s, seen, res):
    """そろいの点検の結果を改善ログに1行足す（回ごとに1回）。『次に上げること』は前の行のものを引き継ぐ（絵の一覧を確かめる『次』は、この点検がやったので置き換える）"""
    ch = os.path.basename(os.path.dirname(os.path.dirname(os.path.abspath(work))))
    p = os.path.join(ROOT, "history", ch, "改善ログ.md")
    name = os.path.basename(os.path.abspath(work))
    tag = f"｜{name}（絵の人物のそろい・自動）｜"
    raw = open(p, "rb").read().decode("utf-8") if os.path.exists(p) else ""
    if not seen or tag in raw:
        return
    eol = "\r\n" if "\r\n" in raw else "\n"
    lines = [x for x in raw.splitlines() if x.startswith("- ")]
    nxt = lines[-1].split("｜")[-1].strip() if lines else ""
    if not nxt or ("一覧" in nxt and ("絵" in nxt or "並べ" in nxt)):
        nxt = "次の回で上げること：2カット以上に出る人物（characters.json にいない人も）を script.json の characters に入れ、絵の点検で設定画と比べられるようにする"
    ng = sorted({i for i, v in res.items() if any("設定画の" in q for q in v.get("問題") or []) or v.get("そろいの注意")})
    note = sorted(i for i, v in res.items() if v.get("そろいの注意"))
    who = "・".join(f"{k} {len(v)}枚" for k, v in seen.items())
    line = (f"- {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))):%Y-%m-%d}{tag}"
            f"設定画と絵を並べて人物の顔と服を見た（{who}）。別人に見えた絵 {len(ng)}枚{('（' + '・'.join(ng) + '）') if ng else ''}は設定画を付けて作り直した"
            f"{('。作り直してもそろわず注意で残した絵：' + '・'.join(note)) if note else ''}（一覧の控え：history/{ch}/checks/{name}/）｜{nxt}")
    body = raw if raw.endswith(eol) or not raw else raw + eol
    open(p, "wb").write((body + line + eol).encode("utf-8"))


def neighbor(s, cid, bad):
    """同じ章の前の絵（無ければ後ろの絵）"""
    chap, cur = {}, None
    for c in s["cuts"]:
        cur = c.get("chapter", cur)
        chap[c["id"]] = cur
    ok = [c["id"] for c in image_cuts(s) if c["id"] not in bad]
    order = [c["id"] for c in image_cuts(s)]
    i = order.index(cid)
    before = [x for x in reversed(order[:i]) if x in ok and chap[x] == chap[cid]]
    after = [x for x in order[i + 1:] if x in ok and chap[x] == chap[cid]]
    return (before or after or [x for x in reversed(order[:i]) if x in ok] or [None])[0]


def main():
    a = argparse.ArgumentParser()
    a.add_argument("work")
    a.add_argument("--fix", action="store_true")
    a.add_argument("--only", default="")
    a = a.parse_args()
    s = json.load(open(os.path.join(a.work, "script.json"), encoding="utf-8"))
    gp = os.path.join(a.work, "images", "_gate.json")
    res = json.load(open(gp, encoding="utf-8")) if os.path.exists(gp) else {}
    only = set(filter(None, a.only.split(",")))
    ids = [c["id"] for c in image_cuts(s) if not only or c["id"] in only]
    missing = [i for i in ids if not os.path.exists(os.path.join(a.work, "images", i + ".png"))]
    if missing:
        print("【メモ】まだ絵が無いカット（見ない）：", missing)
    use = []
    # 前の実行で使い回しが線を超えて止まった回：使い回した絵を1回だけ作り直しに戻す（--only の時は比べる母数が違うので見ない）
    again = [i for i in ids if res.get(i, {}).get("使い回し") and not res[i].get("やり直し")]
    if a.fix and not only and sum(1 for i in ids if res.get(i, {}).get("使い回し")) / max(1, len(ids)) > REUSE_MAX:
        for i in again:
            res[i].pop("使い回し")
            res[i].update({"合格": False, "作り直し": 0, "やり直し": True})
        print("使い回した絵を作り直しに戻す：", again, flush=True)
    else:
        again = []
    run_gate(a.work, s, [i for i in ids if i not in missing and i not in again], res, use)
    seen = {}

    def look(cids):  # 人物のそろい方（image_consistency のチャンネルだけ。2026-11-22）
        for k, v in consistency(a.work, s, set(cids), res, use).items():
            seen.setdefault(k, {}).update(v)
    look([i for i in ids if i not in missing and i not in again])
    save = lambda: json.dump(res, open(gp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    save()
    while a.fix:
        bad = [i for i in ids if i in res and not res[i]["合格"] and not res[i].get("使い回し")]
        redo = [i for i in bad if res[i].get("作り直し", 0) < (FEW_FIX if len(image_cuts(s)) <= FEW_CUTS else MAX_FIX)]
        if not redo:
            break
        args = [sys.executable, "-X", "utf8", os.path.join(ROOT, "pipeline", "make_images_lovart.py"), a.work]
        for i in redo:
            res[i]["作り直し"] = res[i].get("作り直し", 0) + 1
            args += ["--fix", f"{i}={res[i]['直す指示'] or 'Fix the problems: ' + '; '.join(res[i]['問題'])}"]
        save()
        print("作り直し：", redo, flush=True)
        subprocess.run(args)
        run_gate(a.work, s, redo, res, use)
        look(redo)
        save()
    if a.fix:
        bad = [i for i in ids if i in res and not res[i]["合格"] and not res[i].get("使い回し")]
        import shutil
        for i in bad:
            n = neighbor(s, i, set(bad))
            if n:
                shutil.copyfile(os.path.join(a.work, "images", n + ".png"), os.path.join(a.work, "images", i + ".png"))
                res[i]["使い回し"] = n
                print(i, "→", n, "の絵を使い回す", flush=True)
        save()
    if a.fix and not only:
        try:
            kaizen(a.work, s, seen, res)
        except Exception as e:  # noqa: BLE001  記録が書けなくても絵ゲートは止めない
            print(f"（改善ログに書けなかった：{type(e).__name__}）", flush=True)
    reused = [i for i in ids if res.get(i, {}).get("使い回し")]
    rate = len(reused) / max(1, len(ids))
    left = [i for i in ids if i in res and not res[i]["合格"] and not res[i].get("使い回し")]
    i_tok = sum(u.get("promptTokenCount", 0) for u in use)
    o_tok = sum(u.get("candidatesTokenCount", 0) + u.get("thoughtsTokenCount", 0) for u in use)
    yen = round((i_tok / 1e6 * 0.5 + o_tok / 1e6 * 3.0) * 155, 1)  # 推測の単価（gate_script.py と同じ）
    print(f"絵ゲート：見た {len(ids) - len(missing)} 枚・不合格のまま {len(left)}・使い回し {len(reused)}（{rate:.0%}）・Gemini {len(use)}回 約{yen}円")
    if rate > REUSE_MAX:
        print("【止まりました】使い回しが15%を超えました。この回は止めて、在庫の動画で公開をつなぐ（設計書 §5⑦）")
        sys.exit(2)
    sys.exit(1 if left or missing else 0)


if __name__ == "__main__":
    main()

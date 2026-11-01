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
import argparse, json, os, subprocess, sys
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

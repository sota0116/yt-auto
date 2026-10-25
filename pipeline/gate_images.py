# ⑦絵ゲート（設計書 §5⑦）：AIの絵を Claude（2026-10-24 までは Gemini）が1枚ずつ見る → 不合格は作り直す（1枚2回まで）→ 直らなければ近い絵を使い回す
#   python -X utf8 pipeline\gate_images.py <作業フォルダ> [--fix] [--only A01,B03]
# ・見ること：セリフと合っているか／出てこないはずの人がいないか／時代（日本の今）と時間帯／崩れ（手・顔・体）／読める文字やロゴ／
#   実在の人物や有名キャラに似ていないか／裸・血・けが
# ・Gemini は1日に頼める回数に上限があるので、6枚ずつまとめて見せる（1本約9回）。絵は小さくしてから送る
# ・--fix：不合格の絵を make_images_lovart.py --fix で作り直し、もう一度見る。2回直しても不合格なら、
#   同じ章の前の絵（無ければ後ろ）を images\<id>.png に写して使い回す。使い回しが絵の15%を超えたら、終了コード2（その回は止める）
# ・結果は images\_gate.json。不合格が残れば終了コード1
import argparse, json, os, subprocess, sys
from PIL import Image
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gemini

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BATCH, MAX_FIX, REUSE_MAX = 6, 2, 0.15


def image_cuts(s):
    return [c for c in s["cuts"] if c.get("image") and not c.get("same_as") and not c.get("chart")]


def small(work, cid):
    d = os.path.join(work, "images", "_gate_tmp")
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, cid + ".jpg")
    im = Image.open(os.path.join(work, "images", cid + ".png")).convert("RGB")
    im.thumbnail((1024, 576))
    im.save(p, quality=85)
    return p


def judge(work, s, cuts, use):
    S = {"type": "string"}
    sch = {"type": "object", "properties": {"判定": {"type": "array", "items": {"type": "object", "properties": {
        "id": S, "合格": {"type": "boolean"}, "問題": {"type": "array", "items": S}, "直す指示": S},
        "required": ["id", "合格", "問題", "直す指示"]}}}, "required": ["判定"]}
    who = lambda c: ("／出る人：" + "・".join(c["chars"])) if c.get("chars") else ""  # 登場人物（手順書 §5）。場面の説明に名前で出てくる
    listing = "\n".join(f"{i + 1}枚目 id={c['id']}／場面：{c['image']}{who(c)}／この絵の間に流れるセリフ：{c['narration']}" for i, c in enumerate(cuts))
    q = f"""YouTube の解説動画（日本の仕事と年収の統計）に使う挿絵を点検します。添付の絵は順に {len(cuts)} 枚で、下の一覧と同じ順です。
画風の決まり：{s['style']}
1枚ずつ、次のどれかに当たれば不合格にしてください。
1. 場面の説明・セリフと合っていない（場所・時間帯・人数・していること）
2. 場面に出てこないはずの人がいる（場面に人の説明が無いのに人が描かれている、など）
3. 日本の今の時代に見えない、時間帯が違う
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
    return {c["id"]: r.get(c["id"], {"合格": False, "問題": ["Gemini の答えにこの絵が無い"], "直す指示": ""}) for c in cuts}


def run_gate(work, s, ids, res, use):
    cuts = [c for c in image_cuts(s) if c["id"] in ids and os.path.exists(os.path.join(work, "images", c["id"] + ".png"))]
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
    run_gate(a.work, s, [i for i in ids if i not in missing], res, use)
    save = lambda: json.dump(res, open(gp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    save()
    while a.fix:
        bad = [i for i in ids if i in res and not res[i]["合格"] and not res[i].get("使い回し")]
        redo = [i for i in bad if res[i].get("作り直し", 0) < MAX_FIX]
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

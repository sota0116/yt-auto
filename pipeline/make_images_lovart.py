# ⑥絵（設計書 §5⑥）：script.json の image カットを、Lovart の無料モード（Nano Banana 2）で作って images\<id>.png に置く
#   python -X utf8 pipeline\make_images_lovart.py <作業フォルダ> [--par 6] [--only A01,B03] [--force] [--ref <画風の見本.png>] [--fix <id>=<追加の指示>]
# ・same_as と chart のカットは作らない（同じ絵の使い回しと、グラフは別の部品で作る）
# ・作ってある絵は飛ばす。--force で作り直す
# ・お金：Lovart は unlimited（無料・順番待ち）で使う。pending_confirmation（クレジットを使う確認）が出たら confirm せず、そのカットは「失敗」にして次へ
# ・無料モードは順番待ちで1枚に数分〜十数分かかる。頼んだら会話ID（thread）を images\_lovart.json に書き、終わった物から受け取る。
#   途中で止まっても、もう一度動かせば頼み直さずに続きを受け取る（二重に頼まない）
# ・公式クライアント agent_skill.py は書き換えず、部品として読み込む（CLI の send は使うモデルを指定できないため）
# ・--ref の絵を見本として添付し、画風だけをそろえる（構図と中身はまねさせない）
# ・登場人物（2026-10-25）：カットに "chars": ["kenji"] があれば、その人の設定画を添付して「同じ人」として描かせる（顔・髪・服を全部の回でそろえる）。
#   人物は channels\<ch>\characters\characters.json（チャンネルで決まった人）と、script.json の "characters"（その回だけの主役。{"id": {"name", "desc_en"}}）。
#   設定画が無ければ先に作る（チャンネルの人は characters\ に、その回だけの人は images\_chars\ に置く）
# ・チャンネルの絵の決まり（2026-10-27 心理学chから）：profile.json に image_rules_en があれば、カットごとに1文足す。
#   主役（chars）が出る絵は with_chars、"nobody": true か場面に「人物は描かない」の絵は nobody、それ以外は without_chars。nobody 以外は always も足す。
#   script.json に avoid（描かない物）があれば、それも英語にして足す
import argparse, importlib.util, json, os, sys, time
from PIL import Image

LOVART = os.environ.get("LOVART_SKILL", r"C:\Users\koneb\OneDrive\ClaudeBackup\tools\lovart\agent_skill.py")
PROJECT = os.environ.get("LOVART_PROJECT", "2o6natm73im8")
MODEL = {"IMAGE": ["generate_image_nano_banana_2"]}
W, H = 1920, 1080
WAIT_MAX = int(os.environ.get("LOVART_WAIT_MAX", 4 * 3600))  # 全体で待つ上限（秒）
THREAD_MAX = 40 * 60  # 1枚を待つ上限（秒）。超えたら頼み直す（1カット2回まで）


def client():
    spec = importlib.util.spec_from_file_location("lovart_agent_skill", LOVART)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    ak, sk = os.environ.get("LOVART_ACCESS_KEY"), os.environ.get("LOVART_SECRET_KEY")
    if not ak or not sk:
        sys.exit("【止まりました】LOVART_ACCESS_KEY / LOVART_SECRET_KEY が環境変数にありません（中身は人に見せない）")
    return m.AgentSkill(base_url=os.environ.get("LOVART_BASE_URL", "https://lgw.lovart.ai"), access_key=ak, secret_key=sk, timeout=180)


def scenes_en(work, s, ids):
    """場面の説明を英語にする（日本語で頼むと、絵の中にも日本語の文字を描きたがるため）。
    文字が出やすい物（紙・本の背・画面・マグ・看板）は「無地」と書き直させる。1本につき Gemini 1回。images\\_scene_en.json に残す"""
    p = os.path.join(work, "images", "_scene_en.json")
    have = json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {}
    need = [c for c in s["cuts"] if c["id"] in ids and c["id"] not in have]
    if need:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import gemini
        q = ("Translate each Japanese scene description into one natural English sentence or two for an image generator. "
             "Keep every concrete detail (place, time of day, people, action). It is Japan, present day. "
             "Rewrite any object that would normally carry writing so it is explicitly plain: papers, notebooks and documents are "
             "'blank sheets', book spines are 'plain colored spines', screens show 'a soft glow seen from the side' or 'abstract colored blocks', "
             "mugs are 'plain mugs', signs and bus destination boards are 'plain panels'. Remove notes in parentheses that say text is unreadable "
             "(they are already handled). Do not add brands.\n"
             + json.dumps({c["id"]: c["image"] for c in need}, ensure_ascii=False)
             + "\nAlso translate this art style into English: " + s["style"]
             + ("\nAlso translate this list of things NOT to draw into English, as 'avoid': " + s["avoid"] if s.get("avoid") else ""))
        sch = {"type": "object", "properties": {
            "scenes": {"type": "array", "items": {"type": "object", "properties": {"id": {"type": "string"}, "en": {"type": "string"}},
                                                  "required": ["id", "en"]}},
            "style": {"type": "string"}, "avoid": {"type": "string"}}, "required": ["scenes", "style"]}
        t, _ = gemini.ask(q, schema=sch)
        r = json.loads(t)
        have.update({x["id"]: x["en"] for x in r["scenes"]})
        have["_style"] = r["style"]
        if r.get("avoid"):
            have["_avoid"] = r["avoid"]
        json.dump(have, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return have


def load_chars(work, s):
    """登場人物：{id: {"desc_en", "sheet"（設定画のパス）}}。チャンネルの characters.json と、script.json の characters"""
    out = {}
    cdir = os.path.normpath(os.path.join(work, "..", "..", "characters"))
    cp = os.path.join(cdir, "characters.json")
    if os.path.exists(cp):
        for k, v in json.load(open(cp, encoding="utf-8")).get("chars", {}).items():
            out[k] = {"desc_en": v["desc_en"], "sheet": os.path.join(cdir, v.get("sheet", k + ".png"))}
    for k, v in (s.get("characters") or {}).items():
        out[k] = {"desc_en": v["desc_en"], "sheet": os.path.join(work, "images", "_chars", k + ".png")}
    return out


def sheet_prompt(style, ch):
    return ("Generate exactly ONE character reference sheet, landscape 16:9, on a plain warm off-white background.\n"
            f"Art style: {style}\n"
            f"Character: {ch['desc_en']}\n"
            "Show the SAME person three times side by side: full body front view, full body three-quarter view, and a large close-up "
            "of the face. Neutral standing pose, calm expression, even soft light, no props, no other people.\n"
            "TEXT-FREE: no letters, numbers, logos or symbols anywhere. Natural hands and faces.\n"
            "Do not ask questions. Call the image generator exactly once and stop: no editing, upscaling, cropping or post-processing.")


def make_sheets(sk, chars, need, style, par):
    """設定画が無い人物の設定画を作る（無料モード。confirm はしない）。できなかった人物の id を返す"""
    todo = [k for k in need if not os.path.exists(chars[k]["sheet"])]
    waiting, t_end = {}, time.time() + WAIT_MAX
    if todo:
        print("設定画を先に作る：", todo, flush=True)
    while (todo or waiting) and time.time() < t_end:
        while todo and len(waiting) < par:
            k = todo.pop(0)
            try:
                waiting[k] = (sk.send(sheet_prompt(style, chars[k]), PROJECT, prefer_models=MODEL,
                                      include_tools=MODEL["IMAGE"], mode="fast"), time.time())
            except Exception as e:
                if "409" in str(e) or "429" in str(e) or "limit" in str(e).lower():  # 同時に頼める数の上限・回数の上限は、待って頼み直す
                    todo.insert(0, k); time.sleep(30); break
                print(k, "設定画を頼めなかった", str(e)[:120], flush=True)
        time.sleep(15)
        for k in list(waiting):
            tid, t0 = waiting[k]
            try:
                if sk.get_status(tid)["status"] not in ("done", "abort") and time.time() - t0 < THREAD_MAX:
                    continue
                r = sk.get_result(tid)
            except Exception as e:
                print(k, "確かめられない（あとでもう一度）", str(e)[:120], flush=True)
                continue
            del waiting[k]
            d = os.path.dirname(chars[k]["sheet"])
            os.makedirs(d, exist_ok=True)
            got = [x["local_path"] for x in sk.download_artifacts(r, os.path.join(d, "_lovart", k), "lovart")
                   if x.get("local_path") and x.get("type") == "image"]
            if got:
                to_png(got[0], chars[k]["sheet"])
            print(k, "設定画できた" if got else "設定画ができない", flush=True)
    return [k for k in need if not os.path.exists(chars[k]["sheet"])]


def channel_rules(work):
    p = os.path.normpath(os.path.join(work, "..", "..", "profile.json"))
    return (json.load(open(p, encoding="utf-8")).get("image_rules_en") if os.path.exists(p) else None) or {}


def rule_for(rules, cut):
    """チャンネルの絵の決まりのうち、このカットに当てはまる文"""
    if not rules:
        return ""
    if cut.get("nobody") or "人物は描かない" in cut.get("image", ""):
        return rules.get("nobody", "")
    return " ".join(x for x in (rules.get("with_chars" if cut.get("chars") else "without_chars", ""), rules.get("always", "")) if x)


def prompt(en, cut, has_ref, extra="", chars=(), rules=None):
    ref = ("The attached image is a STYLE reference only: match its line quality, color palette and film grain. "
           "Do NOT copy its composition, objects or people.\n") if has_ref else ""
    if chars:  # 添付の順：設定画（人物の順）→ 画風の見本
        who = " ".join(f"Attached image {n + 1} is the character reference sheet of {c['desc_en'].split(',')[0]}."
                       for n, c in enumerate(chars))
        ref = (f"{who} Whenever that person appears, draw exactly the same face, hairstyle, body and clothing as in the sheet. "
               "Do not copy the sheet's layout, background or pose. Character details: " + " ".join(c["desc_en"] for c in chars) + "\n"
               + ref.replace("The attached image is", "The last attached image is"))
    return (f"Generate exactly ONE text-free illustration, landscape 16:9.\n{ref}"
            f"Art style: {en['_style']}\n"
            f"Scene: {en[cut['id']]}\n"
            f"{(rule_for(rules, cut) + chr(10)) if rules else ''}"
            f"{('Avoid: ' + en['_avoid'] + chr(10)) if en.get('_avoid') else ''}"
            f"{('Extra direction: ' + extra + chr(10)) if extra else ''}"
            f"TEXT-FREE: there are no letters, numbers or symbols anywhere in the picture. Every sheet of paper, notebook, "
            f"book spine, folder, mug, screen, sign and calendar is plain and unmarked. No logos or brand names on any object "
            f"(laptops, phones, cars, buses are unbranded). No real company uniforms, no blood or injuries, no nudity, "
            f"no faces resembling famous characters. If the scene does not mention a person, draw no people. Natural hands and faces.\n"
            f"Do not ask questions. Call the image generator exactly once and stop: no editing, upscaling, "
            f"cropping or any post-processing step afterwards.")


def to_png(src, dst):
    """縦横の比だけ 16:9 にそろえ、縮めずに残す（2026-10-28 本人の指摘「画質」。スキル references/16 の1）。
    Lovart の 2752×1536 は 2730×1536 のまま残す（前は 1920×1080 に縮めていて、組み立ての寄りでぼやけた）。
    1920×1080 より小さい時だけ大きくする"""
    im = Image.open(src).convert("RGB")
    w, h = im.size
    if w / h > W / H:
        nw = int(h * W / H); im = im.crop(((w - nw) // 2, 0, (w - nw) // 2 + nw, h))
    else:
        nh = int(w * H / W); im = im.crop((0, (h - nh) // 2, w, (h - nh) // 2 + nh))
    if im.width < W or im.height < H:
        im = im.resize((W, H), Image.LANCZOS)
    im.save(dst)


def main():
    a = argparse.ArgumentParser()
    a.add_argument("work")
    a.add_argument("--par", type=int, default=6, help="同時に頼む数")
    a.add_argument("--only", default="")
    a.add_argument("--force", action="store_true")
    a.add_argument("--ref", default="")
    a.add_argument("--fix", action="append", default=[], help="<id>=<追加の指示>（絵ゲートで落ちた所の作り直し用）")
    a = a.parse_args()
    sk = client()
    if sk.query_mode().get("unlimited") is not True:
        sys.exit("【止まりました】Lovart が unlimited（無料）モードではありません。クレジットを使うので作りません")
    s = json.load(open(os.path.join(a.work, "script.json"), encoding="utf-8"))
    only = set(filter(None, a.only.split(",")))
    fix = dict(f.split("=", 1) for f in a.fix)
    only |= set(fix)
    img = os.path.join(a.work, "images")
    os.makedirs(img, exist_ok=True)
    log_p = os.path.join(img, "_lovart.json")
    log = json.load(open(log_p, encoding="utf-8")) if os.path.exists(log_p) else {}
    save = lambda: json.dump(log, open(log_p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    cuts = {c["id"]: c for c in s["cuts"] if c.get("image") and not c.get("same_as") and not c.get("chart")
            and (not only or c["id"] in only)}
    todo = [i for i in cuts if a.force or i in fix or not os.path.exists(os.path.join(img, i + ".png"))]
    # 前回頼んだまま受け取っていない会話は、頼み直さずに待つ
    waiting = {i: log[i] for i in todo if log.get(i, {}).get("状態") == "待ち" and i not in fix and not a.force}
    queue = [i for i in todo if i not in waiting]
    en = scenes_en(a.work, s, set(cuts))
    ref_url = sk.upload_file(a.ref) if a.ref else ""
    chars = load_chars(a.work, s)
    unknown = sorted({k for i in todo for k in cuts[i].get("chars", []) if k not in chars})
    if unknown:
        sys.exit(f"【止まりました】characters.json にも script.json の characters にも無い人物：{unknown}")
    need_c = sorted({k for i in todo for k in cuts[i].get("chars", [])})
    if make_sheets(sk, chars, need_c, en["_style"], a.par):
        sys.exit("【止まりました】設定画ができていない人物がいます（もう一度動かすと作り直す）")
    sheet_url = {k: sk.upload_file(chars[k]["sheet"]) for k in need_c}
    attach = lambda i: [sheet_url[k] for k in cuts[i].get("chars", [])] + ([ref_url] if ref_url else [])
    rules = channel_rules(a.work)
    print(f"Lovart（無料モード・Nano Banana 2）：新しく頼む {len(queue)} 枚・前回の続き {len(waiting)} 枚（同時に{a.par}本）", flush=True)
    t_end = time.time() + WAIT_MAX
    while (queue or waiting) and time.time() < t_end:
        while queue and len(waiting) < a.par:
            i = queue.pop(0)
            tries = log.get(i, {}).get("回", 0) + 1 if not (a.force or i in fix) else 1
            try:
                tid = sk.send(prompt(en, cuts[i], bool(ref_url), fix.get(i, ""), [chars[k] for k in cuts[i].get("chars", [])], rules),
                              PROJECT, attachments=attach(i) or None, prefer_models=MODEL,
                              include_tools=MODEL["IMAGE"], mode="fast")
            except Exception as e:
                if "409" in str(e) or "429" in str(e) or "limit" in str(e).lower():  # 同時に頼める数の上限・回数の上限は、待って頼み直す
                    queue.insert(0, i); time.sleep(30); break
                log[i] = {"状態": "失敗", "理由": f"頼めなかった：{type(e).__name__} {str(e)[:200]}", "回": tries}; save()
                print(i, log[i]["理由"], flush=True)  # クラウドでは _lovart.json が見えないので、理由をログにも出す（2026-10-25）
                continue
            waiting[i] = log[i] = {"状態": "待ち", "thread": tid, "頼んだ時刻": time.time(), "回": tries}
            save()
        time.sleep(15)
        for i in list(waiting):
            w = waiting[i]
            try:
                st = sk.get_status(w["thread"])["status"]
                if st not in ("done", "abort"):  # running・順番待ちなど、終わっていない状態はすべて待つ
                    r = sk.get_result(w["thread"]) if int(time.time()) % 4 == 0 else {}
                    if r.get("pending_confirmation"):
                        st = "pending"
                    elif time.time() - w["頼んだ時刻"] > THREAD_MAX:
                        st = "too_long"
                    else:
                        continue
                r = sk.get_result(w["thread"])
            except Exception as e:
                print(i, "確かめられない（あとでもう一度）", str(e)[:120], flush=True)
                continue
            if r.get("pending_confirmation"):
                st = "pending"
            del waiting[i]
            # クレジット確認が出ても、その前に無料でできた絵があれば受け取る（確認は押さない）
            got = [d["local_path"] for d in sk.download_artifacts(r, os.path.join(img, "_lovart", i), "lovart")
                   if d.get("local_path") and d.get("type") == "image"]
            if got:
                to_png(got[0], os.path.join(img, i + ".png"))
                log[i] = {"状態": "できた", "thread": w["thread"], "回": w["回"],
                          "秒": round(time.time() - w["頼んだ時刻"]), "元": os.path.relpath(got[0], a.work),
                          "注意": ("あとの編集はクレジットが要るので頼んでいない" if st == "pending" else "")
                                  + ("一部の道具が断られた" if r.get("failures") else "")}
            elif st == "pending":
                log[i] = {"状態": "失敗", "理由": "クレジットを使う確認が出た（confirm していない）", "thread": w["thread"], "回": w["回"]}
            else:
                why = {"too_long": "40分待っても終わらない", "abort": "Lovart 側で中止"}.get(st) or \
                      ("絵が返ってこない：" + " ".join(it.get("text", "") for it in r.get("items", []))[:200])
                log[i] = {"状態": "失敗", "理由": why, "thread": w["thread"], "回": w["回"]}
                if w["回"] < 2:
                    queue.append(i)
            print(i, log[i]["状態"], log[i].get("理由", ""), log[i].get("秒", ""), flush=True)
            save()
    for i in waiting:
        print(i, "まだ待ち（もう一度動かすと続きを受け取る）", flush=True)
    bad = [i for i in todo if log.get(i, {}).get("状態") != "できた"]
    print(f"できた {len(todo) - len(bad)} 枚／できていない {len(bad)} 枚 {bad}")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()

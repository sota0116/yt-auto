# ⑤声（設計書 §5⑤・手順書 §2）：Gemini TTS で、語り手と聞き手の声を分け、章ごとに調子を変えてカットごとに作る
#   python -X utf8 pipeline\make_voice_job.py audition <チャンネル>          … 声の候補を聞き比べ、Gemini に選ばせて profile.json に書く
#   python -X utf8 pipeline\make_voice_job.py estimate <作業フォルダ> [--ch job]
#   python -X utf8 pipeline\make_voice_job.py make <作業フォルダ> [--ch job] [--force] [--only A01,B02]
# ・作ってある声は飛ばす。読み間違えやすい語は、カットの tts_text に読みを書く
# ・同時に2本まで頼む（2チャンネル同時に動くので、チャンネルごとに2本。設計書 §4）。混んでいる時のやり直しは gemini.py
# ・声の長さが字数に比べて長すぎる・短すぎるカット（指示まで読んだ・途中で切れた）は、1回だけ作り直す
# ・使ったトークンと見積もりの円を voice\_cost.json に書く
import argparse, concurrent.futures as cf, io, json, os, statistics, sys, wave
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gemini

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def profile(ch):
    return json.load(open(os.path.join(ROOT, "channels", ch, "profile.json"), encoding="utf-8"))


def prompt(style, tone, text, who=""):
    # 日本語の指示を文の前に置くと、指示まで読み上げる（2026-10-24 に8声とも確認）。
    # 「指示書き」と「読む文」を見出しで分けると、読む文だけになる（同じ文で 25秒→7.5秒）
    return (f"# AUDIO PROFILE: {who}\n## DIRECTOR'S NOTES\nStyle: {style}{tone}\nLanguage: Japanese (Tokyo accent)\n"
            f"Only speak the transcript below. Do not read these notes.\n#### TRANSCRIPT\n{text}")


def who_label(p, who):
    return f"{p[who]['name']}（{p[who]['role']}）"


def secs(data):
    with wave.open(io.BytesIO(data)) as w:
        return w.getnframes() / w.getframerate()


def yen(p, audio_sec, in_tokens=0):
    pr = p["price"]
    usd = audio_sec * pr["audio_tokens_per_sec"] / 1e6 * pr["tts_usd_per_1m_audio_tokens"] + in_tokens / 1e6 * 0.5
    return round(usd * pr["yen_per_usd"], 1)


def tone_of(cut, chapter):
    if cut.get("quiz"):
        return "クイズ"
    if cut.get("strong"):
        return "山場"
    return chapter if chapter in ("つかみ・前置き", "まとめ") else None


def audition(ch):
    p = profile(ch)
    out = os.path.join(ROOT, "channels", ch, "voice_audition")
    os.makedirs(out, exist_ok=True)
    lines = {"narrator": "年収約453万円で1位の仕事が、時給に直すと、6つの中で最下位に落ちます。そして1位は、バス運転手。年収は約453万円です。",
             "listener": "えっ、年収は1位だったのに。それ、うちの部署もみんなやってます。"}
    sec_total, files, use = 0, {}, []
    for who, cands in p["voice_candidates"].items():
        for v in cands:
            data, u = gemini.tts(prompt(p["voices"][who]["style"], "", lines[who], who_label(p, who)), v, p["tts_model"])
            f = os.path.join(out, f"{who}_{v}.wav")
            open(f, "wb").write(data)
            sec_total += secs(data)
            files.setdefault(who, []).append((v, f))
            print(f"{who} {v} {secs(data):.1f}秒", flush=True)
    pick = {}
    for who, fl in files.items():
        role = "語り手（働き方の統計を案内する係。30代前半の落ち着いた男性。ニュース解説のようにテンポよく）" if who == "narrator" \
            else "聞き手（入社3年目の会社員の女性。素直で、すぐ驚く）"
        q = f"""YouTube の長尺動画（仕事と年収の統計番組）の{role}の声を選びます。添付の音声は順に {', '.join(v for v, _ in fl)} です。
読ませた文：「{lines[who]}」
それぞれについて、①読ませた文どおりか（指示の文まで読んでいないか・抜けがないか）②日本語のアクセントとイントネーションの自然さ（10点満点）③役に合っているか（10点満点）④耳だけで10分聞いて疲れないか（10点満点）を判定し、いちばん良い1つを選んでください。甘く付けないでください。"""
        sch = {"type": "object", "properties": {
            "判定": {"type": "array", "items": {"type": "object", "properties": {
                "声": {"type": "string"}, "文どおり": {"type": "boolean"}, "自然さ": {"type": "integer"}, "役に合う": {"type": "integer"},
                "疲れない": {"type": "integer"}, "ひとこと": {"type": "string"}}, "required": ["声", "文どおり", "自然さ", "役に合う", "疲れない", "ひとこと"]}},
            "選んだ声": {"type": "string"}, "理由": {"type": "string"}}, "required": ["判定", "選んだ声", "理由"]}
        t, u = gemini.ask(q, schema=sch, images=[f for _, f in fl])
        use.append(u)
        r = json.loads(t)
        ok = [j for j in r["判定"] if j["文どおり"]]
        best = max(ok, key=lambda j: j["自然さ"] + j["役に合う"] + j["疲れない"]) if ok else None
        pick[who] = {"選んだ声": best["声"] if best else None, "Geminiの選択": r["選んだ声"], "理由": r["理由"], "判定": r["判定"]}
        print(who, json.dumps(pick[who], ensure_ascii=False), flush=True)
    json.dump({"結果": pick, "声の秒数": round(sec_total, 1), "見積もり_円": yen(p, sec_total) + 1.0},
              open(os.path.join(out, "_結果.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    for who in pick:
        if pick[who]["選んだ声"]:
            p["voices"][who]["voice"] = pick[who]["選んだ声"]
    json.dump(p, open(os.path.join(ROOT, "channels", ch, "profile.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("profile.json に書きました：", {w: p["voices"][w]["voice"] for w in p["voices"]})


def plan(work, ch, force=False, only=""):
    p = profile(ch)
    s = json.load(open(os.path.join(work, "script.json"), encoding="utf-8"))
    only = set(filter(None, only.split(",")))
    jobs, chapter = [], "つかみ・前置き"
    for c in s["cuts"]:
        chapter = c.get("chapter", chapter)
        if not c.get("narration") or (only and c["id"] not in only):
            continue
        if not force and os.path.exists(os.path.join(work, "voice", c["id"] + ".wav")):
            continue
        who = c.get("speaker", "narrator")
        tone = p["chapter_tone"].get(tone_of(c, chapter) or "", "")
        jobs.append({"id": c["id"], "who": who, "voice": p["voices"][who]["voice"],
                     "prompt": prompt(p["voices"][who]["style"], tone, c.get("tts_text") or c["narration"], who_label(p, who)),
                     "chars": len(c.get("tts_text") or c["narration"])})
    return p, jobs


def estimate(work, ch):
    p, jobs = plan(work, ch)
    chars = sum(j["chars"] for j in jobs)
    sec = chars / 6.0
    print(f"【有料】Gemini TTS（{p['tts_model']}）で {len(jobs)} カット・{chars:,} 文字。声の長さ 約{sec / 60:.1f}分の見込み")
    print(f"見積もり：約{yen(p, sec * 1.15)}円（作り直し15%込み。単価：{p['price']['source']}）")


def make(work, ch, force, only):
    p, jobs = plan(work, ch, force, only)
    if any(not j["voice"] for j in jobs):
        sys.exit("【止まりました】profile.json の声が決まっていません。先に audition を動かす")
    os.makedirs(os.path.join(work, "voice"), exist_ok=True)
    log, use = {}, []

    def one(j):
        data, u = gemini.tts(j["prompt"], j["voice"], p["tts_model"])
        return j, data, u

    def save(j, data, u):
        open(os.path.join(work, "voice", j["id"] + ".wav"), "wb").write(data)
        log[j["id"]] = {"秒": round(secs(data), 2), "字": j["chars"], "話し手": j["who"]}
        use.append(u)

    with cf.ThreadPoolExecutor(2) as ex:
        for j, data, u in ex.map(one, jobs):
            save(j, data, u)
            print(j["id"], f"{secs(data):.1f}秒", flush=True)
    # 長さの外れを作り直す（1回だけ）
    rates = [v["秒"] / max(1, v["字"]) for v in log.values() if v["字"] >= 8]
    med = statistics.median(rates) if rates else 0.15
    redo = [j for j in jobs if j["id"] in log and
            (log[j["id"]]["秒"] > med * j["chars"] * 1.9 + 1.0 or log[j["id"]]["秒"] < med * j["chars"] * 0.5)]
    for j in redo:
        _, data, u = one(j)
        save(j, data, u)
        print("作り直し", j["id"], f"{secs(data):.1f}秒", flush=True)
    sec = sum(v["秒"] for v in log.values())
    cost = {"カット": len(log), "作り直し": [j["id"] for j in redo], "声の合計_秒": round(sec, 1),
            "入力トークン": sum(u.get("promptTokenCount", 0) for u in use),
            "出力トークン": sum(u.get("candidatesTokenCount", 0) for u in use),
            "1字あたりの秒（中央）": round(med, 3)}
    out_tok = cost["出力トークン"] or sec * p["price"]["audio_tokens_per_sec"]
    cost["見積もり_円"] = round(out_tok / 1e6 * p["price"]["tts_usd_per_1m_audio_tokens"] * p["price"]["yen_per_usd"]
                             + cost["入力トークン"] / 1e6 * 0.5 * p["price"]["yen_per_usd"], 1)
    old = os.path.join(work, "voice", "_cost.json")
    prev = json.load(open(old, encoding="utf-8")) if os.path.exists(old) else {"回": []}
    prev["回"].append({**cost, "カットごと": log})
    prev["合計_円"] = round(sum(r["見積もり_円"] for r in prev["回"]), 1)
    json.dump(prev, open(old, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"声ができました：{len(log)}カット・合計{sec / 60:.1f}分・見積もり約{cost['見積もり_円']}円（作り直し {len(redo)}）")


# まとめて頼む（--by block・ふだんはこちら）
# Gemini TTS は1日に頼める回数に上限がある（2026-10-24 に 100回/日 で止まった）。1カット1回だと1本109回で超えるので、
# 同じ章の続いたカットを最大 BLOCK_CUTS カット・BLOCK_CHARS 字まで、2人の掛け合いとして1回で作り、無音の所で切ってカットに分ける。
# 切れ目は「字数から見込んだ位置」に近く、長い無音を選ぶ（動的計画法）。分けた長さが字数と合わなければ1回作り直し、
# それでも合わなければ、そのまとまりだけ1カットずつ作る
BLOCK_CUTS, BLOCK_CHARS = 12, 420
SPK = {"narrator": "Minato", "listener": "Yui"}


def blocks(work, ch, force, only):
    p = profile(ch)
    s = json.load(open(os.path.join(work, "script.json"), encoding="utf-8"))
    only = set(filter(None, only.split(",")))
    out, cur, chapter = [], None, "つかみ・前置き"
    for c in s["cuts"]:
        new_ch = c.get("chapter")
        chapter = new_ch or chapter
        want = c.get("narration") and (not only or c["id"] in only) and \
            (force or not os.path.exists(os.path.join(work, "voice", c["id"] + ".wav")))
        if not want or new_ch or cur is None or len(cur["cuts"]) >= BLOCK_CUTS or \
                cur["chars"] + len(c.get("tts_text") or c["narration"]) > BLOCK_CHARS:
            if cur and cur["cuts"]:
                out.append(cur)
            cur = {"chapter": chapter, "cuts": [], "chars": 0}
        if want:
            t = c.get("tts_text") or c["narration"]
            cur["cuts"].append({"id": c["id"], "who": c.get("speaker", "narrator"), "text": t, "chars": len(t),
                                "tone": tone_of(c, chapter)})
            cur["chars"] += len(t)
    if cur and cur["cuts"]:
        out.append(cur)
    return p, out


def block_turns(p, b):
    """1カット＝1行。話し方（声の調子＋章の調子）は行ごとの style に書く（3.8 は文の中の指示を読み上げてしまうため）"""
    return [(SPK[x["who"]], x["text"],
             f"{who_label(p, x['who'])}。{p['voices'][x['who']]['style']}{p['chapter_tone'].get(x['tone'] or '', '')}"
             "。東京の標準的なアクセントで。前の人の言葉のあと、約1秒の間をあけてから話す")
            for x in b["cuts"]]


def split_pcm(data, chars, want_gaps=False):
    """まとめて作った声を、無音の所で len(chars) 個に分ける。分けられなければ None"""
    import numpy as np
    with wave.open(io.BytesIO(data)) as w:
        sr = w.getframerate()
        x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32)
    hop = sr // 100  # 10ミリ秒ごと
    n = len(x) // hop
    if n < 10:
        return None
    rms = np.sqrt((x[:n * hop].reshape(n, hop) ** 2).mean(axis=1))
    loud = rms > max(200.0, 0.06 * float(np.percentile(rms, 95)))
    idx = np.flatnonzero(loud)
    if len(idx) == 0:
        return None
    s0, s1 = int(idx[0]), int(idx[-1]) + 1
    gaps, i = [], s0
    while i < s1:  # 0.15秒以上の無音を、切れ目の候補にする
        if not loud[i]:
            j = i
            while j < s1 and not loud[j]:
                j += 1
            if j - i >= 15:
                gaps.append((i, j))
            i = j
        else:
            i += 1
    k = len(chars) - 1
    if k == 0:
        cuts = []
    else:
        if len(gaps) < k:
            return None
        # 区切りを選ぶ：各カットの長さが「字数×平均の速さ」に近く、区切りの無音が長いほど良い（ずれが積み重ならないよう、カットごとの長さで見る）
        rate = (s1 - s0 - 0.6 * sum(min(b - a, 120) for a, b in gaps[:k])) / sum(chars)
        want = [c * rate for c in chars]
        sig = [max(80.0, 0.25 * w_) for w_ in want]
        M, INF = len(gaps), float("inf")
        seg = lambda a, b, j: ((b - a - want[j]) / sig[j]) ** 2
        bonus = lambda g: 4.0 * min(gaps[g][1] - gaps[g][0], 120) / 100
        dp = [[INF] * M for _ in range(k)]
        back = [[-1] * M for _ in range(k)]
        for g in range(M):
            dp[0][g] = seg(s0, gaps[g][0], 0) - bonus(g)
        for j in range(1, k):
            for g in range(j, M):
                best, arg = INF, -1
                for h in range(j - 1, g):
                    v = dp[j - 1][h] + seg(gaps[h][1], gaps[g][0], j)
                    if v < best:
                        best, arg = v, h
                dp[j][g] = best - bonus(g); back[j][g] = arg
        tot = [dp[k - 1][g] + seg(gaps[g][1], s1, k) for g in range(M)]
        g = int(np.argmin(tot))
        if tot[g] == INF:
            return None
        cuts = []
        for j in range(k - 1, -1, -1):
            cuts.append(g); g = back[j][g]
        cuts = [gaps[g] for g in reversed(cuts)]
        if min(b - a for a, b in cuts) < 35:  # 区切りの無音が0.35秒未満＝カットの境目か文の息継ぎか見分けにくい
            return None
    if want_gaps:
        return [(a * hop / sr, b * hop / sr) for a, b in cuts]
    pad = 15  # 声の前後に残す無音（0.15秒）
    starts = [s0] + [b for _, b in cuts]
    ends = [a for a, _ in cuts] + [s1]
    pieces = []
    for st, en in zip(starts, ends):
        seg = x[max(0, st - pad) * hop:min(n, en + pad) * hop].astype(np.int16).tobytes()
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr); w.writeframes(seg)
        pieces.append(buf.getvalue())
    return pieces


def pitch(data):
    """声の高さ（Hz・中央値）を（全体, 頭, 終わり）で返す。自己相関で40ミリ秒ごとに測る。測れなければ None"""
    import numpy as np
    with wave.open(io.BytesIO(data)) as w:
        sr = w.getframerate()
        x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float64)
    fr, out = int(sr * 0.04), []
    lo, hi = int(sr / 400), int(sr / 70)
    for i in range(0, len(x) - fr, fr):
        s = x[i:i + fr]
        if np.sqrt((s ** 2).mean()) < 500:
            continue
        s = s - s.mean()
        ac = np.correlate(s, s, "full")[fr - 1:]
        k = lo + int(np.argmax(ac[lo:hi]))
        if ac[k] > 0.4 * ac[0]:
            out.append(sr / k)
    if len(out) < 5:
        return None
    return float(np.median(out)), float(np.median(out[:12])), float(np.median(out[-12:]))  # 全体・頭・終わり（声の出ている約0.5秒）


# 声の高さの線（2026-10-24 の2本目・268カットで実測：語り手の中央 143Hz・聞き手の中央 222Hz。話し手が入れ替わったカットは 155Hz 以下）
# 頭と終わりは文の抑揚で大きく動く（文の頭は高く、終わりは低い）ので、ずれた時にしか出ない向きだけを見る：
# 聞き手の頭が低い＝前の語り手の声が入った（実測 139Hz。ふつうは 160Hz 以上）／語り手の終わりが高い＝次の聞き手の声が入った（実測 270Hz。ふつうは 205Hz 以下）
PITCH_NARRATOR_MAX, PITCH_LISTENER_MIN, PITCH_LISTENER_HEAD_MIN, PITCH_NARRATOR_TAIL_MAX = 200, 160, 150, 230


def pieces_ok(pieces, chars, whos=None):
    rates = [secs(d) / max(1, c) for d, c in zip(pieces, chars)]
    med = statistics.median(rates)
    if not all(0.45 * med <= r <= 2.2 * med or c < 6 for r, c in zip(rates, chars)):
        return False
    # 長さだけだと、2文あるカットの文の間を境目と取り違えて1つずつずれても通る（2026-10-24 に B19〜C04 で起きた）。
    # ずれると話し手の声が入れ替わるので、声の高さでも見る
    for d, w in zip(pieces, whos or []):
        f = pitch(d)
        if not f:
            continue
        mid, head, tail = f
        if w == "narrator" and (mid > PITCH_NARRATOR_MAX or tail > PITCH_NARRATOR_TAIL_MAX):
            return False
        if w == "listener" and (mid < PITCH_LISTENER_MIN or head < PITCH_LISTENER_HEAD_MIN):
            return False
    return True


def make_blocks(work, ch, force, only):
    p, bl = blocks(work, ch, force, only)
    if any(not p["voices"][w]["voice"] for w in SPK):
        sys.exit("【止まりました】profile.json の声が決まっていません。先に audition を動かす")
    os.makedirs(os.path.join(work, "voice"), exist_ok=True)
    voices = {SPK[w]: p["voices"][w]["voice"] for w in SPK}
    log, use, fallback, reqs = {}, [], [], 0
    print(f"{sum(len(b['cuts']) for b in bl)} カットを {len(bl)} 回に分けて頼みます", flush=True)

    def one(b):
        chars = [x["chars"] for x in b["cuts"]]
        for t in range(2):
            data, u = gemini.tts_multi(block_turns(p, b), voices, p["tts_model"])
            pcs = split_pcm(data, chars)
            if pcs and pieces_ok(pcs, chars, [x["who"] for x in b["cuts"]]):
                return b, pcs, [u] * 1, t + 1, None
            last_u = u
        return b, None, [last_u], 2, data

    try:
        with cf.ThreadPoolExecutor(2) as ex:
            for b, pcs, us, n_req, raw in ex.map(one, bl):
                use += us; reqs += n_req
                if pcs:
                    for x, d in zip(b["cuts"], pcs):
                        open(os.path.join(work, "voice", x["id"] + ".wav"), "wb").write(d)
                        log[x["id"]] = {"秒": round(secs(d), 2), "字": x["chars"], "話し手": x["who"]}
                    print(" ".join(x["id"] for x in b["cuts"]), f"{sum(secs(d) for d in pcs):.1f}秒", flush=True)
                else:
                    open(os.path.join(work, "voice", f"_block_{b['cuts'][0]['id']}.wav"), "wb").write(raw)
                    fallback += [x["id"] for x in b["cuts"]]
                    print("分けられない → 1カットずつ作る：", [x["id"] for x in b["cuts"]], flush=True)
        if fallback:
            make(work, ch, True, ",".join(fallback))
    finally:
        sec = sum(v["秒"] for v in log.values())
        cost = {"作り方": "まとめて", "頼んだ回数": reqs, "カット": len(log), "1カットずつに回した": fallback, "声の合計_秒": round(sec, 1),
                "入力トークン": sum(u.get("promptTokenCount", 0) for u in use),
                "出力トークン": sum(u.get("candidatesTokenCount", 0) for u in use)}
        out_tok = cost["出力トークン"] or sec * p["price"]["audio_tokens_per_sec"]
        cost["見積もり_円"] = round(out_tok / 1e6 * p["price"]["tts_usd_per_1m_audio_tokens"] * p["price"]["yen_per_usd"]
                                 + cost["入力トークン"] / 1e6 * 0.5 * p["price"]["yen_per_usd"], 1)
        old = os.path.join(work, "voice", "_cost.json")
        prev = json.load(open(old, encoding="utf-8")) if os.path.exists(old) else {"回": []}
        prev["回"].append({**cost, "カットごと": log})
        prev["合計_円"] = round(sum(r["見積もり_円"] for r in prev["回"]), 1)
        json.dump(prev, open(old, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"声：{len(log)}カット・{reqs}回・合計{sec / 60:.1f}分・見積もり約{cost['見積もり_円']}円", flush=True)


def main():
    a = argparse.ArgumentParser()
    a.add_argument("cmd", choices=["audition", "estimate", "make"])
    a.add_argument("target")
    a.add_argument("--ch", default="job")
    a.add_argument("--force", action="store_true")
    a.add_argument("--only", default="")
    a.add_argument("--by", choices=["block", "cut"], default="block", help="block＝まとめて頼む（ふだん）／cut＝1カットずつ")
    a = a.parse_args()
    if a.cmd == "audition":
        audition(a.target)
    elif a.cmd == "estimate":
        estimate(a.target, a.ch)
    elif a.by == "block":
        make_blocks(a.target, a.ch, a.force, a.only)
    else:
        make(a.target, a.ch, a.force, a.only)


if __name__ == "__main__":
    main()

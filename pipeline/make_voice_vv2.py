# ⑤声（VOICEVOX・感情づけ版。2026-10-27 から）：make_voice_vv.py と同じ作り方に、カットの役割ごとの感情づけ（voice_emotion.py）を足した
#   python -X utf8 pipeline\make_voice_vv2.py make <作業フォルダ> [--ch spi] [--force] [--only A01,B02]
#   python -X utf8 pipeline\make_voice_vv2.py demo <作業フォルダ> [--ch spi] --out <フォルダ> [--n 16]
#       … 役割の違うカットを選んで「今の声（平ら）」と「感情づけ」を交互につないだ試聴版と、抑揚の幅（半音）を出す。声のフォルダには書かない
#   python -X utf8 pipeline\make_voice_vv2.py plan <作業フォルダ>   … カットごとの役割の一覧だけ出す（台本の emo で直す時に見る）
# ・yt-auto の外のチャンネル（金運おきぬ）は、台本の voice（speaker・speedScale）を使う。読みの表は --yomi で渡す
# ・元の make_voice_vv.py は残す（作業中の回が使っているため）。感情づけの数値は voice_emotion.py の ROLE、チャンネルごとの上書きは profile の voicevox.emotion
import argparse, io, json, os, sys, urllib.parse, wave
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import make_voice_vv as vv
import voice_emotion as emo


def setup(work, ch, yomi_path=""):
    """話し手の番号・基本の設定・読みの置き換え表・感情の上書きを返す"""
    s = json.load(open(os.path.join(work, "script.json"), encoding="utf-8"))
    sv = s.get("voice") or {}
    if sv.get("speaker") is not None:  # 台本に声の設定がある（金運おきぬ）
        sids = {"narrator": sv["speaker"]}
        base = {"narrator": {"speed": sv.get("speedScale", 1.0)}}
        rep = json.load(open(yomi_path, encoding="utf-8")).get("replace", {}) if yomi_path and os.path.exists(yomi_path) else {}
        conf = sv.get("emotion", {})
    else:
        p = vv.profile(ch)["voicevox"]
        sids = {w: vv.speaker_id(p[w]["name"], p[w]["style"]) for w in ("narrator", "listener") if w in p}
        base = {w: p[w] for w in sids}
        rep = vv.yomi(ch)
        conf = p.get("emotion", {})
    return s, sids, base, rep, conf


def plans(s, conf):
    cuts = [c for c in s["cuts"] if c.get("narration")]
    out = []
    for i, c in enumerate(cuts):
        out.append((c, emo.plan(c, i, len(cuts), conf, chapter_start=bool(c.get("yt_chapter")))))
    return out


def synth(text, sid, base, p):
    q = json.loads(vv.call("/audio_query?" + urllib.parse.urlencode({"text": text, "speaker": sid})))
    q = emo.apply(q, p, base, text)
    q.update({"outputSamplingRate": 24000, "outputStereo": False})
    return vv.call(f"/synthesis?speaker={sid}", q, timeout=300)


def flat(text, sid, base):
    """今の作り方（make_voice_vv.synth と同じ。山場の遅さは入れない）"""
    return vv.synth(text, sid, base)


def make(work, ch, force, only, yomi_path):
    s, sids, base, rep, conf = setup(work, ch, yomi_path)
    only = set(filter(None, only.split(",")))
    os.makedirs(os.path.join(work, "voice"), exist_ok=True)
    log = {}
    for c, p in plans(s, conf):
        f = os.path.join(work, "voice", c["id"] + ".wav")
        if (only and c["id"] not in only) or (not force and os.path.exists(f)):
            continue
        who = c.get("speaker", "narrator")
        text = vv.say(c.get("tts_text") or c["narration"], rep)
        data = synth(text, sids[who], base[who], p)
        open(f, "wb").write(data)
        log[c["id"]] = {"秒": round(vv.secs(data), 2), "字": len(text), "話し手": who, "役割": p["role"]}
        print(c["id"], p["role"], f"{vv.secs(data):.1f}秒", flush=True)
    json.dump(log, open(os.path.join(work, "voice", "_emotion.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"声（感情づけ）：{len(log)}カット・合計{sum(v['秒'] for v in log.values()) / 60:.1f}分・VOICEVOX（0円）", flush=True)


def semitones(wavs):
    """声の高さの幅（下から10%〜上から10%の間の半音の数）。メモリが少なくても回るように、8kHz の yin で軽く測る
    （pyin は図解カードの書き出し中にメモリ不足で落ちた。2026-10-27）"""
    import numpy as np, librosa
    fs = []
    for data in wavs:
        y, sr = librosa.load(io.BytesIO(data), sr=8000)
        f0 = librosa.yin(y, fmin=60, fmax=450, sr=sr, frame_length=512, hop_length=128)
        rms = librosa.feature.rms(y=y, frame_length=512, hop_length=128)[0][:len(f0)]
        fs.append(f0[rms > rms.max() * 0.15])  # 声のある所だけ
    a = np.concatenate(fs)
    lo, hi = np.percentile(a, [10, 90])
    return round(float(12 * np.log2(hi / lo)), 1)


def demo(work, ch, out, n, yomi_path):
    s, sids, base, rep, conf = setup(work, ch, yomi_path)
    ps = plans(s, conf)
    # 役割ごとに散らして選ぶ（同じ役割ばかりにしない）
    by = {}
    for c, p in ps:
        by.setdefault(p["role"], []).append((c, p))
    pick, k = [], 0
    while len(pick) < n and any(by.values()):
        for r in list(by):
            if by[r] and len(pick) < n:
                pick.append(by[r].pop(len(by[r]) // 2 if k else 0))
        k += 1
    pick.sort(key=lambda cp: [c["id"] for c, _ in ps].index(cp[0]["id"]))
    os.makedirs(out, exist_ok=True)
    A, B, rows = [], [], []
    for c, p in pick:
        who = c.get("speaker", "narrator")
        text = vv.say(c.get("tts_text") or c["narration"], rep)
        A.append(flat(text, sids[who], base[who]))
        B.append(synth(text, sids[who], base[who], p))
        rows.append(f"{c['id']}\t{p['role']}\t{c['narration']}")

    def join(chunks, f, gap=0.45):
        with wave.open(f, "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(24000)
            for d in chunks:
                with wave.open(io.BytesIO(d)) as r:
                    w.writeframes(r.readframes(r.getnframes()))
                w.writeframes(b"\0\0" * int(24000 * gap))
    join(A, os.path.join(out, "A_今の声.wav"))
    join(B, os.path.join(out, "B_感情づけ.wav"))
    sa, sb = semitones(A), semitones(B)
    open(os.path.join(out, "選んだカット.tsv"), "w", encoding="utf-8").write("\n".join(rows) + "\n")
    print(f"抑揚の幅：今の声 {sa}半音 → 感情づけ {sb}半音（参考5チャンネル 9.1〜15.0・伸びている3つは 13.7〜15.0）")
    print(f"試聴版：{out}\\A_今の声.wav と B_感情づけ.wav（同じ {len(pick)} カット）")


def show_plan(work, ch, yomi_path):
    s, _, _, _, conf = setup(work, ch, yomi_path)
    cnt = {}
    for c, p in plans(s, conf):
        cnt[p["role"]] = cnt.get(p["role"], 0) + 1
        print(c["id"], p["role"], c["narration"][:50])
    print("役割の数：", cnt)


def main():
    a = argparse.ArgumentParser()
    a.add_argument("cmd", choices=["make", "demo", "plan"])
    a.add_argument("work")
    a.add_argument("--ch", default="job")
    a.add_argument("--force", action="store_true")
    a.add_argument("--only", default="")
    a.add_argument("--out", default="")
    a.add_argument("--n", type=int, default=16)
    a.add_argument("--yomi", default="")
    a = a.parse_args()
    if a.cmd == "make":
        make(a.work, a.ch, a.force, a.only, a.yomi)
    elif a.cmd == "plan":
        show_plan(a.work, a.ch, a.yomi)
    else:
        demo(a.work, a.ch, a.out or os.path.join(a.work, "_emotion_demo"), a.n, a.yomi)


if __name__ == "__main__":
    main()

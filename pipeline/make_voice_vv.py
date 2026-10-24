# ⑤声（VOICEVOX 版・2026-10-24 から仕事チャンネルの声はこちら）：VOICEVOX ENGINE で、語り手と聞き手の声をカットごとに作る
#   python -X utf8 pipeline\make_voice_vv.py make <作業フォルダ> [--ch job] [--force] [--only A01,B02]
#   python -X utf8 pipeline\make_voice_vv.py audition <チャンネル>   … 候補の声で同じ文を読ませて voice_audition_vv\ に置く（聞いて決める）
# ・Gemini 版（make_voice_job.py）から替えた理由：1日100回の上限・前払い残高切れで止まる／上限を避けるまとめ作りで、カットの境目がずれる（2026-10-24 の2本目）
# ・お金はかからない。1カットずつ作るので境目はずれない。同じ文なら毎回同じ声になる
# ・エンジンの場所は環境変数 VOICEVOX_URL（ふだんは http://127.0.0.1:50021。GitHub Actions ではサービスのコンテナ）
# ・声のキャラ・速さ・高さは profile.json の voicevox。キャラは名前とスタイル名で指定し、番号はエンジンに聞いて決める
# ・クレジット（キャラの規約で必須）を voice\_credit.txt に書く。upload_job.py が説明文の最後に足す
# ・作ってある声は飛ばす。読み間違えやすい語は、カットの tts_text に読みを書く
import argparse, io, json, os, sys, urllib.error, urllib.parse, urllib.request, wave

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
URL = os.environ.get("VOICEVOX_URL", "http://127.0.0.1:50021")


def profile(ch):
    return json.load(open(os.path.join(ROOT, "channels", ch, "profile.json"), encoding="utf-8"))


def call(path, body=None, timeout=120):
    req = urllib.request.Request(URL + path, data=json.dumps(body).encode() if body is not None else (b"" if "?" in path else None),
                                 method="POST" if body is not None or "?" in path else "GET",
                                 headers={"Content-Type": "application/json"})
    try:
        return urllib.request.urlopen(req, timeout=timeout).read()
    except urllib.error.URLError as e:
        sys.exit(f"【止まりました】VOICEVOX ENGINE に届きません（{URL}）：{e}。エンジンを起動してから、もう一度実行してください")


def speaker_id(name, style):
    for sp in json.loads(call("/speakers")):
        if sp["name"] == name:
            for st in sp["styles"]:
                if st["name"] == style:
                    return st["id"]
            sys.exit(f"【止まりました】{name} にスタイル「{style}」がありません：{[st['name'] for st in sp['styles']]}")
    sys.exit(f"【止まりました】VOICEVOX に {name} がいません（エンジンの版を確かめる）")


def synth(text, sid, v, slow=1.0):
    q = json.loads(call("/audio_query?" + urllib.parse.urlencode({"text": text, "speaker": sid})))
    q.update({"speedScale": v.get("speed", 1.0) * slow, "pitchScale": v.get("pitch", 0.0),
              "intonationScale": v.get("intonation", 1.0), "volumeScale": v.get("volume", 1.0),
              "prePhonemeLength": 0.1, "postPhonemeLength": 0.1, "outputSamplingRate": 24000, "outputStereo": False})
    return call(f"/synthesis?speaker={sid}", q, timeout=300)


def secs(data):
    with wave.open(io.BytesIO(data)) as w:
        return w.getnframes() / w.getframerate()


def make(work, ch, force, only):
    p = profile(ch)
    vv = p["voicevox"]
    sids = {w: speaker_id(vv[w]["name"], vv[w]["style"]) for w in ("narrator", "listener")}
    s = json.load(open(os.path.join(work, "script.json"), encoding="utf-8"))
    only = set(filter(None, only.split(",")))
    os.makedirs(os.path.join(work, "voice"), exist_ok=True)
    log = {}
    for c in s["cuts"]:
        f = os.path.join(work, "voice", c["id"] + ".wav")
        if not c.get("narration") or (only and c["id"] not in only) or (not force and os.path.exists(f)):
            continue
        who = c.get("speaker", "narrator")
        text = c.get("tts_text") or c["narration"]
        # 山場とクイズは少しだけゆっくり（Gemini 版の「数字の所は一段ゆっくり」の代わり）
        data = synth(text, sids[who], vv[who], vv.get("slow_strong", 0.94) if (c.get("strong") or c.get("quiz")) else 1.0)
        open(f, "wb").write(data)
        log[c["id"]] = {"秒": round(secs(data), 2), "字": len(text), "話し手": who}
        print(c["id"], f"{secs(data):.1f}秒", flush=True)
    open(os.path.join(work, "voice", "_credit.txt"), "w", encoding="utf-8").write(vv["credit"] + "\n")
    old = os.path.join(work, "voice", "_cost.json")
    prev = json.load(open(old, encoding="utf-8")) if os.path.exists(old) else {"回": []}
    sec = sum(v["秒"] for v in log.values())
    prev["回"].append({"作り方": "VOICEVOX", "声": {w: f"{vv[w]['name']}（{vv[w]['style']}）" for w in sids}, "カット": len(log),
                      "声の合計_秒": round(sec, 1), "見積もり_円": 0.0, "カットごと": log})
    prev["合計_円"] = round(sum(r["見積もり_円"] for r in prev["回"]), 1)
    json.dump(prev, open(old, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"声：{len(log)}カット・合計{sec / 60:.1f}分・VOICEVOX（0円）", flush=True)


def audition(ch):
    p = profile(ch)
    vv = p["voicevox"]
    out = os.path.join(ROOT, "channels", ch, "voice_audition_vv")
    os.makedirs(out, exist_ok=True)
    lines = {"narrator": "年収約453万円で1位の仕事が、時給に直すと、6つの中で最下位に落ちます。そして1位は、バス運転手。年収は約453万円です。",
             "listener": "えっ、年収は1位だったのに。それ、うちの部署もみんなやってます。"}
    for who, cands in vv["candidates"].items():
        for name, style in cands:
            data = synth(lines[who], speaker_id(name, style), vv[who])
            open(os.path.join(out, f"{who}_{name}_{style}.wav"), "wb").write(data)
            print(who, name, style, f"{secs(data):.1f}秒", flush=True)


def main():
    a = argparse.ArgumentParser()
    a.add_argument("cmd", choices=["audition", "make"])
    a.add_argument("target")
    a.add_argument("--ch", default="job")
    a.add_argument("--force", action="store_true")
    a.add_argument("--only", default="")
    a = a.parse_args()
    if a.cmd == "audition":
        audition(a.target)
    else:
        make(a.target, a.ch, a.force, a.only)


if __name__ == "__main__":
    main()

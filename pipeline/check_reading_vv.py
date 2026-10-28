# ⑤の後（VOICEVOX の声の読み点検）：VOICEVOX がどう読むか（カタカナの読み）を出し、台本の文と食い違う所を Claude に探させる
#   python -X utf8 pipeline\check_reading_vv.py <作業フォルダ> [--ch job]
# ・声は耳で聞けないので、読みの文字で見る（数字・単位・英字・職業名・地名の読み違い、アクセントの位置は見ない）
# ・読み違いが見つかったカットは、script.json の tts_text に正しい読み（ひらがな）を書き、make_voice_vv.py --force --only で作り直す
# ・結果は voice\_reading.json。読み違いがあれば終了コード1
import argparse, json, os, sys, urllib.parse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gemini
import make_voice_vv as vv

BATCH = 40


def hints(work):
    """yomi_auto.py（辞書 Sudachi との照らし合わせ）が voice/_yomi_auto.json に残した食い違いを、カットごとの目印にする
    （2026-10-28 本人の指摘。スキル references/16 の5・7。Gemini を呼ぶ回数は増やさない。ファイルが無ければ空）"""
    p = os.path.join(work, "voice", "_yomi_auto.json")
    if not os.path.exists(p):
        return {}
    out = {}
    for c in json.load(open(p, encoding="utf-8")).get("カット", []):
        xs = [f"{x['語']}（辞書 {x['辞書の読み']}／声 {x['声の読み']}）" for x in c.get("食い違い", [])]
        if xs:
            out[c["id"]] = "、".join(xs)
    return out


def main():
    a = argparse.ArgumentParser()
    a.add_argument("work")
    a.add_argument("--ch", default="job")
    a.add_argument("--fix", action="store_true", help="読み違いのカットに tts_text を書いて、声を作り直す")
    a = a.parse_args()
    prof = vv.profile(a.ch)
    p = prof["voicevox"]
    sid = vv.speaker_id(p["narrator"]["name"], p["narrator"]["style"])
    sf = os.path.join(a.work, "script.json")
    s = json.load(open(sf, encoding="utf-8"))
    cuts = [c for c in s["cuts"] if c.get("narration")]
    rows = []
    for c in cuts:
        t = c.get("tts_text") or c["narration"]
        q = json.loads(vv.call("/audio_query?" + urllib.parse.urlencode({"text": t, "speaker": sid})))
        rows.append({"id": c["id"], "文": t, "読み": q["kana"].replace("'", "").replace("_", "")})
    S = {"type": "string"}
    sch = {"type": "object", "properties": {"読み違い": {"type": "array", "items": {"type": "object", "properties": {
        "id": S, "語": S, "今の読み": S, "正しい読み": S, "tts_text": S}, "required": ["id", "語", "今の読み", "正しい読み", "tts_text"]}}},
        "required": ["読み違い"]}
    hint = hints(a.work)
    if hint:
        print(f"辞書との食い違いの目印：{len(hint)}カット（voice/_yomi_auto.json）")
    bad = []
    for i in range(0, len(rows), BATCH):
        part = rows[i:i + BATCH]
        q = ("日本語の読み上げソフトが、台本の文をどう読むか（カタカナ。/ と、 は区切り）を並べました。"
             f"{prof.get('topic') or '日本の仕事と年収の統計を解説する動画'}です。読みが間違っている語（数字・単位・年・英字・職業名・地名・固有名詞・同じ字で読みが違う語）だけを挙げてください。"
             "アクセント・区切り・カタカナの書き方の違いは挙げないでください。間違いが無ければ空の配列。"
             "tts_text には、そのカットの文全体を、間違えた語だけひらがなに直して書いてください。"
             "「辞書との食い違い」は、辞書（Sudachi）の読みと読み上げソフトの読みが違った語の機械の目印です。必ず確かめ、文脈で正しい方を決めてください（辞書の方が間違えることもあります）。\n\n"
             + "\n".join(f"{r['id']}｜文：{r['文']}｜読み：{r['読み']}" + (f"｜辞書との食い違い：{hint[r['id']]}" if r["id"] in hint else "")
                         for r in part))
        t, _ = gemini.ask(q, schema=sch)
        bad += json.loads(t)["読み違い"]
    json.dump({"読み": rows, "読み違い": bad}, open(os.path.join(a.work, "voice", "_reading.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"読みの点検：{len(rows)}カット・読み違い {len(bad)}")
    for b in bad:
        print(f"  {b['id']}：{b['語']} を「{b['今の読み']}」→「{b['正しい読み']}」")
    if bad and a.fix:
        by = {c["id"]: c for c in s["cuts"]}
        for b in bad:
            if b["id"] in by and b["tts_text"].strip():
                by[b["id"]]["tts_text"] = b["tts_text"].strip()
        json.dump(s, open(sf, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        vv.make(a.work, a.ch, True, ",".join(sorted({b["id"] for b in bad})))
        print("読み違いのカットに tts_text を書き、声を作り直しました")
        return
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()

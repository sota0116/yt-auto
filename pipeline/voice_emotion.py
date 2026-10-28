# 声の感情づけ（2026-10-27 から）：カットの役割を台本から見分けて、VOICEVOX の速さ・高さ・抑揚・間・語の強調を変える
#   make_voice_vv2.py が読み込む。カットに "emo" を書けば、見分けより優先する（hook／reveal／question／strong／aruaru／quiet／plain）
# ・なぜ：全カットを同じ設定で読むと、抑揚の幅が 9.0半音（千年こよみ001・玄野武宏）。参考5チャンネルは 9.1〜15.0半音で、
#   伸びている3つ（FloatingStories・先祖のしわざ・俯瞰の日本史）は 13.7〜15.0半音（_research\spi_bench2_2026-10-27\av_measure.json）
# ・強めすぎると芝居がかる。数値は「試聴版 → 本人が聞く」で決める初期値（推測）。profile の voicevox.emotion で上書きできる
import re

# 役割ごとの初期値。speed・intonation は掛け算、pitch は足し算（VOICEVOX の pitchScale。0.01 ≒ 0.2半音）、pre・post は秒
ROLE = {
    "hook":     {"speed": 0.97, "intonation": 1.30, "pitch": 0.02, "pre": 0.10, "post": 0.25},
    "reveal":   {"speed": 0.95, "intonation": 1.25, "pitch": 0.00, "pre": 0.40, "post": 0.20},
    "question": {"speed": 0.97, "intonation": 1.25, "pitch": 0.01, "pre": 0.15, "post": 0.45},
    "strong":   {"speed": 0.92, "intonation": 1.30, "pitch": -0.02, "pre": 0.30, "post": 0.45},
    "aruaru":   {"speed": 1.03, "intonation": 1.20, "pitch": 0.01, "pre": 0.10, "post": 0.15},
    "quiet":    {"speed": 0.94, "intonation": 1.05, "pitch": -0.03, "pre": 0.20, "post": 0.40},
    "plain":    {"speed": 1.00, "intonation": 1.15, "pitch": 0.00, "pre": 0.10, "post": 0.12},
}
REVEAL = re.compile(r"^(ところが|実は|じつは|しかし|でも|けれど|なのに|ただ、|ただし|本当は|逆に|それなのに|すると)|ところが|実は|本当は")
QUESTION = re.compile(r"(か|のか|でしょうか|ますか|ですか)[。？?]?$|[？?]$")
ASK_VIEWER = re.compile(r"(ますか|ですか|でしょうか|ませんか)[。？?]?$")
ARUARU = re.compile(r"(つい|うっかり|ありますよね|よね[。]?$|ませんか[。]?$|しまう|しまった|忘れて)")
# 強調する語：数・日付・吉日の名前・「だけ」「最強」など（この語を含む言葉のまとまりを少し高く、少し長く）
KEY = re.compile(r"[0-9０-９一二三四五六七八九十百千万億]+(年|月|日|回|円|倍|か所|つ|人|分|秒|歳|割)|最強|だけ|たった|初めて|唯一|いちばん|一番|半分|倍")


def role(cut, i, n, chapter_start=False):
    """カットの役割。台本の emo が最優先。次に strong・quiz・締め・冒頭の順"""
    if cut.get("emo") in ROLE:
        return cut["emo"]
    t = (cut.get("narration") or "").strip()
    if cut.get("strong"):
        return "strong"
    if cut.get("quiz") or (QUESTION.search(t) and len(t) <= 45):
        return "question"
    if i >= n - 2:
        return "quiet"
    if i < 3:
        return "hook"
    if REVEAL.search(t):
        return "reveal"
    if ARUARU.search(t):
        return "aruaru"
    return "plain"


def plan(cut, i, n, conf=None, chapter_start=False):
    r = role(cut, i, n, chapter_start)
    p = dict(ROLE[r])
    p.update((conf or {}).get(r, {}))
    if chapter_start:  # 章の頭は前に少し間（聞く人が切り替わりに気づく）
        p["pre"] = max(p["pre"], 0.35)
    p["role"] = r
    return p


def apply(q, p, base, text):
    """audio_query（q）に感情づけを入れる。base は profile の voicevox の話し手の設定（speed・pitch・intonation・volume）"""
    q.update({"speedScale": base.get("speed", 1.0) * p["speed"],
              "pitchScale": base.get("pitch", 0.0) + p["pitch"],
              "intonationScale": base.get("intonation", 1.0) * p["intonation"],
              "volumeScale": base.get("volume", 1.0),
              "prePhonemeLength": p["pre"], "postPhonemeLength": p["post"]})
    aps = q["accent_phrases"]
    # 強調：KEY に当たる語を含む言葉のまとまりを、高く（+0.12 ≒ 2半音）・少し長く。前のまとまりの後に短い間
    if KEY.search(text):
        for k, ap in enumerate(aps):
            kana = "".join(m["text"] for m in ap["moras"])
            if not _is_key(kana):
                continue
            for m in ap["moras"]:
                if m["pitch"] > 0:
                    m["pitch"] += 0.12
                m["vowel_length"] *= 1.12
            if k > 0 and aps[k - 1].get("pause_mora") is None and p["role"] in ("strong", "reveal", "hook"):
                aps[k - 1]["pause_mora"] = {"text": "、", "consonant": None, "consonant_length": None,
                                            "vowel": "pau", "vowel_length": 0.18, "pitch": 0.0}
    # 見ている人への問い（〜ますか。）は語尾を上げる。「なぜ〜のか。」のような自問は下げたまま
    if aps and p["role"] == "question" and ASK_VIEWER.search(text.strip()):
        aps[-1]["is_interrogative"] = True
    return q


# カナにした時に強調したい音（数・最強・だけ など）
KEY_KANA = re.compile(r"(イチ|ニ|サン|ヨン|ゴ|ロク|ナナ|ハチ|キュウ|キュー|ジュウ|ジュー|ヒャク|ビャク|ピャク|セン|ゼン|マン|オク)"
                      r".*(ネン|ガツ|ニチ|カ|カイ|エン|バイ|ツ|ニン|フン|ビョウ|サイ|ワリ)|サイキョ|ダケ|タッタ|ハジメテ|ユイイツ|イチバン|ハンブン")


def _is_key(kana):
    return bool(KEY_KANA.search(kana))

# ⑤声（金運おきぬ・2026-10-29 新設）：おきぬの声（波音リツ id 9）と、登場人物ごとの声（characters.json の voice）をカットごとに作る
#   python -X utf8 pipeline/make_voice_okinu.py <作業フォルダ> [--ch okinu] [--force] [--only C01,C02]
# ・make_voice_vv.py（共有）は narrator と listener の2つしか声を持てないので、スキルの make_voice.py（人物ごとの声・1音ずつの長さ voice/<id>.vv.json・
#   voice/_credits.txt に対応）を、共有の make_voice_vv.py の部品（エンジンの場所 VOICEVOX_URL・読みの表 yomi.json の dict をエンジンに入れる）と組み合わせた
# ・声の速さ：ショートは 1.0 で作って組み立てで 1.3 倍（手順書 §5）。長尺（v1.7）も 1.0 で作って組み立ても 1.0 倍（手順書 §4。声は script.json の voice.speedScale＝finish が 1.0 を入れる）
# ・読み：yomi.json の replace を tts_text の無いカットの声の文に当てる（スキルの make_voice.py --yomi）／dict はエンジンの辞書に入れる（毎回。クラウドのエンジンは毎回まっさら）
# ・共有ポーズ絵：作業フォルダが消えて run_daily が控えから戻した回は、声の段から続く。控えに絵は無く、Lovart の受け取り直しの対象でもないので、ここで assets/poses から写し直す（finish と同じ place_pose）
# ・台本全体の "voices"（人物の id → 声の番号）と、セリフのカットの "voice" で人物の声になる。何も書かないカットはおきぬ
import argparse, json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "vendor", "youtube-video-maker", "scripts"))
import make_voice_vv as V  # noqa: E402
import make_voice as MV  # noqa: E402  スキル
from write_script_okinu import place_pose  # noqa: E402


def main():
    a = argparse.ArgumentParser()
    a.add_argument("work")
    a.add_argument("--ch", default="okinu")
    a.add_argument("--force", action="store_true")
    a.add_argument("--only", default="")
    a = a.parse_args([x for x in sys.argv[1:] if x != "make"])  # run_daily.py は <作業フォルダ> --ch の形で呼ぶ（"make" が付いても通す）
    work = os.path.abspath(a.work)
    s = json.load(open(os.path.join(work, "script.json"), encoding="utf-8"))
    for c in s.get("cuts", []):
        if str(c.get("img_from", "")).startswith("pose:"):
            place_pose(work, c)  # 絵があれば何もしない
    MV.VOICEVOX = V.URL  # スキルは 127.0.0.1:50021 固定。クラウドは環境変数 VOICEVOX_URL
    V.yomi(a.ch)  # dict をエンジンの辞書に入れる（replace はスキルの --yomi が当てる）
    v = s.get("voice") or {}
    speed = float(v.get("speedScale") or 1.0)
    for cid, spk in (s.get("voices") or {}).items():
        print(f"人物の声：{cid} → {spk}", flush=True)
    argv = [os.path.join(MV.__file__), work, "--engine", "voicevox", "--speaker", str(v.get("speaker", 9)), "--speed", str(speed),
            "--yomi", os.path.join(ROOT, "channels", a.ch, "yomi.json")]
    if a.force:
        argv.append("--force")
    if a.only:
        argv += ["--only", a.only]
    sys.argv = argv
    MV.main()


if __name__ == "__main__":
    main()

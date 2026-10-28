# ⑤声（アナザー日本紀・2026-10-29 新設）：動画スキルの make_voice.py を VOICEVOX 青山龍星（ノーマル・id 13）で回す入れ物
#   python -X utf8 pipeline/make_voice_nihongi.py <作業フォルダ> [--ch nihongi]
# ・VOICEVOX が起動するのを待つ（最大5分）。人物のセリフ用の声は 台本の voices で決まる（スキルが voice/<id>.wav を作り、voice/_credits.txt に使った声を全部書く）
# ・読みは channels/nihongi/yomi.json の replace（tts_text の無いカットに当てる）
# ・終わったら、字のあるカットの wav が全部あるか・_credits.txt があるか・青山龍星が入っているかを確かめる（足りなければ終了コード1）
import argparse, json, os, sys, time, urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from nihongi_common import CDIR, vendor_ok, vendor_run  # noqa: E402

SPEAKER = 13  # 青山龍星 ノーマル


def wait_engine(minutes=5):
    url = "http://127.0.0.1:50021/version"  # 動画スキルの make_voice.py はここ固定（クラウドはサービスのコンテナをこのポートに出す）
    end = time.time() + minutes * 60
    while time.time() < end:
        try:
            urllib.request.urlopen(url, timeout=5).read()
            return True
        except Exception:
            time.sleep(5)
    return False


def main():
    a = argparse.ArgumentParser()
    a.add_argument("work")
    a.add_argument("--ch", default="nihongi")
    a.add_argument("--force", action="store_true")
    a = a.parse_args()
    work = os.path.abspath(a.work)
    bad = vendor_ok()
    if bad:
        sys.exit(f"【止まりました】{bad}")
    if not wait_engine():
        sys.exit("【止まりました】VOICEVOX が起動しません（5分待った）")
    args = [work, "--engine", "voicevox", "--speaker", str(SPEAKER), "--yomi", os.path.join(CDIR, "yomi.json")] + (["--force"] if a.force else [])
    r = vendor_run("make_voice.py", *args, capture=False)
    if r.returncode:
        sys.exit(f"【止まりました】make_voice.py が失敗しました（終了コード {r.returncode}）")
    s = json.load(open(os.path.join(work, "script.json"), encoding="utf-8"))
    miss = [c["id"] for c in s["cuts"] if c.get("narration") and not os.path.exists(os.path.join(work, "voice", c["id"] + ".wav"))]
    cp = os.path.join(work, "voice", "_credits.txt")
    if miss:
        sys.exit(f"【止まりました】声の無いカット：{miss[:10]}")
    if not os.path.exists(cp) or "VOICEVOX:青山龍星" not in open(cp, encoding="utf-8").read():
        sys.exit("【止まりました】voice/_credits.txt が無いか、青山龍星が入っていません")
    print("声：", sum(1 for c in s["cuts"] if c.get("narration")), "カット・", open(cp, encoding="utf-8").read().split())


if __name__ == "__main__":
    main()

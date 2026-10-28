# ⑦組み立て（アナザー日本紀・2026-10-29 新設）：動画スキルの build_short.py／build_long.py → loudnorm2（−14 LUFS の2回測り）
#   python -X utf8 pipeline/build_nihongi.py <作業フォルダ>
# ・ショートは short.mp4（1080x1920）、横動画は long.mp4（1920x1080。chapters.txt も作る）。字幕・帯・hook・セーフゾーンはスキルの build_*.py が台本どおりに作る（制作ルール §6）
# ・スキルの出力は _raw.mp4 に作り、loudnorm2 で整えた物を最終の名前にして、_raw.mp4 は消す
# ・ショートは safezone_check.png も残る（gate_video_nihongi が見る）
import os, subprocess, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from nihongi_common import vendor_ok, vendor_run, kind_of_work  # noqa: E402
import loudnorm2  # noqa: E402


def main():
    work = os.path.abspath(sys.argv[1])
    bad = vendor_ok()
    if bad:
        sys.exit(f"【止まりました】{bad}")
    kind = kind_of_work(work)
    raw = os.path.join(work, "_raw.mp4")
    out = os.path.join(work, "long.mp4" if kind == "long" else "short.mp4")
    r = vendor_run("build_long.py" if kind == "long" else "build_short.py", work, "--out", raw, capture=False)
    if r.returncode or not os.path.exists(raw):
        sys.exit(f"【止まりました】組み立てに失敗しました（終了コード {r.returncode}）")
    tmp = os.path.join(work, "_loudnorm_pass1.mp4")
    loudnorm2.apply(raw, tmp, loudnorm2.measure(raw), True)
    loudnorm2.apply(tmp, out, loudnorm2.measure(tmp), False)
    for f in (tmp, raw):
        if os.path.exists(f):
            os.remove(f)
    print(f"声の大きさ {loudnorm2.lufs(out):.1f} LUFS → {out}")


if __name__ == "__main__":
    main()

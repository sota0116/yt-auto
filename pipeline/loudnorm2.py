# 組み立てた mp4 の音量を -14 LUFS あたりにそろえる（2回測る loudnorm。アナザー日本紀 制作ルール §6 の手順）
#   python -X utf8 pipeline/loudnorm2.py <入力.mp4> <出力.mp4>
# ・元は手元の OneDrive\ClaudeBackup\tools\youtube\loudnorm2.py（2026-10-28）。クラウドには OneDrive が無いので、同じ中身を repo に写した（2026-10-29）
# ・1回目は linear=true（音の形を変えずに上げる）。-15.7 ほどで止まるので、2回目は linear=false・TP -1.0 でもう一度かける
# ・映像はそのまま（-c:v copy）。最後に出来上がりの音量を測って出す
import json, os, re, subprocess, sys


def measure(p, extra=""):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", p, "-af", f"loudnorm=I=-14:TP=-1.0:LRA=11{extra}:print_format=json", "-f", "null", "-"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace").stderr
    return json.loads(re.findall(r"\{[^{}]*\}", r)[-1])


def apply(src, dst, m, linear):
    af = (f"loudnorm=I=-14:TP=-1.0:LRA=11:measured_I={m['input_i']}:measured_TP={m['input_tp']}:measured_LRA={m['input_lra']}:"
          f"measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear={'true' if linear else 'false'}")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", src, "-c:v", "copy", "-af", af, "-ar", "48000", "-c:a", "aac", "-b:a", "192k",
                    "-movflags", "+faststart", dst], check=True)


def lufs(p):
    return float(measure(p)["input_i"])


def main():
    src, dst = sys.argv[1], sys.argv[2]
    tmp = os.path.join(os.path.dirname(os.path.abspath(dst)), "_loudnorm_pass1.mp4")
    apply(src, tmp, measure(src), True)
    apply(tmp, dst, measure(tmp), False)
    os.remove(tmp)
    print(f"{os.path.basename(dst)}：{measure(dst)['input_i']} LUFS")


if __name__ == "__main__":
    main()

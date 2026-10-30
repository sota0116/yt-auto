# ⑧b 完成動画ゲート（金運おきぬ・2026-10-29 新設）：出来上がった動画を、上げる前に機械で見る（Claude に画面を見せる判定は入れていない）
#   python -X utf8 pipeline/gate_video_okinu.py <作業フォルダ> [--video short.mp4|long.mp4]
# ・種類：作業フォルダの名前が S… か script.json の format が short ならショート。それ以外は長尺
# ・形：ショートは 1080x1920・59.5秒以内（ふつうは 25〜45秒）／長尺は 1920x1080 以上の横・8〜16分（1440p の 2560x1440 も可）
# ・声の大きさ：ショート −15 LUFS・長尺 −15 LUFS（v1.7） の ±1.5 以内（ffmpeg の ebur128）
# ・無音：ショートは2秒以上、長尺は3秒以上続く無音が無い（silencedetect −45dB）
# ・ショートの動く絵：build_report.json の「動く絵のカット」が2以上かを注意として出す（Kling を回さない間は静止画に寄りを付けるだけなので、落とさない）
# ・結果は _gate_video.json。不合格があれば終了コード1
import argparse, json, os, re, subprocess, sys


def ff(args):
    return subprocess.run(["ffmpeg", "-hide_banner", "-nostats"] + args, capture_output=True, text=True, encoding="utf-8", errors="replace").stderr


def probe(v):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height:format=duration",
                        "-of", "json", v], capture_output=True, text=True).stdout
    j = json.loads(r)
    return int(j["streams"][0]["width"]), int(j["streams"][0]["height"]), float(j["format"]["duration"])


def main():
    a = argparse.ArgumentParser()
    a.add_argument("work")
    a.add_argument("--video")
    a = a.parse_args()
    work = os.path.abspath(a.work)
    s = json.load(open(os.path.join(work, "script.json"), encoding="utf-8"))
    short = bool(re.match(r"S\d", os.path.basename(work))) or s.get("format") == "short"
    v = os.path.join(work, a.video or ("short.mp4" if short else "long.mp4"))
    if not os.path.exists(v):
        sys.exit(f"【止まりました】動画がありません：{v}")
    w, h, sec = probe(v)
    ng, note = [], []
    if short:
        if (w, h) != (1080, 1920):
            ng.append(f"形が縦 1080x1920 ではありません（{w}x{h}）")
        if sec > 59.5:
            ng.append(f"{sec:.1f}秒（ショートは59.5秒以内）")
        target, sil = -15.0, 2.0
    else:
        if h not in (1080, 1440) or w != h * 16 // 9:
            ng.append(f"形が横 16:9（1920x1080 か 2560x1440）ではありません（{w}x{h}）")
        if not 480 <= sec <= 960:
            ng.append(f"{sec / 60:.1f}分（長尺は8〜16分）")
        target, sil = -15.0, 3.0
    log = ff(["-i", v, "-af", "ebur128=peak=true", "-f", "null", "-"])
    m = re.findall(r"I:\s+(-?[\d.]+) LUFS", log)
    lufs = float(m[-1]) if m else None
    if lufs is None or abs(lufs - target) > 1.5:
        ng.append(f"声の大きさ {lufs} LUFS（{target}±1.5）")
    sl = ff(["-i", v, "-af", "silencedetect=n=-45dB:d=%s" % sil, "-f", "null", "-"])
    longs = [float(x) for x in re.findall(r"silence_duration:\s*([\d.]+)", sl)]
    if longs:
        ng.append(f"{sil:.0f}秒以上の無音が {len(longs)} か所（最長 {max(longs):.1f}秒）")
    if short:
        rp = os.path.join(work, "build_report.json")
        mv = (json.load(open(rp, encoding="utf-8")) if os.path.exists(rp) else {}).get("動く絵のカット")
        if mv is not None and mv < 2:
            note.append(f"動く絵のカットが {mv}（手順書 §6 は2以上。Kling を回していない間は静止画に寄りを付けるだけ）")
    res = {"種類": "short" if short else "long", "動画": os.path.basename(v), "形": f"{w}x{h}", "秒": round(sec, 1), "LUFS": lufs,
           "NG": ng, "注意": note, "合格": not ng}
    json.dump(res, open(os.path.join(work, "_gate_video.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"完成動画ゲート：{res['種類']}・{w}x{h}・{sec:.1f}秒・{lufs} LUFS／NG {len(ng)}件・注意 {len(note)}件")
    for x in ng:
        print("  NG", x)
    for x in note:
        print("  注意", x)
    sys.exit(0 if not ng else 1)


if __name__ == "__main__":
    main()

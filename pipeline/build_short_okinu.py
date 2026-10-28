# ⑦ショートの組み立て（金運おきぬ・2026-10-29 新設）：声・絵・字幕・BGM をスキルの build_short.py でつなぎ、−15 LUFS にそろえる
#   python -X utf8 pipeline/build_short_okinu.py <作業フォルダ> [--out short.mp4]
# ・手順書 §5（S001 で決めた組み立て）：config.json に bgm_volume 0.02 → build_short.py → loudnorm で −15 LUFS（そのままだと −22.9 LUFS）。tempo 1.3 は script.json
# ・BGM：channels/okinu/assets/bgm/okinu_bgm_01_seed1.m4a（自作の曲を m4a にして repo に入れた）。環境変数 OKINU_BGM があればそちら。どちらも無ければ止まる（BGM 無しで出さない）
# ・切り出し（funnel.kind が 切り出し）：長尺の絵（neta.json の long_dir/images。手元だけ）を縦に置き直して images/ に置いてから組み立てる
#   （landscape_to_portrait.py と同じ：上下は同じ絵をぼかして暗くした背景、真ん中に高さ1100で置く。元の大きさの絵があればそちらを使う）
# ・できあがりの点検：長さ（ショートは60秒以内）・LUFS（−15±1）・動く絵のカット数（2以上）・【画質】の有無・セーフゾーン確認画像（safezone_check.png）
#   結果は build_report.json に残す。LUFS が外れたら終了コード1
import argparse, glob, json, os, re, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILL_SCRIPTS = os.path.join(ROOT, "vendor", "youtube-video-maker", "scripts")
sys.path.insert(0, SKILL_SCRIPTS)
TARGET = -15.0
W, H, TOP, BAND = 1080, 1920, 520, 1100


def bgm_path():
    p = os.environ.get("OKINU_BGM") or os.path.join(ROOT, "channels", "okinu", "assets", "bgm", "okinu_bgm_01_seed1.m4a")
    if not os.path.exists(p):
        sys.exit(f"【止まりました】BGM がありません：{p}（環境変数 OKINU_BGM か channels/okinu/assets/bgm/）")
    return p


def to_portrait(src, dst, cx=0.55):
    """横の絵を縦 1080x1920 に置き直す（landscape_to_portrait.py と同じ）"""
    from PIL import Image, ImageDraw, ImageEnhance, ImageFilter
    d, f = os.path.split(src)
    raw = sorted(glob.glob(os.path.join(d, "_lovart", os.path.splitext(f)[0], "*.png")))
    if raw and not os.path.exists(os.path.join(d, "_orig", f)) and Image.open(raw[-1]).size[1] > Image.open(src).size[1]:
        src = raw[-1]  # Lovart から届いた元の大きさの絵（縮めた絵を引き伸ばすとぼやける。手順書 §6）
    im = Image.open(src).convert("RGB")
    w, h = im.size
    bw = int(w * H / h)
    bg = im.resize((bw, H), Image.LANCZOS).crop(((bw - W) // 2, 0, (bw - W) // 2 + W, H))
    bg = ImageEnhance.Brightness(bg.filter(ImageFilter.GaussianBlur(40))).enhance(0.5)
    fw = int(w * BAND / h)
    fg = im.resize((fw, BAND), Image.LANCZOS)
    x0 = min(max(0, int(fw * cx - W / 2)), fw - W)
    fg = fg.crop((x0, 0, x0 + W, BAND))
    mask = Image.new("L", (W, BAND), 255)
    dr = ImageDraw.Draw(mask)
    for i in range(60):
        dr.line((0, i, W, i), fill=int(255 * i / 60)); dr.line((0, BAND - 1 - i, W, BAND - 1 - i), fill=int(255 * i / 60))
    bg.paste(fg, (0, TOP), mask)
    bg.save(dst)


def prepare_cut(work, s):
    neta = json.load(open(os.path.join(work, "neta.json"), encoding="utf-8")) if os.path.exists(os.path.join(work, "neta.json")) else {}
    long_dir = neta.get("long_dir") or ""
    if not long_dir or not os.path.isdir(os.path.join(long_dir, "images")):
        sys.exit("【止まりました】切り出し元の長尺の絵が見つかりません（neta.json の long_dir/images。クラウドは絵を消すので、切り出しは手元だけ）")
    os.makedirs(os.path.join(work, "images"), exist_ok=True)
    bases = sorted({sh.split("@")[0] for c in s["cuts"] for sh in (c.get("shots") or [])})
    for b in bases:
        dst = os.path.join(work, "images", b + ".png")
        src = os.path.join(long_dir, "images", b + ".png")
        if os.path.exists(dst):
            continue
        if not os.path.exists(src):
            sys.exit(f"【止まりました】長尺の絵 {b} が {long_dir}\\images に無い")
        to_portrait(src, dst)
    print(f"切り出し：長尺の絵 {len(bases)} 枚を縦に置き直しました")


def measure(path):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", path, "-af", "ebur128=peak=true", "-f", "null", "-"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    t = r.stderr[r.stderr.rfind("Summary:"):]
    i = re.search(r"I:\s+(-?[\d.]+) LUFS", t)
    p = re.search(r"Peak:\s+(-?[\d.]+) dBFS", t)
    return (float(i.group(1)) if i else None), (float(p.group(1)) if p else None)


def duration(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path], capture_output=True, text=True).stdout.strip()
    return float(out or 0)


def loudnorm(src, dst):
    """2回通し：測ってから、そのままの値で −15 LUFS・ピーク −1.5 に直す（映像は触らない）"""
    af = f"loudnorm=I={TARGET}:TP=-1.5:LRA=11"
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", src, "-af", af + ":print_format=json", "-f", "null", "-"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    m = json.loads(r.stderr[r.stderr.rfind("{"):r.stderr.rfind("}") + 1])
    af2 = (af + f":measured_I={m['input_i']}:measured_TP={m['input_tp']}:measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}"
           f":offset={m['target_offset']}:linear=true")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", src, "-c:v", "copy", "-af", af2, "-ar", "48000", "-c:a", "aac", "-b:a", "192k",
                    "-movflags", "+faststart", dst], check=True)
    return float(m["input_i"])


def main():
    a = argparse.ArgumentParser()
    a.add_argument("work")
    a.add_argument("--out")
    a = a.parse_args()
    work = os.path.abspath(a.work)
    sp = os.path.join(work, "script.json")
    s = json.load(open(sp, encoding="utf-8"))
    s["bgm"] = bgm_path()
    json.dump(s, open(sp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    cfgp = os.path.join(work, "config.json")
    if not os.path.exists(cfgp):
        json.dump({"bgm_volume": 0.02}, open(cfgp, "w", encoding="utf-8"))
    if (s.get("funnel") or {}).get("kind") == "切り出し":
        prepare_cut(work, s)
    import build_short as BS
    raw, out = os.path.join(work, "_raw_short.mp4"), a.out or os.path.join(work, "short.mp4")
    import io, contextlib
    buf = io.StringIO()
    class Tee(io.TextIOBase):
        def write(self, x):
            sys.__stdout__.write(x); buf.write(x); return len(x)
    with contextlib.redirect_stdout(Tee()):
        BS.build(work, raw)
    log = buf.getvalue()
    before = loudnorm(raw, out)
    lufs, peak = measure(out)
    sec = duration(out)
    moving = re.search(r"動く絵：(\d+) カット", log)
    rep = {"秒": round(sec, 1), "LUFS_前": before, "LUFS": lufs, "ピーク_dBFS": peak, "動く絵のカット": int(moving.group(1)) if moving else None,
           "画質の注意": "【画質】" in log, "セーフゾーン確認": os.path.join(work, "safezone_check.png"), "出力": out}
    json.dump(rep, open(os.path.join(work, "build_report.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"組み立て：{sec:.1f}秒・{before:.1f} → {lufs} LUFS（目標 {TARGET}）・ピーク {peak} dBFS・動く絵 {rep['動く絵のカット']} カット")
    bad = []
    if lufs is None or abs(lufs - TARGET) > 1.0:
        bad.append(f"LUFS {lufs}（{TARGET}±1）")
    if sec > 60:
        bad.append(f"{sec:.0f}秒（ショートは60秒以内）")
    if rep["画質の注意"]:
        print("【注意】【画質】が出ています（寄りを弱めるか絵を大きく作り直す）")
    if bad:
        print("【NG】" + "／".join(bad))
        sys.exit(1)


if __name__ == "__main__":
    main()

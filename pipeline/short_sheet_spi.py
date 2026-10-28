# ショートの全カットの1コマを1枚に並べる（千年こよみ・2026-10-28 新設。手順書 §14「電子ゴミの線」4：上げる前に Claude が全部のカットの絵を見る）
#   python -X utf8 pipeline\short_sheet_spi.py <作業フォルダ> [--name short_2]
# ・各カットの真ん中の1コマを、横5枚で並べて <name>\sheet.jpg に出す（カットの id と語りの頭を下に書く）
import argparse, json, os, subprocess, sys
from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "vendor", "youtube-video-maker", "scripts"))
from common import dur  # noqa: E402

FONT = r"C:\Windows\Fonts\NotoSansJP-Bold.ttf"
TW, TH, COLS = 270, 480, 5


def main():
    a = argparse.ArgumentParser()
    a.add_argument("work")
    a.add_argument("--name", default="short")
    a = a.parse_args()
    sw = os.path.join(os.path.abspath(a.work), a.name)
    cuts = json.load(open(os.path.join(sw, "script.json"), encoding="utf-8"))["cuts"]
    video, t, tiles = os.path.join(sw, "short.mp4"), 0.0, []
    for c in cuts:
        d = dur(os.path.join(sw, "_build", c["id"] + "_v.wav"))
        fr = os.path.join(sw, "_build", c["id"] + "_mid.png")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t + d * 0.6:.2f}", "-i", video, "-frames:v", "1", fr], check=True)
        tiles.append((c, Image.open(fr).convert("RGB").resize((TW, TH))))
        t += d
    rows = (len(tiles) + COLS - 1) // COLS
    sheet = Image.new("RGB", (COLS * TW, rows * (TH + 60)), (255, 255, 255))
    dr, f = ImageDraw.Draw(sheet), ImageFont.truetype(FONT, 18)
    for i, (c, im) in enumerate(tiles):
        x, y = i % COLS * TW, i // COLS * (TH + 60)
        sheet.paste(im, (x, y))
        dr.text((x + 6, y + TH + 4), f"{c['id']} {c['narration'][:13]}", font=f, fill=(0, 0, 0))
        dr.text((x + 6, y + TH + 30), c["narration"][13:26], font=f, fill=(0, 0, 0))
    out = os.path.join(sw, "sheet.jpg")
    sheet.save(out, quality=80)
    print("並べました：", out)


if __name__ == "__main__":
    main()

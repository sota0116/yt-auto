# サムネを1枚に並べて見比べるための道具（2026-11-12。references/15「同じ絵を回をまたいで使わない」「雑な切り抜きを貼らない」の点検用）
#   python -X utf8 thumb_lineup.py <出力.jpg> <今回の案> <過去のサムネ1> <過去のサムネ2> ...
#   1枚目が今回の案（黄色い枠）。2枚目からが、同じチャンネルの直近のサムネ（6本が目安）。
#   出来た一覧を目で見て、背景・人物の表情とポーズ・物が重なっていないか、切り出した札を貼っていないかを確かめる。
#   絵の全体がほぼ同じ時だけ「注意」を出す。顔だけ同じ・配置だけ違う物は機械では拾えないので、必ず目で見る。
import os
import sys

from PIL import Image, ImageDraw, ImageFont

W, H, LB, COLS = 480, 270, 28, 4
NEAR = 10  # 64ビットのうち違うビットがこの数以下なら「ほぼ同じ絵」


def load_font(size):
    for p in ("C:/Windows/Fonts/meiryo.ttc", "C:/Windows/Fonts/YuGothM.ttc",
              "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
              "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
              "/System/Library/Fonts/ヒラギノ角ゴシック W4.ttc"):
        try:
            return ImageFont.truetype(p, size)
        except Exception:
            pass
    return ImageFont.load_default()


def dhash(im):
    g = im.convert("L").resize((9, 8), Image.LANCZOS)
    px = list(g.tobytes())
    bits = 0
    for y in range(8):
        for x in range(8):
            bits = (bits << 1) | (1 if px[y * 9 + x] > px[y * 9 + x + 1] else 0)
    return bits


def label(path):
    parts = os.path.abspath(path).replace("\\", "/").split("/")
    return ("/".join(parts[-2:]))[-40:]


def main():
    if len(sys.argv) < 4:
        print("使い方: python -X utf8 thumb_lineup.py <出力.jpg> <今回の案> <過去のサムネ...>")
        return 2
    out, files = sys.argv[1], sys.argv[2:]
    font = load_font(15)
    items = []
    for f in files:
        try:
            im = Image.open(f).convert("RGB")
        except Exception as e:
            print("読めない:", f, e)
            continue
        items.append((f, im.resize((W, H), Image.LANCZOS), dhash(im)))
    if len(items) < 2:
        print("並べる絵が2枚に足りない")
        return 2
    rows = (len(items) + COLS - 1) // COLS
    sheet = Image.new("RGB", (COLS * W, rows * (H + LB)), (34, 34, 34))
    d = ImageDraw.Draw(sheet)
    for i, (f, im, _) in enumerate(items):
        x, y = (i % COLS) * W, (i // COLS) * (H + LB)
        sheet.paste(im, (x, y + LB))
        head = "今回の案 " if i == 0 else "%d " % i
        d.text((x + 4, y + 4), head + label(f), fill=(255, 255, 255), font=font)
        if i == 0:
            d.rectangle([x, y + LB, x + W - 1, y + LB + H - 1], outline=(255, 220, 0), width=5)
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    sheet.save(out, quality=88)
    warn = 0
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            diff = bin(items[i][2] ^ items[j][2]).count("1")
            if diff <= NEAR:
                warn += 1
                print("注意：絵の全体がほぼ同じ（違い %d/64）: %s と %s" % (diff, label(items[i][0]), label(items[j][0])))
    print("並べた枚数", len(items), "／ほぼ同じ絵の組", warn)
    print("この一覧を目で見る（背景・人物の表情とポーズ・物の重なり、切り出した札の有無）:", out)
    return 0


if __name__ == "__main__":
    sys.exit(main())

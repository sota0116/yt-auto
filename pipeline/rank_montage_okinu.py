# 結論の先見せ（金運おきぬ・2026-10-30 クラウドに移した）：ランキングの絵を、伏せ字の札つきで1枚ずつ続けて見せる動画を images/<id>.mp4 に作る
#   単体：python -X utf8 pipeline/rank_montage_okinu.py <作業フォルダ> [--id A10] [--tempo 1.0 --gap 0.3]
#   ふだんは build_long_okinu.py が声のあと・カードの前に呼ぶ（build(work, cuts, durs) を直接）
# 元は OneDrive\ClaudeBackup\tools\youtube\rank_montage_v1.py（2026-10-29 金運おきぬ 003。制作ルール v1.6 §6「5つの NG の絵を1枚0.8〜1.2秒で続けて見せ、物の名前は伏せ字のカードにする」）
#   スキルの common.py（font_file・load_config・resolve_image）に頼らない形に直した：絵は build_long_okinu.pic() と同じ探し方、字は下の FONTS から探す（Windows・Linux の両方）
# ・script.json のカットに "montage": ["B01", "C01", ...]（見せる絵のカット id）と "montage_labels": ["第5位　枯れかけの●●", ...] を書く（same_as はたどる。ポーズ絵も images/<id>.png にある）
# ・長さは、声の長さ（voice/<id>.wav ÷ tempo ＋ gap。build_long の durs と同じ）を絵の数で等分する（1枚が0.8秒未満になる時は知らせる）
# ・字は、左上に朱の順位、その下に白い字の伏せ字（黒い縁）、● だけ黄色。絵は少し暗くして、ゆっくり寄る
# ・"montage_blur": 14 のように書くと、絵をぼかす（物の形は分かるが答えは見えない程度。絵で答えが分かると伏せ字の意味が無い）
# ・つくった images/<id>.mp4 は build_long_okinu.make_cards が clips（images/_v3/<id>.mp4）に写して、そのカットの映像にする（カードは描かない）
import argparse, json, os, subprocess, sys, tempfile, wave
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

W, H, FPS = 1920, 1080, 30
SHU, HL = (179, 58, 43), (255, 230, 0)
FONTS = [r"C:\Windows\Fonts\NotoSansJP-Bold.ttf", os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Windows\Fonts\NotoSansJP-Bold.ttf"),
         "/usr/share/fonts/opentype/noto/NotoSansCJK-Black.ttc", "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
         "/usr/share/fonts/noto-cjk/NotoSansCJK-Black.ttc", "/usr/share/fonts/noto-cjk/NotoSansCJK-Bold.ttc",
         r"C:\Windows\Fonts\meiryob.ttc", r"C:\Windows\Fonts\YuGothB.ttc"]


def font_path():
    p = next((p for p in FONTS if os.path.exists(p)), None)
    if not p:
        raise SystemExit("【止まりました】先見せの字（NotoSansJP-Bold.ttf か NotoSansCJK-Black/Bold.ttc）が見つかりません（Linux は fonts-noto-cjk を入れる）")
    return p


def find_image(work, cuts, c):
    """そのカットの絵（png）。same_as は先をたどる。build_long_okinu.pic() と同じ探し方（png だけ。無ければ .mp4 の1コマ目）"""
    seen, cur = set(), c
    im = os.path.join(work, "images")
    while cur:
        for name in (cur["id"], cur.get("img_src")):
            if name and os.path.exists(os.path.join(im, name + ".png")):
                return os.path.join(im, name + ".png")
        for name in (cur["id"], cur.get("img_src")):
            for sub in ("_kling", ""):
                p = os.path.join(im, sub, (name or "") + ".mp4")
                if name and os.path.exists(p) and not cur.get("montage"):
                    return p
        if not cur.get("same_as") or cur["id"] in seen:
            return None
        seen.add(cur["id"])
        cur = next((x for x in cuts if x["id"] == cur["same_as"]), None)
    return None


def first_frame(src, out):
    if src.endswith(".mp4"):
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", src, "-frames:v", "1", out], check=True)
        return out
    return src


def cover(im):
    s = max(W / im.width, H / im.height)
    im = im.resize((round(im.width * s), round(im.height * s)), Image.LANCZOS)
    x, y = (im.width - W) // 2, (im.height - H) // 2
    return im.crop((x, y, x + W, y + H))


def text_layer(rank, label, ff):
    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    for txt, size, y, col in ((rank, 170, 90, SHU), (label, 120, 300, (255, 255, 255))):
        f = ImageFont.truetype(ff, size)
        m = Image.new("L", (W, H), 0)
        d = ImageDraw.Draw(m)
        x = 110
        for ch in txt:  # ●だけ黄色にするため1字ずつ描く
            d.text((x, y), ch, font=f, fill=255)
            x += d.textlength(ch, font=f)
        out = m.filter(ImageFilter.MaxFilter(size // 9 * 2 + 1))
        lay.paste((0, 0, 0, 255), (0, 0), out)
        x = 110
        for ch in txt:
            c = HL if ch == "●" else col
            ImageDraw.Draw(lay).text((x, y), ch, font=f, fill=c + (255,))
            x += d.textlength(ch, font=f)
    return lay


def build_one(work, cuts, c, total):
    """c（montage のカット）の images/<id>.mp4 を作る。total＝そのカットの長さ（秒）"""
    ff = font_path()
    n = len(c["montage"])
    seg = total / n
    if seg < 0.8:
        print(f"【注意】{c['id']}：1枚 {seg:.2f} 秒（0.8秒より短い）。絵を減らすか、声を長くする", flush=True)
    tmp = tempfile.mkdtemp()
    frames = 0
    for k, (mid, lab) in enumerate(zip(c["montage"], c["montage_labels"])):
        tgt = next((x for x in cuts if x["id"] == mid), None)
        src = find_image(work, cuts, tgt) if tgt else None
        if not src:
            raise SystemExit(f"【止まりました】先見せ {c['id']} の絵 {mid} がまだ無い（images/{mid}.png）")
        im = cover(Image.open(first_frame(src, os.path.join(tmp, f"f{k}.png"))).convert("RGB"))
        im = ImageEnhance.Brightness(im).enhance(0.72)
        if c.get("montage_blur"):
            im = im.filter(ImageFilter.GaussianBlur(c["montage_blur"]))
        rank, label = lab.split("　", 1)
        lay = text_layer(rank, label, ff)
        nf = round(seg * FPS) if k < n - 1 else round(total * FPS) - frames
        for i in range(nf):
            z = 1 + 0.06 * i / max(1, nf - 1)
            zw, zh = round(W * z), round(H * z)
            fr = im.resize((zw, zh), Image.BILINEAR).crop(((zw - W) // 2, (zh - H) // 2, (zw - W) // 2 + W, (zh - H) // 2 + H))
            fr.paste(lay, (0, 0), lay)
            fr.save(os.path.join(tmp, f"{frames:05d}.jpg"), quality=92)
            frames += 1
    out = os.path.join(work, "images", c["id"] + ".mp4")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-framerate", str(FPS), "-i", os.path.join(tmp, "%05d.jpg"),
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", out], check=True)
    import shutil
    shutil.rmtree(tmp, ignore_errors=True)
    print(f"{c['id']}：{n} 枚・1枚 {seg:.2f} 秒・{total:.2f} 秒 → {out}", flush=True)
    return out


def build(work, cuts, durs, only=""):
    """build_long_okinu.py から：durs＝カットごとの長さ（声÷tempo＋gap）。作った mp4 の {id: path}"""
    out = {}
    for c in cuts:
        if c.get("montage") and (not only or c["id"] == only):
            out[c["id"]] = build_one(work, cuts, c, durs[c["id"]])
    return out


def main():
    a = argparse.ArgumentParser()
    a.add_argument("work")
    a.add_argument("--id", default="")
    a.add_argument("--tempo", type=float, default=None)
    a.add_argument("--gap", type=float, default=None)
    o = a.parse_args()
    work = os.path.abspath(o.work)
    sc = json.load(open(os.path.join(work, "script.json"), encoding="utf-8"))
    tempo, gap = o.tempo or sc.get("tempo", 1.0), o.gap if o.gap is not None else sc.get("gap", 0.3)
    durs = {}
    for c in sc["cuts"]:
        if c.get("montage"):
            w = wave.open(os.path.join(work, "voice", c["id"] + ".wav"))
            durs[c["id"]] = w.getnframes() / w.getframerate() / tempo + gap
    build(work, sc["cuts"], durs, o.id)


if __name__ == "__main__":
    main()

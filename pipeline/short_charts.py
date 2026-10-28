# ショート③画面（2026-10-27）：script.json のカットごとの画面（帯・グラフ）を、facts.json の値から縦の短い動画にして images\<id>.mp4 に置く
#   python -X utf8 pipeline\short_charts.py <作業フォルダ> [--still]
# ・数字はすべて facts.json の charts から取る（台本の文から数字を拾わない）
# ・縦 1080x1920。文字はセーフゾーン（左48・上288・右888・下1248。ショートのボタンと説明文にかぶらない所）の中だけに置く
#   字の段は画面の真ん中（x=540）をはさんで左右同じ幅（192〜888）。右のボタンの所（x>888）に掛けない幅を、左にも同じだけあける
#   （2026-10-28 本人「アウトゾーンにかぶらないでほしいだけで、左右どちらかに違和感のある寄り方をしないでほしい」。前はセーフゾーンの左はしに寄せていた）
#   上から：帯（何の話か）270〜470 → 見出しと出典 490〜580 → 棒 600〜1070 → 字幕 1085〜1248（字幕は build_short_job.py が重ねる）
# ・紺の地に生成りの文字、1位（強調）の棒だけ黄。ほかの棒は1位より暗い灰色（手順書 §5 の暗い地のグラフ）
# ・カットの screen：{"hook": true}（帯だけ。大きな字は組み立てで重ねる）／{"chart": 0, "show": 3}（charts[0] の棒を3本出す）
#   rank は5位から上へ1本ずつ、duel は上から出す（show は出した本数）。新しく出た棒は最初の0.5秒で伸びる。そのあとは止めた画面（組み立てで声の長さまでのばす）
# ・確かめ用に、最後の画面を images\_still\<id>.png にも置く（--still なら動画を作らず、これだけ作る）
import argparse, json, os, subprocess, sys
from PIL import Image, ImageDraw
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from make_charts_job import NAVY, PANEL, LINE, KINARI, MUTED, YELLOW, GREY, ease, text, tw, fit

W, H, FPS = 1080, 1920, 30
SAFE_L, SAFE_T, SAFE_R, SAFE_B = 48, 288, 888, 1248
SAFE_W = SAFE_R - SAFE_L
TXT_L, TXT_R = W - SAFE_R, SAFE_R  # 字の段（真ん中 540 をはさんで左右同じ）
TXT_W, CX = TXT_R - TXT_L, W // 2
BAN_T, BAN_B = 270, 470
CAP_T = 1085          # 字幕の段の上の端（build_short_job.py と同じ）
BAR_T, BAR_B = 600, 1070
ANIM = 0.5


def banner(d, ban):
    d.rectangle((0, BAN_T, W, BAN_B), fill=KINARI)
    big = ban[0] if ban else ""
    small = ban[1] if ban and len(ban) > 1 else ""
    text(d, (CX, 345 if small else 370), big, fit(big, 104, TXT_W - 20), fill=NAVY, anchor="mm")
    if small:
        text(d, (CX, 432), small, fit(small, 58, TXT_W - 20, 700), fill=NAVY, weight=700, anchor="mm")


def header(d, title, src):
    text(d, (CX, 490), title, fit(title, 46, TXT_W), fill=KINARI, anchor="ma")
    text(d, (CX, 548), src, fit(src, 28, TXT_W, 500), fill=MUTED, weight=500, anchor="ma")


def bars(d, ch, show, new, t):
    """名前の行の右はしに値、その下に棒。rank は1位が上で、下（5位）から出す"""
    bs = ch["bars"]
    n = len(bs)
    rank = ch.get("reveal") == "bottom_up"
    vis = set(range(n - show, n)) if rank else set(range(show))  # duel は上から出す
    vmax = max(b["value"] for b in bs) or 1
    row = (BAR_B - BAR_T) / n
    name_s, bar_h = (42, 30) if n > 3 else (58, 70)
    for i, b in enumerate(bs):
        y = BAR_T + row * i + (row - (name_s + 12 + bar_h)) / 2
        yb = y + name_s + 12
        hl = b.get("hl", b.get("rank") == 1)
        if i not in vis:
            d.rounded_rectangle((TXT_L, yb, TXT_L + TXT_W * 0.3, yb + bar_h), 8, outline=LINE, width=3)
            if rank:
                text(d, (TXT_L, y), f"{b['rank']}位  ？", name_s, fill=MUTED)
            continue
        k = ease(t / ANIM) if i in new else 1.0
        lab_w = tw(b["label"], name_s)
        head = (f"{b['rank']}位  " if rank else "") + b["name"]
        text(d, (TXT_L, y), head, fit(head, name_s, TXT_W - lab_w - 24), fill=YELLOW if hl else KINARI)
        if k > 0.5:
            text(d, (TXT_R, y), b["label"], name_s, fill=YELLOW if hl else KINARI, anchor="ra")
        d.rounded_rectangle((TXT_L, yb, TXT_L + max(14, TXT_W * b["value"] / vmax * k), yb + bar_h), 8, fill=YELLOW if hl else GREY)


def frame(sc, fx, cut, prev, t):
    im = Image.new("RGB", (W, H), NAVY)
    d = ImageDraw.Draw(im)
    banner(d, sc.get("banner"))
    s = cut.get("screen") or {}
    if "chart" in s:
        ch = fx["charts"][s["chart"]]
        header(d, ch["title"], "出典：" + fx["加工"])
        show = s.get("show", len(ch["bars"]))
        n = len(ch["bars"])
        before = prev.get("show", 0) if prev.get("chart") == s["chart"] else 0
        if ch.get("reveal") == "bottom_up":
            new = set(range(n - show, n - before))
        else:
            new = set(range(before, show))
        bars(d, ch, show, new, t)
    return im


def render(work, still):
    sc = json.load(open(os.path.join(work, "script.json"), encoding="utf-8"))
    fx = json.load(open(os.path.join(work, "facts.json"), encoding="utf-8"))
    os.makedirs(os.path.join(work, "images", "_still"), exist_ok=True)
    prev = {}
    for c in sc["cuts"]:
        s = c.get("screen") or {}
        frame(sc, fx, c, prev, ANIM).save(os.path.join(work, "images", "_still", c["id"] + ".png"))
        if not still:
            out = os.path.join(work, "images", c["id"] + ".mp4")
            p = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
                                  "-i", "-", "-c:v", "libx264", "-crf", "16", "-preset", "fast", "-pix_fmt", "yuv420p", out], stdin=subprocess.PIPE)
            for k in range(int(ANIM * FPS) + 2):
                p.stdin.write(frame(sc, fx, c, prev, k / FPS).tobytes())
            p.stdin.close()
            if p.wait():
                sys.exit(f"【止まりました】画面の動画を作れませんでした：{c['id']}")
        prev = s if "chart" in s else prev
        print(c["id"], json.dumps(s, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    a = argparse.ArgumentParser(); a.add_argument("work"); a.add_argument("--still", action="store_true")
    a = a.parse_args()
    render(os.path.abspath(a.work), a.still)

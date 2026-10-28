# 長尺の予告ショート（手順書 §12。2026-10-28 から。本人が選んだ「統計ショート＋長尺の予告」の予告の方）
#   python -X utf8 pipeline\make_teaser_job.py make <作業フォルダ>
#   python -X utf8 pipeline\make_teaser_job.py upload <作業フォルダ> [--ch job] [--go]
# ・make：long.mp4 と _build\<カット>_v.wav（組み立てが残す、カットごとの声）から冒頭（つかみ〜前置き。最初の章の前まで）の長さを出し、
#   teaser\teaser.mp4・teaser.json・teaser_check.png を作る。クラウドはアップの後に long.mp4 と _build を消すので、毎日の実行の thumb の後に動かす
#   冒頭が58秒を超える時は、58秒までのカットの切れ目で切る。20秒に届かない回は作らない（終了コード 0。teaser.json に理由）
#   画面：紺の地。上（セーフゾーンの中）に長尺のサムネの字（thumb_top を白い札に赤、thumb_text を大きく。強調の部分は黄）、その下に長尺の映像（16:9）
#   字も映像も画面の真ん中（x=540）にそろえる。字の幅は、右のボタンの所（x>888）に掛けない幅を左にも同じだけあけた 192〜888
#   （2026-10-28 本人「アウトゾーンにかぶらないでほしいだけで、左右どちらかに違和感のある寄り方をしないでほしい」）
#   声で言うことは長尺の冒頭のまま（台本の点検・ゲートを通った物）。字はサムネの字（check_job_script・make_thumb_job の点検を通った物）だけ
# ・upload：長尺を上げた後に、予告を非公開で上げる（公開の予約は入れない）。記録は history\<ch>\teasers.json（長尺の uploaded.json には入れない）
#   公開は見張り（watch.py の schedule_teasers）が、長尺の公開の TEASER_AFTER 分後に予約する（ショートの 20:10 と時間をあける）
# ・毎日の実行（run_daily.py）は、profile.json の tools に teaser がある時だけ、thumb の後に make、長尺のアップの後に upload を動かす
#   （作れなくても上げられなくても本編は止めない。理由は作業フォルダの _run.log）
#   --go を付けた時だけ上げる（付けない時は、タイトルと説明文だけ出す）
# ・タイトル：長尺のタイトルの「｜」の前（「AI」「PR」が入る時・32字を超える時は thumb_top｜thumb_text）＋ #年収 #仕事
# ・説明文：1段落目に本編のリンク、続けて LINE の特典・出典（e-Stat の決まりの1文・加工して作成）・作り方の1文・VOICEVOX のクレジット
import argparse, datetime, json, os, re, subprocess, sys, unicodedata, wave
from PIL import Image, ImageDraw
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from make_charts_job import font, tw
from make_thumb_job import parts

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
W, H = 1080, 1920
SAFE = (48, 288, 888, 1248)  # 左・上・右・下（手順書 §12 のショートのセーフゾーン）
NAVY, KINARI = (20, 31, 52), (243, 235, 221)
RED, YEL, WHITE, BLACK = (226, 32, 40), (255, 214, 0), (255, 255, 255), (10, 10, 16)
TXT_L, TXT_R = W - SAFE[2], SAFE[2]  # 字の段（真ん中 540 をはさんで左右同じ）
VX, VY, VW, VH = 60, 690, 960, 540  # 長尺の映像の置き場（真ん中。映像の右はしはボタンの所に少し入るが、字は字の段に出す）
MAX_S, MIN_S = 58.0, 20.0
CAP_Y0, CAP_Y1, CAP_MAX = VY + VH - 130, VY + VH, 13  # 映像の下の130px（長尺の焼き込みの字幕の所）を帯で隠し、大きい字幕を1行13字までで出す
QUIZ_GAP, GAP = 2.0, 0.3  # build_long_job.py と同じカットの後の間
HOW = "人の手では数えきれない統計をプログラムで計算し、グラフと合成音声で動画にしています。数字は全部、出典と照らしています。"
TOKUTEN = "主な職業の年収・労働時間と、産業別の離職率の一覧"
N = lambda s: unicodedata.normalize("NFKC", s or "")


def wav_len(p):
    with wave.open(p) as w:
        return w.getnframes() / w.getframerate()


def opening(work, sc):
    """冒頭（最初の章の前まで。MAX_S を超えない所まで）の [(カット, 始まり, 長さ)] と秒数。組み立てと同じく、声のあるカットを順に足す"""
    t, out = 0.0, []
    for n, c in enumerate(x for x in sc["cuts"] if x.get("narration")):
        if n > 0 and c.get("chapter"):
            break
        p = os.path.join(work, "_build", f"{c['id']}_v.wav")
        if not os.path.exists(p):
            sys.exit(f"【止まりました】組み立ての声がありません：{p}（long.mp4 を組み立てた後に動かす）")
        d = wav_len(p)
        if t + d > MAX_S:
            break
        out.append((c, t, d))
        t += d
    return out, t


def split_long(x, n):
    """n 字を超える所を割る。数字と単位の途中では切らず、助詞の後 → 字の種類が変わる所 → 長さがそろう所、の順に選ぶ"""
    out = []
    while len(x) > n:
        k = -(-len(x) // n)
        aim = -(-len(x) // k)
        best = None
        for i in range(max(2, aim - 6), min(n, len(x) - 2) + 1):
            a, b = x[i - 1], x[i]
            if re.match(r"[0-9０-９.,，．約]", a) and re.match(r"[0-9０-９.,，．%％年月日円人時間分秒位歳つ割倍万億千百件社か]", b):
                continue
            kind = lambda ch: "h" if "ぁ" <= ch <= "ゖ" else "k" if "ァ" <= ch <= "ヺ" or ch == "ー" else "n" if ch.isdigit() else "c"
            score = (3 if a in "をはがにでとへや" else 2 if a == "の" else 0) if kind(b) != "h" else 0
            score = score or (1 if kind(a) != kind(b) else 0)  # 「の」で切ると「6つの / 中で」のように次の語とつながりが切れやすいので、ほかの助詞より後に回す
            key = (score, -abs(i - aim))
            if best is None or key > best[0]:
                best = (key, i)
        i = best[1] if best else aim
        out.append(x[:i])
        x = x[i:]
    return out + [x]


def pieces(s, n=CAP_MAX):
    """字幕の区切り：句読点で切り、n 字を超える所は同じくらいの長さに割る。短い所は次とつなぐ"""
    out = []
    for x in (y.strip() for y in re.split(r"(?<=[、。！？!?])", s)):
        if not x:
            continue
        for part in split_long(x, n):
            if out and len(out[-1]) + len(part) <= n and not out[-1].endswith(("。", "？", "！", "?", "!")):
                out[-1] += part
            else:
                out.append(part)
    return out


def captions(cuts, o):
    """大きい字幕の絵（[(絵, 始まり, 終わり)]）。長尺の焼き込みの小さい字幕の所を帯で隠して、その上に出す。
    時刻は組み立てと同じく、カットの声の長さ（間を除く）を文字数の割合で分ける。話し手で色を分ける（語り手は紺に生成り、聞き手は生成りに紺）"""
    out, cx = [], W // 2
    for c, st, d in cuts:
        ps = pieces(N(c["narration"]))
        speak = d - (QUIZ_GAP if c.get("quiz") else GAP)
        total = sum(len(x) for x in ps) or 1
        t = st
        for k, x in enumerate(ps):
            en = st + d if k == len(ps) - 1 else t + speak * len(x) / total
            lis = c.get("speaker") == "listener"
            im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            dr = ImageDraw.Draw(im)
            dr.rectangle((VX, CAP_Y0, VX + VW, CAP_Y1), fill=KINARI if lis else NAVY)
            z = fit(x, 54, TXT_R - TXT_L - 16, 30)
            dr.text((cx, (CAP_Y0 + CAP_Y1) // 2), x, font=font(z), fill=NAVY if lis else KINARI, anchor="mm")
            p = os.path.join(o, f"_cap{len(out):03d}.png")
            im.save(p)
            out.append((p, t, en))
            t = en
    return out


def say(d, xy, s, size, fill, stroke=BLACK, sw=None, anchor="la"):
    d.text(xy, s, font=font(size), fill=fill, stroke_width=sw if sw is not None else max(5, size // 10), stroke_fill=stroke, anchor=anchor)


def fit(s, size, maxw, low=40):
    while tw(s, size) > maxw and size > low:
        size -= 4
    return size


def overlay(sc, out):
    """上の字（長尺のサムネの字）を、透明の地に描く"""
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    cx, y0, mw = W // 2, SAFE[1] + 16, TXT_R - TXT_L
    top = N(sc.get("thumb_top"))
    y = y0
    if top:
        z = fit(top, 50, mw - 40, 30)
        w = int(tw(top, z)) + 40
        d.rectangle((cx - w // 2, y, cx - w // 2 + w, y + z + 30), fill=WHITE)
        d.text((cx, y + 15), top, font=font(z), fill=RED, anchor="ma")
        y += z + 30 + 24
    lines, hi = parts(N(sc["thumb_text"]), sc.get("thumb_lines"), 2)
    for i, t in enumerate(lines):
        z = fit(t, 130 if i == hi else 96, mw - 12)
        y += z
        say(d, (cx, y), t, z, YEL if i == hi else WHITE, anchor="ms")
        y += int(z * 0.18)
    if y > VY - 10:
        sys.exit(f"【止まりました】上の字が映像にかかります（字の下 {y}px・映像の上 {VY}px）")
    im.save(out)


def make(work):
    sc = json.load(open(os.path.join(work, "script.json"), encoding="utf-8"))
    long_mp4 = os.path.join(work, "long.mp4")
    if not os.path.exists(long_mp4):
        sys.exit(f"【止まりました】{long_mp4} がありません")
    o = os.path.join(work, "teaser")
    os.makedirs(o, exist_ok=True)
    cuts, sec = opening(work, sc)
    rec = {"秒": round(sec, 2)}
    if sec < MIN_S:
        rec["作らなかった"] = f"冒頭が{sec:.1f}秒（{MIN_S:.0f}秒に届かない）"
        json.dump(rec, open(os.path.join(o, "teaser.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(rec["作らなかった"])
        return
    png = os.path.join(o, "_overlay.png")
    overlay(sc, png)
    mp4 = os.path.join(o, "teaser.mp4")
    caps = captions(cuts, o)
    ins = sum([["-loop", "1", "-t", f"{sec:.3f}", "-i", p] for p in [png] + [c[0] for c in caps]], [])
    fc = (f"color=c=0x{NAVY[0]:02X}{NAVY[1]:02X}{NAVY[2]:02X}:s={W}x{H}:r=30:d={sec:.3f}[bg];"
          f"[0:v]scale={VW}:{VH},setsar=1[v];[bg][v]overlay={VX}:{VY}[b];[b][1:v]overlay=0:0[c0];")
    for k, (_, st, en) in enumerate(caps):
        fc += f"[c{k}][{k + 2}:v]overlay=0:0:enable='between(t,{st:.3f},{en:.3f})'[c{k + 1}];"
    fc += f"[0:a]afade=t=out:st={max(0, sec - 0.6):.3f}:d=0.6[a]"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-t", f"{sec:.3f}", "-i", long_mp4, *ins,
                    "-filter_complex", fc, "-map", f"[c{len(caps)}]", "-map", "[a]", "-t", f"{sec:.3f}", "-r", "30",
                    "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", mp4], check=True)
    # 点検用：真ん中あたりの1コマに、セーフゾーンの赤い枠を重ねる（手順書 §12 の safezone_check.png と同じ見方）
    chk = os.path.join(o, "teaser_check.png")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{sec / 2:.2f}", "-i", mp4, "-frames:v", "1", chk], check=True)
    im = Image.open(chk).convert("RGB")
    ImageDraw.Draw(im).rectangle(SAFE, outline=(255, 0, 0), width=4)
    im.save(chk)
    cr = os.path.join(work, "voice", "_credit.txt")
    rec.update(title=title(sc), credit=open(cr, encoding="utf-8").read().strip() if os.path.exists(cr) else "",
               作った日時=datetime.datetime.now().isoformat(timespec="seconds"))
    json.dump(rec, open(os.path.join(o, "teaser.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"できました：{mp4}（{sec:.1f}秒）｜{rec['title']}")


def title(sc):
    from check_job_script import rank_unscoped
    base = N(sc.get("title")).split("|")[0].strip()
    if re.search(r"AI|PR", base.upper()) or len(base) > 32 or not base or (sc.get("type") != "D" and rank_unscoped(base)):
        base = f"{N(sc.get('thumb_top'))}｜{N(sc['thumb_text'])}".strip("｜")
    if re.search(r"AI|PR", base.upper()):
        sys.exit(f"【止まりました】予告のタイトルに「AI」か「PR」：{base}")
    if sc.get("type") != "D" and rank_unscoped(base):
        sys.exit(f"【止まりました】予告のタイトルの順位に、何の中の順位か（「6職種で」など）が無い：{base}")
    return base + " #年収 #仕事"


def description(work, ch, sc, rec, long_id):
    fx = json.load(open(os.path.join(work, "facts.json"), encoding="utf-8"))
    prof = json.load(open(os.path.join(ROOT, "channels", ch, "profile.json"), encoding="utf-8"))
    # LINE の特典の段落は、長尺の説明文の1段落目をそのまま使う（型D は特典が2つセットなど、型で違うため）
    first = (sc.get("desc") or "").split("\n\n")[0]
    line = first.replace("{LINE_URL}", prof["line_url"]) if "LINEで無料で受け取れます" in first and "{LINE_URL}" in first \
        else f"▼{TOKUTEN}を、LINEで無料で受け取れます\n{prof['line_url']}"
    src ="\n".join(f"出典：{s['名前']}（{s['公表日']} 公表）\n{s['URL']}" for s in fx.get("出典", []) if isinstance(s, dict) and s.get("名前"))
    note = "\n".join(x for x in (fx.get("e_stat_note"), fx.get("加工")) if isinstance(x, str))
    d = (f"本編はこちら\nhttps://youtu.be/{long_id}\n\n{line}\n\n"
         f"{src}\n{note}\n\n{HOW}\n{rec.get('credit', '')}").replace("\n\n\n", "\n\n").strip()
    if "PR" in d:
        sys.exit("【止まりました】説明文に PR の文字があります（手順書 §10）")
    return d


def upload(work, ch, go):
    from upload_job import api
    sc = json.load(open(os.path.join(work, "script.json"), encoding="utf-8"))
    rp = os.path.join(work, "teaser", "teaser.json")
    rec = json.load(open(rp, encoding="utf-8")) if os.path.exists(rp) else {}
    video = os.path.join(work, "teaser", "teaser.mp4")
    if rec.get("作らなかった") or not os.path.exists(video):
        print("予告はありません：", rec.get("作らなかった") or video)
        return
    long_id = json.load(open(os.path.join(work, "uploaded.json"), encoding="utf-8")).get("video_id")
    if not long_id:
        sys.exit("【止まりました】長尺の video_id がありません（長尺を上げた後に動かす）")
    desc = description(work, ch, sc, rec, long_id)
    print("タイトル：", rec["title"])
    print("説明文：\n" + desc)
    if not go:
        print("（--go が無いので上げません）")
        return
    hp = os.path.join(ROOT, "history", ch, "teasers.json")
    hist = json.load(open(hp, encoding="utf-8")) if os.path.exists(hp) else {}
    name = os.path.basename(os.path.normpath(work))
    if name in hist:
        sys.exit("【止めました】もう上げてあります（二重アップの防止）")
    status = {"privacyStatus": "private", "selfDeclaredMadeForKids": False, "containsSyntheticMedia": True}
    meta = {"snippet": {"title": rec["title"], "description": desc, "tags": sc.get("tags", []), "categoryId": "27",
                        "defaultLanguage": "ja", "defaultAudioLanguage": "ja"}, "status": status}
    size = os.path.getsize(video)
    r = api(ch, "POST", "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status", meta,
            {"X-Upload-Content-Type": "video/mp4", "X-Upload-Content-Length": str(size)}, timeout=120)
    with open(video, "rb") as f:
        d = json.load(api(ch, "PUT", r.headers["Location"], f.read(), {"Content-Type": "video/mp4"}))
    print("上げました（非公開。公開は見張りが長尺に合わせて予約する）：", f"https://youtube.com/shorts/{d['id']}")
    hist[name] = {"video_id": d["id"], "long_id": long_id, "title": rec["title"], "秒": rec["秒"],
                  "uploaded_at": datetime.datetime.now().astimezone().isoformat(timespec="seconds")}
    json.dump(hist, open(hp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def main():
    a = argparse.ArgumentParser()
    a.add_argument("mode", choices=["make", "upload"])
    a.add_argument("work")
    a.add_argument("--ch", default="job")
    a.add_argument("--go", action="store_true")
    a = a.parse_args()
    work = os.path.abspath(a.work)
    make(work) if a.mode == "make" else upload(work, a.ch, a.go)


if __name__ == "__main__":
    main()

# ⑨完成動画ゲート（アナザー日本紀・2026-10-29 新設）：出来上がった動画を、上げる前に機械と Claude で見る
#   python -X utf8 pipeline/gate_video_nihongi.py <作業フォルダ> [--video short.mp4|long.mp4] [--motion-only]
# ・形：ショートは 1080x1920・59.5秒以内（台本は30〜45秒が目安・手順書 §3）／横動画は 1920x1080・8〜15分
# ・声の大きさ：−14 LUFS の ±1.5 以内（loudnorm2 で整えた後。ffmpeg の ebur128）
# ・無音：ショートは2秒以上、横動画は3秒以上続く無音が無い（silencedetect −45dB）
# ・動く絵：ショートは images/<id>.mp4 が2カット以上で、見どころ（peak）が動く絵（手順書 §3・動画スキル references/16）。
#   クラウドで動画づくりが3回待って静止画のまま先へ進んだ回は、ここで落ちる（紙芝居は出さない）。横動画は0カット・見どころが止まった絵なら落ちる（章ごとの0は注意）
# ・画面：均等に抜き出した画面を Claude（gemini.ask。JUDGE=gemini で Gemini）が見る（字幕の切れ・セーフゾーン・hook の読みやすさ・崩れた絵・偽の文字や看板）。落ちた画面は1枚で見直し、2回とも不合格の時だけ落とす
# ・結果は _gate_video.json。不合格があれば終了コード1
import argparse, glob, json, os, re, subprocess, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gemini  # noqa: E402
from gate_video import ff, length, moving  # noqa: E402
from nihongi_common import kind_of_work  # noqa: E402

LUFS, TOL = -14, 1.5


def size(v):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "csv=p=0", v], capture_output=True, text=True)
    w, h = (r.stdout.strip().split(",") + ["0", "0"])[:2]
    return int(w), int(h)


def main():
    a = argparse.ArgumentParser()
    a.add_argument("work")
    a.add_argument("--video")
    a.add_argument("--motion-only", action="store_true")
    a = a.parse_args()
    work = os.path.abspath(a.work)
    kind = kind_of_work(work)
    v = a.video or os.path.join(work, "long.mp4" if kind == "long" else "short.mp4")
    res, bad = {"種類": kind}, []
    n_mv, still_ch, still_peak = moving(work)
    res["動く絵"] = {"カット": n_mv, "動く絵の無い章": still_ch, "止まった見どころ": still_peak}
    print(f"動く絵 {n_mv} カット・止まった見どころ {len(still_peak)}")
    if kind == "short":
        if (n_mv or 0) < 2:
            bad.append(f"動く絵が{n_mv}カット（ショートは1カット目と見どころの2つ以上。静止画のままの回は出さない）")
    elif not n_mv:
        bad.append("動く絵が0カット（紙芝居は出さない）")
    if still_peak:
        bad.append(f"見どころ（peak）が止まった絵：{still_peak}")
    if a.motion_only:
        for b in bad:
            print("  不合格：", b)
        sys.exit(1 if bad else 0)
    if not os.path.exists(v):
        sys.exit(f"【止まりました】動画がありません：{v}")
    sec = length(v)
    w, h = size(v)
    res.update({"長さ秒": round(sec, 1), "大きさ": f"{w}x{h}"})
    if kind == "short":
        if (w, h) != (1080, 1920):
            bad.append(f"大きさ {w}x{h}（ショートは 1080x1920）")
        if sec > 59.5:
            bad.append(f"長さ {sec:.1f}秒（ショートは59.5秒以内）")
        if sec < 25:
            bad.append(f"長さ {sec:.1f}秒（短すぎる。台本は30〜45秒）")
    else:
        if (w, h) != (1920, 1080):
            bad.append(f"大きさ {w}x{h}（横動画は 1920x1080）")
        if not 480 <= sec <= 930:
            bad.append(f"長さ {sec / 60:.1f}分（8〜15分）")
    sil_d = 2.0 if kind == "short" else 3.0
    log = ff("-i", v, "-vn", "-af", f"ebur128,silencedetect=n=-45dB:d={sil_d}", "-f", "null", "-")
    m = re.findall(r"I:\s+(-?[\d.]+) LUFS", log)
    lufs = float(m[-1]) if m else None
    res["LUFS"] = lufs
    if lufs is None or abs(lufs - LUFS) > TOL:
        bad.append(f"声の大きさ {lufs} LUFS（{LUFS}±{TOL}の外）")
    sil = [float(x) for x in re.findall(r"silence_start: (-?[\d.]+)", log)]
    res["無音"] = sil
    if sil:
        bad.append(f"{sil_d:.0f}秒以上の無音 {len(sil)}か所（最初 {sil[0]:.1f}秒）")
    nfr = 8 if kind == "short" else 10
    d = os.path.join(work, "_build", "_frames")
    os.makedirs(d, exist_ok=True)
    shots = []
    for i in range(nfr):
        t = max(0.4, sec * (i + 0.5) / nfr) if i else 0.6  # 1枚目は頭（hook の画面）
        p = os.path.join(d, f"f{i:02d}.jpg")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.2f}", "-i", v, "-frames:v", "1", "-vf", "scale=720:-2" if kind == "short" else "scale=1280:-2", "-q:v", "3", p])
        shots.append((p, t))
    S = {"type": "string"}
    sch = {"type": "object", "properties": {"判定": {"type": "array", "items": {"type": "object", "properties": {
        "枚目": {"type": "integer"}, "合格": {"type": "boolean"}, "問題": S}, "required": ["枚目", "合格", "問題"]}}}, "required": ["判定"]}
    zone = ("画面は縦長（9:16）。ショートのボタンや説明文にかぶらないよう、文字（帯・字幕・hook）は、上から15%・下から35%・左から4%・右から18%の外側に置く決まり。"
            "文字がこの外にはみ出していれば問題。帯（上の帯）と字幕は、画面の真ん中にそろっていて左右どちらかに寄っていない決まり。" if kind == "short" else
            "画面は横長（16:9）。字幕と場面の見出しが、人物の顔にかぶっていないか。")
    q = f"""YouTube に上げる前の歴史の解説動画（『もしも歴史』の作り話。劇画寄りの歴史漫画の絵）から、均等に{nfr}枚の画面を切り出しました。添付の順に1枚目〜{nfr}枚目です（1枚目は動画の頭）。
1枚ずつ、見る人が気づく次の問題があれば不合格にしてください。
1. 字幕・帯・hook の文字が画面の端で切れている、文字化けしている（□や記号の羅列）、字が小さすぎて読めない
2. {zone}
3. 画面が真っ黒・真っ白・ほぼ何も映っていない
4. 絵が崩れている（手・顔・体・刀などの物の形）、同じ人が別人になっている
5. 絵の中に読める偽の文字・ロゴ・看板の字・吹き出しがある（字幕と帯とhookは除く）
6. 1枚目：hook（大きな結論の文字）が1行5字・2行までで読めるか。
問題が無ければ合格・問題は空。あれば問題を短く書いてください。"""
    t, u = gemini.ask(q, schema=sch, images=[p for p, _ in shots])
    use = [u]
    fr = json.loads(t)["判定"]
    res["画面"] = [{**x, "秒": round(shots[x["枚目"] - 1][1], 1)} for x in fr if 1 <= x["枚目"] <= nfr]
    for x in res["画面"]:
        if not x["合格"]:
            q1 = (q.replace(f"均等に{nfr}枚の画面を切り出しました。添付の順に1枚目〜{nfr}枚目です（1枚目は動画の頭）。\n1枚ずつ、", "1枚の画面を切り出しました。")
                  + f"\n前の判定では「{x['問題']}」と言われました。本当に見る人が気づく問題か、もう一度見てください。枚目は1。")
            t1, u1 = gemini.ask(q1, schema=sch, images=[shots[x["枚目"] - 1][0]])
            use.append(u1)
            r1 = (json.loads(t1)["判定"] or [{"合格": False, "問題": "見直しの答えが空"}])[0]
            x["見直し"] = {"合格": r1["合格"], "問題": r1["問題"]}
            if r1["合格"]:
                x["合格"] = True
            else:
                bad.append(f"画面 {x['秒']}秒：{x['問題']}（見直しも不合格：{r1['問題']}）")
    res["不合格"] = bad
    json.dump(res, open(os.path.join(work, "_gate_video.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"完成動画ゲート：{sec:.1f}秒・{w}x{h}・{lufs} LUFS・{sil_d:.0f}秒以上の無音 {len(sil)}か所・画面 合格{sum(x['合格'] for x in res['画面'])}/{len(res['画面'])}")
    for b in bad:
        print("  不合格：", b)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()

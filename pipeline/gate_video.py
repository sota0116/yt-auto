# ⑨完成動画ゲート（設計書 §5⑨）：出来上がった動画を、上げる前に機械と Claude（2026-10-24 までは Gemini）で見る
#   python -X utf8 pipeline\gate_video.py <作業フォルダ> [--video long.mp4]
# ・長さ：8分以上
# ・声の大きさ：−15 LUFS の ±2 以内（ffmpeg の ebur128 で測る）
# ・無音：3秒以上続く無音が無い（ffmpeg の silencedetect、−45dB）。クイズの間（2秒）は引っかからない
# ・画面：均等に10枚切り出して Gemini が見る（字幕と図のかぶり・切れた文字・真っ黒/真っ白・崩れた絵・読める偽の文字やロゴ）
# ・不合格の画面は、1枚だけでもう一度見せる。2回とも不合格の時だけ落とす（まとめての判定が回ごとに揺れるため）
# ・結果は _gate_video.json。不合格があれば終了コード1
import argparse, json, os, re, subprocess, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gemini

MIN_SEC, LUFS, LUFS_TOL, SIL_SEC, SIL_DB, FRAMES = 480, -15, 2, 3.0, -45, 10


def topic(work):
    """何の動画か。チャンネルの profile.json の topic（無ければ仕事チャンネルの言い方）"""
    p = os.path.normpath(os.path.join(work, "..", "..", "profile.json"))
    return (json.load(open(p, encoding="utf-8")).get("topic") if os.path.exists(p) else None) or "日本の仕事と年収の統計"


def ff(*args):
    return subprocess.run(["ffmpeg", "-hide_banner", "-nostats", *args], capture_output=True, text=True, encoding="utf-8", errors="replace").stderr


def length(v):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", v], capture_output=True, text=True)
    return float(r.stdout.strip())


def main():
    a = argparse.ArgumentParser()
    a.add_argument("work")
    a.add_argument("--video")
    a = a.parse_args()
    v = a.video or os.path.join(a.work, "long.mp4")
    res, bad = {}, []
    sec = length(v)
    res["長さ秒"] = round(sec, 1)
    if sec < MIN_SEC:
        bad.append(f"長さが{sec / 60:.1f}分（8分未満）")
    log = ff("-i", v, "-vn", "-af", f"ebur128,silencedetect=n={SIL_DB}dB:d={SIL_SEC}", "-f", "null", "-")
    m = re.findall(r"I:\s+(-?[\d.]+) LUFS", log)
    lufs = float(m[-1]) if m else None
    res["LUFS"] = lufs
    if lufs is None or abs(lufs - LUFS) > LUFS_TOL:
        bad.append(f"声の大きさ {lufs} LUFS（{LUFS}±{LUFS_TOL}の外）")
    sil = [float(x) for x in re.findall(r"silence_start: (-?[\d.]+)", log)]
    res["3秒以上の無音"] = sil
    if sil:
        bad.append(f"3秒以上の無音 {len(sil)}か所（最初 {sil[0]:.1f}秒）")
    d = os.path.join(a.work, "_build", "_frames")
    os.makedirs(d, exist_ok=True)
    shots = []
    for i in range(FRAMES):
        t = sec * (i + 0.5) / FRAMES
        p = os.path.join(d, f"f{i:02d}.jpg")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.2f}", "-i", v, "-frames:v", "1", "-vf", "scale=1280:-2", "-q:v", "3", p])
        shots.append((p, t))
    S = {"type": "string"}
    sch = {"type": "object", "properties": {"判定": {"type": "array", "items": {"type": "object", "properties": {
        "枚目": {"type": "integer"}, "合格": {"type": "boolean"}, "問題": S}, "required": ["枚目", "合格", "問題"]}}}, "required": ["判定"]}
    q = f"""YouTube に上げる前の解説動画（{topic(a.work)}）から、均等に{FRAMES}枚の画面を切り出しました。添付の順に1枚目〜{FRAMES}枚目です。
1枚ずつ、見る人が気づく次の問題があれば不合格にしてください。
1. 字幕の帯が、図の数字・文字や大事な所にかぶっている
2. 文字が画面の端で切れている、文字化けしている（□や記号の羅列）
3. 画面が真っ黒・真っ白・ほぼ何も映っていない
4. 絵が崩れている（手・顔・体・物の形）
5. 絵の中に読める偽の文字・ロゴ・ブランド名がある
問題が無ければ合格・問題は空。あれば問題を短く書いてください。"""
    t, u = gemini.ask(q, schema=sch, images=[p for p, _ in shots])
    use = [u]
    fr = json.loads(t)["判定"]
    res["画面"] = [{**x, "秒": round(shots[x["枚目"] - 1][1], 1)} for x in fr if 1 <= x["枚目"] <= FRAMES]
    for x in res["画面"]:
        if not x["合格"]:
            # 10枚まとめての判定は回ごとに揺れる（2026-10-24：同じ画面が1回目は合格・2回目は不合格）。落ちた画面だけ1枚で見直し、2回とも不合格なら落とす
            q1 = (q.replace(f"均等に{FRAMES}枚の画面を切り出しました。添付の順に1枚目〜{FRAMES}枚目です。\n1枚ずつ、", "1枚の画面を切り出しました。")
                  + f"\n前の判定では「{x['問題']}」と言われました。本当に見る人が気づく問題か、もう一度見てください。枚目は1。")
            t1, u1 = gemini.ask(q1, schema=sch, images=[shots[x["枚目"] - 1][0]])
            use.append(u1)
            r1 = (json.loads(t1)["判定"] or [{"合格": False, "問題": "見直しの答えが空"}])[0]
            x["見直し"] = {"合格": r1["合格"], "問題": r1["問題"]}
            if r1["合格"]:
                x["合格"] = True
            else:
                bad.append(f"画面 {x['秒']}秒：{x['問題']}（見直しも不合格：{r1['問題']}）")
    yen = round(sum((u.get("promptTokenCount", 0) / 1e6 * 0.5 + (u.get("candidatesTokenCount", 0) + u.get("thoughtsTokenCount", 0)) / 1e6 * 3.0) * 155 for u in use), 1)
    res["不合格"] = bad
    res["Gemini円"] = yen
    json.dump(res, open(os.path.join(a.work, "_gate_video.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"完成動画ゲート：{sec / 60:.1f}分・{lufs} LUFS・3秒以上の無音 {len(sil)}か所・画面 合格{sum(x['合格'] for x in res['画面'])}/{len(res['画面'])}・Gemini 約{yen}円")
    for b in bad:
        print("  不合格：", b)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()

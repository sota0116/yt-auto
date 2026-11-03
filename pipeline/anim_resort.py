# 型A-4 の山場「年収の順位 → 時給の順位」の入れ替わりを、animate（手描き風の動く図）で作る（手順書 §5）
#   make_charts_job.py から呼ぶ。続いた rank_swap のカット（F01〜F04 など）を、1本の動画から切り分けて images\<id>.mp4 に置く
#   python -X utf8 pipeline\anim_resort.py <作業フォルダ>   （単体で試す時）
# ・数字と順位はすべて facts.json から取る（make_charts_job.Facts と同じ物差し）。雛形は pipeline\anim\resort\
# ・作れない時（node・Playwright が無い、名前が長すぎる、など）は例外を出す。呼ぶ側は今までの図（PIL の rank_swap）で作る
# ・区切り：shown 0 のカット＝並べ替え（SEG0 秒）、shown k のカット＝k 番目の職業（SEGL 秒ずつ）。声が長い分は組み立てで最後の画面をのばす
import json, os, re, shutil, subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE = os.path.join(ROOT, "pipeline", "anim", "resort")
ANIMATE = os.path.join(ROOT, "vendor", "animate")
SEG0, SEGL = 3.0, 2.0   # src/head.html と同じ値
FPS_OUT = 30            # make_charts_job.py の FPS
MAX_NAME = 7            # 1人の幅 312px に 44px の字で入る数（「タクシー運転手」で確かめた）
SHORT = {"ケアマネージャー": "ケアマネ"}
MARKS = [("バス", "wheel"), ("タクシー", "lamp"), ("運転", "wheel"), ("トラック", "wheel"), ("リハビリ", "plus"), ("理学", "plus"),
         ("看護", "plus"), ("医", "plus"), ("幼稚園", "flower"), ("教諭", "flower"), ("先生", "flower"), ("保育", "heart"),
         ("ケアマネ", "check"), ("介護", "check")]


def short_name(name):
    if name in SHORT:
        return SHORT[name]
    m = re.search(r"（(.+?)）", name)
    s = m.group(1) if m else name.split("・")[0]
    if len(s) > MAX_NAME:
        raise ValueError(f"職業の名前が長すぎて駒の下に入りません：{name} → {s}")
    return s


def mark_of(name):
    return next((k for w, k in MARKS if w in name), "dot")


def groups(cuts):
    """続いた rank_swap のカットを、同じ jobs ごとにまとめる"""
    out, cur = [], []
    for c in cuts:
        ch = c.get("chart") or {}
        if ch.get("kind") == "rank_swap" and (not cur or cur[0]["chart"]["jobs"] == ch["jobs"]):
            cur.append(c)
            continue
        if cur:
            out.append(cur)
        cur = [c] if ch.get("kind") == "rank_swap" else []
    if cur:
        out.append(cur)
    return out


def data_of(fx, focus):
    inc, wage = fx.order("年収"), fx.order("時給に直した額")
    if len(inc) > 6:
        raise ValueError(f"1画面の棒は6本まで（手順書 §5）：{len(inc)}本")
    if sorted(inc) != sorted(wage):
        raise ValueError("年収と時給の順位の職業がそろっていません")
    names = {j: short_name(j) for j in inc}
    if len(set(names.values())) != len(names):
        raise ValueError(f"短くした名前が重なります：{names}")
    jobs = [{"name": names[j], "inc": float(fx.val(j, "年収")), "wage": float(fx.val(j, "時給に直した額")),
             "r1": inc.index(j) + 1, "r2": wage.index(j) + 1, "mark": mark_of(j)} for j in inc]
    for j in focus:
        if j not in names:
            raise ValueError(f"rank_swap の職業が facts.json の順位にありません：{j}")
    src = fx.source or ""
    return {"jobs": jobs, "focus": [names[j] for j in focus], "src": src}


def slices(group):
    """カットごとの [始まり, 終わり] 秒。最初のカットは 0 から（並べ替えを必ず見せる）"""
    out = []
    for n, c in enumerate(group):
        k = int(c["chart"].get("shown", 0))
        t0 = 0.0 if (n == 0 or k == 0) else SEG0 + (k - 1) * SEGL
        t1 = SEG0 + k * SEGL if k > 0 else SEG0
        out.append((c["id"], t0, t1))
    return out


def run(cmd, log):
    with open(log, "a", encoding="utf-8") as f:
        r = subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT, cwd=ROOT)
    if r.returncode:
        raise RuntimeError(f"止まりました（{os.path.basename(cmd[1])}）：{log} を見てください")


def make(work, group, fx):
    """1つの rank_swap のまとまりを animate で作り、カットごとに images\\<id>.mp4 と _charts\\<id>.png を置く"""
    if not shutil.which("node"):
        raise RuntimeError("node が無い")
    focus = group[0]["chart"]["jobs"]
    data = data_of(fx, focus)
    piece = os.path.join(work, "_anim", "resort_" + group[0]["id"])
    if os.path.exists(os.path.join(piece, "src")):
        shutil.rmtree(os.path.join(piece, "src"))
    os.makedirs(piece, exist_ok=True)
    shutil.copy(os.path.join(TEMPLATE, "piece.json"), piece)
    shutil.copytree(os.path.join(TEMPLATE, "src"), os.path.join(piece, "src"))
    head = os.path.join(piece, "src", "head.html")
    h = open(head, encoding="utf-8").read()
    if "/*DATA*/null" not in h:
        raise RuntimeError("雛形の head.html に /*DATA*/null がありません")
    open(head, "w", encoding="utf-8").write(h.replace("/*DATA*/null", json.dumps(data, ensure_ascii=False)))
    log = os.path.join(piece, "anim.log")
    open(log, "w").close()
    run(["node", os.path.join(ANIMATE, "tools", "build.mjs"), piece], log)
    run(["node", os.path.join(ANIMATE, "tools", "export.mjs"), piece, "--no-audio", "--no-captions"], log)
    final = os.path.join(piece, "renders", "final.mp4")
    if not os.path.exists(final):
        raise RuntimeError("renders/final.mp4 ができていません")
    os.makedirs(os.path.join(work, "images", "_charts"), exist_ok=True)
    made = []
    for cid, t0, t1 in slices(group):
        out = os.path.join(work, "images", cid + ".mp4")
        tmp = out + ".part.mp4"
        r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t0:.3f}", "-t", f"{t1 - t0:.3f}", "-i", final,
                            "-vf", f"fps={FPS_OUT}", "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "16", "-preset", "fast", tmp])
        if r.returncode or not os.path.exists(tmp):
            raise RuntimeError(f"切り分けに失敗：{cid}")
        png = os.path.join(work, "images", "_charts", cid + ".png")   # 確かめ用：そのカットの最後の画面
        r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-sseof", "-0.05", "-i", tmp, "-frames:v", "1", "-update", "1", png])
        if r.returncode:
            raise RuntimeError(f"確かめ用の絵に失敗：{cid}")
        made.append((cid, tmp, out))
    for cid, tmp, out in made:   # 全部できてから置き換える（途中で止まった時に、PIL の図と混ざらないように）
        os.replace(tmp, out)
    shutil.rmtree(os.path.join(piece, "frames"), ignore_errors=True)   # 書き出しの1枚ずつの絵（約200枚）。作業フォルダは次の実行に引き継ぐので残さない
    return [cid for cid, _, _ in made]


if __name__ == "__main__":
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from make_charts_job import Facts
    w = sys.argv[1]
    s = json.load(open(os.path.join(w, "script.json"), encoding="utf-8"))
    fx = Facts(json.load(open(os.path.join(w, "facts.json"), encoding="utf-8")))
    for g in groups(s["cuts"]):
        print("animate:", make(w, g, fx))

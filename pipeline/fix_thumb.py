# サムネの字を、字の組み方と短い言い換えだけで直す（run_daily.py の thumb の段）
#   python -X utf8 pipeline/fix_thumb.py <作業フォルダ>                      … 字の面積が基準（30%）に届かない時（詰まった時の決まり8）
#   python -X utf8 pipeline/fix_thumb.py <作業フォルダ> --reason "<NG の理由>"  … check_thumb_text.py で NG（意味が通らない・つながらない等）の時
# ・直すのは字の項目だけ。絵（bg など）はそのまま。前の指定は _thumb_old.json に足していく
# ・面積の基準は変えない。意味も足さない（台本ゲートを通った内容のまま、行の分け方と短い言い換えで直す）
# ・手で直した例：おきぬ 102「カバンに／●●入れたまま」→「カバンに●●／入れたまま」、日本紀 L101 は下の段を8字→7字（2026-10-31）
# v2（2026-11-04）
# ・本人「サムネのテキストが日本語的に意味わからなかったり、文脈が繋がってないことが多いから変える」
# ・v1 の決まりにあった「助詞を省く」を外した（「年収は建築／でも逆転」のような、つながらない字の元になる）。意味が通ることと、上下の段が1文でつながることを守らせる
# ・job（トップの階層の thumb_top / thumb_text / thumb_lines）と psy（thumb.lines / lines_b）も直せるようにした（v1 は thumb の中の項目だけで、job は直せなかった）
# ・--reason で、面積以外の直し（check_thumb_text の NG）にも使えるようにした
# ・v1 は _backup_2026-11-04/fix_thumb_v1.py（調査/サムネ文字調査_2026-11-03 の中）
import argparse, json, os, re, shutil, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEXT = ("line1", "line2", "judge", "top", "big", "hl", "hl_top", "hl_big", "left_label", "right_label", "tag", "lines", "lines_b")
JOB = ("thumb_top", "thumb_text", "thumb_lines")
JOB_MAX = {"thumb_top": 16, "thumb_text": 10}  # make_thumb_job.py の字数の上限
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from nihongi_common import claude_env  # noqa: E402


def title_of(s):
    t = s.get("title") or (s.get("titles") or [""])[0]
    return t if isinstance(t, str) else str(t)


def is_job(s):
    return not isinstance(s.get("thumb"), dict) and bool(s.get("thumb_text"))


def nums(x):
    """数字の集合。色の指定（#FFE234 など）は数えない"""
    return set(re.findall(r"\d+", re.sub(r"#[0-9A-Fa-f]{6}", "", json.dumps(x, ensure_ascii=False))))


def ok_lines(v):
    """psy の lines の形：[[["語","#色"],..],..]"""
    return isinstance(v, list) and v and all(isinstance(l, list) and l and all(
        isinstance(p, list) and len(p) == 2 and all(isinstance(z, str) for z in p) for p in l) for l in v)


def merge(old, new, keys, allowed_nums):
    """字の項目だけを取り込む。元に無かった項目は足さない。元とタイトルに無い数字が入ったら取り込まない。
    色を変える語（hl）が本文から消えたら外す"""
    out = dict(old)
    for k in keys:
        if k not in old or k not in new or not new[k] or type(new[k]) is not type(old[k]):
            continue
        if k in ("lines", "lines_b") and not ok_lines(new[k]):
            continue
        if k in JOB_MAX and len(new[k]) > JOB_MAX[k]:
            continue
        if nums(new[k]) - allowed_nums:
            continue
        out[k] = new[k]
    if "thumb_lines" in out and "".join(out["thumb_lines"]) != out.get("thumb_text"):
        out.pop("thumb_lines")  # 割り方が本文と合わない時は外す（make_thumb_job が語の切れ目で割る）
    body = "".join(str(out.get(k) or "") for k in ("line1", "line2", "judge", "top", "big")).replace("\n", "")
    if isinstance(out.get("hl"), list):
        out["hl"] = [w for w in out["hl"] if w in body]
    for k in ("hl_top", "hl_big"):
        if out.get(k) and out[k] not in body:
            out[k] = ""
    return out


def ask(cur, title, reason):
    why = (f"点検で次の理由で NG になりました：{reason}" if reason else
           "字が小さく、字の面積が基準の30%に届きませんでした。")
    area = ("" if reason else
            "- 各行の字数の差を小さくする（いちばん長い行の字数が減るほど、1字が大きくなる）。行の境目を動かすか、同じ意味の短い語に替える\n")
    p = f"""YouTube のサムネの字を直してください。{why}
動画のタイトル：{title or "（無し）"}
今の指定：
{json.dumps(cur, ensure_ascii=False)}

決まり
- 字だけを読んで、何の話か・誰（何）のことか分かるようにする。主語や対象を落とさない（「損するのは誰？」だけ、のような主語の無い問いにしない）
- 上の段と下の段（行どうし）を続けて読むと、自然な日本語の1文（か、自然に続く2文）になるようにする。助詞（は・が・を・に・の・で・と）は省かない
- 行の境目は語の切れ目（文節の後ろ）に置く。語の途中で割らない。2行目を助詞から始めない
{area}- 言っている内容は変えない。新しい主張・言葉を足さない。数字はタイトルか今の指定にある物だけ使う。伏せ字（●●）は伏せたまま残す
- タイトルをそのまま写さない（タイトル＝何の話か、サムネ＝命令・結果・数の落差・伏せた答え・問い、と役を分ける）
- 項目の名前と形は今の指定のまま。色を変える語（hl・hl_top・hl_big、lines の "#FFE234" の語）は本文に残る語にし、語の途中で切らない
- thumb_text は10字以内、thumb_top は16字以内。thumb_lines は、つなぐと thumb_text になる並び
- 説明は書かず、直した後の指定を JSON のオブジェクトだけで出力する"""
    r = subprocess.run([shutil.which("claude") or "claude", "-p", "--model", os.environ.get("CLAUDE_PICK_MODEL", "sonnet"), "--output-format", "json"],
                       cwd=ROOT, env=claude_env(), input=p, capture_output=True, text=True, encoding="utf-8", timeout=600)
    out = json.loads(r.stdout).get("result", "")
    return json.loads(out[out.index("{"):out.rindex("}") + 1])


def main():
    a = argparse.ArgumentParser()
    a.add_argument("work")
    a.add_argument("--reason", default="")
    a = a.parse_args()
    sp = os.path.join(a.work, "script.json")
    s = json.load(open(sp, encoding="utf-8"))
    title = title_of(s)
    if is_job(s):
        keys = JOB
        old = {k: s[k] for k in JOB if k in s}
    else:
        keys = TEXT
        old = s.get("thumb")
        if not isinstance(old, dict) or not any(old.get(k) for k in TEXT):
            sys.exit("【止まりました】script.json の thumb に、直せる字の項目がありません")
    new = merge(old, ask({k: old[k] for k in keys if k in old}, title, a.reason), keys, nums(old) | nums(title))
    if new == old:
        sys.exit("【止まりました】サムネの字の直しで、変わる所がありませんでした")
    hp = os.path.join(a.work, "_thumb_old.json")
    hist = json.load(open(hp, encoding="utf-8")) if os.path.exists(hp) else []
    json.dump(hist + [old], open(hp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    if is_job(s):
        for k in JOB:
            s.pop(k, None)
        s.update(new)
    else:
        s["thumb"] = new
    json.dump(s, open(sp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("サムネの字を直しました：", json.dumps(new, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()

# サムネの字の面積が基準（30%）に届かない時に、字の組み方だけを変える（run_daily.py の thumb の段。詰まった時の決まり8）
#   python -X utf8 pipeline/fix_thumb.py <作業フォルダ>
# ・直すのは script.json の thumb の字の項目だけ。絵（bg など）はそのまま。前の指定は _thumb_old.json に足していく
# ・面積の基準は変えない。意味も足さない（台本ゲートを通った内容のまま、行の分け方と短い言い換えで字を太くする）
# ・手で直した例：おきぬ 102「カバンに／●●入れたまま」→「カバンに●●／入れたまま」、日本紀 L101 は下の段を8字→7字（2026-10-31）
import json, os, shutil, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEXT = ("line1", "line2", "judge", "top", "big", "hl", "hl_top", "hl_big", "left_label", "right_label")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from nihongi_common import claude_env  # noqa: E402


def merge(old, new):
    """字の項目だけを取り込む。元に無かった項目は足さない。色を変える語（hl）が本文から消えたら元の字のまま外す"""
    out = dict(old)
    for k in TEXT:
        if k in old and k in new and type(new[k]) is type(old[k]) and new[k]:
            out[k] = new[k]
    body = "".join(str(out.get(k) or "") for k in ("line1", "line2", "judge", "top", "big")).replace("\n", "")
    if isinstance(out.get("hl"), list):
        out["hl"] = [w for w in out["hl"] if w in body]
    for k in ("hl_top", "hl_big"):
        if out.get(k) and out[k] not in body:
            out[k] = ""
    return out


def ask(thumb):
    p = f"""YouTube のサムネの字が小さく、字の面積が基準の30%に届きませんでした。次の指定の字を直してください。
{json.dumps(thumb, ensure_ascii=False)}

決まり
- 言っている内容は変えない。新しい主張・数字・言葉を足さない。伏せ字（●●）は伏せたまま残す
- 各行の字数の差を小さくする（いちばん長い行の字数が減るほど、1字が大きくなる）。行の境目を動かす、助詞を省く、同じ意味の短い語に替える、のどれかで直す
- line1 / line2 / judge / top / big の項目だけを直す。hl・hl_top・hl_big は本文に残る語にする
- 説明は書かず、直した後の指定を JSON のオブジェクトだけで出力する"""
    r = subprocess.run([shutil.which("claude") or "claude", "-p", "--model", os.environ.get("CLAUDE_PICK_MODEL", "sonnet"), "--output-format", "json"],
                       cwd=ROOT, env=claude_env(), input=p, capture_output=True, text=True, encoding="utf-8", timeout=600)
    out = json.loads(r.stdout).get("result", "")
    return json.loads(out[out.index("{"):out.rindex("}") + 1])


def main():
    work = sys.argv[1]
    sp = os.path.join(work, "script.json")
    s = json.load(open(sp, encoding="utf-8"))
    old = s.get("thumb")
    if not isinstance(old, dict) or not any(old.get(k) for k in TEXT):
        sys.exit("【止まりました】script.json の thumb に、直せる字の項目がありません")
    new = merge(old, ask(old))
    if new == old:
        sys.exit("【止まりました】サムネの字の直しで、変わる所がありませんでした")
    hp = os.path.join(work, "_thumb_old.json")
    hist = json.load(open(hp, encoding="utf-8")) if os.path.exists(hp) else []
    json.dump(hist + [old], open(hp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    s["thumb"] = new
    json.dump(s, open(sp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("サムネの字を直しました：", json.dumps(new, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()

# 題が、同じチャンネルのほかの動画の題の言い換えになっていないかを見る（2026-10-30 金運おきぬ。本人「これ公開されてるから違うでしょ」）
#   003 の題「【要注意】玄関を開けた時にコレが見える家は、お金が逃げて貧乏になります。」が、公開済みの 001v6
#   「【要注意】財布を開けた時にコレが入っている人は、金運が逃げて貧乏になります」の物の名前を替えただけだった（制作ルール §12 の2）
# ・【】・記号・数字・伏せ字を外して、文字の並びの似ている度合い（difflib）を出す。0.55 以上で止める
#   （測った値：001v6 と旧003 は 0.73、002 と「トイレに〇〇を置いてたら要注意！お金が逃げる家のトイレのNG5選」は 0.78。
#    言い換えでない組み合わせは、いちばん高くて 0.47）
#   python -X utf8 pipeline\title_guard.py okinu "新しい題"
import difflib, re, sys

LINE = 0.55


def core(t):
    return re.sub(r"[【\[].*?[】\]]|[、。！？!?…・\s0-9０-９〇●]", "", t)


def similar(title, others, skip=()):
    """(似ている度合い, 相手の題) を、似ている順に"""
    out = [(difflib.SequenceMatcher(None, core(title), core(o)).ratio(), o) for o in others if o != title and o not in skip]
    return sorted(out, reverse=True)


def check(title, others, skip=()):
    hits = [(r, o) for r, o in similar(title, others, skip) if r >= LINE]
    if hits:
        sys.exit("【止めました】題が、チャンネルのほかの動画の題の言い換えになっています（title_guard.py・似ている度合い "
                 + "／".join(f"{r:.2f}「{o}」" for r, o in hits[:3]) + "）。型（制作ルール §8 の A〜F）か言い回しを替える")


if __name__ == "__main__":
    sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.abspath(__file__)))
    from upload_job import channel_titles
    t = sys.argv[2]
    for r, o in similar(t, channel_titles(sys.argv[1]))[:5]:
        print(f"{r:.2f}  {o}")
    check(t, channel_titles(sys.argv[1]))
    print("OK（言い換えになっている題はありません）")

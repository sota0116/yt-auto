# 仕事ch（job）のネタ帳の自動補充（毎日 01:17 の research.yml。2026-11-17 本人「なんで俺がやるんだよ」：ネタ切れを人に頼まない）
#   python -X utf8 pipeline\refill_job_neta.py [--dry]
# ・今日選べる行（使っていない・hold でない・facts を作るプログラムがある・作ってよい期間に入っている）が LOW 行を切ったら、
#   統計の職業から 型C「〇〇の1日」の行を1日 ADD 職業まで足す。同じ職業の C-4「〇〇の一生」の行も、8週あけた日（window_start）で一緒に足す
# ・職業の順番：data\job\main40_r7.json の主な職業40（表示名がそろっている）→ 尽きたら shokushu_r7.json の残りの職種（調査の名前のまま。
#   「その他」「他に分類されない」「不詳」「管理的」は外す）。job_facts_common.JOBS にもう入っている職種は飛ばす
# ・足す前に、その職業で c_facts.py（と isshou_facts.py）が facts.json を作れるかを、捨てる作業フォルダで試す。作れない職業は足さない
# ・足した職業は data\job\jobs_extra.json に書く（job_facts_common.py が JOBS に足して読む。産業は当てはめない＝ A-1 には使わない）
# ・値の計算はしない（c_facts.py・isshou_facts.py がする）。全部の職業を使い切ったら Issue を1つ立てる
import argparse, datetime, json, os, sys, tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import job_facts_common as c

ROOT = c.ROOT
BOARD = os.path.join(ROOT, "channels", "job", "ネタ帳.json")
EXTRA = os.path.join(c.DATA, "jobs_extra.json")
JST = datetime.timezone(datetime.timedelta(hours=9))
LOW, ADD, GAP_DAYS = 6, 2, 56
SKIP_WORDS = ("その他", "他に分類されない", "不詳", "管理的")
TARGET_C = "その仕事に就こうか迷っている、または今その仕事をしている20〜40代"
TARGET_C4 = "20〜50代で、今の仕事を続けた先の年収の合計が気になっている会社員"


def jload(p, d):
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else d


def used_ids():
    prod = jload(os.path.join(ROOT, "history", "job", "produced.json"), [])
    ids = {p.get("neta_id") for p in prod}
    vdir = os.path.join(ROOT, "channels", "job", "videos")
    for d in os.listdir(vdir) if os.path.isdir(vdir) else []:
        ids.add(jload(os.path.join(vdir, d, "neta.json"), {}).get("id"))
    return ids


def pickable(board, used, today):
    out = []
    for r in board:
        cmd = r.get("facts_cmd")
        if r["id"] in used or r.get("hold") or not cmd or not os.path.exists(os.path.join(ROOT, "pipeline", cmd[0])):
            continue
        if (r.get("window_start") and today < r["window_start"]) or (r.get("window_end") and today > r["window_end"]):
            continue
        out.append(r)
    return out


def pool():
    """(職種, 表示名) を足す順に。主な職業40 → 残りの職種"""
    m40 = c.load("main40_r7.json")["data"]
    sh = c.load("shokushu_r7.json")["data"]["男女計"]
    out = [(x["職種"], x["表示名"]) for x in m40]
    seen = {o for o, _ in out}
    out += [(n, n) for n in sh if n not in seen and not any(w in n for w in SKIP_WORDS)]
    names = list(sh)
    return [(o, d, f"j{names.index(o):03d}") for o, d in out if o in sh]


def try_make(key, spec, isshou):
    """捨てる作業フォルダで facts.json を作れるか。作れれば True"""
    import c_facts, isshou_facts
    c.JOBS[key] = spec
    ok = True
    for mod in ([c_facts] + ([isshou_facts] if isshou else [])):
        with tempfile.TemporaryDirectory() as w:
            try:
                mod.make(w, key)
                ok = ok and os.path.exists(os.path.join(w, "facts.json"))
            except SystemExit as e:
                print(f"  {spec['表示名']}：{mod.__name__} で作れない（{e}）")
                ok = False
    del c.JOBS[key]
    return ok


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--dry", action="store_true")
    a = a.parse_args()
    now = datetime.datetime.now(JST)
    today = now.date().isoformat()
    board, extra = jload(BOARD, []), jload(EXTRA, {})
    free = pickable(board, used_ids(), today)
    if len(free) >= LOW:
        print(f"job のネタ帳：今日選べる行 {len(free)}行（{LOW}行以上あるので足さない）")
        return
    have = {o for j in c.JOBS.values() for o in j["職種"]}
    forty = set(c.load("a1c_r7.json")["data"]["〇〇の40年の職業"])
    ids = {r["id"] for r in board}
    rows, added = [], []
    for official, disp, key in pool():
        if len(added) >= ADD:
            break
        if official in have or key in c.JOBS or f"c_{key}" in ids:
            continue
        spec = {"職種": [official], "表示名": disp, "産業": None, "足した日": today, "足したもの": "refill_job_neta.py"}
        isshou = official in forty
        if not try_make(key, spec, isshou):
            continue
        extra[key] = spec
        added.append(disp)
        rows.append({"id": f"c_{key}", "title": disp, "type": "C", "frame": "C", "target": TARGET_C, "window_start": "", "window_end": "",
                     "data_ref": "", "premise_numbers": [], "expected_top": "", "facts_cmd": ["c_facts.py", "make", "{work}", key], "hold": False,
                     "メモ": f"ネタ帳の自動補充（refill_job_neta.py・{today}）。統計の職種「{official}」"})
        if isshou:
            ws = (now.date() + datetime.timedelta(days=GAP_DAYS)).isoformat()
            rows.append({"id": f"c4_{key}", "title": f"{disp}の一生", "type": "C", "frame": "C-4", "target": TARGET_C4,
                         "window_start": ws, "window_end": "",
                         "data_ref": "data/job/a1c_r7.json（賃金構造基本統計 第5表の年齢階級・第1表の産業計）", "premise_numbers": [],
                         "expected_top": "", "facts_cmd": ["isshou_facts.py", "make", "{work}", key], "hold": False,
                         "メモ": f"ネタ帳の自動補充（refill_job_neta.py・{today}）。同じ職業の型C の回から8週あけて {ws} から"})
    print(f"job のネタ帳：今日選べる行 {len(free)}行 → {len(added)}職業・{len(rows)}行を足す：{added}")
    if not added:
        from notify import issue
        issue("【ネタ切れ】job：統計の職業を使い切った", f"{now:%m/%d %H:%M} refill_job_neta.py が足せる職業がもうありません。型B・型D のデータを足すか、型の配分を変える")
        return
    if a.dry:
        return
    json.dump(extra, open(EXTRA, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump(board + rows, open(BOARD, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()

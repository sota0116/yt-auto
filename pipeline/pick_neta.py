# ①ネタ（設計書 §5①・手順書 §3・§8）：次に作る回の型とネタを選び、作業フォルダに neta.json と facts.json を置く
#   python -X utf8 pipeline\pick_neta.py <ch> [--dry]
# ・型の順番：探索期は手順書 §3・§8 の並び（10本で D5・A2・B2・C1。D は続けて2本まで。1本目 A-4、2本目 D）を回す
# ・その型のネタが無い（データがまだ取れない）時は、決まり（D は続けて2本まで・A-1/A-4 は直近9本で3本まで）を守れる別の型に回し、
#   回したことを neta.json の「回した理由」に残す（週報に出す）
# ・型A-4 のネタは、a4_facts の組から作る：直近8週の A の回と、年収1位（山場で下がる職業）が同じ組と、職業が4つ以上重なる組は使わない
# ・ほかの型は channels\<ch>\ネタ帳.json の行。facts を作るプログラム（facts_cmd）が無い行は、データ待ちとして飛ばす
# ・作った回と作り途中の回は、history\<ch>\produced.json と channels\<ch>\videos\ の両方から数える
# ・見張り（watch.py）が history\<ch>\type_hold.json に書いた型（直近5本の平均視聴率が30%未満）は、順番の後ろに回す（設計書 §2「型の後回し」）
import argparse, datetime, hashlib, itertools, json, os, re, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))
JST = datetime.timezone(datetime.timedelta(hours=9))
SEQ = ["A", "D", "B", "D", "A", "D", "C", "B", "D", "D"]  # 探索期の10本の並び（判定会で型の配分が決まったら profile.json の type_seq で置き換える）
GAP_DAYS = 56  # 同じ職業・同じ題は8週あける


def today():
    return datetime.datetime.now(JST).date()


def done_list(ch):
    """作った回（produced.json）＋作り途中の回（videos の中の neta.json）を、作った順に"""
    p = os.path.join(ROOT, "history", ch, "produced.json")
    out = json.load(open(p, encoding="utf-8")) if os.path.exists(p) else []
    seen = {x["work"] for x in out}
    vdir = os.path.join(ROOT, "channels", ch, "videos")
    for name in sorted(os.listdir(vdir)) if os.path.isdir(vdir) else []:
        n = os.path.join(vdir, name, "neta.json")
        if name not in seen and os.path.exists(n):
            x = json.load(open(n, encoding="utf-8"))
            out.append({"work": name, "type": x["type"], "frame": x["frame"], "neta_id": x["id"],
                        "jobs": x.get("jobs", []), "made": x.get("made")})
        elif name not in seen and os.path.exists(os.path.join(vdir, name, "script.json")):
            s = json.load(open(os.path.join(vdir, name, "script.json"), encoding="utf-8"))
            f = json.load(open(os.path.join(vdir, name, "facts.json"), encoding="utf-8"))
            out.append({"work": name, "type": s["type"], "frame": s["frame"], "neta_id": name,
                        "jobs": f.get("順位", {}).get("年収") or [j["表示名"] for j in f.get("職業", [])], "made": s.get("pub_date")})
    return out


def type_ok(t, frame, hist):
    last = [h["type"] for h in hist[-2:]]
    if t == "D" and last == ["D", "D"]:
        return False
    if frame in ("A-1", "A-4") and sum(1 for h in hist[-8:] if h["frame"] in ("A-1", "A-4")) >= 3:
        return False
    return True


def a4_candidates(hist):
    from a4_facts import load, ranks, NEAR
    m = load()[0]["data"]
    since = today() - datetime.timedelta(days=GAP_DAYS)
    recent = [h for h in hist if h["type"] == "A" and (not h.get("made") or str(h["made"]) >= since.isoformat())]
    used_top = {h["jobs"][0] for h in recent if h.get("jobs")}
    used_sets = [set(h.get("jobs", [])) for h in recent]
    res = []
    for g in itertools.combinations(m, 6):
        ns = [x["年収_千円"] for x in g]
        if max(ns) - min(ns) > NEAR:
            continue
        rn, rh = ranks(g, "年収_千円"), ranks(g, "時給に直した額_円")
        moved = sum(1 for k in rn if rn[k] != rh[k])
        if moved < 2:  # 手順書：入れ替わりが2つ以上の組だけ
            continue
        order = sorted(rn, key=rn.get)
        if order[0] in used_top or any(len(set(order) & s) >= 4 for s in used_sets):
            continue
        mx = max(abs(rn[k] - rh[k]) for k in rn)
        res.append((-mx, -sum(abs(rn[k] - rh[k]) for k in rn), max(ns) - min(ns), order))
    res.sort()
    return [r[3] for r in res]


def board(ch):
    p = os.path.join(ROOT, "channels", ch, "ネタ帳.json")
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else []


def pick_from_board(ch, t, hist):
    used = {h.get("neta_id") for h in hist}
    for row in board(ch):
        if row["type"] != t or row["id"] in used or row.get("hold"):
            continue
        if not type_ok(t, row["frame"], hist):
            continue
        ws, we = row.get("window_start"), row.get("window_end")
        if (ws and today().isoformat() < ws) or (we and today().isoformat() > we):
            continue
        cmd = row.get("facts_cmd")
        if not cmd or not os.path.exists(os.path.join(ROOT, "pipeline", cmd[0])):
            continue  # データ待ち
        return row
    return None


def choose(ch, hist):
    want = SEQ[len(hist) % len(SEQ)]
    order = [want] + [t for t in ("D", "A", "B", "C") if t != want]
    hp = os.path.join(ROOT, "history", ch, "type_hold.json")
    hold = json.load(open(hp, encoding="utf-8")) if os.path.exists(hp) else {}
    order.sort(key=lambda t: t in hold)  # 後回しの型は、ほかの型にネタが無い時だけ使う
    last_a = next((h.get("frame") for h in reversed(hist) if h["type"] == "A"), None)
    for t in order:
        if t == "A" and last_a == "A-4":  # 型A の中でも骨組みを続けない：前の A が A-4 なら、ネタ帳の A（A-1・A-3）を先に見る
            row = pick_from_board(ch, t, hist)
            if row:
                return row, want, t
        if t == "A" and type_ok("A", "A-4", hist):
            c = a4_candidates(hist)
            if c:
                names = c[0]
                nid = "a4_" + hashlib.sha1("|".join(sorted(names)).encode()).hexdigest()[:8]
                row = {"id": nid, "title": "・".join(names[:3]) + "…年収を並べたら", "type": "A", "frame": "A-4",
                       "target": "年収が同じくらいの仕事のどれを選ぶか迷っている、20〜40代の会社員",
                       "jobs": names, "facts_cmd": ["a4_facts.py", "make", "{work}", *names]}
                return row, want, t
        row = pick_from_board(ch, t, hist)
        if row:
            return row, want, t
    return None, want, None


def main():
    a = argparse.ArgumentParser()
    a.add_argument("ch")
    a.add_argument("--dry", action="store_true")
    a = a.parse_args()
    hist = done_list(a.ch)
    row, want, got = choose(a.ch, hist)
    if not row:
        sys.exit(f"【止まりました】{a.ch}：作れるネタがありません（型 {want} から全部の型を見た）。在庫で公開をつなぐ")
    n = len(hist) + 1
    slug = re.sub(r"[^0-9a-z_]", "", row["id"].lower())
    work = os.path.join(ROOT, "channels", a.ch, "videos", f"{n:03d}_{slug}")
    neta = {**row, "made": today().isoformat(), "順番の型": want}
    if got != want:
        neta["回した理由"] = f"順番は型{want}だったが、作れるネタが無いか決まりに当たるため型{got}に回した"
    print(json.dumps({k: v for k, v in neta.items() if k != "facts_cmd"}, ensure_ascii=False))
    if a.dry:
        return
    os.makedirs(work, exist_ok=True)
    json.dump(neta, open(os.path.join(work, "neta.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    cmd = [x.replace("{work}", work) for x in row["facts_cmd"]]
    r = subprocess.run([sys.executable, "-X", "utf8", os.path.join(ROOT, "pipeline", cmd[0]), *cmd[1:]])
    if r.returncode != 0 or not os.path.exists(os.path.join(work, "facts.json")):
        sys.exit("【止まりました】facts.json を作れませんでした")
    print(work)


if __name__ == "__main__":
    main()
